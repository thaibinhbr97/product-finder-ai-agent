# Execution Plan — Product Finder AI Agent

Source of truth: `Product_Finder_AI_Agent.pdf`. Each step lists its **acceptance check**: the step isn't done until the check passes.

## 0. Audit of the existing code (what was wrong)

| Issue | Spec impact | Fix |
| :--- | :--- | :--- |
| Backend used raw `google-genai`, not **Google ADK** | Violates Part 1 ("Build ... using Google's Agent Development Kit") | Rebuild agent on `google.adk` (`Agent`, `Runner`, `InMemorySessionService`, `FunctionTool`) |
| The last version answered mostly with a regex extractor | The LLM no longer did the parameter extraction | The ADK agent extracts parameters through the `filter_products` tool. Regex is removed |
| `resutls` typo dropped the price filters | Wrong results ($89 shoes returned for "under $50") | Fixed. Covered by unit tests |
| No streaming stage events | Part 2 #1 needs real stage events from the server | `POST /api/chat/stream` (SSE) emits `stage` / `tool_call` / `result` events |
| No frontend, eval, or EVALUATION.md | Parts 2 and 3 missing | Build them |
| `__pycache__/*.pyc` committed to git | Hygiene | `git rm --cached` |
| API key was pasted in chat | Security | **Rotate the key in AI Studio** |

## 1. Tools

| Purpose | Tool |
| :--- | :--- |
| Agent framework | `google-adk` (LLM: `gemini-3.8-flash` through the Gemini API, configurable with `GEMINI_MODEL`) |
| API server | FastAPI + Uvicorn, Server-Sent Events |
| Filtering | Pure Python over `backend/data/products.json` (no embeddings, RAG, or multi-agent) |
| Tests | `pytest` (deterministic filter and API tests with a stubbed LLM) |
| Container / hosting | Docker (`python:3.11-slim`), GCP Cloud Run |
| Frontend | React + Vite + TypeScript, plain CSS (no UI library needed) |
| Evaluation | `deepeval` (`ExactMatchMetric` + `GEval`) |

## 2. Data contract (shared by backend, frontend, and eval)

```jsonc
// Filters (all optional)
{ "category": "clothing|electronics|accessories|groceries", "min_price": 0, "max_price": 50, "keyword": "red" }

// POST /api/chat  -> ChatResponse
{ "session_id": "...", "reply": "...", "products": [...], "product_ids": [0,7],
  "active_filters": {...},
  "tool_call": { "name": "filter_products", "parameters": {...}, "status": "success", "latency_ms": 812.4 } | null,
  "latency_ms": 1534.2 }

// POST /api/chat/stream -> SSE events
event: stage     data: {"stage": "connecting" | "parsing_intent" | "executing_tool" | "rendering"}
event: tool_call data: {name, parameters, status, latency_ms}
event: result    data: ChatResponse
event: error     data: {"detail": "..."}

// POST /api/state  { session_id, active_filters } -> { active_filters, products, product_ids }
```

The agent's tool stores the filters it applied in ADK session state (`tool_context.state["active_filters"]`). The `/api/state` endpoint writes the same key. That's how a chip dismissal in the UI reaches later turns (Part 2 #4).

## 3. Steps

### Phase A: Backend core (Part 1.1)
1. `backend/services/filter_engine.py`: deterministic `filter_products(category, min_price, max_price, keyword)`. Inclusive bounds, case-insensitive category, keyword over name and description.
   **Check:** pytest. "clothing ≤ 50" returns ids `{0, 7}`. "clothing" returns `{0, 5, 7, 8}`.
2. `backend/agent/agent.py`: ADK `Agent` with the `filter_products` tool and strict instructions:
   - Always call the tool for product questions, with the full **cumulative** filter set.
   - Read the current filters from session state so follow-ups ("which ones are red?") keep the existing constraints.
   - Answer only from the tool's results.
3. `backend/agent/runner.py`: `Runner` + `InMemorySessionService`. Runs a turn, collects the function call (name, args), the tool's latency, and the final text. Exposes an async generator of stage events.
4. `backend/main.py`: `GET /api/health`, `POST /api/chat`, `POST /api/chat/stream`, `POST /api/state`, CORS.
   **Check:** pytest with the LLM stubbed (no network) covers the routes and the state-sync path.
   **Check (live):** `curl /api/chat` returns ids `[0, 7]` for "What clothing items are under $50?".

### Phase B: Container and Cloud Run (Part 1.2)
5. `Dockerfile` + `.dockerignore`. **Check:** `docker build` and `docker run`, then curl the health and chat routes.
6. Deploy (user runs this; `gcloud` isn't installed on this machine):
   ```bash
   gcloud run deploy product-finder-agent --source . --region us-central1 \
     --allow-unauthenticated --set-env-vars GEMINI_API_KEY=...,GEMINI_MODEL=gemini-3.8-flash
   ```
   **Check:** curl the public HTTPS URL.

### Phase C: Agentic Control Interface (Part 2)
7. Scaffold `frontend/` (Vite React TS). `VITE_API_URL` points to the local backend or Cloud Run.
8. **Live status + skeleton:** consume the SSE stage events. Show a stage badge with progress steps and a skeleton grid with the same dimensions as the product cards (no spinners). Show the "Waking up serverless container..." notice when the request passes 1.5 s.
9. **Agent Inspector:** collapsed by default, placed above the agent's reply. Shows tool name, parameters as a key/value table, latency (ms), and status.
10. **Constraint chips:** one chip per active filter, each with a dismiss ×, plus "Clear all" when there are 2 or more.
11. **State mutation + sync:** dismissing a chip re-filters the grid on the client right away, then `POST /api/state` updates the ADK session state so the next turn respects it.
    **Check:** `npm run build` passes. Manual flow from the PDF: "Show me clothing under $50" → dismiss Max Price → grid shows all 4 clothing items → "Which ones are red?" runs with only category=clothing.

### Phase D: Evaluation (Part 3)
12. `evaluation/golden_dataset.json`: at least 5 cases (we use 10). Covers category only, combined, range, empty result, synonyms ("tech", "food"), "cheap" with no number, implied category from a product name, out-of-catalog requests, and multi-turn follow-ups.
13. `evaluation/eval_suite.py`: calls the **live** API (`--base-url`). Metrics:
    - `ExactMatchMetric`: sorted product-id set compared with the ground truth.
    - `GEval` (judge = Gemini through DeepEval's `GeminiModel`): checks faithfulness to the returned products and constraints, with no invented items.
14. Run the baseline, then 2 or more iterations (system-prompt rules, few-shot examples, schema descriptions). Record the scores in `EVALUATION.md`: best change, worst change, drift insights.
    **Check:** the baseline is under 100%, and the numbers come from real runs.

## 4. What only the user can do
- Rotate the leaked Gemini API key and put the new one in `.env`.
- Install `gcloud`, authenticate, and run the Cloud Run deploy.
- Run the eval suite against the live LLM (it needs network access and API quota). Then fill in `EVALUATION.md` from the real output.
