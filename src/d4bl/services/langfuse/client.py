from __future__ import annotations

import os
import logging
from typing import Optional

from d4bl.settings import get_settings

try:  # Optional dependency: degrade gracefully when Langfuse is not installed
    from langfuse import Langfuse  # type: ignore
except ImportError:  # pragma: no cover - handled at runtime
    Langfuse = None  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)
_langfuse_client: Optional[Langfuse] = None


def get_langfuse_eval_client() -> Optional[Langfuse]:
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
        langfuse_host = get_settings().langfuse_host

        logger.debug("Initializing Langfuse client - Host: %s", langfuse_host)

        if not langfuse_public_key or not langfuse_secret_key:
            logger.warning("Langfuse credentials not found. Evaluations will be disabled.")
            logger.debug("LANGFUSE_PUBLIC_KEY present: %s", bool(langfuse_public_key))
            logger.debug("LANGFUSE_SECRET_KEY present: %s", bool(langfuse_secret_key))
            return None

        # Adjust host for Docker
        if get_settings().is_docker and "localhost" in langfuse_host:
            original_host = langfuse_host
            langfuse_host = langfuse_host.replace("localhost", "langfuse-web")
            if ":3002" in langfuse_host:
                langfuse_host = langfuse_host.replace(":3002", ":3000")
            logger.debug("Adjusted host for Docker: %s -> %s", original_host, langfuse_host)

        _langfuse_client = Langfuse(
            public_key=langfuse_public_key,
            secret_key=langfuse_secret_key,
            host=langfuse_host,
        )
        logger.info("✅ Langfuse evaluation client initialized successfully")
        logger.debug("Langfuse client configured with host: %s", langfuse_host)
        return _langfuse_client
    except Exception as e:  # pragma: no cover - defensive
        logger.error("Failed to initialize Langfuse client: %s", e, exc_info=True)
        logger.debug("Exception type: %s", type(e).__name__)
        return None
