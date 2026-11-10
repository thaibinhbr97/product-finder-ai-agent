"""Runs the ADK agent and translates ADK events into UI-facing events.

Event stream for one turn (also used by the non-streaming endpoint):
    stage(connecting) -> stage(parsing_intent) -> [stage(executing_tool) -> tool_call]* -> result
On failure an `error` event is emitted instead of `result`.
"""

import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from google.adk.events import Event, EventActions
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService, Session
from google.genai import types

from backend.agent.agent import STATE_KEY, build_agent
from backend.services.filter_engine import filter_engine, normalize_filters

APP_NAME = "product_finder"
USER_ID = "web-user"
TOOL_NAME = "filter_products"


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


class AgentService:
    def __init__(self, agent=None):
        self.agent = agent or build_agent()
        self.session_service = InMemorySessionService()
        self.runner = Runner(
            app_name=APP_NAME, agent=self.agent, session_service=self.session_service
        )

    async def _get_or_create_session(self, session_id: str) -> Session:
        session = await self.session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id
        )
        if session is None:
            session = await self.session_service.create_session(
                app_name=APP_NAME,
                user_id=USER_ID,
                session_id=session_id,
                state={STATE_KEY: {}},
            )
        return session

    async def get_filters(self, session_id: str) -> Dict[str, Any]:
        session = await self._get_or_create_session(session_id)
        return dict(session.state.get(STATE_KEY) or {})

    async def set_filters(self, session_id: str, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Writes UI-edited filters into ADK session state (no LLM call).

        Uses a state-only event, which is the ADK-supported way to mutate
        session state outside of an agent run.
        """
        clean = normalize_filters(filters)
        session = await self._get_or_create_session(session_id)
        await self.session_service.append_event(
            session,
            Event(
                author="user",
                invocation_id=Event.new_id(),
                actions=EventActions(state_delta={STATE_KEY: clean}),
            ),
        )
        return clean

    async def stream_turn(
        self, session_id: str, message: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        start = time.perf_counter()
        yield {"event": "stage", "data": {"stage": "connecting"}}

        try:
            await self._get_or_create_session(session_id)
            yield {"event": "stage", "data": {"stage": "parsing_intent"}}

            tool_calls: List[Dict[str, Any]] = []
            reply_parts: List[str] = []
            new_message = types.Content(role="user", parts=[types.Part(text=message)])

            async for event in self.runner.run_async(
                user_id=USER_ID, session_id=session_id, new_message=new_message
            ):
                for call in event.get_function_calls():
                    if call.name != TOOL_NAME:
                        continue
                    tool_calls.append(
                        {
                            "id": call.id,
                            "name": call.name,
                            "parameters": dict(call.args or {}),
                            "status": "pending",
                            "latency_ms": None,
                        }
                    )
                    yield {"event": "stage", "data": {"stage": "executing_tool"}}

                for response in event.get_function_responses():
                    if response.name != TOOL_NAME:
                        continue
                    payload = response.response or {}
                    record = next(
                        (c for c in reversed(tool_calls) if c["id"] == response.id),
                        tool_calls[-1] if tool_calls else None,
                    )
                    if record is None:
                        continue
                    record["status"] = payload.get("status", "success")
                    record["latency_ms"] = payload.get("latency_ms")
                    if payload.get("error"):
                        record["error"] = payload["error"]
                    yield {"event": "tool_call", "data": _public_tool_call(record)}

                if event.is_final_response() and event.content and event.content.parts:
                    reply_parts.extend(
                        part.text
                        for part in event.content.parts
                        if part.text and not part.thought
                    )

            filters = await self.get_filters(session_id)
            products = filter_engine.filter_products(**filters)
            last_call = _public_tool_call(tool_calls[-1]) if tool_calls else None

            yield {
                "event": "result",
                "data": {
                    "session_id": session_id,
                    "reply": "".join(reply_parts).strip(),
                    "products": products,
                    "product_ids": [p["id"] for p in products],
                    "active_filters": filters,
                    "tool_call": last_call,
                    "tool_calls": [_public_tool_call(c) for c in tool_calls],
                    "latency_ms": _ms(start),
                },
            }
        except Exception as exc:  # surfaced to the client, never swallowed
            yield {
                "event": "error",
                "data": {"detail": f"{type(exc).__name__}: {exc}", "latency_ms": _ms(start)},
            }

    async def run_turn(self, session_id: str, message: str) -> Dict[str, Any]:
        """Non-streaming turn. Raises RuntimeError if the agent failed."""
        result: Optional[Dict[str, Any]] = None
        async for item in self.stream_turn(session_id, message):
            if item["event"] == "error":
                raise RuntimeError(item["data"]["detail"])
            if item["event"] == "result":
                result = item["data"]
        assert result is not None
        return result


def _public_tool_call(record: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in record.items() if k != "id"}
