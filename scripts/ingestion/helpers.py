"""Shared helpers for ingestion scripts."""

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
