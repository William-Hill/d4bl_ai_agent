"""CDC PLACES health outcomes ingestion script.

Fetches health outcome and prevention measures by county/state
from the CDC PLACES SODA API. No authentication required.

Self-contained: uses psycopg2 + httpx only.
"""

import os

import httpx

from .helpers import (
    get_db_connection, execute_batch, make_record_id, safe_float, safe_int,
)

# SODA API endpoint for CDC PLACES county-level data
CDC_PLACES_URL = "https://data.cdc.gov/resource/swc5-untb.json"

# Health equity measures to fetch
CDC_MEASURES = [
    "DIABETES",
    "BPHIGH",       # High blood pressure
    "CASTHMA",      # Current asthma
    "CHD",          # Coronary heart disease
    "MHLTH",        # Mental health not good
    "OBESITY",      # Obesity
    "CSMOKING",     # Current smoking
    "ACCESS2",      # No health insurance (18-64)
    "CHECKUP",      # Annual checkup
    "DEPRESSION",   # Depression
]

# Human-readable measure names
MEASURE_NAMES = {
    "DIABETES": "diabetes",
    "BPHIGH": "high_blood_pressure",
    "CASTHMA": "current_asthma",
    "CHD": "coronary_heart_disease",
    "MHLTH": "poor_mental_health",
    "OBESITY": "obesity",
    "CSMOKING": "current_smoking",
    "ACCESS2": "lack_health_insurance",
    "CHECKUP": "annual_checkup",
    "DEPRESSION": "depression",
}

MEASURE_CATEGORIES = {
    "DIABETES": "health_outcomes",
    "BPHIGH": "health_outcomes",
    "CASTHMA": "health_outcomes",
    "CHD": "health_outcomes",
    "MHLTH": "health_outcomes",
    "OBESITY": "health_risk_behaviors",
    "CSMOKING": "health_risk_behaviors",
    "ACCESS2": "health_status",
    "CHECKUP": "prevention",
    "DEPRESSION": "health_outcomes",
}

UPSERT_SQL = """
    INSERT INTO cdc_health_outcomes
        (id, fips_code, geography_type,
         geography_name, state_fips, year,
         measure, category, data_value,
         data_value_type,
         low_confidence_limit,
         high_confidence_limit,
         total_population)
    VALUES
        (CAST(%(id)s AS UUID), %(fips)s, 'county',
         %(geo_name)s, %(state_fips)s, %(year)s,
         %(measure)s, %(category)s, %(value)s,
         %(dvt)s, %(low_cl)s, %(high_cl)s, %(pop)s)
    ON CONFLICT (fips_code, year, measure,
                 data_value_type)
    DO UPDATE SET
        data_value = %(value)s,
        low_confidence_limit = %(low_cl)s,
        high_confidence_limit = %(high_cl)s,
        total_population = %(pop)s,
        geography_name = %(geo_name)s
"""


def main():
    year = int(os.environ.get("CDC_PLACES_YEAR", "2023"))

    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    records_ingested = 0
    states_seen = set()
    measures_seen = set()

    print(f"Fetching CDC PLACES data for year={year}")

    try:
        with httpx.Client(timeout=60) as client:
            for measure in CDC_MEASURES:
                offset = 0
                limit = 5000
                while True:
                    # Use raw URL string to avoid $-sign encoding issues
                    url = (
                        f"{CDC_PLACES_URL}"
                        f"?$where=year='{year}' AND measureid='{measure}'"
                        f"&$limit={limit}"
                        f"&$offset={offset}"
                        f"&$select=year,stateabbr,statedesc,locationname,"
                        f"locationid,measureid,measure,"
                        f"data_value,data_value_type,low_confidence_limit,"
                        f"high_confidence_limit,totalpopulation,category"
                    )
                    resp = client.get(url)
                    resp.raise_for_status()
                    rows = resp.json()

                    if not rows:
                        break

                    batch = []
                    for row in rows:
                        fips = row.get("locationid")
                        data_val = row.get("data_value")
                        if not fips or data_val is None:
                            continue
                        value = safe_float(data_val)
                        if value is None:
                            continue

                        state_abbr = row.get("stateabbr", "")
                        state_fips = fips[:2]
                        states_seen.add(state_abbr)
                        measures_seen.add(measure)

                        dvt = row.get("data_value_type", "Crude prevalence")

                        batch.append({
                            "id": make_record_id(
                                "cdc", fips, str(year), measure,
                                row.get("data_value_type", "crude"),
                            ),
                            "fips": fips,
                            "geo_name": row.get("locationname", ""),
                            "state_fips": state_fips,
                            "year": year,
                            "measure": MEASURE_NAMES.get(
                                measure, measure.lower()
                            ),
                            "category": MEASURE_CATEGORIES.get(
                                measure, "other"
                            ),
                            "value": value,
                            "dvt": dvt,
                            "low_cl": safe_float(
                                row.get("low_confidence_limit")
                            ),
                            "high_cl": safe_float(
                                row.get("high_confidence_limit")
                            ),
                            "pop": safe_int(
                                row.get("totalpopulation")
                            ),
                        })

                    if batch:
                        execute_batch(cur, UPSERT_SQL, batch)
                        conn.commit()
                        records_ingested += len(batch)

                    print(
                        f"  {measure}: fetched {len(rows)} rows "
                        f"(offset={offset})"
                    )
                    if len(rows) < limit:
                        break
                    offset += limit
    finally:
        cur.close()
        conn.close()

    print(
        f"Ingested {records_ingested} CDC PLACES records "
        f"across {len(states_seen)} states"
    )
    print(f"Measures covered: {sorted(measures_seen)}")
    return records_ingested


if __name__ == "__main__":
    main()
