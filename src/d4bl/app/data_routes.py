"""Data ingestion management endpoints — admin only."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from d4bl.app.auth import require_admin
from d4bl.app.schemas import (
    DataSourceCreate,
    DataSourceResponse,
    DataSourceUpdate,
    IngestionRunResponse,
)
from d4bl.infra.database import DataSource, IngestionRun, get_db

router = APIRouter(prefix="/api/data", tags=["data"])


@router.get("/sources", response_model=list[DataSourceResponse])
async def list_sources(
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # Subquery: latest started_at per data_source_id
    latest_sub = (
        select(
            IngestionRun.data_source_id,
            func.max(IngestionRun.started_at).label("max_started"),
        )
        .group_by(IngestionRun.data_source_id)
        .subquery()
    )

    lr = aliased(IngestionRun)
    query = (
        select(DataSource, lr)
        .outerjoin(
            latest_sub,
            DataSource.id == latest_sub.c.data_source_id,
        )
        .outerjoin(
            lr,
            (lr.data_source_id == latest_sub.c.data_source_id)
            & (lr.started_at == latest_sub.c.max_started),
        )
        .order_by(desc(DataSource.created_at))
    )
    result = await db.execute(query)
    rows = result.all()

    responses = []
    for source, last_run in rows:
        resp = DataSourceResponse(
            **source.to_dict(),
            last_run_status=last_run.status if last_run else None,
            last_run_at=(
                last_run.started_at.isoformat()
                if last_run and last_run.started_at
                else None
            ),
        )
        responses.append(resp)

    return responses


@router.post("/sources", response_model=DataSourceResponse, status_code=201)
async def create_source(
    body: DataSourceCreate,
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    source = DataSource(
        name=body.name,
        source_type=body.source_type,
        config=body.config,
        default_schedule=body.default_schedule,
        enabled=body.enabled,
        created_by=user.id,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return DataSourceResponse(**source.to_dict())


@router.get("/sources/{source_id}", response_model=DataSourceResponse)
async def get_source(
    source_id: uuid.UUID,
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DataSource).where(DataSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    last_run_result = await db.execute(
        select(IngestionRun)
        .where(IngestionRun.data_source_id == source.id)
        .order_by(desc(IngestionRun.started_at))
        .limit(1)
    )
    last_run = last_run_result.scalar_one_or_none()

    return DataSourceResponse(
        **source.to_dict(),
        last_run_status=last_run.status if last_run else None,
        last_run_at=(
            last_run.started_at.isoformat()
            if last_run and last_run.started_at
            else None
        ),
    )


@router.patch("/sources/{source_id}", response_model=DataSourceResponse)
async def update_source(
    source_id: uuid.UUID,
    body: DataSourceUpdate,
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DataSource).where(DataSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    if body.name is not None:
        source.name = body.name
    if body.config is not None:
        source.config = body.config
    if body.default_schedule is not None:
        source.default_schedule = body.default_schedule
    if body.enabled is not None:
        source.enabled = body.enabled

    await db.commit()
    await db.refresh(source)

    last_run_result = await db.execute(
        select(IngestionRun)
        .where(IngestionRun.data_source_id == source.id)
        .order_by(desc(IngestionRun.started_at))
        .limit(1)
    )
    last_run = last_run_result.scalar_one_or_none()

    return DataSourceResponse(
        **source.to_dict(),
        last_run_status=last_run.status if last_run else None,
        last_run_at=(
            last_run.started_at.isoformat()
            if last_run and last_run.started_at
            else None
        ),
    )


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(
    source_id: uuid.UUID,
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DataSource).where(DataSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    await db.delete(source)
    await db.commit()


@router.get("/runs", response_model=list[IngestionRunResponse])
async def list_runs(
    source_id: uuid.UUID | None = None,
    status: str | None = None,
    limit: int = 20,
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if not 1 <= limit <= 100:
        raise HTTPException(
            status_code=422, detail="limit must be between 1 and 100"
        )

    query = (
        select(IngestionRun).order_by(desc(IngestionRun.started_at)).limit(limit)
    )
    if source_id:
        query = query.where(IngestionRun.data_source_id == source_id)
    if status:
        query = query.where(IngestionRun.status == status)

    result = await db.execute(query)
    runs = result.scalars().all()
    return [IngestionRunResponse(**r.to_dict()) for r in runs]


@router.get("/overview")
async def data_overview(
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    total = await db.execute(select(func.count(DataSource.id)))
    enabled = await db.execute(
        select(func.count(DataSource.id)).where(DataSource.enabled.is_(True))
    )
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_failures = await db.execute(
        select(func.count(IngestionRun.id)).where(
            IngestionRun.status == "failed",
            IngestionRun.started_at >= seven_days_ago,
        )
    )

    return {
        "total_sources": total.scalar_one(),
        "enabled_sources": enabled.scalar_one(),
        "recent_failures": recent_failures.scalar_one(),
    }
