"""Register D4BL fine-tuned models with Ollama.

Usage:
    python scripts/training/register_models.py [--models-dir ./models] [--dry-run]

Expects GGUF files in the models/ directory and Modelfiles alongside them.
Creates Ollama models: d4bl-query-parser, d4bl-explainer, d4bl-evaluator.
Runs a quick smoke test on each after registration.
"""

from __future__ import annotations

import argparse
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
