"""
Logic for executing research jobs and streaming their progress.
"""
from __future__ import annotations

import asyncio
import io
import os
import queue
import sys
from datetime import datetime
from typing import Optional
from uuid import UUID

from opentelemetry import trace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.crew import D4Bl
from d4bl.database import ResearchJob, get_db
from d4bl.websocket_manager import (
    create_log_queue,
    get_job_logs,
    remove_log_queue,
    send_websocket_update,
    set_job_logs,
)


class LiveOutputHandler:
    """Capture stdout/stderr and stream the output via WebSocket."""

    def __init__(self, job_id: str, original_stdout, original_stderr, log_queue):
        self.job_id = job_id
        self.original_stdout = original_stdout
        self.original_stderr = original_stderr
        self.log_queue = log_queue
        self.buffer = io.StringIO()
        self.logs: list[str] = []

    def write(self, text: str) -> None:
        """Write to buffer and enqueue non-empty log lines."""
        if not text.strip():
            return

        self.buffer.write(text)
        self.logs.append(text)

        try:
            self.log_queue.put_nowait(
                {
                    "job_id": self.job_id,
                    "type": "log",
                    "message": text,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        except Exception:
            # Queue is full or unavailable; skip the log rather than blocking.
            pass

        self.original_stdout.write(text)
        self.original_stdout.flush()

    def flush(self) -> None:
        """Flush both the capture buffer and the original stdout."""
        self.buffer.flush()
        self.original_stdout.flush()

    def get_logs(self) -> list[str]:
        """Return the accumulated logs."""
        return self.logs


async def update_job_status(
    db: AsyncSession,
    job_id: str,
    status: str,
    progress: Optional[str] = None,
    result: Optional[dict] = None,
    research_data: Optional[dict] = None,
    error: Optional[str] = None,
    logs: Optional[list] = None,
    trace_id: Optional[str] = None,
) -> None:
    """Persist job state updates to the database."""
    try:
        job_uuid = UUID(job_id)
        result_query = select(ResearchJob).where(ResearchJob.job_id == job_uuid)
        result_obj = await db.execute(result_query)
        job = result_obj.scalar_one_or_none()

        if not job:
            return

        job.status = status
        if progress is not None:
            job.progress = progress
        if result is not None:
            job.result = result
        if research_data is not None:
            job.research_data = research_data
        if error is not None:
            job.error = error
        if logs is not None:
            job.logs = logs
        if trace_id:
            job.trace_id = trace_id
        if status in ["completed", "error"]:
            job.completed_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(job)
    except Exception as exc:
        print(f"Error updating job status in database: {exc}")
        await db.rollback()


async def run_research_job(job_id: str, query: str, summary_format: str) -> None:
    """Run the research crew and send progress updates via WebSocket."""
    set_job_logs(job_id, [])

    tracer = trace.get_tracer("d4bl.research_job")
    span_attributes = {
        "d4bl.job_id": job_id,
        "d4bl.query": query,
        "d4bl.summary_format": summary_format,
    }
    trace_id_hex: Optional[str] = None

    async def set_status(
        progress_msg: Optional[str],
        status: str = "running",
        result: Optional[dict] = None,
        research_data: Optional[dict] = None,
        error: Optional[str] = None,
        logs: Optional[list] = None,
        trace_override: Optional[str] = None,
    ) -> None:
        trace_value = trace_override or trace_id_hex
        async for db in get_db():
            try:
                await update_job_status(
                    db,
                    job_id,
                    status,
                    progress=progress_msg,
                    result=result,
                    research_data=research_data,
                    error=error,
                    logs=logs,
                    trace_id=trace_value,
                )
                break
            except Exception as update_err:  # noqa: BLE001
                print(f"Error updating job status: {update_err}")
                break

    try:
        with tracer.start_as_current_span("d4bl.research_job", attributes=span_attributes) as job_span:
            span_context = job_span.get_span_context()
            trace_id_hex = format(span_context.trace_id, "032x")

            await set_status("Initializing research crew...")
            await send_websocket_update(
                job_id,
                {
                    "type": "progress",
                    "job_id": job_id,
                    "status": "running",
                    "progress": "Initializing research crew...",
                    "trace_id": trace_id_hex,
                },
            )

            inputs = {
                "query": query,
                "summary_format": summary_format,
                "current_year": str(datetime.now().year),
            }

            await set_status("Starting research task...")
            await send_websocket_update(
                job_id,
                {
                    "type": "progress",
                    "job_id": job_id,
                    "status": "running",
                    "progress": "Starting research task...",
                    "trace_id": trace_id_hex,
                },
            )

            try:
                crew_instance = D4Bl()
            except Exception as exc:
                error_msg = f"Failed to initialize crew: {exc}"
                print(f"ERROR initializing crew: {error_msg}")
                import traceback

                traceback.print_exc()
                raise Exception(error_msg) from exc

            original_stdout = sys.stdout
            original_stderr = sys.stderr
            job_log_queue = create_log_queue(job_id)
            output_handler = LiveOutputHandler(job_id, original_stdout, original_stderr, job_log_queue)

            async def process_log_queue():
                while True:
                    try:
                        message = await asyncio.get_event_loop().run_in_executor(
                            None, lambda: job_log_queue.get(timeout=0.1)
                        )
                        if message:
                            await send_websocket_update(job_id, message)
                    except queue.Empty:
                        await asyncio.sleep(0.1)
                    except Exception as proc_err:  # noqa: BLE001
                        print(f"Error processing log queue: {proc_err}")
                        await asyncio.sleep(0.1)

            log_processor_task = asyncio.create_task(process_log_queue())

            try:
                sys.stdout = output_handler
                sys.stderr = output_handler
                result = await asyncio.to_thread(lambda: crew_instance.crew().kickoff(inputs=inputs))
            finally:
                sys.stdout = original_stdout
                sys.stderr = original_stderr
                set_job_logs(job_id, output_handler.get_logs())
                await asyncio.sleep(0.5)
                while not job_log_queue.empty():
                    try:
                        message = job_log_queue.get_nowait()
                        if message:
                            await send_websocket_update(job_id, message)
                    except queue.Empty:
                        break
                log_processor_task.cancel()
                try:
                    await log_processor_task
                except asyncio.CancelledError:
                    pass
                remove_log_queue(job_id)

            await set_status("Research completed, processing results...")
            await send_websocket_update(
                job_id,
                {
                    "type": "progress",
                    "job_id": job_id,
                    "status": "running",
                    "progress": "Research completed, processing results...",
                    "trace_id": trace_id_hex,
                },
            )

            result_dict = {
                "raw_output": str(result.raw) if hasattr(result, "raw") else str(result),
                "tasks_output": [],
            }
            research_data_dict = {
                "research_findings": [],
                "analysis_data": [],
                "all_research_content": "",
            }

            try:
                if hasattr(result, "tasks_output") and result.tasks_output:
                    for task_output in result.tasks_output:
                        try:
                            agent_name = "Unknown"
                            if hasattr(task_output, "agent"):
                                agent = task_output.agent
                                if hasattr(agent, "role"):
                                    agent_name = agent.role
                                elif isinstance(agent, str):
                                    agent_name = agent
                                elif hasattr(agent, "__str__"):
                                    agent_name = str(agent)

                            description = ""
                            if hasattr(task_output, "description"):
                                description = str(task_output.description)

                            if hasattr(task_output, "raw"):
                                output = str(task_output.raw)
                            elif hasattr(task_output, "output"):
                                output = str(task_output.output)
                            else:
                                output = str(task_output)

                            result_dict["tasks_output"].append(
                                {"agent": agent_name, "description": description, "output": output}
                            )

                            if "research" in agent_name.lower() or "researcher" in agent_name.lower():
                                research_data_dict["research_findings"].append(
                                    {"agent": agent_name, "description": description, "content": output}
                                )
                                if research_data_dict["all_research_content"]:
                                    research_data_dict["all_research_content"] += "\n\n"
                                research_data_dict["all_research_content"] += (
                                    f"## {agent_name}: {description}\n\n{output}"
                                )
                            elif "analyst" in agent_name.lower() or "analysis" in agent_name.lower():
                                research_data_dict["analysis_data"].append(
                                    {"agent": agent_name, "description": description, "content": output}
                                )
                                if research_data_dict["all_research_content"]:
                                    research_data_dict["all_research_content"] += "\n\n"
                                research_data_dict["all_research_content"] += (
                                    f"## {agent_name}: {description}\n\n{output}"
                                )
                        except Exception as extract_err:  # noqa: BLE001
                            print(f"Error extracting task output: {extract_err}")
                            result_dict["tasks_output"].append(
                                {
                                    "agent": "Unknown",
                                    "description": "",
                                    "output": str(task_output) if task_output else "Error extracting output",
                                }
                            )
            except Exception as exc:  # noqa: BLE001
                print(f"Error processing tasks_output: {exc}")

            try:
                report_path = "output/report.md"
                if os.path.exists(report_path):
                    with open(report_path, "r", encoding="utf-8") as file_handle:
                        result_dict["report"] = file_handle.read()
            except Exception as exc:  # noqa: BLE001
                print(f"Error reading report file: {exc}")

            final_logs = get_job_logs(job_id)
            await set_status(
                "Research completed successfully!",
                status="completed",
                result=result_dict,
                research_data=research_data_dict,
                logs=final_logs,
            )

            await send_websocket_update(
                job_id,
                {
                    "type": "complete",
                    "job_id": job_id,
                    "status": "completed",
                    "result": result_dict,
                    "logs": final_logs,
                    "trace_id": trace_id_hex,
                },
            )

    except Exception as exc:  # noqa: BLE001
        error_msg = str(exc)
        error_logs = get_job_logs(job_id)
        await set_status(
            f"Error: {error_msg}",
            status="error",
            error=error_msg,
            logs=error_logs,
            trace_override=trace_id_hex,
        )
        await send_websocket_update(
            job_id,
            {
                "type": "error",
                "job_id": job_id,
                "status": "error",
                "error": error_msg,
                "logs": error_logs,
                "trace_id": trace_id_hex,
            },
        )

