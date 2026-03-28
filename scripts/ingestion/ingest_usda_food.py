"""USDA Food Access Research Atlas ingestion script.

Downloads the Food Access Research Atlas Excel file from the USDA ERS
website and upserts tract-level food access indicators into the
usda_food_access table.

Usage:
    DATABASE_URL=postgresql://... python scripts/ingestion/ingest_usda_food.py

Environment variables:
    DATABASE_URL           - PostgreSQL connection URL (required)
    USDA_FOOD_ACCESS_YEAR  - Atlas year (default: 2019)
"""

import csv
import io
import os
import zipfile

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


def main() -> int:
    """Run USDA Food Access Research Atlas ingestion.

    Returns total records ingested.
    """
    try:
        year = int(os.environ.get("USDA_FOOD_ACCESS_YEAR", "2019"))
    except ValueError:
        print("ERROR: USDA_FOOD_ACCESS_YEAR must be a valid integer")
        return 0
    # NOTE: The download URL is for the 2019 atlas regardless of year setting.
    # USDA_FOOD_ACCESS_URL can override to point at a different edition.
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

    # Handle ZIP (may contain CSV or XLSX)
    csv_text = None
    if download_url.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            # Prefer the main data CSV/XLSX (skip ReadMe, VariableLookup)
            data_files = [
                n for n in zf.namelist()
                if n.lower().endswith((".csv", ".xlsx"))
                and "readme" not in n.lower()
                and "variable" not in n.lower()
            ]
            if not data_files:
                print("No data files found in USDA ZIP archive.")
                return 0
            chosen = data_files[0]
            print(f"Extracting {chosen} from ZIP")
            raw_bytes = zf.read(chosen)

            if chosen.lower().endswith(".csv"):
                csv_text = raw_bytes.decode("utf-8-sig")

    if csv_text is not None:
        reader = csv.DictReader(io.StringIO(csv_text))
        header = reader.fieldnames or []
        rows_iter = reader
    else:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True)
        ws = wb.active
        _rows = ws.iter_rows(values_only=True)
        header_raw = next(_rows)
        header = [str(h).strip() if h else "" for h in header_raw]
        rows_iter = (dict(zip(header, row)) for row in _rows)

    # Build a case-insensitive header lookup
    header_lower = {h.lower(): h for h in header}

    def get_col(row, name):
        """Get a value from a dict row using case-insensitive key."""
        key = header_lower.get(name.lower())
        return row.get(key) if key else None

    # Check required column exists
    if not header_lower.get("censustract"):
        print(f"ERROR: CensusTract column not found. Headers: {header[:20]}")
        return 0

    # Find which indicators are present
    avail_indicators = [
        ind for ind in FOOD_ACCESS_INDICATORS
        if header_lower.get(ind.lower())
    ]
    print(f"Found {len(avail_indicators)} indicator columns in data")

    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    records_ingested = 0
    states_seen = set()
    tracts_seen = set()
    batch = []

    try:
        for row in rows_iter:
            raw_tract = get_col(row, "CensusTract")
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
            state_name = str(get_col(row, "State") or "").strip()
            county_name = str(get_col(row, "County") or "").strip()

            urban_val = get_col(row, "Urban")
            urban_rural = None
            if urban_val in (1, "1"):
                urban_rural = "urban"
            elif urban_val in (0, "0"):
                urban_rural = "rural"

            population = safe_int(get_col(row, "Pop2010"))
            poverty_rate = safe_float(get_col(row, "PovertyRate"))
            median_income = safe_float(get_col(row, "MedianFamilyIncome"))

            states_seen.add(state_name)
            tracts_seen.add(tract_fips)

            for indicator in avail_indicators:
                raw_val = get_col(row, indicator)
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
