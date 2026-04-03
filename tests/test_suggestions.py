"""Tests for the post-eval suggestion engine."""

from __future__ import annotations

from scripts.training.suggestions import generate_suggestions


class TestGenerateSuggestions:
    def test_blocking_suggestion_for_low_entity_f1(self):
        metrics = {"entity_f1": 0.72, "json_valid_rate": 0.99}
        result = generate_suggestions("query_parser", metrics)
        assert any(s.metric == "entity_f1" and s.severity == "blocking" for s in result.rules)

    def test_no_suggestions_when_all_pass(self):
        metrics = {
            "json_valid_rate": 0.99,
            "entity_f1": 0.90,
            "data_source_accuracy": 0.90,
            "community_framing_f1": 0.80,
            "p95_latency_ms": 500,
            "adversarial_pass_rate": 0.90,
        }
        result = generate_suggestions("query_parser", metrics)
        assert len(result.rules) == 0

    def test_nonblocking_suggestion_for_low_community_framing(self):
        metrics = {
            "json_valid_rate": 0.99,
            "entity_f1": 0.90,
            "data_source_accuracy": 0.90,
            "community_framing_f1": 0.55,
            "p95_latency_ms": 500,
            "adversarial_pass_rate": 0.90,
        }
        result = generate_suggestions("query_parser", metrics)
        assert any(
            s.metric == "community_framing_f1" and s.severity == "non-blocking"
            for s in result.rules
        )

    def test_max_direction_metric_latency(self):
        metrics = {"p95_latency_ms": 1500}
        result = generate_suggestions("query_parser", metrics)
        assert any(s.metric == "p95_latency_ms" and s.severity == "blocking" for s in result.rules)

    def test_explainer_suggestions(self):
        metrics = {"d4bl_composite": 2.5, "factual_accuracy": 0.80}
        result = generate_suggestions("explainer", metrics)
        assert any(s.metric == "d4bl_composite" for s in result.rules)
        assert any(s.metric == "factual_accuracy" for s in result.rules)

    def test_evaluator_suggestions(self):
        metrics = {"hallucination_accuracy": 0.70, "bias_mae": 1.5}
        result = generate_suggestions("evaluator", metrics)
        assert any(s.metric == "hallucination_accuracy" for s in result.rules)
        assert any(s.metric == "bias_mae" for s in result.rules)

    def test_missing_metric_not_suggested(self):
        metrics = {"entity_f1": 0.90}  # passes threshold; other metrics absent
        result = generate_suggestions("query_parser", metrics)
        assert len(result.rules) == 0

    def test_unknown_task_returns_empty(self):
        result = generate_suggestions("unknown_task", {"foo": 0.5})
        assert len(result.rules) == 0

    def test_to_dict_format(self):
        metrics = {"entity_f1": 0.72}
        result = generate_suggestions("query_parser", metrics)
        d = result.to_dict()
        assert "rules" in d
        assert "llm_analysis" in d
        assert "generated_at" in d
        assert d["rules"][0]["metric"] == "entity_f1"
        assert d["rules"][0]["current"] == 0.72
        assert d["rules"][0]["target"] == 0.80