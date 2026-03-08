"""Tests for d4bl.settings — verifies env vars are read at instantiation, not import time."""

from __future__ import annotations

import os

import pytest

from d4bl.settings import _OTEL_SUFFIX, Settings, get_settings

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

    def test_get_settings_reads_env_at_call_time(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Setting an env var *after* import but *before* get_settings()
        should be picked up."""
        get_settings.cache_clear()

        monkeypatch.setenv("OLLAMA_BASE_URL", "http://custom-ollama:9999")
        s = get_settings()
        assert s.ollama_base_url == "http://custom-ollama:9999"

        # Clean up cache so later tests aren't affected
        get_settings.cache_clear()

    def test_settings_constructor_picks_up_current_env(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("POSTGRES_HOST", "my-db-host")
        s = Settings()
        assert s.postgres_host == "my-db-host"

    def test_lru_cache_returns_same_instance(self) -> None:
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

    def test_explicit_otel_env_wins(self) -> None:
        s = _fresh_settings(
            OTEL_EXPORTER_OTLP_ENDPOINT="http://explicit:4318/v1/traces",
            LANGFUSE_OTEL_HOST="http://otel-host:3002",
            LANGFUSE_HOST="http://langfuse-host:3002",
        )
        assert s.otlp_endpoint == "http://explicit:4318/v1/traces"

    def test_falls_back_to_langfuse_otel_host(self) -> None:
        s = _fresh_settings(
            OTEL_EXPORTER_OTLP_ENDPOINT=None,
            LANGFUSE_OTEL_HOST="http://otel-host:4000",
            LANGFUSE_HOST="http://langfuse-host:3002",
        )
        assert s.otlp_endpoint == f"http://otel-host:4000{_OTEL_SUFFIX}"

    def test_falls_back_to_langfuse_host(self) -> None:
        s = _fresh_settings(
            OTEL_EXPORTER_OTLP_ENDPOINT=None,
            LANGFUSE_OTEL_HOST=None,
            LANGFUSE_HOST="http://my-langfuse:5555",
        )
        assert s.otlp_endpoint == f"http://my-langfuse:5555{_OTEL_SUFFIX}"

    def test_empty_otel_host_falls_through_to_langfuse_host(self) -> None:
        s = _fresh_settings(
            OTEL_EXPORTER_OTLP_ENDPOINT=None,
            LANGFUSE_OTEL_HOST="",
            LANGFUSE_HOST="http://my-langfuse:5555",
        )
        assert s.otlp_endpoint == f"http://my-langfuse:5555{_OTEL_SUFFIX}"

    def test_empty_otlp_env_falls_through_to_fallback(self) -> None:
        """OTEL_EXPORTER_OTLP_ENDPOINT="" should be treated as unset."""
        s = _fresh_settings(
            OTEL_EXPORTER_OTLP_ENDPOINT="",
            LANGFUSE_OTEL_HOST=None,
            LANGFUSE_HOST="http://my-langfuse:5555",
        )
        assert s.otlp_endpoint == f"http://my-langfuse:5555{_OTEL_SUFFIX}"

    def test_default_when_nothing_set(self) -> None:
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
    def test_single_origin(self) -> None:
        s = _fresh_settings(CORS_ALLOWED_ORIGINS="http://localhost:3000")
        assert s.cors_allowed_origins == ("http://localhost:3000",)

    def test_multiple_origins(self) -> None:
        s = _fresh_settings(
            CORS_ALLOWED_ORIGINS="http://a.com, http://b.com , http://c.com"
        )
        assert s.cors_allowed_origins == (
            "http://a.com",
            "http://b.com",
            "http://c.com",
        )

    def test_default_wildcard(self) -> None:
        s = _fresh_settings(CORS_ALLOWED_ORIGINS=None)
        assert s.cors_allowed_origins == ("*",)

    def test_empty_string_falls_back_to_wildcard(self) -> None:
        s = _fresh_settings(CORS_ALLOWED_ORIGINS="")
        assert s.cors_allowed_origins == ("*",)


# ---------------------------------------------------------------------------
# Individual field defaults
# ---------------------------------------------------------------------------

class TestFieldDefaults:
    """Verify sane defaults when env vars are unset."""

    def test_ollama_default(self) -> None:
        s = _fresh_settings(OLLAMA_BASE_URL=None)
        assert s.ollama_base_url == "http://localhost:11434"

    def test_ollama_strips_trailing_slash(self) -> None:
        s = _fresh_settings(OLLAMA_BASE_URL="http://localhost:11434/")
        assert s.ollama_base_url == "http://localhost:11434"

    def test_crawl_provider_lowercased(self) -> None:
        s = _fresh_settings(CRAWL_PROVIDER="Firecrawl")
        assert s.crawl_provider == "firecrawl"

    def test_postgres_port_default(self) -> None:
        s = _fresh_settings(POSTGRES_PORT=None)
        assert s.postgres_port == 5432

    def test_postgres_port_from_env(self) -> None:
        s = _fresh_settings(POSTGRES_PORT="54322")
        assert s.postgres_port == 54322

    def test_postgres_port_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid literal"):
            _fresh_settings(POSTGRES_PORT="not_a_number")

    def test_db_echo_truthy(self) -> None:
        for val in ("1", "true", "True", "YES", " on "):
            s = _fresh_settings(DB_ECHO=val)
            assert s.db_echo is True, f"DB_ECHO={val!r} should be True"

    def test_db_echo_falsy(self) -> None:
        for val in ("0", "false", "no", "off", ""):
            s = _fresh_settings(DB_ECHO=val)
            assert s.db_echo is False, f"DB_ECHO={val!r} should be False"

    def test_llm_provider_default(self) -> None:
        s = _fresh_settings(LLM_PROVIDER=None)
        assert s.llm_provider == "ollama"

    def test_llm_provider_from_env(self) -> None:
        s = _fresh_settings(LLM_PROVIDER="gemini")
        assert s.llm_provider == "gemini"

    def test_llm_provider_lowercased(self) -> None:
        s = _fresh_settings(LLM_PROVIDER="Gemini")
        assert s.llm_provider == "gemini"

    def test_llm_model_default(self) -> None:
        s = _fresh_settings(LLM_MODEL=None)
        assert s.llm_model == "mistral"

    def test_llm_model_from_env(self) -> None:
        s = _fresh_settings(LLM_MODEL="gemini-2.0-flash")
        assert s.llm_model == "gemini-2.0-flash"

    def test_llm_api_key_default_none(self) -> None:
        s = _fresh_settings(LLM_API_KEY=None)
        assert s.llm_api_key is None

    def test_llm_api_key_from_env(self) -> None:
        s = _fresh_settings(LLM_API_KEY="sk-test-key")
        assert s.llm_api_key == "sk-test-key"

    def test_supabase_url_default_none(self) -> None:
        s = _fresh_settings(SUPABASE_URL=None)
        assert s.supabase_url is None

    def test_supabase_url_from_env(self) -> None:
        s = _fresh_settings(SUPABASE_URL="https://test.supabase.co")
        assert s.supabase_url == "https://test.supabase.co"

    def test_supabase_jwt_secret_default_none(self) -> None:
        s = _fresh_settings(SUPABASE_JWT_SECRET=None)
        assert s.supabase_jwt_secret is None

    def test_supabase_jwt_secret_from_env(self) -> None:
        s = _fresh_settings(SUPABASE_JWT_SECRET="test-jwt-secret")
        assert s.supabase_jwt_secret == "test-jwt-secret"

    def test_supabase_service_role_key_default_none(self) -> None:
        s = _fresh_settings(SUPABASE_SERVICE_ROLE_KEY=None)
        assert s.supabase_service_role_key is None

    def test_supabase_service_role_key_from_env(self) -> None:
        s = _fresh_settings(SUPABASE_SERVICE_ROLE_KEY="test-service-key")
        assert s.supabase_service_role_key == "test-service-key"

    def test_admin_email_default_none(self) -> None:
        s = _fresh_settings(ADMIN_EMAIL=None)
        assert s.admin_email is None

    def test_admin_email_from_env(self) -> None:
        s = _fresh_settings(ADMIN_EMAIL="admin@example.com")
        assert s.admin_email == "admin@example.com"


# ---------------------------------------------------------------------------
# Supabase auth settings via get_settings
# ---------------------------------------------------------------------------

def test_supabase_auth_settings(monkeypatch):
    """Settings should expose Supabase auth fields."""
    get_settings.cache_clear()
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    try:
        s = get_settings()
        assert s.supabase_url == "https://test.supabase.co"
        assert s.supabase_jwt_secret == "test-jwt-secret"
        assert s.supabase_service_role_key == "test-service-key"
        assert s.admin_email == "admin@example.com"
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Frozen immutability
# ---------------------------------------------------------------------------

class TestFrozen:
    def test_cannot_mutate(self) -> None:
        s = Settings()
        with pytest.raises(AttributeError):
            s.ollama_base_url = "http://changed"  # type: ignore[misc]
