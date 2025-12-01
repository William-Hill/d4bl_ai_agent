"""
Helper functions for running Phoenix evaluations.
"""
from .llm import build_ollama_llm, build_evaluators
from .phoenix import (
    fetch_qa_dataframe,
    sanitize_annotation_dataframe,
    validate_span_ids_against_phoenix,
)
from .jobs import (
    attach_db_context,
    filter_qa_df_by_jobs,
    list_available_jobs,
    match_trace_to_job_id,
    persist_eval_results,
    select_jobs_interactively,
)
from .runner import run_evals_and_log

__all__ = [
    "attach_db_context",
    "build_evaluators",
    "build_ollama_llm",
    "fetch_qa_dataframe",
    "filter_qa_df_by_jobs",
    "list_available_jobs",
    "match_trace_to_job_id",
    "persist_eval_results",
    "run_evals_and_log",
    "sanitize_annotation_dataframe",
    "select_jobs_interactively",
    "validate_span_ids_against_phoenix",
]

