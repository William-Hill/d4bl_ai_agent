"""
FastAPI backend for D4BL AI Agent UI
"""
import asyncio
import os
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import Body, Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.infra.database import close_db, create_tables, get_db, init_db, EvaluationResult, ResearchJob
from d4bl.infra.vector_store import get_vector_store
from d4bl.query.engine import QueryEngine
from d4bl.services.research_runner import run_research_job
from d4bl.app.schemas import (
    EvaluationResultItem,
    JobHistoryResponse,
    JobStatus,
    QueryRequest,
    QueryResponse,
    QuerySourceItem,
    ResearchRequest,
    ResearchResponse,
)
from d4bl.app.websocket_manager import get_job_logs, register_connection, remove_connection


_query_engine = None


def get_query_engine() -> QueryEngine:
    global _query_engine
    if _query_engine is None:
        _query_engine = QueryEngine()
    return _query_engine

app = FastAPI(title="D4BL AI Agent API", version="1.0.0")

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database on application startup"""
    try:
        init_db()
        await create_tables()
        print("✓ Database initialized successfully")
    except Exception as e:
        print(f"⚠ Warning: Database initialization failed: {e}")
        print("  The application will continue but jobs won't be persisted.")
    
    # Check Langfuse availability early and unset OTLP endpoint if not available
    # This prevents OpenTelemetry from trying to export traces when Langfuse is down
    try:
        from d4bl.observability.langfuse import check_langfuse_service_available
        import os
        from d4bl.settings import get_settings
        
        settings = get_settings()
        langfuse_otel_host = settings.langfuse_otel_host or settings.langfuse_host
        
        # Adjust for Docker
        if os.path.exists("/.dockerenv"):
            if "localhost" in langfuse_otel_host:
                langfuse_otel_host = langfuse_otel_host.replace("localhost", "langfuse-web")
            if ":3002" in langfuse_otel_host:
                langfuse_otel_host = langfuse_otel_host.replace(":3002", ":3000")
        
        if not check_langfuse_service_available(langfuse_otel_host):
            print("⚠️ Langfuse service not available. Unsetting OTLP endpoint to prevent export errors.")
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            os.environ.pop("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", None)
        else:
            print("✓ Langfuse service is available")
    except Exception as e:
        print(f"⚠️ Could not check Langfuse availability: {e}")
        # Continue anyway - let individual components handle it


@app.on_event("shutdown")
async def shutdown_event():
    """Close database connections on shutdown"""
    await close_db()


# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
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
        if not request.query or not request.query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")
        
        if request.summary_format not in ["brief", "detailed", "comprehensive"]:
            raise HTTPException(status_code=400, detail="Invalid summary_format. Must be: brief, detailed, or comprehensive")
        
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
        asyncio.create_task(run_research_job(
            job_id, 
            request.query, 
            request.summary_format,
            request.selected_agents
        ))
        
        return ResearchResponse(
            job_id=job_id,
            status="pending",
            message="Research job created successfully"
        )
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Catch any other errors during job creation
        error_msg = f"Error creating research job: {str(e)}"
        print(f"ERROR in create_research: {error_msg}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=error_msg)


@app.get("/api/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str, db: AsyncSession = Depends(get_db)):
    """Get the status of a research job"""
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    
    result_query = select(ResearchJob).where(ResearchJob.job_id == job_uuid)
    result_obj = await db.execute(result_query)
    job = result_obj.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
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
        # Build query
        query = select(ResearchJob)
        
        # Filter by status if provided
        if status:
            query = query.where(ResearchJob.status == status)
        
        # Order by created_at descending (newest first)
        query = query.order_by(desc(ResearchJob.created_at))
        
        # Get total count
        count_query = select(func.count(ResearchJob.job_id))
        if status:
            count_query = count_query.where(ResearchJob.status == status)
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
        print(f"Error fetching job history: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching job history: {str(e)}")


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
    return [
        EvaluationResultItem(
            id=str(row.id),
            span_id=row.span_id,
            trace_id=row.trace_id,
            job_id=str(row.job_id) if row.job_id else None,
            eval_name=row.eval_name,
            label=row.label,
            score=row.score,
            explanation=row.explanation,
            input_text=row.input_text,
            output_text=row.output_text,
            context_text=row.context_text,
            created_at=row.created_at.isoformat() if row.created_at else None,
        )
        for row in rows
    ]


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
            async for db in get_db():
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
                break
        except Exception as db_error:
            print(f"Error fetching job from database: {db_error}")
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
        print(f"WebSocket error: {e}")
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
        
        job_uuid = None
        if job_id:
            try:
                job_uuid = UUID(job_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid job ID format")
        
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
        print(f"Error searching vector database: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error searching vector database: {str(e)}")


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
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    
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
        print(f"Error fetching scraped content: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching scraped content: {str(e)}")


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
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

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
        print(f"Error in NL query: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

