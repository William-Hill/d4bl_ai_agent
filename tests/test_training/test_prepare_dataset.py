"""Tests for scripts/training/prepare_dataset.py — pure functions only.

No file I/O or external dependencies are exercised in these tests.
"""

from __future__ import annotations

import json

import pytest

from scripts.training.prepare_dataset import (
    deduplicate_by_jaccard,
    filter_invalid_json,
    jaccard_similarity,
    split_dataset,
)


# ---------------------------------------------------------------------------
# jaccard_similarity
# ---------------------------------------------------------------------------


class TestJaccardSimilarity:
    def test_identical_strings_return_one(self):
        assert jaccard_similarity("hello world", "hello world") == 1.0

    def test_completely_different_strings_return_zero(self):
        assert jaccard_similarity("apple banana", "cat dog") == 0.0

    def test_partial_overlap_between_zero_and_one(self):
        score = jaccard_similarity("hello world foo", "hello world bar")
        assert 0.0 < score < 1.0

    def test_empty_strings_return_zero(self):
        assert jaccard_similarity("", "") == 0.0

    def test_one_empty_string_returns_zero(self):
        assert jaccard_similarity("hello", "") == 0.0
        assert jaccard_similarity("", "world") == 0.0

    def test_single_word_identical(self):
        assert jaccard_similarity("hello", "hello") == 1.0

    def test_single_word_different(self):
        assert jaccard_similarity("hello", "world") == 0.0

    def test_symmetric(self):
        a = "the quick brown fox"
        b = "the lazy brown dog"
        assert jaccard_similarity(a, b) == jaccard_similarity(b, a)

    def test_known_value(self):
        # {"a", "b"} ∩ {"b", "c"} = {"b"}  union = {"a","b","c"}  → 1/3
        score = jaccard_similarity("a b", "b c")
        assert abs(score - 1 / 3) < 1e-9

    def test_superset(self):
        # "a b c" vs "a b" → intersection {"a","b"} union {"a","b","c"} → 2/3
        score = jaccard_similarity("a b c", "a b")
        assert abs(score - 2 / 3) < 1e-9


# ---------------------------------------------------------------------------
# filter_invalid_json
# ---------------------------------------------------------------------------


def _make_pair(user_content: str, assistant_content: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ]
    }


class TestFilterInvalidJson:
    def test_keeps_pair_with_valid_json_assistant(self):
        pairs = [_make_pair("question", '{"key": "value"}')]
        result = filter_invalid_json(pairs)
        assert len(result) == 1

    def test_removes_pair_with_invalid_json_assistant(self):
        pairs = [_make_pair("question", "not valid json")]
        result = filter_invalid_json(pairs)
        assert len(result) == 0

    def test_empty_input_returns_empty(self):
        result = filter_invalid_json([])
        assert result == []

    def test_mixed_keeps_only_valid(self):
        pairs = [
            _make_pair("q1", '{"a": 1}'),
            _make_pair("q2", "bad json"),
            _make_pair("q3", '{"b": 2}'),
        ]
        result = filter_invalid_json(pairs)
        assert len(result) == 2

    def test_missing_messages_key_removed(self):
        pairs = [{"no_messages": True}]
        result = filter_invalid_json(pairs)
        assert len(result) == 0

    def test_empty_messages_list_removed(self):
        pairs = [{"messages": []}]
        result = filter_invalid_json(pairs)
        assert len(result) == 0

    def test_no_assistant_message_removed(self):
        pairs = [
            {
                "messages": [
                    {"role": "user", "content": "hi"},
                ]
            }
        ]
        result = filter_invalid_json(pairs)
        assert len(result) == 0

    def test_empty_assistant_content_removed(self):
        pairs = [_make_pair("q", "")]
        result = filter_invalid_json(pairs)
        assert len(result) == 0

    def test_nested_json_kept(self):
        pairs = [_make_pair("q", '{"intent": "lookup", "filters": {"state": "AL"}}')]
        result = filter_invalid_json(pairs)
        assert len(result) == 1

    def test_json_array_in_assistant_kept(self):
        pairs = [_make_pair("q", '[{"a": 1}]')]
        result = filter_invalid_json(pairs)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# deduplicate_by_jaccard
# ---------------------------------------------------------------------------


def _make_user_pair(user_text: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": '{"ok": true}'},
        ]
    }


class TestDeduplicateByJaccard:
    def test_empty_input_returns_empty(self):
        assert deduplicate_by_jaccard([], threshold=0.8) == []

    def test_single_pair_returned_unchanged(self):
        pairs = [_make_user_pair("what is the poverty rate in Alabama")]
        result = deduplicate_by_jaccard(pairs, threshold=0.8)
        assert len(result) == 1

    def test_identical_pairs_deduplicated_to_one(self):
        pairs = [
            _make_user_pair("what is the poverty rate in Alabama"),
            _make_user_pair("what is the poverty rate in Alabama"),
        ]
        result = deduplicate_by_jaccard(pairs, threshold=0.8)
        assert len(result) == 1

    def test_different_pairs_both_kept(self):
        pairs = [
            _make_user_pair("infant mortality rate in Mississippi"),
            _make_user_pair("median household income in California"),
        ]
        result = deduplicate_by_jaccard(pairs, threshold=0.8)
        assert len(result) == 2

    def test_near_duplicate_above_threshold_removed(self):
        # Very similar — only one word differs out of many shared words
        base = "what is the poverty rate in the state of Alabama for Black residents"
        near = "what is the poverty rate in the state of Alabama for Black community"
        pairs = [_make_user_pair(base), _make_user_pair(near)]
        result = deduplicate_by_jaccard(pairs, threshold=0.8)
        assert len(result) == 1

    def test_threshold_zero_keeps_only_first(self):
        # At threshold=0.0 any non-empty overlap deduplicates; fully different pairs survive
        pairs = [
            _make_user_pair("alpha beta gamma"),
            _make_user_pair("alpha beta delta"),
        ]
        result = deduplicate_by_jaccard(pairs, threshold=0.0)
        # These share 2 out of 4 words → Jaccard 0.5 > 0.0, so second is removed
        assert len(result) == 1

    def test_threshold_one_keeps_all_non_identical(self):
        # Only exact duplicates removed
        pairs = [
            _make_user_pair("apple orange"),
            _make_user_pair("apple banana"),
        ]
        result = deduplicate_by_jaccard(pairs, threshold=1.0)
        assert len(result) == 2

    def test_first_occurrence_kept(self):
        pairs = [
            _make_user_pair("what is the poverty rate in Alabama"),
            _make_user_pair("what is the poverty rate in Alabama"),
        ]
        result = deduplicate_by_jaccard(pairs, threshold=0.8)
        assert result[0] is pairs[0]

    def test_default_threshold_works(self):
        """Calling without threshold uses default (0.8)."""
        pairs = [_make_user_pair("foo bar baz")]
        result = deduplicate_by_jaccard(pairs)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# split_dataset
# ---------------------------------------------------------------------------


def _make_pairs(n: int) -> list[dict]:
    return [_make_user_pair(f"question number {i} about data") for i in range(n)]


class TestSplitDataset:
    def test_returns_three_splits(self):
        pairs = _make_pairs(100)
        result = split_dataset(pairs)
        assert set(result.keys()) == {"train", "val", "test"}

    def test_no_overlap_between_splits(self):
        pairs = _make_pairs(100)
        result = split_dataset(pairs, seed=0)
        train_set = {id(p) for p in result["train"]}
        val_set = {id(p) for p in result["val"]}
        test_set = {id(p) for p in result["test"]}
        assert train_set.isdisjoint(val_set)
        assert train_set.isdisjoint(test_set)
        assert val_set.isdisjoint(test_set)

    def test_all_pairs_covered(self):
        pairs = _make_pairs(100)
        result = split_dataset(pairs, seed=0)
        total = len(result["train"]) + len(result["val"]) + len(result["test"])
        assert total == 100

    def test_80_10_10_approximate_split(self):
        pairs = _make_pairs(100)
        result = split_dataset(pairs, seed=42)
        assert len(result["train"]) == 80
        assert len(result["val"]) == 10
        assert len(result["test"]) == 10

    def test_deterministic_with_same_seed(self):
        pairs = _make_pairs(50)
        r1 = split_dataset(pairs, seed=99)
        r2 = split_dataset(pairs, seed=99)
        assert [p["messages"][1]["content"] for p in r1["train"]] == [
            p["messages"][1]["content"] for p in r2["train"]
        ]

    def test_different_seeds_produce_different_train_sets(self):
        pairs = _make_pairs(100)
        r1 = split_dataset(pairs, seed=1)
        r2 = split_dataset(pairs, seed=2)
        # With 100 items it's astronomically unlikely they're the same order
        assert r1["train"] != r2["train"]

    def test_small_dataset_still_splits(self):
        pairs = _make_pairs(10)
        result = split_dataset(pairs, seed=0)
        total = len(result["train"]) + len(result["val"]) + len(result["test"])
        assert total == 10

    def test_empty_dataset_returns_empty_splits(self):
        result = split_dataset([], seed=0)
        assert result["train"] == []
        assert result["val"] == []
        assert result["test"] == []

    def test_train_larger_than_val_and_test(self):
        pairs = _make_pairs(100)
        result = split_dataset(pairs, seed=7)
        assert len(result["train"]) > len(result["val"])
        assert len(result["train"]) > len(result["test"])
