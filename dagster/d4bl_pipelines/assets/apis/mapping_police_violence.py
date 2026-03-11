"""Mapping Police Violence incidents ingestion asset.

Fetches police violence incident data from the Mapping Police Violence
dataset (public CSV/Excel). No authentication required.
"""

import csv
import hashlib
import io
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

# Default download URL — configurable via env var since source URLs change
MPV_DATA_URL = os.environ.get(
    "MPV_DATA_URL",
    "https://mappingpoliceviolence.us/s/MPVDatasetDownload.xlsx",
)

# Known race categories in the source data
RACE_CATEGORIES = [
    "White",
    "Black",
    "Hispanic",
    "Asian",
    "Native American",
    "Pacific Islander",
    "Unknown",
]




def _derive_incident_id(date: str, name: str, city: str, state: str) -> str:
    """Derive a stable incident ID from key fields using SHA-256."""
    raw = f"{date}:{name}:{city}:{state}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


@asset(
    group_name="apis",
    description=(
        "Police violence incidents from Mapping Police Violence. "
        "Includes date, location, demographics, armed status, "
        "cause of death, and responsible agency."
    ),
    metadata={
        "source": "Mapping Police Violence (public dataset)",
        "methodology": "D4BL equity-focused policing data collection",
    },
    required_resource_keys={"db_url", "langfuse"},
)
async def mapping_police_violence(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Download MPV data and upsert into police_violence_incidents table."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    db_url = context.resources.db_url

    # --- Langfuse tracing ---
    langfuse = context.resources.langfuse
    trace = None
    try:
        if langfuse:
            trace = langfuse.trace(
                name="dagster:mapping_police_violence",
                metadata={"source_url": MPV_DATA_URL},
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
    races_seen = set()
    years_seen = set()

    context.log.info(f"Downloading MPV data from {MPV_DATA_URL}")

    try:
        async with aiohttp.ClientSession() as http_session:
            timeout = aiohttp.ClientTimeout(total=120)
            async with http_session.get(
                MPV_DATA_URL, timeout=timeout
            ) as resp:
                if resp.status != 200:
                    context.log.error(
                        f"Download failed with status {resp.status}"
                    )
                    flush_langfuse(langfuse, trace, 0)
                    return MaterializeResult(
                        metadata={
                            "status": "skipped",
                            "reason": (
                                f"HTTP {resp.status} from {MPV_DATA_URL}"
                            ),
                            "records_ingested": 0,
                        }
                    )

                content_type = resp.headers.get("Content-Type", "")
                raw_bytes = await resp.read()

            # Handle Excel or CSV formats
            if (
                "spreadsheet" in content_type
                or "excel" in content_type
                or MPV_DATA_URL.endswith(".xlsx")
                or MPV_DATA_URL.endswith(".xls")
            ):
                try:
                    import openpyxl

                    wb = openpyxl.load_workbook(
                        io.BytesIO(raw_bytes), read_only=True
                    )
                    ws = wb.active
                    rows_iter = ws.iter_rows(values_only=True)
                    header = [
                        str(h).strip().lower() if h else ""
                        for h in next(rows_iter)
                    ]
                    rows = [
                        dict(zip(header, row)) for row in rows_iter
                    ]
                except ImportError:
                    context.log.error(
                        "openpyxl not installed; cannot parse Excel. "
                        "Install it or provide a CSV URL via MPV_DATA_URL."
                    )
                    flush_langfuse(langfuse, trace, 0)
                    return MaterializeResult(
                        metadata={
                            "status": "skipped",
                            "reason": "openpyxl not installed",
                            "records_ingested": 0,
                        }
                    )
            else:
                text_data = raw_bytes.decode("utf-8-sig")
                reader = csv.DictReader(io.StringIO(text_data))
                rows = list(reader)
                # Normalize headers to lowercase
                rows = [
                    {k.strip().lower(): v for k, v in row.items()}
                    for row in rows
                ]

        context.log.info(f"Parsed {len(rows)} rows from source data")

        # Map common header variations to canonical names
        def _get(row, *keys, default=""):
            for k in keys:
                val = row.get(k)
                if val is not None and str(val).strip():
                    return str(val).strip()
            return default

        upsert_sql = text("""
            INSERT INTO police_violence_incidents
                (id, incident_id, date, year, state, city,
                 race, age, gender,
                 armed_status, cause_of_death, agency)
            VALUES
                (CAST(:id AS UUID), :incident_id,
                 CAST(:date AS DATE),
                 :year, :state, :city,
                 :race, :age, :gender,
                 :armed_status, :cause_of_death, :agency)
            ON CONFLICT (incident_id)
            DO UPDATE SET
                date = CAST(EXCLUDED.date AS DATE),
                year = EXCLUDED.year,
                state = EXCLUDED.state,
                city = EXCLUDED.city,
                race = EXCLUDED.race,
                age = EXCLUDED.age,
                gender = EXCLUDED.gender,
                armed_status = EXCLUDED.armed_status,
                cause_of_death = EXCLUDED.cause_of_death,
                agency = EXCLUDED.agency
        """)

        async with async_session() as session:
            batch_count = 0
            for row in rows:
                name = _get(
                    row, "victim's name", "name",
                    "victims name", "victim name",
                )
                date_raw = _get(
                    row, "date of incident (month/day/year)",
                    "date", "date of incident",
                )
                city = _get(row, "city", "location_city")
                state = _get(
                    row, "state", "location_state", "state_abbr"
                )
                race = _get(
                    row, "victim's race",
                    "race", "victims race", "victim race",
                    default="Unknown",
                )
                age = _get(
                    row, "victim's age", "age",
                    "victims age", "victim age",
                )
                gender = _get(
                    row, "victim's gender", "gender",
                    "victims gender", "victim gender",
                    default="Unknown",
                )
                armed_status = _get(
                    row, "armed/unarmed status",
                    "armed_status", "armed/unarmed",
                    "allegedly armed", default="Unknown",
                )
                cause = _get(
                    row, "cause of death",
                    "cause_of_death", "manner of death",
                    default="Unknown",
                )
                agency = _get(
                    row, "agency responsible for death",
                    "agency", "department", "agency_name",
                    default="Unknown",
                )

                if not date_raw or not name:
                    continue

                # Parse date to ISO format (YYYY-MM-DD) BEFORE
                # deriving incident ID so the ID is stable.
                date_iso = None
                year = None
                try:
                    from datetime import datetime as _dt

                    for fmt in (
                        "%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y",
                        "%Y/%m/%d", "%d/%m/%Y",
                    ):
                        try:
                            parsed = _dt.strptime(date_raw, fmt)
                            date_iso = parsed.strftime("%Y-%m-%d")
                            year = parsed.year
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass

                if date_iso is None:
                    # Fallback: try to extract year at least
                    for part in date_raw.replace(
                        "-", "/"
                    ).split("/"):
                        try:
                            val = int(part)
                            if val > 1900:
                                year = val
                                break
                        except ValueError:
                            continue
                    date_iso = date_raw

                # Use the normalized ISO date for a stable ID;
                # fall back to "unknown" if parsing failed entirely.
                date_for_id = (
                    date_iso if date_iso != date_raw else "unknown"
                )
                incident_id = _derive_incident_id(
                    date_for_id, name, city, state
                )

                # Parse age as integer
                age_int = None
                try:
                    age_int = int(age)
                except (ValueError, TypeError):
                    pass

                states_seen.add(state)
                races_seen.add(race)
                if year:
                    years_seen.add(year)

                record_uuid = uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"mpv:{incident_id}",
                )

                await session.execute(
                    upsert_sql,
                    {
                        "id": str(record_uuid),
                        "incident_id": incident_id,
                        "date": date_iso,
                        "year": year,
                        "state": state,
                        "city": city,
                        "race": race,
                        "age": age_int,
                        "gender": gender,
                        "armed_status": armed_status,
                        "cause_of_death": cause,
                        "agency": agency,
                    },
                )
                records_ingested += 1
                batch_count += 1

                if batch_count >= 1000:
                    await session.commit()
                    context.log.info(
                        f"  Committed batch: {records_ingested} "
                        f"records so far"
                    )
                    batch_count = 0

            await session.commit()

    except aiohttp.ClientError as exc:
        context.log.error(f"Download failed: {exc}")
        flush_langfuse(langfuse, trace, records_ingested)
        return MaterializeResult(
            metadata={
                "status": "skipped",
                "reason": str(exc),
                "records_ingested": records_ingested,
            }
        )
    finally:
        await engine.dispose()

    bias_flags = [
        "Self-reported/media-sourced data; may not capture all incidents",
        "Race categorization is based on media reports and public records",
        "Incident identification depends on media coverage — "
        "rural and smaller jurisdictions may be underrepresented",
    ]

    flush_langfuse(langfuse, trace, records_ingested)

    context.log.info(
        f"Ingested {records_ingested} police violence incident records "
        f"across {len(states_seen)} states, "
        f"years {sorted(years_seen) if years_seen else 'N/A'}"
    )

    return MaterializeResult(
        metadata={
            "records_ingested": records_ingested,
            "states_covered": len(states_seen),
            "races_seen": sorted(races_seen),
            "years_covered": sorted(years_seen),
            "source_url": MPV_DATA_URL,
            "bias_flags": MetadataValue.json_serializable(bias_flags),
        }
    )
