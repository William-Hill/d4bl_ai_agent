from __future__ import annotations

import time
import logging
from typing import Any, Dict, List, Optional

from d4bl.services.langfuse.quality import evaluate_research_quality
from d4bl.services.langfuse.source_relevance import evaluate_source_relevance
from d4bl.services.langfuse.bias import evaluate_bias_detection
from d4bl.services.langfuse.hallucination import evaluate_hallucination
from d4bl.services.langfuse.reference import evaluate_reference

logger = logging.getLogger(__name__)
eval_logger = logging.getLogger(f"{__name__}.evaluations")
eval_logger.setLevel(logging.INFO)


def run_comprehensive_evaluation(
    query: str,
    research_output: str,
    sources: List[str],
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    start_time = time.time()
    eval_logger.info("=" * 60)
    eval_logger.info("Starting comprehensive evaluation")
    eval_logger.info("Query: %s...", query[:100])
    eval_logger.info("Output length: %s chars", len(research_output))
    eval_logger.info("Sources: %s", len(sources))
    eval_logger.info(
        "Trace ID: %s", trace_id[:16] + "..." if trace_id and len(trace_id) > 16 else trace_id
    )
    eval_logger.info("=" * 60)

    results: Dict[str, Any] = {
        "query": query,
        "trace_id": trace_id,
        "evaluations": {},
        "start_time": start_time,
    }

    # Run evaluations
    eval_logger.info("Running research quality evaluation...")
    try:
        results["evaluations"]["quality"] = evaluate_research_quality(
            query=query,
            research_output=research_output,
            sources=sources,
            trace_id=trace_id,
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.error("Failed to run research quality evaluation: %s", e, exc_info=True)
        results["evaluations"]["quality"] = {"error": str(e), "status": "failed"}

    eval_logger.info("Running source relevance evaluation...")
    try:
        results["evaluations"]["source_relevance"] = evaluate_source_relevance(
            query=query,
            sources=sources,
            trace_id=trace_id,
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.error("Failed to run source relevance evaluation: %s", e, exc_info=True)
        results["evaluations"]["source_relevance"] = {"error": str(e), "status": "failed"}

    eval_logger.info("Running bias detection evaluation...")
    eval_logger.info("Running hallucination evaluation...")
    try:
        results["evaluations"]["hallucination"] = evaluate_hallucination(
            query=query,
            answer=research_output,
            context="; ".join(sources[:5]) if sources else "",
            trace_id=trace_id,
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.error("Failed to run hallucination evaluation: %s", e, exc_info=True)
        results["evaluations"]["hallucination"] = {"error": str(e), "status": "failed"}

    eval_logger.info("Running reference grounding evaluation...")
    try:
        results["evaluations"]["reference"] = evaluate_reference(
            query=query,
            answer=research_output,
            context="; ".join(sources[:5]) if sources else "",
            trace_id=trace_id,
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.error("Failed to run reference evaluation: %s", e, exc_info=True)
        results["evaluations"]["reference"] = {"error": str(e), "status": "failed"}

    try:
        results["evaluations"]["bias"] = evaluate_bias_detection(
            research_output=research_output,
            query=query,
            trace_id=trace_id,
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.error("Failed to run bias detection evaluation: %s", e, exc_info=True)
        results["evaluations"]["bias"] = {"error": str(e), "status": "failed"}

    # Calculate overall score with error handling
    try:
        quality_score = results["evaluations"]["quality"].get("scores", {}).get("overall", 3.0)
        source_score = results["evaluations"]["source_relevance"].get("average", 3.0)
        bias_score = results["evaluations"]["bias"].get("bias_score", 3.0)
        hallucination_score = results["evaluations"]["hallucination"].get("hallucination_score", 3.0)
        reference_score = results["evaluations"]["reference"].get("reference_score", 3.0)

        if results["evaluations"]["quality"].get("status") != "success":
            quality_score = 3.0
            eval_logger.warning("Using default quality score due to evaluation failure")
        if results["evaluations"]["source_relevance"].get("status") != "success":
            source_score = 3.0
            eval_logger.warning("Using default source relevance score due to evaluation failure")
        if results["evaluations"]["bias"].get("status") != "success":
            bias_score = 3.0
            eval_logger.warning("Using default bias score due to evaluation failure")
        if results["evaluations"]["hallucination"].get("status") != "success":
            hallucination_score = 3.0
            eval_logger.warning("Using default hallucination score due to evaluation failure")
        if results["evaluations"]["reference"].get("status") != "success":
            reference_score = 3.0
            eval_logger.warning("Using default reference score due to evaluation failure")

        overall_score = (
            quality_score + source_score + bias_score + hallucination_score + reference_score
        ) / 5.0
        results["overall_score"] = overall_score

        eval_logger.info("Overall evaluation score: %.2f", overall_score)
        eval_logger.info("  - Quality: %.2f", quality_score)
        eval_logger.info("  - Source Relevance: %.2f", source_score)
        eval_logger.info("  - Bias: %.2f", bias_score)
        eval_logger.info("  - Hallucination: %.2f", hallucination_score)
        eval_logger.info("  - Reference: %.2f", reference_score)

    except Exception as score_error:  # pragma: no cover - defensive
        logger.error("Failed to calculate overall score: %s", score_error, exc_info=True)
        results["overall_score"] = 3.0
        results["score_calculation_error"] = str(score_error)

    elapsed_time = time.time() - start_time
    results["elapsed_time"] = elapsed_time
    results["status"] = "completed"

    successful_evals = sum(
        1 for eval_result in results["evaluations"].values() if eval_result.get("status") == "success"
    )
    total_evals = len(results["evaluations"])

    if successful_evals == total_evals:
        results["status"] = "success"
        eval_logger.info("=" * 60)
        eval_logger.info("✅ Comprehensive evaluation completed successfully in %.2fs", elapsed_time)
        eval_logger.info("   All %s evaluations passed", total_evals)
        eval_logger.info("=" * 60)
    elif successful_evals > 0:
        results["status"] = "partial_success"
        eval_logger.warning("=" * 60)
        eval_logger.warning(
            "⚠️ Comprehensive evaluation completed with partial success in %.2fs", elapsed_time
        )
        eval_logger.warning("   %s/%s evaluations passed", successful_evals, total_evals)
        eval_logger.warning("=" * 60)
    else:
        results["status"] = "failed"
        eval_logger.error("=" * 60)
        eval_logger.error("❌ Comprehensive evaluation failed in %.2fs", elapsed_time)
        eval_logger.error("   %s/%s evaluations passed", successful_evals, total_evals)
        eval_logger.error("=" * 60)

    return results
