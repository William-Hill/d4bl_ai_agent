#!/usr/bin/env python3
"""Control runner for data ingestion scripts.

Run all or a subset of ingestion sources with timing and summary reporting.

Usage:
    python scripts/run_ingestion.py                    # run all sources
    python scripts/run_ingestion.py --sources cdc,epa  # run specific sources
    python scripts/run_ingestion.py --list             # list available sources
    python scripts/run_ingestion.py --dry-run          # show what would run
"""

import argparse
import importlib
import os
import sys
import time

# Ensure the scripts/ directory is on sys.path so that
# `import ingestion.ingest_xxx` (with relative helpers) works.
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# Also ensure src/ is on sys.path so we can import the shared registry.
_SRC_DIR = os.path.join(os.path.dirname(_SCRIPTS_DIR), "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from d4bl.services.ingestion_runner import SCRIPT_REGISTRY  # noqa: E402

# Deduplicate: SCRIPT_REGISTRY has aliases; keep only one key per module.
_seen: set[str] = set()
SOURCES: dict[str, str] = {}
for key, mod in SCRIPT_REGISTRY.items():
    if mod not in _seen:
        _seen.add(mod)
        SOURCES[key] = mod


def list_sources() -> None:
    """Print available ingestion sources."""
    print("Available ingestion sources:\n")
    print(f"  {'Source':<12} {'Script'}")
    print(f"  {'-' * 12} {'-' * 30}")
    for key, module in SOURCES.items():
        print(f"  {key:<12} scripts/ingestion/{module}.py")


def format_duration(seconds: float) -> str:
    """Format seconds into a human-readable duration string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(seconds, 60)
    return f"{int(minutes)}m {secs:.1f}s"


def run_source(name: str, module_name: str) -> tuple[int, float, str]:
    """Run a single ingestion source, returning (records, duration, status).

    Dynamically imports the module and calls its ``main()`` function.
    """
    print(f"\n{'=' * 60}")
    print(f"Running: {name} ({module_name})")
    print(f"{'=' * 60}")

    start = time.time()
    try:
        module = importlib.import_module(f"ingestion.{module_name}")
        records = module.main()
        duration = time.time() - start
        print(f"  -> {name}: {records} records in {format_duration(duration)}")
        return records, duration, "ok"
    except Exception as exc:
        duration = time.time() - start
        print(f"  -> {name}: FAILED after {format_duration(duration)} — {exc}")
        return 0, duration, f"error: {exc}"


def print_summary(results: list[tuple[str, int, float, str]]) -> None:
    """Print a summary table of all ingestion results."""
    print(f"\n{'=' * 60}")
    print("INGESTION SUMMARY")
    print(f"{'=' * 60}")
    print(f"  {'Source':<12} {'Records':>10} {'Duration':>10} {'Status'}")
    print(f"  {'-' * 12} {'-' * 10} {'-' * 10} {'-' * 20}")

    total_records = 0
    total_duration = 0.0
    failures = 0

    for name, records, duration, status in results:
        status_display = "ok" if status == "ok" else "FAILED"
        print(
            f"  {name:<12} {records:>10,} {format_duration(duration):>10} {status_display}"
        )
        total_records += records
        total_duration += duration
        if status != "ok":
            failures += 1

    print(f"  {'-' * 12} {'-' * 10} {'-' * 10} {'-' * 20}")
    print(
        f"  {'TOTAL':<12} {total_records:>10,} {format_duration(total_duration):>10} "
        f"{failures} failed"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run data ingestion scripts for D4BL.",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default=None,
        help="Comma-separated list of sources to run (default: all). "
        f"Available: {', '.join(SOURCES)}",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_sources",
        help="List available sources and exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would run without executing.",
    )
    parser.add_argument(
        "--year",
        type=str,
        default=None,
        help="Override data year for sources that support it "
        "(sets ACS_YEAR, CDC_PLACES_YEAR, etc.).",
    )
    args = parser.parse_args()

    # Forward --year to source-specific env vars
    if args.year:
        year_vars = [
            "ACS_YEAR", "CDC_PLACES_YEAR", "EPA_EJSCREEN_YEAR",
            "HUD_FMR_YEAR", "USDA_FOOD_ACCESS_YEAR",
            "CENSUS_DECENNIAL_YEAR", "BJS_YEAR",
        ]
        for var in year_vars:
            os.environ.setdefault(var, args.year)

    if args.list_sources:
        list_sources()
        return 0

    # Determine which sources to run.
    if args.sources:
        requested = [s.strip() for s in args.sources.split(",")]
        unknown = [s for s in requested if s not in SOURCES]
        if unknown:
            print(f"Unknown source(s): {', '.join(unknown)}", file=sys.stderr)
            print(f"Available: {', '.join(SOURCES)}", file=sys.stderr)
            return 1
        selected = [(s, SOURCES[s]) for s in requested]
    else:
        selected = list(SOURCES.items())

    if args.dry_run:
        print("Dry run — would execute the following sources:\n")
        for name, module_name in selected:
            print(f"  {name:<12} -> scripts/ingestion/{module_name}.py")
        return 0

    print(f"Running {len(selected)} ingestion source(s)...")

    results: list[tuple[str, int, float, str]] = []
    for name, module_name in selected:
        records, duration, status = run_source(name, module_name)
        results.append((name, records, duration, status))

    print_summary(results)

    has_failures = any(status != "ok" for _, _, _, status in results)
    return 1 if has_failures else 0


if __name__ == "__main__":
    sys.exit(main())
