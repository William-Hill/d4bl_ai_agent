"""Tests for the NL query API endpoint."""

from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from d4bl.query.fusion import QueryResult, SourceReference


class TestQueryEndpoint:
    @pytest.mark.asyncio
    @patch("d4bl.app.api.get_query_engine")
    @patch("d4bl.app.api.get_db")
    async def test_post_query_returns_answer(
        self, mock_get_db, mock_get_engine
    ):
        """POST /api/query should return a synthesized answer."""
        # Must import app after patches are set up
        from d4bl.app.api import app

        mock_db = AsyncMock()
        mock_get_db.return_value = mock_db

        mock_engine = MagicMock()
        mock_engine.query = AsyncMock(
            return_value=QueryResult(
                answer="NIL policies in Mississippi allow athletes...",
                sources=[
                    SourceReference(
                        url="https://example.com/nil",
                        title="NIL Policy",
                        snippet="MS NIL policy...",
                        source_type="vector",
                        relevance_score=0.9,
                    )
                ],
                query="NIL policies Mississippi",
            )
        )
        mock_get_engine.return_value = mock_engine

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/query",
                json={
                    "question": "What NIL policies affect Black athletes in Mississippi?"
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "sources" in data
        assert "query" in data
        assert len(data["answer"]) > 0
        assert len(data["sources"]) == 1
        assert data["sources"][0]["source_type"] == "vector"

    @pytest.mark.asyncio
    async def test_post_query_missing_question_returns_422(self):
        """POST /api/query with no question field should return 422."""
        from d4bl.app.api import app

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post("/api/query", json={})

        assert response.status_code == 422
