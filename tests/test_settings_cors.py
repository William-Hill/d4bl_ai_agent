"""Tests for CORS origins configuration in Settings."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_settings_has_cors_allowed_origins():
    """Settings must expose cors_allowed_origins as a tuple."""
    from d4bl.settings import Settings
    s = Settings()
    assert hasattr(s, "cors_allowed_origins")
    assert isinstance(s.cors_allowed_origins, tuple)


def test_settings_cors_defaults_to_wildcard():
    """Default CORS origins must include '*' when env var is not set."""
    import os
    os.environ.pop("CORS_ALLOWED_ORIGINS", None)
    from d4bl.settings import Settings
    s = Settings()
    assert "*" in s.cors_allowed_origins


def test_settings_cors_reads_from_env(monkeypatch):
    """CORS origins must be parsed from CORS_ALLOWED_ORIGINS env var (comma-separated)."""
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://example.com")
    from d4bl.settings import Settings
    s = Settings()  # bypass lru_cache by constructing directly
    assert "http://localhost:3000" in s.cors_allowed_origins
    assert "http://example.com" in s.cors_allowed_origins
    assert len(s.cors_allowed_origins) == 2
