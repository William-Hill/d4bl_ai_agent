"""Tests for scripts/training/generate_training_pairs.py — pure functions only.

No Claude API calls or database connections are made in these tests.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys

from scripts.training.generate_training_pairs import (
    _validate_json,
    format_as_chatml,
    generate_query_parser_questions,
    write_pairs_jsonl,
)

# ---------------------------------------------------------------------------
# format_as_chatml
# ---------------------------------------------------------------------------


class TestFormatAsChatml:
    def test_returns_dict_with_messages_key(self):
        result = format_as_chatml("sys", "user msg", "assistant msg")
        assert isinstance(result, dict)
        assert "messages" in result

    def test_messages_has_three_items(self):
        result = format_as_chatml("sys", "user msg", "assistant msg")
        assert len(result["messages"]) == 3

    def test_system_role_and_content(self):
        result = format_as_chatml("my system prompt", "u", "a")
        system_msg = result["messages"][0]
        assert system_msg["role"] == "system"
        assert system_msg["content"] == "my system prompt"

    def test_user_role_and_content(self):
        result = format_as_chatml("s", "hello user", "a")
        user_msg = result["messages"][1]
        assert user_msg["role"] == "user"
        assert user_msg["content"] == "hello user"

    def test_assistant_role_and_content(self):
        result = format_as_chatml("s", "u", "hello assistant")
        asst_msg = result["messages"][2]
        assert asst_msg["role"] == "assistant"
        assert asst_msg["content"] == "hello assistant"

    def test_messages_order(self):
        result = format_as_chatml("s", "u", "a")
        roles = [m["role"] for m in result["messages"]]
        assert roles == ["system", "user", "assistant"]

    def test_empty_strings_allowed(self):
        result = format_as_chatml("", "", "")
        assert len(result["messages"]) == 3

    def test_multiline_content_preserved(self):
        system = "line1\nline2"
        result = format_as_chatml(system, "u", "a")
        assert result["messages"][0]["content"] == system


# ---------------------------------------------------------------------------
# write_pairs_jsonl
# ---------------------------------------------------------------------------


class TestWritePairsJsonl:
    def test_returns_count_of_pairs(self):
        pairs = [{"messages": [{"role": "user", "content": "hi"}]}] * 5
        buf = io.StringIO()
        count = write_pairs_jsonl(pairs, buf)
        assert count == 5

    def test_returns_zero_for_empty_list(self):
        buf = io.StringIO()
        count = write_pairs_jsonl([], buf)
        assert count == 0

    def test_each_line_is_valid_json(self):
        pairs = [{"messages": [{"role": "user", "content": f"msg {i}"}]} for i in range(3)]
        buf = io.StringIO()
        write_pairs_jsonl(pairs, buf)
        buf.seek(0)
        lines = buf.read().strip().split("\n")
        assert len(lines) == 3
        for line in lines:
            obj = json.loads(line)
            assert "messages" in obj

    def test_one_json_object_per_line(self):
        pairs = [{"a": 1}, {"b": 2}]
        buf = io.StringIO()
        write_pairs_jsonl(pairs, buf)
        buf.seek(0)
        lines = [ln for ln in buf.read().splitlines() if ln.strip()]
        assert len(lines) == 2

    def test_writes_to_file_path(self, tmp_path):
        pairs = [{"messages": [{"role": "user", "content": "test"}]}]
        outfile = tmp_path / "out.jsonl"
        count = write_pairs_jsonl(pairs, outfile)
        assert count == 1
        lines = outfile.read_text().strip().splitlines()
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert obj["messages"][0]["content"] == "test"

    def test_preserves_pair_content(self):
        pairs = [{"messages": [{"role": "assistant", "content": "answer"}]}]
        buf = io.StringIO()
        write_pairs_jsonl(pairs, buf)
        buf.seek(0)
        obj = json.loads(buf.read().strip())
        assert obj["messages"][0]["role"] == "assistant"
        assert obj["messages"][0]["content"] == "answer"


# ---------------------------------------------------------------------------
# generate_query_parser_questions
# ---------------------------------------------------------------------------


class TestGenerateQueryParserQuestions:
    def _sample_seed_rows(self) -> list[dict]:
        return [
            {
                "state": "Mississippi",
                "metric_name": "infant_mortality_rate",
                "value": 8.9,
                "race": "Black",
                "year": 2021,
            },
            {
                "state": "Louisiana",
                "metric_name": "uninsured_rate",
                "value": 0.19,
                "race": "Hispanic",
                "year": 2022,
            },
            {
                "state": "Alabama",
                "metric_name": "poverty_rate",
                "value": 0.24,
                "race": "Black",
                "year": 2021,
            },
        ]

    def test_returns_list(self):
        rows = self._sample_seed_rows()
        result = generate_query_parser_questions(rows, count=3)
        assert isinstance(result, list)

    def test_returns_requested_count(self):
        rows = self._sample_seed_rows()
        result = generate_query_parser_questions(rows, count=6)
        assert len(result) == 6

    def test_each_item_has_question_key(self):
        rows = self._sample_seed_rows()
        result = generate_query_parser_questions(rows, count=3)
        for item in result:
            assert "question" in item

    def test_each_item_has_style_key(self):
        rows = self._sample_seed_rows()
        result = generate_query_parser_questions(rows, count=3)
        for item in result:
            assert "style" in item

    def test_each_item_has_seed_data_key(self):
        rows = self._sample_seed_rows()
        result = generate_query_parser_questions(rows, count=3)
        for item in result:
            assert "seed_data" in item

    def test_question_is_non_empty_string(self):
        rows = self._sample_seed_rows()
        result = generate_query_parser_questions(rows, count=3)
        for item in result:
            assert isinstance(item["question"], str)
            assert len(item["question"].strip()) > 0

    def test_style_is_valid(self):
        rows = self._sample_seed_rows()
        valid_styles = {"standard", "community", "adversarial"}
        result = generate_query_parser_questions(rows, count=9)
        for item in result:
            assert item["style"] in valid_styles

    def test_seed_data_references_row(self):
        rows = self._sample_seed_rows()
        result = generate_query_parser_questions(rows, count=3)
        # seed_data should be one of the original rows
        for item in result:
            assert item["seed_data"] in rows

    def test_all_styles_represented_with_enough_count(self):
        rows = self._sample_seed_rows()
        result = generate_query_parser_questions(rows, count=9)
        styles = {item["style"] for item in result}
        assert "standard" in styles
        assert "community" in styles
        assert "adversarial" in styles

    def test_works_with_single_seed_row(self):
        rows = [self._sample_seed_rows()[0]]
        result = generate_query_parser_questions(rows, count=3)
        assert len(result) == 3

    def test_count_zero_returns_empty(self):
        rows = self._sample_seed_rows()
        result = generate_query_parser_questions(rows, count=0)
        assert result == []


# ---------------------------------------------------------------------------
# _validate_json
# ---------------------------------------------------------------------------


class TestValidateJson:
    def test_valid_json_object_returned_as_dict(self):
        result = _validate_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_valid_nested_json(self):
        text = '{"a": {"b": [1, 2, 3]}}'
        result = _validate_json(text)
        assert result == {"a": {"b": [1, 2, 3]}}

    def test_invalid_json_returns_none(self):
        result = _validate_json("not valid json")
        assert result is None

    def test_empty_string_returns_none(self):
        result = _validate_json("")
        assert result is None

    def test_strips_markdown_json_fence(self):
        text = '```json\n{"key": "value"}\n```'
        result = _validate_json(text)
        assert result == {"key": "value"}

    def test_strips_plain_code_fence(self):
        text = '```\n{"key": "value"}\n```'
        result = _validate_json(text)
        assert result == {"key": "value"}

    def test_strips_whitespace_around_json(self):
        text = '  \n  {"key": "value"}  \n  '
        result = _validate_json(text)
        assert result == {"key": "value"}

    def test_json_array_returns_none(self):
        # We only handle objects (dicts), not bare arrays
        result = _validate_json("[1, 2, 3]")
        assert result is None

    def test_json_with_numbers_and_booleans(self):
        text = '{"score": 4, "passed": true, "note": null}'
        result = _validate_json(text)
        assert result == {"score": 4, "passed": True, "note": None}

    def test_partial_fence_still_parsed(self):
        # Leading fence marker but no closing
        text = '```json\n{"key": "value"}'
        result = _validate_json(text)
        assert result == {"key": "value"}


# ---------------------------------------------------------------------------
# _load_checkpoint / _update_checkpoint / _clear_checkpoint
# ---------------------------------------------------------------------------


class TestCheckpointHelpers:
    """Tests for the checkpoint read/write/clear helpers."""

    def test_load_missing_file_returns_default(self, tmp_path):
        from scripts.training.generate_training_pairs import _load_checkpoint

        result = _load_checkpoint("query_parser", "standard", checkpoint_dir=tmp_path)
        assert result == {"last_attempted_idx": -1, "pairs_written": 0, "status": "pending"}

    def test_load_missing_task_returns_default(self, tmp_path):
        from scripts.training.generate_training_pairs import _load_checkpoint, _update_checkpoint

        _update_checkpoint("query_parser", "standard", last_attempted_idx=5, checkpoint_dir=tmp_path)
        result = _load_checkpoint("explainer", "standard", checkpoint_dir=tmp_path)
        assert result == {"last_attempted_idx": -1, "pairs_written": 0, "status": "pending"}

    def test_update_and_load_round_trip(self, tmp_path):
        from scripts.training.generate_training_pairs import _load_checkpoint, _update_checkpoint

        _update_checkpoint(
            "query_parser",
            "standard",
            last_attempted_idx=42,
            pairs_written=10,
            status="in_progress",
            checkpoint_dir=tmp_path,
        )
        result = _load_checkpoint("query_parser", "standard", checkpoint_dir=tmp_path)
        assert result["last_attempted_idx"] == 42
        assert result["pairs_written"] == 10
        assert result["status"] == "in_progress"

    def test_update_merges_partial_fields(self, tmp_path):
        from scripts.training.generate_training_pairs import _load_checkpoint, _update_checkpoint

        _update_checkpoint(
            "query_parser",
            "standard",
            last_attempted_idx=10,
            pairs_written=5,
            status="in_progress",
            checkpoint_dir=tmp_path,
        )
        # Only update pairs_written
        _update_checkpoint("query_parser", "standard", pairs_written=15, checkpoint_dir=tmp_path)
        result = _load_checkpoint("query_parser", "standard", checkpoint_dir=tmp_path)
        assert result["last_attempted_idx"] == 10  # preserved
        assert result["pairs_written"] == 15       # updated
        assert result["status"] == "in_progress"   # preserved

    def test_update_preserves_other_tasks(self, tmp_path):
        from scripts.training.generate_training_pairs import _load_checkpoint, _update_checkpoint

        _update_checkpoint("query_parser", "standard", last_attempted_idx=3, checkpoint_dir=tmp_path)
        _update_checkpoint("explainer", "default", last_attempted_idx=7, checkpoint_dir=tmp_path)
        result = _load_checkpoint("query_parser", "standard", checkpoint_dir=tmp_path)
        assert result["last_attempted_idx"] == 3

    def test_clear_removes_task_entry(self, tmp_path):
        from scripts.training.generate_training_pairs import (
            _clear_checkpoint,
            _load_checkpoint,
            _update_checkpoint,
        )

        _update_checkpoint("query_parser", "standard", last_attempted_idx=5, checkpoint_dir=tmp_path)
        _clear_checkpoint("query_parser", checkpoint_dir=tmp_path)
        result = _load_checkpoint("query_parser", "standard", checkpoint_dir=tmp_path)
        assert result == {"last_attempted_idx": -1, "pairs_written": 0, "status": "pending"}

    def test_clear_preserves_other_tasks(self, tmp_path):
        from scripts.training.generate_training_pairs import (
            _clear_checkpoint,
            _load_checkpoint,
            _update_checkpoint,
        )

        _update_checkpoint("query_parser", "standard", last_attempted_idx=5, checkpoint_dir=tmp_path)
        _update_checkpoint("explainer", "default", last_attempted_idx=9, checkpoint_dir=tmp_path)
        _clear_checkpoint("query_parser", checkpoint_dir=tmp_path)
        result = _load_checkpoint("explainer", "default", checkpoint_dir=tmp_path)
        assert result["last_attempted_idx"] == 9

    def test_atomic_write_produces_valid_json(self, tmp_path):
        from scripts.training.generate_training_pairs import _update_checkpoint

        _update_checkpoint(
            "query_parser",
            "standard",
            last_attempted_idx=1,
            pairs_written=1,
            status="done",
            checkpoint_dir=tmp_path,
        )
        cp_file = tmp_path / ".checkpoint.json"
        assert cp_file.exists()
        data = json.loads(cp_file.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert data["query_parser"]["standard"]["last_attempted_idx"] == 1

    def test_load_corrupted_file_returns_default(self, tmp_path):
        from scripts.training.generate_training_pairs import _load_checkpoint

        cp_file = tmp_path / ".checkpoint.json"
        cp_file.write_text("{not valid json!!!", encoding="utf-8")
        result = _load_checkpoint("any_task", "any_sub", checkpoint_dir=tmp_path)
        assert result == {"last_attempted_idx": -1, "pairs_written": 0, "status": "pending"}


# ---------------------------------------------------------------------------
# TestCLIFlags
# ---------------------------------------------------------------------------


class TestCLIFlags:
    def test_resume_flag_accepted(self):
        result = subprocess.run(
            [sys.executable, "-c",
             "from scripts.training.generate_training_pairs import _build_arg_parser; "
             "p = _build_arg_parser(); "
             "args = p.parse_args(['--task', 'evaluator_v2', '--resume']); "
             "assert args.resume is True"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr

    def test_no_resume_flag_defaults_false(self):
        result = subprocess.run(
            [sys.executable, "-c",
             "from scripts.training.generate_training_pairs import _build_arg_parser; "
             "p = _build_arg_parser(); "
             "args = p.parse_args(['--task', 'evaluator_v2']); "
             "assert args.resume is False"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr

    def test_new_v3_task_choices_accepted(self):
        for task in ["evaluator_v3", "query_parser_v3"]:
            result = subprocess.run(
                [sys.executable, "-c",
                 f"from scripts.training.generate_training_pairs import _build_arg_parser; "
                 f"p = _build_arg_parser(); "
                 f"args = p.parse_args(['--task', '{task}']); "
                 f"assert args.task == '{task}'"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"{task} rejected: {result.stderr}"


# ---------------------------------------------------------------------------
# TestResumeIntegration
# ---------------------------------------------------------------------------


class TestResumeIntegration:
    def test_community_framing_resume_skips_completed_seeds(self, tmp_path):
        from scripts.training.generate_training_pairs import (
            _load_checkpoint,
            _update_checkpoint,
            generate_community_framing_pairs,
        )

        outfile = tmp_path / "query_parser_v3.jsonl"

        # Generate 10 pairs from scratch
        pairs_first = generate_community_framing_pairs(
            conn=None, count=10, outfile=outfile, resume=False,
            checkpoint_dir=tmp_path,
        )
        assert len(pairs_first) == 10
        first_line_count = sum(1 for line in outfile.read_text().strip().split("\n") if line.strip())
        assert first_line_count == 10

        # Simulate crash at seed 5 by resetting checkpoint
        _update_checkpoint(
            "query_parser_v3", "_default",
            last_attempted_idx=4, pairs_written=5, status="in_progress",
            checkpoint_dir=tmp_path,
        )
        # Truncate output to 5 lines
        lines = outfile.read_text().strip().split("\n")
        outfile.write_text("\n".join(lines[:5]) + "\n")

        # Resume should generate seeds 5-9
        pairs_resumed = generate_community_framing_pairs(
            conn=None, count=10, outfile=outfile, resume=True,
            checkpoint_dir=tmp_path,
        )
        assert len(pairs_resumed) == 5  # only newly generated

        final_line_count = sum(1 for line in outfile.read_text().strip().split("\n") if line.strip())
        assert final_line_count == 10  # 5 existing + 5 new

        cp = _load_checkpoint("query_parser_v3", "_default", checkpoint_dir=tmp_path)
        assert cp["status"] == "completed"
        assert cp["last_attempted_idx"] == 9

    def test_overwrite_mode_ignores_checkpoint(self, tmp_path):
        from scripts.training.generate_training_pairs import (
            _update_checkpoint,
            generate_community_framing_pairs,
        )

        outfile = tmp_path / "query_parser_v3.jsonl"

        # Set up stale checkpoint
        _update_checkpoint(
            "query_parser_v3", "_default",
            last_attempted_idx=50, pairs_written=51, status="in_progress",
            checkpoint_dir=tmp_path,
        )

        # Overwrite mode ignores checkpoint
        pairs = generate_community_framing_pairs(
            conn=None, count=5, outfile=outfile, resume=False,
            checkpoint_dir=tmp_path,
        )
        assert len(pairs) == 5
        final_line_count = sum(1 for line in outfile.read_text().strip().split("\n") if line.strip())
        assert final_line_count == 5
