"""Live smoke test: real Gemini via ADK. Usage: python scripts/smoke_live.py"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from backend.agent.service import AgentService  # noqa: E402


async def main():
    service = AgentService()
    for msg in ["What clothing items are under $50?", "Which ones are red?"]:
        r = await service.run_turn("smoke", msg)
        print(json.dumps({k: r[k] for k in ("reply", "product_ids", "active_filters", "tool_call", "latency_ms")}, indent=2))
    ok = (await service.get_filters("smoke")).get("category") == "clothing"
    print("SMOKE", "PASS" if ok else "FAIL")


asyncio.run(main())
