"""Data ingestion management endpoints — admin only."""

import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

import aiohttp

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.app.auth import CurrentUser, require_admin
from d4bl.app.schemas import (
    DataOverviewResponse,
    DataSourceCreate,
    DataSourceResponse,
    DataSourceUpdate,
    IngestionRunResponse,
    KeywordMonitorCreate,
    KeywordMonitorResponse,
    KeywordMonitorUpdate,
    LineageGraphNode,
    LineageGraphResponse,
    LineageRecordResponse,
    ReloadResponse,
    RunStatusResponse,
    ConnectionTestResponse,
    TriggerResponse,
)
from d4bl.infra.database import (
    DataLineage,
    DataSource,
    IngestionRun,
    KeywordMonitor,
    get_db,
)
from d4bl.services.dagster_client import DagsterClient, DagsterClientError

logger = logging.getLogger(__name__)

UPLOAD_ROOT = os.environ.get(
    "D4BL_UPLOAD_DIR", "/tmp/d4bl_uploads"
)
ALLOWED_UPLOAD_EXTENSIONS = {"csv", "xlsx", "json"}

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
    # Subquery for latest run per source (avoids N+1)
    latest_run_subq = (
        select(
            IngestionRun.data_source_id,
            func.max(IngestionRun.started_at).label("max_started"),
        )
        .group_by(IngestionRun.data_source_id)
        .subquery()
    )

    result = await db.execute(
        select(DataSource, IngestionRun)
        .outerjoin(
            latest_run_subq,
            DataSource.id == latest_run_subq.c.data_source_id,
        )
        .outerjoin(
            IngestionRun,
            and_(
                IngestionRun.data_source_id
                == latest_run_subq.c.data_source_id,
                IngestionRun.started_at
                == latest_run_subq.c.max_started,
            ),
        )
        .order_by(desc(DataSource.created_at))
    )
    rows = result.all()
    return [_source_response(source, run) for source, run in rows]


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
    if "default_schedule" in body.model_fields_set:
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


@router.get("/runs/{run_id}", response_model=IngestionRunResponse)
async def get_run(
    run_id: uuid.UUID,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get a single ingestion run by ID."""
    result = await db.execute(select(IngestionRun).where(IngestionRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return IngestionRunResponse(**run.to_dict())


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


@router.post(
    "/sources/{source_id}/upload",
    status_code=202,
)
async def upload_file(
    source_id: uuid.UUID,
    file: UploadFile,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Accept a file upload for a data source.

    Validates file type and saves the file to the upload directory
    for later processing by the Dagster file_upload asset.
    """
    # Verify the source exists
    result = await db.execute(
        select(DataSource).where(DataSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    # Sanitize filename - take only the basename, strip path components
    raw_filename = file.filename or "upload"
    safe_name = PurePosixPath(raw_filename).name
    if not safe_name or safe_name.startswith('.'):
        raise HTTPException(status_code=422, detail="Invalid filename")

    # Validate file extension
    ext = Path(safe_name).suffix.lstrip(".").lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported file type: .{ext}. "
                f"Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}"
            ),
        )

    # Create upload directory
    upload_dir = Path(UPLOAD_ROOT) / str(source_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Save file
    dest = upload_dir / safe_name
    contents = await file.read()
    dest.write_bytes(contents)

    return {"status": "uploaded", "filename": safe_name}


# ---------------------------------------------------------------------------
# Dagster integration endpoints
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Convert a source name into a Dagster-compatible asset key."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")


@router.post(
    "/sources/{source_id}/trigger",
    response_model=TriggerResponse,
    status_code=202,
)
async def trigger_source(
    source_id: uuid.UUID,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a Dagster run to materialise a data source's asset."""
    result = await db.execute(
        select(DataSource).where(DataSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    asset_key = _slugify(source.name)

    # Create a pending ingestion run record
    run = IngestionRun(
        data_source_id=source.id,
        status="pending",
        trigger_type="manual",
        triggered_by=user.id,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()  # get the id

    try:
        async with DagsterClient() as client:
            dagster_result = await client.trigger_run(asset_key)
            run.dagster_run_id = dagster_result["run_id"]
            run.status = "running"
    except DagsterClientError as exc:
        logger.error("Dagster trigger failed for source %s: %s", source_id, exc)
        run.status = "failed"
        run.error_detail = str(exc)
        await db.commit()
        raise HTTPException(status_code=502, detail=str(exc))

    await db.commit()
    await db.refresh(run)

    return TriggerResponse(
        run_id=run.dagster_run_id or "",
        ingestion_run_id=str(run.id),
        status="triggered",
    )


@router.get(
    "/sources/{source_id}/status",
    response_model=RunStatusResponse,
)
async def source_run_status(
    source_id: uuid.UUID,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get the status of the latest ingestion run for a data source."""
    # Verify source exists
    src_result = await db.execute(
        select(DataSource).where(DataSource.id == source_id)
    )
    if not src_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Source not found")

    last_run = await _last_run_for_source(db, source_id)
    if not last_run:
        raise HTTPException(
            status_code=404, detail="No runs found for this source"
        )

    dagster_status = None
    start_time = None
    end_time = None

    if last_run.dagster_run_id:
        try:
            async with DagsterClient() as client:
                status_info = await client.get_run_status(
                    last_run.dagster_run_id
                )
                dagster_status = status_info["status"]
                start_time = status_info.get("start_time")
                end_time = status_info.get("end_time")
        except DagsterClientError as exc:
            logger.warning(
                "Could not fetch Dagster status for run %s: %s",
                last_run.dagster_run_id,
                exc,
            )

    return RunStatusResponse(
        ingestion_run_id=str(last_run.id),
        dagster_run_id=last_run.dagster_run_id,
        local_status=last_run.status,
        dagster_status=dagster_status,
        start_time=start_time,
        end_time=end_time,
    )


@router.post("/reload", response_model=ReloadResponse)
async def reload_dagster(
    user: CurrentUser = Depends(require_admin),
):
    """Reload the Dagster repository location."""
    try:
        async with DagsterClient() as client:
            result = await client.reload_repository()
    except DagsterClientError as exc:
        logger.error("Dagster reload failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    return ReloadResponse(**result)


# ---------------------------------------------------------------------------
# Lineage endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/lineage/{table}/{record_id}",
    response_model=list[LineageRecordResponse],
)
async def get_record_lineage(
    table: str,
    record_id: uuid.UUID,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get full provenance chain for a specific record."""
    result = await db.execute(
        select(DataLineage, DataSource.name, DataSource.source_type)
        .join(IngestionRun, DataLineage.ingestion_run_id == IngestionRun.id)
        .join(DataSource, IngestionRun.data_source_id == DataSource.id)
        .where(
            DataLineage.target_table == table,
            DataLineage.record_id == record_id,
        )
        .order_by(desc(DataLineage.retrieved_at))
    )
    rows = result.all()

    return [
        LineageRecordResponse(
            **lineage.to_dict(),
            data_source_name=source_name,
            data_source_type=source_type,
        )
        for lineage, source_name, source_type in rows
    ]


@router.get("/lineage/graph", response_model=LineageGraphResponse)
async def get_lineage_graph(
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get the asset dependency graph: one node per data source with run stats."""
    # Subquery: latest run per source
    latest_run_subq = (
        select(
            IngestionRun.data_source_id,
            func.max(IngestionRun.started_at).label("max_started"),
        )
        .group_by(IngestionRun.data_source_id)
        .subquery()
    )

    # Subquery: count of lineage records per source
    lineage_counts = (
        select(
            IngestionRun.data_source_id,
            func.count(DataLineage.id).label("record_count"),
        )
        .join(DataLineage, DataLineage.ingestion_run_id == IngestionRun.id)
        .group_by(IngestionRun.data_source_id)
        .subquery()
    )

    result = await db.execute(
        select(
            DataSource,
            IngestionRun.status,
            IngestionRun.started_at,
            lineage_counts.c.record_count,
        )
        .outerjoin(
            latest_run_subq,
            DataSource.id == latest_run_subq.c.data_source_id,
        )
        .outerjoin(
            IngestionRun,
            and_(
                IngestionRun.data_source_id == latest_run_subq.c.data_source_id,
                IngestionRun.started_at == latest_run_subq.c.max_started,
            ),
        )
        .outerjoin(
            lineage_counts,
            DataSource.id == lineage_counts.c.data_source_id,
        )
        .order_by(DataSource.name)
    )
    rows = result.all()

    nodes = [
        LineageGraphNode(
            asset_key=_slugify(source.name),
            source_name=source.name,
            source_type=source.source_type,
            last_run_status=run_status,
            last_run_at=run_started.isoformat() if run_started else None,
            record_count=record_count or 0,
        )
        for source, run_status, run_started, record_count in rows
    ]

    return LineageGraphResponse(nodes=nodes)


# ---------------------------------------------------------------------------
# Test connection endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/sources/{source_id}/test",
    response_model=ConnectionTestResponse,
)
async def test_source_connection(
    source_id: uuid.UUID,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Validate a source's configuration without ingesting data."""
    result = await db.execute(
        select(DataSource).where(DataSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    try:
        test_result = await _test_connection(source.source_type, source.config)
        return test_result
    except Exception as exc:
        logger.error("Connection test failed for source %s: %s", source_id, exc)
        return ConnectionTestResponse(
            success=False,
            message=f"Connection test failed: {exc}",
        )


async def _test_connection(
    source_type: str, config: dict
) -> ConnectionTestResponse:
    """Run a lightweight connectivity check based on source type."""

    if source_type == "api":
        url = config.get("url") or config.get("base_url")
        if not url:
            return ConnectionTestResponse(
                success=False, message="No URL configured"
            )
        async with aiohttp.ClientSession() as session:
            async with session.head(
                url, timeout=aiohttp.ClientTimeout(total=10), allow_redirects=True
            ) as resp:
                return ConnectionTestResponse(
                    success=resp.status < 400,
                    message=f"HTTP {resp.status}",
                    details={"status_code": resp.status},
                )

    elif source_type == "web_scrape":
        url = config.get("url")
        if not url:
            return ConnectionTestResponse(
                success=False, message="No URL configured"
            )
        async with aiohttp.ClientSession() as session:
            async with session.head(
                url, timeout=aiohttp.ClientTimeout(total=10), allow_redirects=True
            ) as resp:
                return ConnectionTestResponse(
                    success=resp.status < 400,
                    message=f"URL reachable (HTTP {resp.status})",
                    details={"status_code": resp.status},
                )

    elif source_type == "rss_feed":
        url = config.get("feed_url") or config.get("url")
        if not url:
            return ConnectionTestResponse(
                success=False, message="No feed URL configured"
            )
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status >= 400:
                    return ConnectionTestResponse(
                        success=False,
                        message=f"Feed returned HTTP {resp.status}",
                    )
                text = await resp.text()
                is_xml = "<rss" in text[:500] or "<feed" in text[:500]
                return ConnectionTestResponse(
                    success=is_xml,
                    message="Valid RSS/Atom feed" if is_xml else "Response is not valid RSS/Atom XML",
                )

    elif source_type == "database":
        dsn = config.get("connection_string") or config.get("dsn")
        if not dsn:
            return ConnectionTestResponse(
                success=False, message="No connection string configured"
            )
        from sqlalchemy.ext.asyncio import create_async_engine as _create_engine

        test_engine = _create_engine(dsn, pool_pre_ping=True)
        try:
            async with test_engine.connect() as conn:
                await conn.execute(select(func.now()))
            return ConnectionTestResponse(
                success=True, message="Database connection successful"
            )
        finally:
            await test_engine.dispose()

    elif source_type == "mcp":
        server_url = config.get("server_url")
        if not server_url:
            return ConnectionTestResponse(
                success=False, message="No MCP server URL configured"
            )
        async with aiohttp.ClientSession() as session:
            async with session.get(
                server_url, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                return ConnectionTestResponse(
                    success=resp.status < 400,
                    message=f"MCP server reachable (HTTP {resp.status})",
                    details={"status_code": resp.status},
                )

    elif source_type == "file_upload":
        upload_dir = Path(UPLOAD_ROOT) / str(config.get("source_id", ""))
        if upload_dir.exists() and any(upload_dir.iterdir()):
            return ConnectionTestResponse(
                success=True,
                message=f"Upload directory exists with {sum(1 for _ in upload_dir.iterdir())} file(s)",
            )
        return ConnectionTestResponse(
            success=False, message="No files found in upload directory"
        )

    return ConnectionTestResponse(
        success=False, message=f"Unknown source type: {source_type}"
    )


# ---------------------------------------------------------------------------
# Keyword monitor CRUD endpoints
# ---------------------------------------------------------------------------


@router.get("/monitors", response_model=list[KeywordMonitorResponse])
async def list_monitors(
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all keyword monitors."""
    result = await db.execute(
        select(KeywordMonitor).order_by(desc(KeywordMonitor.created_at))
    )
    monitors = result.scalars().all()
    return [KeywordMonitorResponse(**m.to_dict()) for m in monitors]


@router.post(
    "/monitors", response_model=KeywordMonitorResponse, status_code=201
)
async def create_monitor(
    body: KeywordMonitorCreate,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new keyword monitor."""
    monitor = KeywordMonitor(
        name=body.name,
        keywords=body.keywords,
        source_ids=body.source_ids,
        schedule=body.schedule,
        enabled=body.enabled,
        created_by=user.id,
    )
    db.add(monitor)
    await db.commit()
    await db.refresh(monitor)
    return KeywordMonitorResponse(**monitor.to_dict())


@router.get(
    "/monitors/{monitor_id}", response_model=KeywordMonitorResponse
)
async def get_monitor(
    monitor_id: uuid.UUID,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a single keyword monitor by ID."""
    result = await db.execute(
        select(KeywordMonitor).where(KeywordMonitor.id == monitor_id)
    )
    monitor = result.scalar_one_or_none()
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return KeywordMonitorResponse(**monitor.to_dict())


@router.patch(
    "/monitors/{monitor_id}", response_model=KeywordMonitorResponse
)
async def update_monitor(
    monitor_id: uuid.UUID,
    body: KeywordMonitorUpdate,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update fields on an existing keyword monitor."""
    result = await db.execute(
        select(KeywordMonitor).where(KeywordMonitor.id == monitor_id)
    )
    monitor = result.scalar_one_or_none()
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")

    if body.name is not None:
        monitor.name = body.name
    if body.keywords is not None:
        monitor.keywords = body.keywords
    if body.source_ids is not None:
        monitor.source_ids = body.source_ids
    if "schedule" in body.model_fields_set:
        monitor.schedule = body.schedule
    if body.enabled is not None:
        monitor.enabled = body.enabled

    await db.commit()
    await db.refresh(monitor)
    return KeywordMonitorResponse(**monitor.to_dict())


@router.delete("/monitors/{monitor_id}", status_code=204)
async def delete_monitor(
    monitor_id: uuid.UUID,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a keyword monitor."""
    result = await db.execute(
        select(KeywordMonitor).where(KeywordMonitor.id == monitor_id)
    )
    monitor = result.scalar_one_or_none()
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")

    await db.delete(monitor)
    await db.commit()
