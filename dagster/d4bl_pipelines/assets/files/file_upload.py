"""File upload data ingestion assets.

Factory that generates Dagster assets for data sources with
source_type='file_upload'.  Each asset reads an uploaded file
(CSV, Excel, or JSON) from disk and upserts its rows into the
database via raw SQL.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from d4bl_pipelines.utils import (
    INGESTED_RECORDS_UPSERT_SQL,
    compute_content_hash,
    db_session,
    derive_record_key,
    slugify,
)
from dagster import (
    AssetExecutionContext,
    AssetsDefinition,
    MaterializeResult,
    MetadataValue,
    asset,
)

UPLOAD_ROOT = os.environ.get(
    "D4BL_UPLOAD_DIR", "/tmp/d4bl_uploads"
)

ALLOWED_EXTENSIONS = {"csv", "xlsx", "json"}


def _file_extension(filename: str) -> str:
    """Return the lowercase file extension without the dot."""
    return Path(filename).suffix.lstrip(".").lower()


def _parse_file(filepath: Path) -> tuple[list[dict], str]:
    """Parse a file and return (rows, format_name).

    Supports CSV, Excel (.xlsx), and JSON.
    """
    ext = _file_extension(filepath.name)

    if ext == "csv":
        import csv

        with open(filepath, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        return rows, "csv"

    elif ext == "xlsx":
        import openpyxl

        wb = openpyxl.load_workbook(filepath, read_only=True)
        ws = wb.active
        data = list(ws.iter_rows(values_only=True))
        if not data:
            return [], "xlsx"
        headers = [str(h) if h is not None else f"col_{i}"
                   for i, h in enumerate(data[0])]
        rows = [
            dict(zip(headers, row))
            for row in data[1:]
        ]
        wb.close()
        return rows, "xlsx"

    elif ext == "json":
        with open(filepath, encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict) and "data" in payload:
            rows = payload["data"]
        else:
            rows = [payload]
        return rows, "json"

    else:
        raise ValueError(f"Unsupported file format: {ext}")


def _latest_file(upload_dir: Path) -> Path | None:
    """Return the most recently modified file in the upload dir."""
    if not upload_dir.exists():
        return None
    files = [
        f for f in upload_dir.iterdir()
        if f.is_file() and _file_extension(f.name) in ALLOWED_EXTENSIONS
    ]
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime)


def build_file_upload_assets(
    data_sources: list[dict],
) -> list[AssetsDefinition]:
    """Generate one Dagster asset per file_upload data source.

    Each dict in *data_sources* must contain at minimum:
        - ``id``: unique source identifier (str or UUID)
        - ``name``: human-readable name
        - ``source_type``: must be ``'file_upload'``
        - ``config``: optional dict with ``upload_dir`` override

    Returns a list of ``AssetsDefinition`` objects.
    """
    assets: list[AssetsDefinition] = []

    for source in data_sources:
        if source.get("source_type") != "file_upload":
            continue

        source_id = str(source["id"])
        source_name = source.get("name", source_id)
        config = source.get("config") or {}
        upload_dir = config.get(
            "upload_dir",
            os.path.join(UPLOAD_ROOT, source_id),
        )

        # Use slugified source name for asset key (matches schedules/triggers)
        asset_key = slugify(source_name)

        @asset(
            name=asset_key,
            group_name="files",
            description=(
                f"Ingest uploaded file for source '{source_name}'"
            ),
            metadata={
                "source_id": source_id,
                "source_name": source_name,
                "upload_dir": upload_dir,
            },
        )
        async def _file_upload_asset(
            context: AssetExecutionContext,
            *,
            _upload_dir: str = upload_dir,
            _source_id: str = source_id,
            _source_name: str = source_name,
        ) -> MaterializeResult:
            """Read the latest file from the upload directory and ingest."""
            from sqlalchemy import text

            dir_path = Path(_upload_dir)
            filepath = _latest_file(dir_path)
            if filepath is None:
                context.log.warning(
                    f"No files found in {_upload_dir}"
                )
                return MaterializeResult(
                    metadata={
                        "records_ingested": 0,
                        "status": "no_file",
                    }
                )

            context.log.info(
                f"Processing file: {filepath.name} "
                f"for source '{_source_name}'"
            )

            rows, file_format = _parse_file(filepath)
            if not rows:
                context.log.warning("Parsed file contains no rows")
                return MaterializeResult(
                    metadata={
                        "records_ingested": 0,
                        "file_name": filepath.name,
                        "file_format": file_format,
                        "status": "empty_file",
                    }
                )

            # Compute a content hash for deduplication tracking
            content_hash = compute_content_hash(rows)

            db_url = context.resources.db_url

            records_ingested = 0
            upsert_sql = text(INGESTED_RECORDS_UPSERT_SQL)
            now = datetime.now(timezone.utc)

            async with db_session(db_url) as session:
                for idx, row in enumerate(rows):
                    record_key = derive_record_key(
                        row, idx, _source_id
                    )
                    record_id = uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"file:{_source_id}:{record_key}",
                    )
                    await session.execute(
                        upsert_sql,
                        {
                            "id": str(record_id),
                            "source_id": _source_id,
                            "record_key": record_key,
                            "data": json.dumps(
                                row, default=str
                            ),
                            "content_hash": content_hash,
                            "ingested_at": now,
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
                    for row_idx, row in enumerate(rows):
                        rk = derive_record_key(
                            row, row_idx, _source_id
                        )
                        rid = uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"file:{_source_id}:{rk}",
                        )
                        lineage_records.append(
                            build_lineage_record(
                                ingestion_run_id=(
                                    ingestion_run_id
                                ),
                                target_table="ingested_records",
                                record_id=rid,
                                source_url=str(filepath),
                                source_hash=content_hash,
                                transformation={
                                    "steps": [
                                        "read_file",
                                        f"parse_{file_format}",
                                        "upsert",
                                    ]
                                },
                            )
                        )
                    if lineage_records:
                        await write_lineage_batch(
                            session, lineage_records
                        )
                    context.log.info(
                        f"Wrote {len(lineage_records)} "
                        f"lineage records"
                    )
                except Exception as lineage_exc:
                    context.log.warning(
                        f"Lineage recording failed: {lineage_exc}"
                    )

            context.log.info(
                f"Ingested {records_ingested} records "
                f"from {filepath.name}"
            )

            return MaterializeResult(
                metadata={
                    "records_ingested": records_ingested,
                    "file_name": filepath.name,
                    "file_format": file_format,
                    "content_hash": content_hash,
                    "source_id": _source_id,
                    "quality_score": MetadataValue.float(
                        min(5.0, (records_ingested / 100) * 5)
                        if records_ingested > 0
                        else 0.0
                    ),
                }
            )

        assets.append(_file_upload_asset)

    return assets
