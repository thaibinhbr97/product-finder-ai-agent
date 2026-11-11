"""Tests for golden_dataset.json consistency and DeepEval ExactMatch integration."""

from evaluation.eval_suite import (
    RESULTS_DIR,
    canonical_filter_and_ids,
    evaluate_suite,
    load_golden_dataset,
)
from backend.services.filter_engine import filter_engine


def test_golden_dataset_has_at_least_five_cases():
    dataset = load_golden_dataset()
    assert len(dataset) >= 5


def test_golden_dataset_ground_truth_matches_filter_engine():
    """Every case's expected_filters must deterministically yield expected_product_ids."""
    dataset = load_golden_dataset()
    for case in dataset:
        products = filter_engine.filter_products(**case["expected_filters"])
        actual_ids = sorted(p["id"] for p in products)
        assert actual_ids == sorted(case["expected_product_ids"]), (
            f"Ground truth mismatch in {case['id']}: "
            f"filters {case['expected_filters']} produced {actual_ids}, "
            f"expected {case['expected_product_ids']}"
        )


def test_evaluate_suite_deterministic_metric():
    dataset = load_golden_dataset()[:3]

    def fake_caller(session_id, initial_filters, message):
        # Match first two cases, fail the third
        for idx, c in enumerate(dataset):
            if c["input"] == message:
                if idx < 2:
                    return {
                        "active_filters": c["expected_filters"],
                        "product_ids": c["expected_product_ids"],
                        "products": filter_engine.filter_products(**c["expected_filters"]),
                        "reply": c["expected_summary"],
                    }
                return {
                    "active_filters": {},
                    "product_ids": [],
                    "products": [],
                    "reply": "Nothing found.",
                }
        raise AssertionError("Unknown message")

    summary = evaluate_suite(fake_caller, dataset, label="unit_test", skip_geval=True)
    (RESULTS_DIR / "eval_unit_test.json").unlink(missing_ok=True)
    assert summary["total_cases"] == 3
    assert summary["exact_match_combined_avg"] == round(2 / 3, 4)
    assert canonical_filter_and_ids({"category": "Clothing"}, [7, 0]) == canonical_filter_and_ids(
        {"category": "clothing"}, [0, 7]
    )
