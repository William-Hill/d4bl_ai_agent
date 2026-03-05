from __future__ import annotations

import logging
import time
from typing import Any

from d4bl.services.langfuse._base import EvalStatus
from d4bl.services.langfuse.parsers import keyword_relevance

logger = logging.getLogger(__name__)
eval_logger = logging.getLogger(f"{__name__}.evaluations")


def evaluate_source_relevance(
    query: str,
    sources: list[str],
    trace_id: str | None = None,
    langfuse: Any = None,
) -> dict[str, Any]:
    start_time = time.time()
    eval_logger.info("Starting source relevance evaluation for %s sources", len(sources))

    if langfuse is None:
        from d4bl.services.langfuse.client import get_langfuse_eval_client
        langfuse = get_langfuse_eval_client()
    if not langfuse:
        logger.warning("Langfuse not available, skipping source relevance evaluation")
        return {"error": "Langfuse not configured", "status": EvalStatus.SKIPPED}

    try:
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        if not sources:
            return {"scores": {}, "average": 0.0, "status": EvalStatus.SKIPPED, "reason": "no_sources"}

        relevance_scores: dict[str, float] = {}
        for idx, source in enumerate(sources):
            try:
                relevance_scores[source] = keyword_relevance(query, source)
            except Exception as source_error:
                logger.warning("Error evaluating source %s (%s...): %s", idx + 1, source[:50], source_error)
                relevance_scores[source] = 3.0

        avg_relevance = (
            sum(relevance_scores.values()) / len(relevance_scores) if relevance_scores else 0.0
        )
        eval_logger.info(
            "Source relevance — Average: %.2f, Sources evaluated: %s",
            avg_relevance, len(relevance_scores),
        )

        if trace_id and langfuse:
            try:
                langfuse.score_current_trace(
                    name="source_relevance",
                    value=avg_relevance,
                    data_type="NUMERIC",
                    comment=f"Average relevance of {len(sources)} sources",
                )
            except Exception as score_error:
                logger.error("Failed to log source relevance score: %s", score_error, exc_info=True)

        elapsed_time = time.time() - start_time
        return {
            "scores": relevance_scores,
            "average": avg_relevance,
            "status": EvalStatus.SUCCESS,
            "elapsed_time": elapsed_time,
        }

    except ValueError as ve:
        logger.error("Validation error in source relevance: %s", ve, exc_info=True)
        return {"error": str(ve), "status": EvalStatus.FAILED, "error_type": "validation"}
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error("Error in source relevance (took %.2fs): %s", elapsed_time, e, exc_info=True)
        return {
            "error": str(e),
            "status": EvalStatus.FAILED,
            "error_type": type(e).__name__,
            "elapsed_time": elapsed_time,
        }
