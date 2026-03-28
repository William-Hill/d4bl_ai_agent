"""Post-eval suggestion engine: rules-based + optional LLM analysis."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from scripts.training.ship_criteria import SHIP_CRITERIA

SUGGESTION_TEXT: dict[str, dict[str, str]] = {
    "query_parser": {
        "json_valid_rate": (
            "Add adversarial examples with malformed input to improve JSON compliance"
        ),
        "entity_f1": (
            "Add training pairs with more diverse entity types "
            "(organizations, policies, geographies)"
        ),
        "data_source_accuracy": (
            "Add examples that clarify when to use vector vs structured search"
        ),
        "community_framing_f1": (
            "Add community-voiced query examples with advocacy framing"
        ),
        "p95_latency_ms": (
            "Consider increasing quantization level or reducing context window"
        ),
        "adversarial_pass_rate": (
            "Add more adversarial prompts with harmful framings that should be reframed"
        ),
    },
    "explainer": {
        "json_valid_rate": "Add examples with complex nested JSON output structure",
        "factual_accuracy": (
            "Verify training data accuracy — check for stale statistics in distillation corpus"
        ),
        "d4bl_composite": (
            "Increase proportion of D4BL methodology-aligned training examples"
        ),
        "register_consistency": (
            "Add single-register examples with clear style separation "
            "between community/policy/research"
        ),
        "p95_latency_ms": (
            "Consider increasing quantization level or reducing context window"
        ),
    },
    "evaluator": {
        "hallucination_accuracy": (
            "Add more hallucination detection examples with subtle factual errors"
        ),
        "relevance_mae": (
            "Add relevance scoring examples with borderline cases (partially relevant)"
        ),
        "bias_mae": (
            "Add bias detection examples covering structural bias, not just explicit bias"
        ),
        "relevance_correlation": (
            "Add more diverse relevance scoring examples across different query types"
        ),
    },
}


@dataclass
class Suggestion:
    metric: str
    severity: str
    current: float
    target: float
    suggestion: str
    category: str = "training_data"


@dataclass
class SuggestionsResult:
    rules: list[Suggestion] = field(default_factory=list)
    llm_analysis: str | None = None
    generated_at: str = ""

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "rules": [asdict(s) for s in self.rules],
            "llm_analysis": self.llm_analysis,
            "generated_at": self.generated_at,
        }


def generate_suggestions(task: str, metrics: dict[str, float | None]) -> SuggestionsResult:
    """Generate rules-based suggestions from eval metrics and ship criteria.

    Args:
        task: One of "query_parser", "explainer", "evaluator".
        metrics: Dict of metric_name -> value.

    Returns:
        SuggestionsResult with rules-based suggestions for metrics that fail thresholds.
    """
    criteria = SHIP_CRITERIA.get(task, {})
    task_suggestions = SUGGESTION_TEXT.get(task, {})
    suggestions: list[Suggestion] = []

    for metric_name, bounds in criteria.items():
        actual = metrics.get(metric_name)
        if actual is None:
            continue

        text = task_suggestions.get(metric_name)
        if not text:
            continue

        blocking = bounds.get("blocking", False)
        severity = "blocking" if blocking else "non-blocking"
        failed = False
        target = 0.0

        if "min" in bounds:
            target = bounds["min"]
            if actual < target:
                failed = True
        if "max" in bounds:
            target = bounds["max"]
            if actual > target:
                failed = True

        if failed:
            suggestions.append(Suggestion(
                metric=metric_name,
                severity=severity,
                current=actual,
                target=target,
                suggestion=text,
            ))

    return SuggestionsResult(rules=suggestions)
