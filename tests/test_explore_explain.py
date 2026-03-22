"""Tests for POST /api/explore/explain LLM endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

EXPLAIN_PAYLOAD = {
    "source": "census",
    "metric": "median_household_income",
    "state_fips": "28",
    "state_name": "Mississippi",
    "value": 45000.0,
    "national_average": 61500.0,
    "year": 2022,
}


def _mock_llm_response(content: str) -> MagicMock:
    """Build a fake LiteLLM response object."""
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


class TestExplainEndpoint:
    """Happy-path and error tests for /api/explore/explain."""

    @pytest.mark.asyncio
    async def test_explain_returns_structured_json(self, override_auth):
        app = override_auth

        llm_json = (
            '{"narrative": "Mississippi ranks below the national average.",'
            ' "methodology_note": "Based on ACS 5-year estimates.",'
            ' "caveats": ["Margin of error not shown.", "Data is from 2022."]}'
        )

        with patch(
            "d4bl.app.explore_insights.acompletion",
            new_callable=AsyncMock,
            return_value=_mock_llm_response(llm_json),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/explore/explain", json=EXPLAIN_PAYLOAD
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["narrative"] == "Mississippi ranks below the national average."
        assert data["methodology_note"] == "Based on ACS 5-year estimates."
        assert len(data["caveats"]) == 2
        assert "generated_at" in data

    @pytest.mark.asyncio
    async def test_explain_fallback_raw_text(self, override_auth):
        """When LLM returns non-JSON, raw text becomes the narrative."""
        app = override_auth

        with patch(
            "d4bl.app.explore_insights.acompletion",
            new_callable=AsyncMock,
            return_value=_mock_llm_response("Just plain text response."),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/explore/explain", json=EXPLAIN_PAYLOAD
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["narrative"] == "Just plain text response."
        assert data["methodology_note"] == ""
        assert data["caveats"] == []

    @pytest.mark.asyncio
    async def test_explain_uses_task_specific_model(self, override_auth):
        """Explain endpoint should use the explainer model via model_for_task."""
        app = override_auth

        llm_json = '{"narrative": "test", "methodology_note": "note", "caveats": []}'

        with patch(
            "d4bl.app.explore_insights.model_for_task",
            return_value="d4bl-explainer",
        ), patch(
            "d4bl.app.explore_insights.acompletion",
            new_callable=AsyncMock,
            return_value=_mock_llm_response(llm_json),
        ) as mock_acompletion:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/explore/explain", json=EXPLAIN_PAYLOAD
                )

        assert resp.status_code == 200
        call_kwargs = mock_acompletion.call_args[1]
        assert call_kwargs["model"] == "ollama/d4bl-explainer"

    @pytest.mark.asyncio
    async def test_explain_503_when_llm_down(self, override_auth):
        app = override_auth

        with patch(
            "d4bl.app.explore_insights.acompletion",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Ollama is down"),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/explore/explain", json=EXPLAIN_PAYLOAD
                )

        assert resp.status_code == 503
        assert "unavailable" in resp.json()["detail"].lower()
