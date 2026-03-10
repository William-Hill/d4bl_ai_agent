"""DOE Civil Rights Data Collection (CRDC) ingestion asset.

Fetches school discipline, AP enrollment, and chronic absenteeism data
disaggregated by race from the DOE Office for Civil Rights bulk CSV
download. No authentication required.
"""

import csv
import io
import os
import uuid

import aiohttp

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

# Bulk CSV download URL for CRDC data
CRDC_BASE_URL = (
    "https://ocrdata.ed.gov/assets/downloads/crdc-2020-2021.zip"
)

# Key civil-rights metrics to extract
CRDC_METRICS = [
    "in_school_suspensions",
    "out_of_school_suspensions",
    "expulsions",
    "ap_enrollment",
    "chronic_absenteeism",
]

# Race categories tracked by CRDC
RACE_CATEGORIES = [
    "White",
    "Black",
    "Hispanic",
    "Asian",
    "AIAN",
    "NHPI",
    "Two_or_more",
]

# Column-name mapping: maps CSV header fragments to (metric, race) tuples.
# CRDC CSVs use column names like "TOT_DISCWODIS_ISS_HI_M" etc.
# We map prefixes to our canonical metric names.
_METRIC_COLUMN_PREFIXES = {
    "SCH_DISCWODIS_ISS": "in_school_suspensions",
    "SCH_DISCWDIS_ISS": "in_school_suspensions",
    "SCH_DISCWODIS_OSS": "out_of_school_suspensions",
    "SCH_DISCWDIS_OSS": "out_of_school_suspensions",
    "SCH_DISCWODIS_EXPWE": "expulsions",
    "SCH_DISCWODIS_EXPWOE": "expulsions",
    "SCH_DISCWDIS_EXPWE": "expulsions",
    "SCH_DISCWDIS_EXPWOE": "expulsions",
    "TOT_APEXAM": "ap_enrollment",
    "TOT_APENR": "ap_enrollment",
    "SCH_APEXAM": "ap_enrollment",
    "SCH_APENR": "ap_enrollment",
    "TOT_ABSENT": "chronic_absenteeism",
    "SCH_ABSENT": "chronic_absenteeism",
}

# CRDC race suffixes
_RACE_SUFFIXES = {
    "_WH": "White",
    "_BL": "Black",
    "_HI": "Hispanic",
    "_AS": "Asian",
    "_AM": "AIAN",
    "_HP": "NHPI",
    "_TR": "Two_or_more",
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


def _parse_crdc_row(row, school_year):
    """Parse a single CRDC CSV row into a list of metric records.

    Returns a list of dicts, each with keys:
        district_id, district_name, state, state_name, school_year,
        metric, race, value
    """
    records = []
    district_id = row.get("LEA_STATE_LEAID", row.get("LEAID", ""))
    district_name = row.get("LEA_NAME", "")
    state = row.get("LEA_STATE", "")
    state_name = row.get("LEA_STATENAME", state)

    if not district_id:
        return records

    # Scan columns for metric+race combinations
    for col_name, raw_value in row.items():
        if raw_value is None or str(raw_value).strip() in ("", "-9", "-2"):
            continue

        col_upper = col_name.upper()
        matched_metric = None
        matched_race = None

        # Check if column matches a metric prefix
        for prefix, metric in _METRIC_COLUMN_PREFIXES.items():
            if col_upper.startswith(prefix):
                suffix = col_upper[len(prefix):]
                # Check race suffix (ignore gender suffixes _M, _F)
                for race_suffix, race in _RACE_SUFFIXES.items():
                    if race_suffix in suffix:
                        matched_metric = metric
                        matched_race = race
                        break
                break

        if not matched_metric or not matched_race:
            continue

        try:
            value = float(str(raw_value).strip())
        except (ValueError, TypeError):
            continue

        records.append({
            "district_id": str(district_id).strip(),
            "district_name": district_name.strip(),
            "state": state.strip(),
            "state_name": state_name.strip(),
            "school_year": school_year,
            "metric": matched_metric,
            "race": matched_race,
            "value": value,
        })

    return records


@asset(
    group_name="apis",
    description=(
        "Civil rights data from DOE CRDC including suspensions, "
        "expulsions, AP enrollment, and chronic absenteeism "
        "disaggregated by race."
    ),
    metadata={
        "source": "DOE Office for Civil Rights Data Collection",
        "methodology": "D4BL equity-focused education data collection",
    },
    required_resource_keys={"db_url", "langfuse"},
)
async def doe_civil_rights(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Fetch CRDC CSV data and upsert into doe_civil_rights table."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    db_url = context.resources.db_url
    school_year = os.environ.get("CRDC_SCHOOL_YEAR", "2020-2021")

    # --- Langfuse tracing ---
    langfuse = context.resources.langfuse
    trace = None
    try:
        if langfuse:
            trace = langfuse.trace(
                name="dagster:doe_civil_rights",
                metadata={"school_year": school_year},
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
    metrics_seen = set()
    races_seen = set()

    download_url = os.environ.get("CRDC_DOWNLOAD_URL", CRDC_BASE_URL)
    context.log.info(
        f"Fetching CRDC data for school_year={school_year} "
        f"from {download_url}"
    )

    try:
        async with aiohttp.ClientSession() as http_session:
            timeout = aiohttp.ClientTimeout(total=300)
            try:
                async with http_session.get(
                    download_url, timeout=timeout
                ) as resp:
                    if resp.status != 200:
                        context.log.warning(
                            f"CRDC download failed with status "
                            f"{resp.status}. CRDC bulk data may not "
                            f"be available at this URL. Skipping."
                        )
                        _flush_langfuse(
                            langfuse, trace, 0,
                            {"status": "skipped",
                             "reason": f"HTTP {resp.status}"},
                        )
                        return MaterializeResult(
                            metadata={
                                "records_ingested": 0,
                                "status": "skipped",
                                "reason": (
                                    f"CRDC download returned HTTP "
                                    f"{resp.status}"
                                ),
                                "source_url": download_url,
                            }
                        )
                    content_bytes = await resp.read()
            except (aiohttp.ClientError, TimeoutError) as exc:
                context.log.warning(
                    f"CRDC download failed: {exc}. Skipping."
                )
                _flush_langfuse(
                    langfuse, trace, 0,
                    {"status": "skipped", "reason": str(exc)},
                )
                return MaterializeResult(
                    metadata={
                        "records_ingested": 0,
                        "status": "skipped",
                        "reason": f"Download error: {exc}",
                        "source_url": download_url,
                    }
                )

        # Handle ZIP or plain CSV
        csv_text = None
        if download_url.endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(io.BytesIO(content_bytes)) as zf:
                csv_names = [
                    n for n in zf.namelist()
                    if n.lower().endswith(".csv")
                ]
                if not csv_names:
                    context.log.warning(
                        "No CSV files found in CRDC ZIP archive."
                    )
                    _flush_langfuse(
                        langfuse, trace, 0,
                        {"status": "skipped",
                         "reason": "no CSV in ZIP"},
                    )
                    return MaterializeResult(
                        metadata={
                            "records_ingested": 0,
                            "status": "skipped",
                            "reason": "No CSV files in ZIP archive",
                            "source_url": download_url,
                        }
                    )
                # Use the first CSV found
                csv_text = zf.read(csv_names[0]).decode(
                    "utf-8", errors="replace"
                )
                context.log.info(
                    f"Extracted {csv_names[0]} from ZIP "
                    f"({len(csv_names)} CSVs total)"
                )
        else:
            csv_text = content_bytes.decode("utf-8", errors="replace")

        reader = csv.DictReader(io.StringIO(csv_text))

        batch = []
        batch_size = 500

        async with async_session() as session:
            for row in reader:
                parsed = _parse_crdc_row(row, school_year)
                batch.extend(parsed)

                if len(batch) >= batch_size:
                    for rec in batch:
                        record_id = uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"crdc:{rec['district_id']}:"
                            f"{rec['school_year']}:"
                            f"{rec['metric']}:{rec['race']}",
                        )

                        upsert_sql = text("""
                            INSERT INTO doe_civil_rights
                                (id, district_id, district_name,
                                 state, state_name, school_year,
                                 metric, race, value)
                            VALUES
                                (CAST(:id AS UUID), :district_id,
                                 :district_name, :state,
                                 :state_name, :school_year,
                                 :metric, :race, :value)
                            ON CONFLICT (district_id, school_year,
                                         metric, race)
                            DO UPDATE SET
                                value = :value,
                                district_name = :district_name,
                                state = :state,
                                state_name = :state_name
                        """)
                        await session.execute(
                            upsert_sql,
                            {
                                "id": str(record_id),
                                "district_id": rec["district_id"],
                                "district_name": rec["district_name"],
                                "state": rec["state"],
                                "state_name": rec["state_name"],
                                "school_year": rec["school_year"],
                                "metric": rec["metric"],
                                "race": rec["race"],
                                "value": rec["value"],
                            },
                        )
                        states_seen.add(rec["state"])
                        metrics_seen.add(rec["metric"])
                        races_seen.add(rec["race"])
                        records_ingested += 1

                    await session.commit()
                    context.log.info(
                        f"Committed batch: {records_ingested} "
                        f"records so far"
                    )
                    batch = []

            # Flush remaining batch
            if batch:
                for rec in batch:
                    record_id = uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"crdc:{rec['district_id']}:"
                        f"{rec['school_year']}:"
                        f"{rec['metric']}:{rec['race']}",
                    )

                    upsert_sql = text("""
                        INSERT INTO doe_civil_rights
                            (id, district_id, district_name,
                             state, state_name, school_year,
                             metric, race, value)
                        VALUES
                            (CAST(:id AS UUID), :district_id,
                             :district_name, :state,
                             :state_name, :school_year,
                             :metric, :race, :value)
                        ON CONFLICT (district_id, school_year,
                                     metric, race)
                        DO UPDATE SET
                            value = :value,
                            district_name = :district_name,
                            state = :state,
                            state_name = :state_name
                    """)
                    await session.execute(
                        upsert_sql,
                        {
                            "id": str(record_id),
                            "district_id": rec["district_id"],
                            "district_name": rec["district_name"],
                            "state": rec["state"],
                            "state_name": rec["state_name"],
                            "school_year": rec["school_year"],
                            "metric": rec["metric"],
                            "race": rec["race"],
                            "value": rec["value"],
                        },
                    )
                    states_seen.add(rec["state"])
                    metrics_seen.add(rec["metric"])
                    races_seen.add(rec["race"])
                    records_ingested += 1

                await session.commit()

    finally:
        await engine.dispose()

    bias_flags = [
        "limitation: CRDC data is biennial (every 2 years)",
        f"coverage: most recent collection is {school_year}",
        "limitation: self-reported by school districts, "
        "potential under-reporting",
    ]
    if len(metrics_seen) < len(CRDC_METRICS):
        missing = set(CRDC_METRICS) - metrics_seen
        bias_flags.append(f"missing_metrics: {sorted(missing)}")

    _flush_langfuse(langfuse, trace, records_ingested)

    context.log.info(
        f"Ingested {records_ingested} CRDC records "
        f"across {len(states_seen)} states, "
        f"{len(metrics_seen)} metrics, {len(races_seen)} races"
    )

    return MaterializeResult(
        metadata={
            "records_ingested": records_ingested,
            "school_year": school_year,
            "states_covered": len(states_seen),
            "metrics_covered": sorted(metrics_seen),
            "races_covered": sorted(races_seen),
            "source_url": download_url,
            "bias_flags": MetadataValue.json_serializable(bias_flags),
        }
    )
