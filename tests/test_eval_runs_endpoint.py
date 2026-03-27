"""Tests for the /api/eval-runs endpoint."""
from __future__ import annotations

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


class TestEvalRunsEndpoint:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_runs(self):
        from unittest.mock import AsyncMock, MagicMock

        from d4bl.app.api import app

        test_app = _override_auth(app)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def mock_get_db():
            yield mock_session

        from d4bl.infra.database import get_db

        test_app.dependency_overrides[get_db] = mock_get_db

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/eval-runs")

        assert resp.status_code == 200
        data = resp.json()
        assert data["runs"] == []

        test_app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_returns_runs_grouped(self):
        from unittest.mock import AsyncMock, MagicMock

        from d4bl.app.api import app

        test_app = _override_auth(app)

        mock_row = MagicMock()
        mock_row.to_dict.return_value = {
            "id": "abc",
            "model_name": "d4bl-query-parser",
            "model_version": "v1.0",
            "base_model_name": "mistral",
            "task": "query_parser",
            "test_set_hash": "deadbeef",
            "metrics": {"json_valid_rate": 0.97},
            "ship_decision": "ship",
            "blocking_failures": None,
            "created_at": "2026-03-27T00:00:00",
        }

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_row]
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def mock_get_db():
            yield mock_session

        from d4bl.infra.database import get_db

        test_app.dependency_overrides[get_db] = mock_get_db

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/eval-runs")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["runs"]) == 1
        assert data["runs"][0]["model_name"] == "d4bl-query-parser"
        assert data["runs"][0]["ship_decision"] == "ship"

        test_app.dependency_overrides.clear()
