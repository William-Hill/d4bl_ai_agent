"""
Centralized configuration for the D4BL agent services.

All environment reads happen at instantiation time (inside ``__post_init__``),
not at class-definition time.  Combined with the ``@lru_cache`` on
``get_settings()``, this means values are resolved once on first call and
frozen thereafter -- but *after* the caller has had a chance to populate
the environment.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

_OTEL_SUFFIX = "/api/public/otel/v1/traces"


@dataclass(frozen=True)
class Settings:
    """Centralized env-based configuration.  All reads happen at instantiation."""

    # -- Environment --
    is_docker: bool = field(init=False)

    # -- LLM / Ollama --
    ollama_base_url: str = field(init=False)
    ollama_model: str = field(init=False)

    # -- Crawl provider --
    crawl_provider: str = field(init=False)
    crawl4ai_base_url: str = field(init=False)
    crawl4ai_api_key: str | None = field(init=False)
    firecrawl_api_key: str | None = field(init=False)
    firecrawl_base_url: str | None = field(init=False)

    # -- Langfuse / OTLP --
    langfuse_host: str = field(init=False)
    langfuse_otel_host: str = field(init=False)
    langfuse_base_url: str = field(init=False)
    otlp_endpoint: str = field(init=False)

    # -- Database --
    postgres_user: str = field(init=False)
    postgres_password: str = field(init=False)
    postgres_host: str = field(init=False)
    postgres_port: int = field(init=False)
    postgres_db: str = field(init=False)
    db_echo: bool = field(init=False)

    # -- CORS --
    cors_allowed_origins: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        def _set(name: str, value: object) -> None:
            object.__setattr__(self, name, value)

        # Environment
        _set(
            "is_docker",
            os.path.exists("/.dockerenv")
            or os.getenv("DOCKER_CONTAINER", "").strip().lower()
            in {"1", "true", "yes", "on"},
        )

        # LLM / Ollama
        _set(
            "ollama_base_url",
            os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
        )
        _set("ollama_model", os.getenv("OLLAMA_MODEL", "mistral"))

        # Crawl provider
        _set("crawl_provider", os.getenv("CRAWL_PROVIDER", "firecrawl").lower())
        _set(
            "crawl4ai_base_url",
            os.getenv("CRAWL4AI_BASE_URL", "http://crawl4ai:11235").rstrip("/"),
        )
        _set("crawl4ai_api_key", os.getenv("CRAWL4AI_API_KEY"))
        _set("firecrawl_api_key", os.getenv("FIRECRAWL_API_KEY"))
        _set(
            "firecrawl_base_url",
            os.getenv("FIRECRAWL_BASE_URL", "http://firecrawl-api:3002").rstrip("/"),
        )

        # Langfuse / OTLP
        _set(
            "langfuse_host",
            os.getenv("LANGFUSE_HOST", "http://localhost:3002").rstrip("/"),
        )
        langfuse_otel_host = os.getenv("LANGFUSE_OTEL_HOST", "").rstrip("/")
        _set("langfuse_otel_host", langfuse_otel_host)
        _set("langfuse_base_url", os.getenv("LANGFUSE_BASE_URL", ""))

        # Build OTLP endpoint: explicit env var > otel host > langfuse host
        # Treat empty-string OTEL_EXPORTER_OTLP_ENDPOINT as unset.
        explicit_otlp = (
            os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or ""
        ).strip()
        _set(
            "otlp_endpoint",
            explicit_otlp
            or f"{langfuse_otel_host or self.langfuse_host}{_OTEL_SUFFIX}",
        )

        # Database
        _set("postgres_user", os.getenv("POSTGRES_USER", "postgres"))
        _set("postgres_password", os.getenv("POSTGRES_PASSWORD", "postgres"))
        _set("postgres_host", os.getenv("POSTGRES_HOST", "localhost"))
        _set("postgres_port", int(os.getenv("POSTGRES_PORT", "5432")))
        _set("postgres_db", os.getenv("POSTGRES_DB", "postgres"))
        _set(
            "db_echo",
            os.getenv("DB_ECHO", "false").strip().lower()
            in {"1", "true", "yes", "on"},
        )

        # CORS
        origins = tuple(
            origin
            for origin in (
                o.strip()
                for o in os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",")
            )
            if origin
        ) or ("*",)
        _set("cors_allowed_origins", origins)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
