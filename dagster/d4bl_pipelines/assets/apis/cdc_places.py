"""CDC PLACES health outcomes ingestion assets.

Fetches health outcome and prevention measures by county and census tract
from the CDC PLACES SODA API. No authentication required.
"""

import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import aiohttp

from d4bl_pipelines.utils import flush_langfuse
from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

# SODA API endpoint for CDC PLACES county-level data
CDC_PLACES_URL = "https://data.cdc.gov/resource/swc5-untb.json"

# SODA API endpoint for CDC PLACES census-tract-level data
CDC_PLACES_TRACT_URL = "https://data.cdc.gov/resource/cwsq-ngmh.json"

# Health equity measures to fetch
CDC_MEASURES = [
    "DIABETES",
    "BPHIGH",       # High blood pressure
    "CASTHMA",      # Current asthma
    "CHD",          # Coronary heart disease
    "MHLTH",        # Mental health not good
    "OBESITY",      # Obesity
    "CSMOKING",     # Current smoking
    "ACCESS2",      # No health insurance (18-64)
    "CHECKUP",      # Annual checkup
    "DEPRESSION",   # Depression
]

# Human-readable measure names
MEASURE_NAMES = {
    "DIABETES": "diabetes",
    "BPHIGH": "high_blood_pressure",
    "CASTHMA": "current_asthma",
    "CHD": "coronary_heart_disease",
    "MHLTH": "poor_mental_health",
    "OBESITY": "obesity",
    "CSMOKING": "current_smoking",
    "ACCESS2": "lack_health_insurance",
    "CHECKUP": "annual_checkup",
    "DEPRESSION": "depression",
}

MEASURE_CATEGORIES = {
    "DIABETES": "health_outcomes",
    "BPHIGH": "health_outcomes",
    "CASTHMA": "health_outcomes",
    "CHD": "health_outcomes",
    "MHLTH": "health_outcomes",
    "OBESITY": "health_risk_behaviors",
    "CSMOKING": "health_risk_behaviors",
    "ACCESS2": "health_status",
    "CHECKUP": "prevention",
    "DEPRESSION": "health_outcomes",
}


async def _fetch_places_measures(
    http_session: aiohttp.ClientSession,
    url: str,
    year: int,
    measures: list[str],
    fips_field: str,
    select_fields: str,
    context: AssetExecutionContext,
) -> AsyncIterator[list[dict[str, Any]]]:
    """Fetch paginated CDC PLACES data from a SODA endpoint.

    Yields pages of rows so callers can process incrementally
    without buffering the entire dataset in memory.

    Parameters
    ----------
    http_session:  aiohttp session for making requests.
    url:           SODA API endpoint URL.
    year:          Data year to filter on.
    measures:      List of CDC measure IDs to fetch.
    fips_field:    Name of the FIPS code field (``countyfips`` or ``locationid``).
    select_fields: Comma-separated $select clause for the SODA query.
    context:       Dagster execution context for logging.

    Yields
    ------
    list[dict]
        A page of row dicts from the SODA API.
    """
    for measure in measures:
        offset = 0
        limit = 5000
        while True:
            params = {
                "$where": f"year={year} AND measureid='{measure}'",
                "$limit": str(limit),
                "$offset": str(offset),
                "$select": select_fields,
            }
            timeout = aiohttp.ClientTimeout(total=120)
            async with http_session.get(
                url, params=params, timeout=timeout
            ) as resp:
                resp.raise_for_status()
                rows = await resp.json()

            if not rows:
                break

            context.log.info(
                f"  {measure}: fetched {len(rows)} rows "
                f"(offset={offset})"
            )
            yield rows
            if len(rows) < limit:
                break
            offset += limit


@asset(
    group_name="apis",
    description=(
        "Health outcomes and prevention measures by county from CDC PLACES. "
        "Includes diabetes, blood pressure, asthma, mental health, and more."
    ),
    metadata={
        "source": "CDC PLACES (SODA API)",
        "methodology": "D4BL equity-focused health data collection",
    },
    required_resource_keys={"db_url", "langfuse"},
)
async def cdc_places_health(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Fetch CDC PLACES data and upsert into cdc_health_outcomes table."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    db_url = context.resources.db_url
    year = int(os.environ.get("CDC_PLACES_YEAR", "2023"))

    # --- Langfuse tracing ---
    langfuse = context.resources.langfuse
    trace = None
    try:
        if langfuse:
            trace = langfuse.trace(
                name="dagster:cdc_places_health",
                metadata={"year": year},
            )
    except Exception as exc:
        context.log.warning(f"Langfuse trace init failed: {exc}")
        langfuse = None

    engine = create_async_engine(db_url, pool_size=3, max_overflow=5)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    records_ingested = 0
    states_seen: set[str] = set()
    measures_seen: set[str] = set()

    context.log.info(f"Fetching CDC PLACES data for year={year}")

    upsert_sql = text("""
        INSERT INTO cdc_health_outcomes
            (id, fips_code, geography_type,
             geography_name, state_fips, year,
             measure, category, data_value,
             data_value_type,
             low_confidence_limit,
             high_confidence_limit,
             total_population)
        VALUES
            (CAST(:id AS UUID), :fips, 'county',
             :geo_name, :state_fips, :year,
             :measure, :category, :value,
             :dvt, :low_cl, :high_cl, :pop)
        ON CONFLICT (fips_code, year, measure,
                     data_value_type)
        DO UPDATE SET
            data_value = :value,
            low_confidence_limit = :low_cl,
            high_confidence_limit = :high_cl,
            total_population = :pop,
            geography_name = :geo_name
    """)

    try:
        async with aiohttp.ClientSession() as http_session:
            pages = _fetch_places_measures(
                http_session=http_session,
                url=CDC_PLACES_URL,
                year=year,
                measures=CDC_MEASURES,
                fips_field="countyfips",
                select_fields=(
                    "year,stateabbr,statedesc,locationname,"
                    "countyname,countyfips,measureid,measure,"
                    "data_value,data_value_type,low_confidence_limit,"
                    "high_confidence_limit,totalpopulation,category"
                ),
                context=context,
            )

            # Batch upsert in groups of 2000
            batch: list[dict[str, Any]] = []
            async for page in pages:
                for row in page:
                    parsed = _parse_row(row, fips_field="countyfips")
                    if parsed is None:
                        continue

                    states_seen.add(row.get("stateabbr", ""))
                    measures_seen.add(row.get("measureid", ""))

                    batch.append(parsed)
                    records_ingested += 1

                    if len(batch) >= 2000:
                        async with async_session() as session:
                            await session.execute(upsert_sql, batch)
                            await session.commit()
                        context.log.info(
                            f"  Committed batch of {len(batch)} county records"
                        )
                        batch = []

            # Flush remaining records
            if batch:
                async with async_session() as session:
                    await session.execute(upsert_sql, batch)
                    await session.commit()
                context.log.info(
                    f"  Committed final batch of {len(batch)} county records"
                )
    finally:
        await engine.dispose()

    bias_flags = []
    if len(measures_seen) < len(CDC_MEASURES):
        missing = set(CDC_MEASURES) - measures_seen
        bias_flags.append(f"missing_measures: {sorted(missing)}")
    bias_flags.append(
        "limitation: county-level only, no race disaggregation in PLACES"
    )

    flush_langfuse(langfuse, trace, records_ingested)

    context.log.info(
        f"Ingested {records_ingested} CDC PLACES records "
        f"across {len(states_seen)} states"
    )

    return MaterializeResult(
        metadata={
            "records_ingested": records_ingested,
            "year": year,
            "states_covered": len(states_seen),
            "measures_covered": sorted(measures_seen),
            "source_url": CDC_PLACES_URL,
            "bias_flags": MetadataValue.json_serializable(bias_flags),
        }
    )


def _parse_row(row: dict, fips_field: str) -> dict[str, Any] | None:
    """Parse a CDC PLACES row into an upsert-ready dict.

    Returns ``None`` when the row should be skipped (missing FIPS or value).
    """
    fips = row.get(fips_field, "")
    data_val = row.get("data_value")
    if not fips or data_val is None:
        return None
    try:
        value = float(data_val)
    except (ValueError, TypeError):
        return None
    try:
        year = int(row.get("year", ""))
    except (ValueError, TypeError):
        return None

    measure = row.get("measureid", "")
    state_fips = fips[:2]
    dvt = row.get("data_value_type", "Crude prevalence")

    record_id = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"cdc:{fips}:{row.get('year', '')}:{measure}:{dvt}",
    )

    low_cl = None
    high_cl = None
    try:
        low_cl = float(row.get("low_confidence_limit", ""))
    except (ValueError, TypeError):
        pass
    try:
        high_cl = float(row.get("high_confidence_limit", ""))
    except (ValueError, TypeError):
        pass

    pop = None
    try:
        pop = int(row.get("totalpopulation", ""))
    except (ValueError, TypeError):
        pass

    return {
        "id": str(record_id),
        "fips": fips,
        "geo_name": row.get("locationname", row.get("countyname", "")),
        "state_fips": state_fips,
        "year": year,
        "measure": MEASURE_NAMES.get(measure, measure.lower()),
        "category": MEASURE_CATEGORIES.get(measure, "other"),
        "value": value,
        "dvt": dvt,
        "low_cl": low_cl,
        "high_cl": high_cl,
        "pop": pop,
    }


@asset(
    group_name="apis",
    description=(
        "Health outcomes and prevention measures by census tract from "
        "CDC PLACES. Includes diabetes, blood pressure, asthma, mental "
        "health, and more at tract-level granularity."
    ),
    metadata={
        "source": "CDC PLACES (SODA API — census tract)",
        "methodology": "D4BL equity-focused health data collection",
    },
    required_resource_keys={"db_url", "langfuse"},
)
async def cdc_places_tract_health(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Fetch CDC PLACES tract-level data and upsert into cdc_health_outcomes."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    db_url = context.resources.db_url
    year = int(os.environ.get("CDC_PLACES_YEAR", "2023"))

    # --- Langfuse tracing ---
    langfuse = context.resources.langfuse
    trace = None
    try:
        if langfuse:
            trace = langfuse.trace(
                name="dagster:cdc_places_tract_health",
                metadata={"year": year},
            )
    except Exception as exc:
        context.log.warning(f"Langfuse trace init failed: {exc}")
        langfuse = None

    engine = create_async_engine(db_url, pool_size=3, max_overflow=5)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    records_ingested = 0
    states_seen: set[str] = set()
    measures_seen: set[str] = set()

    select_fields = (
        "year,stateabbr,statedesc,locationname,"
        "locationid,measureid,measure,"
        "data_value,data_value_type,low_confidence_limit,"
        "high_confidence_limit,totalpopulation,category"
    )

    context.log.info(
        f"Fetching CDC PLACES tract-level data for year={year}"
    )

    upsert_sql = text("""
        INSERT INTO cdc_health_outcomes
            (id, fips_code, geography_type,
             geography_name, state_fips, year,
             measure, category, data_value,
             data_value_type,
             low_confidence_limit,
             high_confidence_limit,
             total_population)
        VALUES
            (CAST(:id AS UUID), :fips, 'tract',
             :geo_name, :state_fips, :year,
             :measure, :category, :value,
             :dvt, :low_cl, :high_cl, :pop)
        ON CONFLICT (fips_code, year, measure,
                     data_value_type)
        DO UPDATE SET
            data_value = :value,
            low_confidence_limit = :low_cl,
            high_confidence_limit = :high_cl,
            total_population = :pop,
            geography_name = :geo_name
    """)

    try:
        async with aiohttp.ClientSession() as http_session:
            pages = _fetch_places_measures(
                http_session=http_session,
                url=CDC_PLACES_TRACT_URL,
                year=year,
                measures=CDC_MEASURES,
                fips_field="locationid",
                select_fields=select_fields,
                context=context,
            )

            # Batch upsert in groups of 2000
            batch: list[dict[str, Any]] = []
            async for page in pages:
                for row in page:
                    parsed = _parse_row(row, fips_field="locationid")
                    if parsed is None:
                        continue

                    states_seen.add(row.get("stateabbr", ""))
                    measures_seen.add(row.get("measureid", ""))

                    batch.append(parsed)
                    records_ingested += 1

                    if len(batch) >= 2000:
                        async with async_session() as session:
                            await session.execute(upsert_sql, batch)
                            await session.commit()
                        context.log.info(
                            f"  Committed batch of {len(batch)} tract records"
                        )
                        batch = []

            # Flush remaining records
            if batch:
                async with async_session() as session:
                    await session.execute(upsert_sql, batch)
                    await session.commit()
                context.log.info(
                    f"  Committed final batch of {len(batch)} tract records"
                )
    finally:
        await engine.dispose()

    bias_flags = []
    if len(measures_seen) < len(CDC_MEASURES):
        missing = set(CDC_MEASURES) - measures_seen
        bias_flags.append(f"missing_measures: {sorted(missing)}")
    bias_flags.append(
        "limitation: tract-level, no race disaggregation in PLACES"
    )

    flush_langfuse(langfuse, trace, records_ingested)

    context.log.info(
        f"Ingested {records_ingested} CDC PLACES tract records "
        f"across {len(states_seen)} states"
    )

    return MaterializeResult(
        metadata={
            "records_ingested": records_ingested,
            "year": year,
            "states_covered": len(states_seen),
            "measures_covered": sorted(measures_seen),
            "source_url": CDC_PLACES_TRACT_URL,
            "bias_flags": MetadataValue.json_serializable(bias_flags),
        }
    )
