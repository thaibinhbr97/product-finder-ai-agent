# Product Finder AI Agent

A full-stack natural language Product Finder AI Agent built with **Google’s Agent Development Kit (`google-adk`)**, **FastAPI**, **React + Vite + TypeScript**, and **DeepEval**, packaged for serverless deployment on **GCP Cloud Run**.

---

## Architecture & Key Features

### Part 1: Core Agent & Backend Architecture (`backend/`)
- **Google ADK Integration**: Built on `google.adk` (`Agent`, `Runner`, `InMemorySessionService`) using `gemini-3.8-flash` (`ThinkingConfig(thinking_level="LOW")`).
- **Deterministic Parameter Extraction**: The LLM never selects products directly. It extracts structured filter parameters (`category`, `min_price`, `max_price`, `keyword`) and invokes the `filter_products` tool, which executes pure Python filtering over [`backend/data/products.json`](file:///Users/bradnguyen/github-repos/product-finder-ai-agent/backend/data/products.json) (no vector embeddings, no RAG, no multi-agent orchestration).
- **Real-Time SSE Streaming & Context Sync**:
  - `POST /api/chat/stream`: Streams Server-Sent Events (`stage`, `tool_call`, `result`) for live UI lifecycle tracking.
  - `POST /api/chat`: Standard JSON chat endpoint.
  - `POST /api/state` (and `/api/state/sync`): Synchronizes manual UI filter mutations directly into the ADK session state (`active_filters`) without an LLM call.

### Part 2: Agentic Control Interface (`frontend/`)
1. **Multi-Stage Live Status & Skeleton Loader** ([`StageStatusBar.tsx`](file:///Users/bradnguyen/github-repos/product-finder-ai-agent/frontend/src/components/StageStatusBar.tsx), [`SkeletonGrid.tsx`](file:///Users/bradnguyen/github-repos/product-finder-ai-agent/frontend/src/components/SkeletonGrid.tsx)):
   - Cycles through `Connecting / Warming` $\rightarrow$ `Parsing Intent` $\rightarrow$ `Executing Tool` $\rightarrow$ `Rendering`.
   - Displays an explicit cold-start notification (`"Waking up serverless container..."`) whenever backend execution exceeds `1.5s`.
   - Renders an animated skeleton card grid matching the exact dimensions of the product cards (zero circular spinners).
2. **Collapsible Tool Call Log (Agent Inspector)** ([`AgentInspector.tsx`](file:///Users/bradnguyen/github-repos/product-finder-ai-agent/frontend/src/components/AgentInspector.tsx)):
   - Positioned directly above the agent's text response and defaults to **collapsed**.
   - Displays `Tool Name` (`filter_products`), structured `Extracted Parameters`, `Round-Trip & Server Latency (ms)`, and `Execution Status` (`HTTP 200 · SUCCESS`).
3. **Active Constraint Chips Bar** ([`ConstraintChipsBar.tsx`](file:///Users/bradnguyen/github-repos/product-finder-ai-agent/frontend/src/components/ConstraintChipsBar.tsx)):
   - Renders dismissible badges above the product grid for every active constraint (`Category: Clothing`, `Max Price: $50`, etc.) plus a single-click `"Clear All"` action when multiple filters are active.
4. **Interactive State Mutation & Context Synchronization** ([`App.tsx`](file:///Users/bradnguyen/github-repos/product-finder-ai-agent/frontend/src/App.tsx)):
   - Dismissing a chip immediately updates the product grid on the client (0ms) and sends a state synchronization payload (`POST /api/state`) to the backend ADK session so follow-up conversational turns respect the mutated constraints.

### Part 3: Automated Agent Evaluation (`evaluation/`)
- **Golden Dataset**: [`golden_dataset.json`](file:///Users/bradnguyen/github-repos/product-finder-ai-agent/golden_dataset.json) (8 diverse prompts covering edge cases, synonyms, empty results, inclusive bounds, and multi-turn state mutations).
- **DeepEval Test Suite**: [`eval_suite.py`](file:///Users/bradnguyen/github-repos/product-finder-ai-agent/eval_suite.py) implementing both `ExactMatchMetric` (deterministic filter & product ID verification) and `GEval` (LLM-as-a-Judge response faithfulness and constraint adherence).
- **Iterative Optimization Report**: Documented in [`EVALUATION.md`](file:///Users/bradnguyen/github-repos/product-finder-ai-agent/EVALUATION.md).

---

## Quick Start

### 1. Backend Setup
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt

# Configure your Gemini API key in .env
echo 'GEMINI_API_KEY="YOUR_GEMINI_API_KEY"' > .env

# Run unit & integration tests (26 tests, no network required)
venv/bin/pytest -q

# Start the FastAPI server on http://localhost:8080
venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8080 --reload
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173). You can switch the **Backend Endpoint** in the top-right header between `http://localhost:8080` and your deployed Cloud Run URL at any time.

### 3. Docker Build & Run
```bash
docker build -t product-finder-backend .
docker run --rm -p 8080:8080 --env-file .env product-finder-backend
```

### 4. Deploy to Google Cloud Run
```bash
gcloud auth login
gcloud config set project YOUR_GCP_PROJECT_ID

gcloud run deploy product-finder-agent \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY="YOUR_GEMINI_API_KEY",GEMINI_MODEL="gemini-3.8-flash",PROMPT_VERSION="v3"
```

### 5. Run DeepEval Suite
```bash
# Evaluate against running backend (or in-process ADK agent)
venv/bin/python eval_suite.py

# Run all 3 prompt optimization iterations (v1, v2, v3)
venv/bin/python eval_suite.py --all-iterations
```
