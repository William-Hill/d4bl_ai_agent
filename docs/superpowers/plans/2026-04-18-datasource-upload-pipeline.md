# Data Source Upload Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn an approved staff CSV/XLSX upload into a live, queryable data source on `/explore` by parsing + validating + normalizing at upload time, and exposing approved uploads through a single "Staff Uploads" tab.

**Architecture:** Parse-on-upload pipeline that writes normalized JSONB rows into `uploaded_datasets` in the same transaction as the `Upload` row. Admin approval is a pure status flip (no processing). A new module `src/d4bl/services/datasource_processing/` hosts pure parser + validation helpers. Two new endpoints surface approved rows in the standard `ExploreResponse` shape so existing `/explore` components are reused unchanged.

**Tech Stack:** Python (FastAPI, SQLAlchemy async, pytest, openpyxl, stdlib `csv`), TypeScript/React 19 (Next.js App Router, Tailwind).

**Spec:** `docs/superpowers/specs/2026-04-18-datasource-upload-pipeline-design.md`

---

## Task 1: Add `openpyxl` dep and scaffold the `datasource_processing` package

**Files:**
- Modify: `pyproject.toml`
- Create: `src/d4bl/services/datasource_processing/__init__.py`

- [ ] **Step 1: Add `openpyxl` to dependencies**

Edit `pyproject.toml` — add `"openpyxl>=3.1"` to the `dependencies` list between `"python-docx>=1.1"` and the closing `]`:

```toml
dependencies = [
    "crewai[tools]==1.5.0",
    "python-dotenv>=1.0.0",
    "litellm>=1.0.0",
    "PyJWT>=2.8.0",
    "httpx>=0.27",
    "APScheduler>=3.10,<4",
    "trafilatura>=1.6",
    "pypdf>=4.0",
    "python-docx>=1.1",
    "openpyxl>=3.1",
]
```

- [ ] **Step 2: Install the new dependency**

Run: `pip install -e .`
Expected: installs `openpyxl` and its transitive deps with no errors.

- [ ] **Step 3: Create the package marker**

Create `src/d4bl/services/datasource_processing/__init__.py` with:

```python
"""Data source processing: parse, validate, and normalize staff CSV/XLSX uploads."""
```

- [ ] **Step 4: Verify import works**

Run: `python -c "import d4bl.services.datasource_processing"`
Expected: no output, exit 0.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/d4bl/services/datasource_processing/__init__.py
git commit -m "feat(deps): add openpyxl and scaffold datasource_processing package"
```

---

## Task 2: Validation helpers (TDD)

Pure functions with no IO. Isolated so we can unit-test the tricky coercion rules without fixtures.

**Files:**
- Create: `src/d4bl/services/datasource_processing/validation.py`
- Create: `tests/test_datasource_processing.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_datasource_processing.py` with:

```python
"""Tests for datasource upload parser + validation."""

import io

import pytest

from d4bl.services.datasource_processing.validation import (
    coerce_numeric,
    coerce_year,
    derive_state_fips,
    validate_metric_name,
)


class TestValidateMetricName:
    def test_valid_snake_case(self):
        assert validate_metric_name("eviction_filing_rate") == "eviction_filing_rate"

    def test_valid_with_digits(self):
        assert validate_metric_name("poverty_rate_2023") == "poverty_rate_2023"

    @pytest.mark.parametrize("bad", ["", "UPPER", "has space", "with-dash", "a" * 65, "!bang"])
    def test_rejects(self, bad):
        with pytest.raises(ValueError):
            validate_metric_name(bad)


class TestDeriveStateFips:
    def test_state_fips(self):
        assert derive_state_fips("13") == "13"

    def test_county_fips(self):
        assert derive_state_fips("13121") == "13"

    def test_tract_fips(self):
        assert derive_state_fips("13121020100") == "13"

    def test_strips_whitespace(self):
        assert derive_state_fips(" 13121 ") == "13"

    def test_accepts_int_like(self):
        # Single-digit states (e.g. "6" for CA) get zero-padded.
        assert derive_state_fips("6") == "06"

    def test_rejects_non_numeric(self):
        with pytest.raises(ValueError):
            derive_state_fips("CA")

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            derive_state_fips("")


class TestCoerceNumeric:
    def test_plain_float(self):
        assert coerce_numeric("14.3") == 14.3

    def test_plain_int(self):
        assert coerce_numeric("42") == 42.0

    def test_with_percent(self):
        assert coerce_numeric("14.3%") == 14.3

    def test_with_commas(self):
        assert coerce_numeric("1,234.5") == 1234.5

    def test_with_whitespace(self):
        assert coerce_numeric("  14.3  ") == 14.3

    @pytest.mark.parametrize("bad", ["", "NaN", "abc", "--", "14.3.0"])
    def test_rejects(self, bad):
        with pytest.raises(ValueError):
            coerce_numeric(bad)


class TestCoerceYear:
    def test_valid_year(self):
        assert coerce_year("2023") == 2023

    def test_int_year(self):
        assert coerce_year(2023) == 2023

    @pytest.mark.parametrize("bad", ["", "20", "abc", "1899", "3000"])
    def test_rejects(self, bad):
        with pytest.raises(ValueError):
            coerce_year(bad)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_datasource_processing.py -v`
Expected: ImportError / ModuleNotFoundError for `validation`.

- [ ] **Step 3: Write the implementation**

Create `src/d4bl/services/datasource_processing/validation.py`:

```python
"""Pure validation + coercion helpers for staff datasource uploads.

Isolated from any IO so that each rule can be unit-tested directly.
"""

from __future__ import annotations

import re
from datetime import datetime

METRIC_NAME_RE = re.compile(r"^[a-z0-9_]{1,64}$")
MIN_YEAR = 1900


def validate_metric_name(name: str) -> str:
    """Return the metric name if it matches ``^[a-z0-9_]{1,64}$``; raise ValueError otherwise."""
    if not isinstance(name, str) or not METRIC_NAME_RE.match(name):
        raise ValueError(
            "metric_name must be snake_case: 1-64 chars of [a-z0-9_]"
        )
    return name


def derive_state_fips(geo_fips: object) -> str:
    """Return the 2-digit state FIPS prefix from a state/county/tract FIPS.

    - "13"        → "13"   (state)
    - "13121"     → "13"   (county)
    - "13121020100" → "13" (tract)
    - "6"         → "06"   (zero-padded state)

    Raises ValueError on empty or non-numeric input.
    """
    if geo_fips is None:
        raise ValueError("geo_fips is required")
    s = str(geo_fips).strip()
    if not s:
        raise ValueError("geo_fips is empty")
    if not s.isdigit():
        raise ValueError(f"geo_fips must be numeric, got {s!r}")
    if len(s) == 1:
        s = "0" + s
    return s[:2]


def coerce_numeric(value: object) -> float:
    """Parse a numeric value, tolerating ``%``, commas, and whitespace.

    Raises ValueError for blanks, NaN, or anything else float() can't handle
    after the strip pipeline.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if value is None:
        raise ValueError("value is empty")
    s = str(value).strip().rstrip("%").replace(",", "").strip()
    if not s or s.lower() == "nan":
        raise ValueError("value is empty or NaN")
    return float(s)  # raises ValueError on malformed input


def coerce_year(value: object) -> int:
    """Parse a 4-digit year between ``MIN_YEAR`` and ``current year + 1``."""
    if isinstance(value, bool):
        raise ValueError("year cannot be boolean")
    if isinstance(value, int):
        year = value
    else:
        s = str(value).strip()
        if not s.isdigit():
            raise ValueError(f"year must be an integer, got {value!r}")
        year = int(s)
    max_year = datetime.now().year + 1
    if not (MIN_YEAR <= year <= max_year):
        raise ValueError(f"year must be between {MIN_YEAR} and {max_year}, got {year}")
    return year
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_datasource_processing.py -v`
Expected: all tests in `TestValidateMetricName`, `TestDeriveStateFips`, `TestCoerceNumeric`, `TestCoerceYear` pass.

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/services/datasource_processing/validation.py tests/test_datasource_processing.py
git commit -m "feat(datasource): add validation + coercion helpers"
```

---

## Task 3: `MappingConfig` dataclass + `DatasourceParseError` exception

**Files:**
- Create: `src/d4bl/services/datasource_processing/parser.py`
- Modify: `tests/test_datasource_processing.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_datasource_processing.py`:

```python
class TestMappingConfig:
    def test_required_fields_only(self):
        from d4bl.services.datasource_processing.parser import MappingConfig

        m = MappingConfig(
            geo_column="county_fips",
            metric_value_column="rate",
            metric_name="eviction_rate",
        )
        assert m.race_column is None
        assert m.year_column is None

    def test_metric_name_validated_in_post_init(self):
        from d4bl.services.datasource_processing.parser import MappingConfig

        with pytest.raises(ValueError):
            MappingConfig(
                geo_column="county_fips",
                metric_value_column="rate",
                metric_name="Bad Name",
            )


class TestDatasourceParseError:
    def test_has_structured_detail(self):
        from d4bl.services.datasource_processing.parser import DatasourceParseError

        err = DatasourceParseError(
            "missing columns",
            detail={"missing_columns": ["race"]},
        )
        assert err.detail == {"missing_columns": ["race"]}
        assert "missing columns" in str(err)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_datasource_processing.py::TestMappingConfig tests/test_datasource_processing.py::TestDatasourceParseError -v`
Expected: ImportError for `parser`.

- [ ] **Step 3: Write the implementation**

Create `src/d4bl/services/datasource_processing/parser.py`:

```python
"""Parse CSV/XLSX staff uploads into normalized ``uploaded_datasets`` rows.

Raises ``DatasourceParseError`` with a structured ``detail`` payload on any
validation failure so callers can surface actionable messages via HTTP 422.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .validation import validate_metric_name


@dataclass
class MappingConfig:
    """Contributor-declared column mapping for a datasource upload."""

    geo_column: str
    metric_value_column: str
    metric_name: str
    race_column: str | None = None
    year_column: str | None = None
    # Fallback year used when ``year_column`` is None.
    data_year: int | None = None

    def __post_init__(self) -> None:
        self.metric_name = validate_metric_name(self.metric_name)


class DatasourceParseError(Exception):
    """Raised when a datasource upload fails parse/validation.

    ``detail`` is a JSON-serializable payload suitable for ``HTTPException(422, detail=...)``.
    """

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.detail = detail or {"message": message}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_datasource_processing.py::TestMappingConfig tests/test_datasource_processing.py::TestDatasourceParseError -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/services/datasource_processing/parser.py tests/test_datasource_processing.py
git commit -m "feat(datasource): add MappingConfig + DatasourceParseError"
```

---

## Task 4: CSV parser (TDD)

Parses CSV bytes into `{header, rows}`. Called by the orchestrator later.

**Files:**
- Modify: `src/d4bl/services/datasource_processing/parser.py`
- Modify: `tests/test_datasource_processing.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_datasource_processing.py`:

```python
class TestReadCsvBytes:
    def test_basic_csv(self):
        from d4bl.services.datasource_processing.parser import read_csv_bytes

        raw = b"county_fips,rate\n13121,14.3\n13089,9.1\n"
        header, rows = read_csv_bytes(raw)
        assert header == ["county_fips", "rate"]
        assert rows == [{"county_fips": "13121", "rate": "14.3"},
                         {"county_fips": "13089", "rate": "9.1"}]

    def test_utf8_with_bom(self):
        from d4bl.services.datasource_processing.parser import read_csv_bytes

        raw = "\ufeffcounty_fips,rate\n13121,14.3\n".encode("utf-8")
        header, _rows = read_csv_bytes(raw)
        # BOM must not contaminate the first header name.
        assert header == ["county_fips", "rate"]

    def test_trims_header_whitespace(self):
        from d4bl.services.datasource_processing.parser import read_csv_bytes

        raw = b" county_fips , rate \n13121, 14.3\n"
        header, rows = read_csv_bytes(raw)
        assert header == ["county_fips", "rate"]
        assert rows[0]["county_fips"] == "13121"
        # Cell whitespace preserved so the value-column coercion can strip it.
        assert rows[0]["rate"] == " 14.3"

    def test_empty_csv_raises(self):
        from d4bl.services.datasource_processing.parser import (
            DatasourceParseError,
            read_csv_bytes,
        )

        with pytest.raises(DatasourceParseError):
            read_csv_bytes(b"")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_datasource_processing.py::TestReadCsvBytes -v`
Expected: AttributeError or ImportError on `read_csv_bytes`.

- [ ] **Step 3: Write the implementation**

Append to `src/d4bl/services/datasource_processing/parser.py`:

```python
import csv
import io


def read_csv_bytes(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    """Parse CSV bytes into ``(header, rows)``.

    - Decodes as ``utf-8-sig`` so a UTF-8 BOM is stripped from the first cell.
    - Trims whitespace from header names (cell values are left raw so downstream
      coercion can handle whitespace consistently).
    - Raises ``DatasourceParseError`` if the file is empty or has no header row.
    """
    if not content:
        raise DatasourceParseError("file is empty")
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    try:
        raw_header = next(reader)
    except StopIteration:
        raise DatasourceParseError("file has no header row")

    header = [h.strip() for h in raw_header]
    rows = [dict(zip(header, r)) for r in reader if any(cell.strip() for cell in r)]
    return header, rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_datasource_processing.py::TestReadCsvBytes -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/services/datasource_processing/parser.py tests/test_datasource_processing.py
git commit -m "feat(datasource): add CSV reader"
```

---

## Task 5: XLSX parser (TDD)

**Files:**
- Modify: `src/d4bl/services/datasource_processing/parser.py`
- Modify: `tests/test_datasource_processing.py`

- [ ] **Step 1: Add the XLSX fixture factory to `tests/conftest.py`**

Append to `tests/conftest.py`:

```python
@pytest.fixture
def make_xlsx_bytes():
    """Factory fixture: given ``header`` + ``rows``, produce XLSX bytes.

    ``rows`` is a list of lists aligned with ``header``. Returns raw bytes
    suitable for feeding to the datasource parser.
    """
    from openpyxl import Workbook

    def _make(header: list[str], rows: list[list]) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.append(header)
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    return _make
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_datasource_processing.py`:

```python
class TestReadXlsxBytes:
    def test_basic_xlsx(self, make_xlsx_bytes):
        from d4bl.services.datasource_processing.parser import read_xlsx_bytes

        raw = make_xlsx_bytes(
            ["county_fips", "rate"],
            [["13121", 14.3], ["13089", 9.1]],
        )
        header, rows = read_xlsx_bytes(raw)
        assert header == ["county_fips", "rate"]
        assert rows[0]["county_fips"] == "13121"
        assert rows[0]["rate"] in ("14.3", 14.3)

    def test_skips_empty_rows(self, make_xlsx_bytes):
        from d4bl.services.datasource_processing.parser import read_xlsx_bytes

        raw = make_xlsx_bytes(
            ["county_fips", "rate"],
            [["13121", 14.3], [None, None], ["13089", 9.1]],
        )
        _header, rows = read_xlsx_bytes(raw)
        assert len(rows) == 2

    def test_empty_workbook_raises(self, make_xlsx_bytes):
        from d4bl.services.datasource_processing.parser import (
            DatasourceParseError,
            read_xlsx_bytes,
        )

        raw = make_xlsx_bytes([], [])
        with pytest.raises(DatasourceParseError):
            read_xlsx_bytes(raw)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_datasource_processing.py::TestReadXlsxBytes -v`
Expected: AttributeError on `read_xlsx_bytes`.

- [ ] **Step 4: Write the implementation**

Append to `src/d4bl/services/datasource_processing/parser.py`:

```python
from openpyxl import load_workbook


def read_xlsx_bytes(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    """Parse XLSX bytes into ``(header, rows)`` using openpyxl.

    - Reads the first worksheet only.
    - ``header`` is taken from row 1, trimmed of whitespace.
    - Empty rows (all cells None / blank) are skipped.
    - Non-string cell values are stringified so downstream coercion sees the
      same shape as the CSV reader.
    """
    if not content:
        raise DatasourceParseError("file is empty")
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise DatasourceParseError(f"could not open xlsx: {exc}") from exc

    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        raw_header = next(rows_iter)
    except StopIteration:
        raise DatasourceParseError("file has no header row")

    header = [("" if h is None else str(h)).strip() for h in raw_header]
    if not any(header):
        raise DatasourceParseError("header row is empty")

    rows: list[dict[str, str]] = []
    for raw_row in rows_iter:
        if raw_row is None or all(cell is None or str(cell).strip() == "" for cell in raw_row):
            continue
        row = {h: ("" if v is None else str(v)) for h, v in zip(header, raw_row)}
        rows.append(row)
    return header, rows
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_datasource_processing.py::TestReadXlsxBytes -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/d4bl/services/datasource_processing/parser.py tests/test_datasource_processing.py tests/conftest.py
git commit -m "feat(datasource): add XLSX reader"
```

---

## Task 6: `parse_datasource_file` orchestrator (TDD)

Dispatches by extension, validates declared columns, normalizes rows, enforces drop thresholds, returns `ParseResult`.

**Files:**
- Modify: `src/d4bl/services/datasource_processing/parser.py`
- Modify: `tests/test_datasource_processing.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_datasource_processing.py`:

```python
def _make_mapping(**overrides):
    from d4bl.services.datasource_processing.parser import MappingConfig

    defaults = dict(
        geo_column="county_fips",
        metric_value_column="rate",
        metric_name="eviction_rate",
        race_column=None,
        year_column=None,
        data_year=2023,
    )
    defaults.update(overrides)
    return MappingConfig(**defaults)


class TestParseDatasourceFile:
    def test_valid_csv_without_race_or_year(self):
        from d4bl.services.datasource_processing.parser import parse_datasource_file

        raw = b"county_fips,rate\n" + b"\n".join(
            f"{13000 + i},{i * 0.5}".encode() for i in range(15)
        )
        result = parse_datasource_file(raw, ".csv", _make_mapping())
        assert result.row_count == 15
        assert result.dropped_counts == {"bad_fips": 0, "non_numeric": 0, "bad_year": 0}
        assert result.normalized_rows[0]["state_fips"] == "13"
        assert result.normalized_rows[0]["year"] == 2023
        assert result.normalized_rows[0]["race"] is None
        assert len(result.preview_rows) == min(20, result.row_count)

    def test_valid_csv_with_race_and_year(self):
        from d4bl.services.datasource_processing.parser import parse_datasource_file

        lines = ["county_fips,race,year,rate"]
        for i in range(12):
            lines.append(f"{13000 + i},Black,2023,{i * 0.5}")
        raw = "\n".join(lines).encode()
        result = parse_datasource_file(
            raw, ".csv",
            _make_mapping(race_column="race", year_column="year"),
        )
        assert all(r["race"] == "Black" for r in result.normalized_rows)
        assert all(r["year"] == 2023 for r in result.normalized_rows)

    def test_missing_declared_column_raises(self):
        from d4bl.services.datasource_processing.parser import (
            DatasourceParseError,
            parse_datasource_file,
        )

        raw = b"county_fips,rate\n13121,14.3\n"
        with pytest.raises(DatasourceParseError) as exc_info:
            parse_datasource_file(raw, ".csv", _make_mapping(race_column="ethnicity"))
        assert "missing_columns" in exc_info.value.detail
        assert "ethnicity" in exc_info.value.detail["missing_columns"]

    def test_many_bad_fips_raises(self):
        from d4bl.services.datasource_processing.parser import (
            DatasourceParseError,
            parse_datasource_file,
        )

        lines = ["county_fips,rate"]
        # 3 good, 10 bad → >10% bad
        for i in range(3):
            lines.append(f"{13000 + i},{i}")
        for i in range(10):
            lines.append(f"X{i},{i}")
        raw = "\n".join(lines).encode()
        with pytest.raises(DatasourceParseError) as exc_info:
            parse_datasource_file(raw, ".csv", _make_mapping())
        assert exc_info.value.detail["dropped"]["reason"] == "bad_fips"

    def test_few_bad_fips_drops_silently(self):
        from d4bl.services.datasource_processing.parser import parse_datasource_file

        lines = ["county_fips,rate"]
        for i in range(20):
            lines.append(f"{13000 + i},{i}")
        lines.append("XX,99")  # 1 bad out of 21 → <10%
        raw = "\n".join(lines).encode()
        result = parse_datasource_file(raw, ".csv", _make_mapping())
        assert result.row_count == 20
        assert result.dropped_counts["bad_fips"] == 1

    def test_many_non_numeric_values_raises(self):
        from d4bl.services.datasource_processing.parser import (
            DatasourceParseError,
            parse_datasource_file,
        )

        lines = ["county_fips,rate"]
        for i in range(5):
            lines.append(f"{13000 + i},{i}")
        for i in range(10):
            lines.append(f"{13100 + i},NaN")
        raw = "\n".join(lines).encode()
        with pytest.raises(DatasourceParseError) as exc_info:
            parse_datasource_file(raw, ".csv", _make_mapping())
        assert exc_info.value.detail["dropped"]["reason"] == "non_numeric"

    def test_too_few_valid_rows_raises(self):
        from d4bl.services.datasource_processing.parser import (
            DatasourceParseError,
            parse_datasource_file,
        )

        raw = b"county_fips,rate\n13121,14.3\n13089,9.1\n"
        with pytest.raises(DatasourceParseError) as exc_info:
            parse_datasource_file(raw, ".csv", _make_mapping())
        assert exc_info.value.detail["reason"] == "too_few_rows"

    def test_percent_and_comma_values_coerce(self):
        from d4bl.services.datasource_processing.parser import parse_datasource_file

        lines = ["county_fips,rate"]
        for i in range(12):
            lines.append(f"{13000 + i},\"1,234.{i}%\"")
        raw = "\n".join(lines).encode()
        result = parse_datasource_file(raw, ".csv", _make_mapping())
        assert result.normalized_rows[0]["value"] > 1000

    def test_unsupported_extension_raises(self):
        from d4bl.services.datasource_processing.parser import (
            DatasourceParseError,
            parse_datasource_file,
        )

        with pytest.raises(DatasourceParseError):
            parse_datasource_file(b"...", ".txt", _make_mapping())

    def test_xlsx_input(self, make_xlsx_bytes):
        from d4bl.services.datasource_processing.parser import parse_datasource_file

        header = ["county_fips", "rate"]
        rows = [[f"{13000 + i}", i * 0.5] for i in range(15)]
        raw = make_xlsx_bytes(header, rows)
        result = parse_datasource_file(raw, ".xlsx", _make_mapping())
        assert result.row_count == 15
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_datasource_processing.py::TestParseDatasourceFile -v`
Expected: ImportError on `parse_datasource_file` or `ParseResult`.

- [ ] **Step 3: Write the implementation**

Append to `src/d4bl/services/datasource_processing/parser.py`:

```python
from dataclasses import field

from .validation import coerce_numeric, coerce_year, derive_state_fips

MIN_VALID_ROWS = 10
MAX_BAD_FIPS_RATIO = 0.10
MIN_NUMERIC_RATIO = 0.90
PREVIEW_LIMIT = 20
SUPPORTED_EXTS = {".csv", ".xlsx"}


@dataclass
class ParseResult:
    normalized_rows: list[dict[str, Any]]
    row_count: int
    dropped_counts: dict[str, int] = field(default_factory=dict)
    preview_rows: list[dict[str, Any]] = field(default_factory=list)


def _check_columns_exist(header: list[str], mapping: MappingConfig) -> None:
    required = [mapping.geo_column, mapping.metric_value_column]
    optional = [c for c in (mapping.race_column, mapping.year_column) if c]
    missing = [c for c in required + optional if c not in header]
    if missing:
        raise DatasourceParseError(
            "declared columns not found in file header",
            detail={"missing_columns": missing, "header": header},
        )


def _normalize_rows(
    rows: list[dict[str, str]], mapping: MappingConfig
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Return (normalized_rows, dropped_counts).

    Drops rows that fail FIPS, numeric, or year parsing individually; the caller
    enforces overall drop-ratio rules.
    """
    dropped = {"bad_fips": 0, "non_numeric": 0, "bad_year": 0}
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            geo_raw = row.get(mapping.geo_column)
            state_fips = derive_state_fips(geo_raw)
            geo_fips = str(geo_raw).strip() if geo_raw is not None else ""
        except ValueError:
            dropped["bad_fips"] += 1
            continue

        value_raw = row.get(mapping.metric_value_column)
        try:
            value = coerce_numeric(value_raw)
        except ValueError:
            dropped["non_numeric"] += 1
            continue

        if mapping.year_column:
            try:
                year = coerce_year(row.get(mapping.year_column))
            except ValueError:
                dropped["bad_year"] += 1
                continue
        else:
            if mapping.data_year is None:
                raise DatasourceParseError(
                    "data_year is required when year_column is not set",
                )
            year = mapping.data_year

        race = None
        if mapping.race_column:
            raw_race = row.get(mapping.race_column)
            race = str(raw_race).strip() if raw_race is not None and str(raw_race).strip() else None

        out.append({
            "geo_fips": geo_fips,
            "state_fips": state_fips,
            "race": race,
            "year": year,
            "value": value,
        })
    return out, dropped


def parse_datasource_file(
    content: bytes, ext: str, mapping: MappingConfig
) -> ParseResult:
    """Parse + validate + normalize a staff datasource upload.

    Raises ``DatasourceParseError`` on any unrecoverable condition (missing
    columns, >10% bad FIPS, <90% numeric, <10 valid rows post-drop, etc.).
    """
    ext = ext.lower()
    if ext == ".csv":
        header, rows = read_csv_bytes(content)
    elif ext == ".xlsx":
        header, rows = read_xlsx_bytes(content)
    else:
        raise DatasourceParseError(
            f"unsupported file type {ext!r}",
            detail={"allowed": sorted(SUPPORTED_EXTS)},
        )

    _check_columns_exist(header, mapping)

    normalized, dropped = _normalize_rows(rows, mapping)
    total_seen = len(rows)

    if total_seen > 0 and (dropped["bad_fips"] / total_seen) > MAX_BAD_FIPS_RATIO:
        raise DatasourceParseError(
            "too many rows have unparseable FIPS values",
            detail={"dropped": {
                "reason": "bad_fips",
                "count": dropped["bad_fips"],
                "total": total_seen,
            }},
        )

    # Numeric rule is computed against rows that passed FIPS, to avoid double-counting.
    fips_ok = total_seen - dropped["bad_fips"]
    if fips_ok > 0:
        numeric_ratio = 1 - (dropped["non_numeric"] / fips_ok)
        if numeric_ratio < MIN_NUMERIC_RATIO:
            raise DatasourceParseError(
                "too many rows have non-numeric values in the metric column",
                detail={"dropped": {
                    "reason": "non_numeric",
                    "count": dropped["non_numeric"],
                    "total": fips_ok,
                }},
            )

    if len(normalized) < MIN_VALID_ROWS:
        raise DatasourceParseError(
            f"fewer than {MIN_VALID_ROWS} valid rows remained after validation",
            detail={"reason": "too_few_rows", "valid": len(normalized)},
        )

    return ParseResult(
        normalized_rows=normalized,
        row_count=len(normalized),
        dropped_counts=dropped,
        preview_rows=normalized[:PREVIEW_LIMIT],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_datasource_processing.py -v`
Expected: all tests (validation + mapping + csv + xlsx + parse) pass.

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/services/datasource_processing/parser.py tests/test_datasource_processing.py
git commit -m "feat(datasource): add parse_datasource_file orchestrator"
```

---

## Task 7: Extend `DataSourceUploadRequest` schema

Add mapping fields to the request schema used by the upload endpoint. Keep backward-compat-safe — new fields are required but the form submits them.

**Files:**
- Modify: `src/d4bl/app/schemas.py:635-648`
- Modify: `tests/test_upload_api.py` (extend `TestUploadSchemas`)

- [ ] **Step 1: Write the failing tests**

Append to the `TestUploadSchemas` class in `tests/test_upload_api.py` (add new methods after `test_datasource_upload_blank_name`):

```python
    def test_datasource_upload_requires_mapping_fields(self):
        from d4bl.app.schemas import DataSourceUploadRequest

        # Missing metric_name should fail.
        with pytest.raises(ValidationError):
            DataSourceUploadRequest(
                source_name="X",
                description="X",
                geographic_level="county",
                data_year=2024,
                geo_column="county_fips",
                metric_value_column="rate",
            )

    def test_datasource_upload_validates_metric_name(self):
        from d4bl.app.schemas import DataSourceUploadRequest

        with pytest.raises(ValidationError):
            DataSourceUploadRequest(
                source_name="X",
                description="X",
                geographic_level="county",
                data_year=2024,
                geo_column="county_fips",
                metric_value_column="rate",
                metric_name="Bad Name",
            )

    def test_datasource_upload_accepts_optional_race_and_year(self):
        from d4bl.app.schemas import DataSourceUploadRequest

        req = DataSourceUploadRequest(
            source_name="X",
            description="X",
            geographic_level="county",
            data_year=2024,
            geo_column="county_fips",
            metric_value_column="rate",
            metric_name="eviction_rate",
            race_column="race",
            year_column="year",
        )
        assert req.race_column == "race"
        assert req.year_column == "year"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_upload_api.py::TestUploadSchemas -v`
Expected: the three new tests fail because the fields don't exist on the schema yet.

- [ ] **Step 3: Update the schema**

Replace the `DataSourceUploadRequest` class in `src/d4bl/app/schemas.py` (lines ~635-648) with:

```python
class DataSourceUploadRequest(BaseModel):
    source_name: str
    description: str
    geographic_level: Literal["state", "county", "tract"]
    data_year: int
    source_url: str | None = None
    category_tags: list[str] | None = None
    # Declared column mapping — contributor tells us what each CSV column means.
    geo_column: str
    metric_value_column: str
    metric_name: str
    race_column: str | None = None
    year_column: str | None = None

    @field_validator("source_name")
    @classmethod
    def source_name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Source name cannot be empty")
        return v.strip()

    @field_validator("metric_name")
    @classmethod
    def metric_name_valid(cls, v: str) -> str:
        from d4bl.services.datasource_processing.validation import validate_metric_name

        return validate_metric_name(v)
```

- [ ] **Step 4: Update the `test_datasource_upload_valid` test to include mapping**

In `tests/test_upload_api.py`, edit `test_datasource_upload_valid` to pass the new required fields:

```python
    def test_datasource_upload_valid(self):
        from d4bl.app.schemas import DataSourceUploadRequest

        req = DataSourceUploadRequest(
            source_name="County Health Rankings 2024",
            description="County-level health outcomes by race",
            geographic_level="county",
            data_year=2024,
            geo_column="county_fips",
            metric_value_column="premature_death_rate",
            metric_name="premature_death_rate",
        )
        assert req.source_name == "County Health Rankings 2024"
        assert req.geographic_level == "county"
        assert req.metric_name == "premature_death_rate"
```

Apply the same mapping-field additions to `test_datasource_upload_invalid_geo_level` and `test_datasource_upload_blank_name` so they don't trigger the new required-field error instead of the one they're asserting:

```python
    def test_datasource_upload_invalid_geo_level(self):
        from d4bl.app.schemas import DataSourceUploadRequest

        with pytest.raises(ValidationError):
            DataSourceUploadRequest(
                source_name="Test",
                description="Test",
                geographic_level="zipcode",
                data_year=2024,
                geo_column="x",
                metric_value_column="y",
                metric_name="z",
            )

    def test_datasource_upload_blank_name(self):
        from d4bl.app.schemas import DataSourceUploadRequest

        with pytest.raises(ValidationError):
            DataSourceUploadRequest(
                source_name="  ",
                description="Test",
                geographic_level="county",
                data_year=2024,
                geo_column="x",
                metric_value_column="y",
                metric_name="z",
            )
```

- [ ] **Step 5: Run tests to verify all pass**

Run: `pytest tests/test_upload_api.py::TestUploadSchemas -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/d4bl/app/schemas.py tests/test_upload_api.py
git commit -m "feat(schemas): add mapping fields to DataSourceUploadRequest"
```

---

## Task 8: Extend the datasource upload endpoint

Parse the uploaded file, validate the declared mapping, and bulk-insert normalized rows into `uploaded_datasets` in the same transaction as the `Upload`.

**Files:**
- Modify: `src/d4bl/app/upload_routes.py` (the `upload_datasource` handler)
- Modify: `tests/test_upload_api.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_upload_api.py` in the `TestUploadEndpoints` class:

```python
    @pytest.mark.asyncio
    async def test_upload_datasource_csv_success(self, user_client, override_db):
        """A valid CSV + mapping parses, persists an Upload, and bulk-inserts rows."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = None
        override_db.execute = AsyncMock(return_value=mock_result)

        # 15 valid county rows with a single metric column.
        header = "county_fips,rate"
        rows = "\n".join(f"{13000 + i},{i * 0.5}" for i in range(15))
        csv_bytes = (header + "\n" + rows + "\n").encode()

        resp = await user_client.post(
            "/api/admin/uploads/datasource",
            files={"file": ("counties.csv", csv_bytes, "text/csv")},
            data={
                "source_name": "Eviction rates",
                "description": "County eviction filing rates",
                "geographic_level": "county",
                "data_year": "2023",
                "geo_column": "county_fips",
                "metric_value_column": "rate",
                "metric_name": "eviction_rate",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["upload_type"] == "datasource"
        assert body["status"] == "pending_review"
        # Upload row was added.
        assert override_db.add.called
        # Bulk insert for uploaded_datasets was executed.
        executed_sql = " ".join(str(call.args[0]) for call in override_db.execute.call_args_list)
        assert "uploaded_datasets" in executed_sql

    @pytest.mark.asyncio
    async def test_upload_datasource_missing_column_returns_422(self, user_client, override_db):
        override_db.execute = AsyncMock()

        csv_bytes = b"county_fips,rate\n13121,14.3\n13089,9.1\n" * 6  # 12 rows
        resp = await user_client.post(
            "/api/admin/uploads/datasource",
            files={"file": ("counties.csv", csv_bytes, "text/csv")},
            data={
                "source_name": "X",
                "description": "X",
                "geographic_level": "county",
                "data_year": "2023",
                "geo_column": "county_fips",
                "metric_value_column": "rate",
                "metric_name": "eviction_rate",
                "race_column": "ethnicity",  # not present in CSV
            },
        )
        assert resp.status_code == 422
        # The structured detail survives as a dict, not a flattened string.
        detail = resp.json()["detail"]
        assert "missing_columns" in detail or (
            isinstance(detail, list) and any("missing" in str(d) for d in detail)
        )
        # No Upload row was added.
        assert not override_db.add.called
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_upload_api.py::TestUploadEndpoints::test_upload_datasource_csv_success tests/test_upload_api.py::TestUploadEndpoints::test_upload_datasource_missing_column_returns_422 -v`
Expected: 422 for the success test (because mapping fields aren't wired into the endpoint yet).

- [ ] **Step 3: Update the endpoint**

In `src/d4bl/app/upload_routes.py`, replace the `upload_datasource` handler (the entire `@router.post("/api/admin/uploads/datasource", ...)` function) with:

```python
@router.post("/api/admin/uploads/datasource", response_model=UploadResponse)
async def upload_datasource(
    file: UploadFile = File(...),
    source_name: str = Form(...),
    description: str = Form(...),
    geographic_level: str = Form(...),
    data_year: int = Form(...),
    geo_column: str = Form(...),
    metric_value_column: str = Form(...),
    metric_name: str = Form(...),
    race_column: str | None = Form(None),
    year_column: str | None = Form(None),
    source_url: str | None = Form(None),
    category_tags: str | None = Form(None),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a CSV/XLSX data source with declared column mapping.

    The file is parsed, validated, and normalized at upload time. Rows are
    bulk-inserted into ``uploaded_datasets`` in the same transaction as the
    ``Upload`` row. Admin approval later flips the status; no processing step
    is required post-approval.
    """
    ext = _file_ext(file.filename)
    if ext not in ALLOWED_DATASOURCE_EXT:
        raise HTTPException(400, f"File type {ext!r} not allowed. Use: {ALLOWED_DATASOURCE_EXT}")

    tags = [t.strip() for t in category_tags.split(",") if t.strip()] if category_tags else None

    try:
        validated = DataSourceUploadRequest(
            source_name=source_name,
            description=description,
            geographic_level=geographic_level,
            data_year=data_year,
            source_url=source_url,
            category_tags=tags,
            geo_column=geo_column,
            metric_value_column=metric_value_column,
            metric_name=metric_name,
            race_column=race_column or None,
            year_column=year_column or None,
        )
    except ValidationError as exc:
        raise HTTPException(422, detail=exc.errors()) from exc

    content = await file.read()
    if len(content) > MAX_DATASOURCE_SIZE:
        raise HTTPException(400, f"File too large. Max {MAX_DATASOURCE_SIZE // (1024 * 1024)}MB")
    if len(content) == 0:
        raise HTTPException(400, "File is empty")

    mapping = MappingConfig(
        geo_column=validated.geo_column,
        metric_value_column=validated.metric_value_column,
        metric_name=validated.metric_name,
        race_column=validated.race_column,
        year_column=validated.year_column,
        data_year=validated.data_year,
    )
    try:
        parse_result = await asyncio.to_thread(
            parse_datasource_file, content, ext, mapping,
        )
    except DatasourceParseError as exc:
        raise HTTPException(422, detail=exc.detail) from exc

    upload_id = uuid4()
    safe_name = _safe_filename(file.filename)

    upload = Upload(
        id=upload_id,
        user_id=user.id,
        upload_type="datasource",
        status="pending_review",
        file_path=None,
        original_filename=safe_name,
        file_size_bytes=len(content),
        metadata_={
            "source_name": validated.source_name,
            "description": validated.description,
            "geographic_level": validated.geographic_level,
            "data_year": validated.data_year,
            "source_url": validated.source_url,
            "category_tags": validated.category_tags,
            "mapping": {
                "geo_column": validated.geo_column,
                "metric_value_column": validated.metric_value_column,
                "metric_name": validated.metric_name,
                "race_column": validated.race_column,
                "year_column": validated.year_column,
            },
            "row_count": parse_result.row_count,
            "dropped_counts": parse_result.dropped_counts,
            "preview_rows": parse_result.preview_rows,
        },
    )
    db.add(upload)

    # Bulk insert normalized rows. Chunk to keep each statement reasonable.
    chunk_size = 1000
    rows = parse_result.normalized_rows
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        params = [
            {
                "upload_id": str(upload_id),
                "row_index": i + j,
                "data": json.dumps(row),
            }
            for j, row in enumerate(chunk)
        ]
        await db.execute(
            text(
                "INSERT INTO uploaded_datasets (upload_id, row_index, data) "
                "VALUES (CAST(:upload_id AS uuid), :row_index, CAST(:data AS jsonb))"
            ),
            params,
        )

    await db.commit()
    return _upload_to_response(upload)
```

Also add to the imports at the top of `src/d4bl/app/upload_routes.py` (add alongside the existing imports):

```python
import json
from d4bl.services.datasource_processing.parser import (
    DatasourceParseError,
    MappingConfig,
    parse_datasource_file,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_upload_api.py -v`
Expected: all upload tests pass including the two new ones.

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/app/upload_routes.py tests/test_upload_api.py
git commit -m "feat(uploads): parse+validate+persist datasource uploads"
```

---

## Task 9: Verify approval flow for datasources

No code change expected — the existing review handler already flips non-document uploads to `approved`. Add a regression test so future edits don't drop this path.

**Files:**
- Modify: `tests/test_upload_api.py`

- [ ] **Step 1: Write the test**

Append to `tests/test_upload_api.py` in the `TestUploadEndpoints` class:

```python
    @pytest.mark.asyncio
    async def test_review_datasource_approve_is_pure_flip(self, admin_client, override_db):
        """Approving a datasource upload is a status flip — no processing call."""
        mock_db = override_db
        # First SELECT: upload exists, status=pending_review, type=datasource.
        fetch_result = MagicMock()
        fetch_result.mappings.return_value.first.return_value = {
            "id": "00000000-0000-0000-0000-00000000aaaa",
            "status": "pending_review",
            "upload_type": "datasource",
        }
        # Subsequent UPDATE executes return a no-op MagicMock.
        mock_db.execute = AsyncMock(side_effect=[fetch_result, MagicMock()])

        resp = await admin_client.patch(
            "/api/admin/uploads/00000000-0000-0000-0000-00000000aaaa/review",
            json={"action": "approve", "notes": None},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "approved"
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/test_upload_api.py::TestUploadEndpoints::test_review_datasource_approve_is_pure_flip -v`
Expected: passes without any code change (existing handler already does this).

- [ ] **Step 3: Commit**

```bash
git add tests/test_upload_api.py
git commit -m "test(uploads): pin datasource approval is a pure status flip"
```

---

## Task 10: New endpoint `GET /api/explore/staff-uploads/available`

Picker data — lists approved datasource uploads with per-upload metadata.

**Files:**
- Modify: `src/d4bl/app/api.py` (add after the existing `/api/explore/bjs` endpoint, around line 1600)
- Modify: `tests/test_explore_api.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_explore_api.py`:

```python
class TestStaffUploadsAvailable:

    @pytest.mark.asyncio
    async def test_available_returns_only_approved_datasource_uploads(
        self, user_client, override_db
    ):
        mock_db = override_db
        rows = [
            {
                "id": "00000000-0000-0000-0000-00000000a001",
                "metadata": {
                    "source_name": "Eviction Rates 2023",
                    "geographic_level": "county",
                    "data_year": 2023,
                    "mapping": {
                        "metric_name": "eviction_rate",
                        "race_column": "race",
                    },
                    "row_count": 3142,
                },
                "reviewed_at": None,
                "uploader_name": "Alice",
            },
        ]
        fetch_result = MagicMock()
        fetch_result.mappings.return_value.all.return_value = rows
        mock_db.execute = AsyncMock(return_value=fetch_result)

        resp = await user_client.get("/api/explore/staff-uploads/available")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["metric_name"] == "eviction_rate"
        assert data[0]["has_race"] is True
        assert data[0]["row_count"] == 3142

    @pytest.mark.asyncio
    async def test_available_requires_auth(self, unauth_client):
        resp = await unauth_client.get("/api/explore/staff-uploads/available")
        assert resp.status_code == 401
```

Make sure `user_client`, `unauth_client`, and `override_db` fixtures are imported or available via `conftest.py` — if not, add them at the top of `tests/test_explore_api.py`:

```python
from unittest.mock import AsyncMock, MagicMock
import pytest
from httpx import ASGITransport, AsyncClient
from d4bl.app.api import app


@pytest.fixture
async def user_client(override_auth):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def unauth_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def override_db(mock_db_session):
    from d4bl.infra.database import get_db
    app.dependency_overrides[get_db] = lambda: mock_db_session
    yield mock_db_session
    app.dependency_overrides.pop(get_db, None)
```

(Skip any fixture that already exists in the file.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_explore_api.py::TestStaffUploadsAvailable -v`
Expected: 404s (endpoint doesn't exist yet).

- [ ] **Step 3: Add the endpoint**

In `src/d4bl/app/api.py`, add after the existing staff / explore endpoints (e.g. after the `/api/explore/bjs` handler):

```python
@app.get("/api/explore/staff-uploads/available")
async def list_staff_upload_datasets(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List approved staff-contributed datasource uploads for the picker."""
    result = await db.execute(
        text("""
            SELECT u.id, u.metadata, u.reviewed_at,
                   p.display_name AS uploader_name
            FROM uploads u
            LEFT JOIN profiles p ON p.id = u.user_id
            WHERE u.upload_type = 'datasource' AND u.status = 'approved'
            ORDER BY u.reviewed_at DESC NULLS LAST
        """)
    )
    rows = result.mappings().all()
    out = []
    for r in rows:
        metadata = r["metadata"] or {}
        mapping = metadata.get("mapping") or {}
        out.append({
            "upload_id": str(r["id"]),
            "source_name": metadata.get("source_name"),
            "metric_name": mapping.get("metric_name"),
            "geographic_level": metadata.get("geographic_level"),
            "data_year": metadata.get("data_year"),
            "has_race": bool(mapping.get("race_column")),
            "row_count": metadata.get("row_count"),
            "uploader_name": r["uploader_name"],
            "approved_at": r["reviewed_at"].isoformat() if r["reviewed_at"] else None,
        })
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_explore_api.py::TestStaffUploadsAvailable -v`
Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/app/api.py tests/test_explore_api.py
git commit -m "feat(explore): add staff-uploads/available endpoint"
```

---

## Task 11: New endpoint `GET /api/explore/staff-uploads`

Main endpoint. Returns `ExploreResponse` for one approved upload.

**Files:**
- Modify: `src/d4bl/app/api.py`
- Modify: `tests/test_explore_api.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_explore_api.py`:

```python
class TestStaffUploadsExplore:

    @pytest.mark.asyncio
    async def test_returns_explore_response_shape(self, user_client, override_db):
        mock_db = override_db
        # First call: fetch metadata + metric_name.
        meta_result = MagicMock()
        meta_result.mappings.return_value.first.return_value = {
            "source_name": "Eviction Rates 2023",
            "mapping": {"metric_name": "eviction_rate", "race_column": "race"},
        }
        # Second call: aggregated rows.
        rows_result = MagicMock()
        rows_result.mappings.return_value.all.return_value = [
            {"state_fips": "13", "value": 14.3, "race": "Black", "year": 2023},
            {"state_fips": "06", "value": 9.1, "race": None, "year": 2023},
        ]
        mock_db.execute = AsyncMock(side_effect=[meta_result, rows_result])

        resp = await user_client.get(
            "/api/explore/staff-uploads?upload_id=00000000-0000-0000-0000-00000000a001"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["available_metrics"] == ["eviction_rate"]
        assert len(data["rows"]) == 2
        assert data["rows"][0]["metric"] == "eviction_rate"
        assert data["rows"][0]["state_name"]  # non-empty string

    @pytest.mark.asyncio
    async def test_missing_upload_id_returns_422(self, user_client, override_db):
        resp = await user_client.get("/api/explore/staff-uploads")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_non_approved_upload_returns_404(self, user_client, override_db):
        mock_db = override_db
        meta_result = MagicMock()
        meta_result.mappings.return_value.first.return_value = None
        mock_db.execute = AsyncMock(return_value=meta_result)

        resp = await user_client.get(
            "/api/explore/staff-uploads?upload_id=00000000-0000-0000-0000-00000000dead"
        )
        assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_explore_api.py::TestStaffUploadsExplore -v`
Expected: 404s on all (endpoint missing).

- [ ] **Step 3: Add the endpoint**

In `src/d4bl/app/api.py`, add right above the `/api/explore/staff-uploads/available` handler:

```python
@app.get("/api/explore/staff-uploads", response_model=ExploreResponse)
async def get_staff_upload_rows(
    request: Request,
    upload_id: UUID,
    state_fips: str | None = None,
    race: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return rows for one approved staff-uploaded datasource in the shared
    ``ExploreResponse`` shape so the frontend reuses built-in map/chart/table
    components unchanged."""
    cache_key = f"{request.url.path}?{request.query_params}"
    cached = explore_cache.get(cache_key)
    if cached is not None:
        return cached

    meta_result = await db.execute(
        text("""
            SELECT metadata ->> 'source_name' AS source_name,
                   metadata -> 'mapping'      AS mapping
            FROM uploads
            WHERE id = CAST(:uid AS uuid)
              AND upload_type = 'datasource'
              AND status = 'approved'
        """),
        {"uid": str(upload_id)},
    )
    meta_row = meta_result.mappings().first()
    if not meta_row:
        raise HTTPException(404, "Not found or not approved")
    mapping = meta_row["mapping"] or {}
    metric_name = mapping.get("metric_name") or "metric"

    params: dict = {
        "uid": str(upload_id),
        "state_fips": state_fips,
        "race": race,
        "year": year,
        "limit": max(1, min(limit, 5000)),
    }
    rows_result = await db.execute(
        text("""
            SELECT ud.data ->> 'state_fips'               AS state_fips,
                   AVG((ud.data ->> 'value')::float)      AS value,
                   ud.data ->> 'race'                     AS race,
                   (ud.data ->> 'year')::int              AS year
            FROM uploaded_datasets ud
            JOIN uploads u ON u.id = ud.upload_id
            WHERE u.id = CAST(:uid AS uuid)
              AND u.upload_type = 'datasource'
              AND u.status = 'approved'
              AND (:state_fips IS NULL OR ud.data ->> 'state_fips' = :state_fips)
              AND (:race IS NULL OR ud.data ->> 'race' = :race)
              AND (:year IS NULL OR (ud.data ->> 'year')::int = :year)
            GROUP BY state_fips, race, year
            ORDER BY state_fips, race, year
            LIMIT :limit
        """),
        params,
    )
    rows_raw = rows_result.mappings().all()

    rows = [
        {
            "state_fips": r["state_fips"],
            "state_name": FIPS_TO_STATE_NAME.get(r["state_fips"], r["state_fips"]),
            "value": float(r["value"]) if r["value"] is not None else 0.0,
            "metric": metric_name,
            "year": r["year"],
            "race": r["race"],
        }
        for r in rows_raw
    ]

    response = {
        "rows": rows,
        "national_average": compute_national_avg(rows),
        "available_metrics": [metric_name],
        "available_years": distinct_values(rows, "year"),
        "available_races": distinct_values(rows, "race"),
    }
    explore_cache.set(cache_key, response)
    return response
```

Add `from uuid import UUID` to imports at the top of `api.py` if not already present, and make sure `compute_national_avg`, `distinct_values`, `FIPS_TO_STATE_NAME`, and `ExploreResponse` are imported (they already are — per `explore_helpers` + `schemas`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_explore_api.py::TestStaffUploadsExplore -v`
Expected: all three pass.

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/app/api.py tests/test_explore_api.py
git commit -m "feat(explore): add staff-uploads main endpoint"
```

---

## Task 12: Frontend `UploadDataSource` form — add mapping fields

**Files:**
- Modify: `ui-nextjs/components/admin/UploadDataSource.tsx`

- [ ] **Step 1: Add mapping state hooks**

Near the other `useState` declarations at the top of the component, add:

```tsx
const [geoColumn, setGeoColumn] = useState('');
const [metricValueColumn, setMetricValueColumn] = useState('');
const [metricName, setMetricName] = useState('');
const [hasRaceColumn, setHasRaceColumn] = useState(false);
const [raceColumn, setRaceColumn] = useState('');
const [hasYearColumn, setHasYearColumn] = useState(false);
const [yearColumn, setYearColumn] = useState('');
```

- [ ] **Step 2: Append the fields to `FormData` in `handleSubmit`**

After the existing `formData.append('data_year', ...)` line, add:

```tsx
formData.append('geo_column', geoColumn);
formData.append('metric_value_column', metricValueColumn);
formData.append('metric_name', metricName);
if (hasRaceColumn && raceColumn) formData.append('race_column', raceColumn);
if (hasYearColumn && yearColumn) formData.append('year_column', yearColumn);
```

Also reset the new fields in the post-success reset block (where `setSourceUrl('')` lives):

```tsx
setGeoColumn('');
setMetricValueColumn('');
setMetricName('');
setHasRaceColumn(false);
setRaceColumn('');
setHasYearColumn(false);
setYearColumn('');
```

- [ ] **Step 3: Render a detailed error for structured 422 bodies**

Replace the current error-catch block in `handleSubmit`:

```tsx
} else {
  const data = await resp.json().catch(() => ({}));
  setError(formatUploadError(data.detail) || 'Upload failed. Please try again.');
}
```

And add this helper above the `export default function UploadDataSource` line:

```tsx
function formatUploadError(detail: unknown): string | null {
  if (!detail) return null;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => {
      if (typeof d === 'string') return d;
      if (d && typeof d === 'object' && 'msg' in d) return String((d as { msg: unknown }).msg);
      return JSON.stringify(d);
    }).join('; ');
  }
  if (typeof detail === 'object') {
    const obj = detail as Record<string, unknown>;
    if (Array.isArray(obj.missing_columns)) {
      return `Missing columns in file header: ${(obj.missing_columns as string[]).join(', ')}`;
    }
    if (obj.dropped && typeof obj.dropped === 'object') {
      const d = obj.dropped as Record<string, unknown>;
      return `Too many invalid rows (${d.reason}): ${d.count} of ${d.total}`;
    }
    if (obj.reason === 'too_few_rows') {
      return `Only ${obj.valid} valid rows after validation — need at least 10.`;
    }
    if (typeof obj.message === 'string') return obj.message;
  }
  return JSON.stringify(detail);
}
```

- [ ] **Step 4: Add the mapping section markup**

In the JSX, add a new section after the existing `source_url` and `category_tags` fields but before the submit button. Use the same visual style as the existing fields:

```tsx
<div className="pt-3 border-t border-[#404040]">
  <h3 className="text-sm font-semibold text-white mb-2">Column mapping</h3>
  <p className="text-xs text-gray-500 mb-3">
    Tell the admin which column means what. Missing or incorrect mappings
    show up as an error immediately.
  </p>
  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
    <div>
      <label htmlFor="ds-geo-column" className="block text-sm font-medium text-gray-300 mb-1">
        Geo column name <span className="text-red-400">*</span>
      </label>
      <input
        id="ds-geo-column"
        type="text"
        value={geoColumn}
        onChange={(e) => setGeoColumn(e.target.value)}
        required
        placeholder="e.g. county_fips"
        className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                   focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
      />
      <p className="mt-1 text-xs text-gray-500">
        State (2-digit), county (5-digit), or tract (11-digit) FIPS code column.
      </p>
    </div>

    <div>
      <label htmlFor="ds-metric-value-column" className="block text-sm font-medium text-gray-300 mb-1">
        Metric value column <span className="text-red-400">*</span>
      </label>
      <input
        id="ds-metric-value-column"
        type="text"
        value={metricValueColumn}
        onChange={(e) => setMetricValueColumn(e.target.value)}
        required
        placeholder="e.g. filing_rate"
        className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                   focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
      />
      <p className="mt-1 text-xs text-gray-500">
        The numeric column to plot on the map.
      </p>
    </div>
  </div>

  <div className="mt-4">
    <label htmlFor="ds-metric-name" className="block text-sm font-medium text-gray-300 mb-1">
      Metric name <span className="text-red-400">*</span>
    </label>
    <input
      id="ds-metric-name"
      type="text"
      value={metricName}
      onChange={(e) => setMetricName(e.target.value)}
      required
      pattern="[a-z0-9_]{1,64}"
      placeholder="e.g. eviction_filing_rate"
      className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                 focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
    />
    <p className="mt-1 text-xs text-gray-500">
      Lowercase, snake_case, 1–64 chars. Becomes the metric identifier on /explore.
    </p>
  </div>

  <div className="mt-4 space-y-3">
    <label className="flex items-center gap-2 text-sm text-gray-300">
      <input
        type="checkbox"
        checked={hasRaceColumn}
        onChange={(e) => setHasRaceColumn(e.target.checked)}
      />
      This dataset has a racial/ethnic breakdown column
    </label>
    {hasRaceColumn && (
      <input
        type="text"
        value={raceColumn}
        onChange={(e) => setRaceColumn(e.target.value)}
        required
        placeholder="e.g. race"
        className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                   focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
      />
    )}

    <label className="flex items-center gap-2 text-sm text-gray-300">
      <input
        type="checkbox"
        checked={hasYearColumn}
        onChange={(e) => setHasYearColumn(e.target.checked)}
      />
      This dataset has a year column
    </label>
    {hasYearColumn && (
      <input
        type="text"
        value={yearColumn}
        onChange={(e) => setYearColumn(e.target.value)}
        required
        placeholder="e.g. year"
        className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                   focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
      />
    )}
  </div>
</div>
```

- [ ] **Step 5: Build and lint**

Run (from `ui-nextjs/`):
```bash
npm run build
npm run lint
```
Expected: both succeed with no new errors.

- [ ] **Step 6: Commit**

```bash
git add ui-nextjs/components/admin/UploadDataSource.tsx
git commit -m "feat(upload-ui): add column mapping fields to datasource form"
```

---

## Task 13: Frontend `ReviewDetail` — datasource-aware rendering

**Files:**
- Modify: `ui-nextjs/components/admin/ReviewDetail.tsx`

- [ ] **Step 1: Add a datasource rendering block**

Above `metadataEntries`, add a branch that short-circuits for datasource uploads:

```tsx
const mapping = upload.metadata?.mapping as Record<string, string | null> | undefined;
const previewRows = upload.metadata?.preview_rows as Array<Record<string, unknown>> | undefined;
const rowCount = upload.metadata?.row_count as number | undefined;
const isDatasource = upload.upload_type === 'datasource';
```

- [ ] **Step 2: Insert the datasource section above the existing metadata list**

Find the current `<div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">` block that renders "Uploader / Type / Filename" and add immediately after it (but inside the outer container):

```tsx
{isDatasource && mapping && (
  <div className="space-y-3">
    <div>
      <p className="text-gray-500 text-xs uppercase tracking-wide mb-1">Column mapping</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
        <div><span className="text-gray-500">geo:</span> <span className="text-gray-200">{mapping.geo_column}</span></div>
        <div><span className="text-gray-500">value:</span> <span className="text-gray-200">{mapping.metric_value_column}</span></div>
        <div><span className="text-gray-500">metric name:</span> <span className="text-gray-200">{mapping.metric_name}</span></div>
        <div><span className="text-gray-500">race:</span> <span className="text-gray-200">{mapping.race_column ?? <em>(none)</em>}</span></div>
        <div><span className="text-gray-500">year:</span> <span className="text-gray-200">{mapping.year_column ?? <em>(uses data_year)</em>}</span></div>
      </div>
    </div>
    <div className="text-sm text-gray-400">
      {rowCount ?? 0} rows · geographic level: {String(upload.metadata?.geographic_level ?? '')} · data year: {String(upload.metadata?.data_year ?? '')}
    </div>
    {previewRows && previewRows.length > 0 && (
      <div>
        <p className="text-gray-500 text-xs uppercase tracking-wide mb-1">Preview (first {previewRows.length})</p>
        <div className="overflow-x-auto">
          <table className="text-xs text-gray-300 border border-[#404040]">
            <thead className="bg-[#292929]">
              <tr>
                <th className="px-2 py-1 text-left">state_fips</th>
                <th className="px-2 py-1 text-left">race</th>
                <th className="px-2 py-1 text-left">year</th>
                <th className="px-2 py-1 text-left">value</th>
              </tr>
            </thead>
            <tbody>
              {previewRows.map((row, i) => (
                <tr key={i} className="border-t border-[#404040]">
                  <td className="px-2 py-1">{String(row.state_fips ?? '')}</td>
                  <td className="px-2 py-1">{row.race == null ? '—' : String(row.race)}</td>
                  <td className="px-2 py-1">{String(row.year ?? '')}</td>
                  <td className="px-2 py-1">{String(row.value ?? '')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )}
  </div>
)}
```

- [ ] **Step 3: Filter the generic metadata list so we don't double-show mapping / preview_rows**

In the line that computes `metadataEntries`, extend the filter:

```tsx
const HIDE_GENERIC_KEYS = new Set(['mapping', 'preview_rows', 'row_count', 'dropped_counts', 'full_text', 'preview_text']);

const metadataEntries = upload.metadata
  ? Object.entries(upload.metadata).filter(
      ([k, v]) => v !== null && v !== undefined && v !== '' && !HIDE_GENERIC_KEYS.has(k),
    )
  : [];
```

- [ ] **Step 4: Build and lint**

Run (from `ui-nextjs/`):
```bash
npm run build
npm run lint
```
Expected: both succeed.

- [ ] **Step 5: Commit**

```bash
git add ui-nextjs/components/admin/ReviewDetail.tsx
git commit -m "feat(review-ui): datasource-aware mapping + preview rendering"
```

---

## Task 14: Frontend `explore-config.ts` — add staff-uploads source

**Files:**
- Modify: `ui-nextjs/lib/explore-config.ts`

- [ ] **Step 1: Append the new `DataSourceConfig`**

At the end of the `DATA_SOURCES` array (right before the closing `];`), insert:

```ts
{
  key: "staff-uploads",
  label: "Staff Uploads",
  accent: "#a29bfe",
  endpoint: "/api/explore/staff-uploads",
  hasRace: true,
  primaryFilterKey: "metric",
  primaryFilterLabel: "Dataset",
  description: "Approved data sources contributed by staff. Each dataset reflects its contributor's methodology and column definitions.",
  sourceUrl: "",
  hasData: true,
},
```

- [ ] **Step 2: Add `METRIC_DIRECTION` entry**

Inside the `METRIC_DIRECTION` object, add a new key before the closing `};`:

```ts
"staff-uploads": { default: null },
```

- [ ] **Step 3: Build and lint**

Run (from `ui-nextjs/`):
```bash
npm run build
npm run lint
```
Expected: both succeed.

- [ ] **Step 4: Commit**

```bash
git add ui-nextjs/lib/explore-config.ts
git commit -m "feat(explore): add staff-uploads DataSourceConfig"
```

---

## Task 15: Frontend `StaffDatasetPicker` component

**Files:**
- Create: `ui-nextjs/components/explore/StaffDatasetPicker.tsx`

- [ ] **Step 1: Write the component**

Create `ui-nextjs/components/explore/StaffDatasetPicker.tsx`:

```tsx
'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';

export interface StaffDatasetSummary {
  upload_id: string;
  source_name: string;
  metric_name: string;
  geographic_level: string;
  data_year: number;
  has_race: boolean;
  row_count: number;
  uploader_name: string | null;
  approved_at: string | null;
}

interface Props {
  value: string | null;
  onChange: (uploadId: string | null, summary: StaffDatasetSummary | null) => void;
}

export default function StaffDatasetPicker({ value, onChange }: Props) {
  const { session } = useAuth();
  const [datasets, setDatasets] = useState<StaffDatasetSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session?.access_token) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`${API_BASE}/api/explore/staff-uploads/available`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
    })
      .then(async (resp) => {
        if (cancelled) return;
        if (!resp.ok) {
          setError('Failed to load staff datasets.');
          return;
        }
        const data = await resp.json();
        setDatasets(Array.isArray(data) ? data : []);
      })
      .catch(() => { if (!cancelled) setError('Failed to load staff datasets.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [session?.access_token]);

  if (loading) return <div className="text-sm text-gray-400">Loading datasets...</div>;
  if (error) return <div className="text-sm text-red-400">{error}</div>;
  if (datasets.length === 0) {
    return (
      <div className="text-sm text-gray-400">
        No staff datasets approved yet. Contributors can upload data sources under Admin &gt; Data Sources.
      </div>
    );
  }

  return (
    <div>
      <label htmlFor="staff-dataset-picker" className="block text-sm font-medium text-gray-300 mb-1">
        Dataset
      </label>
      <select
        id="staff-dataset-picker"
        value={value ?? ''}
        onChange={(e) => {
          const id = e.target.value || null;
          const summary = datasets.find((d) => d.upload_id === id) ?? null;
          onChange(id, summary);
        }}
        className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white text-sm"
      >
        <option value="">-- Pick a dataset --</option>
        {datasets.map((d) => (
          <option key={d.upload_id} value={d.upload_id}>
            {d.source_name} · {d.metric_name} · {d.data_year} ({d.row_count} rows)
          </option>
        ))}
      </select>
    </div>
  );
}
```

- [ ] **Step 2: Build**

Run (from `ui-nextjs/`): `npm run build`
Expected: succeeds (component is unused until Task 16 wires it in — that's fine, tsc checks types in isolation).

- [ ] **Step 3: Commit**

```bash
git add ui-nextjs/components/explore/StaffDatasetPicker.tsx
git commit -m "feat(explore-ui): add StaffDatasetPicker component"
```

---

## Task 16: Frontend `explore/page.tsx` — wire picker + conditional race filter + persistence

**Files:**
- Modify: `ui-nextjs/app/explore/page.tsx`
- Modify: `ui-nextjs/components/explore/MetricFilterPanel.tsx` (likely — depending on filter implementation)

- [ ] **Step 1: Extend `ExploreFilters` + filter state**

At the top of `explore/page.tsx` where `ExploreFilters` is imported or defined, add a new optional field. If it's imported from `MetricFilterPanel.tsx`, extend there:

In `ui-nextjs/components/explore/MetricFilterPanel.tsx`, extend the `ExploreFilters` interface to include:

```ts
uploadId: string | null;
```

Back in `explore/page.tsx`, update every place where `ExploreFilters` defaults are created (e.g. around `metric: filters.metric || null,`) to include:

```ts
uploadId: filters.uploadId ?? null,
```

And in the initial state factory (around line 82-92):

```ts
metric: '',
uploadId: null,
```

- [ ] **Step 2: Persist `uploadId` in localStorage**

The `STORAGE_KEY = 'd4bl-explore-filters'` persistence already round-trips the `filters` object. Just verify the persisted shape includes `uploadId` after step 1 (no extra code needed because the save path spreads the full `filters`).

- [ ] **Step 3: Include `upload_id` in the fetch URL**

Find the block that builds the explore fetch URL (around `if (filters.metric) params.set(activeSource.primaryFilterKey, filters.metric);`) and add:

```ts
if (activeSource.key === 'staff-uploads' && filters.uploadId) {
  params.set('upload_id', filters.uploadId);
}
```

- [ ] **Step 4: Short-circuit the fetch when no upload is picked**

Immediately before the `fetch(...)` call, add:

```ts
if (activeSource.key === 'staff-uploads' && !filters.uploadId) {
  setExploreData(null);
  return;
}
```

- [ ] **Step 5: Render the picker above the filter panel**

Find where `<MetricFilterPanel />` is rendered. Add (at the same level or wrapping) a conditional:

```tsx
import StaffDatasetPicker, { StaffDatasetSummary } from '@/components/explore/StaffDatasetPicker';

// inside the component:
const [activeUploadSummary, setActiveUploadSummary] = useState<StaffDatasetSummary | null>(null);

// in the JSX, right above MetricFilterPanel:
{activeSource.key === 'staff-uploads' && (
  <div className="mb-4">
    <StaffDatasetPicker
      value={filters.uploadId}
      onChange={(id, summary) => {
        setActiveUploadSummary(summary);
        setFilters((prev) => ({
          ...prev,
          uploadId: id,
          // Reset metric-label-only filters on dataset change so the
          // map doesn't stick to a previous dataset's race/year.
          race: null,
          year: null,
        }));
      }}
    />
  </div>
)}
```

- [ ] **Step 6: Hide the race filter when the picked upload has no race column**

Find the prop used by `MetricFilterPanel` to know whether to show the race filter. If the current pattern is `source.hasRace`, compute an effective flag:

```ts
const effectiveHasRace = activeSource.key === 'staff-uploads'
  ? (activeUploadSummary?.has_race ?? false)
  : activeSource.hasRace;
```

Pass `effectiveHasRace` down to `<MetricFilterPanel hasRace={effectiveHasRace} ... />`. If `MetricFilterPanel` takes the full `source` object, instead pass a shallow copy: `source={{ ...activeSource, hasRace: effectiveHasRace }}`.

- [ ] **Step 7: Render an empty-state when Staff Uploads is active with no selection**

Where the existing empty-state is rendered (the `<EmptyDataState ... />` block), add an earlier branch:

```tsx
if (activeSource.key === 'staff-uploads' && !filters.uploadId) {
  return (
    <div className="text-gray-400 text-sm py-12 text-center">
      Pick a dataset from the Dataset dropdown above to view it on the map.
    </div>
  );
}
```

- [ ] **Step 8: Build, lint, and exercise manually**

Run (from `ui-nextjs/`): `npm run build && npm run lint`
Expected: both succeed.

Then start the app and exercise:
1. `npm run dev` (frontend)
2. Navigate to `/explore`, switch to the Staff Uploads tab.
3. Confirm the picker appears and the empty-state message shows when no dataset is picked.

- [ ] **Step 9: Commit**

```bash
git add ui-nextjs/app/explore/page.tsx ui-nextjs/components/explore/MetricFilterPanel.tsx
git commit -m "feat(explore-ui): wire staff-uploads picker with conditional race filter"
```

---

## Task 17: Guide Section 1 copy update

**Files:**
- Modify: `ui-nextjs/app/guide/page.tsx`

- [ ] **Step 1: Update Section 1 "What happens after" paragraph**

In the `<GuideSection title="Adding a Data Source">` block, replace the "What happens after" paragraph. Find:

```tsx
<p>
  <span className="text-white font-semibold">What happens after:</span>{' '}
  An admin reviews your upload and marks it approved or rejected.
  Automated processing and indexing is planned for a follow-up release.
</p>
```

Replace with:

```tsx
<p>
  <span className="text-white font-semibold">What happens after:</span>{' '}
  When you upload, the platform parses your file immediately, validates the
  columns you mapped, and surfaces any errors back to you — so you know it
  landed cleanly before an admin ever sees it. An admin then reviews your
  declared mapping and a preview of the parsed rows. Once approved, your
  dataset appears under the <span className="text-[#00ff32]">Staff Uploads</span>{' '}
  tab on <span className="text-[#00ff32]">/explore</span>, where users can
  view it on the state map alongside built-in sources. Rejected uploads
  never reach <span className="text-[#00ff32]">/explore</span>.
</p>
```

- [ ] **Step 2: Update the "How to upload" paragraph**

Find:

```tsx
<p>
  <span className="text-white font-semibold">How to upload:</span>{' '}
  Go to <span className="text-[#00ff32]">Admin &gt; Data Sources</span> tab. Fill in
  the source name, select your file, and add any relevant notes. Your submission
  enters the review queue immediately.
</p>
```

Replace with:

```tsx
<p>
  <span className="text-white font-semibold">How to upload:</span>{' '}
  Go to <span className="text-[#00ff32]">Admin &gt; Data Sources</span> tab.
  Fill in the source name, select your file, and add any relevant notes.
  You'll also declare which column is the geographic identifier, which
  column holds the metric value, and a short snake_case name for the metric.
  If your file has racial or yearly breakdowns, you can map those columns too.
  Your submission enters the review queue immediately.
</p>
```

- [ ] **Step 3: Update the "Example" paragraph**

Find:

```tsx
<p>
  <span className="text-white font-semibold">Example:</span>{' '}
  A county-level CSV from{' '}
  <span className="text-gray-300">County Health Rankings</span> with columns like{' '}
  <code className="text-xs bg-[#292929] px-1 py-0.5 rounded">county_fips</code>,{' '}
  <code className="text-xs bg-[#292929] px-1 py-0.5 rounded">race</code>, and{' '}
  <code className="text-xs bg-[#292929] px-1 py-0.5 rounded">premature_death_rate</code>{' '}
  is a great fit.
</p>
```

Replace with:

```tsx
<p>
  <span className="text-white font-semibold">Example:</span>{' '}
  A county-level CSV from{' '}
  <span className="text-gray-300">County Health Rankings</span> with columns
  like <code className="text-xs bg-[#292929] px-1 py-0.5 rounded">county_fips</code>,{' '}
  <code className="text-xs bg-[#292929] px-1 py-0.5 rounded">race</code>, and{' '}
  <code className="text-xs bg-[#292929] px-1 py-0.5 rounded">premature_death_rate</code>{' '}
  — mapped as{' '}
  <code className="text-xs bg-[#292929] px-1 py-0.5 rounded">geo_column=county_fips</code>,{' '}
  <code className="text-xs bg-[#292929] px-1 py-0.5 rounded">metric_value_column=premature_death_rate</code>,{' '}
  <code className="text-xs bg-[#292929] px-1 py-0.5 rounded">metric_name=premature_death_rate</code>,{' '}
  <code className="text-xs bg-[#292929] px-1 py-0.5 rounded">race_column=race</code>{' '}
  — is a great fit.
</p>
```

- [ ] **Step 4: Build**

Run (from `ui-nextjs/`): `npm run build`
Expected: succeeds.

- [ ] **Step 5: Commit**

```bash
git add ui-nextjs/app/guide/page.tsx
git commit -m "docs(guide): describe shipped datasource upload pipeline"
```

---

## Task 18: Full test run, manual QA, and PR

**Files:** N/A (verification + PR creation)

- [ ] **Step 1: Run the full Python test suite**

Run: `pytest -x -q`
Expected: all tests pass, exit 0.

- [ ] **Step 2: Run the full frontend build + lint**

Run (from `ui-nextjs/`): `npm run build && npm run lint`
Expected: both succeed.

- [ ] **Step 3: Manual QA — happy path**

Start services:
```bash
# Terminal A
source .venv/bin/activate
python -m uvicorn d4bl.app.api:app --host 0.0.0.0 --port 8000

# Terminal B
cd ui-nextjs && npm run dev
```

As a regular user:
1. Go to `/admin`, Data Sources tab.
2. Upload a small CSV with columns `county_fips,race,rate` and ~15 rows across multiple states.
3. Fill in mapping: geo=`county_fips`, value=`rate`, metric name=`test_rate`, race column=`race`.
4. Confirm success message.

As an admin:
5. Go to review queue. Open the upload. Confirm mapping and preview rows render.
6. Approve it.

As any user:
7. Go to `/explore`, switch to Staff Uploads tab.
8. Pick the newly-approved dataset.
9. Confirm: map colours states, chart renders, data table populates, metric selector shows `test_rate`, race filter appears (because we mapped a race column).

- [ ] **Step 4: Manual QA — error paths**

1. Upload a CSV where `race_column` references a header that doesn't exist → confirm the inline error lists the missing column.
2. Upload a CSV with mostly non-numeric values in the value column → confirm the inline error mentions `non_numeric` and the count.
3. Reject an upload as admin → confirm it does NOT appear in the Staff Uploads picker.
4. Refresh the browser while a staff dataset is selected → confirm the selection survives (localStorage round-trip).

- [ ] **Step 5: Push and open the PR**

```bash
git push -u origin feat/190-datasource-pipeline
gh pr create \
  --title "feat: process approved data source uploads into /explore (#190)" \
  --body "$(cat <<'EOF'
## Summary

- Parses staff CSV/XLSX uploads at submit time with contributor-declared column mapping; normalized rows land in `uploaded_datasets` in the same transaction as the `Upload` row.
- New **Staff Uploads** tab on `/explore` with a dataset picker; approved uploads render through the existing map/chart/table components.
- Guide Section 1 now describes the shipped behavior.

Closes #190.

## Spec + plan

- Spec: `docs/superpowers/specs/2026-04-18-datasource-upload-pipeline-design.md`
- Plan: `docs/superpowers/plans/2026-04-18-datasource-upload-pipeline.md`

## Test plan

- [x] `pytest` — all tests pass
- [x] `npm run build && npm run lint` — clean
- [x] Upload a valid CSV → success; appears in pending review with mapping + preview.
- [x] Approve the upload → appears in Staff Uploads picker.
- [x] Upload with a typo'd `race_column` → inline 422 lists the missing column.
- [x] Upload with >10% non-numeric values → inline 422 with drop counts.
- [x] Reject an upload → does not appear in Staff Uploads picker.
- [x] Refresh `/explore` with a picked dataset → selection persists via localStorage.
EOF
)"
```

- [ ] **Step 6: Verify PR opens cleanly**

Run: `gh pr view --web`
Expected: PR opens in browser, CI runs.

---

## Spec coverage self-review

| Spec item | Task(s) |
| --- | --- |
| openpyxl dep | 1 |
| `datasource_processing` package | 1 |
| Validation helpers | 2 |
| `MappingConfig` + `DatasourceParseError` | 3 |
| CSV reader | 4 |
| XLSX reader | 5 |
| `parse_datasource_file` orchestrator + `ParseResult` | 6 |
| Schema mapping fields + `metric_name` validator | 7 |
| Upload endpoint: parse + bulk insert + 422 | 8 |
| Approval flow pure-flip regression | 9 |
| `/api/explore/staff-uploads/available` | 10 |
| `/api/explore/staff-uploads` main endpoint | 11 |
| Upload form mapping UI + structured 422 rendering | 12 |
| Review detail mapping + preview table | 13 |
| `DataSourceConfig` + `METRIC_DIRECTION` entry | 14 |
| `StaffDatasetPicker` component | 15 |
| Explore page wiring: filters, picker, conditional race filter, persistence, empty state | 16 |
| Guide Section 1 copy | 17 |
| End-to-end QA + PR | 18 |

Coverage is complete.
