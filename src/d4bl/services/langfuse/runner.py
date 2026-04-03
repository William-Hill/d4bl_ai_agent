from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from d4bl.llm import get_llm_for_task
from d4bl.services.langfuse._base import EvalStatus
from d4bl.services.langfuse.bias import evaluate_bias_detection
from d4bl.services.langfuse.client import get_langfuse_eval_client
from d4bl.services.langfuse.content_relevance import evaluate_content_relevance
from d4bl.services.langfuse.hallucination import evaluate_hallucination
from d4bl.services.langfuse.quality import evaluate_research_quality
from d4bl.services.langfuse.reference import evaluate_reference
from d4bl.services.langfuse.report_relevance import evaluate_report_relevance
from d4bl.services.langfuse.source_relevance import evaluate_source_relevance

logger = logging.getLogger(__name__)
eval_logger = logging.getLogger(f"{__name__}.evaluations")


def _build_context(sources: list[str], research_output: str) -> str:
    """Build context string for hallucination/reference evaluations."""
    if sources and len(sources) > 0 and not sources[0].startswith("No URLs"):
        return "; ".join(sources[:5])
    eval_logger.warning("No sources found, using research output as context")
    return research_output[:1000] if research_output else "No context available"


def _score_with_default(
    evaluations: dict[str, Any],
    key: str,
    score_path: str,
    default: float = 3.0,
) -> float | None:
    """Extract a score from evaluation results, returning *None* for skipped evals."""
    result = evaluations.get(key, {})
    status = result.get("status")
    if status == EvalStatus.SKIPPED:
        return None
    if status != EvalStatus.SUCCESS:
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
    sources: list[str],
    trace_id: str | None = None,
    extracted_contents: list[dict[str, Any]] | None = None,
    report: str | None = None,
) -> dict[str, Any]:
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
        llm = get_llm_for_task("evaluator")
    except Exception as llm_err:
        logger.error("Failed to initialise LLM for evaluations: %s", llm_err, exc_info=True)
        llm = None

    results: dict[str, Any] = {
        "query": query,
        "trace_id": trace_id,
        "evaluations": {},
        "start_time": start_time,
    }

    context = _build_context(sources, research_output)

    # --- Build evaluation specs (core + optional) ---
    eval_specs: list[tuple[str, Callable[..., dict[str, Any]], dict[str, Any]]] = [
        (
            "quality",
            evaluate_research_quality,
            dict(
                query=query,
                research_output=research_output,
                sources=sources,
                trace_id=trace_id,
                llm=llm,
                langfuse=langfuse,
            ),
        ),
        (
            "source_relevance",
            evaluate_source_relevance,
            dict(
                query=query,
                sources=sources,
                trace_id=trace_id,
                langfuse=langfuse,
            ),
        ),
        (
            "hallucination",
            evaluate_hallucination,
            dict(
                query=query,
                answer=research_output,
                context=context,
                trace_id=trace_id,
                llm=llm,
                langfuse=langfuse,
            ),
        ),
        (
            "reference",
            evaluate_reference,
            dict(
                query=query,
                answer=research_output,
                context=context,
                trace_id=trace_id,
                llm=llm,
                langfuse=langfuse,
            ),
        ),
        (
            "bias",
            evaluate_bias_detection,
            dict(
                research_output=research_output,
                query=query,
                trace_id=trace_id,
                llm=llm,
                langfuse=langfuse,
            ),
        ),
    ]

    # Add optional evaluations when their preconditions are met
    if extracted_contents and len(extracted_contents) > 0:
        eval_specs.append(
            (
                "content_relevance",
                evaluate_content_relevance,
                dict(
                    query=query,
                    extracted_contents=extracted_contents,
                    trace_id=trace_id,
                    llm=llm,
                    langfuse=langfuse,
                ),
            )
        )
    else:
        eval_logger.info("No extracted contents, skipping content relevance")
        results["evaluations"]["content_relevance"] = {
            "status": EvalStatus.SKIPPED,
            "reason": "no_extracted_contents",
        }

    if report and report.strip():
        eval_specs.append(
            (
                "report_relevance",
                evaluate_report_relevance,
                dict(
                    query=query,
                    report=report,
                    trace_id=trace_id,
                    llm=llm,
                    langfuse=langfuse,
                ),
            )
        )
    else:
        eval_logger.info("No report provided, skipping report relevance")
        results["evaluations"]["report_relevance"] = {
            "status": EvalStatus.SKIPPED,
            "reason": "no_report",
        }

    # --- Run all evaluations in parallel (finding 3.1) ---
    def _run_eval(
        name: str,
        func: Callable[..., dict[str, Any]],
        kwargs: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        eval_logger.info("Running %s evaluation...", name)
        try:
            return name, func(**kwargs)
        except Exception as e:
            logger.error("Failed to run %s evaluation: %s", name, e, exc_info=True)
            return name, {"error": str(e), "status": EvalStatus.FAILED}

    eval_timeout_s = 120
    executor = ThreadPoolExecutor(max_workers=len(eval_specs))
    futures = {
        executor.submit(_run_eval, name, func, kwargs): name for name, func, kwargs in eval_specs
    }
    try:
        for future in as_completed(futures, timeout=eval_timeout_s):
            name, result = future.result()
            results["evaluations"][name] = result
    except TimeoutError:
        logger.error(
            "Evaluation batch timed out after %ss",
            eval_timeout_s,
        )
        for future, name in futures.items():
            if not future.done():
                future.cancel()
                results["evaluations"][name] = {
                    "error": "evaluation_timeout",
                    "status": EvalStatus.FAILED,
                }
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

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

    skipped_evals = sum(
        1 for r in results["evaluations"].values() if r.get("status") == EvalStatus.SKIPPED
    )
    successful_evals = sum(
        1 for r in results["evaluations"].values() if r.get("status") == EvalStatus.SUCCESS
    )
    ran_evals = len(results["evaluations"]) - skipped_evals

    if ran_evals == 0:
        results["status"] = EvalStatus.SKIPPED
        eval_logger.warning("=" * 60)
        eval_logger.warning("All evaluations skipped in %.2fs", elapsed_time)
        eval_logger.warning("=" * 60)
    elif successful_evals == ran_evals:
        results["status"] = EvalStatus.SUCCESS
        eval_logger.info("=" * 60)
        eval_logger.info(
            "All %s evaluations passed in %.2fs",
            ran_evals,
            elapsed_time,
        )
        eval_logger.info("=" * 60)
    elif successful_evals > 0:
        results["status"] = EvalStatus.PARTIAL_SUCCESS
        eval_logger.warning("=" * 60)
        eval_logger.warning(
            "%s/%s evaluations passed in %.2fs",
            successful_evals,
            ran_evals,
            elapsed_time,
        )
        eval_logger.warning("=" * 60)
    else:
        results["status"] = EvalStatus.FAILED
        eval_logger.error("=" * 60)
        eval_logger.error("All evaluations failed in %.2fs", elapsed_time)
        eval_logger.error("=" * 60)

    return results