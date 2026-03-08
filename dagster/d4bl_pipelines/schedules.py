"""Dynamic schedule generation from data_sources and keyword_monitors tables."""

from __future__ import annotations

import logging

import sqlalchemy

from d4bl_pipelines.utils import slugify
from dagster import AssetSelection, DefaultScheduleStatus, ScheduleDefinition

logger = logging.getLogger(__name__)

# Backward-compatible alias for tests
_slugify = slugify


def build_source_schedules(
    data_sources: list[dict],
) -> list[ScheduleDefinition]:
    """Build ScheduleDefinitions from data source config dicts.

    Each source with a non-null ``default_schedule`` and ``enabled=True``
    produces one schedule targeting the corresponding asset.
    """
    schedules: list[ScheduleDefinition] = []
    for source in data_sources:
        cron = source.get("default_schedule")
        if not cron:
            continue
        if not source.get("enabled", True):
            continue

        slug = slugify(source["name"])
        schedules.append(
            ScheduleDefinition(
                name=f"schedule_{slug}",
                cron_schedule=cron,
                target=AssetSelection.assets(slug),
                default_status=DefaultScheduleStatus.RUNNING,
            )
        )
    return schedules


def build_monitor_schedules(
    monitors: list[dict],
) -> list[ScheduleDefinition]:
    """Build ScheduleDefinitions from keyword monitor config dicts.

    Each monitor with a non-null ``schedule`` and ``enabled=True``
    produces one schedule targeting a ``keyword_search_<slug>`` asset.
    """
    schedules: list[ScheduleDefinition] = []
    for monitor in monitors:
        cron = monitor.get("schedule")
        if not cron:
            continue
        if not monitor.get("enabled", True):
            continue

        slug = slugify(monitor["name"])
        schedules.append(
            ScheduleDefinition(
                name=f"monitor_{slug}",
                cron_schedule=cron,
                target=AssetSelection.assets(f"keyword_search_{slug}"),
                default_status=DefaultScheduleStatus.RUNNING,
            )
        )
    return schedules


def _to_sync_url(db_url: str) -> str:
    """Convert an async DB URL to a sync one for SQLAlchemy."""
    return db_url.replace("postgresql+asyncpg://", "postgresql://")


def load_schedules_from_db(db_url: str) -> list[ScheduleDefinition]:
    """Load schedule definitions by querying data_sources and keyword_monitors.

    Uses a synchronous SQLAlchemy engine because Dagster repository loading
    is synchronous.  Returns an empty list when the tables do not exist yet.
    """
    sync_url = _to_sync_url(db_url)
    engine = sqlalchemy.create_engine(sync_url)
    try:
        with engine.connect() as conn:
            # --- data_sources ---
            try:
                rows = conn.execute(
                    sqlalchemy.text("SELECT * FROM data_sources")
                )
                data_sources = [dict(r._mapping) for r in rows]
            except Exception:
                logger.info(
                    "data_sources table not found; skipping source schedules"
                )
                data_sources = []

            # --- keyword_monitors ---
            try:
                rows = conn.execute(
                    sqlalchemy.text("SELECT * FROM keyword_monitors")
                )
                monitors = [dict(r._mapping) for r in rows]
            except Exception:
                logger.info(
                    "keyword_monitors table not found; "
                    "skipping monitor schedules"
                )
                monitors = []

        source_schedules = build_source_schedules(data_sources)
        monitor_schedules = build_monitor_schedules(monitors)
        return source_schedules + monitor_schedules
    except Exception:
        logger.warning(
            "Could not load schedules from database", exc_info=True
        )
        return []
    finally:
        engine.dispose()
