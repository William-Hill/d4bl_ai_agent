"""Tests for the QueryEngine orchestrator."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from d4bl.query.engine import QueryEngine
from d4bl.query.fusion import QueryResult, SourceReference
from d4bl.query.parser import ParsedQuery
from d4bl.query.structured import StructuredResult


class TestQueryEngine:
    def setup_method(self):
        self.engine = QueryEngine(
            ollama_base_url="http://localhost:11434"
        )

    @pytest.mark.asyncio
    async def test_query_orchestrates_full_pipeline(self, mock_db_session):
        """query() should parse, search both sources, fuse, and synthesize."""
        self.engine.parser.parse = AsyncMock(
            return_value=ParsedQuery(
                original_query="NIL policies Mississippi",
                intent="information_retrieval",
                entities=["NIL", "Mississippi"],
                search_queries=["NIL policies Mississippi"],
                data_sources=["vector", "structured"],
            )
        )

        self.engine.vector_store.search_similar = AsyncMock(
            return_value=[
                {
                    "url": "https://example.com/nil",
                    "content": "NIL policy content",
                    "similarity": 0.9,
                    "metadata": {"title": "NIL Policy"},
                }
            ]
        )

        self.engine.structured_searcher.search = AsyncMock(
            return_value=[
                StructuredResult(
                    job_id=str(uuid4()),
                    query="NIL research",
                    status="completed",
                    summary="NIL findings...",
                    created_at="2026-01-15",
                    relevance_score=0.8,
                )
            ]
        )

        self.engine.fusion.synthesize = AsyncMock(
            return_value=QueryResult(
                answer="NIL policies in Mississippi...",
                sources=[
                    SourceReference(
                        url="https://example.com/nil",
                        title="NIL Policy",
                        snippet="...",
                        source_type="vector",
                        relevance_score=0.9,
                    )
                ],
                query="NIL policies Mississippi",
            )
        )

        result = await self.engine.query(
            db=mock_db_session,
            question="NIL policies Mississippi",
        )

        assert isinstance(result, QueryResult)
        assert len(result.answer) > 0
        self.engine.parser.parse.assert_called_once()
        self.engine.vector_store.search_similar.assert_called_once()
        self.engine.structured_searcher.search.assert_called_once()
        self.engine.fusion.synthesize.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_vector_only_when_parser_says_so(
        self, mock_db_session
    ):
        """query() should skip structured search if parser says vector only."""
        self.engine.parser.parse = AsyncMock(
            return_value=ParsedQuery(
                original_query="test",
                intent="information_retrieval",
                entities=[],
                search_queries=["test"],
                data_sources=["vector"],
            )
        )
        self.engine.vector_store.search_similar = AsyncMock(return_value=[])
        self.engine.structured_searcher.search = AsyncMock(return_value=[])
        self.engine.fusion.synthesize = AsyncMock(
            return_value=QueryResult(
                answer="No results", sources=[], query="test"
            )
        )

        await self.engine.query(db=mock_db_session, question="test")

        self.engine.vector_store.search_similar.assert_called_once()
        self.engine.structured_searcher.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_query_structured_only_when_parser_says_so(
        self, mock_db_session
    ):
        """query() should skip vector search if parser says structured only."""
        self.engine.parser.parse = AsyncMock(
            return_value=ParsedQuery(
                original_query="how many jobs ran",
                intent="count_query",
                entities=[],
                search_queries=["research jobs count"],
                data_sources=["structured"],
            )
        )
        self.engine.vector_store.search_similar = AsyncMock(return_value=[])
        self.engine.structured_searcher.search = AsyncMock(return_value=[])
        self.engine.fusion.synthesize = AsyncMock(
            return_value=QueryResult(
                answer="No results", sources=[], query="how many jobs ran"
            )
        )

        await self.engine.query(
            db=mock_db_session, question="how many jobs ran"
        )

        self.engine.vector_store.search_similar.assert_not_called()
        self.engine.structured_searcher.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_passes_job_id_to_vector_search(
        self, mock_db_session
    ):
        """query() should forward job_id to vector store search."""
        self.engine.parser.parse = AsyncMock(
            return_value=ParsedQuery(
                original_query="test",
                intent="information_retrieval",
                entities=[],
                search_queries=["test"],
                data_sources=["vector"],
            )
        )
        self.engine.vector_store.search_similar = AsyncMock(return_value=[])
        self.engine.fusion.synthesize = AsyncMock(
            return_value=QueryResult(
                answer="No results", sources=[], query="test"
            )
        )

        job_id = "abc-123"
        await self.engine.query(
            db=mock_db_session, question="test", job_id=job_id
        )

        call_kwargs = self.engine.vector_store.search_similar.call_args[1]
        assert call_kwargs["job_id"] == job_id
