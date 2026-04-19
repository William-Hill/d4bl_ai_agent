"""Pure validation + coercion helpers for staff datasource uploads.

Isolated from any IO so that each rule can be unit-tested directly.
"""

from __future__ import annotations

import math
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
    # Excel often drops a leading 0 on 5-digit county FIPS (e.g. 01001 → "1001").
    if len(s) == 4:
        s = "0" + s
    if len(s) == 1:
        s = "0" + s
    return s[:2]


def coerce_numeric(value: object) -> float:
    """Parse a numeric value, tolerating ``%``, commas, and whitespace.

    Raises ValueError for blanks, NaN, or anything else float() can't handle
    after the strip pipeline.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        n = float(value)
        if not math.isfinite(n):
            raise ValueError("value must be finite")
        return n
    if value is None:
        raise ValueError("value is empty")
    s = str(value).strip().rstrip("%").replace(",", "").strip()
    if not s or s.lower() == "nan":
        raise ValueError("value is empty or NaN")
    n = float(s)  # raises ValueError on malformed input
    if not math.isfinite(n):
        raise ValueError("value must be finite")
    return n


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
