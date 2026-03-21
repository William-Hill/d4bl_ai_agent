"""Corpus extraction: pull structured rows from the DB and render as JSONL passages."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

from scripts.ingestion.helpers import get_db_connection
from scripts.training.config import CORPUS_BATCH_SIZE, CORPUS_DIR, MAX_PASSAGES_PER_TABLE
from scripts.training.templates import (
    render_bjs_passage,
    render_cdc_passage,
    render_census_passage,
    render_epa_passage,
    render_fbi_passage,
    render_police_violence_passage,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extractor registry
# ---------------------------------------------------------------------------

EXTRACTORS: dict[str, dict[str, Any]] = {
    "census_indicators": {
        "query": (
            "SELECT geography_name, fips_code, race, metric, value, "
            "margin_of_error, year "
            "FROM census_indicators "
            "ORDER BY random() LIMIT %(limit)s"
        ),
        "template": render_census_passage,
    },
    "cdc_health_outcomes": {
        "query": (
            "SELECT geography_name, measure, value, ci_low, ci_high, year "
            "FROM cdc_health_outcomes "
            "ORDER BY random() LIMIT %(limit)s"
        ),
        "template": render_cdc_passage,
    },
    "epa_environmental_justice": {
        "query": (
            "SELECT state_fips, indicator, raw_value, percentile, "
            "state_percentile, minority_pct, year "
            "FROM epa_environmental_justice "
            "ORDER BY random() LIMIT %(limit)s"
        ),
        "template": render_epa_passage,
    },
    "police_violence_incidents": {
        "query": (
            "SELECT city, state, victim_race, armed_status, year "
            "FROM police_violence_incidents "
            "ORDER BY random() LIMIT %(limit)s"
        ),
        "template": render_police_violence_passage,
    },
    "bjs_incarceration": {
        "query": (
            "SELECT state_fips, race, value, facility_type, year "
            "FROM bjs_incarceration "
            "ORDER BY random() LIMIT %(limit)s"
        ),
        "template": render_bjs_passage,
    },
    "fbi_crime_stats": {
        "query": (
            "SELECT state_fips, offense, category, race, count, population, year "
            "FROM fbi_crime_stats "
            "WHERE race IS NOT NULL "
            "ORDER BY random() LIMIT %(limit)s"
        ),
        "template": render_fbi_passage,
    },
}


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def write_passages_jsonl(passages: list[str], outfile: Path) -> int:
    """Write non-empty passages as ``{"text": "..."}`` JSONL lines.

    Creates parent directories as needed. Returns the count of written lines.
    """
    outfile.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with outfile.open("w", encoding="utf-8") as fh:
        for passage in passages:
            if not passage or not passage.strip():
                continue
            fh.write(json.dumps({"text": passage}, ensure_ascii=False) + "\n")
            count += 1
    return count


def extract_table(conn: Any, table: str, max_rows: int) -> list[str]:
    """Fetch rows from *table* and convert them to natural-language passages.

    Uses ``CORPUS_BATCH_SIZE`` for ``fetchmany`` batching. Returns a list of
    rendered passage strings.
    """
    extractor = EXTRACTORS[table]
    query = extractor["query"]
    template = extractor["template"]

    passages: list[str] = []
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, {"limit": max_rows})
        while True:
            rows = cur.fetchmany(CORPUS_BATCH_SIZE)
            if not rows:
                break
            for row in rows:
                try:
                    passage = template(dict(row))
                    if passage and passage.strip():
                        passages.append(passage)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to render row from %s: %s", table, exc)
    return passages


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(tables: list[str] | None = None, max_per_table: int = MAX_PASSAGES_PER_TABLE) -> None:
    """Extract passages from all (or selected) tables and write JSONL files.

    Writes one JSONL per table under ``CORPUS_DIR`` and a combined
    ``corpus_pretrain.jsonl``.
    """
    if tables is None:
        tables = list(EXTRACTORS.keys())

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    combined: list[str] = []

    conn = get_db_connection()
    try:
        for table in tables:
            if table not in EXTRACTORS:
                logger.warning("Unknown table %r — skipping.", table)
                continue
            logger.info("Extracting %s (max %d rows)…", table, max_per_table)
            passages = extract_table(conn, table, max_per_table)
            outfile = CORPUS_DIR / f"{table}.jsonl"
            count = write_passages_jsonl(passages, outfile)
            logger.info("  Wrote %d passages → %s", count, outfile)
            combined.extend(passages)
    finally:
        conn.close()

    combined_file = CORPUS_DIR / "corpus_pretrain.jsonl"
    total = write_passages_jsonl(combined, combined_file)
    logger.info("Combined corpus: %d passages → %s", total, combined_file)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Extract training corpus from the database.")
    parser.add_argument(
        "--tables",
        default="",
        help="Comma-separated list of tables to extract (default: all).",
    )
    parser.add_argument(
        "--max-per-table",
        type=int,
        default=MAX_PASSAGES_PER_TABLE,
        help=f"Maximum rows per table (default: {MAX_PASSAGES_PER_TABLE}).",
    )
    args = parser.parse_args()

    selected_tables = [t.strip() for t in args.tables.split(",") if t.strip()] or None
    main(tables=selected_tables, max_per_table=args.max_per_table)
