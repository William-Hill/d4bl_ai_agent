# Post-Experiment Analysis + /learn Redesign — Design Spec

**Date:** 2026-03-27
**Status:** Draft
**Epic:** #124 (Fine-Tuned Model)

## 1. Problem

The `/learn` page buries interactive tools (playground, eval metrics) beneath 5000px of educational content. Returning users must scroll past sections they've already read. Additionally, after running the eval harness, there's no analysis of *what to improve* — users see metrics but get no actionable guidance for the next training iteration.

## 2. Goals

1. Restructure `/learn` into a tabbed layout so interactive tools are immediately accessible.
2. Add hot-swappable model selection so users can compare any two model configurations (base vs fine-tuned, v1.0 vs v1.1, mistral vs llama3).
3. Generate actionable training data suggestions after eval harness runs — both rules-based (free, always runs) and LLM-powered (optional, deeper analysis).
4. Display suggestions on the Compare tab alongside eval metrics.

## 3. /learn Page Restructure

### 3.1 Tab Layout

Three tabs, with Compare as the default:

| Tab | Content | Audience |
|-----|---------|----------|
| **Compare** (default) | Model selector, pipeline playground, eval metrics, suggested improvements | Returning users, model developers |
| **Learn** | 7 educational sections in vertical scroll (unchanged content) | First-time visitors |
| **Build** | 5 Colab tutorials + slide deck link | Hands-on builders |

### 3.2 Hero

Compact version of the current hero — title, subtitle, no slide deck link (moved to Build tab). Reduced vertical space so tabs appear near the top of the viewport.

### 3.3 Tab Component

Client component (`LearnTabs`) wrapping three panels. URL hash sync (`#compare`, `#learn`, `#build`) so external links can deep-link to a specific tab. Default: `#compare`.

### 3.4 Learn Tab

The 7 educational sections retain their current content and vertical scroll layout:
- What is a Language Model?
- Why Fine-Tune?
- How LoRA Works
- How Quantization Works
- Training Data & Distillation
- D4BL Methodology in AI
- From Data to Justice (RegisterComparison)

### 3.5 Build Tab

- 5 Colab tutorial cards (current `TutorialStep` grid)
- Slide deck link (moved from hero)

## 4. Model Selector (Hot-Swappable)

### 4.1 UI

Two always-visible dropdowns side by side, labeled "Pipeline A" and "Pipeline B", separated by "vs". Each dropdown is populated from `GET /api/models` with options grouped as:

- **Single models:** `mistral:latest`, `llama3:latest`, etc. — all pipeline steps use this model
- **D4BL versions:** `d4bl v1.0`, `d4bl v1.1`, etc. — sets parser model to `d4bl-query-parser` and explainer model to `d4bl-explainer` for that version

Default selection: Pipeline A = `mistral:latest`, Pipeline B = latest D4BL version.

### 4.2 Evaluator Model

The evaluator (judge) is always the same for both pipelines — it doesn't make sense for a model to evaluate itself. Uses `model_for_task("evaluator")` (d4bl-evaluator if configured, otherwise the base model).

### 4.3 Backend Changes

Update `POST /api/compare` to accept explicit model names for each pipeline:

```python
class CompareRequest(BaseModel):
    prompt: str
    pipeline_a_parser: str      # e.g. "mistral"
    pipeline_a_explainer: str   # e.g. "mistral"
    pipeline_b_parser: str      # e.g. "d4bl-query-parser"
    pipeline_b_explainer: str   # e.g. "d4bl-explainer"
```

The endpoint maps these to two `_run_pipeline()` calls:
- Pipeline A: `_run_pipeline(parser_model=pipeline_a_parser, explainer_model=pipeline_a_explainer, ...)`
- Pipeline B: `_run_pipeline(parser_model=pipeline_b_parser, explainer_model=pipeline_b_explainer, ...)`

The `evaluator_model` is resolved from `model_for_task("evaluator")` for both pipelines (same judge).

**Server-side validation:** The endpoint must validate that `pipeline_a_parser`, `pipeline_a_explainer`, `pipeline_b_parser`, and `pipeline_b_explainer` are models available in Ollama (checked against the list from `get_available_models()`). Reject unknown model names with a 400 error to prevent arbitrary model pulls or inference cost spikes.

### 4.4 /api/models Update

Extend the existing `get_available_models()` response (currently returns `provider`, `model`, `model_string`, `is_default`, `task`) with two new fields:

```json
[
  {"provider": "ollama", "model": "mistral", "model_string": "ollama/mistral", "is_default": true, "task": "general", "type": "base", "version": null},
  {"provider": "ollama", "model": "d4bl-query-parser", "model_string": "ollama/d4bl-query-parser", "is_default": false, "task": "query_parser", "type": "finetuned", "version": "v1.0"},
  {"provider": "ollama", "model": "d4bl-explainer", "model_string": "ollama/d4bl-explainer", "is_default": false, "task": "explainer", "type": "finetuned", "version": "v1.0"}
]
```

New fields added to existing shape:
- `type`: `"base"` or `"finetuned"` — `"base"` for the default model, `"finetuned"` for task-specific models
- `version`: model version string or `null` — derived from `QUERY_PARSER_MODEL_VERSION` / `EXPLAINER_MODEL_VERSION` env vars (default `null`). These are display labels, not Ollama tags.

## 5. Post-Experiment Analysis

### 5.1 Rules-Based Suggestions (Always Runs)

After `run_eval_harness.py` computes metrics, a `generate_suggestions()` function maps failing or weak metrics to actionable training data recommendations.

**Suggestion rules by task:**

Query Parser:
| Condition | Severity | Suggestion |
|-----------|----------|-----------|
| `json_valid_rate < 0.95` | blocking | "Add adversarial examples with malformed input to improve JSON compliance" |
| `entity_f1 < 0.80` | blocking | "Add training pairs with more diverse entity types (organizations, policies, geographies)" |
| `data_source_accuracy < 0.85` | blocking | "Add examples that clarify when to use vector vs structured search" |
| `community_framing_f1 < 0.70` | non-blocking | "Add community-voiced query examples with advocacy framing" |
| `p95_latency_ms > 1000` | blocking | "Consider increasing quantization level or reducing context window" |
| `adversarial_pass_rate < 0.85` | blocking | "Add more adversarial prompts with harmful framings that should be reframed" |

Explainer:
| Condition | Severity | Suggestion |
|-----------|----------|-----------|
| `json_valid_rate < 0.95` | blocking | "Add examples with complex nested JSON output structure" |
| `factual_accuracy < 0.90` | blocking | "Verify training data accuracy — check for stale statistics in distillation corpus" |
| `d4bl_composite < 3.5` | blocking | "Increase proportion of D4BL methodology-aligned training examples" |
| `register_consistency < 3.0` | non-blocking | "Add single-register examples with clear style separation between community/policy/research" |
| `p95_latency_ms > 3000` | blocking | "Consider increasing quantization level or reducing context window" |

Evaluator:
| Condition | Severity | Suggestion |
|-----------|----------|-----------|
| `hallucination_accuracy < 0.85` | blocking | "Add more hallucination detection examples with subtle factual errors" |
| `relevance_mae > 0.8` | blocking | "Add relevance scoring examples with borderline cases (partially relevant)" |
| `bias_mae > 1.0` | blocking | "Add bias detection examples covering structural bias, not just explicit bias" |
| `relevance_correlation < 0.70` | non-blocking | "Add more diverse relevance scoring examples across different query types" |

### 5.2 LLM-Powered Analysis (Optional)

Triggered by `--analyze` CLI flag or "Analyze Failures" button in the UI.

**Process:**
1. Collect the worst-performing examples from the eval run (lowest scores, invalid outputs)
2. Send to Claude API with context: the task, the prompt, the expected output, the actual output, and the metric that failed
3. Ask Claude to identify patterns across failures and suggest specific training data improvements
4. Store the analysis in the `suggestions` field alongside rules-based suggestions

**Prompt template:**
```
You are analyzing failures from a fine-tuned model evaluation.

Task: {task}
Model: {model_name} ({model_version})

The following {n} examples had the worst performance:

{examples}

Identify patterns across these failures:
1. What types of inputs consistently fail?
2. What is the model getting wrong?
3. What specific training data would address these weaknesses?

Be specific and actionable. Suggest concrete training data examples to add.
```

**Cost:** ~$0.01-0.05 per analysis (small prompt, few examples). Only runs when explicitly requested.

### 5.3 Storage

Add `suggestions` JSONB column to `model_eval_runs` table:

```sql
ALTER TABLE model_eval_runs ADD COLUMN suggestions JSONB;
```

Schema:
```json
{
  "rules": [
    {
      "metric": "entity_f1",
      "severity": "blocking",
      "current": 0.72,
      "target": 0.80,
      "suggestion": "Add training pairs with more diverse entity types",
      "category": "training_data"
    }
  ],
  "llm_analysis": null,
  "generated_at": "2026-03-27T12:00:00Z"
}
```

`llm_analysis` is null until the user runs `--analyze` or clicks "Analyze Failures".

### 5.4 CLI Integration

Two modes:

```bash
# Mode 1: Run eval with suggestions (rules always generated, LLM optional)
python -m scripts.training.run_eval_harness --persist
python -m scripts.training.run_eval_harness --persist --analyze  # includes LLM analysis

# Mode 2: Analyze an existing run without re-running evals
python -m scripts.training.run_eval_harness --analyze-existing <run-id>
python -m scripts.training.run_eval_harness --analyze-existing latest
```

`--analyze-existing` accepts a UUID run ID or the keyword `latest`. When `latest` is used with `--task`, it resolves to the most recent run for that task. Without `--task`, it resolves to the most recent run globally by `created_at`. It loads the existing metrics from `model_eval_runs`, generates rules-based suggestions, runs LLM analysis, and updates the `suggestions` column. Does not re-run model inference.

Suggestions are printed to CLI alongside the metrics report and persisted to DB when `--persist` is used.

### 5.5 API

`GET /api/eval-runs` already returns `model_eval_runs` rows. The `suggestions` field must be added to both `ModelEvalRun.to_dict()` and `EvalRunItem` Pydantic schema to be included in the response.

New endpoint for on-demand LLM analysis:
```
POST /api/eval-runs/{run_id}/analyze
```
Triggers LLM analysis for a specific eval run, updates the `suggestions.llm_analysis` field, and returns the updated suggestions. **Idempotent:** if `suggestions.llm_analysis` is already populated, return the existing analysis without re-running (and without incurring additional API cost). Pass `?force=true` query parameter to explicitly re-run the analysis.

### 5.6 UI: SuggestionsPanel

Displayed in the Compare tab below eval metrics. Shows:
- Rules-based suggestions grouped by severity (blocking first, then non-blocking)
- Each suggestion shows: metric name, current value vs target, severity badge, actionable recommendation
- "Analyze Failures" button triggers `POST /api/eval-runs/{id}/analyze`
- LLM analysis displayed in an expandable section when available

## 6. Files Modified/Created

```
Modified:
  src/d4bl/app/api.py                          — update /api/compare request schema, add /api/eval-runs/{id}/analyze
  src/d4bl/app/schemas.py                      — update CompareRequest, EvalRunItem (add suggestions field), add SuggestionItem
  src/d4bl/infra/database.py                   — add suggestions column to ModelEvalRun model + to_dict()
  src/d4bl/llm/provider.py                     — extend get_available_models() with type and version fields
  scripts/training/run_eval_harness.py          — integrate generate_suggestions(), add --analyze flag
  scripts/training/ship_criteria.py             — export SHIP_CRITERIA for suggestion rules
  ui-nextjs/app/learn/page.tsx                  — restructure into tabbed layout
  ui-nextjs/components/learn/ModelComparisonPlayground.tsx — add model selector dropdowns
  ui-nextjs/lib/api.ts                          — update types, add analyzeFailures()

Created:
  scripts/training/suggestions.py               — rules-based + LLM suggestion engine
  ui-nextjs/components/learn/LearnTabs.tsx       — tab navigation component
  ui-nextjs/components/learn/SuggestionsPanel.tsx — suggested improvements display
  ui-nextjs/components/learn/BuildTab.tsx         — tutorials + slide deck
  tests/test_suggestions.py                      — suggestion generation tests
  tests/test_learn_tabs.py                        — tab component tests (if applicable)
  supabase/migrations/20260327000001_add_suggestions_to_eval_runs.sql

Migration:
  ALTER TABLE model_eval_runs ADD COLUMN suggestions JSONB;
```

## 7. Not In Scope

- Data lake expansion (separate spec — expand extractors for 11 unused tables + unstructured sources)
- Training script extraction from Colab notebook (separate spec — convert to CLI script with checkpointing)
- Historical version comparison chart (future — metrics over time as a line graph)
- Per-role model dropdowns in the selector (version-level grouping is sufficient for now)
- Individual model role overrides (e.g., use parser from v1.0 but explainer from v1.1)

## 8. Dependencies

- PR #133 (model comparison playground — merged)
- PR #134 (end-to-end pipeline comparison — open)
- Eval harness (PR #130 — merged)
- `model_eval_runs` table (PR #130 — merged)
- Ollama running with models registered
