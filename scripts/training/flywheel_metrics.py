"""Flywheel metrics: query document, training, and research quality stats.

Usage:
    python -m scripts.training.flywheel_metrics
    python -m scripts.training.flywheel_metrics --json
"""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_corpus_stats(rows: list[dict]) -> dict:
    """Build corpus stats from document_chunks aggregation rows.

    Args:
        rows: List of dicts with content_type, chunk_count, total_tokens.

    Returns:
        Dict with total_documents, total_tokens, and content_types breakdown.
    """
    content_types: dict[str, int] = {}
    total_docs = 0
    total_tokens = 0

    for row in rows:
        ct = row["content_type"]
        count = row["chunk_count"]
        tokens = row["total_tokens"]
        content_types[ct] = count
        total_docs += count
        total_tokens += tokens

    return {
        "total_documents": total_docs,
        "total_tokens": total_tokens,
        "content_types": content_types,
    }


def corpus_stats_for_training(conn: Any) -> dict:
    """Generate corpus composition stats for tagging a training run.

    Returns a dict suitable for embedding in model_eval_runs.metrics:
    {
        "corpus_version": "v3.0",
        "corpus_stats": {
            "structured_passages": <int>,
            "unstructured_passages": <int>,
            "content_types": {"research_report": N, "policy_bill": N, ...},
            "total_tokens": <int>,
        }
    }
    """
    import psycopg2.extras

    doc_stats = query_corpus_metrics(conn)

    # Count structured passages from existing extractors
    structured_tables = [
        "census_indicators", "cdc_health_outcomes", "epa_environmental_justice",
        "police_violence_incidents", "bjs_incarceration", "fbi_crime_stats",
    ]
    structured_count = 0
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        for table in structured_tables:
            try:
                cur.execute(
                    f"SELECT COUNT(*) AS cnt FROM {table}"  # noqa: S608
                )
                structured_count += cur.fetchone()["cnt"]
            except Exception:
                pass

    return {
        "corpus_version": "v3.0",
        "corpus_stats": {
            "structured_passages": structured_count,
            "unstructured_passages": doc_stats["total_documents"],
            "content_types": doc_stats["content_types"],
            "total_tokens": doc_stats["total_tokens"],
        },
    }


def query_corpus_metrics(conn: Any) -> dict:
    """Query document corpus statistics from the database."""
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT d.content_type,
                   COUNT(dc.id) AS chunk_count,
                   COALESCE(SUM(dc.token_count), 0) AS total_tokens
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            GROUP BY d.content_type
            ORDER BY chunk_count DESC
        """)
        rows = [dict(r) for r in cur.fetchall()]

    return build_corpus_stats(rows)


def query_training_metrics(conn: Any) -> list[dict]:
    """Query model evaluation runs ordered by version."""
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT model_version, task, metrics, ship_decision, created_at
            FROM model_eval_runs
            ORDER BY created_at DESC
            LIMIT 20
        """)
        return [dict(r) for r in cur.fetchall()]


def query_research_quality(conn: Any) -> dict:
    """Query average evaluation scores across recent completed jobs."""
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT eval_name, AVG(score) AS avg_score, COUNT(*) AS eval_count
            FROM evaluation_results
            WHERE score IS NOT NULL
            GROUP BY eval_name
            ORDER BY eval_name
        """)
        rows = [dict(r) for r in cur.fetchall()]

    return {row["eval_name"]: {"avg_score": float(row["avg_score"]),
                                "count": int(row["eval_count"])} for row in rows}


def main(as_json: bool = False) -> dict:
    """Collect and display all flywheel metrics."""
    from scripts.ingestion.helpers import get_db_connection

    conn = get_db_connection()
    try:
        corpus = query_corpus_metrics(conn)
        training = query_training_metrics(conn)
        research = query_research_quality(conn)
    finally:
        conn.close()

    metrics = {
        "corpus": corpus,
        "training_runs": training,
        "research_quality": research,
    }

    if as_json:
        print(json.dumps(metrics, indent=2, default=str))
    else:
        print("\n=== D4BL Data Flywheel Metrics ===\n")
        print("1. Corpus (Documents In)")
        print(f"   Total chunks: {corpus['total_documents']}")
        print(f"   Total tokens: {corpus['total_tokens']:,}")
        for ct, count in corpus["content_types"].items():
            print(f"     {ct}: {count}")

        print("\n2. Training (Model Quality)")
        for run in training[:5]:
            print(f"   {run['model_version']} / {run['task']}: {run['ship_decision']}")

        print("\n3. Research Quality")
        for name, data in research.items():
            print(f"   {name}: avg={data['avg_score']:.2f} (n={data['count']})")

    return metrics


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Display D4BL data flywheel metrics.")
    parser.add_argument("--json", action="store_true", help="Output as JSON.")
    args = parser.parse_args()
    main(as_json=args.json)
