"""Evaluate the relevance of the generated report to the query."""

from __future__ import annotations

import logging
import time
from typing import Any

from d4bl.services.langfuse._base import EvalStatus
from d4bl.services.langfuse.llm_runner import call_llm_text
from d4bl.services.langfuse.parsers import keyword_relevance, parse_first_json_block
from d4bl.services.langfuse.prompts import report_relevance_prompt

logger = logging.getLogger(__name__)
eval_logger = logging.getLogger(f"{__name__}.evaluations")


def evaluate_report_relevance(
    query: str,
    report: str,
    trace_id: str | None = None,
    llm: Any = None,
    langfuse: Any = None,
) -> dict[str, Any]:
    start_time = time.time()
    eval_logger.info("Starting report relevance evaluation")

    if langfuse is None:
        from d4bl.services.langfuse.client import get_langfuse_eval_client

        langfuse = get_langfuse_eval_client()
    if not langfuse:
        logger.warning("Langfuse not available, skipping report relevance evaluation")
        return {"error": "Langfuse not configured", "status": EvalStatus.SKIPPED}

    try:
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        if not report or not report.strip():
            return {"relevance_score": 0.0, "status": EvalStatus.SKIPPED, "reason": "no_report"}

        if llm is None:
            from d4bl.services.langfuse.llm_runner import get_eval_llm

            llm = get_eval_llm()

        report_sample = report[:3000]
        prompt = report_relevance_prompt(query, report_sample)
        evaluation = call_llm_text(llm, prompt, max_retries=2, retry_delay=2.0)

        parsed = parse_first_json_block(str(evaluation))
        try:
            raw_score = (
                float(parsed["relevance_score"]) if parsed and "relevance_score" in parsed else None
            )
        except (ValueError, TypeError):
            raw_score = None

        if raw_score is not None:
            relevance_score = max(1.0, min(5.0, raw_score))
            explanation = parsed.get("explanation", "")
            key_points_addressed = parsed.get("key_points_addressed", [])
            missing_aspects = parsed.get("missing_aspects", [])
        else:
            relevance_score = keyword_relevance(query, report_sample)
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
            "status": EvalStatus.SUCCESS,
            "elapsed_time": elapsed_time,
        }

    except ValueError as ve:
        logger.error(
            "Validation error in report relevance evaluation: %s",
            ve,
            exc_info=True,
        )
        return {"error": str(ve), "status": EvalStatus.FAILED, "error_type": "validation"}
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(
            "Error in report relevance evaluation (took %.2fs): %s",
            elapsed_time,
            e,
            exc_info=True,
        )
        return {
            "error": str(e),
            "status": EvalStatus.FAILED,
            "error_type": type(e).__name__,
            "elapsed_time": elapsed_time,
        }