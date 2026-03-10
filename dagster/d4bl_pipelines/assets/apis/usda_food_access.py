"""USDA Food Access Research Atlas ingestion asset.

Fetches food access indicators at the census-tract level from the
USDA Economic Research Service ArcGIS FeatureServer.  No authentication
required.
"""

import os
import uuid

import aiohttp

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

# ArcGIS FeatureServer endpoint for the Food Access Research Atlas
USDA_FOOD_ACCESS_URL = (
    "https://services1.arcgis.com/RLQu0rK7h4kbsBq5/arcgis/rest/services/"
    "Food_Access_Research_Atlas/FeatureServer/0/query"
)

# Indicator columns to pivot into rows
FOOD_ACCESS_INDICATORS = [
    "lapop1",
    "lapop10",
    "lapop20",
    "TractSNAP",
    "PovertyRate",
    "MedianFamilyIncome",
]

# Human-readable names for each indicator
INDICATOR_NAMES = {
    "lapop1": "low_access_pop_1mi",
    "lapop10": "low_access_pop_10mi",
    "lapop20": "low_access_pop_20mi",
    "TractSNAP": "snap_participants",
    "PovertyRate": "poverty_rate",
    "MedianFamilyIncome": "median_family_income",
}

# Fields to request from the ArcGIS service
OUT_FIELDS = ",".join([
    "CensusTract",
    "State",
    "County",
    "Urban",
    "Pop2010",
    "PovertyRate",
    "MedianFamilyIncome",
    "lapop1",
    "lapop10",
    "lapop20",
    "TractSNAP",
])


def _flush_langfuse(langfuse, trace, records_ingested=0,
                     extra_metadata=None):
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
        "Food access indicators at the census-tract level from the "
        "USDA Food Access Research Atlas.  Includes low-access population "
        "at 1, 10, and 20 mile thresholds, SNAP participation, poverty "
        "rate, and median family income."
    ),
    metadata={
        "source": "USDA ERS Food Access Research Atlas (ArcGIS)",
        "methodology": "D4BL equity-focused food access data collection",
    },
    required_resource_keys={"db_url", "langfuse"},
)
async def usda_food_access(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Fetch USDA Food Access data and upsert into usda_food_access."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    db_url = context.resources.db_url
    year = int(os.environ.get("USDA_FOOD_ACCESS_YEAR", "2019"))

    # --- Langfuse tracing ---
    langfuse = context.resources.langfuse
    trace = None
    try:
        if langfuse:
            trace = langfuse.trace(
                name="dagster:usda_food_access",
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
    tracts_seen = set()

    context.log.info(
        f"Fetching USDA Food Access Research Atlas data "
        f"(year={year})"
    )

    try:
        async with aiohttp.ClientSession() as http_session:
            offset = 0
            page_size = 2000
            while True:
                params = {
                    "where": "1=1",
                    "outFields": OUT_FIELDS,
                    "f": "json",
                    "resultRecordCount": str(page_size),
                    "resultOffset": str(offset),
                }
                timeout = aiohttp.ClientTimeout(total=120)
                async with http_session.get(
                    USDA_FOOD_ACCESS_URL,
                    params=params,
                    timeout=timeout,
                ) as resp:
                    resp.raise_for_status()
                    payload = await resp.json()

                features = payload.get("features", [])
                if not features:
                    break

                async with async_session() as session:
                    for feature in features:
                        attrs = feature.get("attributes", {})
                        tract_fips = str(
                            attrs.get("CensusTract", "")
                        ).strip()
                        if not tract_fips:
                            continue

                        state_name = attrs.get("State", "")
                        county_name = attrs.get("County", "")
                        urban = attrs.get("Urban", None)
                        population = None
                        try:
                            population = int(attrs.get("Pop2010", ""))
                        except (ValueError, TypeError):
                            pass

                        states_seen.add(state_name)
                        tracts_seen.add(tract_fips)

                        # Pivot each indicator into its own row
                        for indicator in FOOD_ACCESS_INDICATORS:
                            raw_val = attrs.get(indicator)
                            if raw_val is None:
                                continue
                            try:
                                value = float(raw_val)
                            except (ValueError, TypeError):
                                continue

                            record_id = uuid.uuid5(
                                uuid.NAMESPACE_URL,
                                f"usda_food:{tract_fips}:{year}"
                                f":{indicator}",
                            )

                            upsert_sql = text("""
                                INSERT INTO usda_food_access
                                    (id, tract_fips, state_name,
                                     county_name, urban_rural,
                                     population, year, indicator,
                                     indicator_name, value,
                                     bias_flags)
                                VALUES
                                    (CAST(:id AS UUID),
                                     :tract_fips, :state_name,
                                     :county_name, :urban_rural,
                                     :population, :year,
                                     :indicator, :indicator_name,
                                     :value, :bias_flags)
                                ON CONFLICT (tract_fips, year,
                                             indicator)
                                DO UPDATE SET
                                    value = :value,
                                    state_name = :state_name,
                                    county_name = :county_name,
                                    urban_rural = :urban_rural,
                                    population = :population,
                                    indicator_name = :indicator_name,
                                    bias_flags = :bias_flags
                            """)
                            await session.execute(
                                upsert_sql,
                                {
                                    "id": str(record_id),
                                    "tract_fips": tract_fips,
                                    "state_name": state_name,
                                    "county_name": county_name,
                                    "urban_rural": (
                                        "urban"
                                        if urban == 1
                                        else "rural"
                                        if urban == 0
                                        else None
                                    ),
                                    "population": population,
                                    "year": year,
                                    "indicator": indicator,
                                    "indicator_name": (
                                        INDICATOR_NAMES.get(
                                            indicator,
                                            indicator.lower(),
                                        )
                                    ),
                                    "value": value,
                                    "bias_flags": (
                                        "tract-level, not race-"
                                        "disaggregated; food desert "
                                        "definitions vary by "
                                        "distance threshold"
                                    ),
                                },
                            )
                            records_ingested += 1

                    await session.commit()

                context.log.info(
                    f"  Fetched {len(features)} features "
                    f"(offset={offset})"
                )
                if len(features) < page_size:
                    break
                offset += page_size
    finally:
        await engine.dispose()

    bias_flags = [
        "limitation: tract-level data, not race-disaggregated",
        "limitation: food desert definitions vary by distance "
        "threshold (1, 10, 20 miles)",
        f"atlas_year: {year} (based on 2010 Census tracts)",
    ]

    _flush_langfuse(langfuse, trace, records_ingested)

    context.log.info(
        f"Ingested {records_ingested} USDA Food Access records "
        f"across {len(states_seen)} states, "
        f"{len(tracts_seen)} tracts"
    )

    return MaterializeResult(
        metadata={
            "records_ingested": records_ingested,
            "year": year,
            "states_covered": len(states_seen),
            "tracts_covered": len(tracts_seen),
            "indicators": sorted(FOOD_ACCESS_INDICATORS),
            "source_url": USDA_FOOD_ACCESS_URL,
            "bias_flags": MetadataValue.json_serializable(
                bias_flags
            ),
        }
    )
