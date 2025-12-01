"""
Database helpers for enriching and persisting evaluation data.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

import pandas as pd
from sqlalchemy import or_, select

from d4bl import database as db
from d4bl.database import EvaluationResult, ResearchJob, init_db


async def attach_db_context(qa_df: pd.DataFrame) -> pd.DataFrame:
    """
    Enrich qa_df with retrieval context from Postgres using research_data.
    """
    if "input" not in qa_df.columns:
        print("⚠️  qa_df has no 'input' column; cannot attach DB context.")
        if "context" not in qa_df.columns:
            qa_df["context"] = ""
        return qa_df

    if db.async_session_maker is None:
        print("ℹ️  Initializing database connection...")
        try:
            init_db()
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️  Error initializing database connection: {exc}")
            import traceback

            traceback.print_exc()
    if db.async_session_maker is None:
        print("⚠️  Could not initialize database connection; leaving context empty.")
        if "context" not in qa_df.columns:
            qa_df["context"] = ""
        return qa_df

    async with db.async_session_maker() as session:
        result = await session.execute(select(ResearchJob))
        jobs = result.scalars().all()

    query_to_context: Dict[str, str] = {}
    for job in jobs:
        if not job.research_data:
            continue
        ctx = job.research_data.get("all_research_content")
        if not ctx:
            continue
        q = (job.query or "").strip()
        if not q:
            continue
        query_to_context[q] = ctx

    if not query_to_context:
        print("⚠️  No research_data with 'all_research_content' found in DB.")
        if "context" not in qa_df.columns:
            qa_df["context"] = ""
        return qa_df

    print(f"✅ Loaded {len(query_to_context)} queries with research context from DB")

    def find_context_for_input(inp: str) -> str:
        if not isinstance(inp, str):
            inp = str(inp)
        for query, ctx in query_to_context.items():
            if query and query in inp:
                return ctx
        return ""

    qa_df["context"] = qa_df["input"].apply(find_context_for_input)
    num_with_ctx = (qa_df["context"] != "").sum()
    print(f"✅ Attached DB context to {num_with_ctx} / {len(qa_df)} rows")
    return qa_df


async def list_available_jobs() -> List[ResearchJob]:
    """List all available jobs from the database."""
    if db.async_session_maker is None:
        init_db()

    if db.async_session_maker is None:
        return []

    async with db.async_session_maker() as session:
        result = await session.execute(select(ResearchJob).order_by(ResearchJob.created_at.desc()))
        return result.scalars().all()


async def select_jobs_interactively() -> List[UUID]:
    """
    Interactive prompt for choosing job IDs to evaluate.
    """
    jobs = await list_available_jobs()

    if not jobs:
        print("⚠️  No jobs found in the database.")
        return []

    print("\n" + "=" * 70)
    print("Available Jobs:")
    print("=" * 70)
    for i, job in enumerate(jobs, 1):
        status_icon = "✅" if job.status == "completed" else "⏳" if job.status == "running" else "❌"
        query_preview = (job.query or "")[:60] + ("..." if len(job.query or "") > 60 else "")
        created_str = job.created_at.strftime("%Y-%m-%d %H:%M") if job.created_at else "N/A"
        print(f"{i}. {status_icon} [{job.job_id}]")
        print(f"   Query: {query_preview}")
        print(f"   Status: {job.status} | Created: {created_str}")
        if job.trace_id:
            print(f"   Phoenix Trace ID: {job.trace_id}")
        else:
            print("   Phoenix Trace ID: (not yet recorded)")
        print()

    print("=" * 70)
    print("Select job(s) to evaluate:")
    print("  - Enter job numbers separated by commas (e.g., 1,3,5)")
    print("  - Enter 'all' to select all jobs")
    print("  - Enter 'q' to quit")
    print("=" * 70)

    while True:
        try:
            selection = input("\nYour selection: ").strip().lower()

            if selection == "q":
                print("Cancelled.")
                return []

            if selection == "all":
                selected_job_ids = [job.job_id for job in jobs]
                print(f"✅ Selected all {len(selected_job_ids)} job(s)")
                return selected_job_ids

            indices = [int(x.strip()) for x in selection.split(",")]
            selected_jobs = []
            for idx in indices:
                if 1 <= idx <= len(jobs):
                    selected_jobs.append(jobs[idx - 1])
                else:
                    print(f"⚠️  Invalid selection: {idx} (must be between 1 and {len(jobs)})")
                    break
            else:
                selected_job_ids = [job.job_id for job in selected_jobs]
                print(f"✅ Selected {len(selected_job_ids)} job(s):")
                for job in selected_jobs:
                    query_preview = (job.query or "")[:60] + ("..." if len(job.query or "") > 60 else "")
                    print(f"   - [{job.job_id}] {query_preview}")
                return selected_job_ids

        except ValueError:
            print("⚠️  Invalid input. Please enter numbers separated by commas, 'all', or 'q'.")
        except KeyboardInterrupt:
            print("\n\nCancelled.")
            return []


async def filter_qa_df_by_jobs(qa_df: pd.DataFrame, job_ids: List[UUID]) -> pd.DataFrame:
    """
    Filter qa_df to only include rows that match the selected jobs.
    """
    if not job_ids:
        return qa_df

    if db.async_session_maker is None:
        init_db()

    if db.async_session_maker is None:
        print("⚠️  Could not initialize database; cannot filter by jobs.")
        return qa_df

    async with db.async_session_maker() as session:
        result = await session.execute(select(ResearchJob).where(ResearchJob.job_id.in_(job_ids)))
        selected_jobs = result.scalars().all()

    if not selected_jobs:
        print("⚠️  Selected jobs not found in database.")
        return qa_df

    query_to_job_id: Dict[str, UUID] = {}
    for job in sorted(selected_jobs, key=lambda j: j.created_at or datetime.min, reverse=True):
        query = (job.query or "").strip()
        if query:
            query_to_job_id[query] = job.job_id

    trace_col = None
    if "context.trace_id" in qa_df.columns:
        trace_col = "context.trace_id"
    elif "trace_id" in qa_df.columns:
        trace_col = "trace_id"

    selected_trace_ids = {job.trace_id for job in selected_jobs if getattr(job, "trace_id", None)}
    if trace_col and selected_trace_ids:
        filtered_df = qa_df[qa_df[trace_col].isin(selected_trace_ids)].copy()
        if len(filtered_df) > 0:
            print(f"✅ Filtered to {len(filtered_df)} rows by trace_id (from {len(qa_df)} total)")
            return filtered_df
        else:
            print("⚠️  No rows matched selected trace IDs; falling back to query matching.")

    print(f"🔍 Filtering traces to match {len(selected_jobs)} selected job(s)...")

    def matches_any_job(input_text: str) -> bool:
        if not isinstance(input_text, str):
            input_text = str(input_text)

        try:
            if input_text.strip().startswith("{"):
                data = json.loads(input_text)
                if isinstance(data, dict) and "messages" in data:
                    for msg in data.get("messages", []):
                        if isinstance(msg, dict) and "content" in msg:
                            content = msg["content"]
                            for query in query_to_job_id.keys():
                                if query.lower() in content.lower():
                                    return True
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

        input_lower = input_text.lower()
        for query in query_to_job_id.keys():
            if query.lower() in input_lower:
                return True

        return False

    mask = qa_df["input"].apply(matches_any_job)
    filtered_df = qa_df[mask].copy()

    print(f"✅ Filtered to {len(filtered_df)} rows matching selected job(s) (from {len(qa_df)} total)")
    return filtered_df


async def match_trace_to_job_id(
    trace_id: str, input_text: Optional[str] = None, selected_job_ids: Optional[List[UUID]] = None
) -> Optional[UUID]:
    """
    Try to match a trace_id to a job_id using various heuristics.
    """
    if db.async_session_maker is None:
        return None

    if selected_job_ids and len(selected_job_ids) == 1:
        return selected_job_ids[0]

    try:
        async with db.async_session_maker() as session:
            result = await session.execute(select(ResearchJob).where(ResearchJob.trace_id == trace_id))
            job = result.scalar_one_or_none()
            if job:
                print(f"   ✅ Matched saved trace_id {trace_id[:8]}... to job_id {job.job_id}")
                return job.job_id

        try:
            trace_uuid = UUID(trace_id)
            async with db.async_session_maker() as session:
                result = await session.execute(select(ResearchJob).where(ResearchJob.job_id == trace_uuid))
                job = result.scalar_one_or_none()
                if job:
                    print(f"   ✅ Matched trace_id {trace_id[:8]}... to job_id {job.job_id}")
                    return trace_uuid
        except (ValueError, TypeError):
            pass

        async with db.async_session_maker() as session:
            result = await session.execute(select(ResearchJob).order_by(ResearchJob.created_at.desc()))
            all_jobs = result.scalars().all()

        if len(all_jobs) == 0:
            print(f"   ⚠️  No jobs found in database for trace_id {trace_id[:8]}...")
            return None
        if len(all_jobs) == 1:
            job = all_jobs[0]
            print(f"   ✅ Using single job in database: {job.job_id} (trace_id: {trace_id[:8]}...)")
            return job.job_id

        if input_text and isinstance(input_text, str):
            query_to_match = None
            try:
                if input_text.strip().startswith("{"):
                    data = json.loads(input_text)
                    if isinstance(data, dict) and "messages" in data:
                        for msg in data.get("messages", []):
                            if isinstance(msg, dict) and "content" in msg:
                                content = msg["content"]
                                if "SYSTEM:" in content:
                                    parts = content.split("SYSTEM:", 1)
                                    if len(parts) > 1:
                                        query_to_match = parts[1].strip()[:200]
                                else:
                                    query_to_match = content[:200]
                                if query_to_match:
                                    break
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

            if not query_to_match:
                query_to_match = input_text[:200].strip()

            if query_to_match:
                async with db.async_session_maker() as session:
                    query_words = [w.strip() for w in query_to_match.split() if len(w.strip()) > 3][:5]
                    if query_words:
                        conditions = [ResearchJob.query.ilike(f"%{word}%") for word in query_words]
                        result = await session.execute(select(ResearchJob).where(or_(*conditions)))
                        jobs = result.scalars().all()
                        if len(jobs) == 1:
                            print(f"   ✅ Matched by query text to job_id {jobs[0].job_id}")
                            return jobs[0].job_id
                        elif len(jobs) > 1:
                            sorted_jobs = sorted(jobs, key=lambda j: j.created_at or datetime.min, reverse=True)
                            print(
                                "   ✅ Matched by query text (multiple matches, using most recent): "
                                f"{sorted_jobs[0].job_id}"
                            )
                            return sorted_jobs[0].job_id

        most_recent_job = all_jobs[0]
        print(
            "   ⚠️  Could not match by query, using most recent job: "
            f"{most_recent_job.job_id} (trace_id: {trace_id[:8]}...)"
        )
        return most_recent_job.job_id
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  Error matching trace_id to job_id: {exc}")
        import traceback

        traceback.print_exc()

    return None


async def persist_eval_results(
    annotation_df: pd.DataFrame, qa_df: pd.DataFrame, selected_job_ids: Optional[List[UUID]] = None
):
    """Store evaluator outputs (including explanations) in Postgres."""
    span_id_col = next((col for col in ["context.span_id", "span_id"] if col in annotation_df.columns), None)
    if not span_id_col:
        print("⚠️  Annotation dataframe missing span_id column; skipping DB persistence.")
        return

    if db.async_session_maker is None:
        print("ℹ️  Initializing database connection for eval persistence...")
        try:
            init_db()
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️  Error initializing database connection: {exc}")
            import traceback

            traceback.print_exc()

    if db.async_session_maker is None:
        print("⚠️  Could not initialize database connection; skipping eval persistence.")
        return

    qa_lookup = qa_df.copy()
    if qa_lookup.index.name:
        qa_lookup = qa_lookup.reset_index().rename(columns={qa_df.index.name: "span_id"})
    else:
        qa_lookup = qa_lookup.reset_index().rename(columns={"index": "span_id"})
    if "span_id" not in qa_lookup.columns:
        qa_lookup["span_id"] = qa_lookup.get(span_id_col, "")
    qa_lookup = qa_lookup.set_index("span_id", drop=False)

    def get_qa(span_id: str):
        if span_id in qa_lookup.index:
            return qa_lookup.loc[span_id]
        return None

    eval_records: List[EvaluationResult] = []

    if db.async_session_maker is None:
        print("⚠️  Database connection not initialized; skipping eval persistence.")
        return

    for _, row in annotation_df.iterrows():
        span_id = row.get(span_id_col) or row.get("span_id")
        if not span_id or (isinstance(span_id, float) and pd.isna(span_id)):
            continue
        span_id = str(span_id)

        eval_name = row.get("annotation_name") or row.get("name") or "evaluation"
        label = row.get("label")
        score = row.get("score")
        if isinstance(score, float) and pd.isna(score):
            score = None

        explanation = row.get("explanation")

        trace_id = None
        for candidate in ["context.trace_id", "trace_id"]:
            if candidate in row and pd.notna(row[candidate]):
                trace_id = str(row[candidate])
                break

        qa_row = get_qa(span_id)
        input_text = qa_row.get("input") if qa_row is not None else None
        output_text = qa_row.get("output") if qa_row is not None else None
        context_text = qa_row.get("context") if qa_row is not None else None
        if not trace_id and qa_row is not None:
            for candidate in ["context.trace_id", "trace_id"]:
                value = qa_row.get(candidate)
                if value:
                    trace_id = str(value)
                    break

        job_id_uuid = None
        if trace_id:
            print(f"   🔍 Attempting to match trace_id {trace_id[:8]}... to job_id...")
            job_id_uuid = await match_trace_to_job_id(trace_id, input_text, selected_job_ids)
            if job_id_uuid:
                print(f"   ✅ Successfully matched to job_id: {job_id_uuid}")
            else:
                print("   ⚠️  Could not match trace_id to job_id")

        eval_records.append(
            EvaluationResult(
                span_id=span_id,
                trace_id=trace_id,
                job_id=job_id_uuid,
                eval_name=eval_name,
                label=label,
                score=score,
                explanation=explanation,
                input_text=input_text,
                output_text=output_text,
                context_text=context_text,
            )
        )

    if not eval_records:
        print("⚠️  No evaluation records to persist.")
        return

    async with db.async_session_maker() as session:
        session.add_all(eval_records)
        await session.commit()
        print(f"💾 Stored {len(eval_records)} evaluation rows in the database.")

