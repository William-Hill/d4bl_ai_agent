import argparse
import asyncio
import sys
from pathlib import Path
from typing import List, Optional
from uuid import UUID

# Ensure the src directory is on sys.path so we can import the refactored helpers
PROJECT_ROOT = Path(__file__).parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from d4bl.evals.runner import run_evals_and_log


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run LLM evaluations on Phoenix traces",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\nExamples:\n  # Run all evaluators on all traces (slow)\n  python run_evals.py\n\n  # Run only bias evaluator on 10 rows (fast for debugging)\n  python run_evals.py --max-rows 10 --eval-types bias\n\n  # Run hallucination and reference on 5 rows with higher concurrency\n  python run_evals.py --max-rows 5 --eval-types hallucination reference --concurrency 3\n        """,
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Limit number of rows to evaluate (for faster debugging). Default: all rows",
    )
    parser.add_argument(
        "--eval-types",
        nargs="+",
        choices=["hallucination", "bias", "reference"],
        default=None,
        help="Which evaluators to run. Default: all evaluators",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help=(
            "Number of concurrent evaluation requests. Default: 1 "
            "(increase for faster runs if Ollama can handle it)"
        ),
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive mode: select which job(s) to evaluate",
    )
    parser.add_argument(
        "--job-ids",
        nargs="+",
        type=UUID,
        default=None,
        help="Optional list of job IDs to restrict evaluations (skips interactive prompt)",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Optional path to write eval_results_with_explanations.csv",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(
        run_evals_and_log(
            max_rows=args.max_rows,
            eval_types=args.eval_types,
            concurrency=args.concurrency,
            interactive=args.interactive,
            selected_job_ids=args.job_ids,
            output_csv_path=args.output_csv,
        )
    )


if __name__ == "__main__":
    main()
