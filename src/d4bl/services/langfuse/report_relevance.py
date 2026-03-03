"""Evaluate the relevance of the generated report to the query."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from d4bl.services.langfuse.llm_runner import call_llm_text
from d4bl.services.langfuse.prompts import report_relevance_prompt
from d4bl.services.langfuse.parsers import parse_first_json_block

logger = logging.getLogger(__name__)
eval_logger = logging.getLogger(f"{__name__}.evaluations")


def _keyword_relevance(query: str, text: str) -> float:
    """Fallback keyword-matching relevance score."""
    query_words = set(query.lower().split())
    text_lower = text.lower()
    matches = sum(1 for word in query_words if word in text_lower and len(word) > 3)
    return min(5.0, (matches / len(query_words)) * 5) if query_words else 3.0


def evaluate_report_relevance(
    query: str,
    report: str,
    trace_id: Optional[str] = None,
    llm: Any = None,
    langfuse: Any = None,
) -> Dict[str, Any]:
    start_time = time.time()
    eval_logger.info("Starting report relevance evaluation")

    if langfuse is None:
        from d4bl.services.langfuse.client import get_langfuse_eval_client
        langfuse = get_langfuse_eval_client()
    if not langfuse:
        logger.warning("Langfuse not available, skipping report relevance evaluation")
        return {"error": "Langfuse not configured", "status": "skipped"}

    try:
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        if not report or not report.strip():
            return {"relevance_score": 0.0, "status": "skipped", "reason": "no_report"}

        if llm is None:
            from d4bl.services.langfuse.llm_runner import get_eval_llm
            llm = get_eval_llm()

        report_sample = report[:3000]
        prompt = report_relevance_prompt(query, report_sample)
        evaluation = call_llm_text(llm, prompt, max_retries=2, retry_delay=2.0)

        parsed = parse_first_json_block(str(evaluation))
        if parsed and "relevance_score" in parsed:
            relevance_score = max(1.0, min(5.0, float(parsed["relevance_score"])))
            explanation = parsed.get("explanation", "")
            key_points_addressed = parsed.get("key_points_addressed", [])
            missing_aspects = parsed.get("missing_aspects", [])
        else:
            relevance_score = _keyword_relevance(query, report_sample)
            explanation = "Fallback keyword matching (LLM parse failed)"
            key_points_addressed = []
            missing_aspects = []

        eval_logger.info("Report relevance — Score: %.2f", relevance_score)

        if trace_id and langfuse:
            try:
                langfuse.score_current_trace(
                    name="report_relevance",
                    value=relevance_score,
                    data_type="NUMERIC",
                    comment=explanation[:500] if explanation else "Report relevance evaluation",
                )
            except Exception as score_error:
                logger.error("Failed to log report relevance score: %s", score_error, exc_info=True)

        elapsed_time = time.time() - start_time
        return {
            "relevance_score": relevance_score,
            "explanation": explanation,
            "key_points_addressed": key_points_addressed,
            "missing_aspects": missing_aspects,
            "status": "success",
            "elapsed_time": elapsed_time,
        }

    except ValueError as ve:
        logger.error("Validation error in report relevance evaluation: %s", ve, exc_info=True)
        return {"error": str(ve), "status": "failed", "error_type": "validation"}
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error("Error in report relevance evaluation (took %.2fs): %s", elapsed_time, e, exc_info=True)
        return {"error": str(e), "status": "failed", "error_type": type(e).__name__, "elapsed_time": elapsed_time}
