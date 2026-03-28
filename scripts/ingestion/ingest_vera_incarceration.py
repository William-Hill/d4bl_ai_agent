"""Ingest Vera Institute incarceration trends data.

Downloads county-level jail/prison population by race from the
vera-institute/incarceration-trends GitHub repository.

Source: https://github.com/vera-institute/incarceration-trends
"""

from __future__ import annotations

import csv
import io
import os
import sys
from datetime import datetime, timezone

import httpx

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from ingestion.helpers import (
    get_db_connection,
    upsert_batch,
    make_record_id,
    safe_float,
    safe_int,
)

DATA_URL = (
    "https://raw.githubusercontent.com/vera-institute/incarceration-trends/"
    "main/incarceration_trends_county.csv"
)

# Map CSV columns to (race, facility_type) pairs for pivoting wide → long
RACE_FACILITY_MAP = {
    "black_jail_pop": ("black", "jail"),
    "white_jail_pop": ("white", "jail"),
    "latinx_jail_pop": ("latinx", "jail"),
    "aapi_jail_pop": ("aapi", "jail"),
    "native_jail_pop": ("native", "jail"),
    "other_race_jail_pop": ("other", "jail"),
    "black_prison_pop": ("black", "prison"),
    "white_prison_pop": ("white", "prison"),
    "latinx_prison_pop": ("latinx", "prison"),
    "aapi_prison_pop": ("aapi", "prison"),
    "native_prison_pop": ("native", "prison"),
    "other_race_prison_pop": ("other", "prison"),
    "total_jail_pop": ("total", "jail"),
    "total_prison_pop": ("total", "prison"),
}

UPSERT_SQL = """
    INSERT INTO vera_incarceration
        (id, fips, state, county_name, year, urbanicity, facility_type,
         race, population, total_pop, rate_per_100k)
    VALUES
        (CAST(%(id)s AS UUID), %(fips)s, %(state)s, %(county_name)s,
         %(year)s, %(urbanicity)s, %(facility_type)s,
         %(race)s, %(population)s, %(total_pop)s, %(rate_per_100k)s)
    ON CONFLICT (id)
    DO UPDATE SET
        population = EXCLUDED.population,
        total_pop = EXCLUDED.total_pop,
        rate_per_100k = EXCLUDED.rate_per_100k
"""


def main() -> int:
    """Download and ingest Vera incarceration trends data."""
    conn = get_db_connection()
    conn.autocommit = False

    records_ingested = 0

    with httpx.Client(timeout=120, follow_redirects=True) as client:
        print("Downloading Vera Institute incarceration trends CSV...")
        response = client.get(DATA_URL)

        if response.status_code != 200:
            print(f"Failed to download: HTTP {response.status_code}")
            conn.close()
            return 0

        reader = csv.DictReader(io.StringIO(response.text))
        batch = []

        for row in reader:
            fips = row.get("fips", "").strip()
            year_str = row.get("year", "").strip()
            county = row.get("county_name", "").strip()
            state = row.get("state", "").strip()
            urbanicity = row.get("urbanicity", "").strip()

            if not fips or not year_str:
                continue

            year = safe_int(year_str)
            if year is None:
                continue

            total_pop = safe_int(row.get("total_pop"))

            # Pivot wide columns into one row per race/facility_type
            for col, (race, facility_type) in RACE_FACILITY_MAP.items():
                population = safe_int(safe_float(row.get(col)))
                if population is None or population == 0:
                    continue

                # Compute rate per 100k if we have total_pop
                rate = None
                if total_pop and total_pop > 0:
                    rate = round(population / total_pop * 100_000, 2)

                record_id = make_record_id(
                    "vera", str(year), fips, race, facility_type
                )
                batch.append({
                    "id": str(record_id),
                    "fips": fips,
                    "state": state,
                    "county_name": county,
                    "year": year,
                    "urbanicity": urbanicity,
                    "facility_type": facility_type,
                    "race": race,
                    "population": population,
                    "total_pop": total_pop,
                    "rate_per_100k": rate,
                })

            if len(batch) >= 1000:
                count = upsert_batch(conn, UPSERT_SQL, batch)
                records_ingested += count
                batch = []

        if batch:
            count = upsert_batch(conn, UPSERT_SQL, batch)
            records_ingested += count

    conn.close()
    print(f"Vera Incarceration: {records_ingested} records ingested")
    return records_ingested


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
