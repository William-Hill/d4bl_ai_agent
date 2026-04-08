"""
Logic for executing research jobs and streaming their progress.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import queue
import re
import sys
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

import httpx
from opentelemetry import trace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.agents.crew import D4Bl

if TYPE_CHECKING:
    from d4bl.settings import Settings
from d4bl.app.websocket_manager import (
    create_log_queue,
    get_job_logs,
    remove_log_queue,
    send_websocket_update,
    set_job_logs,
)
from d4bl.infra.database import ResearchJob, get_db
from d4bl.observability import get_langfuse_client
from d4bl.services.error_handling import ErrorRecoveryStrategy
from d4bl.services.document_persistence import persist_research_documents
from d4bl.services.langfuse.runner import run_comprehensive_evaluation

logger = logging.getLogger(__name__)


def validate_research_relevance(query: str, output: str, agent_name: str = "Unknown") -> dict:
    """
    Quick validation to check if research output is relevant to the query.
    Returns a dict with validation results and warnings.
    """
    validation_result = {
        "is_relevant": True,
        "warnings": [],
        "query_keywords": [],
        "output_keywords": [],
    }

    if not output or len(output.strip()) < 50:
        validation_result["is_relevant"] = False
        validation_result["warnings"].append("Output is too short or empty")
        return validation_result

    # Extract key terms from query (simple keyword extraction)
    query_lower = query.lower()
    # Extract meaningful words (3+ characters, not common stop words)
    stop_words = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "was",
        "are",
        "were",
        "been",
        "be",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "can",
        "this",
        "that",
        "these",
        "those",
        "how",
        "what",
        "when",
        "where",
        "why",
        "which",
        "who",
    }
    query_words = [w for w in re.findall(r"\b\w{3,}\b", query_lower) if w not in stop_words]
    validation_result["query_keywords"] = query_words[:10]  # Top 10 keywords

    output_lower = output.lower()
    output_words = [w for w in re.findall(r"\b\w{3,}\b", output_lower) if w not in stop_words]
    validation_result["output_keywords"] = list(set(output_words))[:20]  # Top 20 unique keywords

    # Check for keyword overlap
    if query_words:
        matching_keywords = [w for w in query_words if w in output_lower]
        overlap_ratio = len(matching_keywords) / len(query_words)

        if overlap_ratio < 0.2:  # Less than 20% keyword overlap
            validation_result["is_relevant"] = False
            validation_result["warnings"].append(
                f"Low keyword overlap ({overlap_ratio:.1%}). Output may not address the query."
            )
        elif overlap_ratio < 0.4:  # Less than 40% keyword overlap
            validation_result["warnings"].append(
                f"Moderate keyword overlap ({overlap_ratio:.1%}). Verify output addresses the query."
            )

    # Check for common off-topic patterns
    output_lower_short = output_lower[:500]  # Check first 500 chars
    if query_words and not any(word in output_lower_short for word in query_words[:5]):
        validation_result["is_relevant"] = False
        validation_result["warnings"].append(
            "Query keywords not found in output. Output may be off-topic."
        )

    return validation_result


async def warmup_searxng(settings: Settings) -> bool:
    """Ping SearXNG /healthz to wake Fly.io machine. Returns True if healthy."""
    if settings.search_provider != "searxng" or not settings.searxng_base_url:
        return False

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.searxng_base_url}/healthz", timeout=15.0
            )
            if resp.is_success:
                logger.info("SearXNG warmup: %s (status %d)", settings.searxng_base_url, resp.status_code)
                return True
            else:
                logger.warning("SearXNG warmup unhealthy: %s (status %d)", settings.searxng_base_url, resp.status_code)
                return False
    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as exc:
        logger.warning("SearXNG warmup failed (will proceed anyway): %s", exc)
        return False


def _make_notify_progress(job_id: str, trace_id_hex: str | None):
    """Create a notify_progress coroutine for a given job. Testable factory."""

    async def notify_progress(progress_msg: str, phase: str | None = None) -> None:
        """Update DB status and push progress via WebSocket in one call."""
        async for db in get_db():
            try:
                await update_job_status(db, job_id, "running", progress=progress_msg)
                break
            except Exception as update_err:
                logger.error("Error updating job status: %s", update_err, exc_info=True)
                break

        ws_payload = {
            "type": "progress",
            "job_id": job_id,
            "status": "running",
            "message": progress_msg,
            "progress": progress_msg,
            "trace_id": trace_id_hex,
        }
        if phase is not None:
            ws_payload["phase"] = phase
        await send_websocket_update(job_id, ws_payload)

    return notify_progress


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
    progress: str | None = None,
    result: dict | None = None,
    research_data: dict | None = None,
    error: str | None = None,
    logs: list[str] | None = None,
    trace_id: str | None = None,
    evaluation_results: dict | None = None,
    usage: dict | None = None,
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
            if evaluation_results is not None:
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
        if usage is not None:
            job.usage = usage
        if status in ["completed", "error"]:
            job.completed_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(job)
    except Exception as exc:
        print(f"Error updating job status in database: {exc}")
        await db.rollback()


async def run_research_job(
    job_id: str,
    query: str,
    summary_format: str,
    selected_agents: list[str] | None = None,
    model: str | None = None,  # TODO: wire model selection into crew LLM config
) -> None:
    """Run the research crew and send progress updates via WebSocket."""
    set_job_logs(job_id, [])

    tracer = trace.get_tracer("d4bl.research_job")
    span_attributes = {
        "d4bl.job_id": job_id,
        "d4bl.query": query,
        "d4bl.summary_format": summary_format,
    }
    trace_id_hex: str | None = None

    async def set_status(
        progress_msg: str | None,
        status: str = "running",
        result: dict | None = None,
        research_data: dict | None = None,
        error: str | None = None,
        logs: list[str] | None = None,
        trace_override: str | None = None,
        evaluation_results: dict | None = None,
        usage: dict | None = None,
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
                    usage=usage,
                )
                break
            except Exception as update_err:  # noqa: BLE001
                print(f"Error updating job status: {update_err}")
                break

    try:
        with tracer.start_as_current_span(
            "d4bl.research_job", attributes=span_attributes
        ) as job_span:
            span_context = job_span.get_span_context()
            trace_id_hex = format(span_context.trace_id, "032x")

            notify_progress = _make_notify_progress(job_id, trace_id_hex)

            # -- Warmup SearXNG (wakes Fly.io machine) --
            from d4bl.settings import get_settings

            settings = get_settings()
            if settings.search_provider == "searxng" and settings.searxng_base_url:
                await notify_progress("Warming up search services...", phase="warmup")
                await warmup_searxng(settings)

            await notify_progress("Initializing research crew...", phase="init")

            inputs = {
                "query": query,
                "summary_format": summary_format,
                "current_year": str(datetime.now().year),
            }

            try:
                crew_instance = D4Bl()
                if selected_agents:
                    crew_instance.selected_agents = selected_agents
            except Exception as exc:
                error_msg = f"Failed to initialize crew: {exc}"
                logger.error("Failed to initialize crew: %s", exc, exc_info=True)
                raise Exception(error_msg) from exc

            await notify_progress("Starting research task...", phase="research")

            original_stdout = sys.stdout
            original_stderr = sys.stderr
            job_log_queue = create_log_queue(job_id)
            output_handler = LiveOutputHandler(
                job_id, original_stdout, original_stderr, job_log_queue
            )

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

            # Extract LLM token usage and estimate cost
            try:
                from d4bl.services.cost_tracker import extract_usage

                usage_dict = extract_usage(
                    result,
                    provider=settings.llm_provider,
                    model=settings.llm_model,
                )
                if usage_dict:
                    logger.info(
                        "Token usage: %d total (%d prompt + %d completion), est. $%.4f",
                        usage_dict["total_tokens"],
                        usage_dict["prompt_tokens"],
                        usage_dict["completion_tokens"],
                        usage_dict["estimated_cost_usd"],
                    )
            except Exception as exc:
                logger.warning("Failed to extract usage data: %s", exc)
                usage_dict = None

            await notify_progress("Research completed, processing results...", phase="evaluation")

            result_dict = {
                "raw_output": str(result.raw) if hasattr(result, "raw") else str(result),
                "tasks_output": [],
            }
            research_data_dict = {
                "research_findings": [],
                "analysis_data": [],
                "all_research_content": "",
                "source_urls": [],  # Store source URLs from crawl results
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

                            if (
                                "research" in agent_name.lower()
                                or "researcher" in agent_name.lower()
                            ):
                                # Extract source URLs from crawl tool results
                                # The crawl tool returns JSON with source_urls or urls_crawled
                                try:
                                    # Try to parse output as JSON (crawl tool returns JSON)
                                    if output.strip().startswith("{"):
                                        crawl_data = json.loads(output)
                                        # Extract source URLs from crawl results
                                        source_urls = crawl_data.get("source_urls", [])
                                        if not source_urls:
                                            source_urls = crawl_data.get("urls_crawled", [])
                                        if source_urls:
                                            research_data_dict["source_urls"].extend(source_urls)
                                            logger.info(
                                                "Extracted %s source URLs from crawl results",
                                                len(source_urls),
                                            )

                                        # Also extract URLs from results array
                                        results = crawl_data.get("results", [])
                                        for result in results:
                                            url = result.get("url", "")
                                            if url and url not in research_data_dict["source_urls"]:
                                                research_data_dict["source_urls"].append(url)
                                except (json.JSONDecodeError, KeyError, TypeError):
                                    # Output is not JSON, try regex extraction
                                    pass

                                # Validate research output relevance
                                validation = validate_research_relevance(query, output, agent_name)
                                if not validation["is_relevant"] or validation["warnings"]:
                                    logger.warning(
                                        "⚠️ Research output relevance check failed for %s: %s",
                                        agent_name,
                                        "; ".join(validation["warnings"]),
                                    )
                                    # Add validation info to result
                                    result_dict["tasks_output"][-1]["validation"] = validation

                                research_data_dict["research_findings"].append(
                                    {
                                        "agent": agent_name,
                                        "description": description,
                                        "content": output,
                                    }
                                )
                                if research_data_dict["all_research_content"]:
                                    research_data_dict["all_research_content"] += "\n\n"
                                research_data_dict["all_research_content"] += (
                                    f"## {agent_name}: {description}\n\n{output}"
                                )
                            elif (
                                "analyst" in agent_name.lower() or "analysis" in agent_name.lower()
                            ):
                                research_data_dict["analysis_data"].append(
                                    {
                                        "agent": agent_name,
                                        "description": description,
                                        "content": output,
                                    }
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
                                    "output": str(task_output)
                                    if task_output
                                    else "Error extracting output",
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

            # Set trace input/output in Langfuse for evaluations
            # According to Langfuse docs: https://langfuse.com/faq/all/empty-trace-input-and-output
            # We need to explicitly set trace input/output for evaluation features
            research_output = research_data_dict.get("all_research_content", "") or result_dict.get(
                "raw_output", ""
            )
            if langfuse_trace_id and research_output:
                try:
                    langfuse = get_langfuse_client()
                    if langfuse:
                        trace_input = {
                            "query": query,
                            "summary_format": summary_format,
                            "job_id": job_id,
                        }
                        trace_output = {
                            "raw_output": result_dict.get("raw_output", "")[:1000],  # Limit size
                            "research_content_length": len(research_output),
                            "tasks_completed": len(result_dict.get("tasks_output", [])),
                        }

                        # Note: For OTLP traces, trace input/output should be set via OpenTelemetry attributes
                        # The Langfuse REST API doesn't support updating traces created via OTLP
                        # The trace input/output will be populated from the root observation
                        logger.debug(
                            f"Trace input/output will be set from OpenTelemetry span attributes for trace_id: {langfuse_trace_id[:16]}..."
                        )
                except Exception as trace_update_error:
                    logger.warning(f"⚠️ Failed to update trace input/output: {trace_update_error}")
                    logger.debug("   Trace update error details:", exc_info=True)
                    # Continue with evaluations even if trace update fails

            # Run Langfuse evaluations on the research output
            evaluation_results = None
            try:
                sources = []

                # First, use source URLs extracted from crawl results (most reliable)
                if research_data_dict.get("source_urls"):
                    sources.extend(research_data_dict["source_urls"])
                    logger.info(
                        "Using %s source URLs from crawl results",
                        len(research_data_dict["source_urls"]),
                    )

                # Also extract URLs from research text (fallback)
                url_pattern = r"https?://[^\s\)\]\>\"\'\;]+"

                # Extract from all_research_content (already includes findings + analysis)
                # and raw_output (covers anything not in research_content)
                for text in (
                    research_data_dict.get("all_research_content", ""),
                    result_dict.get("raw_output", ""),
                ):
                    if text:
                        sources.extend(re.findall(url_pattern, text))

                # Deduplicate, clean trailing punctuation, and validate
                sources = list(
                    {
                        cleaned
                        for url in sources
                        if (cleaned := url.rstrip(".,;:!?)")).startswith(("http://", "https://"))
                    }
                )

                if not sources:
                    logger.warning("⚠️ No valid URLs found in research output")
                else:
                    logger.info("Found %s unique source URLs for evaluation", len(sources))

                # Extract content from crawl results for content relevance evaluation
                extracted_contents = []
                try:
                    # Parse crawl results from research findings
                    for finding in research_data_dict.get("research_findings", []):
                        content = finding.get("content", "")
                        if content and content.strip().startswith("{"):
                            try:
                                crawl_data = json.loads(content)
                                results = crawl_data.get("results", [])
                                for result in results:
                                    url = result.get("url", "")
                                    extracted_content = result.get(
                                        "extracted_content"
                                    ) or result.get("content", "")
                                    if (
                                        url
                                        and extracted_content
                                        and len(extracted_content.strip()) > 50
                                    ):
                                        extracted_contents.append(
                                            {
                                                "url": url,
                                                "content": extracted_content,
                                                "extracted_content": extracted_content,
                                            }
                                        )
                            except (json.JSONDecodeError, KeyError, TypeError):
                                # Not JSON, skip
                                pass
                except Exception as extract_error:
                    logger.warning("Error extracting content from crawl results: %s", extract_error)

                # Get report for report relevance evaluation
                report_content = result_dict.get("report", "")

                # Use the OpenTelemetry trace_id_hex for evaluations
                # This links evaluations to the trace that Langfuse receives via OTLP
                if research_output and langfuse_trace_id:
                    logger.info(
                        f"🔍 Starting Langfuse evaluations for trace_id: {langfuse_trace_id[:16]}..."
                    )
                    logger.debug(f"   Research output length: {len(research_output)} chars")
                    logger.debug(f"   Sources found: {len(sources)}")
                    logger.debug(f"   Extracted contents: {len(extracted_contents)}")
                    logger.debug(f"   Report available: {bool(report_content)}")

                    try:
                        evaluation_results = run_comprehensive_evaluation(
                            query=query,
                            research_output=research_output[:5000],  # Limit size
                            sources=list(set(sources))[:10],  # Deduplicate and limit
                            trace_id=langfuse_trace_id,  # Use OpenTelemetry trace ID
                            extracted_contents=extracted_contents[:10]
                            if extracted_contents
                            else None,  # Limit to 10
                            report=report_content[:5000] if report_content else None,  # Limit size
                        )

                        eval_status = evaluation_results.get("status", "unknown")
                        elapsed_time = evaluation_results.get("elapsed_time", 0)

                        if eval_status == "success":
                            overall_score = evaluation_results.get("overall_score", "N/A")
                            logger.info(
                                f"✅ Evaluations completed successfully in {elapsed_time:.2f}s"
                            )
                            logger.info(
                                f"   Overall score: {overall_score:.2f}"
                                if isinstance(overall_score, (int, float))
                                else f"   Overall score: {overall_score}"
                            )
                        elif eval_status == "partial_success":
                            overall_score = evaluation_results.get("overall_score", "N/A")
                            logger.warning(
                                f"⚠️ Evaluations completed with partial success in {elapsed_time:.2f}s"
                            )
                            logger.warning(
                                f"   Overall score: {overall_score:.2f}"
                                if isinstance(overall_score, (int, float))
                                else f"   Overall score: {overall_score}"
                            )
                            # Log which evaluations failed
                            for eval_name, eval_result in evaluation_results.get(
                                "evaluations", {}
                            ).items():
                                if eval_result.get("status") != "success":
                                    logger.warning(
                                        f"   - {eval_name}: {eval_result.get('status')} - {eval_result.get('error', 'Unknown error')}"
                                    )
                        else:
                            logger.error(f"❌ Evaluations failed in {elapsed_time:.2f}s")
                            # Log evaluation errors
                            for eval_name, eval_result in evaluation_results.get(
                                "evaluations", {}
                            ).items():
                                if eval_result.get("status") != "success":
                                    logger.error(
                                        f"   - {eval_name}: {eval_result.get('error', 'Unknown error')}"
                                    )

                    except Exception as eval_exec_error:
                        logger.error(
                            f"❌ Exception during evaluation execution: {eval_exec_error}",
                            exc_info=True,
                        )
                        evaluation_results = {
                            "status": "evaluation_failed",
                            "error": str(eval_exec_error),
                            "error_type": type(eval_exec_error).__name__,
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
                    "error_type": type(eval_error).__name__,
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
                usage=usage_dict,
            )

            # Persist crawled content as documents for the data flywheel
            try:
                async for db in get_db():
                    doc_count = await persist_research_documents(
                        UUID(job_id), research_data_dict, db
                    )
                    if doc_count:
                        logger.info(
                            "Persisted %d new documents from research job %s",
                            doc_count,
                            job_id,
                        )
                    break
            except Exception:
                logger.warning(
                    "Failed to persist research documents for job %s",
                    job_id,
                    exc_info=True,
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
