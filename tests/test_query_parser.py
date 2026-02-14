"""Tests for the NL query parser."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from d4bl.query.parser import QueryParser, ParsedQuery


class TestParsedQuery:
    """Test the ParsedQuery data model."""

    def test_parsed_query_defaults(self):
        pq = ParsedQuery(
            original_query="What are NIL policies in Mississippi?",
            intent="information_retrieval",
            entities=["NIL", "Mississippi"],
            search_queries=["NIL policies Mississippi"],
            data_sources=["vector"],
        )
        assert pq.original_query == "What are NIL policies in Mississippi?"
        assert pq.intent == "information_retrieval"
        assert "NIL" in pq.entities
        assert "vector" in pq.data_sources

    def test_parsed_query_with_structured_source(self):
        pq = ParsedQuery(
            original_query="How many research jobs have run?",
            intent="count_query",
            entities=[],
            search_queries=["research jobs count"],
            data_sources=["structured"],
        )
        assert "structured" in pq.data_sources


class TestQueryParser:
    """Test the QueryParser LLM-based parsing."""

    def setup_method(self):
        self.parser = QueryParser(
            ollama_base_url="http://localhost:11434"
        )

    @pytest.mark.asyncio
    @patch("d4bl.query.parser.aiohttp.ClientSession")
    async def test_parse_returns_parsed_query(self, mock_session_cls):
        """parse() should return a ParsedQuery with extracted entities."""
        llm_response = {
            "response": '{"intent": "information_retrieval", "entities": ["NIL", "Mississippi", "Black athletes"], "search_queries": ["NIL policies Mississippi Black athletes"], "data_sources": ["vector", "structured"]}'
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

        result = await self.parser.parse(
            "What NIL policies affect Black athletes in Mississippi?"
        )

        assert isinstance(result, ParsedQuery)
        assert result.intent == "information_retrieval"
        assert "NIL" in result.entities
        assert len(result.search_queries) > 0
        assert "vector" in result.data_sources

    @pytest.mark.asyncio
    @patch("d4bl.query.parser.aiohttp.ClientSession")
    async def test_parse_falls_back_on_llm_failure(self, mock_session_cls):
        """parse() should return a fallback ParsedQuery if LLM fails."""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        result = await self.parser.parse("NIL policies Mississippi")

        assert isinstance(result, ParsedQuery)
        assert result.original_query == "NIL policies Mississippi"
        assert result.search_queries == ["NIL policies Mississippi"]
        assert "vector" in result.data_sources
        assert "structured" in result.data_sources
