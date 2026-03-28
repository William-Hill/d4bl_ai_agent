"""Dataset preparation pipeline: filter, deduplicate, and split training pairs.

Loads raw JSONL files produced by generate_training_pairs.py, applies quality
filtering, removes near-duplicate prompts using Jaccard similarity, and writes
deterministic 80/10/10 train/val/test splits to FINAL_DIR.

Usage:
    python -m scripts.training.prepare_dataset --task query_parser
    python -m scripts.training.prepare_dataset --task explainer
    python -m scripts.training.prepare_dataset --task evaluator
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from scripts.training.config import (
    FINAL_DIR,
    JACCARD_THRESHOLD,
    PAIRS_DIR,
    TRAIN_RATIO,
    VAL_RATIO,
    write_jsonl,
)

# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------


def jaccard_similarity(a: str, b: str) -> float:
    """Compute word-level Jaccard similarity between two strings.

    Returns 0.0 if either string is empty.
    """
    words_a = set(a.split())
    words_b = set(b.split())
    return _jaccard_sets(words_a, words_b)


def _jaccard_sets(a: set, b: set) -> float:
    """Compute Jaccard similarity from pre-tokenized word sets.

    Returns 0.0 if either set is empty.
    """
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def filter_invalid_json(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only pairs whose assistant message contains JSON-parseable content.

    Removes pairs that:
    - Are missing the ``messages`` key
    - Have a ``messages`` value that is not a list
    - Have an empty ``messages`` list
    - Contain any message that is not a dict
    - Have no user-role message with non-empty content
    - Have no assistant-role message
    - Have an assistant content value that is not a string
    - Have an empty assistant content string
    - Have assistant content that is not valid JSON
    """
    valid = []
    for pair in pairs:
        messages = pair.get("messages")
        if not isinstance(messages, list) or not messages:
            continue
        # All messages must be dicts
        if any(not isinstance(msg, dict) for msg in messages):
            continue
        # Require at least one non-empty user message
        has_user = any(
            msg.get("role") == "user" and msg.get("content")
            for msg in messages
        )
        if not has_user:
            continue
        assistant_content = None
        for msg in messages:
            if msg.get("role") == "assistant":
                assistant_content = msg.get("content")
                break
        if not isinstance(assistant_content, str) or not assistant_content:
            continue
        try:
            json.loads(assistant_content)
        except (json.JSONDecodeError, ValueError):
            continue
        valid.append(pair)
    return valid


def _get_user_text(pair: dict[str, Any]) -> str:
    """Extract the user message content from a ChatML pair."""
    for msg in pair.get("messages", []):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""


def deduplicate_by_jaccard(
    pairs: list[dict[str, Any]],
    threshold: float = JACCARD_THRESHOLD,
) -> list[dict[str, Any]]:
    """Remove near-duplicate pairs based on user-message Jaccard similarity.

    Iterates in order; the first occurrence of each unique (by threshold) user
    message is kept and all subsequent near-duplicates are discarded.  Each
    candidate is tokenized once and compared against pre-tokenized kept sets.

    Args:
        pairs: List of ChatML-formatted message dicts.
        threshold: Jaccard score at or above which two messages are considered
            near-duplicates.  Defaults to ``JACCARD_THRESHOLD`` from config.

    Returns:
        Deduplicated list preserving original order of first occurrences.
    """
    if not pairs:
        return pairs

    kept: list[dict[str, Any]] = [pairs[0]]
    kept_word_sets: list[set] = [set(_get_user_text(pairs[0]).lower().split())]

    for pair in pairs[1:]:
        candidate_words = set(_get_user_text(pair).lower().split())
        is_duplicate = any(
            _jaccard_sets(candidate_words, kw) >= threshold
            for kw in kept_word_sets
        )
        if not is_duplicate:
            kept.append(pair)
            kept_word_sets.append(candidate_words)

    return kept


def split_dataset(
    pairs: list[dict[str, Any]],
    train_ratio: float = TRAIN_RATIO,
    val_ratio: float = VAL_RATIO,
    seed: int = 42,
) -> dict[str, list[dict[str, Any]]]:
    """Shuffle and split pairs into train/val/test using a deterministic seed.

    The test split receives whatever remains after train and val are allocated,
    so the three splits always sum to ``len(pairs)``.

    Args:
        pairs: Full list of training examples.
        train_ratio: Fraction allocated to the training split (default 0.80).
        val_ratio: Fraction allocated to the validation split (default 0.10).
        seed: Random seed for reproducibility (default 42).

    Returns:
        Dict with keys ``"train"``, ``"val"``, ``"test"``.
    """
    if not pairs:
        return {"train": [], "val": [], "test": []}

    shuffled = list(pairs)
    rng = random.Random(seed)
    rng.shuffle(shuffled)

    n = len(shuffled)
    train_end = round(n * train_ratio)
    val_end = train_end + round(n * val_ratio)

    return {
        "train": shuffled[:train_end],
        "val": shuffled[train_end:val_end],
        "test": shuffled[val_end:],
    }


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def _load_pairs(path: Path) -> list[dict[str, Any]]:
    """Load newline-delimited JSON from *path*."""
    pairs = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    return pairs


def _write_split(pairs: list[dict[str, Any]], path: Path) -> int:
    """Write *pairs* as newline-delimited JSON to *path*.  Returns count."""
    return write_jsonl(pairs, path)


def load_and_merge_pairs(pairs_dir: Path, task_prefix: str) -> list[dict[str, Any]]:
    """Load and merge all JSONL files matching ``{task_prefix}*.jsonl`` in *pairs_dir*.

    This enables v1 + v2 data to be combined before dedup and splitting.

    Args:
        pairs_dir: Directory containing JSONL pair files.
        task_prefix: Prefix to match (e.g., "evaluator" matches "evaluator.jsonl"
            and "evaluator_v2.jsonl").

    Returns:
        Combined list of pairs from all matching files.
    """
    all_pairs: list[dict[str, Any]] = []
    pattern = f"{task_prefix}*.jsonl"
    matched_files = sorted(pairs_dir.glob(pattern))
    for path in matched_files:
        pairs = _load_pairs(path)
        print(f"[merge] Loaded {len(pairs)} pairs from {path.name}")
        all_pairs.extend(pairs)
    return all_pairs


def apply_swap_augmentation(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Duplicate evaluator pairs with swapped Context/Model output order.

    For each pair whose user message contains both "Context:" and "Model output:"
    sections, creates a copy with those sections swapped. This prevents position
    bias per JudgeLM (ICLR 2025).

    Args:
        pairs: List of ChatML-formatted evaluator pairs.

    Returns:
        Original pairs plus swapped copies (up to 2x input size).
    """
    if not pairs:
        return []

    result = list(pairs)
    separator = "\n\nModel output:\n"

    for pair in pairs:
        user_content = _get_user_text(pair)

        if "Context:\n" not in user_content or separator not in user_content:
            continue

        parts = user_content.split(separator, 1)
        if len(parts) != 2:
            continue

        context_section = parts[0]
        model_output_text = parts[1]
        context_text = context_section.replace("Context:\n", "", 1)

        swapped_user = f"Model output:\n{model_output_text}\n\nContext:\n{context_text}"

        swapped_pair = {
            "messages": [
                pair["messages"][0],
                {"role": "user", "content": swapped_user},
                pair["messages"][2],
            ]
        }
        result.append(swapped_pair)

    return result


# ---------------------------------------------------------------------------
# Task orchestrator
# ---------------------------------------------------------------------------


def process_task(task: str) -> dict[str, int]:
    """Load, filter, deduplicate, and split training data for *task*.

    Uses glob-based merging to combine v1 + v2 pair files when both exist.
    Applies swap augmentation for evaluator relevance and bias subtasks.

    Args:
        task: Task name (e.g. ``"query_parser"``, ``"explainer"``).

    Returns:
        Dict mapping split name to number of examples written.
    """
    pairs = load_and_merge_pairs(PAIRS_DIR, task)

    if not pairs:
        input_path = PAIRS_DIR / f"{task}.jsonl"
        if not input_path.exists():
            raise FileNotFoundError(f"No pairs files found for task: {task}")
        pairs = _load_pairs(input_path)
        print(f"[{task}] Loaded {len(pairs)} pairs from {input_path}")
    else:
        print(f"[{task}] Merged {len(pairs)} total pairs")

    pairs = filter_invalid_json(pairs)
    print(f"[{task}] After JSON filter: {len(pairs)} pairs")

    if task == "evaluator":
        pre_swap = len(pairs)
        pairs = apply_swap_augmentation(pairs)
        print(f"[{task}] After swap augmentation: {len(pairs)} pairs (+{len(pairs) - pre_swap})")

    pairs = deduplicate_by_jaccard(pairs, threshold=JACCARD_THRESHOLD)
    print(f"[{task}] After deduplication: {len(pairs)} pairs")

    splits = split_dataset(pairs)

    counts: dict[str, int] = {}
    for split_name, split_pairs in splits.items():
        out_path = FINAL_DIR / task / f"{split_name}.jsonl"
        n = _write_split(split_pairs, out_path)
        counts[split_name] = n
        print(f"[{task}] Wrote {n} examples to {out_path}")

    return counts


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


_ALL_TASKS = ["query_parser", "explainer", "evaluator"]


def main(task: str) -> None:
    """Run the preparation pipeline for *task*.

    Pass ``"all"`` to process all three tasks in sequence.
    """
    if task == "all":
        for t in _ALL_TASKS:
            process_task(t)
    else:
        process_task(task)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Filter, deduplicate, and split training pairs."
    )
    parser.add_argument(
        "--task",
        required=True,
        help=(
            "Task name matching a file in PAIRS_DIR (e.g. query_parser), "
            "or 'all' to process all tasks."
        ),
    )
    args = parser.parse_args()
    main(args.task)
