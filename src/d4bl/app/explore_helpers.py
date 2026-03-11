"""Shared helpers for explore API endpoints."""

from __future__ import annotations

from typing import Any, Sequence


def compute_national_avg(rows: Sequence[dict[str, Any]]) -> float | None:
    """Return mean of 'value' field across rows, or None if empty."""
    values = [r["value"] for r in rows if r.get("value") is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def distinct_values(rows: Sequence[dict[str, Any]], key: str) -> list[Any]:
    """Return sorted unique values for *key* across rows."""
    return sorted({r[key] for r in rows if r.get(key) is not None})
