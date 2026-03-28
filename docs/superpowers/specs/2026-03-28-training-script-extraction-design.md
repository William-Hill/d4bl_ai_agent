# Training Script Extraction — Design Spec

> **Epic:** #137 — Fine-Tuned Language Model
> **Sprint:** #138 — Extract training script from Colab notebook
> **Source:** `notebooks/training/d4bl_fine_tuning.py` (787 lines, Colab-style `.py` with `# %%` markers)
> **Output:** `scripts/training/train.py`

## Goal

Extract the interactive Colab training notebook into a headless CLI script that can run end-to-end on an A100 Colab runtime (or any CUDA GPU) without manual cell execution, file uploads, or runtime restarts. Add phase-level checkpointing, structured progress output, inline training health checks, and a post-training report.

## Non-Goals

- Apple Silicon / MPS support (future work)
- Multi-GPU / distributed training
- Hyperparameter search
- Integration with the D4BL app (Sprint 3)
- Changes to the training data pipeline (Sprint 1, already complete)

## CLI Interface

```bash
python scripts/training/train.py \
  --data-dir scripts/training_data/final \
  --output-dir /content/d4bl_training \
  --phases all \
  --model unsloth/Qwen2.5-3B-Instruct \
  --quantize q4_k_m \
  --force
```

### Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--data-dir` | `scripts/training_data/final` | Directory containing the 7 JSONL training data files |
| `--output-dir` | `/content/d4bl_training` | Root output directory for checkpoints, adapters, GGUFs |
| `--phases` | `all` | Comma-separated phases to run: `domain`, `parser`, `explainer`, `evaluator`, `export`, or `all` |
| `--model` | `unsloth/Qwen2.5-3B-Instruct` | Base model name (HuggingFace or local path) |
| `--quantize` | `q4_k_m` | GGUF quantization method |
| `--force` | `False` | Skip checkpoint detection, retrain everything |

### Required Training Data Files

The `--data-dir` must contain these files (produced by Sprint 1's pipeline):

| File | Used In |
|------|---------|
| `corpus_pretrain.jsonl` | Phase 1 — domain adaptation |
| `query_parser_train.jsonl` | Phase 2a — parser training |
| `query_parser_val.jsonl` | Phase 2a — parser validation |
| `explainer_train.jsonl` | Phase 2b — explainer training |
| `explainer_val.jsonl` | Phase 2b — explainer validation |
| `evaluator_train.jsonl` | Phase 2c — evaluator training |
| `evaluator_val.jsonl` | Phase 2c — evaluator validation |

The script validates all required files exist before starting any training.

## Architecture

Single file (`scripts/training/train.py`) with these top-level functions:

```
main()                          — argparse + orchestration
check_phase_complete()          — directory-based checkpoint detection
validate_data_dir()             — verify all 7 JSONL files exist
load_training_data()            — load all datasets into memory
train_domain_adapter()          — Phase 1: domain LoRA, merge, save
train_task_adapter()            — Phase 2: generic task adapter training
export_gguf()                   — Phase 3: single adapter → GGUF
run_health_checks()             — heuristic analysis of training metrics
generate_report()               — write training_report.md + telemetry JSON
```

Imports `config.py` for shared path constants. No new modules or abstractions.

### Dependencies

Same as the notebook (already in the Colab environment):
- `unsloth`, `trl`, `peft`, `accelerate`, `bitsandbytes`
- `transformers`, `datasets`, `huggingface_hub`, `torch`

No new dependencies added.

## Phase-Level Checkpointing

On startup, the script scans `--output-dir` for completed phase artifacts:

| Phase | Complete When |
|-------|---------------|
| Domain adaptation | `domain_merged/config.json` exists |
| Query parser | `adapter_parser/adapter_config.json` exists |
| Data explainer | `adapter_explainer/adapter_config.json` exists |
| Evaluator | `adapter_evaluator/adapter_config.json` exists |
| GGUF export (per model) | `gguf/d4bl-<name>-q4_k_m/*.gguf` file exists |

Skipped phases print clearly:

```
[1/5] Phase 1: Domain Adaptation
      ✓ domain_merged/ exists — skipping
```

The `--force` flag disables all checkpoint detection and retrains from scratch.

## Progress Output

### Startup Banner

```
══════════════════════════════════════════════════════
  D4BL Training Pipeline
  Model: unsloth/Qwen2.5-3B-Instruct
  Device: CUDA (NVIDIA A100-SXM4-40GB)
  Precision: bf16
  Output: /content/d4bl_training
══════════════════════════════════════════════════════
```

### Per-Phase Progress

A custom `transformers.TrainerCallback` captures step-level metrics and prints a progress line on each logging step:

```
[2/5] Phase 2a: Query Parser Adapter
      Dataset: 700 train / 88 val
      LoRA: r=8, attention only, 7 epochs
      Step  50/490 | epoch 1/7 | loss: 1.234 | eval_loss: — | lr: 9.2e-5
      Step 100/490 | epoch 2/7 | loss: 0.891 | eval_loss: 0.923 | lr: 8.4e-5
      ...
      Step 490/490 | epoch 7/7 | loss: 0.311 | eval_loss: 0.348 | lr: 0.0
      ✓ Saved to adapter_parser/ (14m 30s)
```

### GGUF Export Progress

```
[5/5] Phase 3: GGUF Export
      Exporting parser...    done (1.8 GB, 2m 15s)
      Exporting explainer... done (1.8 GB, 2m 20s)
      Exporting evaluator... done (1.8 GB, 2m 18s)
```

### Completion Banner

```
══════════════════════════════════════════════════════
  ✓ Complete — 3 GGUF files in /content/d4bl_training/gguf/
  Total time: 1h 47m
  Report: /content/d4bl_training/training_report.md
  Next: python -m scripts.training.register_models
══════════════════════════════════════════════════════
```

## Training Telemetry

### Metrics Captured

The custom `TrainerCallback` records every logging step into a per-phase list:

```python
{
    "step": 50,
    "epoch": 1.0,
    "train_loss": 1.234,
    "eval_loss": null,       # only on eval steps
    "learning_rate": 9.2e-5,
    "timestamp": "2026-03-28T14:32:00Z"
}
```

Per-phase summary stats:
- Start/end timestamps, total duration
- Dataset sizes (train/val)
- LoRA configuration (rank, target modules, alpha)
- Initial and final train/eval loss
- Best eval checkpoint (step, loss)

### Health Checks

After each training phase completes, run these heuristic checks against the collected metrics:

| Check | Condition | Severity |
|-------|-----------|----------|
| **Learning happened** | final eval_loss < initial eval_loss | FAIL |
| **Not overfitting** | eval_loss < 1.5 × train_loss | WARN |
| **Stable training** | No loss spikes > 3× rolling average (window=10) | WARN |
| **Loss converging** | Mean loss decreased over final 20% of steps | WARN |
| **Eval not diverging** | eval_loss trend is non-increasing over last 3 checkpoints | WARN |

Phase 1 (domain adaptation) only checks learning and stability since it has no eval set.

Results print inline:

```
[2/5] Phase 2a: Query Parser — Health Check
      ✓ Learning: eval_loss 1.82 → 0.41 (-77%)
      ✓ Overfit:  eval/train ratio 1.12 (< 1.5)
      ✓ Stability: no loss spikes detected
      ⚠ Plateau:  loss flat over last 15 steps — consider fewer epochs
```

A FAIL health check prints a prominent warning but does not abort training (the user may still want the other phases). The report flags it clearly.

## Training Report

Written to `{output_dir}/training_report.md` after all phases complete.

### Report Structure

```markdown
# D4BL Training Report — {timestamp}

## Configuration
- Model: {model_name}
- Device: {gpu_name}
- Precision: {bf16|fp16}
- Quantization: {quantize_method}
- Data directory: {data_dir}

## Summary
| Phase | Train Loss | Eval Loss | Overfit Ratio | Duration | Status |
|-------|-----------|-----------|---------------|----------|--------|
| Domain Adaptation | 0.892 | — | — | 32m | ✓ |
| Query Parser | 0.311 | 0.348 | 1.12 | 14m | ✓ |
| Explainer | 0.245 | 0.301 | 1.23 | 22m | ✓ |
| Evaluator | 0.287 | 0.335 | 1.17 | 16m | ✓ |

## Health Checks
- ✓ 4/4 phases completed
- ⚠ 1 warning: Parser loss plateaued in final 15 steps
- Recommendation: {any actionable suggestion}

## Per-Phase Details

### Phase 1: Domain Adaptation
- Dataset: {n} passages
- LoRA: r=16, all layers + embeddings, 1 epoch
- Loss curve: {initial} → {final} over {steps} steps
- Duration: {time}

### Phase 2a: Query Parser
- Dataset: {n_train} train / {n_val} val
- LoRA: r=8, attention only, 7 epochs
- Loss curve: {initial} → {final} over {steps} steps
- Eval checkpoints: [{losses at each eval step}]
- Best checkpoint: step {n} (eval_loss {x})
- Health: {pass/warn/fail per check}

### Phase 2b: Data Explainer
(same structure)

### Phase 2c: Evaluator
(same structure)

## GGUF Exports
| Model | File | Size |
|-------|------|------|
| d4bl-query-parser | d4bl-query-parser-q4_k_m.gguf | 1.8 GB |
| d4bl-explainer | d4bl-explainer-q4_k_m.gguf | 1.8 GB |
| d4bl-evaluator | d4bl-evaluator-q4_k_m.gguf | 1.8 GB |

## Total Training Time: {time}
```

### Raw Telemetry

Also written to `{output_dir}/training_telemetry.json`:

```json
{
    "config": { "model": "...", "device": "...", "precision": "...", "data_dir": "..." },
    "phases": {
        "domain": {
            "start": "...", "end": "...", "duration_seconds": 1920,
            "dataset_size": 52341,
            "lora": { "r": 16, "target_modules": [...], "alpha": 32 },
            "steps": [ { "step": 10, "train_loss": 2.34, ... }, ... ],
            "health_checks": { "learning": "pass", "stability": "pass" }
        },
        "parser": { ... },
        "explainer": { ... },
        "evaluator": { ... }
    },
    "exports": { "parser": { "path": "...", "size_bytes": ... }, ... },
    "total_duration_seconds": 6420
}
```

## VRAM Management

The notebook uses `os.kill(os.getpid(), 9)` between GGUF exports to free VRAM on T4 (15GB). On A100 (40GB), this is unnecessary — sequential `del model; gc.collect(); torch.cuda.empty_cache()` between phases is sufficient. The script uses this approach throughout.

If future use on T4 requires process-level isolation, the `--phases` flag enables running exports separately:
```bash
python scripts/training/train.py --phases export  # just GGUF exports
```

## Colab-Specific Removals

| Notebook Pattern | Script Replacement |
|------------------|--------------------|
| `from google.colab import files; files.upload()` | `--data-dir` CLI arg |
| `from google.colab import drive; drive.mount(...)` | User mounts Drive themselves, passes path |
| `from google.colab import userdata; userdata.get("HF_TOKEN")` | `os.environ["HF_TOKEN"]` (standard HF env var) |
| `!pip install unsloth ...` | Removed (pre-installed or user installs) |
| `os.kill(os.getpid(), 9)` | `del model; gc.collect(); torch.cuda.empty_cache()` |
| Hardcoded `/content/` paths | `--output-dir` CLI arg |
| `!cp -r ... {DRIVE_DIR}/` | Removed (user manages backup) |

## Testing

No pytest tests for this script (it requires a GPU to run meaningfully). Validation is via:
1. `--data-dir` validation (fails fast with clear error if files missing)
2. The training report itself serves as the test artifact
3. Existing `test_training/test_integration_models.py` validates the GGUF outputs after `register_models.py`
