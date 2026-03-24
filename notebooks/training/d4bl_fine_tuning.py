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
    NOTE: Each export must be done in a separate cell with a runtime restart
    between them to avoid VRAM exhaustion on T4.

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
# ## 0a. Restore from Google Drive (run first on every session)
#
# Mounts Google Drive and restores any previously backed-up training data
# and model outputs. If this is a fresh session, nothing will be restored
# and you'll need to upload files in Section 1.

# %%
from google.colab import drive
drive.mount('/content/drive')

import os, shutil
from pathlib import Path

DRIVE_DIR = "/content/drive/MyDrive/d4bl_training"
os.makedirs(f"{DRIVE_DIR}/outputs", exist_ok=True)

# Restore JSONL files from Drive if present
restored = 0
if os.path.exists(DRIVE_DIR):
    for f in os.listdir(DRIVE_DIR):
        if f.endswith(".jsonl"):
            shutil.copy(f"{DRIVE_DIR}/{f}", f)
            restored += 1

# Restore model outputs from Drive if present
OUTPUT_DIR = Path("/content/d4bl_training")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
if os.path.exists(f"{DRIVE_DIR}/domain_merged"):
    for item in os.listdir(DRIVE_DIR):
        src = f"{DRIVE_DIR}/{item}"
        dst = str(OUTPUT_DIR / item)
        if os.path.isdir(src) and not os.path.exists(dst):
            shutil.copytree(src, dst)
            print(f"  Restored {item} from Drive")

if restored:
    print(f"Restored {restored} JSONL files from Drive — skip the upload cell")
else:
    print("No files on Drive yet — run the upload cell next")

# %% [markdown]
# ## 0b. Environment Setup

# %%
# Install dependencies — Unsloth first, then pin trl to a compatible version.
# This cell restarts the runtime automatically. After restart, skip this cell
# and continue from the imports cell.
import subprocess, sys  # noqa: E401
subprocess.run([sys.executable, "-m", "pip", "install", "unsloth"], check=True)
subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps",
                "trl", "peft", "accelerate", "bitsandbytes"], check=True)
subprocess.run([sys.executable, "-m", "pip", "install", "huggingface_hub"], check=True)
# Pin trl to 0.15.2 for Unsloth compatibility (newer versions have breaking API changes)
subprocess.run([sys.executable, "-m", "pip", "install", "trl==0.15.2", "--no-deps"], check=True)
# Restart runtime so patched imports take effect
import os
os.kill(os.getpid(), 9)

# %%
# Imports — run this cell after the runtime restart above
import gc
import json
import os
import torch
from pathlib import Path

from datasets import Dataset
from google.colab import userdata
from huggingface_hub import login
from transformers import TrainingArguments
from trl import SFTTrainer
from unsloth import FastLanguageModel

# Authenticate with Hugging Face
HF_TOKEN = userdata.get("HF_TOKEN")
if not HF_TOKEN:
    raise RuntimeError(
        "Missing HF_TOKEN in Colab Secrets. "
        "Add it under Secrets (key icon in sidebar) before running."
    )
login(token=HF_TOKEN)

# %%
# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

MAX_SEQ_LENGTH_DOMAIN = 2048
MAX_SEQ_LENGTH_TASK = 2048
MAX_SEQ_LENGTH_EXPLAINER = 4096

OUTPUT_DIR = Path("/content/d4bl_training")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DOMAIN_MERGED_DIR = str(OUTPUT_DIR / "domain_merged")
ADAPTER_PARSER_DIR = str(OUTPUT_DIR / "adapter_parser")
ADAPTER_EXPLAINER_DIR = str(OUTPUT_DIR / "adapter_explainer")
ADAPTER_EVALUATOR_DIR = str(OUTPUT_DIR / "adapter_evaluator")
GGUF_DIR = str(OUTPUT_DIR / "gguf")

Path(GGUF_DIR).mkdir(parents=True, exist_ok=True)

DRIVE_DIR = "/content/drive/MyDrive/d4bl_training"

print("Output directory:", OUTPUT_DIR)
print("Configuration loaded.")

# %% [markdown]
# ## 1. Upload Training Data
#
# Use the file picker below to upload **all** training data files.
# **Skip this cell** if the restore cell above found files on Drive.
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

# %%
from google.colab import files as colab_files

print("Select all training data files (Ctrl/Cmd+click for multi-select)...")
uploaded = colab_files.upload()
print(f"\nUploaded {len(uploaded)} file(s):")
for name in uploaded:
    size_kb = len(uploaded[name]) / 1024
    print(f"  {name:40s} {size_kb:.1f} KB")

# Back up to Drive so we don't have to re-upload next time
import shutil
for name in uploaded:
    shutil.copy(name, f"{DRIVE_DIR}/{name}")
print("Training data backed up to Drive.")

# %%
# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def load_jsonl(path: str, require_text: bool = False) -> list[dict]:
    """Read a newline-delimited JSON file and return a list of records."""
    records = []
    with open(path, "r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_no}: expected JSON object")
            if require_text and ("text" not in record or not isinstance(record["text"], str)):
                raise ValueError(
                    f"{path}:{line_no}: missing or invalid 'text' field"
                )
            records.append(record)
    return records


def load_dataset_from_jsonl(path: str, require_text: bool = False) -> Dataset:
    """Load a JSONL file as a HuggingFace Dataset."""
    records = load_jsonl(path, require_text=require_text)
    return Dataset.from_list(records)


def format_and_tokenize(dataset):
    """Convert messages-format dataset to plain text for SFTTrainer.

    Task pair datasets use {"messages": [{role, content}, ...]} format.
    SFTTrainer with Unsloth works best with a plain {"text": "..."} dataset.
    This function converts messages to ChatML format strings.
    """
    formatted = []
    for i in range(len(dataset)):
        msgs = dataset[i]["messages"]
        parts = []
        for msg in msgs:
            parts.append(f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>")
        text = "\n".join(parts)
        formatted.append({"text": text})
    return Dataset.from_list(formatted)


# Load all datasets
corpus_dataset = load_dataset_from_jsonl("corpus_pretrain.jsonl", require_text=True)

parser_train_dataset = load_dataset_from_jsonl("query_parser_train.jsonl")
parser_val_dataset = load_dataset_from_jsonl("query_parser_val.jsonl")

explainer_train_dataset = load_dataset_from_jsonl("explainer_train.jsonl")
explainer_val_dataset = load_dataset_from_jsonl("explainer_val.jsonl")

evaluator_train_dataset = load_dataset_from_jsonl("evaluator_train.jsonl")
evaluator_val_dataset = load_dataset_from_jsonl("evaluator_val.jsonl")

print(f"  corpus_pretrain       : {len(corpus_dataset):>5} examples")
print(f"  query_parser (train)  : {len(parser_train_dataset):>5} examples")
print(f"  query_parser (val)    : {len(parser_val_dataset):>5} examples")
print(f"  explainer (train)     : {len(explainer_train_dataset):>5} examples")
print(f"  explainer (val)       : {len(explainer_val_dataset):>5} examples")
print(f"  evaluator (train)     : {len(evaluator_train_dataset):>5} examples")
print(f"  evaluator (val)       : {len(evaluator_val_dataset):>5} examples")

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
    dtype=None,
    load_in_4bit=True,
)
print("Base model loaded.")

# %%
# Attach domain-adaptation LoRA adapters
domain_model = FastLanguageModel.get_peft_model(
    domain_model,
    r=16,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
        "embed_tokens", "lm_head",
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
domain_trainer = SFTTrainer(
    model=domain_model,
    tokenizer=domain_tokenizer,
    train_dataset=corpus_dataset,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH_DOMAIN,
    args=TrainingArguments(
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
    ),
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

del domain_model, domain_trainer
gc.collect()
torch.cuda.empty_cache()
print("VRAM freed.")

# %%
# Back up Phase 1 outputs to Drive
!cp -r /content/d4bl_training/domain_merged {DRIVE_DIR}/
!cp -r /content/d4bl_training/phase1_checkpoints {DRIVE_DIR}/
print("Phase 1 backed up to Drive.")

# %% [markdown]
# ## 3. Phase 2: Task-Specific LoRA Adapters
#
# Each adapter is trained on top of the **domain-merged** checkpoint saved in
# Phase 1. We load that checkpoint fresh for each adapter, attach a smaller
# LoRA sized for the task, train, save only the adapter weights, then free
# VRAM before moving to the next adapter.
#
# **Important:** Task pair datasets use `messages` format (list of role/content
# dicts). We convert them to plain ChatML text using `format_and_tokenize`
# before passing to SFTTrainer, which avoids Unsloth's dataset filtering issues.

# %% [markdown]
# ### 3a. Adapter A: Query Parser

# %%
parser_model, parser_tokenizer = FastLanguageModel.from_pretrained(
    model_name=DOMAIN_MERGED_DIR,
    max_seq_length=MAX_SEQ_LENGTH_TASK,
    dtype=None,
    load_in_4bit=True,
)

parser_model = FastLanguageModel.get_peft_model(
    parser_model,
    r=8,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    lora_alpha=16,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
)
parser_model.print_trainable_parameters()

# %%
# Convert messages format to plain text
parser_train_text = format_and_tokenize(parser_train_dataset)
parser_val_text = format_and_tokenize(parser_val_dataset)
print(f"Formatted: {len(parser_train_text)} train, {len(parser_val_text)} val")

parser_trainer = SFTTrainer(
    model=parser_model,
    tokenizer=parser_tokenizer,
    train_dataset=parser_train_text,
    eval_dataset=parser_val_text,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH_TASK,
    packing=False,
    dataset_num_proc=1,
    args=TrainingArguments(
        output_dir=str(OUTPUT_DIR / "parser_checkpoints"),
        per_device_train_batch_size=4,
        gradient_accumulation_steps=2,
        warmup_steps=20,
        num_train_epochs=3,
        learning_rate=1e-4,
        fp16=True,
        logging_steps=5,
        optim="adamw_8bit",
        seed=42,
        eval_strategy="steps",
        eval_steps=25,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        save_steps=25,
        save_total_limit=3,
        report_to="none",
    ),
)

print("Starting Adapter A (Query Parser) training...")
parser_stats = parser_trainer.train()
print("Parser adapter training complete.")
print(f"  Training loss : {parser_stats.training_loss:.4f}")

parser_model.save_pretrained(ADAPTER_PARSER_DIR)
parser_tokenizer.save_pretrained(ADAPTER_PARSER_DIR)
print(f"Parser adapter saved to: {ADAPTER_PARSER_DIR}")

del parser_model, parser_trainer
gc.collect()
torch.cuda.empty_cache()
print("VRAM freed.")

# %%
!cp -r /content/d4bl_training/adapter_parser {DRIVE_DIR}/
print("Parser adapter backed up to Drive.")

# %% [markdown]
# ### 3b. Adapter B: Data Explainer

# %%
explainer_model, explainer_tokenizer = FastLanguageModel.from_pretrained(
    model_name=DOMAIN_MERGED_DIR,
    max_seq_length=MAX_SEQ_LENGTH_EXPLAINER,
    dtype=None,
    load_in_4bit=True,
)

explainer_model = FastLanguageModel.get_peft_model(
    explainer_model,
    r=32,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    lora_alpha=64,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
)
explainer_model.print_trainable_parameters()

# %%
explainer_train_text = format_and_tokenize(explainer_train_dataset)
explainer_val_text = format_and_tokenize(explainer_val_dataset)
print(f"Formatted: {len(explainer_train_text)} train, {len(explainer_val_text)} val")

explainer_trainer = SFTTrainer(
    model=explainer_model,
    tokenizer=explainer_tokenizer,
    train_dataset=explainer_train_text,
    eval_dataset=explainer_val_text,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH_EXPLAINER,
    packing=False,
    dataset_num_proc=1,
    args=TrainingArguments(
        output_dir=str(OUTPUT_DIR / "explainer_checkpoints"),
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        warmup_steps=30,
        num_train_epochs=3,
        learning_rate=1e-4,
        fp16=True,
        logging_steps=5,
        optim="adamw_8bit",
        seed=42,
        eval_strategy="steps",
        eval_steps=20,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        save_steps=20,
        save_total_limit=3,
        report_to="none",
    ),
)

print("Starting Adapter B (Data Explainer) training...")
explainer_stats = explainer_trainer.train()
print("Explainer adapter training complete.")
print(f"  Training loss : {explainer_stats.training_loss:.4f}")

explainer_model.save_pretrained(ADAPTER_EXPLAINER_DIR)
explainer_tokenizer.save_pretrained(ADAPTER_EXPLAINER_DIR)
print(f"Explainer adapter saved to: {ADAPTER_EXPLAINER_DIR}")

del explainer_model, explainer_trainer
gc.collect()
torch.cuda.empty_cache()
print("VRAM freed.")

# %%
!cp -r /content/d4bl_training/adapter_explainer {DRIVE_DIR}/
print("Explainer adapter backed up to Drive.")

# %% [markdown]
# ### 3c. Adapter C: Evaluator

# %%
evaluator_model, evaluator_tokenizer = FastLanguageModel.from_pretrained(
    model_name=DOMAIN_MERGED_DIR,
    max_seq_length=MAX_SEQ_LENGTH_TASK,
    dtype=None,
    load_in_4bit=True,
)

evaluator_model = FastLanguageModel.get_peft_model(
    evaluator_model,
    r=16,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    lora_alpha=32,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
)
evaluator_model.print_trainable_parameters()

# %%
evaluator_train_text = format_and_tokenize(evaluator_train_dataset)
evaluator_val_text = format_and_tokenize(evaluator_val_dataset)
print(f"Formatted: {len(evaluator_train_text)} train, {len(evaluator_val_text)} val")

evaluator_trainer = SFTTrainer(
    model=evaluator_model,
    tokenizer=evaluator_tokenizer,
    train_dataset=evaluator_train_text,
    eval_dataset=evaluator_val_text,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH_TASK,
    packing=False,
    dataset_num_proc=1,
    args=TrainingArguments(
        output_dir=str(OUTPUT_DIR / "evaluator_checkpoints"),
        per_device_train_batch_size=4,
        gradient_accumulation_steps=2,
        warmup_steps=20,
        num_train_epochs=3,
        learning_rate=1e-4,
        fp16=True,
        logging_steps=5,
        optim="adamw_8bit",
        seed=42,
        eval_strategy="steps",
        eval_steps=25,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        save_steps=25,
        save_total_limit=3,
        report_to="none",
    ),
)

print("Starting Adapter C (Evaluator) training...")
evaluator_stats = evaluator_trainer.train()
print("Evaluator adapter training complete.")
print(f"  Training loss : {evaluator_stats.training_loss:.4f}")

evaluator_model.save_pretrained(ADAPTER_EVALUATOR_DIR)
evaluator_tokenizer.save_pretrained(ADAPTER_EVALUATOR_DIR)
print(f"Evaluator adapter saved to: {ADAPTER_EVALUATOR_DIR}")

del evaluator_model, evaluator_trainer
gc.collect()
torch.cuda.empty_cache()
print("VRAM freed.")

# %%
!cp -r /content/d4bl_training/adapter_evaluator {DRIVE_DIR}/
print("Evaluator adapter backed up to Drive.")

# %% [markdown]
# ## 4. Phase 3: GGUF Export
#
# Each adapter is exported to GGUF format with q4_k_m quantization (~1.8GB each).
#
# **IMPORTANT:** Each export requires a runtime restart to free VRAM.
# Run each export cell, then the restart cell, then the next export.
# The sequence is:
# 1. Run parser export cell
# 2. Run restart cell → Reconnect
# 3. Run explainer export cell
# 4. Run restart cell → Reconnect
# 5. Run evaluator export cell

# %%
# --- Export Parser to GGUF ---
# (Run the restore cell at the top first if runtime was restarted)
from pathlib import Path
from unsloth import FastLanguageModel

OUTPUT_DIR = Path("/content/d4bl_training")
GGUF_DIR = OUTPUT_DIR / "gguf"
DRIVE_DIR = "/content/drive/MyDrive/d4bl_training"

print("--- Exporting parser to GGUF ---")
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=str(OUTPUT_DIR / "adapter_parser"),
    max_seq_length=2048,
    load_in_4bit=True,
)
model.save_pretrained_gguf(
    str(GGUF_DIR / "d4bl-query-parser-q4_k_m"),
    tokenizer,
    quantization_method="q4_k_m",
)
del model, tokenizer
import gc, torch
gc.collect()
torch.cuda.empty_cache()
print("Parser GGUF exported.")

!cp -r /content/d4bl_training/gguf {DRIVE_DIR}/
print("Backed up to Drive.")

# %%
# Restart runtime before next export
import os; os.kill(os.getpid(), 9)

# %%
# --- Export Explainer to GGUF ---
from google.colab import drive
drive.mount('/content/drive')

from pathlib import Path
from unsloth import FastLanguageModel

OUTPUT_DIR = Path("/content/d4bl_training")
GGUF_DIR = OUTPUT_DIR / "gguf"
DRIVE_DIR = "/content/drive/MyDrive/d4bl_training"

# Restore adapters from Drive if needed
import os, shutil
if not os.path.exists(str(OUTPUT_DIR / "adapter_explainer")):
    for item in os.listdir(DRIVE_DIR):
        src = f"{DRIVE_DIR}/{item}"
        dst = str(OUTPUT_DIR / item)
        if os.path.isdir(src) and not os.path.exists(dst):
            shutil.copytree(src, dst)
    print("Restored from Drive")

print("--- Exporting explainer to GGUF ---")
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=str(OUTPUT_DIR / "adapter_explainer"),
    max_seq_length=4096,
    load_in_4bit=True,
)
model.save_pretrained_gguf(
    str(GGUF_DIR / "d4bl-explainer-q4_k_m"),
    tokenizer,
    quantization_method="q4_k_m",
)
del model, tokenizer
import gc, torch
gc.collect()
torch.cuda.empty_cache()
print("Explainer GGUF exported.")

!cp -r /content/d4bl_training/gguf {DRIVE_DIR}/
print("Backed up to Drive.")

# %%
# Restart runtime before next export
import os; os.kill(os.getpid(), 9)

# %%
# --- Export Evaluator to GGUF ---
from google.colab import drive
drive.mount('/content/drive')

from pathlib import Path
from unsloth import FastLanguageModel

OUTPUT_DIR = Path("/content/d4bl_training")
GGUF_DIR = OUTPUT_DIR / "gguf"
DRIVE_DIR = "/content/drive/MyDrive/d4bl_training"

# Restore adapters from Drive if needed
import os, shutil
if not os.path.exists(str(OUTPUT_DIR / "adapter_evaluator")):
    for item in os.listdir(DRIVE_DIR):
        src = f"{DRIVE_DIR}/{item}"
        dst = str(OUTPUT_DIR / item)
        if os.path.isdir(src) and not os.path.exists(dst):
            shutil.copytree(src, dst)
    print("Restored from Drive")

print("--- Exporting evaluator to GGUF ---")
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=str(OUTPUT_DIR / "adapter_evaluator"),
    max_seq_length=2048,
    load_in_4bit=True,
)
model.save_pretrained_gguf(
    str(GGUF_DIR / "d4bl-evaluator-q4_k_m"),
    tokenizer,
    quantization_method="q4_k_m",
)
print("Evaluator GGUF exported.")

!cp -r /content/d4bl_training/gguf {DRIVE_DIR}/
print("All GGUFs backed up to Drive.")

# %% [markdown]
# ## 5. List and Download GGUF Files

# %%
import os
from pathlib import Path

GGUF_DIR = Path("/content/d4bl_training/gguf")

print(f"{'File':<55} {'Size (MB)':>10}")
print("-" * 67)
for root, dirs, files in os.walk(str(GGUF_DIR)):
    for f in sorted(files):
        if f.endswith(".gguf"):
            path = os.path.join(root, f)
            size = os.path.getsize(path) / (1024 * 1024)
            print(f"{path:<55} {size:>10.0f}")

# %%
# Download from Colab (alternative: download directly from Google Drive)
from google.colab import files as colab_files

print("Downloading GGUF files...")
for root, dirs, files in os.walk(str(GGUF_DIR)):
    for fname in sorted(files):
        if fname.endswith(".gguf"):
            fpath = os.path.join(root, fname)
            size_mb = os.path.getsize(fpath) / (1024 ** 2)
            print(f"  Downloading {fname} ({size_mb:.1f} MB)...")
            colab_files.download(fpath)

print("All downloads initiated.")

# %% [markdown]
# ## 6. Training Summary

# %%
print("=" * 60)
print("D4BL Fine-Tuning — Training Summary")
print("=" * 60)
print("\nAll GGUF models are ready for Ollama deployment.")
print("Place the .gguf files in the repo's models/ directory, then run:")
print("  python -m scripts.training.register_models")

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
# - **Mitigation:** Back up to Drive after each phase (cells included above)
# - If disconnected, run the restore cell at top to recover from Drive
#
# ### GGUF Export OOM
# - Each export must be in its own cell with runtime restart between them
# - Use `load_in_4bit=True` (not False) during export
# - The GGUF export loop from the original plan does NOT work on T4 — use
#   the separate cells with restarts instead
#
# ### Model Produces Narrative Instead of JSON
# - This means more training data is needed (current ~115 examples per task
#   is minimal for structured output learning)
# - Increase to 1000+ examples per task and 5-10 epochs
# - Ensure training data has proper ChatML formatting
#
# ### Resuming from Checkpoint
# ```python
# import glob
# checkpoints = sorted(glob.glob("outputs/query_parser/checkpoint-*"))
# latest = checkpoints[-1] if checkpoints else None
# print(f"Resuming from: {latest}")
# trainer.train(resume_from_checkpoint=latest)
# ```
