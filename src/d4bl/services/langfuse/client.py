from __future__ import annotations

import logging
import os

from d4bl.observability.langfuse import resolve_langfuse_host
from d4bl.settings import get_settings

try:  # Optional dependency: degrade gracefully when Langfuse is not installed
    from langfuse import Langfuse  # type: ignore
except ImportError:  # pragma: no cover - handled at runtime
    Langfuse = None  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)
_langfuse_client: Langfuse | None = None


def get_langfuse_eval_client() -> Langfuse | None:
    """Get or initialize Langfuse client for evaluations."""
    global _langfuse_client
    if _langfuse_client is not None:
        return _langfuse_client

    try:
        if Langfuse is None:
            logger.warning("Langfuse SDK not installed. Evaluations will be disabled.")
            return None
        langfuse_public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        langfuse_secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        settings = get_settings()
        langfuse_host = resolve_langfuse_host(settings.langfuse_host, settings.is_docker)

        logger.debug("Initializing Langfuse client - Host: %s", langfuse_host)

        if not langfuse_public_key or not langfuse_secret_key:
            logger.warning("Langfuse credentials not found. Evaluations will be disabled.")
            logger.debug("LANGFUSE_PUBLIC_KEY present: %s", bool(langfuse_public_key))
            logger.debug("LANGFUSE_SECRET_KEY present: %s", bool(langfuse_secret_key))
            return None

        _langfuse_client = Langfuse(
            public_key=langfuse_public_key,
            secret_key=langfuse_secret_key,
            host=langfuse_host,
            timeout=15,
        )
        logger.info("✅ Langfuse evaluation client initialized successfully")
        logger.debug("Langfuse client configured with host: %s", langfuse_host)
        return _langfuse_client
    except Exception as e:  # pragma: no cover - defensive
        logger.error("Failed to initialize Langfuse client: %s", e, exc_info=True)
        logger.debug("Exception type: %s", type(e).__name__)
        return None