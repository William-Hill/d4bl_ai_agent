"""APScheduler-based ingestion scheduling service.

Manages cron schedules for automated data ingestion. Schedules are stored
in the ingestion_schedules DB table and loaded at application startup.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.infra.database import IngestionSchedule

logger = logging.getLogger(__name__)

# Default schedules seeded on first startup when table is empty.
DEFAULT_SCHEDULES: dict[str, str] = {
    "cdc": "0 0 15 1 *",
    "census_acs": "0 0 20 1 *",
    "census_decennial": "0 0 1 4 *",
    "epa": "0 0 1 2 *",
    "bls": "0 6 10 * *",
    "fbi": "0 0 1 10 *",
    "openstates": "0 6 * * 1",
    "hud": "0 0 1 3 *",
    "usda": "0 0 1 3 *",
    "doe": "0 0 1 6 *",
    "bjs": "0 0 1 11 *",
    "police_violence": "0 6 * * 1",
}


def parse_cron(expression: str) -> CronTrigger:
    """Validate and parse a 5-field cron expression into a CronTrigger.

    Delegates to APScheduler's built-in crontab parser.
    Raises ValueError for invalid expressions.
    """
    return CronTrigger.from_crontab(expression)


def build_scheduler() -> AsyncIOScheduler:
    """Create a new AsyncIOScheduler (not yet started)."""
    return AsyncIOScheduler(timezone="UTC")


async def seed_default_schedules(session: AsyncSession) -> int:
    """Insert default schedules if the table is empty. Returns count seeded."""
    result = await session.execute(
        select(IngestionSchedule).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        return 0

    count = 0
    for source_key, cron_expr in DEFAULT_SCHEDULES.items():
        session.add(IngestionSchedule(
            source_key=source_key,
            cron_expression=cron_expr,
            enabled=True,
        ))
        count += 1
    await session.commit()
    logger.info("Seeded %d default ingestion schedules", count)
    return count


async def load_and_register_schedules(
    scheduler: AsyncIOScheduler,
    session: AsyncSession,
    run_job_func,
) -> int:
    """Load enabled schedules from DB and register them with the scheduler.

    Args:
        scheduler: The APScheduler instance.
        session: An async DB session.
        run_job_func: Async callable(source_key: str) invoked when a job fires.

    Returns:
        Number of schedules registered.
    """
    result = await session.execute(
        select(IngestionSchedule).where(IngestionSchedule.enabled.is_(True))
    )
    schedules = result.scalars().all()

    registered = 0
    for sched in schedules:
        try:
            trigger = parse_cron(sched.cron_expression)
            scheduler.add_job(
                run_job_func,
                trigger=trigger,
                args=[sched.source_key],
                id=f"ingest_{sched.source_key}",
                replace_existing=True,
                name=f"Ingest {sched.source_key}",
            )
            logger.info(
                "Registered schedule: %s [%s]",
                sched.source_key,
                sched.cron_expression,
            )
            registered += 1
        except Exception:
            logger.exception(
                "Failed to register schedule for %s", sched.source_key
            )

    return registered


async def update_schedule_status(
    session: AsyncSession,
    source_key: str,
    status: str,
) -> None:
    """Update last_run_at and last_status for a schedule."""
    result = await session.execute(
        select(IngestionSchedule).where(
            IngestionSchedule.source_key == source_key
        )
    )
    sched = result.scalar_one_or_none()
    if sched:
        sched.last_run_at = datetime.now(timezone.utc)
        sched.last_status = status
        await session.commit()
