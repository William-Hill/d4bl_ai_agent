"""FBI Crime Data Explorer (UCR) ingestion script.

Self-contained script that fetches arrest statistics by race and hate
crime incidents from the FBI Crime Data Explorer API. Requires an
FBI_API_KEY; skips gracefully when the key is absent.

BIAS NOTE: FBI UCR data is voluntarily reported by law-enforcement agencies.
Significant underreporting exists, especially from smaller or under-resourced
departments, which can skew racial and geographic breakdowns.

Env vars:
    DAGSTER_POSTGRES_URL  - PostgreSQL connection URL (required)
    FBI_API_KEY           - FBI CDE API key (optional, skips if missing)
"""

import os
import sys

import httpx

from scripts.ingestion.helpers import (
    get_db_connection, execute_batch, make_record_id, safe_int,
)

# FBI Crime Data Explorer base URL
FBI_CDE_URL = "https://api.usa.gov/crime/fbi/cde"

# All 50 states + DC
STATE_ABBREVS = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}

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

UPSERT_SQL = """
    INSERT INTO fbi_crime_stats
        (id, state_abbrev, state_name,
         offense, race, year, category,
         value)
    VALUES
        (%(id)s::UUID,
         %(state_abbrev)s, %(state_name)s,
         %(offense)s, %(race)s, %(year)s,
         %(category)s, %(value)s)
    ON CONFLICT
        (state_abbrev, offense, race,
         year, category)
    DO UPDATE SET
        value = EXCLUDED.value,
        state_name = EXCLUDED.state_name
"""

def main() -> int:
    """Run FBI UCR crime data ingestion.

    Returns total records ingested, or 0 if API key is missing.
    """
    api_key = os.environ.get("FBI_API_KEY")
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
        for state_abbr in STATE_ABBREVS:
            for offense in FBI_OFFENSES:
                url = (
                    f"{FBI_CDE_URL}/arrest/states/offense"
                    f"/{state_abbr}/{offense}/race"
                )
                params = {"API_KEY": api_key}
                try:
                    resp = client.get(url, params=params, timeout=60)
                    if resp.status_code == 404:
                        continue
                    resp.raise_for_status()
                    payload = resp.json()
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
                            race, str(year), "arrest",
                        ),
                        "state_abbrev": state_abbr,
                        "state_name": STATE_ABBREVS[state_abbr],
                        "offense": offense,
                        "race": race,
                        "year": int(year),
                        "category": "arrest",
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

        # --- Hate crime data by state ---
        for state_abbr in STATE_ABBREVS:
            url = f"{FBI_CDE_URL}/hate-crime/state/{state_abbr}"
            params = {"API_KEY": api_key}
            try:
                resp = client.get(url, params=params, timeout=60)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                payload = resp.json()
            except httpx.HTTPStatusError as exc:
                print(
                    f"  WARNING: FBI hate-crime API error "
                    f"{state_abbr}: {exc.response.status_code}"
                )
                continue
            except Exception as exc:
                print(
                    f"  WARNING: FBI hate-crime request failed "
                    f"{state_abbr}: {exc}"
                )
                continue

            rows = payload
            if isinstance(payload, dict):
                rows = payload.get("data", [])
            if not rows:
                continue

            for row in rows:
                year = row.get("data_year") or row.get("year")
                value = safe_int(
                    row.get("incident_count") or row.get("value", 0),
                    default=0,
                )

                if year is None:
                    continue

                bias_motivation = row.get("bias_motivation", "all")

                pending_batch.append({
                    "id": make_record_id(
                        "fbi", state_abbr, "hate-crime",
                        bias_motivation, str(year), "hate_crime",
                    ),
                    "state_abbrev": state_abbr,
                    "state_name": STATE_ABBREVS[state_abbr],
                    "offense": "hate-crime",
                    "race": bias_motivation,
                    "year": int(year),
                    "category": "hate_crime",
                    "value": value,
                })

            if len(pending_batch) >= 500:
                hate_crime_records += _flush_batch()

            print(f"  {state_abbr}/hate-crime: {len(rows)} rows")

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
