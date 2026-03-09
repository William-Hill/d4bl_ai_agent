"""Unit tests for the keyword monitor asset factory.

No database or network access required.
"""

from d4bl_pipelines.assets.keyword_monitors.keyword_search import (
    _build_keyword_query,
    _slugify,
    build_keyword_monitor_assets,
)

# ── _slugify tests ───────────────────────────────────────────────


def test_slugify_basic():
    assert _slugify("Racial Equity") == "racial_equity"


def test_slugify_special_chars():
    assert _slugify("Police (Use of Force)") == "police_use_of_force"


def test_slugify_leading_trailing():
    assert _slugify("  --hello--  ") == "hello"


def test_slugify_empty():
    assert _slugify("") == "unnamed_monitor"


def test_slugify_only_symbols():
    assert _slugify("@@@") == "unnamed_monitor"


# ── _build_keyword_query tests ───────────────────────────────────


def test_build_keyword_query_single_keyword_single_source():
    where, params = _build_keyword_query(
        ["equity"],
        ["aaaaaaaa-1111-2222-3333-444444444444"],
    )
    assert "LOWER(CAST(data AS TEXT)) LIKE :kw_0" in where
    assert params["kw_0"] == "%equity%"
    assert "CAST(:src_0 AS UUID)" in where
    assert params["src_0"] == "aaaaaaaa-1111-2222-3333-444444444444"


def test_build_keyword_query_multiple_keywords():
    where, params = _build_keyword_query(
        ["police", "incarceration", "housing"],
        ["aaaaaaaa-1111-2222-3333-444444444444"],
    )
    assert ":kw_0" in where
    assert ":kw_1" in where
    assert ":kw_2" in where
    assert params["kw_0"] == "%police%"
    assert params["kw_1"] == "%incarceration%"
    assert params["kw_2"] == "%housing%"


def test_build_keyword_query_multiple_sources():
    where, params = _build_keyword_query(
        ["equity"],
        [
            "aaaaaaaa-1111-2222-3333-444444444444",
            "bbbbbbbb-1111-2222-3333-444444444444",
        ],
    )
    assert ":src_0" in where
    assert ":src_1" in where
    assert params["src_0"] == "aaaaaaaa-1111-2222-3333-444444444444"
    assert params["src_1"] == "bbbbbbbb-1111-2222-3333-444444444444"


def test_build_keyword_query_case_insensitive():
    """Keywords are lowercased in params for case-insensitive matching."""
    where, params = _build_keyword_query(
        ["RACIAL Justice"],
        ["aaaaaaaa-1111-2222-3333-444444444444"],
    )
    assert params["kw_0"] == "%racial justice%"


def test_build_keyword_query_empty_keywords():
    """Empty keywords should return WHERE FALSE."""
    where, params = _build_keyword_query(
        [],
        ["aaaaaaaa-1111-2222-3333-444444444444"],
    )
    assert where == "WHERE FALSE"
    assert params == {}


def test_build_keyword_query_empty_source_ids():
    """Empty source_ids should return WHERE FALSE."""
    where, params = _build_keyword_query(
        ["equity"],
        [],
    )
    assert where == "WHERE FALSE"
    assert params == {}


def test_build_keyword_query_uses_cast_not_double_colon():
    """Ensure asyncpg-compatible CAST syntax, not :: shorthand."""
    where, _ = _build_keyword_query(
        ["test"],
        ["aaaaaaaa-1111-2222-3333-444444444444"],
    )
    assert "::" not in where
    assert "CAST(" in where


# ── build_keyword_monitor_assets tests ───────────────────────────

SAMPLE_MONITORS = [
    {
        "id": "aaaaaaaa-1111-2222-3333-444444444444",
        "name": "Police Violence",
        "keywords": ["police", "use of force", "brutality"],
        "source_ids": [
            "cccccccc-1111-2222-3333-444444444444",
            "dddddddd-1111-2222-3333-444444444444",
        ],
        "enabled": True,
    },
    {
        "id": "bbbbbbbb-1111-2222-3333-444444444444",
        "name": "Housing Equity",
        "keywords": ["housing", "redlining", "zoning"],
        "source_ids": ["cccccccc-1111-2222-3333-444444444444"],
        "enabled": True,
    },
    {
        "id": "eeeeeeee-1111-2222-3333-444444444444",
        "name": "Disabled Monitor",
        "keywords": ["test"],
        "source_ids": ["cccccccc-1111-2222-3333-444444444444"],
        "enabled": False,
    },
]


def test_factory_returns_correct_number_of_assets():
    assets = build_keyword_monitor_assets(SAMPLE_MONITORS)
    # Only 2 enabled monitors should produce assets
    assert len(assets) == 2


def test_factory_filters_disabled_monitors():
    disabled_only = [m for m in SAMPLE_MONITORS if not m["enabled"]]
    assets = build_keyword_monitor_assets(disabled_only)
    assert assets == []


def test_factory_asset_group_name():
    assets = build_keyword_monitor_assets(SAMPLE_MONITORS)
    for a in assets:
        for spec in a.specs_by_key.values():
            assert spec.group_name == "keyword_monitors"


def test_factory_asset_names():
    assets = build_keyword_monitor_assets(SAMPLE_MONITORS)
    names = set()
    for a in assets:
        for key in a.specs_by_key:
            names.add(key.path[-1])
    assert "keyword_search_police_violence" in names
    assert "keyword_search_housing_equity" in names


def test_factory_empty_list():
    assets = build_keyword_monitor_assets([])
    assert assets == []


def test_factory_single_monitor():
    single = [SAMPLE_MONITORS[0]]
    assets = build_keyword_monitor_assets(single)
    assert len(assets) == 1
    key = next(iter(assets[0].specs_by_key))
    assert key.path[-1] == "keyword_search_police_violence"
