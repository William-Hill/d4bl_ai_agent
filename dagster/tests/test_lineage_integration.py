"""Integration tests for lineage recording across all asset modules.

Verifies that:
- All asset modules can import the lineage functions
- build_lineage_record produces valid dicts
- write_lineage_batch has the expected async signature
- The lineage record schema is compatible with all asset patterns
"""

import inspect
import uuid
from datetime import datetime, timezone

import pytest
from d4bl_pipelines.quality.lineage import (
    build_lineage_record,
    write_lineage_batch,
)

# ------------------------------------------------------------------ #
# 1. Verify imports from every asset module
# ------------------------------------------------------------------ #

def test_openstates_imports_lineage():
    """openstates.py source can access lineage functions."""
    from d4bl_pipelines.assets.apis import openstates  # noqa: F401
    # Module loaded without error; lineage import is deferred inside
    # the asset function, so we just confirm the module itself loads.


def test_census_acs_imports_lineage():
    """census_acs.py source can access lineage functions."""
    from d4bl_pipelines.assets.apis import census_acs  # noqa: F401


def test_generic_api_imports_lineage():
    """generic_api.py source can access lineage functions."""
    from d4bl_pipelines.assets.apis import generic_api  # noqa: F401


def test_file_upload_imports_lineage():
    """file_upload.py source can access lineage functions."""
    from d4bl_pipelines.assets.files import file_upload  # noqa: F401


def test_web_scrape_imports_lineage():
    """web_scrape.py source can access lineage functions."""
    from d4bl_pipelines.assets.crawlers import web_scrape  # noqa: F401


def test_rss_monitor_imports_lineage():
    """rss_monitor.py source can access lineage functions."""
    from d4bl_pipelines.assets.feeds import rss_monitor  # noqa: F401


def test_external_db_imports_lineage():
    """external_db.py source can access lineage functions."""
    from d4bl_pipelines.assets.databases import external_db  # noqa: F401


def test_mcp_source_imports_lineage():
    """mcp_source.py source can access lineage functions."""
    from d4bl_pipelines.assets.mcp import mcp_source  # noqa: F401


# ------------------------------------------------------------------ #
# 2. build_lineage_record produces valid dicts
# ------------------------------------------------------------------ #

class TestBuildLineageRecord:
    """Validate the structure returned by build_lineage_record."""

    def test_minimal_record(self):
        """A record with only required fields has expected keys."""
        run_id = uuid.uuid4()
        rec_id = uuid.uuid4()
        record = build_lineage_record(
            ingestion_run_id=run_id,
            target_table="test_table",
            record_id=rec_id,
        )
        assert record["ingestion_run_id"] == run_id
        assert record["target_table"] == "test_table"
        assert record["record_id"] == rec_id
        assert isinstance(record["id"], uuid.UUID)
        assert isinstance(record["retrieved_at"], datetime)
        # Optional fields should be None
        assert record["source_url"] is None
        assert record["source_hash"] is None
        assert record["transformation"] is None
        assert record["quality_score"] is None
        assert record["coverage_metadata"] is None
        assert record["bias_flags"] is None

    def test_full_record(self):
        """A record with all fields populated."""
        run_id = uuid.uuid4()
        rec_id = uuid.uuid4()
        record = build_lineage_record(
            ingestion_run_id=run_id,
            target_table="policy_bills",
            record_id=rec_id,
            source_url="https://example.com/api",
            source_hash="abc123",
            transformation={"steps": ["fetch", "parse", "upsert"]},
            quality_score=4.5,
            coverage_metadata={"states": 50},
            bias_flags={"single_source": True},
        )
        assert record["source_url"] == "https://example.com/api"
        assert record["source_hash"] == "abc123"
        assert record["transformation"] == {
            "steps": ["fetch", "parse", "upsert"]
        }
        assert record["quality_score"] == 4.5
        assert record["coverage_metadata"] == {"states": 50}
        assert record["bias_flags"] == {"single_source": True}

    @pytest.mark.parametrize(
        "target_table,steps",
        [
            ("policy_bills", ["fetch_graphql", "map_status", "upsert"]),
            ("census_indicators", ["fetch_acs_api", "compute_rate", "upsert"]),
            ("ingested_records", ["fetch_api", "extract_path", "upsert"]),
            ("ingested_records", ["read_file", "parse_csv", "upsert"]),
            ("scraped_content_vectors", ["crawl", "extract_content", "upsert"]),
            ("ingested_records", ["fetch_feed", "parse_xml", "upsert"]),
            ("ingested_records", ["query_external_db", "transform", "upsert"]),
            ("ingested_records", ["call_mcp_tool", "extract_results", "upsert"]),
        ],
    )
    def test_all_asset_patterns(self, target_table, steps):
        """Each asset's transformation pattern produces a valid record."""
        record = build_lineage_record(
            ingestion_run_id=uuid.uuid4(),
            target_table=target_table,
            record_id=uuid.uuid4(),
            source_url="https://example.com",
            source_hash="deadbeef",
            transformation={"steps": steps},
            quality_score=3.0,
        )
        assert record["target_table"] == target_table
        assert record["transformation"]["steps"] == steps

    def test_unique_ids(self):
        """Each call generates a unique lineage record ID."""
        run_id = uuid.uuid4()
        records = [
            build_lineage_record(
                ingestion_run_id=run_id,
                target_table="t",
                record_id=uuid.uuid4(),
            )
            for _ in range(10)
        ]
        ids = {r["id"] for r in records}
        assert len(ids) == 10

    def test_retrieved_at_is_utc(self):
        """The retrieved_at timestamp uses UTC."""
        record = build_lineage_record(
            ingestion_run_id=uuid.uuid4(),
            target_table="t",
            record_id=uuid.uuid4(),
        )
        assert record["retrieved_at"].tzinfo == timezone.utc


# ------------------------------------------------------------------ #
# 3. write_lineage_batch signature validation
# ------------------------------------------------------------------ #

class TestWriteLineageBatchSignature:
    """Validate the write_lineage_batch function signature."""

    def test_is_coroutine(self):
        """write_lineage_batch must be an async function."""
        assert inspect.iscoroutinefunction(write_lineage_batch)

    def test_accepts_session_and_records(self):
        """write_lineage_batch accepts (session, records) parameters."""
        sig = inspect.signature(write_lineage_batch)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "records" in params
        assert len(params) == 2

    def test_return_annotation_is_int(self):
        """write_lineage_batch should return int (count of written)."""
        sig = inspect.signature(write_lineage_batch)
        assert sig.return_annotation is int


# ------------------------------------------------------------------ #
# 4. Verify lineage code is present in asset source files
# ------------------------------------------------------------------ #

class TestLineageCodePresence:
    """Check that lineage recording code was added to each asset."""

    @pytest.mark.parametrize(
        "module_path",
        [
            "d4bl_pipelines.assets.apis.openstates",
            "d4bl_pipelines.assets.apis.census_acs",
            "d4bl_pipelines.assets.apis.generic_api",
            "d4bl_pipelines.assets.files.file_upload",
            "d4bl_pipelines.assets.crawlers.web_scrape",
            "d4bl_pipelines.assets.feeds.rss_monitor",
            "d4bl_pipelines.assets.databases.external_db",
            "d4bl_pipelines.assets.mcp.mcp_source",
        ],
    )
    def test_module_source_contains_lineage_import(self, module_path):
        """Each asset module source contains the lineage import."""
        import importlib

        mod = importlib.import_module(module_path)
        source = inspect.getsource(mod)
        assert "build_lineage_record" in source
        assert "write_lineage_batch" in source

    @pytest.mark.parametrize(
        "module_path",
        [
            "d4bl_pipelines.assets.apis.openstates",
            "d4bl_pipelines.assets.apis.census_acs",
            "d4bl_pipelines.assets.apis.generic_api",
            "d4bl_pipelines.assets.files.file_upload",
            "d4bl_pipelines.assets.crawlers.web_scrape",
            "d4bl_pipelines.assets.feeds.rss_monitor",
            "d4bl_pipelines.assets.databases.external_db",
            "d4bl_pipelines.assets.mcp.mcp_source",
        ],
    )
    def test_module_has_lineage_error_handling(self, module_path):
        """Each asset module wraps lineage in try/except."""
        import importlib

        mod = importlib.import_module(module_path)
        source = inspect.getsource(mod)
        assert "Lineage recording failed" in source
