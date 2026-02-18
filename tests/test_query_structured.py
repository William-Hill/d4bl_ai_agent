"""Tests for structured database search."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from d4bl.query.structured import StructuredSearcher, StructuredResult


class TestStructuredResult:
    def test_result_fields(self):
        r = StructuredResult(
            job_id=str(uuid4()),
            query="NIL policies",
            status="completed",
            summary="Research on NIL",
            created_at="2026-01-01T00:00:00",
            relevance_score=0.8,
        )
        assert r.status == "completed"
        assert r.relevance_score == 0.8


class TestStructuredSearcher:
    def setup_method(self):
        self.searcher = StructuredSearcher()

    @pytest.mark.asyncio
    async def test_search_by_keyword_returns_matching_jobs(
        self, mock_db_session
    ):
        """search() should return jobs whose query matches keywords."""
        mock_row = MagicMock()
        mock_row.job_id = uuid4()
        mock_row.query = "Mississippi NIL policy impact on Black athletes"
        mock_row.status = "completed"
        mock_row.result = {"summary": "NIL policies in MS..."}
        mock_row.research_data = {"source_urls": ["https://example.com"]}
        mock_row.created_at = datetime(2026, 1, 15)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_row]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        results = await self.searcher.search(
            db=mock_db_session,
            search_queries=["NIL policies Mississippi"],
            limit=5,
        )

        assert len(results) == 1
        assert results[0].query == "Mississippi NIL policy impact on Black athletes"
        assert results[0].relevance_score > 0
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_empty(self, mock_db_session):
        """search() with empty queries should return empty list."""
        results = await self.searcher.search(
            db=mock_db_session,
            search_queries=[],
            limit=5,
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_search_skips_short_keywords(self, mock_db_session):
        """search() should skip keywords shorter than 3 chars."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        results = await self.searcher.search(
            db=mock_db_session,
            search_queries=["an of"],  # All words < 3 chars
            limit=5,
        )
        assert results == []

    def test_score_relevance_full_overlap(self):
        """Full keyword overlap should score 1.0."""
        score = self.searcher._score_relevance(
            "NIL policies Mississippi",
            ["NIL policies Mississippi"],
        )
        assert score == 1.0

    def test_score_relevance_partial_overlap(self):
        """Partial keyword overlap should score between 0 and 1."""
        score = self.searcher._score_relevance(
            "Mississippi NIL policy impact",
            ["NIL policies California"],
        )
        assert 0 < score < 1.0

    def test_extract_summary_from_dict(self):
        """Should extract summary key from result dict."""
        summary = self.searcher._extract_summary(
            {"summary": "NIL analysis results"}
        )
        assert summary == "NIL analysis results"

    def test_extract_summary_none(self):
        """Should return None for None result."""
        assert self.searcher._extract_summary(None) is None
