"""End-to-end smoke test for the data ingestion pipeline.

Exercises the full API flow: create source -> trigger run -> check status ->
query lineage -> test connection -> verify provenance in query results.

Uses mocked DB and ingestion runner to avoid external dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from d4bl.app.auth import CurrentUser, get_current_user
from d4bl.app.schemas import QuerySourceItem
from d4bl.infra.database import (
    DataLineage,
    DataSource,
    IngestionRun,
    get_db,
)
from d4bl.query.fusion import ResultFusion
from d4bl.query.structured import ProvenanceInfo, StructuredResult

# ---- Constants ----

SOURCE_ID = uuid4()
RUN_ID = uuid4()
RECORD_ID = uuid4()
LINEAGE_ID = uuid4()
NOW = datetime.now(timezone.utc)

MOCK_ADMIN = CurrentUser(id=uuid4(), email="admin@test.com", role="admin")


def _make_source(**overrides) -> MagicMock:
    source = MagicMock(spec=DataSource)
    source.id = overrides.get("id", SOURCE_ID)
    source.name = overrides.get("name", "Census ACS")
    source.source_type = overrides.get("source_type", "api")
    source.config = overrides.get("config", {"url": "https://api.census.gov"})
    source.default_schedule = None
    source.enabled = True
    source.created_by = None
    source.created_at = NOW
    source.updated_at = NOW
    source.to_dict = MagicMock(
        return_value={
            "id": str(source.id),
            "name": source.name,
            "source_type": source.source_type,
            "config": source.config,
            "default_schedule": None,
            "enabled": True,
            "created_by": None,
            "created_at": NOW.isoformat(),
            "updated_at": NOW.isoformat(),
        }
    )
    return source


def _make_run(**overrides) -> MagicMock:
    run = MagicMock(spec=IngestionRun)
    run.id = overrides.get("id", RUN_ID)
    run.data_source_id = SOURCE_ID
    run.status = overrides.get("status", "completed")
    run.trigger_type = "manual"
    run.triggered_by = None
    run.records_ingested = 150
    run.started_at = NOW
    run.completed_at = NOW
    run.error_detail = None
    run.to_dict = MagicMock(
        return_value={
            "id": str(run.id),
            "data_source_id": str(SOURCE_ID),
            "status": run.status,
            "trigger_type": "manual",
            "triggered_by": None,
            "records_ingested": 150,
            "started_at": NOW.isoformat(),
            "completed_at": NOW.isoformat(),
            "error_detail": None,
        }
    )
    return run


def _make_lineage() -> MagicMock:
    lineage = MagicMock(spec=DataLineage)
    lineage.id = LINEAGE_ID
    lineage.ingestion_run_id = RUN_ID
    lineage.target_table = "census_indicators"
    lineage.record_id = RECORD_ID
    lineage.source_url = "https://api.census.gov/data/2022/acs/acs5"
    lineage.source_hash = "abc123"
    lineage.transformation = {"steps": ["fetch", "compute_rate", "upsert"]}
    lineage.quality_score = 4.5
    lineage.coverage_metadata = {"gaps": ["Missing tribal data"]}
    lineage.bias_flags = ["single_source: Census ACS only"]
    lineage.retrieved_at = NOW
    lineage.to_dict = MagicMock(
        return_value={
            "id": str(LINEAGE_ID),
            "ingestion_run_id": str(RUN_ID),
            "target_table": "census_indicators",
            "record_id": str(RECORD_ID),
            "source_url": "https://api.census.gov/data/2022/acs/acs5",
            "source_hash": "abc123",
            "transformation": {"steps": ["fetch", "compute_rate", "upsert"]},
            "quality_score": 4.5,
            "coverage_metadata": {"gaps": ["Missing tribal data"]},
            "bias_flags": ["single_source: Census ACS only"],
            "retrieved_at": NOW.isoformat(),
        }
    )
    return lineage


@pytest.fixture
def e2e_app():
    """App with admin auth and mock DB overrides."""
    from d4bl.app.api import app

    mock_session = AsyncMock()

    async def _override_db():
        yield mock_session

    original = app.dependency_overrides.copy()
    app.dependency_overrides[get_current_user] = lambda: MOCK_ADMIN
    app.dependency_overrides[get_db] = _override_db

    try:
        yield app, mock_session
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)


class TestE2EIngestionPipeline:
    """End-to-end smoke test covering the full ingestion pipeline."""

    @pytest.mark.asyncio
    async def test_create_source(self, e2e_app):
        """Step 1: Create a data source via API."""
        app, mock_session = e2e_app
        source = _make_source()

        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        with patch("d4bl.app.data_routes.DataSource", return_value=source):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/api/data/sources",
                    json={
                        "name": "Census ACS",
                        "source_type": "api",
                        "config": {"url": "https://api.census.gov"},
                    },
                )

        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Census ACS"
        assert body["source_type"] == "api"

    @pytest.mark.asyncio
    async def test_trigger_run(self, e2e_app):
        """Step 2: Trigger an ingestion run for a data source."""
        app, mock_session = e2e_app
        source = _make_source()
        run = _make_run(status="pending")

        # Trigger does 4 db.execute calls:
        # 1. source lookup, 2. FOR UPDATE lock, 3. stale run query, 4. concurrency guard
        source_result = MagicMock()
        source_result.scalar_one_or_none = MagicMock(return_value=source)
        lock_result = MagicMock()  # FOR UPDATE result (unused)
        stale_result = MagicMock()
        stale_result.scalars = MagicMock(return_value=iter([]))  # no stale runs
        no_run_result = MagicMock()
        no_run_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute = AsyncMock(
            side_effect=[source_result, lock_result, stale_result, no_run_result]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        async def _refresh(obj):
            obj.id = RUN_ID

        mock_session.refresh = AsyncMock(side_effect=_refresh)

        with (
            patch(
                "d4bl.app.data_routes.resolve_source",
                return_value="ingest_census_acs",
            ),
            patch(
                "d4bl.app.data_routes.run_ingestion_task",
                new_callable=AsyncMock,
            ),
            patch(
                "d4bl.app.data_routes.asyncio.create_task",
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(f"/api/data/sources/{SOURCE_ID}/trigger")

        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "triggered"
        assert body["ingestion_run_id"] == str(RUN_ID)

    @pytest.mark.asyncio
    async def test_lineage_query(self, e2e_app):
        """Step 5: Query lineage for a specific record."""
        app, mock_session = e2e_app
        lineage = _make_lineage()

        mock_result = MagicMock()
        mock_result.all = MagicMock(return_value=[(lineage, "Census ACS", "api")])
        mock_session.execute = AsyncMock(return_value=mock_result)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(f"/api/data/lineage/census_indicators/{RECORD_ID}")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["target_table"] == "census_indicators"
        assert body[0]["quality_score"] == 4.5
        assert body[0]["data_source_name"] == "Census ACS"
        assert body[0]["data_source_type"] == "api"

    @pytest.mark.asyncio
    async def test_lineage_graph(self, e2e_app):
        """Step 5b: Get the asset dependency graph."""
        app, mock_session = e2e_app
        source = _make_source()

        mock_result = MagicMock()
        mock_result.all = MagicMock(return_value=[(source, "completed", NOW, 150)])
        mock_session.execute = AsyncMock(return_value=mock_result)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/data/lineage/graph")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["nodes"]) == 1
        assert body["nodes"][0]["asset_key"] == "census_acs"
        assert body["nodes"][0]["record_count"] == 150

    @pytest.mark.asyncio
    async def test_test_connection(self, e2e_app):
        """Step 6: Test connection validates a source config."""
        app, mock_session = e2e_app
        source = _make_source()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=source)
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_http = AsyncMock()
        mock_http.head = MagicMock(return_value=mock_resp)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "d4bl.app.data_routes.aiohttp.ClientSession",
            return_value=mock_http,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(f"/api/data/sources/{SOURCE_ID}/test")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "200" in body["message"]

    @pytest.mark.asyncio
    async def test_provenance_in_query_results(self):
        """Step 7-8: Provenance metadata flows through to query results."""
        provenance = ProvenanceInfo(
            data_source_name="Census ACS",
            quality_score=4.5,
            coverage_gaps=["Missing tribal data"],
        )
        result = StructuredResult(
            job_id="job-123",
            query="homeownership rates by race",
            status="completed",
            summary="Black homeownership is 44% vs 74% white...",
            created_at="2026-03-01T00:00:00",
            relevance_score=0.85,
            provenance=[provenance],
        )

        fusion = ResultFusion.__new__(ResultFusion)
        sources = fusion.merge_and_rank([], [result])

        assert len(sources) == 1
        src = sources[0]
        assert src.data_source_name == "Census ACS"
        assert src.quality_score == 4.5
        assert src.last_updated == "2026-03-01T00:00:00"
        assert src.coverage_notes == "Missing tribal data"

        # Verify it maps to the API schema correctly
        item = QuerySourceItem(
            url=src.url,
            title=src.title,
            snippet=src.snippet,
            source_type=src.source_type,
            relevance_score=src.relevance_score,
            data_source_name=src.data_source_name,
            quality_score=src.quality_score,
            last_updated=src.last_updated,
            coverage_notes=src.coverage_notes,
        )
        assert item.data_source_name == "Census ACS"
        assert item.quality_score == 4.5
