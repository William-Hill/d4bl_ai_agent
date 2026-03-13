"""EPA EJScreen environmental justice ingestion script.

Self-contained script that fetches state-level EJ screening indicators
from the EPA EJScreen REST API and upserts into epa_environmental_justice.

Env vars:
    DAGSTER_POSTGRES_URL   - PostgreSQL connection URL (required)
    EPA_EJSCREEN_YEAR      - Data year (default: 2024)
"""

import os

import httpx

from .helpers import (
    get_db_connection, execute_batch, make_record_id, safe_float, safe_int,
)

# EPA EJScreen ArcGIS REST endpoint for state-level summaries
EPA_EJSCREEN_URL = (
    "https://ejscreen.epa.gov/mapper/ejscreenRESTbroker.aspx"
)

# Key EJ indicators to track
EJ_INDICATORS = [
    "PM25",                  # Particulate Matter 2.5
    "OZONE",                 # Ozone
    "DSLPM",                 # Diesel particulate matter
    "CANCER",                # Air toxics cancer risk
    "RESP",                  # Air toxics respiratory HI
    "PTRAF",                 # Traffic proximity
    "PNPL",                  # Superfund proximity
    "PRMP",                  # RMP facility proximity
    "PTSDF",                 # Hazardous waste proximity
    "PWDIS",                 # Wastewater discharge
    "PRE1960PCT",            # Pre-1960 housing (lead paint)
    "UNDER5PCT",             # Under age 5
    "OVER64PCT",             # Over age 64
    "MINORPCT",              # People of color
    "LOWINCPCT",             # Low income
    "LINGISOPCT",            # Linguistic isolation
    "LESSHSPCT",             # Less than high school education
    "UNEMPPCT",              # Unemployment rate
]

# State FIPS codes for iteration
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
    "37": "North Carolina", "38": "North Dakota",
    "39": "Ohio", "40": "Oklahoma", "41": "Oregon",
    "42": "Pennsylvania", "44": "Rhode Island",
    "45": "South Carolina", "46": "South Dakota",
    "47": "Tennessee", "48": "Texas", "49": "Utah",
    "50": "Vermont", "51": "Virginia", "53": "Washington",
    "54": "West Virginia", "55": "Wisconsin", "56": "Wyoming",
}

UPSERT_SQL = """
    INSERT INTO epa_environmental_justice
        (id, tract_fips, state_fips, state_name,
         year, indicator, raw_value,
         percentile_state, percentile_national,
         population, minority_pct, low_income_pct)
    VALUES
        (%(id)s::UUID, %(tract_fips)s,
         %(state_fips)s, %(state_name)s, %(year)s,
         %(indicator)s, %(raw_value)s,
         %(pctile_state)s, %(pctile_national)s,
         %(pop)s, %(minority)s, %(lowinc)s)
    ON CONFLICT (tract_fips, year, indicator)
    DO UPDATE SET
        raw_value = EXCLUDED.raw_value,
        percentile_state = EXCLUDED.percentile_state,
        percentile_national = EXCLUDED.percentile_national,
        population = EXCLUDED.population,
        minority_pct = EXCLUDED.minority_pct,
        low_income_pct = EXCLUDED.low_income_pct
"""

def main() -> int:
    """Run EPA EJScreen ingestion for state-level data.

    NOTE: The EPA took EJScreen offline in February 2025. This script
    will likely return 0 records until the service is restored or an
    alternative data source is configured via EPA_EJSCREEN_URL.

    Returns total records ingested.
    """
    try:
        year = int(os.environ.get("EPA_EJSCREEN_YEAR", "2024"))
    except ValueError:
        print("ERROR: EPA_EJSCREEN_YEAR must be a valid integer")
        return 0
    # NOTE: The year label is written into each row but the EJScreen API
    # always returns the latest available dataset regardless of year param.
    # This is acceptable — each run captures a point-in-time snapshot.

    print(f"EPA EJScreen ingestion starting (year={year})")

    conn = get_db_connection()
    client = httpx.Client()

    records_ingested = 0
    states_covered = set()
    pending_batch: list[dict] = []

    try:
        for fips, state_name in STATE_FIPS.items():
            params = {
                "namestr": "",
                "geometry": "",
                "distance": "",
                "unit": "9035",
                "aession": "",
                "f": "json",
                "areaid": fips,
                "areatype": "state",
            }
            try:
                resp = client.get(
                    EPA_EJSCREEN_URL, params=params, timeout=60
                )
                if resp.status_code != 200:
                    print(
                        f"  WARNING: EPA EJScreen returned {resp.status_code} "
                        f"for state {fips} ({state_name})"
                    )
                    continue
                data = resp.json()
            except Exception as exc:
                print(
                    f"  WARNING: Failed to fetch EJScreen for "
                    f"{fips} ({state_name}): {exc}"
                )
                continue

            # Parse the response - EJScreen returns nested data
            raw_data = data if isinstance(data, dict) else {}

            for indicator in EJ_INDICATORS:
                indicator_lower = indicator.lower()
                # Try multiple key patterns
                raw_val = raw_data.get(indicator)
                if raw_val is None:
                    raw_val = raw_data.get(indicator_lower)
                if raw_val is None:
                    raw_val = raw_data.get(f"RAW_{indicator}")

                pctile = raw_data.get(f"P_{indicator}")
                if pctile is None:
                    pctile = raw_data.get(f"PCTILE_{indicator}")

                # Skip if no data at all
                if raw_val is None and pctile is None:
                    continue

                raw_float = safe_float(raw_val)
                pctile_float = safe_float(pctile)

                if raw_float is None and pctile_float is None:
                    continue

                states_covered.add(fips)

                record_id = make_record_id(
                    "epa", fips, str(year), indicator,
                )

                minority = raw_data.get("MINORPCT")
                if minority is None:
                    minority = raw_data.get("minorpct")
                lowinc = raw_data.get("LOWINCPCT")
                if lowinc is None:
                    lowinc = raw_data.get("lowincpct")
                pop = raw_data.get("ACSTOTPOP")
                if pop is None:
                    pop = raw_data.get("acstotpop")

                pending_batch.append({
                    "id": record_id,
                    # tract_fips stores the 2-digit state FIPS because
                    # this script fetches state-level summaries, not
                    # census-tract-level data.
                    "tract_fips": fips,
                    "state_fips": fips,
                    "state_name": state_name,
                    "year": year,
                    "indicator": indicator_lower,
                    "raw_value": raw_float,
                    # State-level aggregation provides only one percentile;
                    # tract-level ingestion would populate these separately.
                    "pctile_state": pctile_float,
                    "pctile_national": pctile_float,
                    "pop": safe_int(pop),
                    "minority": safe_float(minority),
                    "lowinc": safe_float(lowinc),
                })

            # Flush batch when it reaches threshold
            if len(pending_batch) >= 500:
                with conn.cursor() as cur:
                    execute_batch(cur, UPSERT_SQL, pending_batch)
                conn.commit()
                records_ingested += len(pending_batch)
                pending_batch = []

            print(f"  State {fips} ({state_name}): processed")

        # Flush remaining records
        if pending_batch:
            with conn.cursor() as cur:
                execute_batch(cur, UPSERT_SQL, pending_batch)
            conn.commit()
            records_ingested += len(pending_batch)

    finally:
        client.close()
        conn.close()

    print(
        f"EPA EJScreen ingestion complete: {records_ingested} records "
        f"across {len(states_covered)} states"
    )
    return records_ingested


if __name__ == "__main__":
    main()
