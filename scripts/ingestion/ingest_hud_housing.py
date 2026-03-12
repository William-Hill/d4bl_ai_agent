"""HUD Fair Market Rent (FMR) ingestion script.

Fetches Fair Market Rent data by state from the HUD User API.
FMR values serve as a housing affordability proxy for equity analysis.
No authentication required.

Self-contained: uses psycopg2 + httpx only.
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

# State FIPS codes (2-digit) to state name
STATE_FIPS = {
    "01": "Alabama", "02": "Alaska", "04": "Arizona",
    "05": "Arkansas", "06": "California", "08": "Colorado",
    "09": "Connecticut", "10": "Delaware",
    "11": "District of Columbia", "12": "Florida",
    "13": "Georgia", "15": "Hawaii", "16": "Idaho",
    "17": "Illinois", "18": "Indiana", "19": "Iowa",
    "20": "Kansas", "21": "Kentucky", "22": "Louisiana",
    "23": "Maine", "24": "Maryland", "25": "Massachusetts",
    "26": "Michigan", "27": "Minnesota", "28": "Mississippi",
    "29": "Missouri", "30": "Montana", "31": "Nebraska",
    "32": "Nevada", "33": "New Hampshire", "34": "New Jersey",
    "35": "New Mexico", "36": "New York",
    "37": "North Carolina", "38": "North Dakota", "39": "Ohio",
    "40": "Oklahoma", "41": "Oregon", "42": "Pennsylvania",
    "44": "Rhode Island", "45": "South Carolina",
    "46": "South Dakota", "47": "Tennessee", "48": "Texas",
    "49": "Utah", "50": "Vermont", "51": "Virginia",
    "53": "Washington", "54": "West Virginia",
    "55": "Wisconsin", "56": "Wyoming",
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
        f"across {len(STATE_FIPS)} states"
    )

    headers = {"Authorization": f"Bearer {hud_token}"}

    try:
        with httpx.Client(timeout=60, headers=headers) as client:
            for fips_code, state_name in STATE_FIPS.items():
                url = f"{HUD_FMR_URL}/{fips_code}?year={year}"
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                    payload = resp.json()
                except Exception as fetch_exc:
                    print(
                        f"WARNING: Failed to fetch FMR for {state_name} "
                        f"({fips_code}): {fetch_exc}"
                    )
                    continue

                # The API returns data under a "data" key with
                # basicdata or similar structure. Extract FMR values
                # from the top-level or nested response.
                data = payload.get("data", payload)
                if isinstance(data, dict):
                    fmr_data = data
                elif isinstance(data, list) and len(data) > 0:
                    fmr_data = data[0]
                else:
                    print(f"WARNING: No FMR data for {state_name}")
                    continue

                states_seen.add(state_name)

                batch = []
                for indicator in HUD_INDICATORS:
                    field = INDICATOR_FIELDS.get(indicator)
                    value = fmr_data.get(field)
                    # Also try lowercase/snake variants
                    if value is None:
                        value = fmr_data.get(
                            indicator.replace("fmr_", "") + "br"
                        )
                    if value is None:
                        value = fmr_data.get(indicator)
                    if value is None:
                        # Try numeric keys like fmr_0, fmr_1, etc.
                        br_num = indicator.replace(
                            "fmr_", ""
                        ).replace("br", "")
                        value = fmr_data.get(f"fmr_{br_num}")
                    if value is None:
                        continue

                    value = safe_float(value)
                    if value is None:
                        continue

                    indicators_seen.add(indicator)

                    batch.append({
                        "id": make_record_id(
                            "hud_fmr", fips_code, str(year),
                            indicator, "all", "all",
                        ),
                        "fips_code": fips_code,
                        "geography_type": "state",
                        "geography_name": state_name,
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
                    f"  {state_name} ({fips_code}): upserted "
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
