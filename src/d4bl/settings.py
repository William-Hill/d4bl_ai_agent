"""
Centralized configuration for the D4BL agent services.

This keeps environment reads in one place to reduce import-time side effects
spread across modules.
"""
from __future__ import annotations

import os
from functools import lru_cache
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # LLM / Ollama
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")

    # Crawl provider
    crawl_provider: str = os.getenv("CRAWL_PROVIDER", "crawl4ai").lower()
    crawl4ai_base_url: str = os.getenv("CRAWL4AI_BASE_URL", "http://crawl4ai:11235").rstrip("/")
    crawl4ai_api_key: str | None = os.getenv("CRAWL4AI_API_KEY")
    firecrawl_api_key: str | None = os.getenv("FIRECRAWL_API_KEY")

    # Langfuse / OTLP
    langfuse_host: str = os.getenv("LANGFUSE_HOST", "http://localhost:3002")
    langfuse_otel_host: str = os.getenv("LANGFUSE_OTEL_HOST", "")
    langfuse_base_url: str = os.getenv("LANGFUSE_BASE_URL", "")
    otlp_endpoint: str = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        f"{os.getenv('LANGFUSE_OTEL_HOST', os.getenv('LANGFUSE_HOST', 'http://localhost:3002'))}/api/public/otel/v1/traces",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

