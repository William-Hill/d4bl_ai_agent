"""CDC PLACES health outcomes ingestion asset.

Fetches health outcome and prevention measures by county/state
from the CDC PLACES SODA API. No authentication required.
"""

import hashlib
import json
import os
import uuid

import aiohttp

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

# SODA API endpoint for CDC PLACES county-level data
CDC_PLACES_URL = "https://data.cdc.gov/resource/swc5-untb.json"

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


def _flush_langfuse(langfuse, trace, records_ingested=0, extra_metadata=None):
    """Best-effort Langfuse trace finalization."""
    try:
        if trace:
            metadata = {"records_ingested": records_ingested}
            if extra_metadata:
                metadata.update(extra_metadata)
            trace.update(metadata=metadata)
        if langfuse:
            langfuse.flush()
    except Exception:
        pass


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
    states_seen = set()
    measures_seen = set()

    context.log.info(f"Fetching CDC PLACES data for year={year}")

    try:
        async with aiohttp.ClientSession() as http_session:
            for measure in CDC_MEASURES:
                offset = 0
                limit = 5000
                while True:
                    params = {
                        "$where": f"year={year} AND measureid='{measure}'",
                        "$limit": str(limit),
                        "$offset": str(offset),
                        "$select": (
                            "year,stateabbr,statedesc,locationname,"
                            "countyname,countyfips,measureid,measure,"
                            "data_value,data_value_type,low_confidence_limit,"
                            "high_confidence_limit,totalpopulation,category"
                        ),
                    }
                    timeout = aiohttp.ClientTimeout(total=60)
                    async with http_session.get(
                        CDC_PLACES_URL, params=params, timeout=timeout
                    ) as resp:
                        resp.raise_for_status()
                        rows = await resp.json()

                    if not rows:
                        break

                    async with async_session() as session:
                        for row in rows:
                            fips = row.get("countyfips")
                            data_val = row.get("data_value")
                            if not fips or data_val is None:
                                continue
                            try:
                                value = float(data_val)
                            except (ValueError, TypeError):
                                continue

                            state_abbr = row.get("stateabbr", "")
                            states_seen.add(state_abbr)
                            measures_seen.add(measure)

                            record_id = uuid.uuid5(
                                uuid.NAMESPACE_URL,
                                f"cdc:{fips}:{year}:{measure}:"
                                f"{row.get('data_value_type', 'crude')}",
                            )

                            dvt = row.get(
                                "data_value_type", "Crude prevalence"
                            )

                            low_cl = None
                            high_cl = None
                            try:
                                low_cl = float(
                                    row.get("low_confidence_limit", "")
                                )
                            except (ValueError, TypeError):
                                pass
                            try:
                                high_cl = float(
                                    row.get("high_confidence_limit", "")
                                )
                            except (ValueError, TypeError):
                                pass

                            pop = None
                            try:
                                pop = int(
                                    row.get("totalpopulation", "")
                                )
                            except (ValueError, TypeError):
                                pass

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
                            await session.execute(
                                upsert_sql,
                                {
                                    "id": str(record_id),
                                    "fips": fips,
                                    "geo_name": row.get(
                                        "locationname",
                                        row.get("countyname", ""),
                                    ),
                                    "state_fips": state_abbr,
                                    "year": year,
                                    "measure": MEASURE_NAMES.get(
                                        measure, measure.lower()
                                    ),
                                    "category": MEASURE_CATEGORIES.get(
                                        measure, "other"
                                    ),
                                    "value": value,
                                    "dvt": dvt,
                                    "low_cl": low_cl,
                                    "high_cl": high_cl,
                                    "pop": pop,
                                },
                            )
                            records_ingested += 1

                        await session.commit()

                    context.log.info(
                        f"  {measure}: fetched {len(rows)} rows "
                        f"(offset={offset})"
                    )
                    if len(rows) < limit:
                        break
                    offset += limit
    finally:
        await engine.dispose()

    bias_flags = []
    if len(measures_seen) < len(CDC_MEASURES):
        missing = set(CDC_MEASURES) - measures_seen
        bias_flags.append(f"missing_measures: {sorted(missing)}")
    bias_flags.append(
        "limitation: county-level only, no race disaggregation in PLACES"
    )

    _flush_langfuse(langfuse, trace, records_ingested)

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
