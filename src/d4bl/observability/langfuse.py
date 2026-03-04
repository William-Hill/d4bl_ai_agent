from __future__ import annotations

import os
import logging

from d4bl.settings import get_settings

logger = logging.getLogger(__name__)

_langfuse_init_state: bool | None = None  # None=untried, True=ok, False=failed
_langfuse_client = None


def _resolve_langfuse_host(host: str, is_docker: bool) -> str:
    """Adjust a Langfuse host for Docker if needed.

    Replaces localhost with the Docker service name (langfuse-web)
    and adjusts port 3002 to 3000 (internal Docker port).
    """
    if is_docker and "localhost" in host:
        host = host.replace("localhost", "langfuse-web")
        if ":3002" in host:
            host = host.replace(":3002", ":3000")
    return host


def check_langfuse_service_available(host: str, timeout: float = 3.0) -> bool:
    """Check if Langfuse service is reachable via HTTP GET."""
    import urllib.request

    try:
        resp = urllib.request.urlopen(f"{host}/api/public/health", timeout=timeout)
        resp.close()
        return True
    except Exception:
        return False


def initialize_langfuse() -> object | None:
    """Initialize Langfuse observability and CrewAI instrumentation."""
    global _langfuse_init_state, _langfuse_client

    if _langfuse_init_state is not None:
        return _langfuse_client

    try:
        from langfuse import get_client
        from openinference.instrumentation.crewai import CrewAIInstrumentor

        settings = get_settings()

        langfuse_host = settings.langfuse_host
        langfuse_base_url = settings.langfuse_base_url or settings.langfuse_host
        langfuse_otel_host = settings.langfuse_otel_host or langfuse_host
        otlp_endpoint = os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            f"{langfuse_otel_host}/api/public/otel/v1/traces",
        )

        # If running in Docker, ensure BASE_URL uses service name and internal port
        if settings.is_docker:
            if "localhost" in langfuse_base_url or ":3002" in langfuse_base_url:
                langfuse_base_url = langfuse_host

        # Set environment variables if not already set
        if not os.getenv("LANGFUSE_HOST"):
            os.environ["LANGFUSE_HOST"] = langfuse_host
        if settings.is_docker:
            os.environ["LANGFUSE_BASE_URL"] = langfuse_base_url
        elif not os.getenv("LANGFUSE_BASE_URL"):
            os.environ["LANGFUSE_BASE_URL"] = langfuse_base_url

        # Initialize Langfuse client
        _langfuse_client = get_client()

        # Best-effort auth check
        try:
            if _langfuse_client.auth_check():
                logger.info("Langfuse client authenticated and ready")
            else:
                logger.warning("Langfuse authentication failed. Check credentials/host.")
                logger.debug("LANGFUSE_HOST: %s", langfuse_host)
                logger.debug("LANGFUSE_BASE_URL: %s", langfuse_base_url)
        except Exception as auth_error:
            logger.warning("Langfuse auth check failed: %s", auth_error)
            logger.debug("LANGFUSE_HOST: %s", langfuse_host)
            logger.debug("LANGFUSE_BASE_URL: %s", langfuse_base_url)

        current_otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

        if not current_otlp_endpoint:
            os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = otlp_endpoint
            os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = otlp_endpoint
            logger.warning("OTLP endpoint was not set, forced to: %s", otlp_endpoint)
        else:
            logger.info("OTLP endpoint configured: %s", current_otlp_endpoint)
            if current_otlp_endpoint != otlp_endpoint:
                logger.warning(
                    "OTLP endpoint mismatch: expected %s, actual %s",
                    otlp_endpoint,
                    current_otlp_endpoint,
                )

        CrewAIInstrumentor().instrument(skip_dep_check=True)

        _langfuse_init_state = True
        logger.info("CrewAI instrumentation initialized for Langfuse observability")
        logger.debug("Langfuse Host: %s", langfuse_host)
        logger.debug("View traces at: %s", langfuse_base_url)

        return _langfuse_client
    except ImportError as e:
        logger.warning("Langfuse dependencies not installed: %s", e)
        logger.debug(
            "Install with: pip install langfuse openinference-instrumentation-crewai"
        )
        _langfuse_init_state = False
        return None
    except Exception as e:
        logger.error("Error initializing Langfuse: %s", e, exc_info=True)
        _langfuse_init_state = False
        return None


def get_langfuse_client() -> object | None:
    """Get the initialized Langfuse client, initializing if necessary."""
    global _langfuse_client
    if _langfuse_init_state is None:
        _langfuse_client = initialize_langfuse()
    return _langfuse_client

