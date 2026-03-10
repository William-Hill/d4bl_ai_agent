import logging
import os
from urllib.parse import quote_plus

from dagster import ResourceDefinition

logger = logging.getLogger(__name__)


def get_db_url() -> str:
    """Build async PostgreSQL connection URL from environment variables."""
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "postgres")
    db = os.environ.get("POSTGRES_DB", "postgres")
    return f"postgresql+asyncpg://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{db}"


def _get_langfuse_client():
    """Create a Langfuse client if credentials are configured."""
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    host = os.environ.get("LANGFUSE_HOST")

    if not (public_key and secret_key):
        logger.info("Langfuse credentials not configured, tracing disabled")
        return None

    try:
        from langfuse import Langfuse

        return Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )
    except ImportError:
        logger.warning("langfuse package not installed, tracing disabled")
        return None
    except Exception as exc:
        logger.warning("Failed to initialise Langfuse: %s", exc, exc_info=True)
        return None


def get_resources() -> dict[str, ResourceDefinition]:
    """Return the shared Dagster resources for all pipelines."""
    return {
        "db_url": ResourceDefinition.hardcoded_resource(get_db_url()),
        "langfuse": ResourceDefinition.hardcoded_resource(
            _get_langfuse_client()
        ),
    }
