"""Unit tests for the external database asset factory.

No database or network access required.
"""

import pytest

from d4bl_pipelines.assets.databases.external_db import (
    _slugify,
    _derive_record_key,
    _get_last_run_time,
    build_external_db_assets,
)


# ── _slugify tests ───────────────────────────────────────────────


def test_slugify_basic():
    assert _slugify("Census DB") == "census_db"


def test_slugify_special_chars():
    assert _slugify("My Database (prod)") == "my_database_prod"


def test_slugify_leading_trailing():
    assert _slugify("  --hello--  ") == "hello"


def test_slugify_empty():
    assert _slugify("") == "unnamed_source"


def test_slugify_only_symbols():
    assert _slugify("!!!") == "unnamed_source"


def test_slugify_underscores_preserved():
    assert _slugify("my_source_v2") == "my_source_v2"


# ── _derive_record_key tests ────────────────────────────────────


def test_derive_record_key_with_id():
    record = {"id": "row-42", "name": "Test"}
    assert _derive_record_key(record, 0, "src1") == "row-42"


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


# ── _get_last_run_time tests ────────────────────────────────────


def test_get_last_run_time_is_callable():
    """Verify the helper is an async function."""
    import asyncio
    assert asyncio.iscoroutinefunction(_get_last_run_time)


# ── Sample data sources ─────────────────────────────────────────

SAMPLE_DB_SOURCES = [
    {
        "id": "aaaaaaaa-1111-2222-3333-444444444444",
        "name": "External Postgres",
        "source_type": "database",
        "config": {
            "connection_env_var": "EXT_PG_CONN_STRING",
            "query": "SELECT * FROM public.demographics",
            "incremental": False,
        },
    },
    {
        "id": "bbbbbbbb-1111-2222-3333-444444444444",
        "name": "Reporting MySQL",
        "source_type": "database",
        "config": {
            "connection_env_var": "MYSQL_REPORTING_URL",
            "query": (
                "SELECT * FROM reports "
                "WHERE updated_at > :last_run"
            ),
            "incremental": True,
        },
    },
]

MIXED_SOURCES = SAMPLE_DB_SOURCES + [
    {
        "id": "cccccccc-1111-2222-3333-444444444444",
        "name": "Some API",
        "source_type": "api",
        "config": {
            "url": "https://api.example.com/data",
            "method": "GET",
        },
    },
    {
        "id": "dddddddd-1111-2222-3333-444444444444",
        "name": "RSS Feed",
        "source_type": "feed",
        "config": {
            "url": "https://example.com/feed.xml",
        },
    },
]


# ── build_external_db_assets tests ──────────────────────────────


def test_factory_returns_correct_count():
    assets = build_external_db_assets(SAMPLE_DB_SOURCES)
    assert isinstance(assets, list)
    assert len(assets) == 2


def test_factory_filters_non_database_sources():
    assets = build_external_db_assets(MIXED_SOURCES)
    assert len(assets) == 2  # only the two database sources


def test_factory_correct_asset_names():
    assets = build_external_db_assets(SAMPLE_DB_SOURCES)
    names = set()
    for a in assets:
        for key in a.specs_by_key:
            names.add(key.path[-1])
    assert "external_postgres" in names
    assert "reporting_mysql" in names


def test_factory_group_name_is_databases():
    assets = build_external_db_assets(SAMPLE_DB_SOURCES)
    for a in assets:
        for spec in a.specs_by_key.values():
            assert spec.group_name == "databases"


def test_factory_empty_list():
    assets = build_external_db_assets([])
    assert assets == []


def test_factory_all_non_database():
    non_db = [
        {
            "id": "eeeeeeee-1111-2222-3333-444444444444",
            "name": "API Only",
            "source_type": "api",
            "config": {"url": "https://example.com"},
        },
    ]
    assets = build_external_db_assets(non_db)
    assert assets == []


def test_factory_single_source():
    single = [SAMPLE_DB_SOURCES[0]]
    assets = build_external_db_assets(single)
    assert len(assets) == 1
    key = next(iter(assets[0].specs_by_key))
    assert key.path[-1] == "external_postgres"


def test_factory_asset_has_description():
    assets = build_external_db_assets([SAMPLE_DB_SOURCES[0]])
    spec = next(iter(assets[0].specs_by_key.values()))
    assert "External Postgres" in spec.description
    assert "EXT_PG_CONN_STRING" in spec.description
