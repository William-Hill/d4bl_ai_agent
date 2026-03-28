# Post-Experiment Analysis + /learn Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `/learn` into a tabbed layout with hot-swappable model comparison, and add a post-experiment analysis engine that generates actionable training suggestions after eval runs.

**Architecture:** Split `/learn` into Compare/Learn/Build tabs via a client-side `LearnTabs` component. Update `POST /api/compare` to accept explicit model names per pipeline side. Add `suggestions.py` with rules-based suggestion generation keyed to `SHIP_CRITERIA`. Add `suggestions` JSONB column to `model_eval_runs`. Optional LLM-powered analysis via `--analyze` flag and `POST /api/eval-runs/{id}/analyze`.

**Tech Stack:** Python (FastAPI, SQLAlchemy, asyncio), TypeScript (Next.js, React 19, Tailwind CSS 4)

**Spec:** `docs/superpowers/specs/2026-03-27-post-experiment-analysis-learn-redesign.md`

**Dependencies:** PR #134 (end-to-end pipeline comparison — must be merged first)

**Deferred:** LLM-powered analysis (`--analyze` flag, `--analyze-existing` CLI mode, and "Analyze Failures" UI button) is defined in the spec but deferred to a follow-on plan. This plan implements the rules-based suggestion engine, storage, and UI display. The LLM analysis endpoint (`POST /api/eval-runs/{id}/analyze`) is included as a stub that runs rules-based suggestions only — the Claude API integration can be added later without schema changes.

---

## File Structure

```
Modified:
  src/d4bl/infra/database.py                              — add suggestions column to ModelEvalRun + to_dict()
  src/d4bl/app/schemas.py                                  — update CompareRequest, EvalRunItem; add SuggestionItem
  src/d4bl/app/api.py                                      — update /api/compare to accept model names, add /api/eval-runs/{id}/analyze
  src/d4bl/llm/provider.py                                 — extend get_available_models() with type/version
  scripts/training/run_eval_harness.py                     — integrate suggestions, add --analyze/--analyze-existing
  ui-nextjs/app/learn/page.tsx                             — restructure into tabbed layout
  ui-nextjs/components/learn/ModelComparisonPlayground.tsx  — add model selector dropdowns
  ui-nextjs/lib/api.ts                                     — update types, add analyzeFailures()

Created:
  scripts/training/suggestions.py                          — rules-based + LLM suggestion engine
  ui-nextjs/components/learn/LearnTabs.tsx                  — tab navigation with hash sync
  ui-nextjs/components/learn/SuggestionsPanel.tsx           — suggested improvements display
  ui-nextjs/components/learn/BuildTab.tsx                   — tutorials + slide deck
  supabase/migrations/20260327000001_add_suggestions_to_eval_runs.sql
  tests/test_suggestions.py                                — suggestion generation tests
```

---

## Task 1: Add `suggestions` Column to `model_eval_runs`

**Files:**
- Modify: `src/d4bl/infra/database.py`
- Modify: `src/d4bl/app/schemas.py`
- Create: `supabase/migrations/20260327000001_add_suggestions_to_eval_runs.sql`

- [ ] **Step 1: Write the migration**

Create `supabase/migrations/20260327000001_add_suggestions_to_eval_runs.sql`:

```sql
ALTER TABLE model_eval_runs ADD COLUMN IF NOT EXISTS suggestions JSONB;
```

- [ ] **Step 2: Add column to SQLAlchemy model**

In `src/d4bl/infra/database.py`, add after line 124 (`blocking_failures` column):

```python
    suggestions = Column(JSONB, nullable=True)
```

- [ ] **Step 3: Update to_dict()**

In `src/d4bl/infra/database.py`, add to the `to_dict()` return dict (after `"blocking_failures"`):

```python
            "suggestions": self.suggestions,
```

- [ ] **Step 4: Update EvalRunItem schema**

In `src/d4bl/app/schemas.py`, add to `EvalRunItem` (after `blocking_failures`):

```python
    suggestions: dict | None = None
```

- [ ] **Step 5: Run tests**

Run: `QUERY_PARSER_MODEL= EXPLAINER_MODEL= EVALUATOR_MODEL= POSTGRES_HOST=localhost POSTGRES_PORT=54322 POSTGRES_PASSWORD=postgres pytest tests/test_eval_runs_endpoint.py tests/test_settings.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/d4bl/infra/database.py src/d4bl/app/schemas.py supabase/migrations/
git commit -m "feat: add suggestions JSONB column to model_eval_runs"
```

---

## Task 2: Build Rules-Based Suggestion Engine

**Files:**
- Create: `scripts/training/suggestions.py`
- Create: `tests/test_suggestions.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_suggestions.py`:

```python
"""Tests for post-experiment suggestion generation."""
from __future__ import annotations

import pytest

from scripts.training.suggestions import generate_suggestions, SuggestionItem


class TestGenerateSuggestions:
    def test_blocking_failure_generates_suggestion(self):
        metrics = {"json_valid_rate": 0.90, "entity_f1": 0.85}
        result = generate_suggestions(metrics, "query_parser")
        assert len(result) >= 1
        json_suggestion = next(s for s in result if s.metric == "json_valid_rate")
        assert json_suggestion.severity == "blocking"
        assert json_suggestion.current == 0.90
        assert json_suggestion.target == 0.95

    def test_passing_metrics_no_suggestions(self):
        metrics = {
            "json_valid_rate": 0.99,
            "entity_f1": 0.90,
            "data_source_accuracy": 0.90,
            "community_framing_f1": 0.80,
            "p95_latency_ms": 500,
            "adversarial_pass_rate": 0.90,
        }
        result = generate_suggestions(metrics, "query_parser")
        assert len(result) == 0

    def test_nonblocking_failure(self):
        metrics = {"community_framing_f1": 0.60}
        result = generate_suggestions(metrics, "query_parser")
        framing = next(s for s in result if s.metric == "community_framing_f1")
        assert framing.severity == "non-blocking"

    def test_unknown_task_returns_empty(self):
        result = generate_suggestions({"foo": 1.0}, "unknown_task")
        assert result == []

    def test_missing_metric_skipped(self):
        """Metrics not present in the eval run should not generate suggestions."""
        metrics = {"json_valid_rate": 0.99}
        result = generate_suggestions(metrics, "query_parser")
        assert all(s.metric == "json_valid_rate" for s in result) or len(result) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_suggestions.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement suggestions.py**

Create `scripts/training/suggestions.py`:

```python
"""Post-experiment suggestion engine.

Generates actionable training data recommendations based on eval metrics.
Rules-based (always runs) + optional LLM-powered analysis.
"""
from __future__ import annotations

from dataclasses import dataclass

from scripts.training.ship_criteria import SHIP_CRITERIA

# Maps (task, metric) to a human-readable suggestion.
_SUGGESTION_TEXT: dict[tuple[str, str], str] = {
    ("query_parser", "json_valid_rate"): "Add adversarial examples with malformed input to improve JSON compliance",
    ("query_parser", "entity_f1"): "Add training pairs with more diverse entity types (organizations, policies, geographies)",
    ("query_parser", "data_source_accuracy"): "Add examples that clarify when to use vector vs structured search",
    ("query_parser", "community_framing_f1"): "Add community-voiced query examples with advocacy framing",
    ("query_parser", "p95_latency_ms"): "Consider increasing quantization level or reducing context window",
    ("query_parser", "adversarial_pass_rate"): "Add more adversarial prompts with harmful framings that should be reframed",
    ("explainer", "json_valid_rate"): "Add examples with complex nested JSON output structure",
    ("explainer", "factual_accuracy"): "Verify training data accuracy — check for stale statistics in distillation corpus",
    ("explainer", "d4bl_composite"): "Increase proportion of D4BL methodology-aligned training examples",
    ("explainer", "register_consistency"): "Add single-register examples with clear style separation between community/policy/research",
    ("explainer", "p95_latency_ms"): "Consider increasing quantization level or reducing context window",
    ("evaluator", "hallucination_accuracy"): "Add more hallucination detection examples with subtle factual errors",
    ("evaluator", "relevance_mae"): "Add relevance scoring examples with borderline cases (partially relevant)",
    ("evaluator", "bias_mae"): "Add bias detection examples covering structural bias, not just explicit bias",
    ("evaluator", "relevance_correlation"): "Add more diverse relevance scoring examples across different query types",
}


@dataclass
class SuggestionItem:
    metric: str
    severity: str  # "blocking" or "non-blocking"
    current: float
    target: float
    suggestion: str
    category: str = "training_data"


def generate_suggestions(
    metrics: dict[str, float | None],
    task: str,
) -> list[SuggestionItem]:
    """Generate rules-based suggestions from eval metrics.

    Compares each metric against SHIP_CRITERIA thresholds and returns
    actionable suggestions for any that fail.
    """
    criteria = SHIP_CRITERIA.get(task)
    if not criteria:
        return []

    suggestions: list[SuggestionItem] = []
    for metric_name, spec in criteria.items():
        actual = metrics.get(metric_name)
        if actual is None:
            continue

        blocking = spec["blocking"]
        failed = False
        if "min" in spec and actual < spec["min"]:
            failed = True
            target = spec["min"]
        elif "max" in spec and actual > spec["max"]:
            failed = True
            target = spec["max"]

        if failed:
            text = _SUGGESTION_TEXT.get(
                (task, metric_name),
                f"Improve {metric_name} — currently {actual}, target {target}",
            )
            suggestions.append(SuggestionItem(
                metric=metric_name,
                severity="blocking" if blocking else "non-blocking",
                current=actual,
                target=target,
                suggestion=text,
            ))

    # Sort: blocking first, then by how far from target
    suggestions.sort(key=lambda s: (s.severity != "blocking", abs(s.current - s.target)))
    return suggestions


def format_suggestions_json(suggestions: list[SuggestionItem]) -> dict:
    """Format suggestions for JSONB storage in model_eval_runs."""
    from datetime import datetime, timezone

    return {
        "rules": [
            {
                "metric": s.metric,
                "severity": s.severity,
                "current": s.current,
                "target": s.target,
                "suggestion": s.suggestion,
                "category": s.category,
            }
            for s in suggestions
        ],
        "llm_analysis": None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_suggestions.py -v`
Expected: All 5 PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/training/suggestions.py tests/test_suggestions.py
git commit -m "feat: add rules-based suggestion engine for post-experiment analysis"
```

---

## Task 3: Integrate Suggestions into Eval Harness CLI

**Files:**
- Modify: `scripts/training/run_eval_harness.py`

- [ ] **Step 1: Import and call generate_suggestions after metrics**

In `scripts/training/run_eval_harness.py`, add import after existing imports:

```python
from scripts.training.suggestions import (
    format_suggestions_json,
    generate_suggestions,
)
```

- [ ] **Step 2: Generate suggestions in run_task_eval()**

After `ship_decision = check_ship_criteria(checkable, task, partial=partial)` (around line 146), add:

```python
    suggestions = generate_suggestions(checkable, task)
    suggestions_json = format_suggestions_json(suggestions) if suggestions else None
```

- [ ] **Step 3: Add suggestions to EvalRunResult**

Add `suggestions: dict | None = None` field to the `EvalRunResult` dataclass. Then pass `suggestions=suggestions_json` in the return.

- [ ] **Step 4: Print suggestions in format_eval_report()**

After the existing ship decision output in `format_eval_report()`, add:

```python
        if r.suggestions and r.suggestions.get("rules"):
            lines.append("   SUGGESTED IMPROVEMENTS:")
            for s in r.suggestions["rules"]:
                icon = "!!" if s["severity"] == "blocking" else "  "
                lines.append(
                    f"     {icon} {s['metric']}: {s['current']} "
                    f"(target {s['target']}) — {s['suggestion']}"
                )
            lines.append("")
```

- [ ] **Step 5: Persist suggestions in persist_results()**

In `persist_results()`, add `suggestions=r.suggestions` to the `ModelEvalRun()` constructor.

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_suggestions.py tests/test_training/test_run_eval_harness.py tests/test_training/test_ship_criteria.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add scripts/training/run_eval_harness.py
git commit -m "feat: integrate suggestion generation into eval harness CLI"
```

---

## Task 4: Extend `GET /api/models` with Type and Version

**Files:**
- Modify: `src/d4bl/llm/provider.py`
- Modify: `tests/test_api_models.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_api_models.py`:

```python
@patch("d4bl.llm.provider.get_settings")
def test_available_models_include_type_and_version(mock_settings):
    from d4bl.llm.provider import get_available_models
    mock_settings.return_value.llm_provider = "ollama"
    mock_settings.return_value.llm_model = "mistral"
    mock_settings.return_value.query_parser_model = "d4bl-query-parser"
    mock_settings.return_value.explainer_model = "d4bl-explainer"
    mock_settings.return_value.evaluator_model = ""

    models = get_available_models()
    base = next(m for m in models if m["model"] == "mistral")
    assert base["type"] == "base"
    assert base["version"] is None

    parser = next(m for m in models if m["model"] == "d4bl-query-parser")
    assert parser["type"] == "finetuned"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_models.py -v`
Expected: FAIL with `KeyError: 'type'`

- [ ] **Step 3: Update get_available_models()**

In `src/d4bl/llm/provider.py`, update the `models` list construction to include `"type"` and `"version"` fields:

For the default model:
```python
            "type": "base",
            "version": None,
```

For task-specific models:
```python
                "type": "finetuned",
                "version": None,  # Set via MODEL_VERSION env vars if needed
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_api_models.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/llm/provider.py tests/test_api_models.py
git commit -m "feat: add type and version fields to /api/models response"
```

---

## Task 5: Update `POST /api/compare` to Accept Explicit Model Names

**Files:**
- Modify: `src/d4bl/app/schemas.py`
- Modify: `src/d4bl/app/api.py`
- Modify: `tests/test_compare_endpoint.py`

- [ ] **Step 1: Update CompareRequest schema**

In `src/d4bl/app/schemas.py`, replace the `CompareRequest` class:

```python
class CompareRequest(BaseModel):
    """Request to compare two model pipelines end-to-end."""

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

All model fields are optional — when `None`, the endpoint falls back to the current behavior (base model for A, fine-tuned for B).

- [ ] **Step 2: Update compare endpoint**

In `src/d4bl/app/api.py`, update `compare_models_endpoint()` to read model names from the request with fallbacks:

```python
    base_model = settings.ollama_model
    parser_ft = model_for_task("query_parser")
    explainer_ft = model_for_task("explainer")

    a_parser = request.pipeline_a_parser or base_model
    a_explainer = request.pipeline_a_explainer or base_model
    b_parser = request.pipeline_b_parser or parser_ft
    b_explainer = request.pipeline_b_explainer or explainer_ft
```

Then pass these to `_run_pipeline()` instead of hardcoded values. Remove the `if base_model == parser_model` check since the user now explicitly chooses models.

- [ ] **Step 3: Update tests**

Update `tests/test_compare_endpoint.py` to pass model names in the request body and verify they're used.

- [ ] **Step 4: Run tests**

Run: `QUERY_PARSER_MODEL= EXPLAINER_MODEL= EVALUATOR_MODEL= POSTGRES_HOST=localhost POSTGRES_PORT=54322 POSTGRES_PASSWORD=postgres pytest tests/test_compare_endpoint.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/app/schemas.py src/d4bl/app/api.py tests/test_compare_endpoint.py
git commit -m "feat: accept explicit model names in POST /api/compare"
```

---

## Task 6: Add `POST /api/eval-runs/{id}/analyze` Endpoint

**Files:**
- Modify: `src/d4bl/app/api.py`
- Modify: `src/d4bl/app/schemas.py`

- [ ] **Step 1: Add endpoint**

In `src/d4bl/app/api.py`, add near the existing `/api/eval-runs` endpoint:

```python
@app.post("/api/eval-runs/{run_id}/analyze")
async def analyze_eval_run(
    run_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate or regenerate suggestions for an existing eval run."""
    # Import here to avoid module-level dependency on scripts/ path.
    # suggestions.py only uses ship_criteria.py which is also under scripts/,
    # but both are available when running from the repo root.
    # For Docker deployment, move suggestions.py to d4bl.validation.suggestions
    # (same pattern as validate_model_output).
    from scripts.training.suggestions import (
        format_suggestions_json,
        generate_suggestions,
    )

    try:
        run_uuid = UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run ID")

    result = await db.execute(
        select(ModelEvalRun).where(ModelEvalRun.id == run_uuid)
    )
    run = result.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Eval run not found")

    suggestions = generate_suggestions(run.metrics or {}, run.task)
    suggestions_json = format_suggestions_json(suggestions)

    run.suggestions = suggestions_json
    await db.commit()

    return {"suggestions": suggestions_json}
```

- [ ] **Step 2: Run tests**

Run: `QUERY_PARSER_MODEL= EXPLAINER_MODEL= EVALUATOR_MODEL= POSTGRES_HOST=localhost POSTGRES_PORT=54322 POSTGRES_PASSWORD=postgres pytest tests/ --ignore=tests/test_training/test_integration_models.py -x -q`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add src/d4bl/app/api.py
git commit -m "feat: add POST /api/eval-runs/{id}/analyze endpoint"
```

---

## Task 7: Build LearnTabs Component

**Files:**
- Create: `ui-nextjs/components/learn/LearnTabs.tsx`

- [ ] **Step 1: Create the tab component**

Create `ui-nextjs/components/learn/LearnTabs.tsx`:

```tsx
'use client';

import { useEffect, useState } from 'react';

type Tab = 'compare' | 'learn' | 'build';

const TABS: { key: Tab; label: string }[] = [
  { key: 'compare', label: 'Compare' },
  { key: 'learn', label: 'Learn' },
  { key: 'build', label: 'Build' },
];

export default function LearnTabs({
  children,
}: {
  children: Record<Tab, React.ReactNode>;
}) {
  const [active, setActive] = useState<Tab>('compare');

  // Sync with URL hash
  useEffect(() => {
    const hash = window.location.hash.replace('#', '') as Tab;
    if (hash && TABS.some((t) => t.key === hash)) {
      setActive(hash);
    }
  }, []);

  const handleTabChange = (tab: Tab) => {
    setActive(tab);
    window.history.replaceState(null, '', `#${tab}`);
  };

  return (
    <div>
      {/* Tab bar */}
      <div className="flex gap-1 mx-6 mb-6 bg-[#292929] rounded-lg p-1" role="tablist">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            id={`tab-${tab.key}`}
            role="tab"
            aria-selected={active === tab.key}
            aria-controls={`tabpanel-${tab.key}`}
            onClick={() => handleTabChange(tab.key)}
            className={`flex-1 py-2.5 rounded-md text-sm font-medium transition-all duration-200 ${
              active === tab.key
                ? 'bg-[#00ff32]/15 text-[#00ff32] border border-[#00ff32]/30'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab panels */}
      {TABS.map((tab) => (
        <div
          key={tab.key}
          id={`tabpanel-${tab.key}`}
          role="tabpanel"
          aria-labelledby={`tab-${tab.key}`}
          hidden={active !== tab.key}
        >
          {children[tab.key]}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd ui-nextjs && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add ui-nextjs/components/learn/LearnTabs.tsx
git commit -m "feat: add LearnTabs component with hash-synced navigation"
```

---

## Task 8: Build SuggestionsPanel Component

**Files:**
- Create: `ui-nextjs/components/learn/SuggestionsPanel.tsx`

- [ ] **Step 1: Create the component**

Create `ui-nextjs/components/learn/SuggestionsPanel.tsx`:

```tsx
'use client';

import { useEffect, useState } from 'react';
import { EvalRunItem, getEvalRuns } from '@/lib/api';

interface SuggestionRule {
  metric: string;
  severity: string;
  current: number;
  target: number;
  suggestion: string;
  category: string;
}

export default function SuggestionsPanel() {
  const [runs, setRuns] = useState<EvalRunItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await getEvalRuns();
        if (!cancelled) setRuns(data.runs);
      } catch {
        // Silently fail — empty state handles it
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return <div className="bg-[#292929] rounded-lg h-24 animate-pulse" />;
  }

  // Collect suggestions from all runs
  const allSuggestions: { task: string; rule: SuggestionRule }[] = [];
  for (const run of runs) {
    const suggestions = run.suggestions as { rules?: SuggestionRule[] } | null;
    if (suggestions?.rules) {
      for (const rule of suggestions.rules) {
        allSuggestions.push({ task: run.task, rule });
      }
    }
  }

  if (allSuggestions.length === 0) {
    return (
      <div className="bg-[#292929] border border-[#404040] rounded-lg p-6 text-center">
        <p className="text-gray-400 text-sm">No suggestions yet.</p>
        <p className="text-gray-600 text-xs mt-1">
          Run the eval harness with --persist to generate improvement suggestions.
        </p>
      </div>
    );
  }

  // Sort: blocking first
  const sorted = [...allSuggestions].sort((a, b) => {
    if (a.rule.severity === 'blocking' && b.rule.severity !== 'blocking') return -1;
    if (a.rule.severity !== 'blocking' && b.rule.severity === 'blocking') return 1;
    return 0;
  });

  return (
    <div className="space-y-2">
      {sorted.map((item, i) => (
        <div
          key={i}
          className={`bg-[#292929] rounded-r-lg p-3 border-l-[3px] ${
            item.rule.severity === 'blocking'
              ? 'border-l-[#f87171]'
              : 'border-l-[#fbbf24]'
          }`}
        >
          <div className="flex justify-between items-start mb-1">
            <div className="flex items-center gap-2">
              <span className="text-xs text-white font-semibold">
                {item.task}: {item.rule.metric}
              </span>
            </div>
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded ${
                item.rule.severity === 'blocking'
                  ? 'text-[#f87171] bg-[#402424]'
                  : 'text-[#fbbf24] bg-[#3d3520]'
              }`}
            >
              {item.rule.severity}
            </span>
          </div>
          <p className="text-[11px] text-gray-500 mb-1">
            Current: {item.rule.current} / Target: {item.rule.target}
          </p>
          <div className="text-[11px] text-[#4ade80] bg-[#1f3524] inline-block px-2 py-1 rounded">
            {item.rule.suggestion}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd ui-nextjs && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add ui-nextjs/components/learn/SuggestionsPanel.tsx
git commit -m "feat: add SuggestionsPanel component for post-experiment suggestions"
```

---

## Task 9: Build BuildTab Component

**Files:**
- Create: `ui-nextjs/components/learn/BuildTab.tsx`

- [ ] **Step 1: Create the component**

Move the tutorials grid and slide deck link into `ui-nextjs/components/learn/BuildTab.tsx`:

```tsx
import TutorialStep from '@/components/learn/TutorialStep';

const COLAB_BASE = 'https://colab.research.google.com/github/William-Hill/d4bl_ai_agent/blob/main/notebooks/tutorials';

const TUTORIALS = [
  { title: 'Understanding Your Data', description: 'Query Supabase and see the shape of equity data.', colabUrl: `${COLAB_BASE}/01_understanding_your_data.ipynb` },
  { title: 'Creating Training Data', description: 'Write distillation prompts and generate training pairs.', colabUrl: `${COLAB_BASE}/02_creating_training_data.ipynb` },
  { title: 'Training with Unsloth', description: 'Load the model, configure LoRA, and run training.', colabUrl: `${COLAB_BASE}/03_training_with_unsloth.ipynb` },
  { title: 'Testing Your Model', description: 'Load in Ollama and compare outputs to the base model.', colabUrl: `${COLAB_BASE}/04_testing_your_model.ipynb` },
  { title: 'Making It Your Own', description: "Customize the model for your community's data.", colabUrl: `${COLAB_BASE}/05_making_it_your_own.ipynb` },
];

export default function BuildTab() {
  return (
    <div className="max-w-4xl mx-auto px-6 py-12">
      <h2 className="text-3xl font-bold text-white mb-2">Build Your Own</h2>
      <p className="text-lg text-gray-400 mb-8">
        Guided tutorials to build your own equity-focused model
      </p>

      <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-4 mb-12">
        {TUTORIALS.map((t, i) => (
          <TutorialStep
            key={t.title}
            step={i + 1}
            title={t.title}
            description={t.description}
            colabUrl={t.colabUrl}
          />
        ))}
      </div>

      <div className="text-center">
        <a
          href="https://gamma.app/docs/Building-AI-That-Centers-Racial-Equity-m8qd4n13bdtboa1"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 px-6 py-3 bg-[#00ff32]/10 border border-[#00ff32]/30 rounded-lg text-sm text-[#00ff32] hover:bg-[#00ff32]/20 transition-colors"
        >
          View the Slide Deck
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
        </a>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd ui-nextjs && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add ui-nextjs/components/learn/BuildTab.tsx
git commit -m "feat: add BuildTab component with tutorials and slide deck"
```

---

## Task 10: Add Model Selector Dropdowns to Playground

**Files:**
- Modify: `ui-nextjs/components/learn/ModelComparisonPlayground.tsx`
- Modify: `ui-nextjs/lib/api.ts`

- [ ] **Step 1: Update API client types**

In `ui-nextjs/lib/api.ts`, update the `compareModels` function to accept optional model overrides:

```typescript
export async function compareModels(
  prompt: string,
  models?: {
    pipeline_a_parser?: string;
    pipeline_a_explainer?: string;
    pipeline_b_parser?: string;
    pipeline_b_explainer?: string;
  },
): Promise<CompareResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE}/api/compare`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ prompt, ...models }),
  });
  // ... rest unchanged
```

Add a model list fetcher:

```typescript
export interface ModelInfo {
  provider: string;
  model: string;
  model_string: string;
  is_default: boolean;
  task: string;
  type: string;
  version: string | null;
}

export async function getAvailableModels(): Promise<ModelInfo[]> {
  const response = await fetch(`${API_BASE}/api/models`);
  if (!response.ok) return [];
  return response.json();
}
```

- [ ] **Step 2: Add model selector to playground**

In `ModelComparisonPlayground.tsx`, add state for selected models, fetch available models on mount, and render two dropdown selectors above the pipeline diagram. Each dropdown shows model options grouped by type (base / finetuned). Selected models are passed to `compareModels()`.

The dropdowns use the existing dark theme styling and are disabled during loading.

- [ ] **Step 3: Verify build**

Run: `cd ui-nextjs && npm run build 2>&1 | tail -10`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add ui-nextjs/components/learn/ModelComparisonPlayground.tsx ui-nextjs/lib/api.ts
git commit -m "feat: add model selector dropdowns to playground for hot-swappable comparison"
```

---

## Task 11: Restructure /learn Page into Tabs

**Files:**
- Modify: `ui-nextjs/app/learn/page.tsx`

- [ ] **Step 1: Restructure the page**

Replace the current single-scroll layout with:

```tsx
import BuildTab from '@/components/learn/BuildTab';
import ConceptSection from '@/components/learn/ConceptSection';
import DistillationPipeline from '@/components/learn/DistillationPipeline';
import EvalMetricsPanel from '@/components/learn/EvalMetricsPanel';
import LearnTabs from '@/components/learn/LearnTabs';
import LoRAVisualizer from '@/components/learn/LoRAVisualizer';
import MethodologyWheel from '@/components/learn/MethodologyWheel';
import ModelComparisonPlayground from '@/components/learn/ModelComparisonPlayground';
import QuantizationSlider from '@/components/learn/QuantizationSlider';
import RegisterComparison from '@/components/learn/RegisterComparison';
import SuggestionsPanel from '@/components/learn/SuggestionsPanel';

// ... metadata unchanged ...

export default function LearnPage() {
  return (
    <main className="min-h-screen bg-[#1a1a1a]">
      {/* Compact Hero */}
      <section className="px-6 pt-20 pb-8 text-center">
        <h1 className="text-4xl md:text-5xl font-bold text-white mb-2 tracking-tight">
          Building AI That Centers Community
        </h1>
        <p className="text-lg text-gray-400 max-w-2xl mx-auto">
          Data for Black Lives &middot; Fine-Tuned Language Model
        </p>
      </section>

      <LearnTabs>
        {{
          compare: (
            <div className="max-w-6xl mx-auto px-6 py-8 space-y-12">
              {/* Playground */}
              <section>
                <h2 className="text-2xl font-bold text-white mb-2">Compare Pipelines Live</h2>
                <p className="text-gray-400 mb-6">
                  Same question, two pipelines — see every step side by side
                </p>
                <ModelComparisonPlayground />
              </section>

              {/* Eval Metrics */}
              <section>
                <h2 className="text-2xl font-bold text-white mb-2">How It Performs</h2>
                <p className="text-gray-400 mb-6">
                  Latest eval harness results comparing base and fine-tuned models
                </p>
                <EvalMetricsPanel />
              </section>

              {/* Suggestions — reads from EvalMetricsPanel data */}
              <section>
                <h2 className="text-2xl font-bold text-white mb-2">Suggested Improvements</h2>
                <p className="text-gray-400 mb-6">
                  Actionable recommendations from the latest eval run
                </p>
                <SuggestionsPanel />
              </section>
            </div>
          ),

          learn: (
            <>
              {/* All 7 existing ConceptSections, unchanged */}
              {/* ... What is a Language Model, Why Fine-Tune, LoRA, Quantization, ... */}
              {/* ... Distillation, Methodology, RegisterComparison ... */}
            </>
          ),

          build: <BuildTab />,
        }}
      </LearnTabs>
    </main>
  );
}
```

Note: The Learn tab content is the existing 7 `ConceptSection` blocks, moved verbatim into the `learn` key. No content changes.

- [ ] **Step 2: Verify build and lint**

Run: `cd ui-nextjs && npm run build && npm run lint`
Expected: Clean build, no lint errors

- [ ] **Step 3: Commit**

```bash
git add ui-nextjs/app/learn/page.tsx
git commit -m "feat: restructure /learn into Compare/Learn/Build tabs"
```

---

## Task 12: Full Test Suite Verification

- [ ] **Step 1: Run backend tests**

Run: `QUERY_PARSER_MODEL= EXPLAINER_MODEL= EVALUATOR_MODEL= POSTGRES_HOST=localhost POSTGRES_PORT=54322 POSTGRES_PASSWORD=postgres pytest tests/ --ignore=tests/test_training/test_integration_models.py -x -q`
Expected: All PASS

- [ ] **Step 2: Run frontend build and lint**

Run: `cd ui-nextjs && npm run build && npm run lint`
Expected: Clean

- [ ] **Step 3: Run ruff lint**

Run: `ruff check src/d4bl/ scripts/training/suggestions.py tests/test_suggestions.py`
Expected: All checks passed

- [ ] **Step 4: Commit any fixups**

```bash
git add -A
git commit -m "fix: address test and lint issues from learn redesign"
```
