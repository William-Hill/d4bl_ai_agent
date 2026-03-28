"""Ingest County Health Rankings data.

Downloads annual CSV from countyhealthrankings.org with 30+ health
measures per county. FIPS-coded.

Source: https://www.countyhealthrankings.org/
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

YEAR = os.environ.get("CHR_YEAR", "2025")

DATA_URL = (
    f"https://www.countyhealthrankings.org/sites/default/files/media/document/"
    f"{YEAR}%20County%20Health%20Rankings%20Data%20-%20v2.csv"
)

ANALYTIC_URL = (
    "https://www.countyhealthrankings.org/sites/default/files/media/document/"
    f"analytic_data{YEAR}.csv"
)

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
    """Download and ingest County Health Rankings data."""
    conn = get_db_connection()
    conn.autocommit = False

    records_ingested = 0
    now = datetime.now(timezone.utc).isoformat()

    with httpx.Client(timeout=120, follow_redirects=True) as client:
        print(f"Downloading County Health Rankings data for {YEAR}...")
        response = client.get(DATA_URL)

        if response.status_code != 200:
            print(f"Primary URL returned {response.status_code}, trying analytic URL...")
            response = client.get(ANALYTIC_URL)
            if response.status_code != 200:
                print(f"Failed to download data: HTTP {response.status_code}")
                return 0

        reader = csv.DictReader(io.StringIO(response.text))
        batch = []

        for row in reader:
            fips = row.get("FIPS", row.get("fipscode", "")).strip()
            county = row.get("County", row.get("county", "")).strip()
            state = row.get("State", row.get("state", "")).strip()

            if not fips or len(fips) < 5:
                continue

            record_id = make_record_id("county_health_rankings", YEAR, fips)

            measures = {}
            for key, value in row.items():
                if value and key not in ("FIPS", "fipscode", "County", "county", "State", "state"):
                    float_val = safe_float(value)
                    if float_val is not None:
                        measures[key] = float_val

            batch.append({
                "id": str(record_id),
                "source_type": "county_health_rankings",
                "source_key": "chr",
                "external_id": f"chr-{YEAR}-{fips}",
                "title": f"{county}, {state} - County Health Rankings {YEAR}",
                "url": "https://www.countyhealthrankings.org/explore-health-rankings/county-health-rankings-model",
                "content": json.dumps(measures),
                "metadata": json.dumps({
                    "fips": fips,
                    "county": county,
                    "state": state,
                    "year": YEAR,
                    "measure_count": len(measures),
                }),
                "ingested_at": now,
            })

            if len(batch) >= 500:
                count = upsert_batch(conn, UPSERT_SQL, batch)
                records_ingested += count
                batch = []

        if batch:
            count = upsert_batch(conn, UPSERT_SQL, batch)
            records_ingested += count

    conn.close()
    print(f"County Health Rankings: {records_ingested} county records ingested")
    return records_ingested


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
