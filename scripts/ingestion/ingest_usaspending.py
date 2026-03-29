"""Ingest federal spending data from USASpending.gov.

Queries spending by county using the free REST API (no key required).

Source: https://api.usaspending.gov/
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import httpx

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from ingestion.helpers import (
    STATE_FIPS,
    get_db_connection,
    make_record_id,
    safe_float,
    upsert_batch,
)

FISCAL_YEAR = os.environ.get("USASPENDING_YEAR", "2025")

API_BASE = "https://api.usaspending.gov/api/v2"

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


def fetch_state_spending(client: httpx.Client, state_fips: str) -> list[dict]:
    """Fetch county-level spending for a state."""
    url = f"{API_BASE}/search/spending_by_geography/"
    payload = {
        "scope": "place_of_performance",
        "geo_layer": "county",
        "geo_layer_filters": [state_fips],
        "filters": {
            "time_period": [
                {"start_date": f"{int(FISCAL_YEAR)-1}-10-01", "end_date": f"{FISCAL_YEAR}-09-30"}
            ]
        },
    }

    response = client.post(url, json=payload)
    if response.status_code != 200:
        return []

    data = response.json()
    return data.get("results", [])


def main() -> int:
    """Fetch and ingest USASpending data by county."""
    conn = get_db_connection()
    conn.autocommit = False

    records_ingested = 0
    now = datetime.now(timezone.utc).isoformat()

    with httpx.Client(timeout=60) as client:
        for state_fips, state_name in STATE_FIPS.items():
            print(f"  Fetching spending for {state_name} ({state_fips})...")
            results = fetch_state_spending(client, state_fips)

            batch = []
            for result in results:
                county_fips = result.get("shape_code", "")
                if not county_fips:
                    continue

                full_fips = f"{state_fips}{county_fips}"
                amount = safe_float(result.get("aggregated_amount"))
                per_capita = safe_float(result.get("per_capita"))

                record_id = make_record_id("usaspending", FISCAL_YEAR, full_fips)
                batch.append({
                    "id": str(record_id),
                    "source_type": "usaspending",
                    "source_key": "usaspending",
                    "external_id": f"usa-{FISCAL_YEAR}-{full_fips}",
                    "title": f"{result.get('display_name', county_fips)} - Federal Spending FY{FISCAL_YEAR}",
                    "url": f"https://www.usaspending.gov/search/?hash=county-{full_fips}",
                    "content": json.dumps({
                        "total_spending": amount,
                        "per_capita": per_capita,
                        "population": result.get("population"),
                    }),
                    "metadata": json.dumps({
                        "fips": full_fips,
                        "state_fips": state_fips,
                        "county_name": result.get("display_name"),
                        "fiscal_year": FISCAL_YEAR,
                    }),
                    "ingested_at": now,
                })

            if batch:
                count = upsert_batch(conn, UPSERT_SQL, batch)
                records_ingested += count

    conn.close()
    print(f"USASpending: {records_ingested} county records ingested for FY{FISCAL_YEAR}")
    return records_ingested


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)