# Post-Experiment Analysis + /learn Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `/learn` into a tabbed layout with hot-swappable model comparison, and add rules-based + LLM-powered post-eval suggestions.

**Architecture:** The work decomposes into 3 layers: (1) backend — DB migration, suggestion engine, API changes; (2) frontend — tab restructure, model selector dropdowns, SuggestionsPanel; (3) CLI integration — eval harness flags for suggestions and analysis. Each layer is independently testable and commits incrementally.

**Tech Stack:** Python/FastAPI, SQLAlchemy, Next.js/React 19, Tailwind CSS 4, PostgreSQL/JSONB, Ollama

---

## File Structure

```
Modified:
  src/d4bl/infra/database.py              — add suggestions JSONB column to ModelEvalRun
  src/d4bl/app/schemas.py                 — update CompareRequest, EvalRunItem (add id + suggestions); add SuggestionItem, AnalyzeResponse
  src/d4bl/app/api.py                     — update /api/compare, update /api/eval-runs to include id+suggestions, add POST /api/eval-runs/{id}/analyze
  src/d4bl/llm/provider.py                — add type + version fields to get_available_models()
  src/d4bl/settings.py                    — add QUERY_PARSER_MODEL_VERSION, EXPLAINER_MODEL_VERSION env vars (using _set() pattern)
  scripts/training/run_eval_harness.py    — integrate generate_suggestions(), add --analyze/--analyze-existing flags
  ui-nextjs/app/learn/page.tsx            — restructure into tabbed layout
  ui-nextjs/components/learn/ModelComparisonPlayground.tsx — add model selector dropdowns
  ui-nextjs/components/learn/EvalMetricsPanel.tsx — add SuggestionsPanel rendering (not in spec Section 6 but necessary)
  ui-nextjs/lib/api.ts                    — update types (add id to EvalRunItem), add analyzeFailures(), update compareModels()

Unchanged (already exports what we need):
  scripts/training/ship_criteria.py       — SHIP_CRITERIA already exported, no changes needed

Created:
  scripts/training/suggestions.py                    — rules-based suggestion engine (LLM analysis deferred — see note below)
  ui-nextjs/components/learn/LearnTabs.tsx            — tab navigation component
  ui-nextjs/components/learn/BuildTab.tsx             — tutorials + slide deck
  ui-nextjs/components/learn/SuggestionsPanel.tsx     — suggested improvements display
  tests/test_suggestions.py                           — suggestion generation tests
  tests/test_analyze_endpoint.py                      — analyze endpoint tests
  supabase/migrations/20260327000001_add_suggestions_to_eval_runs.sql
```

> **Deferred: LLM-powered analysis (spec Section 5.2).** The rules-based engine is the free, always-runs path and delivers the core value. LLM analysis requires a Claude API key, prompt engineering, and cost management — it will be a follow-up PR. The `suggestions.llm_analysis` field is wired through end-to-end (DB, API, UI) so the follow-up only needs to implement the LLM call itself. The "Analyze Failures" button and `--analyze` flag are present but will show "Coming soon" / print a message until the LLM integration lands.

---

### Task 1: Database Migration — Add suggestions column

**Files:**
- Create: `supabase/migrations/20260327000001_add_suggestions_to_eval_runs.sql`
- Modify: `src/d4bl/infra/database.py:112-140`

- [ ] **Step 1: Write migration SQL**

Create `supabase/migrations/20260327000001_add_suggestions_to_eval_runs.sql`:
```sql
-- Add suggestions column for post-eval analysis (rules-based + LLM)
ALTER TABLE model_eval_runs ADD COLUMN IF NOT EXISTS suggestions JSONB;
```

- [ ] **Step 2: Add suggestions column to SQLAlchemy model**

In `src/d4bl/infra/database.py`, add to `ModelEvalRun` class after `blocking_failures`:
```python
suggestions = Column(JSONB, nullable=True)
```

- [ ] **Step 3: Update ModelEvalRun.to_dict()**

Add `"suggestions": self.suggestions` to the `to_dict()` return dict, after the `blocking_failures` entry.

- [ ] **Step 4: Run existing database tests to confirm no regression**

Run: `pytest tests/test_database.py tests/test_eval_runner_model.py -v`
Expected: All existing tests PASS.

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/20260327000001_add_suggestions_to_eval_runs.sql src/d4bl/infra/database.py
git commit -m "feat(db): add suggestions JSONB column to model_eval_runs"
```

---

### Task 2: Rules-Based Suggestion Engine

**Files:**
- Create: `scripts/training/suggestions.py`
- Create: `tests/test_suggestions.py`

- [ ] **Step 1: Write failing tests for generate_suggestions()**

Create `tests/test_suggestions.py`:
```python
"""Tests for the post-eval suggestion engine."""
from __future__ import annotations

import pytest

from scripts.training.suggestions import generate_suggestions, Suggestion


class TestGenerateSuggestions:
    def test_blocking_suggestion_for_low_entity_f1(self):
        metrics = {"entity_f1": 0.72, "json_valid_rate": 0.99}
        result = generate_suggestions("query_parser", metrics)
        assert any(s.metric == "entity_f1" and s.severity == "blocking" for s in result.rules)

    def test_no_suggestions_when_all_pass(self):
        metrics = {
            "json_valid_rate": 0.99,
            "entity_f1": 0.90,
            "data_source_accuracy": 0.90,
            "community_framing_f1": 0.80,
            "p95_latency_ms": 500,
            "adversarial_pass_rate": 0.90,
        }
        result = generate_suggestions("query_parser", metrics)
        assert len(result.rules) == 0

    def test_nonblocking_suggestion_for_low_community_framing(self):
        metrics = {
            "json_valid_rate": 0.99,
            "entity_f1": 0.90,
            "data_source_accuracy": 0.90,
            "community_framing_f1": 0.55,
            "p95_latency_ms": 500,
            "adversarial_pass_rate": 0.90,
        }
        result = generate_suggestions("query_parser", metrics)
        assert any(
            s.metric == "community_framing_f1" and s.severity == "non-blocking"
            for s in result.rules
        )

    def test_max_direction_metric_latency(self):
        metrics = {"p95_latency_ms": 1500}
        result = generate_suggestions("query_parser", metrics)
        assert any(s.metric == "p95_latency_ms" and s.severity == "blocking" for s in result.rules)

    def test_explainer_suggestions(self):
        metrics = {"d4bl_composite": 2.5, "factual_accuracy": 0.80}
        result = generate_suggestions("explainer", metrics)
        assert any(s.metric == "d4bl_composite" for s in result.rules)
        assert any(s.metric == "factual_accuracy" for s in result.rules)

    def test_evaluator_suggestions(self):
        metrics = {"hallucination_accuracy": 0.70, "bias_mae": 1.5}
        result = generate_suggestions("evaluator", metrics)
        assert any(s.metric == "hallucination_accuracy" for s in result.rules)
        assert any(s.metric == "bias_mae" for s in result.rules)

    def test_missing_metric_not_suggested(self):
        metrics = {"entity_f1": 0.90}  # passes threshold; other metrics absent
        result = generate_suggestions("query_parser", metrics)
        # entity_f1=0.90 passes (≥0.80), absent metrics produce no suggestions
        assert len(result.rules) == 0

    def test_unknown_task_returns_empty(self):
        result = generate_suggestions("unknown_task", {"foo": 0.5})
        assert len(result.rules) == 0

    def test_to_dict_format(self):
        metrics = {"entity_f1": 0.72}
        result = generate_suggestions("query_parser", metrics)
        d = result.to_dict()
        assert "rules" in d
        assert "llm_analysis" in d
        assert "generated_at" in d
        assert d["rules"][0]["metric"] == "entity_f1"
        assert d["rules"][0]["current"] == 0.72
        assert d["rules"][0]["target"] == 0.80
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_suggestions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.training.suggestions'`

- [ ] **Step 3: Implement the suggestion engine**

Create `scripts/training/suggestions.py`:
```python
"""Post-eval suggestion engine: rules-based + optional LLM analysis."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from scripts.training.ship_criteria import SHIP_CRITERIA

# ── Suggestion rules keyed by (task, metric) ────────────────────────
# Each maps a failing metric to an actionable training-data recommendation.
SUGGESTION_TEXT: dict[str, dict[str, str]] = {
    "query_parser": {
        "json_valid_rate": "Add adversarial examples with malformed input to improve JSON compliance",
        "entity_f1": "Add training pairs with more diverse entity types (organizations, policies, geographies)",
        "data_source_accuracy": "Add examples that clarify when to use vector vs structured search",
        "community_framing_f1": "Add community-voiced query examples with advocacy framing",
        "p95_latency_ms": "Consider increasing quantization level or reducing context window",
        "adversarial_pass_rate": "Add more adversarial prompts with harmful framings that should be reframed",
    },
    "explainer": {
        "json_valid_rate": "Add examples with complex nested JSON output structure",
        "factual_accuracy": "Verify training data accuracy — check for stale statistics in distillation corpus",
        "d4bl_composite": "Increase proportion of D4BL methodology-aligned training examples",
        "register_consistency": "Add single-register examples with clear style separation between community/policy/research",
        "p95_latency_ms": "Consider increasing quantization level or reducing context window",
    },
    "evaluator": {
        "hallucination_accuracy": "Add more hallucination detection examples with subtle factual errors",
        "relevance_mae": "Add relevance scoring examples with borderline cases (partially relevant)",
        "bias_mae": "Add bias detection examples covering structural bias, not just explicit bias",
        "relevance_correlation": "Add more diverse relevance scoring examples across different query types",
    },
}


@dataclass
class Suggestion:
    metric: str
    severity: str          # "blocking" or "non-blocking"
    current: float
    target: float
    suggestion: str
    category: str = "training_data"


@dataclass
class SuggestionsResult:
    rules: list[Suggestion] = field(default_factory=list)
    llm_analysis: str | None = None
    generated_at: str = ""

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "rules": [asdict(s) for s in self.rules],
            "llm_analysis": self.llm_analysis,
            "generated_at": self.generated_at,
        }


def generate_suggestions(task: str, metrics: dict[str, float | None]) -> SuggestionsResult:
    """Generate rules-based suggestions from eval metrics and ship criteria.

    Compares each metric against the threshold defined in SHIP_CRITERIA.
    Returns a SuggestionsResult with one Suggestion per failing metric.
    """
    criteria = SHIP_CRITERIA.get(task, {})
    task_suggestions = SUGGESTION_TEXT.get(task, {})
    suggestions: list[Suggestion] = []

    for metric_name, bounds in criteria.items():
        actual = metrics.get(metric_name)
        if actual is None:
            continue

        text = task_suggestions.get(metric_name)
        if not text:
            continue

        blocking = bounds.get("blocking", False)
        severity = "blocking" if blocking else "non-blocking"
        failed = False
        target = 0.0

        if "min" in bounds:
            target = bounds["min"]
            if actual < target:
                failed = True
        if "max" in bounds:
            target = bounds["max"]
            if actual > target:
                failed = True

        if failed:
            suggestions.append(Suggestion(
                metric=metric_name,
                severity=severity,
                current=actual,
                target=target,
                suggestion=text,
            ))

    return SuggestionsResult(rules=suggestions)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_suggestions.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/training/suggestions.py tests/test_suggestions.py
git commit -m "feat(eval): add rules-based suggestion engine for post-eval analysis"
```

---

### Task 3: Update schemas — CompareRequest, EvalRunItem, SuggestionItem

**Files:**
- Modify: `src/d4bl/app/schemas.py:496-537`
- Test: `tests/test_app_schemas.py` (existing), `tests/test_compare_endpoint.py` (existing)

- [ ] **Step 1: Write failing tests for updated schemas**

Append to `tests/test_app_schemas.py`:
```python
from d4bl.app.schemas import (
    CompareRequest,
    EvalRunItem,
    SuggestionItem,
    AnalyzeResponse,
)


class TestCompareRequestModelFields:
    def test_accepts_pipeline_model_fields(self):
        r = CompareRequest(
            prompt="test query",
            pipeline_a_parser="mistral",
            pipeline_a_explainer="mistral",
            pipeline_b_parser="d4bl-query-parser",
            pipeline_b_explainer="d4bl-explainer",
        )
        assert r.pipeline_a_parser == "mistral"
        assert r.pipeline_b_explainer == "d4bl-explainer"

    def test_model_fields_optional_with_defaults(self):
        r = CompareRequest(prompt="test query")
        assert r.pipeline_a_parser is None
        assert r.pipeline_b_parser is None


class TestEvalRunItemSuggestions:
    def test_suggestions_field_present(self):
        item = EvalRunItem(
            model_name="test",
            model_version="v1.0",
            base_model_name="mistral",
            task="query_parser",
            metrics={"json_valid_rate": 0.99},
            ship_decision="ship",
            suggestions={"rules": [], "llm_analysis": None, "generated_at": "2026-03-27"},
        )
        assert item.suggestions is not None
        assert item.suggestions["rules"] == []


class TestSuggestionItem:
    def test_fields(self):
        s = SuggestionItem(
            metric="entity_f1",
            severity="blocking",
            current=0.72,
            target=0.80,
            suggestion="Add more diverse entities",
            category="training_data",
        )
        assert s.severity == "blocking"


class TestAnalyzeResponse:
    def test_fields(self):
        r = AnalyzeResponse(
            run_id="abc-123",
            suggestions={"rules": [], "llm_analysis": "test", "generated_at": "2026-03-27"},
        )
        assert r.suggestions["llm_analysis"] == "test"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_app_schemas.py::TestCompareRequestModelFields -v`
Expected: FAIL with `ImportError` or `ValidationError` (fields don't exist yet).

- [ ] **Step 3: Update schemas**

In `src/d4bl/app/schemas.py`, update `CompareRequest` (around line 496):
```python
class CompareRequest(BaseModel):
    prompt: str
    pipeline_a_parser: str | None = None
    pipeline_a_explainer: str | None = None
    pipeline_b_parser: str | None = None
    pipeline_b_explainer: str | None = None

    @field_validator("prompt")
    @classmethod
    def prompt_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Prompt cannot be empty")
        return v
```

Add new schemas after `EvalRunsResponse` (around line 537):
```python
class SuggestionItem(BaseModel):
    metric: str
    severity: str
    current: float
    target: float
    suggestion: str
    category: str = "training_data"


class AnalyzeResponse(BaseModel):
    run_id: str
    suggestions: dict
```

Update `EvalRunItem` to include `id` and `suggestions` (both needed for the SuggestionsPanel to call the analyze endpoint):
```python
class EvalRunItem(BaseModel):
    id: str | None = None
    model_name: str
    model_version: str
    base_model_name: str
    task: str
    metrics: dict[str, float | None]
    ship_decision: str
    blocking_failures: list[dict] | None = None
    created_at: str | None = None
    suggestions: dict | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_app_schemas.py tests/test_compare_endpoint.py -v`
Expected: All PASS (new and existing tests).

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/app/schemas.py tests/test_app_schemas.py
git commit -m "feat(schemas): add model selector fields to CompareRequest, suggestions to EvalRunItem"
```

---

### Task 4: Extend get_available_models() with type and version fields

**Files:**
- Modify: `src/d4bl/llm/provider.py:117-151`
- Modify: `src/d4bl/settings.py` (add version env vars)
- Test: `tests/test_llm_provider.py` (existing), `tests/test_api_models.py` (existing)

- [ ] **Step 1: Write failing tests for new fields**

Append to `tests/test_llm_provider.py`:
```python
class TestGetAvailableModelsTypeVersion:
    def test_default_model_has_base_type(self):
        models = get_available_models()
        default = next(m for m in models if m["is_default"])
        assert default["type"] == "base"
        assert default["version"] is None

    def test_finetuned_model_has_type_and_version(self):
        with patch.object(settings_module, "get_settings") as mock_settings:
            s = mock_settings.return_value
            s.ollama_model = "mistral"
            s.ollama_base_url = "http://localhost:11434"
            s.query_parser_model = "d4bl-query-parser"
            s.explainer_model = "d4bl-explainer"
            s.evaluator_model = "d4bl-evaluator"
            s.query_parser_model_version = "v1.0"
            s.explainer_model_version = "v1.0"
            models = get_available_models()
            parser = next(m for m in models if m["task"] == "query_parser")
            assert parser["type"] == "finetuned"
            assert parser["version"] == "v1.0"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm_provider.py::TestGetAvailableModelsTypeVersion -v`
Expected: FAIL — `type` and `version` keys missing.

- [ ] **Step 3: Add version env vars to settings**

In `src/d4bl/settings.py`, add field declarations after the existing fine-tuned task model fields (around line 62):
```python
# -- Fine-tuned model version labels (display only) --
query_parser_model_version: str = field(init=False)
explainer_model_version: str = field(init=False)
```

In `__post_init__()`, add `_set()` calls (after the existing task model _set calls):
```python
_set("query_parser_model_version", os.getenv("QUERY_PARSER_MODEL_VERSION", ""))
_set("explainer_model_version", os.getenv("EXPLAINER_MODEL_VERSION", ""))
```

- [ ] **Step 4: Update get_available_models()**

In `src/d4bl/llm/provider.py`, update the function to include `type` and `version` in each model dict:

For the default model entry:
```python
{"provider": ..., "model": ..., "model_string": ..., "is_default": True, "task": "general", "type": "base", "version": None}
```

For task-specific models, determine type and version:
```python
version_attrs = {
    "query_parser": "query_parser_model_version",
    "explainer": "explainer_model_version",
}
# In the loop for task-specific models:
version = getattr(settings, version_attrs.get(task, ""), "") or None
model_entry["type"] = "finetuned"
model_entry["version"] = version
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_llm_provider.py tests/test_api_models.py -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add src/d4bl/settings.py src/d4bl/llm/provider.py tests/test_llm_provider.py
git commit -m "feat(models): add type and version fields to get_available_models()"
```

---

### Task 5: Update /api/compare to accept explicit model names

**Files:**
- Modify: `src/d4bl/app/api.py:688-775`
- Test: `tests/test_compare_endpoint.py`

- [ ] **Step 1: Write failing test for model-specified comparison**

Append to `tests/test_compare_endpoint.py`:
```python
class TestCompareEndpointWithModels:
    @pytest.mark.asyncio
    async def test_compare_with_explicit_models(self):
        from d4bl.app.api import app

        test_app = _override_auth(app)

        parse_output = json.dumps({
            "entities": ["Mississippi"],
            "search_queries": ["median income Mississippi"],
            "data_sources": ["vector"],
        })
        synth_output = "The median income reflects structural inequity."

        async def mock_generate(*, base_url, prompt, model=None, temperature=0.1, timeout_seconds=30):
            if "Parse" in prompt or "parse" in prompt:
                return parse_output
            if "Evaluate" in prompt or "evaluate" in prompt or "score" in prompt.lower():
                return json.dumps({"score": 4, "explanation": "Good", "issues": []})
            return synth_output

        with (
            patch("d4bl.app.api.ollama_generate", side_effect=mock_generate),
            patch("d4bl.app.api.get_available_models", return_value=[
                {"model": "mistral", "type": "base"},
                {"model": "d4bl-query-parser", "type": "finetuned"},
                {"model": "d4bl-explainer", "type": "finetuned"},
            ]),
            patch("d4bl.app.api.ResultFusion") as mock_fusion,
        ):
            mock_fusion.return_value.merge_and_rank.return_value = []

            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as client:
                resp = await client.post("/api/compare", json={
                    "prompt": "What is poverty rate?",
                    "pipeline_a_parser": "mistral",
                    "pipeline_a_explainer": "mistral",
                    "pipeline_b_parser": "d4bl-query-parser",
                    "pipeline_b_explainer": "d4bl-explainer",
                })
                assert resp.status_code == 200
                data = resp.json()
                assert "baseline" in data
                assert "finetuned" in data

    @pytest.mark.asyncio
    async def test_compare_rejects_unknown_model(self):
        from d4bl.app.api import app

        test_app = _override_auth(app)

        with patch("d4bl.app.api.get_available_models", return_value=[
            {"model": "mistral", "type": "base"},
        ]):
            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as client:
                resp = await client.post("/api/compare", json={
                    "prompt": "test",
                    "pipeline_a_parser": "nonexistent-model",
                    "pipeline_a_explainer": "mistral",
                    "pipeline_b_parser": "mistral",
                    "pipeline_b_explainer": "mistral",
                })
                assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_compare_endpoint.py::TestCompareEndpointWithModels -v`
Expected: FAIL — endpoint doesn't validate model names yet.

- [ ] **Step 3: Update /api/compare endpoint**

In `src/d4bl/app/api.py`, modify the `compare_models` handler (around line 688):

1. Extract model names from request, falling back to current defaults:
```python
req_data = CompareRequest(**await request.json()) if hasattr(request, 'json') else body
# ... after parsing body:
pipeline_a_parser = body.pipeline_a_parser or settings.ollama_model
pipeline_a_explainer = body.pipeline_a_explainer or settings.ollama_model
pipeline_b_parser = body.pipeline_b_parser or model_for_task("query_parser")
pipeline_b_explainer = body.pipeline_b_explainer or model_for_task("explainer")
```

2. Validate model names when explicit models are provided:
```python
if body.pipeline_a_parser or body.pipeline_b_parser:
    available = {m["model"] for m in get_available_models()}
    requested = {pipeline_a_parser, pipeline_a_explainer, pipeline_b_parser, pipeline_b_explainer}
    unknown = requested - available
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown models: {', '.join(sorted(unknown))}")
```

3. Pass explicit model names to `_run_pipeline()`:
```python
task_a = _run_with_session(question, pipeline_a_parser, pipeline_a_explainer, evaluator_model, base_url, "Pipeline A")
task_b = _run_with_session(question, pipeline_b_parser, pipeline_b_explainer, evaluator_model, base_url, "Pipeline B")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_compare_endpoint.py -v`
Expected: All PASS (new and existing).

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/app/api.py tests/test_compare_endpoint.py
git commit -m "feat(api): accept explicit model names in /api/compare with validation"
```

---

### Task 6: Add POST /api/eval-runs/{id}/analyze endpoint

**Files:**
- Modify: `src/d4bl/app/api.py`
- Create: `tests/test_analyze_endpoint.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_analyze_endpoint.py`:
```python
"""Tests for POST /api/eval-runs/{id}/analyze endpoint."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


def _override_auth(app):
    from d4bl.app.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-user-id",
        "email": "test@test.com",
        "role": "user",
    }
    return app


class TestAnalyzeEndpoint:
    @pytest.mark.asyncio
    async def test_returns_existing_analysis_when_present(self):
        from d4bl.app.api import app

        test_app = _override_auth(app)
        run_id = str(uuid.uuid4())

        mock_run = MagicMock()
        mock_run.id = run_id
        mock_run.task = "query_parser"
        mock_run.metrics = {"entity_f1": 0.72}
        mock_run.suggestions = {
            "rules": [{"metric": "entity_f1", "severity": "blocking", "current": 0.72, "target": 0.80, "suggestion": "Add diverse entities", "category": "training_data"}],
            "llm_analysis": "Previously analyzed",
            "generated_at": "2026-03-27T00:00:00Z",
        }

        with patch("d4bl.app.api.get_async_session") as mock_session_ctx:
            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_run
            mock_session.execute = AsyncMock(return_value=mock_result)

            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as client:
                resp = await client.post(f"/api/eval-runs/{run_id}/analyze")
                assert resp.status_code == 200
                data = resp.json()
                assert data["suggestions"]["llm_analysis"] == "Previously analyzed"

    @pytest.mark.asyncio
    async def test_returns_404_for_unknown_run(self):
        from d4bl.app.api import app

        test_app = _override_auth(app)
        run_id = str(uuid.uuid4())

        with patch("d4bl.app.api.get_async_session") as mock_session_ctx:
            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)

            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as client:
                resp = await client.post(f"/api/eval-runs/{run_id}/analyze")
                assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_force_regenerates_analysis(self):
        """Verify ?force=true clears existing llm_analysis and regenerates."""
        from d4bl.app.api import app

        test_app = _override_auth(app)
        run_id = str(uuid.uuid4())

        mock_run = MagicMock()
        mock_run.id = run_id
        mock_run.task = "query_parser"
        mock_run.metrics = {"entity_f1": 0.72}
        mock_run.suggestions = {
            "rules": [],
            "llm_analysis": "Old analysis that should be cleared",
            "generated_at": "2026-03-27T00:00:00Z",
        }

        with patch("d4bl.app.api.get_async_session") as mock_session_ctx:
            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_run
            mock_session.execute = AsyncMock(return_value=mock_result)

            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as client:
                resp = await client.post(f"/api/eval-runs/{run_id}/analyze?force=true")
                assert resp.status_code == 200
                data = resp.json()
                # force=true clears old LLM analysis (LLM integration deferred)
                assert data["suggestions"]["llm_analysis"] is None
                # Rules still generated
                assert any(r["metric"] == "entity_f1" for r in data["suggestions"]["rules"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analyze_endpoint.py -v`
Expected: FAIL — endpoint doesn't exist yet.

- [ ] **Step 3: Implement the analyze endpoint**

In `src/d4bl/app/api.py`, add the new endpoint after the existing `/api/eval-runs` handler:

```python
@app.post("/api/eval-runs/{run_id}/analyze")
async def analyze_eval_run(
    run_id: str,
    force: bool = False,
    user: dict = Depends(get_current_user),
):
    """Generate or return suggestions for an eval run.

    Idempotent: returns existing LLM analysis unless ?force=true.
    Rules-based suggestions are always (re)generated from current metrics.
    """
    from scripts.training.suggestions import generate_suggestions

    async with get_async_session() as session:
        result = await session.execute(
            select(ModelEvalRun).where(ModelEvalRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail="Eval run not found")

        # Always regenerate rules-based suggestions from current metrics
        suggestions_result = generate_suggestions(run.task, run.metrics or {})

        # Preserve existing LLM analysis unless force=true
        existing = run.suggestions or {}
        if existing.get("llm_analysis") and not force:
            suggestions_result.llm_analysis = existing["llm_analysis"]

        run.suggestions = suggestions_result.to_dict()
        await session.commit()

        return {"run_id": str(run.id), "suggestions": run.suggestions}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analyze_endpoint.py -v`
Expected: All PASS.

- [ ] **Step 5: Also update GET /api/eval-runs to include suggestions in response**

In the `get_eval_runs` handler, ensure the `EvalRunItem` construction includes `id=str(run.id)` and `suggestions=run.suggestions` when building items from `ModelEvalRun` rows. Both are needed for the SuggestionsPanel to call the analyze endpoint.

- [ ] **Step 6: Run full backend tests**

Run: `pytest tests/test_eval_runs_endpoint.py tests/test_analyze_endpoint.py -v`
Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add src/d4bl/app/api.py tests/test_analyze_endpoint.py
git commit -m "feat(api): add POST /api/eval-runs/{id}/analyze for suggestion generation"
```

---

### Task 7: Integrate suggestions into eval harness CLI

**Files:**
- Modify: `scripts/training/run_eval_harness.py:371-401`
- Test: `tests/test_eval_harness_model_flag.py` (extend)

- [ ] **Step 1: Write failing test for --analyze flag**

Append to `tests/test_eval_harness_model_flag.py`:
```python
class TestAnalyzeFlag:
    def test_parse_args_accepts_analyze(self):
        from scripts.training.run_eval_harness import build_parser
        args = build_parser().parse_args(["--task", "query_parser", "--persist", "--analyze"])
        assert args.analyze is True

    def test_parse_args_accepts_analyze_existing(self):
        from scripts.training.run_eval_harness import build_parser
        args = build_parser().parse_args(["--analyze-existing", "latest", "--task", "query_parser"])
        assert args.analyze_existing == "latest"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_eval_harness_model_flag.py::TestAnalyzeFlag -v`
Expected: FAIL — `build_parser` doesn't exist or flags not recognized.

- [ ] **Step 3: Extract argument parser and add new flags**

In `scripts/training/run_eval_harness.py`:

1. Extract the argparse setup into a `build_parser()` function (return the `ArgumentParser`).
2. Add `--analyze` flag (`store_true`): prints "LLM analysis coming soon" after suggestions (placeholder until Claude API integration).
3. Add `--analyze-existing` flag (string): accepts a UUID or "latest" to analyze an existing run without re-running evals.

- [ ] **Step 4: Implement post-eval suggestion printing**

After `persist_results()` completes, generate and print suggestions:
```python
from scripts.training.suggestions import generate_suggestions

def print_suggestions(results: list[EvalRunResult]) -> None:
    for result in results:
        suggestions = generate_suggestions(result.task, result.metrics)
        print(f"\n{'='*60}")
        print(f"Suggestions for {result.task}:")
        for s in suggestions.rules:
            icon = "BLOCK" if s.severity == "blocking" else "WARN"
            print(f"  [{icon}] {s.metric}: {s.current:.2f} -> {s.target:.2f}")
            print(f"         {s.suggestion}")
        if not suggestions.rules:
            print("  All metrics pass -- no suggestions.")
```

- [ ] **Step 5: Implement --analyze-existing code path**

This is a distinct mode that skips model inference entirely:
```python
def analyze_existing_run(run_id_or_latest: str, task: str | None) -> None:
    """Load an existing eval run from DB, generate suggestions, update the row."""
    from d4bl.infra.database import ModelEvalRun
    from d4bl.settings import get_settings
    from sqlalchemy import create_engine, select, desc
    from sqlalchemy.orm import Session

    settings = get_settings()
    db_url = f"postgresql://{settings.postgres_user}:{settings.postgres_password}@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    engine = create_engine(db_url)

    with Session(engine) as session:
        if run_id_or_latest == "latest":
            query = select(ModelEvalRun).order_by(desc(ModelEvalRun.created_at))
            if task:
                query = query.where(ModelEvalRun.task == task)
            run = session.execute(query.limit(1)).scalar_one_or_none()
        else:
            run = session.execute(
                select(ModelEvalRun).where(ModelEvalRun.id == run_id_or_latest)
            ).scalar_one_or_none()

        if not run:
            print(f"No eval run found for: {run_id_or_latest}")
            return

        suggestions = generate_suggestions(run.task, run.metrics or {})
        run.suggestions = suggestions.to_dict()
        session.commit()

        print(f"Updated suggestions for run {run.id} ({run.task})")
        for s in suggestions.rules:
            icon = "BLOCK" if s.severity == "blocking" else "WARN"
            print(f"  [{icon}] {s.metric}: {s.current:.2f} -> {s.target:.2f}")
            print(f"         {s.suggestion}")
        if not suggestions.rules:
            print("  All metrics pass -- no suggestions.")

    engine.dispose()
```

Wire it in `main()`:
```python
if args.analyze_existing:
    analyze_existing_run(args.analyze_existing, args.task)
    return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_eval_harness_model_flag.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/training/run_eval_harness.py tests/test_eval_harness_model_flag.py
git commit -m "feat(eval): integrate suggestions into eval harness CLI with --analyze flag"
```

---

### Task 8: Frontend — LearnTabs component

**Files:**
- Create: `ui-nextjs/components/learn/LearnTabs.tsx`

- [ ] **Step 1: Create the tab navigation component**

Create `ui-nextjs/components/learn/LearnTabs.tsx`:
```tsx
"use client";

import { useState, useEffect, type ReactNode } from "react";

interface Tab {
  id: string;
  label: string;
  content: ReactNode;
}

interface LearnTabsProps {
  tabs: Tab[];
  defaultTab?: string;
}

export default function LearnTabs({ tabs, defaultTab = "compare" }: LearnTabsProps) {
  const [activeTab, setActiveTab] = useState(defaultTab);

  // Sync with URL hash on mount and hash change
  useEffect(() => {
    const hash = window.location.hash.replace("#", "");
    if (hash && tabs.some((t) => t.id === hash)) {
      setActiveTab(hash);
    }

    const onHashChange = () => {
      const h = window.location.hash.replace("#", "");
      if (h && tabs.some((t) => t.id === h)) {
        setActiveTab(h);
      }
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, [tabs]);

  const handleTabClick = (id: string) => {
    setActiveTab(id);
    window.history.replaceState(null, "", `#${id}`);
  };

  return (
    <div>
      {/* Tab bar */}
      <div className="flex border-b border-gray-700 mb-8">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => handleTabClick(tab.id)}
            className={`px-6 py-3 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? "border-b-2 border-blue-400 text-blue-400"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tabs.map((tab) => (
        <div key={tab.id} className={activeTab === tab.id ? "block" : "hidden"}>
          {tab.content}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add ui-nextjs/components/learn/LearnTabs.tsx
git commit -m "feat(ui): add LearnTabs component with URL hash sync"
```

---

### Task 9: Frontend — BuildTab component

**Files:**
- Create: `ui-nextjs/components/learn/BuildTab.tsx`

- [ ] **Step 1: Create the Build tab content**

Create `ui-nextjs/components/learn/BuildTab.tsx`. This extracts the tutorial grid and slide deck link from the current learn page:

```tsx
import TutorialStep from "./TutorialStep";

const TUTORIALS = [
  {
    step: 1,
    title: "Prepare Training Data",
    description: "Convert expert Q&A into structured JSONL format for fine-tuning",
    colabUrl: "https://colab.research.google.com/github/William-Hill/d4bl_ai_agent/blob/main/notebooks/01_prepare_training_data.ipynb",
  },
  {
    step: 2,
    title: "Fine-Tune with LoRA",
    description: "Train a LoRA adapter on your prepared data using Unsloth",
    colabUrl: "https://colab.research.google.com/github/William-Hill/d4bl_ai_agent/blob/main/notebooks/02_fine_tune_with_lora.ipynb",
  },
  {
    step: 3,
    title: "Quantize & Export",
    description: "Convert your fine-tuned model to GGUF format for Ollama",
    colabUrl: "https://colab.research.google.com/github/William-Hill/d4bl_ai_agent/blob/main/notebooks/03_quantize_and_export.ipynb",
  },
  {
    step: 4,
    title: "Evaluate Your Model",
    description: "Run the evaluation harness and compare against baselines",
    colabUrl: "https://colab.research.google.com/github/William-Hill/d4bl_ai_agent/blob/main/notebooks/04_evaluate_model.ipynb",
  },
  {
    step: 5,
    title: "Deploy to Ollama",
    description: "Register your model with Ollama and wire it into the app",
    colabUrl: "https://colab.research.google.com/github/William-Hill/d4bl_ai_agent/blob/main/notebooks/05_deploy_to_ollama.ipynb",
  },
];

const SLIDE_DECK_URL = "https://gamma.app/docs/Fine-Tuned-Language-Models-for-Data-Justice-sz28cpbxrgl5wsp";

export default function BuildTab() {
  return (
    <div className="space-y-8">
      {/* Slide deck link */}
      <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-6">
        <h3 className="text-lg font-semibold text-white mb-2">Presentation Slide Deck</h3>
        <p className="text-gray-400 mb-4">
          A comprehensive walkthrough of the fine-tuning methodology, from data preparation to deployment.
        </p>
        <a
          href={SLIDE_DECK_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 text-blue-400 hover:text-blue-300 font-medium"
        >
          View Slide Deck
          <span aria-hidden="true">&rarr;</span>
        </a>
      </div>

      {/* Tutorial grid */}
      <div>
        <h3 className="text-lg font-semibold text-white mb-4">Hands-On Tutorials</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {TUTORIALS.map((t) => (
            <TutorialStep
              key={t.step}
              step={t.step}
              title={t.title}
              description={t.description}
              colabUrl={t.colabUrl}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
```

Note: The actual tutorial URLs and slide deck URL must match what's currently in the learn page. The implementor should read the current `page.tsx` to extract the exact values.

- [ ] **Step 2: Commit**

```bash
git add ui-nextjs/components/learn/BuildTab.tsx
git commit -m "feat(ui): add BuildTab component with tutorials and slide deck"
```

---

### Task 10: Frontend — SuggestionsPanel component

**Files:**
- Create: `ui-nextjs/components/learn/SuggestionsPanel.tsx`

- [ ] **Step 1: Create the suggestions display component**

Create `ui-nextjs/components/learn/SuggestionsPanel.tsx`:
```tsx
"use client";

import { useState } from "react";

interface SuggestionRule {
  metric: string;
  severity: string;
  current: number;
  target: number;
  suggestion: string;
  category: string;
}

interface Suggestions {
  rules: SuggestionRule[];
  llm_analysis: string | null;
  generated_at: string;
}

interface SuggestionsPanelProps {
  suggestions: Suggestions | null;
  runId: string;
  onAnalyze?: (runId: string) => Promise<void>;
}

export default function SuggestionsPanel({ suggestions, runId, onAnalyze }: SuggestionsPanelProps) {
  const [analyzing, setAnalyzing] = useState(false);
  const [expanded, setExpanded] = useState(false);

  if (!suggestions || suggestions.rules.length === 0) {
    return null;
  }

  const blocking = suggestions.rules.filter((r) => r.severity === "blocking");
  const nonblocking = suggestions.rules.filter((r) => r.severity === "non-blocking");

  const handleAnalyze = async () => {
    if (!onAnalyze) return;
    setAnalyzing(true);
    try {
      await onAnalyze(runId);
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <div className="mt-4 bg-gray-800/50 border border-gray-700 rounded-lg p-4">
      <h4 className="text-sm font-semibold text-white mb-3">Suggested Improvements</h4>

      {/* Blocking suggestions */}
      {blocking.length > 0 && (
        <div className="mb-3">
          <p className="text-xs font-medium text-red-400 uppercase tracking-wide mb-2">Blocking</p>
          <ul className="space-y-2">
            {blocking.map((s) => (
              <li key={s.metric} className="text-sm bg-red-900/20 border border-red-800/30 rounded p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-red-300">{s.metric}</span>
                  <span className="text-xs text-gray-400">
                    {s.current.toFixed(2)} → {s.target.toFixed(2)}
                  </span>
                </div>
                <p className="text-gray-300">{s.suggestion}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Non-blocking suggestions */}
      {nonblocking.length > 0 && (
        <div className="mb-3">
          <p className="text-xs font-medium text-yellow-400 uppercase tracking-wide mb-2">Non-blocking</p>
          <ul className="space-y-2">
            {nonblocking.map((s) => (
              <li key={s.metric} className="text-sm bg-yellow-900/20 border border-yellow-800/30 rounded p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-yellow-300">{s.metric}</span>
                  <span className="text-xs text-gray-400">
                    {s.current.toFixed(2)} → {s.target.toFixed(2)}
                  </span>
                </div>
                <p className="text-gray-300">{s.suggestion}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* LLM Analysis section */}
      {suggestions.llm_analysis ? (
        <div className="mt-3">
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-sm text-blue-400 hover:text-blue-300 font-medium"
          >
            {expanded ? "Hide" : "Show"} LLM Analysis
          </button>
          {expanded && (
            <div className="mt-2 bg-gray-900/50 rounded p-3 text-sm text-gray-300 whitespace-pre-wrap">
              {suggestions.llm_analysis}
            </div>
          )}
        </div>
      ) : onAnalyze ? (
        <button
          onClick={handleAnalyze}
          disabled={analyzing}
          className="mt-2 text-sm bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 text-white px-4 py-2 rounded transition-colors"
        >
          {analyzing ? "Analyzing..." : "Analyze Failures"}
        </button>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add ui-nextjs/components/learn/SuggestionsPanel.tsx
git commit -m "feat(ui): add SuggestionsPanel for post-eval improvement suggestions"
```

---

### Task 11: Frontend — Update API types and functions

**Files:**
- Modify: `ui-nextjs/lib/api.ts:206-276`

- [ ] **Step 1: Update TypeScript types**

In `ui-nextjs/lib/api.ts`, add new types and update existing ones:

Add `SuggestionRule` and `Suggestions` interfaces:
```typescript
export interface SuggestionRule {
  metric: string;
  severity: string;
  current: number;
  target: number;
  suggestion: string;
  category: string;
}

export interface Suggestions {
  rules: SuggestionRule[];
  llm_analysis: string | null;
  generated_at: string;
}
```

Add `id` and `suggestions` to `EvalRunItem` (both needed for SuggestionsPanel → analyze endpoint):
```typescript
export interface EvalRunItem {
  id: string | null;  // NEW — needed for POST /api/eval-runs/{id}/analyze
  // ... existing fields ...
  suggestions: Suggestions | null;  // NEW
}
```

Add optional model fields to `compareModels` parameters:
```typescript
export interface CompareModelsParams {
  prompt: string;
  pipeline_a_parser?: string;
  pipeline_a_explainer?: string;
  pipeline_b_parser?: string;
  pipeline_b_explainer?: string;
}
```

Add `ModelInfo` type for model selector:
```typescript
export interface ModelInfo {
  provider: string;
  model: string;
  model_string: string;
  is_default: boolean;
  task: string;
  type: "base" | "finetuned";
  version: string | null;
}
```

- [ ] **Step 2: Update compareModels function**

Update `compareModels` to accept the new params object. The `string` union preserves backward compatibility — verify no other callers exist besides `ModelComparisonPlayground.tsx` (currently the only caller):
```typescript
export async function compareModels(params: CompareModelsParams | string): Promise<CompareResponse> {
  const body = typeof params === "string" ? { prompt: params } : params;
  const resp = await fetch(`${API_BASE}/api/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    if (resp.status === 401) window.location.href = "/login";
    throw new Error(`Compare failed: ${resp.status}`);
  }
  return resp.json();
}
```

- [ ] **Step 3: Add analyzeFailures function**

```typescript
export async function analyzeFailures(runId: string, force = false): Promise<{ run_id: string; suggestions: Suggestions }> {
  const url = `${API_BASE}/api/eval-runs/${runId}/analyze${force ? "?force=true" : ""}`;
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
  });
  if (!resp.ok) {
    if (resp.status === 401) window.location.href = "/login";
    throw new Error(`Analyze failed: ${resp.status}`);
  }
  return resp.json();
}
```

- [ ] **Step 4: Add getModels function**

```typescript
export async function getModels(): Promise<ModelInfo[]> {
  const resp = await fetch(`${API_BASE}/api/models`);
  if (!resp.ok) throw new Error(`Failed to fetch models: ${resp.status}`);
  const data = await resp.json();
  return data.models ?? data;
}
```

- [ ] **Step 5: Commit**

```bash
git add ui-nextjs/lib/api.ts
git commit -m "feat(ui): update API types for model selector, suggestions, and analyze"
```

---

### Task 12: Frontend — Update ModelComparisonPlayground with model selector

**Files:**
- Modify: `ui-nextjs/components/learn/ModelComparisonPlayground.tsx`

- [ ] **Step 1: Add model selector state and dropdowns**

In `ModelComparisonPlayground.tsx`:

1. Import `getModels`, `ModelInfo`, `CompareModelsParams` from `@/lib/api`.
2. Add state for available models and selected models:
```tsx
const [models, setModels] = useState<ModelInfo[]>([]);
const [pipelineA, setPipelineA] = useState({ parser: "", explainer: "" });
const [pipelineB, setPipelineB] = useState({ parser: "", explainer: "" });
```

3. Add `useEffect` to fetch models on mount and set defaults:
```tsx
useEffect(() => {
  getModels().then((m) => {
    setModels(m);
    const defaultBase = m.find((x) => x.is_default)?.model ?? "";
    const latestFt = m.filter((x) => x.type === "finetuned");
    const ftParser = latestFt.find((x) => x.task === "query_parser")?.model ?? defaultBase;
    const ftExplainer = latestFt.find((x) => x.task === "explainer")?.model ?? defaultBase;
    setPipelineA({ parser: defaultBase, explainer: defaultBase });
    setPipelineB({ parser: ftParser, explainer: ftExplainer });
  }).catch(() => {});
}, []);
```

4. Add model selector UI above the prompt textarea — two side-by-side sections labeled "Pipeline A" and "Pipeline B" with a "vs" separator. Each section has a single dropdown that selects a model grouping:
   - Base models: sets both parser and explainer to the same model
   - D4BL versions: sets parser to d4bl-query-parser and explainer to d4bl-explainer

```tsx
{/* Model Selector */}
<div className="flex items-center gap-4 mb-6">
  <div className="flex-1">
    <label className="block text-xs text-gray-400 mb-1">Pipeline A</label>
    <select
      value={pipelineA.parser}
      onChange={(e) => {
        const model = e.target.value;
        const info = models.find((m) => m.model === model);
        if (info?.type === "finetuned") {
          const ftModels = models.filter((m) => m.type === "finetuned");
          setPipelineA({
            parser: ftModels.find((m) => m.task === "query_parser")?.model ?? model,
            explainer: ftModels.find((m) => m.task === "explainer")?.model ?? model,
          });
        } else {
          setPipelineA({ parser: model, explainer: model });
        }
      }}
      className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm text-white"
    >
      {models.filter((m) => m.type === "base").map((m) => (
        <option key={m.model} value={m.model}>{m.model}</option>
      ))}
      <optgroup label="Fine-Tuned">
        {[...new Set(models.filter((m) => m.type === "finetuned").map((m) => m.version))].map((v) => (
          <option key={`ft-${v}`} value={models.find((m) => m.type === "finetuned")?.model ?? ""}>
            D4BL {v}
          </option>
        ))}
      </optgroup>
    </select>
  </div>
  <span className="text-gray-500 font-bold mt-5">vs</span>
  <div className="flex-1">
    <label className="block text-xs text-gray-400 mb-1">Pipeline B</label>
    {/* Same dropdown pattern as Pipeline A but with pipelineB state */}
    <select
      value={pipelineB.parser}
      onChange={(e) => {
        const model = e.target.value;
        const info = models.find((m) => m.model === model);
        if (info?.type === "finetuned") {
          const ftModels = models.filter((m) => m.type === "finetuned");
          setPipelineB({
            parser: ftModels.find((m) => m.task === "query_parser")?.model ?? model,
            explainer: ftModels.find((m) => m.task === "explainer")?.model ?? model,
          });
        } else {
          setPipelineB({ parser: model, explainer: model });
        }
      }}
      className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm text-white"
    >
      {models.filter((m) => m.type === "base").map((m) => (
        <option key={m.model} value={m.model}>{m.model}</option>
      ))}
      <optgroup label="Fine-Tuned">
        {[...new Set(models.filter((m) => m.type === "finetuned").map((m) => m.version))].map((v) => (
          <option key={`ft-${v}`} value={models.find((m) => m.type === "finetuned")?.model ?? ""}>
            D4BL {v}
          </option>
        ))}
      </optgroup>
    </select>
  </div>
</div>
```

5. Update the `compareModels` call to pass the selected models:
```tsx
const res = await compareModels({
  prompt: queryText,
  pipeline_a_parser: pipelineA.parser,
  pipeline_a_explainer: pipelineA.explainer,
  pipeline_b_parser: pipelineB.parser,
  pipeline_b_explainer: pipelineB.explainer,
});
```

- [ ] **Step 2: Commit**

```bash
git add ui-nextjs/components/learn/ModelComparisonPlayground.tsx
git commit -m "feat(ui): add hot-swappable model selector to comparison playground"
```

---

### Task 13: Frontend — Update EvalMetricsPanel with SuggestionsPanel

**Files:**
- Modify: `ui-nextjs/components/learn/EvalMetricsPanel.tsx`

- [ ] **Step 1: Import and render SuggestionsPanel**

In `EvalMetricsPanel.tsx`:

1. Import the new components and API functions:
```tsx
import SuggestionsPanel from "./SuggestionsPanel";
import { analyzeFailures } from "@/lib/api";
```

2. Inside each `TaskCard`, after the metrics display, render:
```tsx
<SuggestionsPanel
  suggestions={run.suggestions}
  runId={run.id ?? ""}
  onAnalyze={async (id) => {
    const result = await analyzeFailures(id);
    // Refresh the eval runs to pick up updated suggestions
    // (re-fetch from API)
  }}
/>
```

Note: The implementor must check the current `TaskCard` structure and wire the `run.id` through from the API response. The `EvalRunItem` type may need an `id` field added — check and add if missing.

- [ ] **Step 2: Commit**

```bash
git add ui-nextjs/components/learn/EvalMetricsPanel.tsx
git commit -m "feat(ui): integrate SuggestionsPanel into eval metrics display"
```

---

### Task 14: Frontend — Restructure /learn page into tabbed layout

**Files:**
- Modify: `ui-nextjs/app/learn/page.tsx`

- [ ] **Step 1: Restructure the page**

Rewrite `ui-nextjs/app/learn/page.tsx` to use the tabbed layout:

1. Keep the compact hero (title + subtitle, no slide deck link).
2. Import `LearnTabs`, `BuildTab`, `ModelComparisonPlayground`, `EvalMetricsPanel`, and all educational section components.
3. Define three tabs:

```tsx
import LearnTabs from "@/components/learn/LearnTabs";
import BuildTab from "@/components/learn/BuildTab";
// ... other imports

export default function LearnPage() {
  return (
    <main className="min-h-screen bg-gray-950 text-white">
      {/* Compact hero */}
      <section className="pt-16 pb-8 px-6 max-w-6xl mx-auto text-center">
        <h1 className="text-4xl font-bold mb-3">Fine-Tuned Models for Data Justice</h1>
        <p className="text-gray-400 text-lg max-w-2xl mx-auto">
          Compare model pipelines, explore evaluation metrics, and learn how fine-tuning
          embeds equity methodology into AI systems.
        </p>
      </section>

      {/* Tabs */}
      <section className="max-w-6xl mx-auto px-6 pb-16">
        <LearnTabs
          tabs={[
            {
              id: "compare",
              label: "Compare",
              content: (
                <div className="space-y-12">
                  <ModelComparisonPlayground />
                  <EvalMetricsPanel />
                </div>
              ),
            },
            {
              id: "learn",
              label: "Learn",
              content: (
                <div className="space-y-16">
                  {/* All 7 existing ConceptSection blocks, unchanged */}
                </div>
              ),
            },
            {
              id: "build",
              label: "Build",
              content: <BuildTab />,
            },
          ]}
        />
      </section>
    </main>
  );
}
```

The implementor must copy the 7 ConceptSection blocks from the current page into the Learn tab content, preserving them exactly.

- [ ] **Step 2: Verify the build succeeds**

Run: `cd ui-nextjs && npm run build`
Expected: Build succeeds with no errors.

- [ ] **Step 3: Run lint**

Run: `cd ui-nextjs && npm run lint`
Expected: No lint errors.

- [ ] **Step 4: Commit**

```bash
git add ui-nextjs/app/learn/page.tsx
git commit -m "feat(ui): restructure /learn into tabbed layout (Compare, Learn, Build)"
```

---

### Task 15: Integration testing and final verification

**Files:**
- All modified files

- [ ] **Step 1: Run all Python tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests PASS.

- [ ] **Step 2: Run frontend build**

Run: `cd ui-nextjs && npm run build`
Expected: Build succeeds.

- [ ] **Step 3: Run frontend lint**

Run: `cd ui-nextjs && npm run lint`
Expected: No errors.

- [ ] **Step 4: Verify migration file exists and is valid SQL**

Run: `cat supabase/migrations/20260327000001_add_suggestions_to_eval_runs.sql`
Expected: Valid ALTER TABLE statement.

- [ ] **Step 5: Final commit if any remaining changes**

```bash
git status
# If any unstaged changes, stage and commit
```
