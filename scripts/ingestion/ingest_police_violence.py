"""Mapping Police Violence incidents ingestion script.

Fetches police violence incident data from the Mapping Police Violence
dataset (Excel/CSV) and upserts into the police_violence_incidents table.

Usage:
    DAGSTER_POSTGRES_URL=postgresql://... python scripts/ingestion/ingest_police_violence.py

Environment variables:
    DAGSTER_POSTGRES_URL  - PostgreSQL connection URL (required)
    MPV_DATA_URL          - Override download URL
                            (default: https://mappingpoliceviolence.us/s/MPVDatasetDownload.xlsx)
"""

import csv
import hashlib
import io
import os
from datetime import datetime

import httpx

from .helpers import (
    get_db_connection, execute_batch, make_record_id, safe_int,
)

MPV_DEFAULT_URL = "https://mappingpoliceviolence.us/s/MPVDatasetDownload.xlsx"

UPSERT_SQL = """
    INSERT INTO police_violence_incidents
        (id, incident_id, date, year, state, city,
         race, age, gender,
         armed_status, cause_of_death, agency)
    VALUES
        (%(id)s::UUID, %(incident_id)s,
         %(date)s::DATE,
         %(year)s, %(state)s, %(city)s,
         %(race)s, %(age)s, %(gender)s,
         %(armed_status)s, %(cause_of_death)s, %(agency)s)
    ON CONFLICT (incident_id)
    DO UPDATE SET
        date = EXCLUDED.date,
        year = EXCLUDED.year,
        state = EXCLUDED.state,
        city = EXCLUDED.city,
        race = EXCLUDED.race,
        age = EXCLUDED.age,
        gender = EXCLUDED.gender,
        armed_status = EXCLUDED.armed_status,
        cause_of_death = EXCLUDED.cause_of_death,
        agency = EXCLUDED.agency
"""

MPV_BATCH_SIZE = 1000


def _derive_incident_id(date: str, name: str, city: str, state: str) -> str:
    """Derive a stable incident ID from key fields using SHA-256."""
    raw = f"{date}:{name}:{city}:{state}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _get(row, *keys, default=""):
    """Get the first non-empty value from a row using multiple possible keys."""
    for k in keys:
        val = row.get(k)
        if val is not None and str(val).strip():
            return str(val).strip()
    return default


def _parse_date(date_raw):
    """Parse a date string into (iso_date, year) tuple."""
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(date_raw, fmt)
            return parsed.strftime("%Y-%m-%d"), parsed.year
        except ValueError:
            continue

    # Fallback: try to extract year at least
    year = None
    for part in date_raw.replace("-", "/").split("/"):
        try:
            val = int(part)
            if val > 1900:
                year = val
                break
        except ValueError:
            continue

    return date_raw, year


def main():
    mpv_url = os.environ.get("MPV_DATA_URL", MPV_DEFAULT_URL)

    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    records_ingested = 0
    states_seen = set()
    races_seen = set()
    years_seen = set()

    print(f"Downloading MPV data from {mpv_url}")

    try:
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            resp = client.get(mpv_url)
            if resp.status_code != 200:
                print(f"Download failed with status {resp.status_code}")
                return 0

            content_type = resp.headers.get("Content-Type", "")
            raw_bytes = resp.content

        # Handle Excel or CSV formats
        if (
            "spreadsheet" in content_type
            or "excel" in content_type
            or mpv_url.endswith(".xlsx")
            or mpv_url.endswith(".xls")
        ):
            import openpyxl

            wb = openpyxl.load_workbook(
                io.BytesIO(raw_bytes), read_only=True
            )
            ws = wb.active
            rows_iter = ws.iter_rows(values_only=True)
            header = [
                str(h).strip().lower() if h else ""
                for h in next(rows_iter)
            ]
            rows = [dict(zip(header, row)) for row in rows_iter]
        else:
            text_data = raw_bytes.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text_data))
            rows = [
                {k.strip().lower(): v for k, v in row.items()}
                for row in reader
            ]

        print(f"Parsed {len(rows)} rows from source data")

        batch = []
        for row in rows:
            name = _get(
                row, "victim's name", "name",
                "victims name", "victim name",
            )
            date_raw = _get(
                row, "date of incident (month/day/year)",
                "date", "date of incident",
            )
            city = _get(row, "city", "location_city")
            state = _get(
                row, "state", "location_state", "state_abbr"
            )
            race = _get(
                row, "victim's race",
                "race", "victims race", "victim race",
                default="Unknown",
            )
            age = _get(
                row, "victim's age", "age",
                "victims age", "victim age",
            )
            gender = _get(
                row, "victim's gender", "gender",
                "victims gender", "victim gender",
                default="Unknown",
            )
            armed_status = _get(
                row, "armed/unarmed status",
                "armed_status", "armed/unarmed",
                "allegedly armed", default="Unknown",
            )
            cause = _get(
                row, "cause of death",
                "cause_of_death", "manner of death",
                default="Unknown",
            )
            agency = _get(
                row, "agency responsible for death",
                "agency", "department", "agency_name",
                default="Unknown",
            )

            if not date_raw or not name:
                continue

            # Truncate string fields to fit varchar(200) columns
            name = name[:200]
            city = city[:200]
            state = state[:200]
            race = race[:200]
            gender = gender[:200]
            armed_status = armed_status[:200]
            cause = cause[:200]
            agency = agency[:200]

            date_iso, year = _parse_date(date_raw)

            # Use the normalized ISO date for a stable ID
            date_for_id = date_iso if date_iso != date_raw else "unknown"
            incident_id = _derive_incident_id(date_for_id, name, city, state)

            # Parse age as integer
            age_int = safe_int(age)

            states_seen.add(state)
            races_seen.add(race)
            if year:
                years_seen.add(year)

            batch.append({
                "id": make_record_id("mpv", incident_id),
                "incident_id": incident_id,
                "date": date_iso,
                "year": year,
                "state": state,
                "city": city,
                "race": race,
                "age": age_int,
                "gender": gender,
                "armed_status": armed_status,
                "cause_of_death": cause,
                "agency": agency,
            })

            if len(batch) >= MPV_BATCH_SIZE:
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
        print(f"Download failed: {exc}")
        return records_ingested
    finally:
        cur.close()
        conn.close()

    print(
        f"Ingested {records_ingested} police violence incident records "
        f"across {len(states_seen)} states, "
        f"years {sorted(years_seen) if years_seen else 'N/A'}"
    )
    return records_ingested


if __name__ == "__main__":
    main()
