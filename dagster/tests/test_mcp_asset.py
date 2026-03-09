"""Unit tests for the MCP source asset factory.

No database or network access required.
"""

import pytest
from d4bl_pipelines.assets.mcp.mcp_source import (
    _build_jsonrpc_request,
    _extract_results,
    _slugify,
    build_mcp_assets,
)

# ── _slugify tests ───────────────────────────────────────────────


def test_slugify_basic():
    assert _slugify("Census MCP") == "census_mcp"


def test_slugify_special_chars():
    assert _slugify("My Tool (v2)") == "my_tool_v2"


def test_slugify_leading_trailing():
    assert _slugify("  --hello--  ") == "hello"


def test_slugify_empty():
    assert _slugify("") == "unnamed_source"


def test_slugify_only_symbols():
    assert _slugify("@#$") == "unnamed_source"


def test_slugify_preserves_numbers():
    assert _slugify("api2 data") == "api2_data"


# ── _build_jsonrpc_request tests ─────────────────────────────────


def test_build_jsonrpc_request_structure():
    result = _build_jsonrpc_request("get_data", {"limit": 10})
    assert result["jsonrpc"] == "2.0"
    assert result["method"] == "tools/call"
    assert result["id"] == 1
    assert result["params"]["name"] == "get_data"
    assert result["params"]["arguments"] == {"limit": 10}


def test_build_jsonrpc_request_empty_params():
    result = _build_jsonrpc_request("list_items", {})
    assert result["params"]["name"] == "list_items"
    assert result["params"]["arguments"] == {}


def test_build_jsonrpc_request_complex_params():
    params = {
        "query": "SELECT *",
        "filters": {"state": "CA", "year": 2024},
    }
    result = _build_jsonrpc_request("search", params)
    assert result["params"]["arguments"] == params


def test_build_jsonrpc_request_has_all_required_fields():
    result = _build_jsonrpc_request("test", {})
    assert set(result.keys()) == {
        "jsonrpc", "method", "params", "id"
    }


# ── _extract_results tests ──────────────────────────────────────


def test_extract_results_list_response():
    response = {
        "jsonrpc": "2.0",
        "result": [{"id": 1}, {"id": 2}],
        "id": 1,
    }
    records = _extract_results(response)
    assert len(records) == 2
    assert records[0] == {"id": 1}
    assert records[1] == {"id": 2}


def test_extract_results_single_object():
    response = {
        "jsonrpc": "2.0",
        "result": {"name": "test", "value": 42},
        "id": 1,
    }
    records = _extract_results(response)
    assert len(records) == 1
    assert records[0] == {"name": "test", "value": 42}


def test_extract_results_scalar_value():
    response = {
        "jsonrpc": "2.0",
        "result": "plain text",
        "id": 1,
    }
    records = _extract_results(response)
    assert records == [{"value": "plain text"}]


def test_extract_results_null_result():
    response = {"jsonrpc": "2.0", "result": None, "id": 1}
    assert _extract_results(response) == []


def test_extract_results_missing_result():
    response = {"jsonrpc": "2.0", "id": 1}
    assert _extract_results(response) == []


def test_extract_results_error_response():
    response = {
        "jsonrpc": "2.0",
        "error": {"code": -32600, "message": "Invalid Request"},
        "id": 1,
    }
    with pytest.raises(ValueError, match="JSON-RPC error -32600"):
        _extract_results(response)


def test_extract_results_error_with_details():
    response = {
        "jsonrpc": "2.0",
        "error": {
            "code": -32601,
            "message": "Method not found",
            "data": "tools/call is not available",
        },
        "id": 1,
    }
    with pytest.raises(ValueError, match="Method not found"):
        _extract_results(response)


# ── build_mcp_assets tests ──────────────────────────────────────

SAMPLE_MCP_SOURCES = [
    {
        "id": "aaaa1111-2222-3333-4444-555555555555",
        "name": "Supabase MCP",
        "source_type": "mcp",
        "config": {
            "server_url": "http://localhost:9000/rpc",
            "tool_name": "list_tables",
            "tool_params": {"schema": "public"},
        },
    },
    {
        "id": "bbbb1111-2222-3333-4444-555555555555",
        "name": "Census MCP Tool",
        "source_type": "mcp",
        "config": {
            "server_url": "http://mcp.example.com/rpc",
            "tool_name": "get_indicators",
            "tool_params": {"year": 2024},
            "auth_env_var": "CENSUS_MCP_TOKEN",
        },
    },
]

MIXED_SOURCES = [
    SAMPLE_MCP_SOURCES[0],
    {
        "id": "cccc1111-2222-3333-4444-555555555555",
        "name": "Some REST API",
        "source_type": "api",
        "config": {
            "url": "https://api.example.com/data",
            "method": "GET",
        },
    },
    SAMPLE_MCP_SOURCES[1],
    {
        "id": "dddd1111-2222-3333-4444-555555555555",
        "name": "A File Source",
        "source_type": "file",
        "config": {"path": "/data/test.csv"},
    },
]


def test_build_mcp_assets_returns_list():
    assets = build_mcp_assets(SAMPLE_MCP_SOURCES)
    assert isinstance(assets, list)
    assert len(assets) == 2


def test_build_mcp_assets_correct_names():
    assets = build_mcp_assets(SAMPLE_MCP_SOURCES)
    names = set()
    for a in assets:
        for key in a.specs_by_key:
            names.add(key.path[-1])
    assert "supabase_mcp" in names
    assert "census_mcp_tool" in names


def test_build_mcp_assets_group_name():
    assets = build_mcp_assets(SAMPLE_MCP_SOURCES)
    for a in assets:
        for spec in a.specs_by_key.values():
            assert spec.group_name == "mcp"


def test_build_mcp_assets_filters_non_mcp():
    assets = build_mcp_assets(MIXED_SOURCES)
    assert len(assets) == 2
    names = set()
    for a in assets:
        for key in a.specs_by_key:
            names.add(key.path[-1])
    assert "supabase_mcp" in names
    assert "census_mcp_tool" in names
    assert "some_rest_api" not in names
    assert "a_file_source" not in names


def test_build_mcp_assets_empty_list():
    assets = build_mcp_assets([])
    assert assets == []


def test_build_mcp_assets_no_mcp_sources():
    non_mcp = [
        {
            "id": "eeee1111-2222-3333-4444-555555555555",
            "name": "API Only",
            "source_type": "api",
            "config": {"url": "https://example.com"},
        },
    ]
    assets = build_mcp_assets(non_mcp)
    assert assets == []


def test_build_mcp_assets_single_source():
    single = [SAMPLE_MCP_SOURCES[0]]
    assets = build_mcp_assets(single)
    assert len(assets) == 1
    key = next(iter(assets[0].specs_by_key))
    assert key.path[-1] == "supabase_mcp"


def test_build_mcp_assets_description_contains_tool_name():
    assets = build_mcp_assets([SAMPLE_MCP_SOURCES[0]])
    spec = next(iter(assets[0].specs_by_key.values()))
    assert "list_tables" in spec.description
    assert "localhost:9000" in spec.description
