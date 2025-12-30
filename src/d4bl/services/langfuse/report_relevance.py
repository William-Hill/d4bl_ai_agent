"""
Evaluate the relevance of the generated report to the query.
"""
from __future__ import annotations

import logging
import time
import json
from typing import Any, Dict, Optional

from d4bl.services.langfuse.client import get_langfuse_eval_client
from d4bl.services.langfuse.llm_runner import get_eval_llm, call_llm_text
from d4bl.services.langfuse.prompts import report_relevance_prompt

logger = logging.getLogger(__name__)
eval_logger = logging.getLogger(f"{__name__}.evaluations")
eval_logger.setLevel(logging.INFO)


def evaluate_report_relevance(
    query: str,
    report: str,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluate how relevant the generated report is to the query.
    
    Args:
        query: The original research query
        report: The generated report content
        trace_id: Optional trace ID for Langfuse logging
    
    Returns:
        Dict with relevance score and explanation
    """
    start_time = time.time()
    eval_logger.info("Starting report relevance evaluation")

    langfuse = get_langfuse_eval_client()
    if not langfuse:
        logger.warning("Langfuse not available, skipping report relevance evaluation")
        return {"error": "Langfuse not configured", "status": "skipped"}

    try:
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        if not report or not report.strip():
            logger.warning("No report provided for relevance evaluation")
            return {
                "relevance_score": 0.0,
                "status": "skipped",
                "reason": "no_report",
            }

        # Limit report length for evaluation (first 3000 chars)
        report_sample = report[:3000] if len(report) > 3000 else report
        
        prompt = report_relevance_prompt(query, report_sample)
        
        llm = get_eval_llm()
        llm_start = time.time()
        evaluation = call_llm_text(llm, prompt, max_retries=2, retry_delay=2.0)
        eval_logger.debug("LLM call successful in %.2fs", time.time() - llm_start)

        # Parse JSON response
        try:
            if isinstance(evaluation, str):
                eval_data = json.loads(evaluation)
            else:
                eval_data = evaluation
            
            relevance_score = float(eval_data.get("relevance_score", 3.0))
            explanation = eval_data.get("explanation", "")
            key_points_addressed = eval_data.get("key_points_addressed", [])
            missing_aspects = eval_data.get("missing_aspects", [])
            
            # Ensure score is in valid range
            relevance_score = max(1.0, min(5.0, relevance_score))
            
        except (json.JSONDecodeError, KeyError, ValueError) as parse_error:
            logger.warning("Failed to parse evaluation response: %s", parse_error)
            # Fallback: use keyword matching
            query_lower = query.lower()
            report_lower = report_sample.lower()
            query_words = set(query_lower.split())
            matches = sum(1 for word in query_words if word in report_lower and len(word) > 3)
            relevance_score = min(5.0, (matches / len(query_words)) * 5) if query_words else 3.0
            explanation = "Fallback keyword matching (LLM parse failed)"
            key_points_addressed = []
            missing_aspects = []

        eval_logger.info(
            "Report relevance evaluation - Score: %.2f",
            relevance_score,
        )

        # Log to Langfuse
        if trace_id and langfuse:
            try:
                langfuse.score_current_trace(
                    name="report_relevance",
                    value=relevance_score,
                    data_type="NUMERIC",
                    comment=explanation[:500] if explanation else "Report relevance evaluation",
                )
                langfuse.flush()
                eval_logger.debug("Report relevance score logged to Langfuse")
            except Exception as score_error:
                logger.error("Failed to log report relevance score to Langfuse: %s", score_error, exc_info=True)

        elapsed_time = time.time() - start_time
        eval_logger.info("Report relevance evaluation completed in %.2fs", elapsed_time)

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
        return {
            "error": str(e),
            "status": "failed",
            "error_type": type(e).__name__,
            "elapsed_time": elapsed_time,
        }

