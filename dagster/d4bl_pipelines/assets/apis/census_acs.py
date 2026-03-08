"""Census ACS data ingestion asset.

Migrated from scripts/ingest_census_acs.py.
Fetches race-disaggregated indicators (homeownership, income, poverty)
from the Census Bureau API and upserts into census_indicators table.
"""

import hashlib
import os
import uuid
from datetime import datetime, timezone

import aiohttp
from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

CENSUS_BASE_URL = "https://api.census.gov/data"

# Metric -> race -> Census API variable codes
METRIC_VARIABLES = {
    "homeownership_rate": {
        "total": {"num": "B25003_002E", "den": "B25003_001E"},
        "black": {"num": "B25003B_002E", "den": "B25003B_001E"},
        "white": {"num": "B25003H_002E", "den": "B25003H_001E"},
        "hispanic": {"num": "B25003I_002E", "den": "B25003I_001E"},
    },
    "median_household_income": {
        "total": {"val": "B19013_001E"},
        "black": {"val": "B19013B_001E"},
        "white": {"val": "B19013H_001E"},
        "hispanic": {"val": "B19013I_001E"},
    },
    "poverty_rate": {
        "total": {"num": "B17001_002E", "den": "B17001_001E"},
        "black": {"num": "B17001B_002E", "den": "B17001B_001E"},
        "white": {"num": "B17001H_002E", "den": "B17001H_001E"},
        "hispanic": {"num": "B17001I_002E", "den": "B17001I_001E"},
    },
}

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


def _compute_rate(
    numerator: str, denominator: str
) -> float | None:
    """Compute a percentage rate from numerator/denominator strings."""
    try:
        num = float(numerator)
        den = float(denominator)
        if den <= 0:
            return None
        return round((num / den) * 100, 2)
    except (ValueError, TypeError):
        return None


async def _fetch_acs(
    session: aiohttp.ClientSession,
    year: int,
    variables: list[str],
    state_fips: str | None = None,
) -> list[list[str]]:
    """Fetch data from the Census ACS 5-Year API."""
    all_vars = ",".join(variables)
    url = f"{CENSUS_BASE_URL}/{year}/acs/acs5"
    params = {"get": f"NAME,{all_vars}", "for": "state:*"}
    if state_fips:
        params["for"] = f"state:{state_fips}"
    api_key = os.environ.get("CENSUS_API_KEY")
    if api_key:
        params["key"] = api_key

    async with session.get(url, params=params) as resp:
        resp.raise_for_status()
        return await resp.json()


@asset(
    group_name="apis",
    description=(
        "Race-disaggregated Census ACS indicators: "
        "homeownership, income, poverty rates by state."
    ),
    metadata={
        "source": "US Census Bureau ACS 5-Year Estimates",
        "methodology": "D4BL equity-focused data collection",
    },
)
async def census_acs_indicators(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Fetch Census ACS data and upsert into census_indicators table."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import (
        create_async_engine,
        AsyncSession,
    )
    from sqlalchemy.orm import sessionmaker

    year = int(os.environ.get("ACS_YEAR", "2022"))
    state_filter = os.environ.get("ACS_STATE_FIPS")
    db_url = context.resources.db_url

    engine = create_async_engine(
        db_url, pool_size=3, max_overflow=5
    )
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    records_ingested = 0
    states_covered = []
    races_covered = set()
    all_variables = set()
    for metric_vars in METRIC_VARIABLES.values():
        for race_vars in metric_vars.values():
            all_variables.update(race_vars.values())
    variables = sorted(all_variables)

    context.log.info(
        f"Fetching Census ACS data for "
        f"year={year}, state={state_filter or 'all'}"
    )

    async with aiohttp.ClientSession() as http_session:
        rows = await _fetch_acs(
            http_session, year, variables, state_filter
        )

    if not rows or len(rows) < 2:
        context.log.warning("No data returned from Census API")
        return MaterializeResult(
            metadata={
                "records_ingested": 0,
                "status": "no_data",
            }
        )

    headers = rows[0]
    data_rows = rows[1:]
    state_col = headers.index("state")

    async with async_session() as session:
        for row in data_rows:
            state_fips = row[state_col]
            state_name = STATE_FIPS.get(
                state_fips, f"Unknown ({state_fips})"
            )
            states_covered.append(state_fips)

            for metric, race_vars in METRIC_VARIABLES.items():
                for race, var_map in race_vars.items():
                    races_covered.add(race)
                    if "val" in var_map:
                        val_idx = headers.index(var_map["val"])
                        raw_val = row[val_idx]
                        try:
                            value = float(raw_val)
                        except (ValueError, TypeError):
                            continue
                    else:
                        num_idx = headers.index(var_map["num"])
                        den_idx = headers.index(var_map["den"])
                        value = _compute_rate(
                            row[num_idx], row[den_idx]
                        )
                        if value is None:
                            continue

                    record_id = uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"census:{state_fips}:{year}:{race}:{metric}",
                    )

                    upsert_sql = text("""
                        INSERT INTO census_indicators
                            (id, fips_code, geography_type,
                             geography_name, state_fips, year,
                             race, metric, value)
                        VALUES
                            (CAST(:id AS UUID), :fips, 'state',
                             :name, :state_fips, :year,
                             :race, :metric, :value)
                        ON CONFLICT (fips_code, year, race, metric)
                        DO UPDATE SET value = :value
                    """)
                    await session.execute(
                        upsert_sql,
                        {
                            "id": str(record_id),
                            "fips": state_fips,
                            "name": state_name,
                            "state_fips": state_fips,
                            "year": year,
                            "race": race,
                            "metric": metric,
                            "value": value,
                        },
                    )
                    records_ingested += 1

        await session.commit()

    # Compute coverage metadata
    all_fips = set(STATE_FIPS.keys())
    covered_fips = set(states_covered)
    missing_fips = all_fips - covered_fips
    all_races = {
        "total", "black", "white", "hispanic",
        "asian", "native_american", "multiracial",
    }
    missing_races = all_races - races_covered

    content_hash = hashlib.sha256(
        f"{year}:{sorted(states_covered)}:{records_ingested}"
        .encode()
    ).hexdigest()[:32]

    context.log.info(
        f"Ingested {records_ingested} records "
        f"for {len(covered_fips)} states"
    )

    return MaterializeResult(
        metadata={
            "records_ingested": records_ingested,
            "year": year,
            "states_covered": len(covered_fips),
            "states_missing": sorted(missing_fips),
            "races_covered": sorted(races_covered),
            "races_missing": sorted(missing_races),
            "content_hash": content_hash,
            "quality_score": MetadataValue.float(
                min(
                    5.0,
                    (len(covered_fips) / len(all_fips)) * 5,
                )
            ),
            "source_url": (
                f"{CENSUS_BASE_URL}/{year}/acs/acs5"
            ),
        }
    )
