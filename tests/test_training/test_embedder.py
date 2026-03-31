"""Tests for the batch embedder utility."""

from unittest.mock import AsyncMock, patch

import pytest

from scripts.training.embedder import batch_embed, format_embedding_for_pg


class TestFormatEmbedding:
    def test_formats_as_pgvector_string(self):
        vec = [1.0, 2.5, -3.0]
        result = format_embedding_for_pg(vec)
        assert result == "[1.0,2.5,-3.0]"

    def test_empty_vector(self):
        assert format_embedding_for_pg([]) == "[]"


class TestBatchEmbed:
    @pytest.mark.asyncio
    async def test_returns_embeddings_for_each_text(self):
        fake_embedding = [0.1] * 1024
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"embedding": fake_embedding})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            results = await batch_embed(["hello", "world"])

        assert len(results) == 2
        assert len(results[0]) == 1024

    @pytest.mark.asyncio
    async def test_truncates_long_text(self):
        long_text = "a " * 4000  # 8000 chars
        fake_embedding = [0.1] * 1024
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"embedding": fake_embedding})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            results = await batch_embed([long_text])

        assert len(results) == 1
        call_args = mock_session.post.call_args
        sent_prompt = call_args[1]["json"]["prompt"]
        assert len(sent_prompt) <= 6000
