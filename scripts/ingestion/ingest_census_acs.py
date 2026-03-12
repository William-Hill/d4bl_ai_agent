"""Census ACS 5-Year data ingestion script.

Self-contained script that fetches race-disaggregated indicators
(homeownership, income, poverty) from the Census Bureau API at
state and county level, and upserts into the census_indicators table.

Env vars:
    DAGSTER_POSTGRES_URL  - PostgreSQL connection URL (required)
    CENSUS_API_KEY        - Census API key (optional, higher rate limits)
    ACS_YEAR              - Data year (default: 2022)
"""

import os

import httpx

from .helpers import (
    get_db_connection, execute_batch, make_record_id, safe_float,
)

CENSUS_BASE_URL = "https://api.census.gov/data"

# Metric -> race -> Census API variable codes
METRIC_VARIABLES = {
    "homeownership_rate": {
        "total": {"num": "B25003_002E", "den": "B25003_001E"},
        "black": {"num": "B25003B_002E", "den": "B25003B_001E"},
        "white": {"num": "B25003H_002E", "den": "B25003H_001E"},
        "hispanic": {"num": "B25003I_002E", "den": "B25003I_001E"},
    },
    "median_household_income": {
        "total": {"val": "B19013_001E"},
        "black": {"val": "B19013B_001E"},
        "white": {"val": "B19013H_001E"},
        "hispanic": {"val": "B19013I_001E"},
    },
    "poverty_rate": {
        "total": {"num": "B17001_002E", "den": "B17001_001E"},
        "black": {"num": "B17001B_002E", "den": "B17001B_001E"},
        "white": {"num": "B17001H_002E", "den": "B17001H_001E"},
        "hispanic": {"num": "B17001I_002E", "den": "B17001I_001E"},
    },
}

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

# Precomputed set of all Census API variable codes
CENSUS_VARIABLES = sorted(
    {v for m in METRIC_VARIABLES.values() for r in m.values() for v in r.values()}
)


def _compute_rate(numerator: str, denominator: str) -> float | None:
    """Compute a percentage rate from numerator/denominator strings."""
    try:
        num = float(numerator)
        den = float(denominator)
        if den <= 0:
            return None
        return round((num / den) * 100, 2)
    except (ValueError, TypeError):
        return None


def _fetch_acs(
    client: httpx.Client,
    year: int,
    variables: list[str],
    geography: str = "state:*",
    state_fips: str | None = None,
) -> list[list[str]]:
    """Fetch data from the Census ACS 5-Year API."""
    all_vars = ",".join(variables)
    url = f"{CENSUS_BASE_URL}/{year}/acs/acs5"
    params = {"get": f"NAME,{all_vars}", "for": geography}
    if state_fips:
        if geography == "state:*":
            params["for"] = f"state:{state_fips}"
        elif geography == "county:*":
            params["in"] = f"state:{state_fips}"
        else:
            raise ValueError(
                f"Unsupported state_fips filter for geography {geography!r}"
            )
    api_key = os.environ.get("CENSUS_API_KEY")
    if api_key:
        params["key"] = api_key

    resp = client.get(url, params=params, timeout=120)
    resp.raise_for_status()
    return resp.json()


def _build_records(
    headers: list[str],
    data_rows: list[list[str]],
    geography_type: str,
    year: int,
) -> list[dict]:
    """Parse API rows into upsert-ready dicts."""
    state_col = headers.index("state")
    has_county = "county" in headers
    county_col = headers.index("county") if has_county else None
    name_col = headers.index("NAME")

    records = []
    for row in data_rows:
        st_fips = row[state_col]

        if geography_type == "state":
            fips_code = st_fips
            geo_name = STATE_FIPS.get(st_fips, f"Unknown ({st_fips})")
            id_prefix = "census"
        elif geography_type == "county":
            county_code = row[county_col]
            fips_code = st_fips + county_code
            geo_name = row[name_col]
            id_prefix = "census:county"
        else:
            raise ValueError(f"Unsupported geography_type: {geography_type}")

        for metric, race_vars in METRIC_VARIABLES.items():
            for race, var_map in race_vars.items():
                if "val" in var_map:
                    val_idx = headers.index(var_map["val"])
                    raw_val = row[val_idx]
                    try:
                        value = float(raw_val)
                    except (ValueError, TypeError):
                        continue
                else:
                    num_idx = headers.index(var_map["num"])
                    den_idx = headers.index(var_map["den"])
                    value = _compute_rate(row[num_idx], row[den_idx])
                    if value is None:
                        continue

                records.append({
                    "id": make_record_id(
                        id_prefix, fips_code, str(year), race, metric,
                    ),
                    "fips_code": fips_code,
                    "geography_type": geography_type,
                    "geography_name": geo_name,
                    "state_fips": st_fips,
                    "year": year,
                    "race": race,
                    "metric": metric,
                    "value": value,
                })

    return records


UPSERT_SQL = """
    INSERT INTO census_indicators
        (id, fips_code, geography_type,
         geography_name, state_fips, year,
         race, metric, value)
    VALUES
        (%(id)s::UUID, %(fips_code)s, %(geography_type)s,
         %(geography_name)s, %(state_fips)s, %(year)s,
         %(race)s, %(metric)s, %(value)s)
    ON CONFLICT (fips_code, year, race, metric)
    DO UPDATE SET value = EXCLUDED.value,
        geography_name = EXCLUDED.geography_name,
        geography_type = EXCLUDED.geography_type,
        state_fips = EXCLUDED.state_fips
"""

def _upsert_batch(conn, records: list[dict]) -> int:
    """Upsert a list of records in batches. Returns total upserted."""
    total = 0
    with conn.cursor() as cur:
        for i in range(0, len(records), 500):
            batch = records[i : i + 500]
            execute_batch(cur, UPSERT_SQL, batch)
            total += len(batch)
    conn.commit()
    return total


def main() -> int:
    """Run Census ACS ingestion for state + county geographies.

    Returns total records ingested.
    """
    year = int(os.environ.get("ACS_YEAR", "2022"))

    print(f"Census ACS ingestion starting (year={year})")

    conn = get_db_connection()
    client = httpx.Client()
    total_ingested = 0

    try:
        # --- State-level ---
        print(f"Fetching state-level ACS data for {len(STATE_FIPS)} states...")
        rows = _fetch_acs(client, year, CENSUS_VARIABLES, geography="state:*")

        if rows and len(rows) >= 2:
            headers = rows[0]
            data_rows = rows[1:]
            records = _build_records(headers, data_rows, "state", year)
            count = _upsert_batch(conn, records)
            total_ingested += count
            print(f"  State-level: {count} records upserted")
        else:
            print("  State-level: no data returned")

        # --- County-level ---
        print(f"Fetching county-level ACS data...")
        rows = _fetch_acs(client, year, CENSUS_VARIABLES, geography="county:*")

        if rows and len(rows) >= 2:
            headers = rows[0]
            data_rows = rows[1:]
            records = _build_records(headers, data_rows, "county", year)
            count = _upsert_batch(conn, records)
            total_ingested += count
            print(f"  County-level: {count} records upserted")
        else:
            print("  County-level: no data returned")

    finally:
        client.close()
        conn.close()

    print(f"Census ACS ingestion complete: {total_ingested} total records")
    return total_ingested


if __name__ == "__main__":
    main()
