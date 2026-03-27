# Tutorial Notebooks — Design Spec

**Date:** 2026-03-26
**Sprint:** 6 — Tutorial Notebooks
**Status:** Draft
**Branch:** `feat/tutorial-notebooks`

---

## Overview

Five standalone Google Colab tutorial notebooks teaching users how to build an equity-focused fine-tuned language model, using D4BL's actual approach as the template. Each notebook is self-contained — installs its own dependencies, includes sample data inline, and runs independently. Target audience ranges from non-technical community members (clear explanations) to ML practitioners (real runnable code on Colab T4).

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Data source | Bundled sample data (Python dicts) | Self-contained, no credentials needed |
| Notebook independence | Standalone (Approach A) | Any notebook works alone, easier to share/maintain |
| Training mode | Full with QUICK_MODE flag | Defaults to full run, `QUICK_MODE = True` for fast demo |
| Location | `notebooks/tutorials/` at repo root | Visible, standard location |
| Audience | Progressive disclosure | Clear explanations for beginners, real code for practitioners |

## Notebook Structure Convention

Every notebook follows this structure:

1. **Title cell** — notebook title, "Open in Colab" badge, D4BL one-liner
2. **Overview** — 2-3 sentences: what you'll learn, why it matters for equity work
3. **Prerequisites** — what you need (Google account, etc.), estimated time
4. **Setup cell** — `!pip install` dependencies, imports
5. **Concept sections** — markdown explaining the concept, then code demonstrating it
6. **Hands-on exercises** — cells with `# TODO` comments for users to modify
7. **Summary** — what you built, link to next notebook

**Conventions:**
- Every code cell has a markdown cell above explaining what and why
- Sample data embedded as Python dicts/strings (no external file downloads)
- `QUICK_MODE = True` flag where applicable
- D4BL equity context throughout, not just ML mechanics

## Notebook Specs

### Notebook 1: Understanding Your Data

**File:** `notebooks/tutorials/01_understanding_your_data.ipynb`
**Time estimate:** 15 minutes
**Dependencies:** pandas, matplotlib (pre-installed on Colab)

**Sections:**

| # | Section | Content |
|---|---------|---------|
| 1 | What is equity data? | D4BL's 17 data sources, why they matter |
| 2 | Sample data exploration | Load embedded CDC Places, Census ACS, EPA EJScreen rows as DataFrames |
| 3 | Spotting disparities | Compute Black/white ratios for a metric, bar chart visualization |
| 4 | Data shape for training | Preview how raw rows become distillation prompt inputs |
| 5 | Exercise | Pick a different metric, compute disparity ratio |

**Sample data:** ~20 rows each from 3 sources (CDC Places, Census ACS, EPA EJScreen), embedded as Python dicts. Includes columns: state, metric, black_value, white_value, year.

### Notebook 2: Creating Training Data

**File:** `notebooks/tutorials/02_creating_training_data.ipynb`
**Time estimate:** 20 minutes
**Dependencies:** json (stdlib only)

**Sections:**

| # | Section | Content |
|---|---------|---------|
| 1 | What is distillation? | Large model teaches small model, equity framing in prompts |
| 2 | Anatomy of a training pair | Real ChatML example with system/user/assistant, explain each role |
| 3 | The three adapters | Query parser, explainer, evaluator — one example pair each |
| 4 | Writing a distillation prompt | Walk through D4BL's prompt templates, explain each instruction |
| 5 | Generating pairs | Mock distillation function (hardcoded response, no API key needed) |
| 6 | The register system | Same data → community/policy/research register outputs |
| 7 | Exercise | Write own distillation prompt for a different metric |

**Prompt templates:** Inlined from `scripts/training/templates.py` with explanatory annotations.

**Mock distillation:** A function that takes a data row + template and returns a pre-written response matching the expected format. No API calls.

### Notebook 3: Training with Unsloth

**File:** `notebooks/tutorials/03_training_with_unsloth.ipynb`
**Time estimate:** 10 min (QUICK_MODE) / 25 min (full)
**Dependencies:** unsloth, transformers, datasets, trl

**Sections:**

| # | Section | Content |
|---|---------|---------|
| 1 | What is LoRA? | Recap with link to /learn page visualizer |
| 2 | Setup | Install Unsloth, load Qwen2.5-3B-Instruct, verify GPU |
| 3 | Configure LoRA | rank=16, target modules, alpha, dropout — D4BL's actual values |
| 4 | Prepare dataset | Load ~50 embedded query_parser training pairs, format with `apply_chat_template()` |
| 5 | Training loop | SFTTrainer, 7 epochs, lr=2e-4, warmup_ratio=0.1. QUICK_MODE: 10 steps |
| 6 | Monitor training | Show loss curve, explain what to look for |
| 7 | Save and export | Save LoRA adapter, show file size vs full model |
| 8 | Exercise | Modify rank (8 vs 32), rerun, compare adapter sizes |

**Key Sprint 2.5 lesson:** Notebook explicitly demonstrates `apply_chat_template()` vs manual ChatML string concatenation, showing why the latter fails for structured JSON output.

**QUICK_MODE:** Defined at top of notebook. `True` = `max_steps=10`, `False` = full 7-epoch run.

**Training data:** ~50 query_parser examples embedded as a Python list of ChatML dicts, subset of real `query_parser_train.jsonl`.

### Notebook 4: Testing Your Model

**File:** `notebooks/tutorials/04_testing_your_model.ipynb`
**Time estimate:** 15 minutes
**Dependencies:** unsloth, transformers

**Sections:**

| # | Section | Content |
|---|---------|---------|
| 1 | Why test? | Ship criteria philosophy, not just "does it work" |
| 2 | Load the model | Load LoRA adapter (from Notebook 3 or pre-saved download link) |
| 3 | Run inference | Generate responses for 5 test prompts |
| 4 | Validate structure | Check JSON validity, field completeness — inlined validation logic |
| 5 | Compare to base | Same prompts through base Qwen2.5-3B, side-by-side comparison |
| 6 | Ship criteria check | D4BL's ship/no-ship framework, manual metric check |
| 7 | Exercise | Write 3 test prompts about a topic you care about, compare models |

**Standalone fallback:** For users who skipped Notebook 3, a setup cell downloads a pre-trained adapter. Uses a placeholder URL (to be updated when models are published to HuggingFace).

### Notebook 5: Making It Your Own

**File:** `notebooks/tutorials/05_making_it_your_own.ipynb`
**Time estimate:** 20 min (QUICK_MODE) / 35 min (full)
**Dependencies:** unsloth, transformers, datasets, trl

**Sections:**

| # | Section | Content |
|---|---------|---------|
| 1 | The methodology is portable | D4BL's approach transfers to other communities |
| 2 | Bring your own data | Template cell for user's CSV/dict data, reshape to expected format |
| 3 | Customize distillation prompts | Modify D4BL templates: community name, structural context, policy landscape |
| 4 | Generate custom training pairs | Mock distillation from user data + custom prompts |
| 5 | Train on custom data | Short training run on user's pairs, QUICK_MODE default |
| 6 | What's next | D4BL resources, contributing back, HuggingFace publishing, Ollama local |
| 7 | Exercise | End-to-end: pick metric → write prompt → generate → train → test |

## /learn Page Updates

1. **Update TutorialStep URLs** — change `colabUrl="#"` to actual Colab URLs:
   ```
   https://colab.research.google.com/github/William-Hill/d4bl_ai_agent/blob/main/notebooks/tutorials/01_understanding_your_data.ipynb
   ```

2. **Add Gamma deck link** — add a link to the existing slide deck in the hero section or as a small section before tutorials:
   ```
   https://gamma.app/docs/Building-AI-That-Centers-Racial-Equity-m8qd4n13bdtboa1
   ```

## File Structure

```
notebooks/
└── tutorials/
    ├── 01_understanding_your_data.ipynb
    ├── 02_creating_training_data.ipynb
    ├── 03_training_with_unsloth.ipynb
    ├── 04_testing_your_model.ipynb
    └── 05_making_it_your_own.ipynb

ui-nextjs/
└── app/learn/page.tsx              # Updated colabUrls + Gamma link
```

## Out of Scope

- Live API calls to Claude for distillation (mock only)
- Supabase database connection
- Publishing models to HuggingFace (instructions only)
- RunPod deployment
- Mobile 1.5B model training
