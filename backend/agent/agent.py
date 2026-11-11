"""Google ADK agent definition: one LlmAgent with one deterministic tool.

No multi-agent orchestration, no RAG, no embeddings. The model's only job is
to turn natural language into `filter_products` arguments and to summarize
the tool output.
"""

import json
import os
import time
from typing import Any, Dict, Optional, Union

from google.adk.agents import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models import BaseLlm
from google.adk.tools import ToolContext
from google.genai import types

from backend.agent.prompts import DEFAULT_PROMPT_VERSION, get_prompt_template
from backend.agent.resilient_llm import ResilientGeminiLlm
from backend.services.filter_engine import filter_engine, normalize_filters

STATE_KEY = "active_filters"
DEFAULT_MODEL = "gemini-3.8-flash"


def filter_products(
    tool_context: ToolContext,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    keyword: Optional[str] = None,
) -> Dict[str, Any]:
    """Filters the store catalog deterministically and returns matching products.

    Always pass the COMPLETE set of filters that should apply (existing active
    filters plus any changes from the user's latest message). Omitted
    arguments mean "no constraint".

    Args:
        category: One of: clothing, electronics, accessories, groceries.
        min_price: Inclusive minimum price in dollars.
        max_price: Inclusive maximum price in dollars.
        keyword: Single lowercase word matched against product name and description
            (e.g. "red", "cotton", "laptop").

    Returns:
        A dict with status, the applied filters, the match count and the products.
    """
    start = time.perf_counter()
    try:
        filters = normalize_filters(
            {
                "category": category,
                "min_price": min_price,
                "max_price": max_price,
                "keyword": keyword,
            }
        )
    except ValueError as exc:
        return {
            "status": "error",
            "error": str(exc),
            "latency_ms": round((time.perf_counter() - start) * 1000, 3),
        }

    products = filter_engine.filter_products(**filters)
    # Persist in ADK session state so later turns and the UI see the same constraints.
    tool_context.state[STATE_KEY] = filters

    return {
        "status": "success",
        "applied_filters": filters,
        "count": len(products),
        "products": [
            {
                "id": p["id"],
                "name": p["name"],
                "category": p["category"],
                "price": p["price"],
                "description": p["description"],
            }
            for p in products
        ],
        "latency_ms": round((time.perf_counter() - start) * 1000, 3),
    }


def _make_instruction(prompt_version: str):
    template = get_prompt_template(prompt_version)

    def instruction(ctx: ReadonlyContext) -> str:
        active = ctx.state.get(STATE_KEY) or {}
        return template.format(active_filters=json.dumps(active, sort_keys=True))

    return instruction


def _generate_content_config(model_name: Optional[str]) -> types.GenerateContentConfig:
    config = types.GenerateContentConfig(
        http_options=types.HttpOptions(
            timeout=15000,
            retry_options=types.HttpRetryOptions(
                attempts=1, http_status_codes=[500, 502, 503, 504]
            ),
        ),
    )
    # Gemini 3 models are tuned for the default temperature (1.0); only override if asked.
    if os.environ.get("GEMINI_TEMPERATURE"):
        config.temperature = float(os.environ["GEMINI_TEMPERATURE"])
    # Low thinking keeps tool-call latency down. Set GEMINI_THINKING_LEVEL="" to disable.
    thinking_level = os.environ.get("GEMINI_THINKING_LEVEL", "low").strip()
    if thinking_level and model_name:
        config.thinking_config = types.ThinkingConfig(thinking_level=thinking_level.upper())
    return config


def build_agent(
    model: Union[str, BaseLlm, None] = None,
    prompt_version: Optional[str] = None,
) -> Agent:
    resolved = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    model_name = resolved if isinstance(resolved, str) else None
    llm_model: Union[str, BaseLlm] = (
        ResilientGeminiLlm(model=resolved) if isinstance(resolved, str) else resolved
    )
    prompt_version = prompt_version or os.environ.get("PROMPT_VERSION", DEFAULT_PROMPT_VERSION)
    return Agent(
        name="product_finder",
        description="Finds products in the store catalog from natural language queries.",
        model=llm_model,
        instruction=_make_instruction(prompt_version),
        tools=[filter_products],
        generate_content_config=_generate_content_config(model_name),
    )
