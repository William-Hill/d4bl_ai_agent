"""Tests for ingestion scheduling."""

import pytest
from d4bl.infra.database import IngestionSchedule


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
