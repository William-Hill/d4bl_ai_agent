# BJS Incarceration Ingestion Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest Bureau of Justice Statistics incarceration data from annual CSV publications into the existing `bjs_incarceration` table, and expose it through the explore UI.

**Architecture:** Download the BJS "Prisoners in 20XX" zip archive, parse 6 CSV files covering prisoner populations by race/state, imprisonment rates, admissions, and releases. Upsert normalized records using the existing `metric` + `value` schema. Add a `/api/explore/bjs` endpoint and frontend data source config entry.

**Tech Stack:** Python (httpx, psycopg2, csv, zipfile), FastAPI, Next.js/TypeScript

**Spec:** `docs/superpowers/specs/2026-03-14-bjs-incarceration-ingestion-design.md`

---

## Chunk 1: Ingestion Script with CSV Parsing

### Task 1: CSV parsing helpers with tests

**Files:**
- Create: `scripts/ingestion/bjs_csv_parser.py`
- Create: `tests/test_bjs_csv_parser.py`

This module handles all BJS CSV parsing quirks: header skipping, comma-formatted numbers, footnote stripping, sentinel values. Each table gets a dedicated parse function returning normalized record dicts.

- [ ] **Step 1: Write failing tests for CSV utility functions**

Create `tests/test_bjs_csv_parser.py`:

```python
"""Tests for BJS CSV parsing helpers."""

from scripts.ingestion.bjs_csv_parser import (
    clean_jurisdiction,
    clean_number,
    STATE_NAME_TO_ABBREV,
)


class TestCleanNumber:
    def test_plain_integer(self):
        assert clean_number("12345") == 12345.0

    def test_comma_formatted(self):
        assert clean_number("1,520,403") == 1520403.0

    def test_quoted_comma(self):
        assert clean_number('"1,520,403"') == 1520403.0

    def test_not_reported(self):
        assert clean_number("/") is None

    def test_not_applicable(self):
        assert clean_number("~") is None

    def test_less_than(self):
        assert clean_number("--") is None

    def test_empty(self):
        assert clean_number("") is None

    def test_float_value(self):
        assert clean_number("479") == 479.0


class TestCleanJurisdiction:
    def test_plain_state(self):
        assert clean_jurisdiction("Alabama") == "Alabama"

    def test_footnote_suffix(self):
        assert clean_jurisdiction("Alabama/d") == "Alabama"

    def test_multi_footnote(self):
        assert clean_jurisdiction("Illinois/d,g") == "Illinois"

    def test_quoted_with_footnote(self):
        assert clean_jurisdiction('"Illinois/d,g"') == "Illinois"

    def test_federal(self):
        assert clean_jurisdiction("Federal/c") == "Federal"

    def test_rhode_island_no_space(self):
        # The CSV has "Rhode Islande" (footnote 'e' without slash)
        assert clean_jurisdiction("Rhode Islande") == "Rhode Island"

    def test_virginia_suffix(self):
        # The CSV has "Virginial" (footnote 'l' without slash)
        assert clean_jurisdiction("Virginial") == "Virginia"


class TestStateMapping:
    def test_all_50_states_plus_dc(self):
        assert len(STATE_NAME_TO_ABBREV) >= 51

    def test_alabama(self):
        assert STATE_NAME_TO_ABBREV["Alabama"] == "AL"

    def test_wyoming(self):
        assert STATE_NAME_TO_ABBREV["Wyoming"] == "WY"

    def test_dc(self):
        assert STATE_NAME_TO_ABBREV["District of Columbia"] == "DC"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_bjs_csv_parser.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement utility functions and state mapping**

Create `scripts/ingestion/bjs_csv_parser.py`:

```python
"""BJS CSV parsing helpers.

Handles quirks of Bureau of Justice Statistics CSV formatting:
header rows, comma-formatted numbers, footnote markers, sentinel values.
"""

from __future__ import annotations

import re

# Sentinel values that mean "no data"
_SKIP_VALUES = frozenset({"", "/", "~", "--"})

# Footnote patterns: "Alabama/d", "Illinois/d,g", or stuck-on like "Virginial"
_FOOTNOTE_SLASH = re.compile(r"/[a-z,*]+$")
# Known cases where footnote letter is appended without a slash
_STUCK_FOOTNOTES: dict[str, str] = {
    "Rhode Islande": "Rhode Island",
    "Virginial": "Virginia",
}


STATE_NAME_TO_ABBREV: dict[str, str] = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI",
    "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
    "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME",
    "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE",
    "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
    "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH",
    "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}

# Rows to skip when parsing state-level tables
_SKIP_ROWS = frozenset({
    "Northeast", "Midwest", "South", "West",
    "Percent change", "Note:", "Source:", "",
})


def clean_number(val: str) -> float | None:
    """Parse a BJS-formatted number, returning None for sentinel values."""
    val = val.strip().strip('"')
    if val in _SKIP_VALUES:
        return None
    try:
        return float(val.replace(",", ""))
    except ValueError:
        return None


def clean_jurisdiction(name: str) -> str:
    """Strip footnote markers from a jurisdiction name."""
    name = name.strip().strip('"')
    # Check stuck-on footnotes first
    if name in _STUCK_FOOTNOTES:
        return _STUCK_FOOTNOTES[name]
    # Strip /x,y suffixes
    name = _FOOTNOTE_SLASH.sub("", name)
    return name


def should_skip_row(first_cell: str) -> bool:
    """Return True if this row is a header, footer, region, or blank."""
    cell = first_cell.strip().strip('"')
    if not cell:
        return True
    for prefix in _SKIP_ROWS:
        if cell.startswith(prefix):
            return True
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_bjs_csv_parser.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/ingestion/bjs_csv_parser.py tests/test_bjs_csv_parser.py
git commit -m "feat(bjs): add CSV parsing helpers with tests (#92)"
```

---

### Task 2: Table parsers with tests

**Files:**
- Modify: `scripts/ingestion/bjs_csv_parser.py`
- Modify: `tests/test_bjs_csv_parser.py`

Add parse functions for each of the 6 target CSV tables. Each returns a list of normalized record dicts matching the `bjs_incarceration` schema.

- [ ] **Step 1: Write failing tests for table parsers**

Add to `tests/test_bjs_csv_parser.py`:

```python
import csv
import io
import textwrap

from scripts.ingestion.bjs_csv_parser import (
    parse_table3_sentenced,
    parse_appendix_table1,
    parse_admissions_releases,
)


# Minimal CSV content mimicking BJS format (8 header rows + blank + title + column header + data)
TABLE3_CSV = textwrap.dedent("""\
    Bureau of Justice Statistics,,,,,,,,,,,,,,,,,,,,,
    Filename: p23stt03.csv,,,,,,,,,,,,,,,,,,,,,
    Title,,,,,,,,,,,,,,,,,,,,,
    Report,,,,,,,,,,,,,,,,,,,,,
    Data source,,,,,,,,,,,,,,,,,,,,,
    Authors,,,,,,,,,,,,,,,,,,,,,
    Contact,,,,,,,,,,,,,,,,,,,,,
    Date,,,,,,,,,,,,,,,,,,,,,
    ,,,,,,,,,,,,,,,,,,,,,
    Title repeated,,,,,,,,,,,,,,,,,,,,,
    Year,,Total/a,,Federal/b,,State,,Male,,Female,,"White/c,d",,"Black/c,d",,Hispanic/d,,"American Indian/Alaska Native/c,d",,"Asian/c,d,e",
    2023,,"1,210,308",,"143,297",,"1,067,011",,"1,124,435",,"85,873",,"370,500",,"394,500",,"282,700",,"19,700",,"15,200",
    Percent change,,,,,,,,,,,,,,,,,,,,,
""")

APPENDIX_CSV = textwrap.dedent("""\
    Bureau of Justice Statistics,,,,,,,,,,,,,,,,,,,,,,,,,
    Filename,,,,,,,,,,,,,,,,,,,,,,,,,
    Title,,,,,,,,,,,,,,,,,,,,,,,,,
    Report,,,,,,,,,,,,,,,,,,,,,,,,,
    Source,,,,,,,,,,,,,,,,,,,,,,,,,
    Authors,,,,,,,,,,,,,,,,,,,,,,,,,
    Contact,,,,,,,,,,,,,,,,,,,,,,,,,
    Date,,,,,,,,,,,,,,,,,,,,,,,,,
    ,,,,,,,,,,,,,,,,,,,,,,,,,
    Title,,,,,,,,,,,,,,,,,,,,,,,,,
    Jurisdiction,,Total,White/a,Black/a,Hispanic,American Indian/Alaska Native/a,Asian/a,Native Hawaiian/Other Pacific Islander/a,Two or more races/a,Other/a,Unknown,Did not report,,,,,,,,,,,,,
    Federal/b,,"156,627","47,472","57,542","45,684","3,839","2,091",/,/,~,~,0,,,,,,,,,,,,,
    State,,,,,,,,,,,,,,,,,,,,,,,,,
    ,Alabama,"27,181","12,341","14,548",0,1,10,0,0,0,281,0,,,,,,,,,,,,,
    ,California,"95,962","19,150","26,520","44,166","1,111","1,145",336,~,"3,534",~,0,,,,,,,,,,,,,
    Note:,,,,,,,,,,,,,,,,,,,,,,,,,
""")

TABLE8_CSV = textwrap.dedent("""\
    Bureau of Justice Statistics,,,,,,,,,,
    Filename,,,,,,,,,,
    Title,,,,,,,,,,
    Report,,,,,,,,,,
    Source,,,,,,,,,,
    Authors,,,,,,,,,,
    Contact,,,,,,,,,,
    Date,,,,,,,,,,
    ,,,,,,,,,,
    Title,,,,,,,,,,
    Jurisdiction,,2022 total ,2023 total,Change,Percent change,,2022 new court commitments,2023 new court commitments,2022 conditional supervision violations/a,2023 conditional supervision violations/a
    ,U.S. total/b,"469,217","472,278","3,061",0.7,%,"346,518","350,628","112,045","111,385"
    Federal/c,,"44,873","42,221","-2,652",-5.9,%,"38,440","36,026","6,433","6,195"
    State/b,,"424,344","430,057","5,713",1.3,%,"308,078","314,602","105,612","105,190"
    ,Alabama/d,"9,515","9,786",271,2.8,,"7,363","7,885",496,348
    Note:,,,,,,,,,,
""")


class TestParseTable3:
    def test_basic_parsing(self):
        reader = csv.reader(io.StringIO(TABLE3_CSV))
        records = parse_table3_sentenced(reader, data_year=2023)

        # Should produce records for year 2023 with total, federal, state
        # breakdowns across 6 races x 3 genders (+ total for each)
        assert len(records) > 0

        # Check a specific record
        total_pop = [r for r in records
                     if r["metric"] == "sentenced_population"
                     and r["race"] == "total"
                     and r["gender"] == "total"
                     and r["year"] == 2023]
        assert len(total_pop) == 1
        assert total_pop[0]["value"] == 1210308.0
        assert total_pop[0]["state_abbrev"] == "US"

    def test_race_breakdown(self):
        reader = csv.reader(io.StringIO(TABLE3_CSV))
        records = parse_table3_sentenced(reader, data_year=2023)

        black = [r for r in records
                 if r["metric"] == "sentenced_population"
                 and r["race"] == "black"
                 and r["gender"] == "total"
                 and r["year"] == 2023]
        assert len(black) == 1
        assert black[0]["value"] == 394500.0


class TestParseAppendixTable1:
    def test_state_rows(self):
        reader = csv.reader(io.StringIO(APPENDIX_CSV))
        records = parse_appendix_table1(reader, data_year=2023)

        al_total = [r for r in records
                    if r["state_abbrev"] == "AL"
                    and r["race"] == "total"]
        assert len(al_total) == 1
        assert al_total[0]["value"] == 27181.0
        assert al_total[0]["metric"] == "total_population"

    def test_race_breakdown(self):
        reader = csv.reader(io.StringIO(APPENDIX_CSV))
        records = parse_appendix_table1(reader, data_year=2023)

        al_black = [r for r in records
                    if r["state_abbrev"] == "AL"
                    and r["race"] == "black"]
        assert len(al_black) == 1
        assert al_black[0]["value"] == 14548.0

    def test_skips_federal_and_state_header(self):
        reader = csv.reader(io.StringIO(APPENDIX_CSV))
        records = parse_appendix_table1(reader, data_year=2023)
        # Federal row is kept with state_abbrev "US"
        federal = [r for r in records if r["state_abbrev"] == "US"]
        assert len(federal) > 0
        # "State" header row should be skipped
        state_header = [r for r in records if r["state_name"] == "State"]
        assert len(state_header) == 0

    def test_skip_sentinel_values(self):
        reader = csv.reader(io.StringIO(APPENDIX_CSV))
        records = parse_appendix_table1(reader, data_year=2023)
        # California has ~ for some races — those should be skipped
        ca_records = [r for r in records if r["state_abbrev"] == "CA"]
        # Should not have records for races where value is ~
        for r in ca_records:
            assert r["value"] is not None


class TestParseAdmissionsReleases:
    def test_admissions(self):
        reader = csv.reader(io.StringIO(TABLE8_CSV))
        # metric_map uses RAW column indices (not stripped)
        # Raw layout: 0=empty, 1=jurisdiction, 2=2022_total, 3=2023_total,
        #             4=change, 5=pct_change, 6=empty, 7=2022_ncc,
        #             8=2023_ncc, 9=2022_viol, 10=2023_viol
        records = parse_admissions_releases(
            reader,
            metric_map={
                2: ("admissions_total", 2022),
                3: ("admissions_total", 2023),
                7: ("admissions_new_court_commitment", 2022),
                8: ("admissions_new_court_commitment", 2023),
                9: ("admissions_supervision_violations", 2022),
                10: ("admissions_supervision_violations", 2023),
            },
        )

        al_2023 = [r for r in records
                   if r["state_abbrev"] == "AL"
                   and r["year"] == 2023
                   and r["metric"] == "admissions_total"]
        assert len(al_2023) == 1
        assert al_2023[0]["value"] == 9786.0
        assert al_2023[0]["race"] == "total"
        assert al_2023[0]["gender"] == "total"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_bjs_csv_parser.py -v -k "ParseTable or ParseAppendix or ParseAdmissions"`
Expected: FAIL — functions not found

- [ ] **Step 3: Implement table parsers**

Add to `scripts/ingestion/bjs_csv_parser.py`:

```python
import csv
from typing import Iterator

# Number of metadata header rows in BJS CSVs (before column headers)
HEADER_ROWS = 10

# Race column mapping for Appendix Table 1
RACE_LABELS_APPENDIX = [
    "total", "white", "black", "hispanic", "aian", "asian",
    "nhpi", "two_or_more", "other", "unknown", "did_not_report",
]


def _skip_header(reader: Iterator[list[str]], n: int = HEADER_ROWS) -> None:
    """Consume n rows from the reader (header/metadata rows)."""
    for _ in range(n):
        try:
            next(reader)
        except StopIteration:
            break


def _strip_empty(row: list[str]) -> list[str]:
    """Remove empty interleaving columns from a BJS CSV row."""
    return [c for c in row if c.strip()]


def _parse_national_table(
    reader: Iterator[list[str]], metric_base: str,
) -> list[dict]:
    """Parse Tables 3/5/6: national data by race x sex (same column layout).

    Column layout (with empty interleaving columns stripped):
    Year, Total, Federal, State, Male, Female, White, Black, Hispanic, AIAN, Asian

    Tables 5/6 have an extra sub-header row ("Per 100,000...") that is
    harmlessly skipped because clean_number returns None for text.
    """
    _skip_header(reader)
    # Skip column header row (and any sub-header — text rows are skipped
    # by the year_val is None guard below)
    try:
        next(reader)
    except StopIteration:
        return []

    records: list[dict] = []

    # (stripped_col_index, metric_suffix, gender, race)
    col_defs = [
        (1, "", "total", "total"),         # Total
        (2, "_federal", "total", "total"),  # Federal
        (3, "_state", "total", "total"),    # State
        (4, "", "male", "total"),           # Male
        (5, "", "female", "total"),         # Female
        (6, "", "total", "white"),          # White
        (7, "", "total", "black"),          # Black
        (8, "", "total", "hispanic"),       # Hispanic
        (9, "", "total", "aian"),           # AIAN
        (10, "", "total", "asian"),         # Asian
    ]

    for row in reader:
        cells = _strip_empty(row)
        if not cells or should_skip_row(cells[0]):
            break

        year_val = clean_number(cells[0])
        if year_val is None:
            continue
        year = int(year_val)

        for col_idx, metric_suffix, gender, race in col_defs:
            if col_idx >= len(cells):
                continue
            value = clean_number(cells[col_idx])
            if value is None:
                continue
            records.append({
                "state_abbrev": "US",
                "state_name": "United States",
                "year": year,
                "facility_type": "prison",
                "metric": f"{metric_base}{metric_suffix}",
                "race": race,
                "gender": gender,
                "value": value,
            })

    return records


def parse_table3_sentenced(reader: Iterator[list[str]], data_year: int) -> list[dict]:
    """Parse Table 3: sentenced prisoner counts."""
    return _parse_national_table(reader, "sentenced_population")


def parse_table5_rates(reader: Iterator[list[str]], data_year: int) -> list[dict]:
    """Parse Table 5: imprisonment rates (all ages)."""
    return _parse_national_table(reader, "imprisonment_rate_all_ages")


def parse_table6_rates(reader: Iterator[list[str]], data_year: int) -> list[dict]:
    """Parse Table 6: imprisonment rates (adults)."""
    return _parse_national_table(reader, "imprisonment_rate_adult")


def parse_appendix_table1(reader: Iterator[list[str]], data_year: int) -> list[dict]:
    """Parse Appendix Table 1: prisoners by jurisdiction and race."""
    _skip_header(reader)
    # Skip column header row
    try:
        next(reader)
    except StopIteration:
        return []

    records: list[dict] = []
    # Only ingest these races (skip nhpi, two_or_more, other, unknown, did_not_report)
    target_races = {"total", "white", "black", "hispanic", "aian", "asian"}

    for row in reader:
        if not row or should_skip_row(row[0]):
            break

        # Determine jurisdiction name and data columns
        # State rows have indent: first cell empty, jurisdiction in second cell
        # Federal row: "Federal/b" in first cell
        first = row[0].strip().strip('"')
        second = row[1].strip().strip('"') if len(row) > 1 else ""

        if first and clean_jurisdiction(first).startswith("Federal"):
            jurisdiction = "Federal"
            data_start = 2  # data starts at column 2
        elif first and clean_jurisdiction(first) == "State":
            continue  # Skip "State" section header
        elif not first and second:
            jurisdiction = clean_jurisdiction(second)
            data_start = 2
        else:
            continue

        # Map jurisdiction to state abbreviation
        if jurisdiction == "Federal":
            state_abbrev = "US"
            state_name = "United States (Federal)"
        else:
            state_abbrev = STATE_NAME_TO_ABBREV.get(jurisdiction)
            if not state_abbrev:
                continue  # Skip unknown jurisdictions
            state_name = jurisdiction

        # Extract race values: Total, White, Black, Hispanic, AIAN, Asian, ...
        # Column order matches RACE_LABELS_APPENDIX
        for i, race_label in enumerate(RACE_LABELS_APPENDIX):
            if race_label not in target_races:
                continue
            col_idx = data_start + i
            if col_idx >= len(row):
                continue
            value = clean_number(row[col_idx])
            if value is None:
                continue
            records.append({
                "state_abbrev": state_abbrev,
                "state_name": state_name,
                "year": data_year,
                "facility_type": "prison",
                "metric": "total_population",
                "race": race_label,
                "gender": "total",
                "value": value,
            })

    return records


def parse_admissions_releases(
    reader: Iterator[list[str]],
    metric_map: dict[int, tuple[str, int]],
) -> list[dict]:
    """Parse Tables 8/9: admissions or releases by jurisdiction.

    metric_map maps RAW column index (0-based in the original CSV row)
    to (metric_name, year). We use raw indices (not stripped) because
    the empty separator columns appear inconsistently between aggregate
    and state rows (the % column is present in aggregate rows but empty
    in state rows), which would shift stripped indices.
    """
    _skip_header(reader)
    # Skip column header row
    try:
        next(reader)
    except StopIteration:
        return []

    records: list[dict] = []

    for row in reader:
        if not row or should_skip_row(row[0]):
            break

        first = row[0].strip().strip('"')
        second = row[1].strip().strip('"') if len(row) > 1 else ""

        # Determine jurisdiction
        if first and clean_jurisdiction(first).startswith("Federal"):
            jurisdiction = "Federal"
        elif not first and second:
            cleaned = clean_jurisdiction(second)
            if cleaned.startswith(("U.S. total", "State")):
                continue  # Skip aggregate rows
            jurisdiction = cleaned
        else:
            continue

        if jurisdiction == "Federal":
            state_abbrev = "US"
            state_name = "United States (Federal)"
        else:
            state_abbrev = STATE_NAME_TO_ABBREV.get(jurisdiction)
            if not state_abbrev:
                continue
            state_name = jurisdiction

        # Extract values using RAW column indices
        for col_idx, (metric_name, year) in metric_map.items():
            if col_idx >= len(row):
                continue
            value = clean_number(row[col_idx])
            if value is None:
                continue
            records.append({
                "state_abbrev": state_abbrev,
                "state_name": state_name,
                "year": year,
                "facility_type": "prison",
                "metric": metric_name,
                "race": "total",
                "gender": "total",
                "value": value,
            })

    return records
```

Note: `_strip_empty` is only used by `_parse_national_table` (Tables 3/5/6) where the column layout is consistent across all rows. Tables 8/9 use raw column indices via `parse_admissions_releases` to avoid the column-shifting bug caused by inconsistent empty columns between aggregate and state rows.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_bjs_csv_parser.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/ingestion/bjs_csv_parser.py tests/test_bjs_csv_parser.py
git commit -m "feat(bjs): add CSV table parsers for Tables 3/5/6/8/9 and Appendix T1 (#92)"
```

---

### Task 3: Main ingestion script

**Files:**
- Create: `scripts/ingestion/ingest_bjs_incarceration.py`

- [ ] **Step 1: Create the ingestion script**

Create `scripts/ingestion/ingest_bjs_incarceration.py`:

```python
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

# Table 8 column mapping: RAW column index -> (metric, year)
# Raw cols: 0=empty, 1=jurisdiction, 2=2022_total, 3=2023_total,
#           4=change, 5=pct_change, 6=empty, 7=2022_ncc,
#           8=2023_ncc, 9=2022_viol, 10=2023_viol
ADMISSIONS_MAP_2023 = {
    2: ("admissions_total", 2022),
    3: ("admissions_total", 2023),
    7: ("admissions_new_court_commitment", 2022),
    8: ("admissions_new_court_commitment", 2023),
    9: ("admissions_supervision_violations", 2022),
    10: ("admissions_supervision_violations", 2023),
}

# Table 9 column mapping: RAW column index -> (metric, year)
# Raw cols: 0=empty, 1=jurisdiction, 2=2022_total, 3=2023_total,
#           4=change, 5=pct_change, 6=empty, 7=2022_uncond,
#           8=2023_uncond, 9=2022_cond, 10=2023_cond,
#           11=2022_deaths, 12=2023_deaths
RELEASES_MAP_2023 = {
    2: ("releases_total", 2022),
    3: ("releases_total", 2023),
    7: ("releases_unconditional", 2022),
    8: ("releases_unconditional", 2023),
    9: ("releases_conditional", 2022),
    10: ("releases_conditional", 2023),
    11: ("releases_deaths", 2022),
    12: ("releases_deaths", 2023),
}


def _download_zip(url: str, dest: str) -> None:
    """Download a file from url to dest path."""
    print(f"  Downloading {url} ...")
    resp = httpx.get(url, follow_redirects=True, timeout=60.0)
    if resp.status_code != 200:
        print(
            f"Error: Failed to download BJS data (HTTP {resp.status_code}). "
            f"The URL pattern may have changed for this publication year. "
            f"Check https://bjs.ojp.gov/library/publications/list?series_filter=Prisoners",
            file=sys.stderr,
        )
        sys.exit(1)
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
        except zipfile.BadZipFile:
            print("Error: Downloaded file is not a valid zip archive.", file=sys.stderr)
            sys.exit(1)

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
                records = parse_admissions_releases(reader, ADMISSIONS_MAP_2023)
                print(f"  Table 8 (admissions): {len(records)} records")
                all_records.extend(records)
        else:
            print(f"  WARNING: p{yy}stt08.csv not found, skipping admissions")

        # Table 9 — Releases
        t9_path = os.path.join(tmpdir, f"p{yy}stt09.csv")
        if os.path.exists(t9_path):
            with open(t9_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                records = parse_admissions_releases(reader, RELEASES_MAP_2023)
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
    main()
```

- [ ] **Step 2: Verify script imports work**

Run: `python -c "from scripts.ingestion.ingest_bjs_incarceration import main; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add scripts/ingestion/ingest_bjs_incarceration.py
git commit -m "feat(bjs): add main ingestion script (#92)"
```

---

### Task 4: Register in dispatcher

**Files:**
- Modify: `scripts/run_ingestion.py:25-38` (SOURCES dict)
- Modify: `scripts/run_ingestion.py:142-146` (year forwarding)

- [ ] **Step 1: Add BJS to SOURCES dict**

In `scripts/run_ingestion.py`, add `"bjs": "ingest_bjs_incarceration"` to the SOURCES dict (after the `"openstates"` entry on line 37):

```python
    "openstates": "ingest_openstates",
    "bjs": "ingest_bjs_incarceration",
```

- [ ] **Step 2: Add BJS_YEAR to year forwarding**

In `scripts/run_ingestion.py`, add `"BJS_YEAR"` to the `year_vars` list (line 143-145):

```python
        year_vars = [
            "ACS_YEAR", "CDC_PLACES_YEAR", "EPA_EJSCREEN_YEAR",
            "HUD_FMR_YEAR", "USDA_FOOD_ACCESS_YEAR",
            "CENSUS_DECENNIAL_YEAR", "BJS_YEAR",
        ]
```

- [ ] **Step 3: Verify registration**

Run: `python scripts/run_ingestion.py --list`
Expected: Output includes `bjs` in the list of available sources

Run: `python scripts/run_ingestion.py --dry-run --sources bjs`
Expected: Shows `bjs` would run

- [ ] **Step 4: Commit**

```bash
git add scripts/run_ingestion.py
git commit -m "feat(bjs): register BJS in ingestion dispatcher (#92)"
```

---

## Chunk 2: Explore UI Integration

### Task 5: Backend explore endpoint

**Files:**
- Modify: `src/d4bl/app/api.py:51-68` (add import)
- Modify: `src/d4bl/app/api.py:1068-1069` (add endpoint before `/api/explore/policies`)

- [ ] **Step 1: Add BjsIncarceration import**

In `src/d4bl/app/api.py`, add `BjsIncarceration` to the import block at line 51:

```python
from d4bl.infra.database import (
    BjsIncarceration,
    BlsLaborStatistic,
    ...
```

- [ ] **Step 2: Add the explore endpoint**

Insert before the `/api/explore/policies` endpoint (before line 1070):

```python
@app.get("/api/explore/bjs", response_model=ExploreResponse)
async def get_bjs_incarceration(
    state_fips: str | None = None,
    metric: str | None = None,
    race: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bureau of Justice Statistics incarceration data."""
    try:
        query = select(BjsIncarceration).where(
            BjsIncarceration.state_abbrev != "US",
            BjsIncarceration.gender == "total",
        )
        if state_fips:
            abbrev = FIPS_TO_ABBREV.get(state_fips)
            if abbrev:
                query = query.where(BjsIncarceration.state_abbrev == abbrev)
        if metric:
            query = query.where(BjsIncarceration.metric == metric)
        if race:
            query = query.where(BjsIncarceration.race == race)
        if year:
            query = query.where(BjsIncarceration.year == year)
        query = query.order_by(BjsIncarceration.state_abbrev).limit(max(1, min(limit, 5000)))

        result = await db.execute(query)
        rows_raw = result.scalars().all()

        row_dicts = [
            {
                "state_fips": ABBREV_TO_FIPS.get(r.state_abbrev, ""),
                "state_name": r.state_name,
                "value": r.value,
                "metric": r.metric,
                "year": r.year,
                "race": r.race,
            }
            for r in rows_raw
        ]

        # Use national-level BJS data for national average if available
        nat_avg = compute_national_avg(row_dicts)

        return ExploreResponse(
            rows=[ExploreRow(**d) for d in row_dicts],
            national_average=nat_avg,
            available_metrics=distinct_values(row_dicts, "metric"),
            available_years=distinct_values(row_dicts, "year"),
            available_races=distinct_values(row_dicts, "race"),
        )
    except Exception:
        logger.error("Failed to fetch BJS incarceration data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch BJS incarceration data")
```

- [ ] **Step 3: Verify endpoint compiles**

Run: `python -c "from d4bl.app.api import app; print('OK')"`
Expected: `OK` (no import errors)

- [ ] **Step 4: Commit**

```bash
git add src/d4bl/app/api.py
git commit -m "feat(bjs): add /api/explore/bjs endpoint (#92)"
```

---

### Task 6: Frontend data source config

**Files:**
- Modify: `ui-nextjs/lib/explore-config.ts:124-133` (add config entry)

- [ ] **Step 1: Add BJS data source config**

In `ui-nextjs/lib/explore-config.ts`, add a new entry to the `DATA_SOURCES` array after the "Police Violence" entry (before the closing `];` on line 133):

```typescript
  {
    key: "bjs",
    label: "BJS Incarceration",
    accent: "#a29bfe",
    endpoint: "/api/explore/bjs",
    hasRace: true,
    primaryFilterKey: "metric",
    primaryFilterLabel: "Metric",
  },
```

- [ ] **Step 2: Verify frontend builds**

Run: `cd ui-nextjs && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add ui-nextjs/lib/explore-config.ts
git commit -m "feat(bjs): add BJS Incarceration to explore data sources (#92)"
```

---

### Task 7: Integration test

**Files:**
- Create: `tests/test_bjs_explore_endpoint.py`

- [ ] **Step 1: Write explore endpoint test**

Create `tests/test_bjs_explore_endpoint.py`:

```python
"""Smoke test for the BJS explore endpoint registration."""

import pytest


def test_bjs_endpoint_exists():
    """Verify the BJS explore endpoint is registered on the app."""
    from d4bl.app.api import app

    routes = [r.path for r in app.routes]
    assert "/api/explore/bjs" in routes


def test_bjs_frontend_config():
    """Verify BJS is in the expected frontend config shape."""
    import json
    from pathlib import Path

    config_path = Path(__file__).parent.parent / "ui-nextjs" / "lib" / "explore-config.ts"
    content = config_path.read_text()
    assert '"bjs"' in content
    assert "/api/explore/bjs" in content
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_bjs_explore_endpoint.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_bjs_explore_endpoint.py
git commit -m "test(bjs): add explore endpoint integration tests (#92)"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | CSV parsing helpers + tests | `scripts/ingestion/bjs_csv_parser.py`, `tests/test_bjs_csv_parser.py` |
| 2 | Table parsers + tests | Same files as Task 1 |
| 3 | Main ingestion script | `scripts/ingestion/ingest_bjs_incarceration.py` |
| 4 | Dispatcher registration | `scripts/run_ingestion.py` |
| 5 | Backend explore endpoint | `src/d4bl/app/api.py` |
| 6 | Frontend data source config | `ui-nextjs/lib/explore-config.ts` |
| 7 | Integration tests | `tests/test_bjs_explore_endpoint.py` |
