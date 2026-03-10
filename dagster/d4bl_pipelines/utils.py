"""Shared utilities for D4BL data ingestion pipelines."""

import hashlib
import json
import re
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker


def slugify(name: str, fallback: str = "unnamed_source") -> str:
    """Convert a human-readable name to a valid Dagster asset name."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug or fallback


def derive_record_key(record: Any, index: int, source_id: str) -> str:
    """Derive a stable key for a record.

    Priority: record["id"] > record["key"] > content hash fallback.
    """
    if isinstance(record, dict):
        if "id" in record:
            return str(record["id"])
        if "key" in record:
            return str(record["key"])
    content = json.dumps(record, sort_keys=True, default=str)
    return hashlib.sha256(
        f"{source_id}:{index}:{content}".encode()
    ).hexdigest()[:16]


def compute_content_hash(data: Any) -> str:
    """Compute a SHA-256 content hash (first 32 hex chars)."""
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, default=str).encode()
    ).hexdigest()[:32]


@asynccontextmanager
async def db_session(db_url: str):
    """Async context manager for a SQLAlchemy session with engine lifecycle."""
    engine = create_async_engine(db_url, pool_size=3, max_overflow=5)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            yield session
    finally:
        await engine.dispose()


def flush_langfuse(langfuse, trace, records_ingested=0, extra_metadata=None):
    """Best-effort Langfuse trace finalization."""
    try:
        if trace:
            metadata = {"records_ingested": records_ingested}
            if extra_metadata:
                metadata.update(extra_metadata)
            trace.update(metadata=metadata)
        if langfuse:
            langfuse.flush()
    except Exception:
        pass


# Shared SQL for ingested_records upsert
INGESTED_RECORDS_UPSERT_SQL = """
    INSERT INTO ingested_records
        (id, source_id, record_key, data, content_hash, ingested_at)
    VALUES
        (CAST(:id AS UUID), CAST(:source_id AS UUID),
         :record_key, CAST(:data AS JSONB),
         :content_hash, :ingested_at)
    ON CONFLICT (source_id, record_key)
    DO UPDATE SET
        data = CAST(:data AS JSONB),
        content_hash = :content_hash,
        ingested_at = :ingested_at
"""
