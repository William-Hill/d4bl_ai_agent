"""Run the full training data pipeline: extract → distill → prepare.

Usage:
    python scripts/run_training_pipeline.py                    # Full pipeline
    python scripts/run_training_pipeline.py --stage extract    # Corpus only
    python scripts/run_training_pipeline.py --stage distill    # Pairs only
    python scripts/run_training_pipeline.py --stage prepare    # Split only
    python scripts/run_training_pipeline.py --dry-run          # Preview only
"""

import argparse
import os
import sys
import time


def _positive_int(value: str) -> int:
    """Argparse type function that accepts only positive integers."""
    try:
        ivalue = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer")
    if ivalue <= 0:
        raise argparse.ArgumentTypeError(f"{value!r} must be a positive integer (got {ivalue})")
    return ivalue


def main():
    parser = argparse.ArgumentParser(description="Training data pipeline")
    parser.add_argument(
        "--stage",
        choices=["extract", "distill", "prepare", "all"],
        default="all",
    )
    parser.add_argument(
        "--task",
        choices=["query_parser", "explainer", "evaluator", "all"],
        default="all",
    )
    parser.add_argument("--max-per-table", type=_positive_int, default=10_000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print("DRY RUN — would execute:")
        if args.stage in ("extract", "all"):
            print("  Stage 1: Extract corpus from DB")
        if args.stage in ("distill", "all"):
            print(f"  Stage 2: Generate training pairs (task={args.task})")
            print("  Requires: ANTHROPIC_API_KEY, DAGSTER_POSTGRES_URL")
        if args.stage in ("prepare", "all"):
            print(f"  Stage 3: Filter, dedup, split (task={args.task})")
        return

    start = time.time()

    if args.stage in ("extract", "all"):
        print("\n" + "=" * 60)
        print("STAGE 1: Domain Corpus Extraction")
        print("=" * 60)
        from scripts.training.extract_corpus import main as extract_main
        extract_main(max_per_table=args.max_per_table)

    if args.stage in ("distill", "all"):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("Error: Set ANTHROPIC_API_KEY env var", file=sys.stderr)
            sys.exit(1)
        print("\n" + "=" * 60)
        print("STAGE 2: Claude Distillation")
        print("=" * 60)
        from scripts.training.generate_training_pairs import main as distill_main
        distill_main(task=args.task)

    if args.stage in ("prepare", "all"):
        print("\n" + "=" * 60)
        print("STAGE 3: Dataset Preparation")
        print("=" * 60)
        from scripts.training.prepare_dataset import main as prepare_main
        prepare_main(task=args.task)

    elapsed = time.time() - start
    print(f"\nPipeline complete in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
