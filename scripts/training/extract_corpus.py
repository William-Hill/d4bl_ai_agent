"""Corpus extraction: pull structured rows from the DB and render as JSONL passages."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from scripts.training.config import (
    CORPUS_BATCH_SIZE,
    CORPUS_DIR,
    MAX_PASSAGES_PER_TABLE,
    write_jsonl,
)
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
            "SELECT geography_name, fips_code, measure, category, "
            "data_value, data_value_type, low_confidence_limit, "
            "high_confidence_limit, total_population, year "
            "FROM cdc_health_outcomes "
            "ORDER BY random() LIMIT %(limit)s"
        ),
        "template": render_cdc_passage,
    },
    "epa_environmental_justice": {
        "query": (
            "SELECT state_name, tract_fips, indicator, raw_value, "
            "percentile_state, percentile_national, population, "
            "minority_pct, low_income_pct, year "
            "FROM epa_environmental_justice "
            "ORDER BY random() LIMIT %(limit)s"
        ),
        "template": render_epa_passage,
    },
    "police_violence_incidents": {
        "query": (
            "SELECT state, city, race, age, gender, "
            "armed_status, cause_of_death, year, agency "
            "FROM police_violence_incidents "
            "ORDER BY random() LIMIT %(limit)s"
        ),
        "template": render_police_violence_passage,
    },
    "bjs_incarceration": {
        "query": (
            "SELECT state_name, state_abbrev, facility_type, "
            "metric, race, gender, value, year "
            "FROM bjs_incarceration "
            "ORDER BY random() LIMIT %(limit)s"
        ),
        "template": render_bjs_passage,
    },
    "fbi_crime_stats": {
        "query": (
            "SELECT state_name, offense, category, "
            "COALESCE(race, bias_motivation, 'unknown') AS race, "
            "value, COALESCE(population, 0) AS population, year "
            "FROM fbi_crime_stats "
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
    def _to_text_obj(p: str):
        if not p or not p.strip():
            return None
        return {"text": p.strip()}

    return write_jsonl(passages, outfile, transform=_to_text_obj)


def extract_table(conn: Any, table: str, max_rows: int) -> list[str]:
    """Fetch rows from *table* and convert them to natural-language passages.

    Uses ``CORPUS_BATCH_SIZE`` for ``fetchmany`` batching. Returns a list of
    rendered passage strings.
    """
    extractor = EXTRACTORS[table]
    query = extractor["query"]
    template = extractor["template"]

    import psycopg2.extras  # lazy import — not available in CI test env

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
    target_tables = [t for t in tables if t in EXTRACTORS]
    skipped = [t for t in tables if t not in EXTRACTORS]
    for t in skipped:
        logger.warning("Unknown table %r — skipping.", t)

    from scripts.ingestion.helpers import get_db_connection

    conn = get_db_connection()
    try:
        for table in target_tables:
            logger.info("Extracting %s (max %d rows)…", table, max_per_table)
            passages = extract_table(conn, table, max_per_table)
            outfile = CORPUS_DIR / f"{table}.jsonl"
            count = write_passages_jsonl(passages, outfile)
            logger.info("  Wrote %d passages → %s", count, outfile)
    finally:
        conn.close()

    # Build combined corpus by streaming per-table files from disk
    combined_file = CORPUS_DIR / "corpus_pretrain.jsonl"
    total = 0
    with combined_file.open("w", encoding="utf-8") as out:
        for table in target_tables:
            table_file = CORPUS_DIR / f"{table}.jsonl"
            if table_file.exists():
                with table_file.open(encoding="utf-8") as f:
                    for line in f:
                        out.write(line)
                        total += 1
    logger.info("Combined corpus: %d passages → %s", total, combined_file)


def _positive_int(value: str) -> int:
    ivalue = int(value)
    if ivalue <= 0:
        msg = f"must be a positive integer, got {value}"
        raise argparse.ArgumentTypeError(msg)
    return ivalue


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
        type=_positive_int,
        default=MAX_PASSAGES_PER_TABLE,
        help=f"Maximum rows per table (default: {MAX_PASSAGES_PER_TABLE}).",
    )
    args = parser.parse_args()

    selected_tables = [t.strip() for t in args.tables.split(",") if t.strip()] or None
    main(tables=selected_tables, max_per_table=args.max_per_table)
