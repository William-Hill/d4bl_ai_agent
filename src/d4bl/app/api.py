"""
FastAPI backend for D4BL AI Agent UI
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import Body, Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import String, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.app.auth import CurrentUser, get_current_user, require_admin
from d4bl.app.data_routes import router as data_router
from d4bl.app.explore_helpers import compute_national_avg, distinct_values
from d4bl.app.schemas import (
    EvaluationResultItem,
    ExploreResponse,
    ExploreRow,
    IndicatorItem,
    InviteRequest,
    JobHistoryResponse,
    JobStatus,
    PolicyBillItem,
    QueryRequest,
    QueryResponse,
    QuerySourceItem,
    ResearchRequest,
    ResearchResponse,
    StateSummaryItem,
    UpdateRoleRequest,
    UserProfile,
)
from d4bl.app.websocket_manager import get_job_logs, register_connection, remove_connection
from d4bl.infra import database as _db_mod
from d4bl.infra.database import (
    BlsLaborStatistic,
    CdcHealthOutcome,
    CensusIndicator,
    DoeCivilRights,
    EpaEnvironmentalJustice,
    EvaluationResult,
    FbiCrimeStat,
    HudFairHousing,
    PoliceViolenceIncident,
    PolicyBill,
    ResearchJob,
    UsdaFoodAccess,
    close_db,
    create_tables,
    get_db,
    init_db,
)
from d4bl.infra.vector_store import get_vector_store
from d4bl.llm import get_available_models
from d4bl.query.engine import QueryEngine
from d4bl.services.research_runner import run_research_job
from d4bl.settings import get_settings

logger = logging.getLogger(__name__)

ABBREV_TO_FIPS: dict[str, str] = {v: k for k, v in {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY",
}.items()}

# Reverse lookup: FIPS -> abbreviation
FIPS_TO_ABBREV: dict[str, str] = {v: k for k, v in ABBREV_TO_FIPS.items()}

# FIPS -> full state name (for endpoints where model lacks state_name)
FIPS_TO_NAME: dict[str, str] = {
    "01": "Alabama", "02": "Alaska", "04": "Arizona", "05": "Arkansas",
    "06": "California", "08": "Colorado", "09": "Connecticut", "10": "Delaware",
    "11": "District of Columbia", "12": "Florida", "13": "Georgia", "15": "Hawaii",
    "16": "Idaho", "17": "Illinois", "18": "Indiana", "19": "Iowa",
    "20": "Kansas", "21": "Kentucky", "22": "Louisiana", "23": "Maine",
    "24": "Maryland", "25": "Massachusetts", "26": "Michigan", "27": "Minnesota",
    "28": "Mississippi", "29": "Missouri", "30": "Montana", "31": "Nebraska",
    "32": "Nevada", "33": "New Hampshire", "34": "New Jersey", "35": "New Mexico",
    "36": "New York", "37": "North Carolina", "38": "North Dakota", "39": "Ohio",
    "40": "Oklahoma", "41": "Oregon", "42": "Pennsylvania", "44": "Rhode Island",
    "45": "South Carolina", "46": "South Dakota", "47": "Tennessee", "48": "Texas",
    "49": "Utah", "50": "Vermont", "51": "Virginia", "53": "Washington",
    "54": "West Virginia", "55": "Wisconsin", "56": "Wyoming",
}


def parse_job_uuid(job_id: str) -> UUID:
    """Parse a string job ID into a UUID, raising HTTP 400 on failure."""
    try:
        return UUID(job_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid job ID format")


async def fetch_research_job(db: AsyncSession, job_uuid: UUID) -> ResearchJob:
    """Load a ResearchJob by UUID, raising HTTP 404 if not found."""
    result = await db.execute(
        select(ResearchJob).where(ResearchJob.job_id == job_uuid)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


_background_tasks: set = set()


def _log_task_exception(task: asyncio.Task) -> None:
    """Log unhandled exceptions from background tasks."""
    _background_tasks.discard(task)
    if not task.cancelled() and task.exception():
        logger.error("Background task failed: %s", task.exception(), exc_info=task.exception())


@lru_cache(maxsize=1)
def get_query_engine() -> QueryEngine:
    """Return a cached QueryEngine singleton for NL query processing."""
    return QueryEngine()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown logic."""
    # --- Startup ---
    try:
        init_db()
        await create_tables()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.warning("Database initialization failed: %s", e)
        logger.warning("The application will continue but jobs won't be persisted.")

    # Check Langfuse availability early and unset OTLP endpoint if not available
    try:
        from d4bl.observability.langfuse import (
            check_langfuse_service_available,
            resolve_langfuse_host,
        )

        settings = get_settings()
        langfuse_otel_host = resolve_langfuse_host(
            settings.langfuse_otel_host or settings.langfuse_host,
            settings.is_docker,
        )

        if not check_langfuse_service_available(langfuse_otel_host):
            logger.warning("Langfuse service not available. Unsetting OTLP endpoint.")
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            os.environ.pop("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", None)
        else:
            logger.info("Langfuse service is available")
    except Exception as e:
        logger.warning("Could not check Langfuse availability: %s", e)

    yield  # --- App runs here ---

    # --- Shutdown ---
    await close_db()


_settings = get_settings()

app = FastAPI(title="D4BL AI Agent API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_settings.cors_allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data_router)

# ---------------------------------------------------------------------------
# Admin ingestion: track background subprocess jobs
# ---------------------------------------------------------------------------
VALID_INGEST_SOURCES = frozenset(
    ["cdc", "census", "epa", "fbi", "bls", "hud", "usda", "doe", "police", "openstates"]
)

_MAX_INGESTION_JOBS = 50
_ingestion_jobs: dict[str, dict] = {}  # job_id -> {process, sources, started_at}


def _evict_finished_jobs() -> None:
    """Remove completed jobs to prevent unbounded growth."""
    to_remove = [
        jid for jid, entry in _ingestion_jobs.items()
        if entry["process"].poll() is not None
    ]
    for jid in to_remove:
        _ingestion_jobs.pop(jid, None)


@app.get("/")
async def read_root():
    """Root endpoint for health/status."""
    return {"status": "ok", "message": "D4BL AI Agent API"}


@app.get("/api/models")
async def list_models():
    """Return available LLM models."""
    return get_available_models()


@app.post("/api/research", response_model=ResearchResponse)
async def create_research(
    request: ResearchRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new research job"""
    try:
        # Create job in database
        job = ResearchJob(
            query=request.query,
            summary_format=request.summary_format,
            status="pending",
            progress="Job created, waiting to start...",
            user_id=user.id,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        job_id = str(job.job_id)

        # Start the research job in the background (WebSocket will connect separately)
        # Store the task reference to prevent GC from cancelling it prematurely
        task = asyncio.create_task(run_research_job(
            job_id,
            request.query,
            request.summary_format,
            request.selected_agents,
            request.model,
        ))
        _background_tasks.add(task)
        task.add_done_callback(_log_task_exception)

        return ResearchResponse(
            job_id=job_id,
            status="pending",
            message="Research job created successfully"
        )
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error("Error in create_research: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error creating research job")


@app.get("/api/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(
    job_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the status of a research job"""
    job_uuid = parse_job_uuid(job_id)
    job = await fetch_research_job(db, job_uuid)
    if not user.is_admin and job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatus(**job.to_dict())


@app.get("/api/jobs", response_model=JobHistoryResponse)
async def get_job_history(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated job history"""
    try:
        # Build shared filters
        filters = []
        if status:
            filters.append(ResearchJob.status == status)
        if not user.is_admin:
            filters.append(ResearchJob.user_id == user.id)

        query = select(ResearchJob)
        count_query = select(func.count(ResearchJob.job_id))
        for f in filters:
            query = query.where(f)
            count_query = count_query.where(f)

        query = query.order_by(desc(ResearchJob.created_at))

        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        # Execute query
        result = await db.execute(query)
        jobs = result.scalars().all()

        return JobHistoryResponse(
            jobs=[JobStatus(**job.to_dict()) for job in jobs],
            total=total,
            page=page,
            page_size=page_size
        )
    except Exception as e:
        logger.error("Error fetching job history: %s", e)
        raise HTTPException(status_code=500, detail="Error fetching job history")


@app.get("/api/evaluations", response_model=list[EvaluationResultItem])
async def get_evaluations(
    trace_id: str | None = None,
    job_id: str | None = None,  # job_id maps to trace_id in Phoenix
    span_id: str | None = None,
    eval_name: str | None = None,
    limit: int = 100,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return recent evaluation results for display in the UI."""
    limit = max(1, min(limit, 500))
    query = select(EvaluationResult).order_by(desc(EvaluationResult.created_at)).limit(limit)

    # Filter by job_id if provided (preferred), otherwise by trace_id
    if job_id:
        try:
            job_uuid = UUID(job_id)
            query = query.where(EvaluationResult.job_id == job_uuid)
        except (ValueError, TypeError):
            # If job_id is not a valid UUID, try as trace_id
            query = query.where(EvaluationResult.trace_id == job_id)
    elif trace_id:
        query = query.where(EvaluationResult.trace_id == trace_id)
    if span_id:
        query = query.where(EvaluationResult.span_id == span_id)
    if eval_name:
        query = query.where(EvaluationResult.eval_name == eval_name)

    result = await db.execute(query)
    rows = result.scalars().all()
    return [EvaluationResultItem(**row.to_dict()) for row in rows]


@app.websocket("/ws/{job_id}")
async def websocket_endpoint(
    websocket: WebSocket, job_id: str, token: str | None = None
):
    """WebSocket endpoint for real-time progress updates"""
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return
    # Validate JWT manually (can't use Depends in WebSocket easily)
    from d4bl.app.auth import decode_supabase_jwt
    settings = get_settings()
    try:
        payload = decode_supabase_jwt(token, settings)
    except Exception:
        await websocket.close(code=1008, reason="Invalid token")
        return

    # Verify job ownership
    user_id = payload.get("sub")
    if _db_mod.async_session_maker is None:
        init_db()
    try:
        async with _db_mod.async_session_maker() as db:
            role_result = await db.execute(
                text("SELECT role FROM profiles WHERE id = CAST(:uid AS uuid)"),
                {"uid": user_id},
            )
            role = role_result.scalar_one_or_none() or "user"

            if role != "admin":
                job_result = await db.execute(
                    select(ResearchJob).where(ResearchJob.job_id == UUID(job_id))
                )
                job_obj = job_result.scalar_one_or_none()
                if not job_obj or str(job_obj.user_id or "") != user_id:
                    await websocket.close(code=1008, reason="Access denied")
                    return
    except Exception as ownership_err:
        logger.warning("Could not verify job ownership: %s", ownership_err)
        await websocket.close(code=1008, reason="Access denied")
        return

    await websocket.accept()
    register_connection(job_id, websocket)

    try:
        # Send current status if job exists (in case job already completed)
        # Try to get from database first
        try:
            job_uuid = UUID(job_id)
            if _db_mod.async_session_maker is None:
                init_db()
            async with _db_mod.async_session_maker() as db:
                result_query = select(ResearchJob).where(ResearchJob.job_id == job_uuid)
                result_obj = await db.execute(result_query)
                job = result_obj.scalar_one_or_none()

                if job:
                    job_dict = job.to_dict()
                    if job.status == "completed":
                        await websocket.send_json({
                            "type": "complete",
                            "job_id": job_id,
                            "status": "completed",
                            "result": job_dict.get("result")
                        })
                    elif job.status == "error":
                        await websocket.send_json({
                            "type": "error",
                            "job_id": job_id,
                            "status": "error",
                            "error": job_dict.get("error")
                        })
                    else:
                        await websocket.send_json({
                            "type": "status",
                            "job_id": job_id,
                            "status": job.status,
                            "progress": job_dict.get("progress"),
                            "logs": job_dict.get("logs") or get_job_logs(job_id)
                        })
        except Exception as db_error:
            logger.error("Error fetching job from database: %s", db_error)
            # Fallback to in-memory logs if available
            fallback_logs = get_job_logs(job_id)
            if fallback_logs:
                await websocket.send_json({
                    "type": "status",
                    "job_id": job_id,
                    "status": "unknown",
                    "logs": fallback_logs
                })

        # Keep connection alive and handle messages
        while True:
            try:
                data = await websocket.receive_text()
                # Echo back or handle client messages if needed
                await websocket.send_json({"type": "pong", "data": data})
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket error: %s", e)
    finally:
        remove_connection(job_id)


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.post("/api/vector/search")
async def search_similar_content(
    query: str = Body(..., embed=True, description="Text query to search for"),
    job_id: str | None = Body(None, embed=True, description="Optional job ID to filter results"),
    limit: int = Body(10, embed=True, ge=1, le=50, description="Maximum number of results"),
    similarity_threshold: float = Body(0.7, embed=True, ge=0.0, le=1.0, description="Minimum cosine similarity score"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Search for similar scraped content using vector similarity.
    
    Request body:
    - query (required): Text query to search for
    - job_id (optional): Job ID to filter results to a specific research job
    - limit (optional, default: 10): Maximum number of results (1-50)
    - similarity_threshold (optional, default: 0.7): Minimum cosine similarity score (0-1)
    """
    try:
        if not query or not query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")

        job_uuid = parse_job_uuid(job_id) if job_id else None

        vector_store = get_vector_store()
        results = await vector_store.search_similar(
            db=db,
            query_text=query,
            job_id=job_uuid,
            limit=limit,
            similarity_threshold=similarity_threshold,
        )

        return {
            "query": query,
            "job_id": job_id,
            "results": results,
            "count": len(results),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error searching vector database: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error searching vector database")


@app.get("/api/vector/job/{job_id}")
async def get_scraped_content_by_job(
    job_id: str,
    limit: int | None = None,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all scraped content stored in vector database for a specific job.
    
    Args:
        job_id: Research job ID
        limit: Optional limit on number of results
    """
    job_uuid = parse_job_uuid(job_id)

    try:
        vector_store = get_vector_store()
        results = await vector_store.get_by_job_id(
            db=db,
            job_id=job_uuid,
            limit=limit,
        )

        return {
            "job_id": job_id,
            "results": results,
            "count": len(results),
        }
    except Exception as e:
        logger.error("Error fetching scraped content: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error fetching scraped content")


@app.post("/api/query", response_model=QueryResponse)
async def natural_language_query(
    request: QueryRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query research data using natural language.

    Searches both the vector store (scraped content) and structured
    database (research jobs) and returns a synthesized answer with
    source citations.
    """
    try:
        engine = get_query_engine()
        result = await engine.query(
            db=db,
            question=request.question.strip(),
            job_id=request.job_id,
            limit=request.limit,
        )
        return QueryResponse(
            answer=result.answer,
            sources=[
                QuerySourceItem(
                    url=s.url,
                    title=s.title,
                    snippet=s.snippet,
                    source_type=s.source_type,
                    relevance_score=s.relevance_score,
                )
                for s in result.sources
            ],
            query=result.query,
        )
    except Exception as e:
        logger.error("Error in NL query: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Query failed")


@app.get("/api/explore/indicators", response_model=list[IndicatorItem])
async def get_indicators(
    state_fips: str | None = None,
    geography_type: str = "state",
    metric: str | None = None,
    race: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get Census ACS indicators, optionally filtered."""
    try:
        query = select(CensusIndicator)
        if state_fips is not None:
            query = query.where(CensusIndicator.state_fips == state_fips)
        if geography_type:
            query = query.where(CensusIndicator.geography_type == geography_type)
        if metric is not None:
            query = query.where(CensusIndicator.metric == metric)
        if race is not None:
            query = query.where(CensusIndicator.race == race)
        if year is not None:
            query = query.where(CensusIndicator.year == year)
        query = query.limit(max(1, min(limit, 5000)))
        result = await db.execute(query)
        rows = result.scalars().all()
        return [
            IndicatorItem(
                fips_code=r.fips_code,
                geography_name=r.geography_name,
                state_fips=r.state_fips,
                geography_type=r.geography_type,
                year=r.year,
                race=r.race,
                metric=r.metric,
                value=r.value,
                margin_of_error=r.margin_of_error,
            )
            for r in rows
        ]
    except Exception as e:
        logger.error("Error fetching indicators: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error fetching indicators") from e


@app.get("/api/explore/cdc", response_model=ExploreResponse)
async def get_cdc_health(
    state_fips: str | None = None,
    measure: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """CDC health outcomes aggregated to state level."""
    try:
        query = select(CdcHealthOutcome).where(
            CdcHealthOutcome.geography_type == "state"
        )
        if state_fips:
            query = query.where(CdcHealthOutcome.state_fips == state_fips)
        if measure:
            query = query.where(CdcHealthOutcome.measure == measure)
        if year:
            query = query.where(CdcHealthOutcome.year == year)
        query = query.order_by(CdcHealthOutcome.state_fips).limit(max(1, min(limit, 5000)))

        result = await db.execute(query)
        rows_raw = result.scalars().all()

        row_dicts = [
            {
                "state_fips": r.state_fips,
                "state_name": r.geography_name,
                "value": r.data_value,
                "metric": r.measure,
                "year": r.year,
                "race": None,
            }
            for r in rows_raw
        ]

        return ExploreResponse(
            rows=[ExploreRow(**d) for d in row_dicts],
            national_average=compute_national_avg(row_dicts),
            available_metrics=distinct_values(row_dicts, "metric"),
            available_years=distinct_values(row_dicts, "year"),
            available_races=[],
        )
    except Exception:
        logger.error("Failed to fetch CDC health data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch CDC health data")


@app.get("/api/explore/epa", response_model=ExploreResponse)
async def get_epa_environmental_justice(
    state_fips: str | None = None,
    indicator: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """EPA EJScreen environmental justice data aggregated to state level."""
    try:
        query = select(
            EpaEnvironmentalJustice.state_fips,
            EpaEnvironmentalJustice.state_name,
            func.avg(EpaEnvironmentalJustice.raw_value).label("avg_value"),
            EpaEnvironmentalJustice.indicator,
            EpaEnvironmentalJustice.year,
        ).group_by(
            EpaEnvironmentalJustice.state_fips,
            EpaEnvironmentalJustice.state_name,
            EpaEnvironmentalJustice.indicator,
            EpaEnvironmentalJustice.year,
        )
        if state_fips:
            query = query.where(EpaEnvironmentalJustice.state_fips == state_fips)
        if indicator:
            query = query.where(EpaEnvironmentalJustice.indicator == indicator)
        if year:
            query = query.where(EpaEnvironmentalJustice.year == year)
        query = query.order_by(EpaEnvironmentalJustice.state_fips).limit(max(1, min(limit, 5000)))

        result = await db.execute(query)
        rows_raw = result.mappings().all()

        row_dicts = [
            {
                "state_fips": r["state_fips"],
                "state_name": r["state_name"],
                "value": r["avg_value"],
                "metric": r["indicator"],
                "year": r["year"],
                "race": None,
            }
            for r in rows_raw
        ]

        return ExploreResponse(
            rows=[ExploreRow(**d) for d in row_dicts],
            national_average=compute_national_avg(row_dicts),
            available_metrics=distinct_values(row_dicts, "metric"),
            available_years=distinct_values(row_dicts, "year"),
            available_races=[],
        )
    except Exception:
        logger.error("Failed to fetch EPA EJ data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch EPA EJ data")


@app.get("/api/explore/fbi", response_model=ExploreResponse)
async def get_fbi_crime_stats(
    state_fips: str | None = None,
    offense: str | None = None,
    race: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FBI Crime Data Explorer statistics."""
    try:
        query = select(FbiCrimeStat)
        if state_fips:
            abbrev = FIPS_TO_ABBREV.get(state_fips)
            if abbrev:
                query = query.where(FbiCrimeStat.state_abbrev == abbrev)
        if offense:
            query = query.where(FbiCrimeStat.offense == offense)
        if race:
            query = query.where(FbiCrimeStat.race == race)
        if year:
            query = query.where(FbiCrimeStat.year == year)
        query = query.order_by(FbiCrimeStat.state_abbrev).limit(max(1, min(limit, 5000)))

        result = await db.execute(query)
        rows_raw = result.scalars().all()

        row_dicts = [
            {
                "state_fips": ABBREV_TO_FIPS.get(r.state_abbrev, ""),
                "state_name": r.state_name,
                "value": r.value,
                "metric": r.offense,
                "year": r.year,
                "race": r.race,
            }
            for r in rows_raw
        ]

        return ExploreResponse(
            rows=[ExploreRow(**d) for d in row_dicts],
            national_average=compute_national_avg(row_dicts),
            available_metrics=distinct_values(row_dicts, "metric"),
            available_years=distinct_values(row_dicts, "year"),
            available_races=distinct_values(row_dicts, "race"),
        )
    except Exception:
        logger.error("Failed to fetch FBI crime data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch FBI crime data")


@app.get("/api/explore/bls", response_model=ExploreResponse)
async def get_bls_labor_stats(
    state_fips: str | None = None,
    metric: str | None = None,
    race: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """BLS labor statistics."""
    try:
        query = select(BlsLaborStatistic).where(
            BlsLaborStatistic.state_fips.isnot(None)
        )
        if state_fips:
            query = query.where(BlsLaborStatistic.state_fips == state_fips)
        if metric:
            query = query.where(BlsLaborStatistic.metric == metric)
        if race:
            query = query.where(BlsLaborStatistic.race == race)
        if year:
            query = query.where(BlsLaborStatistic.year == year)
        query = query.order_by(BlsLaborStatistic.state_fips).limit(max(1, min(limit, 5000)))

        result = await db.execute(query)
        rows_raw = result.scalars().all()

        row_dicts = [
            {
                "state_fips": r.state_fips,
                "state_name": r.state_name or "",
                "value": r.value,
                "metric": r.metric,
                "year": r.year,
                "race": r.race,
            }
            for r in rows_raw
        ]

        return ExploreResponse(
            rows=[ExploreRow(**d) for d in row_dicts],
            national_average=compute_national_avg(row_dicts),
            available_metrics=distinct_values(row_dicts, "metric"),
            available_years=distinct_values(row_dicts, "year"),
            available_races=distinct_values(row_dicts, "race"),
        )
    except Exception:
        logger.error("Failed to fetch BLS labor data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch BLS labor data")


@app.get("/api/explore/hud", response_model=ExploreResponse)
async def get_hud_fair_housing(
    state_fips: str | None = None,
    indicator: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """HUD fair housing data filtered to state-level geography."""
    try:
        query = select(HudFairHousing).where(
            HudFairHousing.geography_type == "state"
        )
        if state_fips:
            query = query.where(HudFairHousing.state_fips == state_fips)
        if indicator:
            query = query.where(HudFairHousing.indicator == indicator)
        if year:
            query = query.where(HudFairHousing.year == year)
        query = query.order_by(HudFairHousing.state_fips).limit(max(1, min(limit, 5000)))

        result = await db.execute(query)
        rows_raw = result.scalars().all()

        row_dicts = [
            {
                "state_fips": r.state_fips,
                "state_name": r.geography_name,
                "value": r.value,
                "metric": r.indicator,
                "year": r.year,
                "race": None,
            }
            for r in rows_raw
        ]

        return ExploreResponse(
            rows=[ExploreRow(**d) for d in row_dicts],
            national_average=compute_national_avg(row_dicts),
            available_metrics=distinct_values(row_dicts, "metric"),
            available_years=distinct_values(row_dicts, "year"),
            available_races=[],
        )
    except Exception:
        logger.error("Failed to fetch HUD fair housing data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch HUD fair housing data")


@app.get("/api/explore/usda", response_model=ExploreResponse)
async def get_usda_food_access(
    state_fips: str | None = None,
    indicator: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """USDA food access data aggregated to state level."""
    try:
        query = select(
            UsdaFoodAccess.state_fips,
            UsdaFoodAccess.state_name,
            func.avg(UsdaFoodAccess.value).label("avg_value"),
            UsdaFoodAccess.indicator,
            UsdaFoodAccess.year,
        ).group_by(
            UsdaFoodAccess.state_fips,
            UsdaFoodAccess.state_name,
            UsdaFoodAccess.indicator,
            UsdaFoodAccess.year,
        )
        if state_fips:
            query = query.where(UsdaFoodAccess.state_fips == state_fips)
        if indicator:
            query = query.where(UsdaFoodAccess.indicator == indicator)
        if year:
            query = query.where(UsdaFoodAccess.year == year)
        query = query.order_by(UsdaFoodAccess.state_fips).limit(max(1, min(limit, 5000)))

        result = await db.execute(query)
        rows_raw = result.mappings().all()

        row_dicts = [
            {
                "state_fips": r["state_fips"],
                "state_name": r["state_name"] or "",
                "value": r["avg_value"],
                "metric": r["indicator"],
                "year": r["year"],
                "race": None,
            }
            for r in rows_raw
        ]

        return ExploreResponse(
            rows=[ExploreRow(**d) for d in row_dicts],
            national_average=compute_national_avg(row_dicts),
            available_metrics=distinct_values(row_dicts, "metric"),
            available_years=distinct_values(row_dicts, "year"),
            available_races=[],
        )
    except Exception:
        logger.error("Failed to fetch USDA food access data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch USDA food access data")


@app.get("/api/explore/doe", response_model=ExploreResponse)
async def get_doe_civil_rights(
    state_fips: str | None = None,
    state: str | None = None,
    metric: str | None = None,
    race: str | None = None,
    school_year: str | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """DOE Civil Rights Data Collection aggregated to state level."""
    try:
        # Convert state_fips to abbreviation if provided
        state_abbrev = state
        if state_fips and not state_abbrev:
            state_abbrev = FIPS_TO_ABBREV.get(state_fips)

        query = select(
            DoeCivilRights.state,
            DoeCivilRights.state_name,
            DoeCivilRights.metric.label("metric_name"),
            DoeCivilRights.race,
            DoeCivilRights.school_year,
            func.avg(DoeCivilRights.value).label("avg_value"),
        ).group_by(
            DoeCivilRights.state,
            DoeCivilRights.state_name,
            DoeCivilRights.metric,
            DoeCivilRights.race,
            DoeCivilRights.school_year,
        )
        if state_abbrev:
            query = query.where(DoeCivilRights.state == state_abbrev)
        if metric:
            query = query.where(DoeCivilRights.metric == metric)
        if race:
            query = query.where(DoeCivilRights.race == race)
        if school_year:
            query = query.where(DoeCivilRights.school_year == school_year)
        query = query.order_by(DoeCivilRights.state).limit(max(1, min(limit, 5000)))

        result = await db.execute(query)
        rows_raw = result.mappings().all()

        row_dicts = [
            {
                "state_fips": ABBREV_TO_FIPS.get(r["state"], ""),
                "state_name": r["state_name"],
                "value": r["avg_value"],
                "metric": r["metric_name"],
                "year": int(r["school_year"][:4]) if r["school_year"] else 0,
                "race": r["race"],
            }
            for r in rows_raw
        ]

        return ExploreResponse(
            rows=[ExploreRow(**d) for d in row_dicts],
            national_average=compute_national_avg(row_dicts),
            available_metrics=distinct_values(row_dicts, "metric"),
            available_years=distinct_values(row_dicts, "year"),
            available_races=distinct_values(row_dicts, "race"),
        )
    except Exception:
        logger.error("Failed to fetch DOE civil rights data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch DOE civil rights data")


@app.get("/api/explore/police-violence", response_model=ExploreResponse)
async def get_police_violence(
    state_fips: str | None = None,
    state: str | None = None,
    race: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Police violence incidents aggregated by state/race/year."""
    try:
        # Convert state_fips to abbreviation if provided
        state_abbrev = state
        if state_fips and not state_abbrev:
            state_abbrev = FIPS_TO_ABBREV.get(state_fips)

        query = select(
            PoliceViolenceIncident.state,
            PoliceViolenceIncident.race,
            PoliceViolenceIncident.year,
            func.count().label("count"),
        ).group_by(
            PoliceViolenceIncident.state,
            PoliceViolenceIncident.race,
            PoliceViolenceIncident.year,
        )
        if state_abbrev:
            query = query.where(PoliceViolenceIncident.state == state_abbrev)
        if race:
            query = query.where(PoliceViolenceIncident.race == race)
        if year:
            query = query.where(PoliceViolenceIncident.year == year)
        query = query.order_by(PoliceViolenceIncident.state).limit(max(1, min(limit, 5000)))

        result = await db.execute(query)
        rows_raw = result.mappings().all()

        row_dicts = [
            {
                "state_fips": ABBREV_TO_FIPS.get(r["state"], ""),
                "state_name": FIPS_TO_NAME.get(ABBREV_TO_FIPS.get(r["state"], ""), r["state"]),
                "value": float(r["count"]),
                "metric": "incidents",
                "year": r["year"],
                "race": r["race"],
            }
            for r in rows_raw
        ]

        return ExploreResponse(
            rows=[ExploreRow(**d) for d in row_dicts],
            national_average=compute_national_avg(row_dicts),
            available_metrics=distinct_values(row_dicts, "metric"),
            available_years=distinct_values(row_dicts, "year"),
            available_races=distinct_values(row_dicts, "race"),
        )
    except Exception:
        logger.error("Failed to fetch police violence data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch police violence data")


@app.get("/api/explore/policies", response_model=list[PolicyBillItem])
async def get_policies(
    state: str | None = None,
    status: str | None = None,
    topic: str | None = None,
    session: str | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get policy bills, optionally filtered."""
    try:
        query = select(PolicyBill)
        if state is not None:
            query = query.where(PolicyBill.state == state)
        if status is not None:
            query = query.where(PolicyBill.status == status)
        if session is not None:
            query = query.where(PolicyBill.session == session)
        if topic is not None:
            # JSON array containment: cast topic_tags to text and use LIKE
            query = query.where(
                PolicyBill.topic_tags.cast(String).contains(topic)
            )
        query = query.limit(max(1, min(limit, 5000)))
        result = await db.execute(query)
        rows = result.scalars().all()
        return [
            PolicyBillItem(
                state=r.state,
                state_name=r.state_name,
                bill_number=r.bill_number,
                title=r.title,
                summary=r.summary,
                status=r.status,
                topic_tags=r.topic_tags,
                introduced_date=str(r.introduced_date) if r.introduced_date else None,
                last_action_date=str(r.last_action_date) if r.last_action_date else None,
                url=r.url,
            )
            for r in rows
        ]
    except Exception as e:
        logger.error("Error fetching policies: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error fetching policies") from e


@app.get("/api/explore/states", response_model=list[StateSummaryItem])
async def get_states_summary(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Summarize available data per state for choropleth coloring."""
    try:
        # Aggregate metrics available per state
        metrics_query = text(
            """
            SELECT
                state_fips,
                geography_name AS state_name,
                STRING_AGG(DISTINCT metric, ',') AS metrics,
                MAX(year) AS latest_year
            FROM census_indicators
            WHERE geography_type = 'state'
            GROUP BY state_fips, geography_name
            ORDER BY state_fips
        """
        )
        metrics_result = await db.execute(metrics_query)
        metrics_rows = metrics_result.mappings().all()

        # Aggregate bill count per state
        bills_query = text(
            """
            SELECT state_name, COUNT(*) AS bill_count
            FROM policy_bills
            GROUP BY state_name
        """
        )
        bills_result = await db.execute(bills_query)
        bills_rows = bills_result.mappings().all()

        # Build lookup: state_name -> bill_count
        bill_counts_by_name: dict = {}
        for row in bills_rows:
            bill_counts_by_name[row["state_name"]] = row["bill_count"]

        summary: list[StateSummaryItem] = []
        for row in metrics_rows:
            metrics_list = row["metrics"].split(",") if row["metrics"] else []
            bill_count = bill_counts_by_name.get(row["state_name"], 0)
            summary.append(
                StateSummaryItem(
                    state_fips=row["state_fips"],
                    state_name=row["state_name"],
                    available_metrics=metrics_list,
                    bill_count=bill_count,
                    latest_year=row["latest_year"],
                )
            )

        return summary
    except Exception as e:
        logger.error("Error fetching state summary: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error fetching state summary") from e


@app.get("/api/auth/me")
async def get_me(user: CurrentUser = Depends(get_current_user)):
    """Return the authenticated user's profile info."""
    return {"id": str(user.id), "email": user.email, "role": user.role}


@app.post("/api/admin/invite")
async def invite_user(
    request: InviteRequest,
    user: CurrentUser = Depends(require_admin),
):
    """Invite a new user by email (admin only)."""
    import httpx

    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{settings.supabase_url}/auth/v1/invite",
            json={"email": request.email},
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
            },
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code, detail="Failed to invite user"
        )
    return {"message": f"Invitation sent to {request.email}"}


@app.get("/api/admin/users", response_model=list[UserProfile])
async def list_users(
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all user profiles (admin only)."""
    result = await db.execute(
        text(
            "SELECT id, email, role, display_name, created_at"
            " FROM profiles ORDER BY created_at"
        )
    )
    rows = result.mappings().all()
    return [
        UserProfile(
            id=str(row["id"]),
            email=row["email"],
            role=row["role"],
            display_name=row["display_name"],
            created_at=(
                row["created_at"].isoformat() if row["created_at"] else None
            ),
        )
        for row in rows
    ]


@app.patch("/api/admin/users/{user_id}")
async def update_user_role(
    user_id: str,
    request: UpdateRoleRequest,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a user's role (admin only)."""
    target_uuid = parse_job_uuid(user_id)

    # Prevent demoting the last admin
    if request.role != "admin":
        count_result = await db.execute(
            text("SELECT count(*) FROM profiles WHERE role = 'admin'")
        )
        admin_count = count_result.scalar_one()
        if admin_count <= 1:
            # Check if target is currently an admin
            target_result = await db.execute(
                text(
                    "SELECT role FROM profiles WHERE id = CAST(:uid AS uuid)"
                ),
                {"uid": str(target_uuid)},
            )
            target_role = target_result.scalar_one_or_none()
            if target_role == "admin":
                raise HTTPException(
                    status_code=409,
                    detail="Cannot demote the last admin",
                )

    result = await db.execute(
        text(
            "UPDATE profiles SET role = :role, updated_at = now()"
            " WHERE id = CAST(:uid AS uuid)"
        ),
        {"role": request.role, "uid": str(target_uuid)},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found")
    await db.commit()
    return {"message": f"User {user_id} role updated to {request.role}"}


# ---------------------------------------------------------------------------
# Admin ingestion endpoints
# ---------------------------------------------------------------------------


@app.post("/api/admin/ingest")
async def start_ingestion(
    body: dict = Body(default={}),
    user: CurrentUser = Depends(require_admin),
):
    """Spawn a background ingestion subprocess (admin only)."""
    _evict_finished_jobs()
    if len(_ingestion_jobs) >= _MAX_INGESTION_JOBS:
        raise HTTPException(
            status_code=429,
            detail="Too many ingestion jobs. Wait for running jobs to finish.",
        )
    sources: list[str] = body.get("sources") or sorted(VALID_INGEST_SOURCES)
    invalid = set(sources) - VALID_INGEST_SOURCES
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid source(s): {', '.join(sorted(invalid))}. "
            f"Valid: {', '.join(sorted(VALID_INGEST_SOURCES))}",
        )

    job_id = str(uuid4())
    script = str(
        Path(__file__).resolve().parents[3] / "scripts" / "run_ingestion.py"
    )
    cmd = [sys.executable, script, "--sources", ",".join(sources)]
    log_dir = Path(__file__).resolve().parents[3] / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = open(log_dir / f"ingest-{job_id}.log", "w")
    proc = subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    _ingestion_jobs[job_id] = {
        "process": proc,
        "sources": sources,
        "started_at": datetime.utcnow().isoformat(),
        "log_file": log_file,
    }
    return {"status": "started", "sources": sources, "job_id": job_id}


@app.get("/api/admin/ingest/status/{job_id}")
async def ingestion_status(
    job_id: str,
    user: CurrentUser = Depends(require_admin),
):
    """Check whether an ingestion subprocess is still running (admin only)."""
    entry = _ingestion_jobs.get(job_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Ingestion job not found")

    proc: subprocess.Popen = entry["process"]
    returncode = proc.poll()
    if returncode is None:
        status = "running"
    elif returncode == 0:
        status = "done"
    else:
        status = "error"

    return {
        "job_id": job_id,
        "status": status,
        "sources": entry["sources"],
        "started_at": entry["started_at"],
        "returncode": returncode,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

