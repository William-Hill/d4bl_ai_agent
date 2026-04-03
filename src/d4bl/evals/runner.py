"""Run LLM evaluations against completed research jobs stored in PostgreSQL."""

from __future__ import annotations

import asyncio
import logging
import traceback
from uuid import UUID

from sqlalchemy import select

from d4bl.infra import database as db_module
from d4bl.infra.database import ResearchJob, init_db
from d4bl.services.langfuse.runner import run_comprehensive_evaluation

logger = logging.getLogger(__name__)


def _extract_eval_inputs(job: ResearchJob) -> dict | None:
    """Extract evaluation inputs from a completed job.

    Returns a kwargs dict for ``run_comprehensive_evaluation``, or ``None``
    if the job has no usable result text.
    """
    raw_result = job.result or {}
    research_output = (
        str(raw_result.get("raw_output", "")).strip() if isinstance(raw_result, dict) else ""
    )
    if not research_output:
        return None

    research_data = job.research_data if isinstance(job.research_data, dict) else {}
    findings_raw = research_data.get("research_findings")
    findings = findings_raw if isinstance(findings_raw, list) else []
    sources_raw = research_data.get("source_urls")
    sources = sources_raw if isinstance(sources_raw, list) else []
    report = raw_result.get("report") if isinstance(raw_result, dict) else None

    return {
        "query": job.query,
        "research_output": research_output,
        "sources": sources,
        "trace_id": job.trace_id or str(job.job_id),
        "report": report if isinstance(report, str) else None,
        "extracted_contents": [
            {"url": f.get("url", ""), "content": f.get("content", "")}
            for f in findings
            if isinstance(f, dict) and "url" in f
        ]
        or None,
    }


async def run_evals_and_log(
    max_rows: int | None = None,
    concurrency: int = 1,
    selected_job_ids: list[UUID] | None = None,
) -> None:
    """Run evaluations on completed research jobs and log results.

    Args:
        max_rows: Limit number of jobs to evaluate. Default: all.
        concurrency: Number of concurrent evaluation requests.
        selected_job_ids: Restrict evaluation to specific job UUIDs.
    """
    init_db()

    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")
    sem = asyncio.Semaphore(concurrency)

    async def _evaluate_job(job: ResearchJob) -> None:
        async with sem:
            inputs = _extract_eval_inputs(job)
            if inputs is None:
                logger.warning("Job %s has no result text, skipping.", job.job_id)
                return

            logger.info(
                "Running evaluations for job %s: %s...",
                job.job_id,
                job.query[:60],
            )
            await asyncio.to_thread(run_comprehensive_evaluation, **inputs)

    async with db_module.async_session_maker() as db:
        query = (
            select(ResearchJob)
            .where(
                ResearchJob.status == "completed",
                ResearchJob.result.isnot(None),
            )
            .order_by(ResearchJob.created_at.desc())
        )

        if selected_job_ids:
            query = query.where(ResearchJob.job_id.in_(selected_job_ids))

        if max_rows is not None:
            query = query.limit(max_rows)

        result = await db.execute(query)
        jobs = result.scalars().all()

        if not jobs:
            logger.info("No completed research jobs found to evaluate.")
            return

        logger.info("Evaluating %d research job(s)...", len(jobs))

        results = await asyncio.gather(*[_evaluate_job(j) for j in jobs], return_exceptions=True)

    for job, outcome in zip(jobs, results, strict=True):
        if isinstance(outcome, BaseException):
            logger.error(
                "Evaluation failed for job %s: %s\n%s",
                job.job_id,
                outcome,
                "".join(traceback.format_exception(outcome)),
            )
    logger.info("Evaluation run complete.")