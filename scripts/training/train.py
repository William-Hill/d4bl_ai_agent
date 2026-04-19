#!/usr/bin/env python3
"""D4BL Training Pipeline — Headless CLI Script.

Extracts the three-phase LoRA fine-tuning pipeline from the Colab notebook
into a script that runs end-to-end on any CUDA GPU.

Usage:
    python scripts/training/train.py --data-dir scripts/training_data/final
    python scripts/training/train.py --phases parser,explainer --force
    python scripts/training/train.py --output-dir /content/d4bl_training --phases export
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import torch
from datasets import Dataset
from huggingface_hub import login
from transformers import TrainerCallback
from trl import SFTConfig, SFTTrainer
from unsloth import FastModel

from scripts.training.config import FINAL_DIR

# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

ALL_PHASES = ["domain", "parser", "explainer", "evaluator", "export"]

ADAPTER_LABELS = {
    "parser": "2a: Query Parser",
    "explainer": "2b: Data Explainer",
    "evaluator": "2c: Evaluator",
}

STATUS_ICONS = {"pass": "\u2713", "warn": "\u26a0", "fail": "\u2717"}

ADAPTER_CONFIGS = {
    "parser": {
        "r": 8,
        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
        "lora_alpha": 16,
        "max_seq_length": 4096,
        "epochs": 7,
        "batch_size": 8,
        "grad_accum": 2,
        "warmup_steps": 20,
        "lr": 1e-4,
        "eval_steps": 25,
        "save_steps": 25,
        "train_file": "query_parser_train.jsonl",
        "val_file": "query_parser_val.jsonl",
        "output_subdir": "adapter_parser",
        "checkpoint_subdir": "parser_checkpoints",
        "gguf_name": "d4bl-query-parser-qwen35",
    },
    "explainer": {
        "r": 16,
        "target_modules": [
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        "lora_alpha": 32,
        "max_seq_length": 8192,
        "epochs": 4,
        "batch_size": 4,
        "grad_accum": 4,
        "warmup_steps": 30,
        "lr": 1e-4,
        "eval_steps": 20,
        "save_steps": 20,
        "train_file": "explainer_train.jsonl",
        "val_file": "explainer_val.jsonl",
        "output_subdir": "adapter_explainer",
        "checkpoint_subdir": "explainer_checkpoints",
        "gguf_name": "d4bl-explainer-qwen35",
    },
    "evaluator": {
        "r": 16,
        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
        "lora_alpha": 32,
        "max_seq_length": 4096,
        "epochs": 7,
        "batch_size": 8,
        "grad_accum": 2,
        "warmup_steps": 20,
        "lr": 1e-4,
        "eval_steps": 25,
        "save_steps": 25,
        "train_file": "evaluator_train.jsonl",
        "val_file": "evaluator_val.jsonl",
        "output_subdir": "adapter_evaluator",
        "checkpoint_subdir": "evaluator_checkpoints",
        "gguf_name": "d4bl-evaluator-qwen35",
    },
}


# ──────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────

def _get_hf_token() -> str | None:
    """Read HF_TOKEN from environment. Returns None if not set."""
    import os
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("  Warning: HF_TOKEN not set. Model downloads may fail for gated models.")
    return token


def _format_duration(seconds: float) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours = int(minutes // 60)
    mins = minutes % 60
    return f"{hours}h {mins:02d}m"


def _now_utc() -> str:
    """ISO 8601 UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def print_banner(args: argparse.Namespace, device_name: str, precision: str) -> None:
    """Print the startup banner."""
    print("\n" + "\u2550" * 54)
    print("  D4BL Training Pipeline")
    print(f"  Model:     {args.model}")
    print(f"  Device:    CUDA ({device_name})")
    print(f"  Precision: {precision}")
    print(f"  Output:    {args.output_dir}")
    print(f"  Phases:    {', '.join(args.phases)}")
    if args.force:
        print("  Mode:      FORCE (ignoring checkpoints)")
    print("\u2550" * 54)


def print_completion_banner(output_dir: Path, total_seconds: float) -> None:
    """Print the completion banner."""
    gguf_dir = output_dir / "gguf"
    gguf_count = sum(1 for d in gguf_dir.iterdir() if d.is_dir()) if gguf_dir.exists() else 0
    print("\n" + "\u2550" * 54)
    print(f"  \u2713 Complete \u2014 {gguf_count} GGUF files in {gguf_dir}")
    print(f"  Total time: {_format_duration(total_seconds)}")
    print(f"  Report: {output_dir / 'training_report.md'}")
    print("  Next: python -m scripts.training.register_models")
    print("\u2550" * 54 + "\n")


def validate_data_dir(data_dir: Path, phases: list[str]) -> None:
    """Validate that required training data files exist.

    Only checks files needed by the requested phases.
    """
    needed: list[str] = []
    if "domain" in phases:
        needed.append("corpus_pretrain.jsonl")
    for adapter_name in ["parser", "explainer", "evaluator"]:
        if adapter_name in phases:
            cfg = ADAPTER_CONFIGS[adapter_name]
            needed.append(cfg["train_file"])
            needed.append(cfg["val_file"])

    missing = [f for f in needed if not (data_dir / f).exists()]
    if missing:
        print(f"\nERROR: Missing training data files in {data_dir}:")
        for f in missing:
            print(f"  - {f}")
        print("\nRun the training data pipeline first:")
        print("  python -m scripts.training.prepare_dataset")
        sys.exit(1)
    print(f"\n  Data directory: {data_dir} ({len(needed)} files validated)")


def check_phase_complete(path: Path, phase_type: str) -> bool:
    """Check if a phase has already completed by looking for output artifacts."""
    if phase_type == "domain":
        return (path / "config.json").exists()
    elif phase_type == "adapter":
        return (path / "adapter_config.json").exists()
    elif phase_type == "gguf":
        if not path.exists():
            return False
        return any(f.suffix == ".gguf" for f in path.iterdir())
    return False


def load_jsonl(path: Path, require_text: bool = False) -> list[dict]:
    """Read a JSONL file into a list of dicts."""
    records = []
    with open(path, encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_no}: expected JSON object")
            if require_text and ("text" not in record or not isinstance(record["text"], str)):
                raise ValueError(f"{path}:{line_no}: missing or invalid 'text' field")
            records.append(record)
    return records


def load_dataset_from_jsonl(path: Path, require_text: bool = False) -> Dataset:
    """Load a JSONL file as a HuggingFace Dataset."""
    records = load_jsonl(path, require_text=require_text)
    return Dataset.from_list(records)


def format_and_tokenize(dataset: Dataset, processor) -> Dataset:
    """Convert messages-format dataset to plain text using the model's chat template.

    Falls back to manual ChatML if the processor lacks a chat template.
    """
    formatted = []
    for record in dataset:
        msgs = record["messages"]
        try:
            text = processor.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=False
            )
        except (AttributeError, TypeError, KeyError, ValueError):
            parts = []
            for msg in msgs:
                parts.append(f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>")
            text = "\n".join(parts) + "\n"
        formatted.append({"text": text})
    return Dataset.from_list(formatted)



def free_vram() -> None:
    """Run garbage collection and flush CUDA memory cache.

    Callers must `del` their own model/trainer references before calling
    this, since Python cannot unbind a caller's local variables.
    """
    gc.collect()
    torch.cuda.empty_cache()


# ──────────────────────────────────────────────────────────────────────
# Telemetry
# ──────────────────────────────────────────────────────────────────────

class TelemetryCallback(TrainerCallback):
    """Captures per-step training metrics and prints progress."""

    def __init__(self, phase_label: str, phase_num: int, total_phases: int):
        self.phase_label = phase_label
        self.phase_num = phase_num
        self.total_phases = total_phases
        self.steps: list[dict] = []
        self.total_steps: int | None = None

    def on_train_begin(self, args, state, control, **kwargs):
        self.total_steps = state.max_steps

    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs is None:
            return
        entry = {
            "step": state.global_step,
            "epoch": round(state.epoch, 2) if state.epoch else None,
            "train_loss": logs.get("loss"),
            "eval_loss": logs.get("eval_loss"),
            "learning_rate": logs.get("learning_rate"),
            "timestamp": _now_utc(),
        }
        self.steps.append(entry)

        # Print progress line
        step = state.global_step
        total = self.total_steps or "?"
        epoch_str = f"epoch {entry['epoch']:.1f}" if entry["epoch"] else ""
        loss_str = f"loss: {entry['train_loss']:.4f}" if entry["train_loss"] is not None else ""
        eval_str = f"eval_loss: {entry['eval_loss']:.4f}" if entry["eval_loss"] is not None else ""
        lr_str = f"lr: {entry['learning_rate']:.1e}" if entry["learning_rate"] is not None else ""
        parts = [p for p in [epoch_str, loss_str, eval_str, lr_str] if p]
        print(f"      Step {step:>4}/{total} | {' | '.join(parts)}")

    def get_summary(self) -> dict:
        """Return a summary dict of the training metrics."""
        if not self.steps:
            return {}
        train_losses = [s["train_loss"] for s in self.steps if s["train_loss"] is not None]
        eval_losses = [s["eval_loss"] for s in self.steps if s["eval_loss"] is not None]
        return {
            "initial_train_loss": train_losses[0] if train_losses else None,
            "final_train_loss": train_losses[-1] if train_losses else None,
            "initial_eval_loss": eval_losses[0] if eval_losses else None,
            "final_eval_loss": eval_losses[-1] if eval_losses else None,
            "eval_checkpoints": eval_losses,
            "best_eval_loss": min(eval_losses) if eval_losses else None,
            "total_steps": self.total_steps,
            "steps": self.steps,
        }


# ──────────────────────────────────────────────────────────────────────
# Phase 1: Domain Adaptation
# ──────────────────────────────────────────────────────────────────────

def train_domain_adapter(
    model_name: str,
    corpus_dataset: Dataset,
    output_dir: Path,
    use_bf16: bool,
) -> dict:
    """Phase 1: Domain-adaptive LoRA pre-training, then merge into base weights."""
    start_timestamp = _now_utc()
    phase_start = time.monotonic()
    print("\n      Phase 1: Domain Adaptation")
    print(f"      Dataset: {len(corpus_dataset)} passages")
    print("      LoRA: r=16, all layers + embeddings, 1 epoch")

    # Load base model in 4-bit
    model, processor = FastModel.from_pretrained(
        model_name=model_name,
        max_seq_length=4096,
        dtype=None,
        load_in_4bit=True,
    )
    print("      Base model loaded.")

    # Attach domain LoRA
    model = FastModel.get_peft_model(
        model,
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
    model.print_trainable_parameters()

    # Train
    callback = TelemetryCallback("Domain Adaptation", 1, 5)
    trainer = SFTTrainer(
        model=model,
        processing_class=processor,
        train_dataset=corpus_dataset,
        callbacks=[callback],
        args=SFTConfig(
            output_dir=str(output_dir / "phase1_checkpoints"),
            max_length=4096,
            dataset_text_field="text",
            per_device_train_batch_size=8,
            gradient_accumulation_steps=4,
            warmup_steps=50,
            num_train_epochs=1,
            learning_rate=2e-4,
            fp16=not use_bf16,
            bf16=use_bf16,
            logging_steps=10,
            optim="adamw_8bit",
            seed=42,
            save_steps=500,
            save_total_limit=2,
            report_to="none",
        ),
    )

    print("      Training...")
    checkpoint_dir = output_dir / "phase1_checkpoints"
    resume = str(checkpoint_dir) if checkpoint_dir.exists() and any(checkpoint_dir.iterdir()) else None
    train_result = trainer.train(resume_from_checkpoint=resume)
    duration = time.monotonic() - phase_start

    # Merge LoRA into base weights
    domain_merged_dir = str(output_dir / "domain_merged")
    print("      Merging domain LoRA into base weights...")
    model.save_pretrained_merged(
        domain_merged_dir,
        processor,
        save_method="merged_16bit",
    )
    print(f"      \u2713 Saved to domain_merged/ ({_format_duration(duration)})")

    summary = callback.get_summary()
    summary.update({
        "phase": "domain",
        "dataset_size": len(corpus_dataset),
        "lora": {"r": 16, "target_modules": "all + embeddings", "alpha": 32},
        "training_loss": train_result.training_loss,
        "start": start_timestamp,
        "duration_seconds": round(duration, 1),
    })

    del model, trainer
    free_vram()
    return summary


# ──────────────────────────────────────────────────────────────────────
# Phase 2: Task-Specific Adapters
# ──────────────────────────────────────────────────────────────────────

def train_task_adapter(
    adapter_name: str,
    base_model_dir: str,
    train_dataset: Dataset,
    val_dataset: Dataset,
    output_dir: Path,
    cfg: dict,
    use_bf16: bool,
    phase_num: int,
    total_phases: int,
) -> dict:
    """Train a single task-specific LoRA adapter on the domain-merged base."""
    start_timestamp = _now_utc()
    phase_start = time.monotonic()
    label = ADAPTER_LABELS[adapter_name]

    print(f"\n[{phase_num}/{total_phases}] Phase {label} Adapter")
    print(f"      Dataset: {len(train_dataset)} train / {len(val_dataset)} val")
    print(f"      LoRA: r={cfg['r']}, {len(cfg['target_modules'])} modules, {cfg['epochs']} epochs")

    # Load domain-merged base
    model, processor = FastModel.from_pretrained(
        model_name=base_model_dir,
        max_seq_length=cfg["max_seq_length"],
        dtype=None,
        load_in_4bit=True,
    )

    # Attach task LoRA
    model = FastModel.get_peft_model(
        model,
        r=cfg["r"],
        target_modules=cfg["target_modules"],
        lora_alpha=cfg["lora_alpha"],
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )
    model.print_trainable_parameters()

    # Convert messages -> text using chat template
    train_text = format_and_tokenize(train_dataset, processor)
    val_text = format_and_tokenize(val_dataset, processor)
    print(f"      Formatted: {len(train_text)} train, {len(val_text)} val")

    # Train
    callback = TelemetryCallback(label, phase_num, total_phases)
    trainer = SFTTrainer(
        model=model,
        processing_class=processor,
        train_dataset=train_text,
        eval_dataset=val_text,
        callbacks=[callback],
        args=SFTConfig(
            output_dir=str(output_dir / cfg["checkpoint_subdir"]),
            max_length=cfg["max_seq_length"],
            dataset_text_field="text",
            packing=False,
            per_device_train_batch_size=cfg["batch_size"],
            gradient_accumulation_steps=cfg["grad_accum"],
            warmup_steps=cfg["warmup_steps"],
            num_train_epochs=cfg["epochs"],
            learning_rate=cfg["lr"],
            fp16=not use_bf16,
            bf16=use_bf16,
            logging_steps=5,
            optim="adamw_8bit",
            seed=42,
            eval_strategy="steps",
            eval_steps=cfg["eval_steps"],
            load_best_model_at_end=True,
            metric_for_best_model="eval_loss",
            save_steps=cfg["save_steps"],
            save_total_limit=3,
            report_to="none",
        ),
    )

    print("      Training...")
    checkpoint_dir = output_dir / cfg["checkpoint_subdir"]
    resume = str(checkpoint_dir) if checkpoint_dir.exists() and any(checkpoint_dir.iterdir()) else None
    train_result = trainer.train(resume_from_checkpoint=resume)
    duration = time.monotonic() - phase_start

    # Save adapter weights
    adapter_dir = output_dir / cfg["output_subdir"]
    model.save_pretrained(str(adapter_dir))
    processor.save_pretrained(str(adapter_dir))
    print(f"      \u2713 Saved to {cfg['output_subdir']}/ ({_format_duration(duration)})")

    summary = callback.get_summary()
    summary.update({
        "phase": adapter_name,
        "dataset_size_train": len(train_dataset),
        "dataset_size_val": len(val_dataset),
        "lora": {
            "r": cfg["r"],
            "target_modules": cfg["target_modules"],
            "alpha": cfg["lora_alpha"],
        },
        "training_loss": train_result.training_loss,
        "start": start_timestamp,
        "duration_seconds": round(duration, 1),
    })

    del model, trainer
    free_vram()
    return summary


# ──────────────────────────────────────────────────────────────────────
# Phase 3: GGUF Export
# ──────────────────────────────────────────────────────────────────────

def export_gguf(
    adapter_dir: Path,
    output_dir: Path,
    gguf_name: str,
    quantize: str,
    max_seq_length: int,
) -> dict:
    """Export a single adapter to GGUF format."""
    export_start = time.monotonic()
    gguf_subdir = output_dir / "gguf" / f"{gguf_name}-{quantize}"
    gguf_subdir.mkdir(parents=True, exist_ok=True)

    print(f"      Exporting {gguf_name}...", end=" ", flush=True)

    model, processor = FastModel.from_pretrained(
        model_name=str(adapter_dir),
        max_seq_length=max_seq_length,
        load_in_4bit=True,
    )
    model.save_pretrained_gguf(
        str(gguf_subdir),
        processor,
        quantization_method=quantize,
    )

    # Find the .gguf file and report size
    gguf_files = list(gguf_subdir.glob("*.gguf"))
    size_bytes = sum(f.stat().st_size for f in gguf_files)
    size_gb = size_bytes / (1024 ** 3)
    duration = time.monotonic() - export_start

    print(f"done ({size_gb:.1f} GB, {_format_duration(duration)})")

    del model, processor
    free_vram()
    return {
        "gguf_name": gguf_name,
        "path": str(gguf_subdir),
        "size_bytes": size_bytes,
        "duration_seconds": round(duration, 1),
    }


# ──────────────────────────────────────────────────────────────────────
# Health Checks
# ──────────────────────────────────────────────────────────────────────

def run_health_checks(phase_name: str, stats: dict) -> dict[str, dict]:
    """Run heuristic health checks on training telemetry.

    Returns a dict of check_name -> {"status": "pass"|"warn"|"fail", "message": str}.
    """
    checks: dict[str, dict] = {}
    steps = stats.get("steps", [])
    train_losses = [s["train_loss"] for s in steps if s["train_loss"] is not None]
    eval_losses = [s["eval_loss"] for s in steps if s["eval_loss"] is not None]

    # Check 1: Learning happened
    if eval_losses:
        initial, final = eval_losses[0], eval_losses[-1]
        pct = (1 - final / initial) * 100 if initial > 0 else 0
        if final < initial:
            checks["learning"] = {
                "status": "pass",
                "message": f"eval_loss {initial:.3f} \u2192 {final:.3f} ({pct:+.0f}%)",
            }
        else:
            checks["learning"] = {
                "status": "fail",
                "message": f"eval_loss {initial:.3f} \u2192 {final:.3f} (no improvement)",
            }
    elif train_losses:
        initial, final = train_losses[0], train_losses[-1]
        pct = (1 - final / initial) * 100 if initial > 0 else 0
        if final < initial:
            checks["learning"] = {
                "status": "pass",
                "message": f"train_loss {initial:.3f} \u2192 {final:.3f} ({pct:+.0f}%)",
            }
        else:
            checks["learning"] = {
                "status": "fail",
                "message": f"train_loss {initial:.3f} \u2192 {final:.3f} (no improvement)",
            }

    # Check 2: Not overfitting (eval/train ratio)
    if eval_losses and train_losses:
        final_eval = eval_losses[-1]
        final_train = train_losses[-1]
        ratio = final_eval / final_train if final_train > 0 else float("inf")
        if ratio < 1.5:
            checks["overfit"] = {
                "status": "pass",
                "message": f"eval/train ratio {ratio:.2f} (< 1.5)",
            }
        else:
            checks["overfit"] = {
                "status": "warn",
                "message": f"eval/train ratio {ratio:.2f} (\u2265 1.5 \u2014 possible overfitting)",
            }

    # Check 3: Stable training (no spikes > 3x rolling average)
    if len(train_losses) >= 10:
        window = 10
        spikes = 0
        for i in range(window, len(train_losses)):
            rolling_avg = sum(train_losses[i - window : i]) / window
            if train_losses[i] > 3 * rolling_avg:
                spikes += 1
        if spikes == 0:
            checks["stability"] = {"status": "pass", "message": "no loss spikes detected"}
        else:
            checks["stability"] = {
                "status": "warn",
                "message": f"{spikes} loss spike(s) > 3x rolling average",
            }

    # Check 4: Loss converging (final 20% trending down)
    if len(train_losses) >= 10:
        tail_start = int(len(train_losses) * 0.8)
        tail = train_losses[tail_start:]
        if len(tail) >= 2:
            tail_mean_first_half = sum(tail[: len(tail) // 2]) / (len(tail) // 2)
            tail_mean_second_half = sum(tail[len(tail) // 2 :]) / (len(tail) - len(tail) // 2)
            if tail_mean_second_half <= tail_mean_first_half:
                checks["convergence"] = {"status": "pass", "message": "loss still decreasing"}
            else:
                checks["convergence"] = {
                    "status": "warn",
                    "message": f"loss flat/rising in final {len(tail)} steps \u2014 consider fewer epochs",
                }

    # Check 5: Eval not diverging (last 3 eval checkpoints)
    if len(eval_losses) >= 3:
        last3 = eval_losses[-3:]
        if last3[-1] <= last3[0]:
            checks["eval_trend"] = {"status": "pass", "message": "eval_loss trending down"}
        else:
            checks["eval_trend"] = {
                "status": "warn",
                "message": f"eval_loss rising over last 3 checkpoints: {[f'{loss:.3f}' for loss in last3]}",
            }

    return checks


def print_health_checks(
    phase_num: int, total_phases: int, label: str, checks: dict[str, dict]
) -> None:
    """Print health check results inline."""
    print(f"\n      {label} \u2014 Health Check")
    status_icons = STATUS_ICONS
    for name, check in checks.items():
        icon = status_icons.get(check["status"], "?")
        print(f"      {icon} {name.capitalize()}: {check['message']}")


# ──────────────────────────────────────────────────────────────────────
# Report Generation
# ──────────────────────────────────────────────────────────────────────

def generate_report(output_dir: Path, telemetry: dict) -> None:
    """Write training_report.md and training_telemetry.json."""
    config = telemetry["config"]
    phases = telemetry["phases"]
    exports = telemetry["exports"]
    total_time = telemetry.get("total_duration_seconds", 0)

    # ── Markdown report ──
    lines: list[str] = []
    lines.append(f"# D4BL Training Report \u2014 {_now_utc()}\n")

    lines.append("## Configuration\n")
    lines.append(f"- **Model:** {config['model']}")
    lines.append(f"- **Device:** {config.get('device', 'unknown')}")
    lines.append(f"- **Precision:** {config.get('precision', 'unknown')}")
    lines.append(f"- **Quantization:** {config['quantize']}")
    lines.append(f"- **Data directory:** {config['data_dir']}")
    lines.append("")

    # Summary table
    lines.append("## Summary\n")
    lines.append("| Phase | Train Loss | Eval Loss | Overfit Ratio | Duration | Status |")
    lines.append("|-------|-----------|-----------|---------------|----------|--------|")

    phase_labels = {
        "domain": "Domain Adaptation",
        "parser": "Query Parser",
        "explainer": "Data Explainer",
        "evaluator": "Evaluator",
    }
    total_warnings = 0
    total_fails = 0
    for name, label in phase_labels.items():
        if name not in phases:
            continue
        p = phases[name]
        train_loss = p.get("final_train_loss") or p.get("training_loss")
        eval_loss = p.get("final_eval_loss")
        train_str = f"{train_loss:.3f}" if train_loss is not None else "\u2014"
        eval_str = f"{eval_loss:.3f}" if eval_loss is not None else "\u2014"

        checks = p.get("health_checks", {})
        n_warn = sum(1 for c in checks.values() if c["status"] == "warn")
        n_fail = sum(1 for c in checks.values() if c["status"] == "fail")
        total_warnings += n_warn
        total_fails += n_fail
        if n_fail > 0:
            status = "\u2717 FAIL"
        elif n_warn > 0:
            status = f"\u26a0 {n_warn} warn"
        else:
            status = "\u2713"

        overfit = checks.get("overfit", {})
        if "overfit" in checks:
            # Extract the ratio number from "eval/train ratio 1.12 (< 1.5)"
            msg = overfit.get("message", "")
            parts = msg.split("ratio ")
            overfit_str = parts[1].split(" ")[0] if len(parts) > 1 else "\u2014"
        else:
            overfit_str = "\u2014"

        duration_str = _format_duration(p.get("duration_seconds", 0))
        lines.append(f"| {label} | {train_str} | {eval_str} | {overfit_str} | {duration_str} | {status} |")

    lines.append("")

    # Health check summary
    lines.append("## Health Checks\n")
    total_phases_trained = len(phases)
    phases_with_failures = sum(
        1 for p in phases.values()
        if any(c["status"] == "fail" for c in p.get("health_checks", {}).values())
    )
    passed = total_phases_trained - phases_with_failures
    lines.append(f"- {passed}/{total_phases_trained} phases passed all checks")
    if total_warnings:
        lines.append(f"- {total_warnings} warning(s) across all phases")
    if total_fails:
        lines.append(f"- {total_fails} FAILURE(s) \u2014 review per-phase details below")
    lines.append("")

    # Per-phase details
    lines.append("## Per-Phase Details\n")
    for name, label in phase_labels.items():
        if name not in phases:
            continue
        p = phases[name]
        lines.append(f"### {label}\n")

        ds_size = p.get("dataset_size") or p.get("dataset_size_train")
        if ds_size:
            val_size = p.get("dataset_size_val")
            if val_size:
                lines.append(f"- **Dataset:** {ds_size} train / {val_size} val")
            else:
                lines.append(f"- **Dataset:** {ds_size} passages")

        lora = p.get("lora", {})
        if lora:
            lines.append(f"- **LoRA:** r={lora.get('r')}, alpha={lora.get('alpha')}, modules={lora.get('target_modules')}")

        train_loss = p.get("training_loss")
        if train_loss is not None:
            lines.append(f"- **Final training loss:** {train_loss:.4f}")

        initial_eval = p.get("initial_eval_loss")
        final_eval = p.get("final_eval_loss")
        if initial_eval is not None and final_eval is not None:
            lines.append(f"- **Eval loss:** {initial_eval:.3f} \u2192 {final_eval:.3f}")

        best = p.get("best_eval_loss")
        if best is not None:
            lines.append(f"- **Best eval loss:** {best:.4f}")

        eval_ckpts = p.get("eval_checkpoints", [])
        if eval_ckpts:
            ckpt_strs = [f"{loss:.3f}" for loss in eval_ckpts]
            lines.append(f"- **Eval checkpoints:** [{', '.join(ckpt_strs)}]")

        duration = p.get("duration_seconds", 0)
        lines.append(f"- **Duration:** {_format_duration(duration)}")

        checks = p.get("health_checks", {})
        if checks:
            status_icons = STATUS_ICONS
            lines.append("- **Health:**")
            for check_name, check in checks.items():
                icon = status_icons.get(check["status"], "?")
                lines.append(f"  - {icon} {check_name}: {check['message']}")
        lines.append("")

    # GGUF exports
    if exports:
        lines.append("## GGUF Exports\n")
        lines.append("| Model | Path | Size |")
        lines.append("|-------|------|------|")
        for name, info in exports.items():
            size_gb = info["size_bytes"] / (1024 ** 3)
            lines.append(f"| {info['gguf_name']} | `{info['path']}` | {size_gb:.1f} GB |")
        lines.append("")

    lines.append(f"## Total Training Time: {_format_duration(total_time)}\n")

    # Write report
    report_path = output_dir / "training_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  Report written to: {report_path}")

    # ── JSON telemetry ──
    telemetry_path = output_dir / "training_telemetry.json"
    telemetry_path.write_text(
        json.dumps(telemetry, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"  Telemetry written to: {telemetry_path}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="D4BL Training Pipeline — headless LoRA fine-tuning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=FINAL_DIR,
        help="Directory containing the 7 JSONL training data files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("d4bl_training"),
        help="Root output directory for checkpoints, adapters, GGUFs",
    )
    parser.add_argument(
        "--phases",
        type=str,
        default="all",
        help="Comma-separated phases: domain,parser,explainer,evaluator,export (or 'all')",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="unsloth/Qwen3.5-4B",
        help="Base model name (HuggingFace or local path)",
    )
    parser.add_argument(
        "--quantize",
        type=str,
        default="q4_k_m",
        help="GGUF quantization method",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Retrain all phases, ignoring existing checkpoints",
    )
    args = parser.parse_args(argv)

    # Parse phases
    if args.phases == "all":
        args.phases = list(ALL_PHASES)
    else:
        args.phases = [p.strip() for p in args.phases.split(",")]
        invalid = set(args.phases) - set(ALL_PHASES)
        if invalid:
            parser.error(f"Unknown phases: {invalid}. Valid: {ALL_PHASES}")

    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    pipeline_start = time.monotonic()
    telemetry = {
        "config": {
            "model": args.model,
            "data_dir": str(args.data_dir),
            "output_dir": str(args.output_dir),
            "phases": args.phases,
            "quantize": args.quantize,
            "force": args.force,
        },
        "phases": {},
        "exports": {},
    }

    # Setup
    if not torch.cuda.is_available():
        print("\nERROR: CUDA is not available. This script requires a GPU.")
        print("Run on a machine with a CUDA-capable GPU (e.g., Colab with T4/A100).")
        sys.exit(1)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    use_bf16 = torch.cuda.is_bf16_supported()
    device_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
    precision = "bf16" if use_bf16 else "fp16"

    telemetry["config"]["device"] = device_name
    telemetry["config"]["precision"] = precision

    print_banner(args, device_name, precision)

    # Authenticate with HuggingFace
    hf_token = _get_hf_token()
    if hf_token:
        login(token=hf_token)

    # Validate data directory
    validate_data_dir(args.data_dir, args.phases)

    phase_num = 0
    total_phases = len(args.phases)

    # Phase 1: Domain adaptation
    if "domain" in args.phases:
        phase_num += 1
        domain_dir = args.output_dir / "domain_merged"
        if not args.force and check_phase_complete(domain_dir, "domain"):
            print(f"\n[{phase_num}/{total_phases}] Phase 1: Domain Adaptation")
            print(f"      \u2713 {domain_dir} exists \u2014 skipping")
        else:
            corpus = load_dataset_from_jsonl(
                args.data_dir / "corpus_pretrain.jsonl", require_text=True
            )
            print(f"      Loaded {len(corpus)} passages")
            stats = train_domain_adapter(
                model_name=args.model,
                corpus_dataset=corpus,
                output_dir=args.output_dir,
                use_bf16=use_bf16,
            )
            del corpus
            telemetry["phases"]["domain"] = stats
            checks = run_health_checks("domain", stats)
            print_health_checks(phase_num, total_phases, "Domain Adaptation", checks)
            telemetry["phases"]["domain"]["health_checks"] = checks

    # Phase 2: Task-specific adapters
    phase2_adapters = [a for a in ["parser", "explainer", "evaluator"] if a in args.phases]
    if phase2_adapters:
        domain_merged_path = args.output_dir / "domain_merged"
        if not check_phase_complete(domain_merged_path, "domain"):
            print(f"\n  ERROR: {domain_merged_path} not found.")
            print("  Phase 2 adapters require a completed Phase 1 (domain adaptation).")
            print("  Run with --phases domain first, or include 'domain' in --phases.")
            sys.exit(1)

    for adapter_name in phase2_adapters:
        phase_num += 1
        cfg = ADAPTER_CONFIGS[adapter_name]
        adapter_dir = args.output_dir / cfg["output_subdir"]
        label = ADAPTER_LABELS[adapter_name]

        if not args.force and check_phase_complete(adapter_dir, "adapter"):
            print(f"\n[{phase_num}/{total_phases}] Phase {label} Adapter")
            print(f"      \u2713 {adapter_dir} exists \u2014 skipping")
        else:
            train_ds = load_dataset_from_jsonl(args.data_dir / cfg["train_file"])
            val_ds = load_dataset_from_jsonl(args.data_dir / cfg["val_file"])
            domain_merged = str(args.output_dir / "domain_merged")
            stats = train_task_adapter(
                adapter_name=adapter_name,
                base_model_dir=domain_merged,
                train_dataset=train_ds,
                val_dataset=val_ds,
                output_dir=args.output_dir,
                cfg=cfg,
                use_bf16=use_bf16,
                phase_num=phase_num,
                total_phases=total_phases,
            )
            del train_ds, val_ds
            telemetry["phases"][adapter_name] = stats
            checks = run_health_checks(adapter_name, stats)
            print_health_checks(phase_num, total_phases, f"{label} Adapter", checks)
            telemetry["phases"][adapter_name]["health_checks"] = checks

    # Phase 3: GGUF export
    if "export" in args.phases:
        phase_num += 1
        print(f"\n[{phase_num}/{total_phases}] Phase 3: GGUF Export")
        for adapter_name, cfg in ADAPTER_CONFIGS.items():
            adapter_path = args.output_dir / cfg["output_subdir"]
            if not check_phase_complete(adapter_path, "adapter"):
                print(f"      \u2014 {cfg['gguf_name']}: adapter not found at {adapter_path}, skipping")
                continue
            gguf_subdir = args.output_dir / "gguf" / f"{cfg['gguf_name']}-{args.quantize}"
            if not args.force and check_phase_complete(gguf_subdir, "gguf"):
                print(f"      \u2713 {cfg['gguf_name']} already exported \u2014 skipping")
            else:
                export_info = export_gguf(
                    adapter_dir=adapter_path,
                    output_dir=args.output_dir,
                    gguf_name=cfg["gguf_name"],
                    quantize=args.quantize,
                    max_seq_length=cfg["max_seq_length"],
                )
                telemetry["exports"][adapter_name] = export_info

    # Report
    total_time = time.monotonic() - pipeline_start
    telemetry["total_duration_seconds"] = round(total_time, 1)
    generate_report(args.output_dir, telemetry)
    print_completion_banner(args.output_dir, total_time)


if __name__ == "__main__":
    main()