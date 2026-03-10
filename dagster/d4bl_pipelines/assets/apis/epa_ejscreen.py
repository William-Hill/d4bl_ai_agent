"""EPA EJScreen environmental justice ingestion asset.

Fetches environmental justice screening data by state from the
EPA EJScreen API. No authentication required.

Note: EJScreen data is fetched at state summary level.
Tract-level data can be added as follow-up work.
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

# EPA EJScreen ArcGIS REST endpoint for state-level summaries
EPA_EJSCREEN_URL = (
    "https://ejscreen.epa.gov/mapper/ejscreenRESTbroker.aspx"
)

# Key EJ indicators to track
EJ_INDICATORS = [
    "PM25",                  # Particulate Matter 2.5
    "OZONE",                 # Ozone
    "DSLPM",                 # Diesel particulate matter
    "CANCER",                # Air toxics cancer risk
    "RESP",                  # Air toxics respiratory HI
    "PTRAF",                 # Traffic proximity
    "PNPL",                  # Superfund proximity
    "PRMP",                  # RMP facility proximity
    "PTSDF",                 # Hazardous waste proximity
    "PWDIS",                 # Wastewater discharge
    "PRE1960PCT",            # Pre-1960 housing (lead paint)
    "UNDER5PCT",             # Under age 5
    "OVER64PCT",             # Over age 64
    "MINORPCT",              # People of color
    "LOWINCPCT",             # Low income
    "LINGISOPCT",            # Linguistic isolation
    "LESSHSPCT",             # Less than high school education
    "UNEMPPCT",              # Unemployment rate
]

# State FIPS codes for iteration
STATE_FIPS = {
    "01": "Alabama", "02": "Alaska", "04": "Arizona",
    "05": "Arkansas", "06": "California", "08": "Colorado",
    "09": "Connecticut", "10": "Delaware",
    "11": "District of Columbia", "12": "Florida",
    "13": "Georgia", "15": "Hawaii", "16": "Idaho",
    "17": "Illinois", "18": "Indiana", "19": "Iowa",
    "20": "Kansas", "21": "Kentucky", "22": "Louisiana",
    "23": "Maine", "24": "Maryland", "25": "Massachusetts",
    "26": "Michigan", "27": "Minnesota", "28": "Mississippi",
    "29": "Missouri", "30": "Montana", "31": "Nebraska",
    "32": "Nevada", "33": "New Hampshire", "34": "New Jersey",
    "35": "New Mexico", "36": "New York",
    "37": "North Carolina", "38": "North Dakota",
    "39": "Ohio", "40": "Oklahoma", "41": "Oregon",
    "42": "Pennsylvania", "44": "Rhode Island",
    "45": "South Carolina", "46": "South Dakota",
    "47": "Tennessee", "48": "Texas", "49": "Utah",
    "50": "Vermont", "51": "Virginia", "53": "Washington",
    "54": "West Virginia", "55": "Wisconsin", "56": "Wyoming",
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
        "Environmental justice screening indicators by state from EPA EJScreen. "
        "Includes pollution, proximity, and demographic indicators."
    ),
    metadata={
        "source": "EPA EJScreen",
        "methodology": "D4BL environmental justice data collection",
    },
    required_resource_keys={"db_url", "langfuse"},
)
async def epa_ejscreen(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Fetch EPA EJScreen state-level data and upsert into epa_environmental_justice."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    db_url = context.resources.db_url
    year = int(os.environ.get("EPA_EJSCREEN_YEAR", "2024"))

    langfuse = context.resources.langfuse
    trace = None
    try:
        if langfuse:
            trace = langfuse.trace(
                name="dagster:epa_ejscreen",
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
    states_covered = set()

    context.log.info(f"Fetching EPA EJScreen data for year={year}")

    try:
        async with aiohttp.ClientSession() as http_session:
            for fips, state_name in STATE_FIPS.items():
                params = {
                    "namestr": "",
                    "geometry": "",
                    "distance": "",
                    "unit": "9035",
                    "aession": "",
                    "f": "json",
                    "areaid": fips,
                    "areatype": "state",
                }
                timeout = aiohttp.ClientTimeout(total=60)
                try:
                    async with http_session.get(
                        EPA_EJSCREEN_URL, params=params, timeout=timeout
                    ) as resp:
                        if resp.status != 200:
                            context.log.warning(
                                f"EPA EJScreen returned {resp.status} "
                                f"for state {fips} ({state_name})"
                            )
                            continue
                        data = await resp.json(content_type=None)
                except Exception as fetch_exc:
                    context.log.warning(
                        f"Failed to fetch EJScreen for {fips}: {fetch_exc}"
                    )
                    continue

                # Parse the response - EJScreen returns nested data
                raw_data = data if isinstance(data, dict) else {}

                async with async_session() as session:
                    for indicator in EJ_INDICATORS:
                        indicator_lower = indicator.lower()
                        # Try multiple key patterns
                        raw_val = (
                            raw_data.get(indicator)
                            or raw_data.get(indicator_lower)
                            or raw_data.get(f"RAW_{indicator}")
                        )
                        pctile = (
                            raw_data.get(f"P_{indicator}")
                            or raw_data.get(f"PCTILE_{indicator}")
                        )

                        # Skip if no data at all
                        if raw_val is None and pctile is None:
                            continue

                        try:
                            raw_float = float(raw_val) if raw_val is not None else None
                        except (ValueError, TypeError):
                            raw_float = None
                        try:
                            pctile_float = float(pctile) if pctile is not None else None
                        except (ValueError, TypeError):
                            pctile_float = None

                        if raw_float is None and pctile_float is None:
                            continue

                        states_covered.add(fips)

                        record_id = uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"epa:{fips}:{year}:{indicator}",
                        )

                        minority = raw_data.get("MINORPCT") or raw_data.get("minorpct")
                        lowinc = raw_data.get("LOWINCPCT") or raw_data.get("lowincpct")
                        pop = raw_data.get("ACSTOTPOP") or raw_data.get("acstotpop")

                        upsert_sql = text("""
                            INSERT INTO epa_environmental_justice
                                (id, tract_fips, state_fips, state_name,
                                 year, indicator, raw_value,
                                 percentile_state, percentile_national,
                                 population, minority_pct, low_income_pct)
                            VALUES
                                (CAST(:id AS UUID), :tract_fips,
                                 :state_fips, :state_name, :year,
                                 :indicator, :raw_value,
                                 :pctile_state, :pctile_national,
                                 :pop, :minority, :lowinc)
                            ON CONFLICT (tract_fips, year, indicator)
                            DO UPDATE SET
                                raw_value = :raw_value,
                                percentile_state = :pctile_state,
                                percentile_national = :pctile_national,
                                population = :pop,
                                minority_pct = :minority,
                                low_income_pct = :lowinc
                        """)
                        await session.execute(
                            upsert_sql,
                            {
                                "id": str(record_id),
                                "tract_fips": fips,
                                "state_fips": fips,
                                "state_name": state_name,
                                "year": year,
                                "indicator": indicator_lower,
                                "raw_value": raw_float,
                                "pctile_state": pctile_float,
                                "pctile_national": pctile_float,
                                "pop": int(pop) if pop else None,
                                "minority": float(minority) if minority else None,
                                "lowinc": float(lowinc) if lowinc else None,
                            },
                        )
                        records_ingested += 1

                    await session.commit()

                context.log.info(
                    f"  State {fips} ({state_name}): processed"
                )
    finally:
        await engine.dispose()

    bias_flags = [
        "limitation: state-level aggregates only, tract data in follow-up",
        "single_source: all data from EPA EJScreen",
    ]
    if len(states_covered) < len(STATE_FIPS):
        missing = set(STATE_FIPS.keys()) - states_covered
        bias_flags.append(
            f"missing_states: {len(missing)} states had no data"
        )

    _flush_langfuse(langfuse, trace, records_ingested)

    return MaterializeResult(
        metadata={
            "records_ingested": records_ingested,
            "year": year,
            "states_covered": len(states_covered),
            "indicators": sorted(EJ_INDICATORS),
            "source_url": EPA_EJSCREEN_URL,
            "bias_flags": MetadataValue.json_serializable(bias_flags),
        }
    )
