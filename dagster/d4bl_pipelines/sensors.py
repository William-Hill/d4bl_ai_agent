"""Dagster sensors for the D4BL data pipelines."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Tuple

from d4bl_pipelines.assets.files.file_upload import (
    ALLOWED_EXTENSIONS,
    UPLOAD_ROOT,
    _file_extension,
)
from d4bl_pipelines.utils import slugify
from dagster import (
    AssetKey,
    DefaultSensorStatus,
    RunRequest,
    SensorEvaluationContext,
    SkipReason,
    sensor,
)

SENSOR_MIN_INTERVAL = 30  # seconds


@sensor(
    minimum_interval_seconds=SENSOR_MIN_INTERVAL,
    default_status=DefaultSensorStatus.STOPPED,
    description=(
        "Watches upload directories for new files and triggers "
        "file upload asset materialization."
    ),
)
def file_upload_sensor(context: SensorEvaluationContext):
    """Scan upload directories for new files.

    Uses a JSON cursor mapping ``filepath -> mtime`` to track
    files that have already been processed.
    """
    upload_root = Path(
        os.environ.get("D4BL_UPLOAD_DIR", UPLOAD_ROOT)
    )

    # Load cursor (previously-seen files)
    cursor_raw = context.cursor or "{}"
    try:
        seen_files: dict[str, float] = json.loads(cursor_raw)
    except (json.JSONDecodeError, TypeError):
        seen_files = {}

    if not upload_root.exists():
        context.log.debug(
            f"Upload root does not exist: {upload_root}"
        )
        return

    new_seen = dict(seen_files)

    # Build a mapping from source_id (directory name) to asset key.
    # The sensor scans UUID-named directories, but file_upload assets
    # are keyed by slugify(source_name).  We read asset metadata to
    # find the correct mapping.  Fallback: use slugify(source_id).
    source_id_to_asset_key: dict[str, str] = {}
    for asset_def in context.repository_def.get_all_assets() if hasattr(context, "repository_def") else []:
        for spec in getattr(asset_def, "specs_by_key", {}).values():
            meta = spec.metadata or {}
            sid = meta.get("source_id")
            if sid and spec.group_name == "files":
                source_id_to_asset_key[str(sid)] = spec.key.path[-1]

    for source_dir in upload_root.iterdir():
        if not source_dir.is_dir():
            continue

        source_id = source_dir.name

        for filepath in source_dir.iterdir():
            if not filepath.is_file():
                continue
            if _file_extension(filepath.name) not in ALLOWED_EXTENSIONS:
                continue

            file_key = str(filepath)
            file_mtime = filepath.stat().st_mtime

            # Skip if we've already seen this file at this mtime
            if seen_files.get(file_key) == file_mtime:
                continue

            # Use metadata mapping when available, fall back to slugify
            asset_key = source_id_to_asset_key.get(
                source_id, slugify(source_id)
            )
            context.log.info(
                f"New file detected: {filepath.name} "
                f"for source {source_id}"
            )

            yield RunRequest(
                run_key=f"{file_key}:{file_mtime}",
                asset_selection=[AssetKey(asset_key)],
                tags={
                    "source_id": source_id,
                    "file_name": filepath.name,
                },
            )

            new_seen[file_key] = file_mtime

    context.update_cursor(json.dumps(new_seen))


# ---------------------------------------------------------------------------
# Vector embedding sensor
# ---------------------------------------------------------------------------

EMBEDDING_SOURCE_TYPES = ("web_scrape", "rss_feed")

EMBEDDING_SENSOR_INTERVAL = 60  # seconds


def _get_recent_completed_runs(
    db_url: str,
    since_timestamp: str,
) -> List[Tuple[str, str, str, str]]:
    """Return ingestion runs completed after *since_timestamp*.

    Each row is ``(run_id, data_source_id, source_type, completed_at)``
    where *source_type* is one of :data:`EMBEDDING_SOURCE_TYPES`.

    Uses a **sync** SQLAlchemy engine because Dagster sensors execute
    in a synchronous context.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(db_url)
    query = text("""
        SELECT ir.id, ir.data_source_id, ds.source_type, ir.completed_at
        FROM ingestion_runs ir
        JOIN data_sources ds ON ds.id = ir.data_source_id
        WHERE ir.status = 'completed'
          AND ir.completed_at > CAST(:since AS TIMESTAMPTZ)
          AND ds.source_type = ANY(CAST(:types AS VARCHAR[]))
        ORDER BY ir.completed_at ASC
    """)

    with engine.connect() as conn:
        rows = conn.execute(
            query,
            {
                "since": since_timestamp,
                "types": list(EMBEDDING_SOURCE_TYPES),
            },
        ).fetchall()

    engine.dispose()
    return [
        (str(r[0]), str(r[1]), r[2], r[3].isoformat())
        for r in rows
    ]


@sensor(
    minimum_interval_seconds=EMBEDDING_SENSOR_INTERVAL,
    default_status=DefaultSensorStatus.STOPPED,
    description=(
        "Watches for completed web-scrape and RSS ingestion runs "
        "and triggers vector embedding for their content."
    ),
)
def vector_embedding_sensor(context: SensorEvaluationContext):
    """Yield a :class:`RunRequest` for each new ingestion run that needs
    vector embedding.

    The cursor stores the ISO-8601 timestamp of the last processed run's
    ``completed_at`` value.  On first evaluation the sensor starts from
    the Unix epoch so all existing runs are picked up.
    """
    db_url = os.environ.get(
        "DAGSTER_INGESTION_DB_URL",
        os.environ.get("DATABASE_URL", ""),
    )

    if not db_url:
        yield SkipReason("No database URL configured (DAGSTER_INGESTION_DB_URL)")
        return

    since = context.cursor or "1970-01-01T00:00:00+00:00"

    try:
        runs = _get_recent_completed_runs(db_url, since)
    except Exception as exc:
        context.log.error(f"Failed to query ingestion runs: {exc}")
        yield SkipReason(f"DB query error: {exc}")
        return

    if not runs:
        yield SkipReason("No new ingestion runs requiring embedding")
        return

    latest_ts = since
    for run_id, source_id, source_type, completed_at in runs:
        context.log.info(
            f"Requesting embedding for ingestion run {run_id} "
            f"(source_type={source_type})"
        )
        yield RunRequest(
            run_key=f"embed_{run_id}_{completed_at}",
            run_config={
                "ingestion_run_id": run_id,
                "data_source_id": source_id,
                "source_type": source_type,
            },
            tags={
                "source_type": source_type,
                "ingestion_run_id": run_id,
            },
        )
        if completed_at > latest_ts:
            latest_ts = completed_at

    context.update_cursor(latest_ts)
