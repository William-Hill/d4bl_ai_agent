"""Tests for eval harness metric computation."""
from __future__ import annotations

import json

import pytest

from scripts.training.eval_harness import (
    compute_entity_f1,
    compute_parser_metrics,
    compute_explainer_metrics,
    compute_evaluator_metrics,
    load_test_set,
)


class TestComputeEntityF1:
    def test_perfect_match(self):
        assert compute_entity_f1(["a", "b", "c"], ["a", "b", "c"]) == 1.0

    def test_no_overlap(self):
        assert compute_entity_f1(["a", "b"], ["c", "d"]) == 0.0

    def test_partial_overlap(self):
        # predicted: a, b — expected: a, c
        # precision = 1/2, recall = 1/2, F1 = 0.5
        assert compute_entity_f1(["a", "b"], ["a", "c"]) == pytest.approx(0.5)

    def test_empty_predicted(self):
        assert compute_entity_f1([], ["a", "b"]) == 0.0

    def test_empty_expected(self):
        assert compute_entity_f1(["a", "b"], []) == 0.0

    def test_case_insensitive(self):
        assert compute_entity_f1(["Alabama"], ["alabama"]) == 1.0


class TestComputeParserMetrics:
    def test_all_valid_outputs(self):
        outputs = [
            {"raw": '{"intent": "lookup", "entities": ["Alabama"]}', "latency": 0.5},
            {"raw": '{"intent": "compare", "entities": ["Texas", "California"]}', "latency": 0.8},
        ]
        expected = [
            {"entities": ["Alabama"], "data_sources": ["census_indicators"]},
            {"entities": ["Texas", "California"], "data_sources": ["census_indicators"]},
        ]
        metrics = compute_parser_metrics(outputs, expected)
        assert metrics["json_valid_rate"] == 1.0
        assert "entity_f1" in metrics
        assert "p95_latency_ms" in metrics
        assert metrics["p95_latency_ms"] == pytest.approx(800.0, abs=50)

    def test_invalid_json_counted(self):
        outputs = [
            {"raw": "not json", "latency": 0.5},
            {"raw": '{"intent": "lookup", "entities": ["A"]}', "latency": 0.3},
        ]
        expected = [{"entities": ["B"]}, {"entities": ["A"]}]
        metrics = compute_parser_metrics(outputs, expected)
        assert metrics["json_valid_rate"] == 0.5


class TestComputeExplainerMetrics:
    def test_valid_outputs(self):
        outputs = [
            {"raw": '{"narrative": "Test narrative."}', "latency": 1.5},
        ]
        metrics = compute_explainer_metrics(outputs)
        assert metrics["json_valid_rate"] == 1.0
        assert "p95_latency_ms" in metrics


class TestComputeEvaluatorMetrics:
    def test_hallucination_accuracy(self):
        outputs = [
            {"raw": '{"score": 5, "label": "FACTUAL"}', "latency": 0.3},
            {"raw": '{"score": 1, "label": "HALLUCINATED"}', "latency": 0.4},
        ]
        expected_labels = ["FACTUAL", "HALLUCINATED"]
        metrics = compute_evaluator_metrics(outputs, expected_labels=expected_labels)
        assert metrics["hallucination_accuracy"] == 1.0

    def test_incorrect_labels(self):
        outputs = [
            {"raw": '{"score": 5, "label": "FACTUAL"}', "latency": 0.3},
            {"raw": '{"score": 5, "label": "FACTUAL"}', "latency": 0.4},
        ]
        expected_labels = ["FACTUAL", "HALLUCINATED"]
        metrics = compute_evaluator_metrics(outputs, expected_labels=expected_labels)
        assert metrics["hallucination_accuracy"] == 0.5


class TestLoadTestSet:
    def test_load_valid_jsonl(self, tmp_path):
        p = tmp_path / "test.jsonl"
        examples = [
            {"messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "question"},
                {"role": "assistant", "content": '{"intent": "lookup"}'},
            ]}
        ]
        p.write_text("\n".join(json.dumps(e) for e in examples))
        result = load_test_set(str(p))
        assert len(result) == 1
        assert result[0]["input"] == "question"
        assert result[0]["expected_raw"] == '{"intent": "lookup"}'

    def test_load_empty_file(self, tmp_path):
        p = tmp_path / "empty.jsonl"
        p.write_text("")
        result = load_test_set(str(p))
        assert result == []


from d4bl.infra.database import ModelEvalRun


class TestModelEvalRun:
    def test_model_has_required_columns(self):
        """ModelEvalRun should have all columns from the design spec."""
        columns = {c.name for c in ModelEvalRun.__table__.columns}
        expected = {
            "id", "model_name", "model_version", "base_model_name",
            "task", "test_set_hash", "metrics", "ship_decision",
            "blocking_failures", "created_at",
        }
        assert expected.issubset(columns)

    def test_tablename(self):
        assert ModelEvalRun.__tablename__ == "model_eval_runs"
