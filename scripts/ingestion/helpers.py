"""Shared helpers for ingestion scripts."""

import os
import sys
import uuid

import psycopg2
import psycopg2.extras

BATCH_SIZE = 500


def safe_float(val, default=None):
    """Convert to float, returning default on failure."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_int(val, default=None):
    """Convert to int, returning default on failure."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def make_record_id(*parts: str) -> str:
    """Generate a deterministic UUID5 from colon-joined parts."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, ":".join(parts)))


def get_db_connection():
    """Get a psycopg2 connection from DAGSTER_POSTGRES_URL env var."""
    db_url = os.environ.get("DAGSTER_POSTGRES_URL")
    if not db_url:
        print("Error: Set DAGSTER_POSTGRES_URL env var", file=sys.stderr)
        sys.exit(1)
    return psycopg2.connect(db_url)


def execute_batch(cur, sql, params_list, page_size=BATCH_SIZE):
    """Wrapper around psycopg2.extras.execute_batch."""
    psycopg2.extras.execute_batch(cur, sql, params_list, page_size=page_size)
