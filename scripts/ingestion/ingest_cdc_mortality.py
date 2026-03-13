"""CDC WONDER mortality data ingestion script.

Fetches mortality data from two SODA API datasets:
- bi63-dtpu: state-level leading causes of death (1999-2017)
- m74n-4hbs: national race-disaggregated excess deaths (2015-2023)

Self-contained: uses psycopg2 + httpx only.
"""

from collections import defaultdict

import httpx

from .helpers import (
    execute_batch,
    get_db_connection,
    make_record_id,
    safe_float,
    safe_int,
)

# --- SODA API endpoints ---
CDC_STATE_MORTALITY_URL = "https://data.cdc.gov/resource/bi63-dtpu.json"
CDC_EXCESS_DEATHS_URL = "https://data.cdc.gov/resource/m74n-4hbs.json"

# --- State name -> FIPS mapping ---
STATE_NAME_TO_FIPS = {
    "Alabama": "01", "Alaska": "02", "Arizona": "04", "Arkansas": "05",
    "California": "06", "Colorado": "08", "Connecticut": "09", "Delaware": "10",
    "District of Columbia": "11", "Florida": "12", "Georgia": "13", "Hawaii": "15",
    "Idaho": "16", "Illinois": "17", "Indiana": "18", "Iowa": "19",
    "Kansas": "20", "Kentucky": "21", "Louisiana": "22", "Maine": "23",
    "Maryland": "24", "Massachusetts": "25", "Michigan": "26", "Minnesota": "27",
    "Mississippi": "28", "Missouri": "29", "Montana": "30", "Nebraska": "31",
    "Nevada": "32", "New Hampshire": "33", "New Jersey": "34", "New Mexico": "35",
    "New York": "36", "North Carolina": "37", "North Dakota": "38", "Ohio": "39",
    "Oklahoma": "40", "Oregon": "41", "Pennsylvania": "42", "Rhode Island": "44",
    "South Carolina": "45", "South Dakota": "46", "Tennessee": "47", "Texas": "48",
    "Utah": "49", "Vermont": "50", "Virginia": "51", "Washington": "53",
    "West Virginia": "54", "Wisconsin": "55", "Wyoming": "56",
}

# --- Race mapping for m74n-4hbs ---
RACE_MAP = {
    "Non-Hispanic White": "white",
    "Non-Hispanic Black": "black",
    "Hispanic": "hispanic",
    "Non-Hispanic Asian": "asian",
    "Non-Hispanic American Indian or Alaska Native": "native_american",
    "Other": "multiracial",
}

STATE_UPSERT_SQL = """
    INSERT INTO cdc_mortality
        (id, geo_id, geography_type, state_fips, state_name,
         year, cause_of_death, race, deaths, age_adjusted_rate)
    VALUES
        (CAST(%(id)s AS UUID), %(geo_id)s, 'state', %(state_fips)s, %(state_name)s,
         %(year)s, %(cause_of_death)s, 'total', %(deaths)s, %(age_adjusted_rate)s)
    ON CONFLICT (geo_id, year, cause_of_death, race)
    DO UPDATE SET
        deaths = %(deaths)s,
        age_adjusted_rate = %(age_adjusted_rate)s,
        state_name = %(state_name)s
"""

NATIONAL_UPSERT_SQL = """
    INSERT INTO cdc_mortality
        (id, geo_id, geography_type, state_fips, state_name,
         year, cause_of_death, race, deaths, age_adjusted_rate)
    VALUES
        (CAST(%(id)s AS UUID), 'US', 'national', NULL, NULL,
         %(year)s, 'all_causes', %(race)s, %(deaths)s, NULL)
    ON CONFLICT (geo_id, year, cause_of_death, race)
    DO UPDATE SET
        deaths = %(deaths)s
"""


def _ingest_state(conn, client: httpx.Client) -> int:
    """Ingest state-level leading causes of death from bi63-dtpu."""
    conn.autocommit = False
    cur = conn.cursor()
    count = 0
    offset = 0
    limit = 50000

    try:
        while True:
            url = (
                f"{CDC_STATE_MORTALITY_URL}"
                f"?$limit={limit}"
                f"&$offset={offset}"
                f"&$order=year,state"
            )
            resp = client.get(url)
            resp.raise_for_status()
            rows = resp.json()

            if not rows:
                break

            print(f"  Fetched {len(rows)} rows (offset={offset})")

            batch = []
            for row in rows:
                state_name = row.get("state")
                cause = row.get("cause_name")
                year_str = row.get("year")

                if not state_name or not cause or not year_str:
                    continue
                if cause == "All causes" or state_name == "United States":
                    continue

                state_fips = STATE_NAME_TO_FIPS.get(state_name)
                if not state_fips:
                    continue

                year = safe_int(year_str)
                if year is None:
                    continue

                batch.append({
                    "id": make_record_id(
                        "cdc-mortality", state_fips, str(year), cause, "total",
                    ),
                    "geo_id": state_fips,
                    "state_fips": state_fips,
                    "state_name": state_name,
                    "year": year,
                    "cause_of_death": cause,
                    "deaths": safe_int(row.get("deaths")),
                    "age_adjusted_rate": safe_float(row.get("aadr")),
                })

            if batch:
                execute_batch(cur, STATE_UPSERT_SQL, batch)
                conn.commit()
                count += len(batch)

            if len(rows) < limit:
                break
            offset += limit
    finally:
        cur.close()

    return count


def _ingest_national_race(conn, client: httpx.Client) -> int:
    """Ingest national excess deaths by race from m74n-4hbs, aggregated to annual."""
    annual_deaths: dict[tuple[int, str], float] = defaultdict(float)
    offset = 0
    limit = 50000

    while True:
        url = (
            f"{CDC_EXCESS_DEATHS_URL}"
            f"?$limit={limit}"
            f"&$offset={offset}"
            f"&$where=sex='All Sexes'"
            f"&$select=mmwryear,raceethnicity,deaths_unweighted"
            f"&$order=mmwryear,raceethnicity"
        )
        resp = client.get(url)
        resp.raise_for_status()
        rows = resp.json()

        if not rows:
            break

        print(f"  Fetched {len(rows)} weekly rows (offset={offset})")

        for row in rows:
            race = RACE_MAP.get(row.get("raceethnicity", ""))
            if not race:
                continue

            year = safe_int(row.get("mmwryear"))
            deaths = safe_float(row.get("deaths_unweighted"))
            if year is None or deaths is None:
                continue

            annual_deaths[(year, race)] += deaths

        if len(rows) < limit:
            break
        offset += limit

    # Upsert aggregated annual totals
    conn.autocommit = False
    cur = conn.cursor()
    batch = []
    try:
        for (year, race), total_deaths in sorted(annual_deaths.items()):
            batch.append({
                "id": make_record_id(
                    "cdc-mortality", "US", str(year), "all_causes", race,
                ),
                "year": year,
                "race": race,
                "deaths": int(total_deaths),
            })

        if batch:
            execute_batch(cur, NATIONAL_UPSERT_SQL, batch)
            conn.commit()
    finally:
        cur.close()

    return len(batch)


def main() -> int:
    """Run CDC mortality ingestion. Returns total records ingested."""
    conn = get_db_connection()
    count = 0

    try:
        with httpx.Client(timeout=120) as client:
            print("Ingesting state-level leading causes of death...")
            state_count = _ingest_state(conn, client)
            print(f"  State: {state_count} records ingested.")
            count += state_count

            print("Ingesting national race-disaggregated excess deaths...")
            national_count = _ingest_national_race(conn, client)
            print(f"  National: {national_count} records ingested.")
            count += national_count
    finally:
        conn.close()

    print(f"Total: {count} records ingested.")
    return count


if __name__ == "__main__":
    main()
