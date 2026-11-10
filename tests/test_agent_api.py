"""End-to-end tests through the real ADK Runner (fake model, no network)."""

import json

import pytest
from fastapi.testclient import TestClient

from backend.agent.agent import build_agent
from backend.main import app, get_agent_service


def test_tool_declaration_hides_tool_context():
    from google.adk.tools import FunctionTool

    agent = build_agent(model="gemini-3.8-flash")
    decl = FunctionTool(agent.tools[0])._get_declaration()
    schema = decl.parameters_json_schema or decl.parameters.model_dump(exclude_none=True)
    text = json.dumps(schema, default=str)
    assert decl.name == "filter_products"
    for p in ("category", "min_price", "max_price", "keyword"):
        assert p in text
    assert "tool_context" not in text


def test_thinking_config_is_valid_type():
    cfg = build_agent(model="gemini-3.8-flash").generate_content_config
    assert cfg.thinking_config.thinking_level.name == "LOW"


@pytest.mark.asyncio
async def test_combined_query_via_adk(service):
    result = await service.run_turn("s1", "What clothing items are under $50?")
    assert result["product_ids"] == [0, 7]
    assert result["active_filters"] == {"category": "clothing", "max_price": 50.0}
    assert result["tool_call"]["name"] == "filter_products"
    assert result["tool_call"]["parameters"] == {"category": "clothing", "max_price": 50}
    assert result["tool_call"]["status"] == "success"
    assert isinstance(result["tool_call"]["latency_ms"], float)
    assert "UBC Hoodie" in result["reply"] and "T-Shirt" in result["reply"]


@pytest.mark.asyncio
async def test_stage_event_order(service):
    events = [e async for e in service.stream_turn("s2", "Show me all clothing items.")]
    stages = [e["data"]["stage"] for e in events if e["event"] == "stage"]
    assert stages == ["connecting", "parsing_intent", "executing_tool"]
    kinds = [e["event"] for e in events]
    assert kinds.index("tool_call") < kinds.index("result")
    assert events[-1]["event"] == "result"


@pytest.mark.asyncio
async def test_pdf_state_mutation_workflow(service, fake_llm):
    """PDF Part 2 #4: search -> dismiss Max Price chip -> follow-up respects mutation."""
    r1 = await service.run_turn("s3", "Show me clothing under $50")
    assert r1["active_filters"] == {"category": "clothing", "max_price": 50.0}

    # User dismisses the "Max Price: $50" chip in the UI.
    synced = await service.set_filters("s3", {"category": "clothing"})
    assert synced == {"category": "clothing"}
    assert await service.get_filters("s3") == {"category": "clothing"}

    # Follow-up: the model must see the mutated state (no max_price) in its instruction.
    r2 = await service.run_turn("s3", "Which ones are red?")
    # requests[-2] = the call that decided the tool args; requests[-1] = the summary call.
    decision_instruction = fake_llm.requests[-2].config.system_instruction
    assert 'Current active filters: {"category": "clothing"}' in decision_instruction
    assert "max_price" not in decision_instruction
    summary_instruction = fake_llm.requests[-1].config.system_instruction
    assert '{"category": "clothing", "keyword": "red"}' in summary_instruction
    assert r2["tool_call"]["parameters"] == {"category": "clothing", "keyword": "red"}
    assert r2["active_filters"] == {"category": "clothing", "keyword": "red"}
    assert r2["product_ids"] == []  # no red clothing in the catalog


@pytest.mark.asyncio
async def test_invalid_tool_args_report_error(service):
    result = await service.run_turn("s4", "bad category")
    assert result["tool_call"]["status"] == "error"
    assert "furniture" in result["tool_call"]["error"]
    assert result["active_filters"] == {}


@pytest.mark.asyncio
async def test_no_tool_call_for_out_of_catalog(service):
    result = await service.run_turn("s5", "I need a sofa")
    assert result["tool_call"] is None
    assert result["reply"]


# ---------- HTTP layer ----------

@pytest.fixture
def client(service):
    app.dependency_overrides[get_agent_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_http_chat_and_state(client):
    r = client.post("/api/chat", json={"session_id": "h1", "message": "What clothing items are under $50?"})
    assert r.status_code == 200, r.text
    assert r.json()["product_ids"] == [0, 7]

    r = client.post("/api/state", json={"session_id": "h1", "active_filters": {"category": "clothing", "max_price": None}})
    assert r.status_code == 200
    assert r.json()["product_ids"] == [0, 5, 7, 8]
    assert client.get("/api/state/h1").json()["active_filters"] == {"category": "clothing"}

    r = client.post("/api/state", json={"session_id": "h1", "active_filters": {"category": "furniture"}})
    assert r.status_code == 422


def test_http_stream_sse(client):
    with client.stream("POST", "/api/chat/stream", json={"session_id": "h2", "message": "Show me all clothing items."}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    events = [line[len("event: "):] for line in body.splitlines() if line.startswith("event: ")]
    assert events == ["stage", "stage", "stage", "tool_call", "result"]


def test_http_health_products_and_validation(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert len(client.get("/api/products").json()["products"]) == 13
    assert client.post("/api/chat", json={"session_id": "x", "message": ""}).status_code == 422


def test_upstream_failure_returns_502(client, fake_llm):
    def boom(_):
        raise RuntimeError("Gemini unavailable")

    fake_llm.script = boom
    r = client.post("/api/chat", json={"session_id": "h3", "message": "anything"})
    assert r.status_code == 502
    assert "Gemini unavailable" in r.json()["detail"]
