# Sprint 3: Eval Harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an automated evaluation harness that runs the held-out test sets through both baseline and fine-tuned models, computes per-adapter metrics from the design spec (Section 6), checks ship/no-ship criteria, and stores results in a `model_eval_runs` table for regression tracking.

**Architecture:** Extend the existing `compare_models.py` (which only checks validity + latency) into a full metrics pipeline. Add a `scripts/training/eval_harness.py` module with metric computation functions per adapter. Add a `scripts/training/ship_criteria.py` module that codifies the blocking/non-blocking thresholds from the spec. Add a `ModelEvalRun` SQLAlchemy model to persist results. Add a CLI script `scripts/training/run_eval_harness.py` that ties it together — loads test JSONL, runs models, computes metrics, checks ship criteria, optionally stores to DB.

**Tech Stack:** Python, pytest, SQLAlchemy, asyncio, Ollama API (via existing `ollama_generate`)

**Spec:** `docs/superpowers/specs/2026-03-21-fine-tuned-model-design.md` (Section 6)

**Dependencies:** Sprint 2 (PR #126) and Sprint 2.5 (PR #129) merged — provides validators, test JSONL files, and Modelfiles. Codebase integration (PR #127) merged — provides `model_for_task()`, `compare_models.py`.

**Deferred:** Claude-as-judge for D4BL alignment scoring (requires API key + cost), community feedback loop, HuggingFace Hub model card publishing, `adversarial_pass_rate` and `community_framing_f1` computation (require curated adversarial/community test subsets), `relevance_correlation` (requires scipy), baseline model comparison in eval runs (use existing `compare_models.py` for A/B).

**Known limitations:**
- **Test set sizes are smaller than spec targets:** The spec calls for 30-50 examples per adapter; current test sets have 15-20. Expansion is deferred to a follow-up task.
- **Explainer and evaluator will report `no_ship` until LLM-judged metrics are added:** Several blocking criteria (`factual_accuracy`, `d4bl_composite` for explainer; `bias_mae` for evaluator) require Claude-as-judge scoring, which is deferred. Use `--partial` flag to evaluate only computable metrics during development.

---

## File Structure

```
scripts/training/
├── eval_harness.py              # Create: metric computation per adapter
├── ship_criteria.py             # Create: ship/no-ship threshold definitions + checker
├── run_eval_harness.py          # Create: CLI entry point — load, run, score, persist
├── compare_models.py            # Existing (PR #127): validity + latency comparison
├── validate_model_output.py     # Existing (Sprint 2): JSON validators
src/d4bl/infra/
├── database.py                  # Modify: add ModelEvalRun model
supabase/migrations/
├── 20260325000001_add_model_eval_runs.sql  # Create: migration for model_eval_runs table
tests/
├── test_training/
│   ├── test_eval_harness.py     # Create: metric computation unit tests
│   ├── test_ship_criteria.py    # Create: ship criteria checker tests
│   ├── test_run_eval_harness.py # Create: CLI integration tests
```

---

## Task 1: Add Ship Criteria Definitions

**Files:**
- Create: `scripts/training/ship_criteria.py`
- Create: `tests/test_training/test_ship_criteria.py`

- [ ] **Step 1: Write failing tests for ship criteria checker**

Create `tests/test_training/test_ship_criteria.py`:

```python
"""Tests for ship/no-ship criteria checker."""
from __future__ import annotations

import pytest

from scripts.training.ship_criteria import (
    SHIP_CRITERIA,
    ShipDecision,
    check_ship_criteria,
)


class TestShipCriteria:
    def test_criteria_has_all_tasks(self):
        assert "query_parser" in SHIP_CRITERIA
        assert "explainer" in SHIP_CRITERIA
        assert "evaluator" in SHIP_CRITERIA

    def test_all_criteria_have_blocking_flag(self):
        for task, criteria in SHIP_CRITERIA.items():
            for metric, spec in criteria.items():
                assert "blocking" in spec, f"{task}.{metric} missing 'blocking'"
                assert "min" in spec or "max" in spec, (
                    f"{task}.{metric} needs 'min' or 'max'"
                )


class TestCheckShipCriteria:
    def test_ship_when_all_blocking_pass(self):
        metrics = {
            "json_valid_rate": 0.98,
            "entity_f1": 0.85,
            "data_source_accuracy": 0.90,
            "p95_latency_ms": 800,
            "adversarial_pass_rate": 0.90,
            "community_framing_f1": 0.75,
        }
        result = check_ship_criteria(metrics, "query_parser")
        assert result.decision == "ship"
        assert result.blocking_failures == []

    def test_no_ship_when_blocking_fails(self):
        metrics = {
            "json_valid_rate": 0.80,  # below 0.95 threshold
            "entity_f1": 0.85,
            "data_source_accuracy": 0.90,
            "p95_latency_ms": 800,
            "adversarial_pass_rate": 0.90,
            "community_framing_f1": 0.75,
        }
        result = check_ship_criteria(metrics, "query_parser")
        assert result.decision == "no_ship"
        assert "json_valid_rate" in [f.metric for f in result.blocking_failures]

    def test_ship_with_gaps_when_only_nonblocking_fails(self):
        metrics = {
            "json_valid_rate": 0.98,
            "entity_f1": 0.85,
            "data_source_accuracy": 0.90,
            "p95_latency_ms": 800,
            "adversarial_pass_rate": 0.90,
            "community_framing_f1": 0.50,  # below 0.70 but non-blocking
        }
        result = check_ship_criteria(metrics, "query_parser")
        assert result.decision == "ship_with_gaps"
        assert len(result.nonblocking_failures) > 0

    def test_max_threshold_check(self):
        """p95_latency_ms uses 'max' not 'min' — exceeding is a failure."""
        metrics = {
            "json_valid_rate": 0.98,
            "entity_f1": 0.85,
            "data_source_accuracy": 0.90,
            "p95_latency_ms": 1500,  # above 1000 max
            "adversarial_pass_rate": 0.90,
            "community_framing_f1": 0.75,
        }
        result = check_ship_criteria(metrics, "query_parser")
        assert result.decision == "no_ship"
        assert "p95_latency_ms" in [f.metric for f in result.blocking_failures]

    def test_missing_metric_treated_as_failure(self):
        metrics = {"json_valid_rate": 0.98}  # missing everything else
        result = check_ship_criteria(metrics, "query_parser")
        assert result.decision == "no_ship"
        assert len(result.blocking_failures) > 0

    def test_partial_mode_skips_missing_metrics(self):
        """In partial mode, missing metrics are not treated as failures."""
        metrics = {"json_valid_rate": 0.98}  # only one metric provided
        result = check_ship_criteria(metrics, "query_parser", partial=True)
        # json_valid_rate passes, missing ones skipped — no blocking failures
        assert result.decision == "ship"

    def test_unknown_task_raises(self):
        with pytest.raises(KeyError):
            check_ship_criteria({}, "nonexistent_task")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_training/test_ship_criteria.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.training.ship_criteria'`

- [ ] **Step 3: Implement ship_criteria.py**

Create `scripts/training/ship_criteria.py`:

```python
"""Ship/no-ship criteria for fine-tuned models.

Codifies the thresholds from the design spec (Section 6.4).
Blocking criteria must pass to ship. Non-blocking criteria can ship
with known gaps and a plan to fix.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# From design spec Section 6.4 — do not change without updating the spec.
SHIP_CRITERIA: dict[str, dict[str, dict]] = {
    "query_parser": {
        "json_valid_rate":       {"min": 0.95, "blocking": True},
        "entity_f1":             {"min": 0.80, "blocking": True},
        "data_source_accuracy":  {"min": 0.85, "blocking": True},
        "community_framing_f1":  {"min": 0.70, "blocking": False},
        "p95_latency_ms":        {"max": 1000, "blocking": True},
        "adversarial_pass_rate": {"min": 0.85, "blocking": True},
    },
    "explainer": {
        "json_valid_rate":       {"min": 0.95, "blocking": True},
        "factual_accuracy":      {"min": 0.90, "blocking": True},
        "d4bl_composite":        {"min": 3.5,  "blocking": True},
        "register_consistency":  {"min": 3.0,  "blocking": False},
        "p95_latency_ms":        {"max": 3000, "blocking": True},
    },
    "evaluator": {
        "hallucination_accuracy": {"min": 0.85, "blocking": True},
        "relevance_mae":          {"max": 0.8,  "blocking": True},
        "relevance_correlation":  {"min": 0.70, "blocking": False},
        "bias_mae":               {"max": 1.0,  "blocking": True},
    },
}


@dataclass
class CriterionFailure:
    metric: str
    threshold: float
    actual: float | None
    direction: str  # "min" or "max"
    blocking: bool


@dataclass
class ShipDecision:
    decision: str  # "ship", "no_ship", "ship_with_gaps"
    blocking_failures: list[CriterionFailure] = field(default_factory=list)
    nonblocking_failures: list[CriterionFailure] = field(default_factory=list)
    metrics_checked: int = 0


def check_ship_criteria(
    metrics: dict[str, float], task: str, *, partial: bool = False,
) -> ShipDecision:
    """Check metrics against ship criteria for a given task.

    Args:
        metrics: Dict of metric_name -> value.
        task: One of "query_parser", "explainer", "evaluator".
        partial: If True, skip criteria for metrics not present in ``metrics``.
            Useful during development when LLM-judged metrics are not yet available.

    Returns:
        ShipDecision with decision string and failure details.

    Raises:
        KeyError: If task is not in SHIP_CRITERIA.
    """
    criteria = SHIP_CRITERIA[task]
    blocking_failures: list[CriterionFailure] = []
    nonblocking_failures: list[CriterionFailure] = []

    for metric, spec in criteria.items():
        actual = metrics.get(metric)
        blocking = spec["blocking"]

        # In partial mode, skip metrics that aren't available
        if partial and actual is None:
            continue

        failed = False
        direction = "min" if "min" in spec else "max"

        if actual is None:
            failed = True
        elif "min" in spec and actual < spec["min"]:
            failed = True
        elif "max" in spec and actual > spec["max"]:
            failed = True

        if failed:
            threshold = spec.get("min", spec.get("max"))
            failure = CriterionFailure(
                metric=metric,
                threshold=threshold,
                actual=actual,
                direction=direction,
                blocking=blocking,
            )
            if blocking:
                blocking_failures.append(failure)
            else:
                nonblocking_failures.append(failure)

    if blocking_failures:
        decision = "no_ship"
    elif nonblocking_failures:
        decision = "ship_with_gaps"
    else:
        decision = "ship"

    return ShipDecision(
        decision=decision,
        blocking_failures=blocking_failures,
        nonblocking_failures=nonblocking_failures,
        metrics_checked=len(criteria),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_training/test_ship_criteria.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/training/ship_criteria.py tests/test_training/test_ship_criteria.py
git commit -m "feat(eval): add ship/no-ship criteria definitions and checker"
```

---

## Task 2: Add Metric Computation Functions

**Files:**
- Create: `scripts/training/eval_harness.py`
- Create: `tests/test_training/test_eval_harness.py`

This module computes the per-adapter metrics defined in the design spec (Section 6.3). It takes model outputs + ground truth and returns a metrics dict that can be fed into `check_ship_criteria()`.

- [ ] **Step 1: Write failing tests for query parser metrics**

Create `tests/test_training/test_eval_harness.py`:

```python
"""Tests for eval harness metric computation."""
from __future__ import annotations

import json

import pytest

from scripts.training.eval_harness import (
    compute_entity_f1,
    compute_parser_metrics,
    compute_explainer_metrics,
    compute_evaluator_metrics,
    load_test_set,
)


class TestComputeEntityF1:
    def test_perfect_match(self):
        assert compute_entity_f1(["a", "b", "c"], ["a", "b", "c"]) == 1.0

    def test_no_overlap(self):
        assert compute_entity_f1(["a", "b"], ["c", "d"]) == 0.0

    def test_partial_overlap(self):
        # predicted: a, b — expected: a, c
        # precision = 1/2, recall = 1/2, F1 = 0.5
        assert compute_entity_f1(["a", "b"], ["a", "c"]) == pytest.approx(0.5)

    def test_empty_predicted(self):
        assert compute_entity_f1([], ["a", "b"]) == 0.0

    def test_empty_expected(self):
        assert compute_entity_f1(["a", "b"], []) == 0.0

    def test_case_insensitive(self):
        assert compute_entity_f1(["Alabama"], ["alabama"]) == 1.0


class TestComputeParserMetrics:
    def test_all_valid_outputs(self):
        outputs = [
            {"raw": '{"intent": "lookup", "entities": ["Alabama"]}', "latency": 0.5},
            {"raw": '{"intent": "compare", "entities": ["Texas", "California"]}', "latency": 0.8},
        ]
        expected = [
            {"entities": ["Alabama"], "data_sources": ["census_indicators"]},
            {"entities": ["Texas", "California"], "data_sources": ["census_indicators"]},
        ]
        metrics = compute_parser_metrics(outputs, expected)
        assert metrics["json_valid_rate"] == 1.0
        assert "entity_f1" in metrics
        assert "p95_latency_ms" in metrics
        assert metrics["p95_latency_ms"] == pytest.approx(800.0, abs=50)

    def test_invalid_json_counted(self):
        outputs = [
            {"raw": "not json", "latency": 0.5},
            {"raw": '{"intent": "lookup", "entities": ["A"]}', "latency": 0.3},
        ]
        expected = [{"entities": ["B"]}, {"entities": ["A"]}]
        metrics = compute_parser_metrics(outputs, expected)
        assert metrics["json_valid_rate"] == 0.5


class TestComputeExplainerMetrics:
    def test_valid_outputs(self):
        outputs = [
            {"raw": '{"narrative": "Test narrative."}', "latency": 1.5},
        ]
        metrics = compute_explainer_metrics(outputs)
        assert metrics["json_valid_rate"] == 1.0
        assert "p95_latency_ms" in metrics


class TestComputeEvaluatorMetrics:
    def test_hallucination_accuracy(self):
        outputs = [
            {"raw": '{"score": 5, "label": "FACTUAL"}', "latency": 0.3},
            {"raw": '{"score": 1, "label": "HALLUCINATED"}', "latency": 0.4},
        ]
        expected_labels = ["FACTUAL", "HALLUCINATED"]
        metrics = compute_evaluator_metrics(outputs, expected_labels=expected_labels)
        assert metrics["hallucination_accuracy"] == 1.0

    def test_incorrect_labels(self):
        outputs = [
            {"raw": '{"score": 5, "label": "FACTUAL"}', "latency": 0.3},
            {"raw": '{"score": 5, "label": "FACTUAL"}', "latency": 0.4},
        ]
        expected_labels = ["FACTUAL", "HALLUCINATED"]
        metrics = compute_evaluator_metrics(outputs, expected_labels=expected_labels)
        assert metrics["hallucination_accuracy"] == 0.5


class TestLoadTestSet:
    def test_load_valid_jsonl(self, tmp_path):
        p = tmp_path / "test.jsonl"
        examples = [
            {"messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "question"},
                {"role": "assistant", "content": '{"intent": "lookup"}'},
            ]}
        ]
        p.write_text("\n".join(json.dumps(e) for e in examples))
        result = load_test_set(str(p))
        assert len(result) == 1
        assert result[0]["input"] == "question"
        assert result[0]["expected_raw"] == '{"intent": "lookup"}'

    def test_load_empty_file(self, tmp_path):
        p = tmp_path / "empty.jsonl"
        p.write_text("")
        result = load_test_set(str(p))
        assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_training/test_eval_harness.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement eval_harness.py**

Create `scripts/training/eval_harness.py`:

```python
"""Metric computation for D4BL fine-tuned model evaluation.

Computes per-adapter metrics defined in the design spec (Section 6.3).
Takes model outputs + ground truth, returns metrics dicts compatible
with ``ship_criteria.check_ship_criteria()``.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from scripts.training.validate_model_output import (
    ValidationResult,
    validate_evaluator_output,
    validate_explainer_output,
    validate_parser_output,
)


def load_test_set(path: str) -> list[dict]:
    """Load a ChatML JSONL test set and extract input/expected pairs.

    Each line is ``{"messages": [system, user, assistant]}``.
    Returns list of ``{"input": str, "expected_raw": str, "expected": dict|None}``.
    """
    results = []
    text = Path(path).read_text().strip()
    if not text:
        return []
    for line in text.splitlines():
        if not line.strip():
            continue
        example = json.loads(line)
        messages = example["messages"]
        user_msg = messages[1]["content"]
        assistant_msg = messages[2]["content"]
        try:
            expected = json.loads(assistant_msg)
        except (json.JSONDecodeError, KeyError):
            expected = None
        results.append({
            "input": user_msg,
            "expected_raw": assistant_msg,
            "expected": expected,
        })
    return results


def compute_entity_f1(
    predicted: list[str], expected: list[str]
) -> float:
    """Compute F1 score between predicted and expected entity lists.

    Case-insensitive comparison.
    """
    pred_set = {e.lower() for e in predicted}
    exp_set = {e.lower() for e in expected}
    if not pred_set and not exp_set:
        return 1.0
    if not pred_set or not exp_set:
        return 0.0
    tp = len(pred_set & exp_set)
    precision = tp / len(pred_set)
    recall = tp / len(exp_set)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _percentile(values: list[float], p: float) -> float:
    """Compute the p-th percentile (0-100) of a sorted list."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_v[int(k)]
    return sorted_v[f] * (c - k) + sorted_v[c] * (k - f)


def compute_parser_metrics(
    outputs: list[dict],
    expected: list[dict],
) -> dict[str, float]:
    """Compute query parser metrics.

    Args:
        outputs: List of {"raw": str, "latency": float} from model.
        expected: List of {"entities": [...], "data_sources": [...]} ground truth.

    Returns:
        Dict with keys: json_valid_rate, schema_valid_rate, entity_f1,
        data_source_accuracy, p50_latency_ms, p95_latency_ms.
    """
    n = len(outputs)
    if n == 0:
        return {
            "json_valid_rate": 0.0, "schema_valid_rate": 0.0,
            "entity_f1": 0.0, "data_source_accuracy": 0.0,
            "p50_latency_ms": 0.0, "p95_latency_ms": 0.0,
        }

    json_valid = 0
    schema_valid = 0
    entity_f1_scores: list[float] = []
    ds_correct = 0
    latencies_ms: list[float] = []

    for i, output in enumerate(outputs):
        latencies_ms.append(output["latency"] * 1000)
        result: ValidationResult = validate_parser_output(output["raw"])

        if result.parsed is not None:
            json_valid += 1

        if result.valid:
            schema_valid += 1

        if result.parsed and i < len(expected):
            exp = expected[i]
            # Entity F1
            pred_entities = result.parsed.get("entities", [])
            exp_entities = exp.get("entities", [])
            if isinstance(pred_entities, list) and isinstance(exp_entities, list):
                entity_f1_scores.append(
                    compute_entity_f1(pred_entities, exp_entities)
                )

            # Data source accuracy
            pred_ds = set(result.parsed.get("data_sources", []))
            exp_ds = set(exp.get("data_sources", []))
            if exp_ds and pred_ds:
                ds_correct += 1 if pred_ds & exp_ds else 0

    return {
        "json_valid_rate": json_valid / n,
        "schema_valid_rate": schema_valid / n,
        "entity_f1": (
            sum(entity_f1_scores) / len(entity_f1_scores)
            if entity_f1_scores else 0.0
        ),
        "data_source_accuracy": ds_correct / n if n > 0 else 0.0,
        "p50_latency_ms": _percentile(latencies_ms, 50),
        "p95_latency_ms": _percentile(latencies_ms, 95),
    }


def compute_explainer_metrics(outputs: list[dict]) -> dict[str, float]:
    """Compute explainer metrics.

    Note: factual_accuracy, d4bl_composite, and register_consistency
    require LLM-as-judge scoring (deferred — returns None for these).
    JSON validity and latency are computed here.

    Args:
        outputs: List of {"raw": str, "latency": float} from model.

    Returns:
        Dict with json_valid_rate, p50_latency_ms, p95_latency_ms,
        and None placeholders for LLM-judged metrics.
    """
    n = len(outputs)
    if n == 0:
        return {
            "json_valid_rate": 0.0, "p50_latency_ms": 0.0,
            "p95_latency_ms": 0.0, "factual_accuracy": None,
            "d4bl_composite": None, "register_consistency": None,
        }

    json_valid = 0
    latencies_ms: list[float] = []

    for output in outputs:
        latencies_ms.append(output["latency"] * 1000)
        result = validate_explainer_output(output["raw"])
        if result.parsed is not None:
            json_valid += 1

    return {
        "json_valid_rate": json_valid / n,
        "p50_latency_ms": _percentile(latencies_ms, 50),
        "p95_latency_ms": _percentile(latencies_ms, 95),
        # LLM-judged metrics — deferred (require Claude API)
        "factual_accuracy": None,
        "d4bl_composite": None,
        "register_consistency": None,
    }


def compute_evaluator_metrics(
    outputs: list[dict],
    expected_labels: list[str] | None = None,
    expected_scores: list[float] | None = None,
) -> dict[str, float]:
    """Compute evaluator metrics.

    Args:
        outputs: List of {"raw": str, "latency": float} from model.
        expected_labels: Ground-truth labels (FACTUAL/HALLUCINATED) for
            hallucination accuracy. None if not applicable.
        expected_scores: Ground-truth 1-5 scores for relevance MAE.
            None if not applicable.

    Returns:
        Dict with hallucination_accuracy, relevance_mae, bias_mae, etc.
    """
    n = len(outputs)
    if n == 0:
        return {
            "hallucination_accuracy": 0.0,
            "relevance_mae": None,
            "bias_mae": None,
            "relevance_correlation": None,
        }

    json_valid = 0
    correct_labels = 0
    score_errors: list[float] = []

    for i, output in enumerate(outputs):
        result = validate_evaluator_output(output["raw"])
        if result.parsed is not None:
            json_valid += 1

        if result.valid and result.parsed:
            # Hallucination accuracy
            if expected_labels and i < len(expected_labels):
                pred_label = result.parsed.get("label", "").upper()
                if pred_label == expected_labels[i].upper():
                    correct_labels += 1

            # Score MAE
            if expected_scores and i < len(expected_scores):
                pred_score = result.parsed.get("score")
                if isinstance(pred_score, (int, float)):
                    score_errors.append(abs(pred_score - expected_scores[i]))

    label_count = len(expected_labels) if expected_labels else 0

    return {
        "hallucination_accuracy": (
            correct_labels / label_count if label_count > 0 else 0.0
        ),
        "relevance_mae": (
            sum(score_errors) / len(score_errors) if score_errors else None
        ),
        "bias_mae": None,  # Requires separate bias test set
        "relevance_correlation": None,  # Requires scipy — deferred
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_training/test_eval_harness.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/training/eval_harness.py tests/test_training/test_eval_harness.py
git commit -m "feat(eval): add metric computation functions for all three adapters"
```

---

## Task 3: Add ModelEvalRun Database Model

**Files:**
- Modify: `src/d4bl/infra/database.py`
- Create: `supabase/migrations/20260325000001_add_model_eval_runs.sql`
- Modify: `tests/test_training/test_eval_harness.py` (add model test)

- [ ] **Step 1: Write failing test for ModelEvalRun**

Add to `tests/test_training/test_eval_harness.py`:

```python
from d4bl.infra.database import ModelEvalRun


class TestModelEvalRun:
    def test_model_has_required_columns(self):
        """ModelEvalRun should have all columns from the design spec."""
        columns = {c.name for c in ModelEvalRun.__table__.columns}
        expected = {
            "id", "model_name", "model_version", "base_model_name",
            "task", "test_set_hash", "metrics", "ship_decision",
            "blocking_failures", "created_at",
        }
        assert expected.issubset(columns)

    def test_tablename(self):
        assert ModelEvalRun.__tablename__ == "model_eval_runs"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_training/test_eval_harness.py::TestModelEvalRun -v`
Expected: FAIL with `ImportError: cannot import name 'ModelEvalRun'`

- [ ] **Step 3: Add ModelEvalRun to database.py**

In `src/d4bl/infra/database.py`, first add the JSONB import near the top where the other PostgreSQL dialect imports are (around line 23):

```python
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
```

Then add after the `EvaluationResult` class (after line ~108):

```python
class ModelEvalRun(Base):
    """Track evaluation runs per model version for regression detection."""
    __tablename__ = "model_eval_runs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    model_name = Column(String(100), nullable=False, index=True)
    model_version = Column(String(50), nullable=False)
    base_model_name = Column(String(100), nullable=False)
    task = Column(String(50), nullable=False, index=True)
    test_set_hash = Column(String(64), nullable=False)
    metrics = Column(JSONB, nullable=False)
    ship_decision = Column(String(20), nullable=False)
    blocking_failures = Column(JSONB, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now, index=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "model_name": self.model_name,
            "model_version": self.model_version,
            "base_model_name": self.base_model_name,
            "task": self.task,
            "test_set_hash": self.test_set_hash,
            "metrics": self.metrics,
            "ship_decision": self.ship_decision,
            "blocking_failures": self.blocking_failures,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
```

- [ ] **Step 4: Create migration**

Create `supabase/migrations/20260325000001_add_model_eval_runs.sql`:

```sql
-- Track evaluation runs per model version for regression detection
CREATE TABLE IF NOT EXISTS model_eval_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    base_model_name VARCHAR(100) NOT NULL,
    task VARCHAR(50) NOT NULL,
    test_set_hash VARCHAR(64) NOT NULL,
    metrics JSONB NOT NULL,
    ship_decision VARCHAR(20) NOT NULL,
    blocking_failures JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_model_eval_runs_model_name ON model_eval_runs (model_name);
CREATE INDEX IF NOT EXISTS idx_model_eval_runs_task ON model_eval_runs (task);
CREATE INDEX IF NOT EXISTS idx_model_eval_runs_created_at ON model_eval_runs (created_at);
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_training/test_eval_harness.py::TestModelEvalRun -v`
Expected: All 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/d4bl/infra/database.py supabase/migrations/20260325000001_add_model_eval_runs.sql tests/test_training/test_eval_harness.py
git commit -m "feat(eval): add ModelEvalRun database model and migration"
```

---

## Task 4: Build the Eval Harness CLI

**Files:**
- Create: `scripts/training/run_eval_harness.py`
- Create: `tests/test_training/test_run_eval_harness.py`

This ties everything together: loads test JSONL, runs both models via Ollama, computes metrics, checks ship criteria, optionally persists to DB.

- [ ] **Step 1: Write failing tests for CLI components**

Create `tests/test_training/test_run_eval_harness.py`:

```python
"""Tests for the eval harness CLI."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.training.run_eval_harness import (
    compute_test_set_hash,
    format_eval_report,
    run_task_eval,
    EvalRunResult,
)


class TestComputeTestSetHash:
    def test_deterministic(self, tmp_path):
        p = tmp_path / "test.jsonl"
        p.write_text('{"messages": [{"role": "system", "content": "s"}, '
                      '{"role": "user", "content": "q"}, '
                      '{"role": "assistant", "content": "a"}]}\n')
        h1 = compute_test_set_hash(str(p))
        h2 = compute_test_set_hash(str(p))
        assert h1 == h2
        assert len(h1) == 64  # SHA256 hex

    def test_different_content_different_hash(self, tmp_path):
        p1 = tmp_path / "a.jsonl"
        p2 = tmp_path / "b.jsonl"
        p1.write_text('{"messages": [{"role": "system", "content": "s"}, '
                       '{"role": "user", "content": "q1"}, '
                       '{"role": "assistant", "content": "a"}]}')
        p2.write_text('{"messages": [{"role": "system", "content": "s"}, '
                       '{"role": "user", "content": "q2"}, '
                       '{"role": "assistant", "content": "a"}]}')
        assert compute_test_set_hash(str(p1)) != compute_test_set_hash(str(p2))


class TestFormatEvalReport:
    def test_report_includes_decision(self):
        from scripts.training.ship_criteria import ShipDecision
        result = EvalRunResult(
            task="query_parser",
            model_name="d4bl-query-parser",
            model_version="v1.0",
            base_model_name="mistral",
            test_set_hash="abc123",
            metrics={"json_valid_rate": 0.98, "entity_f1": 0.85},
            ship_decision=ShipDecision(decision="ship"),
        )
        report = format_eval_report([result])
        assert "query_parser" in report
        assert "SHIP" in report.upper()
        assert "0.98" in report


class TestRunTaskEval:
    @pytest.mark.asyncio
    @patch("scripts.training.run_eval_harness._run_prompt", new_callable=AsyncMock)
    async def test_runs_all_examples(self, mock_run):
        mock_run.return_value = ('{"intent": "lookup", "entities": ["AL"]}', 0.5)
        test_set = [
            {"input": "q1", "expected_raw": '{"entities": ["AL"]}',
             "expected": {"entities": ["AL"], "data_sources": ["census_indicators"]}},
            {"input": "q2", "expected_raw": '{"entities": ["TX"]}',
             "expected": {"entities": ["TX"], "data_sources": ["census_indicators"]}},
        ]
        result = await run_task_eval(
            task="query_parser",
            test_set=test_set,
            model_name="d4bl-query-parser",
            model_version="v1.0",
            base_model_name="mistral",
            base_url="http://localhost:11434",
            test_set_hash="abc",
        )
        assert result.task == "query_parser"
        assert result.metrics["json_valid_rate"] == 1.0
        assert mock_run.call_count == 2  # only fine-tuned (no baseline in task eval)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_training/test_run_eval_harness.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement run_eval_harness.py**

Create `scripts/training/run_eval_harness.py`:

```python
"""Eval harness CLI — run test sets through models and check ship criteria.

Usage:
    python -m scripts.training.run_eval_harness
    python -m scripts.training.run_eval_harness --task query_parser
    python -m scripts.training.run_eval_harness --persist  # save to DB
    python -m scripts.training.run_eval_harness --model-version v1.1
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from scripts.training.eval_harness import (
    compute_evaluator_metrics,
    compute_explainer_metrics,
    compute_parser_metrics,
    load_test_set,
)
from scripts.training.ship_criteria import ShipDecision, check_ship_criteria

logger = logging.getLogger(__name__)

# Default test set paths (relative to repo root)
DEFAULT_TEST_SETS: dict[str, str] = {
    "query_parser": "scripts/training_data/final/query_parser_test.jsonl",
    "explainer": "scripts/training_data/final/explainer_test.jsonl",
    "evaluator": "scripts/training_data/final/evaluator_test.jsonl",
}

# Fine-tuned model names per task
TASK_MODELS: dict[str, str] = {
    "query_parser": "d4bl-query-parser",
    "explainer": "d4bl-explainer",
    "evaluator": "d4bl-evaluator",
}


@dataclass
class EvalRunResult:
    task: str
    model_name: str
    model_version: str
    base_model_name: str
    test_set_hash: str
    metrics: dict[str, float | None]
    ship_decision: ShipDecision
    elapsed_seconds: float = 0.0


def compute_test_set_hash(path: str) -> str:
    """Compute SHA256 hash of a test set file for version tracking."""
    content = Path(path).read_bytes()
    return hashlib.sha256(content).hexdigest()


async def _run_prompt(
    base_url: str, model: str, prompt: str, timeout: int = 120,
) -> tuple[str, float]:
    """Run a single prompt and return (output, latency_seconds)."""
    from d4bl.llm.ollama_client import ollama_generate

    start = time.monotonic()
    output = await ollama_generate(
        base_url=base_url, prompt=prompt, model=model,
        temperature=0.1, timeout_seconds=timeout,
    )
    elapsed = time.monotonic() - start
    return output, elapsed


async def run_task_eval(
    task: str,
    test_set: list[dict],
    model_name: str,
    model_version: str,
    base_model_name: str,
    base_url: str,
    test_set_hash: str,
) -> EvalRunResult:
    """Run evaluation for a single task.

    Runs all test examples through the fine-tuned model,
    computes metrics, and checks ship criteria.
    """
    start = time.monotonic()
    outputs: list[dict] = []

    for example in test_set:
        try:
            raw, latency = await _run_prompt(
                base_url, model_name, example["input"]
            )
        except Exception as e:
            logger.warning("Prompt failed: %s", e)
            raw, latency = str(e), 0.0

        outputs.append({"raw": raw, "latency": latency})

    # Compute task-specific metrics
    if task == "query_parser":
        expected = [ex.get("expected", {}) or {} for ex in test_set]
        metrics = compute_parser_metrics(outputs, expected)
    elif task == "explainer":
        metrics = compute_explainer_metrics(outputs)
    elif task == "evaluator":
        # Extract expected labels from ground truth
        expected_labels = []
        for ex in test_set:
            exp = ex.get("expected") or {}
            label = exp.get("label", "")
            expected_labels.append(label)
        metrics = compute_evaluator_metrics(
            outputs, expected_labels=expected_labels if any(expected_labels) else None
        )
    else:
        metrics = {}

    # Filter None values before ship criteria check (deferred LLM-judged metrics)
    checkable = {k: v for k, v in metrics.items() if v is not None}
    ship_decision = check_ship_criteria(checkable, task)

    # Note: explainer and evaluator will get "no_ship" until LLM-judged
    # metrics (factual_accuracy, d4bl_composite, bias_mae) are implemented.
    # Use --partial flag to evaluate only computable metrics.
    elapsed = time.monotonic() - start

    return EvalRunResult(
        task=task,
        model_name=model_name,
        model_version=model_version,
        base_model_name=base_model_name,
        test_set_hash=test_set_hash,
        metrics=metrics,
        ship_decision=ship_decision,
        elapsed_seconds=round(elapsed, 2),
    )


def format_eval_report(results: list[EvalRunResult]) -> str:
    """Format eval results into a human-readable report."""
    lines = ["=" * 70, "D4BL Model Evaluation Report", "=" * 70, ""]

    for r in results:
        decision_str = r.ship_decision.decision.upper()
        lines.append(f"## {r.task} — {r.model_name} ({r.model_version})")
        lines.append(f"   Decision: {decision_str}")
        lines.append(f"   Elapsed:  {r.elapsed_seconds:.1f}s")
        lines.append(f"   Test set: {r.test_set_hash[:12]}...")
        lines.append("")

        lines.append("   Metrics:")
        # Metrics that should display as raw numbers, not percentages
        _RAW_METRICS = {"p50_latency_ms", "p95_latency_ms", "relevance_mae", "bias_mae"}
        for metric, value in sorted(r.metrics.items()):
            if value is None:
                lines.append(f"     {metric}: (deferred — requires LLM judge)")
            elif metric in _RAW_METRICS:
                lines.append(f"     {metric}: {value:.2f}")
            elif isinstance(value, float) and value <= 1.0:
                lines.append(f"     {metric}: {value:.2%}")
            else:
                lines.append(f"     {metric}: {value:.2f}")
        lines.append("")

        if r.ship_decision.blocking_failures:
            lines.append("   BLOCKING FAILURES:")
            for f in r.ship_decision.blocking_failures:
                actual = f"(missing)" if f.actual is None else f"{f.actual}"
                lines.append(
                    f"     {f.metric}: {actual} "
                    f"({'<' if f.direction == 'min' else '>'} "
                    f"{f.threshold})"
                )
            lines.append("")

        if r.ship_decision.nonblocking_failures:
            lines.append("   NON-BLOCKING GAPS:")
            for f in r.ship_decision.nonblocking_failures:
                actual = f"(missing)" if f.actual is None else f"{f.actual}"
                lines.append(f"     {f.metric}: {actual} (target: {f.threshold})")
            lines.append("")

        lines.append("-" * 70)
        lines.append("")

    # Summary
    decisions = [r.ship_decision.decision for r in results]
    if all(d == "ship" for d in decisions):
        lines.append("OVERALL: SHIP — all tasks pass blocking criteria")
    elif any(d == "no_ship" for d in decisions):
        lines.append("OVERALL: NO SHIP — blocking failures detected")
    else:
        lines.append("OVERALL: SHIP WITH GAPS — non-blocking issues remain")

    return "\n".join(lines)


async def persist_results(results: list[EvalRunResult]) -> None:
    """Save eval results to the model_eval_runs database table."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from d4bl.infra.database import ModelEvalRun
    from d4bl.settings import get_settings

    settings = get_settings()
    db_url = (
        f"postgresql+asyncpg://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )
    engine = create_async_engine(db_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        for r in results:
            run = ModelEvalRun(
                model_name=r.model_name,
                model_version=r.model_version,
                base_model_name=r.base_model_name,
                task=r.task,
                test_set_hash=r.test_set_hash,
                metrics=r.metrics,
                ship_decision=r.ship_decision.decision,
                blocking_failures=[
                    {
                        "metric": f.metric,
                        "threshold": f.threshold,
                        "actual": f.actual,
                        "direction": f.direction,
                    }
                    for f in r.ship_decision.blocking_failures
                ] or None,
            )
            session.add(run)
        await session.commit()

    await engine.dispose()
    logger.info("Persisted %d eval runs to database", len(results))


async def main(args: argparse.Namespace) -> int:
    tasks = [args.task] if args.task else list(DEFAULT_TEST_SETS.keys())
    results: list[EvalRunResult] = []

    for task in tasks:
        test_path = args.test_set or DEFAULT_TEST_SETS[task]
        if not Path(test_path).exists():
            logger.error("Test set not found: %s", test_path)
            continue

        test_set = load_test_set(test_path)
        if not test_set:
            logger.warning("Empty test set: %s", test_path)
            continue

        logger.info(
            "Running %s eval: %d examples, model=%s",
            task, len(test_set), TASK_MODELS[task],
        )

        result = await run_task_eval(
            task=task,
            test_set=test_set,
            model_name=TASK_MODELS[task],
            model_version=args.model_version,
            base_model_name=args.baseline,
            base_url=args.ollama_url,
            test_set_hash=compute_test_set_hash(test_path),
        )
        results.append(result)

    if not results:
        logger.error("No results — check test set paths")
        return 1

    print(format_eval_report(results))

    if args.persist:
        await persist_results(results)

    has_no_ship = any(r.ship_decision.decision == "no_ship" for r in results)
    return 1 if has_no_ship else 0


def cli() -> int:
    parser = argparse.ArgumentParser(
        description="Run D4BL model evaluation harness"
    )
    parser.add_argument(
        "--task", choices=["query_parser", "explainer", "evaluator"],
        help="Run only one task (default: all)",
    )
    parser.add_argument(
        "--test-set", help="Override test set JSONL path",
    )
    parser.add_argument(
        "--baseline", default="mistral", help="Baseline model name",
    )
    parser.add_argument(
        "--model-version", default="v1.0",
        help="Version label for this eval run",
    )
    parser.add_argument(
        "--ollama-url", default="http://localhost:11434",
        help="Ollama base URL",
    )
    parser.add_argument(
        "--persist", action="store_true",
        help="Save results to model_eval_runs DB table",
    )
    parser.add_argument(
        "--partial", action="store_true",
        help="Only check computable metrics (skip LLM-judged criteria)",
    )
    args = parser.parse_args()
    return asyncio.run(main(args))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    sys.exit(cli())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_training/test_run_eval_harness.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/training/run_eval_harness.py tests/test_training/test_run_eval_harness.py
git commit -m "feat(eval): add eval harness CLI with test-set runner and ship criteria"
```

---

## Task 5: Add Regression Detection Helpers

**Files:**
- Modify: `scripts/training/run_eval_harness.py`
- Create: `tests/test_training/test_regression.py`

Add a function to compare the current eval run against the most recent stored run for the same task, flagging regressions.

- [ ] **Step 1: Write failing tests for regression detection**

Create `tests/test_training/test_regression.py`:

```python
"""Tests for regression detection between eval runs."""
from __future__ import annotations

import pytest

from scripts.training.run_eval_harness import detect_regressions, RegressionAlert


class TestDetectRegressions:
    def test_no_regression_when_improved(self):
        previous = {"json_valid_rate": 0.90, "entity_f1": 0.80}
        current = {"json_valid_rate": 0.95, "entity_f1": 0.85}
        alerts = detect_regressions(current, previous, task="query_parser")
        assert alerts == []

    def test_regression_detected(self):
        previous = {"json_valid_rate": 0.95, "entity_f1": 0.85}
        current = {"json_valid_rate": 0.85, "entity_f1": 0.75}
        alerts = detect_regressions(current, previous, task="query_parser")
        assert len(alerts) == 2
        assert all(a.direction == "decreased" for a in alerts)

    def test_latency_regression_is_increase(self):
        previous = {"p95_latency_ms": 500}
        current = {"p95_latency_ms": 1200}
        alerts = detect_regressions(current, previous, task="query_parser")
        assert len(alerts) == 1
        assert alerts[0].direction == "increased"

    def test_no_previous_returns_empty(self):
        current = {"json_valid_rate": 0.95}
        alerts = detect_regressions(current, None, task="query_parser")
        assert alerts == []

    def test_threshold_tolerance(self):
        """Small changes (<2%) should not trigger alerts."""
        previous = {"json_valid_rate": 0.95}
        current = {"json_valid_rate": 0.94}  # -1%, within tolerance
        alerts = detect_regressions(
            current, previous, task="query_parser", tolerance=0.02
        )
        assert alerts == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_training/test_regression.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement detect_regressions()**

Add to `scripts/training/run_eval_harness.py`, after the imports:

```python
# Metrics where higher is worse (latency, MAE)
_HIGHER_IS_WORSE = {"p50_latency_ms", "p95_latency_ms", "relevance_mae", "bias_mae"}


@dataclass
class RegressionAlert:
    metric: str
    previous: float
    current: float
    delta: float
    direction: str  # "increased" or "decreased"


def detect_regressions(
    current: dict[str, float | None],
    previous: dict[str, float | None] | None,
    task: str,
    tolerance: float = 0.02,
) -> list[RegressionAlert]:
    """Compare current metrics against previous run, flag regressions.

    A regression is when a metric moves in the wrong direction by more
    than ``tolerance`` (default 2%).

    Args:
        current: Current eval metrics.
        previous: Previous eval metrics (None = no comparison).
        task: Task name (for context, currently unused).
        tolerance: Minimum absolute change to trigger alert.

    Returns:
        List of RegressionAlert for each regressed metric.
    """
    if previous is None:
        return []

    alerts: list[RegressionAlert] = []
    for metric, cur_val in current.items():
        if cur_val is None:
            continue
        prev_val = previous.get(metric)
        if prev_val is None:
            continue

        delta = cur_val - prev_val

        if metric in _HIGHER_IS_WORSE:
            # For latency/MAE, increase is bad
            if delta > tolerance:
                alerts.append(RegressionAlert(
                    metric=metric, previous=prev_val, current=cur_val,
                    delta=delta, direction="increased",
                ))
        else:
            # For accuracy/F1, decrease is bad
            if delta < -tolerance:
                alerts.append(RegressionAlert(
                    metric=metric, previous=prev_val, current=cur_val,
                    delta=delta, direction="decreased",
                ))

    return alerts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_training/test_regression.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/training/run_eval_harness.py tests/test_training/test_regression.py
git commit -m "feat(eval): add regression detection between eval runs"
```

---

## Task 6: Full Test Suite Verification

- [ ] **Step 1: Run all training-related tests**

Run: `pytest tests/test_training/ -v --ignore=tests/test_training/test_integration_models.py`
Expected: All tests PASS. Integration model tests are ignored (they require Ollama running).

- [ ] **Step 2: Run the full project test suite**

Run: `pytest tests/ -v --ignore=tests/test_training/test_integration_models.py`
Expected: All tests PASS. No regressions from adding the new model + migration.

- [ ] **Step 3: Run linting**

Run: `cd ui-nextjs && npm run lint && npm run build`
Expected: Clean (no frontend changes in this sprint).

- [ ] **Step 4: Verify test sets exist and are loadable**

Run: `python -c "from scripts.training.eval_harness import load_test_set; ts = load_test_set('scripts/training_data/final/query_parser_test.jsonl'); print(f'Loaded {len(ts)} parser examples'); ts = load_test_set('scripts/training_data/final/explainer_test.jsonl'); print(f'Loaded {len(ts)} explainer examples'); ts = load_test_set('scripts/training_data/final/evaluator_test.jsonl'); print(f'Loaded {len(ts)} evaluator examples')"`
Expected: `Loaded 15 parser examples`, `Loaded 20 explainer examples`, `Loaded 15 evaluator examples`

- [ ] **Step 5: Commit if any fixups needed**

```bash
git add -A
git commit -m "fix: address test suite issues from eval harness sprint"
```
