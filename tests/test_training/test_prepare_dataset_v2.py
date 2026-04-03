"""Tests for v2 prepare_dataset additions — glob merge and swap augmentation."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.training.prepare_dataset import (
    apply_swap_augmentation,
    load_and_merge_pairs,
)


def _make_pair(user: str, assistant: str, system: str = "sys") -> dict:
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }


class TestLoadAndMergePairs:
    def test_merges_two_files(self, tmp_path: Path):
        f1 = tmp_path / "evaluator.jsonl"
        f2 = tmp_path / "evaluator_v2.jsonl"
        f1.write_text(json.dumps(_make_pair("q1", '{"a":1}')) + "\n")
        f2.write_text(json.dumps(_make_pair("q2", '{"b":2}')) + "\n")
        result = load_and_merge_pairs(tmp_path, "evaluator")
        assert len(result) == 2
        user_contents = [r["messages"][1]["content"] for r in result]
        assert "q1" in user_contents
        assert "q2" in user_contents

    def test_single_file_still_works(self, tmp_path: Path):
        f1 = tmp_path / "evaluator.jsonl"
        f1.write_text(json.dumps(_make_pair("q1", '{"a":1}')) + "\n")
        result = load_and_merge_pairs(tmp_path, "evaluator")
        assert len(result) == 1
        assert result[0]["messages"][1]["content"] == "q1"

    def test_no_files_returns_empty(self, tmp_path: Path):
        result = load_and_merge_pairs(tmp_path, "evaluator")
        assert result == []

    def test_ignores_unrelated_files(self, tmp_path: Path):
        f1 = tmp_path / "evaluator.jsonl"
        f2 = tmp_path / "explainer.jsonl"
        f1.write_text(json.dumps(_make_pair("q1", '{"a":1}')) + "\n")
        f2.write_text(json.dumps(_make_pair("q2", '{"b":2}')) + "\n")
        result = load_and_merge_pairs(tmp_path, "evaluator")
        assert len(result) == 1
        assert result[0]["messages"][1]["content"] == "q1"


class TestApplySwapAugmentation:
    def test_doubles_pair_count(self):
        pairs = [_make_pair("Context:\ndata\n\nModel output:\nresponse", '{"score":3}')]
        result = apply_swap_augmentation(pairs)
        assert len(result) == 2

    def test_original_pair_preserved(self):
        original = _make_pair("Context:\ndata\n\nModel output:\nresponse", '{"score":3}')
        snapshot = copy.deepcopy(original)
        result = apply_swap_augmentation([original])
        assert original == snapshot
        assert result[0] == snapshot

    def test_swapped_pair_has_reversed_sections(self):
        pairs = [
            _make_pair(
                "Context:\nthe context data\n\nModel output:\nthe model response",
                '{"score": 4}',
            )
        ]
        result = apply_swap_augmentation(pairs)
        swapped_user = result[1]["messages"][1]["content"]
        assert swapped_user.index("Model output:") < swapped_user.index("Context:")

    def test_empty_input_returns_empty(self):
        assert apply_swap_augmentation([]) == []

    def test_pairs_without_separator_unchanged(self):
        pairs = [_make_pair("just a question", '{"score":3}')]
        snapshot = copy.deepcopy(pairs)
        result = apply_swap_augmentation(pairs)
        assert len(result) == 1
        assert result[0] == snapshot[0]