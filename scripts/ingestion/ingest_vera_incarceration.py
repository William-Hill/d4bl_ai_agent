"""Ingest Vera Institute incarceration trends data.

Downloads county-level jail/prison population by race from the
vera-institute/incarceration-trends GitHub repository.

Source: https://github.com/vera-institute/incarceration-trends
"""

from __future__ import annotations

import csv
import io
import json
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
)

DATA_URL = (
    "https://raw.githubusercontent.com/vera-institute/incarceration-trends/"
    "master/incarceration_trends.csv"
)

RACE_COLUMNS = [
    "black_jail_pop",
    "white_jail_pop",
    "latinx_jail_pop",
    "aapi_jail_pop",
    "native_jail_pop",
    "other_race_jail_pop",
    "black_prison_pop",
    "white_prison_pop",
    "latinx_prison_pop",
    "aapi_prison_pop",
    "native_prison_pop",
    "other_race_prison_pop",
    "total_jail_pop",
    "total_prison_pop",
    "total_pop",
    "black_pop_15to64",
    "white_pop_15to64",
    "latinx_pop_15to64",
]

UPSERT_SQL = """
    INSERT INTO ingested_records
        (id, source_type, source_key, external_id, title, url, content,
         metadata, ingested_at)
    VALUES
        (CAST(%(id)s AS UUID), %(source_type)s, %(source_key)s, %(external_id)s,
         %(title)s, %(url)s, %(content)s,
         CAST(%(metadata)s AS JSONB), %(ingested_at)s)
    ON CONFLICT (source_type, external_id)
    DO UPDATE SET
        content = EXCLUDED.content,
        metadata = EXCLUDED.metadata,
        ingested_at = EXCLUDED.ingested_at
"""


def main() -> int:
    """Download and ingest Vera incarceration trends data."""
    conn = get_db_connection()
    conn.autocommit = False

    records_ingested = 0
    now = datetime.now(timezone.utc).isoformat()

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
            year = row.get("year", "").strip()
            county = row.get("county_name", "").strip()
            state = row.get("state", "").strip()

            if not fips or not year:
                continue

            measures = {}
            for col in RACE_COLUMNS:
                val = safe_float(row.get(col))
                if val is not None:
                    measures[col] = val

            if not measures:
                continue

            record_id = make_record_id("vera", year, fips)
            batch.append({
                "id": str(record_id),
                "source_type": "vera_incarceration",
                "source_key": "vera",
                "external_id": f"vera-{year}-{fips}",
                "title": f"{county}, {state} - Incarceration Trends {year}",
                "url": "https://github.com/vera-institute/incarceration-trends",
                "content": json.dumps(measures),
                "metadata": json.dumps({
                    "fips": fips,
                    "county": county,
                    "state": state,
                    "year": year,
                    "urbanicity": row.get("urbanicity", ""),
                    "region": row.get("region", ""),
                }),
                "ingested_at": now,
            })

            if len(batch) >= 1000:
                count = upsert_batch(conn, UPSERT_SQL, batch)
                records_ingested += count
                batch = []

        if batch:
            count = upsert_batch(conn, UPSERT_SQL, batch)
            records_ingested += count

    conn.close()
    print(f"Vera Incarceration: {records_ingested} county-year records ingested")
    return records_ingested


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
