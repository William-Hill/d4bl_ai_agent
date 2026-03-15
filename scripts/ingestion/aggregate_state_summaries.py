#!/usr/bin/env python3
"""Aggregate tract/district-level data into state-level summaries.

Populates the ``state_summary`` table so explore-page endpoints can query
pre-computed state averages instead of aggregating on the fly.
"""

from __future__ import annotations

import logging
import os
import sys
from collections import defaultdict
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Ensure src/ is importable
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SRC_DIR = os.path.join(_REPO_ROOT, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from d4bl.infra.database import get_database_url  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Source-specific SQL queries
# ---------------------------------------------------------------------------

_QUERIES: dict[str, str] = {
    "epa": (
        "SELECT state_fips, state_name, indicator, year, raw_value, population "
        "FROM epa_environmental_justice "
        "WHERE population IS NOT NULL AND raw_value IS NOT NULL"
    ),
    "usda": (
        "SELECT state_fips, state_name, indicator, year, value, population "
        "FROM usda_food_access "
        "WHERE population IS NOT NULL AND value IS NOT NULL"
    ),
    "census-demographics": (
        "SELECT state_fips, state_name, race, year, population "
        "FROM census_demographics "
        "WHERE geo_type = 'tract' AND population IS NOT NULL"
    ),
    "doe": (
        "SELECT state, state_name, metric, race, school_year, value, "
        "total_enrollment "
        "FROM doe_civil_rights "
        "WHERE total_enrollment IS NOT NULL AND value IS NOT NULL"
    ),
}

# Map run_ingestion source names to aggregation source keys
_SOURCE_NAME_MAP: dict[str, str] = {
    "epa": "epa",
    "usda": "usda",
    "census_decennial": "census-demographics",
    "doe": "doe",
}


def _fetch_query(source: str) -> str:
    """Return the raw SQL for fetching tract/district data for *source*."""
    if source not in _QUERIES:
        raise ValueError(f"Unknown aggregation source: {source}")
    return _QUERIES[source]


def _get_sync_session() -> Session:
    """Create a synchronous SQLAlchemy session for ingestion use."""
    url = get_database_url().replace("+asyncpg", "")
    engine = create_engine(url)
    factory = sessionmaker(bind=engine)
    return factory()


# ---------------------------------------------------------------------------
# Per-source aggregation functions
# ---------------------------------------------------------------------------


def aggregate_epa(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Population-weighted average of EPA tract indicators per state."""
    # Key: (state_fips, indicator, year)
    buckets: dict[tuple, dict] = defaultdict(
        lambda: {"weighted_sum": 0.0, "total_pop": 0, "state_name": ""}
    )
    for r in rows:
        key = (r["state_fips"], r["indicator"], r["year"])
        pop = r["population"]
        buckets[key]["weighted_sum"] += r["raw_value"] * pop
        buckets[key]["total_pop"] += pop
        buckets[key]["state_name"] = r["state_name"]

    results = []
    for (state_fips, indicator, year), b in buckets.items():
        if b["total_pop"] == 0:
            continue
        results.append(
            {
                "source": "epa",
                "state_fips": state_fips,
                "state_name": b["state_name"],
                "metric": indicator,
                "race": "total",
                "year": year,
                "value": b["weighted_sum"] / b["total_pop"],
                "sample_size": b["total_pop"],
            }
        )
    return results


def aggregate_usda(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Population-weighted average of USDA tract indicators per state."""
    buckets: dict[tuple, dict] = defaultdict(
        lambda: {"weighted_sum": 0.0, "total_pop": 0, "state_name": ""}
    )
    for r in rows:
        key = (r["state_fips"], r["indicator"], r["year"])
        pop = r["population"]
        buckets[key]["weighted_sum"] += r["value"] * pop
        buckets[key]["total_pop"] += pop
        buckets[key]["state_name"] = r["state_name"]

    results = []
    for (state_fips, indicator, year), b in buckets.items():
        if b["total_pop"] == 0:
            continue
        results.append(
            {
                "source": "usda",
                "state_fips": state_fips,
                "state_name": b["state_name"],
                "metric": indicator,
                "race": "total",
                "year": year,
                "value": b["weighted_sum"] / b["total_pop"],
                "sample_size": b["total_pop"],
            }
        )
    return results


def aggregate_census_demographics(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sum tract populations per state/race/year."""
    # Key: (state_fips, race, year)
    buckets: dict[tuple, dict] = defaultdict(
        lambda: {"total_pop": 0, "state_name": ""}
    )
    for r in rows:
        key = (r["state_fips"], r["race"], r["year"])
        buckets[key]["total_pop"] += r["population"]
        buckets[key]["state_name"] = r["state_name"]

    # Derive sample_size from state total population (race="total" sum)
    state_totals: dict[tuple, int] = {}  # (state_fips, year) -> total
    for (state_fips, race, year), b in buckets.items():
        if race == "total":
            state_totals[(state_fips, year)] = b["total_pop"]

    results = []
    for (state_fips, race, year), b in buckets.items():
        results.append(
            {
                "source": "census-demographics",
                "state_fips": state_fips,
                "state_name": b["state_name"],
                "metric": "population",
                "race": race,
                "year": year,
                "value": float(b["total_pop"]),
                "sample_size": state_totals.get(
                    (state_fips, year), b["total_pop"]
                ),
            }
        )
    return results


def aggregate_doe(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Enrollment-weighted average of DOE district metrics per state."""
    buckets: dict[tuple, dict] = defaultdict(
        lambda: {
            "weighted_sum": 0.0,
            "total_enrollment": 0,
            "state_name": "",
        }
    )
    for r in rows:
        # school_year is like "2020-2021" — extract start year
        year = int(r["school_year"].split("-")[0])
        key = (r["state"], r["metric"], r["race"], year)
        enrollment = r["total_enrollment"]
        buckets[key]["weighted_sum"] += r["value"] * enrollment
        buckets[key]["total_enrollment"] += enrollment
        buckets[key]["state_name"] = r["state_name"]

    results = []
    for (state, metric, race, year), b in buckets.items():
        if b["total_enrollment"] == 0:
            continue
        results.append(
            {
                "source": "doe",
                "state_fips": state,
                "state_name": b["state_name"],
                "metric": metric,
                "race": race,
                "year": year,
                "value": b["weighted_sum"] / b["total_enrollment"],
                "sample_size": b["total_enrollment"],
            }
        )
    return results


_AGGREGATORS: dict[str, Any] = {
    "epa": aggregate_epa,
    "usda": aggregate_usda,
    "census-demographics": aggregate_census_demographics,
    "doe": aggregate_doe,
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_aggregation(sources: list[str]) -> None:
    """Aggregate tract/district data to state summaries.

    Parameters
    ----------
    sources:
        List of source names as used by ``run_ingestion.py``
        (e.g. ``["epa", "census_decennial"]``).
    """
    session = _get_sync_session()
    try:
        for name in sources:
            agg_key = _SOURCE_NAME_MAP.get(name, name)
            if agg_key not in _AGGREGATORS:
                logger.warning(
                    "No aggregation function for source %r, skipping", name
                )
                continue

            logger.info("Aggregating state summaries for %s", agg_key)
            query = _fetch_query(agg_key)
            result = session.execute(text(query))
            rows = [dict(r._mapping) for r in result]

            if not rows:
                logger.info("No rows for %s, skipping", agg_key)
                continue

            summaries = _AGGREGATORS[agg_key](rows)
            logger.info(
                "%s: %d summary rows from %d raw rows",
                agg_key,
                len(summaries),
                len(rows),
            )

            # Delete existing summaries for this source and re-insert
            session.execute(
                text("DELETE FROM state_summary WHERE source = :src"),
                {"src": agg_key},
            )

            for s in summaries:
                session.execute(
                    text(
                        "INSERT INTO state_summary "
                        "(source, state_fips, state_name, metric, race, "
                        "year, value, sample_size) "
                        "VALUES (:source, :state_fips, :state_name, "
                        ":metric, :race, :year, :value, :sample_size)"
                    ),
                    s,
                )

            session.commit()
            logger.info("Committed %d summaries for %s", len(summaries), agg_key)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
