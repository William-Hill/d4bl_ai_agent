"""USDA Food Access Research Atlas ingestion script.

Fetches food access indicators at the census-tract level from the
USDA Economic Research Service ArcGIS FeatureServer and upserts into
the usda_food_access table.

Usage:
    DAGSTER_POSTGRES_URL=postgresql://... python scripts/ingestion/ingest_usda_food.py

Environment variables:
    DAGSTER_POSTGRES_URL   - PostgreSQL connection URL (required)
    USDA_FOOD_ACCESS_YEAR  - Atlas year (default: 2019)
"""

import os

import httpx

from scripts.ingestion.helpers import (
    get_db_connection, execute_batch, make_record_id, safe_float, safe_int,
)

# ArcGIS FeatureServer endpoint for the Food Access Research Atlas
USDA_FOOD_ACCESS_URL = (
    "https://services1.arcgis.com/RLQu0rK7h4kbsBq5/arcgis/rest/services/"
    "Food_Access_Research_Atlas/FeatureServer/0/query"
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

# Fields to request from the ArcGIS service
OUT_FIELDS = ",".join([
    "CensusTract",
    "State",
    "County",
    "Urban",
    "Pop2010",
    "PovertyRate",
    "MedianFamilyIncome",
    "lapop1",
    "lapop10",
    "lapop20",
    "TractSNAP",
])

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

    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    records_ingested = 0
    states_seen = set()
    tracts_seen = set()

    print(f"Fetching USDA Food Access Research Atlas data (year={year})")

    try:
        with httpx.Client(timeout=120) as client:
            offset = 0
            page_size = 2000
            while True:
                params = {
                    "where": "1=1",
                    "outFields": OUT_FIELDS,
                    "f": "json",
                    "resultRecordCount": str(page_size),
                    "resultOffset": str(offset),
                }
                resp = client.get(USDA_FOOD_ACCESS_URL, params=params)
                resp.raise_for_status()
                payload = resp.json()

                features = payload.get("features", [])
                if not features:
                    break

                batch = []
                for feature in features:
                    attrs = feature.get("attributes", {})
                    raw_tract = attrs.get("CensusTract", "")

                    # Normalize: ArcGIS may return numeric
                    # (losing leading zeros) or with ".0" suffix.
                    # Convert to 11-digit zero-padded string.
                    try:
                        tract_fips = str(int(float(raw_tract))).zfill(11)
                    except (ValueError, TypeError):
                        tract_fips = (
                            str(raw_tract)
                            .replace(".0", "")
                            .strip()
                            .zfill(11)
                        )
                    if not tract_fips or tract_fips == "0" * 11:
                        continue

                    state_fips = tract_fips[:2]
                    county_fips = tract_fips[:5]
                    state_name = attrs.get("State", "")
                    county_name = attrs.get("County", "")
                    urban = attrs.get("Urban", None)

                    population = safe_int(attrs.get("Pop2010"))
                    poverty_rate = safe_float(attrs.get("PovertyRate"))
                    median_income = safe_float(attrs.get("MedianFamilyIncome"))

                    states_seen.add(state_name)
                    tracts_seen.add(tract_fips)

                    # Pivot each indicator into its own row
                    for indicator in FOOD_ACCESS_INDICATORS:
                        raw_val = attrs.get(indicator)
                        if raw_val is None:
                            continue
                        value = safe_float(raw_val)
                        if value is None:
                            continue

                        indicator_name = INDICATOR_NAMES.get(
                            indicator, indicator.lower()
                        )

                        urban_rural = None
                        if urban == 1:
                            urban_rural = "urban"
                        elif urban == 0:
                            urban_rural = "rural"

                        batch.append({
                            "id": make_record_id(
                                "usda_food", tract_fips,
                                str(year), indicator,
                            ),
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

                # Flush remaining batch for this page
                if batch:
                    execute_batch(cur, UPSERT_SQL, batch)
                    conn.commit()
                    records_ingested += len(batch)

                print(f"  Fetched {len(features)} features (offset={offset})")
                if len(features) < page_size:
                    break
                offset += page_size

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
