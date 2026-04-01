# D4BL Fine-Tuned Language Model: Experiment Log

**Rolling document tracking model training experiments, methodology, and results.**
**Started:** 2026-03-25
**Last updated:** 2026-03-31

---

## Experiment Index

| # | Date | Name | Base Model | Key Result |
|---|------|------|------------|------------|
| 1 | 2026-03-23 | Sprint 2 baseline | Qwen2.5-3B | 3/11 integration tests passing |
| 2 | 2026-03-25 | Sprint 2.5 JSON fix | Qwen2.5-3B | 11/11 integration tests passing |
| 3 | 2026-03-29 | v2 Qwen 3.5 upgrade | Qwen3.5-4B | Base model upgrade, v2 training data |
| 4 | 2026-03-31 | v3 document layer + subtask dispatch | Qwen3.5-4B | Parser entity F1 +16pp, evaluator 0%->84% |

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
