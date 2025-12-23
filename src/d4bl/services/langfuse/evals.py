"""
Compatibility shim — Langfuse evals moved to dedicated modules.
Re-export the public API to avoid breaking imports.
"""

from d4bl.services.langfuse.runner import (
    evaluate_research_quality,
    evaluate_source_relevance,
    evaluate_bias_detection,
    run_comprehensive_evaluation,
)

__all__ = [
    "evaluate_research_quality",
    "evaluate_source_relevance",
    "evaluate_bias_detection",
    "run_comprehensive_evaluation",
]

