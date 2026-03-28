"""Eval harness CLI — run test sets through models and check ship criteria.

Usage:
    python -m scripts.training.run_eval_harness
    python -m scripts.training.run_eval_harness --task query_parser
    python -m scripts.training.run_eval_harness --persist  # save to DB
    python -m scripts.training.run_eval_harness --model-version v1.1
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.training.eval_harness import (
    compute_evaluator_metrics,
    compute_explainer_metrics,
    compute_parser_metrics,
    load_test_set,
)
from scripts.training.ship_criteria import ShipDecision, check_ship_criteria

logger = logging.getLogger(__name__)

# Metrics where higher is worse (latency, MAE); also display as raw numbers
_HIGHER_IS_WORSE = {"p50_latency_ms", "p95_latency_ms", "relevance_mae", "bias_mae"}

# Default test set paths (relative to repo root)
DEFAULT_TEST_SETS: dict[str, str] = {
    "query_parser": "scripts/training_data/final/query_parser_test.jsonl",
    "explainer": "scripts/training_data/final/explainer_test.jsonl",
    "evaluator": "scripts/training_data/final/evaluator_test.jsonl",
}

# Fine-tuned model names per task
TASK_MODELS: dict[str, str] = {
    "query_parser": "d4bl-query-parser",
    "explainer": "d4bl-explainer",
    "evaluator": "d4bl-evaluator",
}


def resolve_model_name(model_override: str | None, task: str) -> str:
    """Resolve inference model: --model override takes precedence over TASK_MODELS."""
    if model_override:
        return model_override
    return TASK_MODELS[task]


@dataclass
class RegressionAlert:
    metric: str
    previous: float
    current: float
    delta: float
    direction: str  # "increased" or "decreased"


@dataclass
class EvalRunResult:
    task: str
    model_name: str
    model_version: str
    base_model_name: str
    test_set_hash: str
    metrics: dict[str, float | None]
    ship_decision: ShipDecision
    elapsed_seconds: float = 0.0


def compute_test_set_hash(path: str) -> str:
    """Compute SHA256 hash of a test set file for version tracking."""
    content = Path(path).read_bytes()
    return hashlib.sha256(content).hexdigest()


async def _run_prompt(
    base_url: str, model: str, prompt: str, timeout: int = 120,
) -> tuple[str, float]:
    """Run a single prompt and return (output, latency_seconds)."""
    from d4bl.llm.ollama_client import ollama_generate

    start = time.monotonic()
    output = await ollama_generate(
        base_url=base_url, prompt=prompt, model=model,
        temperature=0.1, timeout_seconds=timeout,
    )
    elapsed = time.monotonic() - start
    return output, elapsed


async def run_task_eval(
    task: str,
    test_set: list[dict],
    model_name: str,
    model_version: str,
    base_model_name: str,
    base_url: str,
    test_set_hash: str,
    *,
    partial: bool = False,
) -> EvalRunResult:
    """Run evaluation for a single task.

    Runs all test examples through the fine-tuned model,
    computes metrics, and checks ship criteria.
    """
    start = time.monotonic()
    outputs: list[dict] = []

    for example in test_set:
        try:
            raw, latency = await _run_prompt(
                base_url, model_name, example["input"]
            )
        except Exception as e:
            logger.warning("Prompt failed: %s", e)
            raw, latency = str(e), 0.0

        outputs.append({"raw": raw, "latency": latency})

    # Compute task-specific metrics
    if task == "query_parser":
        expected = [ex.get("expected", {}) or {} for ex in test_set]
        metrics = compute_parser_metrics(outputs, expected)
    elif task == "explainer":
        metrics = compute_explainer_metrics(outputs)
    elif task == "evaluator":
        expected_labels = []
        expected_scores = []
        for ex in test_set:
            exp = ex.get("expected") or {}
            expected_labels.append(exp.get("label", ""))
            score = exp.get("score")
            if isinstance(score, (int, float)):
                expected_scores.append(float(score))
        metrics = compute_evaluator_metrics(
            outputs,
            expected_labels=expected_labels if any(expected_labels) else None,
            expected_scores=expected_scores if expected_scores else None,
        )
    else:
        logger.warning("Unknown task '%s', returning empty metrics", task)
        metrics = {}

    # Filter None values before ship criteria check (deferred LLM-judged metrics)
    checkable = {k: v for k, v in metrics.items() if v is not None}
    ship_decision = check_ship_criteria(checkable, task, partial=partial)

    elapsed = time.monotonic() - start

    return EvalRunResult(
        task=task,
        model_name=model_name,
        model_version=model_version,
        base_model_name=base_model_name,
        test_set_hash=test_set_hash,
        metrics=metrics,
        ship_decision=ship_decision,
        elapsed_seconds=round(elapsed, 2),
    )


def format_eval_report(results: list[EvalRunResult]) -> str:
    """Format eval results into a human-readable report."""
    lines = ["=" * 70, "D4BL Model Evaluation Report", "=" * 70, ""]

    for r in results:
        decision_str = r.ship_decision.decision.upper()
        lines.append(f"## {r.task} -- {r.model_name} ({r.model_version})")
        lines.append(f"   Decision: {decision_str}")
        lines.append(f"   Elapsed:  {r.elapsed_seconds:.1f}s")
        lines.append(f"   Test set: {r.test_set_hash[:12]}...")
        lines.append("")

        lines.append("   Metrics:")
        for metric, value in sorted(r.metrics.items()):
            if value is None:
                lines.append(f"     {metric}: (deferred -- requires LLM judge)")
            elif metric in _HIGHER_IS_WORSE:
                lines.append(f"     {metric}: {value:.2f}")
            elif isinstance(value, float) and value <= 1.0:
                lines.append(f"     {metric}: {value:.2%}")
            else:
                lines.append(f"     {metric}: {value:.2f}")
        lines.append("")

        if r.ship_decision.blocking_failures:
            lines.append("   BLOCKING FAILURES:")
            for f in r.ship_decision.blocking_failures:
                actual = "(missing)" if f.actual is None else f"{f.actual}"
                lines.append(
                    f"     {f.metric}: {actual} "
                    f"({'<' if f.direction == 'min' else '>'} "
                    f"{f.threshold})"
                )
            lines.append("")

        if r.ship_decision.nonblocking_failures:
            lines.append("   NON-BLOCKING GAPS:")
            for f in r.ship_decision.nonblocking_failures:
                actual = "(missing)" if f.actual is None else f"{f.actual}"
                lines.append(f"     {f.metric}: {actual} (target: {f.threshold})")
            lines.append("")

        lines.append("-" * 70)
        lines.append("")

    # Summary
    decisions = [r.ship_decision.decision for r in results]
    if all(d == "ship" for d in decisions):
        lines.append("OVERALL: SHIP -- all tasks pass blocking criteria")
    elif any(d == "no_ship" for d in decisions):
        lines.append("OVERALL: NO SHIP -- blocking failures detected")
    else:
        lines.append("OVERALL: SHIP WITH GAPS -- non-blocking issues remain")

    return "\n".join(lines)


def detect_regressions(
    current: dict[str, float | None],
    previous: dict[str, float | None] | None,
    task: str,
    tolerance: float = 0.02,
) -> list[RegressionAlert]:
    """Compare current metrics against previous run, flag regressions.

    A regression is when a metric moves in the wrong direction by more
    than ``tolerance`` (default 2%).

    Args:
        current: Current eval metrics.
        previous: Previous eval metrics (None = no comparison).
        task: Task name (for context, currently unused).
        tolerance: Minimum absolute change to trigger alert.

    Returns:
        List of RegressionAlert for each regressed metric.
    """
    if previous is None:
        return []

    alerts: list[RegressionAlert] = []
    for metric, cur_val in current.items():
        if cur_val is None:
            continue
        prev_val = previous.get(metric)
        if prev_val is None:
            continue

        delta = cur_val - prev_val

        if metric in _HIGHER_IS_WORSE:
            # For latency/MAE, increase is bad
            if delta > tolerance:
                alerts.append(RegressionAlert(
                    metric=metric, previous=prev_val, current=cur_val,
                    delta=delta, direction="increased",
                ))
        else:
            # For accuracy/F1, decrease is bad
            if delta < -tolerance:
                alerts.append(RegressionAlert(
                    metric=metric, previous=prev_val, current=cur_val,
                    delta=delta, direction="decreased",
                ))

    return alerts


def _print_suggestions(suggestions) -> None:
    """Print suggestion rules to stdout."""
    for s in suggestions.rules:
        icon = "BLOCK" if s.severity == "blocking" else "WARN"
        print(f"  [{icon}] {s.metric}: {s.current:.2f} -> {s.target:.2f}")
        print(f"         {s.suggestion}")
    if not suggestions.rules:
        print("  All metrics pass -- no suggestions.")


def _make_engine_and_session():
    """Create an async engine + session factory from settings."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from d4bl.infra.database import get_database_url

    engine = create_async_engine(get_database_url())
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def persist_results(results: list[EvalRunResult]) -> None:
    """Save eval results to the model_eval_runs database table."""
    from d4bl.infra.database import ModelEvalRun
    from scripts.training.suggestions import generate_suggestions

    engine, session_factory = _make_engine_and_session()

    try:
        async with session_factory() as session:
            for r in results:
                run = ModelEvalRun(
                    model_name=r.model_name,
                    model_version=r.model_version,
                    base_model_name=r.base_model_name,
                    task=r.task,
                    test_set_hash=r.test_set_hash,
                    metrics=r.metrics,
                    ship_decision=r.ship_decision.decision,
                    blocking_failures=[
                        asdict(f) for f in r.ship_decision.blocking_failures
                    ] or None,
                    suggestions=generate_suggestions(r.task, r.metrics).to_dict(),
                )
                session.add(run)
            await session.commit()
        logger.info("Persisted %d eval runs to database", len(results))
    except Exception as e:
        logger.error("Failed to persist results to database: %s", e)
        raise
    finally:
        await engine.dispose()


async def _analyze_existing_run(run_id_or_latest: str, task: str | None) -> None:
    """Load an existing eval run from DB, generate suggestions, update the row."""
    from sqlalchemy import desc as sa_desc
    from sqlalchemy.future import select

    from d4bl.infra.database import ModelEvalRun
    from scripts.training.suggestions import generate_suggestions

    engine, session_factory = _make_engine_and_session()

    try:
        async with session_factory() as session:
            if run_id_or_latest == "latest":
                query = select(ModelEvalRun).order_by(sa_desc(ModelEvalRun.created_at))
                if task:
                    query = query.where(ModelEvalRun.task == task)
                result = await session.execute(query.limit(1))
                run = result.scalar_one_or_none()
            else:
                result = await session.execute(
                    select(ModelEvalRun).where(ModelEvalRun.id == run_id_or_latest)
                )
                run = result.scalar_one_or_none()

            if not run:
                print(f"No eval run found for: {run_id_or_latest}")
                return

            suggestions = generate_suggestions(run.task, run.metrics or {})
            existing = run.suggestions or {}
            if existing.get("llm_analysis"):
                suggestions.llm_analysis = existing["llm_analysis"]
            run.suggestions = suggestions.to_dict()
            await session.commit()

            print(f"Updated suggestions for run {run.id} ({run.task})")
            _print_suggestions(suggestions)
    finally:
        await engine.dispose()


async def main(args: argparse.Namespace) -> int:
    if args.analyze_existing:
        await _analyze_existing_run(args.analyze_existing, args.task)
        return 0

    if args.test_set and not args.task:
        logger.error("--test-set requires --task to specify which task to run")
        return 1

    tasks = [args.task] if args.task else list(DEFAULT_TEST_SETS.keys())
    results: list[EvalRunResult] = []

    for task in tasks:
        test_path = args.test_set or DEFAULT_TEST_SETS[task]
        if not Path(test_path).exists():
            logger.error("Test set not found: %s", test_path)
            continue

        test_set = load_test_set(test_path)
        if not test_set:
            logger.warning("Empty test set: %s", test_path)
            continue

        model_name = resolve_model_name(args.model, task)
        logger.info(
            "Running %s eval: %d examples, model=%s",
            task, len(test_set), model_name,
        )

        result = await run_task_eval(
            task=task,
            test_set=test_set,
            model_name=model_name,
            model_version=args.model_version,
            base_model_name=args.baseline,
            base_url=args.ollama_url,
            test_set_hash=compute_test_set_hash(test_path),
            partial=args.partial,
        )
        results.append(result)

    if not results:
        logger.error("No results -- check test set paths")
        return 1

    print(format_eval_report(results))

    if args.persist:
        await persist_results(results)

    from scripts.training.suggestions import generate_suggestions
    print("\n" + "=" * 60)
    print("POST-EVAL SUGGESTIONS")
    print("=" * 60)
    for result in results:
        suggestions = generate_suggestions(result.task, result.metrics)
        print(f"\n--- {result.task} ---")
        _print_suggestions(suggestions)
        if args.analyze:
            print("  [LLM analysis coming soon -- requires Claude API key]")

    has_no_ship = any(r.ship_decision.decision == "no_ship" for r in results)
    return 1 if has_no_ship else 0


def build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Run D4BL model evaluation harness"
    )
    parser.add_argument(
        "--task", choices=["query_parser", "explainer", "evaluator"],
        help="Run only one task (default: all)",
    )
    parser.add_argument(
        "--test-set", help="Override test set JSONL path",
    )
    parser.add_argument(
        "--baseline", default="mistral", help="Baseline model name",
    )
    parser.add_argument(
        "--model",
        help="Override inference model (default: use task-specific fine-tuned model)",
    )
    parser.add_argument(
        "--model-version", default="v1.0",
        help="Version label for this eval run",
    )
    parser.add_argument(
        "--ollama-url", default="http://localhost:11434",
        help="Ollama base URL",
    )
    parser.add_argument(
        "--persist", action="store_true",
        help="Save results to model_eval_runs DB table",
    )
    parser.add_argument(
        "--partial", action="store_true",
        help="Only check computable metrics (skip LLM-judged criteria)",
    )
    parser.add_argument(
        "--analyze", action="store_true",
        help="Print LLM analysis placeholder after suggestions (coming soon)",
    )
    parser.add_argument(
        "--analyze-existing",
        help="Analyze an existing eval run by UUID or 'latest' (skips model inference)",
    )
    return parser


def cli() -> int:
    args = build_parser().parse_args()
    return asyncio.run(main(args))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    sys.exit(cli())
