from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from d4bl.services.langfuse.client import get_langfuse_eval_client

logger = logging.getLogger(__name__)
eval_logger = logging.getLogger(f"{__name__}.evaluations")
eval_logger.setLevel(logging.INFO)


def evaluate_source_relevance(
    query: str,
    sources: List[str],
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    start_time = time.time()
    eval_logger.info("Starting source relevance evaluation for %s sources", len(sources))

    langfuse = get_langfuse_eval_client()
    if not langfuse:
        logger.warning("Langfuse not available, skipping source relevance evaluation")
        return {"error": "Langfuse not configured", "status": "skipped"}

    try:
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        if not sources:
            logger.warning("No sources provided for relevance evaluation")
            return {
                "scores": {},
                "average": 0.0,
                "status": "skipped",
                "reason": "no_sources",
            }

        relevance_scores = {}
        query_keywords = set(query.lower().split())
        for idx, source in enumerate(sources):
            try:
                url_lower = source.lower()
                matches = sum(1 for keyword in query_keywords if keyword in url_lower)
                relevance = min(5.0, (matches / len(query_keywords)) * 5) if query_keywords else 3.0
                relevance_scores[source] = relevance
                eval_logger.debug(
                    "Source %s/%s: relevance=%.2f (%s/%s matches)",
                    idx + 1,
                    len(sources),
                    relevance,
                    matches,
                    len(query_keywords),
                )
            except Exception as source_error:  # pragma: no cover - defensive
                logger.warning("Error evaluating source %s (%s...): %s", idx + 1, source[:50], source_error)
                relevance_scores[source] = 3.0

        avg_relevance = (
            sum(relevance_scores.values()) / len(relevance_scores) if relevance_scores else 0.0
        )
        eval_logger.info(
            "Source relevance evaluation - Average: %.2f, Sources evaluated: %s",
            avg_relevance,
            len(relevance_scores),
        )

        if trace_id and langfuse:
            try:
                langfuse.score_current_trace(
                    name="source_relevance",
                    value=avg_relevance,
                    data_type="NUMERIC",
                    comment=f"Average relevance of {len(sources)} sources",
                )
                langfuse.flush()
                eval_logger.debug("Source relevance score logged to Langfuse")
            except Exception as score_error:  # pragma: no cover - best-effort
                logger.error("Failed to log source relevance score to Langfuse: %s", score_error, exc_info=True)

        elapsed_time = time.time() - start_time
        eval_logger.info("Source relevance evaluation completed in %.2fs", elapsed_time)

        return {
            "scores": relevance_scores,
            "average": avg_relevance,
            "status": "success",
            "elapsed_time": elapsed_time,
        }

    except ValueError as ve:
        logger.error("Validation error in source relevance evaluation: %s", ve, exc_info=True)
        return {"error": str(ve), "status": "failed", "error_type": "validation"}
    except Exception as e:  # pragma: no cover - defensive
        elapsed_time = time.time() - start_time
        logger.error("Error in source relevance evaluation (took %.2fs): %s", elapsed_time, e, exc_info=True)
        return {
            "error": str(e),
            "status": "failed",
            "error_type": type(e).__name__,
            "elapsed_time": elapsed_time,
        }
