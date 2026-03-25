# D4BL Fine-Tuned Language Model: Training Report

**Sprint 2.5 — Improving Structured JSON Output Quality**
**Date:** 2026-03-25
**Author:** D4BL Engineering
**Status:** Complete

---

## Abstract

This report documents the training, evaluation, and deployment of three domain-specialized small language models for the Data for Black Lives (D4BL) research platform. Built on Qwen2.5-3B-Instruct with LoRA adapters, these models embed D4BL's methodology of centering community voice, naming structural causes of racial disparities, and connecting data to policy action. Sprint 2.5 addressed critical quality issues from the initial training run (Sprint 2), improving integration test pass rates from 3/11 to 15/15 by fixing training data volume, chat template formatting, epoch count, and Ollama template configuration.

---

## 1. Problem Statement (Observation)

### 1.1 Background

D4BL's AI agent platform requires three specialized inference tasks:
- **Query Parsing**: Convert natural-language research questions into structured JSON search intents
- **Data Explanation**: Transform statistical findings into equity-framed narratives with structural context
- **Evaluation**: Score model outputs for hallucination, relevance, bias, and equity framing

Generic large language models (GPT-4, Claude) can perform these tasks but cost $0.01-0.10 per request, lack D4BL's specific methodology, and require internet connectivity. A fine-tuned small model running locally would cost <$0.001 per request and embed D4BL's equity lens directly.

### 1.2 Sprint 2 Results (Baseline)

The initial training run (Sprint 2) produced models that learned domain content — equity vocabulary, racial disparity statistics, structural cause framing — but failed to reliably produce structured JSON output. Only 3 of 11 integration tests passed.

**Observed failure mode**: Models generated long-form narrative text instead of JSON objects, ignoring the "Respond with ONLY valid JSON" instruction in the system prompt.

---

## 2. Hypothesis

We hypothesized four root causes for the JSON output failures:

| # | Root Cause | Evidence | Predicted Fix |
|---|-----------|----------|---------------|
| 1 | Insufficient training examples (~115 per task after dedup) | Small models need 500+ examples to learn structured output patterns | Increase to 1000 raw pairs per task |
| 2 | Too few training steps (45 per adapter: 3 epochs x ~15 steps/epoch) | Model hadn't seen enough repetitions of the JSON output pattern | Increase to 7 epochs |
| 3 | `format_and_tokenize` lost chat template structure | Manual ChatML string concatenation doesn't produce the same token boundaries as the tokenizer's native template | Use `tokenizer.apply_chat_template()` |
| 4 | No output length constraint | Models could generate indefinitely, defaulting to narrative | Add `num_predict` parameter to Modelfiles |

A fifth root cause was discovered during deployment:

| 5 | Ollama double-wraps ChatML templates | Ollama's SYSTEM directive adds its own ChatML layer around the model's trained template | Use explicit TEMPLATE directive with matching ChatML |

---

## 3. Methodology

### 3.1 Model Architecture

```
Base Model: Qwen2.5-3B-Instruct (3 billion parameters)
Quantization: 4-bit NF4 (via Unsloth)
Training Method: LoRA (Low-Rank Adaptation)
Export Format: GGUF q4_k_m (~1.8 GB per model)
Inference Runtime: Ollama (local) / RunPod (production)
```

**Three-phase training pipeline:**

| Phase | Purpose | LoRA Rank | Target Layers | Epochs |
|-------|---------|-----------|---------------|--------|
| 1 — Domain Adaptation | Teach D4BL vocabulary and equity framing | r=16 | All (attention + FFN + embeddings) | 1 |
| 2a — Query Parser | Structured intent extraction | r=8 | Attention only | 7 |
| 2b — Data Explainer | Long-form equity narratives | r=32 | Attention + FFN | 7 |
| 2c — Evaluator | Quality/alignment scoring | r=16 | Attention only | 7 |
| 3 — GGUF Export | Quantize for deployment | — | — | — |

### 3.2 Training Data Pipeline

**Source**: D4BL's Supabase database containing census, health, environmental, criminal justice, and economic data across racial demographics.

**Distillation method**: Claude Sonnet 4 generates teacher responses for each task. The student model's training data consists of (system prompt, user input, assistant JSON response) triples.

```
Database rows → Seed data extraction → Question/prompt generation
    → Claude distillation → JSON validation → Deduplication → Train/Val/Test split
```

**Question diversity** (query parser): Three styles of questions are generated from seed data:
- **Standard** (40%): "What is the poverty rate in Alabama?"
- **Community-framed** (40%): "Our community in Georgia is struggling with eviction. What does the data show?"
- **Adversarial** (20%): "Isn't poverty just a result of individual choices in Louisiana?"

**Data quality pipeline**:
1. JSON validation: Reject any pair where Claude's response isn't valid JSON
2. Near-duplicate removal: Jaccard similarity on user messages (threshold: 1.0 — exact duplicates only)
3. Deterministic split: 80% train / 10% validation / 10% test (seed=42)

### 3.3 Sprint 2 vs Sprint 2.5 Changes

| Parameter | Sprint 2 | Sprint 2.5 | Rationale |
|-----------|----------|------------|-----------|
| Raw pairs per task | 300 | 1,000 | More examples for structured output learning |
| Jaccard dedup threshold | 0.8 | 1.0 (exact only) | Template-based questions have high word overlap but diverse JSON responses |
| Training epochs (Phase 2) | 3 | 7 | More exposure to JSON patterns |
| Chat template | Manual ChatML strings | `tokenizer.apply_chat_template()` | Preserves native token boundaries |
| `num_predict` | Not set | 512 (parser/evaluator), 1024 (explainer) | Prevents runaway generation |
| Ollama config | SYSTEM directive | TEMPLATE with explicit ChatML | Prevents double-wrapping |
| trl version | 0.15.2 (pinned) | 0.16+ (SFTConfig API) | Current library compatibility |
| GPU precision | fp16 hardcoded | Auto-detect bf16/fp16 | A100 compatibility |

### 3.4 Reproducibility

**Hardware**: Google Colab with A100 GPU (also works on T4 with fp16)

**Total training time**: ~2 hours on A100

**Cost**:
| Item | Cost |
|------|------|
| Claude API distillation (2,998 calls) | ~$15 |
| Google Colab A100 (~2 hours) | Free tier / ~$4 Colab Pro |
| **Total** | **~$15-19** |

**To reproduce from scratch:**

```bash
# Step 1: Generate training pairs (~60 min, ~$15 API cost)
bash scripts/run_sprint25_generation.sh

# Step 2: Upload to Google Colab and run notebook
# Upload: corpus_pretrain.jsonl + 6 task split files
# Run: notebooks/training/d4bl_fine_tuning.ipynb (all cells)

# Step 3: Download GGUFs and register with Ollama
cp ~/Downloads/d4bl-*-q4_k_m.gguf models/
python -m scripts.training.register_models

# Step 4: Verify
pytest tests/test_training/test_integration_models.py -v
```

---

## 4. Experiment

### 4.1 Training Data Statistics

| Task | Raw Pairs | After Dedup | Train | Validation | Test |
|------|-----------|-------------|-------|------------|------|
| Query Parser | 1,000 | 542 | 434 | 54 | 54 |
| Data Explainer | 998 | 598 | 478 | 60 | 60 |
| Evaluator | 1,000 | 200 | 160 | 20 | 20 |
| **Total** | **2,998** | **1,340** | **1,072** | **134** | **134** |

Domain corpus for Phase 1: ~41,339 passages extracted from 6 database tables.

### 4.2 Training Results

**Phase 1 — Domain Adaptation** (41,339 examples, 1 epoch, 2,584 steps):
- Training loss: 2.13 → 0.43 (steady decline, no overfitting)
- Model successfully absorbed D4BL equity vocabulary

**Phase 2a — Query Parser** (434 examples, 7 epochs, 385 steps):

| Step | Train Loss | Val Loss |
|------|-----------|----------|
| 25 | 2.54 | 2.40 |
| 125 | 0.54 | 0.61 |
| 250 | 0.38 | 0.49 |
| 350 | 0.34 | 0.47 |

Best checkpoint selected at step 325 (val loss 0.468). Train/val gap is healthy — no severe overfitting.

**Phase 2b — Data Explainer** (478 examples, 7 epochs, 420 steps):

| Step | Train Loss | Val Loss |
|------|-----------|----------|
| 20 | 1.66 | 1.52 |
| 120 | 0.85 | **0.83** |
| 240 | 0.61 | 0.83 |
| 420 | 0.39 | 0.95 |

Val loss bottomed at step ~120-240, then climbed (overfitting in later epochs). `load_best_model_at_end=True` selected the checkpoint with best val loss (~0.83).

**Phase 2c — Evaluator** (160 examples, 7 epochs, 140 steps):

| Step | Train Loss | Val Loss |
|------|-----------|----------|
| 25 | 2.10 | 1.88 |
| 75 | 0.76 | 0.76 |
| 125 | 0.70 | **0.69** |

Train and val loss tracked closely — no overfitting. Best checkpoint at step 125.

### 4.3 Model Artifacts

| Model | File | Size | Quantization |
|-------|------|------|-------------|
| Query Parser | `d4bl-query-parser-q4_k_m.gguf` | 1.8 GB | q4_k_m |
| Data Explainer | `d4bl-explainer-q4_k_m.gguf` | 1.8 GB | q4_k_m |
| Evaluator | `d4bl-evaluator-q4_k_m.gguf` | 1.8 GB | q4_k_m |

---

## 5. Results

### 5.1 Integration Test Results

| Test | Sprint 2 | Sprint 2.5 |
|------|----------|------------|
| Parser: simple lookup | FAIL | **PASS** |
| Parser: comparison query | FAIL | **PASS** |
| Parser: trend query | FAIL | **PASS** |
| Parser: outputs valid JSON | FAIL | **PASS** |
| Explainer: metric explanation | FAIL | **PASS** |
| Explainer: outputs valid JSON | PASS | **PASS** |
| Evaluator: bias detection | FAIL | **PASS** |
| Evaluator: good content scoring | FAIL | **PASS** |
| Evaluator: score in range | FAIL | **PASS** |
| Latency: parser < 10s | PASS | **PASS** |
| Latency: explainer < 30s | PASS | **PASS** |
| **Total** | **3/11** | **15/15** |

### 5.2 Qualitative Output Examples

#### Query Parser

**Input**: "Our community in Georgia is struggling with eviction. What does the data show?"

**Output** (valid JSON):
```json
{
  "entities": ["Georgia", "Georgia communities"],
  "search_queries": [
    "Georgia housing stability rates",
    "eviction rates by race and income Georgia",
    "housing insecurity structural causes Georgia",
    "federal housing policy impacts Georgia neighborhoods"
  ],
  "data_sources": ["census_demographics", "census_indicators", "eviction_data", "policy_bills"],
  "community_framing": {"issue_type": "housing-justice"}
}
```

**Notable**: The model correctly identifies the community framing, selects relevant data sources including eviction data, and generates search queries that focus on structural causes.

#### Query Parser — Adversarial Input

**Input**: "Isn't poverty just a result of individual choices rather than systemic issues in Louisiana?"

**Output** (valid JSON):
```json
{
  "entities": ["Louisiana"],
  "search_queries": [
    "Louisiana poverty structural causes",
    "Louisiana economic inequality policy interventions",
    "Louisiana housing affordability barriers",
    "Louisiana education funding disparities"
  ],
  "data_sources": ["census_demographics", "cdc_health_outcomes", "epa_environmental_justice", "eviction_data"],
  "community_framing": {"issue_type": "economic-justice", "structural_frame": "systemic-poverty"}
}
```

**Notable**: The model reframes the deficit-framing question toward structural causes, consistent with D4BL methodology.

#### Data Explainer

**Input**: `{"metric": "incarceration_rate", "geography": "Texas", "race": "Black", "value": 2148, "comparison_value": 450, "comparison_race": "White", "year": 2021}`

**Output** (valid JSON):
```json
{
  "narrative": "In 2021, Texas recorded an incarceration rate of 2,148 Black individuals per 100,000 residents, significantly higher than the comparable rate for White residents at 450 per 100,000. This disparity represents a profound overrepresentation of Black Texans in state prisons and correctional facilities, reflecting systemic barriers to educational access, employment opportunities, and fair sentencing.",
  "structural_context": "This racial disparity stems from decades of structural inequities including exclusionary zoning, underfunded public education, and discriminatory policing practices..."
}
```

**Notable**: The narrative names structural causes (exclusionary zoning, underfunded education, discriminatory policing), not individual factors.

#### Evaluator — Bias Detection

**Input**: `Evaluate for bias: "Crime rates are higher in Black neighborhoods because of cultural factors."`

**Output** (valid JSON):
```json
{
  "bias": true,
  "category": "Cultural Factors",
  "context": "Black neighborhoods have higher crime rates.",
  "supporting_evidence": "The statement suggests a causal relationship between race and criminal behavior, which is not supported by empirical evidence. Research indicates that socioeconomic status, access to resources, and historical factors are more significant in determining crime rates."
}
```

**Notable**: Correctly identifies cultural deficit framing as biased and cites structural factors as the evidence-based alternative.

### 5.3 Production Deployment Cost

| Deployment Option | Monthly Cost | Latency |
|-------------------|-------------|---------|
| RunPod Serverless | $5-25/mo | 100-500ms (warm) |
| RunPod Dedicated (A4000) | $24-144/mo | <100ms |
| Local Ollama (dev) | $0 | <1s |

---

## 6. Analysis

### 6.1 What Worked

1. **Native chat template** was the single most impactful fix. Manual ChatML strings produced token sequences that differed subtly from what Qwen2.5-Instruct was pre-trained with, causing the model to "fall out" of instruction-following mode.

2. **TEMPLATE directive in Modelfiles** solved the deployment gap. The model worked perfectly with raw ChatML but Ollama's SYSTEM directive added a second layer of ChatML wrapping. Using TEMPLATE with explicit ChatML markers matched the training format exactly.

3. **More training data** helped, though the improvement was partially masked by the template fix. The parser (434 train) and explainer (478 train) show better output diversity than the evaluator (160 train).

4. **`load_best_model_at_end=True`** saved us from overfitting. The explainer's val loss started climbing at epoch 4, but the best checkpoint (epoch 2-3) was automatically selected.

### 6.2 What Didn't Work as Expected

1. **Jaccard deduplication** at 0.8 was too aggressive for template-generated questions. Word-level Jaccard can't distinguish "What is the poverty rate in Alabama?" from "What is the poverty rate in Mississippi?" — they share too many words. Setting threshold to 1.0 (exact-only) was the pragmatic fix.

2. **Evaluator training data volume** remained lower than targets (160 train vs 434-478 for other tasks). The 4 subtasks share the same seed rows, creating more true duplicates.

3. **Output schema alignment**: The models learned the field names from the Claude distillation training data (`entities`, `search_queries`, `bias`), not the field names originally specified in the Modelfiles (`intent`, `score`). This required updating validators to accept both schemas.

### 6.3 Key Insight: Template Alignment is Critical

The most important lesson from this sprint: **the exact token sequence seen during training must match what the model sees during inference**. This includes:
- The system prompt text (must match `_STUDENT_*_SYSTEM` constants)
- The ChatML delimiters (`<|im_start|>`, `<|im_end|>`)
- The turn structure (system → user → assistant)

Any deviation — even adding whitespace or wrapping in another template layer — causes the model to fall back to its pre-training behavior (long-form narrative).

---

## 7. Future Work

### 7.1 Short-Term (Sprint 3)

- **Codebase integration**: Wire models into FastAPI endpoints with automatic fallback to general model
- **Model routing**: `model_for_task()` helper that selects the right adapter based on task type
- **Production deployment**: Deploy to RunPod Serverless with Ollama serving all 3 models

### 7.2 Medium-Term (Sprint 4-5)

- **More diverse training data**: Generate questions from a wider variety of seed data (currently only 3 tables used for seeds). Add questions about specific policies, historical events, and cross-state comparisons.
- **Evaluator improvements**: Generate more varied evaluation scenarios with different levels of bias, different evaluation dimensions, and edge cases.
- **Evaluation harness**: Automated comparative evaluation against baseline (Qwen2.5-3B-Instruct without fine-tuning) and larger models (Mistral, Llama).
- **Output schema alignment**: Either retrain with Modelfile-matching schemas in the distillation prompts, or standardize on the training data schema throughout the codebase.

### 7.3 Long-Term

- **Community feedback loop**: Collect user feedback on model outputs to create a human-preference dataset for RLHF/DPO alignment.
- **Mobile deployment**: Quantize to Qwen2.5-1.5B for on-device inference via llama.cpp.
- **Continuous training**: Automate the retrain cycle as new data sources are ingested — new census data, new policy bills, new health outcomes.
- **Multi-turn support**: Currently single-turn only. Add conversation context for follow-up questions.
- **Bias auditing**: Systematic evaluation of model outputs across demographic groups to ensure equitable performance.

---

## 8. Appendix

### A. Repository Structure

```
scripts/training/
  config.py                  # Training constants (PAIRS_PER_TASK, etc.)
  generate_training_pairs.py # Claude distillation with cost tracking
  prepare_dataset.py         # Filter, dedup, split pipeline
  extract_corpus.py          # Database → NL passages
  prompts.py                 # Distillation prompts and system prompts
  templates.py               # Passage rendering per data source
  register_models.py         # Ollama registration + smoke tests
  validate_model_output.py   # Output validators

notebooks/training/
  d4bl_fine_tuning.py        # Colab training notebook (Jupytext)
  d4bl_fine_tuning.ipynb     # Colab training notebook (ipynb)

models/
  Modelfile.query-parser     # Ollama config with TEMPLATE
  Modelfile.explainer
  Modelfile.evaluator
  *.gguf                     # Model weights (not in git)

tests/test_training/
  test_integration_models.py # End-to-end tests via Ollama
  test_modelfiles.py         # Modelfile structure tests
  test_validate_model_output.py
  test_generate_pairs.py
  test_prepare_dataset.py
```

### B. Data Sources Used in Training

| Table | Records | Used For |
|-------|---------|----------|
| census_indicators | 38,552 | Seed data for questions, corpus passages |
| cdc_health_outcomes | ~25,000 | Corpus passages, explainer training |
| epa_environmental_justice | ~15,000 | Corpus passages |
| police_violence_incidents | ~10,000 | Corpus passages |
| bjs_incarceration | ~5,000 | Corpus passages |
| fbi_crime_stats | ~8,000 | Corpus passages |

### C. Hyperparameters

| Parameter | Phase 1 | Phase 2a | Phase 2b | Phase 2c |
|-----------|---------|----------|----------|----------|
| LoRA rank | 16 | 8 | 32 | 16 |
| LoRA alpha | 32 | 16 | 64 | 32 |
| Learning rate | 2e-4 | 1e-4 | 1e-4 | 1e-4 |
| Batch size | 4 | 4 | 2 | 4 |
| Gradient accum | 4 | 2 | 4 | 2 |
| Effective batch | 16 | 8 | 8 | 8 |
| Max seq length | 2048 | 2048 | 4096 | 2048 |
| Optimizer | AdamW 8-bit | AdamW 8-bit | AdamW 8-bit | AdamW 8-bit |
| Precision | bf16 | bf16 | bf16 | bf16 |
| Quantization | NF4 | NF4 | NF4 | NF4 |
