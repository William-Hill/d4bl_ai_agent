"""DOE Civil Rights Data Collection (CRDC) ingestion script.

Fetches school discipline, AP enrollment, and chronic absenteeism data
disaggregated by race from the DOE Office for Civil Rights bulk CSV
download and upserts into the doe_civil_rights table.

Usage:
    DATABASE_URL=postgresql://... python scripts/ingestion/ingest_doe_education.py

Environment variables:
    DATABASE_URL          - PostgreSQL connection URL (required)
    CRDC_SCHOOL_YEAR      - School year string (default: 2020-2021)
    CRDC_DOWNLOAD_URL     - Override download URL (default: CRDC bulk ZIP)
"""

import csv
import io
import os
import zipfile

import httpx

from .helpers import (
    get_db_connection, execute_batch, make_record_id,
)

# Bulk CSV download URL for CRDC data
CRDC_BASE_URL = (
    "https://ocrdata.ed.gov/assets/downloads/crdc-2020-2021.zip"
)

# Column-name mapping: maps CSV header fragments to (metric, race) tuples.
_METRIC_COLUMN_PREFIXES = {
    "SCH_DISCWODIS_ISS": "in_school_suspensions",
    "SCH_DISCWDIS_ISS": "in_school_suspensions",
    "SCH_DISCWODIS_OSS": "out_of_school_suspensions",
    "SCH_DISCWDIS_OSS": "out_of_school_suspensions",
    "SCH_DISCWODIS_EXPWE": "expulsions",
    "SCH_DISCWODIS_EXPWOE": "expulsions",
    "SCH_DISCWDIS_EXPWE": "expulsions",
    "SCH_DISCWDIS_EXPWOE": "expulsions",
    "TOT_APEXAM": "ap_enrollment",
    "TOT_APENR": "ap_enrollment",
    "SCH_APEXAM": "ap_enrollment",
    "SCH_APENR": "ap_enrollment",
    "TOT_ABSENT": "chronic_absenteeism",
    "SCH_ABSENT": "chronic_absenteeism",
}

# CRDC race suffixes
_RACE_SUFFIXES = {
    "_WH": "White",
    "_BL": "Black",
    "_HI": "Hispanic",
    "_AS": "Asian",
    "_AM": "AIAN",
    "_HP": "NHPI",
    "_TR": "Two_or_more",
}

UPSERT_SQL = """
    INSERT INTO doe_civil_rights
        (id, district_id, district_name,
         state, state_name, school_year,
         metric, race, value)
    VALUES
        (%(id)s::UUID, %(district_id)s,
         %(district_name)s, %(state)s,
         %(state_name)s, %(school_year)s,
         %(metric)s, %(race)s, %(value)s)
    ON CONFLICT (district_id, school_year, metric, race)
    DO UPDATE SET
        value = EXCLUDED.value,
        district_name = EXCLUDED.district_name,
        state = EXCLUDED.state,
        state_name = EXCLUDED.state_name
"""

def _parse_crdc_row(row: dict, school_year: str) -> list[dict]:
    """Parse a single CRDC CSV row into a list of metric records."""
    records = []
    district_id = row.get("LEA_STATE_LEAID", row.get("LEAID", ""))
    district_name = row.get("LEA_NAME", "")
    state = row.get("LEA_STATE", "")
    state_name = row.get("LEA_STATENAME", state)

    if not district_id:
        return records

    for col_name, raw_value in row.items():
        if raw_value is None or str(raw_value).strip() in ("", "-9", "-2"):
            continue

        col_upper = col_name.upper()
        matched_metric = None
        matched_race = None

        for prefix, metric in _METRIC_COLUMN_PREFIXES.items():
            if col_upper.startswith(prefix):
                suffix = col_upper[len(prefix):]
                for race_suffix, race in _RACE_SUFFIXES.items():
                    if suffix.endswith(race_suffix):
                        matched_metric = metric
                        matched_race = race
                        break
                break

        if not matched_metric or not matched_race:
            continue

        try:
            value = float(str(raw_value).strip())
        except (ValueError, TypeError):
            continue

        records.append({
            "district_id": str(district_id).strip(),
            "district_name": district_name.strip(),
            "state": state.strip(),
            "state_name": state_name.strip(),
            "school_year": school_year,
            "metric": matched_metric,
            "race": matched_race,
            "value": value,
        })

    return records


def main() -> int:
    school_year = os.environ.get("CRDC_SCHOOL_YEAR", "2020-2021")
    download_url = os.environ.get("CRDC_DOWNLOAD_URL", CRDC_BASE_URL)

    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    records_ingested = 0
    states_seen = set()
    metrics_seen = set()
    races_seen = set()

    print(f"Fetching CRDC data for school_year={school_year} from {download_url}")

    try:
        with httpx.Client(timeout=300, follow_redirects=True) as client:
            resp = client.get(download_url)
            if resp.status_code != 200:
                print(
                    f"CRDC download failed with status {resp.status_code}. "
                    f"CRDC bulk data may not be available at this URL. Skipping."
                )
                return 0
            content_bytes = resp.content

        # Handle ZIP or plain CSV
        csv_text = None
        if download_url.endswith(".zip"):
            try:
                zf = zipfile.ZipFile(io.BytesIO(content_bytes))
            except zipfile.BadZipFile:
                print(
                    "CRDC download is not a valid ZIP file. "
                    "The DOE may have changed the download URL. "
                    "Set CRDC_DOWNLOAD_URL env var to override. Skipping."
                )
                return 0
            with zf:
                csv_names = [
                    n for n in zf.namelist()
                    if n.lower().endswith(".csv")
                ]
                if not csv_names:
                    print("No CSV files found in CRDC ZIP archive.")
                    return 0
                # Prefer CSV whose name contains the school year
                chosen = csv_names[0]
                for name in csv_names:
                    if school_year.replace("-", "") in name or school_year in name:
                        chosen = name
                        break
                csv_text = zf.read(chosen).decode("utf-8", errors="replace")
                print(f"Extracted {chosen} from ZIP ({len(csv_names)} CSVs total)")
        else:
            csv_text = content_bytes.decode("utf-8", errors="replace")

        reader = csv.DictReader(io.StringIO(csv_text))

        batch = []
        for row in reader:
            parsed = _parse_crdc_row(row, school_year)

            for rec in parsed:
                batch.append({
                    "id": make_record_id(
                        "crdc", rec["district_id"],
                        rec["school_year"],
                        rec["metric"], rec["race"],
                    ),
                    "district_id": rec["district_id"],
                    "district_name": rec["district_name"],
                    "state": rec["state"],
                    "state_name": rec["state_name"],
                    "school_year": rec["school_year"],
                    "metric": rec["metric"],
                    "race": rec["race"],
                    "value": rec["value"],
                })
                states_seen.add(rec["state"])
                metrics_seen.add(rec["metric"])
                races_seen.add(rec["race"])

            if len(batch) >= 500:
                execute_batch(cur, UPSERT_SQL, batch)
                conn.commit()
                records_ingested += len(batch)
                print(f"  Committed batch: {records_ingested} records so far")
                batch = []

        # Flush remaining batch
        if batch:
            execute_batch(cur, UPSERT_SQL, batch)
            conn.commit()
            records_ingested += len(batch)

    except httpx.HTTPError as exc:
        print(f"CRDC download failed: {exc}. Skipping.")
        return 0
    finally:
        cur.close()
        conn.close()

    print(
        f"Ingested {records_ingested} CRDC records "
        f"across {len(states_seen)} states, "
        f"{len(metrics_seen)} metrics, {len(races_seen)} races"
    )
    return records_ingested


if __name__ == "__main__":
    main()
