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

        if i < len(expected):
            exp = expected[i]
            exp_entities = exp.get("entities", [])
            if isinstance(exp_entities, list):
                if (
                    result.valid
                    and result.parsed
                    and isinstance(result.parsed.get("entities"), list)
                    and all(isinstance(e, str) for e in result.parsed["entities"])
                ):
                    entity_f1_scores.append(
                        compute_entity_f1(result.parsed["entities"], exp_entities)
                    )
                else:
                    entity_f1_scores.append(0.0)

            exp_ds_raw = exp.get("data_sources", [])
            if isinstance(exp_ds_raw, list) and exp_ds_raw:
                if (
                    result.valid
                    and result.parsed
                    and isinstance(result.parsed.get("data_sources"), list)
                ):
                    pred_ds = set(result.parsed["data_sources"])
                    exp_ds = set(exp_ds_raw)
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
    total_score_error = 0.0
    scored_count = 0

    for i, output in enumerate(outputs):
        result = validate_evaluator_output(output["raw"])
        if result.parsed is not None:
            json_valid += 1

        if result.valid and result.parsed:
            if expected_labels and i < len(expected_labels):
                pred_label = result.parsed.get("label", "").upper()
                if pred_label == expected_labels[i].upper():
                    correct_labels += 1

            if expected_scores and i < len(expected_scores):
                scored_count += 1
                pred_score = result.parsed.get("score")
                if isinstance(pred_score, (int, float)):
                    total_score_error += abs(pred_score - expected_scores[i])
                else:
                    # Invalid/missing score: worst-case error on 1-5 scale
                    total_score_error += 4.0

    label_count = len(expected_labels) if expected_labels else 0

    return {
        "hallucination_accuracy": (
            correct_labels / label_count if label_count > 0 else 0.0
        ),
        "relevance_mae": (
            total_score_error / scored_count if scored_count > 0 else None
        ),
        "bias_mae": None,  # Requires separate bias test set
        "relevance_correlation": None,  # Requires scipy — deferred
    }
