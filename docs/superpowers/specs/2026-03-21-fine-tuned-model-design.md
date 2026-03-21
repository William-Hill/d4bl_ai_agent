# D4BL Fine-Tuned Language Model — Design Specification

**Date:** 2026-03-21
**Status:** Draft
**Author:** D4BL Engineering

## Executive Summary

D4BL is building a domain-specialized small language model for racial equity data analysis. Rather than relying on generic models that treat racial disparities as edge cases, we will fine-tune Qwen2.5-3B with LoRA adapters that embed D4BL's methodology — centering community voice, naming structural causes, connecting to policy action, and acknowledging data limitations.

The model handles three tasks: query parsing (NL → structured intent), data explanation (metrics → equity-framed narratives), and evaluation (output → quality/alignment scores). A smaller 1.5B sibling model enables on-device mobile inference.

**Key decisions:**
- **Base model:** Qwen2.5-3B-Instruct (best performance-per-parameter at this size)
- **Training method:** LoRA fine-tuning via Unsloth on free Google Colab T4
- **Training data:** Distillation from Claude using D4BL's Supabase data
- **Deployment:** Ollama (local dev) → RunPod (production) → llama.cpp (mobile)
- **Methodology:** D4BL's Community Engagement → Power Building cycle embedded in training data, output schemas, and evaluation criteria

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Key Concepts (Educational Reference)](#2-key-concepts)
3. [Training Data Pipeline](#3-training-data-pipeline)
4. [Training Pipeline](#4-training-pipeline)
5. [Deployment Architecture](#5-deployment-architecture)
6. [Evaluation Harness](#6-evaluation-harness)
7. [Educational Page & Deliverables](#7-educational-page--deliverables)
8. [D4BL Methodology Integration](#8-d4bl-methodology-integration)
9. [PRD Summary](#9-prd-summary)

---

## 1. Architecture Overview

### Model Architecture

```
┌─────────────────────────────────────────────────┐
│              Qwen2.5-3B-Instruct                │
│            (Domain Base Model)                   │
│                                                  │
│  Continued pre-training on D4BL corpus           │
│  (equity terminology, data source schemas,       │
│   indicator definitions, geographic codes)        │
└──────────┬──────────┬──────────┬────────────────┘
           │          │          │
    ┌──────▼──┐ ┌─────▼────┐ ┌──▼──────────┐
    │ LoRA A  │ │ LoRA B   │ │ LoRA C      │
    │ Query   │ │ Explain  │ │ Evaluate    │
    │ Parser  │ │ Narrator │ │ (4 heads)   │
    └─────────┘ └──────────┘ └─────────────┘
         │           │             │
         ▼           ▼             ▼
    NL → JSON   Rows → JSON   Content → Scores
```

### Two-Stage Training

1. **Continued pre-training** (optional but valuable) — Feed the base Qwen2.5-3B the ingested data corpus so it learns equity domain vocabulary, indicator names, FIPS codes, racial categories, data source schemas. Unsupervised next-token prediction.
2. **LoRA fine-tuning** — Task-specific adapters trained on input/output pairs generated via distillation from Claude.

### Runtime

Load the base model once, swap LoRA adapters per task. In Ollama, this means separate model entries sharing the same base weights.

### Model Matrix

| Model | Size | Target | Tasks |
|-------|------|--------|-------|
| Qwen2.5-3B Q4_K_M | 1.8GB | Cloud + Local | All 3 adapters (parser, explainer, evaluator) |
| Qwen2.5-1.5B Q4_K_M | 0.9GB | Mobile | Parser + evaluator (lightweight) |
| mistral (existing) | 4.1GB | Cloud + Local | CrewAI agents (fallback) |
| mxbai-embed-large | 0.7GB | Cloud + Local | Embeddings (unchanged) |

---

## 2. Key Concepts

This section serves as both technical documentation and source material for the educational page and slide deck.

### 2.1 What is Fine-Tuning?

A pre-trained model like Qwen2.5-3B has already learned language from trillions of tokens. Fine-tuning is like hiring a generalist researcher and then training them specifically on racial equity data. They already know how to read and write — you're teaching them your domain and your tasks.

Three levels:

| Level | What Changes | Analogy |
|-------|-------------|---------|
| Continued pre-training | Updates all weights with raw text | Reading 100 books on equity before starting the job |
| Full fine-tuning | Updates all weights with task examples | Intensive on-the-job training for every skill |
| LoRA fine-tuning | Updates only small added layers | Learning a specific procedure while keeping all prior knowledge intact |

### 2.2 What is LoRA?

**Low-Rank Adaptation.** A 3B parameter model has billions of weight values. Full fine-tuning updates all of them — expensive and risks "catastrophic forgetting" (the model gets good at your task but forgets how to do everything else).

LoRA's insight: **task-specific knowledge can be captured in a much smaller matrix.** Instead of updating the full weight matrix W (say, 4096×4096 = 16M values), LoRA decomposes the update into two tiny matrices: A (4096×16) and B (16×4096). That's only 131K values — 99.2% fewer parameters to train.

```
Original:     output = W × input          (16M parameters, frozen)
LoRA update:  output = W × input + B×A × input  (131K parameters, trained)
```

**Practical implications:**
- Training is fast — minutes instead of hours
- Adapters are tiny — ~10-50MB vs 6GB for the full model
- You can swap them — one base model, multiple adapters for different tasks
- No forgetting — the original weights are frozen

**Rank** controls adapter capacity:

| Rank | Adapter Size (3B model) | Good For |
|------|------------------------|----------|
| 8 | ~5 MB | Simple classification (hallucination: yes/no) |
| 16 | ~10 MB | Structured extraction (query parsing) |
| 32 | ~20 MB | Generation tasks (equity narratives) |
| 64 | ~40 MB | Complex multi-step reasoning |

**Target modules** — which weight matrices get LoRA adapters:

```python
# Attention layers — how the model focuses
"q_proj", "k_proj", "v_proj", "o_proj"

# Feed-forward layers — what the model computes
"gate_proj", "up_proj", "down_proj"

# Embedding layers — how the model represents tokens
"embed_tokens", "lm_head"
```

For structured extraction (query parser), attention-only is sufficient. For generation (explainer), include feed-forward layers for more capacity.

**Alpha** scales the LoRA update. Rule of thumb: `alpha = 2 × rank`. So rank 16 → alpha 32. Higher alpha = more adapter influence relative to frozen base weights.

### 2.3 What is Quantization?

Models store each weight as a number. Full precision uses 16 bits per weight (FP16). Quantization reduces the bits per weight:

| Format | Bits | 3B Model Size | Quality Loss | Use Case |
|--------|------|---------------|-------------|----------|
| FP16 | 16 | ~6 GB | None | Training |
| Q8_0 | 8 | ~3 GB | Negligible | High-quality inference |
| Q4_K_M | 4 | ~1.8 GB | Small | **Our target** |
| Q2_K | 2 | ~1 GB | Noticeable | Extreme edge cases |

**Q4_K_M** uses two techniques:
- **K-means quantization**: Instead of uniformly spacing the 16 possible 4-bit values, clusters the actual weight distribution and picks optimal bucket centers
- **Mixed precision (M)**: Critical layers (first/last attention, embeddings) get 5-6 bits; middle layers get 4 bits

This is why Q4_K_M loses almost nothing on structured output tasks like JSON generation.

### 2.4 GGUF Format

GGUF (GPT-Generated Unified Format) packages model weights, tokenizer, and metadata into a single file. Ollama uses GGUF natively.

Pipeline: Train in PyTorch (FP16) → Convert to GGUF → Quantize to Q4_K_M → Load in Ollama.

Unsloth handles this entire conversion automatically.

### 2.5 Tokenization

Qwen2.5 uses a tokenizer with ~150K vocabulary entries. Domain-specific terms matter:

```
Generic tokenizer might split:
  "Environmental justice" → ["Environ", "mental", " justice"]  (3 tokens)

Well-trained tokenizer may have:
  "Environmental justice" → ["Environmental", " justice"]  (2 tokens)
```

Qwen2.5's tokenizer is large enough that most equity terms are already single or two tokens. Continued pre-training helps the model learn that compound concepts like "environmental justice" have specific domain meaning.

### 2.6 Distillation

Using a large "teacher" model (Claude) to generate training data for a small "student" model (Qwen2.5-3B).

```
D4BL Supabase data  →  Claude (teacher)  →  Gold-standard outputs
                                                    ↓
                                            Training pairs (JSONL)
                                                    ↓
                                          Qwen2.5-3B + LoRA (student)
```

### 2.7 Training Data Quality > Quantity

For LoRA fine-tuning:

| Task Complexity | Examples Needed |
|----------------|----------------|
| Binary classification (hallucination) | 100-200 |
| Structured extraction (query parsing) | 200-500 |
| Short generation (explain endpoint) | 300-500 |
| Long generation (research synthesis) | 500-1000 |

200 carefully crafted, diverse, edge-case-covering examples outperform 2000 noisy ones.

### 2.8 Transformer Architecture (Reference)

A transformer is a stack of repeating layers (Qwen2.5-3B has 36). Each layer:

```
Input tokens
     ↓
┌─────────────────────┐
│  Self-Attention      │  "Which other words should I pay attention to?"
│  (Q, K, V matrices) │  ← LoRA inserts adapters here
└─────────┬───────────┘
          ↓
┌─────────────────────┐
│  Feed-Forward Net    │  "What do I compute from what I attended to?"
│  (Up, Gate, Down)    │  ← LoRA can also target these
└─────────┬───────────┘
          ↓
     Next layer...
```

Self-attention lets the word "gap" in "racial wealth gap" look back at "racial" and "wealth" to understand the compound concept. The Q, K, V matrices control this and are the primary LoRA targets.

---

## 3. Training Data Pipeline

### 3.1 Stage 1: Domain Corpus Extraction (Continued Pre-Training)

Pull raw data from Supabase and convert to natural language text for unsupervised pre-training.

**Example transformation:**

```
Supabase row:                       Natural language passage:
─────────────                       ──────────────────────────
census_indicators                   "In Alabama (FIPS 01), the median
  fips: 01000                        household income for Black residents
  race: black                        was $35,400 in 2022, with a margin
  metric: median_household_income    of error of ±$1,200."
  value: 35400
  margin_of_error: 1200
  year: 2022
```

**What this teaches the model:**
- FIPS code structure and meaning
- Indicator names and units (rates vs. counts vs. percentiles)
- Racial categories and how they're reported
- Geographic hierarchies (state → county → tract)
- Domain vocabulary ("margin of error," "age-adjusted rate," "disparity ratio")

**Volume:** ~50K-100K text passages, 50-150 tokens each, totaling 5-10M tokens of domain text.

**Data sources to template:**

| Table | Template Focus |
|-------|---------------|
| census_indicators | Income, poverty, homeownership by race and state |
| cdc_health_outcomes | Health measures by county with confidence intervals |
| epa_environmental_justice | EJ indicators by tract with percentile rankings |
| police_violence_incidents | Incident descriptions with demographics |
| bjs_incarceration | Incarceration rates by state, race, gender |
| fbi_crime_stats | Arrest and hate crime data by state and race |
| bls_labor_statistics | Employment metrics by race |
| doe_civil_rights | School discipline by race and district |
| census_demographics | Population by race at multiple geographic levels |
| policy_bills | Legislation with topic tags and status |
| eviction_data | Eviction rates with demographic context |
| traffic_stops | Stop, search, and arrest rates by race |
| vera_incarceration | County-level incarceration trends |

### 3.2 Stage 2: Task-Specific Training Pairs (Distillation)

For each LoRA adapter, use Claude to generate gold-standard input/output pairs from real data.

**Distillation system prompt (applied to all pair generation):**

```
You are generating training data for a racial equity research model
built by Data for Black Lives (D4BL).

Your outputs must:
1. Center affected communities, not abstract statistics
2. Name structural and historical causes of disparities
3. Connect findings to actionable policy interventions
4. Acknowledge data limitations and collection biases
5. Be accessible to community organizers, not just academics
6. Never frame racial disparities as innate or cultural —
   always connect to systems and structures
```

#### Adapter A: Query Parser (300-500 pairs)

**Input:** Natural language question
**Output:** Structured JSON intent

```json
{
  "input": "Why are Black families in Atlanta being pushed out of their neighborhoods?",
  "output": {
    "entities": ["Black families", "Atlanta", "displacement", "gentrification"],
    "search_queries": [
      "gentrification displacement Black communities Atlanta",
      "eviction rates race Atlanta Georgia",
      "housing affordability racial disparities Atlanta metro"
    ],
    "data_sources": ["structured", "vector"],
    "community_framing": {
      "detected": true,
      "issue_domain": "housing_justice",
      "structural_frame": "gentrification_displacement"
    }
  }
}
```

**Training data categories:**
- Standard research queries (100-150)
- Community-voiced queries (100) — written in the language communities use to describe problems
- Multi-domain / ambiguous queries (50-100)
- All data source types represented (50-100)
- Out-of-domain queries (25) — should gracefully decline
- Adversarial queries (25) — prompt injection, SQL injection attempts

#### Adapter B: Data Explainer (300-500 pairs)

**Input:** Structured data context with register parameter
**Output:** Equity-framed narrative JSON

```json
{
  "input": {
    "source": "census_acs",
    "metric": "median_household_income",
    "state": "Mississippi",
    "state_fips": "28",
    "year": 2022,
    "value": 48610,
    "national_average": 74580,
    "racial_breakdown": {"white": 56200, "black": 32400, "hispanic": 41800},
    "disparity_ratio": 1.73,
    "disparity_label": "White-to-Black",
    "register": "community"
  },
  "output": {
    "narrative": "Black families in Mississippi bring home $32,400 a year — nearly $24,000 less than White families in the same state. That's not a gap in effort. It's the result of decades of policy choices: underfunded schools, discriminatory lending, and jobs that pay less in communities where Black people live.",
    "structural_context": "Mississippi's racial income disparity is rooted in post-Reconstruction sharecropping systems, Jim Crow-era exclusion from GI Bill benefits and FHA lending, and ongoing occupational segregation. The state has the highest percentage of Black residents (38%) and the lowest median income nationally — a correlation driven by systematic disinvestment, not coincidence.",
    "methodology_note": "Based on American Community Survey 5-year estimates (2018-2022). Median income represents the midpoint — half of households earn more, half less. Dollar amounts are not adjusted for Mississippi's lower cost of living.",
    "data_limitations": [
      "Census income data captures only reported income — missing informal economy, which disproportionately supports excluded communities",
      "Margin of error is larger for smaller racial populations, making some estimates less reliable",
      "Hispanic ethnicity overlaps with racial categories in Census methodology",
      "Income alone does not capture wealth (assets minus debts), where the Black-White gap is 6:1 nationally"
    ],
    "caveats": [
      "ACS 5-year estimates smooth over recent changes — a 2022 policy impact wouldn't show until 2025+ data",
      "State-level median masks significant county-level variation"
    ],
    "policy_connections": [
      {
        "domain": "economic_equity",
        "policy_levers": [
          "Earned Income Tax Credit expansion",
          "Minimum wage increase (MS has no state minimum)",
          "Workforce development targeting historically excluded communities"
        ],
        "relevant_legislation": []
      }
    ]
  }
}
```

**Register variations — same data, three audiences:**

| Register | Tone | Reading Level | Example Opening |
|----------|------|--------------|-----------------|
| `community` | Direct, personal, structural framing | Grade 8-10 | "Black families in Mississippi bring home $32,400 a year — nearly $24,000 less than White families..." |
| `policy` | Formal, actionable, intervention-focused | Grade 12-14 | "Mississippi exhibits a White-to-Black income disparity ratio of 1.73. Targeted interventions — EITC expansion, state minimum wage legislation..." |
| `research` | Academic, methodological, citation-ready | Grade 14-16 | "Analysis of ACS 5-year estimates (2018-2022) reveals a persistent racial income disparity in Mississippi (White-to-Black ratio: 1.73, 95% MOE ±$1,200)..." |

#### Adapter C: Evaluator (600 pairs, 4 sub-tasks)

All sub-tasks share one adapter, differentiated by system prompt prefix.

**Hallucination detection (200 pairs):**
```json
{
  "task": "HALLUCINATION",
  "input": {"context": "...", "answer": "..."},
  "output": {"label": "FACTUAL|HALLUCINATED", "explanation": "..."}
}
```

**Relevance scoring (200 pairs):**
```json
{
  "task": "RELEVANCE",
  "input": {"query": "...", "content": "..."},
  "output": {"score": 1-5, "explanation": "..."}
}
```

**Bias detection (100 pairs):**
```json
{
  "task": "BIAS",
  "input": {"query": "...", "output": "..."},
  "output": {"bias_score": 1-5, "feedback": "..."}
}
```

**D4BL equity framing (100 pairs):**
```json
{
  "task": "EQUITY_FRAMING",
  "input": {"query": "...", "model_output": "..."},
  "output": {
    "score": 1-5,
    "centers_community": true,
    "names_structural_causes": true,
    "connects_to_policy": false,
    "acknowledges_data_limits": true,
    "feedback": "Output correctly identifies the disparity but frames it as a 'cultural gap' rather than connecting to redlining and disinvestment."
  }
}
```

### 3.3 Stage 3: Data Quality & Split

```
Raw pairs from Claude
       ↓
┌──────────────────┐
│  Quality Filter   │  Remove malformed JSON, hallucinated facts,
│                   │  inconsistent scores
└──────┬───────────┘
       ↓
┌──────────────────┐
│  Deduplication    │  Remove near-duplicate questions
│                   │  (Jaccard similarity > 0.8)
└──────┬───────────┘
       ↓
┌──────────────────┐
│  Train/Val/Test   │  80% train / 10% validation / 10% test
│  Split            │  Stratified by data source and task type
└──────┬───────────┘
       ↓
  Final JSONL files:
  ├── corpus_pretrain.jsonl        (50K+ passages)
  ├── query_parser_train.jsonl     (240-400 pairs)
  ├── query_parser_val.jsonl       (30-50 pairs)
  ├── query_parser_test.jsonl      (30-50 pairs)
  ├── explainer_train.jsonl        (240-400 pairs)
  ├── explainer_val.jsonl          (30-50 pairs)
  ├── explainer_test.jsonl         (30-50 pairs)
  ├── evaluator_train.jsonl        (480 pairs)
  ├── evaluator_val.jsonl          (60 pairs)
  └── evaluator_test.jsonl         (60 pairs)
```

### 3.4 Training Data Format (ChatML)

All training data uses ChatML format, which Qwen2.5 natively supports:

```json
{
  "messages": [
    {"role": "system", "content": "You are a query parser for D4BL..."},
    {"role": "user", "content": "What's the Black-White income gap in Georgia?"},
    {"role": "assistant", "content": "{\"entities\": [...], ...}"}
  ]
}
```

One JSON object per line in the JSONL file.

---

## 4. Training Pipeline

All training runs on a free Google Colab T4 GPU (16GB VRAM).

### 4.1 Environment Setup

```
Google Colab Notebook
├── GPU: T4 (16GB VRAM) — free tier
├── RAM: 12.7GB system
├── Storage: ~80GB (model + data + outputs)
│
├── Install:
│   pip install unsloth
│   pip install --no-deps trl peft accelerate bitsandbytes
│   pip install supabase
│
└── Authenticate:
    - Hugging Face token (download Qwen2.5-3B, upload fine-tuned model)
    - Supabase credentials (pull training data)
```

### 4.2 Phase 1: Continued Pre-Training (Domain Vocabulary)

**Goal:** Teach the base model equity domain vocabulary before any task-specific training.

**Before continued pre-training:**
- Model sees "FIPS 28" → meaningless tokens
- Model sees "disparity ratio" → vague understanding

**After continued pre-training:**
- Model sees "FIPS 28" → Mississippi
- Model sees "disparity ratio" → structural inequality metric

```python
from unsloth import FastLanguageModel

# Load base model in 4-bit (QLoRA)
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Qwen2.5-3B-Instruct",
    max_seq_length=2048,
    dtype=None,           # Auto-detect (float16 on T4)
    load_in_4bit=True,    # QLoRA — 3B model fits in ~2GB VRAM
)

# Add LoRA adapters to all layers (including embeddings for vocabulary)
model = FastLanguageModel.get_peft_model(
    model,
    r=16,                 # Rank 16 — good for domain adaptation
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",     # Attention
        "gate_proj", "up_proj", "down_proj",          # Feed-forward
        "embed_tokens", "lm_head",                    # Embeddings (new vocab)
    ],
    lora_alpha=32,        # Alpha = 2 × rank
    lora_dropout=0,       # Unsloth optimized
    use_gradient_checkpointing="unsloth",  # 60% less VRAM
)
```

**Hyperparameter explanations:**

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `r=16` | Rank 16 | Enough capacity for domain vocabulary without overfitting on 50K passages |
| `target_modules` includes `embed_tokens`, `lm_head` | Unusual for task training | Critical for continued pre-training — this is where new token representations are learned |
| `lora_alpha=32` | 2 × rank | LoRA update scaled by alpha/rank = 2.0 — good balance for domain adaptation |
| `load_in_4bit=True` | QLoRA | Frozen base weights in 4-bit NF4, LoRA adapters in float16. 3B model fits on 16GB T4 |

```python
from trl import SFTTrainer
from transformers import TrainingArguments

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=domain_corpus,
    dataset_text_field="text",
    max_seq_length=2048,
    args=TrainingArguments(
        per_device_train_batch_size=4,   # T4 VRAM limit
        gradient_accumulation_steps=4,   # Effective batch = 16
        warmup_steps=50,                 # Gentle learning rate ramp
        num_train_epochs=1,              # Single pass — avoid overfitting
        learning_rate=2e-4,              # Standard for LoRA CPT
        fp16=True,                       # Half-precision on T4
        logging_steps=10,
        output_dir="outputs/domain_cpt",
        optim="adamw_8bit",             # 30% VRAM savings
        seed=42,
    ),
)
trainer.train()
```

**Training argument explanations:**

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `batch_size=4` | 4 examples per GPU step | T4 VRAM constraint |
| `gradient_accumulation=4` | 4 steps before weight update | Effective batch of 16 for training stability |
| `warmup_steps=50` | LR ramps up over 50 steps | Prevents early instability from large gradients |
| `epochs=1` | Single pass through corpus | Domain adaptation doesn't need multiple passes |
| `learning_rate=2e-4` | 0.0002 | Standard LoRA rate. Too high = forgetting, too low = no learning |
| `fp16=True` | Half-precision | 2× faster, fits in T4 VRAM |
| `adamw_8bit` | 8-bit optimizer | Saves ~30% VRAM vs full precision |

**Duration:** ~30-45 minutes on T4 for 50K passages.
**Output:** LoRA adapter weights (~40MB) encoding domain knowledge.

### 4.3 Phase 2: Task-Specific LoRA Training

Each adapter trains on top of the domain-adapted base.

#### Adapter A: Query Parser

```python
# Load domain-adapted model (base + CPT adapter merged)
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="outputs/domain_cpt/merged",
    max_seq_length=2048,
    load_in_4bit=True,
)

# Fresh LoRA — smaller rank, attention-only
model = FastLanguageModel.get_peft_model(
    model,
    r=8,                  # Rank 8 — sufficient for JSON extraction
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
    ],                    # Attention only — parsing needs focus, not new computation
    lora_alpha=16,
    lora_dropout=0,
)
```

**Why rank 8 and attention-only?** Query parsing is structured extraction — the model needs to learn *what to attend to* in the question. It doesn't need new computational patterns (feed-forward) or new vocabulary (embeddings). Lower rank = faster training, smaller adapter, less overfitting risk.

```python
trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=query_parser_train,
    args=TrainingArguments(
        per_device_train_batch_size=4,
        gradient_accumulation_steps=2,    # Effective batch = 8
        warmup_steps=20,
        num_train_epochs=3,               # Small datasets need multiple passes
        learning_rate=1e-4,               # Lower than CPT — fine-grained
        fp16=True,
        logging_steps=5,
        output_dir="outputs/query_parser",
        optim="adamw_8bit",
        evaluation_strategy="steps",
        eval_steps=25,                    # Check val loss every 25 steps
        load_best_model_at_end=True,      # Revert to best checkpoint
        seed=42,
    ),
)
```

**Key differences from Phase 1:**
- `epochs=3`: Small datasets (300 examples) need multiple passes; validation loss monitors overfitting
- `learning_rate=1e-4`: Half of CPT rate — more precise adjustments within an already-adapted model
- `eval_steps=25`: Checks validation loss every 25 steps; `load_best_model_at_end` reverts if overfitting

**Duration:** ~15-20 minutes on T4 for 300 examples × 3 epochs.

#### Adapter B: Data Explainer

```python
model = FastLanguageModel.get_peft_model(
    model,
    r=32,                 # Higher rank — generation needs more capacity
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",   # FFN included for generation
    ],
    lora_alpha=64,
)
```

**Why rank 32 with FFN layers?** The explainer generates multi-paragraph narratives with structural context, policy connections, and register-appropriate tone. The model needs to:
1. Understand the data (attention layers)
2. Compose novel equity-framed text (feed-forward layers)
3. Maintain consistent voice across registers (higher rank for expressiveness)

```python
trainer = SFTTrainer(
    model=model,
    train_dataset=explainer_train,
    args=TrainingArguments(
        per_device_train_batch_size=2,    # Larger outputs = more VRAM
        gradient_accumulation_steps=4,    # Effective batch = 8
        warmup_steps=30,
        num_train_epochs=3,
        learning_rate=1e-4,
        max_seq_length=4096,              # Longer outputs need bigger context
        fp16=True,
        output_dir="outputs/explainer",
        evaluation_strategy="steps",
        eval_steps=20,
        load_best_model_at_end=True,
    ),
)
```

**Duration:** ~30-40 minutes on T4.

#### Adapter C: Evaluator (Multi-Task)

```python
model = FastLanguageModel.get_peft_model(
    model,
    r=16,                 # Mid-range — classification + short generation
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
    ],
    lora_alpha=32,
)
```

**Why one adapter for 4 tasks?** All are classification/scoring tasks with similar structure (input text → JSON with score + explanation). A shared adapter learns the general evaluation pattern. The system prompt steers which lens to apply. More parameter-efficient than 4 separate adapters, and the tasks reinforce each other.

Training data mixes all four sub-tasks (hallucination, relevance, bias, equity framing), shuffled randomly so the model learns to distinguish by system prompt.

**Duration:** ~20-25 minutes on T4.

### 4.4 Phase 3: Export & Quantize

```python
# Merge LoRA into base weights and export to GGUF
model.save_pretrained_gguf(
    "outputs/query_parser/gguf",
    tokenizer,
    quantization_method="q4_k_m",
)
```

**What happens during GGUF export:**

```
LoRA Adapter (40MB, float16)
  + Base Model (6GB, 4-bit during training)
       ↓
  Merge: W_new = W_base + (B × A) × (alpha/rank)
       ↓
  Full merged model (6GB, float16)
       ↓
  Quantize to Q4_K_M (k-means clustering, mixed precision)
       ↓
  Final GGUF file (~1.8GB)
```

**Output:** Three self-contained GGUF files:

```
outputs/
├── d4bl-query-parser-q4_k_m.gguf     (~1.8GB)
├── d4bl-explainer-q4_k_m.gguf        (~1.8GB)
└── d4bl-evaluator-q4_k_m.gguf        (~1.8GB)
```

### 4.5 Training Monitoring

**What to watch:**

```
Step  Train Loss  Val Loss   Status
────  ──────────  ────────   ──────
  10     2.45       2.50     Normal — learning
  50     1.20       1.25     Good — converging
  75     0.85       0.92     Watch — gap appearing
 100     0.60       0.95     Overfitting — val loss rising

→ load_best_model_at_end picks step 75's checkpoint
```

**Key metrics:**
- Train loss: Should decrease steadily
- Val loss: Should track train loss; divergence = overfitting
- JSON validity rate: Target >95% parseable outputs
- Task accuracy: Correct entities, required fields present

### 4.6 Complete Training Timeline

```
Day 1: Data extraction + distillation
  └── Extract data from Supabase
  └── Generate 50K corpus passages (scripted)
  └── Generate 300 query parser pairs via Claude
  └── Generate 300 explainer pairs via Claude
  └── Generate 600 evaluator pairs via Claude

Day 2: Training
  └── Phase 1: Continued pre-training (~45 min)
  └── Phase 2a: Query parser adapter (~20 min)
  └── Phase 2b: Explainer adapter (~35 min)
  └── Phase 2c: Evaluator adapter (~25 min)
  └── Phase 3: GGUF export (~10 min)

Day 3: Testing + iteration
  └── Load in Ollama, test against real queries
  └── Compare to current mistral outputs
  └── Identify weak spots, add targeted examples
  └── Retrain (incremental — ~15 min per adapter)
```

---

## 5. Deployment Architecture

### 5.1 Local Development (Ollama)

Each model registered via a Modelfile:

```dockerfile
# Modelfile.query-parser
FROM ./d4bl-query-parser-q4_k_m.gguf

PARAMETER temperature 0.1
PARAMETER num_ctx 2048
PARAMETER stop "<|im_end|>"

SYSTEM """You are a query parser for D4BL, a racial equity research platform.
Parse user questions into structured search intents.
Respond with ONLY valid JSON."""
```

```bash
ollama create d4bl-query-parser -f Modelfile.query-parser
ollama create d4bl-explainer    -f Modelfile.explainer
ollama create d4bl-evaluator    -f Modelfile.evaluator
```

**Request routing:**

```
FastAPI checks task type
    ↓
Query parsing?  → d4bl-query-parser
Explain view?   → d4bl-explainer
Evaluation?     → d4bl-evaluator
CrewAI agents?  → mistral (unchanged)
Embeddings?     → mxbai-embed-large (unchanged)
```

### 5.2 Production Deployment Options

#### Option A: RunPod Dedicated GPU (Recommended for start)

- GPU: RTX A4000 (16GB) at $0.20/hr
- Ollama server with all models loaded
- Exposed via HTTPS reverse proxy with API key auth
- **Cost:** ~$24/month (4hr active/day) to ~$144/month (always on)

#### Option B: RunPod Serverless (Cheapest for low traffic)

- Pay-per-request: ~$0.00018/request
- Cold start: 15-30s, warm: 100-500ms
- Scales to zero
- **Cost:** ~$5.40/month at 1000 requests/day

#### Option C: Hugging Face Inference Endpoints (Most managed)

- OpenAI-compatible API (works with existing LiteLLM setup)
- T4 at $0.60/hr with scale-to-zero
- Model versioning built in
- **Cost:** ~$72/month at 4hr active/day

**Recommended progression:** Start with RunPod Serverless → upgrade to dedicated if cold starts are a problem.

### 5.3 Integration with Existing Code

Minimal code changes — the Ollama API is the same:

```python
# Current
response = ollama_generate(prompt, model="mistral")

# Updated
response = ollama_generate(prompt, model="d4bl-query-parser")
```

For cloud, `OLLAMA_BASE_URL` already supports remote instances:

```bash
# Local dev
OLLAMA_BASE_URL=http://localhost:11434

# Production
OLLAMA_BASE_URL=https://your-runpod-id.runpod.ai
```

### 5.4 Fallback Strategy

```python
async def parse_query(query: str) -> ParsedIntent:
    try:
        response = await ollama_generate(
            prompt=query,
            model="d4bl-query-parser",
            timeout=10,
        )
        result = json.loads(response)
        validate_parsed_intent(result)
        return result
    except (json.JSONDecodeError, ValidationError, TimeoutError):
        logger.warning("Fine-tuned parser failed, falling back to mistral")
        response = await ollama_generate(
            prompt=PARSER_PROMPT + query,
            model="mistral",
            timeout=30,
        )
        return json.loads(response)
```

### 5.5 Model Registry & Versioning

Hugging Face Hub (free for public models):

```
d4bl-org/query-parser-v1.0
├── model card (training data, metrics, limitations)
├── GGUF files (q4_k_m, q8_0)
├── training config (hyperparameters, data version)
└── eval results (accuracy, latency, comparison)
```

### 5.6 Mobile / On-Device Inference

#### Hardware Requirements

| Device | RAM | Can Run Q4 3B? | Can Run Q4 1.5B? |
|--------|-----|----------------|------------------|
| iPhone 15 Pro+ | 8GB | Yes, tight | Yes, comfortable |
| iPhone 16 Pro | 8GB | Yes | Yes |
| Pixel 9 Pro | 12-16GB | Yes | Yes |
| Mid-range Android (6-8GB) | 6-8GB | Marginal | Yes |
| Older phones (4-6GB) | 4-6GB | No | Marginal |

#### Memory Budget (3B on iPhone 16 Pro)

```
Model weights:          ~1.8 GB
KV cache:               ~200-400 MB
Runtime overhead:       ~200 MB
Total needed:           ~2.2-2.4 GB
Available (8GB - OS):   ~4-5 GB
Headroom:               ~1.6-2.8 GB  ✅
```

#### Inference Speed

| Model | iPhone 16 Pro | Pixel 9 Pro | Mid-range Phone |
|-------|--------------|-------------|-----------------|
| Qwen2.5-3B Q4 | ~15-25 tok/s | ~10-20 tok/s | ~5-10 tok/s |
| Qwen2.5-1.5B Q4 | ~30-50 tok/s | ~20-30 tok/s | ~15-25 tok/s |

For query parser output (~50-100 tokens): 1.5B on iPhone = 1-3 seconds.

#### Recommended Mobile Architecture: Hybrid

```
┌─────────────────────────────────────────────────────┐
│                   MOBILE APP                         │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  On-Device (Qwen2.5-1.5B Q4_K_M, 0.9GB)     │   │
│  │  via llama.cpp (Swift/Kotlin bindings)         │   │
│  │                                                │   │
│  │  ✅ Query parsing (instant, offline-capable)   │   │
│  │  ✅ Quick relevance scoring (offline)          │   │
│  │  ⚠️ Short explanations (offline fallback)     │   │
│  └──────────────────────────────────────────────┘   │
│                      │                               │
│                      ↓ (if online)                   │
│  ┌──────────────────────────────────────────────┐   │
│  │  Cloud API (Qwen2.5-3B via Ollama)            │   │
│  │                                                │   │
│  │  ✅ Full equity narratives                    │   │
│  │  ✅ Policy connections                        │   │
│  │  ✅ Comprehensive evaluation                  │   │
│  │  ✅ CrewAI research pipeline                  │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  Local Cache (SQLite)                         │   │
│  │  Cached narratives, pre-computed state_summary│   │
│  │  Enables meaningful offline experience         │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

#### Mobile Inference Framework: llama.cpp

llama.cpp runs any GGUF model — same file format as Ollama. No conversion needed.

```
Training pipeline produces GGUF
         ↓
    Same file used by:
    ├── Ollama (local dev)
    ├── Ollama on RunPod (cloud prod)
    └── llama.cpp on mobile (on-device)
```

#### Training Impact

None — the pipeline is identical. Train on both 3B and 1.5B:

```
Same training data → Train on Qwen2.5-3B → cloud GGUF
Same training data → Train on Qwen2.5-1.5B → mobile GGUF
Both in same Colab notebook, ~30 min extra
```

The 1.5B model may need slightly more training examples for the explainer task to compensate for less base capacity.

### 5.7 Full Deployment Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    LOCAL DEV                             │
│                                                          │
│  Next.js (3000) → FastAPI (8000) → Ollama (11434)       │
│                                      ├── d4bl-query-parser│
│                                      ├── d4bl-explainer   │
│                                      ├── d4bl-evaluator   │
│                                      ├── mistral (fallback)│
│                                      └── mxbai-embed-large│
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                   PRODUCTION                             │
│                                                          │
│  Vercel/Railway         RunPod (GPU)                     │
│  ┌──────────────┐      ┌────────────────────────┐       │
│  │ Next.js      │      │  Ollama Server          │       │
│  │ (Frontend)   │      │  ├── d4bl-query-parser  │       │
│  └──────┬───────┘      │  ├── d4bl-explainer     │       │
│         │              │  ├── d4bl-evaluator     │       │
│  ┌──────▼───────┐      │  ├── mistral (fallback) │       │
│  │ FastAPI      │──────│  └── mxbai-embed-large  │       │
│  │ (Backend)    │ HTTPS│                          │       │
│  └──────────────┘      └────────────────────────┘       │
│                                                          │
│  Supabase (Vector DB + Auth)                             │
│  PostgreSQL (Job storage + eval results)                 │
│  Langfuse (Observability)                                │
│  HuggingFace Hub (Model Registry)                        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                   MOBILE                                 │
│                                                          │
│  ┌──────────────────────────────────────────────┐       │
│  │  iOS / Android App                            │       │
│  │  ├── llama.cpp (Qwen2.5-1.5B, on-device)    │       │
│  │  ├── SQLite (cached data)                     │       │
│  │  └── Cloud API (Qwen2.5-3B, when online)     │       │
│  └──────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────┘
```

---

## 6. Evaluation Harness

### 6.1 Evaluation Dimensions

```
                    ┌─────────────────────────┐
                    │     Eval Dimensions      │
                    └─────────────────────────┘
                               │
        ┌──────────┬───────────┼───────────┬──────────┐
        ↓          ↓           ↓           ↓          ↓
   Correctness  Latency   D4BL Alignment  Cost    Robustness
```

### 6.2 Test Set Design

Hold out 10% of training data — never trained on.

**Query parser test set (30-50 examples):**
- Standard research queries (15)
- Community-voiced queries (10)
- Ambiguous / multi-domain queries (10)
- Out-of-domain queries (5)
- Adversarial queries (5)

**Explainer test set (30-50 examples):**
- States with large disparities (10)
- States with small disparities (5)
- Multiple data sources (10)
- All three registers (10)
- Edge cases: missing data, suppressed estimates (5)

**Evaluator test set (60 examples):**
- Hallucination: clear factual (10), clear hallucinated (10)
- Relevance: high (5), medium (5), low (5)
- Bias: unbiased (5), subtly biased (5), overtly biased (5)
- Equity framing: aligned (5), misaligned (5)

### 6.3 Metrics Per Adapter

#### Query Parser Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| json_valid_rate | % outputs that parse as valid JSON | >95% |
| schema_valid_rate | % valid JSON matching expected schema | >90% |
| entity_f1 | Harmonic mean of precision and recall on entities | >0.85 |
| data_source_accuracy | % correct structured vs. vector routing | >85% |
| community_framing_f1 | Precision/recall on community voice detection | >0.70 |
| p50_latency_ms | Median response time | <500ms |
| p95_latency_ms | 95th percentile response time | <1000ms |
| adversarial_pass_rate | % adversarial inputs handled safely | >85% |

#### Explainer Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| json_valid_rate | % valid JSON with all required fields | >95% |
| factual_accuracy | % stated facts verifiable against source | >90% |
| number_accuracy | % cited numbers matching source exactly | >95% |
| centers_community | 1-5: narrative centers affected community | >3.5 |
| names_structural_causes | 1-5: connects to systemic factors | >3.5 |
| connects_to_policy | 1-5: relevant/actionable policy connections | >3.0 |
| acknowledges_limitations | 1-5: honest data limitation statements | >3.5 |
| register_consistency | 1-5: tone matches requested register | >3.0 |
| d4bl_composite | Weighted average of D4BL alignment scores | >3.5 |
| p95_latency_ms | 95th percentile response time | <3000ms |

#### Evaluator Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| hallucination_accuracy | % correct FACTUAL/HALLUCINATED labels | >85% |
| hallucination_f1 | F1 on HALLUCINATED class | >0.80 |
| relevance_mae | Mean absolute error on 1-5 scores | <0.8 |
| relevance_correlation | Spearman rank correlation with ground truth | >0.70 |
| bias_mae | Mean absolute error on 1-5 bias scores | <1.0 |
| equity_framing_accuracy | % correct on each sub-criterion | >80% |

### 6.4 Ship / No-Ship Criteria

Defined before training to prevent post-hoc rationalization:

```python
SHIP_CRITERIA = {
    "query_parser": {
        "json_valid_rate":       {"min": 0.95, "blocking": True},
        "entity_f1":             {"min": 0.80, "blocking": True},
        "data_source_accuracy":  {"min": 0.85, "blocking": True},
        "community_framing_f1":  {"min": 0.70, "blocking": False},
        "p95_latency_ms":        {"max": 1000, "blocking": True},
        "adversarial_pass_rate": {"min": 0.85, "blocking": True},
    },
    "explainer": {
        "json_valid_rate":       {"min": 0.95, "blocking": True},
        "factual_accuracy":      {"min": 0.90, "blocking": True},
        "d4bl_composite":        {"min": 3.5,  "blocking": True},
        "register_consistency":  {"min": 3.0,  "blocking": False},
        "p95_latency_ms":        {"max": 3000, "blocking": True},
    },
    "evaluator": {
        "hallucination_accuracy":{"min": 0.85, "blocking": True},
        "relevance_mae":         {"max": 0.8,  "blocking": True},
        "relevance_correlation": {"min": 0.70, "blocking": False},
        "bias_mae":              {"max": 1.0,  "blocking": True},
    },
}
# blocking=True  → Must pass to ship
# blocking=False → Can ship with known gap + plan to fix
```

### 6.5 Automated Eval Pipeline

```python
# scripts/eval_fine_tuned_model.py

async def run_comparison(
    test_set_path: str,
    base_model: str = "mistral",
    fine_tuned_model: str = "d4bl-query-parser",
    task: str = "query_parser",
) -> ComparisonReport:

    test_examples = load_jsonl(test_set_path)

    base_results = []
    ft_results = []

    for example in test_examples:
        input_text = example["messages"][1]["content"]
        expected = example["messages"][2]["content"]

        # Run both models on same input
        base_output = await ollama_generate(
            prompt=FULL_PARSER_PROMPT + input_text,
            model=base_model,
        )
        base_results.append({...})

        ft_output = await ollama_generate(
            prompt=input_text,
            model=fine_tuned_model,
        )
        ft_results.append({...})

    # Compute metrics and check ship criteria
    base_metrics = compute_metrics(base_results, task)
    ft_metrics = compute_metrics(ft_results, task)
    ship_decision = check_ship_criteria(ft_metrics, SHIP_CRITERIA[task])

    return ComparisonReport(
        base=base_metrics,
        fine_tuned=ft_metrics,
        deltas={k: ft_metrics[k] - base_metrics[k] for k in ft_metrics},
        ship_decision=ship_decision,
    )
```

### 6.6 Regression Testing

Store eval results in the database for version-over-version tracking:

```python
class ModelEvalRun(Base):
    __tablename__ = "model_eval_runs"

    id = Column(UUID, primary_key=True)
    model_name = Column(String)          # "d4bl-query-parser"
    model_version = Column(String)       # "v1.1"
    base_model_name = Column(String)     # "mistral"
    task = Column(String)                # "query_parser"
    test_set_hash = Column(String)       # SHA256 of test set
    metrics = Column(JSONB)
    ship_decision = Column(String)       # "ship" / "no_ship" / "ship_with_gaps"
    blocking_failures = Column(JSONB)
    created_at = Column(DateTime)
```

### 6.7 D4BL Methodology Alignment Scoring

The most novel evaluation dimension — scoring whether outputs follow D4BL principles:

```python
async def score_d4bl_alignment(output: dict, context: dict) -> D4BLAlignmentScore:
    prompt = f"""Score this output on D4BL methodology alignment.

    Context: {json.dumps(context)}
    Output: {json.dumps(output)}

    Score each criterion 1-5:
    1. Centers community
    2. Names structural causes
    3. Connects to policy
    4. Acknowledges limitations
    5. Register appropriateness

    Respond with JSON."""

    response = await ollama_generate(prompt, model="d4bl-evaluator")
    return D4BLAlignmentScore(**json.loads(response))
```

### 6.8 Community Feedback Loop

```
Community uses tool
    ↓
Flags outputs that miss context, misframe issues, or lack actionability
    ↓
Flagged examples become new training data (with corrected outputs)
    ↓
Retrain LoRA adapter (incremental, ~15 min on Colab)
    ↓
Deploy updated model
    ↓
Re-run eval suite (regression check)
    ↓
Community uses improved tool (repeat)
```

---

## 7. Educational Page & Deliverables

### 7.1 Educational Page (`/learn`)

New Next.js route with interactive concept explainers.

**Page structure:**
1. Hero — "Building AI That Centers Community"
2. Interactive concept sections (scrollytelling):
   - What is a Language Model?
   - Why Fine-Tune? (D4BL's case)
   - How LoRA Works (interactive rank slider)
   - How Quantization Works (interactive bit slider)
   - Training Data & Distillation (step-by-step animation)
   - D4BL Methodology in AI (clickable wheel)
   - From Data to Justice (full pipeline)
3. Guided tutorial (Colab notebook links)
4. Eval comparison placeholder (future playground)

**Interactive components:**

| Component | Interaction | What It Teaches |
|-----------|-------------|-----------------|
| `LoRAVisualizer` | Rank slider (8-64) dynamically updates adapter size/percentage | Trade-off between capacity and efficiency |
| `QuantizationSlider` | Bit slider (2-16) shows precision loss, model size, quality impact | Why Q4_K_M is the sweet spot |
| `MethodologyWheel` | Click each D4BL stage to see AI connection | How methodology maps to training |
| `DistillationPipeline` | Step-through animation (play/pause) | How training data is created from real data |
| `RegisterComparison` | Tab toggle (community/policy/research) | Same data, different audiences |

**File structure:**

```
ui-nextjs/
├── app/learn/page.tsx
├── components/learn/
│   ├── ConceptSection.tsx
│   ├── LoRAVisualizer.tsx
│   ├── QuantizationSlider.tsx
│   ├── MethodologyWheel.tsx
│   ├── DistillationPipeline.tsx
│   ├── RegisterComparison.tsx
│   ├── TutorialStep.tsx
│   └── PlaygroundPlaceholder.tsx
```

**Guided tutorial steps:**

| Step | Title | What Users Learn |
|------|-------|-----------------|
| 1 | Understanding Your Data | Query Supabase, see equity data shape |
| 2 | Creating Training Data | Write distillation prompts, generate pairs |
| 3 | Training with Unsloth | Load model, configure LoRA, run training |
| 4 | Testing Your Model | Load in Ollama, compare to base |
| 5 | Making It Your Own | Customize for your community's data |

### 7.2 Gamma Slide Deck

**Deck: "Building AI That Centers Community: D4BL's Fine-Tuned Language Model"**

15-18 slides with D4BL branding (dark theme, neon green #00ff32 accents).

| # | Slide | Content |
|---|-------|---------|
| 1 | Title | "Building AI That Centers Community" |
| 2 | The Problem | Generic AI treats racial equity as edge case |
| 3 | D4BL's Approach | Methodology wheel |
| 4 | What We Built | 17 data sources, 25+ tables |
| 5 | Why a Custom Model | Side-by-side: generic vs. D4BL output |
| 6 | What is Fine-Tuning? | Specialist hire analogy |
| 7 | How LoRA Works | Visual: small adapters, big impact |
| 8 | Our Training Data | Supabase → Claude → training pairs |
| 9 | D4BL Methodology in Training | Each stage maps to training |
| 10 | Three Adapters | Parser, Explainer (registers), Evaluator |
| 11 | Community Voice Recognition | Community-framed question examples |
| 12 | The Register System | Same data, three audiences |
| 13 | Deployment | Laptop → cloud → mobile |
| 14 | Evaluation & Accountability | Ship criteria, alignment scoring |
| 15 | The Feedback Cycle | Community flags → retrain → improve |
| 16 | Educational Resources | /learn page, Colab tutorials, open-source models |
| 17 | What's Next | Mobile app, playground, community training workshops |
| 18 | Call to Action | How to get involved |

### 7.3 PRD

Stored at `docs/superpowers/specs/2026-03-21-fine-tuned-model-prd.md` (separate document).

Key sections: Executive Summary, Goals & Success Metrics, User Stories, D4BL Methodology Integration, Technical Architecture, Phased Rollout, Risks & Mitigations, Educational Deliverables.

---

## 8. D4BL Methodology Integration

### How Each Stage Maps to the Model

| D4BL Stage | Model Feature |
|------------|---------------|
| **Community Engagement** | Training data includes community-voiced queries; register system makes outputs accessible; community feedback becomes training data |
| **Problem Identification** | Query parser recognizes community problem framings ("Why can't our kids just go to school?") and maps to data sources |
| **Data Collection + Analysis** | Explainer adds structural_context and data_limitations to every narrative; acknowledges collection biases |
| **Policy Innovation** | policy_connections field maps metrics to policy levers and relevant legislation |
| **Power Building** | Model as tool for community organizers; open-source on HuggingFace; educational resources for community capacity building |
| **(Repeat)** | Community feedback loop: flags → training data → retrain → improve |

### Distillation System Prompt

All training data generation uses this D4BL-aligned system prompt:

```
You are generating training data for a racial equity research model
built by Data for Black Lives (D4BL).

Your outputs must:
1. Center affected communities, not abstract statistics
2. Name structural and historical causes of disparities
3. Connect findings to actionable policy interventions
4. Acknowledge data limitations and collection biases
5. Be accessible to community organizers, not just academics
6. Never frame racial disparities as innate or cultural —
   always connect to systems and structures
```

This prompt becomes the DNA of the fine-tuned model — every training example carries this framing.

### Equity Framing Evaluator

A novel evaluation dimension that scores D4BL methodology alignment:

```json
{
  "score": 1-5,
  "centers_community": true/false,
  "names_structural_causes": true/false,
  "connects_to_policy": true/false,
  "acknowledges_data_limits": true/false,
  "feedback": "specific improvement suggestions"
}
```

This ensures the model doesn't just produce technically correct output, but output that serves D4BL's mission.

---

## 9. PRD Summary

### Goals

1. **Domain specialization**: D4BL composite alignment score >3.5/5.0
2. **Cost**: <$30/month production inference
3. **Latency**: P95 <1s query parsing, <3s explanations
4. **Accessibility**: Runs on laptop (Ollama), phone (1.5B), cloud (RunPod)

### Phased Rollout

| Phase | Scope | Timeline |
|-------|-------|----------|
| Phase 1 (MVP) | Query parser adapter + eval harness | 3-5 days |
| Phase 2 | Explainer + evaluator adapters | 1 week |
| Phase 3 | Mobile 1.5B model, /learn page, Gamma deck | 2 weeks |
| Phase 4 | Live playground, community feedback loop | Future |

### Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Model reproduces biased framing | Equity alignment evaluator; D4BL-aligned training data |
| Training data insufficient | Start small (300 examples), iterate with community feedback |
| 3B too small for narrative quality | Fallback to mistral; path to 7B if needed |
| Cold start latency in production | RunPod dedicated pod if serverless too slow |
| Mobile memory constraints | 1.5B sibling model at 0.9GB; hybrid cloud architecture |

### Success Criteria

- All blocking ship criteria pass for each adapter
- Measurable improvement over base model on all dimensions
- D4BL methodology alignment score >3.5 composite
- Community feedback incorporated into at least one retraining cycle
- Educational page live with all interactive components
- Stakeholder presentation delivered via Gamma
