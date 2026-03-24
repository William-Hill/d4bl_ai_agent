"""Integration tests for D4BL fine-tuned models via Ollama.

These tests require the models to be registered in Ollama.
Run after `python scripts/training/register_models.py`.

Skip automatically if Ollama is not running or models aren't loaded.
"""

from __future__ import annotations

import json
import subprocess
import time

import pytest

from scripts.training.validate_model_output import (
    validate_evaluator_output,
    validate_explainer_output,
    validate_parser_output,
)


def _get_ollama_models() -> set[str] | None:
    """Return loaded model names, or None if Ollama is unreachable."""
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return None
        lines = result.stdout.strip().splitlines()
        if len(lines) <= 1:
            return set()
        return {line.split()[0] for line in lines[1:] if line.strip()}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


_OLLAMA_MODELS = _get_ollama_models()


def _ollama_available() -> bool:
    return _OLLAMA_MODELS is not None


def _model_loaded(model_name: str) -> bool:
    if _OLLAMA_MODELS is None:
        return False
    return model_name in _OLLAMA_MODELS or f"{model_name}:latest" in _OLLAMA_MODELS


def _run_model(model_name: str, prompt: str, timeout: int = 120) -> str:
    """Run a prompt through an Ollama model and return the response."""
    result = subprocess.run(
        ["ollama", "run", model_name, prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Ollama run failed: {result.stderr}")
    return result.stdout.strip()


skip_no_ollama = pytest.mark.skipif(
    not _ollama_available(), reason="Ollama not running"
)


@skip_no_ollama
class TestQueryParserIntegration:
    MODEL = "d4bl-query-parser"

    @pytest.fixture(autouse=True)
    def check_model(self):
        if not _model_loaded(self.MODEL):
            pytest.skip(f"Model {self.MODEL} not registered in Ollama")

    def test_simple_lookup(self):
        response = _run_model(
            self.MODEL,
            "What is the poverty rate in Alabama?",
        )
        result = validate_parser_output(response)
        assert result.valid, f"Invalid output: {result.errors}\nRaw: {response}"

    def test_comparison_query(self):
        response = _run_model(
            self.MODEL,
            "Compare median household income between Black and White residents in Mississippi",
        )
        result = validate_parser_output(response)
        assert result.valid, f"Invalid output: {result.errors}\nRaw: {response}"

    def test_trend_query(self):
        response = _run_model(
            self.MODEL,
            "How has the incarceration rate for Black men changed from 2015 to 2023?",
        )
        result = validate_parser_output(response)
        assert result.valid, f"Invalid output: {result.errors}\nRaw: {response}"

    def test_outputs_valid_json(self):
        """Verify output is parseable JSON (most basic requirement)."""
        response = _run_model(
            self.MODEL,
            "Show me diabetes rates by county in California",
        )
        result = validate_parser_output(response)
        assert result.parsed is not None, f"Could not parse JSON from: {response}"


@skip_no_ollama
class TestExplainerIntegration:
    MODEL = "d4bl-explainer"

    @pytest.fixture(autouse=True)
    def check_model(self):
        if not _model_loaded(self.MODEL):
            pytest.skip(f"Model {self.MODEL} not registered in Ollama")

    def test_single_metric_explanation(self):
        prompt = json.dumps({
            "metric": "poverty_rate",
            "geography": "Mississippi",
            "race": "Black",
            "value": 28.4,
            "comparison_value": 10.6,
            "comparison_race": "White",
            "year": 2022,
        })
        response = _run_model(self.MODEL, prompt, timeout=180)
        result = validate_explainer_output(response)
        assert result.valid, f"Invalid output: {result.errors}\nRaw: {response[:500]}"
        assert len(result.parsed["narrative"]) > 50, "Narrative too short"

    def test_outputs_valid_json(self):
        prompt = json.dumps({
            "metric": "median_household_income",
            "geography": "Alabama",
            "race": "Black",
            "value": 35400,
            "year": 2022,
        })
        response = _run_model(self.MODEL, prompt, timeout=180)
        result = validate_explainer_output(response)
        assert result.parsed is not None, f"Could not parse JSON from: {response[:500]}"


@skip_no_ollama
class TestEvaluatorIntegration:
    MODEL = "d4bl-evaluator"

    @pytest.fixture(autouse=True)
    def check_model(self):
        if not _model_loaded(self.MODEL):
            pytest.skip(f"Model {self.MODEL} not registered in Ollama")

    def test_bias_evaluation(self):
        response = _run_model(
            self.MODEL,
            'Evaluate for bias: "Crime rates are higher in Black neighborhoods because of cultural factors."',
        )
        result = validate_evaluator_output(response)
        assert result.valid, f"Invalid output: {result.errors}\nRaw: {response}"
        assert result.parsed["score"] <= 3, "Biased content should score low"

    def test_good_content_evaluation(self):
        response = _run_model(
            self.MODEL,
            'Evaluate for equity_framing: "The 2.7x disparity in '
            "poverty rates between Black and White residents in "
            "Mississippi reflects decades of structural "
            "disinvestment, including exclusion from federal "
            'homeownership programs."',
        )
        result = validate_evaluator_output(response)
        assert result.valid, f"Invalid output: {result.errors}\nRaw: {response}"
        assert result.parsed["score"] >= 3

    def test_score_in_valid_range(self):
        response = _run_model(
            self.MODEL,
            'Evaluate for relevance: "The weather in Paris is nice today."',
        )
        result = validate_evaluator_output(response)
        assert result.valid, f"Invalid output: {result.errors}\nRaw: {response}"
        assert 1 <= result.parsed["score"] <= 5


@skip_no_ollama
class TestModelLatency:
    """Verify models respond within acceptable time limits."""

    @pytest.fixture(autouse=True)
    def check_models(self):
        for model in ("d4bl-query-parser", "d4bl-explainer", "d4bl-evaluator"):
            if not _model_loaded(model):
                pytest.skip(f"Model {model} not registered")

    def test_parser_responds_under_10s(self):
        """Query parser P95 target: <1s. Allow 10s for cold start."""
        start = time.monotonic()
        _run_model(
            "d4bl-query-parser",
            "What is the poverty rate in Alabama?",
            timeout=10,
        )
        elapsed = time.monotonic() - start
        assert elapsed < 10, f"Parser took {elapsed:.1f}s (target: <10s with cold start)"

    def test_explainer_responds_under_30s(self):
        """Explainer P95 target: <3s. Allow 30s for cold start."""
        start = time.monotonic()
        prompt = json.dumps({"metric": "poverty_rate", "geography": "Alabama", "value": 18.2, "year": 2022})
        _run_model("d4bl-explainer", prompt, timeout=30)
        elapsed = time.monotonic() - start
        assert elapsed < 30, f"Explainer took {elapsed:.1f}s (target: <30s with cold start)"
