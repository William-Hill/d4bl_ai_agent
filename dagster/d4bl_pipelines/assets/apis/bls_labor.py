"""BLS Labor Statistics ingestion asset.

Fetches unemployment rates and median weekly earnings by race from the
Bureau of Labor Statistics (BLS) Public Data API via POST requests.
API key is optional but recommended (25 req/day without vs 500 with).
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

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

# Series ID -> metadata mapping
BLS_SERIES = {
    "LNS14000003": {"metric": "unemployment_rate", "race": "Black"},
    "LNS14000006": {"metric": "unemployment_rate", "race": "White"},
    "LNS14000009": {"metric": "unemployment_rate", "race": "Hispanic"},
    "LNS14000000": {"metric": "unemployment_rate", "race": "Total"},
    "LEU0252881500": {"metric": "median_weekly_earnings", "race": "Black"},
    "LEU0252883600": {"metric": "median_weekly_earnings", "race": "White"},
    "LEU0252884500": {"metric": "median_weekly_earnings", "race": "Hispanic"},
}




@asset(
    group_name="apis",
    description=(
        "Labor statistics by race from BLS including unemployment rates "
        "and median weekly earnings. National-level data only."
    ),
    metadata={
        "source": "Bureau of Labor Statistics (BLS) Public Data API",
        "methodology": "D4BL equity-focused labor data collection",
    },
    required_resource_keys={"db_url", "langfuse"},
)
async def bls_labor_stats(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Fetch BLS labor statistics and upsert into bls_labor_statistics."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    db_url = context.resources.db_url
    start_year = os.environ.get("BLS_START_YEAR", "2019")
    end_year = os.environ.get("BLS_END_YEAR", "2024")
    api_key = os.environ.get("BLS_API_KEY")

    if not api_key:
        context.log.warning(
            "BLS_API_KEY not set. Proceeding without authentication "
            "(lower rate limits: 25 requests/day vs 500)."
        )

    # --- Langfuse tracing ---
    langfuse = context.resources.langfuse
    trace = None
    try:
        if langfuse:
            trace = langfuse.trace(
                name="dagster:bls_labor_stats",
                metadata={
                    "start_year": start_year,
                    "end_year": end_year,
                },
            )
    except Exception as exc:
        context.log.warning(f"Langfuse trace init failed: {exc}")
        langfuse = None

    engine = create_async_engine(db_url, pool_size=3, max_overflow=5)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    records_ingested = 0
    series_seen = set()

    series_ids = list(BLS_SERIES.keys())

    context.log.info(
        f"Fetching BLS data for {len(series_ids)} series, "
        f"years {start_year}-{end_year}"
    )

    try:
        async with aiohttp.ClientSession() as http_session:
            # BLS limits 50 series per request; we have <50 so one batch
            for i in range(0, len(series_ids), 50):
                batch = series_ids[i : i + 50]

                payload = {
                    "seriesid": batch,
                    "startyear": start_year,
                    "endyear": end_year,
                }
                if api_key:
                    payload["registrationkey"] = api_key

                timeout = aiohttp.ClientTimeout(total=60)
                async with http_session.post(
                    BLS_API_URL,
                    json=payload,
                    timeout=timeout,
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()

                if data.get("status") != "REQUEST_SUCCEEDED":
                    msg = data.get("message", ["Unknown error"])
                    context.log.error(
                        f"BLS API request failed: {msg}"
                    )
                    continue

                results = data.get("Results", {})
                series_list = results.get("series", [])

                upsert_sql = text("""
                    INSERT INTO bls_labor_statistics
                        (id, series_id, state_fips, state_name,
                         metric, race, year, period, value,
                         footnotes)
                    VALUES
                        (CAST(:id AS UUID), :series_id,
                         :state_fips, :state_name,
                         :metric, :race,
                         :year, :period, :value,
                         :footnotes)
                    ON CONFLICT (series_id, year, period)
                    DO UPDATE SET
                        value = EXCLUDED.value,
                        footnotes = EXCLUDED.footnotes,
                        metric = EXCLUDED.metric,
                        race = EXCLUDED.race
                """)

                async with async_session() as session:
                    for series in series_list:
                        sid = series.get("seriesID", "")
                        meta = BLS_SERIES.get(sid)
                        if not meta:
                            continue

                        series_seen.add(sid)

                        for obs in series.get("data", []):
                            year = obs.get("year", "")
                            period = obs.get("period", "")
                            raw_value = obs.get("value", "")

                            try:
                                value = float(raw_value)
                            except (ValueError, TypeError):
                                continue

                            footnote_list = obs.get("footnotes", [])
                            footnotes = ", ".join(
                                fn.get("text", "")
                                for fn in footnote_list
                                if fn.get("text")
                            ) or None

                            record_id = uuid.uuid5(
                                uuid.NAMESPACE_URL,
                                f"bls:{sid}:{year}:{period}",
                            )

                            await session.execute(
                                upsert_sql,
                                {
                                    "id": str(record_id),
                                    "series_id": sid,
                                    "state_fips": None,
                                    "state_name": None,
                                    "metric": meta["metric"],
                                    "race": meta["race"],
                                    "year": year,
                                    "period": period,
                                    "value": value,
                                    "footnotes": footnotes,
                                },
                            )
                            records_ingested += 1

                    await session.commit()

                context.log.info(
                    f"  Batch {i // 50 + 1}: processed "
                    f"{len(series_list)} series"
                )
    finally:
        await engine.dispose()

    bias_flags = [
        "national_level_only: race-disaggregated data is only "
        "available at the national level",
        "state_level_not_race_disaggregated: state-level BLS data "
        "does not break down by race",
    ]
    if len(series_seen) < len(BLS_SERIES):
        missing = set(BLS_SERIES.keys()) - series_seen
        bias_flags.append(f"missing_series: {sorted(missing)}")

    flush_langfuse(langfuse, trace, records_ingested)

    context.log.info(
        f"Ingested {records_ingested} BLS labor statistics records "
        f"across {len(series_seen)} series"
    )

    return MaterializeResult(
        metadata={
            "records_ingested": records_ingested,
            "start_year": start_year,
            "end_year": end_year,
            "series_covered": sorted(series_seen),
            "source_url": BLS_API_URL,
            "bias_flags": MetadataValue.json_serializable(bias_flags),
        }
    )
