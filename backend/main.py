"""FastAPI entrypoint for the Product Finder agent (Cloud Run target)."""

import json
import os
import time
from functools import lru_cache
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

load_dotenv()  # local dev only; Cloud Run / docker pass env vars directly

from backend.agent.service import AgentService  # noqa: E402
from backend.services.filter_engine import filter_engine  # noqa: E402

app = FastAPI(
    title="Product Finder AI Agent API",
    description="Google ADK agent that extracts filters and applies them deterministically.",
    version="2.0.0",
)

_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def get_agent_service() -> AgentService:
    return AgentService()


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2000)


class StateRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    active_filters: Dict[str, Optional[Any]] = Field(default_factory=dict)


@app.get("/")
def root():
    return {"service": "product-finder-agent", "docs": "/docs", "health": "/api/health"}


@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": time.time()}


@app.get("/api/products")
def list_products():
    """Full catalog, used by the UI for instant client-side re-filtering."""
    return {"products": filter_engine.products}


@app.post("/api/chat")
async def chat(req: ChatRequest, service: AgentService = Depends(get_agent_service)):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    try:
        return await service.run_turn(req.session_id, req.message.strip())
    except RuntimeError as exc:
        # Upstream (Gemini) failure: report it honestly instead of faking an answer.
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, service: AgentService = Depends(get_agent_service)):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    async def sse():
        async for item in service.stream_turn(req.session_id, req.message.strip()):
            yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/state")
@app.post("/api/state/sync")
async def sync_state(req: StateRequest, service: AgentService = Depends(get_agent_service)):
    """Syncs UI filter edits (chip dismissals, Clear All) into the agent's session state."""
    try:
        filters = await service.set_filters(req.session_id, req.active_filters)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    products = filter_engine.filter_products(**filters)
    return {
        "status": "SYNCHRONIZED",
        "session_id": req.session_id,
        "active_filters": filters,
        "products": products,
        "product_ids": [p["id"] for p in products],
        "count": len(products),
    }


@app.get("/api/state/{session_id}")
async def get_state(session_id: str, service: AgentService = Depends(get_agent_service)):
    return {"session_id": session_id, "active_filters": await service.get_filters(session_id)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
