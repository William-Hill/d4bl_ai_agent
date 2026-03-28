"""FBI Crime Data Explorer (UCR) ingestion script.

Self-contained script that fetches arrest statistics by race and hate
crime incidents (disaggregated by bias motivation) from the FBI Crime
Data Explorer API. Requires an API key; skips gracefully when absent.

BIAS NOTE: FBI UCR data is voluntarily reported by law-enforcement agencies.
Significant underreporting exists, especially from smaller or under-resourced
departments, which can skew racial and geographic breakdowns.

Env vars:
    DATABASE_URL          - PostgreSQL connection URL (required)
    FBI_API_KEY           - FBI CDE API key (falls back to DATA_GOV_API_KEY)
"""

import os
import sys

import httpx

from .helpers import (
    STATE_ABBREV_TO_NAME,
    execute_batch,
    get_db_connection,
    make_record_id,
    safe_int,
)

# FBI Crime Data Explorer base URL
FBI_CDE_URL = "https://api.usa.gov/crime/fbi/cde"

# All 50 states + DC — alias to the shared helper dict
STATE_ABBREVS = STATE_ABBREV_TO_NAME

FBI_OFFENSES = [
    "aggravated-assault",
    "burglary",
    "larceny",
    "motor-vehicle-theft",
    "homicide",
    "robbery",
    "arson",
    "violent-crime",
    "property-crime",
]

# Year range for hate crime queries (API requires from/to in MM-YYYY format)
HATE_CRIME_START_YEAR = 2015
HATE_CRIME_END_YEAR = 2024

# Category constants
CAT_ARREST = "arrest"
CAT_HATE_CRIME = "hate_crime"
CAT_HATE_CRIME_CATEGORY = "hate_crime_category"

# Bias sections to ingest: (API response key, offense value, category value)
BIAS_SECTIONS = [
    ("bias", "hate-crime", CAT_HATE_CRIME),
    ("bias_category", "hate-crime-category", CAT_HATE_CRIME_CATEGORY),
]

UPSERT_SQL = """
    INSERT INTO fbi_crime_stats
        (id, state_abbrev, state_name,
         offense, race, bias_motivation,
         year, category, value)
    VALUES
        (%(id)s::UUID, %(state_abbrev)s, %(state_name)s,
         %(offense)s, %(race)s, %(bias_motivation)s,
         %(year)s, %(category)s, %(value)s)
    ON CONFLICT (state_abbrev, offense,
        COALESCE(race, ''), COALESCE(bias_motivation, ''),
        year, category)
    DO UPDATE SET
        value = EXCLUDED.value,
        state_name = EXCLUDED.state_name
"""

def main() -> int:
    """Run FBI UCR crime data ingestion.

    Returns total records ingested, or 0 if API key is missing.
    """
    api_key = os.environ.get("FBI_API_KEY") or os.environ.get("DATA_GOV_API_KEY")
    if not api_key:
        print(
            "FBI_API_KEY not set - skipping FBI UCR ingestion",
            file=sys.stderr,
        )
        return 0

    print(
        f"FBI UCR ingestion starting "
        f"({len(STATE_ABBREVS)} states, {len(FBI_OFFENSES)} offenses)"
    )

    conn = get_db_connection()
    client = httpx.Client()

    arrest_records = 0
    hate_crime_records = 0
    states_seen: set[str] = set()
    offenses_seen: set[str] = set()
    pending_batch: list[dict] = []

    def _flush_batch() -> int:
        """Flush pending_batch to DB, return count flushed."""
        nonlocal pending_batch
        if not pending_batch:
            return 0
        with conn.cursor() as cur:
            execute_batch(cur, UPSERT_SQL, pending_batch)
        conn.commit()
        flushed = len(pending_batch)
        pending_batch = []
        return flushed

    try:
        # --- Arrest data by race ---
        consecutive_errors = 0
        for state_abbr in STATE_ABBREVS:
            if consecutive_errors >= 5:
                print(
                    "  Skipping arrest data: API returned errors for "
                    "5 consecutive requests (endpoint may require "
                    "a different API key)"
                )
                break
            for offense in FBI_OFFENSES:
                url = (
                    f"{FBI_CDE_URL}/arrest/states/offense"
                    f"/{state_abbr}/{offense}/race"
                )
                params = {"API_KEY": api_key}
                try:
                    resp = client.get(url, params=params, timeout=60)
                    if resp.status_code in (403, 503):
                        consecutive_errors += 1
                        if consecutive_errors >= 5:
                            break
                        continue
                    if resp.status_code == 404:
                        continue
                    resp.raise_for_status()
                    payload = resp.json()
                    consecutive_errors = 0
                except httpx.HTTPStatusError as exc:
                    print(
                        f"  WARNING: FBI API error "
                        f"{state_abbr}/{offense}: {exc.response.status_code}"
                    )
                    continue
                except Exception as exc:
                    print(
                        f"  WARNING: FBI API request failed "
                        f"{state_abbr}/{offense}: {exc}"
                    )
                    continue

                # payload may be dict with "data" key or a list
                rows = payload
                if isinstance(payload, dict):
                    rows = payload.get("data", [])
                if not rows:
                    continue

                for row in rows:
                    race = row.get("race") or row.get("key")
                    if not race:
                        continue

                    year = row.get("data_year") or row.get("year")
                    value = safe_int(
                        row.get("value") or row.get("arrest_count", 0),
                        default=0,
                    )

                    if year is None:
                        continue

                    states_seen.add(state_abbr)
                    offenses_seen.add(offense)

                    pending_batch.append({
                        "id": make_record_id(
                            "fbi", state_abbr, offense,
                            race, str(year), CAT_ARREST,
                        ),
                        "state_abbrev": state_abbr,
                        "state_name": STATE_ABBREVS[state_abbr],
                        "offense": offense,
                        "race": race,
                        "bias_motivation": None,
                        "year": safe_int(year),
                        "category": CAT_ARREST,
                        "value": value,
                    })

                if len(pending_batch) >= 500:
                    arrest_records += _flush_batch()

                print(
                    f"  {state_abbr}/{offense}: "
                    f"{len(rows)} race rows"
                )

        # Flush remaining arrest records
        arrest_records += _flush_batch()

        # --- Hate crime data by state, per year, disaggregated by bias ---
        for state_abbr in STATE_ABBREVS:
            for year in range(HATE_CRIME_START_YEAR, HATE_CRIME_END_YEAR + 1):
                url = f"{FBI_CDE_URL}/hate-crime/state/{state_abbr}"
                params = {
                    "API_KEY": api_key,
                    "from": f"01-{year}",
                    "to": f"12-{year}",
                }
                try:
                    resp = client.get(url, params=params, timeout=60)
                    if resp.status_code == 404:
                        continue
                    resp.raise_for_status()
                    payload = resp.json()
                except httpx.HTTPStatusError as exc:
                    print(
                        f"  WARNING: FBI hate-crime API error "
                        f"{state_abbr}/{year}: {exc.response.status_code}"
                    )
                    continue
                except Exception as exc:
                    print(
                        f"  WARNING: FBI hate-crime request failed "
                        f"{state_abbr}/{year}: {exc}"
                    )
                    continue

                if not isinstance(payload, dict):
                    continue

                incident_section = payload.get("incident_section", {})
                row_count = 0

                for api_key_name, offense, category in BIAS_SECTIONS:
                    for label, count in incident_section.get(api_key_name, {}).items():
                        value = safe_int(count, default=0)
                        if value == 0:
                            continue

                        states_seen.add(state_abbr)
                        row_count += 1

                        pending_batch.append({
                            "id": make_record_id(
                                "fbi", state_abbr, offense,
                                label, str(year), category,
                            ),
                            "state_abbrev": state_abbr,
                            "state_name": STATE_ABBREVS[state_abbr],
                            "offense": offense,
                            "race": None,
                            "bias_motivation": label,
                            "year": year,
                            "category": category,
                            "value": value,
                        })

                if len(pending_batch) >= 500:
                    hate_crime_records += _flush_batch()

                if row_count > 0:
                    print(
                        f"  {state_abbr}/{year}: "
                        f"{row_count} bias rows"
                    )

        # Flush remaining hate crime records
        hate_crime_records += _flush_batch()

    finally:
        client.close()
        conn.close()

    total = arrest_records + hate_crime_records
    print(
        f"FBI UCR ingestion complete: {total} records "
        f"({arrest_records} arrests, {hate_crime_records} hate crimes) "
        f"across {len(states_seen)} states"
    )
    return total


if __name__ == "__main__":
    main()
