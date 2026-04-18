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
