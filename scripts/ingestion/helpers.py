"""Shared helpers for ingestion scripts."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import psycopg2
import psycopg2.extras

# Load .env file if python-dotenv is installed and .env exists.
# In the cloud, real env vars are used and .env is absent — this is a no-op.
try:
    from dotenv import load_dotenv
    # Walk up from scripts/ingestion/ to find .env at repo root.
    # Also check the main repo root when running from a git worktree.
    _repo_root = Path(__file__).resolve().parent.parent.parent
    _env_file = _repo_root / ".env"
    if not _env_file.is_file():
        # In a worktree, the main repo .env may be elsewhere
        import subprocess
        try:
            _main_root = subprocess.check_output(
                ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                cwd=_repo_root, stderr=subprocess.DEVNULL,
            ).decode().strip()
            # git-common-dir returns the .git dir; parent is the main repo
            _env_file = Path(_main_root).parent / ".env"
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    if _env_file.is_file():
        load_dotenv(_env_file)
except ImportError:
    pass

BATCH_SIZE = 500


def safe_float(val: object, default: float | None = None) -> float | None:
    """Convert to float, returning default on failure."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_int(val: object, default: int | None = None) -> int | None:
    """Convert to int, returning default on failure."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def make_record_id(*parts: str) -> str:
    """Generate a deterministic UUID5 from colon-joined parts."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, ":".join(parts)))


def get_db_connection() -> psycopg2.extensions.connection:
    """Get a psycopg2 connection from DAGSTER_POSTGRES_URL env var."""
    db_url = os.environ.get("DAGSTER_POSTGRES_URL")
    if not db_url:
        print("Error: Set DAGSTER_POSTGRES_URL env var", file=sys.stderr)
        sys.exit(1)
    return psycopg2.connect(db_url)


def execute_batch(
    cur: psycopg2.extensions.cursor,
    sql: str,
    params_list: list[dict],
    page_size: int = BATCH_SIZE,
) -> None:
    """Wrapper around psycopg2.extras.execute_batch."""
    psycopg2.extras.execute_batch(cur, sql, params_list, page_size=page_size)


def upsert_batch(
    conn: psycopg2.extensions.connection,
    sql: str,
    records: list[dict],
) -> int:
    """Upsert records in BATCH_SIZE chunks with a single commit.

    Returns total records upserted.
    """
    total = 0
    with conn.cursor() as cur:
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i : i + BATCH_SIZE]
            execute_batch(cur, sql, batch)
            total += len(batch)
    conn.commit()
    return total


STATE_FIPS = {
    "01": "Alabama", "02": "Alaska", "04": "Arizona",
    "05": "Arkansas", "06": "California", "08": "Colorado",
    "09": "Connecticut", "10": "Delaware",
    "11": "District of Columbia", "12": "Florida",
    "13": "Georgia", "15": "Hawaii", "16": "Idaho",
    "17": "Illinois", "18": "Indiana", "19": "Iowa",
    "20": "Kansas", "21": "Kentucky", "22": "Louisiana",
    "23": "Maine", "24": "Maryland", "25": "Massachusetts",
    "26": "Michigan", "27": "Minnesota", "28": "Mississippi",
    "29": "Missouri", "30": "Montana", "31": "Nebraska",
    "32": "Nevada", "33": "New Hampshire", "34": "New Jersey",
    "35": "New Mexico", "36": "New York",
    "37": "North Carolina", "38": "North Dakota",
    "39": "Ohio", "40": "Oklahoma", "41": "Oregon",
    "42": "Pennsylvania", "44": "Rhode Island",
    "45": "South Carolina", "46": "South Dakota",
    "47": "Tennessee", "48": "Texas", "49": "Utah",
    "50": "Vermont", "51": "Virginia", "53": "Washington",
    "54": "West Virginia", "55": "Wisconsin", "56": "Wyoming",
}
