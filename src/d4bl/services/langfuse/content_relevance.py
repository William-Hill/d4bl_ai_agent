"""
Evaluate the relevance of extracted content from URLs to the query.
"""
from __future__ import annotations

import logging
import time
import json
from typing import Any, Dict, List, Optional

from d4bl.services.langfuse.client import get_langfuse_eval_client
from d4bl.services.langfuse.llm_runner import get_eval_llm, call_llm_text
from d4bl.services.langfuse.prompts import content_relevance_prompt

logger = logging.getLogger(__name__)
eval_logger = logging.getLogger(f"{__name__}.evaluations")
eval_logger.setLevel(logging.INFO)


def evaluate_content_relevance(
    query: str,
    extracted_contents: List[Dict[str, Any]],  # List of dicts with 'url' and 'content' keys
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluate how relevant the extracted content from URLs is to the query.
    
    Args:
        query: The original research query
        extracted_contents: List of dicts with 'url' and 'content' (or 'extracted_content') keys
        trace_id: Optional trace ID for Langfuse logging
    
    Returns:
        Dict with relevance scores per URL and overall statistics
    """
    start_time = time.time()
    eval_logger.info("Starting content relevance evaluation for %s URLs", len(extracted_contents))

    langfuse = get_langfuse_eval_client()
    if not langfuse:
        logger.warning("Langfuse not available, skipping content relevance evaluation")
        return {"error": "Langfuse not configured", "status": "skipped"}

    try:
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        if not extracted_contents:
            logger.warning("No extracted contents provided for relevance evaluation")
            return {
                "scores": {},
                "average": 0.0,
                "status": "skipped",
                "reason": "no_contents",
            }

        relevance_scores = {}
        llm = get_eval_llm()

        # Evaluate each extracted content
        for idx, item in enumerate(extracted_contents):
            url = item.get("url", f"unknown_{idx}")
            content = item.get("extracted_content") or item.get("content", "")
            
            if not content or len(content.strip()) < 50:
                logger.warning("Skipping evaluation for %s: insufficient content", url)
                relevance_scores[url] = {
                    "score": 0.0,
                    "reason": "insufficient_content",
                }
                continue

            try:
                # Limit content length for evaluation (first 2000 chars)
                content_sample = content[:2000] if len(content) > 2000 else content
                
                prompt = content_relevance_prompt(query, url, content_sample)
                
                eval_logger.debug("Evaluating content relevance for URL %s/%s: %s", idx + 1, len(extracted_contents), url[:50])
                
                llm_start = time.time()
                evaluation = call_llm_text(llm, prompt, max_retries=2, retry_delay=2.0)
                eval_logger.debug("LLM call successful in %.2fs", time.time() - llm_start)

                # Parse JSON response
                try:
                    if isinstance(evaluation, str):
                        # Try to extract JSON from response
                        eval_data = json.loads(evaluation)
                    else:
                        eval_data = evaluation
                    
                    score = float(eval_data.get("relevance_score", 3.0))
                    explanation = eval_data.get("explanation", "")
                    
                    # Ensure score is in valid range
                    score = max(1.0, min(5.0, score))
                    
                    relevance_scores[url] = {
                        "score": score,
                        "explanation": explanation,
                    }
                    
                    eval_logger.debug(
                        "URL %s/%s: relevance=%.2f - %s",
                        idx + 1,
                        len(extracted_contents),
                        score,
                        explanation[:100] if explanation else "No explanation",
                    )
                except (json.JSONDecodeError, KeyError, ValueError) as parse_error:
                    logger.warning("Failed to parse evaluation response for %s: %s", url[:50], parse_error)
                    # Fallback: use keyword matching
                    query_lower = query.lower()
                    content_lower = content_sample.lower()
                    query_words = set(query_lower.split())
                    matches = sum(1 for word in query_words if word in content_lower and len(word) > 3)
                    fallback_score = min(5.0, (matches / len(query_words)) * 5) if query_words else 3.0
                    relevance_scores[url] = {
                        "score": fallback_score,
                        "explanation": "Fallback keyword matching (LLM parse failed)",
                    }
                    
            except Exception as eval_error:
                logger.warning("Error evaluating content for %s: %s", url[:50], eval_error)
                relevance_scores[url] = {
                    "score": 3.0,
                    "reason": f"evaluation_error: {str(eval_error)[:100]}",
                }

        # Calculate average relevance
        scores_only = [v.get("score", 0.0) for v in relevance_scores.values() if isinstance(v, dict)]
        avg_relevance = sum(scores_only) / len(scores_only) if scores_only else 0.0
        
        eval_logger.info(
            "Content relevance evaluation - Average: %.2f, URLs evaluated: %s/%s",
            avg_relevance,
            len(scores_only),
            len(extracted_contents),
        )

        # Log to Langfuse
        if trace_id and langfuse:
            try:
                langfuse.score_current_trace(
                    name="content_relevance",
                    value=avg_relevance,
                    data_type="NUMERIC",
                    comment=f"Average relevance of extracted content from {len(extracted_contents)} URLs",
                )
                langfuse.flush()
                eval_logger.debug("Content relevance score logged to Langfuse")
            except Exception as score_error:
                logger.error("Failed to log content relevance score to Langfuse: %s", score_error, exc_info=True)

        elapsed_time = time.time() - start_time
        eval_logger.info("Content relevance evaluation completed in %.2fs", elapsed_time)

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
        return {
            "error": str(e),
            "status": "failed",
            "error_type": type(e).__name__,
            "elapsed_time": elapsed_time,
        }

