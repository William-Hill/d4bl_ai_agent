"""CDC mortality data ingestion assets.

Two assets write to a unified cdc_mortality table:
- cdc_mortality_state: state-level leading causes of death (SODA dataset bi63-dtpu)
- cdc_mortality_national_race: national race-disaggregated excess deaths (SODA dataset m74n-4hbs)
"""

import uuid

import aiohttp

from d4bl_pipelines.utils import flush_langfuse
from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

# --- SODA API endpoints ---
CDC_STATE_MORTALITY_URL = "https://data.cdc.gov/resource/bi63-dtpu.json"
CDC_EXCESS_DEATHS_URL = "https://data.cdc.gov/resource/m74n-4hbs.json"

# --- State name → FIPS mapping (used by bi63-dtpu which returns state names) ---
STATE_NAME_TO_FIPS = {
    "Alabama": "01", "Alaska": "02", "Arizona": "04", "Arkansas": "05",
    "California": "06", "Colorado": "08", "Connecticut": "09", "Delaware": "10",
    "District of Columbia": "11", "Florida": "12", "Georgia": "13", "Hawaii": "15",
    "Idaho": "16", "Illinois": "17", "Indiana": "18", "Iowa": "19",
    "Kansas": "20", "Kentucky": "21", "Louisiana": "22", "Maine": "23",
    "Maryland": "24", "Massachusetts": "25", "Michigan": "26", "Minnesota": "27",
    "Mississippi": "28", "Missouri": "29", "Montana": "30", "Nebraska": "31",
    "Nevada": "32", "New Hampshire": "33", "New Jersey": "34", "New Mexico": "35",
    "New York": "36", "North Carolina": "37", "North Dakota": "38", "Ohio": "39",
    "Oklahoma": "40", "Oregon": "41", "Pennsylvania": "42", "Rhode Island": "44",
    "South Carolina": "45", "South Dakota": "46", "Tennessee": "47", "Texas": "48",
    "Utah": "49", "Vermont": "50", "Virginia": "51", "Washington": "53",
    "West Virginia": "54", "Wisconsin": "55", "Wyoming": "56",
}

# --- Race mapping for m74n-4hbs excess deaths dataset ---
RACE_MAP = {
    "Non-Hispanic White": "white",
    "Non-Hispanic Black": "black",
    "Hispanic": "hispanic",
    "Non-Hispanic Asian": "asian",
    "Non-Hispanic American Indian or Alaska Native": "native_american",
    "Other": "multiracial",
    "All": "total",
}


@asset(
    group_name="apis",
    description=(
        "State-level leading causes of death from NCHS (1999-2017). "
        "10 leading causes by state and year. No race disaggregation."
    ),
    metadata={
        "source": "NCHS Leading Causes of Death (SODA bi63-dtpu)",
        "methodology": "D4BL equity-focused mortality data collection",
    },
    required_resource_keys={"db_url", "langfuse"},
)
async def cdc_mortality_state(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Fetch state-level leading causes of death and upsert into cdc_mortality."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    db_url = context.resources.db_url

    # --- Langfuse tracing ---
    langfuse = context.resources.langfuse
    trace = None
    try:
        if langfuse:
            trace = langfuse.trace(
                name="dagster:cdc_mortality_state",
                metadata={"source": "bi63-dtpu"},
            )
    except Exception as exc:
        context.log.warning(f"Langfuse trace init failed: {exc}")
        langfuse = None

    engine = create_async_engine(db_url, pool_size=3, max_overflow=5)
    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    records_ingested = 0
    states_seen = set()
    causes_seen = set()
    years_seen = set()

    upsert_sql = text("""
        INSERT INTO cdc_mortality
            (id, geo_id, geography_type, state_fips, state_name,
             year, cause_of_death, race, deaths, age_adjusted_rate)
        VALUES
            (CAST(:id AS UUID), :geo_id, 'state', :state_fips, :state_name,
             :year, :cause_of_death, 'total', :deaths, :age_adjusted_rate)
        ON CONFLICT (geo_id, year, cause_of_death, race)
        DO UPDATE SET
            deaths = :deaths,
            age_adjusted_rate = :age_adjusted_rate,
            state_name = :state_name
    """)

    context.log.info("Fetching state-level mortality data from NCHS SODA API")

    try:
        async with aiohttp.ClientSession() as http_session:
            offset = 0
            limit = 50000
            while True:
                params = {
                    "$limit": str(limit),
                    "$offset": str(offset),
                    "$order": "year,state",
                }
                timeout = aiohttp.ClientTimeout(total=120)
                async with http_session.get(
                    CDC_STATE_MORTALITY_URL, params=params, timeout=timeout
                ) as resp:
                    resp.raise_for_status()
                    rows = await resp.json()

                if not rows:
                    break

                async with async_session() as session:
                    for row in rows:
                        state_name = row.get("state")
                        cause = row.get("cause_name")
                        year_str = row.get("year")

                        if not state_name or not cause or not year_str:
                            continue
                        # Skip the "All causes" aggregation row
                        if cause == "All causes":
                            continue
                        # Skip the "United States" national-level row
                        if state_name == "United States":
                            continue

                        state_fips = STATE_NAME_TO_FIPS.get(state_name)
                        if not state_fips:
                            continue

                        try:
                            year = int(year_str)
                        except (ValueError, TypeError):
                            continue

                        deaths = None
                        try:
                            deaths = int(row.get("deaths", ""))
                        except (ValueError, TypeError):
                            pass

                        aadr = None
                        try:
                            aadr = float(row.get("aadr", ""))
                        except (ValueError, TypeError):
                            pass

                        record_id = uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"cdc-mortality:{state_fips}:{year}:{cause}:total",
                        )

                        await session.execute(upsert_sql, {
                            "id": str(record_id),
                            "geo_id": state_fips,
                            "state_fips": state_fips,
                            "state_name": state_name,
                            "year": year,
                            "cause_of_death": cause,
                            "deaths": deaths,
                            "age_adjusted_rate": aadr,
                        })
                        records_ingested += 1
                        states_seen.add(state_fips)
                        causes_seen.add(cause)
                        years_seen.add(year)

                    await session.commit()

                context.log.info(
                    f"Fetched {len(rows)} rows (offset={offset})"
                )
                if len(rows) < limit:
                    break
                offset += limit
    finally:
        await engine.dispose()

    bias_flags = [
        "race disaggregation not available from this source",
        "data ends 2017; source has not been updated since",
    ]
    if len(states_seen) < 51:
        bias_flags.append(
            f"missing {51 - len(states_seen)} states/territories"
        )

    flush_langfuse(langfuse, trace, records_ingested)

    context.log.info(
        f"Ingested {records_ingested} state mortality records "
        f"across {len(states_seen)} states, {len(years_seen)} years"
    )

    return MaterializeResult(
        metadata={
            "records_ingested": records_ingested,
            "states_covered": len(states_seen),
            "causes_covered": sorted(causes_seen),
            "year_range": f"{min(years_seen)}-{max(years_seen)}" if years_seen else "none",
            "source_url": CDC_STATE_MORTALITY_URL,
            "bias_flags": MetadataValue.json_serializable(bias_flags),
        }
    )


@asset(
    group_name="apis",
    description=(
        "National race-disaggregated excess death counts from NCHS (2015-2023). "
        "Weekly data aggregated to annual totals by race/ethnicity."
    ),
    metadata={
        "source": "NCHS AH Excess Deaths by Race (SODA m74n-4hbs)",
        "methodology": "D4BL equity-focused mortality data collection",
    },
    required_resource_keys={"db_url", "langfuse"},
)
async def cdc_mortality_national_race(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Fetch national excess deaths by race and upsert into cdc_mortality."""
    from collections import defaultdict

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    db_url = context.resources.db_url

    # --- Langfuse tracing ---
    langfuse = context.resources.langfuse
    trace = None
    try:
        if langfuse:
            trace = langfuse.trace(
                name="dagster:cdc_mortality_national_race",
                metadata={"source": "m74n-4hbs"},
            )
    except Exception as exc:
        context.log.warning(f"Langfuse trace init failed: {exc}")
        langfuse = None

    engine = create_async_engine(db_url, pool_size=3, max_overflow=5)
    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Accumulate weekly deaths by (year, race) for annual aggregation
    annual_deaths: dict[tuple[int, str], float] = defaultdict(float)
    rows_fetched = 0

    context.log.info("Fetching national excess deaths by race from NCHS SODA API")

    try:
        async with aiohttp.ClientSession() as http_session:
            offset = 0
            limit = 50000
            while True:
                params = {
                    "$limit": str(limit),
                    "$offset": str(offset),
                    "$where": "sex='All Sexes'",
                    "$select": "mmwryear,raceethnicity,deaths_unweighted",
                    "$order": "mmwryear,raceethnicity",
                }
                timeout = aiohttp.ClientTimeout(total=120)
                async with http_session.get(
                    CDC_EXCESS_DEATHS_URL, params=params, timeout=timeout
                ) as resp:
                    resp.raise_for_status()
                    rows = await resp.json()

                if not rows:
                    break

                for row in rows:
                    race_raw = row.get("raceethnicity", "")
                    year_str = row.get("mmwryear", "")
                    deaths_str = row.get("deaths_unweighted", "")

                    race = RACE_MAP.get(race_raw)
                    if not race:
                        continue

                    try:
                        year = int(year_str)
                        deaths = float(deaths_str)
                    except (ValueError, TypeError):
                        continue

                    annual_deaths[(year, race)] += deaths
                    rows_fetched += 1

                context.log.info(
                    f"Fetched {len(rows)} rows (offset={offset})"
                )
                if len(rows) < limit:
                    break
                offset += limit

        # --- Upsert aggregated annual totals ---
        upsert_sql = text("""
            INSERT INTO cdc_mortality
                (id, geo_id, geography_type, state_fips, state_name,
                 year, cause_of_death, race, deaths, age_adjusted_rate)
            VALUES
                (CAST(:id AS UUID), 'US', 'national', NULL, NULL,
                 :year, 'all_causes', :race, :deaths, NULL)
            ON CONFLICT (geo_id, year, cause_of_death, race)
            DO UPDATE SET
                deaths = :deaths
        """)

        records_ingested = 0
        years_seen = set()
        races_seen = set()

        async with async_session() as session:
            for (year, race), total_deaths in sorted(annual_deaths.items()):
                record_id = uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"cdc-mortality:US:{year}:all_causes:{race}",
                )
                await session.execute(upsert_sql, {
                    "id": str(record_id),
                    "year": year,
                    "race": race,
                    "deaths": round(total_deaths),
                })
                records_ingested += 1
                years_seen.add(year)
                races_seen.add(race)

            await session.commit()
    finally:
        await engine.dispose()

    bias_flags = [
        "national-level only; no state/county breakdown by race",
        "counts under 10 suppressed by NCHS",
        "weekly data aggregated to annual totals; some precision lost",
    ]

    flush_langfuse(langfuse, trace, records_ingested)

    context.log.info(
        f"Ingested {records_ingested} national mortality records "
        f"({len(races_seen)} races, {len(years_seen)} years) "
        f"from {rows_fetched} weekly rows"
    )

    return MaterializeResult(
        metadata={
            "records_ingested": records_ingested,
            "weekly_rows_fetched": rows_fetched,
            "races_covered": sorted(races_seen),
            "year_range": f"{min(years_seen)}-{max(years_seen)}" if years_seen else "none",
            "source_url": CDC_EXCESS_DEATHS_URL,
            "bias_flags": MetadataValue.json_serializable(bias_flags),
        }
    )
