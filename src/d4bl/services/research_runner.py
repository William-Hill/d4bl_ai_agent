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
from d4bl.observability import get_langfuse_client
from d4bl.database import ResearchJob, get_db
from d4bl.app.websocket_manager import (
    create_log_queue,
    get_job_logs,
    remove_log_queue,
    send_websocket_update,
    set_job_logs,
)
from d4bl.services.error_handling import safe_execute, ErrorRecoveryStrategy
from d4bl.services.langfuse.evals import run_comprehensive_evaluation
import logging

logger = logging.getLogger(__name__)


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
    evaluation_results: Optional[dict] = None,
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
            # Include evaluation results in result dict
            if evaluation_results is not None:
                result = result or {}
                result["evaluation_results"] = evaluation_results
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
        evaluation_results: Optional[dict] = None,
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
                    evaluation_results=evaluation_results,
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

            # Use OpenTelemetry trace_id_hex for Langfuse trace linking
            # CrewAI is already instrumented with OpenTelemetry, so traces are automatically
            # sent to Langfuse via OTLP. The trace_id_hex from OpenTelemetry is what Langfuse uses.
            langfuse_trace_id = trace_id_hex
            logger.info(f"Using OpenTelemetry trace_id for Langfuse: {langfuse_trace_id[:16]}...")
            
            try:
                sys.stdout = output_handler
                sys.stderr = output_handler
                
                # Execute crew with error handling
                def execute_crew():
                    try:
                        return crew_instance.crew().kickoff(inputs=inputs)
                    except Exception as e:
                        logger.error(f"Crew execution failed: {e}", exc_info=True)
                        # Try recovery strategy
                        recovery_result = ErrorRecoveryStrategy.return_partial_results(
                            e, {"query": query, "partial_results": []}
                        )
                        # Create a mock result object for partial failure
                        class PartialResult:
                            def __init__(self, error_data):
                                self.raw = error_data
                                self.tasks_output = []
                        
                        return PartialResult(recovery_result)
                
                # Execute crew - traces are automatically sent via OpenTelemetry instrumentation
                result = await asyncio.to_thread(execute_crew)
                
                # Flush Langfuse client if available to ensure all traces are sent
                langfuse = get_langfuse_client()
                if langfuse:
                    langfuse.flush()
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

            # Run Langfuse evaluations on the research output
            evaluation_results = None
            try:
                research_output = research_data_dict.get("all_research_content", "") or result_dict.get("raw_output", "")
                sources = []
                
                # Extract sources from research data
                import re
                for finding in research_data_dict.get("research_findings", []):
                    # Try to extract URLs from content
                    urls = re.findall(r'https?://[^\s\)]+', finding.get("content", ""))
                    sources.extend(urls)
                
                # Also check raw output for URLs
                if result_dict.get("raw_output"):
                    urls = re.findall(r'https?://[^\s\)]+', result_dict.get("raw_output", ""))
                    sources.extend(urls)
                
                # Use the OpenTelemetry trace_id_hex for evaluations
                # This links evaluations to the trace that Langfuse receives via OTLP
                if research_output and langfuse_trace_id:
                    logger.info(f"🔍 Starting Langfuse evaluations for trace_id: {langfuse_trace_id[:16]}...")
                    logger.debug(f"   Research output length: {len(research_output)} chars")
                    logger.debug(f"   Sources found: {len(sources)}")
                    
                    try:
                        evaluation_results = run_comprehensive_evaluation(
                            query=query,
                            research_output=research_output[:5000],  # Limit size
                            sources=list(set(sources))[:10],  # Deduplicate and limit
                            trace_id=langfuse_trace_id  # Use OpenTelemetry trace ID
                        )
                        
                        eval_status = evaluation_results.get('status', 'unknown')
                        elapsed_time = evaluation_results.get('elapsed_time', 0)
                        
                        if eval_status == 'success':
                            overall_score = evaluation_results.get('overall_score', 'N/A')
                            logger.info(f"✅ Evaluations completed successfully in {elapsed_time:.2f}s")
                            logger.info(f"   Overall score: {overall_score:.2f}" if isinstance(overall_score, (int, float)) else f"   Overall score: {overall_score}")
                        elif eval_status == 'partial_success':
                            overall_score = evaluation_results.get('overall_score', 'N/A')
                            logger.warning(f"⚠️ Evaluations completed with partial success in {elapsed_time:.2f}s")
                            logger.warning(f"   Overall score: {overall_score:.2f}" if isinstance(overall_score, (int, float)) else f"   Overall score: {overall_score}")
                            # Log which evaluations failed
                            for eval_name, eval_result in evaluation_results.get('evaluations', {}).items():
                                if eval_result.get('status') != 'success':
                                    logger.warning(f"   - {eval_name}: {eval_result.get('status')} - {eval_result.get('error', 'Unknown error')}")
                        else:
                            logger.error(f"❌ Evaluations failed in {elapsed_time:.2f}s")
                            # Log evaluation errors
                            for eval_name, eval_result in evaluation_results.get('evaluations', {}).items():
                                if eval_result.get('status') != 'success':
                                    logger.error(f"   - {eval_name}: {eval_result.get('error', 'Unknown error')}")
                    
                    except Exception as eval_exec_error:
                        logger.error(f"❌ Exception during evaluation execution: {eval_exec_error}", exc_info=True)
                        evaluation_results = {
                            "status": "evaluation_failed",
                            "error": str(eval_exec_error),
                            "error_type": type(eval_exec_error).__name__
                        }
                        
                elif not research_output:
                    logger.warning("No research output available, skipping evaluations")
                    evaluation_results = {"status": "skipped", "reason": "no_research_output"}
                elif not langfuse_trace_id:
                    logger.warning("No trace_id available, skipping evaluations")
                    evaluation_results = {"status": "skipped", "reason": "no_trace_id"}
            except Exception as eval_error:
                logger.error(f"❌ Failed to run evaluations: {eval_error}", exc_info=True)
                logger.error(f"   Error type: {type(eval_error).__name__}")
                evaluation_results = {
                    "status": "evaluation_failed",
                    "error": str(eval_error),
                    "error_type": type(eval_error).__name__
                }
            
            final_logs = get_job_logs(job_id)
            
            # Include evaluation results in result dict
            if evaluation_results:
                result_dict["evaluation_results"] = evaluation_results
            
            await set_status(
                "Research completed successfully!",
                status="completed",
                result=result_dict,
                research_data=research_data_dict,
                logs=final_logs,
                evaluation_results=evaluation_results,
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

