# Step-by-Step Implementation Guide: Part 1 — Core Agent & Architecture

This guide documents the complete Part 1 implementation using **Google’s Agent Development Kit (`google-adk`)**, deterministic Python filtering, FastAPI SSE streaming, and Docker / GCP Cloud Run deployment.

---

## 1. Architecture Overview

```
Natural Language User Query
            │
            ▼
┌─────────────────────────────────────────────┐
│ FastAPI Backend (backend/main.py)           │
│ - POST /api/chat          (JSON)            │
│ - POST /api/chat/stream   (SSE stages)      │
│ - POST /api/state         (Context Sync)    │
│ - GET  /api/products      (Catalog)         │
│ - GET  /api/health        (Warmup probe)    │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│ Google ADK Runner & Session Service         │
│ (backend/agent/service.py & agent.py)       │
│ - LlmAgent (gemini-3.8-flash)               │
│ - InMemorySessionService (active_filters)   │
│ - FunctionTool: filter_products             │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│ Deterministic Filter Engine                 │
│ (backend/services/filter_engine.py)         │
│ - Pure Python over backend/data/products.json│
│ - Zero vector embeddings / RAG              │
└─────────────────────────────────────────────┘
```

---

## 2. Backend Modules

1. **[`backend/services/filter_engine.py`](file:///Users/bradnguyen/github-repos/product-finder-ai-agent/backend/services/filter_engine.py)**
   - Loads `backend/data/products.json` (13 products across `clothing`, `electronics`, `accessories`, and `groceries`).
   - Validates and normalizes filter dictionaries via `normalize_filters()`.
   - Executes deterministic inclusive price (`min_price <= price <= max_price`), case-insensitive `category`, and `keyword` filtering.

2. **[`backend/agent/prompts.py`](file:///Users/bradnguyen/github-repos/product-finder-ai-agent/backend/agent/prompts.py)**
   - Stores versioned system prompt templates (`v1` baseline, `v2` explicit rules, `v3` rules + few-shot examples) injected with `{active_filters}` from the ADK session state.

3. **[`backend/agent/agent.py`](file:///Users/bradnguyen/github-repos/product-finder-ai-agent/backend/agent/agent.py)**
   - Defines the ADK tool `filter_products(tool_context, category, min_price, max_price, keyword)` which persists applied filters into `tool_context.state["active_filters"]`.
   - Builds the ADK `Agent` with `ThinkingConfig(thinking_level="LOW")` for low-latency tool calling on `gemini-3.8-flash`.

4. **[`backend/agent/service.py`](file:///Users/bradnguyen/github-repos/product-finder-ai-agent/backend/agent/service.py)**
   - Wraps ADK `Runner` and `InMemorySessionService`.
   - Streams granular execution lifecycle events (`connecting` $\rightarrow$ `parsing_intent` $\rightarrow$ `executing_tool` $\rightarrow$ `tool_call` $\rightarrow$ `result`).
   - Synchronizes manual UI filter mutations into ADK session state via `set_filters()` using a state-delta `Event`.

5. **[`backend/main.py`](file:///Users/bradnguyen/github-repos/product-finder-ai-agent/backend/main.py)**
   - Exposes REST and SSE endpoints with CORS enabled for the Agent Control Interface.

---

## 3. Running & Testing Locally

### 3.1 Unit & Integration Tests (No Network Required)
```bash
venv/bin/pytest -q
```

### 3.2 Run FastAPI Server Locally
```bash
venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8080 --reload
```

### 3.3 Run with Docker
```bash
docker build -t product-finder-backend .
docker run --rm -p 8080:8080 --env-file .env product-finder-backend
```

### 3.4 Verify Scenarios with `curl`
```bash
# Category Search ("Show me all clothing items.") -> IDs [0, 5, 7, 8]
curl -s -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "demo-1", "message": "Show me all clothing items."}' | python3 -m json.tool

# Combined Search ("What clothing items are under $50?") -> IDs [0, 7] ($45 Hoodie, $15 T-Shirt)
curl -s -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "demo-2", "message": "What clothing items are under $50?"}' | python3 -m json.tool
```

---

## 4. Deploying to Google Cloud Run

```bash
gcloud auth login
gcloud config set project YOUR_GCP_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

gcloud run deploy product-finder-agent \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY="YOUR_NEW_GEMINI_API_KEY",GEMINI_MODEL="gemini-3.8-flash",PROMPT_VERSION="v3"
```
