"""Tests for model comparison endpoint schemas and behavior."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from d4bl.app.schemas import CompareRequest


def _override_auth(app):
    """Stub out Supabase auth for testing."""
    from d4bl.app.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-user-id",
        "email": "test@test.com",
        "role": "user",
    }
    return app


class TestCompareRequest:
    def test_valid_request(self):
        r = CompareRequest(prompt="What is poverty rate?", task="query_parser")
        assert r.prompt == "What is poverty rate?"
        assert r.task == "query_parser"

    def test_blank_prompt_rejected(self):
        with pytest.raises(ValidationError):
            CompareRequest(prompt="", task="query_parser")

    def test_invalid_task_rejected(self):
        with pytest.raises(ValidationError):
            CompareRequest(prompt="test", task="invalid_task")


class TestCompareEndpoint:
    @pytest.mark.asyncio
    async def test_compare_returns_both_outputs(self):
        from d4bl.app.api import app

        test_app = _override_auth(app)

        baseline_output = "The median income is $45,081."
        finetuned_output = json.dumps({
            "intent": "lookup",
            "metrics": ["median_household_income"],
            "geographies": ["Mississippi"],
            "races": [],
            "time_range": None,
            "sources": ["census"],
        })

        call_count = 0

        async def mock_generate(
            *, base_url, prompt, model=None, temperature=0.1, timeout_seconds=30
        ):
            nonlocal call_count
            call_count += 1
            if model and "d4bl" in model:
                return finetuned_output
            return baseline_output

        with (
            patch("d4bl.app.api.ollama_generate", side_effect=mock_generate),
            patch("d4bl.app.api.model_for_task", return_value="d4bl-query-parser"),
        ):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/compare",
                    json={
                        "prompt": "What is the median income in Mississippi?",
                        "task": "query_parser",
                    },
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["baseline"]["model_name"] == "mistral"
        assert data["finetuned"]["valid_json"] is True
        assert data["baseline"]["valid_json"] is False
        assert data["metrics"]["validity_improved"] is True
        assert data["task"] == "query_parser"
        assert call_count == 2

        # Clean up
        test_app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_compare_same_model_returns_error(self):
        """When no fine-tuned model is configured, both resolve to the same model."""
        from d4bl.app.api import app

        test_app = _override_auth(app)

        with patch("d4bl.app.api.model_for_task", return_value="mistral"):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/compare",
                    json={
                        "prompt": "test",
                        "task": "query_parser",
                    },
                )

        assert resp.status_code == 400
        assert "not configured" in resp.json()["detail"].lower()

        test_app.dependency_overrides.clear()
