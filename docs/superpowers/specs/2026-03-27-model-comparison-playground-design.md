# Model Comparison Playground — Design Spec

**Date:** 2026-03-27
**Status:** Draft
**Epic:** #124 (Fine-Tuned Model)
**Location:** `/learn` page, replacing `PlaygroundPlaceholder`

## 1. Problem

The fine-tuned D4BL models (query parser, explainer, evaluator) are wired into the application (Sprint 3, PR #127) and an eval harness exists (PR #130), but there is no way to visually verify improvements over the base model. The eval harness is CLI-only, and the `/learn` page has a "Coming Soon" placeholder where an interactive comparison should be.

## 2. Goals

1. Let users run ad-hoc queries through both the base and fine-tuned models and see outputs side by side with fast deterministic metrics.
2. Display pre-computed deep metrics (entity F1, equity composite, bias MAE, etc.) from full eval harness runs on the `/learn` page.
3. Reuse existing infrastructure: `ollama_generate()`, `validate_model_output.py`, `model_for_task()`, `model_eval_runs` DB table.

## 3. Architecture

```
/learn page
├── [existing educational content]
├── EvalMetricsPanel (pre-computed deep metrics from model_eval_runs)
│   └── GET /api/eval-runs
└── ModelComparisonPlayground (interactive, replaces PlaygroundPlaceholder)
    └── POST /api/compare
```

## 4. Backend

### 4.1 `POST /api/compare` (new endpoint)

Requires Supabase JWT auth (consistent with all other endpoints).

**Request:**

```python
class CompareRequest(BaseModel):
    prompt: str           # User's query
    task: str             # "query_parser" | "explainer" | "evaluator"
```

**Behavior:**

1. Resolve baseline model from `settings.ollama_model` (default: `mistral`).
2. Resolve fine-tuned model from `model_for_task(task)`.
3. If both resolve to the same model (no fine-tuned model configured), return an error indicating fine-tuned models are not configured.
4. Run `ollama_generate()` for both models concurrently (`asyncio.gather`).
5. Validate both outputs with the appropriate validator from `validate_model_output.py` (`validate_parser_output`, `validate_explainer_output`, `validate_evaluator_output`).
6. Return both outputs, latency, validation results, and computed deltas.

**Response:**

```python
class ModelOutput(BaseModel):
    model_name: str
    output: str
    latency_seconds: float
    valid_json: bool
    errors: list[str] | None = None

class CompareMetrics(BaseModel):
    latency_delta_pct: float        # (finetuned - baseline) / baseline * 100
    validity_improved: bool         # baseline invalid → finetuned valid
    task_specific_flag: str | None  # e.g. "Has structural framing", "Intent parsed"

class CompareResponse(BaseModel):
    baseline: ModelOutput
    finetuned: ModelOutput
    metrics: CompareMetrics
    task: str
```

**Task-specific flags:**

| Task | Flag computed | Logic |
|------|-------------|-------|
| query_parser | "Intent parsed" | `parsed.get("intent") in {"compare", "trend", "lookup", "aggregate"}` |
| explainer | "Has structural framing" | `"narrative" in parsed` |
| evaluator | "Score present" | `"score" in parsed and isinstance(parsed["score"], (int, float))` |

These flags are derived from the existing validators' parsed output — no new validation logic needed.

**Implementation location:** Add to `src/d4bl/app/api.py` alongside existing endpoints. The comparison logic is thin — it calls `ollama_generate()` twice and `validate_*_output()` twice.

### 4.2 `GET /api/eval-runs` (new endpoint)

Requires Supabase JWT auth.

**Request:** No parameters (returns latest runs per task).

**Behavior:**

1. Query `model_eval_runs` table for the most recent run per `(model_name, task)` pair.
2. Return grouped by task, with both baseline and fine-tuned entries where available.

**Response:**

```python
class EvalRunItem(BaseModel):
    model_name: str
    model_version: str
    base_model_name: str
    task: str
    metrics: dict[str, float | None]
    ship_decision: str
    blocking_failures: list[dict] | None
    created_at: str

class EvalRunsResponse(BaseModel):
    runs: list[EvalRunItem]
```

**Implementation:** Simple SQLAlchemy query using `ModelEvalRun` model with `DISTINCT ON (model_name, task)` ordered by `created_at DESC`.

### 4.3 `run_eval_harness.py --model` flag (CLI change)

Currently `TASK_MODELS` is hardcoded — you can only evaluate the fine-tuned models. Add a `--model` flag to override the **inference model** (the model actually called via `_run_prompt`):

```bash
# Run baseline metrics (inference model = mistral)
python -m scripts.training.run_eval_harness \
  --task query_parser --model mistral --model-version baseline --persist

# Run fine-tuned metrics (existing behavior, inference model = d4bl-query-parser)
python -m scripts.training.run_eval_harness \
  --task query_parser --model-version v1.0 --persist
```

When `--model` is provided, use it instead of `TASK_MODELS[task]` for inference. The `--model` value is also stored as `model_name` in the DB row. Note: the existing `--baseline` flag sets `base_model_name`, which is a metadata label (not the inference model). These are independent: `--model` controls what runs, `--baseline` labels what it's compared against.

This populates `model_eval_runs` with rows for both `mistral` and `d4bl-query-parser`, which the `GET /api/eval-runs` endpoint surfaces.

## 5. Frontend

### 5.1 `ModelComparisonPlayground` component

Replaces `PlaygroundPlaceholder` on the `/learn` page. Client component (`'use client'`).

**Layout (approved in brainstorming):**

1. **Query input** — text input + "Compare Models" button.
2. **Task selector** — pill buttons for Query Parser / Explainer / Evaluator.
3. **Summary delta bar** — horizontal bar showing key metric deltas: Valid JSON (before → after), Latency (% change), task-specific flag.
4. **Side-by-side panels** — base model (left, `#404040` border) and fine-tuned (right, green `#00ff32` border). Each shows raw output in monospace + validation tags below.
5. **Loading state** — skeleton placeholder while models run (can take several seconds).
6. **Error state** — if models aren't configured or Ollama is down, show a clear message.

**Styling:** Follows existing D4BL dark theme (`bg-[#1a1a1a]`, `border-[#404040]`, green accent `#00ff32`). Matches existing component patterns on the `/learn` page.

### 5.2 `EvalMetricsPanel` component

Displays pre-computed metrics from the eval harness. Client component.

**Layout:**

1. **Per-task cards** — one card per task (Query Parser, Explainer, Evaluator).
2. **Each card shows:**
   - Model names (baseline vs. fine-tuned)
   - Key metrics with baseline → fine-tuned comparison
   - Ship decision badge (ship / no_ship / ship_with_gaps)
   - Blocking failures if any
3. **Empty state** — "No evaluation data yet. Run the eval harness to see metrics here." with the CLI command.

### 5.3 `/learn` page integration

In `app/learn/page.tsx`:

1. Replace `import PlaygroundPlaceholder` with `import ModelComparisonPlayground`.
2. Add `import EvalMetricsPanel`.
3. Add a new `<ConceptSection title="How It Performs" subtitle="Eval harness results">` containing `EvalMetricsPanel`, placed before the "What's Next" section.
4. Inside the existing `<ConceptSection title="What's Next">`, replace `<PlaygroundPlaceholder />` with `<ModelComparisonPlayground />`.

### 5.4 API client functions

Add to `ui-nextjs/lib/api.ts`:

```typescript
export async function compareModels(prompt: string, task: string): Promise<CompareResponse> { ... }
export async function getEvalRuns(): Promise<EvalRunsResponse> { ... }
```

## 6. Files Modified/Created

```
Modified:
  src/d4bl/app/api.py                    — add /api/compare and /api/eval-runs endpoints
  src/d4bl/app/schemas.py                — add request/response models
  scripts/training/run_eval_harness.py   — add --model flag
  ui-nextjs/app/learn/page.tsx           — swap components
  ui-nextjs/lib/api.ts                   — add API client functions

Created:
  ui-nextjs/components/learn/ModelComparisonPlayground.tsx
  ui-nextjs/components/learn/EvalMetricsPanel.tsx
```

## 7. Not In Scope

- No auth changes (uses existing Supabase JWT pattern)
- No new database models (reuses `model_eval_runs`)
- No new validators (reuses `validate_model_output.py`)
- No streaming responses (both models run to completion then return)
- No rate limiting (auth requirement is sufficient protection)
- No mobile-specific layout (responsive via flex-wrap is sufficient)

## 8. Dependencies

- Sprint 3 (PR #127) — model routing, `model_for_task()`
- Eval harness (PR #130) — `model_eval_runs` table, `run_eval_harness.py`
- Sprint 2 (PR #126) — `validate_model_output.py` validators
- Ollama running locally with both base and fine-tuned models registered
