# Upgrade Base Model to Qwen 3.5-4B

**Issue:** #140
**Date:** 2026-03-29
**Status:** Design approved

## Motivation

The v1.0 eval harness showed 0% hallucination detection accuracy and 59% entity F1. Two levers address this: expanded training data (#139, merged) and a stronger base model. Qwen 3.5-4B offers 256K context, improved reasoning benchmarks, and Gated Delta Networks for faster inference — a meaningful upgrade from Qwen 2.5-3B.

## Approach

Minimal in-place migration of `scripts/training/train.py` and related files. No new abstractions or duplicate scripts. The `--model` CLI flag remains for flexibility.

## Changes

### 1. Unsloth API Migration

| Current | New |
|---------|-----|
| `from unsloth import FastLanguageModel` | `from unsloth import FastModel` |
| `FastLanguageModel.from_pretrained(...)` | `FastModel.from_pretrained(...)` |
| `FastLanguageModel.get_peft_model(...)` | `FastModel.get_peft_model(...)` |
| Default `--model`: `unsloth/Qwen2.5-3B-Instruct` | `unsloth/Qwen3.5-4B` |

`FastModel.from_pretrained()` returns a multimodal processor instead of a plain tokenizer. The processor still supports `apply_chat_template()` and works with `SFTTrainer(processing_class=...)`. Rename `tokenizer` variables to `processor` throughout for clarity.

### 2. Sequence Lengths (targeting A100)

| Adapter | Current | New |
|---------|---------|-----|
| Domain adaptation | 2048 | 4096 |
| Parser | 2048 | 4096 |
| Explainer | 4096 | 8192 |
| Evaluator | 2048 | 4096 |

### 3. Batch Sizes (targeting A100 40GB VRAM)

LoRA ranks stay unchanged (ablation discipline — isolate model + data improvements).

| Adapter | Current batch x grad_accum | New batch x grad_accum | Effective batch |
|---------|---------------------------|------------------------|-----------------|
| Domain | 4 x 4 | 8 x 4 | 32 |
| Parser | 4 x 2 | 8 x 2 | 16 |
| Explainer | 2 x 4 | 4 x 4 | 16 |
| Evaluator | 4 x 2 | 8 x 2 | 16 |

### 4. GGUF Naming

Pattern: `d4bl-{adapter}-qwen35-{quantize}.gguf`

- `d4bl-query-parser-qwen35-q4_k_m.gguf`
- `d4bl-explainer-qwen35-q4_k_m.gguf`
- `d4bl-evaluator-qwen35-q4_k_m.gguf`

### 5. Files Modified

| File | Changes |
|------|---------|
| `scripts/training/train.py` | `FastLanguageModel` -> `FastModel`, default model, seq lengths, batch sizes, `tokenizer` -> `processor`, `gguf_name` values |
| `scripts/training/register_models.py` | GGUF filename references in `MODELS` dict |
| `models/Modelfile.query-parser` | `FROM` line, `num_ctx` 2048 -> 4096 |
| `models/Modelfile.explainer` | `FROM` line, `num_ctx` 4096 -> 8192 |
| `models/Modelfile.evaluator` | `FROM` line, `num_ctx` 2048 -> 4096 |

### 6. No Changes Needed

- `eval_harness.py`, `validate_model_output.py` — operate on model outputs, model-agnostic
- `ship_criteria.py`, `compare_models.py` — consume metrics dicts, no model-specific logic
- `config.py`, `generate_training_pairs.py` — training data pipeline, unrelated to model loading
- Tests — update any `FastLanguageModel` mocks to `FastModel`

## Non-Goals

- Changing LoRA ranks or architectures (isolate variables for ablation)
- Adding model profile abstraction (YAGNI)
- Supporting Qwen 2.5 and 3.5 simultaneously in the same run
