"""BJS incarceration CSV parsing utilities and table parsers.

BJS CSVs follow a consistent format:
- 10 metadata/header rows before the column header row
- National tables (3, 5, 6) use empty interleaving columns between data columns
- Appendix Table 1 has state rows indented (first cell empty, jurisdiction in second cell)
- Tables 8/9 use raw column indices (not stripped) due to inconsistent empty separators
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# State name → abbreviation mapping (all 50 states + DC)
# ---------------------------------------------------------------------------

STATE_NAME_TO_ABBREV: dict[str, str] = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "District of Columbia": "DC",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
}

# Region headers to skip when parsing state tables
_REGION_HEADERS = {"Northeast", "Midwest", "South", "West"}

# Single-character lowercase footnote letters that may be appended to state names
# in BJS tables (e.g. "Rhode Islande" → "Rhode Island", "Virginial" → "Virginia")
_STUCK_FOOTNOTE_RE = re.compile(r"^(.+?)[a-z]$")


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def clean_number(val: str) -> float | None:
    """Parse a BJS-formatted number string into a float.

    Strips surrounding quotes and commas. Returns None for sentinel values
    ("", "/", "~", "--") that indicate not-reported or not-applicable data.
    """
    val = val.strip().strip('"')
    if val in ("", "/", "~", "--"):
        return None
    # Remove thousands-separator commas
    val = val.replace(",", "")
    try:
        return float(val)
    except ValueError:
        return None


def clean_jurisdiction(name: str) -> str:
    """Clean a BJS jurisdiction name.

    Handles:
    - Surrounding quotes: '"Illinois/d,g"' → 'Illinois'
    - Slash-suffix footnotes: 'Alabama/d' → 'Alabama'
    - Multi-footnote slash patterns: 'Illinois/d,g' → 'Illinois'
    - Stuck single-letter footnotes: 'Rhode Islande' → 'Rhode Island'
    - Stuck multi-char footnotes on known states: 'Virginial' → 'Virginia'
    """
    name = name.strip().strip('"').strip()

    # Strip footnote markers after a slash: "Alabama/d" or "Federal/b,c"
    if "/" in name:
        name = name.split("/")[0].strip()

    # At this point check if it's a known state; if so, we're done
    if name in STATE_NAME_TO_ABBREV or name in ("Federal", "U.S. total", "State"):
        return name

    # Check for stuck single-character lowercase footnote appended to a known state name
    # e.g. "Rhode Islande" → try "Rhode Island", "Virginial" → try "Virginia"
    m = _STUCK_FOOTNOTE_RE.match(name)
    if m:
        candidate = m.group(1)
        if candidate in STATE_NAME_TO_ABBREV:
            return candidate

    return name


def should_skip_row(first_cell: str) -> bool:
    """Return True if this row should be skipped during state table parsing.

    Skips region headers (Northeast, Midwest, South, West), note/source lines,
    blank lines, and "Percent change" summary rows.
    """
    stripped = first_cell.strip().strip('"')
    if not stripped:
        return True
    if stripped in _REGION_HEADERS:
        return True
    lower = stripped.lower()
    if lower.startswith("note") or lower.startswith("source"):
        return True
    if lower == "percent change":
        return True
    return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _skip_header(reader: Any, n: int = 10) -> None:
    """Skip the first n metadata header rows of a BJS CSV file."""
    for _ in range(n):
        try:
            next(reader)
        except StopIteration:
            break


def _strip_empty(row: list[str]) -> list[str]:
    """Remove empty interleaving columns from a national-table row."""
    return [cell for cell in row if cell.strip() != ""]


def _make_record(
    state_abbrev: str,
    state_name: str,
    year: int,
    metric: str,
    race: str,
    gender: str,
    value: float | None,
) -> dict[str, Any]:
    """Build a standardised record dict."""
    return {
        "state_abbrev": state_abbrev,
        "state_name": state_name,
        "year": year,
        "facility_type": "prison",
        "metric": metric,
        "race": race,
        "gender": gender,
        "value": value,
    }


def _parse_national_table(reader: Any, metric_base: str) -> list[dict[str, Any]]:
    """Shared parsing logic for BJS national tables (Tables 3, 5, 6).

    After stripping empty interleaving columns the layout is:
      [0] Year
      [1] Total
      [2] Federal
      [3] State
      [4] Male
      [5] Female
      [6] White
      [7] Black
      [8] Hispanic
      [9] AIAN
      [10] Asian

    Each year row produces records for US national totals across the
    race × gender dimensions above.
    """
    # Skip 10 metadata rows then the column header row (row 11)
    _skip_header(reader, n=10)
    try:
        next(reader)  # column header row
    except StopIteration:
        return []

    records: list[dict[str, Any]] = []

    for raw_row in reader:
        row = _strip_empty(raw_row)
        if not row:
            continue

        first = row[0].strip()
        # Skip "Percent change" and other non-year rows
        if not first or not first[:4].isdigit():
            continue

        try:
            year = int(first[:4])
        except ValueError:
            continue

        def _val(idx: int) -> float | None:
            try:
                return clean_number(row[idx])
            except IndexError:
                return None

        # Total (race=total, gender=total)
        records.append(_make_record("US", "United States", year, metric_base, "total", "total", _val(1)))
        # Facility type breakdown (use race="total" with different metrics for federal/state)
        records.append(_make_record("US", "United States", year, f"{metric_base}_federal", "total", "total", _val(2)))
        records.append(_make_record("US", "United States", year, f"{metric_base}_state", "total", "total", _val(3)))
        # Gender breakdown
        records.append(_make_record("US", "United States", year, metric_base, "total", "male", _val(4)))
        records.append(_make_record("US", "United States", year, metric_base, "total", "female", _val(5)))
        # Race breakdown (gender=total)
        records.append(_make_record("US", "United States", year, metric_base, "white", "total", _val(6)))
        records.append(_make_record("US", "United States", year, metric_base, "black", "total", _val(7)))
        records.append(_make_record("US", "United States", year, metric_base, "hispanic", "total", _val(8)))
        records.append(_make_record("US", "United States", year, metric_base, "aian", "total", _val(9)))
        records.append(_make_record("US", "United States", year, metric_base, "asian", "total", _val(10)))

    return [r for r in records if r["value"] is not None]


# ---------------------------------------------------------------------------
# Table parsers
# ---------------------------------------------------------------------------


def parse_table3_sentenced(reader: Any, data_year: int) -> list[dict[str, Any]]:
    """Parse BJS Table 3: sentenced prisoner counts by race × sex (national).

    Returns records with metric='sentenced_population'.
    """
    return _parse_national_table(reader, "sentenced_population")


def parse_table5_rates(reader: Any, data_year: int) -> list[dict[str, Any]]:
    """Parse BJS Table 5: imprisonment rates all ages (national).

    Returns records with metric='imprisonment_rate_all_ages'.
    """
    return _parse_national_table(reader, "imprisonment_rate_all_ages")


def parse_table6_rates(reader: Any, data_year: int) -> list[dict[str, Any]]:
    """Parse BJS Table 6: imprisonment rates adults (national).

    Returns records with metric='imprisonment_rate_adult'.
    """
    return _parse_national_table(reader, "imprisonment_rate_adult")


def parse_appendix_table1(reader: Any, data_year: int) -> list[dict[str, Any]]:
    """Parse BJS Appendix Table 1: prisoners by jurisdiction and race.

    State rows are indented: first cell is empty, jurisdiction is in the
    second cell. Federal row has the jurisdiction in the first cell.

    Column layout (0-indexed, no empty separators in this table):
      [0]  Jurisdiction (first cell — empty for state rows)
      [1]  Jurisdiction name (second cell for state rows; empty for Federal)
      [2]  Total
      [3]  White
      [4]  Black
      [5]  Hispanic
      [6]  AIAN
      [7]  Asian
      [8]  NHPI        ← skipped
      [9]  Two or more ← skipped
      [10] Other       ← skipped
      [11] Unknown     ← skipped
      [12] Did not report ← skipped

    Races kept: total, white, black, hispanic, aian, asian.
    Sentinel values (None) are dropped.
    """
    _skip_header(reader, n=10)
    try:
        next(reader)  # column header row
    except StopIteration:
        return []

    # Race name → column index
    race_cols: dict[str, int] = {
        "total": 2,
        "white": 3,
        "black": 4,
        "hispanic": 5,
        "aian": 6,
        "asian": 7,
    }

    records: list[dict[str, Any]] = []

    for raw_row in reader:
        # Pad row so index access is safe
        row = raw_row + [""] * 13

        first = row[0].strip().strip('"')
        second = row[1].strip().strip('"')

        # Skip blank rows, note rows, "State" section header (second cell is empty
        # and first is "State" or a region name)
        if not first and not second:
            continue
        if should_skip_row(first) and not second:
            continue

        # Determine jurisdiction
        is_federal = False
        if first and not second:
            # Could be "Federal/b", "State", or a region header
            jname = clean_jurisdiction(first)
            if jname in _REGION_HEADERS or jname == "State":
                continue
            if jname == "Federal":
                is_federal = True
                state_abbrev = "US"
                state_name = "Federal"
            else:
                # Some other top-level row we don't recognise — skip
                continue
        elif not first and second:
            # Indented state row
            jname = clean_jurisdiction(second)
            if jname not in STATE_NAME_TO_ABBREV:
                # Unrecognised jurisdiction — skip
                continue
            state_abbrev = STATE_NAME_TO_ABBREV[jname]
            state_name = jname
        else:
            # Both cells populated — unusual; skip
            continue

        for race, col_idx in race_cols.items():
            raw_val = row[col_idx] if col_idx < len(row) else ""
            value = clean_number(raw_val)
            if value is None:
                continue
            records.append(_make_record(
                state_abbrev,
                state_name,
                data_year,
                "total_population",
                race,
                "total",
                value,
            ))

    return records


def parse_admissions_releases(
    reader: Any,
    metric_map: dict[int, tuple[str, int]],
) -> list[dict[str, Any]]:
    """Parse BJS Tables 8/9: admissions or releases by jurisdiction.

    Uses RAW column indices (not stripped) to handle inconsistently placed
    empty separator columns.

    Args:
        reader: csv.reader over the BJS CSV file.
        metric_map: Mapping of raw column index → (metric_name, year).
            Example: {3: ("admissions_total", 2023), ...}

    Jurisdiction detection (same indentation convention as Appendix Table 1):
    - Indented state rows: first cell empty, second cell has jurisdiction name.
    - Federal row: first cell has "Federal/..." string, second cell empty.
    - "U.S. total" row: indented (first cell empty), second cell "U.S. total/b".
    - "State" aggregate: skip.
    - Region headers: skip.
    """
    _skip_header(reader, n=10)
    try:
        next(reader)  # column header row
    except StopIteration:
        return []

    records: list[dict[str, Any]] = []

    for raw_row in reader:
        row = raw_row + [""] * (max(metric_map.keys(), default=0) + 2)

        first = row[0].strip().strip('"')
        second = row[1].strip().strip('"') if len(row) > 1 else ""

        if not first and not second:
            continue
        if should_skip_row(first) and not second:
            continue

        # Determine jurisdiction
        if first and not second:
            jname = clean_jurisdiction(first)
            if jname in _REGION_HEADERS or jname == "State":
                continue
            if jname == "Federal":
                state_abbrev = "US"
                state_name = "Federal"
            else:
                continue
        elif not first and second:
            jname = clean_jurisdiction(second)
            # U.S. total row
            if "U.S." in jname or "U.S" in jname or "total" in jname.lower():
                state_abbrev = "US"
                state_name = "United States"
            elif jname in STATE_NAME_TO_ABBREV:
                state_abbrev = STATE_NAME_TO_ABBREV[jname]
                state_name = jname
            else:
                continue
        else:
            continue

        for col_idx, (metric_name, year) in metric_map.items():
            raw_val = row[col_idx] if col_idx < len(row) else ""
            value = clean_number(raw_val)
            if value is None:
                continue
            records.append(_make_record(
                state_abbrev,
                state_name,
                year,
                metric_name,
                "total",
                "total",
                value,
            ))

    return records
