"""
High-level orchestration for running Phoenix evaluations end-to-end.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from phoenix.client import Client
from phoenix.evals import async_evaluate_dataframe
from phoenix.evals.utils import to_annotation_dataframe

from d4bl.evals.jobs import (
    attach_db_context,
    filter_qa_df_by_jobs,
    persist_eval_results,
    select_jobs_interactively,
)
from d4bl.evals.llm import build_evaluators, build_ollama_llm
from d4bl.evals.phoenix import (
    fetch_qa_dataframe,
    sanitize_annotation_dataframe,
    validate_span_ids_against_phoenix,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


async def run_evals_and_log(
    max_rows: Optional[int] = None,
    eval_types: Optional[List[str]] = None,
    concurrency: int = 1,
    interactive: bool = False,
    selected_job_ids: Optional[List[UUID]] = None,
    output_csv_path: Optional[Path] = None,
):
    """
    Execute Phoenix evaluators and log the results to both Postgres and Phoenix.
    """
    phoenix_endpoint = os.getenv("PHOENIX_ENDPOINT")
    if not phoenix_endpoint:
        phoenix_endpoint = "http://phoenix:6006" if os.path.exists("/.dockerenv") else "http://localhost:6006"

    os.environ["PHOENIX_ENDPOINT"] = phoenix_endpoint

    print(f"🔍 Connecting to Phoenix at {phoenix_endpoint}...")
    client = Client(base_url=phoenix_endpoint)

    project_name = os.getenv("PHOENIX_PROJECT_NAME") or os.getenv("PHOENIX_PROJECT", "d4bl-crewai")
    print(f"Using Phoenix project: {project_name!r}")

    qa_df = fetch_qa_dataframe(client, project_name=project_name)
    print(f"Loaded {len(qa_df)} Q&A rows from traces")

    if max_rows and max_rows > 0:
        original_len = len(qa_df)
        qa_df = qa_df.head(max_rows)
        print(f"🔧 Limited to {len(qa_df)} rows (from {original_len}) for faster debugging")

    if interactive and not selected_job_ids:
        selected_job_ids = await select_jobs_interactively()
        if not selected_job_ids:
            print("❌ No jobs selected. Exiting.")
            return

    if selected_job_ids:
        qa_df = await filter_qa_df_by_jobs(qa_df, selected_job_ids)
        if len(qa_df) == 0:
            print("⚠️  No traces found matching the selected job(s).")
            return

    qa_df = await attach_db_context(qa_df)

    llm = build_ollama_llm()
    if eval_types:
        print(f"✅ Using evaluators: {', '.join(eval_types)}")
    else:
        print("✅ Using all evaluators: hallucination, bias, reference")
    evaluators = build_evaluators(llm, eval_types=eval_types)

    if not evaluators:
        print("⚠️  No evaluators configured. Exiting.")
        return

    print(f"🚀 Running {len(evaluators)} evaluator(s) on {len(qa_df)} rows...")
    try:
        results_df = await async_evaluate_dataframe(
            dataframe=qa_df,
            evaluators=evaluators,
            concurrency=concurrency,
        )
        print(f"✅ Evaluations completed. Results shape: {results_df.shape}")
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Error running evaluations: {exc}")
        import traceback

        traceback.print_exc()
        return

    if results_df is None or len(results_df) == 0:
        print("⚠️  No evaluation results generated. Check the error messages above.")
        return

    output_path = output_csv_path or PROJECT_ROOT / "eval_results_with_explanations.csv"
    try:
        results_df.to_csv(output_path, index=False)
        print(f"💾 Saved evaluator outputs (labels, scores, explanations) to {output_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  Could not save evaluator outputs to CSV: {exc}")

    try:
        annotation_df = to_annotation_dataframe(dataframe=results_df)

        if annotation_df is None or len(annotation_df) == 0:
            print("⚠️  No annotations generated from results.")
            return

        print(f"✅ Generated {len(annotation_df)} annotations")
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Error converting results to annotations: {exc}")
        import traceback

        traceback.print_exc()
        return

    annotation_df = sanitize_annotation_dataframe(annotation_df, qa_df)
    if annotation_df is None or len(annotation_df) == 0:
        print("⚠️  Annotation dataframe failed validation; skipping persistence/logging.")
        return

    try:
        await persist_eval_results(annotation_df, qa_df, selected_job_ids)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  Could not persist evaluation results to DB: {exc}")
        import traceback

        traceback.print_exc()

    try:
        print("🔎 Validating annotations against Phoenix before logging...")
        validate_span_ids_against_phoenix(client, project_name, annotation_df)

        client.spans.log_span_annotations_dataframe(
            dataframe=annotation_df,
            annotator_kind="LLM",
        )
        print("✅ Logged eval annotations to Phoenix.")
        print("\nSample annotations:")
        print(annotation_df.head())
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Error logging annotations to Phoenix: {exc}")
        import traceback

        traceback.print_exc()

