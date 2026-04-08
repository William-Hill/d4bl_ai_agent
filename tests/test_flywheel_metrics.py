"""Tests for GET /api/admin/flywheel-metrics endpoint."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient


class TestFlywheelMetricsAuth:
    """Flywheel metrics endpoint requires admin auth."""

    def test_requires_auth(self, _patch_settings):
        from d4bl.app.api import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/admin/flywheel-metrics")
        assert response.status_code == 401


class TestFlywheelMetricsEmpty:
    """Flywheel metrics with no data returns zero-value defaults."""

    def test_empty_database(self, override_admin_auth):
        from d4bl.infra.database import get_db

        app = override_admin_auth

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def mock_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = mock_get_db

        try:
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/admin/flywheel-metrics")
            assert response.status_code == 200
            data = response.json()

            assert data["corpus"]["total_chunks"] == 0
            assert data["corpus"]["total_tokens"] == 0
            assert data["corpus"]["content_types"] == {}
            assert data["corpus"]["unstructured_pct"] == 0.0
            assert data["training_runs"] == []
            assert data["research_quality"] == {}
            assert data["time_series"]["corpus_diversity"] == []
            assert data["time_series"]["model_accuracy"] == []
            assert data["time_series"]["research_quality"] == []
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestFlywheelMetricsWithData:
    """Flywheel metrics with data returns computed values."""

    def test_with_corpus_and_training_data(self, override_admin_auth):
        from d4bl.infra.database import get_db

        app = override_admin_auth

        mock_db = AsyncMock()
        call_count = 0

        async def mock_execute(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()

            if call_count == 1:
                # Corpus query
                mock_result.mappings.return_value.all.return_value = [
                    {"content_type": "policy_bill", "chunk_count": 200, "total_tokens": 500000},
                    {"content_type": "research_report", "chunk_count": 100, "total_tokens": 250000},
                ]
            elif call_count == 2:
                # Training runs query
                mock_result.mappings.return_value.all.return_value = [
                    {
                        "model_version": "v3.0",
                        "task": "parser",
                        "metrics": {
                            "entity_f1": 0.82,
                            "hallucination_accuracy": 0.91,
                            "corpus_stats": {
                                "structured_passages": 1000,
                                "unstructured_passages": 300,
                            },
                        },
                        "ship_decision": "ship",
                        "created_at": datetime(2026, 3, 15, tzinfo=timezone.utc),
                    },
                ]
            elif call_count == 3:
                # Combined evaluation_results query (per eval_name + month)
                mock_result.mappings.return_value.all.return_value = [
                    {"eval_name": "hallucination_accuracy", "month": datetime(2026, 3, 1, tzinfo=timezone.utc), "avg_score": 0.88, "eval_count": 42},
                    {"eval_name": "relevance", "month": datetime(2026, 3, 1, tzinfo=timezone.utc), "avg_score": 0.76, "eval_count": 42},
                ]
            else:
                mock_result.mappings.return_value.all.return_value = []

            return mock_result

        mock_db.execute = mock_execute

        async def mock_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = mock_get_db

        try:
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/admin/flywheel-metrics")
            assert response.status_code == 200
            data = response.json()

            assert data["corpus"]["total_chunks"] == 300
            assert data["corpus"]["total_tokens"] == 750000
            assert data["corpus"]["content_types"]["policy_bill"] == 200

            assert len(data["training_runs"]) == 1
            assert data["training_runs"][0]["model_version"] == "v3.0"

            assert "hallucination_accuracy" in data["research_quality"]
            assert data["research_quality"]["hallucination_accuracy"]["avg_score"] == 0.88

            assert len(data["time_series"]["corpus_diversity"]) == 1
            assert len(data["time_series"]["model_accuracy"]) == 1
            assert len(data["time_series"]["research_quality"]) == 1
        finally:
            app.dependency_overrides.pop(get_db, None)
