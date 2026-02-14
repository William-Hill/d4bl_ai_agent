"""Tests for VectorStore embedding generation and search."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from d4bl.infra.vector_store import VectorStore, get_vector_store


class TestVectorStore:
    """Unit tests for VectorStore methods."""

    def setup_method(self):
        self.store = VectorStore(
            ollama_base_url="http://localhost:11434",
            embedder_model="mxbai-embed-large",
        )

    @patch("d4bl.infra.vector_store.requests.post")
    def test_generate_embedding_returns_vector(self, mock_post):
        """generate_embedding should return a list of floats from Ollama."""
        fake_embedding = [0.1] * 1024
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": fake_embedding}
        mock_post.return_value = mock_response

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            self.store.generate_embedding("test text")
        )

        assert isinstance(result, list)
        assert len(result) == 1024
        mock_post.assert_called_once()

    @patch("d4bl.infra.vector_store.requests.post")
    def test_generate_embedding_truncates_long_text(self, mock_post):
        """generate_embedding should truncate text longer than 6000 chars."""
        fake_embedding = [0.2] * 1024
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": fake_embedding}
        mock_post.return_value = mock_response

        import asyncio
        long_text = "x" * 10000
        result = asyncio.get_event_loop().run_until_complete(
            self.store.generate_embedding(long_text)
        )

        assert len(result) == 1024
        # Verify the text sent was truncated
        call_kwargs = mock_post.call_args
        sent_prompt = call_kwargs[1]["json"]["prompt"] if "json" in call_kwargs[1] else call_kwargs[0][0]
        # The prompt should be truncated to 6000 chars
        assert len(sent_prompt) <= 6000

    @pytest.mark.asyncio
    async def test_store_scraped_content_calls_generate_embedding(
        self, mock_db_session
    ):
        """store_scraped_content should generate embedding and insert."""
        job_id = uuid4()
        self.store.generate_embedding = AsyncMock(
            return_value=[0.1] * 1024
        )
        mock_db_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one=MagicMock(return_value=uuid4()))
        )
        mock_db_session.commit = AsyncMock()

        result = await self.store.store_scraped_content(
            db=mock_db_session,
            job_id=job_id,
            url="https://example.com",
            content="Test content about NIL policies in Mississippi",
        )

        self.store.generate_embedding.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_store_scraped_content_skips_short_content(
        self, mock_db_session
    ):
        """store_scraped_content should skip content that is too short."""
        job_id = uuid4()

        result = await self.store.store_scraped_content(
            db=mock_db_session,
            job_id=job_id,
            url="https://example.com",
            content="short",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_search_similar_generates_query_embedding(
        self, mock_db_session
    ):
        """search_similar should generate embedding for the query text."""
        self.store.generate_embedding = AsyncMock(
            return_value=[0.1] * 1024
        )

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        await self.store.search_similar(
            db=mock_db_session,
            query_text="NIL policies Mississippi",
            limit=5,
        )

        self.store.generate_embedding.assert_called_once_with(
            "NIL policies Mississippi"
        )

    @pytest.mark.asyncio
    async def test_store_batch_stores_multiple_items(self, mock_db_session):
        """store_batch should store each item and return count."""
        self.store.generate_embedding = AsyncMock(
            return_value=[0.1] * 1024
        )
        mock_db_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one=MagicMock(return_value=uuid4()))
        )
        mock_db_session.commit = AsyncMock()

        items = [
            {"url": "https://example.com/1", "content": "Content about NIL policy one"},
            {"url": "https://example.com/2", "content": "Content about NIL policy two"},
        ]

        count = await self.store.store_batch(
            db=mock_db_session,
            job_id=uuid4(),
            items=items,
        )

        assert count == 2
        assert self.store.generate_embedding.call_count == 2


class TestGetVectorStore:
    """Test the singleton factory."""

    def test_returns_vector_store_instance(self):
        store = get_vector_store()
        assert isinstance(store, VectorStore)

    def test_returns_same_instance(self):
        store1 = get_vector_store()
        store2 = get_vector_store()
        assert store1 is store2
