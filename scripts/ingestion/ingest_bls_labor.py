"""BLS Labor Statistics ingestion script.

Fetches unemployment rates and median weekly earnings by race from the
Bureau of Labor Statistics (BLS) Public Data API via POST requests.
API key is optional but recommended (25 req/day without vs 500 with).

Self-contained: uses psycopg2 + httpx only.
"""

import os

import httpx

from .helpers import (
    get_db_connection, execute_batch, make_record_id, safe_float, safe_int,
)

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

# Series ID -> metadata mapping
BLS_SERIES = {
    "LNS14000003": {"metric": "unemployment_rate", "race": "Black"},
    "LNS14000006": {"metric": "unemployment_rate", "race": "White"},
    "LNS14000009": {"metric": "unemployment_rate", "race": "Hispanic"},
    "LNS14000000": {"metric": "unemployment_rate", "race": "Total"},
    "LEU0252881500": {"metric": "median_weekly_earnings", "race": "Black"},
    "LEU0252883600": {"metric": "median_weekly_earnings", "race": "White"},
    "LEU0252884500": {"metric": "median_weekly_earnings", "race": "Hispanic"},
}

UPSERT_SQL = """
    INSERT INTO bls_labor_statistics
        (id, series_id, state_fips, state_name,
         metric, race, year, period, value,
         footnotes)
    VALUES
        (CAST(%(id)s AS UUID), %(series_id)s,
         %(state_fips)s, %(state_name)s,
         %(metric)s, %(race)s,
         %(year)s, %(period)s, %(value)s,
         %(footnotes)s)
    ON CONFLICT (series_id, year, period)
    DO UPDATE SET
        value = EXCLUDED.value,
        footnotes = EXCLUDED.footnotes,
        metric = EXCLUDED.metric,
        race = EXCLUDED.race
"""


def main() -> int:
    """Run BLS labor statistics ingestion.

    Returns total records ingested.
    """
    start_year = os.environ.get("BLS_START_YEAR", "2019")
    end_year = os.environ.get("BLS_END_YEAR", "2024")
    api_key = os.environ.get("BLS_API_KEY")

    if not api_key:
        print(
            "WARNING: BLS_API_KEY not set. Proceeding without authentication "
            "(lower rate limits: 25 requests/day vs 500)."
        )

    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    records_ingested = 0
    series_seen = set()
    series_ids = list(BLS_SERIES.keys())

    print(
        f"Fetching BLS data for {len(series_ids)} series, "
        f"years {start_year}-{end_year}"
    )

    try:
        with httpx.Client(timeout=60) as client:
            # BLS limits 50 series per request; we have <50 so one batch
            for i in range(0, len(series_ids), 50):
                batch_ids = series_ids[i : i + 50]

                payload = {
                    "seriesid": batch_ids,
                    "startyear": start_year,
                    "endyear": end_year,
                }
                if api_key:
                    payload["registrationkey"] = api_key

                resp = client.post(BLS_API_URL, json=payload)
                resp.raise_for_status()
                data = resp.json()

                if data.get("status") != "REQUEST_SUCCEEDED":
                    msg = data.get("message", ["Unknown error"])
                    print(f"ERROR: BLS API request failed: {msg}")
                    continue

                results = data.get("Results", {})
                series_list = results.get("series", [])

                batch = []
                for series in series_list:
                    sid = series.get("seriesID", "")
                    meta = BLS_SERIES.get(sid)
                    if not meta:
                        continue

                    series_seen.add(sid)

                    for obs in series.get("data", []):
                        raw_year = obs.get("year", "")
                        period = obs.get("period", "")
                        raw_value = obs.get("value", "")

                        year = safe_int(raw_year)
                        if year is None:
                            continue

                        value = safe_float(raw_value)
                        if value is None:
                            continue

                        footnote_list = obs.get("footnotes", [])
                        footnotes = ", ".join(
                            fn.get("text", "")
                            for fn in footnote_list
                            if fn.get("text")
                        ) or None

                        batch.append({
                            "id": make_record_id(
                                "bls", sid, str(year), period,
                            ),
                            "series_id": sid,
                            "state_fips": None,
                            "state_name": None,
                            "metric": meta["metric"],
                            "race": meta["race"],
                            "year": year,
                            "period": period,
                            "value": value,
                            "footnotes": footnotes,
                        })

                if batch:
                    execute_batch(cur, UPSERT_SQL, batch)
                    conn.commit()
                    records_ingested += len(batch)

                print(
                    f"  Batch {i // 50 + 1}: processed "
                    f"{len(series_list)} series"
                )
    finally:
        cur.close()
        conn.close()

    print(
        f"Ingested {records_ingested} BLS labor statistics records "
        f"across {len(series_seen)} series"
    )
    print(f"Series covered: {sorted(series_seen)}")
    return records_ingested


if __name__ == "__main__":
    main()
