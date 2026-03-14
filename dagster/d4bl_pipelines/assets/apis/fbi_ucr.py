"""FBI Crime Data Explorer (UCR) ingestion asset.

Fetches arrest statistics by race and hate crime incidents
(disaggregated by bias motivation) from the FBI Crime Data Explorer API.
Requires an API key (FBI_API_KEY or DATA_GOV_API_KEY); skips gracefully
when absent.

BIAS NOTE: FBI UCR data is voluntarily reported by law-enforcement agencies.
Significant underreporting exists, especially from smaller or under-resourced
departments, which can skew racial and geographic breakdowns.
"""

import os
import uuid

import aiohttp

from d4bl_pipelines.utils import flush_langfuse
from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

# FBI Crime Data Explorer base URL
FBI_CDE_URL = "https://api.usa.gov/crime/fbi/cde"

# All 50 states + DC
STATE_ABBREVS = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}

FBI_OFFENSES = [
    "aggravated-assault",
    "burglary",
    "larceny",
    "motor-vehicle-theft",
    "homicide",
    "robbery",
    "arson",
    "violent-crime",
    "property-crime",
]

# Year range for hate crime queries (API requires from/to in MM-YYYY format)
HATE_CRIME_START_YEAR = 2015
HATE_CRIME_END_YEAR = 2024

# Category constants
CAT_ARREST = "arrest"
CAT_HATE_CRIME = "hate_crime"
CAT_HATE_CRIME_CATEGORY = "hate_crime_category"

# Bias sections to ingest: (API response key, offense value, category value)
BIAS_SECTIONS = [
    ("bias", "hate-crime", CAT_HATE_CRIME),
    ("bias_category", "hate-crime-category", CAT_HATE_CRIME_CATEGORY),
]




@asset(
    group_name="apis",
    description=(
        "Crime statistics by race from FBI Crime Data Explorer (UCR). "
        "Includes arrests by race/offense and hate crime incidents by state. "
        "NOTE: FBI data is voluntarily reported; significant underreporting exists."
    ),
    metadata={
        "source": "FBI Crime Data Explorer (CDE)",
        "methodology": "D4BL equity-focused criminal justice data collection",
    },
    required_resource_keys={"db_url", "langfuse"},
)
async def fbi_ucr_crime(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Fetch FBI UCR crime data and upsert into fbi_crime_stats table."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    # --- Check for API key ---
    api_key = os.environ.get("FBI_API_KEY") or os.environ.get("DATA_GOV_API_KEY")
    if not api_key:
        context.log.warning(
            "FBI_API_KEY not set - skipping fbi_ucr_crime"
        )
        return MaterializeResult(
            metadata={
                "status": "skipped",
                "reason": "missing_api_key",
            }
        )

    db_url = context.resources.db_url

    # --- Langfuse tracing ---
    langfuse = context.resources.langfuse
    trace = None
    try:
        if langfuse:
            trace = langfuse.trace(
                name="dagster:fbi_ucr_crime",
                metadata={"offenses": FBI_OFFENSES},
            )
    except Exception as exc:
        context.log.warning(f"Langfuse trace init failed: {exc}")
        langfuse = None

    engine = create_async_engine(db_url, pool_size=3, max_overflow=5)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    records_ingested = 0
    states_seen = set()
    offenses_seen = set()
    hate_crime_records = 0

    context.log.info(
        f"Fetching FBI UCR data for {len(STATE_ABBREVS)} states, "
        f"{len(FBI_OFFENSES)} offenses"
    )

    try:
        async with aiohttp.ClientSession() as http_session:
            timeout = aiohttp.ClientTimeout(total=60)

            # --- Shared upsert SQL (includes both race and bias_motivation) ---
            upsert_sql = text("""
                INSERT INTO fbi_crime_stats
                    (id, state_abbrev, state_name,
                     offense, race, bias_motivation,
                     year, category, value)
                VALUES
                    (CAST(:id AS UUID),
                     :state_abbrev, :state_name,
                     :offense, :race, :bias_motivation,
                     :year, :category, :value)
                ON CONFLICT
                    (state_abbrev, offense,
                     COALESCE(race, ''),
                     COALESCE(bias_motivation, ''),
                     year, category)
                DO UPDATE SET
                    value = :value,
                    state_name = :state_name
            """)

            consecutive_errors = 0
            for state_abbr in STATE_ABBREVS:
                if consecutive_errors >= 5:
                    context.log.warning(
                        "Skipping arrest data: API returned errors for "
                        "5 consecutive requests (endpoint may require "
                        "a different API key)"
                    )
                    break
                for offense in FBI_OFFENSES:
                    url = (
                        f"{FBI_CDE_URL}/arrest/states/offense"
                        f"/{state_abbr}/{offense}/race"
                    )
                    params = {"API_KEY": api_key}
                    try:
                        async with http_session.get(
                            url, params=params, timeout=timeout
                        ) as resp:
                            if resp.status in (403, 503):
                                consecutive_errors += 1
                                if consecutive_errors >= 5:
                                    break
                                continue
                            if resp.status == 404:
                                continue
                            resp.raise_for_status()
                            payload = await resp.json()
                            consecutive_errors = 0
                    except aiohttp.ClientResponseError as exc:
                        context.log.warning(
                            f"FBI API error {state_abbr}/{offense}: "
                            f"{exc.status}"
                        )
                        continue
                    except Exception as exc:
                        context.log.warning(
                            f"FBI API request failed "
                            f"{state_abbr}/{offense}: {exc}"
                        )
                        continue

                    # payload may be dict with "data" key or a list
                    rows = payload
                    if isinstance(payload, dict):
                        rows = payload.get("data", [])
                    if not rows:
                        continue

                    async with async_session() as session:
                        for row in rows:
                            race = row.get("race") or row.get("key")
                            if not race:
                                continue

                            year = row.get("data_year") or row.get("year")
                            value = row.get("value") or row.get("arrest_count", 0)
                            try:
                                value = int(value)
                            except (ValueError, TypeError):
                                value = 0

                            if year is None:
                                continue

                            states_seen.add(state_abbr)
                            offenses_seen.add(offense)

                            record_id = uuid.uuid5(
                                uuid.NAMESPACE_URL,
                                f"fbi:{state_abbr}:{offense}:"
                                f"{race}:{year}:{CAT_ARREST}",
                            )

                            await session.execute(
                                upsert_sql,
                                {
                                    "id": str(record_id),
                                    "state_abbrev": state_abbr,
                                    "state_name": STATE_ABBREVS[state_abbr],
                                    "offense": offense,
                                    "race": race,
                                    "bias_motivation": None,
                                    "year": int(year),
                                    "category": CAT_ARREST,
                                    "value": value,
                                },
                            )
                            records_ingested += 1

                        await session.commit()

                    context.log.info(
                        f"  {state_abbr}/{offense}: "
                        f"{len(rows)} race rows"
                    )

            # --- Hate crime data by state, per year, disaggregated by bias ---
            for state_abbr in STATE_ABBREVS:
                for year in range(HATE_CRIME_START_YEAR, HATE_CRIME_END_YEAR + 1):
                    url = (
                        f"{FBI_CDE_URL}/hate-crime/state/{state_abbr}"
                    )
                    params = {
                        "API_KEY": api_key,
                        "from": f"01-{year}",
                        "to": f"12-{year}",
                    }
                    try:
                        async with http_session.get(
                            url, params=params, timeout=timeout
                        ) as resp:
                            if resp.status == 404:
                                continue
                            resp.raise_for_status()
                            payload = await resp.json()
                    except aiohttp.ClientResponseError as exc:
                        context.log.warning(
                            f"FBI hate-crime API error "
                            f"{state_abbr}/{year}: {exc.status}"
                        )
                        continue
                    except Exception as exc:
                        context.log.warning(
                            f"FBI hate-crime request failed "
                            f"{state_abbr}/{year}: {exc}"
                        )
                        continue

                    if not isinstance(payload, dict):
                        continue

                    incident_section = payload.get("incident_section", {})
                    batch_rows: list[dict] = []

                    for api_key_name, offense, category in BIAS_SECTIONS:
                        for label, count in incident_section.get(api_key_name, {}).items():
                            try:
                                value = int(count)
                            except (ValueError, TypeError):
                                value = 0
                            if value == 0:
                                continue

                            record_id = uuid.uuid5(
                                uuid.NAMESPACE_URL,
                                f"fbi:{state_abbr}:{offense}:"
                                f"{label}:{year}:{category}",
                            )

                            batch_rows.append({
                                "id": str(record_id),
                                "state_abbrev": state_abbr,
                                "state_name": STATE_ABBREVS[state_abbr],
                                "offense": offense,
                                "race": None,
                                "bias_motivation": label,
                                "year": year,
                                "category": category,
                                "value": value,
                            })

                    if batch_rows:
                        states_seen.add(state_abbr)
                        async with async_session() as session:
                            for row_params in batch_rows:
                                await session.execute(
                                    upsert_sql, row_params
                                )
                            await session.commit()
                        hate_crime_records += len(batch_rows)

                        context.log.info(
                            f"  {state_abbr}/{year}: "
                            f"{len(batch_rows)} bias rows"
                        )

    finally:
        await engine.dispose()

    total = records_ingested + hate_crime_records

    bias_flags = [
        (
            "voluntary_reporting: FBI UCR data is voluntarily reported "
            "by law-enforcement agencies; significant underreporting "
            "exists, especially from smaller or under-resourced "
            "departments"
        ),
        (
            "coverage_gap: not all agencies report every year; "
            "racial breakdowns may be incomplete"
        ),
    ]
    if len(offenses_seen) < len(FBI_OFFENSES):
        missing = set(FBI_OFFENSES) - offenses_seen
        bias_flags.append(
            f"missing_offenses: {sorted(missing)}"
        )

    flush_langfuse(langfuse, trace, total)

    context.log.info(
        f"Ingested {total} FBI UCR records "
        f"({records_ingested} arrests, {hate_crime_records} hate crimes) "
        f"across {len(states_seen)} states"
    )

    return MaterializeResult(
        metadata={
            "records_ingested": total,
            "arrest_records": records_ingested,
            "hate_crime_records": hate_crime_records,
            "states_covered": len(states_seen),
            "offenses_covered": sorted(offenses_seen),
            "source_url": FBI_CDE_URL,
            "bias_flags": MetadataValue.json_serializable(
                bias_flags
            ),
        }
    )
