"""USDA Food Access Research Atlas ingestion script.

Downloads the Food Access Research Atlas Excel file from the USDA ERS
website and upserts tract-level food access indicators into the
usda_food_access table.

Usage:
    DAGSTER_POSTGRES_URL=postgresql://... python scripts/ingestion/ingest_usda_food.py

Environment variables:
    DAGSTER_POSTGRES_URL   - PostgreSQL connection URL (required)
    USDA_FOOD_ACCESS_YEAR  - Atlas year (default: 2019)
"""

import io
import os

import httpx

from .helpers import (
    get_db_connection, execute_batch, make_record_id, safe_float, safe_int,
)

# Direct download URL for the Food Access Research Atlas Excel file
USDA_DOWNLOAD_URL = (
    "https://www.ers.usda.gov/media/5627/"
    "food-access-research-atlas-data-download-2019.zip"
)

# Indicator columns to pivot into rows
FOOD_ACCESS_INDICATORS = [
    "lapop1",
    "lapop10",
    "lapop20",
    "TractSNAP",
    "PovertyRate",
    "MedianFamilyIncome",
]

# Human-readable names for each indicator
INDICATOR_NAMES = {
    "lapop1": "low_access_pop_1mi",
    "lapop10": "low_access_pop_10mi",
    "lapop20": "low_access_pop_20mi",
    "TractSNAP": "snap_participants",
    "PovertyRate": "poverty_rate",
    "MedianFamilyIncome": "median_family_income",
}

UPSERT_SQL = """
    INSERT INTO usda_food_access
        (id, tract_fips, state_fips,
         county_fips, state_name,
         county_name, urban_rural,
         population, poverty_rate,
         median_income, year,
         indicator, value)
    VALUES
        (%(id)s::UUID,
         %(tract_fips)s, %(state_fips)s,
         %(county_fips)s, %(state_name)s,
         %(county_name)s, %(urban_rural)s,
         %(population)s, %(poverty_rate)s,
         %(median_income)s, %(year)s,
         %(indicator)s, %(value)s)
    ON CONFLICT (tract_fips, year, indicator)
    DO UPDATE SET
        value = EXCLUDED.value,
        state_fips = EXCLUDED.state_fips,
        county_fips = EXCLUDED.county_fips,
        state_name = EXCLUDED.state_name,
        county_name = EXCLUDED.county_name,
        urban_rural = EXCLUDED.urban_rural,
        population = EXCLUDED.population,
        poverty_rate = EXCLUDED.poverty_rate,
        median_income = EXCLUDED.median_income
"""


def main():
    year = int(os.environ.get("USDA_FOOD_ACCESS_YEAR", "2019"))
    download_url = os.environ.get("USDA_FOOD_ACCESS_URL", USDA_DOWNLOAD_URL)

    print(f"Downloading USDA Food Access Research Atlas (year={year})")

    with httpx.Client(timeout=300, follow_redirects=True) as client:
        resp = client.get(download_url)
        if resp.status_code != 200:
            print(
                f"USDA download failed with status {resp.status_code}. "
                f"Skipping."
            )
            return 0
        raw_bytes = resp.content

    # Handle ZIP or Excel
    import zipfile
    if download_url.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            xlsx_names = [
                n for n in zf.namelist()
                if n.lower().endswith(".xlsx")
            ]
            if not xlsx_names:
                print("No Excel files found in USDA ZIP archive.")
                return 0
            print(f"Extracting {xlsx_names[0]} from ZIP")
            raw_bytes = zf.read(xlsx_names[0])

    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True)
    ws = wb.active

    rows_iter = ws.iter_rows(values_only=True)
    header_raw = next(rows_iter)
    header = [str(h).strip() if h else "" for h in header_raw]

    # Find column indices
    def col_idx(name):
        for i, h in enumerate(header):
            if h.lower() == name.lower():
                return i
        return None

    tract_col = col_idx("CensusTract")
    state_col = col_idx("State")
    county_col = col_idx("County")
    urban_col = col_idx("Urban")
    pop_col = col_idx("Pop2010")
    pov_col = col_idx("PovertyRate")
    income_col = col_idx("MedianFamilyIncome")

    indicator_cols = {}
    for ind in FOOD_ACCESS_INDICATORS:
        idx = col_idx(ind)
        if idx is not None:
            indicator_cols[ind] = idx

    if tract_col is None:
        print(f"ERROR: CensusTract column not found. Headers: {header[:20]}")
        return 0

    print(f"Found {len(indicator_cols)} indicator columns in Excel")

    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    records_ingested = 0
    states_seen = set()
    tracts_seen = set()
    batch = []

    try:
        for row in rows_iter:
            raw_tract = row[tract_col] if tract_col < len(row) else None
            if not raw_tract:
                continue

            try:
                tract_fips = str(int(float(raw_tract))).zfill(11)
            except (ValueError, TypeError):
                tract_fips = str(raw_tract).replace(".0", "").strip().zfill(11)
            if not tract_fips or tract_fips == "0" * 11:
                continue

            state_fips = tract_fips[:2]
            county_fips = tract_fips[:5]
            state_name = str(row[state_col]).strip() if state_col and state_col < len(row) else ""
            county_name = str(row[county_col]).strip() if county_col and county_col < len(row) else ""

            urban_val = row[urban_col] if urban_col and urban_col < len(row) else None
            urban_rural = None
            if urban_val == 1 or urban_val == "1":
                urban_rural = "urban"
            elif urban_val == 0 or urban_val == "0":
                urban_rural = "rural"

            population = safe_int(row[pop_col] if pop_col and pop_col < len(row) else None)
            poverty_rate = safe_float(row[pov_col] if pov_col and pov_col < len(row) else None)
            median_income = safe_float(row[income_col] if income_col and income_col < len(row) else None)

            states_seen.add(state_name)
            tracts_seen.add(tract_fips)

            for indicator, idx in indicator_cols.items():
                raw_val = row[idx] if idx < len(row) else None
                if raw_val is None:
                    continue
                value = safe_float(raw_val)
                if value is None:
                    continue

                indicator_name = INDICATOR_NAMES.get(indicator, indicator.lower())

                batch.append({
                    "id": make_record_id("usda_food", tract_fips, str(year), indicator),
                    "tract_fips": tract_fips,
                    "state_fips": state_fips,
                    "county_fips": county_fips,
                    "state_name": state_name,
                    "county_name": county_name,
                    "urban_rural": urban_rural,
                    "population": population,
                    "poverty_rate": poverty_rate,
                    "median_income": median_income,
                    "year": year,
                    "indicator": indicator_name,
                    "value": value,
                })

                if len(batch) >= 500:
                    execute_batch(cur, UPSERT_SQL, batch)
                    conn.commit()
                    records_ingested += len(batch)
                    print(f"  Committed batch: {records_ingested} records so far")
                    batch = []

        if batch:
            execute_batch(cur, UPSERT_SQL, batch)
            conn.commit()
            records_ingested += len(batch)

    finally:
        cur.close()
        conn.close()

    print(
        f"Ingested {records_ingested} USDA Food Access records "
        f"across {len(states_seen)} states, "
        f"{len(tracts_seen)} tracts"
    )
    return records_ingested


if __name__ == "__main__":
    main()
