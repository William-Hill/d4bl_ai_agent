"""Tests for the shared Ollama HTTP helper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from d4bl.llm.ollama_client import ollama_generate


class TestOllamaGenerate:
    """Test the ollama_generate helper."""

    @staticmethod
    def _make_aiohttp_mocks(response_body: dict, status: int = 200):
        """Build mock aiohttp session + response."""
        mock_response = MagicMock()
        mock_response.status = status
        mock_response.json = AsyncMock(return_value=response_body)
        mock_response.text = AsyncMock(return_value=str(response_body))
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post.return_value = mock_response
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        return mock_session

    @pytest.mark.asyncio
    @patch("d4bl.llm.ollama_client.aiohttp.ClientSession")
    async def test_returns_response_text(self, mock_session_cls):
        """Should return the 'response' field from Ollama."""
        mock_session = self._make_aiohttp_mocks(
            {"response": "Hello world"}
        )
        mock_session_cls.return_value = mock_session

        result = await ollama_generate(
            base_url="http://localhost:11434",
            prompt="Say hello",
        )
        assert result == "Hello world"

    @pytest.mark.asyncio
    @patch("d4bl.llm.ollama_client.aiohttp.ClientSession")
    async def test_raises_on_non_200(self, mock_session_cls):
        """Should raise RuntimeError on non-200 status."""
        mock_session = self._make_aiohttp_mocks({}, status=500)
        mock_session_cls.return_value = mock_session

        with pytest.raises(RuntimeError, match="500"):
            await ollama_generate(
                base_url="http://localhost:11434",
                prompt="fail",
            )

    @pytest.mark.asyncio
    @patch("d4bl.llm.ollama_client.aiohttp.ClientSession")
    async def test_passes_model_and_temperature(self, mock_session_cls):
        """Should forward model and temperature to Ollama."""
        mock_session = self._make_aiohttp_mocks({"response": "ok"})
        mock_session_cls.return_value = mock_session

        await ollama_generate(
            base_url="http://localhost:11434",
            prompt="test",
            model="llama3",
            temperature=0.5,
        )

        call_kwargs = mock_session.post.call_args
        sent_json = call_kwargs[1]["json"]
        assert sent_json["model"] == "llama3"
        assert sent_json["options"]["temperature"] == 0.5

    @pytest.mark.asyncio
    @patch("d4bl.llm.ollama_client.aiohttp.ClientSession")
    async def test_custom_timeout(self, mock_session_cls):
        """Should accept a custom timeout."""
        mock_session = self._make_aiohttp_mocks({"response": "ok"})
        mock_session_cls.return_value = mock_session

        result = await ollama_generate(
            base_url="http://localhost:11434",
            prompt="test",
            timeout_seconds=120,
        )
        assert result == "ok"
