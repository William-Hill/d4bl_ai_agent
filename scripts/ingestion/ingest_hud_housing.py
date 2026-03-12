"""HUD Fair Market Rent (FMR) ingestion script.

Fetches Fair Market Rent data by state from the HUD User API.
FMR values serve as a housing affordability proxy for equity analysis.

Requires HUD_API_TOKEN env var (register at https://www.huduser.gov/hudapi/public/register).

Usage:
    DAGSTER_POSTGRES_URL=postgresql://... HUD_API_TOKEN=... python scripts/ingestion/ingest_hud_housing.py
"""

import os

import httpx

from .helpers import (
    get_db_connection, execute_batch, make_record_id, safe_float,
)

# HUD FMR API endpoint
HUD_FMR_URL = "https://www.huduser.gov/hudapi/public/fmr/statedata"

# Fair Market Rent indicators by bedroom count
HUD_INDICATORS = [
    "fmr_0br",
    "fmr_1br",
    "fmr_2br",
    "fmr_3br",
    "fmr_4br",
]

# Mapping from indicator name to the API response field
INDICATOR_FIELDS = {
    "fmr_0br": "Efficiency",
    "fmr_1br": "One-Bedroom",
    "fmr_2br": "Two-Bedroom",
    "fmr_3br": "Three-Bedroom",
    "fmr_4br": "Four-Bedroom",
}

# State abbreviation → (FIPS code, state name)
# The HUD API statedata endpoint requires 2-letter state abbreviations.
STATES = {
    "AL": ("01", "Alabama"), "AK": ("02", "Alaska"),
    "AZ": ("04", "Arizona"), "AR": ("05", "Arkansas"),
    "CA": ("06", "California"), "CO": ("08", "Colorado"),
    "CT": ("09", "Connecticut"), "DE": ("10", "Delaware"),
    "DC": ("11", "District of Columbia"), "FL": ("12", "Florida"),
    "GA": ("13", "Georgia"), "HI": ("15", "Hawaii"),
    "ID": ("16", "Idaho"), "IL": ("17", "Illinois"),
    "IN": ("18", "Indiana"), "IA": ("19", "Iowa"),
    "KS": ("20", "Kansas"), "KY": ("21", "Kentucky"),
    "LA": ("22", "Louisiana"), "ME": ("23", "Maine"),
    "MD": ("24", "Maryland"), "MA": ("25", "Massachusetts"),
    "MI": ("26", "Michigan"), "MN": ("27", "Minnesota"),
    "MS": ("28", "Mississippi"), "MO": ("29", "Missouri"),
    "MT": ("30", "Montana"), "NE": ("31", "Nebraska"),
    "NV": ("32", "Nevada"), "NH": ("33", "New Hampshire"),
    "NJ": ("34", "New Jersey"), "NM": ("35", "New Mexico"),
    "NY": ("36", "New York"), "NC": ("37", "North Carolina"),
    "ND": ("38", "North Dakota"), "OH": ("39", "Ohio"),
    "OK": ("40", "Oklahoma"), "OR": ("41", "Oregon"),
    "PA": ("42", "Pennsylvania"), "RI": ("44", "Rhode Island"),
    "SC": ("45", "South Carolina"), "SD": ("46", "South Dakota"),
    "TN": ("47", "Tennessee"), "TX": ("48", "Texas"),
    "UT": ("49", "Utah"), "VT": ("50", "Vermont"),
    "VA": ("51", "Virginia"), "WA": ("53", "Washington"),
    "WV": ("54", "West Virginia"), "WI": ("55", "Wisconsin"),
    "WY": ("56", "Wyoming"),
}

UPSERT_SQL = """
    INSERT INTO hud_fair_housing
        (id, fips_code, geography_type, geography_name,
         state_fips, year, indicator, value,
         race_group_a, race_group_b)
    VALUES
        (CAST(%(id)s AS UUID), %(fips_code)s,
         %(geography_type)s, %(geography_name)s,
         %(state_fips)s, %(year)s, %(indicator)s,
         %(value)s, %(race_group_a)s, %(race_group_b)s)
    ON CONFLICT (fips_code, year, indicator,
                 race_group_a, race_group_b)
    DO UPDATE SET
        value = EXCLUDED.value,
        geography_type = EXCLUDED.geography_type,
        geography_name = EXCLUDED.geography_name,
        state_fips = EXCLUDED.state_fips
"""


def main():
    year = int(os.environ.get("HUD_FMR_YEAR", "2024"))

    hud_token = os.environ.get("HUD_API_TOKEN")
    if not hud_token:
        print("HUD_API_TOKEN not set - skipping HUD FMR ingestion")
        return 0

    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    records_ingested = 0
    states_seen = set()
    indicators_seen = set()

    print(
        f"Fetching HUD FMR data for year={year} "
        f"across {len(STATES)} states"
    )

    headers = {"Authorization": f"Bearer {hud_token}"}

    try:
        with httpx.Client(timeout=60, headers=headers) as client:
            for abbr, (fips_code, state_name) in STATES.items():
                url = f"{HUD_FMR_URL}/{abbr}?year={year}"
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                    payload = resp.json()
                except Exception as fetch_exc:
                    print(
                        f"WARNING: Failed to fetch FMR for {state_name} "
                        f"({abbr}): {fetch_exc}"
                    )
                    continue

                # Response has "data" with "metroareas" and "counties"
                # arrays. Each entry has FMR fields like "Efficiency",
                # "One-Bedroom", etc. We ingest county-level records.
                data = payload.get("data", payload)
                counties = []
                if isinstance(data, dict):
                    counties = data.get("counties", [])
                    if not counties:
                        # Fallback: maybe metroareas has data
                        counties = data.get("metroareas", [])
                elif isinstance(data, list):
                    counties = data

                if not counties:
                    print(f"WARNING: No FMR data for {state_name}")
                    continue

                states_seen.add(state_name)

                batch = []
                for area in counties:
                    area_code = str(
                        area.get("code", area.get("fips_code", ""))
                    ).strip()
                    area_name = str(
                        area.get("name", area.get("county_name", ""))
                    ).strip()

                    if not area_code:
                        continue

                    for indicator in HUD_INDICATORS:
                        field = INDICATOR_FIELDS.get(indicator)
                        value = safe_float(area.get(field))
                        if value is None:
                            value = safe_float(area.get(indicator))
                        if value is None:
                            continue

                        indicators_seen.add(indicator)

                        batch.append({
                            "id": make_record_id(
                                "hud_fmr", area_code, str(year),
                                indicator, "all", "all",
                            ),
                            "fips_code": area_code,
                            "geography_type": "county",
                            "geography_name": area_name,
                            "state_fips": fips_code,
                            "year": year,
                            "indicator": indicator,
                            "value": value,
                            "race_group_a": "all",
                            "race_group_b": "all",
                        })

                if batch:
                    execute_batch(cur, UPSERT_SQL, batch)
                    conn.commit()
                    records_ingested += len(batch)

                print(
                    f"  {state_name} ({abbr}): upserted "
                    f"{len(batch)} FMR records"
                )
    finally:
        cur.close()
        conn.close()

    print(
        f"Ingested {records_ingested} HUD FMR records "
        f"across {len(states_seen)} states"
    )
    print(f"Indicators covered: {sorted(indicators_seen)}")
    return records_ingested


if __name__ == "__main__":
    main()
