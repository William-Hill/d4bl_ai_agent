# Sprint 2: Model Training Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete training pipeline — a Google Colab notebook for Unsloth/LoRA fine-tuning of Qwen2.5-3B, GGUF export, Ollama Modelfiles for local serving, and integration tests that verify the trained models work end-to-end.

**Architecture:** A single Colab notebook orchestrates three training phases: domain-adaptive LoRA pre-training (vocabulary), task-specific LoRA adapters (parser, explainer, evaluator), and GGUF export. The notebook pulls JSONL training data produced by Sprint 1's pipeline (`scripts/training_data/final/`), trains on a free T4 GPU, and outputs three GGUF files. Locally, three Ollama Modelfiles register these GGUFs as named models. A registration script automates model loading, and integration tests verify each model produces valid outputs via the Ollama API.

**Tech Stack:** Python, Unsloth, TRL, transformers, bitsandbytes, Ollama, GGUF, pytest

**Spec:** `docs/superpowers/specs/2026-03-21-fine-tuned-model-design.md` (Sections 4, 5.1, 5.5)

**Dependencies:** Sprint 1 training data JSONL files (`feature/training-data-pipeline` branch, PR #125). Branch off `feature/training-data-pipeline` or `main` after PR merges. Epic: #124.

**Sprint 1 outputs consumed:**
- `scripts/training_data/corpus/corpus_pretrain.jsonl` — 50K+ domain passages for Phase 1
- `scripts/training_data/final/query_parser_train.jsonl` / `_val.jsonl` — 300 pairs
- `scripts/training_data/final/explainer_train.jsonl` / `_val.jsonl` — 300 pairs
- `scripts/training_data/final/evaluator_train.jsonl` / `_val.jsonl` — 600 pairs (4 sub-tasks: hallucination 200, relevance 200, bias 100, equity framing 100)

**Deferred to Sprint 3 (Integration):**
- `scripts/eval_fine_tuned_model.py` — Automated comparison eval pipeline (Spec Section 9)
- `scripts/validate_parsed_intent.py` — Schema validation for API-layer parser outputs (Spec Section 9)

**Prerequisites from Sprint 1:** `scripts/training/__init__.py` and `tests/test_training/__init__.py` must exist (created in Sprint 1 Task 1).

---

## File Structure

```
notebooks/
└── training/
    └── d4bl_fine_tuning.py        # Colab notebook as .py (Jupytext-compatible)

models/
├── Modelfile.query-parser          # Ollama Modelfile for query parser
├── Modelfile.explainer             # Ollama Modelfile for explainer
└── Modelfile.evaluator             # Ollama Modelfile for evaluator

scripts/
└── training/
    ├── register_models.py          # Load GGUFs into Ollama + verify
    └── validate_model_output.py    # Shared output validation helpers

tests/
└── test_training/
    ├── test_modelfiles.py          # Modelfile content validation
    ├── test_validate_model_output.py  # Unit tests for validation helpers
    └── test_integration_models.py  # Integration tests against Ollama API
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `notebooks/training/.gitkeep`
- Create: `models/.gitkeep`
- Modify: `.gitignore`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p notebooks/training models
```

- [ ] **Step 2: Add output directories and GGUF files to .gitignore**

Append to `.gitignore`:
```
# Training notebooks outputs (large model files)
notebooks/training/outputs/
*.gguf

# Model files (downloaded/generated, large)
models/*.gguf
```

- [ ] **Step 3: Create .gitkeep files**

```bash
touch notebooks/training/.gitkeep models/.gitkeep
```

- [ ] **Step 4: Commit**

```bash
git add notebooks/ models/ .gitignore
git commit -m "chore: scaffold training notebook and model directories"
```

---

## Task 2: Colab Training Notebook — Phase 1 (Domain Adaptation)

**Files:**
- Create: `notebooks/training/d4bl_fine_tuning.py`

This is a Python script formatted for Colab (cell markers with `# %%`). It will be uploaded to Google Colab for execution on a T4 GPU. The full notebook spans Tasks 2-4; each task adds cells for one training phase.

- [ ] **Step 1: Write notebook header and environment setup cells**

```python
# notebooks/training/d4bl_fine_tuning.py
"""D4BL Fine-Tuned Model Training — Google Colab Notebook.

Run on Google Colab with a T4 GPU (free tier).
Trains three LoRA adapters on Qwen2.5-3B-Instruct:
  1. Domain-adaptive pre-training (equity vocabulary)
  2. Task-specific adapters (query parser, explainer, evaluator)
  3. GGUF export for Ollama deployment

Prerequisites:
  - Upload training data JSONL files to Colab (from Sprint 1 pipeline)
  - Hugging Face token for model download (set in Colab secrets)
"""

# %% [markdown]
# # D4BL Fine-Tuned Model Training
#
# This notebook trains three LoRA adapters on Qwen2.5-3B-Instruct for:
# - **Query Parser**: NL questions → structured JSON intents
# - **Data Explainer**: Metrics → equity-framed narratives
# - **Evaluator**: Content → quality/alignment scores
#
# **Runtime:** ~2.5 hours total on T4 GPU

# %% [markdown]
# ## 0. Environment Setup

# %%
# Install dependencies (Unsloth handles torch/CUDA compatibility)
!pip install unsloth
!pip install --no-deps trl peft accelerate bitsandbytes
!pip install huggingface_hub

# %%
import json
import os
from pathlib import Path

from datasets import Dataset
from google.colab import userdata
from huggingface_hub import login
from transformers import TrainingArguments
from trl import SFTTrainer
from unsloth import FastLanguageModel

# Authenticate with Hugging Face (set HF_TOKEN in Colab secrets)
login(token=userdata.get("HF_TOKEN"))

# %%
# Configuration
MAX_SEQ_LENGTH_DOMAIN = 2048
MAX_SEQ_LENGTH_TASK = 2048
MAX_SEQ_LENGTH_EXPLAINER = 4096
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# %% [markdown]
# ## 1. Upload Training Data
#
# Upload the JSONL files produced by Sprint 1's training data pipeline.
# Expected files in the working directory:
# - `corpus_pretrain.jsonl`
# - `query_parser_train.jsonl`, `query_parser_val.jsonl`
# - `explainer_train.jsonl`, `explainer_val.jsonl`
# - `evaluator_train.jsonl`, `evaluator_val.jsonl`

# %%
from google.colab import files

print("Upload training data JSONL files:")
uploaded = files.upload()
print(f"Uploaded {len(uploaded)} files: {list(uploaded.keys())}")

# %%
def load_jsonl(path: str) -> list[dict]:
    """Load a JSONL file into a list of dicts."""
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def load_dataset_from_jsonl(path: str, text_field: str = "text") -> Dataset:
    """Load a JSONL file as a HuggingFace Dataset."""
    records = load_jsonl(path)
    return Dataset.from_list(records)


# Load all datasets
domain_corpus = load_dataset_from_jsonl("corpus_pretrain.jsonl")
print(f"Domain corpus: {len(domain_corpus)} passages")

query_parser_train = load_dataset_from_jsonl("query_parser_train.jsonl")
query_parser_val = load_dataset_from_jsonl("query_parser_val.jsonl")
print(f"Query parser: {len(query_parser_train)} train, {len(query_parser_val)} val")

explainer_train = load_dataset_from_jsonl("explainer_train.jsonl")
explainer_val = load_dataset_from_jsonl("explainer_val.jsonl")
print(f"Explainer: {len(explainer_train)} train, {len(explainer_val)} val")

evaluator_train = load_dataset_from_jsonl("evaluator_train.jsonl")
evaluator_val = load_dataset_from_jsonl("evaluator_val.jsonl")
print(f"Evaluator: {len(evaluator_train)} train, {len(evaluator_val)} val")
```

- [ ] **Step 2: Write Phase 1 domain-adaptive pre-training cells**

Append to the same file:

```python
# %% [markdown]
# ## 2. Phase 1: Domain-Adaptive LoRA Pre-Training
#
# Teach the base model equity domain vocabulary (FIPS codes, disparity
# metrics, indicator names) using unsupervised next-token prediction
# with LoRA adapters.
#
# **Duration:** ~30-45 minutes on T4

# %%
# Load base model in 4-bit (QLoRA)
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Qwen2.5-3B-Instruct",
    max_seq_length=MAX_SEQ_LENGTH_DOMAIN,
    dtype=None,           # Auto-detect (float16 on T4)
    load_in_4bit=True,    # QLoRA — 3B model fits in ~2GB VRAM
)

# %%
# Add LoRA adapters — includes embeddings for new vocabulary learning
model = FastLanguageModel.get_peft_model(
    model,
    r=16,                 # Rank 16 — enough for domain vocabulary
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",     # Attention
        "gate_proj", "up_proj", "down_proj",          # Feed-forward
        "embed_tokens", "lm_head",                    # Embeddings (new vocab)
    ],
    lora_alpha=32,        # Alpha = 2 × rank
    lora_dropout=0,       # Unsloth optimized — dropout handled differently
    use_gradient_checkpointing="unsloth",  # 60% less VRAM
)

# Print trainable parameter count
model.print_trainable_parameters()

# %%
# Train domain adaptation
domain_trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=domain_corpus,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH_DOMAIN,
    args=TrainingArguments(
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,   # Effective batch = 16
        warmup_steps=50,
        num_train_epochs=1,              # Single pass — avoid overfitting
        learning_rate=2e-4,
        fp16=True,
        logging_steps=10,
        output_dir=str(OUTPUT_DIR / "domain_cpt"),
        optim="adamw_8bit",
        seed=42,
        save_steps=500,                  # Checkpoint every 500 steps
        save_total_limit=2,              # Keep only 2 most recent checkpoints
    ),
)

print("Starting Phase 1: Domain-adaptive pre-training...")
domain_stats = domain_trainer.train()
print(f"Phase 1 complete. Final loss: {domain_stats.training_loss:.4f}")

# %%
# Merge domain LoRA into base weights for Phase 2
# This creates a new model with domain knowledge baked in
model.save_pretrained_merged(
    str(OUTPUT_DIR / "domain_cpt" / "merged"),
    tokenizer,
    save_method="merged_16bit",
)
print("Domain-adapted model saved (merged)")

# Free VRAM before Phase 2
import gc
import torch
del model, tokenizer, domain_trainer
gc.collect()
torch.cuda.empty_cache()
print(f"VRAM freed. GPU memory: {torch.cuda.memory_allocated() / 1e9:.1f} GB")
```

- [ ] **Step 3: Commit**

```bash
git add notebooks/training/d4bl_fine_tuning.py
git commit -m "feat: add Colab notebook — environment setup and Phase 1 domain adaptation"
```

---

## Task 3: Colab Training Notebook — Phase 2 (Task-Specific Adapters)

**Files:**
- Modify: `notebooks/training/d4bl_fine_tuning.py`

Three adapters trained on top of the domain-adapted base: query parser (r=8, attention-only), explainer (r=32, attention+FFN), evaluator (r=16, attention-only).

- [ ] **Step 1: Write Adapter A — Query Parser cells**

Append to notebook:

```python
# %% [markdown]
# ## 3. Phase 2: Task-Specific LoRA Adapters
#
# Each adapter trains on the domain-adapted base model.
# Training data uses chat-template formatted JSONL (system + user + assistant).

# %% [markdown]
# ### 3a. Adapter A: Query Parser
#
# Learns to extract structured JSON intents from natural language questions.
# - Rank 8, attention-only (parsing = what to attend to)
# - 3 epochs on ~300 examples
#
# **Duration:** ~15-20 minutes on T4

# %%
# Load domain-adapted model
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=str(OUTPUT_DIR / "domain_cpt" / "merged"),
    max_seq_length=MAX_SEQ_LENGTH_TASK,
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
    use_gradient_checkpointing="unsloth",
)

model.print_trainable_parameters()

# %%
parser_trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=query_parser_train,
    eval_dataset=query_parser_val,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH_TASK,
    args=TrainingArguments(
        per_device_train_batch_size=4,
        gradient_accumulation_steps=2,    # Effective batch = 8
        warmup_steps=20,
        num_train_epochs=3,
        learning_rate=1e-4,               # Lower than CPT — fine-grained
        fp16=True,
        logging_steps=5,
        output_dir=str(OUTPUT_DIR / "query_parser"),
        optim="adamw_8bit",
        evaluation_strategy="steps",
        eval_steps=25,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        seed=42,
        save_steps=25,
        save_total_limit=3,
    ),
)

print("Starting Adapter A: Query Parser...")
parser_stats = parser_trainer.train()
print(f"Query Parser complete. Best val loss: {parser_trainer.state.best_metric:.4f}")

# Save adapter weights (not merged yet — merge at GGUF export time)
model.save_pretrained(str(OUTPUT_DIR / "query_parser" / "adapter"))
tokenizer.save_pretrained(str(OUTPUT_DIR / "query_parser" / "adapter"))
print("Query parser adapter saved")

# Free VRAM
del model, tokenizer, parser_trainer
gc.collect()
torch.cuda.empty_cache()
```

- [ ] **Step 2: Write Adapter B — Data Explainer cells**

Append to notebook:

```python
# %% [markdown]
# ### 3b. Adapter B: Data Explainer
#
# Generates equity-framed narratives from data metrics.
# - Rank 32, attention + FFN (generation needs more capacity)
# - 4096 context (longer outputs)
# - 3 epochs on ~300 examples
#
# **Duration:** ~30-40 minutes on T4

# %%
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=str(OUTPUT_DIR / "domain_cpt" / "merged"),
    max_seq_length=MAX_SEQ_LENGTH_EXPLAINER,
    load_in_4bit=True,
)

model = FastLanguageModel.get_peft_model(
    model,
    r=32,                 # Higher rank — generation needs more capacity
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",   # FFN included for generation
    ],
    lora_alpha=64,
    lora_dropout=0,
    use_gradient_checkpointing="unsloth",  # Critical for T4 VRAM with r=32 + 4096 ctx
)

model.print_trainable_parameters()

# %%
explainer_trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=explainer_train,
    eval_dataset=explainer_val,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH_EXPLAINER,
    args=TrainingArguments(
        per_device_train_batch_size=2,    # Larger outputs = more VRAM
        gradient_accumulation_steps=4,    # Effective batch = 8
        warmup_steps=30,
        num_train_epochs=3,
        learning_rate=1e-4,
        fp16=True,
        logging_steps=5,
        output_dir=str(OUTPUT_DIR / "explainer"),
        optim="adamw_8bit",
        evaluation_strategy="steps",
        eval_steps=20,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        seed=42,
        save_steps=20,
        save_total_limit=3,
    ),
)

print("Starting Adapter B: Data Explainer...")
explainer_stats = explainer_trainer.train()
print(f"Explainer complete. Best val loss: {explainer_trainer.state.best_metric:.4f}")

model.save_pretrained(str(OUTPUT_DIR / "explainer" / "adapter"))
tokenizer.save_pretrained(str(OUTPUT_DIR / "explainer" / "adapter"))
print("Explainer adapter saved")

del model, tokenizer, explainer_trainer
gc.collect()
torch.cuda.empty_cache()
```

- [ ] **Step 3: Write Adapter C — Evaluator cells**

Append to notebook:

```python
# %% [markdown]
# ### 3c. Adapter C: Evaluator (Multi-Task)
#
# Scores outputs on hallucination, relevance, bias, and equity framing.
# One adapter for all 4 sub-tasks — system prompt steers which lens to apply.
# - Rank 16, attention-only (classification + short generation)
# - 3 epochs on ~600 examples (hallucination 200, relevance 200, bias 100, equity framing 100, shuffled)
#
# **Duration:** ~20-25 minutes on T4

# %%
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=str(OUTPUT_DIR / "domain_cpt" / "merged"),
    max_seq_length=MAX_SEQ_LENGTH_TASK,
    load_in_4bit=True,
)

model = FastLanguageModel.get_peft_model(
    model,
    r=16,                 # Mid-range — classification + short generation
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
    ],
    lora_alpha=32,
    lora_dropout=0,
    use_gradient_checkpointing="unsloth",
)

model.print_trainable_parameters()

# %%
evaluator_trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=evaluator_train,
    eval_dataset=evaluator_val,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH_TASK,
    args=TrainingArguments(
        per_device_train_batch_size=4,
        gradient_accumulation_steps=2,
        warmup_steps=20,
        num_train_epochs=3,
        learning_rate=1e-4,
        fp16=True,
        logging_steps=5,
        output_dir=str(OUTPUT_DIR / "evaluator"),
        optim="adamw_8bit",
        evaluation_strategy="steps",
        eval_steps=25,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        seed=42,
        save_steps=25,
        save_total_limit=3,
    ),
)

print("Starting Adapter C: Evaluator...")
evaluator_stats = evaluator_trainer.train()
print(f"Evaluator complete. Best val loss: {evaluator_trainer.state.best_metric:.4f}")

model.save_pretrained(str(OUTPUT_DIR / "evaluator" / "adapter"))
tokenizer.save_pretrained(str(OUTPUT_DIR / "evaluator" / "adapter"))
print("Evaluator adapter saved")

del model, tokenizer, evaluator_trainer
gc.collect()
torch.cuda.empty_cache()
```

- [ ] **Step 4: Commit**

```bash
git add notebooks/training/d4bl_fine_tuning.py
git commit -m "feat: add Phase 2 task-specific adapter training (parser, explainer, evaluator)"
```

---

## Task 4: Colab Training Notebook — Phase 3 (GGUF Export)

**Files:**
- Modify: `notebooks/training/d4bl_fine_tuning.py`

Merges each LoRA adapter into the base model and exports to Q4_K_M GGUF format.

- [ ] **Step 1: Write GGUF export cells**

Append to notebook:

```python
# %% [markdown]
# ## 4. Phase 3: GGUF Export
#
# Merge each LoRA adapter into the domain-adapted base and quantize to
# Q4_K_M GGUF format. Each output is a self-contained model file (~1.8GB).
#
# **Duration:** ~10 minutes total

# %%
ADAPTERS = {
    "query_parser": {
        "adapter_dir": str(OUTPUT_DIR / "query_parser" / "adapter"),
        "output_name": "d4bl-query-parser-q4_k_m",
        "max_seq_length": MAX_SEQ_LENGTH_TASK,
    },
    "explainer": {
        "adapter_dir": str(OUTPUT_DIR / "explainer" / "adapter"),
        "output_name": "d4bl-explainer-q4_k_m",
        "max_seq_length": MAX_SEQ_LENGTH_EXPLAINER,
    },
    "evaluator": {
        "adapter_dir": str(OUTPUT_DIR / "evaluator" / "adapter"),
        "output_name": "d4bl-evaluator-q4_k_m",
        "max_seq_length": MAX_SEQ_LENGTH_TASK,
    },
}

gguf_dir = OUTPUT_DIR / "gguf"
gguf_dir.mkdir(exist_ok=True)

for name, cfg in ADAPTERS.items():
    print(f"\n{'='*60}")
    print(f"Exporting {name} to GGUF...")
    print(f"{'='*60}")

    # Load domain-adapted base + task adapter
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=cfg["adapter_dir"],
        max_seq_length=cfg["max_seq_length"],
        load_in_4bit=False,  # Full precision for merge
    )

    # Merge LoRA weights and export to GGUF Q4_K_M
    model.save_pretrained_gguf(
        str(gguf_dir / cfg["output_name"]),
        tokenizer,
        quantization_method="q4_k_m",
    )

    print(f"{name} exported: {cfg['output_name']}.gguf")

    del model, tokenizer
    gc.collect()
    torch.cuda.empty_cache()

# %%
# List output files
print("\nGGUF files produced:")
for f in sorted(gguf_dir.glob("*.gguf")):
    size_mb = f.stat().st_size / (1024 * 1024)
    print(f"  {f.name}: {size_mb:.0f} MB")

# %% [markdown]
# ## 5. Download GGUF Files
#
# Download the GGUF files to your local machine, then place them in the
# `models/` directory of the D4BL repo for Ollama registration.

# %%
from google.colab import files as colab_files

for f in sorted(gguf_dir.glob("*.gguf")):
    print(f"Downloading {f.name}...")
    colab_files.download(str(f))

print("\nDone! Place these files in the repo's models/ directory.")
print("Then run: python scripts/training/register_models.py")

# %% [markdown]
# ## 6. Training Summary
#
# Review training metrics before downloading.

# %%
print("=" * 60)
print("TRAINING SUMMARY")
print("=" * 60)
print(f"\nPhase 1 (Domain Adaptation):")
print(f"  Final train loss: {domain_stats.training_loss:.4f}")
print(f"\nPhase 2a (Query Parser):")
print(f"  Final train loss: {parser_stats.training_loss:.4f}")
print(f"\nPhase 2b (Explainer):")
print(f"  Final train loss: {explainer_stats.training_loss:.4f}")
print(f"\nPhase 2c (Evaluator):")
print(f"  Final train loss: {evaluator_stats.training_loss:.4f}")
print(f"\nGGUF files: {len(list(gguf_dir.glob('*.gguf')))}")
```

- [ ] **Step 2: Commit**

```bash
git add notebooks/training/d4bl_fine_tuning.py
git commit -m "feat: add Phase 3 GGUF export and download cells to training notebook"
```

---

## Task 5: Ollama Modelfiles

**Files:**
- Create: `models/Modelfile.query-parser`
- Create: `models/Modelfile.explainer`
- Create: `models/Modelfile.evaluator`

These Modelfiles register the GGUF files with Ollama. Each references a local GGUF path and sets task-appropriate parameters.

- [ ] **Step 1: Write tests for Modelfile content validation**

```python
# tests/test_training/test_modelfiles.py
"""Tests for Ollama Modelfile content and structure."""

from pathlib import Path

import pytest

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models"

MODELFILES = {
    "query-parser": MODELS_DIR / "Modelfile.query-parser",
    "explainer": MODELS_DIR / "Modelfile.explainer",
    "evaluator": MODELS_DIR / "Modelfile.evaluator",
}


class TestModelfileStructure:
    """All Modelfiles must have FROM, PARAMETER, and SYSTEM directives."""

    @pytest.fixture(params=list(MODELFILES.keys()))
    def modelfile(self, request):
        path = MODELFILES[request.param]
        return request.param, path.read_text()

    def test_has_from_directive(self, modelfile):
        name, content = modelfile
        assert content.strip().startswith("FROM "), f"{name}: must start with FROM"

    def test_from_references_gguf(self, modelfile):
        name, content = modelfile
        from_line = [l for l in content.splitlines() if l.startswith("FROM ")][0]
        assert ".gguf" in from_line, f"{name}: FROM must reference a .gguf file"

    def test_has_temperature(self, modelfile):
        name, content = modelfile
        assert "PARAMETER temperature" in content, f"{name}: must set temperature"

    def test_has_num_ctx(self, modelfile):
        name, content = modelfile
        assert "PARAMETER num_ctx" in content, f"{name}: must set num_ctx"

    def test_has_stop_token(self, modelfile):
        name, content = modelfile
        assert "PARAMETER stop" in content, f"{name}: must set stop token"

    def test_has_system_prompt(self, modelfile):
        name, content = modelfile
        assert "SYSTEM" in content, f"{name}: must have SYSTEM prompt"

    def test_system_requests_json(self, modelfile):
        name, content = modelfile
        assert "JSON" in content, f"{name}: SYSTEM must request JSON output"


class TestModelfileSpecifics:
    """Task-specific parameter validation."""

    def test_parser_low_temperature(self):
        content = MODELFILES["query-parser"].read_text()
        # Parser needs deterministic output
        assert "PARAMETER temperature 0.1" in content

    def test_parser_ctx_2048(self):
        content = MODELFILES["query-parser"].read_text()
        assert "PARAMETER num_ctx 2048" in content

    def test_explainer_moderate_temperature(self):
        content = MODELFILES["explainer"].read_text()
        assert "PARAMETER temperature 0.3" in content

    def test_explainer_ctx_4096(self):
        content = MODELFILES["explainer"].read_text()
        # Explainer trained with 4096 context — must match at inference
        assert "PARAMETER num_ctx 4096" in content

    def test_evaluator_low_temperature(self):
        content = MODELFILES["evaluator"].read_text()
        assert "PARAMETER temperature 0.1" in content

    def test_evaluator_ctx_2048(self):
        content = MODELFILES["evaluator"].read_text()
        assert "PARAMETER num_ctx 2048" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_training/test_modelfiles.py -v`
Expected: FAIL — files not found

- [ ] **Step 3: Create Modelfile.query-parser**

```dockerfile
# models/Modelfile.query-parser
FROM ./d4bl-query-parser-q4_k_m.gguf
PARAMETER temperature 0.1
PARAMETER num_ctx 2048
PARAMETER stop "<|im_end|>"
SYSTEM """You are a query parser for D4BL, a racial equity research platform.
Parse user questions into structured search intents.
Respond with ONLY valid JSON matching this schema:
{
  "intent": "compare|trend|lookup|aggregate",
  "metrics": ["metric_name"],
  "geographies": ["state or county name"],
  "races": ["race/ethnicity"],
  "time_range": {"start": year, "end": year},
  "sources": ["data_source"]
}"""
```

- [ ] **Step 4: Create Modelfile.explainer**

```dockerfile
# models/Modelfile.explainer
FROM ./d4bl-explainer-q4_k_m.gguf
PARAMETER temperature 0.3
PARAMETER num_ctx 4096
PARAMETER stop "<|im_end|>"
SYSTEM """You are a racial equity data analyst for D4BL (Data for Black Lives).
Generate equity-framed narratives that:
- Name structural causes of disparities, not just symptoms
- Connect data to policy implications and community action
- Acknowledge data limitations and collection biases
- Use language accessible to community members
Respond with ONLY valid JSON matching the requested output schema."""
```

- [ ] **Step 5: Create Modelfile.evaluator**

```dockerfile
# models/Modelfile.evaluator
FROM ./d4bl-evaluator-q4_k_m.gguf
PARAMETER temperature 0.1
PARAMETER num_ctx 2048
PARAMETER stop "<|im_end|>"
SYSTEM """You are an evaluation model for D4BL (Data for Black Lives).
Score model outputs on the dimension specified in the user prompt.
Evaluation dimensions: hallucination, relevance, bias, equity_framing.
Respond with ONLY valid JSON:
{
  "score": 1-5,
  "explanation": "brief justification",
  "issues": ["specific issue found"] or []
}"""
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_training/test_modelfiles.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add models/Modelfile.* tests/test_training/test_modelfiles.py
git commit -m "feat: add Ollama Modelfiles for query parser, explainer, and evaluator"
```

---

## Task 6: Output Validation Helpers

**Files:**
- Create: `scripts/training/validate_model_output.py`
- Create: `tests/test_training/test_validate_model_output.py`

Shared validation functions for checking model outputs (JSON validity, required fields, score ranges). Used by both the registration script and integration tests.

- [ ] **Step 1: Write tests for validation helpers**

```python
# tests/test_training/test_validate_model_output.py
"""Tests for model output validation helpers."""

import pytest

from scripts.training.validate_model_output import (
    validate_parser_output,
    validate_explainer_output,
    validate_evaluator_output,
    ValidationResult,
)


class TestValidationResult:
    def test_valid_result(self):
        r = ValidationResult(valid=True, parsed={"key": "val"}, errors=[])
        assert r.valid
        assert r.parsed == {"key": "val"}

    def test_invalid_result(self):
        r = ValidationResult(valid=False, parsed=None, errors=["bad json"])
        assert not r.valid
        assert "bad json" in r.errors


class TestParserValidation:
    def test_valid_output(self):
        raw = '{"intent": "compare", "metrics": ["poverty_rate"], "geographies": ["Alabama"]}'
        result = validate_parser_output(raw)
        assert result.valid
        assert result.parsed["intent"] == "compare"

    def test_invalid_json(self):
        result = validate_parser_output("not json at all")
        assert not result.valid
        assert any("JSON" in e for e in result.errors)

    def test_missing_intent(self):
        raw = '{"metrics": ["poverty_rate"]}'
        result = validate_parser_output(raw)
        assert not result.valid
        assert any("intent" in e for e in result.errors)

    def test_invalid_intent_value(self):
        raw = '{"intent": "invalid_type", "metrics": ["poverty_rate"]}'
        result = validate_parser_output(raw)
        assert not result.valid

    def test_empty_metrics_allowed(self):
        raw = '{"intent": "lookup", "metrics": []}'
        result = validate_parser_output(raw)
        assert result.valid

    def test_extracts_json_from_wrapper_text(self):
        raw = 'Here is the result:\n{"intent": "lookup", "metrics": ["income"]}\nDone.'
        result = validate_parser_output(raw)
        assert result.valid


class TestExplainerValidation:
    def test_valid_output(self):
        raw = '{"narrative": "Poverty rates in Alabama...", "structural_context": "Historical redlining...", "policy_connection": "HB-123..."}'
        result = validate_explainer_output(raw)
        assert result.valid

    def test_invalid_json(self):
        result = validate_explainer_output("plain text narrative")
        assert not result.valid

    def test_missing_narrative(self):
        raw = '{"structural_context": "something"}'
        result = validate_explainer_output(raw)
        assert not result.valid
        assert any("narrative" in e for e in result.errors)


class TestEvaluatorValidation:
    def test_valid_output(self):
        raw = '{"score": 4, "explanation": "Good alignment", "issues": []}'
        result = validate_evaluator_output(raw)
        assert result.valid

    def test_score_out_of_range(self):
        raw = '{"score": 6, "explanation": "test", "issues": []}'
        result = validate_evaluator_output(raw)
        assert not result.valid
        assert any("score" in e for e in result.errors)

    def test_score_zero_invalid(self):
        raw = '{"score": 0, "explanation": "test", "issues": []}'
        result = validate_evaluator_output(raw)
        assert not result.valid

    def test_missing_score(self):
        raw = '{"explanation": "test", "issues": []}'
        result = validate_evaluator_output(raw)
        assert not result.valid
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_training/test_validate_model_output.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement validation helpers**

```python
# scripts/training/validate_model_output.py
"""Validation helpers for D4BL fine-tuned model outputs.

Each validator parses raw model output (string) and checks for required
fields and value constraints. Used by the registration script and
integration tests.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    valid: bool
    parsed: dict | None
    errors: list[str] = field(default_factory=list)


_VALID_INTENTS = {"compare", "trend", "lookup", "aggregate"}


def _extract_json(raw: str) -> tuple[dict | None, str | None]:
    """Try to parse JSON from raw text, including extracting from wrapper text."""
    raw = raw.strip()
    # Direct parse
    try:
        return json.loads(raw), None
    except json.JSONDecodeError:
        pass
    # Try to find JSON object in text
    match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group()), None
        except json.JSONDecodeError:
            pass
    return None, "Invalid JSON: could not parse response"


def validate_parser_output(raw: str) -> ValidationResult:
    """Validate query parser model output."""
    parsed, err = _extract_json(raw)
    if err:
        return ValidationResult(valid=False, parsed=None, errors=[err])

    errors = []
    if "intent" not in parsed:
        errors.append("Missing required field: intent")
    elif parsed["intent"] not in _VALID_INTENTS:
        errors.append(
            f"Invalid intent '{parsed['intent']}', must be one of: {_VALID_INTENTS}"
        )

    return ValidationResult(valid=len(errors) == 0, parsed=parsed, errors=errors)


def validate_explainer_output(raw: str) -> ValidationResult:
    """Validate data explainer model output."""
    parsed, err = _extract_json(raw)
    if err:
        return ValidationResult(valid=False, parsed=None, errors=[err])

    errors = []
    if "narrative" not in parsed:
        errors.append("Missing required field: narrative")

    return ValidationResult(valid=len(errors) == 0, parsed=parsed, errors=errors)


def validate_evaluator_output(raw: str) -> ValidationResult:
    """Validate evaluator model output."""
    parsed, err = _extract_json(raw)
    if err:
        return ValidationResult(valid=False, parsed=None, errors=[err])

    errors = []
    if "score" not in parsed:
        errors.append("Missing required field: score")
    elif not isinstance(parsed["score"], (int, float)) or not (1 <= parsed["score"] <= 5):
        errors.append(f"Invalid score {parsed.get('score')}: must be 1-5")

    return ValidationResult(valid=len(errors) == 0, parsed=parsed, errors=errors)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_training/test_validate_model_output.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/training/validate_model_output.py tests/test_training/test_validate_model_output.py
git commit -m "feat: add model output validation helpers for parser, explainer, evaluator"
```

---

## Task 7: Model Registration Script

**Files:**
- Create: `scripts/training/register_models.py`

Script that loads GGUF files into Ollama via Modelfiles and runs a quick smoke test on each.

- [ ] **Step 1: Write the registration script**

```python
# scripts/training/register_models.py
"""Register D4BL fine-tuned models with Ollama.

Usage:
    python scripts/training/register_models.py [--models-dir ./models] [--dry-run]

Expects GGUF files in the models/ directory and Modelfiles alongside them.
Creates Ollama models: d4bl-query-parser, d4bl-explainer, d4bl-evaluator.
Runs a quick smoke test on each after registration.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from scripts.training.validate_model_output import (
    validate_parser_output,
    validate_explainer_output,
    validate_evaluator_output,
)

MODELS = {
    "d4bl-query-parser": {
        "modelfile": "Modelfile.query-parser",
        "gguf": "d4bl-query-parser-q4_k_m.gguf",
        "smoke_prompt": "What is the poverty rate for Black residents in Mississippi?",
        "validator": validate_parser_output,
    },
    "d4bl-explainer": {
        "modelfile": "Modelfile.explainer",
        "gguf": "d4bl-explainer-q4_k_m.gguf",
        "smoke_prompt": '{"metric": "poverty_rate", "geography": "Mississippi", "race": "Black", "value": 28.4, "year": 2022}',
        "validator": validate_explainer_output,
    },
    "d4bl-evaluator": {
        "modelfile": "Modelfile.evaluator",
        "gguf": "d4bl-evaluator-q4_k_m.gguf",
        "smoke_prompt": 'Evaluate for bias: "Black people in Mississippi are poor because of cultural issues."',
        "validator": validate_evaluator_output,
    },
}


def run_ollama_create(model_name: str, modelfile_path: Path) -> bool:
    """Register a model with Ollama via `ollama create`."""
    result = subprocess.run(
        ["ollama", "create", model_name, "-f", str(modelfile_path)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr.strip()}")
        return False
    print(f"  Created: {model_name}")
    return True


def run_smoke_test(model_name: str, prompt: str) -> str | None:
    """Run a quick inference test and return the response."""
    result = subprocess.run(
        ["ollama", "run", model_name, prompt],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        print(f"  Smoke test FAILED: {result.stderr.strip()}")
        return None
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Register D4BL models with Ollama")
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent / "models",
        help="Directory containing Modelfiles and GGUF files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check files exist without registering",
    )
    args = parser.parse_args()

    models_dir = args.models_dir
    if not models_dir.is_dir():
        print(f"Models directory not found: {models_dir}")
        return 1

    # Check all required files exist
    missing = []
    for name, cfg in MODELS.items():
        modelfile = models_dir / cfg["modelfile"]
        gguf = models_dir / cfg["gguf"]
        if not modelfile.exists():
            missing.append(str(modelfile))
        if not gguf.exists():
            missing.append(str(gguf))

    if missing:
        print("Missing files:")
        for f in missing:
            print(f"  {f}")
        print("\nPlace GGUF files from Colab in the models/ directory.")
        return 1

    if args.dry_run:
        print("Dry run — all files present. Ready to register.")
        return 0

    # Register each model
    results = {}
    for name, cfg in MODELS.items():
        print(f"\nRegistering {name}...")
        modelfile_path = models_dir / cfg["modelfile"]

        if not run_ollama_create(name, modelfile_path):
            results[name] = "FAILED (create)"
            continue

        # Smoke test
        print(f"  Running smoke test...")
        response = run_smoke_test(name, cfg["smoke_prompt"])
        if response is None:
            results[name] = "FAILED (smoke test)"
            continue

        validation = cfg["validator"](response)
        if validation.valid:
            results[name] = "OK"
            print(f"  Smoke test PASSED (valid JSON output)")
        else:
            results[name] = f"WARNING (invalid output: {validation.errors})"
            print(f"  Smoke test WARNING: {validation.errors}")
            print(f"  Raw output: {response[:200]}")

    # Summary
    print(f"\n{'='*50}")
    print("Registration Summary:")
    for name, status in results.items():
        print(f"  {name}: {status}")

    failed = sum(1 for s in results.values() if "FAILED" in s)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Commit**

```bash
git add scripts/training/register_models.py
git commit -m "feat: add Ollama model registration script with smoke tests"
```

---

## Task 8: Integration Tests

**Files:**
- Create: `tests/test_training/test_integration_models.py`

Integration tests that verify the trained models produce valid outputs via the Ollama API. These tests require the models to be registered in Ollama (skip if not available).

- [ ] **Step 1: Write integration tests**

```python
# tests/test_training/test_integration_models.py
"""Integration tests for D4BL fine-tuned models via Ollama.

These tests require the models to be registered in Ollama.
Run after `python scripts/training/register_models.py`.

Skip automatically if Ollama is not running or models aren't loaded.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from scripts.training.validate_model_output import (
    validate_parser_output,
    validate_explainer_output,
    validate_evaluator_output,
)


def _ollama_available() -> bool:
    """Check if Ollama is running."""
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _model_loaded(model_name: str) -> bool:
    """Check if a specific model is registered in Ollama."""
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=5
        )
        return model_name in result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _run_model(model_name: str, prompt: str, timeout: int = 120) -> str:
    """Run a prompt through an Ollama model and return the response."""
    result = subprocess.run(
        ["ollama", "run", model_name, prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Ollama run failed: {result.stderr}")
    return result.stdout.strip()


skip_no_ollama = pytest.mark.skipif(
    not _ollama_available(), reason="Ollama not running"
)


@skip_no_ollama
class TestQueryParserIntegration:
    MODEL = "d4bl-query-parser"

    @pytest.fixture(autouse=True)
    def check_model(self):
        if not _model_loaded(self.MODEL):
            pytest.skip(f"Model {self.MODEL} not registered in Ollama")

    def test_simple_lookup(self):
        response = _run_model(
            self.MODEL,
            "What is the poverty rate in Alabama?",
        )
        result = validate_parser_output(response)
        assert result.valid, f"Invalid output: {result.errors}\nRaw: {response}"
        assert result.parsed["intent"] in ("lookup", "compare", "trend", "aggregate")

    def test_comparison_query(self):
        response = _run_model(
            self.MODEL,
            "Compare median household income between Black and White residents in Mississippi",
        )
        result = validate_parser_output(response)
        assert result.valid, f"Invalid output: {result.errors}\nRaw: {response}"

    def test_trend_query(self):
        response = _run_model(
            self.MODEL,
            "How has the incarceration rate for Black men changed from 2015 to 2023?",
        )
        result = validate_parser_output(response)
        assert result.valid, f"Invalid output: {result.errors}\nRaw: {response}"

    def test_outputs_valid_json(self):
        """Verify output is parseable JSON (most basic requirement)."""
        response = _run_model(
            self.MODEL,
            "Show me diabetes rates by county in California",
        )
        result = validate_parser_output(response)
        assert result.parsed is not None, f"Could not parse JSON from: {response}"


@skip_no_ollama
class TestExplainerIntegration:
    MODEL = "d4bl-explainer"

    @pytest.fixture(autouse=True)
    def check_model(self):
        if not _model_loaded(self.MODEL):
            pytest.skip(f"Model {self.MODEL} not registered in Ollama")

    def test_single_metric_explanation(self):
        prompt = json.dumps({
            "metric": "poverty_rate",
            "geography": "Mississippi",
            "race": "Black",
            "value": 28.4,
            "comparison_value": 10.6,
            "comparison_race": "White",
            "year": 2022,
        })
        response = _run_model(self.MODEL, prompt, timeout=180)
        result = validate_explainer_output(response)
        assert result.valid, f"Invalid output: {result.errors}\nRaw: {response[:500]}"
        assert len(result.parsed["narrative"]) > 50, "Narrative too short"

    def test_outputs_valid_json(self):
        prompt = json.dumps({
            "metric": "median_household_income",
            "geography": "Alabama",
            "race": "Black",
            "value": 35400,
            "year": 2022,
        })
        response = _run_model(self.MODEL, prompt, timeout=180)
        result = validate_explainer_output(response)
        assert result.parsed is not None, f"Could not parse JSON from: {response[:500]}"


@skip_no_ollama
class TestEvaluatorIntegration:
    MODEL = "d4bl-evaluator"

    @pytest.fixture(autouse=True)
    def check_model(self):
        if not _model_loaded(self.MODEL):
            pytest.skip(f"Model {self.MODEL} not registered in Ollama")

    def test_bias_evaluation(self):
        response = _run_model(
            self.MODEL,
            'Evaluate for bias: "Crime rates are higher in Black neighborhoods because of cultural factors."',
        )
        result = validate_evaluator_output(response)
        assert result.valid, f"Invalid output: {result.errors}\nRaw: {response}"
        # Biased content should score low
        assert result.parsed["score"] <= 3, "Biased content should score low"

    def test_good_content_evaluation(self):
        response = _run_model(
            self.MODEL,
            'Evaluate for equity_framing: "The 2.7x disparity in poverty rates between Black and White residents in Mississippi reflects decades of structural disinvestment, including exclusion from federal homeownership programs."',
        )
        result = validate_evaluator_output(response)
        assert result.valid, f"Invalid output: {result.errors}\nRaw: {response}"
        # Well-framed content should score higher
        assert result.parsed["score"] >= 3

    def test_score_in_valid_range(self):
        response = _run_model(
            self.MODEL,
            'Evaluate for relevance: "The weather in Paris is nice today."',
        )
        result = validate_evaluator_output(response)
        assert result.valid, f"Invalid output: {result.errors}\nRaw: {response}"
        assert 1 <= result.parsed["score"] <= 5


@skip_no_ollama
class TestModelLatency:
    """Verify models respond within acceptable time limits."""

    @pytest.fixture(autouse=True)
    def check_models(self):
        for model in ("d4bl-query-parser", "d4bl-explainer", "d4bl-evaluator"):
            if not _model_loaded(model):
                pytest.skip(f"Model {model} not registered")

    def test_parser_responds_under_10s(self):
        """Query parser P95 target: <1s. Allow 10s for cold start."""
        import time
        start = time.monotonic()
        response = _run_model(
            "d4bl-query-parser",
            "What is the poverty rate in Alabama?",
            timeout=10,
        )
        elapsed = time.monotonic() - start
        assert elapsed < 10, f"Parser took {elapsed:.1f}s (target: <10s with cold start)"

    def test_explainer_responds_under_30s(self):
        """Explainer P95 target: <3s. Allow 30s for cold start."""
        import time
        start = time.monotonic()
        prompt = json.dumps({"metric": "poverty_rate", "geography": "Alabama", "value": 18.2, "year": 2022})
        response = _run_model("d4bl-explainer", prompt, timeout=30)
        elapsed = time.monotonic() - start
        assert elapsed < 30, f"Explainer took {elapsed:.1f}s (target: <30s with cold start)"
```

- [ ] **Step 2: Commit**

```bash
git add tests/test_training/test_integration_models.py
git commit -m "feat: add integration tests for fine-tuned models via Ollama API"
```

---

## Task 9: Documentation & Final Cleanup

**Files:**
- Modify: `notebooks/training/d4bl_fine_tuning.py` (add troubleshooting section)

- [ ] **Step 1: Add troubleshooting cells to notebook**

Append to `notebooks/training/d4bl_fine_tuning.py`:

```python
# %% [markdown]
# ## Troubleshooting
#
# ### Out of VRAM
# - Reduce `per_device_train_batch_size` (e.g., 4 → 2)
# - Ensure `use_gradient_checkpointing="unsloth"` is set
# - Check no other notebooks are using the GPU: `!nvidia-smi`
#
# ### Colab Session Timeout
# - Phase 1 + Phase 2 + Phase 3 total ~2.5 hours
# - Free tier sessions may disconnect after 90 minutes of inactivity
# - **Mitigation:** Save checkpoints frequently (`save_steps`) and resume from last checkpoint
# - If disconnected mid-Phase-2, skip Phase 1 (merged model is saved) and retrain only the current adapter
#
# ### GGUF Export Fails
# - Ensure sufficient disk space: `!df -h`
# - Each GGUF is ~1.8GB, need ~6GB free for all three
# - If Colab storage is full, download Phase 1-2 outputs and clear before Phase 3
#
# ### Model Produces Invalid JSON
# - Check val loss — if it diverged from train loss, the model overfit
# - Increase training data or reduce epochs
# - Check that training data JSONL has correct chat template formatting
#
# ### Resuming from Checkpoint
# To resume an interrupted adapter training:
# ```python
# # Find the latest checkpoint
# import glob
# checkpoints = sorted(glob.glob("outputs/query_parser/checkpoint-*"))
# latest = checkpoints[-1] if checkpoints else None
# print(f"Resuming from: {latest}")
# # Pass resume_from_checkpoint to trainer.train()
# trainer.train(resume_from_checkpoint=latest)
# ```
```

- [ ] **Step 2: Run all local tests**

Run: `python -m pytest tests/test_training/test_modelfiles.py tests/test_training/test_validate_model_output.py -v`
Expected: PASS (integration tests skipped without Ollama models)

- [ ] **Step 3: Final commit**

```bash
git add notebooks/training/d4bl_fine_tuning.py
git commit -m "docs: add troubleshooting section to training notebook"
```
