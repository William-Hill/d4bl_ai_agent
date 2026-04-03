"""Tests for ingestion scheduling."""

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from d4bl.infra.database import IngestionSchedule
from d4bl.services.scheduler import (
    DEFAULT_SCHEDULES,
    build_scheduler,
    parse_cron,
)


def test_ingestion_schedule_model_exists():
    """IngestionSchedule model has expected columns."""
    assert hasattr(IngestionSchedule, "id")
    assert hasattr(IngestionSchedule, "source_key")
    assert hasattr(IngestionSchedule, "cron_expression")
    assert hasattr(IngestionSchedule, "enabled")
    assert hasattr(IngestionSchedule, "last_run_at")
    assert hasattr(IngestionSchedule, "last_status")


def test_ingestion_schedule_table_name():
    """Table name is ingestion_schedules."""
    assert IngestionSchedule.__tablename__ == "ingestion_schedules"


def test_ingestion_schedule_to_dict():
    """to_dict returns expected keys."""
    schedule = IngestionSchedule(
        source_key="cdc",
        cron_expression="0 0 15 1 *",
        enabled=True,
    )
    d = schedule.to_dict()
    assert d["source_key"] == "cdc"
    assert d["cron_expression"] == "0 0 15 1 *"
    assert d["enabled"] is True


def test_default_schedules_has_expected_sources():
    """DEFAULT_SCHEDULES covers all existing ingestion sources."""
    expected = {
        "cdc",
        "census_acs",
        "census_decennial",
        "epa",
        "bls",
        "fbi",
        "openstates",
        "hud",
        "usda",
        "doe",
        "bjs",
        "police_violence",
        "rss",
        "news",
        "web",
        "county_health",
        "usaspending",
        "vera",
    }
    assert expected == set(DEFAULT_SCHEDULES.keys())


def test_parse_cron_valid():
    """parse_cron returns a CronTrigger for valid expressions."""
    result = parse_cron("0 6 * * 1")
    assert isinstance(result, CronTrigger)


def test_parse_cron_all_stars():
    """parse_cron handles all-star expression."""
    result = parse_cron("* * * * *")
    assert isinstance(result, CronTrigger)


def test_parse_cron_invalid_raises():
    """parse_cron raises ValueError for malformed expressions."""
    with pytest.raises(ValueError):
        parse_cron("0 6 *")


def test_build_scheduler_returns_async_scheduler():
    """build_scheduler returns an AsyncIOScheduler instance."""
    scheduler = build_scheduler()
    assert isinstance(scheduler, AsyncIOScheduler)