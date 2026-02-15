"""Tests for result fusion and answer synthesis."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from d4bl.query.fusion import ResultFusion, QueryResult, SourceReference
from d4bl.query.structured import StructuredResult


class TestSourceReference:
    def test_from_vector_result(self):
        ref = SourceReference(
            url="https://example.com/nil",
            title="NIL Policy",
            snippet="Mississippi NIL policy...",
            source_type="vector",
            relevance_score=0.85,
        )
        assert ref.source_type == "vector"
        assert ref.relevance_score == 0.85


class TestQueryResult:
    def test_query_result_fields(self):
        qr = QueryResult(
            answer="NIL policies in Mississippi allow...",
            sources=[
                SourceReference(
                    url="https://example.com",
                    title="Source",
                    snippet="...",
                    source_type="vector",
                    relevance_score=0.9,
                )
            ],
            query="NIL policies Mississippi",
        )
        assert len(qr.sources) == 1
        assert qr.answer.startswith("NIL")


class TestResultFusion:
    def setup_method(self):
        self.fusion = ResultFusion(
            ollama_base_url="http://localhost:11434"
        )

    def test_merge_and_rank_combines_sources(self):
        """Should merge vector and structured results."""
        vector_results = [
            {
                "url": "https://example.com/nil",
                "content": "NIL policy content",
                "similarity": 0.9,
                "content_type": "html",
                "metadata": {"title": "NIL Policy"},
            },
            {
                "url": "https://example.com/other",
                "content": "Other content",
                "similarity": 0.7,
                "content_type": "html",
                "metadata": {},
            },
        ]
        structured_results = [
            StructuredResult(
                job_id=str(uuid4()),
                query="NIL policies",
                status="completed",
                summary="Research found that NIL policies...",
                created_at="2026-01-15T00:00:00",
                relevance_score=0.8,
            ),
        ]

        merged = self.fusion.merge_and_rank(
            vector_results, structured_results
        )
        assert len(merged) == 3
        source_types = {s.source_type for s in merged}
        assert "vector" in source_types
        assert "structured" in source_types

    def test_merge_and_rank_deduplicates_by_url(self):
        """Duplicate URLs from vector results should be deduplicated."""
        vector_results = [
            {
                "url": "https://example.com/nil",
                "content": "Content v1",
                "similarity": 0.9,
                "metadata": {},
            },
            {
                "url": "https://example.com/nil",
                "content": "Content v2",
                "similarity": 0.8,
                "metadata": {},
            },
        ]

        merged = self.fusion.merge_and_rank(vector_results, [])
        assert len(merged) == 1

    def test_merge_and_rank_sorts_by_relevance(self):
        """Results should be sorted by relevance score descending."""
        vector_results = [
            {"url": "https://a.com", "content": "A", "similarity": 0.5, "metadata": {}},
            {"url": "https://b.com", "content": "B", "similarity": 0.9, "metadata": {}},
        ]

        merged = self.fusion.merge_and_rank(vector_results, [])
        assert merged[0].relevance_score > merged[1].relevance_score

    @pytest.mark.asyncio
    @patch("d4bl.query.fusion.aiohttp.ClientSession")
    async def test_synthesize_returns_query_result(self, mock_session_cls):
        """synthesize() should return a QueryResult with an answer."""
        llm_response = {
            "response": "Based on the available research, NIL policies in Mississippi allow college athletes to profit from their name, image, and likeness."
        }
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=llm_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        sources = [
            SourceReference(
                url="https://example.com/nil",
                title="NIL Policy",
                snippet="Mississippi NIL policy content...",
                source_type="vector",
                relevance_score=0.9,
            ),
        ]

        result = await self.fusion.synthesize(
            query="What NIL policies affect Black athletes in Mississippi?",
            sources=sources,
        )

        assert isinstance(result, QueryResult)
        assert len(result.answer) > 0
        assert len(result.sources) == 1

    @pytest.mark.asyncio
    async def test_synthesize_no_sources_returns_no_results_message(self):
        """synthesize() with no sources should say no results found."""
        result = await self.fusion.synthesize(
            query="Nonexistent topic xyz",
            sources=[],
        )
        assert isinstance(result, QueryResult)
        assert "no" in result.answer.lower()

    @pytest.mark.asyncio
    @patch("d4bl.query.fusion.aiohttp.ClientSession")
    async def test_synthesize_falls_back_on_llm_failure(self, mock_session_cls):
        """synthesize() should fall back to raw sources if LLM fails."""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        sources = [
            SourceReference(
                url="https://example.com",
                title="Test Source",
                snippet="Some content...",
                source_type="vector",
                relevance_score=0.9,
            ),
        ]

        result = await self.fusion.synthesize(
            query="test query",
            sources=sources,
        )

        assert isinstance(result, QueryResult)
        # Fallback answer should contain the source title
        assert "Test Source" in result.answer
