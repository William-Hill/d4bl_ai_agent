"""FBI Crime Data Explorer (UCR) ingestion asset.

Fetches arrest statistics by race and hate crime incidents from the
FBI Crime Data Explorer API.  Requires an FBI_API_KEY environment variable;
the asset skips gracefully when the key is absent.

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
    api_key = os.environ.get("FBI_API_KEY")
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

            # --- Arrest data by race ---
            arrest_upsert_sql = text("""
                INSERT INTO fbi_crime_stats
                    (id, state_abbrev, state_name,
                     offense, race, year, category,
                     value)
                VALUES
                    (CAST(:id AS UUID),
                     :state_abbrev, :state_name,
                     :offense, :race, :year,
                     :category, :value)
                ON CONFLICT
                    (state_abbrev, offense, race,
                     year, category)
                DO UPDATE SET
                    value = :value,
                    state_name = :state_name
            """)

            for state_abbr in STATE_ABBREVS:
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
                            if resp.status == 404:
                                continue
                            resp.raise_for_status()
                            payload = await resp.json()
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
                            race = row.get("race") or row.get(
                                "key"
                            )
                            if not race:
                                continue

                            year = row.get("data_year") or row.get(
                                "year"
                            )
                            value = row.get("value") or row.get(
                                "arrest_count", 0
                            )
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
                                f"{race}:{year}:arrest",
                            )

                            await session.execute(
                                arrest_upsert_sql,
                                {
                                    "id": str(record_id),
                                    "state_abbrev": state_abbr,
                                    "state_name": STATE_ABBREVS[
                                        state_abbr
                                    ],
                                    "offense": offense,
                                    "race": race,
                                    "year": int(year),
                                    "category": "arrest",
                                    "value": value,
                                },
                            )
                            records_ingested += 1

                        await session.commit()

                    context.log.info(
                        f"  {state_abbr}/{offense}: "
                        f"{len(rows)} race rows"
                    )

            # --- Hate crime data by state ---
            hate_upsert_sql = text("""
                INSERT INTO fbi_crime_stats
                    (id, state_abbrev, state_name,
                     offense, race, year, category,
                     value)
                VALUES
                    (CAST(:id AS UUID),
                     :state_abbrev, :state_name,
                     :offense, :race, :year,
                     :category, :value)
                ON CONFLICT
                    (state_abbrev, offense, race,
                     year, category)
                DO UPDATE SET
                    value = :value,
                    state_name = :state_name
            """)

            for state_abbr in STATE_ABBREVS:
                url = (
                    f"{FBI_CDE_URL}/hate-crime/state/{state_abbr}"
                )
                params = {"API_KEY": api_key}
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
                        f"FBI hate-crime API error {state_abbr}: "
                        f"{exc.status}"
                    )
                    continue
                except Exception as exc:
                    context.log.warning(
                        f"FBI hate-crime request failed "
                        f"{state_abbr}: {exc}"
                    )
                    continue

                rows = payload
                if isinstance(payload, dict):
                    rows = payload.get("data", [])
                if not rows:
                    continue

                async with async_session() as session:
                    for row in rows:
                        year = row.get("data_year") or row.get(
                            "year"
                        )
                        value = row.get("incident_count") or row.get(
                            "value", 0
                        )
                        try:
                            value = int(value)
                        except (ValueError, TypeError):
                            value = 0

                        if year is None:
                            continue

                        bias_motivation = row.get(
                            "bias_motivation", "all"
                        )

                        record_id = uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"fbi:{state_abbr}:hate-crime:"
                            f"{bias_motivation}:{year}:hate_crime",
                        )

                        await session.execute(
                            hate_upsert_sql,
                            {
                                "id": str(record_id),
                                "state_abbrev": state_abbr,
                                "state_name": STATE_ABBREVS[
                                    state_abbr
                                ],
                                "offense": "hate-crime",
                                "race": bias_motivation,
                                "year": int(year),
                                "category": "hate_crime",
                                "value": value,
                            },
                        )
                        hate_crime_records += 1

                    await session.commit()

                context.log.info(
                    f"  {state_abbr}/hate-crime: "
                    f"{len(rows)} rows"
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
