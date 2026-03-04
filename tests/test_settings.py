"""Tests for d4bl.settings — verifies env vars are read at instantiation, not import time."""

from __future__ import annotations

import os

import pytest

from d4bl.settings import Settings, get_settings, _OTEL_SUFFIX


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_settings(**env_overrides: str | None) -> Settings:
    """Create a Settings instance with specific env vars, then restore originals."""
    old = {}
    for key, val in env_overrides.items():
        old[key] = os.environ.get(key)
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val
    try:
        return Settings()
    finally:
        for key, orig in old.items():
            if orig is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = orig


# ---------------------------------------------------------------------------
# Core: env vars read at instantiation, not module import
# ---------------------------------------------------------------------------

class TestDeferredEnvReads:
    """Env vars must be read when Settings() is called, not when the module loads."""

    def test_get_settings_reads_env_at_call_time(self, monkeypatch):
        """Setting an env var *after* import but *before* get_settings()
        should be picked up."""
        get_settings.cache_clear()

        monkeypatch.setenv("OLLAMA_BASE_URL", "http://custom-ollama:9999")
        s = get_settings()
        assert s.ollama_base_url == "http://custom-ollama:9999"

        # Clean up cache so later tests aren't affected
        get_settings.cache_clear()

    def test_settings_constructor_picks_up_current_env(self, monkeypatch):
        monkeypatch.setenv("POSTGRES_HOST", "my-db-host")
        s = Settings()
        assert s.postgres_host == "my-db-host"

    def test_lru_cache_returns_same_instance(self):
        get_settings.cache_clear()
        a = get_settings()
        b = get_settings()
        assert a is b
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# OTLP endpoint fallback chain
# ---------------------------------------------------------------------------

class TestOtlpEndpoint:
    """otlp_endpoint: explicit env > LANGFUSE_OTEL_HOST > LANGFUSE_HOST."""

    def test_explicit_otel_env_wins(self):
        s = _fresh_settings(
            OTEL_EXPORTER_OTLP_ENDPOINT="http://explicit:4318/v1/traces",
            LANGFUSE_OTEL_HOST="http://otel-host:3002",
            LANGFUSE_HOST="http://langfuse-host:3002",
        )
        assert s.otlp_endpoint == "http://explicit:4318/v1/traces"

    def test_falls_back_to_langfuse_otel_host(self):
        s = _fresh_settings(
            OTEL_EXPORTER_OTLP_ENDPOINT=None,
            LANGFUSE_OTEL_HOST="http://otel-host:4000",
            LANGFUSE_HOST="http://langfuse-host:3002",
        )
        assert s.otlp_endpoint == f"http://otel-host:4000{_OTEL_SUFFIX}"

    def test_falls_back_to_langfuse_host(self):
        s = _fresh_settings(
            OTEL_EXPORTER_OTLP_ENDPOINT=None,
            LANGFUSE_OTEL_HOST=None,
            LANGFUSE_HOST="http://my-langfuse:5555",
        )
        assert s.otlp_endpoint == f"http://my-langfuse:5555{_OTEL_SUFFIX}"

    def test_empty_otel_host_falls_through_to_langfuse_host(self):
        s = _fresh_settings(
            OTEL_EXPORTER_OTLP_ENDPOINT=None,
            LANGFUSE_OTEL_HOST="",
            LANGFUSE_HOST="http://my-langfuse:5555",
        )
        assert s.otlp_endpoint == f"http://my-langfuse:5555{_OTEL_SUFFIX}"

    def test_empty_otlp_env_falls_through_to_fallback(self):
        """OTEL_EXPORTER_OTLP_ENDPOINT="" should be treated as unset."""
        s = _fresh_settings(
            OTEL_EXPORTER_OTLP_ENDPOINT="",
            LANGFUSE_OTEL_HOST=None,
            LANGFUSE_HOST="http://my-langfuse:5555",
        )
        assert s.otlp_endpoint == f"http://my-langfuse:5555{_OTEL_SUFFIX}"

    def test_default_when_nothing_set(self):
        s = _fresh_settings(
            OTEL_EXPORTER_OTLP_ENDPOINT=None,
            LANGFUSE_OTEL_HOST=None,
            LANGFUSE_HOST=None,
        )
        assert s.otlp_endpoint == f"http://localhost:3002{_OTEL_SUFFIX}"


# ---------------------------------------------------------------------------
# CORS parsing
# ---------------------------------------------------------------------------

class TestCorsParsing:
    def test_single_origin(self):
        s = _fresh_settings(CORS_ALLOWED_ORIGINS="http://localhost:3000")
        assert s.cors_allowed_origins == ("http://localhost:3000",)

    def test_multiple_origins(self):
        s = _fresh_settings(
            CORS_ALLOWED_ORIGINS="http://a.com, http://b.com , http://c.com"
        )
        assert s.cors_allowed_origins == (
            "http://a.com",
            "http://b.com",
            "http://c.com",
        )

    def test_default_wildcard(self):
        s = _fresh_settings(CORS_ALLOWED_ORIGINS=None)
        assert s.cors_allowed_origins == ("*",)

    def test_empty_string_falls_back_to_wildcard(self):
        s = _fresh_settings(CORS_ALLOWED_ORIGINS="")
        assert s.cors_allowed_origins == ("*",)


# ---------------------------------------------------------------------------
# Individual field defaults
# ---------------------------------------------------------------------------

class TestFieldDefaults:
    """Verify sane defaults when env vars are unset."""

    def test_ollama_default(self):
        s = _fresh_settings(OLLAMA_BASE_URL=None)
        assert s.ollama_base_url == "http://localhost:11434"

    def test_ollama_strips_trailing_slash(self):
        s = _fresh_settings(OLLAMA_BASE_URL="http://localhost:11434/")
        assert s.ollama_base_url == "http://localhost:11434"

    def test_crawl_provider_lowercased(self):
        s = _fresh_settings(CRAWL_PROVIDER="Firecrawl")
        assert s.crawl_provider == "firecrawl"

    def test_postgres_port_default(self):
        s = _fresh_settings(POSTGRES_PORT=None)
        assert s.postgres_port == 5432

    def test_postgres_port_from_env(self):
        s = _fresh_settings(POSTGRES_PORT="54322")
        assert s.postgres_port == 54322

    def test_postgres_port_invalid_raises(self):
        with pytest.raises(ValueError):
            _fresh_settings(POSTGRES_PORT="not_a_number")

    def test_db_echo_truthy(self):
        for val in ("1", "true", "True", "YES", " on "):
            s = _fresh_settings(DB_ECHO=val)
            assert s.db_echo is True, f"DB_ECHO={val!r} should be True"

    def test_db_echo_falsy(self):
        for val in ("0", "false", "no", "off", ""):
            s = _fresh_settings(DB_ECHO=val)
            assert s.db_echo is False, f"DB_ECHO={val!r} should be False"


# ---------------------------------------------------------------------------
# Frozen immutability
# ---------------------------------------------------------------------------

class TestFrozen:
    def test_cannot_mutate(self):
        s = Settings()
        with pytest.raises(AttributeError):
            s.ollama_base_url = "http://changed"  # type: ignore[misc]
