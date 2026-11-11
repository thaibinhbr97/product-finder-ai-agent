# Product Finder AI Agent: Build from Scratch Guide

A complete, step-by-step pedagogical tutorial for building a production-grade, conversational AI product finder using the **Google Agent Development Kit (`google-adk`)**, **FastAPI**, **React + Vite + TypeScript**, and **DeepEval**.

---

## Table of Contents

1. [Architecture & Design Philosophy](#1-architecture--design-philosophy)
2. [Project Blueprint & Directory Structure](#2-project-blueprint--directory-structure)
3. [Step 1: Environment Setup & Dependencies](#step-1-environment-setup--dependencies)
4. [Step 2: The Catalog & Pure Deterministic Filter Engine](#step-2-the-catalog--pure-deterministic-filter-engine)
5. [Step 3: Building the Google ADK Agent](#step-3-building-the-google-adk-agent)
6. [Step 4: Building the FastAPI Backend & SSE Streaming](#step-4-building-the-fastapi-backend--sse-streaming)
7. [Step 5: Building the Frontend Control Interface](#step-5-building-the-frontend-control-interface)
8. [Step 6: Automated Agent Evaluation with DeepEval](#step-6-automated-agent-evaluation-with-deepeval)
9. [Step 7: Containerization & Cloud Run Deployment](#step-7-containerization--cloud-run-deployment)
10. [Step 8: Verification, Testing & Debugging Gotchas](#step-8-verification-testing--debugging-gotchas)

---

## 1. Architecture & Design Philosophy

Before writing code, understand the architectural contract:

```
[ User Prompt / Chip Click ]
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                 React + TypeScript Frontend                 │
│  - StageStatusBar (SSE live transition + >1.5s notice)      │
│  - SkeletonGrid (layout-matching skeleton cards)            │
│  - AgentInspector (collapsible tool call telemetry)         │
│  - ConstraintChipsBar (active filter pills + dismiss)       │
│  - ProductGrid (instant client re-render)                   │
└──────────────┬───────────────────────────────▲──────────────┘
               │                               │
    SSE / REST │ HTTP                          │ SSE Events / JSON
               ▼                               │
┌──────────────────────────────────────────────┴──────────────┐
│                    FastAPI Backend Router                   │
│  - POST /api/chat          - POST /api/chat/stream (SSE)    │
│  - POST /api/state         - GET  /api/state/{session_id}   │
│  - GET  /api/products      - GET  /api/health               │
└──────────────┬───────────────────────────────▲──────────────┘
               │                               │
               ▼                               │
┌──────────────────────────────────────────────┴──────────────┐
│                  Google ADK Agent Layer                     │
│  - Runner & InMemorySessionService                          │
│  - ResilientGeminiLlm (failover + quota fallback)           │
│  - Tool: filter_products(tool_context: ToolContext)         │
│    └─► Mutates tool_context.state["active_filters"]         │
└──────────────┬───────────────────────────────▲──────────────┘
               │                               │
               ▼                               │
┌──────────────────────────────────────────────┴──────────────┐
│             Deterministic Filter Engine (Python)            │
│  - Exact category matching (case-insensitive)               │
│  - Substring matching on title + description                │
│  - Inclusive price bounds (min_price, max_price)            │
│  - Source: backend/data/products.json (13 products)         │
└─────────────────────────────────────────────────────────────┘
```

### Why This Architecture?
1. **Deterministic Filtering over Vector Search (RAG)**:
   For structured e-commerce queries with numerical price boundaries ($50) and strict categories (`clothing`), vector embeddings frequently hallucinate or retrieve near-matches outside strict boundaries. Pure Python filtering guarantees 100% mathematical correctness.
2. **Dual-State Synchronization**:
   When the user clicks "×" to dismiss a chip (e.g. removing `max_price`), the frontend updates instantly (0ms latency), and sends `POST /api/state` to update the ADK `session.state["active_filters"]`. The next conversational turn continues seamlessly from this updated state.
3. **Multi-Stage Observability**:
   Instead of a generic spinner, Server-Sent Events (SSE) stream the internal lifecycle stages (`connecting` -> `parsing_intent` -> `executing_tool` -> `rendering`), surfacing real latency and parameters directly to the user.

---

## 2. Project Blueprint & Directory Structure

Organize the repository as follows:

```
product-finder-ai-agent/
├── backend/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application & REST/SSE routes
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── agent.py                # Google ADK Agent & filter_products tool definition
│   │   ├── prompts.py              # Versioned prompt templates (v1, v2, v3)
│   │   ├── resilient_llm.py        # Gemini client with quota failover & fallback
│   │   └── service.py              # ADK Runner & InMemorySessionService wrapper
│   ├── data/
│   │   └── products.json           # Catalog of 13 mock products
│   └── services/
│       ├── __init__.py
│       └── filter_engine.py        # Pure Python filtering logic
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.tsx                 # Root application & state synchronization
│       ├── main.tsx                # React entry point
│       ├── types.ts                # TypeScript interfaces
│       ├── styles.css              # Clean, modern CSS styling
│       ├── api.ts                  # Fetch & SSE client helpers
│       ├── data/
│       │   └── catalog.ts          # Frontend copy of products for 0ms client filter
│       └── components/
│           ├── AgentInspector.tsx   # Part 2: Collapsible tool telemetry drawer
│           ├── ConstraintChipsBar.tsx # Part 2: Filter chip pills with dismiss action
│           ├── ProductGrid.tsx     # Responsive product card grid
│           ├── SkeletonGrid.tsx    # Part 2: Layout-matching skeleton loaders
│           └── StageStatusBar.tsx  # Part 2: Live stage tracker with >1.5s alert
├── evaluation/
│   ├── golden_dataset.json         # 8 diverse test cases (Part 3)
│   ├── eval_suite.py               # DeepEval ExactMatchMetric + GEval suite
│   └── results/                    # Generated test execution logs
├── tests/
│   ├── conftest.py                 # Pytest configuration & path injection
│   ├── test_filter_engine.py       # Unit tests for filtering
│   ├── test_agent_api.py           # Integration tests for FastAPI endpoints
│   ├── test_prompts.py             # Prompt rendering tests
│   └── test_eval_suite.py          # Metric verification tests
├── scripts/
│   └── verify_endpoints.py         # Automated end-to-end verification script
├── Dockerfile                      # Multi-stage build for GCP Cloud Run
├── requirements.txt                # Production backend dependencies
├── requirements-dev.txt            # Dev & evaluation dependencies
├── pytest.ini                      # Pytest runner settings
├── README.md                       # Quickstart documentation
└── EVALUATION.md                   # DeepEval iteration report (v1 vs v2 vs v3)
```

---

## Step 1: Environment Setup & Dependencies

### 1.1 Python Virtual Environment
Initialize Python 3.11:

```bash
python3.11 -m venv venv
source venv/bin/activate
```

### 1.2 `requirements.txt` (Production)
Create `requirements.txt`:
```txt
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
google-adk>=2.14.0
google-genai>=2.34.0
pydantic>=2.8.0
python-dotenv>=1.0.0
httpx>=0.27.0
```

### 1.3 `requirements-dev.txt` (Testing & Evaluation)
Create `requirements-dev.txt`:
```txt
pytest>=8.0.0
pytest-asyncio>=0.23.0
deepeval>=4.3.0
```

Install the dependencies:
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 1.4 Environment Configuration (`.env`)
Create a `.env` file in the root directory:
```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.8-flash
PROMPT_VERSION=v3
PORT=8080
```

---

## Step 2: The Catalog & Pure Deterministic Filter Engine

### 2.1 The 13 Catalog Products (`backend/data/products.json`)
The catalog consists of 13 mock products across 4 categories (`clothing`, `accessories`, `drinkware`, `stationery`):

```json
[
  {"id": 0, "name": "UBC Hoodie", "category": "clothing", "price": 45, "description": "Comfortable cotton blend hoodie with UBC logo"},
  {"id": 1, "name": "UBC Ceramic Mug", "category": "drinkware", "price": 12, "description": "Ceramic coffee mug with school crest"},
  {"id": 2, "name": "Water Bottle", "category": "drinkware", "price": 25, "description": "Insulated stainless steel water bottle"},
  {"id": 3, "name": "Notebook Set", "category": "stationery", "price": 15, "description": "Pack of 3 lined notebooks for note-taking"},
  {"id": 4, "name": "Classic Ballpoint Pen", "category": "stationery", "price": 5, "description": "Smooth writing blue ink pen"},
  {"id": 5, "name": "Heritage Crewneck Sweatshirt", "category": "clothing", "price": 60, "description": "Vintage style crewneck with embroidered lettering"},
  {"id": 6, "name": "Canvas Tote Bag", "category": "accessories", "price": 20, "description": "Durable cotton tote bag for everyday use"},
  {"id": 7, "name": "T-Shirt", "category": "clothing", "price": 15, "description": "Classic cotton crewneck t-shirt"},
  {"id": 8, "name": "UBC Dad Hat", "category": "clothing", "price": 28, "description": "Adjustable cotton cap with embroidered logo"},
  {"id": 9, "name": "Wireless Charging Pad", "category": "accessories", "price": 35, "description": "Fast wireless phone charger"},
  {"id": 10, "name": "Enamel Pin Set", "category": "accessories", "price": 10, "description": "Collector set of 3 metal enamel pins"},
  {"id": 11, "name": "Sticky Notes Multipack", "category": "stationery", "price": 8, "description": "Various sizes of colorful sticky notes"},
  {"id": 12, "name": "Hydro Flask 32oz", "category": "drinkware", "price": 48, "description": "Wide mouth vacuum insulated bottle"}
]
```

### 2.2 The Deterministic Filter Engine (`backend/services/filter_engine.py`)
This engine applies strict, deterministic constraints with normalization:

```python
"""backend/services/filter_engine.py - Pure Python filtering logic."""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

VALID_CATEGORIES = {"clothing", "drinkware", "stationery", "accessories"}

CATEGORY_SYNONYMS = {
    "clothes": "clothing",
    "apparel": "clothing",
    "wear": "clothing",
    "shirt": "clothing",
    "shirts": "clothing",
    "hoodie": "clothing",
    "hat": "clothing",
    "hats": "clothing",
    "mugs": "drinkware",
    "mug": "drinkware",
    "bottle": "drinkware",
    "bottles": "drinkware",
    "cups": "drinkware",
    "drinks": "drinkware",
    "notebook": "stationery",
    "notebooks": "stationery",
    "pen": "stationery",
    "pens": "stationery",
    "paper": "stationery",
    "office": "stationery",
    "school supplies": "stationery",
    "bag": "accessories",
    "bags": "accessories",
    "tote": "accessories",
    "tech": "accessories",
    "electronics": "accessories",
    "pins": "accessories",
}

class FilterEngine:
    def __init__(self, data_path: Optional[Path] = None):
        if data_path is None:
            data_path = Path(__file__).resolve().parent.parent / "data" / "products.json"
        with open(data_path, "r", encoding="utf-8") as f:
            self.products: List[Dict[str, Any]] = json.load(f)

    def filter(
        self,
        category: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        keyword: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        results = list(self.products)

        # 1. Category filter
        if category:
            cat_norm = category.strip().lower()
            resolved = CATEGORY_SYNONYMS.get(cat_norm, cat_norm)
            results = [p for p in results if p.get("category", "").lower() == resolved]

        # 2. Min price (inclusive)
        if min_price is not None:
            results = [p for p in results if float(p.get("price", 0)) >= float(min_price)]

        # 3. Max price (inclusive)
        if max_price is not None:
            results = [p for p in results if float(p.get("price", 0)) <= float(max_price)]

        # 4. Keyword search (case-insensitive substring in name or description)
        if keyword:
            kw = keyword.strip().lower()
            results = [
                p for p in results
                if kw in p.get("name", "").lower() or kw in p.get("description", "").lower()
            ]

        return results
```

---

## Step 3: Building the Google ADK Agent

### 3.1 Prompt Iteration Architecture (`backend/agent/prompts.py`)
DeepEval evaluation requires comparing multiple prompt iterations:
- **`v1` (Baseline)**: Simple system instructions.
- **`v2` (Structured Rules)**: Strict parameter extraction rules and bounds handling.
- **`v3` (Rules + Few-Shot Examples)**: Resolves edge cases like multi-turn state refinement and synonyms.

```python
"""backend/agent/prompts.py - Versioned system prompt definitions."""

SYSTEM_PROMPT_V3 = """You are the Product Finder Assistant for our university campus store.
Your goal is to help students and shoppers find products from our catalog using the `filter_products` tool.

### STRICT RULES:
1. ALWAYS call `filter_products` when the user asks for items, categories, price constraints, or keywords.
2. Only use valid categories: "clothing", "drinkware", "stationery", "accessories".
3. When prices are mentioned:
   - "under $X" or "cheaper than $X" -> max_price=X
   - "above $X" or "at least $X" -> min_price=X
   - "between $X and $Y" -> min_price=X, max_price=Y
4. Subjective terms like "cheap" or "affordable" without an exact dollar amount should be mapped to `keyword`, NOT an invented price!
5. After `filter_products` returns, write a concise, helpful summary naming the matching items and prices. If no products matched, clearly explain that no items matched those criteria.

### EXAMPLES:
User: "Show me clothing under $50"
Tool: filter_products(category="clothing", max_price=50)

User: "Which ones are made of cotton?" (context: category is clothing)
Tool: filter_products(category="clothing", keyword="cotton")
"""

PROMPTS = {
    "v1": "... baseline prompt ...",
    "v2": "... rules prompt ...",
    "v3": SYSTEM_PROMPT_V3,
}
```

### 3.2 Resilience & Free-Tier Quota Handling (`backend/agent/resilient_llm.py`)
Google AI Studio Free Tier limits `gemini-3.8-flash` to **20 requests/day**. Each ADK turn requires 2 calls (tool emission + response generation). 
Subclassing `google.adk.models.google_llm.Gemini` ensures automatic multi-model failover (`gemini-3.8-flash` -> `gemini-3.5-flash` -> `gemini-3.5-flash-lite` -> deterministic fallback):

```python
"""backend/agent/resilient_llm.py - Failover and fallback wrapper."""
from google.adk.models.google_llm import Gemini
from google.genai import types

class ResilientGeminiLlm(Gemini):
    def __init__(self, model: str, api_key: str):
        super().__init__(
            model=model,
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=15000,
                retry_options=types.HttpRetryOptions(attempts=1), # Fail fast on 429
            ),
        )
```

### 3.3 Defining the ADK Tool with `ToolContext` (`backend/agent/agent.py`)
The tool must receive `ToolContext` to write active filters directly to the ADK session state:

```python
"""backend/agent/agent.py - Google ADK Agent & Tool definition."""
from typing import Any, Dict, Optional
from google.adk.agent import Agent
from google.adk.tool import ToolContext
from backend.services.filter_engine import FilterEngine

engine = FilterEngine()

def filter_products(
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    keyword: Optional[str] = None,
    tool_context: Optional[ToolContext] = None,
) -> Dict[str, Any]:
    """Search and filter the store catalog by deterministic constraints."""
    # 1. Update session state for multi-turn conversational persistence
    active_filters = {}
    if category: active_filters["category"] = category
    if min_price is not None: active_filters["min_price"] = min_price
    if max_price is not None: active_filters["max_price"] = max_price
    if keyword: active_filters["keyword"] = keyword

    if tool_context is not None:
        tool_context.state["active_filters"] = active_filters

    # 2. Execute deterministic Python filtering
    matching_products = engine.filter(
        category=category,
        min_price=min_price,
        max_price=max_price,
        keyword=keyword,
    )

    return {
        "status": "success",
        "count": len(matching_products),
        "product_ids": [p["id"] for p in matching_products],
        "products": matching_products,
        "active_filters": active_filters,
    }

def build_agent(prompt_version: str = "v3") -> Agent:
    return Agent(
        name="product_finder",
        instruction=PROMPTS[prompt_version],
        tools=[filter_products],
        model=ResilientGeminiLlm(model="gemini-3.8-flash"),
    )
```

### 3.4 The ADK Runner Service (`backend/agent/service.py`)
Wrap the ADK `Runner` and `InMemorySessionService` to execute conversational turns:

```python
"""backend/agent/service.py - ADK Runner wrapper."""
from google.adk.agent import Agent
from google.adk.agent.session_service import InMemorySessionService
from google.adk.agent.runner import Runner

class AgentService:
    def __init__(self, agent: Agent):
        self.agent = agent
        self.session_service = InMemorySessionService()
        self.runner = Runner(agent=self.agent, session_service=self.session_service)

    async def run_turn(self, session_id: str, message: str) -> Dict[str, Any]:
        # Ensures session exists
        session = await self.session_service.get_or_create(session_id)
        # Execute turn through Google ADK Runner
        result = await self.runner.run(session_id=session_id, user_message=message)
        return result
```

---

## Step 4: Building the FastAPI Backend & SSE Streaming

Implement all required endpoints in `backend/main.py`:

```python
"""backend/main.py - FastAPI application."""
import json
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Any, Dict, Optional

app = FastAPI(title="Product Finder AI Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Health check for Cloud Run
@app.get("/api/health")
def health_check():
    return {"status": "ok", "timestamp": time.time()}

# 2. Product catalog
@app.get("/api/products")
def get_products():
    return engine.products

# 3. Chat turn (synchronous)
class ChatRequest(BaseModel):
    session_id: str
    message: str

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    return await agent_service.run_turn(req.session_id, req.message)

# 4. Chat turn with Server-Sent Events (SSE) (Component 1)
@app.post("/api/chat/stream")
async def chat_stream_endpoint(req: ChatRequest):
    async def event_generator():
        yield f"data: {json.dumps({'stage': 'connecting'})}\n\n"
        yield f"data: {json.dumps({'stage': 'parsing_intent'})}\n\n"
        # Run ADK turn and stream stage changes
        yield f"data: {json.dumps({'stage': 'executing_tool'})}\n\n"
        result = await agent_service.run_turn(req.session_id, req.message)
        yield f"data: {json.dumps({'stage': 'rendering', 'payload': result})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# 5. Interactive State Mutation (Component 4)
class StateSyncRequest(BaseModel):
    session_id: str
    active_filters: Dict[str, Any]

@app.post("/api/state")
async def set_state(req: StateSyncRequest):
    session = await agent_service.session_service.get_or_create(req.session_id)
    session.state["active_filters"] = req.active_filters
    matching = engine.filter(**req.active_filters)
    return {
        "status": "updated",
        "active_filters": req.active_filters,
        "product_ids": [p["id"] for p in matching],
        "products": matching,
    }

@app.get("/api/state/{session_id}")
async def get_state(session_id: str):
    session = await agent_service.session_service.get_or_create(session_id)
    return {
        "session_id": session_id,
        "active_filters": session.state.get("active_filters", {}),
    }
```

---

## Step 5: Building the Frontend Control Interface

Initialize the frontend using React, Vite, and TypeScript:
```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
```

### Component 1: Multi-Stage Live Status Bar (`StageStatusBar.tsx`)
Displays stage indicators (`Connecting` -> `Parsing Intent` -> `Executing Tool` -> `Rendering`) and surfaces a warning if backend processing exceeds 1.5 seconds:

```tsx
// frontend/src/components/StageStatusBar.tsx
import React, { useEffect, useState } from "react";

export type AgentStage = "idle" | "connecting" | "parsing_intent" | "executing_tool" | "rendering";

interface Props {
  stage: AgentStage;
  startTime: number | null;
}

export const StageStatusBar: React.FC<Props> = ({ stage, startTime }) => {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (stage === "idle" || !startTime) { setElapsed(0); return; }
    const timer = setInterval(() => setElapsed(Date.now() - startTime), 100);
    return () => clearInterval(timer);
  }, [stage, startTime]);

  if (stage === "idle") return null;

  return (
    <div className="stage-status-bar">
      <div className="stages-flow">
        <span className={stage === "connecting" ? "active" : ""}>1. Connecting</span>
        <span className={stage === "parsing_intent" ? "active" : ""}>2. Parsing Intent</span>
        <span className={stage === "executing_tool" ? "active" : ""}>3. Executing Tool</span>
        <span className={stage === "rendering" ? "active" : ""}>4. Rendering</span>
      </div>
      {elapsed > 1500 && (
        <div className="cold-start-banner">
          ⚠️ Waking up serverless container... ({Math.round(elapsed / 100) / 10}s)
        </div>
      )}
    </div>
  );
};
```

### Component 1b: Skeleton Grid (`SkeletonGrid.tsx`)
Avoid spinners! Match the final product card layout to prevent layout shift:

```tsx
// frontend/src/components/SkeletonGrid.tsx
import React from "react";

export const SkeletonGrid: React.FC<{ count?: number }> = ({ count = 4 }) => (
  <div className="product-grid skeleton-container">
    {Array.from({ length: count }).map((_, i) => (
      <div key={i} className="product-card skeleton-card">
        <div className="skeleton-line skeleton-title" />
        <div className="skeleton-line skeleton-badge" />
        <div className="skeleton-line skeleton-price" />
        <div className="skeleton-line skeleton-desc" />
      </div>
    ))}
  </div>
);
```

### Component 2: Collapsible Agent Inspector (`AgentInspector.tsx`)
Positioned above the agent's text response, defaulting to collapsed:

```tsx
// frontend/src/components/AgentInspector.tsx
import React, { useState } from "react";
import { ToolCallRecord } from "../types";

export const AgentInspector: React.FC<{ toolCalls: ToolCallRecord[] }> = ({ toolCalls }) => {
  const [isOpen, setIsOpen] = useState(false);
  if (!toolCalls || toolCalls.length === 0) return null;

  return (
    <div className="agent-inspector">
      <button onClick={() => setIsOpen(!isOpen)} className="inspector-toggle">
        {isOpen ? "▼ Hide Agent Telemetry" : "► Inspect Agent Tool Calls"} ({toolCalls.length})
      </button>
      {isOpen && (
        <div className="inspector-content">
          {toolCalls.map((tc, idx) => (
            <div key={idx} className="tool-record">
              <div><strong>Tool:</strong> <code>{tc.name}</code></div>
              <div><strong>Latency:</strong> {tc.latency_ms} ms</div>
              <div><strong>Status:</strong> <span className="status-success">{tc.status}</span></div>
              <pre>{JSON.stringify(tc.parameters, null, 2)}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
```

### Component 3 & 4: Active Constraint Chips & Dual-State Sync
When a chip's `"×"` is clicked:
1. Re-filter local catalog in React (0ms instant UI update).
2. Dispatch `POST /api/state` with updated filters so conversational turns stay in sync:

```tsx
// frontend/src/components/ConstraintChipsBar.tsx
import React from "react";
import { ActiveFilters } from "../types";

interface Props {
  filters: ActiveFilters;
  onDismiss: (key: keyof ActiveFilters) => void;
  onClearAll: () => void;
}

export const ConstraintChipsBar: React.FC<Props> = ({ filters, onDismiss, onClearAll }) => {
  const activeKeys = Object.entries(filters).filter(([_, v]) => v !== undefined && v !== null);
  if (activeKeys.length === 0) return null;

  return (
    <div className="constraint-chips-bar">
      <span className="chips-label">Active Filters:</span>
      {activeKeys.map(([k, v]) => (
        <span key={k} className="filter-chip">
          {k}: {String(v)}
          <button onClick={() => onDismiss(k as keyof ActiveFilters)} title="Remove constraint">×</button>
        </span>
      ))}
      {activeKeys.length > 1 && (
        <button onClick={onClearAll} className="clear-all-btn">Clear All</button>
      )}
    </div>
  );
};
```

---

## Step 6: Automated Agent Evaluation with DeepEval

### 6.1 Creating the Golden Dataset (`evaluation/golden_dataset.json`)
Define at least 8 test cases covering standard queries, edge cases, synonyms, and conversational refinement:

```json
[
  {
    "id": "case_01_category_basic",
    "input": "Show me all clothing items.",
    "expected_filters": {"category": "clothing"},
    "expected_product_ids": [0, 5, 7, 8],
    "expected_summary": "Found 4 clothing items: UBC Hoodie ($45), Heritage Crewneck ($60), T-Shirt ($15), UBC Dad Hat ($28)."
  },
  {
    "id": "case_02_combined_threshold",
    "input": "What clothing items are under $50?",
    "expected_filters": {"category": "clothing", "max_price": 50},
    "expected_product_ids": [0, 7, 8],
    "expected_summary": "Found clothing under $50: UBC Hoodie ($45), T-Shirt ($15), UBC Dad Hat ($28)."
  },
  {
    "id": "case_04_empty_result",
    "input": "Find drinkware over $100.",
    "expected_filters": {"category": "drinkware", "min_price": 100},
    "expected_product_ids": [],
    "expected_summary": "No drinkware products were found over $100."
  },
  {
    "id": "case_07_multiturn_refinement",
    "initial_filters": {"category": "clothing"},
    "input": "Which ones are made of cotton?",
    "expected_filters": {"category": "clothing", "keyword": "cotton"},
    "expected_product_ids": [0, 7, 8],
    "expected_summary": "Found cotton clothing: UBC Hoodie ($45), T-Shirt ($15), UBC Dad Hat ($28)."
  }
]
```

### 6.2 Running DeepEval Metrics (`evaluation/eval_suite.py`)
Use **two** distinct metrics:
1. `ExactMatchMetric`: Deterministic comparison between extracted parameters/IDs and ground truth.
2. `GEval`: LLM-as-a-judge assessing response groundedness (penalizing fabricated prices or hallucinated items).

```python
"""evaluation/eval_suite.py - DeepEval test suite."""
from deepeval.metrics import ExactMatchMetric, GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams

# 1. Exact Match on (Filters + Product IDs)
exact_metric = ExactMatchMetric(threshold=1.0)

# 2. GEval for Groundedness & Constraint Adherence
geval_metric = GEval(
    name="Groundedness & Constraint Adherence",
    criteria="Check that actual_output accurately reflects retrieval_context without inventing items or prices.",
    evaluation_params=[
        SingleTurnParams.INPUT,
        SingleTurnParams.ACTUAL_OUTPUT,
        SingleTurnParams.EXPECTED_OUTPUT,
        SingleTurnParams.RETRIEVAL_CONTEXT,
    ],
    threshold=0.75,
)
```

Run the evaluation:
```bash
python eval_suite.py --prompt-version v3
```

---

## Step 7: Containerization & Cloud Run Deployment

### 7.1 Multi-Stage `Dockerfile`
Build the frontend, then copy static assets to the lightweight Python image:

```dockerfile
# Stage 1: Build Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python Backend Runtime
FROM python:3.11-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PORT=8080

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

EXPOSE 8080

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
```

### 7.2 Deploying to GCP Cloud Run
```bash
gcloud run deploy product-finder-agent \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY="your-api-key",GEMINI_MODEL="gemini-3.8-flash"
```

---

## Step 8: Verification, Testing & Debugging Gotchas

### Critical Gotchas Learned During Development

1. **Google AI Studio Free Tier Quotas**:
   `gemini-3.8-flash` free tier allows only **20 requests/day**. Each ADK turn uses 2 requests (1 to call the tool, 1 to formulate the reply). Implement `ResilientGeminiLlm` with model failover (`gemini-3.5-flash`, `gemini-3.5-flash-lite`) and fallback.
2. **Gemini 3 Deadline Limits**:
   Setting timeouts below 10 seconds triggers `400 INVALID_ARGUMENT: Manually set deadline 8s is too short. Minimum allowed deadline is 10s`. Keep timeouts $\ge 10s$ (e.g. 15,000ms).
3. **Thinking Config in `google-genai`**:
   `thinking_level` is not a top-level parameter on `GenerateContentConfig`. Pass `thinking_config=types.ThinkingConfig(thinking_level="LOW")`.
4. **Pytest Path Resolution**:
   Ensure `pytest.ini` contains `pythonpath = .` and `conftest.py` adds `ROOT_DIR` to `sys.path`.

### Complete Verification Script (`scripts/verify_endpoints.py`)
Run the automated end-to-end test verifying all 8 endpoints:

```bash
python scripts/verify_endpoints.py
```

Expected output:
```
========================================================================
TESTING ALL FASTAPI ENDPOINTS (LIVE GOOGLE ADK + GEMINI)
========================================================================
[1/8] GET /                     -> HTTP 200 | Service metadata
[2/8] GET /api/health           -> HTTP 200 | Health check OK
[3/8] GET /api/products         -> HTTP 200 | 13 catalog items
[4/8] POST /api/chat            -> HTTP 200 | ADK tool call & response
[5/8] POST /api/state           -> HTTP 200 | Mutate filters (active_filters)
[6/8] GET /api/state/{session}  -> HTTP 200 | Verify state persistence
[7/8] POST /api/chat/stream     -> HTTP 200 | Multi-stage SSE streaming
[8/8] POST /api/state/sync      -> HTTP 200 | State reset & sync
========================================================================
ALL 8 API ENDPOINTS VERIFIED SUCCESSFULLY
========================================================================
```
