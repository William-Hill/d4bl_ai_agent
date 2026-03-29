# Qwen 3.5-4B Base Model Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the D4BL training pipeline from Qwen 2.5-3B to Qwen 3.5-4B, targeting A100 GPU.

**Architecture:** In-place migration of `train.py` — swap Unsloth's `FastLanguageModel` API for `FastModel`, update default model, bump sequence lengths and batch sizes for A100 VRAM, and version GGUF filenames to include the base model name.

**Tech Stack:** Unsloth (FastModel API), Qwen 3.5-4B, PyTorch, trl/SFTTrainer, Ollama Modelfiles

**Spec:** `docs/superpowers/specs/2026-03-29-qwen35-4b-upgrade-design.md`

---

### Task 1: Update Unsloth API import and default model in train.py

**Files:**
- Modify: `scripts/training/train.py`

- [ ] **Step 1: Replace FastLanguageModel import**

In `scripts/training/train.py`, change the import on line 28:

```python
# Old:
from unsloth import FastLanguageModel

# New:
from unsloth import FastModel
```

- [ ] **Step 2: Replace all FastLanguageModel references with FastModel**

There are 8 occurrences of `FastLanguageModel` in `train.py`. Replace all of them:

```python
# In train_domain_adapter() (line 332-342):
model, processor = FastModel.from_pretrained(
    model_name=model_name,
    max_seq_length=2048,
    dtype=None,
    load_in_4bit=True,
)

model = FastModel.get_peft_model(
    model,
    ...
)

# In train_task_adapter() (line 441-449):
model, processor = FastModel.from_pretrained(
    model_name=base_model_dir,
    max_seq_length=cfg["max_seq_length"],
    dtype=None,
    load_in_4bit=True,
)

model = FastModel.get_peft_model(
    model,
    ...
)

# In export_gguf() (line 549):
model, processor = FastModel.from_pretrained(
    model_name=str(adapter_dir),
    max_seq_length=max_seq_length,
    load_in_4bit=True,
)
```

- [ ] **Step 3: Rename all `tokenizer` variables to `processor`**

Throughout `train.py`, rename the variable `tokenizer` to `processor`. This affects:

- `train_domain_adapter()`: the return value from `from_pretrained`, and the `save_pretrained_merged` call
- `train_task_adapter()`: the return value from `from_pretrained`, the `format_and_tokenize` call, and the `save_pretrained` call
- `export_gguf()`: the return value from `from_pretrained`, and the `save_pretrained_gguf` call
- `SFTTrainer` instantiation: `processing_class=processor` (already named correctly)

In `train_domain_adapter()`:
```python
model, processor = FastModel.from_pretrained(...)
# ...
model.save_pretrained_merged(
    domain_merged_dir,
    processor,
    save_method="merged_16bit",
)
```

In `train_task_adapter()`:
```python
model, processor = FastModel.from_pretrained(...)
# ...
train_text = format_and_tokenize(train_dataset, processor)
val_text = format_and_tokenize(val_dataset, processor)
# ...
trainer = SFTTrainer(
    model=model,
    processing_class=processor,
    ...
)
# ...
model.save_pretrained(str(adapter_dir))
processor.save_pretrained(str(adapter_dir))
```

In `export_gguf()`:
```python
model, processor = FastModel.from_pretrained(...)
model.save_pretrained_gguf(
    str(gguf_subdir),
    processor,
    quantization_method=quantize,
)
# ...
del model, processor
```

- [ ] **Step 4: Rename the `format_and_tokenize` function parameter**

```python
# Old:
def format_and_tokenize(dataset: Dataset, tokenizer) -> Dataset:
    formatted = []
    for record in dataset:
        msgs = record["messages"]
        try:
            text = tokenizer.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=False
            )
        except (AttributeError, TypeError, KeyError, ValueError):
            ...
        formatted.append({"text": text})
    return Dataset.from_list(formatted)

# New:
def format_and_tokenize(dataset: Dataset, processor) -> Dataset:
    formatted = []
    for record in dataset:
        msgs = record["messages"]
        try:
            text = processor.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=False
            )
        except (AttributeError, TypeError, KeyError, ValueError):
            ...
        formatted.append({"text": text})
    return Dataset.from_list(formatted)
```

- [ ] **Step 5: Update default model in argparse**

```python
# Old (line 880):
parser.add_argument(
    "--model",
    type=str,
    default="unsloth/Qwen2.5-3B-Instruct",
    help="Base model name (HuggingFace or local path)",
)

# New:
parser.add_argument(
    "--model",
    type=str,
    default="unsloth/Qwen3.5-4B",
    help="Base model name (HuggingFace or local path)",
)
```

- [ ] **Step 6: Commit**

```bash
git add scripts/training/train.py
git commit -m "feat(training): migrate from FastLanguageModel to FastModel API for Qwen 3.5-4B (#140)"
```

---

### Task 2: Update sequence lengths and batch sizes for A100

**Files:**
- Modify: `scripts/training/train.py`

- [ ] **Step 1: Update domain adaptation sequence length and batch size**

In `train_domain_adapter()`, update the `from_pretrained` call and `SFTConfig`:

```python
# from_pretrained max_seq_length:
model, processor = FastModel.from_pretrained(
    model_name=model_name,
    max_seq_length=4096,  # was 2048
    dtype=None,
    load_in_4bit=True,
)

# SFTConfig:
args=SFTConfig(
    output_dir=str(output_dir / "phase1_checkpoints"),
    max_length=4096,  # was 2048
    dataset_text_field="text",
    per_device_train_batch_size=8,  # was 4
    ...
)
```

Also update the print statement and LoRA summary:

```python
print("      LoRA: r=16, all layers + embeddings, 1 epoch")
# Update the from_pretrained and SFTConfig max_seq_length references only
```

- [ ] **Step 2: Update ADAPTER_CONFIGS sequence lengths and batch sizes**

```python
ADAPTER_CONFIGS = {
    "parser": {
        "r": 8,
        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
        "lora_alpha": 16,
        "max_seq_length": 4096,  # was 2048
        "epochs": 7,
        "batch_size": 8,  # was 4
        "grad_accum": 2,
        "warmup_steps": 20,
        "lr": 1e-4,
        "eval_steps": 25,
        "save_steps": 25,
        "train_file": "query_parser_train.jsonl",
        "val_file": "query_parser_val.jsonl",
        "output_subdir": "adapter_parser",
        "checkpoint_subdir": "parser_checkpoints",
        "gguf_name": "d4bl-query-parser",  # updated in Task 3
    },
    "explainer": {
        "r": 32,
        "target_modules": [
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        "lora_alpha": 64,
        "max_seq_length": 8192,  # was 4096
        "epochs": 7,
        "batch_size": 4,  # was 2
        "grad_accum": 4,
        "warmup_steps": 30,
        "lr": 1e-4,
        "eval_steps": 20,
        "save_steps": 20,
        "train_file": "explainer_train.jsonl",
        "val_file": "explainer_val.jsonl",
        "output_subdir": "adapter_explainer",
        "checkpoint_subdir": "explainer_checkpoints",
        "gguf_name": "d4bl-explainer",  # updated in Task 3
    },
    "evaluator": {
        "r": 16,
        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
        "lora_alpha": 32,
        "max_seq_length": 4096,  # was 2048
        "epochs": 7,
        "batch_size": 8,  # was 4
        "grad_accum": 2,
        "warmup_steps": 20,
        "lr": 1e-4,
        "eval_steps": 25,
        "save_steps": 25,
        "train_file": "evaluator_train.jsonl",
        "val_file": "evaluator_val.jsonl",
        "output_subdir": "adapter_evaluator",
        "checkpoint_subdir": "evaluator_checkpoints",
        "gguf_name": "d4bl-evaluator",  # updated in Task 3
    },
}
```

- [ ] **Step 3: Commit**

```bash
git add scripts/training/train.py
git commit -m "feat(training): bump seq lengths and batch sizes for A100 (#140)"
```

---

### Task 3: Update GGUF naming

**Files:**
- Modify: `scripts/training/train.py`
- Modify: `scripts/training/register_models.py`

- [ ] **Step 1: Update gguf_name in ADAPTER_CONFIGS**

In `scripts/training/train.py`, update the `gguf_name` values in `ADAPTER_CONFIGS`:

```python
# parser:
"gguf_name": "d4bl-query-parser-qwen35",  # was "d4bl-query-parser"

# explainer:
"gguf_name": "d4bl-explainer-qwen35",  # was "d4bl-explainer"

# evaluator:
"gguf_name": "d4bl-evaluator-qwen35",  # was "d4bl-evaluator"
```

- [ ] **Step 2: Update MODELS dict in register_models.py**

In `scripts/training/register_models.py`, update the `gguf` values:

```python
MODELS = {
    "d4bl-query-parser": {
        "modelfile": "Modelfile.query-parser",
        "gguf": "d4bl-query-parser-qwen35-q4_k_m.gguf",  # was "d4bl-query-parser-q4_k_m.gguf"
        "smoke_prompt": (
            "What is the poverty rate for Black residents"
            " in Mississippi?"
        ),
        "validator": validate_parser_output,
    },
    "d4bl-explainer": {
        "modelfile": "Modelfile.explainer",
        "gguf": "d4bl-explainer-qwen35-q4_k_m.gguf",  # was "d4bl-explainer-q4_k_m.gguf"
        "smoke_prompt": (
            '{"metric": "poverty_rate", "geography": "Mississippi",'
            ' "race": "Black", "value": 28.4, "year": 2022}'
        ),
        "validator": validate_explainer_output,
    },
    "d4bl-evaluator": {
        "modelfile": "Modelfile.evaluator",
        "gguf": "d4bl-evaluator-qwen35-q4_k_m.gguf",  # was "d4bl-evaluator-q4_k_m.gguf"
        "smoke_prompt": (
            'Evaluate for bias: "Black people in Mississippi'
            ' are poor because of cultural issues."'
        ),
        "validator": validate_evaluator_output,
    },
}
```

- [ ] **Step 3: Commit**

```bash
git add scripts/training/train.py scripts/training/register_models.py
git commit -m "feat(training): version GGUF filenames with qwen35 base model (#140)"
```

---

### Task 4: Update Modelfiles

**Files:**
- Modify: `models/Modelfile.query-parser`
- Modify: `models/Modelfile.explainer`
- Modify: `models/Modelfile.evaluator`

- [ ] **Step 1: Update Modelfile.query-parser**

```
FROM ./d4bl-query-parser-qwen35-q4_k_m.gguf
PARAMETER temperature 0.1
PARAMETER num_ctx 4096
PARAMETER num_predict 512
PARAMETER stop "<|im_end|>"
TEMPLATE """<|im_start|>system
Parse the user's research question into a structured JSON object with keys: entities, search_queries, data_sources, community_framing. Respond with ONLY valid JSON.<|im_end|>
<|im_start|>user
{{ .Prompt }}<|im_end|>
<|im_start|>assistant
"""
```

- [ ] **Step 2: Update Modelfile.explainer**

```
FROM ./d4bl-explainer-qwen35-q4_k_m.gguf
PARAMETER temperature 0.3
PARAMETER num_ctx 8192
PARAMETER num_predict 1024
PARAMETER stop "<|im_end|>"
TEMPLATE """<|im_start|>system
Generate a structured JSON explanation of the provided data finding. Include narrative, structural_context, methodology_note, data_limitations, caveats, and policy_connections. Respond with ONLY valid JSON.<|im_end|>
<|im_start|>user
{{ .Prompt }}<|im_end|>
<|im_start|>assistant
"""
```

- [ ] **Step 3: Update Modelfile.evaluator**

```
FROM ./d4bl-evaluator-qwen35-q4_k_m.gguf
PARAMETER temperature 0.1
PARAMETER num_ctx 4096
PARAMETER num_predict 512
PARAMETER stop "<|im_end|>"
TEMPLATE """<|im_start|>system
Evaluate the model output against the provided context and return a structured JSON judgment. Respond with ONLY valid JSON.<|im_end|>
<|im_start|>user
{{ .Prompt }}<|im_end|>
<|im_start|>assistant
"""
```

- [ ] **Step 4: Commit**

```bash
git add models/Modelfile.query-parser models/Modelfile.explainer models/Modelfile.evaluator
git commit -m "feat(training): update Modelfiles for Qwen 3.5-4B GGUFs and context lengths (#140)"
```

---

### Task 5: Update Modelfile tests

**Files:**
- Modify: `tests/test_training/test_modelfiles.py`

- [ ] **Step 1: Update hardcoded num_ctx values in parametrized test**

In `tests/test_training/test_modelfiles.py`, update the `test_parameter_value` parametrization:

```python
@pytest.mark.parametrize("model,param,value", [
    ("query-parser", "temperature", "0.1"),
    ("query-parser", "num_ctx", "4096"),      # was "2048"
    ("explainer", "temperature", "0.3"),
    ("explainer", "num_ctx", "8192"),          # was "4096"
    ("evaluator", "temperature", "0.1"),
    ("evaluator", "num_ctx", "4096"),          # was "2048"
])
def test_parameter_value(self, model, param, value):
    content = MODELFILES[model].read_text()
    assert f"PARAMETER {param} {value}" in content
```

- [ ] **Step 2: Run the Modelfile tests**

Run: `pytest tests/test_training/test_modelfiles.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_training/test_modelfiles.py
git commit -m "test(training): update Modelfile test expectations for Qwen 3.5-4B (#140)"
```

---

### Task 6: Run full training test suite

**Files:** (none modified — verification only)

- [ ] **Step 1: Run all training tests**

Run: `pytest tests/test_training/ -v --ignore=tests/test_training/test_integration_models.py`
Expected: All tests PASS (integration tests skipped since they require Ollama with registered models)

- [ ] **Step 2: Verify no remaining references to FastLanguageModel or old defaults**

Run: `grep -rn "FastLanguageModel\|Qwen2\.5-3B\|d4bl-query-parser-q4_k_m\|d4bl-explainer-q4_k_m\|d4bl-evaluator-q4_k_m" scripts/training/ models/ tests/test_training/`
Expected: No matches (only docs/notebooks may still reference old model)
