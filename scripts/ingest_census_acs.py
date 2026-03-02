#!/usr/bin/env python
"""
Ingest Census ACS 5-year estimates into census_indicators table.

Usage:
    python scripts/ingest_census_acs.py [--year 2022] [--state 28] [--dry-run]

Env vars:
    CENSUS_API_KEY   (optional, higher rate limit)
    ACS_YEAR         (default: 2022)
    ACS_GEOGRAPHY    (default: state,county)
    POSTGRES_*       (connection settings, same as rest of app)
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

import aiohttp
from sqlalchemy.dialects.postgresql import insert

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import d4bl.infra.database as dbmod
from d4bl.infra.database import CensusIndicator


# Census ACS variable codes by metric and race
# B25003: Tenure (homeownership), B19013: Median HH income, B17001: Poverty
METRIC_VARS: dict[str, dict[str, object]] = {
    "homeownership_rate": {
        "total": ("B25003_001E", "B25003_002E"),  # total, owner-occupied
        "black": ("B25003B_001E", "B25003B_002E"),
        "white": ("B25003A_001E", "B25003A_002E"),
        "hispanic": ("B25003I_001E", "B25003I_002E"),
    },
    "median_household_income": {
        "total": "B19013_001E",
        "black": "B19013B_001E",
        "white": "B19013A_001E",
        "hispanic": "B19013I_001E",
    },
    "poverty_rate": {
        "total": ("B17001_001E", "B17001_002E"),  # total, below poverty
        "black": ("B17001B_001E", "B17001B_002E"),
        "white": ("B17001A_001E", "B17001A_002E"),
        "hispanic": ("B17001I_001E", "B17001I_002E"),
    },
}

CENSUS_BASE = "https://api.census.gov/data"


async def fetch_acs(
    session: aiohttp.ClientSession,
    year: int,
    vars: list[str],
    geography: str,
    api_key: Optional[str],
) -> list[dict]:
    """Fetch one ACS query. Returns list of dicts with variable values."""
    get_str = ",".join(["NAME"] + vars)
    url = f"{CENSUS_BASE}/{year}/acs/acs5"
    params: dict[str, str] = {"get": get_str, "for": geography}
    if api_key:
        params["key"] = api_key

    async with session.get(url, params=params) as resp:
        resp.raise_for_status()
        rows = await resp.json()

    headers = rows[0]
    return [dict(zip(headers, row)) for row in rows[1:]]


def compute_rate(numerator: str, denominator: str) -> Optional[float]:
    """Compute a ratio from two Census string values. Returns None if data unavailable."""
    try:
        num = float(numerator)
        den = float(denominator)
        if den <= 0:
            return None
        return round(num / den * 100, 2)
    except (TypeError, ValueError):
        return None


async def ingest_state_level(
    db_session,
    http_session: aiohttp.ClientSession,
    year: int,
    api_key: Optional[str],
    state_filter: Optional[str],
    dry_run: bool,
) -> int:
    """Ingest state-level indicators. Returns row count."""
    count = 0
    geography = "state:*" if not state_filter else f"state:{state_filter}"

    for metric, races in METRIC_VARS.items():
        for race, vars in races.items():
            try:
                # For rate metrics, vars is a tuple (denominator, numerator)
                if isinstance(vars, tuple):
                    rows = await fetch_acs(http_session, year, list(vars), geography, api_key)
                    for row in rows:
                        fips = row.get("state", "")
                        value = compute_rate(row.get(vars[1]), row.get(vars[0]))  # type: ignore[index]
                        if value is None:
                            continue
                        if not dry_run:
                            stmt = (
                                insert(CensusIndicator)
                                .values(
                                    fips_code=fips,
                                    geography_type="state",
                                    geography_name=row.get("NAME", ""),
                                    state_fips=fips,
                                    year=year,
                                    race=race,
                                    metric=metric,
                                    value=value,
                                )
                                .on_conflict_do_update(
                                    index_elements=["fips_code", "year", "race", "metric"],
                                    set={
                                        "geography_type": "state",
                                        "geography_name": row.get("NAME", ""),
                                        "state_fips": fips,
                                        "value": value,
                                    },
                                )
                            )
                            await db_session.execute(stmt)
                        count += 1
                else:
                    # Direct value metric (e.g. median income)
                    rows = await fetch_acs(http_session, year, [vars], geography, api_key)  # type: ignore[list-item]
                    for row in rows:
                        fips = row.get("state", "")
                        raw = row.get(vars)  # type: ignore[arg-type]
                        try:
                            value = float(raw)
                        except (TypeError, ValueError):
                            continue
                        if value < 0:
                            continue
                        if not dry_run:
                            stmt = (
                                insert(CensusIndicator)
                                .values(
                                    fips_code=fips,
                                    geography_type="state",
                                    geography_name=row.get("NAME", ""),
                                    state_fips=fips,
                                    year=year,
                                    race=race,
                                    metric=metric,
                                    value=value,
                                )
                                .on_conflict_do_update(
                                    index_elements=["fips_code", "year", "race", "metric"],
                                    set={
                                        "geography_type": "state",
                                        "geography_name": row.get("NAME", ""),
                                        "state_fips": fips,
                                        "value": value,
                                    },
                                )
                            )
                            await db_session.execute(stmt)
                        count += 1
            except Exception as e:  # pragma: no cover - defensive logging
                print(f"  Warning: {metric}/{race} fetch failed: {e}", file=sys.stderr)

    if not dry_run:
        await db_session.commit()

    return count


async def main(year: int, state_filter: Optional[str], dry_run: bool) -> None:
    dbmod.init_db()
    assert dbmod.async_session_maker is not None, "init_db() must set async_session_maker"
    if not dry_run:
        await dbmod.create_tables()

    api_key = os.getenv("CENSUS_API_KEY")

    print(f"Ingesting Census ACS {year} data (dry_run={dry_run})")

    async with dbmod.async_session_maker() as db:
        async with aiohttp.ClientSession() as http:
            count = await ingest_state_level(db, http, year, api_key, state_filter, dry_run)

    print(f"Done. {count} rows {'would be' if dry_run else ''} ingested.")
    await dbmod.close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Census ACS data")
    parser.add_argument(
        "--year",
        type=int,
        default=int(os.getenv("ACS_YEAR", "2022")),
        help="ACS survey year (e.g. 2022)",
    )
    parser.add_argument(
        "--state",
        default=None,
        help="2-digit FIPS code, e.g. 28 for Mississippi",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch but do not write to DB",
    )
    args = parser.parse_args()

    asyncio.run(main(args.year, args.state, args.dry_run))

