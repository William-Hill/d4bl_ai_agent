import uuid

import pytest
from sqlalchemy import select

from d4bl.infra.database import (
    DataLineage,
    DataSource,
    IngestionRun,
    KeywordMonitor,
    create_tables,
    get_db,
)


@pytest.fixture
async def db_session():
    await create_tables()
    async for session in get_db():
        yield session


@pytest.mark.asyncio
async def test_data_source_create(db_session):
    source = DataSource(
        name="Test Census API",
        source_type="api",
        config={"url": "https://api.census.gov/data", "method": "GET"},
        default_schedule="0 2 * * 1",
        enabled=True,
        created_by=uuid.uuid4(),
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    assert source.id is not None
    assert source.source_type == "api"
    assert source.config["url"] == "https://api.census.gov/data"
    assert source.enabled is True


@pytest.mark.asyncio
async def test_data_source_valid_types_persist(db_session):
    """Valid source_type values can be persisted."""
    for stype in ["api", "file_upload", "web_scrape", "rss_feed", "database", "mcp"]:
        source = DataSource(
            name=f"Test {stype}",
            source_type=stype,
            config={},
            enabled=True,
            created_by=uuid.uuid4(),
        )
        db_session.add(source)
    await db_session.commit()

    result = await db_session.execute(select(DataSource))
    sources = result.scalars().all()
    assert len(sources) >= 6


@pytest.mark.asyncio
async def test_ingestion_run_create(db_session):
    source = DataSource(
        name="Test Source",
        source_type="api",
        config={},
        enabled=True,
        created_by=uuid.uuid4(),
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    run = IngestionRun(
        data_source_id=source.id,
        dagster_run_id="dagster-run-abc123",
        status="running",
        trigger_type="manual",
        triggered_by=uuid.uuid4(),
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    assert run.id is not None
    assert run.data_source_id == source.id
    assert run.status == "running"


@pytest.mark.asyncio
async def test_data_lineage_create(db_session):
    source = DataSource(
        name="Test Source",
        source_type="api",
        config={},
        enabled=True,
        created_by=uuid.uuid4(),
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    run = IngestionRun(
        data_source_id=source.id,
        status="completed",
        trigger_type="scheduled",
        records_ingested=150,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    lineage = DataLineage(
        ingestion_run_id=run.id,
        target_table="census_indicators",
        record_id=uuid.uuid4(),
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
    db_session.add(lineage)
    await db_session.commit()
    await db_session.refresh(lineage)

    assert lineage.id is not None
    assert lineage.quality_score == 4.2
    assert lineage.bias_flags["geographic_bias"] == "Southern states overrepresented"


@pytest.mark.asyncio
async def test_keyword_monitor_create(db_session):
    source = DataSource(
        name="News API",
        source_type="api",
        config={},
        enabled=True,
        created_by=uuid.uuid4(),
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    monitor = KeywordMonitor(
        name="Police Reform Tracker",
        keywords=["police reform", "use of force", "qualified immunity"],
        source_ids=[str(source.id)],
        schedule="0 6 * * *",
        enabled=True,
        created_by=uuid.uuid4(),
    )
    db_session.add(monitor)
    await db_session.commit()
    await db_session.refresh(monitor)

    assert monitor.id is not None
    assert "police reform" in monitor.keywords
    assert len(monitor.source_ids) == 1
