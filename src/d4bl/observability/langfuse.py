from __future__ import annotations

import os
import logging

from d4bl.settings import get_settings

logger = logging.getLogger(__name__)

_langfuse_initialized = False
_langfuse_client = None


def initialize_langfuse():
    """Initialize Langfuse observability and CrewAI instrumentation."""
    global _langfuse_initialized, _langfuse_client

    if _langfuse_initialized:
        return _langfuse_client

    try:
        from langfuse import get_client
        from openinference.instrumentation.crewai import CrewAIInstrumentor

        settings = get_settings()

        langfuse_public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        langfuse_secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        langfuse_host = settings.langfuse_host
        langfuse_base_url = settings.langfuse_base_url or settings.langfuse_host
        langfuse_otel_host = settings.langfuse_otel_host or langfuse_host
        otlp_endpoint = os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            f"{langfuse_otel_host}/api/public/otel/v1/traces",
        )

        # If running in Docker, ensure BASE_URL uses service name and internal port
        if os.path.exists("/.dockerenv"):
            if "localhost" in langfuse_base_url or ":3002" in langfuse_base_url:
                langfuse_base_url = langfuse_host

        # Set environment variables if not already set
        if langfuse_public_key and not os.getenv("LANGFUSE_PUBLIC_KEY"):
            os.environ["LANGFUSE_PUBLIC_KEY"] = langfuse_public_key
        if langfuse_secret_key and not os.getenv("LANGFUSE_SECRET_KEY"):
            os.environ["LANGFUSE_SECRET_KEY"] = langfuse_secret_key
        if not os.getenv("LANGFUSE_HOST"):
            os.environ["LANGFUSE_HOST"] = langfuse_host
        if os.path.exists("/.dockerenv"):
            os.environ["LANGFUSE_BASE_URL"] = langfuse_base_url
        elif not os.getenv("LANGFUSE_BASE_URL"):
            os.environ["LANGFUSE_BASE_URL"] = langfuse_base_url

        # Initialize Langfuse client
        _langfuse_client = get_client()

        # Best-effort auth check
        try:
            if _langfuse_client.auth_check():
                print("✅ Langfuse client authenticated and ready!")
            else:
                print("⚠️ Langfuse authentication failed. Check credentials/host.")
                print(f"   LANGFUSE_HOST: {langfuse_host}")
                print(f"   LANGFUSE_BASE_URL: {langfuse_base_url}")
        except Exception as auth_error:
            print(f"⚠️ Langfuse auth check failed: {auth_error}")
            print(f"   LANGFUSE_HOST: {langfuse_host}")
            print(f"   LANGFUSE_BASE_URL: {langfuse_base_url}")

        current_otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        current_traces_endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")

        if not current_otlp_endpoint:
            os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = otlp_endpoint
            os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = otlp_endpoint
            print(f"⚠️  OTLP endpoint was not set! Forced to: {otlp_endpoint}")
        else:
            print(f"✓ OTLP endpoint configured: {current_otlp_endpoint}")
            if current_otlp_endpoint != otlp_endpoint:
                print("⚠️  WARNING: OTLP endpoint mismatch!")
                print(f"   Expected: {otlp_endpoint}")
                print(f"   Actual: {current_otlp_endpoint}")

        CrewAIInstrumentor().instrument(skip_dep_check=True)
        print("✅ CrewAI instrumentation initialized")

        _langfuse_initialized = True
        print("✅ CrewAI instrumentation initialized for Langfuse observability")
        print(f"   Langfuse Host: {langfuse_host}")
        print(f"   View traces at: {langfuse_base_url}")

        return _langfuse_client
    except ImportError as e:
        print(f"⚠️ Langfuse dependencies not installed: {e}")
        print("   Install with: pip install langfuse openinference-instrumentation-crewai")
        _langfuse_initialized = False
        return None
    except Exception as e:
        print(f"⚠️ Error initializing Langfuse: {e}")
        import traceback

        traceback.print_exc()
        _langfuse_initialized = False
        return None


def get_langfuse_client():
    """Get the initialized Langfuse client, initializing if necessary."""
    global _langfuse_client
    if _langfuse_client is None:
        _langfuse_client = initialize_langfuse()
    return _langfuse_client

