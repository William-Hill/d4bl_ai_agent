"""One-time migration script to populate documents + document_chunks from existing data.

Migrates content from:
  - policy_bills        -> documents (content_type='policy_bill')
  - research_jobs       -> documents (content_type='research_report')
  - scraped_content_vectors -> documents (content_type='scraped_web', preserving embeddings)

Usage:
    DATABASE_URL=postgresql://... python scripts/training/migrate_documents.py
    DATABASE_URL=postgresql://... python scripts/training/migrate_documents.py --dry-run
    DATABASE_URL=postgresql://... python scripts/training/migrate_documents.py --sources policy_bills,research_jobs
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.extras

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from training.chunker import chunk_text
from training.embedder import format_embedding_for_pg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pure transformation helpers (unit-testable, no DB access)
# ---------------------------------------------------------------------------


def policy_bill_to_document(bill: dict[str, Any]) -> dict[str, Any]:
    """Convert a policy_bills row dict to a document dict.

    Returns a dict with keys:
        title, content_type, source_url, source_key, metadata, extraction_metadata, text.
    """
    topic_tags = bill.get("topic_tags") or []
    # topic_tags may be a JSON string from psycopg2 depending on column type
    if isinstance(topic_tags, str):
        try:
            topic_tags = json.loads(topic_tags)
        except (ValueError, TypeError):
            topic_tags = []

    return {
        "title": bill.get("title") or "",
        "content_type": "policy_bill",
        "source_url": bill.get("url") or None,
        "source_key": "openstates",
        "metadata": {
            "state": bill.get("state"),
            "status": bill.get("status"),
            "topic_tags": topic_tags,
            "session": bill.get("session"),
            "bill_number": bill.get("bill_number"),
        },
        "extraction_metadata": {},
        "text": bill.get("summary") or "",
    }


def extract_research_job_text(
    result: dict[str, Any] | None,
    research_data: dict[str, Any] | None,
) -> str:
    """Extract narrative text from research job JSON fields.

    Checks result for keys: final_report, summary, report, output.
    Checks research_data for key: research_findings.
    Returns combined non-empty parts joined by newlines, or empty string.
    """
    parts: list[str] = []

    if result and isinstance(result, dict):
        for key in ("final_report", "summary", "report", "output"):
            val = result.get(key)
            if val and isinstance(val, str) and val.strip():
                parts.append(val.strip())
                break  # use first match only from result

    if research_data and isinstance(research_data, dict):
        val = research_data.get("research_findings")
        if val and isinstance(val, str) and val.strip():
            parts.append(val.strip())

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# DB migration helpers
# ---------------------------------------------------------------------------

_INSERT_DOCUMENT_SQL = """
    INSERT INTO documents
        (title, source_url, content_type, source_key, job_id,
         extraction_metadata, metadata)
    VALUES
        (%(title)s, %(source_url)s, %(content_type)s, %(source_key)s,
         CAST(%(job_id)s AS UUID),
         CAST(%(extraction_metadata)s AS JSONB),
         CAST(%(metadata)s AS JSONB))
    ON CONFLICT (source_url) WHERE source_url IS NOT NULL
    DO NOTHING
    RETURNING id
"""

_INSERT_DOCUMENT_NO_URL_SQL = """
    INSERT INTO documents
        (title, content_type, source_key, job_id,
         extraction_metadata, metadata)
    VALUES
        (%(title)s, %(content_type)s, %(source_key)s,
         CAST(%(job_id)s AS UUID),
         CAST(%(extraction_metadata)s AS JSONB),
         CAST(%(metadata)s AS JSONB))
    RETURNING id
"""

_INSERT_CHUNK_SQL = """
    INSERT INTO document_chunks
        (document_id, content, chunk_index, token_count, metadata)
    VALUES
        (CAST(%(document_id)s AS UUID), %(content)s, %(chunk_index)s,
         %(token_count)s, CAST(%(metadata)s AS JSONB))
    ON CONFLICT (document_id, chunk_index) DO NOTHING
"""

_INSERT_CHUNK_WITH_EMBEDDING_SQL = """
    INSERT INTO document_chunks
        (document_id, content, chunk_index, token_count, embedding, metadata)
    VALUES
        (CAST(%(document_id)s AS UUID), %(content)s, %(chunk_index)s,
         %(token_count)s, CAST(%(embedding)s AS vector),
         CAST(%(metadata)s AS JSONB))
    ON CONFLICT (document_id, chunk_index) DO NOTHING
"""


def _insert_document_and_chunks(
    cur: psycopg2.extensions.cursor,
    title: str,
    content_type: str,
    source_url: str | None,
    source_key: str | None,
    job_id: str | None,
    extraction_metadata: dict,
    metadata: dict,
    text: str,
    target_tokens: int = 500,
    embedding: str | None = None,
) -> int:
    """Insert one document row and its chunks. Returns 1 if inserted, 0 if skipped."""
    params = {
        "title": title,
        "content_type": content_type,
        "source_url": source_url,
        "source_key": source_key,
        "job_id": job_id,
        "extraction_metadata": json.dumps(extraction_metadata),
        "metadata": json.dumps(metadata),
    }

    if source_url:
        cur.execute(_INSERT_DOCUMENT_SQL, params)
    else:
        # No unique constraint applies — always insert
        cur.execute(_INSERT_DOCUMENT_NO_URL_SQL, params)

    row = cur.fetchone()
    if not row:
        # ON CONFLICT DO NOTHING — document already exists, skip chunks too
        return 0

    document_id = str(row[0])
    chunks = chunk_text(text, target_tokens=target_tokens)

    if not chunks and text:
        # Non-empty text that didn't chunk (very short) — create one chunk
        chunks = [{
            "content": text,
            "chunk_index": 0,
            "token_count": max(1, len(text.split())),
            "metadata": {"boundary": "end"},
        }]

    for chunk in chunks:
        chunk_params = {
            "document_id": document_id,
            "content": chunk["content"],
            "chunk_index": chunk["chunk_index"],
            "token_count": chunk["token_count"],
            "metadata": json.dumps(chunk.get("metadata", {})),
        }
        if embedding is not None:
            chunk_params["embedding"] = embedding
            cur.execute(_INSERT_CHUNK_WITH_EMBEDDING_SQL, chunk_params)
        else:
            cur.execute(_INSERT_CHUNK_SQL, chunk_params)

    return 1


def _migrate_policy_bills(
    conn: psycopg2.extensions.connection,
    dry_run: bool = False,
) -> int:
    """Migrate policy_bills rows into documents + document_chunks.

    Returns count of documents inserted.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT id, title, summary, state, status, topic_tags,
                   session, url, bill_number
            FROM policy_bills
        """)
        bills = cur.fetchall()

    logger.info("Found %d policy bills to migrate", len(bills))
    if dry_run:
        logger.info("[dry-run] Would migrate %d policy bills", len(bills))
        return len(bills)

    inserted = 0
    with conn.cursor() as cur:
        for bill in bills:
            doc = policy_bill_to_document(dict(bill))
            inserted += _insert_document_and_chunks(
                cur=cur,
                title=doc["title"],
                content_type=doc["content_type"],
                source_url=doc["source_url"],
                source_key=doc["source_key"],
                job_id=None,
                extraction_metadata=doc["extraction_metadata"],
                metadata=doc["metadata"],
                text=doc["text"],
            )
    conn.commit()
    logger.info("Inserted %d policy bill documents", inserted)
    return inserted


def _migrate_research_jobs(
    conn: psycopg2.extensions.connection,
    dry_run: bool = False,
) -> int:
    """Migrate completed research_jobs rows into documents + document_chunks.

    Returns count of documents inserted.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT job_id, query, result, research_data, created_at
            FROM research_jobs
            WHERE status = 'completed'
        """)
        jobs = cur.fetchall()

    logger.info("Found %d completed research jobs to migrate", len(jobs))
    if dry_run:
        logger.info("[dry-run] Would migrate %d research jobs", len(jobs))
        return len(jobs)

    inserted = 0
    with conn.cursor() as cur:
        for job in jobs:
            result = job.get("result")
            research_data = job.get("research_data")

            # result/research_data may be stored as JSON strings
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except (ValueError, TypeError):
                    result = {"final_report": result}
            if isinstance(research_data, str):
                try:
                    research_data = json.loads(research_data)
                except (ValueError, TypeError):
                    research_data = None

            text = extract_research_job_text(result, research_data)
            if not text:
                continue

            query = job.get("query") or ""
            job_id = str(job["job_id"]) if job.get("job_id") else None

            inserted += _insert_document_and_chunks(
                cur=cur,
                title=query[:200] if query else "Research Report",
                content_type="research_report",
                source_url=None,
                source_key="research_jobs",
                job_id=job_id,
                extraction_metadata={},
                metadata={"query": query},
                text=text,
            )
    conn.commit()
    logger.info("Inserted %d research job documents", inserted)
    return inserted


def _migrate_scraped_content(
    conn: psycopg2.extensions.connection,
    dry_run: bool = False,
) -> int:
    """Migrate scraped_content_vectors rows into documents + document_chunks.

    Embeddings are transferred as-is (no re-computation).
    Returns count of documents inserted.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT id, job_id, url, content, content_type, metadata, embedding
            FROM scraped_content_vectors
        """)
        rows = cur.fetchall()

    logger.info("Found %d scraped content rows to migrate", len(rows))
    if dry_run:
        logger.info("[dry-run] Would migrate %d scraped content rows", len(rows))
        return len(rows)

    inserted = 0
    with conn.cursor() as cur:
        for row in rows:
            content = row.get("content") or ""
            url = row.get("url") or None
            job_id = str(row["job_id"]) if row.get("job_id") else None
            embedding = row.get("embedding")

            row_meta = row.get("metadata") or {}
            if isinstance(row_meta, str):
                try:
                    row_meta = json.loads(row_meta)
                except (ValueError, TypeError):
                    row_meta = {}

            content_type = row.get("content_type") or "scraped_web"

            # Convert embedding to pgvector literal string if it's a list
            embedding_str: str | None = None
            if embedding is not None:
                if isinstance(embedding, (list, tuple)):
                    embedding_str = format_embedding_for_pg(embedding)
                elif isinstance(embedding, str):
                    embedding_str = embedding

            inserted += _insert_document_and_chunks(
                cur=cur,
                title=url or "Scraped Content",
                content_type=content_type,
                source_url=url,
                source_key="scraped_content_vectors",
                job_id=job_id,
                extraction_metadata={},
                metadata=row_meta,
                text=content,
                target_tokens=500,
                embedding=embedding_str,
            )
    conn.commit()
    logger.info("Inserted %d scraped content documents", inserted)
    return inserted


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

ALL_SOURCES: dict[str, Any] = {
    "policy_bills": _migrate_policy_bills,
    "research_jobs": _migrate_research_jobs,
    "scraped_content": _migrate_scraped_content,
}


def main(sources: list[str], dry_run: bool = False) -> None:
    """Run document migration for specified sources."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    from ingestion.helpers import get_db_connection

    conn = get_db_connection()
    try:
        for source in sources:
            fn = ALL_SOURCES.get(source)
            if fn is None:
                logger.warning("Unknown source: %s — skipping", source)
                continue
            logger.info("Migrating source: %s%s", source, " [dry-run]" if dry_run else "")
            count = fn(conn, dry_run=dry_run)
            logger.info("Source %s: %d documents processed", source, count)
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate existing data into documents + document_chunks tables."
    )
    parser.add_argument(
        "--sources",
        default=",".join(ALL_SOURCES.keys()),
        help=f"Comma-separated list of sources to migrate. "
             f"Available: {', '.join(ALL_SOURCES.keys())}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview counts without writing to DB.",
    )
    args = parser.parse_args()

    requested = [s.strip() for s in args.sources.split(",") if s.strip()]
    main(sources=requested, dry_run=args.dry_run)
