"""Compare baseline vs fine-tuned model outputs side by side.

Usage:
    python -m scripts.training.compare_models
    python -m scripts.training.compare_models --task query_parser
    python -m scripts.training.compare_models --baseline mistral --ollama-url http://localhost:11434
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from dataclasses import dataclass

from scripts.training.validate_model_output import (
    validate_evaluator_output,
    validate_explainer_output,
    validate_parser_output,
)

# Sample prompts per task (representative of real usage)
SAMPLE_PROMPTS: dict[str, list[str]] = {
    "query_parser": [
        "What is the median household income for Black families in Mississippi?",
        "Compare cancer rates between white and Hispanic populations in Texas and California",
        "Show me the trend in police use of force incidents in Chicago over the last 5 years",
        "Which states have the highest incarceration rates for Black men?",
        "How does air quality near EPA Superfund sites affect minority communities?",
    ],
    "explainer": [
        (
            "Data source: census\nMetric: median_household_income\n"
            "State: Mississippi (FIPS 28)\nValue: 45081\n"
            "National average: 69021\nYear: 2022\n"
            "Racial breakdown: white: 55602, black: 32815, hispanic: 42189\n"
            "Max disparity ratio: 1.69 (white vs black)\n\n"
            "Provide a concise narrative explaining what this data means for "
            "racial equity in this state."
        ),
    ],
    "evaluator": [
        (
            "Evaluate the following response for equity framing quality.\n\n"
            "Query: What is the median household income in Mississippi?\n"
            "Response: The median household income in Mississippi is $45,081, "
            "which is below the national average of $69,021. Black families earn "
            "significantly less at $32,815 compared to white families at $55,602.\n\n"
            "Score 1-5 on: structural framing, community voice, policy connection, "
            "data acknowledgment."
        ),
    ],
}

VALIDATORS = {
    "query_parser": validate_parser_output,
    "explainer": validate_explainer_output,
    "evaluator": validate_evaluator_output,
}


@dataclass
class ComparisonResult:
    prompt: str
    task: str
    baseline_valid: bool
    baseline_latency: float
    finetuned_valid: bool
    finetuned_latency: float
    baseline_output: str = ""
    finetuned_output: str = ""
    baseline_errors: list[str] | None = None
    finetuned_errors: list[str] | None = None

    @property
    def latency_delta(self) -> float:
        return self.finetuned_latency - self.baseline_latency

    @property
    def validity_improved(self) -> bool:
        return self.finetuned_valid and not self.baseline_valid


async def _run_prompt(
    base_url: str, model: str, prompt: str, timeout: int = 60,
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


async def compare_single(
    base_url: str,
    baseline_model: str,
    finetuned_model: str,
    task: str,
    prompt: str,
) -> ComparisonResult:
    """Run one prompt through both models and compare."""
    validator = VALIDATORS[task]

    try:
        b_output, b_latency = await _run_prompt(base_url, baseline_model, prompt)
    except Exception as e:
        b_output, b_latency = str(e), float("nan")

    try:
        f_output, f_latency = await _run_prompt(base_url, finetuned_model, prompt)
    except Exception as e:
        f_output, f_latency = str(e), float("nan")

    b_result = validator(b_output)
    f_result = validator(f_output)

    return ComparisonResult(
        prompt=prompt[:100],
        task=task,
        baseline_valid=b_result.valid,
        baseline_latency=round(b_latency, 3),
        finetuned_valid=f_result.valid,
        finetuned_latency=round(f_latency, 3),
        baseline_output=b_output[:200],
        finetuned_output=f_output[:200],
        baseline_errors=b_result.errors or None,
        finetuned_errors=f_result.errors or None,
    )


def format_report(results: list[ComparisonResult]) -> str:
    """Format comparison results into a human-readable report."""
    lines = ["=" * 70, "Model Comparison Report", "=" * 70, ""]

    by_task: dict[str, list[ComparisonResult]] = {}
    for r in results:
        by_task.setdefault(r.task, []).append(r)

    for task, task_results in by_task.items():
        lines.append(f"## {task}")
        lines.append("-" * 40)

        b_valid = sum(1 for r in task_results if r.baseline_valid)
        f_valid = sum(1 for r in task_results if r.finetuned_valid)
        total = len(task_results)

        b_avg_lat = sum(r.baseline_latency for r in task_results) / total
        f_avg_lat = sum(r.finetuned_latency for r in task_results) / total

        lines.append(f"  Validity:  baseline {b_valid}/{total}  |  fine-tuned {f_valid}/{total}")
        lines.append(f"  Latency:   baseline {b_avg_lat:.2f}s  |  fine-tuned {f_avg_lat:.2f}s")
        lines.append("")

        for i, r in enumerate(task_results, 1):
            status = "+" if r.finetuned_valid else "x"
            delta = f"{r.latency_delta:+.2f}s"
            lines.append(f"  [{i}] {status} {delta}  {r.prompt[:60]}...")
            if r.finetuned_errors:
                lines.append(f"      Errors: {', '.join(r.finetuned_errors)}")

        lines.append("")

    return "\n".join(lines)


async def main(args: argparse.Namespace) -> int:
    tasks = [args.task] if args.task else list(SAMPLE_PROMPTS.keys())
    results: list[ComparisonResult] = []

    for task in tasks:
        finetuned = {
            "query_parser": "d4bl-query-parser",
            "explainer": "d4bl-explainer",
            "evaluator": "d4bl-evaluator",
        }[task]

        for prompt in SAMPLE_PROMPTS[task]:
            result = await compare_single(
                base_url=args.ollama_url,
                baseline_model=args.baseline,
                finetuned_model=finetuned,
                task=task,
                prompt=prompt,
            )
            results.append(result)

    print(format_report(results))
    all_failed = all(not r.finetuned_valid for r in results)
    return 1 if all_failed else 0


def cli() -> int:
    parser = argparse.ArgumentParser(description="Compare baseline vs fine-tuned models")
    parser.add_argument("--baseline", default="mistral", help="Baseline model name")
    parser.add_argument("--task", choices=["query_parser", "explainer", "evaluator"],
                        help="Run only one task (default: all)")
    parser.add_argument("--ollama-url", default="http://localhost:11434",
                        help="Ollama base URL")
    args = parser.parse_args()
    return asyncio.run(main(args))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(cli())