"""
FastAPI backend for D4BL AI Agent UI
"""
import asyncio
import os
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.database import close_db, create_tables, get_db, init_db, EvaluationResult, ResearchJob
from d4bl.services.research_runner import run_research_job
from d4bl.app.schemas import (
    EvaluationResultItem,
    JobHistoryResponse,
    JobStatus,
    ResearchRequest,
    ResearchResponse,
)
from d4bl.app.websocket_manager import get_job_logs, register_connection, remove_connection

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
        asyncio.create_task(run_research_job(job_id, request.query, request.summary_format))
        
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

