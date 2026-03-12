"""CDC + ACS race-weighted health outcome overlay.

Joins CDC PLACES health outcomes with Census ACS population-by-race data
to produce race-weighted health estimates.  For each CDC record and each
tracked race, we compute:

    estimated_value = health_rate * (race_pop / total_pop)

The results are upserted into the ``cdc_acs_race_estimates`` table.
"""

import hashlib
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

RACES = ["black", "white", "hispanic"]

# Census B03002 (Hispanic or Latino Origin by Race) variable mapping
_ACS_POP_VARS = {
    "B03002_001E": "total",
    "B03002_003E": "white",
    "B03002_004E": "black",
    "B03002_012E": "hispanic",
}

_ACS_VAR_LIST = ",".join(sorted(_ACS_POP_VARS.keys()))

CENSUS_BASE_URL = "https://api.census.gov/data"

BIAS_FLAGS = [
    "computed estimate via proportional attribution, not direct measurement",
    "assumes uniform health rate across racial groups within geography",
]

BATCH_SIZE = 2000


# ---------------------------------------------------------------------------
# Pure computation
# ---------------------------------------------------------------------------

def compute_race_estimates(
    cdc_row: dict,
    acs_pops: dict[str, int | float],
) -> list[dict]:
    """Compute race-weighted health estimates for a single CDC record.

    Parameters
    ----------
    cdc_row : dict
        A CDC health outcome record with keys: fips_code, geography_type,
        geography_name, state_fips, year, measure, data_value,
        low_confidence_limit, high_confidence_limit.
    acs_pops : dict
        Population counts keyed by race label (``total``, ``black``,
        ``white``, ``hispanic``).

    Returns
    -------
    list[dict]
        One dict per race present in *acs_pops* (excluding ``total``).
    """
    total_pop = acs_pops.get("total", 0)
    if not total_pop or total_pop <= 0:
        return []

    health_rate = cdc_row["data_value"]
    results = []
    for race in RACES:
        race_pop = acs_pops.get(race)
        if race_pop is None:
            continue
        share = race_pop / total_pop
        estimated = health_rate * share

        low = cdc_row.get("low_confidence_limit")
        high = cdc_row.get("high_confidence_limit")

        results.append({
            "fips_code": cdc_row["fips_code"],
            "geography_type": cdc_row["geography_type"],
            "geography_name": cdc_row["geography_name"],
            "state_fips": cdc_row["state_fips"],
            "year": cdc_row["year"],
            "measure": cdc_row["measure"],
            "race": race,
            "health_rate": health_rate,
            "race_population_share": round(share, 6),
            "estimated_value": round(estimated, 6),
            "total_population": int(total_pop),
            "confidence_low": round(low * share, 6) if low is not None else None,
            "confidence_high": round(high * share, 6) if high is not None else None,
        })
    return results


# ---------------------------------------------------------------------------
# Census ACS population fetching
# ---------------------------------------------------------------------------

async def _fetch_acs_populations(
    http: aiohttp.ClientSession,
    year: int,
    geography: str,
    state_fips: str | None = None,
) -> dict[str, dict[str, int]]:
    """Fetch population-by-race from Census ACS B03002 table.

    Returns a dict keyed by FIPS code, each value a dict with race totals.
    """
    url = f"{CENSUS_BASE_URL}/{year}/acs/acs5"
    params: dict[str, str] = {
        "get": f"NAME,{_ACS_VAR_LIST}",
        "for": geography,
    }
    if state_fips:
        params["in"] = f"state:{state_fips}"
    api_key = os.environ.get("CENSUS_API_KEY")
    if api_key:
        params["key"] = api_key

    timeout = aiohttp.ClientTimeout(total=120)
    async with http.get(url, params=params, timeout=timeout) as resp:
        resp.raise_for_status()
        rows = await resp.json()

    if not rows or len(rows) < 2:
        return {}

    headers = rows[0]
    result: dict[str, dict[str, int]] = {}
    for row in rows[1:]:
        row_dict = dict(zip(headers, row))
        # Build FIPS code depending on geography
        if "tract" in row_dict:
            fips = row_dict["state"] + row_dict["county"] + row_dict["tract"]
        elif "county" in row_dict:
            fips = row_dict["state"] + row_dict["county"]
        else:
            fips = row_dict.get("state", "")

        pops: dict[str, int] = {}
        for var_code, race_label in _ACS_POP_VARS.items():
            try:
                pops[race_label] = int(float(row_dict.get(var_code, 0)))
            except (ValueError, TypeError):
                pops[race_label] = 0
        result[fips] = pops

    return result


# ---------------------------------------------------------------------------
# Dagster asset
# ---------------------------------------------------------------------------

@asset(
    group_name="apis",
    deps=["cdc_places_health", "census_acs_county_indicators"],
    description=(
        "Race-weighted CDC health estimates computed by overlaying "
        "ACS population-by-race on CDC PLACES health outcomes."
    ),
    metadata={
        "source": "CDC PLACES + Census ACS B03002",
        "methodology": "Proportional attribution overlay",
    },
    required_resource_keys={"db_url", "langfuse"},
)
async def cdc_acs_race_overlay(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Join CDC health outcomes with ACS race demographics and upsert estimates."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    year = int(os.environ.get("ACS_YEAR", "2022"))
    db_url = context.resources.db_url

    # --- Langfuse tracing (best-effort) ---
    langfuse = context.resources.langfuse
    trace = None
    try:
        if langfuse:
            trace = langfuse.trace(
                name="dagster:cdc_acs_race_overlay",
                metadata={"year": year},
            )
    except Exception as lf_exc:
        context.log.warning(f"Langfuse trace init failed: {lf_exc}")
        langfuse = None

    engine = create_async_engine(db_url, pool_size=3, max_overflow=5)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    records_upserted = 0
    geographies_processed = set()

    try:
        # ------------------------------------------------------------------
        # 1. Read CDC health outcomes from DB
        # ------------------------------------------------------------------
        cdc_rows: list[dict] = []
        async with async_session() as session:
            result = await session.execute(
                text(
                    "SELECT fips_code, geography_type, geography_name, "
                    "state_fips, year, measure, data_value, "
                    "low_confidence_limit, high_confidence_limit "
                    "FROM cdc_health_outcomes "
                    "WHERE year = :year"
                ),
                {"year": year},
            )
            for row in result.mappings():
                cdc_rows.append(dict(row))

        context.log.info(f"Loaded {len(cdc_rows)} CDC records for year={year}")
        if not cdc_rows:
            await engine.dispose()
            flush_langfuse(langfuse, trace, records_ingested=0)
            return MaterializeResult(
                metadata={"records_upserted": 0, "status": "no_cdc_data"}
            )

        # Partition CDC rows by geography type
        county_cdc = [r for r in cdc_rows if r["geography_type"] == "county"]
        tract_cdc = [r for r in cdc_rows if r["geography_type"] == "tract"]

        context.log.info(
            f"CDC records: {len(county_cdc)} county, {len(tract_cdc)} tract"
        )

        # ------------------------------------------------------------------
        # 2. Fetch ACS population data
        # ------------------------------------------------------------------
        try:
            fetch_span = trace.span(name="fetch_acs") if trace else None
        except Exception:
            fetch_span = None

        acs_pop: dict[str, dict[str, int]] = {}
        async with aiohttp.ClientSession() as http:
            # County: single call
            if county_cdc:
                context.log.info("Fetching county-level ACS populations")
                county_pops = await _fetch_acs_populations(
                    http, year, "county:*"
                )
                acs_pop.update(county_pops)
                context.log.info(
                    f"Fetched ACS data for {len(county_pops)} counties"
                )

            # Tract: per-state calls
            if tract_cdc:
                tract_states = {r["state_fips"] for r in tract_cdc}
                context.log.info(
                    f"Fetching tract-level ACS populations for "
                    f"{len(tract_states)} states"
                )
                for st_fips in sorted(tract_states):
                    try:
                        tract_pops = await _fetch_acs_populations(
                            http, year, "tract:*", state_fips=st_fips,
                        )
                        acs_pop.update(tract_pops)
                    except Exception as exc:
                        context.log.warning(
                            f"Failed to fetch ACS tracts for state "
                            f"{st_fips}: {exc}"
                        )

        try:
            if fetch_span:
                fetch_span.end(
                    metadata={"acs_geographies_fetched": len(acs_pop)}
                )
        except Exception:
            pass

        context.log.info(
            f"Total ACS population records: {len(acs_pop)}"
        )

        # ------------------------------------------------------------------
        # 3. Compute estimates and upsert
        # ------------------------------------------------------------------
        try:
            store_span = trace.span(name="store") if trace else None
        except Exception:
            store_span = None

        upsert_sql = text("""
            INSERT INTO cdc_acs_race_estimates
                (id, fips_code, geography_type, geography_name,
                 state_fips, year, measure, race,
                 health_rate, race_population_share, estimated_value,
                 total_population, confidence_low, confidence_high)
            VALUES
                (CAST(:id AS UUID), :fips_code, :geography_type,
                 :geography_name, :state_fips, :year, :measure, :race,
                 :health_rate, :race_population_share, :estimated_value,
                 :total_population, :confidence_low, :confidence_high)
            ON CONFLICT (fips_code, year, measure, race)
            DO UPDATE SET
                health_rate = :health_rate,
                race_population_share = :race_population_share,
                estimated_value = :estimated_value,
                total_population = :total_population,
                confidence_low = :confidence_low,
                confidence_high = :confidence_high,
                geography_name = :geography_name,
                geography_type = :geography_type
        """)

        batch: list[dict] = []
        async with async_session() as session:
            for cdc_row in cdc_rows:
                fips = cdc_row["fips_code"]
                pop_data = acs_pop.get(fips)
                if not pop_data:
                    continue

                estimates = compute_race_estimates(cdc_row, pop_data)
                for est in estimates:
                    record_id = uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"cdc_acs:{est['fips_code']}:{est['year']}:"
                        f"{est['measure']}:{est['race']}",
                    )
                    est["id"] = str(record_id)
                    batch.append(est)
                    geographies_processed.add(fips)

                    if len(batch) >= BATCH_SIZE:
                        for params in batch:
                            await session.execute(upsert_sql, params)
                        await session.commit()
                        records_upserted += len(batch)
                        context.log.info(
                            f"Upserted batch: {records_upserted} total"
                        )
                        batch = []

            # Flush remaining
            if batch:
                for params in batch:
                    await session.execute(upsert_sql, params)
                await session.commit()
                records_upserted += len(batch)

            # --- Lineage recording ---
            try:
                from d4bl_pipelines.quality.lineage import (
                    build_lineage_record,
                    write_lineage_batch,
                )

                ingestion_run_id = uuid.uuid4()
                lineage_records = []
                for fips in geographies_processed:
                    rec_id = uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"cdc_acs:lineage:{fips}:{year}",
                    )
                    lineage_records.append(
                        build_lineage_record(
                            ingestion_run_id=ingestion_run_id,
                            target_table="cdc_acs_race_estimates",
                            record_id=rec_id,
                            source_url=(
                                f"{CENSUS_BASE_URL}/{year}/acs/acs5"
                            ),
                            transformation={
                                "steps": [
                                    "query_cdc_health_outcomes",
                                    "fetch_acs_b03002",
                                    "compute_race_weighted_estimate",
                                    "upsert",
                                ],
                            },
                            bias_flags=BIAS_FLAGS,
                        )
                    )
                if lineage_records:
                    await write_lineage_batch(session, lineage_records)
                context.log.info(
                    f"Wrote {len(lineage_records)} lineage records"
                )
            except Exception as lineage_exc:
                context.log.warning(
                    f"Lineage recording failed: {lineage_exc}"
                )

        try:
            if store_span:
                store_span.end(
                    metadata={"records_upserted": records_upserted}
                )
        except Exception:
            pass

    finally:
        await engine.dispose()

    content_hash = hashlib.sha256(
        f"{year}:{len(geographies_processed)}:{records_upserted}".encode()
    ).hexdigest()[:32]

    context.log.info(
        f"Upserted {records_upserted} race estimates for "
        f"{len(geographies_processed)} geographies"
    )

    flush_langfuse(
        langfuse, trace, records_upserted,
        extra_metadata={
            "geographies_processed": len(geographies_processed),
        },
    )

    return MaterializeResult(
        metadata={
            "records_upserted": records_upserted,
            "year": year,
            "geographies_processed": len(geographies_processed),
            "races": MetadataValue.json_serializable(RACES),
            "content_hash": content_hash,
            "source_url": f"{CENSUS_BASE_URL}/{year}/acs/acs5",
            "bias_flags": MetadataValue.json_serializable(BIAS_FLAGS),
        }
    )
