"""End-to-end verification of all FastAPI endpoints in `backend/main.py`.

Tests all 8 endpoints:
  1. GET  /
  2. GET  /api/health
  3. GET  /api/products
  4. POST /api/chat
  5. POST /api/chat/stream (SSE)
  6. POST /api/state
  7. POST /api/state/sync
  8. GET  /api/state/{session_id}
"""

import json
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
VENV_SITE = ROOT_DIR / "venv" / "lib" / "python3.11" / "site-packages"
for p in (str(ROOT_DIR), str(VENV_SITE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient  # noqa: E402
from backend.main import app  # noqa: E402


def verify_all_endpoints() -> None:
    client = TestClient(app)
    session_id = f"verify-{int(time.time())}"

    print("=" * 72, flush=True)
    print("TESTING ALL FASTAPI ENDPOINTS (LIVE GOOGLE ADK + GEMINI)", flush=True)
    print("=" * 72, flush=True)

    # 1. GET /
    t0 = time.perf_counter()
    r = client.get("/")
    ms = (time.perf_counter() - t0) * 1000
    assert r.status_code == 200, r.text
    print(f"[1/8] GET /                     -> HTTP {r.status_code} ({ms:.1f}ms) | {r.json()}", flush=True)

    # 2. GET /api/health
    t0 = time.perf_counter()
    r = client.get("/api/health")
    ms = (time.perf_counter() - t0) * 1000
    assert r.status_code == 200 and r.json()["status"] == "ok", r.text
    print(f"[2/8] GET /api/health           -> HTTP {r.status_code} ({ms:.1f}ms) | {r.json()}", flush=True)

    # 3. GET /api/products
    t0 = time.perf_counter()
    r = client.get("/api/products")
    ms = (time.perf_counter() - t0) * 1000
    assert r.status_code == 200, r.text
    products = r.json()["products"]
    assert len(products) == 13
    print(
        f"[3/8] GET /api/products         -> HTTP {r.status_code} ({ms:.1f}ms) | {len(products)} catalog items",
        flush=True,
    )

    # 4. POST /api/chat (Initial search: "What clothing items are under $50?")
    t0 = time.perf_counter()
    r = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "What clothing items are under $50?"},
    )
    ms = (time.perf_counter() - t0) * 1000
    assert r.status_code == 200, r.text
    body = r.json()
    assert sorted(body["product_ids"]) == [0, 7], f"Expected [0, 7], got {body['product_ids']}"
    assert body["active_filters"] == {"category": "clothing", "max_price": 50.0}
    assert body["tool_call"]["name"] == "filter_products"
    print(
        f"[4/8] POST /api/chat            -> HTTP {r.status_code} ({ms:.0f}ms)\n"
        f"      Query:          'What clothing items are under $50?'\n"
        f"      Tool Call:      {body['tool_call']}\n"
        f"      Active Filters: {body['active_filters']}\n"
        f"      Product IDs:    {body['product_ids']} ({[p['name'] for p in body['products']]})\n"
        f"      Agent Reply:    {body['reply']}",
        flush=True,
    )

    # 5. POST /api/state (Simulate dismissing 'Max Price: $50' chip in UI)
    t0 = time.perf_counter()
    r = client.post(
        "/api/state",
        json={"session_id": session_id, "active_filters": {"category": "clothing"}},
    )
    ms = (time.perf_counter() - t0) * 1000
    assert r.status_code == 200, r.text
    state_body = r.json()
    assert sorted(state_body["product_ids"]) == [0, 5, 7, 8]
    print(
        f"[5/8] POST /api/state           -> HTTP {r.status_code} ({ms:.1f}ms) | "
        f"filters={state_body['active_filters']} | product_ids={state_body['product_ids']}",
        flush=True,
    )

    # 6. GET /api/state/{session_id}
    t0 = time.perf_counter()
    r = client.get(f"/api/state/{session_id}")
    ms = (time.perf_counter() - t0) * 1000
    assert r.status_code == 200, r.text
    assert r.json()["active_filters"] == {"category": "clothing"}
    print(
        f"[6/8] GET /api/state/{{session}}  -> HTTP {r.status_code} ({ms:.1f}ms) | {r.json()}",
        flush=True,
    )

    # 7. POST /api/chat/stream (SSE follow-up query respecting mutated state: "Which ones are made of cotton?")
    t0 = time.perf_counter()
    events = []
    final_result = None
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"session_id": session_id, "message": "Which ones are made of cotton?"},
    ) as stream_resp:
        assert stream_resp.status_code == 200
        raw = "".join(stream_resp.iter_text())
    ms = (time.perf_counter() - t0) * 1000

    for block in raw.strip().split("\n\n"):
        if not block.strip():
            continue
        ev_type = None
        data_str = None
        for line in block.splitlines():
            if line.startswith("event:"):
                ev_type = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_str = line.split(":", 1)[1].strip()
        if ev_type and data_str:
            parsed = json.loads(data_str)
            events.append((ev_type, parsed))
            if ev_type == "result":
                final_result = parsed

    stage_list = [d["stage"] for t, d in events if t == "stage"]
    assert stage_list == ["connecting", "parsing_intent", "executing_tool"], stage_list
    assert final_result is not None
    assert sorted(final_result["product_ids"]) == [0, 7]
    assert final_result["active_filters"].get("category") == "clothing"
    print(
        f"[7/8] POST /api/chat/stream     -> HTTP 200 ({ms:.0f}ms)\n"
        f"      Follow-Up:      'Which ones are made of cotton?' (after dismissing max_price)\n"
        f"      SSE Stages:     {stage_list}\n"
        f"      Active Filters: {final_result['active_filters']}\n"
        f"      Product IDs:    {final_result['product_ids']} ({[p['name'] for p in final_result['products']]})\n"
        f"      Agent Reply:    {final_result['reply']}",
        flush=True,
    )

    # 8. POST /api/state/sync (Clear All constraints)
    t0 = time.perf_counter()
    r = client.post(
        "/api/state/sync",
        json={"session_id": session_id, "active_filters": {}},
    )
    ms = (time.perf_counter() - t0) * 1000
    assert r.status_code == 200, r.text
    sync_body = r.json()
    assert len(sync_body["product_ids"]) == 13
    print(
        f"[8/8] POST /api/state/sync      -> HTTP {r.status_code} ({ms:.1f}ms) | "
        f"status={sync_body['status']} | count={sync_body['count']} (all filters cleared)",
        flush=True,
    )

    print("=" * 72, flush=True)
    print("ALL 8 API ENDPOINTS VERIFIED SUCCESSFULLY", flush=True)
    print("=" * 72, flush=True)


if __name__ == "__main__":
    verify_all_endpoints()
