# Step-by-Step Implementation Guide: Part 1 — Core Agent & Architecture

This guide provides concrete, step-by-step instructions to implement and deploy the backend service for the **Product Finder AI Agent** as specified in `Product_Finder_AI_Agent.pdf`.

---

## Architecture of Part 1

```
User Query (Natural Language)
            │
            ▼
┌─────────────────────────┐
│     FastAPI Service     │
│       (Cloud Run)       │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ Google ADK / Gemini API │ ──> Extracts: { category: "clothing", max_price: 50.0 }
│  (Tool Call Definition) │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  Deterministic Filter   │ ──> Pure Python logic on products.json
│    (Zero Embeddings)    │     Returns matching product objects
└───────────┬─────────────┘
            │
            ▼
Response to Client (JSON/SSE)
- Extracted tool parameters
- Filtered product list
- Natural language agent summary
- Server latency (ms) & status
```

---

## Step 1: Environment & Project Directory Setup

### 1.1 Create the Directory Layout
Run the following in the repository root:
```bash
mkdir -p backend/data backend/agent backend/services
```

### 1.2 Convert Mock Dataset to JSON
Convert the existing `project.js` mock data into `backend/data/products.json`:
```bash
node -e '
const fs = require("fs");
const data = fs.readFileSync("project.js", "utf8");
// Extract and parse JSON
const json = JSON.parse(data);
fs.writeFileSync("backend/data/products.json", JSON.stringify(json, null, 2));
console.log("Created backend/data/products.json with " + json.length + " products.");
'
```

### 1.3 Create `requirements.txt`
Place the following in `requirements.txt`:
```txt
fastapi>=0.110.0
uvicorn[standard]>=0.28.0
pydantic>=2.6.0
google-genai>=0.1.1
python-dotenv>=1.0.1
httpx>=0.27.0
```

### 1.4 Set Up Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Step 2: Implement the Deterministic Filter Engine

Create `backend/services/filter_engine.py`. This module handles deterministic data filtering with **no vector embeddings or RAG**.

```python
# backend/services/filter_engine.py
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "products.json"

class FilterEngine:
    def __init__(self, data_path: Path = DATA_FILE):
        with open(data_path, "r", encoding="utf-8") as f:
            self.products: List[Dict[str, Any]] = json.load(f)

    def filter_products(
        self,
        category: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        keyword: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Deterministically filters the product dataset based on extracted parameters.
        """
        results = self.products

        # Category Filter (normalized case-insensitive)
        if category:
            cat_lower = category.strip().lower()
            results = [p for p in results if p.get("category", "").lower() == cat_lower]

        # Minimum Price Floor
        if min_price is not None:
            results = [p for p in results if p.get("price", 0) >= min_price]

        # Maximum Price Ceiling
        if max_price is not None:
            results = [p for p in results if p.get("price", 0) <= max_price]

        # Keyword Filter in Name or Description
        if keyword:
            kw = keyword.strip().lower()
            results = [
                p for p in results
                if kw in p.get("name", "").lower() or kw in p.get("description", "").lower()
            ]

        return results

# Singleton instance
filter_engine = FilterEngine()
```

---

## Step 3: Implement Session State Management

Create `backend/services/session_store.py` to maintain multi-turn conversation memory and active filter constraints. This supports Part 2's interactive filter chip mutations.

```python
# backend/services/session_store.py
from typing import Dict, Any, Optional

class SessionStore:
    def __init__(self):
        # Maps session_id to session state
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def get_or_create(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "active_filters": {},
                "history": [],
            }
        return self.sessions[session_id]

    def update_filters(self, session_id: str, new_filters: Dict[str, Any]) -> Dict[str, Any]:
        session = self.get_or_create(session_id)
        # Update or remove filters (if value is None, remove key)
        for k, v in new_filters.items():
            if v is None:
                session["active_filters"].pop(k, None)
            else:
                session["active_filters"][k] = v
        return session["active_filters"]

    def clear_filters(self, session_id: str):
        session = self.get_or_create(session_id)
        session["active_filters"] = {}

session_store = SessionStore()
```

---

## Step 4: Implement Google ADK / Gemini Agent with Function Calling

Create `backend/agent/adk_agent.py`. This uses the official Google GenAI SDK to define the `filter_products` function declaration for deterministic parameter extraction.

```python
# backend/agent/adk_agent.py
import os
import json
import time
from typing import Dict, Any, Tuple
from google import genai
from google.genai import types
from backend.services.filter_engine import filter_engine
from backend.services.session_store import session_store

# Initialize Google GenAI client
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# Define tool schema for deterministic parameter extraction
filter_tool = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="filter_products",
            description="Filters products from the catalog deterministically using exact constraints.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "category": types.Schema(
                        type="STRING",
                        description="Category to filter by. Allowed canonical values: clothing, electronics, groceries, accessories."
                    ),
                    "min_price": types.Schema(
                        type="NUMBER",
                        description="Minimum price floor (e.g., items over $20 -> min_price=20.0)."
                    ),
                    "max_price": types.Schema(
                        type="NUMBER",
                        description="Maximum price ceiling (e.g., items under $50 -> max_price=50.0)."
                    ),
                    "keyword": types.Schema(
                        type="STRING",
                        description="Keyword to search in product name or description (e.g., 'cotton', 'laptop')."
                    ),
                },
            ),
        )
    ]
)

SYSTEM_INSTRUCTION = """You are a helpful, accurate Product Finder AI Agent.
Your job is to parse the user's natural language request and invoke the `filter_products` tool with exact deterministic parameters.
Rules:
1. Always call `filter_products` whenever the user asks for products or specifies categories, prices, or keywords.
2. Canonical categories in the catalog are: 'clothing', 'electronics', 'groceries', 'accessories'. Normalize user input to one of these if applicable.
3. Map phrases like 'under $50' to max_price=50.0, 'at least $20' to min_price=20.0.
4. When summarizing the returned products, strictly report the actual matching products, names, and prices returned by the tool. DO NOT invent or hallucinate items not in the tool result.
5. If no items match, clearly state that no matching products were found in the catalog.
6. Respect active filter constraints from previous turns unless explicitly cleared or overridden by the user.
"""

def run_agent_turn(session_id: str, message: str) -> Dict[str, Any]:
    start_time = time.perf_counter()
    session = session_store.get_or_create(session_id)
    active_filters = session.get("active_filters", {})

    prompt = f"Current active search constraints: {json.dumps(active_filters)}\nUser query: {message}"

    # First turn: Ask LLM with tools
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[filter_tool],
            temperature=0.1,
        ),
    )

    tool_call_meta = {
        "name": None,
        "parameters": {},
        "status": "NO_TOOL_CALLED",
    }
    products = []

    # Check for function call
    if response.function_calls:
        func_call = response.function_calls[0]
        tool_name = func_call.name
        tool_args = dict(func_call.args) if func_call.args else {}

        tool_call_meta["name"] = tool_name
        tool_call_meta["parameters"] = tool_args
        tool_call_meta["status"] = "SUCCESS"

        # Merge new extracted parameters with active filters
        updated_filters = {**active_filters, **tool_args}
        session_store.update_filters(session_id, updated_filters)

        # Deterministic execution
        products = filter_engine.filter_products(**updated_filters)

        # Second turn: Generate natural language response grounded in tool output
        followup_content = [
            prompt,
            response.candidates[0].content,
            types.Content(
                parts=[
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": products, "count": len(products)}
                    )
                ]
            )
        ]

        summary_response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=followup_content,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.2,
            ),
        )
        reply_text = summary_response.text
    else:
        # Fallback if no tool was called
        reply_text = response.text or "I couldn't identify specific product search parameters."
        products = filter_engine.filter_products(**active_filters)

    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
    tool_call_meta["latency_ms"] = latency_ms

    return {
        "reply": reply_text,
        "products": products,
        "tool_call": tool_call_meta,
        "active_filters": session["active_filters"],
        "latency_ms": latency_ms,
    }
```

---

## Step 5: Implement FastAPI Service & Endpoints

Create `backend/main.py`:

```python
# backend/main.py
import os
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional

from backend.agent.adk_agent import run_agent_turn
from backend.services.session_store import session_store
from backend.services.filter_engine import filter_engine

app = FastAPI(
    title="Product Finder AI Agent API",
    description="Backend service for deterministic product filtering using Google ADK / Gemini.",
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

@app.get("/api/health")
def health():
    """Health check endpoint used by Cloud Run and frontend warmup probe."""
    return {"status": "ok", "timestamp": time.time()}

@app.post("/api/chat")
def chat(req: ChatRequest):
    """Processes natural language user search queries."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    try:
        result = run_agent_turn(req.session_id, req.message)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/state/sync")
def sync_state(req: StateSyncRequest):
    """
    Synchronizes manual client filter mutations (e.g., chip dismissals)
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
```

---

## Step 6: Containerization (Docker)

### 6.1 Create `.dockerignore`
```plaintext
venv
__pycache__
*.pyc
.git
.env
node_modules
evaluation
```

### 6.2 Create `Dockerfile`
```dockerfile
# Multi-stage lightweight Python container
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and data
COPY backend/ ./backend/

# Expose port (Cloud Run sets $PORT dynamically)
EXPOSE 8080

# Start Uvicorn server
CMD exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}
```

### 6.3 Test Docker Image Locally
```bash
# Build container image
docker build -t product-finder-backend .

# Run container locally with your Gemini API key
docker run -p 8080:8080 -e GEMINI_API_KEY="your-gemini-api-key" product-finder-backend

# Test in a separate terminal:
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-1", "message": "What clothing items are under $50?"}'
```

---

## Step 7: Deploying to Google Cloud Run

### 7.1 Verify GCP Project & Authenticate
Ensure `gcloud` is logged in and your target project is set:
```bash
gcloud auth login
gcloud config set project YOUR_GCP_PROJECT_ID
gcloud services enable run.googleapis.com artifactregistry.googleapis.com
```

### 7.2 Deploy Directly from Source to Cloud Run
Run the one-step Cloud Run deploy command:
```bash
gcloud run deploy product-finder-backend \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY="your-gemini-api-key"
```

### 7.3 Verify Deployment
Once deployment finishes, `gcloud` outputs your Service URL:
```text
Service [product-finder-backend] revision [product-finder-backend-00001-abc] has been deployed and is serving 100 percent of traffic.
Service URL: https://product-finder-backend-xyz.a.run.app
```

Test the live HTTPS endpoint:
```bash
# Test health check
curl https://product-finder-backend-xyz.a.run.app/api/health

# Test agent query
curl -X POST https://product-finder-backend-xyz.a.run.app/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "live-demo", "message": "Show me all clothing items"}'
```

---

## Step 8: Verification Checklist for Part 1

Before moving to Part 2 (Frontend) and Part 3 (DeepEval), verify each requirement:

| Verification Item | Expected Output | Status |
| :--- | :--- | :--- |
| **Category Query** | `"Show me all clothing items"` $\rightarrow$ category: `"clothing"`, returns IDs `[0, 5, 7, 8]` | [ ] |
| **Combined Query** | `"What clothing items are under $50?"` $\rightarrow$ category: `"clothing"`, max_price: `50.0`, returns IDs `[0, 7]` ($45 Hoodie, $15 T-Shirt), excludes ID `5` ($89 Shoes) and ID `8` ($75 Jacket) | [ ] |
| **Zero Vector Embeddings** | Deterministic Python filter only; no vector search, ChromaDB, FAISS, or Pinecone | [ ] |
| **Containerization** | Dockerfile builds cleanly and runs locally | [ ] |
| **Cloud Run HTTPS** | Publicly accessible HTTPS endpoint serving live requests | [ ] |
