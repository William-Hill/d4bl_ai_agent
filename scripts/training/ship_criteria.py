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
    metrics_checked = 0

    for metric, spec in criteria.items():
        actual = metrics.get(metric)
        blocking = spec["blocking"]

        # In partial mode, skip metrics that aren't available
        if partial and actual is None:
            continue

        metrics_checked += 1
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
        metrics_checked=metrics_checked,
    )
