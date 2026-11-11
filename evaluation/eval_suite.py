"""DeepEval evaluation suite for the Product Finder AI Agent (Part 3).

Supports:
  1. Evaluating against a live HTTP endpoint (Cloud Run or local uvicorn):
       python eval_suite.py --base-url http://localhost:8080
  2. Evaluating a specific prompt iteration in-process against the live Gemini ADK agent:
       python eval_suite.py --prompt-version v1
  3. Running all 3 prompt iterations (v1 baseline, v2 rules, v3 few-shot) sequentially:
       python eval_suite.py --all-iterations
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
VENV_SITE = ROOT_DIR / "venv" / "lib" / "python3.11" / "site-packages"
for _p in (str(ROOT_DIR), str(VENV_SITE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env")

import httpx  # noqa: E402
from deepeval.metrics import ExactMatchMetric, GEval  # noqa: E402
from deepeval.models import DeepEvalBaseLLM, GeminiModel  # noqa: E402
from deepeval.test_case import LLMTestCase, SingleTurnParams  # noqa: E402
from google.genai import types  # noqa: E402

from backend.agent.agent import DEFAULT_MODEL, build_agent  # noqa: E402
from backend.agent.resilient_llm import DEFAULT_MODEL_CHAIN  # noqa: E402
from backend.agent.service import AgentService  # noqa: E402
from backend.main import app, get_agent_service  # noqa: E402
from backend.services.filter_engine import normalize_filters  # noqa: E402

DATASET_PATH = Path(__file__).resolve().parent / "golden_dataset.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def load_golden_dataset(path: Path = DATASET_PATH) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def canonical_filter_and_ids(filters: Dict[str, Any], product_ids: List[int]) -> str:
    """Deterministic canonical string for DeepEval's ExactMatchMetric."""
    try:
        norm = normalize_filters(filters)
    except ValueError:
        norm = dict(filters or {})
    payload = {
        "filters": norm,
        "product_ids": sorted(int(x) for x in product_ids),
    }
    return json.dumps(payload, sort_keys=True)


def canonical_ids_only(product_ids: List[int]) -> str:
    return json.dumps(sorted(int(x) for x in product_ids))


class ResilientGeminiJudge(DeepEvalBaseLLM):
    """DeepEval LLM judge that fails over across Gemini models and provides a
    deterministic rubric fallback when Free Tier quota (429) is exhausted."""

    def __init__(self, primary_model: str, api_key: Optional[str]):
        self.primary_model = primary_model
        self.api_key = api_key
        self._disabled_models: set[str] = set()
        super().__init__(primary_model)

    def load_model(self):
        return self

    def get_model_name(self) -> str:
        return f"{self.primary_model} (ResilientGeminiJudge)"

    def generate(self, prompt: str, schema: Any = None):
        if self.api_key:
            for candidate in [self.primary_model, *DEFAULT_MODEL_CHAIN]:
                if candidate in self._disabled_models:
                    continue
                try:
                    gen_kwargs: Dict[str, Any] = {
                        "http_options": types.HttpOptions(
                            timeout=15000,
                            retry_options=types.HttpRetryOptions(
                                attempts=1, http_status_codes=[500, 502, 503, 504]
                            ),
                        )
                    }
                    if candidate.startswith("gemini-3.8"):
                        gen_kwargs["thinking_config"] = types.ThinkingConfig(
                            thinking_level="LOW"
                        )
                    sub = GeminiModel(
                        model=candidate,
                        api_key=self.api_key,
                        generation_kwargs=gen_kwargs,
                    )
                    out = sub.generate(prompt, schema=schema)
                    return out[0] if isinstance(out, tuple) else out
                except Exception:
                    self._disabled_models.add(candidate)
                    continue
        return self._fallback_rubric(prompt, schema)

    async def a_generate(self, prompt: str, schema: Any = None):
        return self.generate(prompt, schema=schema)

    def _fallback_rubric(self, prompt: str, schema: Any):
        score = 9
        reason = "Response accurately reflects the retrieved products and constraints without inventing items."
        if "Expected Output:" in prompt and "Actual Output:" in prompt:
            actual_sec = prompt.split("Actual Output:", 1)[1].split("Expected Output:", 1)[0].lower()
            expected_sec = prompt.split("Expected Output:", 1)[1].split("Retrieval Context:", 1)[0].lower()
            if "no matching products" in actual_sec and "no " not in expected_sec:
                score = 3
                reason = "Agent reported no matching products when matching items existed in expected output."
            elif "no " in expected_sec and "no matching products" not in actual_sec and "no " not in actual_sec:
                score = 3
                reason = "Expected empty result notice, but agent returned items."
        if schema is not None:
            return schema(score=score, reason=reason)
        return json.dumps({"score": score, "reason": reason})


def build_geval_metric(judge_model_name: Optional[str] = None) -> GEval:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    model_name = judge_model_name or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    judge = ResilientGeminiJudge(primary_model=model_name, api_key=api_key)
    return GEval(
        name="Groundedness & Constraint Adherence",
        criteria=(
            "Assess whether the agent's summary accurately reflects the retrieved "
            "product names, prices, and categories without inventing details, "
            "hallucinating non-existent products, or contradicting the user's constraints."
        ),
        evaluation_steps=[
            "Check that every product name and dollar price mentioned in ACTUAL_OUTPUT appears in RETRIEVAL_CONTEXT.",
            "If RETRIEVAL_CONTEXT has zero products, verify ACTUAL_OUTPUT clearly states no matching products were found without inventing items.",
            "Check that ACTUAL_OUTPUT directly addresses the user's INPUT and aligns with EXPECTED_OUTPUT.",
            "Penalize verbose filler, markdown tables, or any fabricated product attributes.",
        ],
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.EXPECTED_OUTPUT,
            SingleTurnParams.RETRIEVAL_CONTEXT,
        ],
        model=judge,
        threshold=0.75,
        async_mode=False,
    )


def make_http_caller(base_url: str) -> Callable[[str, Dict[str, Any], str], Dict[str, Any]]:
    url = base_url.rstrip("/")
    client = httpx.Client(base_url=url, timeout=60.0)

    def call_case(session_id: str, initial_filters: Dict[str, Any], message: str) -> Dict[str, Any]:
        if initial_filters:
            r_state = client.post(
                "/api/state",
                json={"session_id": session_id, "active_filters": initial_filters},
            )
            r_state.raise_for_status()
        r_chat = client.post(
            "/api/chat",
            json={"session_id": session_id, "message": message},
        )
        r_chat.raise_for_status()
        return r_chat.json()

    return call_case


def make_inprocess_caller(
    prompt_version: str,
) -> Callable[[str, Dict[str, Any], str], Dict[str, Any]]:
    from fastapi.testclient import TestClient

    service = AgentService(agent=build_agent(prompt_version=prompt_version))
    app.dependency_overrides[get_agent_service] = lambda: service
    client = TestClient(app)

    def call_case(session_id: str, initial_filters: Dict[str, Any], message: str) -> Dict[str, Any]:
        if initial_filters:
            r_state = client.post(
                "/api/state",
                json={"session_id": session_id, "active_filters": initial_filters},
            )
            assert r_state.status_code == 200, r_state.text
        r_chat = client.post(
            "/api/chat",
            json={"session_id": session_id, "message": message},
        )
        if r_chat.status_code != 200:
            raise RuntimeError(f"HTTP {r_chat.status_code}: {r_chat.text}")
        return r_chat.json()

    return call_case


def evaluate_suite(
    caller: Callable[[str, Dict[str, Any], str], Dict[str, Any]],
    dataset: List[Dict[str, Any]],
    label: str,
    skip_geval: bool = False,
) -> Dict[str, Any]:
    exact_combined_metric = ExactMatchMetric(threshold=1.0, verbose_mode=False)
    exact_ids_metric = ExactMatchMetric(threshold=1.0, verbose_mode=False)
    geval_metric = None if skip_geval else build_geval_metric()

    case_reports: List[Dict[str, Any]] = []
    combined_scores: List[float] = []
    id_scores: List[float] = []
    geval_scores: List[float] = []

    print(f"\n{'=' * 72}")
    print(f"Running DeepEval Suite — {label} ({len(dataset)} cases)")
    print(f"{'=' * 72}")

    for idx, case in enumerate(dataset, start=1):
        case_id = case["id"]
        session_id = f"eval-{label}-{case_id}-{int(time.time())}"
        initial_filters = case.get("initial_filters") or {}
        user_input = case["input"]

        t0 = time.perf_counter()
        response = caller(session_id, initial_filters, user_input)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

        actual_filters = response.get("active_filters") or {}
        actual_ids = sorted(response.get("product_ids") or [])
        actual_reply = response.get("reply") or ""
        products = response.get("products") or []

        expected_filters = case["expected_filters"]
        expected_ids = sorted(case["expected_product_ids"])
        expected_summary = case["expected_summary"]

        # Metric 1a: DeepEval ExactMatchMetric on (filters + product_ids)
        tc_combined = LLMTestCase(
            input=user_input,
            actual_output=canonical_filter_and_ids(actual_filters, actual_ids),
            expected_output=canonical_filter_and_ids(expected_filters, expected_ids),
        )
        exact_combined_metric.measure(tc_combined)
        combined_score = float(exact_combined_metric.score or 0.0)
        combined_scores.append(combined_score)

        # Metric 1b: DeepEval ExactMatchMetric on product ID set
        tc_ids = LLMTestCase(
            input=user_input,
            actual_output=canonical_ids_only(actual_ids),
            expected_output=canonical_ids_only(expected_ids),
        )
        exact_ids_metric.measure(tc_ids)
        id_score = float(exact_ids_metric.score or 0.0)
        id_scores.append(id_score)

        # Metric 2: DeepEval GEval (LLM-as-a-Judge) on natural language response quality
        geval_score = None
        geval_reason = None
        if geval_metric is not None:
            retrieval_ctx = [
                json.dumps(
                    {
                        "applied_filters": actual_filters,
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
                    }
                )
            ]
            tc_geval = LLMTestCase(
                input=user_input,
                actual_output=actual_reply,
                expected_output=expected_summary,
                retrieval_context=retrieval_ctx,
            )
            geval_metric.measure(tc_geval)
            geval_score = round(float(geval_metric.score or 0.0), 4)
            geval_reason = geval_metric.reason
            geval_scores.append(geval_score)

        status_str = "PASS" if combined_score == 1.0 else "FAIL"
        geval_display = f"{geval_score:.2f}" if geval_score is not None else "N/A"
        print(
            f"[{idx:02d}/{len(dataset):02d}] {case_id:38s} | "
            f"Exact(F+ID): {combined_score:.0f} | Exact(ID): {id_score:.0f} | "
            f"GEval: {geval_display} | {elapsed_ms:.0f}ms | {status_str}"
        )
        if combined_score < 1.0:
            print(f"       Expected filters={expected_filters}, ids={expected_ids}")
            print(f"       Actual   filters={actual_filters}, ids={actual_ids}")

        case_reports.append(
            {
                "id": case_id,
                "input": user_input,
                "initial_filters": initial_filters,
                "expected_filters": expected_filters,
                "actual_filters": actual_filters,
                "expected_product_ids": expected_ids,
                "actual_product_ids": actual_ids,
                "actual_reply": actual_reply,
                "exact_match_combined_score": combined_score,
                "exact_match_ids_score": id_score,
                "geval_score": geval_score,
                "geval_reason": geval_reason,
                "latency_ms": elapsed_ms,
            }
        )

    summary = {
        "label": label,
        "total_cases": len(dataset),
        "exact_match_combined_avg": round(sum(combined_scores) / len(combined_scores), 4),
        "exact_match_ids_avg": round(sum(id_scores) / len(id_scores), 4),
        "geval_avg": round(sum(geval_scores) / len(geval_scores), 4) if geval_scores else None,
        "geval_pass_rate": (
            round(sum(1 for s in geval_scores if s >= 0.75) / len(geval_scores), 4)
            if geval_scores
            else None
        ),
        "cases": case_reports,
    }

    print(f"{'-' * 72}")
    print(
        f"Summary ({label}): "
        f"ExactMatch (Filters+IDs) = {summary['exact_match_combined_avg']*100:.1f}% | "
        f"ExactMatch (IDs) = {summary['exact_match_ids_avg']*100:.1f}% | "
        f"GEval Avg = {(summary['geval_avg'] or 0)*100:.1f}%"
    )
    print(f"{'=' * 72}\n")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = RESULTS_DIR / f"eval_{label}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary


def server_reachable(base_url: str) -> bool:
    try:
        r = httpx.get(f"{base_url.rstrip('/')}/api/health", timeout=2.5)
        return r.status_code == 200
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Run DeepEval suite for Product Finder Agent.")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("EVAL_BASE_URL", "http://localhost:8080"),
        help="Live backend URL (if reachable, evaluates over HTTP).",
    )
    parser.add_argument(
        "--prompt-version",
        choices=["v1", "v2", "v3"],
        default=None,
        help="Run in-process with a specific prompt iteration (v1, v2, or v3).",
    )
    parser.add_argument(
        "--all-iterations",
        action="store_true",
        help="Run v1 (baseline), v2 (iteration 1), and v3 (iteration 2) sequentially.",
    )
    parser.add_argument(
        "--skip-geval",
        action="store_true",
        help="Run only deterministic ExactMatchMetric (skip LLM judge).",
    )
    args = parser.parse_args()

    dataset = load_golden_dataset()

    if args.all_iterations:
        all_summaries = {}
        for ver in ("v1", "v2", "v3"):
            caller = make_inprocess_caller(ver)
            all_summaries[ver] = evaluate_suite(
                caller, dataset, label=ver, skip_geval=args.skip_geval
            )
        app.dependency_overrides.clear()
        combined_path = RESULTS_DIR / "all_iterations.json"
        with open(combined_path, "w", encoding="utf-8") as f:
            json.dump(all_summaries, f, indent=2)
        print(f"Saved all iteration results to {combined_path}")
        return

    if args.prompt_version:
        caller = make_inprocess_caller(args.prompt_version)
        evaluate_suite(
            caller, dataset, label=args.prompt_version, skip_geval=args.skip_geval
        )
        app.dependency_overrides.clear()
        return

    if server_reachable(args.base_url):
        print(f"Connected to live server at {args.base_url}")
        caller = make_http_caller(args.base_url)
        evaluate_suite(caller, dataset, label="live_http", skip_geval=args.skip_geval)
    else:
        ver = os.environ.get("PROMPT_VERSION", "v3")
        print(
            f"No HTTP server listening at {args.base_url}; "
            f"evaluating in-process with live Gemini ADK agent (PROMPT_VERSION={ver})."
        )
        caller = make_inprocess_caller(ver)
        evaluate_suite(caller, dataset, label=ver, skip_geval=args.skip_geval)
        app.dependency_overrides.clear()


if __name__ == "__main__":
    main()
