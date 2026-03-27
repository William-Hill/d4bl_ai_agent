"""
FastAPI backend for D4BL AI Agent UI
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import time
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
from starlette.requests import Request

from d4bl.app.auth import CurrentUser, get_current_user, require_admin
from d4bl.app.cache import explore_cache
from d4bl.app.data_routes import router as data_router
from d4bl.app.explore_helpers import (
    FIPS_TO_STATE_NAME,
    build_response_from_summary,
    build_state_agg_response,
    compute_national_avg,
    distinct_values,
)
from d4bl.app.explore_insights import router as explore_insights_router
from d4bl.app.schemas import (
    CompareMetrics,
    CompareRequest,
    CompareResponse,
    EvalRunItem,
    EvalRunsResponse,
    EvaluationResultItem,
    ExploreResponse,
    ExploreRow,
    InviteRequest,
    JobHistoryResponse,
    JobStatus,
    ModelOutput,
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
    BjsIncarceration,
    BlsLaborStatistic,
    CdcHealthOutcome,
    CdcMortality,
    CensusIndicator,
    EvaluationResult,
    FbiCrimeStat,
    HudFairHousing,
    IngestionRun,
    ModelEvalRun,
    PoliceViolenceIncident,
    PolicyBill,
    ResearchJob,
    close_db,
    create_tables,
    get_db,
    init_db,
)
from d4bl.infra.vector_store import get_vector_store
from d4bl.llm import get_available_models
from d4bl.llm.ollama_client import model_for_task, ollama_generate
from d4bl.query.engine import QueryEngine
from d4bl.services.research_runner import run_research_job
from d4bl.settings import get_settings
from d4bl.validation.model_output import (
    ValidationResult,
    validate_evaluator_output,
    validate_explainer_output,
    validate_parser_output,
)

_COMPARE_VALIDATORS = {
    "query_parser": validate_parser_output,
    "explainer": validate_explainer_output,
    "evaluator": validate_evaluator_output,
}


def _task_specific_flag(task: str, validation_result: ValidationResult) -> str | None:
    """Compute a human-readable task-specific flag from validated output."""
    if not validation_result.valid or not validation_result.parsed:
        return None
    parsed = validation_result.parsed
    if task == "query_parser":
        valid_intents = {"compare", "trend", "lookup", "aggregate"}
        if parsed.get("intent") in valid_intents:
            return "Intent parsed"
    elif task == "explainer":
        if "narrative" in parsed:
            return "Has structural framing"
    elif task == "evaluator":
        score = parsed.get("score")
        if isinstance(score, (int, float)):
            return "Score present"
    return None


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

# Alias for backward compat within this file
FIPS_TO_NAME = FIPS_TO_STATE_NAME


_FRESHNESS_CHECK_INTERVAL = 30  # seconds
_last_freshness_check = 0.0


def _reset_freshness_state() -> None:
    """Reset freshness check state (for testing)."""
    global _last_freshness_check
    _last_freshness_check = 0.0


async def _check_cache_freshness(session: AsyncSession):
    """Invalidate cache if a newer ingestion run completed.

    Throttled to query the DB at most once every 30 seconds so that
    high-traffic endpoints don't issue a DB round-trip on every request.
    """
    global _last_freshness_check
    now = time.time()
    if now - _last_freshness_check < _FRESHNESS_CHECK_INTERVAL:
        return
    _last_freshness_check = now
    try:
        result = await session.execute(
            select(func.max(IngestionRun.completed_at)).where(
                IngestionRun.status == "completed"
            )
        )
        latest = result.scalar()
        if latest:
            explore_cache.invalidate_if_stale(newer_than=latest.timestamp())
    except Exception:
        # If the ingestion_runs table doesn't exist yet, skip silently.
        logger.debug("Cache freshness check skipped", exc_info=True)


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
app.include_router(explore_insights_router)

# ---------------------------------------------------------------------------
# Admin ingestion: track background subprocess jobs
# ---------------------------------------------------------------------------
VALID_INGEST_SOURCES = frozenset(
    ["cdc", "census", "epa", "fbi", "bls", "hud", "usda", "doe", "police", "openstates", "bjs"]
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


@app.get("/api/eval-runs", response_model=EvalRunsResponse)
async def get_eval_runs(
    task: str | None = None,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return latest model evaluation runs for the eval metrics dashboard."""
    # Deduplicate first: get latest run per (model_name, task) via subquery,
    # then apply limit — avoids dropping less-frequent model/task combos.
    latest_subq = (
        select(
            ModelEvalRun.model_name,
            ModelEvalRun.task,
            func.max(ModelEvalRun.created_at).label("max_created"),
        )
        .group_by(ModelEvalRun.model_name, ModelEvalRun.task)
    )
    if task:
        latest_subq = latest_subq.where(ModelEvalRun.task == task)
    latest_subq = latest_subq.subquery()

    query = (
        select(ModelEvalRun)
        .join(
            latest_subq,
            (ModelEvalRun.model_name == latest_subq.c.model_name)
            & (ModelEvalRun.task == latest_subq.c.task)
            & (ModelEvalRun.created_at == latest_subq.c.max_created),
        )
        .order_by(desc(ModelEvalRun.created_at))
        .limit(20)
    )

    result = await db.execute(query)
    rows = result.scalars().all()

    unique_runs: list[EvalRunItem] = []
    for row in rows:
        d = row.to_dict()
        unique_runs.append(EvalRunItem(
            model_name=d["model_name"],
            model_version=d["model_version"],
            base_model_name=d["base_model_name"],
            task=d["task"],
            metrics=d["metrics"],
            ship_decision=d["ship_decision"],
            blocking_failures=d.get("blocking_failures"),
            created_at=str(d.get("created_at", "")),
        ))

    return EvalRunsResponse(runs=unique_runs)


@app.post("/api/compare", response_model=CompareResponse)
async def compare_models_endpoint(
    request: CompareRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Run a prompt through base and fine-tuned models, return side-by-side comparison."""
    settings = get_settings()
    baseline_model = settings.ollama_model
    finetuned_model = model_for_task(request.task)

    if baseline_model == finetuned_model:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Fine-tuned model not configured for task '{request.task}'. "
                f"Set the {request.task.upper()}_MODEL environment variable."
            ),
        )

    base_url = settings.ollama_base_url

    async def _run(model: str) -> tuple[str, float]:
        start = time.monotonic()
        output = await ollama_generate(
            base_url=base_url,
            prompt=request.prompt,
            model=model,
            temperature=0.1,
            timeout_seconds=60,
        )
        return output, round(time.monotonic() - start, 3)

    try:
        (b_output, b_latency), (f_output, f_latency) = await asyncio.gather(
            _run(baseline_model),
            _run(finetuned_model),
        )
    except Exception as exc:
        logger.warning("Model inference failed for task %s", request.task, exc_info=True)
        raise HTTPException(
            status_code=502, detail="Model inference failed"
        ) from exc

    validator = _COMPARE_VALIDATORS[request.task]
    b_result = validator(b_output)
    f_result = validator(f_output)

    latency_delta_pct = (
        round((f_latency - b_latency) / b_latency * 100, 1)
        if b_latency > 0
        else 0.0
    )

    return CompareResponse(
        baseline=ModelOutput(
            model_name=baseline_model,
            output=b_output,
            latency_seconds=b_latency,
            valid_json=b_result.parsed is not None,
            errors=b_result.errors or None,
        ),
        finetuned=ModelOutput(
            model_name=finetuned_model,
            output=f_output,
            latency_seconds=f_latency,
            valid_json=f_result.parsed is not None,
            errors=f_result.errors or None,
        ),
        metrics=CompareMetrics(
            latency_delta_pct=latency_delta_pct,
            validity_improved=(f_result.parsed is not None) and (b_result.parsed is None),
            task_specific_flag=_task_specific_flag(request.task, f_result),
        ),
        task=request.task,
    )


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


@app.get("/api/explore/indicators", response_model=ExploreResponse)
async def get_indicators(
    request: Request,
    state_fips: str | None = None,
    metric: str | None = None,
    race: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Census ACS indicators — returns ExploreResponse."""
    cache_key = f"{request.url.path}?{request.query_params}"
    await _check_cache_freshness(db)
    cached = explore_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        query = select(CensusIndicator).where(
            CensusIndicator.geography_type == "state"
        )
        if state_fips is not None:
            query = query.where(CensusIndicator.state_fips == state_fips)
        if metric is not None:
            query = query.where(CensusIndicator.metric == metric)
        if race is not None:
            query = query.where(CensusIndicator.race == race)
        if year is not None:
            query = query.where(CensusIndicator.year == year)
        query = query.limit(max(1, min(limit, 5000)))
        result = await db.execute(query)
        rows_raw = result.scalars().all()

        rows = [
            {
                "state_fips": r.state_fips,
                "state_name": r.geography_name,
                "value": r.value,
                "metric": r.metric,
                "year": r.year,
                "race": r.race,
            }
            for r in rows_raw
        ]

        response = {
            "rows": rows,
            "national_average": compute_national_avg(rows),
            "available_metrics": distinct_values(rows, "metric"),
            "available_years": distinct_values(rows, "year"),
            "available_races": distinct_values(rows, "race"),
        }
        explore_cache.set(cache_key, response)
        return response
    except Exception as e:
        logger.error("Error fetching indicators: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error fetching indicators") from e


@app.get("/api/explore/cdc", response_model=ExploreResponse)
async def get_cdc_health(
    request: Request,
    state_fips: str | None = None,
    measure: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """CDC health outcomes aggregated to state level."""
    cache_key = f"{request.url.path}?{request.query_params}"
    await _check_cache_freshness(db)
    cached = explore_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        # Aggregate county/tract data up to state level
        query = select(
            CdcHealthOutcome.state_fips,
            func.avg(CdcHealthOutcome.data_value).label("avg_value"),
            CdcHealthOutcome.measure,
            CdcHealthOutcome.year,
        ).group_by(
            CdcHealthOutcome.state_fips,
            CdcHealthOutcome.measure,
            CdcHealthOutcome.year,
        )
        if state_fips:
            query = query.where(CdcHealthOutcome.state_fips == state_fips)
        if measure:
            query = query.where(CdcHealthOutcome.measure == measure)
        if year:
            query = query.where(CdcHealthOutcome.year == year)
        query = query.order_by(CdcHealthOutcome.state_fips).limit(max(1, min(limit, 5000)))

        result = await db.execute(query)
        rows_raw = result.mappings().all()
        response = build_state_agg_response(rows_raw, metric_key="measure")
        explore_cache.set(cache_key, response)
        return response
    except Exception:
        logger.error("Failed to fetch CDC health data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch CDC health data")


@app.get("/api/explore/epa", response_model=ExploreResponse)
async def get_epa_environmental_justice(
    request: Request,
    state_fips: str | None = None,
    indicator: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """EPA EJScreen environmental justice data aggregated to state level."""
    cache_key = f"{request.url.path}?{request.query_params}"
    await _check_cache_freshness(db)
    cached = explore_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        response = await build_response_from_summary(
            db,
            source="epa",
            state_fips=state_fips,
            metric_value=indicator,
            year=year,
            limit=limit,
        )
        explore_cache.set(cache_key, response)
        return response
    except Exception:
        logger.error("Failed to fetch EPA EJ data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch EPA EJ data")


@app.get("/api/explore/fbi", response_model=ExploreResponse)
async def get_fbi_crime_stats(
    request: Request,
    state_fips: str | None = None,
    offense: str | None = None,
    race: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FBI Crime Data Explorer statistics."""
    cache_key = f"{request.url.path}?{request.query_params}"
    await _check_cache_freshness(db)
    cached = explore_cache.get(cache_key)
    if cached is not None:
        return cached
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

        response = ExploreResponse(
            rows=[ExploreRow(**d) for d in row_dicts],
            national_average=compute_national_avg(row_dicts),
            available_metrics=distinct_values(row_dicts, "metric"),
            available_years=distinct_values(row_dicts, "year"),
            available_races=distinct_values(row_dicts, "race"),
        )
        explore_cache.set(cache_key, response)
        return response
    except Exception:
        logger.error("Failed to fetch FBI crime data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch FBI crime data")


@app.get("/api/explore/bls", response_model=ExploreResponse)
async def get_bls_labor_stats(
    request: Request,
    state_fips: str | None = None,
    metric: str | None = None,
    race: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """BLS labor statistics."""
    cache_key = f"{request.url.path}?{request.query_params}"
    await _check_cache_freshness(db)
    cached = explore_cache.get(cache_key)
    if cached is not None:
        return cached
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

        response = ExploreResponse(
            rows=[ExploreRow(**d) for d in row_dicts],
            national_average=compute_national_avg(row_dicts),
            available_metrics=distinct_values(row_dicts, "metric"),
            available_years=distinct_values(row_dicts, "year"),
            available_races=distinct_values(row_dicts, "race"),
        )
        explore_cache.set(cache_key, response)
        return response
    except Exception:
        logger.error("Failed to fetch BLS labor data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch BLS labor data")


@app.get("/api/explore/hud", response_model=ExploreResponse)
async def get_hud_fair_housing(
    request: Request,
    state_fips: str | None = None,
    indicator: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """HUD fair housing data aggregated to state level."""
    cache_key = f"{request.url.path}?{request.query_params}"
    await _check_cache_freshness(db)
    cached = explore_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        # Aggregate county-level data up to state level
        query = select(
            HudFairHousing.state_fips,
            func.avg(HudFairHousing.value).label("avg_value"),
            HudFairHousing.indicator,
            HudFairHousing.year,
        ).group_by(
            HudFairHousing.state_fips,
            HudFairHousing.indicator,
            HudFairHousing.year,
        )
        if state_fips:
            query = query.where(HudFairHousing.state_fips == state_fips)
        if indicator:
            query = query.where(HudFairHousing.indicator == indicator)
        if year:
            query = query.where(HudFairHousing.year == year)
        query = query.order_by(HudFairHousing.state_fips).limit(max(1, min(limit, 5000)))

        result = await db.execute(query)
        rows_raw = result.mappings().all()
        response = build_state_agg_response(rows_raw, metric_key="indicator")
        explore_cache.set(cache_key, response)
        return response
    except Exception:
        logger.error("Failed to fetch HUD fair housing data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch HUD fair housing data")


@app.get("/api/explore/usda", response_model=ExploreResponse)
async def get_usda_food_access(
    request: Request,
    state_fips: str | None = None,
    indicator: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """USDA food access data aggregated to state level."""
    cache_key = f"{request.url.path}?{request.query_params}"
    await _check_cache_freshness(db)
    cached = explore_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        response = await build_response_from_summary(
            db,
            source="usda",
            state_fips=state_fips,
            metric_value=indicator,
            year=year,
            limit=limit,
        )
        explore_cache.set(cache_key, response)
        return response
    except Exception:
        logger.error("Failed to fetch USDA food access data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch USDA food access data")


@app.get("/api/explore/doe", response_model=ExploreResponse)
async def get_doe_civil_rights(
    request: Request,
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
    cache_key = f"{request.url.path}?{request.query_params}"
    await _check_cache_freshness(db)
    cached = explore_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        # Convert school_year string (e.g. "2017-18") to integer year
        year_int: int | None = None
        if school_year:
            try:
                year_int = int(school_year[:4])
            except (ValueError, IndexError):
                year_int = None

        # Resolve state_fips: accept either FIPS code or abbreviation
        resolved_fips = state_fips
        if not resolved_fips and state:
            resolved_fips = ABBREV_TO_FIPS.get(state.upper())

        response = await build_response_from_summary(
            db,
            source="doe",
            state_fips=resolved_fips,
            metric_value=metric,
            race=race,
            year=year_int,
            limit=limit,
        )
        explore_cache.set(cache_key, response)
        return response
    except Exception:
        logger.error("Failed to fetch DOE civil rights data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch DOE civil rights data")


@app.get("/api/explore/police-violence", response_model=ExploreResponse)
async def get_police_violence(
    request: Request,
    state_fips: str | None = None,
    state: str | None = None,
    race: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Police violence incidents aggregated by state/race/year."""
    cache_key = f"{request.url.path}?{request.query_params}"
    await _check_cache_freshness(db)
    cached = explore_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        # Convert state_fips to abbreviation if provided
        state_abbrev = state
        if state_fips and not state_abbrev:
            state_abbrev = FIPS_TO_ABBREV.get(state_fips)

        # Per-race breakdown
        race_query = select(
            PoliceViolenceIncident.state,
            PoliceViolenceIncident.race,
            PoliceViolenceIncident.year,
            func.count().label("count"),
        ).group_by(
            PoliceViolenceIncident.state,
            PoliceViolenceIncident.race,
            PoliceViolenceIncident.year,
        )
        # State-level totals (race="total") for map/table display
        total_query = select(
            PoliceViolenceIncident.state,
            PoliceViolenceIncident.year,
            func.count().label("count"),
        ).group_by(
            PoliceViolenceIncident.state,
            PoliceViolenceIncident.year,
        )

        if state_abbrev:
            race_query = race_query.where(PoliceViolenceIncident.state == state_abbrev)
            total_query = total_query.where(PoliceViolenceIncident.state == state_abbrev)
        if race:
            race_query = race_query.where(PoliceViolenceIncident.race == race)
        if year:
            race_query = race_query.where(PoliceViolenceIncident.year == year)
            total_query = total_query.where(PoliceViolenceIncident.year == year)

        race_query = race_query.order_by(PoliceViolenceIncident.state).limit(max(1, min(limit, 5000)))
        total_query = total_query.order_by(PoliceViolenceIncident.state).limit(max(1, min(limit, 5000)))

        race_result = await db.execute(race_query)
        total_result = await db.execute(total_query)

        row_dicts = []
        # Add per-race rows
        for r in race_result.mappings().all():
            fips = ABBREV_TO_FIPS.get(r["state"], "")
            row_dicts.append({
                "state_fips": fips,
                "state_name": FIPS_TO_NAME.get(fips, r["state"]),
                "value": float(r["count"]),
                "metric": "incidents",
                "year": r["year"],
                "race": r["race"],
            })
        # Add "total" rows so the map and table can display state-level values
        for r in total_result.mappings().all():
            fips = ABBREV_TO_FIPS.get(r["state"], "")
            row_dicts.append({
                "state_fips": fips,
                "state_name": FIPS_TO_NAME.get(fips, r["state"]),
                "value": float(r["count"]),
                "metric": "incidents",
                "year": r["year"],
                "race": "total",
            })

        response = ExploreResponse(
            rows=[ExploreRow(**d) for d in row_dicts],
            national_average=compute_national_avg(
                [d for d in row_dicts if d["race"] == "total"]
            ),
            available_metrics=distinct_values(row_dicts, "metric"),
            available_years=distinct_values(row_dicts, "year"),
            available_races=distinct_values(row_dicts, "race"),
        )
        explore_cache.set(cache_key, response)
        return response
    except Exception:
        logger.error("Failed to fetch police violence data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch police violence data")


@app.get("/api/explore/bjs", response_model=ExploreResponse)
async def get_bjs_incarceration(
    request: Request,
    state_fips: str | None = None,
    metric: str | None = None,
    race: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bureau of Justice Statistics incarceration data."""
    cache_key = f"{request.url.path}?{request.query_params}"
    await _check_cache_freshness(db)
    cached = explore_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        query = select(BjsIncarceration).where(
            BjsIncarceration.state_abbrev != "US",
            BjsIncarceration.gender == "total",
        )
        if state_fips:
            abbrev = FIPS_TO_ABBREV.get(state_fips)
            if abbrev:
                query = query.where(BjsIncarceration.state_abbrev == abbrev)
        if metric:
            query = query.where(BjsIncarceration.metric == metric)
        if race:
            query = query.where(BjsIncarceration.race == race)
        if year:
            query = query.where(BjsIncarceration.year == year)
        query = query.order_by(BjsIncarceration.state_abbrev).limit(max(1, min(limit, 5000)))

        result = await db.execute(query)
        rows_raw = result.scalars().all()

        row_dicts = [
            {
                "state_fips": ABBREV_TO_FIPS.get(r.state_abbrev, ""),
                "state_name": r.state_name,
                "value": r.value,
                "metric": r.metric,
                "year": r.year,
                "race": r.race,
            }
            for r in rows_raw
        ]

        nat_avg = compute_national_avg(row_dicts)

        response = ExploreResponse(
            rows=[ExploreRow(**d) for d in row_dicts],
            national_average=nat_avg,
            available_metrics=distinct_values(row_dicts, "metric"),
            available_years=distinct_values(row_dicts, "year"),
            available_races=distinct_values(row_dicts, "race"),
        )
        explore_cache.set(cache_key, response)
        return response
    except Exception:
        logger.error("Failed to fetch BJS incarceration data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch BJS incarceration data")


@app.get("/api/explore/census-demographics", response_model=ExploreResponse)
async def get_census_demographics(
    request: Request,
    state_fips: str | None = None,
    metric: str | None = None,
    race: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Census Decennial demographics aggregated to state level."""
    cache_key = f"{request.url.path}?{request.query_params}"
    await _check_cache_freshness(db)
    cached = explore_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        response = await build_response_from_summary(
            db,
            source="census-demographics",
            state_fips=state_fips,
            metric_value=metric,
            race=race,
            year=year,
            limit=limit,
        )
        explore_cache.set(cache_key, response)
        return response
    except Exception:
        logger.error("Failed to fetch Census demographics data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch Census demographics data")


@app.get("/api/explore/cdc-mortality", response_model=ExploreResponse)
async def get_cdc_mortality(
    request: Request,
    state_fips: str | None = None,
    cause_of_death: str | None = None,
    race: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """CDC mortality data — age-adjusted rates by cause and race."""
    cache_key = f"{request.url.path}?{request.query_params}"
    await _check_cache_freshness(db)
    cached = explore_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        query = select(CdcMortality)
        if state_fips:
            query = query.where(CdcMortality.state_fips == state_fips)
        if cause_of_death:
            query = query.where(CdcMortality.cause_of_death == cause_of_death)
        if race:
            query = query.where(CdcMortality.race == race)
        if year:
            query = query.where(CdcMortality.year == year)
        query = query.order_by(CdcMortality.state_fips).limit(max(1, min(limit, 5000)))

        result = await db.execute(query)
        rows_raw = result.scalars().all()

        row_dicts = [
            {
                "state_fips": r.state_fips,
                "state_name": r.state_name or FIPS_TO_NAME.get(r.state_fips, r.state_fips),
                "value": float(r.age_adjusted_rate) if r.age_adjusted_rate is not None else 0.0,
                "metric": r.cause_of_death,
                "year": r.year,
                "race": r.race,
            }
            for r in rows_raw
        ]

        response = ExploreResponse(
            rows=[ExploreRow(**d) for d in row_dicts],
            national_average=compute_national_avg(row_dicts),
            available_metrics=distinct_values(row_dicts, "metric"),
            available_years=distinct_values(row_dicts, "year"),
            available_races=distinct_values(row_dicts, "race"),
        )
        explore_cache.set(cache_key, response)
        return response
    except Exception:
        logger.error("Failed to fetch CDC mortality data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch CDC mortality data")


@app.get("/api/explore/policies", response_model=list[PolicyBillItem])
async def get_policies(
    request: Request,
    state: str | None = None,
    status: str | None = None,
    topic: str | None = None,
    session: str | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get policy bills, optionally filtered."""
    cache_key = f"{request.url.path}?{request.query_params}"
    await _check_cache_freshness(db)
    cached = explore_cache.get(cache_key)
    if cached is not None:
        return cached
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
        response = [
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
        explore_cache.set(cache_key, response)
        return response
    except Exception as e:
        logger.error("Error fetching policies: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error fetching policies") from e


@app.get("/api/explore/states", response_model=list[StateSummaryItem])
async def get_states_summary(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Summarize available data per state for choropleth coloring."""
    cache_key = f"{request.url.path}?{request.query_params}"
    await _check_cache_freshness(db)
    cached = explore_cache.get(cache_key)
    if cached is not None:
        return cached
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

        explore_cache.set(cache_key, summary)
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

