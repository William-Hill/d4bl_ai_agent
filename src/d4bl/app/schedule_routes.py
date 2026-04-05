"""Admin API routes for managing ingestion schedules."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.app.auth import CurrentUser, require_admin
from d4bl.infra.database import (
    IngestionRun,
    IngestionSchedule,
    async_session_maker,
    get_db,
)
from d4bl.services.ingestion_runner import resolve_source, run_ingestion_task

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])

# Strong references to prevent background tasks from being GC'd.
_background_tasks: set = set()


def _log_task_exception(task: asyncio.Task) -> None:
    """Log unhandled exceptions from background tasks."""
    _background_tasks.discard(task)
    if not task.cancelled() and task.exception():
        logger.error("Background task failed: %s", task.exception(), exc_info=task.exception())


@router.get("/api/admin/schedules")
async def list_schedules(
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all ingestion schedules."""
    result = await db.execute(select(IngestionSchedule))
    schedules = result.scalars().all()
    return [s.to_dict() for s in schedules]


@router.post("/api/admin/schedules")
async def create_or_update_schedule(
    body: dict = Body(...),
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create or update an ingestion schedule.

    Body: {"source_key": str, "cron_expression": str, "enabled": bool}
    """
    source_key = body.get("source_key")
    cron_expression = body.get("cron_expression")
    enabled = body.get("enabled", True)

    if not source_key or not cron_expression:
        raise HTTPException(
            status_code=422,
            detail="source_key and cron_expression are required",
        )

    try:
        CronTrigger.from_crontab(cron_expression)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Check for existing schedule with this source_key
    result = await db.execute(
        select(IngestionSchedule).where(IngestionSchedule.source_key == source_key)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.cron_expression = cron_expression
        existing.enabled = enabled
        existing.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(existing)
        schedule = existing
    else:
        schedule = IngestionSchedule(
            source_key=source_key,
            cron_expression=cron_expression,
            enabled=enabled,
        )
        db.add(schedule)
        await db.commit()
        await db.refresh(schedule)

    return {
        "id": str(schedule.id),
        "source_key": schedule.source_key,
        "cron_expression": schedule.cron_expression,
        "enabled": schedule.enabled,
    }


@router.delete("/api/admin/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: UUID,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete an ingestion schedule."""
    result = await db.execute(select(IngestionSchedule).where(IngestionSchedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    await db.delete(schedule)
    await db.commit()
    return {"status": "deleted", "id": str(schedule_id)}


@router.post("/api/admin/schedules/{schedule_id}/run")
async def trigger_schedule(
    schedule_id: UUID,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Trigger an ingestion schedule immediately."""
    result = await db.execute(select(IngestionSchedule).where(IngestionSchedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    module_name = resolve_source(schedule.source_key)
    if not module_name:
        raise HTTPException(
            status_code=422,
            detail=f"No ingestion script for source: {schedule.source_key}",
        )

    run_id = uuid4()
    run = IngestionRun(
        id=run_id,
        status="pending",
        trigger_type="manual",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.commit()

    task = asyncio.create_task(run_ingestion_task(run_id, module_name, async_session_maker))
    _background_tasks.add(task)
    task.add_done_callback(_log_task_exception)

    return {
        "status": "triggered",
        "source_key": schedule.source_key,
        "run_id": str(run_id),
    }
