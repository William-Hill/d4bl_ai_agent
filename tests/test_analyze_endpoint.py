"""Tests for POST /api/eval-runs/{id}/analyze endpoint."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


def _override_auth(app):
    from d4bl.app.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-user-id",
        "email": "test@test.com",
        "role": "user",
    }
    return app


def _mock_db_with_run(run_obj):
    """Create a mock async DB session that returns the given run object."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = run_obj
    mock_session.execute = AsyncMock(return_value=mock_result)
    return mock_session


class TestAnalyzeEndpoint:
    @pytest.mark.asyncio
    async def test_returns_existing_analysis_when_present(self):
        from d4bl.app.api import app
        from d4bl.infra.database import get_db

        test_app = _override_auth(app)
        run_id = str(uuid.uuid4())

        mock_run = MagicMock()
        mock_run.id = run_id
        mock_run.task = "query_parser"
        mock_run.metrics = {"entity_f1": 0.72}
        mock_run.suggestions = {
            "rules": [{"metric": "entity_f1", "severity": "blocking", "current": 0.72, "target": 0.80, "suggestion": "Add diverse entities", "category": "training_data"}],
            "llm_analysis": "Previously analyzed",
            "generated_at": "2026-03-27T00:00:00Z",
        }

        mock_session = _mock_db_with_run(mock_run)

        async def mock_get_db():
            yield mock_session

        test_app.dependency_overrides[get_db] = mock_get_db

        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            resp = await client.post(f"/api/eval-runs/{run_id}/analyze")
            assert resp.status_code == 200
            data = resp.json()
            assert data["suggestions"]["llm_analysis"] == "Previously analyzed"

        test_app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_returns_404_for_unknown_run(self):
        from d4bl.app.api import app
        from d4bl.infra.database import get_db

        test_app = _override_auth(app)
        run_id = str(uuid.uuid4())

        mock_session = _mock_db_with_run(None)

        async def mock_get_db():
            yield mock_session

        test_app.dependency_overrides[get_db] = mock_get_db

        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            resp = await client.post(f"/api/eval-runs/{run_id}/analyze")
            assert resp.status_code == 404

        test_app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_force_regenerates_analysis(self):
        """Verify ?force=true clears existing llm_analysis and regenerates."""
        from d4bl.app.api import app
        from d4bl.infra.database import get_db

        test_app = _override_auth(app)
        run_id = str(uuid.uuid4())

        mock_run = MagicMock()
        mock_run.id = run_id
        mock_run.task = "query_parser"
        mock_run.metrics = {"entity_f1": 0.72}
        mock_run.suggestions = {
            "rules": [],
            "llm_analysis": "Old analysis that should be cleared",
            "generated_at": "2026-03-27T00:00:00Z",
        }

        mock_session = _mock_db_with_run(mock_run)

        async def mock_get_db():
            yield mock_session

        test_app.dependency_overrides[get_db] = mock_get_db

        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            resp = await client.post(f"/api/eval-runs/{run_id}/analyze?force=true")
            assert resp.status_code == 200
            data = resp.json()
            # force=true clears old LLM analysis (LLM integration deferred)
            assert data["suggestions"]["llm_analysis"] is None
            # Rules still generated
            assert any(r["metric"] == "entity_f1" for r in data["suggestions"]["rules"])

        test_app.dependency_overrides.clear()
