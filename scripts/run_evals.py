import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

# Ensure the src directory is on sys.path so we can import the refactored helpers
PROJECT_ROOT = Path(__file__).parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from d4bl.evals.runner import run_evals_and_log


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run LLM evaluations on completed research jobs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\nExamples:\n  # Run all evaluators on all jobs\n  python run_evals.py\n\n  # Run on 10 jobs with higher concurrency\n  python run_evals.py --max-rows 10 --concurrency 3\n\n  # Run on specific jobs\n  python run_evals.py --job-ids abc123 def456\n        """,
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Limit number of jobs to evaluate (for faster debugging). Default: all",
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
        "--job-ids",
        nargs="+",
        type=UUID,
        default=None,
        help="Optional list of job IDs to restrict evaluations",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(
        run_evals_and_log(
            max_rows=args.max_rows,
            concurrency=args.concurrency,
            selected_job_ids=args.job_ids,
        )
    )


if __name__ == "__main__":
    main()
