import os
from urllib.parse import quote_plus

from dagster import ResourceDefinition


def get_db_url() -> str:
    """Build async PostgreSQL connection URL from environment variables."""
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "postgres")
    db = os.environ.get("POSTGRES_DB", "postgres")
    return f"postgresql+asyncpg://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{db}"


def get_resources() -> dict[str, ResourceDefinition]:
    """Return the shared Dagster resources for all pipelines."""
    return {
        "db_url": ResourceDefinition.hardcoded_resource(get_db_url()),
    }
