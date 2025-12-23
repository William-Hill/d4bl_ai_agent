from __future__ import annotations

import time
import logging
from typing import Any, Dict, Optional

from d4bl.services.langfuse.client import get_langfuse_eval_client
from d4bl.services.langfuse.llm_runner import get_eval_llm, call_llm_text
from d4bl.services.langfuse.prompts import bias_prompt
from d4bl.services.langfuse.parsers import parse_bias_score

logger = logging.getLogger(__name__)
eval_logger = logging.getLogger(f"{__name__}.evaluations")
eval_logger.setLevel(logging.INFO)


def evaluate_bias_detection(
    research_output: str,
    query: str,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    start_time = time.time()
    eval_logger.info("Starting bias detection evaluation")

    langfuse = get_langfuse_eval_client()
    if not langfuse:
        logger.warning("Langfuse not available, skipping bias detection evaluation")
        return {"error": "Langfuse not configured", "status": "skipped"}

    try:
        if not research_output or not research_output.strip():
            raise ValueError("Research output cannot be empty")
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        prompt = bias_prompt(query, research_output)

        try:
            llm = get_eval_llm()
        except Exception as llm_error:
            logger.error("Failed to initialize LLM for bias detection: %s", llm_error, exc_info=True)
            raise ValueError(f"LLM initialization failed: {str(llm_error)}") from llm_error

        llm_start = time.time()
        bias_feedback = call_llm_text(llm, prompt, max_retries=2, retry_delay=2.0)
        eval_logger.debug("LLM invocation successful in %.2fs", time.time() - llm_start)

        bias_score, feedback = parse_bias_score(str(bias_feedback))
        bias_score = max(1.0, min(5.0, float(bias_score)))

        eval_logger.info("Bias detection evaluation - Score: %.2f", bias_score)

        if trace_id and langfuse:
            try:
                langfuse.score_current_trace(
                    name="bias_detection",
                    value=bias_score,
                    data_type="NUMERIC",
                    comment=feedback[:500],
                )
                langfuse.flush()
                eval_logger.debug("Bias detection score logged to Langfuse")
            except Exception as score_error:  # pragma: no cover - best-effort
                logger.error("Failed to log bias detection score to Langfuse: %s", score_error, exc_info=True)

        elapsed_time = time.time() - start_time
        eval_logger.info("Bias detection evaluation completed in %.2fs", elapsed_time)

        return {
            "bias_score": bias_score,
            "feedback": feedback[:500],
            "status": "success",
            "elapsed_time": elapsed_time,
        }

    except ValueError as ve:
        logger.error("Validation error in bias detection: %s", ve, exc_info=True)
        return {"error": str(ve), "status": "failed", "error_type": "validation"}
    except Exception as e:  # pragma: no cover - defensive
        elapsed_time = time.time() - start_time
        logger.error("Error in bias detection (took %.2fs): %s", elapsed_time, e, exc_info=True)
        return {
            "error": str(e),
            "status": "failed",
            "error_type": type(e).__name__,
            "elapsed_time": elapsed_time,
        }
