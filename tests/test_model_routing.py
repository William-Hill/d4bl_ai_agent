"""Tests for task-specific model routing."""

from __future__ import annotations

from unittest.mock import patch

from d4bl.llm.ollama_client import model_for_task


class TestModelForTask:
    """model_for_task() resolves the right model name per task."""

    @patch("d4bl.llm.ollama_client.get_settings")
    def test_returns_task_model_when_configured(self, mock_settings):
        mock_settings.return_value.query_parser_model = "d4bl-query-parser"
        mock_settings.return_value.ollama_model = "mistral"
        assert model_for_task("query_parser") == "d4bl-query-parser"

    @patch("d4bl.llm.ollama_client.get_settings")
    def test_falls_back_to_ollama_model_when_empty(self, mock_settings):
        mock_settings.return_value.query_parser_model = ""
        mock_settings.return_value.ollama_model = "mistral"
        assert model_for_task("query_parser") == "mistral"

    @patch("d4bl.llm.ollama_client.get_settings")
    def test_explainer_task(self, mock_settings):
        mock_settings.return_value.explainer_model = "d4bl-explainer"
        mock_settings.return_value.ollama_model = "mistral"
        assert model_for_task("explainer") == "d4bl-explainer"

    @patch("d4bl.llm.ollama_client.get_settings")
    def test_evaluator_task(self, mock_settings):
        mock_settings.return_value.evaluator_model = "d4bl-evaluator"
        mock_settings.return_value.ollama_model = "mistral"
        assert model_for_task("evaluator") == "d4bl-evaluator"

    @patch("d4bl.llm.ollama_client.get_settings")
    def test_explainer_falls_back_when_empty(self, mock_settings) -> None:
        mock_settings.return_value.explainer_model = ""
        mock_settings.return_value.ollama_model = "mistral"
        assert model_for_task("explainer") == "mistral"

    @patch("d4bl.llm.ollama_client.get_settings")
    def test_evaluator_falls_back_when_empty(self, mock_settings) -> None:
        mock_settings.return_value.evaluator_model = ""
        mock_settings.return_value.ollama_model = "mistral"
        assert model_for_task("evaluator") == "mistral"

    @patch("d4bl.llm.ollama_client.get_settings")
    def test_unknown_task_returns_default(self, mock_settings):
        mock_settings.return_value.ollama_model = "mistral"
        assert model_for_task("unknown_task") == "mistral"
