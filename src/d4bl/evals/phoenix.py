"""
Utilities for interacting with Phoenix traces and evaluation outputs.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
from phoenix.client import Client
from phoenix.client.helpers.spans import get_input_output_context


def fetch_qa_dataframe(client: Client, project_name: str | None = None) -> pd.DataFrame:
    """
    Fetch a dataframe containing input/output/context columns from Phoenix.
    """
    qa_df = get_input_output_context(client, project_name=project_name)
    if qa_df is not None and not qa_df.empty:
        print(f"✅ Found {len(qa_df)} Q&A rows with retrieval context (get_input_output_context)")
        return qa_df

    print("⚠️  No RAG-style retrieval spans found via get_input_output_context.")
    print("   Falling back to LLM spans...")

    spans_df = client.spans.get_spans_dataframe(project_name=project_name)
    if spans_df is None or spans_df.empty:
        raise RuntimeError(
            f"No spans found for project {project_name!r}. "
            "Run some agent tasks first to generate traces."
        )

    trace_col = "context.trace_id" if "context.trace_id" in spans_df.columns else "trace_id"
    span_id_col = "context.span_id" if "context.span_id" in spans_df.columns else "span_id"

    input_col = None
    output_col = None
    for col in spans_df.columns:
        lower = col.lower()
        if "input" in lower and ("value" in lower or "messages" in lower):
            input_col = col
        if "output" in lower and ("value" in lower or "messages" in lower):
            output_col = col

    if not input_col or not output_col:
        if "attributes.llm.input_messages" in spans_df.columns:
            input_col = "attributes.llm.input_messages"
        if "attributes.llm.output_messages" in spans_df.columns:
            output_col = "attributes.llm.output_messages"

    if not input_col or not output_col:
        raise RuntimeError(
            "Could not find input/output columns in spans. "
            f"Available columns: {list(spans_df.columns)}"
        )

    llm_spans = spans_df[spans_df[input_col].notna() & spans_df[output_col].notna()].copy()
    if llm_spans.empty:
        raise RuntimeError(
            f"No LLM spans with both input and output found for project {project_name!r}."
        )

    qa_df = pd.DataFrame(
        {
            "input": llm_spans[input_col].astype(str),
            "output": llm_spans[output_col].astype(str),
            trace_col: llm_spans[trace_col].astype(str),
        }
    )
    qa_df["context"] = ""
    qa_df.index = llm_spans[span_id_col].astype(str)

    print(f"✅ Built QA dataframe from LLM spans: {len(qa_df)} rows (context to be filled from DB)")
    return qa_df


def sanitize_annotation_dataframe(
    annotation_df: pd.DataFrame, qa_df: pd.DataFrame
) -> Optional[pd.DataFrame]:
    """
    Ensure the annotation dataframe has the columns Phoenix expects and prune bad rows.
    """
    if annotation_df is None or len(annotation_df) == 0:
        print("⚠️  Annotation dataframe is empty.")
        return None

    df = annotation_df.copy()

    span_col = None
    for candidate in ["context.span_id", "span_id"]:
        if candidate in df.columns:
            span_col = candidate
            break
    if span_col is None:
        print("⚠️  Annotation dataframe is missing a span_id column.")
        return None
    if span_col != "context.span_id":
        df["context.span_id"] = df[span_col]

    df["context.span_id"] = df["context.span_id"].astype(str)
    df = df.dropna(subset=["context.span_id"])
    df = df[df["context.span_id"].str.strip() != ""]

    if "context.trace_id" not in df.columns and "trace_id" in df.columns:
        df["context.trace_id"] = df["trace_id"]

    if "annotation_name" not in df.columns:
        if "name" in df.columns:
            df["annotation_name"] = df["name"]
        else:
            print("⚠️  Annotation dataframe missing annotation_name column.")
            return None

    df = df.drop_duplicates(subset=["context.span_id", "annotation_name", "label", "score"])

    if qa_df is not None and len(qa_df) > 0:
        available_span_ids = set(str(idx) for idx in qa_df.index)
        missing_mask = ~df["context.span_id"].isin(available_span_ids)
        missing_count = missing_mask.sum()
        if missing_count > 0:
            sample_missing = df.loc[missing_mask, "context.span_id"].head(5).tolist()
            print(f"⚠️  {missing_count} annotation rows reference spans not present in qa_df.")
            print(f"   Sample missing span_ids: {sample_missing}")
            df = df[~missing_mask]

    if len(df) == 0:
        print("⚠️  After sanitizing, no annotations remain.")
        return None

    unique_spans = df["context.span_id"].nunique()
    print(f"🔧 Annotation dataframe ready: {len(df)} rows across {unique_spans} unique span IDs.")
    return df


def validate_span_ids_against_phoenix(
    client: Client, project_name: str, annotation_df: pd.DataFrame, sample_size: int = 5
):
    """
    Fetch span metadata from Phoenix and warn if any annotation span_ids are unknown.
    """
    if "context.span_id" not in annotation_df.columns:
        print("⚠️  Cannot validate span IDs; column context.span_id missing.")
        return

    span_ids = list(dict.fromkeys(annotation_df["context.span_id"].tolist()))
    if not span_ids:
        print("⚠️  No span IDs to validate against Phoenix.")
        return

    try:
        spans_df = client.spans.get_spans_dataframe(project_name=project_name)
        if spans_df is None or len(spans_df) == 0:
            print("⚠️  Phoenix returned no spans during validation; ensure traces exist.")
            return

        available_ids = set()
        for col in ["context.span_id", "span_id"]:
            if col in spans_df.columns:
                available_ids.update(spans_df[col].astype(str).tolist())

        missing = [sid for sid in span_ids if sid not in available_ids]
        if missing:
            print(f"⚠️  Phoenix does not currently recognize {len(missing)} span_id(s) from the annotations.")
            print(f"   Sample missing span_ids: {missing[:sample_size]}")
        else:
            print("✅ All annotation span_ids were found in Phoenix spans.")
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  Could not validate span IDs against Phoenix: {exc}")

