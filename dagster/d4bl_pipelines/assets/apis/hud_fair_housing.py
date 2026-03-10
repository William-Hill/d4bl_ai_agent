"""HUD Fair Market Rent (FMR) ingestion asset.

Fetches Fair Market Rent data by state from the HUD User API.
FMR values serve as a housing affordability proxy for equity analysis.
No authentication required.
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

# HUD FMR API endpoint
HUD_FMR_URL = "https://www.huduser.gov/hudapi/public/fmr/statedata"

# Fair Market Rent indicators by bedroom count
HUD_INDICATORS = [
    "fmr_0br",
    "fmr_1br",
    "fmr_2br",
    "fmr_3br",
    "fmr_4br",
]

# Mapping from indicator name to the API response field
INDICATOR_FIELDS = {
    "fmr_0br": "Efficiency",
    "fmr_1br": "One-Bedroom",
    "fmr_2br": "Two-Bedroom",
    "fmr_3br": "Three-Bedroom",
    "fmr_4br": "Four-Bedroom",
}

# State FIPS codes (2-digit) to state abbreviation
STATE_FIPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
    "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
    "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
    "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
    "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
    "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
    "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
    "56": "WY",
}


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
        "Fair Market Rent data by state from HUD. "
        "Includes FMR for 0–4 bedroom units as a housing "
        "affordability proxy for equity analysis."
    ),
    metadata={
        "source": "HUD User API (FMR)",
        "methodology": "D4BL equity-focused housing data collection",
    },
    required_resource_keys={"db_url", "langfuse"},
)
async def hud_fair_housing(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Fetch HUD FMR data and upsert into hud_fair_housing table."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    db_url = context.resources.db_url
    year = int(os.environ.get("HUD_FMR_YEAR", "2024"))

    # --- Langfuse tracing ---
    langfuse = context.resources.langfuse
    trace = None
    try:
        if langfuse:
            trace = langfuse.trace(
                name="dagster:hud_fair_housing",
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
    indicators_seen = set()

    context.log.info(
        f"Fetching HUD FMR data for year={year} "
        f"across {len(STATE_FIPS)} states"
    )

    try:
        async with aiohttp.ClientSession() as http_session:
            for fips_code, state_abbr in STATE_FIPS.items():
                url = f"{HUD_FMR_URL}/{fips_code}"
                timeout = aiohttp.ClientTimeout(total=60)
                try:
                    async with http_session.get(
                        url, timeout=timeout
                    ) as resp:
                        resp.raise_for_status()
                        payload = await resp.json()
                except Exception as fetch_exc:
                    context.log.warning(
                        f"Failed to fetch FMR for {state_abbr} "
                        f"({fips_code}): {fetch_exc}"
                    )
                    continue

                # The API returns data under a "data" key with
                # basicdata or similar structure. Extract FMR values
                # from the top-level or nested response.
                data = payload.get("data", payload)
                if isinstance(data, dict):
                    fmr_data = data
                elif isinstance(data, list) and len(data) > 0:
                    fmr_data = data[0]
                else:
                    context.log.warning(
                        f"No FMR data for {state_abbr}"
                    )
                    continue

                states_seen.add(state_abbr)

                async with async_session() as session:
                    for indicator in HUD_INDICATORS:
                        field = INDICATOR_FIELDS.get(indicator)
                        value = fmr_data.get(field)
                        # Also try lowercase/snake variants
                        if value is None:
                            value = fmr_data.get(
                                indicator.replace("fmr_", "")
                                + "br"
                            )
                        if value is None:
                            value = fmr_data.get(indicator)
                        if value is None:
                            # Try numeric keys like
                            # fmr_0, fmr_1, etc.
                            br_num = indicator.replace(
                                "fmr_", ""
                            ).replace("br", "")
                            value = fmr_data.get(f"fmr_{br_num}")
                        if value is None:
                            continue

                        try:
                            value = float(value)
                        except (ValueError, TypeError):
                            continue

                        indicators_seen.add(indicator)

                        record_id = uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"hud_fmr:{fips_code}:{year}:"
                            f"{indicator}:all:all",
                        )

                        upsert_sql = text("""
                            INSERT INTO hud_fair_housing
                                (id, fips_code, state_abbr,
                                 year, indicator, value,
                                 race_group_a, race_group_b,
                                 bias_flag)
                            VALUES
                                (CAST(:id AS UUID), :fips_code,
                                 :state_abbr, :year, :indicator,
                                 :value, :race_group_a,
                                 :race_group_b, :bias_flag)
                            ON CONFLICT (fips_code, year, indicator,
                                         race_group_a, race_group_b)
                            DO UPDATE SET
                                value = :value,
                                state_abbr = :state_abbr,
                                bias_flag = :bias_flag
                        """)
                        await session.execute(
                            upsert_sql,
                            {
                                "id": str(record_id),
                                "fips_code": fips_code,
                                "state_abbr": state_abbr,
                                "year": year,
                                "indicator": indicator,
                                "value": value,
                                "race_group_a": "all",
                                "race_group_b": "all",
                                "bias_flag": (
                                    "HUD FMR does not disaggregate "
                                    "by race"
                                ),
                            },
                        )
                        records_ingested += 1

                    await session.commit()

                context.log.info(
                    f"  {state_abbr} ({fips_code}): upserted FMR "
                    f"records"
                )
    finally:
        await engine.dispose()

    bias_flags = [
        "limitation: HUD FMR does not directly disaggregate "
        "by race",
        "limitation: state-level aggregates may mask local "
        "variation",
    ]
    if len(indicators_seen) < len(HUD_INDICATORS):
        missing = set(HUD_INDICATORS) - indicators_seen
        bias_flags.append(
            f"missing_indicators: {sorted(missing)}"
        )

    _flush_langfuse(langfuse, trace, records_ingested)

    context.log.info(
        f"Ingested {records_ingested} HUD FMR records "
        f"across {len(states_seen)} states"
    )

    return MaterializeResult(
        metadata={
            "records_ingested": records_ingested,
            "year": year,
            "states_covered": len(states_seen),
            "indicators_covered": sorted(indicators_seen),
            "source_url": HUD_FMR_URL,
            "bias_flags": MetadataValue.json_serializable(
                bias_flags
            ),
        }
    )
