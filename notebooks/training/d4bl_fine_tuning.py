"""
D4BL Fine-Tuning Notebook — Colab-Compatible Training Script

This notebook fine-tunes Qwen2.5-3B-Instruct using a three-phase LoRA strategy
for the Data for Black Lives (D4BL) AI agent:

  Phase 1 — Domain-Adaptive LoRA Pre-Training:
    Adapts the base model to D4BL's equity-focused corpus (corpus_pretrain.jsonl)
    using a full-layer LoRA (r=16) for one epoch. The domain LoRA is then merged
    into the base weights and saved as a new checkpoint.

  Phase 2 — Task-Specific LoRA Adapters (three adapters trained sequentially):
    Adapter A — Query Parser:  lightweight attention-only LoRA (r=8) trained on
                               ~300 structured query examples for 3 epochs.
    Adapter B — Data Explainer: larger LoRA (r=32, attention+FFN) trained on
                                long-form explanation data at 4096-token context.
    Adapter C — Evaluator:     medium attention-only LoRA (r=16) trained on
                               ~600 evaluation examples for 3 epochs.

  Phase 3 — GGUF Export:
    Each task adapter is loaded over the domain-adapted base, then exported to
    GGUF format (q4_k_m quantization) for local Ollama deployment.

Run in Google Colab with a T4 or A100 GPU. All secrets (HF token) are read from
Colab's userdata store. Training data files are uploaded at runtime.
"""

# %% [markdown]
# # D4BL Fine-Tuning: Qwen2.5-3B-Instruct with LoRA
#
# **Overview**
#
# This notebook implements a three-phase fine-tuning pipeline for the D4BL AI agent:
#
# | Phase | What it does | LoRA rank | Epochs |
# |-------|--------------|-----------|--------|
# | 1 — Domain Adaptation | Teach the model D4BL vocabulary and equity framing | r=16 (all layers) | 1 |
# | 2a — Query Parser | Structured intent extraction from natural-language queries | r=8 (attention) | 3 |
# | 2b — Data Explainer | Long-form plain-language explanation of statistical data | r=32 (attention+FFN) | 3 |
# | 2c — Evaluator | Score and critique research outputs for bias and accuracy | r=16 (attention) | 3 |
# | 3 — GGUF Export | Quantise each adapter to q4_k_m for Ollama deployment | — | — |
#
# **Prerequisites**
# - Google Colab with T4 or A100 GPU runtime
# - Hugging Face token stored in Colab Secrets as `HF_TOKEN`
# - Training data files (see Section 1 for the full list)

# %% [markdown]
# ## 0. Environment Setup

# %%
# Install dependencies
# unsloth provides optimised LoRA training; install before other packages
# so it can patch transformers/peft correctly at import time.
import subprocess, sys  # noqa: E401
subprocess.run([sys.executable, "-m", "pip", "install", "unsloth"], check=True)
subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps",
                "trl", "peft", "accelerate", "bitsandbytes"], check=True)
subprocess.run([sys.executable, "-m", "pip", "install", "huggingface_hub"], check=True)

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

# Authenticate with Hugging Face
HF_TOKEN = userdata.get("HF_TOKEN")
login(token=HF_TOKEN)

# %%
# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

# Sequence length caps for each phase / adapter
MAX_SEQ_LENGTH_DOMAIN = 2048      # Phase 1 — domain pre-training
MAX_SEQ_LENGTH_TASK = 2048        # Phase 2 task adapters (parser, evaluator)
MAX_SEQ_LENGTH_EXPLAINER = 4096   # Phase 2b — explainer needs longer context

# Base directory for all saved checkpoints and merged models
OUTPUT_DIR = Path("/content/d4bl_training")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DOMAIN_MERGED_DIR = str(OUTPUT_DIR / "domain_merged")
ADAPTER_PARSER_DIR = str(OUTPUT_DIR / "adapter_parser")
ADAPTER_EXPLAINER_DIR = str(OUTPUT_DIR / "adapter_explainer")
ADAPTER_EVALUATOR_DIR = str(OUTPUT_DIR / "adapter_evaluator")
GGUF_DIR = str(OUTPUT_DIR / "gguf")

Path(GGUF_DIR).mkdir(parents=True, exist_ok=True)

print("Output directory:", OUTPUT_DIR)
print("Configuration loaded.")

# %% [markdown]
# ## 1. Upload Training Data
#
# Use the file picker below to upload **all** training data files before
# proceeding. Expected files:
#
# | File | Used in |
# |------|---------|
# | `corpus_pretrain.jsonl` | Phase 1 — domain adaptation |
# | `query_parser_train.jsonl` | Phase 2a — parser training split |
# | `query_parser_val.jsonl` | Phase 2a — parser validation split |
# | `explainer_train.jsonl` | Phase 2b — explainer training split |
# | `explainer_val.jsonl` | Phase 2b — explainer validation split |
# | `evaluator_train.jsonl` | Phase 2c — evaluator training split |
# | `evaluator_val.jsonl` | Phase 2c — evaluator validation split |
#
# Each file must be newline-delimited JSON with at minimum a `"text"` key per
# record (the formatted prompt+completion string).

# %%
from google.colab import files as colab_files

print("Select all training data files (Ctrl/Cmd+click for multi-select)...")
uploaded = colab_files.upload()
print(f"\nUploaded {len(uploaded)} file(s):")
for name in uploaded:
    size_kb = len(uploaded[name]) / 1024
    print(f"  {name:40s} {size_kb:.1f} KB")

# %%
def load_jsonl(path: str) -> list[dict]:
    """Read a newline-delimited JSON file and return a list of records."""
    records = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_dataset_from_jsonl(path: str) -> Dataset:
    """Load a JSONL file as a HuggingFace Dataset."""
    records = load_jsonl(path)
    return Dataset.from_list(records)


# Load all datasets
corpus_dataset = load_dataset_from_jsonl("corpus_pretrain.jsonl")

parser_train_dataset = load_dataset_from_jsonl("query_parser_train.jsonl")
parser_val_dataset = load_dataset_from_jsonl("query_parser_val.jsonl")

explainer_train_dataset = load_dataset_from_jsonl("explainer_train.jsonl")
explainer_val_dataset = load_dataset_from_jsonl("explainer_val.jsonl")

evaluator_train_dataset = load_dataset_from_jsonl("evaluator_train.jsonl")
evaluator_val_dataset = load_dataset_from_jsonl("evaluator_val.jsonl")

print("Datasets loaded:")
print(f"  corpus_pretrain       : {len(corpus_dataset):>5} examples")
print(f"  query_parser_train    : {len(parser_train_dataset):>5} examples")
print(f"  query_parser_val      : {len(parser_val_dataset):>5} examples")
print(f"  explainer_train       : {len(explainer_train_dataset):>5} examples")
print(f"  explainer_val         : {len(explainer_val_dataset):>5} examples")
print(f"  evaluator_train       : {len(evaluator_train_dataset):>5} examples")
print(f"  evaluator_val         : {len(evaluator_val_dataset):>5} examples")

# %% [markdown]
# ## 2. Phase 1: Domain-Adaptive LoRA Pre-Training
#
# We load Qwen2.5-3B-Instruct in 4-bit (NF4) quantisation, attach a full-layer
# LoRA (r=16, all projection matrices including embeddings and LM head), and
# train for one epoch on the D4BL equity corpus. The goal is to shift the
# model's prior toward D4BL terminology and framing before task-specific
# fine-tuning.
#
# After training the domain LoRA is **merged** into the base weights so that
# subsequent adapters compose cleanly on top of a single checkpoint.

# %%
# Load Qwen2.5-3B-Instruct in 4-bit quantisation
domain_model, domain_tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Qwen2.5-3B-Instruct",
    max_seq_length=MAX_SEQ_LENGTH_DOMAIN,
    dtype=None,           # auto-detect (bfloat16 on Ampere+, float16 on T4)
    load_in_4bit=True,
)
print("Base model loaded.")
print(f"  Parameters : {domain_model.num_parameters():,}")

# %%
# Attach domain-adaptation LoRA adapters
domain_model = FastLanguageModel.get_peft_model(
    domain_model,
    r=16,
    target_modules=[
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
        "embed_tokens",
        "lm_head",
    ],
    lora_alpha=32,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
)
print("Domain LoRA adapters attached.")
domain_model.print_trainable_parameters()

# %%
# Train Phase 1 — domain adaptation
domain_training_args = TrainingArguments(
    output_dir=str(OUTPUT_DIR / "phase1_checkpoints"),
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    warmup_steps=50,
    num_train_epochs=1,
    learning_rate=2e-4,
    fp16=True,
    logging_steps=10,
    optim="adamw_8bit",
    seed=42,
    save_steps=500,
    save_total_limit=2,
    report_to="none",
)

domain_trainer = SFTTrainer(
    model=domain_model,
    tokenizer=domain_tokenizer,
    train_dataset=corpus_dataset,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH_DOMAIN,
    args=domain_training_args,
)

print("Starting Phase 1 training...")
domain_stats = domain_trainer.train()
print("Phase 1 training complete.")
print(f"  Training loss : {domain_stats.training_loss:.4f}")

# %%
# Merge domain LoRA into base weights and save merged checkpoint
print("Merging domain LoRA into base weights...")
domain_model.save_pretrained_merged(
    DOMAIN_MERGED_DIR,
    domain_tokenizer,
    save_method="merged_16bit",
)
print(f"Domain-merged model saved to: {DOMAIN_MERGED_DIR}")

# Free VRAM before loading the next model
import gc
import torch

del domain_model
del domain_trainer
gc.collect()
torch.cuda.empty_cache()
print("VRAM freed.")

# %% [markdown]
# ## 3. Phase 2: Task-Specific LoRA Adapters
#
# Each adapter is trained on top of the **domain-merged** checkpoint saved in
# Phase 1. We load that checkpoint fresh for each adapter, attach a smaller
# LoRA sized for the task, train, save only the adapter weights, then free
# VRAM before moving to the next adapter.

# %% [markdown]
# ### 3a. Adapter A: Query Parser
#
# **Goal:** Structured intent extraction — map a natural-language query to a
# typed JSON payload (metric, geography, filters, comparison).
#
# | Hyperparameter | Value |
# |----------------|-------|
# | LoRA rank | r=8 (attention-only) |
# | Target modules | q_proj, k_proj, v_proj, o_proj |
# | lora_alpha | 16 |
# | Training examples | ~300 |
# | Epochs | 3 |
# | Learning rate | 1e-4 |
#
# Attention-only adapters are sufficient for short, highly-structured outputs
# and keep the parameter count low.

# %%
# Load domain-adapted model for parser adapter training
parser_model, parser_tokenizer = FastLanguageModel.from_pretrained(
    model_name=DOMAIN_MERGED_DIR,
    max_seq_length=MAX_SEQ_LENGTH_TASK,
    dtype=None,
    load_in_4bit=True,
)
print("Domain-merged model loaded for parser adapter.")

# Attach parser LoRA — attention-only, r=8
parser_model = FastLanguageModel.get_peft_model(
    parser_model,
    r=8,
    target_modules=[
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
    ],
    lora_alpha=16,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
)
print("Parser LoRA adapters attached.")
parser_model.print_trainable_parameters()

# %%
# Train Adapter A — Query Parser
parser_training_args = TrainingArguments(
    output_dir=str(OUTPUT_DIR / "parser_checkpoints"),
    per_device_train_batch_size=4,
    gradient_accumulation_steps=2,
    warmup_steps=20,
    num_train_epochs=3,
    learning_rate=1e-4,
    fp16=True,
    logging_steps=10,
    optim="adamw_8bit",
    seed=42,
    evaluation_strategy="steps",
    eval_steps=25,
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    save_steps=25,
    save_total_limit=3,
    report_to="none",
)

parser_trainer = SFTTrainer(
    model=parser_model,
    tokenizer=parser_tokenizer,
    train_dataset=parser_train_dataset,
    eval_dataset=parser_val_dataset,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH_TASK,
    args=parser_training_args,
)

print("Starting Adapter A (Query Parser) training...")
parser_stats = parser_trainer.train()
print("Parser adapter training complete.")
print(f"  Training loss : {parser_stats.training_loss:.4f}")

# Save only the adapter weights
parser_model.save_pretrained(ADAPTER_PARSER_DIR)
parser_tokenizer.save_pretrained(ADAPTER_PARSER_DIR)
print(f"Parser adapter saved to: {ADAPTER_PARSER_DIR}")

# Free VRAM
del parser_model
del parser_trainer
gc.collect()
torch.cuda.empty_cache()
print("VRAM freed.")

# %% [markdown]
# ### 3b. Adapter B: Data Explainer
#
# **Goal:** Generate plain-language, equity-framed explanations of statistical
# data for a general audience — e.g., "What does a Gini coefficient of 0.49
# mean for Black households in Cook County?"
#
# | Hyperparameter | Value |
# |----------------|-------|
# | LoRA rank | r=32 (attention + FFN) |
# | Target modules | q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj |
# | lora_alpha | 64 |
# | Max sequence length | 4096 |
# | Epochs | 3 |
# | Learning rate | 1e-4 |
#
# The larger rank and FFN coverage are needed for long-form generation quality.
# The 4096-token context handles data tables embedded in prompts.

# %%
# Load domain-adapted model for explainer adapter training
explainer_model, explainer_tokenizer = FastLanguageModel.from_pretrained(
    model_name=DOMAIN_MERGED_DIR,
    max_seq_length=MAX_SEQ_LENGTH_EXPLAINER,
    dtype=None,
    load_in_4bit=True,
)
print("Domain-merged model loaded for explainer adapter.")

# Attach explainer LoRA — attention + FFN, r=32
explainer_model = FastLanguageModel.get_peft_model(
    explainer_model,
    r=32,
    target_modules=[
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    ],
    lora_alpha=64,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
)
print("Explainer LoRA adapters attached.")
explainer_model.print_trainable_parameters()

# %%
# Train Adapter B — Data Explainer
explainer_training_args = TrainingArguments(
    output_dir=str(OUTPUT_DIR / "explainer_checkpoints"),
    per_device_train_batch_size=2,
    gradient_accumulation_steps=4,
    warmup_steps=30,
    num_train_epochs=3,
    learning_rate=1e-4,
    fp16=True,
    logging_steps=10,
    optim="adamw_8bit",
    seed=42,
    evaluation_strategy="steps",
    eval_steps=20,
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    save_steps=20,
    save_total_limit=3,
    report_to="none",
)

explainer_trainer = SFTTrainer(
    model=explainer_model,
    tokenizer=explainer_tokenizer,
    train_dataset=explainer_train_dataset,
    eval_dataset=explainer_val_dataset,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH_EXPLAINER,
    args=explainer_training_args,
)

print("Starting Adapter B (Data Explainer) training...")
explainer_stats = explainer_trainer.train()
print("Explainer adapter training complete.")
print(f"  Training loss : {explainer_stats.training_loss:.4f}")

# Save only the adapter weights
explainer_model.save_pretrained(ADAPTER_EXPLAINER_DIR)
explainer_tokenizer.save_pretrained(ADAPTER_EXPLAINER_DIR)
print(f"Explainer adapter saved to: {ADAPTER_EXPLAINER_DIR}")

# Free VRAM
del explainer_model
del explainer_trainer
gc.collect()
torch.cuda.empty_cache()
print("VRAM freed.")

# %% [markdown]
# ### 3c. Adapter C: Evaluator
#
# **Goal:** Score and critique D4BL research outputs on four dimensions:
# factual accuracy, equity framing, source quality, and actionability.
# Returns a structured JSON rubric with scores and a brief rationale.
#
# | Hyperparameter | Value |
# |----------------|-------|
# | LoRA rank | r=16 (attention-only) |
# | Target modules | q_proj, k_proj, v_proj, o_proj |
# | lora_alpha | 32 |
# | Training examples | ~600 |
# | Epochs | 3 |
# | Learning rate | 1e-4 |

# %%
# Load domain-adapted model for evaluator adapter training
evaluator_model, evaluator_tokenizer = FastLanguageModel.from_pretrained(
    model_name=DOMAIN_MERGED_DIR,
    max_seq_length=MAX_SEQ_LENGTH_TASK,
    dtype=None,
    load_in_4bit=True,
)
print("Domain-merged model loaded for evaluator adapter.")

# Attach evaluator LoRA — attention-only, r=16
evaluator_model = FastLanguageModel.get_peft_model(
    evaluator_model,
    r=16,
    target_modules=[
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
    ],
    lora_alpha=32,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
)
print("Evaluator LoRA adapters attached.")
evaluator_model.print_trainable_parameters()

# %%
# Train Adapter C — Evaluator
evaluator_training_args = TrainingArguments(
    output_dir=str(OUTPUT_DIR / "evaluator_checkpoints"),
    per_device_train_batch_size=4,
    gradient_accumulation_steps=2,
    warmup_steps=20,
    num_train_epochs=3,
    learning_rate=1e-4,
    fp16=True,
    logging_steps=10,
    optim="adamw_8bit",
    seed=42,
    evaluation_strategy="steps",
    eval_steps=25,
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    save_steps=25,
    save_total_limit=3,
    report_to="none",
)

evaluator_trainer = SFTTrainer(
    model=evaluator_model,
    tokenizer=evaluator_tokenizer,
    train_dataset=evaluator_train_dataset,
    eval_dataset=evaluator_val_dataset,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH_TASK,
    args=evaluator_training_args,
)

print("Starting Adapter C (Evaluator) training...")
evaluator_stats = evaluator_trainer.train()
print("Evaluator adapter training complete.")
print(f"  Training loss : {evaluator_stats.training_loss:.4f}")

# Save only the adapter weights
evaluator_model.save_pretrained(ADAPTER_EVALUATOR_DIR)
evaluator_tokenizer.save_pretrained(ADAPTER_EVALUATOR_DIR)
print(f"Evaluator adapter saved to: {ADAPTER_EVALUATOR_DIR}")

# Free VRAM
del evaluator_model
del evaluator_trainer
gc.collect()
torch.cuda.empty_cache()
print("VRAM freed.")

# %% [markdown]
# ## 4. Phase 3: GGUF Export
#
# For each task adapter we:
# 1. Load the domain-merged base model in **full precision** (load_in_4bit=False)
#    so that unsloth can merge + quantise without precision loss.
# 2. Load the task adapter weights on top.
# 3. Export to GGUF with `q4_k_m` quantisation — a good balance of size (~1.7 GB
#    per model) and quality for CPU inference via Ollama.
#
# The three output files can be registered as separate Ollama model families
# (e.g., `d4bl-parser:q4_k_m`, `d4bl-explainer:q4_k_m`, `d4bl-evaluator:q4_k_m`).

# %%

# Adapter registry: name → paths and sequence length used during export
ADAPTERS = {
    "parser": {
        "adapter_dir": ADAPTER_PARSER_DIR,
        "output_name": "d4bl-query-parser-q4_k_m",
        "max_seq_length": MAX_SEQ_LENGTH_TASK,
    },
    "explainer": {
        "adapter_dir": ADAPTER_EXPLAINER_DIR,
        "output_name": "d4bl-explainer-q4_k_m",
        "max_seq_length": MAX_SEQ_LENGTH_EXPLAINER,
    },
    "evaluator": {
        "adapter_dir": ADAPTER_EVALUATOR_DIR,
        "output_name": "d4bl-evaluator-q4_k_m",
        "max_seq_length": MAX_SEQ_LENGTH_TASK,
    },
}

gguf_output_paths = {}

for adapter_name, cfg in ADAPTERS.items():
    print(f"\n--- Exporting '{adapter_name}' to GGUF ---")

    # Load adapter directly via FastLanguageModel (preserves Unsloth GGUF export)
    export_model, export_tokenizer = FastLanguageModel.from_pretrained(
        model_name=cfg["adapter_dir"],
        max_seq_length=cfg["max_seq_length"],
        dtype=None,
        load_in_4bit=False,  # full precision required for GGUF export
    )

    # Export to GGUF — Unsloth handles LoRA merge internally
    gguf_path = str(Path(GGUF_DIR) / cfg["output_name"])
    export_model.save_pretrained_gguf(
        gguf_path,
        export_tokenizer,
        quantization_method="q4_k_m",
    )
    gguf_output_paths[adapter_name] = gguf_path
    print(f"  Saved: {gguf_path}")

    # Free VRAM before next adapter
    del export_model
    gc.collect()
    torch.cuda.empty_cache()

print("\nAll GGUF files exported.")

# %%
# List GGUF output files with sizes
import os

print(f"{'File':<55} {'Size (MB)':>10}")
print("-" * 67)
for adapter_name, base_path in gguf_output_paths.items():
    # unsloth appends the quant suffix to the filename
    for fname in sorted(os.listdir(GGUF_DIR)):
        if fname.startswith(Path(base_path).name) and fname.endswith(".gguf"):
            fpath = os.path.join(GGUF_DIR, fname)
            size_mb = os.path.getsize(fpath) / (1024 ** 2)
            print(f"{fname:<55} {size_mb:>10.1f}")

# %% [markdown]
# ## 5. Download GGUF Files
#
# Run the cell below to download all three GGUF files to your local machine.
# Each file is approximately 1.7 GB with q4_k_m quantisation.

# %%
from google.colab import files as colab_files

print("Downloading GGUF files...")
for fname in sorted(os.listdir(GGUF_DIR)):
    if fname.endswith(".gguf"):
        fpath = os.path.join(GGUF_DIR, fname)
        size_mb = os.path.getsize(fpath) / (1024 ** 2)
        print(f"  Downloading {fname} ({size_mb:.1f} MB)...")
        colab_files.download(fpath)

print("All downloads initiated.")

# %% [markdown]
# ## 6. Training Summary
#
# Final training losses for all phases and adapters.

# %%
# Print a consolidated training summary
print("=" * 60)
print("D4BL Fine-Tuning — Training Summary")
print("=" * 60)

summary_rows = [
    ("Phase 1 — Domain Adaptation", domain_stats),
    ("Phase 2a — Query Parser",     parser_stats),
    ("Phase 2b — Data Explainer",   explainer_stats),
    ("Phase 2c — Evaluator",        evaluator_stats),
]

for label, stats in summary_rows:
    loss = stats.training_loss
    print(f"  {label:<35} training loss: {loss:.4f}")

print("=" * 60)
print("\nAll GGUF models are ready for Ollama deployment.")
print("Register each model with:")
print("  python scripts/training/register_models.py")

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
