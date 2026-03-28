"""Admin API routes for managing ingestion schedules."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.app.auth import CurrentUser, require_admin
from d4bl.infra.database import IngestionRun, IngestionSchedule, get_db
from d4bl.services.scheduler import parse_cron

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


@router.get("/api/admin/schedules")
async def list_schedules(
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all ingestion schedules."""
    result = await db.execute(select(IngestionSchedule))
    schedules = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "source_key": s.source_key,
            "cron_expression": s.cron_expression,
            "enabled": s.enabled,
            "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
            "last_status": s.last_status,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in schedules
    ]


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

    # Validate cron expression
    try:
        parse_cron(cron_expression)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Check for existing schedule with this source_key
    result = await db.execute(
        select(IngestionSchedule).where(
            IngestionSchedule.source_key == source_key
        )
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
    result = await db.execute(
        select(IngestionSchedule).where(IngestionSchedule.id == schedule_id)
    )
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
    result = await db.execute(
        select(IngestionSchedule).where(IngestionSchedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    from d4bl.services.ingestion_runner import resolve_source

    module_name = resolve_source(schedule.source_key)
    if not module_name:
        raise HTTPException(
            status_code=422,
            detail=f"No ingestion script for source: {schedule.source_key}",
        )

    from d4bl.infra.database import async_session_maker
    from d4bl.services.ingestion_runner import run_ingestion_task

    run_id = uuid4()
    run = IngestionRun(
        id=run_id,
        status="pending",
        trigger_type="scheduled",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.commit()

    asyncio.create_task(
        run_ingestion_task(run_id, module_name, async_session_maker)
    )

    return {
        "status": "triggered",
        "source_key": schedule.source_key,
        "run_id": str(run_id),
    }
