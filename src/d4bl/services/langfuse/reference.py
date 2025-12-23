from __future__ import annotations

import time
import logging
from typing import Any, Dict, Optional

from d4bl.services.langfuse.client import get_langfuse_eval_client
from d4bl.services.langfuse.llm_runner import get_eval_llm, call_llm_text
from d4bl.services.langfuse.prompts import reference_prompt
from d4bl.services.langfuse.parsers import parse_label_score

logger = logging.getLogger(__name__)
eval_logger = logging.getLogger(f"{__name__}.evaluations")
eval_logger.setLevel(logging.INFO)


MAPPING = {
    "WELL_REFERENCED": 5.0,
    "WEAKLY_REFERENCED": 3.0,
    "UNGROUNDED": 1.0,
}


def evaluate_reference(
    query: str,
    answer: str,
    context: str,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    start_time = time.time()
    eval_logger.info("Starting reference grounding evaluation")

    langfuse = get_langfuse_eval_client()
    if not langfuse:
        logger.warning("Langfuse not available, skipping reference evaluation")
        return {"error": "Langfuse not configured", "status": "skipped"}

    try:
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        if not answer or not answer.strip():
            raise ValueError("Answer cannot be empty")
        if not context or not context.strip():
            raise ValueError("Context cannot be empty")

        prompt = reference_prompt(query, answer, context)
        try:
            llm = get_eval_llm()
        except Exception as llm_error:
            logger.error("Failed to initialize LLM for reference eval: %s", llm_error, exc_info=True)
            raise ValueError(f"LLM initialization failed: {str(llm_error)}") from llm_error

        llm_start = time.time()
        response = call_llm_text(llm, prompt, max_retries=2, retry_delay=2.0)
        eval_logger.debug("LLM invocation successful in %.2fs", time.time() - llm_start)

        score, explanation = parse_label_score(str(response), MAPPING, default_score=3.0)
        score = max(1.0, min(5.0, float(score)))

        eval_logger.info("Reference grounding evaluation - Score: %.2f", score)

        if trace_id and langfuse:
            try:
                langfuse.score_current_trace(
                    name="reference_grounding",
                    value=score,
                    data_type="NUMERIC",
                    comment=str(explanation)[:500],
                )
                langfuse.flush()
                eval_logger.debug("Reference grounding score logged to Langfuse")
            except Exception as score_error:  # pragma: no cover - best effort
                logger.error("Failed to log reference score to Langfuse: %s", score_error, exc_info=True)

        elapsed_time = time.time() - start_time
        eval_logger.info("Reference grounding evaluation completed in %.2fs", elapsed_time)

        return {
            "reference_score": score,
            "explanation": str(explanation)[:500],
            "status": "success",
            "elapsed_time": elapsed_time,
        }

    except ValueError as ve:
        logger.error("Validation error in reference evaluation: %s", ve, exc_info=True)
        return {"error": str(ve), "status": "failed", "error_type": "validation"}
    except Exception as e:  # pragma: no cover - defensive
        elapsed_time = time.time() - start_time
        logger.error("Error in reference evaluation (took %.2fs): %s", elapsed_time, e, exc_info=True)
        return {
            "error": str(e),
            "status": "failed",
            "error_type": type(e).__name__,
            "elapsed_time": elapsed_time,
        }
