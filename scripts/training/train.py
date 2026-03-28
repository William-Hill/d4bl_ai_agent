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
from unsloth import FastLanguageModel

# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

ALL_PHASES = ["domain", "parser", "explainer", "evaluator", "export"]

REQUIRED_DATA_FILES = [
    "corpus_pretrain.jsonl",
    "query_parser_train.jsonl",
    "query_parser_val.jsonl",
    "explainer_train.jsonl",
    "explainer_val.jsonl",
    "evaluator_train.jsonl",
    "evaluator_val.jsonl",
]

ADAPTER_CONFIGS = {
    "parser": {
        "r": 8,
        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
        "lora_alpha": 16,
        "max_seq_length": 2048,
        "epochs": 7,
        "batch_size": 4,
        "grad_accum": 2,
        "warmup_steps": 20,
        "lr": 1e-4,
        "eval_steps": 25,
        "save_steps": 25,
        "train_file": "query_parser_train.jsonl",
        "val_file": "query_parser_val.jsonl",
        "output_subdir": "adapter_parser",
        "checkpoint_subdir": "parser_checkpoints",
        "gguf_name": "d4bl-query-parser",
    },
    "explainer": {
        "r": 32,
        "target_modules": [
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        "lora_alpha": 64,
        "max_seq_length": 4096,
        "epochs": 7,
        "batch_size": 2,
        "grad_accum": 4,
        "warmup_steps": 30,
        "lr": 1e-4,
        "eval_steps": 20,
        "save_steps": 20,
        "train_file": "explainer_train.jsonl",
        "val_file": "explainer_val.jsonl",
        "output_subdir": "adapter_explainer",
        "checkpoint_subdir": "explainer_checkpoints",
        "gguf_name": "d4bl-explainer",
    },
    "evaluator": {
        "r": 16,
        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
        "lora_alpha": 32,
        "max_seq_length": 2048,
        "epochs": 7,
        "batch_size": 4,
        "grad_accum": 2,
        "warmup_steps": 20,
        "lr": 1e-4,
        "eval_steps": 25,
        "save_steps": 25,
        "train_file": "evaluator_train.jsonl",
        "val_file": "evaluator_val.jsonl",
        "output_subdir": "adapter_evaluator",
        "checkpoint_subdir": "evaluator_checkpoints",
        "gguf_name": "d4bl-evaluator",
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


def format_and_tokenize(dataset: Dataset, tokenizer) -> Dataset:
    """Convert messages-format dataset to plain text using the model's chat template.

    Falls back to manual ChatML if the tokenizer lacks a chat template.
    """
    formatted = []
    for record in dataset:
        msgs = record["messages"]
        try:
            text = tokenizer.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=False
            )
        except (AttributeError, TypeError, KeyError, ValueError):
            parts = []
            for msg in msgs:
                parts.append(f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>")
            text = "\n".join(parts) + "\n"
        formatted.append({"text": text})
    return Dataset.from_list(formatted)


def load_training_data(data_dir: Path, phases: list[str]) -> dict[str, Dataset]:
    """Load all training datasets needed by the requested phases."""
    datasets: dict[str, Dataset] = {}

    if "domain" in phases:
        datasets["corpus"] = load_dataset_from_jsonl(
            data_dir / "corpus_pretrain.jsonl", require_text=True
        )
        print(f"  corpus_pretrain       : {len(datasets['corpus']):>5} passages")

    for adapter_name in ["parser", "explainer", "evaluator"]:
        if adapter_name not in phases:
            continue
        cfg = ADAPTER_CONFIGS[adapter_name]
        train_ds = load_dataset_from_jsonl(data_dir / cfg["train_file"])
        val_ds = load_dataset_from_jsonl(data_dir / cfg["val_file"])
        datasets[f"{adapter_name}_train"] = train_ds
        datasets[f"{adapter_name}_val"] = val_ds
        print(f"  {adapter_name:<22}: {len(train_ds):>5} train / {len(val_ds):>5} val")

    return datasets


def free_vram(*objects) -> None:
    """Delete objects and free CUDA memory."""
    for obj in objects:
        del obj
    gc.collect()
    torch.cuda.empty_cache()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="D4BL Training Pipeline — headless LoRA fine-tuning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("scripts/training_data/final"),
        help="Directory containing the 7 JSONL training data files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/content/d4bl_training"),
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
        default="unsloth/Qwen2.5-3B-Instruct",
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

    # Load training data
    datasets = load_training_data(args.data_dir, args.phases)

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
            stats = train_domain_adapter(
                model_name=args.model,
                corpus_dataset=datasets["corpus"],
                output_dir=args.output_dir,
                use_bf16=use_bf16,
            )
            telemetry["phases"]["domain"] = stats
            checks = run_health_checks("domain", stats)
            print_health_checks(phase_num, total_phases, "Domain Adaptation", checks)
            telemetry["phases"]["domain"]["health_checks"] = checks

    # Phase 2: Task-specific adapters
    for adapter_name in ["parser", "explainer", "evaluator"]:
        if adapter_name not in args.phases:
            continue
        phase_num += 1
        cfg = ADAPTER_CONFIGS[adapter_name]
        adapter_dir = args.output_dir / cfg["output_subdir"]
        label = {"parser": "2a: Query Parser", "explainer": "2b: Data Explainer", "evaluator": "2c: Evaluator"}[adapter_name]

        if not args.force and check_phase_complete(adapter_dir, "adapter"):
            print(f"\n[{phase_num}/{total_phases}] Phase {label} Adapter")
            print(f"      \u2713 {adapter_dir} exists \u2014 skipping")
        else:
            domain_merged = str(args.output_dir / "domain_merged")
            stats = train_task_adapter(
                adapter_name=adapter_name,
                base_model_dir=domain_merged,
                train_dataset=datasets[f"{adapter_name}_train"],
                val_dataset=datasets[f"{adapter_name}_val"],
                output_dir=args.output_dir,
                cfg=cfg,
                use_bf16=use_bf16,
                phase_num=phase_num,
                total_phases=total_phases,
            )
            telemetry["phases"][adapter_name] = stats
            checks = run_health_checks(adapter_name, stats)
            print_health_checks(phase_num, total_phases, f"{label} Adapter", checks)
            telemetry["phases"][adapter_name]["health_checks"] = checks

    # Phase 3: GGUF export
    if "export" in args.phases:
        phase_num += 1
        print(f"\n[{phase_num}/{total_phases}] Phase 3: GGUF Export")
        for adapter_name, cfg in ADAPTER_CONFIGS.items():
            gguf_subdir = args.output_dir / "gguf" / f"{cfg['gguf_name']}-{args.quantize}"
            if not args.force and check_phase_complete(gguf_subdir, "gguf"):
                print(f"      \u2713 {cfg['gguf_name']} already exported \u2014 skipping")
            else:
                export_info = export_gguf(
                    adapter_dir=args.output_dir / cfg["output_subdir"],
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
