"""Passage templates: convert structured DB rows to natural-language passages.

Each render_*_passage function accepts a dict representing one database row and
returns a plain-text string suitable for model pre-training.
"""

from __future__ import annotations

from scripts.ingestion.constants import STATE_ABBREV_TO_NAME

# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------

_DOLLAR_METRICS: set[str] = {
    "median_household_income",
    "median_earnings",
    "median_gross_rent",
}

_RATE_METRICS: set[str] = {
    "poverty_rate",
    "homeownership_rate",
    "unemployment_rate",
    "labor_force_participation",
}

_EPA_INDICATORS: dict[str, str] = {
    "PM25": "PM2.5 (fine particulate matter)",
    "OZONE": "ozone",
    "DSLPM": "diesel particulate matter",
    "CANCR": "air toxics cancer risk",
    "RESP": "air toxics respiratory hazard index",
    "PTRAF": "traffic proximity",
    "PWDIS": "wastewater discharge",
    "PNPL": "Superfund proximity",
    "PRMP": "RMP facility proximity",
    "PTSDF": "hazardous waste proximity",
    "UST": "underground storage tanks",
    "LDPNT": "lead paint indicator",
    "SOCVULN": "social vulnerability",
    "LINGISO": "linguistic isolation",
    "LOWINCPCT": "low income percentage",
    "LESSHSPCT": "less than high school education",
    "UNDER5PCT": "percent under age 5",
    "OVER64PCT": "percent over age 64",
    "DEMOGIDX": "demographic index",
    "DISPROPMINORITY": "disproportionate minority",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_value(value: float, metric: str) -> str:
    """Format a numeric value based on metric type.

    Returns "$X,XXX" for dollar metrics, "X.X%" for rate metrics,
    otherwise a plain string representation.
    """
    if metric in _DOLLAR_METRICS:
        return f"${int(value):,}"
    if metric in _RATE_METRICS:
        return f"{value:.1f}%"
    return str(value)


def _capitalize_race(race: str) -> str:
    """Return a human-readable race label.

    Empty string → "total population"; otherwise title-case with underscores
    replaced by spaces.
    """
    if not race:
        return "total population"
    return race.replace("_", " ").title()


# ---------------------------------------------------------------------------
# Render functions
# ---------------------------------------------------------------------------


def render_census_passage(row: dict) -> str:
    """Render an ACS census indicator row as a natural-language passage.

    Expected keys: geography_name, fips_code, race, metric, value,
                   margin_of_error (optional), year.
    """
    geo = row["geography_name"]
    fips = row["fips_code"]
    race = _capitalize_race(row.get("race", ""))
    metric = row["metric"]
    value = row["value"]
    moe = row.get("margin_of_error")
    year = row.get("year", "")

    formatted_value = _format_value(value, metric)
    metric_label = metric.replace("_", " ")

    passage = (
        f"In {year}, {geo} (FIPS: {fips}) reported a {metric_label} of "
        f"{formatted_value} for the {race}."
    )

    if moe is not None:
        formatted_moe = _format_value(moe, metric)
        passage += f" The margin of error was {formatted_moe}."

    return passage


def render_cdc_passage(row: dict) -> str:
    """Render a CDC PLACES health outcome row as a natural-language passage.

    Expected keys: geography_name, fips_code, measure, category,
                   data_value, data_value_type, low_confidence_limit,
                   high_confidence_limit, total_population, year.
    """
    geo = row["geography_name"]
    measure = row["measure"].replace("_", " ").lower()
    value = row["data_value"]
    ci_low = row.get("low_confidence_limit")
    ci_high = row.get("high_confidence_limit")
    year = row.get("year", "")

    passage = (
        f"In {year}, {geo} had a {row.get('data_value_type', 'crude prevalence')} "
        f"of {value:.1f}% for {measure}"
    )
    if ci_low is not None and ci_high is not None:
        passage += f" (95% confidence interval: {ci_low:.1f}%–{ci_high:.1f}%)"
    passage += "."
    return passage


def render_epa_passage(row: dict) -> str:
    """Render an EPA EJScreen indicator row as a natural-language passage.

    Expected keys: state_name, tract_fips, indicator, raw_value,
                   percentile_state, percentile_national, population,
                   minority_pct, low_income_pct, year.
    """
    state_name = row["state_name"]
    indicator_code = row["indicator"]
    display_name = _EPA_INDICATORS.get(indicator_code, indicator_code)
    raw_value = row["raw_value"]
    pct_national = row["percentile_national"]
    pct_state = row["percentile_state"]
    minority_pct = row["minority_pct"]
    year = row.get("year", "")

    passage = (
        f"In {year}, a census tract in {state_name} recorded a {display_name} "
        f"value of {raw_value} (national percentile: {int(pct_national)}, "
        f"state percentile: {int(pct_state)}). "
        f"The tract had a minority population of {minority_pct:.1f}%."
    )
    return passage


def render_police_violence_passage(row: dict) -> str:
    """Render a police violence incident row as a natural-language passage.

    Expected keys: state (2-letter abbrev), city, race, age, gender,
                   armed_status, cause_of_death, year, agency.
    """
    city = row.get("city") or "Unknown"
    state_abbrev = row.get("state") or ""
    state_name = STATE_ABBREV_TO_NAME.get(state_abbrev, state_abbrev)
    race = row.get("race") or "Unknown"
    armed_status = row.get("armed_status") or "unknown"
    year = row.get("year", "")

    passage = (
        f"In {year}, a fatal police encounter occurred in {city}, {state_name}. "
        f"The victim was identified as {race} and was {armed_status}."
    )
    return passage


def render_bjs_passage(row: dict) -> str:
    """Render a BJS incarceration row as a natural-language passage.

    Expected keys: state_name, state_abbrev, facility_type, metric,
                   race, gender, value, year.
    """
    state_name = row["state_name"]
    race = row["race"]
    value = int(row["value"])
    facility_type = row["facility_type"]
    year = row.get("year", "")

    passage = (
        f"In {year}, {state_name} held {value:,} incarcerated individuals "
        f"identified as {race} in {facility_type} facilities."
    )
    return passage


def render_fbi_passage(row: dict) -> str:
    """Render an FBI crime statistics row as a natural-language passage.

    Expected keys: state_name, offense, category, race, value, population, year.
    """
    state_name = row["state_name"]
    offense = row["offense"]
    category = row["category"]
    race = row["race"]
    count = int(row["value"])
    population = int(row["population"]) if row.get("population") else 0
    year = row.get("year", "")

    rate_per_100k = (count / population * 100_000) if population else 0.0

    passage = (
        f"In {year}, {state_name} reported {count:,} arrests for {offense} "
        f"(category: {category}) among individuals identified as {race}. "
        f"This represents a rate of {rate_per_100k:.1f} per 100,000 people."
    )
    return passage
