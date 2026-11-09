import os
import time
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.agent.adk_agent import run_agent_turn
from backend.services.filter_engine import filter_engine
from backend.services.session_store import session_store

app = FastAPI(
    title="Product Finder AI Agent API",
    description="Backend service for deterministic product filter using Google ADK / Gemini.",
    version="1.0.0",
)

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    session_id: str
    message: str

class StateSyncRequest(BaseModel):
    session_id: str
    active_filters: Dict[str, Any]

@app.get("/")
def root():
    return {
        "message": "Product Finder AI Agent API is running.",
        "docs": "/docs",
        "health": "/api/health"
    }    

@app.get("/api/health")
def health():
    """Health check endpoint used by Cloud Run and frontend wrapup probe.
    """
    return {"status": "ok", "timestamp": time.time()}

@app.post("/api/chat")
def chat(req: ChatRequest):
    """Processes natural language user search queries."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    print(f"\n[API] Incoming /api/chat request for session '{req.session_id}': \"{req.message}\"", flush=True)
    try:
        result = run_agent_turn(req.session_id, req.message)
        print(f"[API] Successfully processed in {result.get('latency_ms')}ms with {len(result.get('products', []))} products", flush=True)
        return result
    except Exception as e:
        import traceback
        print(f"[API ERROR] {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/api/state/sync")
def sync_state(req: StateSyncRequest):
    """
    Syncronizes manual client filter mutation (e.g., chip dismissals)
    with the backend session memory and returns re-filtered products immediately.
    """
    session = session_store.get_or_create(req.session_id)
    session["active_filters"] = req.active_filters
    products = filter_engine.filter_products(**req.active_filters)
    return {
        "status": "SYNCHRONIZED",
        "active_filters": req.active_filters,
        "products": products,
        "count": len(products),
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
