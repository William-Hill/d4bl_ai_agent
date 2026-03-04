"""
FastAPI backend for D4BL AI Agent UI
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from typing import AsyncGenerator, List, Optional
from uuid import UUID

from fastapi import Body, Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import String, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.infra import database as _db_mod
from d4bl.infra.database import (
    CensusIndicator,
    EvaluationResult,
    PolicyBill,
    ResearchJob,
    close_db,
    create_tables,
    get_db,
    init_db,
)
from d4bl.infra.vector_store import get_vector_store
from d4bl.query.engine import QueryEngine
from d4bl.services.research_runner import run_research_job
from d4bl.settings import get_settings
from d4bl.app.schemas import (
    EvaluationResultItem,
    IndicatorItem,
    JobHistoryResponse,
    JobStatus,
    PolicyBillItem,
    QueryRequest,
    QueryResponse,
    QuerySourceItem,
    ResearchRequest,
    ResearchResponse,
    StateSummaryItem,
)
from d4bl.app.websocket_manager import get_job_logs, register_connection, remove_connection

logger = logging.getLogger(__name__)


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
            _resolve_langfuse_host,
            check_langfuse_service_available,
        )

        settings = get_settings()
        langfuse_otel_host = _resolve_langfuse_host(
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

@app.get("/")
async def read_root():
    """Root endpoint for health/status."""
    return {"status": "ok", "message": "D4BL AI Agent API"}


@app.post("/api/research", response_model=ResearchResponse)
async def create_research(request: ResearchRequest, db: AsyncSession = Depends(get_db)):
    """Create a new research job"""
    try:
        # Create job in database
        job = ResearchJob(
            query=request.query,
            summary_format=request.summary_format,
            status="pending",
            progress="Job created, waiting to start..."
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
async def get_job_status(job_id: str, db: AsyncSession = Depends(get_db)):
    """Get the status of a research job"""
    job_uuid = parse_job_uuid(job_id)
    job = await fetch_research_job(db, job_uuid)
    return JobStatus(**job.to_dict())


@app.get("/api/jobs", response_model=JobHistoryResponse)
async def get_job_history(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get paginated job history"""
    try:
        # Build shared filters
        filters = []
        if status:
            filters.append(ResearchJob.status == status)

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


@app.get("/api/evaluations", response_model=List[EvaluationResultItem])
async def get_evaluations(
    trace_id: Optional[str] = None,
    job_id: Optional[str] = None,  # job_id maps to trace_id in Phoenix
    span_id: Optional[str] = None,
    eval_name: Optional[str] = None,
    limit: int = 100,
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
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time progress updates"""
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
    job_id: Optional[str] = Body(None, embed=True, description="Optional job ID to filter results"),
    limit: int = Body(10, embed=True, ge=1, le=50, description="Maximum number of results"),
    similarity_threshold: float = Body(0.7, embed=True, ge=0.0, le=1.0, description="Minimum cosine similarity score"),
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
    limit: Optional[int] = None,
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


@app.get("/api/explore/indicators", response_model=List[IndicatorItem])
async def get_indicators(
    state_fips: Optional[str] = None,
    geography_type: str = "state",
    metric: Optional[str] = None,
    race: Optional[str] = None,
    year: Optional[int] = None,
    limit: int = 1000,
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


@app.get("/api/explore/policies", response_model=List[PolicyBillItem])
async def get_policies(
    state: Optional[str] = None,
    status: Optional[str] = None,
    topic: Optional[str] = None,
    session: Optional[str] = None,
    limit: int = 1000,
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


@app.get("/api/explore/states", response_model=List[StateSummaryItem])
async def get_states_summary(db: AsyncSession = Depends(get_db)):
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

        summary: List[StateSummaryItem] = []
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

