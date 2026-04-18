"""Parse CSV/XLSX staff uploads into normalized ``uploaded_datasets`` rows.

Raises ``DatasourceParseError`` with a structured ``detail`` payload on any
validation failure so callers can surface actionable messages via HTTP 422.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Any

from openpyxl import load_workbook

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
