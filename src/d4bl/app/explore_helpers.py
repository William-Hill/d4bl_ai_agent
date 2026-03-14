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


# FIPS -> full state name (shared lookup for aggregation endpoints)
FIPS_TO_STATE_NAME: dict[str, str] = {
    "01": "Alabama", "02": "Alaska", "04": "Arizona", "05": "Arkansas",
    "06": "California", "08": "Colorado", "09": "Connecticut", "10": "Delaware",
    "11": "District of Columbia", "12": "Florida", "13": "Georgia", "15": "Hawaii",
    "16": "Idaho", "17": "Illinois", "18": "Indiana", "19": "Iowa",
    "20": "Kansas", "21": "Kentucky", "22": "Louisiana", "23": "Maine",
    "24": "Maryland", "25": "Massachusetts", "26": "Michigan", "27": "Minnesota",
    "28": "Mississippi", "29": "Missouri", "30": "Montana", "31": "Nebraska",
    "32": "Nevada", "33": "New Hampshire", "34": "New Jersey", "35": "New Mexico",
    "36": "New York", "37": "North Carolina", "38": "North Dakota", "39": "Ohio",
    "40": "Oklahoma", "41": "Oregon", "42": "Pennsylvania", "44": "Rhode Island",
    "45": "South Carolina", "46": "South Dakota", "47": "Tennessee", "48": "Texas",
    "49": "Utah", "50": "Vermont", "51": "Virginia", "53": "Washington",
    "54": "West Virginia", "55": "Wisconsin", "56": "Wyoming",
}


def build_state_agg_response(
    rows_raw: Sequence[dict[str, Any]],
    metric_key: str,
) -> "ExploreResponse":
    """Build ExploreResponse from state-aggregated query mappings.

    Returns ExploreResponse for endpoints that aggregate sub-state data
    to state level via AVG/GROUP BY.
    """
    from d4bl.app.schemas import ExploreResponse, ExploreRow

    row_dicts = [
        {
            "state_fips": r["state_fips"],
            "state_name": FIPS_TO_STATE_NAME.get(r["state_fips"], r["state_fips"]),
            "value": r["avg_value"],
            "metric": r[metric_key],
            "year": r["year"],
            "race": None,
        }
        for r in rows_raw
    ]
    return ExploreResponse(
        rows=[ExploreRow(**d) for d in row_dicts],
        national_average=compute_national_avg(row_dicts),
        available_metrics=distinct_values(row_dicts, "metric"),
        available_years=distinct_values(row_dicts, "year"),
        available_races=[],
    )
