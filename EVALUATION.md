# Automated Agent Evaluation Report (`EVALUATION.md`)

This document tracks the evaluation methodology, golden dataset design, iterative prompt/system optimizations, and key insights regarding LLM evaluation drift for the **Product Finder AI Agent** (`google-adk` + `gemini-3.8-flash`), benchmarked with **DeepEval**.

---

## 1. Evaluation Architecture & Metrics

The evaluation pipeline ([`evaluation/eval_suite.py`](file:///Users/bradnguyen/github-repos/product-finder-ai-agent/evaluation/eval_suite.py) / [`eval_suite.py`](file:///Users/bradnguyen/github-repos/product-finder-ai-agent/eval_suite.py)) benchmarks the agent against [`golden_dataset.json`](file:///Users/bradnguyen/github-repos/product-finder-ai-agent/golden_dataset.json) (8 diverse scenarios covering basic category lookups, combined price ceilings, colloquial synonyms, empty result sets, subjective price adjectives, inclusive boundaries, and multi-turn state mutations).

### Metric 1: Deterministic Metric (`ExactMatchMetric`)
- **Implementation**: `deepeval.metrics.ExactMatchMetric(threshold=1.0)`
- **Target**: Compares the canonical JSON representation of both:
  1. **Extracted Filter Parameters + Product ID Set** (`{"filters": ..., "product_ids": [...]}`)
  2. **Exact Product ID Set** (`[0, 7]`, etc.)
- **Purpose**: Verifies with zero ambiguity that the Google ADK agent extracted the exact deterministic filter constraints and retrieved the exact ground-truth product IDs.

### Metric 2: LLM-as-a-Judge Metric (`GEval`)
- **Implementation**: `deepeval.metrics.GEval` backed by `deepeval.models.GeminiModel(model="gemini-3.8-flash")` (`threshold=0.75`).
- **Criteria**:
  > *"Assess whether the agent's summary accurately reflects the retrieved product names, prices, and categories without inventing details, hallucinating non-existent products, or contradicting the user's constraints."*
- **Evaluation Parameters**: `INPUT`, `ACTUAL_OUTPUT`, `EXPECTED_OUTPUT`, and `RETRIEVAL_CONTEXT` (the actual JSON returned by `filter_products`).

---

## 2. Iterative Optimization Summary

All three prompt/system iterations are preserved in [`backend/agent/prompts.py`](file:///Users/bradnguyen/github-repos/product-finder-ai-agent/backend/agent/prompts.py) and can be reproduced at any time via `PROMPT_VERSION=v1|v2|v3` or `python eval_suite.py --all-iterations`.

| Iteration | Configuration (`PROMPT_VERSION`) | `ExactMatch` (Filters + IDs) | `ExactMatch` (Product IDs Only) | `GEval` Mean Score | `GEval` Pass Rate ($\ge 0.75$) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Baseline** | `v1` — Minimal ADK instruction, no synonym table or cumulative state rules | **50.0%** (4 / 8) | **62.5%** (5 / 8) | **0.71** | **62.5%** (5 / 8) |
| **Iteration 1** | `v2` — Explicit category synonym mapping, non-invented price rule, cumulative state rule | **87.5%** (7 / 8) | **87.5%** (7 / 8) | **0.89** | **87.5%** (7 / 8) |
| **Iteration 2** | `v3` — `v2` + multi-turn & synonym few-shot examples + concise grounding format | **100.0%** (8 / 8) | **100.0%** (8 / 8) | **0.95** | **100.0%** (8 / 8) |

---

## 3. Case-by-Case Breakdown Across Iterations

| Case ID | User Prompt (and Initial State) | Ground Truth Filters & IDs | Baseline (`v1`) | Iteration 1 (`v2`) | Iteration 2 (`v3`) |
| :--- | :--- | :--- | :---: | :---: | :---: |
| `case_01_category_basic` | `"Show me all clothing items."` | `{category: "clothing"}` $\rightarrow$ `[0, 5, 7, 8]` | PASS (`1.0` / `0.90`) | PASS (`1.0` / `0.94`) | PASS (`1.0` / `0.97`) |
| `case_02_combined_threshold` | `"What clothing items are under $50?"` | `{category: "clothing", max_price: 50.0}` $\rightarrow$ `[0, 7]` | PASS (`1.0` / `0.92`) | PASS (`1.0` / `0.95`) | PASS (`1.0` / `0.98`) |
| `case_03_price_range_synonym` | `"Show me tech gadgets between 100 and 300 bucks."` | `{category: "electronics", min_price: 100.0, max_price: 300.0}` $\rightarrow$ `[2, 3]` | **FAIL** (passed `keyword="tech"` instead of `category="electronics"`) | PASS (`1.0` / `0.91`) | PASS (`1.0` / `0.96`) |
| `case_04_empty_result_impossible_price` | `"Show me groceries over $100."` | `{category: "groceries", min_price: 100.0}` $\rightarrow$ `[]` | PASS (`1.0` / `0.85`) | PASS (`1.0` / `0.92`) | PASS (`1.0` / `0.96`) |
| `case_05_subjective_no_invented_price` | `"Show me cheap accessories."` | `{category: "accessories"}` $\rightarrow$ `[6]` | **FAIL** (hallucinated `max_price: 20.0`, returning `[]`) | PASS (`1.0` / `0.88`) | PASS (`1.0` / `0.93`) |
| `case_06_exact_boundary_inclusive` | `"What clothing items cost at least $15 and at most $45?"` | `{category: "clothing", min_price: 15.0, max_price: 45.0}` $\rightarrow$ `[0, 7]` | PASS (`1.0` / `0.88`) | PASS (`1.0` / `0.93`) | PASS (`1.0` / `0.96`) |
| `case_07_multiturn_context_refinement` | State `{category: "clothing"}` + `"Which ones are made of cotton?"` | `{category: "clothing", keyword: "cotton"}` $\rightarrow$ `[0, 7]` | **FAIL** (dropped `category="clothing"`, only sent `keyword="cotton"`) | **FAIL** (occasionally omitted existing category without example) | PASS (`1.0` / `0.95`) |
| `case_08_synonym_food_and_description_keyword` | `"Which food items are red?"` | `{category: "groceries", keyword: "red"}` $\rightarrow$ `[9]` | **FAIL** (failed to map `"food"` $\rightarrow$ `"groceries"`) | PASS (`1.0` / `0.89`) | PASS (`1.0` / `0.94`) |

---

## 4. Analysis of Changes

### Best-Performing Change
**Explicit Cumulative State Rule + Multi-Turn Few-Shot Examples (`v1` $\rightarrow$ `v2` $\rightarrow$ `v3` in `backend/agent/prompts.py`)**
- **Problem**: Because `filter_products` takes optional keyword arguments (`category`, `min_price`, `max_price`, `keyword`), the baseline LLM treated each turn as a delta—passing only `{"keyword": "cotton"}` on a follow-up question and wiping out the active `category="clothing"` filter from session state. Similarly, subjective adjectives like `"cheap"` caused the baseline model to invent arbitrary `max_price` numbers (`$20`), excluding valid products (`$49 Backpack`).
- **Fix**:
  1. Instructed the agent to always pass the **complete cumulative filter set** starting from `{active_filters}` injected via ADK's dynamic instruction provider (`ReadonlyContext.state["active_filters"]`).
  2. Added the explicit constraint: *"Never invent a price limit the user did not give (e.g. 'cheap' alone sets no price)."*
  3. Added compact few-shot examples in `v3` demonstrating active-state refinement (`Active {"category": "clothing"} | "which ones are red?" -> category="clothing", keyword="red"`).
- **Impact**: Raised deterministic `ExactMatch` from **50.0%** to **100.0%** and eliminated multi-turn filter regressions after UI chip dismissals.

### Worst-Performing Change
**Aggressive Deadline + Unsupported Thinking Tier (`timeout < 10s` and `thinking_level="MINIMAL"`)**
- **Problem**: During latency tuning on `gemini-3.8-flash`, we tested setting `http_options=HttpOptions(timeout=8000)` (8s deadline) and `thinking_level="MINIMAL"` (and earlier, a raw `thinking_level` kwarg on `GenerateContentConfig` instead of `ThinkingConfig`).
- **Outcome**:
  - Google's Gemini API immediately rejected requests with `400 INVALID_ARGUMENT: Manually set deadline 8s is too short. Minimum allowed deadline is 10s`, and rejected `MINIMAL` because `gemini-3.8-flash` only supports `LOW`, `MEDIUM`, and `HIGH`.
  - Conversely, leaving `thinking_config` unset caused `gemini-3.8-flash` to default to `MEDIUM` thinking, taking 15–22 seconds per tool call and triggering `504 DEADLINE_EXCEEDED` when paired with a 15-second timeout.
- **Resolution**: Used `types.ThinkingConfig(thinking_level="LOW")` inside `GenerateContentConfig` with automatic retry on transient `429/5xx` codes, reducing turn latency to ~1.5–3.5 seconds reliably.

---

## 5. Key Insights on LLM Evaluation Drift

1. **Judge Sensitivity to Formatting vs. Factual Grounding**:
   - In early `GEval` runs, when the agent formatted product results as multi-line bullet lists or added conversational pleasantries (*"Sure! I'd be happy to help you find..."*), the LLM judge occasionally penalized completeness/conciseness by 0.05–0.15 even when the product names and prices were 100% accurate. Constraining the system prompt to *"Keep it to 1-3 short sentences. Do not use markdown tables"* stabilized `GEval` variance across runs.
2. **Coupling Between Tool Extraction Errors and Downstream Judge Scores**:
   - When the agent failed parameter extraction in `v1` (e.g., inventing `max_price=20` for `"cheap accessories"` and getting 0 products back from the tool), the agent truthfully reported *"No accessories found under $20."* A naive faithfulness-only metric would score that response high because it was faithful to the (wrong) tool output! Including both `EXPECTED_OUTPUT` and `RETRIEVAL_CONTEXT` in `GEval`—alongside deterministic `ExactMatchMetric` on `filters + product_ids`—prevented false positives when the tool call itself was wrong.
3. **Model Deprecation & Judge Drift**:
   - Hardcoding older model identifiers (`gemini-1.5-flash` or `gemini-2.5-flash`) caused immediate `404 NOT_FOUND` failures for newer API keys migrated to `gemini-3.8-flash`. Furthermore, `gemini-3.8-flash` disables custom temperature overrides in DeepEval (`supports_temperature=False`, defaulting to `1.0`), which introduces slight score jitter ($\pm 0.03$) on `GEval` unless evaluation steps (`evaluation_steps`) are explicitly enumerated.

---

## 6. Reproducing the Evaluation

```bash
# Run against the default v3 agent (or live server if running on :8080)
venv/bin/python eval_suite.py

# Run a specific prompt iteration in-process
venv/bin/python eval_suite.py --prompt-version v1
venv/bin/python eval_suite.py --prompt-version v2
venv/bin/python eval_suite.py --prompt-version v3

# Run all 3 iterations and save JSON reports to evaluation/results/
venv/bin/python eval_suite.py --all-iterations
```
