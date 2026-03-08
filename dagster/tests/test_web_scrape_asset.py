"""Unit tests for the web scrape asset factory.

No database or network access required.
"""

import pytest

from d4bl_pipelines.assets.crawlers.web_scrape import (
    _slugify,
    build_web_scrape_assets,
)


# ── Sample data sources ─────────────────────────────────────────


WEB_SCRAPE_SOURCES = [
    {
        "id": "aaaaaaaa-1111-2222-3333-444444444444",
        "name": "D4BL Blog",
        "source_type": "web_scrape",
        "config": {
            "urls": [
                "https://d4bl.org/blog/post-1",
                "https://d4bl.org/blog/post-2",
            ],
            "depth": 1,
            "selectors": [".article-body"],
            "crawl_provider": "firecrawl",
        },
    },
    {
        "id": "bbbbbbbb-1111-2222-3333-444444444444",
        "name": "Policy Reports",
        "source_type": "web_scrape",
        "config": {
            "urls": ["https://example.com/report.html"],
            "depth": 2,
        },
    },
]

NON_WEB_SCRAPE_SOURCES = [
    {
        "id": "cccccccc-1111-2222-3333-444444444444",
        "name": "Census API",
        "source_type": "api",
        "config": {
            "url": "https://api.census.gov/data",
            "method": "GET",
        },
    },
    {
        "id": "dddddddd-1111-2222-3333-444444444444",
        "name": "CSV Upload",
        "source_type": "file_upload",
        "config": {
            "file_path": "/data/upload.csv",
        },
    },
]


MIXED_SOURCES = WEB_SCRAPE_SOURCES + NON_WEB_SCRAPE_SOURCES


# ── _slugify tests ──────────────────────────────────────────────


def test_slugify_basic():
    assert _slugify("D4BL Blog") == "d4bl_blog"


def test_slugify_special_chars():
    assert _slugify("Policy Reports (v2)") == "policy_reports_v2"


def test_slugify_leading_trailing():
    assert _slugify("  --hello--  ") == "hello"


def test_slugify_empty():
    assert _slugify("") == "unnamed_source"


def test_slugify_only_symbols():
    assert _slugify("@#$%") == "unnamed_source"


def test_slugify_already_clean():
    assert _slugify("simple_name") == "simple_name"


# ── build_web_scrape_assets tests ──────────────────────────────


def test_factory_returns_correct_count():
    assets = build_web_scrape_assets(WEB_SCRAPE_SOURCES)
    assert isinstance(assets, list)
    assert len(assets) == 2


def test_factory_filters_non_web_scrape():
    assets = build_web_scrape_assets(NON_WEB_SCRAPE_SOURCES)
    assert assets == []


def test_factory_mixed_sources_only_web_scrape():
    assets = build_web_scrape_assets(MIXED_SOURCES)
    assert len(assets) == 2


def test_factory_correct_asset_names():
    assets = build_web_scrape_assets(WEB_SCRAPE_SOURCES)
    names = set()
    for a in assets:
        for key in a.specs_by_key:
            names.add(key.path[-1])
    assert "d4bl_blog" in names
    assert "policy_reports" in names


def test_factory_group_name_is_crawlers():
    assets = build_web_scrape_assets(WEB_SCRAPE_SOURCES)
    for a in assets:
        for spec in a.specs_by_key.values():
            assert spec.group_name == "crawlers"


def test_factory_empty_list():
    assets = build_web_scrape_assets([])
    assert assets == []


def test_factory_single_source():
    single = [WEB_SCRAPE_SOURCES[0]]
    assets = build_web_scrape_assets(single)
    assert len(assets) == 1
    key = next(iter(assets[0].specs_by_key))
    assert key.path[-1] == "d4bl_blog"


def test_factory_description_includes_url_count():
    assets = build_web_scrape_assets(WEB_SCRAPE_SOURCES)
    for a in assets:
        for spec in a.specs_by_key.values():
            assert "Web scrape ingestion" in spec.description
