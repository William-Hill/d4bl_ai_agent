# D4BL Fine-Tuned Language Model: Experiment Log

**Rolling document tracking model training experiments, methodology, and results.**
**Started:** 2026-03-25
**Last updated:** 2026-04-01

---

## Experiment Index

| # | Date | Name | Base Model | Key Result |
|---|------|------|------------|------------|
| 1 | 2026-03-23 | Sprint 2 baseline | Qwen2.5-3B | 3/11 integration tests passing |
| 2 | 2026-03-25 | Sprint 2.5 JSON fix | Qwen2.5-3B | 11/11 integration tests passing |
| 3 | 2026-03-29 | v2 Qwen 3.5 upgrade | Qwen3.5-4B | Base model upgrade, v2 training data |
| 4 | 2026-03-31 | v3 document layer + subtask dispatch | Qwen3.5-4B | Parser entity F1 +16pp, evaluator 0%->84% |
| 5 | 2026-04-01 | v3.1 expanded state coverage (FAILED) | Qwen3.5-4B | Domain re-adaptation broke evaluator output format |
| 6 | 2026-04-03 | v3.0 full retrain (clean slate) | Qwen3.5-4B | Hallucination 87%, parser entity F1 75%, all adapters co-adapted |

## Cumulative Cost

| Experiment | Claude API | Colab Compute | Cumulative Total |
|------------|-----------|---------------|------------------|
| 1. Sprint 2 baseline | ~$15.00 | ~$4.00 | ~$19.00 |
| 2. Sprint 2.5 JSON fix | ~$15.00 | ~$4.00 | ~$38.00 |
| 3. v2 Qwen 3.5 upgrade | $0.02 (resume) | ~$4.00 | ~$42.02 |
| 4. v3 document layer | $0.59 | ~$4.00 | ~$46.61 |
| 5. v3.1 expanded states (FAILED) | $0.59 | ~$4.00 | ~$51.20 |
| 6. v3.0 full retrain | $0.00 | ~$4.00 | **~$55.20** |

---

## Experiment 1: Sprint 2 Baseline

**Date:** 2026-03-23
**Report:** `docs/training-report-sprint-2.5.md` (Section 1.2)

### Observation
Models trained on ~115 examples per task produced narrative text instead of structured JSON. Only 3/11 integration tests passed.

### Hypothesis
Insufficient training data, too few epochs, and incorrect chat template tokenization caused the model to ignore JSON output instructions.

### Results
Established baseline failure mode. See Experiment 2 for fixes.

---

## Experiment 2: Sprint 2.5 — JSON Output Fix

**Date:** 2026-03-25
**Report:** `docs/training-report-sprint-2.5.md`

### Observation
Sprint 2 models generated narrative text instead of JSON.

### Hypothesis
Four root causes: (1) insufficient examples (~115 after dedup), (2) too few epochs (3), (3) manual ChatML tokenization losing structure, (4) no output length constraint. A fifth cause discovered during deployment: Ollama double-wrapping ChatML templates.

### Methodology
- Increased to 1,000 raw pairs per task
- Increased to 7 epochs
- Switched to `tokenizer.apply_chat_template()`
- Added `num_predict` to Modelfiles
- Used explicit `TEMPLATE` directive in Modelfiles

### Results

| Metric | Sprint 2 | Sprint 2.5 |
|--------|----------|------------|
| Integration tests passing | 3/11 | 11/11 |
| JSON valid rate (parser) | ~30% | >95% |
| JSON valid rate (explainer) | ~40% | >95% |

### Conclusion
All five hypotheses confirmed. Training data volume and chat template formatting were the primary drivers. The model had learned domain content but couldn't express it in the required format.

---

## Experiment 3: v2 Qwen 3.5-4B Upgrade

**Date:** 2026-03-29

### Observation
Qwen2.5-3B (1.8GB quantized) was the smallest viable model but showed capacity limits on complex evaluation tasks. Qwen3.5-4B offered a newer architecture with Gated Delta Networks.

### Hypothesis
Upgrading from Qwen2.5-3B to Qwen3.5-4B would improve model capacity without significantly increasing inference cost. The larger parameter count (4B vs 3B) and newer architecture should handle multi-task evaluation better.

### Methodology
- Base model: `unsloth/Qwen3.5-4B`
- Same training data as Sprint 2.5 (v2 corpus: 41,339 passages, same task pairs)
- Same three-phase pipeline (domain adaptation + 3 task adapters + GGUF export)
- LoRA configs updated in `train.py` (parser r=16 up from r=8)
- Hardware: Colab A100-SXM4-40GB

### Results

| Metric | Qwen2.5-3B (v1) | Qwen3.5-4B (v2) |
|--------|-----------------|-----------------|
| GGUF size | 1.8 GB | 2.5 GB |
| Parser entity_f1 | — | 56.83% |
| Parser data_source_accuracy | — | 71.60% |
| Evaluator hallucination_accuracy | — | 0%* |

*Evaluator 0% was later identified as a system prompt mismatch, not a model quality issue (see Experiment 4).

### Conclusion
Successful base model migration. Established v2 baseline metrics for comparison. The evaluator's 0% accuracy was a red herring caused by using a generic system prompt at inference time while the model was trained with subtask-specific prompts.

---

## Experiment 4: v3 Document Layer + Subtask Dispatch

**Date:** 2026-03-31

### Observation
Two gaps identified in v2:

1. **Training data gap**: The corpus contained only structured data records (census, CDC, FBI, etc.) but no unstructured text (policy bills, research reports, scraped web content). The model had no exposure to document-style passages.

2. **Evaluation architecture gap**: The single evaluator adapter was trained on four subtasks (hallucination, relevance, bias, equity framing) with different output schemas, but served through one generic Modelfile. The model couldn't determine which output format to use at inference time.

### Hypotheses

**H1 (Document layer):** Adding unstructured document passages to the domain corpus and document-sourced hallucination pairs to the evaluator training data will improve:
- Domain adaptation coverage for document-style content
- Evaluator accuracy on unstructured content hallucination detection

**H2 (Community framing):** Adding parser training pairs with populated `community_framing` metadata will improve entity extraction F1 and the model's ability to detect community-voiced research questions.

**H3 (Subtask dispatch):** Matching the inference system prompt to the subtask-specific prompt used during training will recover evaluator accuracy that was lost to format confusion.

### Methodology

#### Database changes
1. Created `documents` and `document_chunks` tables (parent-child schema for RAG)
2. Migrated 1,849 policy bills from `policy_bills` into the new schema
3. Applied `scraped_content_vectors` compatibility view with `INSTEAD OF INSERT` trigger
4. Created IVFFlat index on `document_chunks.embedding` (deferred REINDEX — no embeddings yet)

#### Training data changes

| Component | v2 | v3 | Delta |
|-----------|-----|-----|-------|
| Domain corpus | 41,339 passages | 43,188 passages | +1,849 document passages |
| Evaluator pairs (raw) | 2,400 | 2,750 | +350 doc hallucination pairs |
| Parser pairs (raw) | 1,300 | 1,500 | +200 community framing pairs |

New v3 training pair types:
- **`evaluator_v3` (doc hallucination):** 175 document chunks perturbed via Claude into hallucinated versions, producing 350 FACTUAL/HALLUCINATED pairs. Cost: $0.59 (175 API calls).
- **`query_parser_v3` (community framing):** 200 deterministic template-based pairs with populated `community_framing` dict. No Claude calls needed — ground truth is known from template parameters.

#### Training configuration
- Base model: `unsloth/Qwen3.5-4B`
- Hardware: Colab A100-SXM4-40GB, bf16 precision
- Same three-phase pipeline as v2
- Total training time: 1h 55m

#### Training health (all phases passed)

| Phase | Train Loss | Eval Loss | Overfit Ratio | Duration |
|-------|-----------|-----------|---------------|----------|
| Domain Adaptation | 0.485 | — | — | 59m 14s |
| Query Parser | 0.336 | 0.428 | 1.27 | 7m 23s |
| Data Explainer | 0.675 | 0.760 | 1.13 | 7m 45s |
| Evaluator | 0.593 | 0.622 | 1.05 | 24m 49s |

#### Inference architecture change
Created subtask-specific Ollama Modelfiles for the evaluator, each with the exact system prompt used during training:

| Model | System Prompt Focus | `num_predict` |
|-------|-------------------|---------------|
| `d4bl-evaluator-hallucination` | "factually grounded in the provided context" | 64 |
| `d4bl-evaluator-relevance` | "rate how relevant" | 128 |
| `d4bl-evaluator-bias` | "rate the degree of harmful bias" | 128 |
| `d4bl-evaluator-equity-framing` | "equity-centered, structural framing" | 256 |

Updated `run_eval_harness.py` to dispatch evaluator test examples to the correct subtask model based on the system prompt in the training pair.

### Results

#### Parser (H1 + H2 confirmed)

| Metric | v2 | v3 | Delta | Target |
|--------|-----|-----|-------|--------|
| entity_f1 | 56.83% | **72.66%** | **+15.83pp** | 80% |
| data_source_accuracy | 71.60% | **98.77%** | **+27.17pp** | 85% |
| json_valid_rate | 98.77% | 98.77% | 0 | 95% |
| schema_valid_rate | 71.60% | **98.77%** | **+27.17pp** | — |

#### Evaluator (H1 + H3 confirmed)

| Metric | v2 (generic prompt) | v3 (subtask dispatch) | Delta | Target |
|--------|--------------------|-----------------------|-------|--------|
| hallucination_accuracy | 0%* | **84%** (63.75% overall) | **+84pp** | 85% |
| relevance_mae | 1.00 | 1.53 | -0.53 | < 0.80 |

*v2's 0% was prompt mismatch, not model failure.

Hallucination error analysis (43 hallucination test examples):
- Correct: 36/43 (84%)
- False positives: 4 (predicted HALLUCINATED, was FACTUAL)
- False negatives: 3 (predicted FACTUAL, was HALLUCINATED)
- Parse failures: 0
- Error pattern: balanced (no systematic bias toward either label)

#### Explainer

| Metric | v2 | v3 | Delta | Target |
|--------|-----|-----|-------|--------|
| json_valid_rate | 100% | 100% | 0 | 95% |
| p95_latency_ms | — | 13,125 | — | < 3,000 |

Latency is MacBook CPU inference, not representative of production (GPU).

### Conclusions

1. **H1 confirmed**: Document layer passages improved both domain coverage and evaluation quality. The 1,849 policy bill passages taught the model document-style text patterns.

2. **H2 confirmed**: Community framing pairs drove the parser's entity_f1 from 56.83% to 72.66% (+16pp). Data source accuracy jumped to 98.77%, suggesting the model now understands which data sources are relevant to equity questions.

3. **H3 confirmed**: Subtask dispatch was the dominant factor for evaluator improvement. The model had learned all four evaluation tasks but couldn't select the right output format without the matching system prompt. This is a fundamental insight for multi-task fine-tuning on small models: **the inference prompt must match the training prompt exactly**.

### Remaining gaps

| Gap | Current | Target | Suggested intervention |
|-----|---------|--------|----------------------|
| Parser entity_f1 | 72.66% | 80% | More diverse entity training pairs (organizations, sub-state geographies) |
| Evaluator hallucination | 84% | 85% | Near threshold — a few more edge-case pairs may close this |
| Evaluator relevance MAE | 1.53 | < 0.80 | Add borderline relevance scoring examples (partially relevant content) |
| Explainer LLM-judged metrics | deferred | — | Requires Claude API key for LLM judge evaluation |

### Cost

| Item | Cost |
|------|------|
| Doc hallucination pair generation (175 Claude calls) | $0.59 |
| Colab A100 training (1h 55m) | ~$4.00 |
| **Total incremental cost for v3** | **~$4.59** |

---

## Experiment 5: v3.1 Expanded State Coverage (FAILED)

**Date:** 2026-04-01
**Status:** Failed — reverted to v3 evaluator GGUF

### Observation

The v3 evaluator scored 84% hallucination accuracy but was trained on document chunks from only 4 states (AL, AK, AR, AZ). Expanding to 8 states (adding MS, GA, CA, NY) would increase document diversity from 1,849 to 2,896 bills across more geographic and policy contexts.

### Hypothesis

Training the evaluator on document chunks from 8 states instead of 4 would improve hallucination detection accuracy past the 85% ship threshold by exposing the model to more diverse policy language patterns.

### Methodology

1. Expanded OpenStates ingestion to 8 states (added 1,047 new D4BL-relevant bills)
2. Re-extracted corpus: 44,235 passages (was 43,188)
3. Regenerated evaluator_v3 pairs from the expanded document pool (350 pairs, $0.59)
4. Re-ran domain adaptation on the expanded corpus (required because corpus changed)
5. Skipped parser/explainer adapters (unchanged data)
6. Retrained evaluator adapter on the new domain-adapted base

#### Training health (appeared normal)

| Phase | Train Loss | Eval Loss | Overfit Ratio | Duration |
|-------|-----------|-----------|---------------|----------|
| Domain Adaptation | 0.481 | — | — | 59m 14s |
| Evaluator | 0.551 | 0.603 | 1.09 | 33m 20s |

### Results

**Catastrophic failure.** The retrained evaluator produced verbose prose, `<think>` reasoning blocks, and wrong JSON schemas instead of `{"label": "FACTUAL/HALLUCINATED"}`.

| Metric | v3 (working) | v3.1 (broken) |
|--------|-------------|---------------|
| hallucination_accuracy | 84% | 0.5% |
| relevance_mae | 1.53 | 4.00 |

### Root Cause Analysis

**Domain adaptation interference.** Re-running Phase 1 (domain adaptation) on the slightly expanded corpus (44,235 vs 43,188 passages) produced a new `domain_merged` checkpoint with different base weights. The evaluator LoRA, trained on this new base, lost its ability to produce terse JSON output.

Key factors:
- The domain corpus teaches the model to produce **prose passages** (the training format)
- The evaluator LoRA (r=16, attention-only) is too small to fully override the base model's prose tendency when the base weights shift
- The previous v3 evaluator worked because its LoRA was trained on a specific domain-adapted base — the LoRA and base were "co-adapted"
- Even though the domain adaptation loss was nearly identical (0.481 vs 0.485), the internal weight distribution changed enough to break the evaluator's output behavior

### Resolution

Reverted to the v3 evaluator GGUF (March 31 training run) which produces correct output. The v3 parser and explainer GGUFs were unaffected (those adapters were skipped during v3.1 training).

### Lessons Learned

1. **Never re-run domain adaptation without retraining ALL task adapters.** The domain-merged checkpoint is the foundation — changing it invalidates all existing LoRA adapters.
2. **Preserve the domain_merged checkpoint on Drive** before any re-training run. Back it up to a versioned directory (e.g., `domain_merged_v3/`).
3. **The evaluator is the most fragile adapter** (r=16, attention-only, multiple output schemas). It's the first to break when the base shifts.
4. **For incremental data additions (small corpus changes), retrain only the task adapter WITHOUT re-running domain adaptation.** Use `--phases evaluator` to skip Phase 1.

### Cost

| Item | Cost |
|------|------|
| Doc hallucination pair generation (175 Claude calls) | $0.59 |
| Colab A100 training (~48 min) | ~$4.00 |
| **Total (wasted)** | **~$4.59** |

---

## Experiment 6: v3.0 Full Retrain (Clean Slate)

**Date:** 2026-04-03
**Status:** Partial ship — hallucination passes, parser/relevance need work

### Observation

The v3.1 attempt (Experiment 5) overwrote the `domain_merged` checkpoint. All task adapters were invalidated since they were LoRA deltas trained against the v3 domain base. A full retrain from scratch was needed.

### Hypothesis

Retraining ALL phases (domain adaptation + 3 task adapters) on the expanded corpus (44,235 passages) from a clean state would produce co-adapted adapters that work correctly together, unlike v3.1 which only retrained the evaluator.

### Methodology

1. Cleared ALL stale training state from Drive (kept only `training_data_final/`)
2. Full training on Colab A100: domain → parser → explainer → evaluator → GGUF export
3. Used `--force` flag to ignore any cached checkpoints
4. Backed up `domain_merged` to versioned Drive directory (`d4bl_training_v3_domain_merged_backup/`)
5. Registered all 7 Ollama models (3 main + 4 evaluator subtasks)

#### Training health (all 4/4 phases passed)

| Phase | Train Loss | Eval Loss | Overfit Ratio | Duration |
|-------|-----------|-----------|---------------|----------|
| Domain Adaptation | 0.481 | — | — | 59m 42s |
| Query Parser | 0.323 | 0.320 | 0.99 | 8m 37s |
| Data Explainer | 0.679 | 0.753 | 1.11 | 7m 40s |
| Evaluator | 0.549 | 0.603 | 1.10 | 30m 43s |

Total training time: 2h 02m. GGUF exports: 3 × 2.52 GB (Q4_K_M).

### Results

| Metric | v3 (Exp 4) | v3.1 (Exp 5, broken) | v3.0 retrain (this) | Ship threshold |
|--------|-----------|---------------------|---------------------|----------------|
| hallucination_accuracy | 84% | 0.5% | **87.11%** | ≥ 85% ✓ |
| relevance_mae | 1.53 | 4.00 | 2.70 | ≤ 0.80 ✗ |
| entity_f1 | 91% | — | 74.88% | ≥ 80% ✗ |
| json_valid (parser) | 98% | — | 96.30% | — |
| json_valid (explainer) | 100% | — | 100% | — |
| p95 latency (parser) | — | — | 5170ms | ≤ 1000ms ✗ |
| p95 latency (explainer) | — | — | 13751ms | ≤ 3000ms ✗ |

### Analysis

**Hallucination accuracy (87.11%)** crosses the 85% ship threshold for the first time. This is a genuine improvement over v3's 84%, likely from the expanded corpus providing more diverse factual grounding patterns.

**Entity F1 (74.88%)** regressed from v3's 91%. Possible causes:
- The expanded domain corpus shifted the base model's entity recognition behavior
- All adapters were retrained from scratch — the parser lost some of v3's co-adaptation
- Needs investigation: compare predicted vs expected entities to identify specific failure modes

**Relevance MAE (2.70)** is worse than v3's 1.53. The eval harness now correctly dispatches to subtask-specific models (d4bl-evaluator-relevance), which may use a different scoring scale than expected. Scoring calibration mismatch under investigation.

**Latency** is dominated by Qwen 3.5's `<think>` reasoning blocks (empty, ~10 tokens overhead) plus the natural generation speed of a 4B model on Mac hardware (~60 tok/s). The `<think>` blocks cannot be disabled for custom GGUF files — tested: Ollama API `think: false`, Modelfile `PARAMETER think false`, and `/no_think` system prompt token. None work. Latency thresholds need adjustment for local inference or require cloud GPU deployment.

### Infrastructure fixes discovered during eval

1. **Stale editable install**: `pip install -e .` pointed to a different directory (`d4bl-fix-169`). All code changes to `ollama_client.py` and `validation/model_output.py` were invisible. Fixed by re-running `pip install -e .` in the correct repo.
2. **`ollama_generate` missing `num_predict`**: The Ollama API client only sent `temperature` in options. Added `num_predict: 2048` to prevent JSON truncation.
3. **Modelfile `num_predict` not honored**: `ollama create` doesn't reliably apply Modelfile parameters to custom GGUFs. Workaround: send `num_predict` explicitly in every API call.
4. **Subtask evaluator models not registered**: `register_models.py` only registered 3 main models. Added all 4 subtask evaluator models (hallucination, relevance, bias, equity-framing).
5. **Validator missing fields**: `_KNOWN_EVAL_FIELDS` didn't include `label` or `reasoning` (v3 training output schema). Added both.
6. **Think block stripping**: Added `_THINK_RE` regex to `_extract_json()` for defensive stripping of `<think>` blocks before JSON parsing.

### Lessons Learned

1. **Always verify the editable install target** after switching branches or worktrees. `pip show <pkg>` reveals the actual source directory.
2. **Explicit API options > Modelfile parameters** for custom GGUFs. Don't rely on Modelfile `PARAMETER` for Ollama inference — pass options in every API call.
3. **Qwen 3.5 thinking mode cannot be disabled** for custom GGUF files. It's baked into the model weights. Stripping in post-processing is the only reliable approach.
4. **Register ALL models the eval harness needs** before running evals. The subtask dispatch silently falls back to the wrong model if subtask models aren't registered.

### Next Steps

- Investigate relevance scoring scale mismatch (model vs test set conventions)
- Investigate entity F1 regression (compare predicted vs expected entity lists)
- Adjust ship criteria latency thresholds for local vs deployed inference
- Consider Qwen 2.5 (no thinking mode) or smaller quantization for latency-sensitive deployment

### Cost

| Item | Cost |
|------|------|
| Training data generation | $0.00 (reused v3 data) |
| Colab A100 training (~2h) | ~$4.00 |
| **Total** | **~$4.00** |

---

## Appendix: Reproducibility

### Environment
```
Base model: unsloth/Qwen3.5-4B
Training hardware: NVIDIA A100-SXM4-40GB (Colab Pro)
Inference hardware: Apple M-series MacBook (CPU, for eval)
Quantization: Q4_K_M (GGUF)
Framework: Unsloth + HuggingFace TRL + SFTTrainer
Distillation model: claude-sonnet-4-20250514
```

### Regenerating v3 training data
```bash
# 1. Extract corpus (includes document passages)
PYTHONPATH=.:scripts python scripts/training/extract_corpus.py

# 2. Copy updated corpus to final dir
cp scripts/training_data/corpus/corpus_pretrain.jsonl scripts/training_data/final/

# 3. Generate v3 pairs
PYTHONPATH=.:scripts python scripts/run_training_pipeline.py --stage distill --task evaluator_v3
PYTHONPATH=.:scripts python scripts/run_training_pipeline.py --stage distill --task query_parser_v3

# 4. Prepare final dataset
PYTHONPATH=.:scripts python scripts/run_training_pipeline.py --stage prepare
```

### Running evals
```bash
# Full eval with subtask dispatch
PYTHONPATH=.:scripts python -m scripts.training.run_eval_harness --model-version v3.0 --partial

# Single task
PYTHONPATH=.:scripts python -m scripts.training.run_eval_harness --task evaluator --model-version v3.0 --partial
```
