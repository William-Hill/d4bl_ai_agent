"""Unit tests for the generic API asset factory.

No database or network access required.
"""

import pytest
from d4bl_pipelines.assets.apis.generic_api import (
    _build_headers,
    _derive_record_key,
    _extract_path,
    _slugify,
    build_api_assets,
)

# ── _extract_path tests ──────────────────────────────────────────


def test_extract_path_simple():
    data = {"data": {"results": [1, 2, 3]}}
    assert _extract_path(data, "data.results") == [1, 2, 3]


def test_extract_path_single_key():
    data = {"items": [{"id": 1}]}
    assert _extract_path(data, "items") == [{"id": 1}]


def test_extract_path_empty_string():
    data = {"a": 1}
    assert _extract_path(data, "") == {"a": 1}


def test_extract_path_deeply_nested():
    data = {"a": {"b": {"c": {"d": 42}}}}
    assert _extract_path(data, "a.b.c.d") == 42


def test_extract_path_list_index():
    data = {"items": ["zero", "one", "two"]}
    assert _extract_path(data, "items.1") == "one"


def test_extract_path_missing_key():
    data = {"a": 1}
    with pytest.raises(KeyError):
        _extract_path(data, "b")


def test_extract_path_invalid_traverse():
    data = {"a": 42}
    with pytest.raises(KeyError):
        _extract_path(data, "a.b")


# ── _slugify tests ───────────────────────────────────────────────


def test_slugify_basic():
    assert _slugify("Census ACS") == "census_acs"


def test_slugify_special_chars():
    assert _slugify("My API (v2)") == "my_api_v2"


def test_slugify_leading_trailing():
    assert _slugify("  --hello--  ") == "hello"


def test_slugify_empty():
    assert _slugify("") == "unnamed_source"


def test_slugify_only_symbols():
    assert _slugify("!!!") == "unnamed_source"


# ── _derive_record_key tests ────────────────────────────────────


def test_derive_record_key_with_id():
    record = {"id": "abc-123", "name": "Test"}
    assert _derive_record_key(record, 0, "src1") == "abc-123"


def test_derive_record_key_with_key_field():
    record = {"key": "my-key", "value": 1}
    assert _derive_record_key(record, 0, "src1") == "my-key"


def test_derive_record_key_fallback_hash():
    record = {"x": 1, "y": 2}
    result = _derive_record_key(record, 0, "src1")
    assert len(result) == 16  # truncated hash


def test_derive_record_key_non_dict():
    result = _derive_record_key("plain string", 5, "src1")
    assert len(result) == 16


# ── _build_headers tests ────────────────────────────────────────


def test_build_headers_no_auth():
    config = {"headers": {"Accept": "application/json"}}
    headers = _build_headers(config)
    assert headers == {"Accept": "application/json"}


def test_build_headers_no_headers_key():
    config = {}
    assert _build_headers(config) == {}


def test_build_headers_bearer_auth(monkeypatch):
    monkeypatch.setenv("MY_TOKEN", "secret123")
    config = {
        "auth": {
            "type": "bearer",
            "credentials_env_var": "MY_TOKEN",
        }
    }
    headers = _build_headers(config)
    assert headers["Authorization"] == "Bearer secret123"


def test_build_headers_api_key_auth(monkeypatch):
    monkeypatch.setenv("MY_API_KEY", "key456")
    config = {
        "auth": {
            "type": "api_key",
            "credentials_env_var": "MY_API_KEY",
            "header_name": "X-Custom-Key",
        }
    }
    headers = _build_headers(config)
    assert headers["X-Custom-Key"] == "key456"


def test_build_headers_api_key_default_header(monkeypatch):
    monkeypatch.setenv("MY_API_KEY", "key789")
    config = {
        "auth": {
            "type": "api_key",
            "credentials_env_var": "MY_API_KEY",
        }
    }
    headers = _build_headers(config)
    assert headers["X-API-Key"] == "key789"


def test_build_headers_missing_env_var(monkeypatch):
    monkeypatch.delenv("NONEXISTENT_VAR_XYZ", raising=False)
    config = {
        "auth": {
            "type": "bearer",
            "credentials_env_var": "NONEXISTENT_VAR_XYZ",
        }
    }
    headers = _build_headers(config)
    assert "Authorization" not in headers


# ── build_api_assets tests ──────────────────────────────────────


SAMPLE_SOURCES = [
    {
        "id": "aaaaaaaa-1111-2222-3333-444444444444",
        "name": "Test API One",
        "source_type": "api",
        "config": {
            "url": "https://api.example.com/data",
            "method": "GET",
            "params": {"limit": "100"},
            "response_path": "data.results",
        },
    },
    {
        "id": "bbbbbbbb-1111-2222-3333-444444444444",
        "name": "Another Source",
        "source_type": "api",
        "config": {
            "url": "https://api.example.com/v2/items",
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "response_path": "items",
            "auth": {
                "type": "bearer",
                "credentials_env_var": "EXAMPLE_TOKEN",
            },
        },
    },
]


def test_build_api_assets_returns_list():
    assets = build_api_assets(SAMPLE_SOURCES)
    assert isinstance(assets, list)
    assert len(assets) == 2


def test_build_api_assets_correct_names():
    assets = build_api_assets(SAMPLE_SOURCES)
    names = set()
    for a in assets:
        for key in a.specs_by_key:
            names.add(key.path[-1])
    assert "test_api_one" in names
    assert "another_source" in names


def test_build_api_assets_group():
    assets = build_api_assets(SAMPLE_SOURCES)
    for a in assets:
        for spec in a.specs_by_key.values():
            assert spec.group_name == "apis"


def test_build_api_assets_empty_list():
    assets = build_api_assets([])
    assert assets == []


def test_build_api_assets_single_source():
    single = [SAMPLE_SOURCES[0]]
    assets = build_api_assets(single)
    assert len(assets) == 1
    key = next(iter(assets[0].specs_by_key))
    assert key.path[-1] == "test_api_one"
