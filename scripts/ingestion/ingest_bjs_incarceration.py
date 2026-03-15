"""BJS National Prisoner Statistics ingestion script.

Downloads the "Prisoners in 20XX" statistical tables zip from BJS,
parses CSV files for prisoner populations, imprisonment rates,
admissions, and releases, and upserts into bjs_incarceration table.

Env vars:
    DAGSTER_POSTGRES_URL  - PostgreSQL connection URL (required)
    BJS_YEAR              - Publication data year (default: 2023)
"""

import csv
import os
import sys
import tempfile
import zipfile

import httpx

from .bjs_csv_parser import (
    parse_admissions_releases,
    parse_appendix_table1,
    parse_table3_sentenced,
    parse_table5_rates,
    parse_table6_rates,
)
from .helpers import get_db_connection, make_record_id, upsert_batch

# URL pattern: last 2 digits of the year
BJS_URL_TEMPLATE = "https://bjs.ojp.gov/document/p{yy}st.zip"

UPSERT_SQL = """\
INSERT INTO bjs_incarceration
    (id, state_abbrev, state_name, year, facility_type, metric, race, gender, value)
VALUES
    (%(id)s::UUID, %(state_abbrev)s, %(state_name)s, %(year)s,
     %(facility_type)s, %(metric)s, %(race)s, %(gender)s, %(value)s)
ON CONFLICT (state_abbrev, year, facility_type, metric, race, gender)
DO UPDATE SET value = EXCLUDED.value, state_name = EXCLUDED.state_name
"""


def _build_admissions_map(data_year: int) -> dict[int, tuple[str, int]]:
    """Build Table 8 column mapping: RAW column index -> (metric, year)."""
    prev = data_year - 1
    return {
        2: ("admissions_total", prev),
        3: ("admissions_total", data_year),
        7: ("admissions_new_court_commitment", prev),
        8: ("admissions_new_court_commitment", data_year),
        9: ("admissions_supervision_violations", prev),
        10: ("admissions_supervision_violations", data_year),
    }


def _build_releases_map(data_year: int) -> dict[int, tuple[str, int]]:
    """Build Table 9 column mapping: RAW column index -> (metric, year)."""
    prev = data_year - 1
    return {
        2: ("releases_total", prev),
        3: ("releases_total", data_year),
        7: ("releases_unconditional", prev),
        8: ("releases_unconditional", data_year),
        9: ("releases_conditional", prev),
        10: ("releases_conditional", data_year),
        11: ("releases_deaths", prev),
        12: ("releases_deaths", data_year),
    }


def _download_zip(url: str, dest: str) -> None:
    """Download a file from url to dest path."""
    print(f"  Downloading {url} ...")
    resp = httpx.get(url, follow_redirects=True, timeout=60.0)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Failed to download BJS data (HTTP {resp.status_code}). "
            "The URL pattern may have changed for this publication year."
        )
    with open(dest, "wb") as f:
        f.write(resp.content)


def _add_ids(records: list[dict]) -> list[dict]:
    """Add deterministic record IDs."""
    for r in records:
        r["id"] = make_record_id(
            "bjs",
            r["state_abbrev"],
            str(r["year"]),
            r["facility_type"],
            r["metric"],
            r["race"],
            r["gender"],
        )
    return records


def main() -> int:
    """Download BJS prisoner data, parse CSVs, and upsert records."""
    data_year = int(os.environ.get("BJS_YEAR", "2023"))
    yy = str(data_year)[-2:]

    url = BJS_URL_TEMPLATE.format(yy=yy)
    print(f"BJS Incarceration Ingestion — year {data_year}")

    conn = get_db_connection()
    total = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "bjs_data.zip")
        _download_zip(url, zip_path)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmpdir)
        except zipfile.BadZipFile as exc:
            raise RuntimeError("Downloaded file is not a valid zip archive.") from exc

        # Define CSV file -> parser mapping
        parse_tasks = [
            (f"p{yy}stt03.csv", parse_table3_sentenced, f"Table 3 (sentenced population)"),
            (f"p{yy}stt05.csv", parse_table5_rates, f"Table 5 (imprisonment rates, all ages)"),
            (f"p{yy}stt06.csv", parse_table6_rates, f"Table 6 (imprisonment rates, adults)"),
            (f"p{yy}stat01.csv", parse_appendix_table1, f"Appendix Table 1 (population by race/state)"),
        ]

        all_records: list[dict] = []

        for filename, parser, label in parse_tasks:
            filepath = os.path.join(tmpdir, filename)
            if not os.path.exists(filepath):
                print(f"  WARNING: {filename} not found in zip, skipping {label}")
                continue
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                records = parser(reader, data_year=data_year)
                print(f"  {label}: {len(records)} records")
                all_records.extend(records)

        # Table 8 — Admissions
        t8_path = os.path.join(tmpdir, f"p{yy}stt08.csv")
        if os.path.exists(t8_path):
            with open(t8_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                records = parse_admissions_releases(reader, _build_admissions_map(data_year))
                print(f"  Table 8 (admissions): {len(records)} records")
                all_records.extend(records)
        else:
            print(f"  WARNING: p{yy}stt08.csv not found, skipping admissions")

        # Table 9 — Releases
        t9_path = os.path.join(tmpdir, f"p{yy}stt09.csv")
        if os.path.exists(t9_path):
            with open(t9_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                records = parse_admissions_releases(reader, _build_releases_map(data_year))
                print(f"  Table 9 (releases): {len(records)} records")
                all_records.extend(records)
        else:
            print(f"  WARNING: p{yy}stt09.csv not found, skipping releases")

        # Add deterministic IDs and upsert
        _add_ids(all_records)
        print(f"  Total: {len(all_records)} records — upserting ...")
        total = upsert_batch(conn, UPSERT_SQL, all_records)

    conn.close()
    print(f"  Done. {total} records upserted.")
    return total


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
