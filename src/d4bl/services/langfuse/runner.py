from __future__ import annotations

import time
import logging
from typing import Any, Dict, List, Optional

from d4bl.services.langfuse.client import get_langfuse_eval_client
from d4bl.services.langfuse.llm_runner import get_eval_llm
from d4bl.services.langfuse.quality import evaluate_research_quality
from d4bl.services.langfuse.source_relevance import evaluate_source_relevance
from d4bl.services.langfuse.bias import evaluate_bias_detection
from d4bl.services.langfuse.hallucination import evaluate_hallucination
from d4bl.services.langfuse.reference import evaluate_reference
from d4bl.services.langfuse.content_relevance import evaluate_content_relevance
from d4bl.services.langfuse.report_relevance import evaluate_report_relevance

logger = logging.getLogger(__name__)
eval_logger = logging.getLogger(f"{__name__}.evaluations")


def _build_context(sources: List[str], research_output: str) -> str:
    """Build context string for hallucination/reference evaluations."""
    if sources and len(sources) > 0 and not sources[0].startswith("No URLs"):
        return "; ".join(sources[:5])
    eval_logger.warning("No sources found, using research output as context")
    return research_output[:1000] if research_output else "No context available"


def _score_with_default(
    evaluations: Dict[str, Any],
    key: str,
    score_path: str,
    default: float = 3.0,
) -> Optional[float]:
    """Extract a score from evaluation results, returning *None* for skipped evals."""
    result = evaluations.get(key, {})
    status = result.get("status")
    if status == "skipped":
        return None
    if status != "success":
        return default

    # Navigate dotted paths like "scores.overall"
    parts = score_path.split(".")
    val = result
    for part in parts:
        if isinstance(val, dict):
            val = val.get(part, default)
        else:
            return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


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

    # --- Init shared resources once (findings 3.2 + 3.3) ---
    langfuse = get_langfuse_eval_client()
    try:
        llm = get_eval_llm()
    except Exception as llm_err:
        logger.error("Failed to initialise LLM for evaluations: %s", llm_err, exc_info=True)
        llm = None

    results: Dict[str, Any] = {
        "query": query,
        "trace_id": trace_id,
        "evaluations": {},
        "start_time": start_time,
    }

    context = _build_context(sources, research_output)

    # --- Run evaluations ---
    eval_specs: list[tuple[str, dict[str, Any]]] = [
        ("quality", dict(
            query=query, research_output=research_output, sources=sources,
            trace_id=trace_id, llm=llm, langfuse=langfuse,
        )),
        ("source_relevance", dict(
            query=query, sources=sources, trace_id=trace_id, langfuse=langfuse,
        )),
        ("hallucination", dict(
            query=query, answer=research_output, context=context,
            trace_id=trace_id, llm=llm, langfuse=langfuse,
        )),
        ("reference", dict(
            query=query, answer=research_output, context=context,
            trace_id=trace_id, llm=llm, langfuse=langfuse,
        )),
        ("bias", dict(
            research_output=research_output, query=query,
            trace_id=trace_id, llm=llm, langfuse=langfuse,
        )),
    ]

    eval_funcs = {
        "quality": evaluate_research_quality,
        "source_relevance": evaluate_source_relevance,
        "hallucination": evaluate_hallucination,
        "reference": evaluate_reference,
        "bias": evaluate_bias_detection,
    }

    for name, kwargs in eval_specs:
        eval_logger.info("Running %s evaluation...", name)
        try:
            results["evaluations"][name] = eval_funcs[name](**kwargs)
        except Exception as e:
            logger.error("Failed to run %s evaluation: %s", name, e, exc_info=True)
            results["evaluations"][name] = {"error": str(e), "status": "failed"}

    # Optional evaluations
    if extracted_contents and len(extracted_contents) > 0:
        eval_logger.info("Running content relevance evaluation...")
        try:
            results["evaluations"]["content_relevance"] = evaluate_content_relevance(
                query=query, extracted_contents=extracted_contents,
                trace_id=trace_id, llm=llm, langfuse=langfuse,
            )
        except Exception as e:
            logger.error("Failed to run content relevance evaluation: %s", e, exc_info=True)
            results["evaluations"]["content_relevance"] = {"error": str(e), "status": "failed"}
    else:
        eval_logger.info("No extracted contents provided, skipping content relevance evaluation")
        results["evaluations"]["content_relevance"] = {"status": "skipped", "reason": "no_extracted_contents"}

    if report and report.strip():
        eval_logger.info("Running report relevance evaluation...")
        try:
            results["evaluations"]["report_relevance"] = evaluate_report_relevance(
                query=query, report=report,
                trace_id=trace_id, llm=llm, langfuse=langfuse,
            )
        except Exception as e:
            logger.error("Failed to run report relevance evaluation: %s", e, exc_info=True)
            results["evaluations"]["report_relevance"] = {"error": str(e), "status": "failed"}
    else:
        eval_logger.info("No report provided, skipping report relevance evaluation")
        results["evaluations"]["report_relevance"] = {"status": "skipped", "reason": "no_report"}

    # --- Flush Langfuse once at the end (finding 3.6) ---
    if langfuse:
        try:
            langfuse.flush()
        except Exception as flush_err:
            logger.warning("Langfuse flush failed: %s", flush_err)

    # --- Calculate overall score ---
    score_specs = [
        ("quality", "scores.overall"),
        ("source_relevance", "average"),
        ("bias", "bias_score"),
        ("hallucination", "hallucination_score"),
        ("reference", "reference_score"),
        ("content_relevance", "average"),
        ("report_relevance", "relevance_score"),
    ]

    scores_to_average: list[float] = []
    for eval_key, path in score_specs:
        val = _score_with_default(results["evaluations"], eval_key, path)
        if val is not None:
            scores_to_average.append(val)

    overall_score = sum(scores_to_average) / len(scores_to_average) if scores_to_average else 3.0
    results["overall_score"] = overall_score

    eval_logger.info("Overall evaluation score: %.2f", overall_score)
    for eval_key, path in score_specs:
        val = _score_with_default(results["evaluations"], eval_key, path)
        if val is not None:
            eval_logger.info("  - %s: %.2f", eval_key, val)

    elapsed_time = time.time() - start_time
    results["elapsed_time"] = elapsed_time

    successful_evals = sum(
        1 for r in results["evaluations"].values() if r.get("status") == "success"
    )
    total_evals = len(results["evaluations"])

    if successful_evals == total_evals:
        results["status"] = "success"
        eval_logger.info("=" * 60)
        eval_logger.info("All %s evaluations passed in %.2fs", total_evals, elapsed_time)
        eval_logger.info("=" * 60)
    elif successful_evals > 0:
        results["status"] = "partial_success"
        eval_logger.warning("=" * 60)
        eval_logger.warning("%s/%s evaluations passed in %.2fs", successful_evals, total_evals, elapsed_time)
        eval_logger.warning("=" * 60)
    else:
        results["status"] = "failed"
        eval_logger.error("=" * 60)
        eval_logger.error("All evaluations failed in %.2fs", elapsed_time)
        eval_logger.error("=" * 60)

    return results
