"""Census Decennial PL 94-171 race/ethnicity demographics ingestion.

Fetches population counts by race at county and tract level from the
Census Bureau API and upserts into the census_demographics table.

Env vars:
    DATABASE_URL               - PostgreSQL connection URL (required)
    CENSUS_API_KEY             - Census API key (optional, higher rate limits)
    CENSUS_DECENNIAL_YEAR      - Data year (default: 2020)
"""

from __future__ import annotations

import os

import httpx

from .helpers import (
    STATE_FIPS, get_db_connection, make_record_id, safe_int, upsert_batch,
)

# 2020 PL 94-171 variables: race alone counts + Hispanic
RACE_VARIABLES = {
    "total":        "P1_001N",
    "White":        "P1_003N",
    "Black":        "P1_004N",
    "AIAN":         "P1_005N",
    "Asian":        "P1_006N",
    "NHPI":         "P1_007N",
    "Other":        "P1_008N",
    "Two_or_more":  "P1_009N",
    "Hispanic":     "P2_002N",
}

ALL_VARIABLES = sorted(RACE_VARIABLES.values())

UPSERT_SQL = """
    INSERT INTO census_demographics
        (id, geo_id, geo_type, state_fips, state_name,
         county_name, year, race, population, pct_of_total)
    VALUES
        (%(id)s::UUID, %(geo_id)s, %(geo_type)s, %(state_fips)s,
         %(state_name)s, %(county_name)s, %(year)s, %(race)s,
         %(population)s, %(pct_of_total)s)
    ON CONFLICT (geo_id, year, race)
    DO UPDATE SET population = EXCLUDED.population,
        pct_of_total = EXCLUDED.pct_of_total,
        state_name = EXCLUDED.state_name,
        county_name = EXCLUDED.county_name,
        geo_type = EXCLUDED.geo_type
"""


def _pct(part: int | None, total: int | None) -> float | None:
    """Compute percentage, returning None if total is zero or inputs invalid."""
    if part is None or total is None or total == 0:
        return None
    return round((part / total) * 100, 2)


def _fetch_decennial(
    client: httpx.Client,
    year: int,
    geography: str,
    state_fips: str | None = None,
) -> list[list[str]]:
    """Fetch data from the Census Decennial PL API."""
    url = f"https://api.census.gov/data/{year}/dec/pl"
    all_vars = ",".join(ALL_VARIABLES)
    params: dict[str, str] = {"get": f"NAME,{all_vars}", "for": geography}
    if state_fips:
        params["in"] = f"state:{state_fips}"
    api_key = os.environ.get("CENSUS_API_KEY")
    if api_key:
        params["key"] = api_key

    resp = client.get(url, params=params, timeout=120)
    resp.raise_for_status()
    return resp.json()


def _build_records(
    headers: list[str],
    data_rows: list[list[str]],
    geo_type: str,
    year: int,
) -> list[dict]:
    """Parse API rows into upsert-ready dicts.

    Returns list of dicts with keys: id, geo_id, geo_type, state_fips,
    state_name, county_name, year, race, population, pct_of_total.
    Rows with unparseable total population are skipped.
    """
    try:
        state_col = headers.index("state")
        name_col = headers.index("NAME")
        county_col = headers.index("county")
    except ValueError as exc:
        print(f"WARNING: Missing expected column: {exc}")
        return []

    tract_col = headers.index("tract") if "tract" in headers else None

    # Precompute column indices for race variables
    var_cols = {race: headers.index(var) for race, var in RACE_VARIABLES.items()}
    total_col = var_cols["total"]

    records: list[dict] = []
    for row in data_rows:
        st_fips = row[state_col]

        if geo_type == "county":
            geo_id = st_fips + row[county_col]
        elif geo_type == "tract":
            if tract_col is None:
                continue
            geo_id = st_fips + row[county_col] + row[tract_col]
        else:
            continue

        state_name = STATE_FIPS.get(st_fips)
        county_name = row[name_col]

        total_pop = safe_int(row[total_col])
        if total_pop is None:
            continue

        for race, col in var_cols.items():
            pop = safe_int(row[col])
            if pop is None:
                continue

            records.append({
                "id": make_record_id("decennial", geo_id, str(year), race),
                "geo_id": geo_id,
                "geo_type": geo_type,
                "state_fips": st_fips,
                "state_name": state_name,
                "county_name": county_name,
                "year": year,
                "race": race,
                "population": pop,
                "pct_of_total": _pct(pop, total_pop),
            })

    return records


def main() -> int:
    """Run Census Decennial ingestion for county + tract geographies.

    Returns total records ingested.
    """
    try:
        year = int(os.environ.get("CENSUS_DECENNIAL_YEAR", "2020"))
    except ValueError:
        print("ERROR: CENSUS_DECENNIAL_YEAR must be a valid integer")
        return 0

    print(f"Census Decennial ingestion starting (year={year})")

    conn = get_db_connection()
    client = httpx.Client()
    total_ingested = 0

    try:
        # --- County-level (single request for all states) ---
        print("Fetching county-level data...")
        rows = _fetch_decennial(client, year, "county:*")

        if rows and len(rows) >= 2:
            headers = rows[0]
            records = _build_records(headers, rows[1:], "county", year)
            count = upsert_batch(conn, UPSERT_SQL, records)
            total_ingested += count
            print(f"  County-level: {count} records upserted")
        else:
            print("  County-level: no data returned")

        # --- Tract-level (must request per state) ---
        print(f"Fetching tract-level data for {len(STATE_FIPS)} states...")
        for st_fips, st_name in sorted(STATE_FIPS.items()):
            try:
                rows = _fetch_decennial(
                    client, year, "tract:*", state_fips=st_fips,
                )
            except httpx.HTTPStatusError as exc:
                print(f"  {st_name} ({st_fips}): HTTP {exc.response.status_code}, skipping")
                continue

            if not rows or len(rows) < 2:
                print(f"  {st_name} ({st_fips}): no data")
                continue

            headers = rows[0]
            records = _build_records(headers, rows[1:], "tract", year)
            count = upsert_batch(conn, UPSERT_SQL, records)
            total_ingested += count
            print(f"  {st_name}: {count} tract records upserted")

    finally:
        client.close()
        conn.close()

    print(f"Census Decennial ingestion complete: {total_ingested} total records")
    return total_ingested


if __name__ == "__main__":
    main()
