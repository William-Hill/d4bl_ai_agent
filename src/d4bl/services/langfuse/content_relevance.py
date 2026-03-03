"""Evaluate the relevance of extracted content from URLs to the query."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from d4bl.services.langfuse.llm_runner import call_llm_text
from d4bl.services.langfuse.prompts import content_relevance_prompt
from d4bl.services.langfuse.parsers import parse_first_json_block

logger = logging.getLogger(__name__)
eval_logger = logging.getLogger(f"{__name__}.evaluations")


def _keyword_relevance(query: str, text: str) -> float:
    """Fallback keyword-matching relevance score."""
    query_words = set(query.lower().split())
    text_lower = text.lower()
    matches = sum(1 for word in query_words if word in text_lower and len(word) > 3)
    return min(5.0, (matches / len(query_words)) * 5) if query_words else 3.0


def evaluate_content_relevance(
    query: str,
    extracted_contents: List[Dict[str, Any]],
    trace_id: Optional[str] = None,
    llm: Any = None,
    langfuse: Any = None,
) -> Dict[str, Any]:
    start_time = time.time()
    eval_logger.info("Starting content relevance evaluation for %s URLs", len(extracted_contents))

    if langfuse is None:
        from d4bl.services.langfuse.client import get_langfuse_eval_client
        langfuse = get_langfuse_eval_client()
    if not langfuse:
        logger.warning("Langfuse not available, skipping content relevance evaluation")
        return {"error": "Langfuse not configured", "status": "skipped"}

    try:
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        if not extracted_contents:
            return {"scores": {}, "average": 0.0, "status": "skipped", "reason": "no_contents"}

        if llm is None:
            from d4bl.services.langfuse.llm_runner import get_eval_llm
            llm = get_eval_llm()

        relevance_scores: Dict[str, Dict[str, Any]] = {}

        for idx, item in enumerate(extracted_contents):
            url = item.get("url", f"unknown_{idx}")
            content = item.get("extracted_content") or item.get("content", "")

            if not content or len(content.strip()) < 50:
                relevance_scores[url] = {"score": 0.0, "reason": "insufficient_content"}
                continue

            content_sample = content[:2000]

            try:
                prompt = content_relevance_prompt(query, url, content_sample)
                evaluation = call_llm_text(llm, prompt, max_retries=2, retry_delay=2.0)

                parsed = parse_first_json_block(str(evaluation))
                if parsed and "relevance_score" in parsed:
                    score = max(1.0, min(5.0, float(parsed["relevance_score"])))
                    relevance_scores[url] = {
                        "score": score,
                        "explanation": parsed.get("explanation", ""),
                    }
                else:
                    relevance_scores[url] = {
                        "score": _keyword_relevance(query, content_sample),
                        "explanation": "Fallback keyword matching (LLM parse failed)",
                    }
            except Exception as eval_error:
                logger.warning("Error evaluating content for %s: %s", url[:50], eval_error)
                relevance_scores[url] = {
                    "score": 3.0,
                    "reason": f"evaluation_error: {str(eval_error)[:100]}",
                }

        scores_only = [v.get("score", 0.0) for v in relevance_scores.values()]
        avg_relevance = sum(scores_only) / len(scores_only) if scores_only else 0.0

        eval_logger.info(
            "Content relevance — Average: %.2f, URLs evaluated: %s/%s",
            avg_relevance, len(scores_only), len(extracted_contents),
        )

        if trace_id and langfuse:
            try:
                langfuse.score_current_trace(
                    name="content_relevance",
                    value=avg_relevance,
                    data_type="NUMERIC",
                    comment=f"Average relevance of extracted content from {len(extracted_contents)} URLs",
                )
            except Exception as score_error:
                logger.error("Failed to log content relevance score: %s", score_error, exc_info=True)

        elapsed_time = time.time() - start_time
        return {
            "scores": relevance_scores,
            "average": avg_relevance,
            "status": "success",
            "elapsed_time": elapsed_time,
            "urls_evaluated": len(scores_only),
            "urls_total": len(extracted_contents),
        }

    except ValueError as ve:
        logger.error("Validation error in content relevance evaluation: %s", ve, exc_info=True)
        return {"error": str(ve), "status": "failed", "error_type": "validation"}
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error("Error in content relevance evaluation (took %.2fs): %s", elapsed_time, e, exc_info=True)
        return {"error": str(e), "status": "failed", "error_type": type(e).__name__, "elapsed_time": elapsed_time}
