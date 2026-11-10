"""Shared test fixtures.

`ScriptedLlm` is a fake ADK model: it lets the REAL google-adk Runner, tool
execution and session state run end to end without calling Gemini.
"""

import json
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

import pytest
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types

from backend.agent.agent import build_agent
from backend.agent.service import AgentService

# Maps a user message to the tool args the fake model "extracts" (None = no tool call).
Script = Callable[[str], Optional[Dict[str, Any]]]


class ScriptedLlm(BaseLlm):
    model: str = "scripted-fake"
    script: Any = None
    requests: List[LlmRequest] = []

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.requests.append(llm_request)
        last = llm_request.contents[-1]
        fn_responses = [p.function_response for p in last.parts if p.function_response]

        if fn_responses:  # second model call: summarize the tool output
            payload = fn_responses[0].response
            names = ", ".join(f"{p['name']} (${p['price']})" for p in payload.get("products", []))
            text = f"Found {payload.get('count', 0)}: {names}" if names else "No matches."
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))
            return

        user_text = "".join(p.text or "" for p in last.parts)
        args = self.script(user_text)
        if args is None:
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text="We only sell 4 categories.")])
            )
            return
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(function_call=types.FunctionCall(name="filter_products", args=args))],
            )
        )


DEFAULT_SCRIPT = {
    "What clothing items are under $50?": {"category": "clothing", "max_price": 50},
    "Show me clothing under $50": {"category": "clothing", "max_price": 50},
    "Show me all clothing items.": {"category": "clothing"},
    "Which ones are red?": "__refine_red__",
    "bad category": {"category": "furniture"},
    "I need a sofa": None,
}


@pytest.fixture
def fake_llm():
    llm = ScriptedLlm(requests=[])

    def script(text: str):
        value = DEFAULT_SCRIPT[text]
        if value == "__refine_red__":
            # Emulates a correct model: refine the CURRENT active filters from the instruction.
            sys = llm.requests[-1].config.system_instruction
            marker = "Current active filters: "
            active = json.loads(sys.split(marker, 1)[1].splitlines()[0])
            return {**active, "keyword": "red"}
        return value

    llm.script = script
    return llm


@pytest.fixture
def service(fake_llm):
    # v1 prompt contains the literal "Current active filters: {...}" line used by the script.
    return AgentService(agent=build_agent(model=fake_llm, prompt_version="v1"))
