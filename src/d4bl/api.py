"""
FastAPI backend for D4BL AI Agent UI
"""
import asyncio
import json
import os
import sys
import io
import queue
import threading
from datetime import datetime
from typing import Optional
from uuid import uuid4
from contextlib import redirect_stdout, redirect_stderr

import os
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from d4bl.crew import D4Bl

app = FastAPI(title="D4BL AI Agent API", version="1.0.0")

# Get project root directory
project_root = Path(__file__).parent.parent.parent
ui_dir = project_root / "ui"

# Serve static files if UI directory exists
if ui_dir.exists():
    app.mount("/static", StaticFiles(directory=str(ui_dir)), name="static")

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active WebSocket connections
active_connections: dict[str, WebSocket] = {}

# Store live output logs for each job
job_logs: dict[str, list] = {}

# Queues for sending log messages asynchronously (one per job)
log_queues: dict[str, queue.Queue] = {}


class ResearchRequest(BaseModel):
    query: str
    summary_format: str = "detailed"  # brief, detailed, comprehensive


class ResearchResponse(BaseModel):
    job_id: str
    status: str
    message: str


class JobStatus(BaseModel):
    job_id: str
    status: str  # pending, running, completed, error
    progress: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None


# In-memory job storage (use a database in production)
jobs: dict[str, JobStatus] = {}


async def send_websocket_update(job_id: str, message: dict):
    """Send WebSocket update if connection exists"""
    if job_id in active_connections:
        try:
            await active_connections[job_id].send_json(message)
        except Exception as e:
            print(f"Error sending WebSocket update: {e}")
            # Remove broken connection
            if job_id in active_connections:
                del active_connections[job_id]


class LiveOutputHandler:
    """Custom output handler that captures stdout/stderr and sends via WebSocket"""
    def __init__(self, job_id: str, original_stdout, original_stderr, log_queue: queue.Queue):
        self.job_id = job_id
        self.original_stdout = original_stdout
        self.original_stderr = original_stderr
        self.log_queue = log_queue
        self.buffer = io.StringIO()
        self.logs = []
        
    def write(self, text: str):
        """Write to buffer and send via WebSocket"""
        if text.strip():  # Only send non-empty lines
            self.buffer.write(text)
            self.logs.append(text)
            
            # Queue message for async sending
            try:
                self.log_queue.put_nowait({
                    "job_id": self.job_id,
                    "type": "log",
                    "message": text,
                    "timestamp": datetime.now().isoformat()
                })
            except queue.Full:
                pass  # Queue is full, skip this message
            
            # Also write to original stdout for terminal visibility
            self.original_stdout.write(text)
            self.original_stdout.flush()
    
    def flush(self):
        """Flush the buffer"""
        self.buffer.flush()
        self.original_stdout.flush()
    
    def get_logs(self) -> list:
        """Get all captured logs"""
        return self.logs

async def run_research_job(job_id: str, query: str, summary_format: str):
    """Run the research crew and send progress updates via WebSocket"""
    # Initialize logs for this job
    job_logs[job_id] = []
    
    try:
        jobs[job_id].status = "running"
        jobs[job_id].progress = "Initializing research crew..."
        
        await send_websocket_update(job_id, {
            "type": "progress",
            "job_id": job_id,
            "status": "running",
            "progress": "Initializing research crew..."
        })

        inputs = {
            'query': query,
            'summary_format': summary_format,
            'current_year': str(datetime.now().year)
        }

        await send_websocket_update(job_id, {
            "type": "progress",
            "job_id": job_id,
            "status": "running",
            "progress": "Starting research task..."
        })

        # Initialize crew with error handling
        try:
            crew_instance = D4Bl()
        except Exception as e:
            error_msg = f"Failed to initialize crew: {str(e)}"
            print(f"ERROR initializing crew: {error_msg}")
            import traceback
            traceback.print_exc()
            raise Exception(error_msg) from e

        # Set up live output capture
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        # Create a queue for this job
        job_log_queue = queue.Queue()
        log_queues[job_id] = job_log_queue
        output_handler = LiveOutputHandler(job_id, original_stdout, original_stderr, job_log_queue)
        
        # Start background task to process log queue
        async def process_log_queue():
            """Process log messages from queue and send via WebSocket"""
            while True:
                try:
                    # Get message from queue with timeout
                    message = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: job_log_queue.get(timeout=0.1)
                    )
                    if message:
                        await send_websocket_update(job_id, message)
                except queue.Empty:
                    # Check if job is still running
                    if job_id not in jobs or jobs[job_id].status not in ["running"]:
                        break
                    await asyncio.sleep(0.1)
                except Exception as e:
                    print(f"Error processing log queue: {e}")
                    await asyncio.sleep(0.1)
        
        log_processor_task = asyncio.create_task(process_log_queue())
        
        # Run the crew with output capture
        try:
            # Redirect stdout and stderr to capture live output
            sys.stdout = output_handler
            sys.stderr = output_handler
            
            # Run crew in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: crew_instance.crew().kickoff(inputs=inputs)
            )
            
        except Exception as e:
            error_msg = f"Failed to run crew: {str(e)}"
            print(f"ERROR running crew: {error_msg}")
            import traceback
            traceback.print_exc()
            raise Exception(error_msg) from e
        finally:
            # Restore original stdout/stderr
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            # Store logs
            job_logs[job_id] = output_handler.get_logs()
            
            # Flush remaining log messages (wait a bit for queue to empty)
            await asyncio.sleep(0.5)
            
            # Process any remaining messages in the queue
            while not job_log_queue.empty():
                try:
                    message = job_log_queue.get_nowait()
                    if message:
                        await send_websocket_update(job_id, message)
                except queue.Empty:
                    break
            
            # Cancel log processor task
            log_processor_task.cancel()
            try:
                await log_processor_task
            except asyncio.CancelledError:
                pass
            # Clean up queue
            if job_id in log_queues:
                del log_queues[job_id]

        await send_websocket_update(job_id, {
            "type": "progress",
            "job_id": job_id,
            "status": "running",
            "progress": "Research completed, processing results..."
        })

        # Extract results with error handling
        result_dict = {
            "raw_output": str(result.raw) if hasattr(result, 'raw') else str(result),
            "tasks_output": []
        }

        # Try to extract task outputs
        try:
            if hasattr(result, 'tasks_output') and result.tasks_output:
                for task_output in result.tasks_output:
                    try:
                        # Safely extract agent name
                        agent_name = "Unknown"
                        if hasattr(task_output, 'agent'):
                            agent = task_output.agent
                            if hasattr(agent, 'role'):
                                agent_name = agent.role
                            elif isinstance(agent, str):
                                agent_name = agent
                            elif hasattr(agent, '__str__'):
                                agent_name = str(agent)
                        
                        # Safely extract description
                        description = ""
                        if hasattr(task_output, 'description'):
                            description = str(task_output.description)
                        
                        # Safely extract output
                        output = ""
                        if hasattr(task_output, 'raw'):
                            output = str(task_output.raw)
                        elif hasattr(task_output, 'output'):
                            output = str(task_output.output)
                        else:
                            output = str(task_output)
                        
                        result_dict["tasks_output"].append({
                            "agent": agent_name,
                            "description": description,
                            "output": output
                        })
                    except Exception as e:
                        # If individual task extraction fails, log and continue
                        print(f"Error extracting task output: {e}")
                        result_dict["tasks_output"].append({
                            "agent": "Unknown",
                            "description": "",
                            "output": str(task_output) if task_output else "Error extracting output"
                        })
        except Exception as e:
            print(f"Error processing tasks_output: {e}")

        # Check if report file was created
        try:
            report_path = "output/report.md"
            if os.path.exists(report_path):
                with open(report_path, 'r', encoding='utf-8') as f:
                    result_dict["report"] = f.read()
        except Exception as e:
            print(f"Error reading report file: {e}")

        jobs[job_id].status = "completed"
        jobs[job_id].result = result_dict
        jobs[job_id].progress = "Research completed successfully!"

        await send_websocket_update(job_id, {
            "type": "complete",
            "job_id": job_id,
            "status": "completed",
            "result": result_dict,
            "logs": job_logs.get(job_id, [])
        })

    except Exception as e:
        error_msg = str(e)
        jobs[job_id].status = "error"
        jobs[job_id].error = error_msg
        jobs[job_id].progress = f"Error: {error_msg}"

        await send_websocket_update(job_id, {
            "type": "error",
            "job_id": job_id,
            "status": "error",
            "error": error_msg,
            "logs": job_logs.get(job_id, [])
        })


@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the main UI"""
    html_path = ui_dir / "index.html"
    if html_path.exists():
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # Replace relative paths with /static/ for CSS and JS
            content = content.replace('href="styles.css"', 'href="/static/styles.css"')
            content = content.replace('src="app.js"', 'src="/static/app.js"')
            return HTMLResponse(content=content)
    return HTMLResponse(content="<h1>D4BL AI Agent API</h1><p>UI not found. Please check the ui directory.</p>")


@app.post("/api/research", response_model=ResearchResponse)
async def create_research(request: ResearchRequest):
    """Create a new research job"""
    try:
        if not request.query or not request.query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")
        
        if request.summary_format not in ["brief", "detailed", "comprehensive"]:
            raise HTTPException(status_code=400, detail="Invalid summary_format. Must be: brief, detailed, or comprehensive")
        
        job_id = str(uuid4())
        jobs[job_id] = JobStatus(
            job_id=job_id,
            status="pending",
            progress="Job created, waiting to start..."
        )
        
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
async def get_job_status(job_id: str):
    """Get the status of a research job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    # Ensure result is JSON serializable
    if job.result:
        try:
            # Test if result is JSON serializable
            import json
            json.dumps(job.result)
        except (TypeError, ValueError) as e:
            # If not serializable, convert to string
            job.result = {"error": f"Result serialization error: {str(e)}", "raw": str(job.result)}
    
    return job


@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time progress updates"""
    await websocket.accept()
    active_connections[job_id] = websocket
    
    try:
        # Send current status if job exists (in case job already completed)
        if job_id in jobs:
            job = jobs[job_id]
            if job.status == "completed":
                await websocket.send_json({
                    "type": "complete",
                    "job_id": job_id,
                    "status": "completed",
                    "result": job.result
                })
            elif job.status == "error":
                await websocket.send_json({
                    "type": "error",
                    "job_id": job_id,
                    "status": "error",
                    "error": job.error
                })
            else:
                await websocket.send_json({
                    "type": "status",
                    "job_id": job_id,
                    "status": job.status,
                    "progress": job.progress,
                    "logs": job_logs.get(job_id, [])
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
        if job_id in active_connections:
            del active_connections[job_id]


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

