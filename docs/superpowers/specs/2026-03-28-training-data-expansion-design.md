# Training Data Expansion Design (Issue #139)

**Date:** 2026-03-28
**Parent:** #137 (Epic: Improve Fine-Tuned Model Performance v1.0 → v2.0)
**Target base model:** Qwen 3.5-4B (issue #140)

## Problem

The v1.0 eval harness results show critical training data gaps across the evaluator and query parser:

| Task | Metric | v1.0 Actual | Ship Target | Gap |
|------|--------|-------------|-------------|-----|
| **Evaluator** | hallucination_accuracy | 0% | 85% | Critical |
| **Evaluator** | training examples | 160 (40/subtask) | — | Severely undersized |
| **Query Parser** | entity_f1 | 59% | 80% | Large |
| **Query Parser** | json_valid_rate | 87% | 95% | Moderate |
| **Explainer** | training examples | 478 | — | Adequate (defer) |

### Root Causes

**Evaluator (0% hallucination accuracy):**
1. **Static model outputs** — every training example evaluates the same sentence template. The model never sees hallucinated content, varied quality levels, or diverse output formats.
2. **Shared system prompt** — all 4 subtasks (hallucination, relevance, bias, equity_framing) use one generic student prompt despite having completely different output schemas.
3. **Low example count** — 160 total across 4 subtasks means ~40 examples each, far below the minimum needed for pattern learning.

**Query Parser (59% entity F1):**
1. **Narrow entity type coverage** — training data contains almost exclusively state names and racial group names. Organizations, policies, counties, demographic intersections, and temporal references are absent.
2. **Near saturation for existing types** — at 434 examples, research shows diminishing returns for the entity types already covered (NuNER, JMIR AI study). More of the same won't help.

## Strategy: Research-Informed Approach

### Evaluator: Perturbation-Based Synthetic Hallucinations

Following [Patronus Lynx](https://www.patronus.ai/blog/lynx-state-of-the-art-open-source-hallucination-detection-model) (trained on 2,400 samples with perturbation-based hallucinations, outperformed GPT-4o) and [CATS](https://arxiv.org/abs/2410.12278) (controlled automatic task-specific synthetic data generation):

**Why perturbation over free-form generation:**
- Produces realistic hallucinations matching what the explainer model will actually produce in production (wrong statistic, misattributed geography, fabricated trend)
- Hallucinated text stays stylistically identical to factual text — the model must learn to check claims, not detect style shifts
- [HaluCheck](https://arxiv.org/abs/2505.17558) showed 1B-3B models trained on carefully crafted synthetic negatives achieved +24% F1 gains; a 4B model should do at least as well

**Bias mitigation via swap augmentation** ([JudgeLM, ICLR 2025](https://arxiv.org/abs/2310.17631)):
- For relevance and bias subtasks, duplicate training examples with swapped (context, model_output) presentation order
- Prevents position bias at ~5% consistency improvement, zero additional API cost

### Query Parser: Breadth Over Volume

Following [NuNER](https://arxiv.org/abs/2402.15343) (EMNLP 2024) — annotation diversity is the most influential factor for entity recognition, not text diversity. Only 5 examples per concept needed for F1 0.65, representing 6x improvement in data efficiency.

[Sample size research](https://ai.jmir.org/2024/1/e52095) shows diminishing returns for NER fine-tuning at ~439-527 sentences. Our 434 parser examples are near this threshold for existing entity types. Gains come from filling entity type gaps, not scaling volume.

### Data Integrity: Accumulate, Don't Replace

Following [ICLR 2025 research on model collapse](https://openreview.net/forum?id=5B2K4LRgmz):
- Model collapse is caused by replacement of real data with synthetic data, not by synthetic data itself
- As long as synthetic data accumulates alongside real/existing data, collapse is avoided
- New pairs are written to separate files (`evaluator_v2.jsonl`, `query_parser_v2.jsonl`) and merged during the prepare step
- Existing `pairs/` data is never deleted or overwritten

## Section 1: Evaluator Expansion

### Three-Step Hallucination Generation Pipeline

```
Step 1: Generate factual response
  Input:  seed row (census/CDC/EPA data)
  Output: grounded narrative paragraph

Step 2: Apply controlled perturbations (Claude generates these)
  Perturbation types:
  - Entity swap:          "Mississippi" -> "Vermont" (wrong geography)
  - Statistic fabrication: "$35,400" -> "$52,100" (wrong number)
  - Trend invention:      add "decreased 15% since 2018" (no trend data exists)
  - Source misattribution: "CDC data" -> "Census data" (wrong source)
  - Causal fabrication:   invent causal claim not in source data

Step 3: Format as evaluator training pair
  FACTUAL pair:      (context=seed_row, model_output=factual_response)   -> {"label": "FACTUAL"}
  HALLUCINATED pair: (context=seed_row, model_output=perturbed_response) -> {"label": "HALLUCINATED"}
```

Each factual response produces one factual + one hallucinated training pair (perfectly balanced classes).

### Per-Subtask Student System Prompts

Replace the single shared `_STUDENT_EVALUATOR_SYSTEM` with 4 task-specific prompts:

| Subtask | Student System Prompt (abbreviated) | Output Schema |
|---------|-------------------------------------|---------------|
| Hallucination | "Determine if the model output is factually grounded in the context..." | `{"label": "FACTUAL" or "HALLUCINATED"}` |
| Relevance | "Rate how relevant the model output is to the context on a 1-5 scale..." | `{"score": N, "reasoning": "..."}` |
| Bias | "Rate the degree of harmful bias in the model output on a 1-5 scale..." | `{"score": N, "reasoning": "..."}` |
| Equity framing | "Evaluate whether the model output applies equity-centered structural framing..." | `{"centers_community": bool, "names_structural_causes": bool, "avoids_deficit_framing": bool, "connects_to_policy": bool, "score": N}` |

### Tiered Quality Model Outputs

Instead of the single static template sentence, generate model outputs at 4 quality tiers for non-hallucination subtasks (relevance, bias, equity_framing):

| Tier | Description | Distribution |
|------|-------------|-------------|
| Excellent | Fully grounded, equity-framed, policy-connected | 25% |
| Good | Mostly correct, missing some structural context | 25% |
| Poor | Vague, generic, misses key data points | 25% |
| Hallucinated | Contains perturbation-based factual errors | 25% |

This teaches the evaluator to discriminate across a quality spectrum, not just binary.

### Swap Augmentation

For relevance and bias subtasks, duplicate each training pair with swapped context/output order. Applied during `prepare_dataset.py` (no additional API calls). Based on [JudgeLM](https://arxiv.org/abs/2310.17631) finding of ~5% consistency improvement.

### Target Counts (Post-Dedup)

| Subtask | Current | Target | New API Calls | Method |
|---------|---------|--------|---------------|--------|
| Hallucination | ~40 | 500+ | ~300 (generates 2 pairs each) | Perturbation pipeline |
| Relevance | ~40 | 300+ | ~300 | Tiered quality + swap augmentation |
| Bias | ~40 | 300+ | ~300 | Tiered quality + swap augmentation |
| Equity framing | ~40 | 300+ | ~300 | Tiered quality outputs |
| **Total** | 160 | 1,400+ | ~1,200 | |

Estimated cost: $8-12 (1,200 Sonnet 4 calls)

## Section 2: Query Parser Expansion

### Entity Type Gap Analysis

| Entity Type | Current Coverage | Examples in Training | Target |
|------------|-----------------|---------------------|--------|
| State names | High | ~400+ | No change needed |
| Racial groups | High | ~400+ | No change needed |
| **Organizations** | **None** | 0 | 50+ |
| **Policy names** | **None** | 0 | 50+ |
| **Counties/cities** | **Very low** | ~10 | 80+ |
| **Demographic intersections** | **None** | 0 | 40+ |
| **Temporal references** | **None** | 0 | 30+ |
| **Data source names** | **Low** | ~20 | 50+ |

Following NuNER's finding of ~5 examples per concept, 50 examples per new entity type gives 10x that floor.

### New Template Categories

**Organization-centric (~50 examples):**
```
"What has {org} reported about {metric} in {state}?"
"How does {org}'s data compare to {org2}'s findings on {metric}?"
```
Orgs: HUD, CDC, EPA, NAACP, Urban League, Vera Institute, Sentencing Project, ACLU, etc.

**Policy-centric (~50 examples):**
```
"How has {policy} affected {metric} for {race} communities in {state}?"
"What data exists on {policy} outcomes in {county}?"
```
Policies: drawn from `policy_bills` table + hardcoded list (ACA, Section 8, Title VI, Fair Housing Act, etc.)

**Sub-state geography (~80 examples):**
```
"Compare {metric} between {county} and {county2} in {state}."
"What are {metric} rates in {city}, {state}?"
```
Counties/cities from: `bjs_incarceration`, `vera_incarceration`, `police_violence_incidents`, `epa_environmental_justice`

**Intersectional demographics (~40 examples):**
```
"What are {metric} outcomes for low-income {race} {demographic} in {state}?"
"How does {metric} affect elderly {race} homeowners versus renters?"
```

**Temporal (~30 examples):**
```
"How has {metric} changed in {state} since {event}?"
"What were {metric} trends before and after {policy} in {state}?"
```

**Adversarial JSON stress (~50 examples):**
- Very long/short questions, special characters, ambiguous queries
- No clear entities, informal/colloquial language
- Target JSON validity specifically

### Expanded Seed Data Sources

Add to `_load_seed_rows()`:

| Table | What It Provides |
|-------|-----------------|
| `policy_bills` | Real policy names, sponsor orgs, bill numbers |
| `bjs_incarceration` | County-level geography |
| `vera_incarceration` | County-level geography, facility names |
| `police_violence_incidents` | City-level geography, department names |
| `epa_environmental_justice` | Tract-level geography, environmental metrics |

### Target Counts

| Category | New Examples | API Calls | Purpose |
|----------|------------|-----------|---------|
| Org-centric | 50 | ~55 | New entity type coverage |
| Policy-centric | 50 | ~55 | New entity type coverage |
| Sub-state geography | 80 | ~90 | New entity type coverage |
| Intersectional | 40 | ~45 | New entity type coverage |
| Temporal | 30 | ~35 | New entity type coverage |
| Adversarial JSON | 50 | ~55 | JSON reliability |
| **Total** | **300** | **~335** | |

Estimated cost: $3-4 (335 Sonnet 4 calls)

## Section 3: Pipeline Changes & Staged Execution

### Data Merge Strategy

New pairs are appended to the `pairs/` directory as separate files, never overwriting existing data:

| Data Layer | Source | Role |
|-----------|--------|------|
| Real data anchor | `corpus_pretrain.jsonl` (Census, CDC, EPA extracts) | Grounds model in real-world distributions |
| Existing synthetic | `pairs/evaluator.jsonl`, `pairs/query_parser.jsonl` | Sprint 2.5 distillation (preserved as-is) |
| New synthetic | `pairs/evaluator_v2.jsonl`, `pairs/query_parser_v2.jsonl` | Gap-filling expansion (this work) |

The `prepare_dataset.py` step merges old + new via glob (`pairs/evaluator*.jsonl`), deduplicates, then splits.

### Formalized Verification Gate

Based on [synthetic data verification research](https://arxiv.org/html/2510.16657v1) — an external verifier (human or better model) prevents quality degradation in synthetic training data.

**Evaluator verification (between Stage 1 and Stage 2):**

| Check | Sample Size | Pass Threshold | What to Look For |
|-------|------------|---------------|-----------------|
| Hallucination realism | 30 hallucinated pairs | 80% pass | Perturbation is non-obvious but detectable given context |
| Label correctness | 30 factual + 30 hallucinated | 90% pass | Labels match actual content |
| Schema compliance | 50 random across subtasks | 95% pass | Output matches per-subtask JSON schema |
| Quality tier distribution | All pairs | Within 5% of 25/25/25/25 | Even distribution |

Proceed to Stage 2 only if all checks pass. If hallucination realism < 80%, revise perturbation prompt and regenerate.

**Parser verification (after Stage 2):**

| Check | Sample Size | Pass Threshold | What to Look For |
|-------|------------|---------------|-----------------|
| Entity extraction | 30 new-entity-type pairs | 80% pass | Entities correctly identified |
| Entity type coverage | All new pairs | All 6 types present | Orgs, policies, counties, intersections, temporal, adversarial |
| Schema compliance | 50 random pairs | 95% pass | Output matches parser JSON schema |

### Code Changes

**New functions in `generate_training_pairs.py`:**

1. `_generate_factual_response(seed_row) -> str` — Claude produces grounded narrative from seed row
2. `_perturb_to_hallucination(seed_row, factual_response) -> str` — Applies one of 5 perturbation types
3. `_generate_tiered_model_output(seed_row, quality_tier) -> str` — Generates output at specified quality tier
4. `generate_query_parser_questions_v2(seed_rows, count, entity_type) -> list` — Entity-type-specific question generation

**New high-level generators (parallel to existing, not replacing them):**

5. `generate_evaluator_pairs_v2(conn, count_per_subtask, outfile)` — New function using perturbation pipeline for hallucination subtask, tiered quality outputs for others, per-subtask student prompts. Writes to `pairs/evaluator_v2.jsonl`.
6. `generate_query_parser_pairs_v2(conn, count, entity_types, outfile)` — New function using entity-type-specific templates and expanded seed tables. Writes to `pairs/query_parser_v2.jsonl`.

**Modifications to existing functions:**

- `_load_seed_rows()` — Add 5 new seed tables to the table list
- New CLI flags: `--task evaluator_v2` and `--task query_parser_v2` (existing `--task evaluator` and `--task query_parser` remain unchanged for reproducibility)

**New constants in `prompts.py`:**

- 4 per-subtask student system prompts
- Perturbation instruction prompt with 5 perturbation type definitions
- Tiered quality output prompts (excellent/good/poor)
- ~15 new question templates across 6 entity type categories

**Changes to `config.py`:**

- `EVALUATOR_V2_PAIRS_PER_SUBTASK = 350` (targets 300+ post-dedup)
- `PARSER_V2_ENTITY_PAIRS = 300`

**Changes to `prepare_dataset.py`:**

- Swap augmentation step for evaluator relevance/bias pairs
- Merge logic: glob `pairs/evaluator*.jsonl` and `pairs/query_parser*.jsonl`

### Staged Execution

**Stage 1: Evaluator expansion**
```bash
python -m scripts.training.generate_training_pairs --task evaluator_v2
# -> ~1,200 API calls -> pairs/evaluator_v2.jsonl
# Run verification gate (rubric above)
python -m scripts.training.prepare_dataset
```

**Stage 2: Query parser expansion** (only after Stage 1 verified)
```bash
python -m scripts.training.generate_training_pairs --task query_parser_v2
# -> ~335 API calls -> pairs/query_parser_v2.jsonl
# Run verification gate
python -m scripts.training.prepare_dataset
```

### Cost Summary

| Stage | API Calls | Estimated Cost |
|-------|-----------|---------------|
| Evaluator expansion | ~1,200 | $8-12 |
| Parser expansion | ~335 | $3-4 |
| **Total** | **~1,535** | **$11-16** |

## Out of Scope

| Item | Reason |
|------|--------|
| Explainer expansion | 478 examples adequate; measure deferred LLM-judged metrics first |
| DPO training stage ([HaluCheck](https://arxiv.org/abs/2505.17558)) | Big pipeline change; revisit if SFT + perturbation doesn't hit 85% hallucination accuracy |
| Constrained decoding (Outlines) | Inference-time fix; Ollama doesn't support natively |
| Parser task decomposition ([Google Research](https://research.google/blog/small-models-big-results-achieving-superior-intent-extraction-through-decomposition/)) | Architecture change; consider for v2.1 |
| Continuous post-training | Requires infrastructure for incremental updates; consider for v3.0 |
| Chain-of-thought evaluator output | Changes output schema the app consumes; consider for v2.1 |

## References

### Evaluator (Hallucination Detection & Judge Training)
- [Patronus Lynx](https://www.patronus.ai/blog/lynx-state-of-the-art-open-source-hallucination-detection-model) — SOTA open-source hallucination detection, trained on 2,400 perturbation-based samples
- [Patronus x Databricks Training](https://www.databricks.com/blog/patronus-ai-lynx) — Training methodology and infrastructure
- [CATS: Controlled Automatic Task-Specific Synthetic Data](https://arxiv.org/abs/2410.12278) — 5 hallucination pattern types, generation-selection pipeline
- [HaluCheck: Curriculum DPO on Synthetic Negatives](https://arxiv.org/abs/2505.17558) — 1B-3B models, +24% F1 via curriculum learning
- [HAD: Hallucination Detection with Qwen2.5](https://arxiv.org/html/2510.19318) — Fine-tuned Qwen2.5 for span-level hallucination detection
- [JudgeLM: Fine-tuned LLMs are Scalable Judges](https://arxiv.org/abs/2310.17631) — Swap augmentation, reference support, bias mitigation (ICLR 2025)
- [LLM-as-Judge Comprehensive Survey](https://arxiv.org/html/2412.05579v2) — Two-stage SFT+DPO training protocol
- [Perturbation-Based Synthetic Data for Hallucination Detection](https://arxiv.org/abs/2407.05474) — Perturbation methodology
- [Framework for Synthetically Generating Fine-Grained Hallucinated Data](https://link.springer.com/article/10.1007/s10579-025-09864-x) — 5 hallucination categories

### Query Parser (Entity Recognition & Structured Output)
- [NuNER: Entity Recognition via LLM-Annotated Data](https://arxiv.org/abs/2402.15343) — Annotation diversity > text diversity, 5 examples per concept sufficient (EMNLP 2024)
- [Sample Size Considerations for Fine-Tuning LLMs for NER](https://ai.jmir.org/2024/1/e52095) — Saturation at ~450 examples
- [Small Models, Big Results: Intent Extraction through Decomposition](https://research.google/blog/small-models-big-results-achieving-superior-intent-extraction-through-decomposition/) — Decomposition for small models (EMNLP 2025)
- [ENTDA: Entity-Based Data Augmentation](https://liuxiyang641.github.io/nlp/ENTDA/) — Entity swap/replace augmentation
- [Experimental Study on Data Augmentation for NER](https://arxiv.org/html/2411.14551v1) — Augmentation saturation points
- [STED: Evaluating LLM Structured Output Reliability](https://arxiv.org/abs/2512.23712) — JSON compliance metrics
- [PARSE: Schema Optimization for Entity Extraction](https://arxiv.org/html/2510.08623v1) — Schema design for reliability

### Data Pipeline & Integrity
- [Model Collapse: Accumulate vs Replace](https://openreview.net/forum?id=5B2K4LRgmz) — ICLR 2025, synthetic data safe if real data preserved
- [Escaping Model Collapse via Synthetic Data Verification](https://arxiv.org/html/2510.16657v1) — External verifier prevents quality degradation
- [AI Training in 2026: Anchoring Synthetic Data in Human Truth](https://invisibletech.ai/blog/ai-training-in-2026-anchoring-synthetic-data-in-human-truth/) — Human-in-the-loop curation
- [Preventing Model Collapse in 2025](https://humansintheloop.org/what-is-model-collapse-and-why-its-a-2025-concern/) — Practical guidelines
- [3 Ways Synthetic Data Breaks Models](https://humansintheloop.org/3-ways-synthetic-data-breaks-models-and-how-human-validators-fix-them/) — Validation methodologies
- [Next-Generation LLM Training: Data-Centric Perspective](https://arxiv.org/html/2603.14712) — Data quality over quantity
- [Continuous Post-Training for Dynamic Language Models](https://mbrenndoerfer.com/writing/continuous-post-training-incremental-model-updates-dynamic-language-models) — Incremental update paradigm
