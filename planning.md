# Comprehensive Project Plan: Product Finder AI Agent

This planning document outlines the complete roadmap, architectural design, technology stack, and step-by-step implementation guide for the **Product Finder AI Agent** assignment as specified in `Product_Finder_AI_Agent.pdf`.

---

## 1. Project Overview & Objectives

The goal is to develop a production-ready, full-stack AI agent that processes natural language search queries to find products from a mock dataset using **deterministic parameter extraction and tool execution**, provides an **Agentic Control Interface** with real-time state visualization and bidirectional context synchronization, and is verified via an automated **DeepEval evaluation pipeline**.

### Core Constraints & Key Principles
- **No Vector Embeddings / No RAG / No Multi-Agent Orchestration**: Filter logic must be deterministic Python code triggered by structured tool parameters extracted from the LLM.
- **Agentic Frontend (Not a Simple Chatbox)**: Advanced UI components exposing execution lifecycle, cold starts, collapsible tool call inspector, dynamic constraint chips, and immediate client-side mutation synchronized with backend conversation memory.
- **Cloud Run Deployment**: Containerized backend hosted serverless on Google Cloud Platform with public HTTPS access.
- **DeepEval Rigor**: Golden dataset covering edge cases, deterministic and LLM-as-a-judge metrics, with at least 2 optimization iterations documented in `EVALUATION.md`.

---

## 2. Technology Stack & Tools Used

| Layer | Tool / Technology | Version / Specification | Purpose |
| :--- | :--- | :--- | :--- |
| **Backend Framework** | **FastAPI** + **Uvicorn** | Python 3.11+, FastAPI `>=0.110` | High-performance asynchronous API, Server-Sent Events (SSE) streaming, state management. |
| **Agent / LLM Framework** | **Google GenAI / ADK** (`google-genai` or `google-cloud-aiplatform`) | Gemini 1.5 Flash / Pro | Function calling / tool parameter extraction (`filter_products`), structured intent parsing. |
| **Dataset & Storage** | **In-memory JSON** (`products.json` from `project.js`) | Pure Python filtering logic | Deterministic category, price ceiling/floor, and keyword filtering. |
| **Containerization** | **Docker** | Multi-stage `python:3.11-slim` | Portable, reproducible production container image. |
| **Cloud Hosting** | **GCP Cloud Run** | Serverless Container | Fully managed HTTPS endpoint, automatic scaling, cold-start handling. |
| **Frontend Framework** | **React** + **Vite** + **TypeScript** | React 18+, Vite 5+, TS | Fast, modular, type-safe Agentic Control Interface. |
| **Styling & Icons** | **Tailwind CSS** + **Lucide React** | Tailwind v3+, Lucide icons | Modern, responsive styling for skeleton grids, chips, and accordions. |
| **Evaluation Framework** | **DeepEval** (`deepeval`) | DeepEval `>=1.0` | Automated testing using `ExactMatchMetric` and `GEval` / `AnswerRelevancyMetric`. |
| **Evaluation Reporting** | **Markdown** (`EVALUATION.md`) | Structured analysis | Tracking baseline vs. iteration metric scores and evaluation drift. |

---

## 3. System Architecture & Component Design

```
                     ┌────────────────────────────────────────────────────────┐
                     │              Agentic Frontend (React + Vite)           │
                     │  - Multi-Stage Status (SSE) & Skeleton Loader (>1.5s)  │
                     │  - Collapsible Agent Inspector (Tool, Latency, Status) │
                     │  - Active Constraint Chips Bar (Dismiss & Clear All)  │
                     │  - Instant Client Mutation + Context Sync              │
                     └──────────────────────────┬─────────────────────────────┘
                                                │
                          HTTP / SSE (Streaming & State Sync)
                                                │
                                                ▼
                     ┌────────────────────────────────────────────────────────┐
                     │          FastAPI Backend Service (GCP Cloud Run)       │
                     │  - POST /api/chat (SSE Stream or JSON Response)        │
                     │  - POST /api/state/sync (Mutate Active Session State)  │
                     │  - GET /api/health (Warmup & Health Check)             │
                     └──────────┬─────────────────────────────────┬───────────┘
                                │                                 │
             Tool Call Extraction                               Deterministic Execution
                                ▼                                 ▼
                     ┌──────────────────────┐        ┌────────────────────────┐
                     │   Google ADK / LLM   │        │ Deterministic Engine   │
                     │   (Gemini Tool Use)  │        │ (products.json Filter) │
                     └──────────────────────┘        └────────────────────────┘
```

---

## 4. Target Repository Directory Structure

```plaintext
product-finder-ai-agent/
├── Product_Finder_AI_Agent.pdf       # Original specification
├── README.md                         # Project documentation and walkthrough
├── planning.md                       # This comprehensive planning roadmap
├── Dockerfile                        # Multi-stage container definition
├── .dockerignore                     # Docker build exclusions
├── requirements.txt                  # Python production dependencies
├── requirements-dev.txt              # Testing & eval dependencies (deepeval, pytest)
│
├── backend/                          # FastAPI Service
│   ├── __init__.py
│   ├── main.py                       # FastAPI entrypoint, routes, SSE endpoints
│   ├── config.py                     # Environment variables, Gemini API keys
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── adk_agent.py              # Google ADK / Gemini tool declaration & prompt
│   │   └── prompts.py                # System instructions & few-shot examples
│   ├── services/
│   │   ├── __init__.py
│   │   ├── filter_engine.py          # Deterministic filtering logic on dataset
│   │   └── session_store.py          # Conversation memory & active constraint state
│   └── data/
│       └── products.json             # Mock dataset (converted from project.js)
│
├── frontend/                         # React + Vite + TypeScript Frontend
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── src/
│   │   ├── App.tsx                   # Main layout and orchestrator
│   │   ├── types/
│   │   │   └── index.ts              # Type definitions (Product, FilterState, ToolLog)
│   │   ├── components/
│   │   │   ├── MultiStageStatus.tsx  # Stage indicator & >1.5s cold-start alert
│   │   │   ├── SkeletonGrid.tsx      # Skeleton card grid placeholder
│   │   │   ├── AgentInspector.tsx    # Collapsible tool call & latency viewer
│   │   │   ├── ConstraintChips.tsx   # Active filter badges with dismiss & clear
│   │   │   ├── ProductGrid.tsx       # Rendered products with image & pricing
│   │   │   └── ChatInput.tsx         # Search prompt input box
│   │   └── services/
│   │       └── api.ts                # API client with SSE & state mutation calls
│
└── evaluation/                       # Automated DeepEval Pipeline
    ├── golden_dataset.json           # At least 5 edge-case test queries with ground truths
    ├── eval_suite.py                 # DeepEval test suite (ExactMatch + GEval)
    └── EVALUATION.md                 # Baseline vs Iteration 1 & 2 results and insights
```

---

## 5. Step-by-Step Implementation Guide

### Phase 1: Data Setup & Deterministic Filter Engine
1. **Extract Mock Data**:
   - Convert `project.js` into clean `backend/data/products.json`.
   - Validate schema: `id`, `name`, `category`, `description`, `price`, `image`.
2. **Implement `filter_engine.py`**:
   - Function signature:
     ```python
     def filter_products(
         category: Optional[str] = None,
         min_price: Optional[float] = None,
         max_price: Optional[float] = None,
         keyword: Optional[str] = None
     ) -> list[dict]:
     ```
   - Normalization: Case-insensitive category matching (`clothing`, `electronics`, `groceries`, `accessories`).
   - Boundary checks: Inclusive price range (`min_price <= item.price <= max_price`).
   - Pure deterministic logic: Ensure zero embedding/vector operations.

### Phase 2: Google ADK / Agent Logic & Parameter Extraction
1. **Define Tool Specification**:
   - Declare `filter_products` tool for the Gemini / Google ADK model with precise schema descriptions for `category`, `min_price`, `max_price`, and `keyword`.
2. **Conversation Context & State Management (`session_store.py`)**:
   - Store conversation turn history per `session_id`.
   - Store current accumulated search constraints (e.g. `{"category": "clothing", "max_price": 50.0}`).
   - Support manual override/dismissal of specific constraints via state mutation endpoint.
3. **Prompt Engineering (`prompts.py`)**:
   - Set strict system instructions:
     - Always call `filter_products` when the query contains product intent.
     - Extract implicit and explicit numerical thresholds (e.g., "under $50" -> `max_price=50.0`).
     - Map natural phrases to canonical categories.
     - Generate clear, truthful natural language summaries based only on the returned results.

### Phase 3: FastAPI Backend & Streaming API
1. **Endpoints**:
   - `POST /api/chat`: Accepts `{ session_id, message }`. Streams execution events via Server-Sent Events (SSE) or returns structured response:
     - Events: `STAGE_CONNECTING`, `STAGE_PARSING`, `STAGE_EXECUTING_TOOL`, `STAGE_RENDERING`.
     - Final payload: `{ reply, products, tool_call: { name, params, latency_ms, status }, active_filters }`.
   - `POST /api/state/sync`: Accepts `{ session_id, active_filters }`. Re-filters products deterministically without calling LLM and updates session memory.
   - `GET /api/health`: Health probe for container warmup.
2. **Latency Tracking**:
   - Measure high-resolution wall-clock time (`time.perf_counter()`) for the LLM call and overall tool execution to pass to the frontend inspector.

### Phase 4: Containerization & Cloud Run Deployment
1. **Dockerfile**:
   - Multi-stage or optimized `python:3.11-slim` build.
   - Expose `$PORT` (default 8080) and run via `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`.
2. **GCP Cloud Run Deploy**:
   - Configure gcloud CLI: `gcloud config set project <PROJECT_ID>`.
   - Deploy: `gcloud run deploy product-finder-agent --source . --region <REGION> --allow-unauthenticated`.
   - Verify public HTTPS endpoint and cold-start latency behavior.

### Phase 5: Agentic Control Interface (Frontend)
1. **Component 1: Multi-Stage Live Status & Skeleton Loader**:
   - Display dynamic badges cycling: *Connecting / Warming* -> *Parsing Intent* -> *Executing Tool* -> *Rendering*.
   - Start a client-side timer upon request submission; if execution > 1.5s, render explicit notification: *"Waking up serverless container..."*.
   - Replace circular spinners with animated CSS skeleton card grid matching target product card geometry.
2. **Component 2: Collapsible Tool Call Log (Agent Inspector)**:
   - Accordion component placed above the agent's textual response.
   - Default state: Collapsed.
   - Expanded state: Clean key-value formatted view displaying:
     - `Tool Name`: `filter_products`
     - `Extracted Parameters`: category, min_price, max_price, keywords
     - `Latency`: Total server round-trip in ms
     - `Execution Status`: HTTP 200 / Success
3. **Component 3: Active Constraint Chips Bar**:
   - Positioned directly above the product results grid.
   - Individual badges for each active constraint (e.g., `Category: Clothing` `[X]`, `Max Price: $50` `[X]`).
   - "Clear All" action button visible when $\ge 1$ filters are active.
4. **Component 4: Interactive State Mutation & Context Synchronization**:
   - Clicking `[X]` on a chip immediately updates the client-side product grid without prompting the LLM.
   - Sends background sync payload to `POST /api/state/sync` with updated filters.
   - Subsequent user conversational prompts (e.g., "Which ones are red?") inherit the updated context without reapplying deleted constraints.

### Phase 6: Automated Evaluation with DeepEval
1. **Construct `golden_dataset.json`**:
   - Minimum 5 diverse test queries covering edge cases:
     1. *Category Only*: "Show me all clothing items"
     2. *Price Ceiling*: "What clothing items are under $50?"
     3. *Price Range*: "Find electronics between $50 and $300"
     4. *Empty Result / Edge Case*: "Show me groceries over $100" (returns empty list)
     5. *Multi-turn Mutation / Negation*: "Show me items that are not electronics under $20"
2. **Implement `eval_suite.py`**:
   - **Deterministic Metric**: `ExactMatchMetric` (or custom assertion) checking that extracted parameters (`category`, `max_price`) match ground truth values and/or return expected product IDs (`[0, 7]`).
   - **LLM-Based Evaluation Metric**: `GEval` checking response faithfulness and constraint adherence ("Assess whether the agent's summary accurately reflects the retrieved product prices and categories without inventing details").
3. **Iterative Optimization & `EVALUATION.md`**:
   - Run **Baseline Evaluation** and record metric scores and pass rates.
   - **Iteration 1**: Refine system instructions and tool parameter descriptions (e.g. strict type casting, handling currency symbols).
   - **Iteration 2**: Add few-shot examples or fallback logic for negative constraints / edge conditions.
   - Document metrics, best-performing change, worst-performing change, and analysis of LLM evaluation drift in `EVALUATION.md`.

---

## 6. Edge Cases & Mitigation Strategies

| Edge Case | Risk | Mitigation Strategy |
| :--- | :--- | :--- |
| **Cloud Run Cold Start (> 1.5s)** | User feels UI is frozen or hanging | Multi-stage status listener triggers warning banner *"Waking up serverless container..."* after 1500ms; skeleton grid keeps layout stable. |
| **Empty Filter Results** | Agent might hallucinate non-existent items | Tool returns empty list `[]`; system prompt mandates agent reply: "No products found matching those criteria" rather than suggesting made-up products. |
| **Conflicting Constraints** | User specifies "min $100 and under $50" | Filter engine validates `min_price <= max_price`; returns empty list or prompts user for clarification. |
| **Manual Chip Dismissal vs. Next Prompt** | Agent forgets manual deletions in follow-up queries | Active filters are statefully preserved in backend session store and sent alongside conversation history in every turn. |
| **Overly High Initial Eval Pass Rate** | Assignment requires initial agent < 100% | Use strict evaluation criteria in GEval (penalize extraneous formatting, verify strict grounding) and add difficult linguistic edge cases to `golden_dataset.json`. |

---

## 7. Deliverables Checklist

- [ ] **Backend**:
  - [ ] `backend/data/products.json` generated from `project.js`.
  - [ ] Deterministic `filter_products` logic implemented in Python.
  - [ ] Google ADK / Gemini tool integration with structured parameter extraction.
  - [ ] REST / SSE endpoints (`/api/chat`, `/api/state/sync`, `/api/health`).
- [ ] **Frontend**:
  - [ ] Animated skeleton card grid loader matching final product grid.
  - [ ] Dynamic multi-stage status indicator with >1.5s cold-start notification.
  - [ ] Collapsible Agent Inspector displaying tool name, parameters, latency, status.
  - [ ] Active Constraint Chips with dismiss (`X`) and "Clear All" functionality.
  - [ ] Bidirectional state synchronization between frontend chip dismissals and backend session.
- [ ] **Deployment**:
  - [ ] Clean `Dockerfile` configured for Cloud Run.
  - [ ] Deployed public HTTPS Cloud Run service.
- [ ] **Evaluation**:
  - [ ] `evaluation/golden_dataset.json` with $\ge 5$ edge-case test cases.
  - [ ] `evaluation/eval_suite.py` with `ExactMatchMetric` and `GEval`.
  - [ ] Baseline, Iteration 1, and Iteration 2 executed.
  - [ ] `EVALUATION.md` documenting metrics, best/worst changes, and LLM drift insights.
