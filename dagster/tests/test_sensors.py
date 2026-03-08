"""Unit tests for Dagster sensors."""

from d4bl_pipelines.sensors import (
    EMBEDDING_SENSOR_INTERVAL,
    EMBEDDING_SOURCE_TYPES,
    _get_recent_completed_runs,
    file_upload_sensor,
    vector_embedding_sensor,
)


def test_file_upload_sensor_is_importable():
    """The file_upload_sensor should be importable and defined."""
    assert file_upload_sensor is not None


def test_vector_embedding_sensor_is_importable():
    """The vector_embedding_sensor should be importable and defined."""
    assert vector_embedding_sensor is not None


def test_file_upload_sensor_name():
    """The file_upload_sensor should have the expected Dagster name."""
    assert file_upload_sensor.name == "file_upload_sensor"


def test_vector_embedding_sensor_name():
    """The vector_embedding_sensor should have the expected Dagster name."""
    assert vector_embedding_sensor.name == "vector_embedding_sensor"


def test_vector_embedding_sensor_interval():
    """The embedding sensor should use the configured minimum interval."""
    assert EMBEDDING_SENSOR_INTERVAL == 60


def test_embedding_source_types():
    """The source types targeted for embedding should include web and RSS."""
    assert "web_scrape" in EMBEDDING_SOURCE_TYPES
    assert "rss_feed" in EMBEDDING_SOURCE_TYPES


def test_get_recent_completed_runs_is_callable():
    """The helper function should be callable."""
    assert callable(_get_recent_completed_runs)
