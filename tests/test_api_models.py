"""Tests for the /api/models endpoint and model param on research."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from d4bl.app.api import app


@pytest.mark.asyncio
async def test_get_models_returns_list():
    """GET /api/models should return a list of available models."""
    mock_models = [
        {
            "provider": "gemini",
            "model": "gemini-2.0-flash",
            "model_string": "gemini/gemini-2.0-flash",
            "is_default": True,
        }
    ]
    with patch("d4bl.app.api.get_available_models", return_value=mock_models):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/models")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["provider"] == "gemini"
    assert data[0]["is_default"] is True


def test_research_request_accepts_model():
    """ResearchRequest schema should accept an optional model field."""
    from d4bl.app.schemas import ResearchRequest
    req = ResearchRequest(query="test query", model="gemini/gemini-2.0-flash")
    assert req.model == "gemini/gemini-2.0-flash"


def test_research_request_model_defaults_none():
    """ResearchRequest.model should default to None."""
    from d4bl.app.schemas import ResearchRequest
    req = ResearchRequest(query="test query")
    assert req.model is None
