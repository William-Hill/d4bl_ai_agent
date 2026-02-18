from __future__ import annotations

import time
import logging
from typing import Any, Dict, List, Optional

from d4bl.services.langfuse.quality import evaluate_research_quality
from d4bl.services.langfuse.source_relevance import evaluate_source_relevance
from d4bl.services.langfuse.bias import evaluate_bias_detection
from d4bl.services.langfuse.hallucination import evaluate_hallucination
from d4bl.services.langfuse.reference import evaluate_reference
from d4bl.services.langfuse.content_relevance import evaluate_content_relevance
from d4bl.services.langfuse.report_relevance import evaluate_report_relevance

logger = logging.getLogger(__name__)
eval_logger = logging.getLogger(f"{__name__}.evaluations")
eval_logger.setLevel(logging.INFO)


def run_comprehensive_evaluation(
    query: str,
    research_output: str,
    sources: List[str],
    trace_id: Optional[str] = None,
    extracted_contents: Optional[List[Dict[str, Any]]] = None,
    report: Optional[str] = None,
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
        # Use sources if available, otherwise use a portion of research output as context
        if sources and len(sources) > 0 and not sources[0].startswith("No URLs"):
            context = "; ".join(sources[:5])
        else:
            # Fallback: use first part of research output as context
            context = research_output[:1000] if research_output else "No context available"
            eval_logger.warning("No sources found, using research output as context for hallucination evaluation")
        
        results["evaluations"]["hallucination"] = evaluate_hallucination(
            query=query,
            answer=research_output,
            context=context,
            trace_id=trace_id,
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.error("Failed to run hallucination evaluation: %s", e, exc_info=True)
        results["evaluations"]["hallucination"] = {"error": str(e), "status": "failed"}

    eval_logger.info("Running reference grounding evaluation...")
    try:
        # Use sources if available, otherwise use a portion of research output as context
        if sources and len(sources) > 0 and not sources[0].startswith("No URLs"):
            context = "; ".join(sources[:5])
        else:
            # Fallback: use first part of research output as context
            context = research_output[:1000] if research_output else "No context available"
            eval_logger.warning("No sources found, using research output as context for reference evaluation")
        
        results["evaluations"]["reference"] = evaluate_reference(
            query=query,
            answer=research_output,
            context=context,
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

    # Evaluate extracted content relevance
    eval_logger.info("Running content relevance evaluation...")
    try:
        if extracted_contents and len(extracted_contents) > 0:
            results["evaluations"]["content_relevance"] = evaluate_content_relevance(
                query=query,
                extracted_contents=extracted_contents,
                trace_id=trace_id,
            )
        else:
            eval_logger.info("No extracted contents provided, skipping content relevance evaluation")
            results["evaluations"]["content_relevance"] = {
                "status": "skipped",
                "reason": "no_extracted_contents",
            }
    except Exception as e:  # pragma: no cover - defensive
        logger.error("Failed to run content relevance evaluation: %s", e, exc_info=True)
        results["evaluations"]["content_relevance"] = {"error": str(e), "status": "failed"}

    # Evaluate report relevance
    eval_logger.info("Running report relevance evaluation...")
    try:
        if report and report.strip():
            results["evaluations"]["report_relevance"] = evaluate_report_relevance(
                query=query,
                report=report,
                trace_id=trace_id,
            )
        else:
            eval_logger.info("No report provided, skipping report relevance evaluation")
            results["evaluations"]["report_relevance"] = {
                "status": "skipped",
                "reason": "no_report",
            }
    except Exception as e:  # pragma: no cover - defensive
        logger.error("Failed to run report relevance evaluation: %s", e, exc_info=True)
        results["evaluations"]["report_relevance"] = {"error": str(e), "status": "failed"}

    # Calculate overall score with error handling
    try:
        quality_score = results["evaluations"]["quality"].get("scores", {}).get("overall", 3.0)
        source_score = results["evaluations"]["source_relevance"].get("average", 3.0)
        bias_score = results["evaluations"]["bias"].get("bias_score", 3.0)
        hallucination_score = results["evaluations"]["hallucination"].get("hallucination_score", 3.0)
        reference_score = results["evaluations"]["reference"].get("reference_score", 3.0)

        # Handle different statuses: success, skipped, failed
        quality_status = results["evaluations"]["quality"].get("status")
        if quality_status not in ("success", "skipped"):
            quality_score = 3.0
            eval_logger.warning("Using default quality score due to evaluation failure")
        elif quality_status == "skipped":
            eval_logger.info("Quality evaluation was skipped, using default score")
        
        source_status = results["evaluations"]["source_relevance"].get("status")
        if source_status not in ("success", "skipped"):
            source_score = 3.0
            eval_logger.warning("Using default source relevance score due to evaluation failure")
        elif source_status == "skipped":
            eval_logger.info("Source relevance evaluation was skipped (no sources), using default score")
        
        bias_status = results["evaluations"]["bias"].get("status")
        if bias_status not in ("success", "skipped"):
            bias_score = 3.0
            eval_logger.warning("Using default bias score due to evaluation failure")
        elif bias_status == "skipped":
            eval_logger.info("Bias evaluation was skipped, using default score")
        
        hallucination_status = results["evaluations"]["hallucination"].get("status")
        if hallucination_status not in ("success", "skipped"):
            hallucination_score = 3.0
            eval_logger.warning("Using default hallucination score due to evaluation failure")
        elif hallucination_status == "skipped":
            eval_logger.info("Hallucination evaluation was skipped, using default score")
        
        reference_status = results["evaluations"]["reference"].get("status")
        if reference_status not in ("success", "skipped"):
            reference_score = 3.0
            eval_logger.warning("Using default reference score due to evaluation failure")
        elif reference_status == "skipped":
            eval_logger.info("Reference evaluation was skipped, using default score")

        # Include new evaluations in overall score if available
        content_relevance_score = results["evaluations"]["content_relevance"].get("average", 3.0)
        report_relevance_score = results["evaluations"]["report_relevance"].get("relevance_score", 3.0)
        
        # Handle skipped evaluations
        content_relevance_status = results["evaluations"]["content_relevance"].get("status")
        if content_relevance_status not in ("success", "skipped"):
            content_relevance_score = 3.0
        elif content_relevance_status == "skipped":
            content_relevance_score = None  # Don't include in average if skipped
        
        report_relevance_status = results["evaluations"]["report_relevance"].get("status")
        if report_relevance_status not in ("success", "skipped"):
            report_relevance_score = 3.0
        elif report_relevance_status == "skipped":
            report_relevance_score = None  # Don't include in average if skipped
        
        # Calculate overall score (average of all non-skipped evaluations)
        scores_to_average = [quality_score, source_score, bias_score, hallucination_score, reference_score]
        if content_relevance_score is not None:
            scores_to_average.append(content_relevance_score)
        if report_relevance_score is not None:
            scores_to_average.append(report_relevance_score)
        
        overall_score = sum(scores_to_average) / len(scores_to_average) if scores_to_average else 3.0
        results["overall_score"] = overall_score

        eval_logger.info("Overall evaluation score: %.2f", overall_score)
        eval_logger.info("  - Quality: %.2f", quality_score)
        eval_logger.info("  - Source Relevance: %.2f", source_score)
        eval_logger.info("  - Bias: %.2f", bias_score)
        eval_logger.info("  - Hallucination: %.2f", hallucination_score)
        eval_logger.info("  - Reference: %.2f", reference_score)
        if content_relevance_status != "skipped":
            eval_logger.info("  - Content Relevance: %.2f", content_relevance_score)
        if report_relevance_status != "skipped":
            eval_logger.info("  - Report Relevance: %.2f", report_relevance_score)

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
