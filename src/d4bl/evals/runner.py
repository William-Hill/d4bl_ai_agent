"""Run LLM evaluations against completed research jobs stored in PostgreSQL."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select

from d4bl.infra.database import ResearchJob, init_db, get_db
from d4bl.services.langfuse.runner import run_comprehensive_evaluation

logger = logging.getLogger(__name__)


async def run_evals_and_log(
    max_rows: Optional[int] = None,
    eval_types: Optional[List[str]] = None,
    concurrency: int = 1,
    interactive: bool = False,
    selected_job_ids: Optional[List[UUID]] = None,
    output_csv_path: Optional[Path] = None,
) -> None:
    """Run evaluations on completed research jobs and log results.

    Args:
        max_rows: Limit number of jobs to evaluate. Default: all.
        eval_types: Which evaluator categories to run (unused; all run by default).
        concurrency: Number of concurrent evaluation requests.
        interactive: Unused; kept for CLI compatibility.
        selected_job_ids: Restrict evaluation to specific job UUIDs.
        output_csv_path: Unused; kept for CLI compatibility.
    """
    init_db()

    async for db in get_db():
        query = select(ResearchJob).where(ResearchJob.status == "completed")

        if selected_job_ids:
            query = query.where(ResearchJob.job_id.in_(selected_job_ids))

        if max_rows:
            query = query.limit(max_rows)

        result = await db.execute(query)
        jobs = result.scalars().all()

        if not jobs:
            logger.info("No completed research jobs found to evaluate.")
            return

        logger.info("Evaluating %d research job(s)...", len(jobs))

        sem = asyncio.Semaphore(concurrency)

        async def _evaluate_job(job: ResearchJob) -> None:
            async with sem:
                result_dict = job.to_dict()
                research_output = str(result_dict.get("result") or "")
                if not research_output:
                    logger.warning("Job %s has no result, skipping.", job.job_id)
                    return

                logger.info(
                    "Running evaluations for job %s: %s...",
                    job.job_id,
                    job.query[:60],
                )
                # run_comprehensive_evaluation is synchronous — run it in a
                # thread pool so it doesn't block the event loop.
                await asyncio.to_thread(
                    run_comprehensive_evaluation,
                    query=job.query,
                    research_output=research_output,
                    sources=[],
                    trace_id=str(job.job_id),
                )

        results = await asyncio.gather(
            *[_evaluate_job(j) for j in jobs], return_exceptions=True
        )
        for job, outcome in zip(jobs, results):
            if isinstance(outcome, BaseException):
                logger.error("Evaluation failed for job %s: %s", job.job_id, outcome)
        logger.info("Evaluation run complete.")
        break
