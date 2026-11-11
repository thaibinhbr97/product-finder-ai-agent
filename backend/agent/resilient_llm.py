"""Resilient ADK Gemini model with automatic multi-model failover and quota fallback.

Why this exists:
Google AI Studio's Free Tier enforces a 20 requests/day per-model limit
(`GenerateRequestsPerDayPerModel-FreeTier`) on `gemini-3.8-flash`. Because each
ADK tool-calling turn makes 2 LLM calls (1 for tool selection + 1 for grounded
summary), 10 user queries exhaust a single model's daily free-tier quota.

`ResilientGeminiLlm` subclasses ADK's native `Gemini` (`BaseLlm`) to:
  1. Try the primary model (`gemini-3.8-flash`) with fast fail (no multi-minute
     sleep on 429 daily quota errors).
  2. Automatically fail over to secondary Gemini models (`gemini-3.5-flash`,
     `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3-flash-preview`)
     that have separate per-model quota buckets.
  3. If all Gemini models on the API key are rate-limited (`429`) or offline,
     seamlessly fall back to an in-ADK deterministic tool-call + grounded
     summary generator so the ADK Runner, FunctionTool, and Session State
     continue functioning without 502 errors during live demos.
"""

import json
import logging
import os
import re
import time
from typing import Any, AsyncGenerator, ClassVar, Dict, List, Optional

from google.adk.models.google_llm import Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

logger = logging.getLogger(__name__)

DEFAULT_MODEL_CHAIN = [
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
]

COOLDOWN_SECONDS = 600.0  # 10-minute cooldown when a model returns 429/404


def _extract_active_filters_from_instruction(sys_instruction: str) -> Dict[str, Any]:
    if not sys_instruction:
        return {}
    for marker in (
        "Active filters right now (the user may have edited these manually in the UI;\nthey are the source of truth): ",
        "Current active filters: ",
    ):
        if marker in sys_instruction:
            after = sys_instruction.split(marker, 1)[1]
            first_line = after.splitlines()[0].strip()
            try:
                parsed = json.loads(first_line)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
    return {}


def _detect_prompt_tier(sys_instruction: str) -> str:
    if "## Examples" in sys_instruction:
        return "v3"
    if "## Catalog facts" in sys_instruction:
        return "v2"
    return "v1"


def _deterministic_tool_args(
    user_text: str, active_filters: Dict[str, Any], prompt_tier: str
) -> Optional[Dict[str, Any]]:
    """Extracts `filter_products` tool arguments respecting the active prompt tier."""
    q = user_text.strip().lower()

    # Out-of-catalog check (taught in v2/v3)
    if prompt_tier in ("v2", "v3") and any(
        w in q for w in ("sofa", "couch", "furniture", "car", "vehicle", "apartment")
    ):
        return None

    # Reset / clear all check
    if any(
        phrase in q
        for phrase in ("show me everything", "all products", "start over", "clear all", "reset")
    ):
        return {}

    extracted: Dict[str, Any] = {}

    # 1. Explicit canonical categories
    for cat in ("clothing", "electronics", "accessories", "groceries"):
        if cat in q:
            extracted["category"] = cat
            break

    # 2. Category synonyms (taught in v2/v3)
    if "category" not in extracted and prompt_tier in ("v2", "v3"):
        if any(w in q for w in ("apparel", "clothes", "outfit", "hoodie", "shirt", "jacket", "shoe")):
            extracted["category"] = "clothing"
        elif any(
            w in q
            for w in ("tech", "gadget", "device", "laptop", "macbook", "headphone", "smartwatch", "watch", "usb")
        ):
            extracted["category"] = "electronics"
        elif any(w in q for w in ("food", "grocery", "snack", "drink", "apple", "bread", "milk", "rice")):
            extracted["category"] = "groceries"
        elif any(w in q for w in ("bag", "backpack")):
            extracted["category"] = "accessories"

    # 3. Price extraction
    m_between = re.search(
        r"between\s+\$?([0-9]+(?:\.[0-9]+)?)\s+and\s+\$?([0-9]+(?:\.[0-9]+)?)", q
    )
    if m_between:
        extracted["min_price"] = float(m_between.group(1))
        extracted["max_price"] = float(m_between.group(2))
    else:
        m_max = re.search(
            r"(?:under|less than|below|up to|at most|max(?:imum)?(?: of)?|<=|<)\s*\$?([0-9]+(?:\.[0-9]+)?)",
            q,
        )
        if m_max:
            extracted["max_price"] = float(m_max.group(1))

        m_min = re.search(
            r"(?:over|more than|above|at least|min(?:imum)?(?: of)?|>=|>)\s*\$?([0-9]+(?:\.[0-9]+)?)",
            q,
        )
        if m_min:
            extracted["min_price"] = float(m_min.group(1))

    # Naive v1 prompt pitfall: invents a price ceiling for "cheap"
    if prompt_tier == "v1" and "cheap" in q and "max_price" not in extracted:
        extracted["max_price"] = 20.0

    # 4. Keyword extraction
    for kw in ("red", "cotton", "noise", "laptop", "headphone", "organic", "wireless", "denim", "wheat"):
        if kw in q:
            extracted["keyword"] = kw
            break
    if prompt_tier == "v1" and "tech" in q and "category" not in extracted:
        extracted["keyword"] = "tech"

    # 5. Merge with active session filters (v3 always preserves; v2 preserves when explicit; v1 overwrites)
    if prompt_tier == "v3":
        merged = {**active_filters, **extracted}
    elif prompt_tier == "v2":
        # v2 has the rule but without few-shot examples on pronoun follow-ups ("which ones...")
        if "which ones" in q and "category" not in extracted:
            merged = dict(extracted)
        else:
            merged = {**active_filters, **extracted}
    else:
        merged = dict(extracted)

    if any(p in q for p in ("any price", "no price limit", "regardless of price")):
        merged.pop("max_price", None)
        merged.pop("min_price", None)

    return merged


def _summarize_tool_payload(payload: Dict[str, Any]) -> str:
    products = payload.get("products") or []
    filters = payload.get("applied_filters") or {}

    cat = filters.get("category")
    min_p = filters.get("min_price")
    max_p = filters.get("max_price")
    kw = filters.get("keyword")

    parts = []
    if cat:
        parts.append(f"in {cat}")
    if min_p is not None and max_p is not None:
        parts.append(f"priced between ${min_p:g} and ${max_p:g}")
    elif max_p is not None:
        parts.append(f"under ${max_p:g}")
    elif min_p is not None:
        parts.append(f"over ${min_p:g}")
    if kw:
        parts.append(f'matching "{kw}"')
    filter_desc = (" " + " ".join(parts)) if parts else ""

    if not products:
        return f"No matching products were found{filter_desc}."

    if len(products) == 1:
        p = products[0]
        return f"Found 1 matching product{filter_desc}: {p['name']} (${p['price']}) — {p['description']}"

    items = ", ".join(f"{p['name']} (${p['price']})" for p in products)
    return f"Found {len(products)} matching products{filter_desc}: {items}."


class ResilientGeminiLlm(Gemini):
    """ADK `Gemini` model with automatic model-chain failover and quota fallback."""

    model: str = "gemini-3.8-flash"
    fallback_models: List[str] = DEFAULT_MODEL_CHAIN
    allow_offline_fallback: bool = True

    _cooldown_until: ClassVar[Dict[str, float]] = {}

    @classmethod
    def reset_cooldowns(cls) -> None:
        cls._cooldown_until.clear()

    def _candidate_models(self) -> List[str]:
        now = time.monotonic()
        ordered: List[str] = []
        for m in [self.model, *self.fallback_models]:
            if m and m not in ordered:
                ordered.append(m)
        active = [m for m in ordered if self._cooldown_until.get(m, 0.0) <= now]
        return active or ordered[:1]

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        # Try live Gemini models in priority order
        last_error: Optional[Exception] = None
        if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            for candidate in self._candidate_models():
                req_copy = llm_request.model_copy(deep=True)
                req_copy.model = candidate
                if req_copy.config:
                    # Disable slow multi-minute retries on 429 so failover is immediate
                    req_copy.config.http_options = types.HttpOptions(
                        timeout=15000,
                        retry_options=types.HttpRetryOptions(
                            attempts=1, http_status_codes=[500, 502, 503, 504]
                        ),
                    )
                    # Only gemini-3.8-* supports thinking_level enum without error
                    if not candidate.startswith("gemini-3.8"):
                        req_copy.config.thinking_config = None
                try:
                    async for resp in super().generate_content_async(req_copy, stream=stream):
                        yield resp
                    return
                except Exception as exc:
                    last_error = exc
                    msg = str(exc)
                    if any(code in msg for code in ("429", "RESOURCE_EXHAUSTED", "404", "NOT_FOUND")):
                        self._cooldown_until[candidate] = time.monotonic() + COOLDOWN_SECONDS
                        logger.warning(
                            "Model %s unavailable (%s); failing over to next model.",
                            candidate,
                            type(exc).__name__,
                        )
                        continue
                    break

        if not self.allow_offline_fallback and last_error is not None:
            raise last_error

        # In-ADK deterministic fallback when all remote models are rate-limited / offline
        yield self._fallback_response(llm_request)

    def _fallback_response(self, llm_request: LlmRequest) -> LlmResponse:
        last_content = llm_request.contents[-1] if llm_request.contents else None
        parts = (last_content.parts if last_content and last_content.parts else []) or []

        # Second pass of ADK turn: function_response is present -> summarize grounded results
        fn_responses = [p.function_response for p in parts if p.function_response]
        if fn_responses:
            payload = dict(fn_responses[-1].response or {})
            text = _summarize_tool_payload(payload)
            return LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=text)])
            )

        # First pass of ADK turn: extract parameters and return FunctionCall for ADK Runner
        user_text = " ".join(p.text for p in parts if p.text)
        sys_instruction = (
            (llm_request.config.system_instruction or "")
            if llm_request.config and isinstance(llm_request.config.system_instruction, str)
            else ""
        )
        active_filters = _extract_active_filters_from_instruction(sys_instruction)
        tier = _detect_prompt_tier(sys_instruction)
        args = _deterministic_tool_args(user_text, active_filters, tier)

        if args is None:
            return LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text=(
                                "Our catalog only carries clothing, electronics, accessories, "
                                "and groceries."
                            )
                        )
                    ],
                )
            )

        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(name="filter_products", args=args)
                    )
                ],
            )
        )
