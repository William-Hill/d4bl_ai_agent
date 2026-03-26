"""Tests for the eval harness CLI."""
from __future__ import annotations

import hashlib
import json
from unittest.mock import AsyncMock, patch

import pytest

from scripts.training.run_eval_harness import (
    compute_test_set_hash,
    format_eval_report,
    run_task_eval,
    EvalRunResult,
)


class TestComputeTestSetHash:
    def test_deterministic(self, tmp_path):
        p = tmp_path / "test.jsonl"
        p.write_text('{"messages": [{"role": "system", "content": "s"}, '
                      '{"role": "user", "content": "q"}, '
                      '{"role": "assistant", "content": "a"}]}\n')
        h1 = compute_test_set_hash(str(p))
        h2 = compute_test_set_hash(str(p))
        assert h1 == h2
        assert len(h1) == 64  # SHA256 hex

    def test_different_content_different_hash(self, tmp_path):
        p1 = tmp_path / "a.jsonl"
        p2 = tmp_path / "b.jsonl"
        p1.write_text('{"messages": [{"role": "system", "content": "s"}, '
                       '{"role": "user", "content": "q1"}, '
                       '{"role": "assistant", "content": "a"}]}')
        p2.write_text('{"messages": [{"role": "system", "content": "s"}, '
                       '{"role": "user", "content": "q2"}, '
                       '{"role": "assistant", "content": "a"}]}')
        assert compute_test_set_hash(str(p1)) != compute_test_set_hash(str(p2))


class TestFormatEvalReport:
    def test_report_includes_decision(self):
        from scripts.training.ship_criteria import ShipDecision
        result = EvalRunResult(
            task="query_parser",
            model_name="d4bl-query-parser",
            model_version="v1.0",
            base_model_name="mistral",
            test_set_hash="abc123",
            metrics={"json_valid_rate": 0.98, "entity_f1": 0.85},
            ship_decision=ShipDecision(decision="ship"),
        )
        report = format_eval_report([result])
        assert "query_parser" in report
        assert "SHIP" in report.upper()
        assert "0.98" in report or "98.00%" in report


class TestRunTaskEval:
    @pytest.mark.asyncio
    @patch("scripts.training.run_eval_harness._run_prompt", new_callable=AsyncMock)
    async def test_runs_all_examples(self, mock_run):
        mock_run.return_value = ('{"intent": "lookup", "entities": ["AL"]}', 0.5)
        test_set = [
            {"input": "q1", "expected_raw": '{"entities": ["AL"]}',
             "expected": {"entities": ["AL"], "data_sources": ["census_indicators"]}},
            {"input": "q2", "expected_raw": '{"entities": ["TX"]}',
             "expected": {"entities": ["TX"], "data_sources": ["census_indicators"]}},
        ]
        result = await run_task_eval(
            task="query_parser",
            test_set=test_set,
            model_name="d4bl-query-parser",
            model_version="v1.0",
            base_model_name="mistral",
            base_url="http://localhost:11434",
            test_set_hash="abc",
        )
        assert result.task == "query_parser"
        assert result.metrics["json_valid_rate"] == 1.0
        assert mock_run.call_count == 2  # only fine-tuned (no baseline in task eval)
