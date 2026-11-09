import json
import os
import time
from typing import Any, Dict, Tuple

from google import genai
from google.genai import types

from backend.services.filter_engine import filter_engine
from backend.services.session_store import session_store

# Initialize Google GenAI client (uses default endpoint and 15s timeout)
client = genai.Client(
    api_key=os.environ.get("GEMINI_API_KEY"),
    http_options=types.HttpOptions(timeout=15000)
)

# Model name to use (gemini-3.8-flash)
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
filter_tool = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="filter_products",
            description="Filters products from the catalog determistically using exact constraints.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "category": types.Schema(
                        type=types.Type.STRING,
                        description="Category to filter by. Allowed canonical values: clothing, electronics, groceries, accessories."
                    ),
                    "min_price": types.Schema(
                        type=types.Type.NUMBER,
                        description="Minimum price floor (e.g., items over $20 -> min_price=20.0)."
                    ),
                    "max_price": types.Schema(
                        type=types.Type.NUMBER,
                        description="Maximum price ceiling (e.g., items under $50 -> max_price=50.0)."
                    ),                   
                    "keyword": types.Schema(
                        type=types.Type.STRING,
                        description="Keyword to search in product name or description (e.g., 'cotton', 'laptop')."
                    ),
                },
            )
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

def format_summary(products: list, query: str) -> str:
    """Generates a truthful, deterministic natural language summary directly from products."""
    if not products:
        return "No products found matching your search criteria."
    if len(products) == 1:
        p = products[0]
        return f"Found 1 item: {p['name']} for ${p['price']}."
    items_desc = ", ".join([f"{p['name']} (${p['price']})" for p in products[:3]])
    remaining = len(products) - 3
    if remaining > 0:
        return f"Found {len(products)} matching items, including {items_desc}, and {remaining} more."
    return f"Found {len(products)} matching items: {items_desc}."

def run_agent_turn(session_id: str, message: str) -> Dict[str, Any]:
    start_time = time.perf_counter()
    session = session_store.get_or_create(session_id)
    active_filters = session.get("active_filters", {})

    prompt = f"Current active search constraints: {json.dumps(active_filters)}\nUser query: {message}"

    print(f"[AGENT] Starting turn for session '{session_id}' with message: \"{message}\"", flush=True)
    print(f"[AGENT] Active filters: {active_filters}", flush=True)

    # First turn: Ask LLM with tools
    print(f"[AGENT] Invoking model '{MODEL_NAME}' for tool parameter extraction...", flush=True)
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[filter_tool],
            temperature=0.1,
        )
    )

    t_first_turn = round((time.perf_counter() - start_time) * 1000, 2)
    print(f"[AGENT] Model response received in {t_first_turn}ms", flush=True)

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

        print(f"[AGENT] Tool called: '{tool_name}' with extracted arguments: {tool_args}", flush=True)

        tool_call_meta["name"] = tool_name
        tool_call_meta["parameters"] = tool_args
        tool_call_meta["status"] = "SUCCESS"

        # Merge new extracted parameters with active filters
        updated_filters = {**active_filters, **tool_args}
        session_store.updated_filters(session_id, updated_filters)

        # Deterministic execution
        products = filter_engine.filter_products(**updated_filters)
        print(f"[AGENT] Filtered {len(products)} products from catalog matching {updated_filters}", flush=True)

        # Baseline summary from filtered products
        reply_text = format_summary(products, message)

        # Optional natural language polish turn
        try:
            summary_prompt = (
                f"User asked: {message}\n"
                f"Matching products: {json.dumps(products)}\n"
                "In 1-2 concise sentences, summarize these matching products and their prices accurately."
            )
            summary_response = client.models.generate_content(
                model=MODEL_NAME,
                contents=summary_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.2,
                )
            )
            if summary_response and summary_response.text:
                reply_text = summary_response.text.strip()
        except Exception as e:
            print(f"[AGENT] LLM summary polish skipped ({e}), using deterministic summary", flush=True)
    else:
        print("[AGENT] No tool was called by the model.", flush=True)
        reply_text = response.text or "I couldn't identify specific product search parameters."
        products = filter_engine.filter_products(**active_filters)
    
    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
    tool_call_meta["latency_ms"] = latency_ms

    print(f"[AGENT] Turn finished in {latency_ms}ms. Returning {len(products)} products.", flush=True)

    return {
        "reply": reply_text,
        "products": products,
        "tool_call": tool_call_meta,
        "active_filters": session["active_filters"],
        "latency_ms": latency_ms,
    }



