"""EPA EJScreen environmental justice ingestion asset.

Fetches environmental justice screening data by state from the
EPA EJScreen API. No authentication required.

Note: EJScreen data is fetched at state summary level.
Tract-level data can be added as follow-up work.
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

# CSV column names for the indicators we track.
# These map 1:1 to EJ_INDICATORS (which are used for both
# the REST API and the CSV download).
CSV_INDICATOR_COLUMNS = list(EJ_INDICATORS)

# Default download URL — EPA EJScreen annual CSV (US Percentiles).
# EPA discontinued public access in Feb 2025; set EPA_EJSCREEN_CSV_URL
# env var to point at a mirror (e.g. Zenodo, Harvard Dataverse).
DEFAULT_EJSCREEN_CSV_URL = (
    "https://gaftp.epa.gov/EJSCREEN/{year}/EJSCREEN_{year}_USPR.csv.zip"
)


def aggregate_block_groups_to_tracts(
    rows: list[dict],
) -> dict[str, dict]:
    """Aggregate block-group rows to tract-level using population-weighted averages.

    Args:
        rows: List of dicts with keys matching the EJScreen CSV columns.
              Each row is one block group.

    Returns:
        Dict keyed by 11-digit tract FIPS, values are dicts with:
        - state_fips, state_abbrev, population, minority_pct, low_income_pct
        - indicators: dict[indicator_lower -> {raw_value, percentile_national}]
    """
    accum: dict[str, dict] = {}

    for row in rows:
        bg_id = row.get("ID", "").strip()
        if len(bg_id) < 11:
            continue
        tract_fips = bg_id[:11]

        try:
            pop = int(float(row.get("ACSTOTPOP", "") or "0"))
        except (ValueError, TypeError):
            pop = 0
        if pop <= 0:
            continue

        if tract_fips not in accum:
            accum[tract_fips] = {
                "state_fips": tract_fips[:2],
                "state_abbrev": row.get("ST_ABBREV", ""),
                "pop_total": 0,
                "minority_weighted": 0.0,
                "lowinc_weighted": 0.0,
                "indicators": {},
            }

        t = accum[tract_fips]
        t["pop_total"] += pop

        try:
            minority = float(row.get("MINORPCT", "") or "0")
            t["minority_weighted"] += minority * pop
        except (ValueError, TypeError):
            pass
        try:
            lowinc = float(row.get("LOWINCPCT", "") or "0")
            t["lowinc_weighted"] += lowinc * pop
        except (ValueError, TypeError):
            pass

        for col in CSV_INDICATOR_COLUMNS:
            col_lower = col.lower()
            if col_lower not in t["indicators"]:
                t["indicators"][col_lower] = {
                    "raw_weighted": 0.0,
                    "pctile_weighted": 0.0,
                    "pop_with_data": 0,
                }
            ind = t["indicators"][col_lower]

            raw_str = row.get(col, "")
            if raw_str is None or str(raw_str).strip() == "":
                raw_val = None
            else:
                try:
                    raw_val = float(raw_str)
                except (ValueError, TypeError):
                    raw_val = None

            pctile_str = row.get(f"P_{col}", "")
            if pctile_str is None or str(pctile_str).strip() == "":
                pctile_val = None
            else:
                try:
                    pctile_val = float(pctile_str)
                except (ValueError, TypeError):
                    pctile_val = None

            if raw_val is not None or pctile_val is not None:
                ind["pop_with_data"] += pop
                if raw_val is not None:
                    ind["raw_weighted"] += raw_val * pop
                if pctile_val is not None:
                    ind["pctile_weighted"] += pctile_val * pop

    result: dict[str, dict] = {}
    for tract_fips, t in accum.items():
        pop = t["pop_total"]
        if pop <= 0:
            continue

        indicators: dict[str, dict] = {}
        for ind_name, ind_data in t["indicators"].items():
            p = ind_data["pop_with_data"]
            if p <= 0:
                continue
            indicators[ind_name] = {
                "raw_value": ind_data["raw_weighted"] / p,
                "percentile_national": ind_data["pctile_weighted"] / p,
            }

        result[tract_fips] = {
            "state_fips": t["state_fips"],
            "state_abbrev": t["state_abbrev"],
            "population": pop,
            "minority_pct": t["minority_weighted"] / pop,
            "low_income_pct": t["lowinc_weighted"] / pop,
            "indicators": indicators,
        }

    return result


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

                # Hoist the SQL text object outside the per-indicator
                # loop so it is compiled once per state, not once per row.
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

                async with async_session() as session:
                    for indicator in EJ_INDICATORS:
                        indicator_lower = indicator.lower()
                        # Try multiple key patterns (use `is not None`
                        # so that legitimate zero values are preserved)
                        raw_val = raw_data.get(indicator)
                        if raw_val is None:
                            raw_val = raw_data.get(indicator_lower)
                        if raw_val is None:
                            raw_val = raw_data.get(f"RAW_{indicator}")

                        pctile = raw_data.get(f"P_{indicator}")
                        if pctile is None:
                            pctile = raw_data.get(f"PCTILE_{indicator}")

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

                        minority = raw_data.get("MINORPCT")
                        if minority is None:
                            minority = raw_data.get("minorpct")
                        lowinc = raw_data.get("LOWINCPCT")
                        if lowinc is None:
                            lowinc = raw_data.get("lowincpct")
                        pop = raw_data.get("ACSTOTPOP")
                        if pop is None:
                            pop = raw_data.get("acstotpop")

                        await session.execute(
                            upsert_sql,
                            {
                                "id": str(record_id),
                                # tract_fips stores the 2-digit state FIPS
                                # because this asset fetches state-level
                                # summaries, not census-tract-level data.
                                "tract_fips": fips,
                                "state_fips": fips,
                                "state_name": state_name,
                                "year": year,
                                "indicator": indicator_lower,
                                "raw_value": raw_float,
                                "pctile_state": pctile_float,
                                "pctile_national": pctile_float,
                                "pop": int(pop) if pop is not None else None,
                                "minority": float(minority) if minority is not None else None,
                                "lowinc": float(lowinc) if lowinc is not None else None,
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
        "limitation: tract_fips stores 2-digit state FIPS (not 11-digit tract)",
        "single_source: all data from EPA EJScreen",
    ]
    if len(states_covered) < len(STATE_FIPS):
        missing = set(STATE_FIPS.keys()) - states_covered
        bias_flags.append(
            f"missing_states: {len(missing)} states had no data"
        )

    flush_langfuse(langfuse, trace, records_ingested)

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


@asset(
    group_name="apis",
    description=(
        "Environmental justice screening indicators by census tract from "
        "EPA EJScreen bulk CSV download. Aggregates block-group data to "
        "tract level using population-weighted averages."
    ),
    metadata={
        "source": "EPA EJScreen Annual CSV",
        "methodology": "D4BL environmental justice data collection",
        "granularity": "tract",
    },
    required_resource_keys={"db_url", "langfuse"},
)
async def epa_ejscreen_tract(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Download EPA EJScreen CSV, aggregate block groups to tracts, upsert."""
    import csv as csv_mod
    import io
    import tempfile
    import zipfile

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    db_url = context.resources.db_url
    year = int(os.environ.get("EPA_EJSCREEN_YEAR", "2024"))

    csv_url = os.environ.get(
        "EPA_EJSCREEN_CSV_URL",
        DEFAULT_EJSCREEN_CSV_URL.format(year=year),
    )

    langfuse = context.resources.langfuse
    trace = None
    try:
        if langfuse:
            trace = langfuse.trace(
                name="dagster:epa_ejscreen_tract",
                metadata={"year": year, "csv_url": csv_url},
            )
    except Exception as exc:
        context.log.warning(f"Langfuse trace init failed: {exc}")
        langfuse = None

    engine = create_async_engine(db_url, pool_size=3, max_overflow=5)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    context.log.info(
        f"Downloading EJScreen CSV for year={year} from {csv_url}"
    )

    # --- Download ZIP to temp file ---
    try:
        download_span = trace.span(name="download") if trace else None
    except Exception:
        download_span = None

    tmp_path = None
    try:
        async with aiohttp.ClientSession() as http_session:
            timeout = aiohttp.ClientTimeout(total=600)
            async with http_session.get(
                csv_url, timeout=timeout
            ) as resp:
                if resp.status != 200:
                    context.log.error(
                        f"Failed to download EJScreen CSV: "
                        f"HTTP {resp.status}. Set EPA_EJSCREEN_CSV_URL "
                        f"env var to point at a working mirror."
                    )
                    await engine.dispose()
                    flush_langfuse(langfuse, trace, 0)
                    return MaterializeResult(
                        metadata={
                            "records_ingested": 0,
                            "status": "download_failed",
                            "http_status": resp.status,
                        }
                    )
                with tempfile.NamedTemporaryFile(
                    suffix=".zip", delete=False
                ) as tmp:
                    tmp_path = tmp.name
                    async for chunk in resp.content.iter_chunked(
                        1024 * 1024
                    ):
                        tmp.write(chunk)

        try:
            if download_span:
                download_span.end(
                    metadata={"file_size_mb": os.path.getsize(tmp_path) / (1024 * 1024)}
                )
        except Exception:
            pass

        context.log.info(
            f"Downloaded {os.path.getsize(tmp_path) / (1024*1024):.1f} MB"
        )

        # --- Extract and parse CSV ---
        try:
            parse_span = trace.span(name="parse") if trace else None
        except Exception:
            parse_span = None

        rows: list[dict] = []
        with zipfile.ZipFile(tmp_path, "r") as zf:
            csv_names = [
                n for n in zf.namelist()
                if n.lower().endswith(".csv")
            ]
            if not csv_names:
                context.log.error("No CSV file found in ZIP")
                await engine.dispose()
                flush_langfuse(langfuse, trace, 0)
                return MaterializeResult(
                    metadata={
                        "records_ingested": 0,
                        "status": "no_csv_in_zip",
                    }
                )
            csv_name = csv_names[0]
            context.log.info(f"Parsing {csv_name}")
            with zf.open(csv_name) as csv_file:
                reader = csv_mod.DictReader(
                    io.TextIOWrapper(csv_file, encoding="utf-8")
                )
                for row in reader:
                    rows.append(row)

        context.log.info(f"Parsed {len(rows)} block-group rows")
        try:
            if parse_span:
                parse_span.end(
                    metadata={"block_groups": len(rows)}
                )
        except Exception:
            pass

        # --- Aggregate to tract level ---
        tracts = aggregate_block_groups_to_tracts(rows)
        context.log.info(
            f"Aggregated to {len(tracts)} tracts"
        )

        # --- Upsert into database ---
        records_ingested = 0
        states_covered = set()

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

        try:
            store_span = trace.span(name="store") if trace else None
        except Exception:
            store_span = None

        async with async_session() as session:
            for tract_fips, tract_data in tracts.items():
                states_covered.add(tract_data["state_fips"])
                state_name = STATE_FIPS.get(
                    tract_data["state_fips"],
                    tract_data["state_abbrev"],
                )

                for indicator, ind_vals in tract_data[
                    "indicators"
                ].items():
                    record_id = uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"epa:tract:{tract_fips}:{year}:{indicator}",
                    )
                    await session.execute(
                        upsert_sql,
                        {
                            "id": str(record_id),
                            "tract_fips": tract_fips,
                            "state_fips": tract_data["state_fips"],
                            "state_name": state_name,
                            "year": year,
                            "indicator": indicator,
                            "raw_value": ind_vals["raw_value"],
                            "pctile_state": None,
                            "pctile_national": ind_vals[
                                "percentile_national"
                            ],
                            "pop": tract_data["population"],
                            "minority": tract_data["minority_pct"],
                            "lowinc": tract_data["low_income_pct"],
                        },
                    )
                    records_ingested += 1

            await session.commit()

            # --- Lineage recording ---
            try:
                from d4bl_pipelines.quality.lineage import (
                    build_lineage_record,
                    write_lineage_batch,
                )

                ingestion_run_id = uuid.uuid4()
                lineage_records = []
                for fips in states_covered:
                    rec_id = uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"epa:tract:lineage:{fips}:{year}",
                    )
                    lineage_records.append(
                        build_lineage_record(
                            ingestion_run_id=ingestion_run_id,
                            target_table="epa_environmental_justice",
                            record_id=rec_id,
                            source_url=csv_url,
                            transformation={
                                "steps": [
                                    "download_csv",
                                    "aggregate_block_groups",
                                    "upsert",
                                ],
                                "geography": "tract",
                                "state_fips": fips,
                            },
                        )
                    )
                if lineage_records:
                    await write_lineage_batch(
                        session, lineage_records
                    )
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
                    metadata={"records_ingested": records_ingested}
                )
        except Exception:
            pass

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        await engine.dispose()

    bias_flags = [
        "aggregation: block-group data averaged to tract level "
        "(population-weighted)",
        "percentile_state: not available in aggregated tract data "
        "(set to null)",
    ]
    if len(states_covered) < len(STATE_FIPS):
        missing = set(STATE_FIPS.keys()) - states_covered
        bias_flags.append(
            f"missing_states: {len(missing)} states had no data"
        )

    flush_langfuse(langfuse, trace, records_ingested)

    context.log.info(
        f"Ingested {records_ingested} EJScreen tract records "
        f"for {len(tracts)} tracts across "
        f"{len(states_covered)} states"
    )

    return MaterializeResult(
        metadata={
            "records_ingested": records_ingested,
            "year": year,
            "tracts_covered": len(tracts),
            "states_covered": len(states_covered),
            "block_groups_parsed": len(rows),
            "indicators": sorted(
                ind.lower() for ind in CSV_INDICATOR_COLUMNS
            ),
            "source_url": csv_url,
            "bias_flags": MetadataValue.json_serializable(
                bias_flags
            ),
        }
    )
