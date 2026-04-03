"""Tests for model comparison endpoint schemas and behavior."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

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
        r = CompareRequest(prompt="What is poverty rate?")
        assert r.prompt == "What is poverty rate?"

    def test_blank_prompt_rejected(self):
        with pytest.raises(ValidationError):
            CompareRequest(prompt="")


class TestCompareEndpoint:
    @pytest.mark.asyncio
    async def test_compare_runs_both_pipelines(self):
        from d4bl.app.api import app

        test_app = _override_auth(app)

        parse_output = json.dumps(
            {
                "entities": ["Mississippi"],
                "search_queries": ["median income Mississippi"],
                "data_sources": ["vector"],
            }
        )
        synth_output = "The median income reflects structural inequity."

        async def mock_generate(
            *, base_url, prompt, model=None, temperature=0.1, timeout_seconds=30
        ):
            # Parse step gets JSON, synthesize step gets prose
            if "extract" in prompt.lower() or "parser" in prompt.lower():
                return parse_output
            return synth_output

        # Mock DB session and vector store
        mock_session = AsyncMock()
        mock_vs = MagicMock()
        mock_vs.search_similar = AsyncMock(return_value=[])

        async def mock_get_db():
            yield mock_session

        from d4bl.infra.database import get_db

        test_app.dependency_overrides[get_db] = mock_get_db

        with (
            patch("d4bl.app.api.ollama_generate", side_effect=mock_generate),
            patch(
                "d4bl.app.api.model_for_task",
                side_effect=lambda t: f"d4bl-{t}" if t != "evaluator" else "mistral",
            ),
            patch("d4bl.app.api._run_pipeline") as mock_pipeline,
        ):
            # Instead of mocking the internals, let's test the endpoint contract
            pass

        # Simpler approach: mock _run_pipeline directly
        from d4bl.app.schemas import PipelinePath, PipelineStep

        baseline_path = PipelinePath(
            label="Base Model",
            steps=[
                PipelineStep(
                    step="parse", model_name="mistral", output=parse_output, latency_seconds=1.0
                ),
                PipelineStep(
                    step="search",
                    model_name="database",
                    output="Found 0 sources",
                    latency_seconds=0.1,
                ),
                PipelineStep(
                    step="synthesize",
                    model_name="mistral",
                    output=synth_output,
                    latency_seconds=2.0,
                ),
            ],
            final_answer=synth_output,
            total_latency_seconds=3.1,
        )
        finetuned_path = PipelinePath(
            label="Fine-Tuned",
            steps=[
                PipelineStep(
                    step="parse",
                    model_name="d4bl-query_parser",
                    output=parse_output,
                    latency_seconds=0.5,
                ),
                PipelineStep(
                    step="search",
                    model_name="database",
                    output="Found 0 sources",
                    latency_seconds=0.1,
                ),
                PipelineStep(
                    step="synthesize",
                    model_name="d4bl-explainer",
                    output=synth_output,
                    latency_seconds=1.5,
                ),
            ],
            final_answer=synth_output,
            total_latency_seconds=2.1,
        )

        async def mock_run_pipeline(**kwargs):
            if kwargs.get("label") == "Base Model":
                return baseline_path
            return finetuned_path

        with (
            patch("d4bl.app.api._run_pipeline", side_effect=mock_run_pipeline),
            patch("d4bl.app.api.model_for_task", side_effect=lambda t: f"d4bl-{t}"),
        ):
            from d4bl.infra.database import get_db

            test_app.dependency_overrides[get_db] = mock_get_db

            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/compare",
                    json={"prompt": "What is the median income in Mississippi?"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["baseline"]["label"] == "Base Model"
        assert data["finetuned"]["label"] == "Fine-Tuned"
        assert len(data["baseline"]["steps"]) == 3
        assert len(data["finetuned"]["steps"]) == 3
        assert data["baseline"]["steps"][0]["step"] == "parse"
        assert data["baseline"]["steps"][2]["step"] == "synthesize"
        assert data["prompt"] == "What is the median income in Mississippi?"

        test_app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_compare_same_model_returns_error(self):
        """When no fine-tuned model is configured, both resolve to the same model."""
        from d4bl.app.api import app

        test_app = _override_auth(app)

        with patch("d4bl.app.api.model_for_task", return_value="mistral"):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/compare",
                    json={"prompt": "test"},
                )

        assert resp.status_code == 400
        assert "not configured" in resp.json()["detail"].lower()

        test_app.dependency_overrides.clear()


class TestCompareEndpointWithModels:
    @pytest.mark.asyncio
    async def test_compare_with_explicit_models(self):
        from d4bl.app.api import app
        from d4bl.app.schemas import PipelinePath, PipelineStep

        test_app = _override_auth(app)

        baseline_path = PipelinePath(
            label="Pipeline A",
            steps=[
                PipelineStep(step="parse", model_name="mistral", output="{}", latency_seconds=1.0),
                PipelineStep(
                    step="search", model_name="database", output="Found 0", latency_seconds=0.1
                ),
                PipelineStep(
                    step="synthesize", model_name="mistral", output="Answer", latency_seconds=2.0
                ),
            ],
            final_answer="Answer",
            total_latency_seconds=3.1,
        )
        finetuned_path = PipelinePath(
            label="Pipeline B",
            steps=[
                PipelineStep(
                    step="parse", model_name="d4bl-query-parser", output="{}", latency_seconds=0.5
                ),
                PipelineStep(
                    step="search", model_name="database", output="Found 0", latency_seconds=0.1
                ),
                PipelineStep(
                    step="synthesize",
                    model_name="d4bl-explainer",
                    output="Answer",
                    latency_seconds=1.5,
                ),
            ],
            final_answer="Answer",
            total_latency_seconds=2.1,
        )

        async def mock_run_pipeline(**kwargs):
            if kwargs.get("label") == "Pipeline A":
                return baseline_path
            return finetuned_path

        try:
            with (
                patch("d4bl.app.api._run_pipeline", side_effect=mock_run_pipeline),
                patch(
                    "d4bl.app.api.get_available_models",
                    return_value=[
                        {"model": "mistral", "type": "base"},
                        {"model": "d4bl-query-parser", "type": "finetuned"},
                        {"model": "d4bl-explainer", "type": "finetuned"},
                    ],
                ),
            ):
                transport = ASGITransport(app=test_app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post(
                        "/api/compare",
                        json={
                            "prompt": "What is poverty rate?",
                            "pipeline_a_parser": "mistral",
                            "pipeline_a_explainer": "mistral",
                            "pipeline_b_parser": "d4bl-query-parser",
                            "pipeline_b_explainer": "d4bl-explainer",
                        },
                    )

            assert resp.status_code == 200
            data = resp.json()
            assert data["baseline"]["label"] == "Pipeline A"
            assert data["finetuned"]["label"] == "Pipeline B"
        finally:
            test_app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_compare_rejects_unknown_model(self):
        from d4bl.app.api import app

        test_app = _override_auth(app)

        try:
            with patch(
                "d4bl.app.api.get_available_models",
                return_value=[
                    {"model": "mistral", "type": "base"},
                ],
            ):
                transport = ASGITransport(app=test_app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post(
                        "/api/compare",
                        json={
                            "prompt": "test",
                            "pipeline_a_parser": "nonexistent-model",
                            "pipeline_a_explainer": "mistral",
                            "pipeline_b_parser": "mistral",
                            "pipeline_b_explainer": "mistral",
                        },
                    )

            assert resp.status_code == 400
            assert "nonexistent-model" in resp.json()["detail"]
        finally:
            test_app.dependency_overrides.clear()