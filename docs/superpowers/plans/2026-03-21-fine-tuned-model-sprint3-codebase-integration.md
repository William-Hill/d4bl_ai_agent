# Sprint 3: Codebase Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the fine-tuned D4BL models (query parser, explainer, evaluator) into the existing application so each LLM call uses the appropriate task-specific model with automatic fallback to the general-purpose model.

**Architecture:** Add three task-specific model name settings to `Settings`. Add a `model_for_task()` helper in `ollama_client.py` that resolves the right model name per task. Update each call site (parser, fusion, explain endpoint, evaluators) to pass the resolved model name. Add a comparison eval script that runs the same prompts through both models and reports score deltas.

**Tech Stack:** Python, FastAPI, CrewAI LLM, LiteLLM, pytest

**Spec:** `docs/superpowers/specs/2026-03-21-fine-tuned-model-design.md` (Section 5.3, 9)

**Dependencies:** Sprint 2 merged (PR #126) — provides Modelfiles, `validate_model_output.py`, `register_models.py`, and integration tests.

**Deferred to Sprint 4:** `/learn` educational page, mobile 1.5B model, Gamma deck, RunPod production deployment, `ParsedQuery.community_framing` field extension (Spec Section 9 line 1475), `ModelEvalRun` database model (Spec Section 9 line 1476), `TrainingDataLineage` database model (Spec Section 9 line 1477).

---

## File Structure

```
src/d4bl/
├── settings.py                          # Modify: add 3 task-model settings
├── llm/
│   ├── ollama_client.py                 # Modify: add model_for_task() helper
│   ├── provider.py                      # Modify: add get_llm_for_task()
│   ├── __init__.py                      # Modify: export new functions
├── query/
│   ├── parser.py                        # Modify: use query_parser model
│   ├── fusion.py                        # Modify: use explainer model
├── app/
│   ├── explore_insights.py              # Modify: use explainer model
├── services/langfuse/
│   ├── llm_runner.py                    # Modify: add get_eval_llm_for_task()
│   ├── _base.py                         # Modify: accept task parameter
│   ├── runner.py                        # Modify: pass evaluator model
scripts/
├── training/
│   ├── compare_models.py               # Create: A/B comparison eval script
tests/
├── test_model_routing.py               # Create: model routing unit tests
├── test_compare_models.py              # Create: comparison script tests
```

---

## Task 1: Add Task-Specific Model Settings

**Files:**
- Modify: `src/d4bl/settings.py`
- Modify: `tests/test_settings.py`

- [ ] **Step 1: Write failing tests for new settings**

Add to `tests/test_settings.py` inside the `TestFieldDefaults` class:

```python
def test_task_model_settings_default_to_empty(self):
    """Task-specific model settings default to empty string (use general model)."""
    s = _fresh_settings()
    assert s.query_parser_model == ""
    assert s.explainer_model == ""
    assert s.evaluator_model == ""

def test_task_model_settings_from_env(self):
    """Task-specific model settings read from environment."""
    s = _fresh_settings(
        QUERY_PARSER_MODEL="d4bl-query-parser",
        EXPLAINER_MODEL="d4bl-explainer",
        EVALUATOR_MODEL="d4bl-evaluator",
    )
    assert s.query_parser_model == "d4bl-query-parser"
    assert s.explainer_model == "d4bl-explainer"
    assert s.evaluator_model == "d4bl-evaluator"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_settings.py::TestFieldDefaults::test_task_model_settings_default_to_empty tests/test_settings.py::TestFieldDefaults::test_task_model_settings_from_env -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'query_parser_model'`

- [ ] **Step 3: Add settings fields**

In `src/d4bl/settings.py`, add three field declarations after the `llm_api_key` field (around line 57):

```python
    # -- Fine-tuned task models (empty = use llm_model / ollama_model) --
    query_parser_model: str = field(init=False)
    explainer_model: str = field(init=False)
    evaluator_model: str = field(init=False)
```

In `__post_init__`, after the `_set("llm_api_key", ...)` line (around line 146), add:

```python
        # Fine-tuned task models
        _set("query_parser_model", os.getenv("QUERY_PARSER_MODEL", ""))
        _set("explainer_model", os.getenv("EXPLAINER_MODEL", ""))
        _set("evaluator_model", os.getenv("EVALUATOR_MODEL", ""))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_settings.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/settings.py tests/test_settings.py
git commit -m "feat: add task-specific model name settings for fine-tuned models"
```

---

## Task 2: Add Model Routing Helper to ollama_client

**Files:**
- Modify: `src/d4bl/llm/ollama_client.py`
- Create: `tests/test_model_routing.py`

- [ ] **Step 1: Write failing tests for model_for_task()**

Create `tests/test_model_routing.py`:

```python
"""Tests for task-specific model routing."""
from __future__ import annotations

from unittest.mock import patch

import pytest

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
    def test_unknown_task_returns_default(self, mock_settings):
        mock_settings.return_value.ollama_model = "mistral"
        assert model_for_task("unknown_task") == "mistral"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_model_routing.py -v`
Expected: FAIL with `ImportError: cannot import name 'model_for_task'`

- [ ] **Step 3: Implement model_for_task()**

Add to `src/d4bl/llm/ollama_client.py`, after the imports and before `ollama_generate`:

```python
# Task name → Settings attribute mapping
_TASK_MODEL_ATTRS: dict[str, str] = {
    "query_parser": "query_parser_model",
    "explainer": "explainer_model",
    "evaluator": "evaluator_model",
}


def model_for_task(task: str) -> str:
    """Resolve the Ollama model name for a given task.

    Returns the task-specific model if configured (non-empty env var),
    otherwise falls back to the general ``ollama_model`` setting.
    """
    settings = get_settings()
    attr = _TASK_MODEL_ATTRS.get(task)
    if attr:
        task_model = getattr(settings, attr, "")
        if task_model:
            return task_model
    return settings.ollama_model
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_model_routing.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/llm/ollama_client.py tests/test_model_routing.py
git commit -m "feat: add model_for_task() routing helper"
```

---

## Task 3: Wire Query Parser to Use Fine-Tuned Model

**Files:**
- Modify: `src/d4bl/query/parser.py`
- Modify: `tests/test_query_parser.py`

- [ ] **Step 1: Write failing test for model routing in parser**

Add a new test to `tests/test_query_parser.py`:

```python
@patch("d4bl.query.parser.model_for_task", return_value="d4bl-query-parser")
@patch("d4bl.query.parser.ollama_generate", new_callable=AsyncMock)
async def test_parse_uses_task_specific_model(self, mock_generate, mock_model):
    """Parser should call model_for_task('query_parser') and pass result to ollama_generate."""
    mock_generate.return_value = json.dumps({
        "entities": ["test"],
        "search_queries": ["test query"],
        "data_sources": ["vector"],
    })
    parser = QueryParser(ollama_base_url="http://localhost:11434")
    await parser.parse("test question")

    mock_model.assert_called_once_with("query_parser")
    mock_generate.assert_called_once()
    call_kwargs = mock_generate.call_args[1]
    assert call_kwargs["model"] == "d4bl-query-parser"
```

Note: The `@patch` decorator handles the import — no direct import of `model_for_task` is needed in the test file. The patch target `d4bl.query.parser.model_for_task` patches where it's used (in parser.py), not where it's defined.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_query_parser.py::TestQueryParser::test_parse_uses_task_specific_model -v`
Expected: FAIL (no `model_for_task` import in parser.py, no `model` kwarg passed)

- [ ] **Step 3: Update parser.py to use model_for_task()**

In `src/d4bl/query/parser.py`:

1. Add import after the existing `ollama_generate` import:

```python
from d4bl.llm.ollama_client import model_for_task, ollama_generate
```

(Replace the existing single import line.)

2. In `_parse_with_llm()`, change the `ollama_generate` call to pass the model:

```python
    async def _parse_with_llm(self, query: str) -> ParsedQuery:
        """Use the fine-tuned query parser model (or fallback) to parse the query."""
        prompt = PARSE_PROMPT.substitute(query=query)

        raw_text = await ollama_generate(
            base_url=self.ollama_base_url,
            prompt=prompt,
            model=model_for_task("query_parser"),
            temperature=0.1,
            timeout_seconds=30,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_query_parser.py -v`
Expected: All tests PASS (existing tests still work because `model_for_task` returns `settings.ollama_model` when no task model is configured, which is the same default `ollama_generate` was using)

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/query/parser.py tests/test_query_parser.py
git commit -m "feat: wire query parser to use fine-tuned model via model_for_task"
```

---

## Task 4: Wire Result Fusion to Use Fine-Tuned Explainer

**Files:**
- Modify: `src/d4bl/query/fusion.py`
- Modify: `tests/test_query_fusion.py`

- [ ] **Step 1: Write failing test for model routing in fusion**

Add a new test to `tests/test_query_fusion.py`:

```python
@patch("d4bl.query.fusion.model_for_task", return_value="d4bl-explainer")
@patch("d4bl.query.fusion.ollama_generate", new_callable=AsyncMock)
async def test_synthesize_uses_task_specific_model(self, mock_generate, mock_model):
    """Fusion should use the explainer model for synthesis."""
    mock_generate.return_value = "Test answer"
    fusion = ResultFusion(ollama_base_url="http://localhost:11434")
    sources = [SourceReference(
        url="http://example.com", title="Test", snippet="test",
        source_type="vector", relevance_score=0.9,
    )]
    await fusion.synthesize("test query", sources)

    mock_model.assert_called_once_with("explainer")
    call_kwargs = mock_generate.call_args[1]
    assert call_kwargs["model"] == "d4bl-explainer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_query_fusion.py::TestResultFusion::test_synthesize_uses_task_specific_model -v`
Expected: FAIL

- [ ] **Step 3: Update fusion.py to use model_for_task()**

In `src/d4bl/query/fusion.py`:

1. Update import:

```python
from d4bl.llm.ollama_client import model_for_task, ollama_generate
```

2. Update `_generate_answer()` to pass the model:

```python
    async def _generate_answer(
        self, query: str, sources: list[SourceReference]
    ) -> str:
        """Use the fine-tuned explainer model (or fallback) to synthesize an answer."""
        sources_text = "\n".join(
            f"[{i + 1}] ({s.source_type}) {s.title}\n{s.snippet}"
            for i, s in enumerate(sources[:10])
        )
        prompt = SYNTHESIS_PROMPT.substitute(
            query=query, sources_text=sources_text
        )

        return await ollama_generate(
            base_url=self.ollama_base_url,
            prompt=prompt,
            model=model_for_task("explainer"),
            temperature=0.3,
            timeout_seconds=60,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_query_fusion.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/query/fusion.py tests/test_query_fusion.py
git commit -m "feat: wire result fusion to use fine-tuned explainer model"
```

---

## Task 5: Wire Explore Insights Explain Endpoint to Use Fine-Tuned Explainer

**Files:**
- Modify: `src/d4bl/app/explore_insights.py`
- Modify: `tests/test_explore_explain.py` (NOT `test_explore_insights.py` — that file tests state-summary)

- [ ] **Step 1: Write failing test for model routing in explain endpoint**

Add a test to `tests/test_explore_explain.py`, following the existing pattern in that file (uses `override_auth` fixture, `_mock_llm_response` helper, inline `AsyncClient`):

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_explore_explain.py::TestExplainEndpoint::test_explain_uses_task_specific_model -v`
Expected: FAIL

- [ ] **Step 3: Update explore_insights.py to use model_for_task()**

In `src/d4bl/app/explore_insights.py`:

1. Add import:

```python
from d4bl.llm.ollama_client import model_for_task
```

2. In `explain_view()`, replace the model string construction:

```python
    # Before:
    model = f"ollama/{settings.ollama_model}"

    # After:
    model = f"ollama/{model_for_task('explainer')}"
```

The `settings = get_settings()` line is still needed for `settings.ollama_base_url` in the `acompletion` call.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_explore_explain.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/app/explore_insights.py tests/test_explore_explain.py
git commit -m "feat: wire explore explain endpoint to use fine-tuned explainer model"
```

---

## Task 6: Wire Evaluators to Use Fine-Tuned Evaluator Model

**Files:**
- Modify: `src/d4bl/services/langfuse/llm_runner.py`
- Modify: `src/d4bl/llm/provider.py`
- Modify: `src/d4bl/llm/__init__.py`
- Create or modify: `tests/test_llm_provider.py`

The evaluators use the CrewAI `LLM` class (not `ollama_generate`), so we need a `get_llm_for_task()` function in `provider.py` that creates a task-specific LLM instance.

- [ ] **Step 1: Write failing tests for get_llm_for_task()**

Add to `tests/test_llm_provider.py`:

```python
class TestGetLlmForTask:
    """get_llm_for_task() creates a task-specific LLM when configured."""

    @patch("d4bl.llm.provider.get_settings")
    @patch("d4bl.llm.provider.LLM")
    def test_returns_task_specific_llm(self, mock_llm_cls, mock_get_settings):
        from d4bl.llm.provider import get_llm_for_task
        mock_get_settings.return_value.evaluator_model = "d4bl-evaluator"
        mock_get_settings.return_value.llm_provider = "ollama"
        mock_get_settings.return_value.llm_model = "mistral"
        mock_get_settings.return_value.ollama_base_url = "http://localhost:11434"
        mock_get_settings.return_value.llm_api_key = None

        result = get_llm_for_task("evaluator")
        mock_llm_cls.assert_called()
        call_kwargs = mock_llm_cls.call_args[1]
        assert call_kwargs["model"] == "ollama/d4bl-evaluator"

    @patch("d4bl.llm.provider.get_settings")
    @patch("d4bl.llm.provider.get_llm")
    def test_falls_back_to_default_llm(self, mock_get_llm, mock_get_settings):
        from d4bl.llm.provider import get_llm_for_task
        mock_get_settings.return_value.evaluator_model = ""
        mock_get_settings.return_value.llm_provider = "ollama"
        sentinel = object()
        mock_get_llm.return_value = sentinel

        result = get_llm_for_task("evaluator")
        assert result is sentinel
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm_provider.py::TestGetLlmForTask -v`
Expected: FAIL with `ImportError: cannot import name 'get_llm_for_task'`

- [ ] **Step 3: Implement get_llm_for_task() in provider.py**

Add to `src/d4bl/llm/provider.py`, after `reset_llm()`:

```python
def get_llm_for_task(task: str) -> LLM:
    """Get an LLM instance for a specific task.

    If a task-specific model is configured (e.g. EVALUATOR_MODEL env var),
    creates a new LLM for that model. Otherwise returns the default LLM.

    Note: Task-specific instances are NOT cached as singletons — they are
    lightweight wrappers and creating them is cheap. This avoids stale state
    if env vars change.
    """
    from d4bl.llm.ollama_client import _TASK_MODEL_ATTRS, model_for_task

    settings = get_settings()

    # If no task-specific model is configured, return the shared default
    attr = _TASK_MODEL_ATTRS.get(task)
    task_setting = getattr(settings, attr, "") if attr else ""
    if not task_setting:
        return get_llm()

    task_model = model_for_task(task)

    provider = settings.llm_provider
    model_string = build_llm_model_string(provider, task_model)

    kwargs: dict = {
        "model": model_string,
        "temperature": 0.1,
        "timeout": 180.0,
        "num_retries": 5,
    }

    if provider == "ollama":
        kwargs["base_url"] = settings.ollama_base_url
    elif settings.llm_api_key:
        kwargs["api_key"] = settings.llm_api_key

    logger.info("Creating task-specific LLM (task=%s, model=%s)", task, task_model)
    return LLM(**kwargs)
```

- [ ] **Step 4: Export from __init__.py**

In `src/d4bl/llm/__init__.py`, add `get_llm_for_task` to the imports and `__all__`:

```python
from d4bl.llm.provider import build_llm_model_string, get_available_models, get_llm, get_llm_for_task, reset_llm
```

```python
__all__ = [
    "get_llm",
    "get_llm_for_task",
    "reset_llm",
    ...
]
```

- [ ] **Step 5: Update llm_runner.py to use task-specific LLM**

In `src/d4bl/services/langfuse/llm_runner.py`, **replace** the existing import on line 7:

```python
# Before (line 7):
from d4bl.llm import get_ollama_llm

# After:
from d4bl.llm import get_llm_for_task, get_ollama_llm
```

Then add the new function after the `get_eval_llm` alias:

```python
def get_eval_llm_for_task(task: str = "evaluator"):
    """Get an LLM configured for a specific evaluation task."""
    return get_llm_for_task(task)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_llm_provider.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/d4bl/llm/provider.py src/d4bl/llm/__init__.py src/d4bl/services/langfuse/llm_runner.py tests/test_llm_provider.py
git commit -m "feat: add get_llm_for_task() for task-specific LLM instances"
```

---

## Task 7: Update Evaluation Runner to Use Evaluator Model

**Files:**
- Modify: `src/d4bl/services/langfuse/runner.py`
- Modify: `tests/test_langfuse_evaluations.py` (or existing eval test file)

- [ ] **Step 1: Read the current runner.py to understand the LLM injection pattern**

Run: `cat -n src/d4bl/services/langfuse/runner.py | head -60`

The runner calls `get_eval_llm()` once and passes the LLM to all evaluators. We need it to use `get_eval_llm_for_task("evaluator")` instead.

- [ ] **Step 2: Write failing test**

Create `tests/test_eval_runner_model.py`:

```python
"""Test that the evaluation runner uses the task-specific evaluator model."""
from unittest.mock import MagicMock, patch

import pytest


class TestRunnerModelRouting:
    @patch("d4bl.services.langfuse.runner.get_eval_llm_for_task")
    @patch("d4bl.services.langfuse.runner.get_langfuse_eval_client")
    def test_runner_calls_get_eval_llm_for_task(self, mock_langfuse, mock_get_task_llm):
        """run_comprehensive_evaluation() should call get_eval_llm_for_task('evaluator')."""
        from d4bl.services.langfuse.runner import run_comprehensive_evaluation

        mock_langfuse.return_value = None  # Skip Langfuse (returns SKIPPED)
        mock_get_task_llm.return_value = MagicMock()

        run_comprehensive_evaluation(
            query="test", research_output="test output", sources=[]
        )

        mock_get_task_llm.assert_called_once_with("evaluator")
```

- [ ] **Step 3: Update runner.py**

In `src/d4bl/services/langfuse/runner.py`, change the LLM initialization:

```python
# Before:
from d4bl.services.langfuse.llm_runner import get_eval_llm

# After:
from d4bl.services.langfuse.llm_runner import get_eval_llm, get_eval_llm_for_task
```

In `run_comprehensive_evaluation()`, change:

```python
# Before:
llm = get_eval_llm()

# After:
llm = get_eval_llm_for_task("evaluator")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ -v -k "eval" --ignore=tests/test_training`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/services/langfuse/runner.py tests/
git commit -m "feat: wire evaluation runner to use fine-tuned evaluator model"
```

---

## Task 8: Update /api/models Endpoint to Show Task-Specific Models

**Files:**
- Modify: `src/d4bl/llm/provider.py`
- Modify: `tests/test_api_models.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_api_models.py`:

```python
@patch("d4bl.llm.provider.get_settings")
def test_available_models_includes_task_models(self, mock_settings):
    """When task models are configured, /api/models should list them."""
    from d4bl.llm.provider import get_available_models
    mock_settings.return_value.llm_provider = "ollama"
    mock_settings.return_value.llm_model = "mistral"
    mock_settings.return_value.query_parser_model = "d4bl-query-parser"
    mock_settings.return_value.explainer_model = "d4bl-explainer"
    mock_settings.return_value.evaluator_model = ""  # not configured

    models = get_available_models()
    model_names = [m["model"] for m in models]
    assert "mistral" in model_names
    assert "d4bl-query-parser" in model_names
    assert "d4bl-explainer" in model_names
    # evaluator not configured, should not appear as separate entry
    assert len(models) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_models.py::test_available_models_includes_task_models -v`
Expected: FAIL (currently returns only 1 model)

- [ ] **Step 3: Update get_available_models()**

In `src/d4bl/llm/provider.py`, update `get_available_models()`:

```python
def get_available_models() -> list[dict]:
    """Return available models based on current configuration.

    Includes the default model plus any configured task-specific models.
    """
    settings = get_settings()
    current_model_string = build_llm_model_string(
        settings.llm_provider, settings.llm_model
    )
    models = [
        {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "model_string": current_model_string,
            "is_default": True,
            "task": "general",
        }
    ]

    seen = {settings.llm_model}
    task_attrs = {
        "query_parser": "query_parser_model",
        "explainer": "explainer_model",
        "evaluator": "evaluator_model",
    }
    for task, attr in task_attrs.items():
        model_name = getattr(settings, attr, "")
        if model_name and model_name not in seen:
            seen.add(model_name)
            models.append({
                "provider": settings.llm_provider,
                "model": model_name,
                "model_string": build_llm_model_string(settings.llm_provider, model_name),
                "is_default": False,
                "task": task,
            })

    return models
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_models.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/llm/provider.py tests/test_api_models.py
git commit -m "feat: show task-specific models in /api/models endpoint"
```

---

## Task 9: Add Comparison Eval Script

**Prerequisite:** Sprint 2 (PR #126) must be merged before starting this task. It provides `scripts/training/validate_model_output.py` with the `validate_parser_output`, `validate_explainer_output`, and `validate_evaluator_output` functions used below. If Sprint 2 is not yet merged, skip this task and return to it after merge.

**Files:**
- Create: `scripts/training/compare_models.py`
- Create: `tests/test_compare_models.py`

This script runs the same prompts through both the baseline (mistral) and fine-tuned models, then reports score deltas. It reuses the `validate_model_output.py` validators from Sprint 2.

- [ ] **Step 1: Write failing tests for comparison logic**

Create `tests/test_compare_models.py`:

```python
"""Tests for the model comparison evaluation script."""
from __future__ import annotations

import pytest

from scripts.training.compare_models import (
    ComparisonResult,
    compare_single,
    format_report,
)


class TestComparisonResult:
    def test_delta(self):
        r = ComparisonResult(
            prompt="test", task="query_parser",
            baseline_valid=True, baseline_latency=1.0,
            finetuned_valid=True, finetuned_latency=0.5,
        )
        assert r.latency_delta == -0.5

    def test_validity_improvement(self):
        r = ComparisonResult(
            prompt="test", task="query_parser",
            baseline_valid=False, baseline_latency=1.0,
            finetuned_valid=True, finetuned_latency=0.5,
        )
        assert r.validity_improved is True


class TestFormatReport:
    def test_report_structure(self):
        results = [
            ComparisonResult(
                prompt="p1", task="query_parser",
                baseline_valid=True, baseline_latency=1.0,
                finetuned_valid=True, finetuned_latency=0.5,
            ),
        ]
        report = format_report(results)
        assert "query_parser" in report
        assert "Latency" in report
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_compare_models.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement compare_models.py**

Create `scripts/training/compare_models.py`:

```python
"""Compare baseline vs fine-tuned model outputs side by side.

Usage:
    python -m scripts.training.compare_models
    python -m scripts.training.compare_models --task query_parser
    python -m scripts.training.compare_models --baseline mistral --ollama-url http://localhost:11434
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from dataclasses import dataclass

from scripts.training.validate_model_output import (
    validate_evaluator_output,
    validate_explainer_output,
    validate_parser_output,
)

logger = logging.getLogger(__name__)

# Sample prompts per task (representative of real usage)
SAMPLE_PROMPTS: dict[str, list[str]] = {
    "query_parser": [
        "What is the median household income for Black families in Mississippi?",
        "Compare cancer rates between white and Hispanic populations in Texas and California",
        "Show me the trend in police use of force incidents in Chicago over the last 5 years",
        "Which states have the highest incarceration rates for Black men?",
        "How does air quality near EPA Superfund sites affect minority communities?",
    ],
    "explainer": [
        (
            "Data source: census\nMetric: median_household_income\n"
            "State: Mississippi (FIPS 28)\nValue: 45081\n"
            "National average: 69021\nYear: 2022\n"
            "Racial breakdown: white: 55602, black: 32815, hispanic: 42189\n"
            "Max disparity ratio: 1.69 (white vs black)\n\n"
            "Provide a concise narrative explaining what this data means for "
            "racial equity in this state."
        ),
    ],
    "evaluator": [
        (
            "Evaluate the following response for equity framing quality.\n\n"
            "Query: What is the median household income in Mississippi?\n"
            "Response: The median household income in Mississippi is $45,081, "
            "which is below the national average of $69,021. Black families earn "
            "significantly less at $32,815 compared to white families at $55,602.\n\n"
            "Score 1-5 on: structural framing, community voice, policy connection, "
            "data acknowledgment."
        ),
    ],
}

VALIDATORS = {
    "query_parser": validate_parser_output,
    "explainer": validate_explainer_output,
    "evaluator": validate_evaluator_output,
}


@dataclass
class ComparisonResult:
    prompt: str
    task: str
    baseline_valid: bool
    baseline_latency: float
    finetuned_valid: bool
    finetuned_latency: float
    baseline_output: str = ""
    finetuned_output: str = ""
    baseline_errors: list[str] | None = None
    finetuned_errors: list[str] | None = None

    @property
    def latency_delta(self) -> float:
        return self.finetuned_latency - self.baseline_latency

    @property
    def validity_improved(self) -> bool:
        return self.finetuned_valid and not self.baseline_valid


async def _run_prompt(
    base_url: str, model: str, prompt: str, timeout: int = 60,
) -> tuple[str, float]:
    """Run a single prompt and return (output, latency_seconds)."""
    # Import here to avoid circular imports at module level
    from d4bl.llm.ollama_client import ollama_generate

    start = time.monotonic()
    output = await ollama_generate(
        base_url=base_url, prompt=prompt, model=model,
        temperature=0.1, timeout_seconds=timeout,
    )
    elapsed = time.monotonic() - start
    return output, elapsed


async def compare_single(
    base_url: str,
    baseline_model: str,
    finetuned_model: str,
    task: str,
    prompt: str,
) -> ComparisonResult:
    """Run one prompt through both models and compare."""
    validator = VALIDATORS[task]

    try:
        b_output, b_latency = await _run_prompt(base_url, baseline_model, prompt)
    except Exception as e:
        b_output, b_latency = str(e), 0.0

    try:
        f_output, f_latency = await _run_prompt(base_url, finetuned_model, prompt)
    except Exception as e:
        f_output, f_latency = str(e), 0.0

    b_result = validator(b_output)
    f_result = validator(f_output)

    return ComparisonResult(
        prompt=prompt[:100],
        task=task,
        baseline_valid=b_result.valid,
        baseline_latency=round(b_latency, 3),
        finetuned_valid=f_result.valid,
        finetuned_latency=round(f_latency, 3),
        baseline_output=b_output[:200],
        finetuned_output=f_output[:200],
        baseline_errors=b_result.errors or None,
        finetuned_errors=f_result.errors or None,
    )


def format_report(results: list[ComparisonResult]) -> str:
    """Format comparison results into a human-readable report."""
    lines = ["=" * 70, "Model Comparison Report", "=" * 70, ""]

    by_task: dict[str, list[ComparisonResult]] = {}
    for r in results:
        by_task.setdefault(r.task, []).append(r)

    for task, task_results in by_task.items():
        lines.append(f"## {task}")
        lines.append("-" * 40)

        b_valid = sum(1 for r in task_results if r.baseline_valid)
        f_valid = sum(1 for r in task_results if r.finetuned_valid)
        total = len(task_results)

        b_avg_lat = sum(r.baseline_latency for r in task_results) / total
        f_avg_lat = sum(r.finetuned_latency for r in task_results) / total

        lines.append(f"  Validity:  baseline {b_valid}/{total}  |  fine-tuned {f_valid}/{total}")
        lines.append(f"  Latency:   baseline {b_avg_lat:.2f}s  |  fine-tuned {f_avg_lat:.2f}s")
        lines.append("")

        for i, r in enumerate(task_results, 1):
            status = "✓" if r.finetuned_valid else "✗"
            delta = f"{r.latency_delta:+.2f}s"
            lines.append(f"  [{i}] {status} {delta}  {r.prompt[:60]}...")
            if r.finetuned_errors:
                lines.append(f"      Errors: {', '.join(r.finetuned_errors)}")

        lines.append("")

    return "\n".join(lines)


async def main(args: argparse.Namespace) -> int:
    tasks = [args.task] if args.task else list(SAMPLE_PROMPTS.keys())
    results: list[ComparisonResult] = []

    for task in tasks:
        finetuned = {
            "query_parser": "d4bl-query-parser",
            "explainer": "d4bl-explainer",
            "evaluator": "d4bl-evaluator",
        }[task]

        for prompt in SAMPLE_PROMPTS[task]:
            result = await compare_single(
                base_url=args.ollama_url,
                baseline_model=args.baseline,
                finetuned_model=finetuned,
                task=task,
                prompt=prompt,
            )
            results.append(result)

    print(format_report(results))
    return 0


def cli() -> int:
    parser = argparse.ArgumentParser(description="Compare baseline vs fine-tuned models")
    parser.add_argument("--baseline", default="mistral", help="Baseline model name")
    parser.add_argument("--task", choices=["query_parser", "explainer", "evaluator"],
                        help="Run only one task (default: all)")
    parser.add_argument("--ollama-url", default="http://localhost:11434",
                        help="Ollama base URL")
    args = parser.parse_args()
    return asyncio.run(main(args))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(cli())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_compare_models.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/training/compare_models.py tests/test_compare_models.py
git commit -m "feat: add model comparison eval script (baseline vs fine-tuned)"
```

---

## Task 10: Update .env.example and Documentation

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Add new env vars to .env.example**

Append to `.env.example`:

```bash
# Fine-tuned task-specific models (leave empty to use default LLM_MODEL)
# Set these after running scripts/training/register_models.py
QUERY_PARSER_MODEL=
EXPLAINER_MODEL=
EVALUATOR_MODEL=
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add fine-tuned model env vars to .env.example"
```

---

## Task 11: Full Test Suite Verification

- [ ] **Step 1: Run the complete test suite**

Run: `pytest tests/ -v --ignore=tests/test_training/test_integration_models.py`
Expected: All tests PASS. No regressions — when no `QUERY_PARSER_MODEL`/`EXPLAINER_MODEL`/`EVALUATOR_MODEL` env vars are set, the system behaves identically to before (all calls use `settings.ollama_model`).

- [ ] **Step 2: Run lint**

Run: `cd ui-nextjs && npm run lint && npm run build`
Expected: Clean (no frontend changes in this sprint, but verify no breakage)

- [ ] **Step 3: Verify model routing end-to-end (manual)**

```bash
# Without fine-tuned models (should behave exactly like before)
unset QUERY_PARSER_MODEL EXPLAINER_MODEL EVALUATOR_MODEL
pytest tests/test_model_routing.py tests/test_query_parser.py tests/test_query_fusion.py -v

# With fine-tuned models configured (unit tests with mocks)
QUERY_PARSER_MODEL=d4bl-query-parser EXPLAINER_MODEL=d4bl-explainer EVALUATOR_MODEL=d4bl-evaluator pytest tests/test_model_routing.py -v
```

- [ ] **Step 4: Final commit if any fixups needed**

```bash
git add -A
git commit -m "fix: address test suite issues from integration sprint"
```
