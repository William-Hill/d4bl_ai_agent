from __future__ import annotations

import time
import logging
from typing import Any, Dict, List, Optional

from d4bl.services.langfuse.client import get_langfuse_eval_client
from d4bl.services.langfuse.llm_runner import get_eval_llm, call_llm_text
from d4bl.services.langfuse.prompts import quality_prompt
from d4bl.services.langfuse.parsers import parse_first_json_block, default_quality_scores

logger = logging.getLogger(__name__)
eval_logger = logging.getLogger(f"{__name__}.evaluations")
eval_logger.setLevel(logging.INFO)


def evaluate_research_quality(
    query: str,
    research_output: str,
    sources: List[str],
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    start_time = time.time()
    eval_logger.info("Starting research quality evaluation")
    eval_logger.debug(
        "Query length: %s, Output length: %s, Sources: %s",
        len(query),
        len(research_output),
        len(sources),
    )
    eval_logger.debug(
        "Trace ID: %s", trace_id[:16] + "..." if trace_id and len(trace_id) > 16 else trace_id
    )

    langfuse = get_langfuse_eval_client()
    if not langfuse:
        logger.warning("Langfuse not available, skipping research quality evaluation")
        return {"error": "Langfuse not configured", "status": "skipped"}

    try:
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        if not research_output or not research_output.strip():
            raise ValueError("Research output cannot be empty")

        prompt = quality_prompt(query, research_output, sources)

        try:
            llm = get_eval_llm()
        except Exception as llm_error:
            logger.error("Failed to initialize LLM for evaluation: %s", llm_error, exc_info=True)
            raise ValueError(f"LLM initialization failed: {str(llm_error)}") from llm_error

        llm_start = time.time()
        evaluation = call_llm_text(llm, prompt, max_retries=2, retry_delay=2.0)
        eval_logger.debug("LLM call successful in %.2fs", time.time() - llm_start)

        scores = parse_first_json_block(str(evaluation))
        scores = default_quality_scores(scores, str(evaluation))

        eval_logger.info(
            "Evaluation scores - Overall: %.2f, Relevance: %.2f, Completeness: %.2f, Accuracy: %.2f, Bias: %.2f, Clarity: %.2f",
            scores["overall"],
            scores["relevance"],
            scores["completeness"],
            scores["accuracy"],
            scores["bias"],
            scores["clarity"],
        )

        if trace_id and langfuse:
            try:
                langfuse.score_current_trace(
                    name="research_quality",
                    value=scores["overall"],
                    data_type="NUMERIC",
                    comment=scores.get("feedback", "")[:500],
                )
                langfuse.flush()
                eval_logger.debug("Score logged to Langfuse for trace_id: %s", trace_id[:16])
            except Exception as score_error:  # pragma: no cover - best-effort
                logger.error("Failed to log score to Langfuse: %s", score_error, exc_info=True)

        elapsed_time = time.time() - start_time
        eval_logger.info("Research quality evaluation completed in %.2fs", elapsed_time)

        return {
            "scores": scores,
            "trace_id": trace_id,
            "status": "success",
            "elapsed_time": elapsed_time,
        }

    except ValueError as ve:
        logger.error("Validation error in research quality evaluation: %s", ve, exc_info=True)
        return {"error": str(ve), "status": "failed", "error_type": "validation"}
    except Exception as e:  # pragma: no cover - defensive
        elapsed_time = time.time() - start_time
        logger.error("Error in research quality evaluation (took %.2fs): %s", elapsed_time, e, exc_info=True)
        return {
            "error": str(e),
            "status": "failed",
            "error_type": type(e).__name__,
            "elapsed_time": elapsed_time,
        }
