# Model Comparison Playground — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the "Coming Soon" placeholder on the `/learn` page with a live side-by-side model comparison playground and a pre-computed eval metrics panel, backed by two new API endpoints.

**Architecture:** Add `POST /api/compare` (runs a prompt through base + fine-tuned models, validates outputs, returns comparison) and `GET /api/eval-runs` (serves pre-computed metrics from `model_eval_runs` table). Add `--model` flag to `run_eval_harness.py` so baseline metrics can be persisted. Build two new React components: `ModelComparisonPlayground` (interactive) and `EvalMetricsPanel` (pre-computed results). Wire both into the `/learn` page.

**Tech Stack:** Python (FastAPI, SQLAlchemy, asyncio), TypeScript (Next.js, React 19, Tailwind CSS 4)

**Spec:** `docs/superpowers/specs/2026-03-27-model-comparison-playground-design.md`

**Dependencies:** Sprint 3 (PR #127) — model routing. Eval harness (PR #130) — `model_eval_runs` table. Sprint 2 (PR #126) — `validate_model_output.py`.

---

## File Structure

```
Modified:
  src/d4bl/app/api.py                                     — add /api/compare and /api/eval-runs endpoints
  src/d4bl/app/schemas.py                                  — add CompareRequest, CompareResponse, EvalRunItem, EvalRunsResponse
  scripts/training/run_eval_harness.py                     — add --model flag to override inference model
  ui-nextjs/app/learn/page.tsx                             — swap PlaygroundPlaceholder for new components
  ui-nextjs/lib/api.ts                                     — add compareModels() and getEvalRuns() functions

Created:
  ui-nextjs/components/learn/ModelComparisonPlayground.tsx  — interactive side-by-side comparison widget
  ui-nextjs/components/learn/EvalMetricsPanel.tsx           — pre-computed eval harness results display
  tests/test_compare_endpoint.py                           — tests for /api/compare
  tests/test_eval_runs_endpoint.py                         — tests for /api/eval-runs
  tests/test_eval_harness_model_flag.py                    — tests for --model CLI flag
```

---

## Task 1: Add Pydantic Schemas for Compare and Eval Runs

**Files:**
- Modify: `src/d4bl/app/schemas.py`
- Test: `tests/test_compare_endpoint.py`

- [ ] **Step 1: Write failing test for schema validation**

Create `tests/test_compare_endpoint.py`:

```python
"""Tests for model comparison endpoint schemas and behavior."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from d4bl.app.schemas import CompareRequest


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_compare_endpoint.py::TestCompareRequest -v`
Expected: FAIL with `ImportError: cannot import name 'CompareRequest'`

- [ ] **Step 3: Add schemas to schemas.py**

Add at the end of `src/d4bl/app/schemas.py`, before the final blank line:

```python
# --- Model Comparison models ---


class ModelOutput(BaseModel):
    """Output from a single model run."""

    model_name: str
    output: str
    latency_seconds: float
    valid_json: bool
    errors: list[str] | None = None


class CompareMetrics(BaseModel):
    """Computed deltas between baseline and fine-tuned outputs."""

    latency_delta_pct: float
    validity_improved: bool
    task_specific_flag: str | None = None


class CompareRequest(BaseModel):
    """Request to compare base vs fine-tuned model on a prompt."""

    prompt: str
    task: Literal["query_parser", "explainer", "evaluator"]

    @field_validator("prompt")
    @classmethod
    def prompt_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Prompt cannot be empty")
        return v


class CompareResponse(BaseModel):
    """Side-by-side comparison of base and fine-tuned model outputs."""

    baseline: ModelOutput
    finetuned: ModelOutput
    metrics: CompareMetrics
    task: str


# --- Eval Run models ---


class EvalRunItem(BaseModel):
    """A single model evaluation run result."""

    model_name: str
    model_version: str
    base_model_name: str
    task: str
    metrics: dict[str, Any]
    ship_decision: str
    blocking_failures: list[dict] | None = None
    created_at: str | None = None


class EvalRunsResponse(BaseModel):
    """Collection of eval run results."""

    runs: list[EvalRunItem]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_compare_endpoint.py::TestCompareRequest -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/app/schemas.py tests/test_compare_endpoint.py
git commit -m "feat: add Pydantic schemas for model comparison and eval runs endpoints"
```

---

## Task 2: Add `POST /api/compare` Endpoint

**Files:**
- Modify: `src/d4bl/app/api.py`
- Test: `tests/test_compare_endpoint.py`

- [ ] **Step 1: Write failing test for compare endpoint**

Add to `tests/test_compare_endpoint.py`:

```python
import json
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient


def _override_auth(app):
    """Stub out Supabase auth for testing."""
    from d4bl.app.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-user-id",
        "email": "test@test.com",
        "role": "user",
    }
    return app


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

        async def mock_generate(*, base_url, prompt, model=None, temperature=0.1, timeout_seconds=30):
            nonlocal call_count
            call_count += 1
            if model and "d4bl" in model:
                return finetuned_output
            return baseline_output

        with patch("d4bl.app.api.ollama_generate", side_effect=mock_generate):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/compare", json={
                    "prompt": "What is the median income in Mississippi?",
                    "task": "query_parser",
                })

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
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/compare", json={
                    "prompt": "test",
                    "task": "query_parser",
                })

        assert resp.status_code == 400
        assert "not configured" in resp.json()["detail"].lower()

        test_app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_compare_endpoint.py::TestCompareEndpoint -v`
Expected: FAIL (no `/api/compare` endpoint)

- [ ] **Step 3: Implement the compare endpoint**

In `src/d4bl/app/api.py`:

1. Add to the imports at the top (add to the existing `from d4bl.app.schemas import` block):

```python
    CompareRequest,
    CompareResponse,
    CompareMetrics,
    ModelOutput,
```

2. Add new imports after the existing `from d4bl.llm import get_available_models` line:

```python
from d4bl.llm.ollama_client import model_for_task, ollama_generate
from scripts.training.validate_model_output import (
    validate_evaluator_output,
    validate_explainer_output,
    validate_parser_output,
)
```

3. Add a validator map and task-specific flag function after the imports:

```python
_COMPARE_VALIDATORS = {
    "query_parser": validate_parser_output,
    "explainer": validate_explainer_output,
    "evaluator": validate_evaluator_output,
}


def _task_specific_flag(task: str, validation_result) -> str | None:
    """Compute a human-readable task-specific flag from validated output."""
    if not validation_result.valid or not validation_result.parsed:
        return None
    parsed = validation_result.parsed
    if task == "query_parser":
        valid_intents = {"compare", "trend", "lookup", "aggregate"}
        if parsed.get("intent") in valid_intents:
            return "Intent parsed"
    elif task == "explainer":
        if "narrative" in parsed:
            return "Has structural framing"
    elif task == "evaluator":
        score = parsed.get("score")
        if isinstance(score, (int, float)):
            return "Score present"
    return None
```

4. Add the endpoint before the `@app.websocket` handler:

```python
@app.post("/api/compare", response_model=CompareResponse)
async def compare_models(
    request: CompareRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Run a prompt through base and fine-tuned models, return side-by-side comparison."""
    settings = get_settings()
    baseline_model = settings.ollama_model
    finetuned_model = model_for_task(request.task)

    if baseline_model == finetuned_model:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Fine-tuned model not configured for task '{request.task}'. "
                f"Set the {request.task.upper()}_MODEL environment variable."
            ),
        )

    base_url = settings.ollama_base_url

    # Run both models concurrently
    async def _run(model: str) -> tuple[str, float]:
        start = time.monotonic()
        output = await ollama_generate(
            base_url=base_url,
            prompt=request.prompt,
            model=model,
            temperature=0.1,
            timeout_seconds=60,
        )
        return output, round(time.monotonic() - start, 3)

    try:
        (b_output, b_latency), (f_output, f_latency) = await asyncio.gather(
            _run(baseline_model), _run(finetuned_model),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Model inference failed: {exc}")

    validator = _COMPARE_VALIDATORS[request.task]
    b_result = validator(b_output)
    f_result = validator(f_output)

    latency_delta_pct = (
        round((f_latency - b_latency) / b_latency * 100, 1)
        if b_latency > 0
        else 0.0
    )

    return CompareResponse(
        baseline=ModelOutput(
            model_name=baseline_model,
            output=b_output,
            latency_seconds=b_latency,
            valid_json=b_result.valid,
            errors=b_result.errors or None,
        ),
        finetuned=ModelOutput(
            model_name=finetuned_model,
            output=f_output,
            latency_seconds=f_latency,
            valid_json=f_result.valid,
            errors=f_result.errors or None,
        ),
        metrics=CompareMetrics(
            latency_delta_pct=latency_delta_pct,
            validity_improved=f_result.valid and not b_result.valid,
            task_specific_flag=_task_specific_flag(request.task, f_result),
        ),
        task=request.task,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_compare_endpoint.py -v`
Expected: All 5 tests PASS (3 schema + 2 endpoint)

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/app/api.py tests/test_compare_endpoint.py
git commit -m "feat: add POST /api/compare endpoint for side-by-side model comparison"
```

---

## Task 3: Add `GET /api/eval-runs` Endpoint

**Files:**
- Modify: `src/d4bl/app/api.py`
- Modify: `src/d4bl/app/schemas.py` (already done in Task 1)
- Test: `tests/test_eval_runs_endpoint.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_eval_runs_endpoint.py`:

```python
"""Tests for the /api/eval-runs endpoint."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from d4bl.app.schemas import EvalRunsResponse


def _override_auth(app):
    from d4bl.app.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-user-id",
        "email": "test@test.com",
        "role": "user",
    }
    return app


class TestEvalRunsEndpoint:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_runs(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        from d4bl.app.api import app

        test_app = _override_auth(app)

        # Mock the DB session to return no rows
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def mock_get_db():
            yield mock_session

        from d4bl.infra.database import get_db

        test_app.dependency_overrides[get_db] = mock_get_db

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/eval-runs")

        assert resp.status_code == 200
        data = resp.json()
        assert data["runs"] == []

        test_app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_returns_runs_grouped(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        from d4bl.app.api import app

        test_app = _override_auth(app)

        mock_row = MagicMock()
        mock_row.to_dict.return_value = {
            "id": "abc",
            "model_name": "d4bl-query-parser",
            "model_version": "v1.0",
            "base_model_name": "mistral",
            "task": "query_parser",
            "test_set_hash": "deadbeef",
            "metrics": {"json_valid_rate": 0.97},
            "ship_decision": "ship",
            "blocking_failures": None,
            "created_at": "2026-03-27T00:00:00",
        }

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_row]
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def mock_get_db():
            yield mock_session

        from d4bl.infra.database import get_db

        test_app.dependency_overrides[get_db] = mock_get_db

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/eval-runs")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["runs"]) == 1
        assert data["runs"][0]["model_name"] == "d4bl-query-parser"
        assert data["runs"][0]["ship_decision"] == "ship"

        test_app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_eval_runs_endpoint.py -v`
Expected: FAIL (no `/api/eval-runs` endpoint, returns 404)

- [ ] **Step 3: Implement the endpoint**

In `src/d4bl/app/api.py`:

1. Add to the `from d4bl.app.schemas import` block:

```python
    EvalRunItem,
    EvalRunsResponse,
```

2. Add to the `from d4bl.infra.database import` block:

```python
    ModelEvalRun,
```

3. Add the endpoint (near the existing `/api/evaluations` endpoint):

```python
@app.get("/api/eval-runs", response_model=EvalRunsResponse)
async def get_eval_runs(
    task: str | None = None,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return latest model evaluation runs for the eval metrics dashboard."""
    # Get the most recent run per (model_name, task) combination
    query = (
        select(ModelEvalRun)
        .order_by(desc(ModelEvalRun.created_at))
        .limit(20)
    )
    if task:
        query = query.where(ModelEvalRun.task == task)

    result = await db.execute(query)
    rows = result.scalars().all()

    # Deduplicate: keep only the latest per (model_name, task)
    seen: set[tuple[str, str]] = set()
    unique_runs: list[EvalRunItem] = []
    for row in rows:
        key = (row.model_name, row.task)
        if key not in seen:
            seen.add(key)
            d = row.to_dict()
            unique_runs.append(EvalRunItem(
                model_name=d["model_name"],
                model_version=d["model_version"],
                base_model_name=d["base_model_name"],
                task=d["task"],
                metrics=d["metrics"],
                ship_decision=d["ship_decision"],
                blocking_failures=d.get("blocking_failures"),
                created_at=str(d.get("created_at", "")),
            ))

    return EvalRunsResponse(runs=unique_runs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_eval_runs_endpoint.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Run full backend tests to check for regressions**

Run: `pytest tests/ -v --ignore=tests/test_training/test_integration_models.py -x -q`
Expected: All tests PASS (no regressions)

- [ ] **Step 6: Commit**

```bash
git add src/d4bl/app/api.py tests/test_eval_runs_endpoint.py
git commit -m "feat: add GET /api/eval-runs endpoint for eval metrics dashboard"
```

---

## Task 4: Add `--model` Flag to Eval Harness CLI

**Files:**
- Modify: `scripts/training/run_eval_harness.py`
- Test: `tests/test_eval_harness_model_flag.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_eval_harness_model_flag.py`:

```python
"""Tests for the --model flag in run_eval_harness.py."""
from __future__ import annotations

import argparse

import pytest


class TestModelFlag:
    def test_model_flag_overrides_task_model(self):
        """When --model is provided, it should be used instead of TASK_MODELS[task]."""
        from scripts.training.run_eval_harness import resolve_model_name, TASK_MODELS

        # Without --model: uses default
        assert resolve_model_name(None, "query_parser") == TASK_MODELS["query_parser"]

        # With --model: uses override
        assert resolve_model_name("mistral", "query_parser") == "mistral"
        assert resolve_model_name("custom-model", "explainer") == "custom-model"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_eval_harness_model_flag.py -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_model_name'`

- [ ] **Step 3: Add resolve_model_name function and --model CLI arg**

In `scripts/training/run_eval_harness.py`:

1. Add after the `TASK_MODELS` dict:

```python
def resolve_model_name(model_override: str | None, task: str) -> str:
    """Resolve inference model: --model override takes precedence over TASK_MODELS."""
    if model_override:
        return model_override
    return TASK_MODELS[task]
```

2. In `cli()`, add the `--model` argument after `--baseline`:

```python
    parser.add_argument(
        "--model",
        help="Override inference model (default: use task-specific fine-tuned model)",
    )
```

3. In `main()`, replace `TASK_MODELS[task]` with `resolve_model_name()`. Change the two lines that reference it:

Replace:

```python
        logger.info(
            "Running %s eval: %d examples, model=%s",
            task, len(test_set), TASK_MODELS[task],
        )

        result = await run_task_eval(
            task=task,
            test_set=test_set,
            model_name=TASK_MODELS[task],
```

With:

```python
        model_name = resolve_model_name(args.model, task)
        logger.info(
            "Running %s eval: %d examples, model=%s",
            task, len(test_set), model_name,
        )

        result = await run_task_eval(
            task=task,
            test_set=test_set,
            model_name=model_name,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_eval_harness_model_flag.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/training/run_eval_harness.py tests/test_eval_harness_model_flag.py
git commit -m "feat: add --model flag to eval harness for baseline metric collection"
```

---

## Task 5: Add Frontend API Client Functions

**Files:**
- Modify: `ui-nextjs/lib/api.ts`

- [ ] **Step 1: Add TypeScript interfaces and functions**

Add at the end of `ui-nextjs/lib/api.ts`:

```typescript
// --- Model Comparison types ---

export interface ModelOutput {
  model_name: string;
  output: string;
  latency_seconds: number;
  valid_json: boolean;
  errors: string[] | null;
}

export interface CompareMetrics {
  latency_delta_pct: number;
  validity_improved: boolean;
  task_specific_flag: string | null;
}

export interface CompareResponse {
  baseline: ModelOutput;
  finetuned: ModelOutput;
  metrics: CompareMetrics;
  task: string;
}

export interface EvalRunItem {
  model_name: string;
  model_version: string;
  base_model_name: string;
  task: string;
  metrics: Record<string, number | null>;
  ship_decision: string;
  blocking_failures: Record<string, unknown>[] | null;
  created_at: string | null;
}

export interface EvalRunsResponse {
  runs: EvalRunItem[];
}

export async function compareModels(prompt: string, task: string): Promise<CompareResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE}/api/compare`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ prompt, task }),
  });

  handle401(response);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Model comparison failed');
  }

  return response.json();
}

export async function getEvalRuns(task?: string): Promise<EvalRunsResponse> {
  const params = task ? `?task=${encodeURIComponent(task)}` : '';
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE}/api/eval-runs${params}`, { headers });

  handle401(response);

  if (!response.ok) {
    throw new Error('Failed to fetch evaluation runs');
  }

  return response.json();
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd ui-nextjs && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors related to api.ts

- [ ] **Step 3: Commit**

```bash
git add ui-nextjs/lib/api.ts
git commit -m "feat: add compareModels() and getEvalRuns() API client functions"
```

---

## Task 6: Build ModelComparisonPlayground Component

**Files:**
- Create: `ui-nextjs/components/learn/ModelComparisonPlayground.tsx`

- [ ] **Step 1: Create the component**

Create `ui-nextjs/components/learn/ModelComparisonPlayground.tsx`:

```tsx
'use client';

import { useState } from 'react';
import { compareModels, CompareResponse } from '@/lib/api';

type Task = 'query_parser' | 'explainer' | 'evaluator';

const TASK_LABELS: Record<Task, string> = {
  query_parser: 'Query Parser',
  explainer: 'Explainer',
  evaluator: 'Evaluator',
};

const PLACEHOLDER_PROMPTS: Record<Task, string> = {
  query_parser: 'What is the median household income for Black families in Mississippi?',
  explainer:
    'Data source: census\nMetric: median_household_income\nState: Mississippi (FIPS 28)\nValue: 45081\nNational average: 69021\nYear: 2022\nRacial breakdown: white: 55602, black: 32815, hispanic: 42189',
  evaluator:
    'Evaluate for equity framing: "The median household income in Mississippi is $45,081, below the national average."',
};

function OutputPanel({
  label,
  modelName,
  output,
  latency,
  validJson,
  errors,
  isFineTuned,
}: {
  label: string;
  modelName: string;
  output: string;
  latency: number;
  validJson: boolean;
  errors: string[] | null;
  isFineTuned: boolean;
}) {
  const borderClass = isFineTuned ? 'border-[#00ff32]/30' : 'border-[#404040]';
  const labelColor = isFineTuned ? 'text-[#00ff32]' : 'text-gray-400';
  const badgeBg = isFineTuned ? 'bg-[#1f3524]' : 'bg-[#333]';
  const badgeText = isFineTuned ? 'text-[#4ade80]' : 'text-gray-400';

  return (
    <div className={`flex-1 min-w-0 bg-[#292929] border ${borderClass} rounded-lg p-4`}>
      <div className="flex justify-between items-center mb-3">
        <span className={`text-xs uppercase tracking-widest ${labelColor}`}>{label}</span>
        <span className={`${badgeBg} ${badgeText} px-2 py-0.5 rounded text-[10px]`}>
          {modelName}
        </span>
      </div>
      <div className="bg-[#1a1a1a] rounded-md p-3 min-h-[120px] max-h-[300px] overflow-auto">
        <pre className="text-xs text-gray-300 whitespace-pre-wrap break-words font-mono leading-relaxed">
          {output}
        </pre>
      </div>
      <div className="flex gap-1.5 mt-2 flex-wrap">
        <span
          className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
            validJson ? 'bg-[#1f3524] text-[#4ade80]' : 'bg-[#402424] text-[#f87171]'
          }`}
        >
          {validJson ? 'Valid JSON' : 'Invalid JSON'}
        </span>
        <span className="bg-[#333] text-gray-400 px-2 py-0.5 rounded text-[10px]">
          {latency.toFixed(2)}s
        </span>
        {errors?.map((e, i) => (
          <span key={i} className="bg-[#402424] text-[#f87171] px-2 py-0.5 rounded text-[10px]">
            {e}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function ModelComparisonPlayground() {
  const [task, setTask] = useState<Task>('query_parser');
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleCompare = async () => {
    const queryText = prompt.trim() || PLACEHOLDER_PROMPTS[task];
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await compareModels(queryText, task);
      setResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Comparison failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Query input */}
      <div className="flex gap-2">
        <input
          type="text"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder={PLACEHOLDER_PROMPTS[task]}
          className="flex-1 bg-[#292929] border border-[#404040] rounded-lg px-4 py-2.5 text-sm text-gray-200 placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-[#00ff32]/50"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !loading) handleCompare();
          }}
        />
        <button
          onClick={handleCompare}
          disabled={loading}
          className="bg-[#00ff32] hover:bg-[#00cc28] disabled:opacity-50 disabled:cursor-not-allowed text-black font-semibold px-5 py-2.5 rounded-lg text-sm transition-colors whitespace-nowrap"
        >
          {loading ? 'Running...' : 'Compare Models'}
        </button>
      </div>

      {/* Task selector */}
      <div className="flex gap-1.5">
        {(Object.keys(TASK_LABELS) as Task[]).map((t) => (
          <button
            key={t}
            onClick={() => {
              setTask(t);
              setResult(null);
            }}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              task === t
                ? 'bg-[#00ff32] text-black'
                : 'bg-[#333] text-gray-400 hover:text-white'
            }`}
          >
            {TASK_LABELS[t]}
          </button>
        ))}
      </div>

      {/* Error state */}
      {error && (
        <div className="bg-[#2a1a1a] border border-[#803a3a] text-red-200 rounded-lg px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="space-y-4">
          <div className="bg-[#292929] rounded-lg h-12 animate-pulse" />
          <div className="flex gap-3">
            <div className="flex-1 bg-[#292929] rounded-lg h-48 animate-pulse" />
            <div className="flex-1 bg-[#292929] rounded-lg h-48 animate-pulse" />
          </div>
        </div>
      )}

      {/* Results */}
      {result && (
        <>
          {/* Summary delta bar */}
          <div className="flex bg-[#292929] rounded-lg overflow-hidden divide-x divide-[#404040]">
            <div className="flex-1 text-center py-2.5 px-2">
              <div className="text-[9px] text-gray-500 uppercase tracking-widest mb-0.5">
                Valid JSON
              </div>
              <div className="text-sm font-bold">
                <span className={result.baseline.valid_json ? 'text-[#4ade80]' : 'text-[#f87171]'}>
                  {result.baseline.valid_json ? 'Yes' : 'No'}
                </span>
                <span className="text-gray-600 mx-1">&rarr;</span>
                <span className={result.finetuned.valid_json ? 'text-[#4ade80]' : 'text-[#f87171]'}>
                  {result.finetuned.valid_json ? 'Yes' : 'No'}
                </span>
              </div>
            </div>
            <div className="flex-1 text-center py-2.5 px-2">
              <div className="text-[9px] text-gray-500 uppercase tracking-widest mb-0.5">
                Latency
              </div>
              <div
                className={`text-sm font-bold ${
                  result.metrics.latency_delta_pct < 0 ? 'text-[#4ade80]' : 'text-[#f87171]'
                }`}
              >
                {result.metrics.latency_delta_pct > 0 ? '+' : ''}
                {result.metrics.latency_delta_pct.toFixed(0)}%
              </div>
              <div className="text-[10px] text-gray-600">
                {result.baseline.latency_seconds.toFixed(1)}s &rarr;{' '}
                {result.finetuned.latency_seconds.toFixed(1)}s
              </div>
            </div>
            {result.metrics.task_specific_flag && (
              <div className="flex-1 text-center py-2.5 px-2">
                <div className="text-[9px] text-gray-500 uppercase tracking-widest mb-0.5">
                  Quality
                </div>
                <div className="text-sm font-bold text-[#4ade80]">
                  {result.metrics.task_specific_flag}
                </div>
              </div>
            )}
          </div>

          {/* Side-by-side panels */}
          <div className="flex flex-col sm:flex-row gap-3">
            <OutputPanel
              label="Base Model"
              modelName={result.baseline.model_name}
              output={result.baseline.output}
              latency={result.baseline.latency_seconds}
              validJson={result.baseline.valid_json}
              errors={result.baseline.errors}
              isFineTuned={false}
            />
            <OutputPanel
              label="Fine-Tuned"
              modelName={result.finetuned.model_name}
              output={result.finetuned.output}
              latency={result.finetuned.latency_seconds}
              validJson={result.finetuned.valid_json}
              errors={result.finetuned.errors}
              isFineTuned={true}
            />
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify component compiles**

Run: `cd ui-nextjs && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add ui-nextjs/components/learn/ModelComparisonPlayground.tsx
git commit -m "feat: add ModelComparisonPlayground component with side-by-side comparison"
```

---

## Task 7: Build EvalMetricsPanel Component

**Files:**
- Create: `ui-nextjs/components/learn/EvalMetricsPanel.tsx`

- [ ] **Step 1: Create the component**

Create `ui-nextjs/components/learn/EvalMetricsPanel.tsx`:

```tsx
'use client';

import { useEffect, useState } from 'react';
import { EvalRunItem, getEvalRuns } from '@/lib/api';

const TASK_LABELS: Record<string, string> = {
  query_parser: 'Query Parser',
  explainer: 'Explainer',
  evaluator: 'Evaluator',
};

const SHIP_BADGES: Record<string, { bg: string; text: string; label: string }> = {
  ship: { bg: 'bg-[#1f3524]', text: 'text-[#4ade80]', label: 'Ship' },
  no_ship: { bg: 'bg-[#402424]', text: 'text-[#f87171]', label: 'No Ship' },
  ship_with_gaps: { bg: 'bg-[#3d3520]', text: 'text-[#fbbf24]', label: 'Ship with Gaps' },
};

/** Metrics where lower is better (latency, MAE). */
const LOWER_IS_BETTER = new Set(['p50_latency_ms', 'p95_latency_ms', 'relevance_mae', 'bias_mae']);

function MetricRow({ name, value }: { name: string; value: number | null }) {
  if (value === null) {
    return (
      <div className="flex justify-between py-1">
        <span className="text-xs text-gray-500">{name}</span>
        <span className="text-xs text-gray-600 italic">deferred</span>
      </div>
    );
  }

  const isPercent = !LOWER_IS_BETTER.has(name) && value <= 1.0;
  const displayValue = isPercent ? `${(value * 100).toFixed(1)}%` : value.toFixed(2);

  return (
    <div className="flex justify-between py-1">
      <span className="text-xs text-gray-400">{name}</span>
      <span className="text-xs text-gray-200 font-mono">{displayValue}</span>
    </div>
  );
}

function TaskCard({ runs }: { runs: EvalRunItem[] }) {
  const task = runs[0]?.task ?? 'unknown';
  const label = TASK_LABELS[task] ?? task;

  return (
    <div className="bg-[#292929] border border-[#404040] rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold text-white">{label}</h4>
        <div className="flex gap-1.5">
          {runs.map((r) => {
            const badge = SHIP_BADGES[r.ship_decision] ?? SHIP_BADGES.no_ship;
            return (
              <span
                key={r.model_name}
                className={`${badge.bg} ${badge.text} px-2 py-0.5 rounded text-[10px] font-semibold`}
              >
                {r.model_name}: {badge.label}
              </span>
            );
          })}
        </div>
      </div>

      {runs.map((r) => (
        <div key={r.model_name} className="mb-3 last:mb-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] text-gray-500 uppercase tracking-wider">
              {r.model_name}
            </span>
            <span className="text-[10px] text-gray-600">{r.model_version}</span>
          </div>
          <div className="bg-[#1a1a1a] rounded-md p-3 divide-y divide-[#333]">
            {Object.entries(r.metrics).map(([name, value]) => (
              <MetricRow key={name} name={name} value={value} />
            ))}
          </div>
          {r.blocking_failures && r.blocking_failures.length > 0 && (
            <div className="mt-2">
              {r.blocking_failures.map((f, i) => (
                <div
                  key={i}
                  className="text-[10px] text-[#f87171] bg-[#402424] rounded px-2 py-1 mb-1"
                >
                  {(f as Record<string, unknown>).metric as string}:{' '}
                  {String((f as Record<string, unknown>).actual ?? 'missing')} (need{' '}
                  {(f as Record<string, unknown>).direction === 'min' ? '>=' : '<='}{' '}
                  {String((f as Record<string, unknown>).threshold)})
                </div>
              ))}
            </div>
          )}
        </div>
      ))}

      {runs[0]?.created_at && (
        <div className="text-[10px] text-gray-600 mt-2">
          Last run: {new Date(runs[0].created_at).toLocaleDateString()}
        </div>
      )}
    </div>
  );
}

export default function EvalMetricsPanel() {
  const [runs, setRuns] = useState<EvalRunItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await getEvalRuns();
        if (!cancelled) setRuns(data.runs);
      } catch (err: unknown) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-[#292929] rounded-lg h-48 animate-pulse" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-[#2a1a1a] border border-[#803a3a] text-red-200 rounded-lg px-4 py-3 text-sm">
        {error}
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="bg-[#292929] border border-[#404040] rounded-lg p-6 text-center">
        <p className="text-gray-400 text-sm mb-2">No evaluation data yet.</p>
        <p className="text-gray-600 text-xs font-mono">
          python -m scripts.training.run_eval_harness --persist
        </p>
      </div>
    );
  }

  // Group by task
  const byTask: Record<string, EvalRunItem[]> = {};
  for (const run of runs) {
    if (!byTask[run.task]) byTask[run.task] = [];
    byTask[run.task].push(run);
  }

  return (
    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {Object.entries(byTask).map(([task, taskRuns]) => (
        <TaskCard key={task} runs={taskRuns} />
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Verify component compiles**

Run: `cd ui-nextjs && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add ui-nextjs/components/learn/EvalMetricsPanel.tsx
git commit -m "feat: add EvalMetricsPanel component for pre-computed eval results"
```

---

## Task 8: Wire Components into /learn Page

**Files:**
- Modify: `ui-nextjs/app/learn/page.tsx`

- [ ] **Step 1: Update imports**

In `ui-nextjs/app/learn/page.tsx`, replace the `PlaygroundPlaceholder` import:

```tsx
// Remove this line:
import PlaygroundPlaceholder from '@/components/learn/PlaygroundPlaceholder';

// Add these lines:
import EvalMetricsPanel from '@/components/learn/EvalMetricsPanel';
import ModelComparisonPlayground from '@/components/learn/ModelComparisonPlayground';
```

- [ ] **Step 2: Add EvalMetricsPanel section**

Before the `{/* Section: What's Next */}` comment (around line 203), add:

```tsx
      {/* Section: How It Performs */}
      <ConceptSection
        title="How It Performs"
        subtitle="Eval harness results comparing base and fine-tuned models"
      >
        <p className="mb-6">
          We run each model through a standardized test set and measure JSON
          validity, entity extraction, equity framing, and latency. These are
          the latest results from our evaluation harness.
        </p>
        <EvalMetricsPanel />
      </ConceptSection>
```

- [ ] **Step 3: Replace PlaygroundPlaceholder**

In the "What's Next" section, update the title/subtitle and swap the component:

Replace:

```tsx
      <ConceptSection
        title="What's Next"
        subtitle="The playground is coming"
      >
        <p className="mb-6">
          We&apos;re building an interactive playground where you can query the D4BL
          model directly, compare outputs across registers, and export results
          for your own analysis.
        </p>
        <PlaygroundPlaceholder />
      </ConceptSection>
```

With:

```tsx
      <ConceptSection
        title="Compare Models Live"
        subtitle="Run any prompt through both models and see the difference"
      >
        <p className="mb-6">
          Type a query below to see how the fine-tuned D4BL model compares to
          the base model. Select a task type to test different adapters.
        </p>
        <ModelComparisonPlayground />
      </ConceptSection>
```

- [ ] **Step 4: Verify build**

Run: `cd ui-nextjs && npm run build 2>&1 | tail -10`
Expected: Build succeeds

- [ ] **Step 5: Run lint**

Run: `cd ui-nextjs && npm run lint 2>&1 | tail -10`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add ui-nextjs/app/learn/page.tsx
git commit -m "feat: wire ModelComparisonPlayground and EvalMetricsPanel into /learn page"
```

---

## Task 9: Full Test Suite Verification

- [ ] **Step 1: Run backend tests**

Run: `pytest tests/ -v --ignore=tests/test_training/test_integration_models.py -x -q`
Expected: All tests PASS, no regressions

- [ ] **Step 2: Run frontend build and lint**

Run: `cd ui-nextjs && npm run build && npm run lint`
Expected: Clean build, no lint errors

- [ ] **Step 3: Final commit if any fixups needed**

```bash
git add -A
git commit -m "fix: address test suite issues from playground integration"
```
