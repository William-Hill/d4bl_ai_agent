"""Unit tests for data ingestion models (no database required)."""

import uuid

from d4bl.infra.database import (
    DataLineage,
    DataSource,
    IngestionRun,
    KeywordMonitor,
)


def test_data_source_create():
    user_id = uuid.uuid4()
    source = DataSource(
        id=uuid.uuid4(),
        name="Test Census API",
        source_type="api",
        config={"url": "https://api.census.gov/data", "method": "GET"},
        default_schedule="0 2 * * 1",
        enabled=True,
        created_by=user_id,
    )

    assert source.name == "Test Census API"
    assert source.source_type == "api"
    assert source.config["url"] == "https://api.census.gov/data"
    assert source.enabled is True
    assert source.created_by == user_id

    d = source.to_dict()
    assert d["name"] == "Test Census API"
    assert d["source_type"] == "api"
    assert d["enabled"] is True


def test_data_source_valid_types():
    """All valid source_type values can be set on the model."""
    valid_types = ["api", "file_upload", "web_scrape", "rss_feed", "database", "mcp"]
    for stype in valid_types:
        source = DataSource(
            id=uuid.uuid4(),
            name=f"Test {stype}",
            source_type=stype,
            config={},
            enabled=True,
            created_by=uuid.uuid4(),
        )
        assert source.source_type == stype
        assert source.to_dict()["source_type"] == stype


def test_ingestion_run_create():
    source_id = uuid.uuid4()
    user_id = uuid.uuid4()
    run = IngestionRun(
        id=uuid.uuid4(),
        data_source_id=source_id,
        dagster_run_id="dagster-run-abc123",
        status="running",
        trigger_type="manual",
        triggered_by=user_id,
    )

    assert run.data_source_id == source_id
    assert run.status == "running"
    assert run.dagster_run_id == "dagster-run-abc123"
    assert run.trigger_type == "manual"

    d = run.to_dict()
    assert d["data_source_id"] == str(source_id)
    assert d["status"] == "running"
    assert d["trigger_type"] == "manual"


def test_data_lineage_create():
    run_id = uuid.uuid4()
    record_id = uuid.uuid4()
    lineage = DataLineage(
        id=uuid.uuid4(),
        ingestion_run_id=run_id,
        target_table="census_indicators",
        record_id=record_id,
        source_url="https://api.census.gov/data/2022/acs/acs5",
        source_hash="sha256:abc123",
        transformation={"steps": ["fetch", "normalize", "upsert"]},
        quality_score=4.2,
        coverage_metadata={
            "geography": {"covered": ["AL", "MS"], "missing": ["HI"]},
            "demographics": {"races": ["total", "black", "white"]},
        },
        bias_flags={
            "geographic_bias": "Southern states overrepresented",
            "demographic_gaps": ["Native American data absent"],
        },
    )

    assert lineage.quality_score == 4.2
    assert lineage.bias_flags["geographic_bias"] == "Southern states overrepresented"
    assert lineage.target_table == "census_indicators"
    assert lineage.source_hash == "sha256:abc123"

    d = lineage.to_dict()
    assert d["ingestion_run_id"] == str(run_id)
    assert d["record_id"] == str(record_id)
    assert d["quality_score"] == 4.2


def test_keyword_monitor_create():
    source_id = uuid.uuid4()
    user_id = uuid.uuid4()
    monitor = KeywordMonitor(
        id=uuid.uuid4(),
        name="Police Reform Tracker",
        keywords=["police reform", "use of force", "qualified immunity"],
        source_ids=[str(source_id)],
        schedule="0 6 * * *",
        enabled=True,
        created_by=user_id,
    )

    assert "police reform" in monitor.keywords
    assert len(monitor.source_ids) == 1
    assert monitor.name == "Police Reform Tracker"
    assert monitor.enabled is True

    d = monitor.to_dict()
    assert d["name"] == "Police Reform Tracker"
    assert d["keywords"] == ["police reform", "use of force", "qualified immunity"]
    assert d["enabled"] is True
