"""Tests for the cost_tracker module."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from d4bl.services.cost_tracker import _estimate_cost, extract_usage


class TestEstimateCost:
    def test_ollama_is_free(self):
        assert _estimate_cost(1000, 1000, "ollama", "llama3") == 0.0

    def test_known_gemini_model(self):
        # gemini-2.5-flash: $0.15/1M prompt, $0.60/1M completion
        cost = _estimate_cost(1_000_000, 1_000_000, "google", "gemini/gemini-2.5-flash")
        assert cost == pytest.approx(0.75, abs=0.001)

    def test_unknown_model_uses_default(self):
        cost = _estimate_cost(1_000_000, 0, "openai", "gpt-5-turbo")
        # default prompt = $0.15/1M
        assert cost == pytest.approx(0.15, abs=0.001)

    def test_zero_tokens(self):
        assert _estimate_cost(0, 0, "google", "gemini/gemini-2.5-flash") == 0.0


class TestExtractUsage:
    def test_extracts_from_pydantic_like_object(self):
        metrics = SimpleNamespace(
            total_tokens=5000,
            prompt_tokens=3000,
            completion_tokens=2000,
            cached_prompt_tokens=0,
            successful_requests=10,
        )
        result = SimpleNamespace(token_usage=metrics, raw="test")
        usage = extract_usage(result, provider="google", model="gemini/gemini-2.5-flash")

        assert usage is not None
        assert usage["total_tokens"] == 5000
        assert usage["prompt_tokens"] == 3000
        assert usage["completion_tokens"] == 2000
        assert usage["successful_requests"] == 10
        assert usage["estimated_cost_usd"] > 0
        assert usage["model"] == "gemini/gemini-2.5-flash"
        assert usage["provider"] == "google"

    def test_returns_none_when_no_token_usage(self):
        result = SimpleNamespace(raw="test")
        assert extract_usage(result) is None

    def test_returns_none_when_all_zeros(self):
        metrics = SimpleNamespace(
            total_tokens=0,
            prompt_tokens=0,
            completion_tokens=0,
            cached_prompt_tokens=0,
            successful_requests=0,
        )
        result = SimpleNamespace(token_usage=metrics)
        assert extract_usage(result) is None

    def test_ollama_cost_is_zero(self):
        metrics = SimpleNamespace(
            total_tokens=10000,
            prompt_tokens=8000,
            completion_tokens=2000,
            cached_prompt_tokens=0,
            successful_requests=5,
        )
        result = SimpleNamespace(token_usage=metrics)
        usage = extract_usage(result, provider="ollama", model="llama3")

        assert usage is not None
        assert usage["estimated_cost_usd"] == 0.0
