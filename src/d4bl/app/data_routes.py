"""Data ingestion management endpoints — admin only."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.app.auth import CurrentUser, require_admin
from d4bl.app.schemas import (
    DataOverviewResponse,
    DataSourceCreate,
    DataSourceResponse,
    DataSourceUpdate,
    IngestionRunResponse,
)
from d4bl.infra.database import DataSource, IngestionRun, get_db

router = APIRouter(prefix="/api/data", tags=["data"])


async def _last_run_for_source(
    db: AsyncSession, source_id: uuid.UUID
) -> IngestionRun | None:
    """Return the most recent ingestion run for a given data source."""
    result = await db.execute(
        select(IngestionRun)
        .where(IngestionRun.data_source_id == source_id)
        .order_by(desc(IngestionRun.started_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


def _source_response(
    source: DataSource, last_run: IngestionRun | None
) -> DataSourceResponse:
    """Build a DataSourceResponse from a source and its optional last run."""
    return DataSourceResponse(
        **source.to_dict(),
        last_run_status=last_run.status if last_run else None,
        last_run_at=(
            last_run.started_at.isoformat()
            if last_run and last_run.started_at
            else None
        ),
    )


@router.get("/sources", response_model=list[DataSourceResponse])
async def list_sources(
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all data sources with their latest ingestion run status."""
    result = await db.execute(
        select(DataSource).order_by(desc(DataSource.created_at))
    )
    sources = result.scalars().all()

    responses = []
    for source in sources:
        last_run = await _last_run_for_source(db, source.id)
        responses.append(_source_response(source, last_run))

    return responses


@router.post("/sources", response_model=DataSourceResponse, status_code=201)
async def create_source(
    body: DataSourceCreate,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new data source configuration."""
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
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a single data source by ID."""
    result = await db.execute(
        select(DataSource).where(DataSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    last_run = await _last_run_for_source(db, source.id)
    return _source_response(source, last_run)


@router.patch("/sources/{source_id}", response_model=DataSourceResponse)
async def update_source(
    source_id: uuid.UUID,
    body: DataSourceUpdate,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update fields on an existing data source."""
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

    last_run = await _last_run_for_source(db, source.id)
    return _source_response(source, last_run)


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(
    source_id: uuid.UUID,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a data source and its associated runs."""
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
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List ingestion runs, optionally filtered by source or status."""
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


@router.get("/overview", response_model=DataOverviewResponse)
async def data_overview(
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return high-level statistics about data sources and recent runs."""
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
