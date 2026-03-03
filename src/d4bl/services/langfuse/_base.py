"""Base evaluation helper — captures the common evaluator boilerplate."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, Optional

from d4bl.services.langfuse.llm_runner import call_llm_text

logger = logging.getLogger(__name__)
eval_logger = logging.getLogger(f"{__name__}.evaluations")


def run_llm_evaluation(
    eval_name: str,
    prompt: str,
    parse_fn: Callable[[str], tuple[float, str]],
    score_key: str,
    trace_id: Optional[str] = None,
    llm: Any = None,
    langfuse: Any = None,
) -> Dict[str, Any]:
    """Run a single LLM-based evaluation with standard boilerplate.

    Args:
        eval_name: Human-readable name for logging and Langfuse score name.
        prompt: The fully-built prompt string to send to the LLM.
        parse_fn: Callable that takes the raw LLM response text and returns
                  ``(score, feedback)`` where score is a float in [1, 5].
        score_key: Key used for the score in the returned dict
                   (e.g. ``"bias_score"``, ``"hallucination_score"``).
        trace_id: Optional Langfuse trace ID for linking.
        llm: Pre-initialised LLM instance. If *None*, one is created via
             ``get_eval_llm()``.
        langfuse: Pre-initialised Langfuse client. If *None*, one is fetched
                  via ``get_langfuse_eval_client()``.

    Returns:
        Dict with at least ``{score_key, "feedback"/"explanation", "status",
        "elapsed_time"}``.  On failure the dict contains ``"error"`` and
        ``"error_type"`` instead.
    """
    start_time = time.time()
    eval_logger.info("Starting %s evaluation", eval_name)

    # Lazily resolve dependencies when not injected
    if langfuse is None:
        from d4bl.services.langfuse.client import get_langfuse_eval_client
        langfuse = get_langfuse_eval_client()

    if not langfuse:
        logger.warning("Langfuse not available, skipping %s evaluation", eval_name)
        return {"error": "Langfuse not configured", "status": "skipped"}

    try:
        if llm is None:
            from d4bl.services.langfuse.llm_runner import get_eval_llm
            llm = get_eval_llm()

        llm_start = time.time()
        raw_response = call_llm_text(llm, prompt, max_retries=2, retry_delay=2.0)
        eval_logger.debug(
            "%s LLM call completed in %.2fs", eval_name, time.time() - llm_start
        )

        score, feedback = parse_fn(str(raw_response))
        score = max(1.0, min(5.0, float(score)))

        eval_logger.info("%s evaluation — Score: %.2f", eval_name, score)

        if trace_id and langfuse:
            try:
                langfuse.score_current_trace(
                    name=eval_name,
                    value=score,
                    data_type="NUMERIC",
                    comment=str(feedback)[:500],
                )
                eval_logger.debug("%s score logged to Langfuse", eval_name)
            except Exception as score_error:
                logger.error(
                    "Failed to log %s score to Langfuse: %s",
                    eval_name, score_error, exc_info=True,
                )

        elapsed_time = time.time() - start_time
        eval_logger.info("%s evaluation completed in %.2fs", eval_name, elapsed_time)

        return {
            score_key: score,
            "feedback": str(feedback)[:500],
            "status": "success",
            "elapsed_time": elapsed_time,
        }

    except ValueError as ve:
        logger.error("Validation error in %s: %s", eval_name, ve, exc_info=True)
        return {"error": str(ve), "status": "failed", "error_type": "validation"}
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(
            "Error in %s (took %.2fs): %s", eval_name, elapsed_time, e, exc_info=True
        )
        return {
            "error": str(e),
            "status": "failed",
            "error_type": type(e).__name__,
            "elapsed_time": elapsed_time,
        }
