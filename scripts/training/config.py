"""Shared constants and utilities for the training data pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

# Output directories
BASE_DIR = Path(__file__).resolve().parent.parent / "training_data"
CORPUS_DIR = BASE_DIR / "corpus"
PAIRS_DIR = BASE_DIR / "pairs"
FINAL_DIR = BASE_DIR / "final"

# Corpus extraction
CORPUS_BATCH_SIZE = 500
MAX_PASSAGES_PER_TABLE = 10_000

# Distillation
DISTILLATION_MODEL = "claude-sonnet-4-20250514"
PAIRS_PER_TASK = 1000
EVALUATOR_PAIRS_PER_SUBTASK = 250

# Dataset split ratios
TRAIN_RATIO = 0.80
VAL_RATIO = 0.10
TEST_RATIO = 0.10

# Deduplication
JACCARD_THRESHOLD = 0.8


def write_jsonl(
    items: list,
    outfile: Path,
    transform: Optional[Callable] = None,
) -> int:
    """Write items to a JSONL file.

    An optional ``transform`` callable is applied to each item before writing.
    If ``transform`` returns ``None`` the item is skipped.  Creates parent
    directories as needed.

    Args:
        items: List of JSON-serialisable objects to write.
        outfile: Destination file path.
        transform: Optional per-item transformation; returning ``None`` skips the item.

    Returns:
        Number of lines written.
    """
    outfile = Path(outfile)
    outfile.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with outfile.open("w", encoding="utf-8") as fh:
        for item in items:
            if transform is not None:
                item = transform(item)
            if item is None:
                continue
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
            count += 1
    return count
