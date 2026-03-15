"""Tests for the ingestion runner service."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from d4bl.services.ingestion_runner import (
    SCRIPT_REGISTRY,
    resolve_source,
    run_ingestion_task,
)


class TestScriptRegistry:
    def test_registry_has_all_sources_with_aliases(self):
        # 13 canonical sources + 12 aliases = 25 entries
        assert len(SCRIPT_REGISTRY) == 25
        # All values should be valid module names
        modules = set(SCRIPT_REGISTRY.values())
        assert len(modules) == 13

    def test_registry_contains_key_sources(self):
        assert "cdc" in SCRIPT_REGISTRY
        assert "census" in SCRIPT_REGISTRY
        assert "epa" in SCRIPT_REGISTRY
        assert "bjs" in SCRIPT_REGISTRY

    def test_registry_aliases_resolve_same_module(self):
        assert SCRIPT_REGISTRY["census"] == SCRIPT_REGISTRY["census_acs"]
        assert SCRIPT_REGISTRY["cdc"] == SCRIPT_REGISTRY["cdc_places"]


class TestResolveSource:
    def test_exact_match(self):
        assert resolve_source("cdc") == "ingest_cdc_places"

    def test_slugified_match(self):
        assert resolve_source("CDC") == "ingest_cdc_places"
        assert resolve_source("Census ACS") == "ingest_census_acs"

    def test_unknown_source(self):
        assert resolve_source("nonexistent") is None

    def test_empty_string(self):
        assert resolve_source("") is None

    def test_special_characters_stripped(self):
        assert resolve_source("CDC!@#") == "ingest_cdc_places"


def _make_mock_session_factory(run_row):
    """Create a mock async session factory that returns a session with the given run."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = run_row
    session.execute = AsyncMock(return_value=result_mock)
    session.commit = AsyncMock()

    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock(return_value=session)
    return factory, session


def _make_pending_run():
    """Create a mock IngestionRun in pending state."""
    run = MagicMock()
    run.id = uuid.uuid4()
    run.status = "pending"
    run.records_ingested = None
    run.completed_at = None
    run.error_detail = None
    return run


class TestRunIngestionTask:
    @pytest.mark.asyncio
    async def test_successful_run(self):
        """Script main() returns record count → run marked completed."""
        run = _make_pending_run()
        factory, session = _make_mock_session_factory(run)

        mock_module = MagicMock()
        mock_module.main.return_value = 42

        with patch(
            "d4bl.services.ingestion_runner._import_script",
            return_value=mock_module,
        ):
            await run_ingestion_task(run.id, "ingest_test", factory)

        assert run.status == "completed"
        assert run.records_ingested == 42
        assert run.completed_at is not None
        assert run.error_detail is None
        assert session.commit.await_count >= 2

    @pytest.mark.asyncio
    async def test_failed_run(self):
        """Script main() raises → run marked failed with error detail."""
        run = _make_pending_run()
        factory, session = _make_mock_session_factory(run)

        mock_module = MagicMock()
        mock_module.main.side_effect = RuntimeError("API timeout")

        with patch(
            "d4bl.services.ingestion_runner._import_script",
            return_value=mock_module,
        ):
            await run_ingestion_task(run.id, "ingest_test", factory)

        assert run.status == "failed"
        assert "API timeout" in run.error_detail
        assert run.completed_at is not None

    @pytest.mark.asyncio
    async def test_none_return_treated_as_zero(self):
        """Script main() returns None → records_ingested set to 0."""
        run = _make_pending_run()
        factory, session = _make_mock_session_factory(run)

        mock_module = MagicMock()
        mock_module.main.return_value = None

        with patch(
            "d4bl.services.ingestion_runner._import_script",
            return_value=mock_module,
        ):
            await run_ingestion_task(run.id, "ingest_test", factory)

        assert run.status == "completed"
        assert run.records_ingested == 0

    @pytest.mark.asyncio
    async def test_run_not_found_logs_and_returns(self):
        """If the IngestionRun row is not found, task exits gracefully."""
        factory, session = _make_mock_session_factory(None)

        await run_ingestion_task(uuid.uuid4(), "ingest_test", factory)
