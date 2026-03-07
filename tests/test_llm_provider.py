"""Tests for d4bl.llm.provider — multi-provider LLM factory."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestBuildLlmModelString:
    def test_ollama_provider(self) -> None:
        from d4bl.llm.provider import build_llm_model_string
        assert build_llm_model_string("ollama", "mistral") == "ollama/mistral"

    def test_gemini_provider(self) -> None:
        from d4bl.llm.provider import build_llm_model_string
        assert build_llm_model_string("gemini", "gemini-2.0-flash") == "gemini/gemini-2.0-flash"

    def test_openai_provider(self) -> None:
        from d4bl.llm.provider import build_llm_model_string
        assert build_llm_model_string("openai", "gpt-4o-mini") == "openai/gpt-4o-mini"

    def test_anthropic_provider(self) -> None:
        from d4bl.llm.provider import build_llm_model_string
        assert build_llm_model_string("anthropic", "claude-haiku-4-5-20251001") == "anthropic/claude-haiku-4-5-20251001"


class TestGetLlm:
    @patch("d4bl.llm.provider.get_settings")
    @patch("d4bl.llm.provider.LLM")
    def test_ollama_sets_base_url(self, mock_llm_cls, mock_get_settings) -> None:
        from d4bl.llm.provider import get_llm, reset_llm
        reset_llm()
        mock_settings = MagicMock()
        mock_settings.llm_provider = "ollama"
        mock_settings.llm_model = "mistral"
        mock_settings.llm_api_key = None
        mock_settings.ollama_base_url = "http://localhost:11434"
        mock_get_settings.return_value = mock_settings

        get_llm()

        mock_llm_cls.assert_called_once()
        call_kwargs = mock_llm_cls.call_args[1]
        assert call_kwargs["model"] == "ollama/mistral"
        assert call_kwargs["base_url"] == "http://localhost:11434"
        reset_llm()

    @patch("d4bl.llm.provider.get_settings")
    @patch("d4bl.llm.provider.LLM")
    def test_gemini_sets_api_key(self, mock_llm_cls, mock_get_settings) -> None:
        from d4bl.llm.provider import get_llm, reset_llm
        reset_llm()
        mock_settings = MagicMock()
        mock_settings.llm_provider = "gemini"
        mock_settings.llm_model = "gemini-2.0-flash"
        mock_settings.llm_api_key = "test-gemini-key"
        mock_settings.ollama_base_url = "http://localhost:11434"
        mock_get_settings.return_value = mock_settings

        get_llm()

        mock_llm_cls.assert_called_once()
        call_kwargs = mock_llm_cls.call_args[1]
        assert call_kwargs["model"] == "gemini/gemini-2.0-flash"
        assert call_kwargs["api_key"] == "test-gemini-key"
        assert "base_url" not in call_kwargs
        reset_llm()


class TestGetAvailableModels:
    @patch("d4bl.llm.provider.get_settings")
    def test_returns_configured_model(self, mock_get_settings) -> None:
        from d4bl.llm.provider import get_available_models
        mock_settings = MagicMock()
        mock_settings.llm_provider = "gemini"
        mock_settings.llm_model = "gemini-2.0-flash"
        mock_get_settings.return_value = mock_settings

        models = get_available_models()
        assert len(models) >= 1
        default_model = next(m for m in models if m["is_default"])
        assert default_model["provider"] == "gemini"
        assert default_model["model"] == "gemini-2.0-flash"
