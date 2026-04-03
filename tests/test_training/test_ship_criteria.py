"""Tests for ship/no-ship criteria checker."""

from __future__ import annotations

import pytest

from scripts.training.ship_criteria import (
    SHIP_CRITERIA,
    check_ship_criteria,
)


class TestShipCriteria:
    def test_criteria_has_all_tasks(self):
        assert "query_parser" in SHIP_CRITERIA
        assert "explainer" in SHIP_CRITERIA
        assert "evaluator" in SHIP_CRITERIA

    def test_all_criteria_have_blocking_flag(self):
        for task, criteria in SHIP_CRITERIA.items():
            for metric, spec in criteria.items():
                assert "blocking" in spec, f"{task}.{metric} missing 'blocking'"
                assert "min" in spec or "max" in spec, f"{task}.{metric} needs 'min' or 'max'"


class TestCheckShipCriteria:
    def test_ship_when_all_blocking_pass(self):
        metrics = {
            "json_valid_rate": 0.98,
            "entity_f1": 0.85,
            "data_source_accuracy": 0.90,
            "p95_latency_ms": 800,
            "adversarial_pass_rate": 0.90,
            "community_framing_f1": 0.75,
        }
        result = check_ship_criteria(metrics, "query_parser")
        assert result.decision == "ship"
        assert result.blocking_failures == []

    def test_no_ship_when_blocking_fails(self):
        metrics = {
            "json_valid_rate": 0.80,  # below 0.95 threshold
            "entity_f1": 0.85,
            "data_source_accuracy": 0.90,
            "p95_latency_ms": 800,
            "adversarial_pass_rate": 0.90,
            "community_framing_f1": 0.75,
        }
        result = check_ship_criteria(metrics, "query_parser")
        assert result.decision == "no_ship"
        assert "json_valid_rate" in [f.metric for f in result.blocking_failures]

    def test_ship_with_gaps_when_only_nonblocking_fails(self):
        metrics = {
            "json_valid_rate": 0.98,
            "entity_f1": 0.85,
            "data_source_accuracy": 0.90,
            "p95_latency_ms": 800,
            "adversarial_pass_rate": 0.90,
            "community_framing_f1": 0.50,  # below 0.70 but non-blocking
        }
        result = check_ship_criteria(metrics, "query_parser")
        assert result.decision == "ship_with_gaps"
        assert len(result.nonblocking_failures) > 0

    def test_max_threshold_check(self):
        """p95_latency_ms uses 'max' not 'min' — exceeding is a failure."""
        metrics = {
            "json_valid_rate": 0.98,
            "entity_f1": 0.85,
            "data_source_accuracy": 0.90,
            "p95_latency_ms": 1500,  # above 1000 max
            "adversarial_pass_rate": 0.90,
            "community_framing_f1": 0.75,
        }
        result = check_ship_criteria(metrics, "query_parser")
        assert result.decision == "no_ship"
        assert "p95_latency_ms" in [f.metric for f in result.blocking_failures]

    def test_missing_metric_treated_as_failure(self):
        metrics = {"json_valid_rate": 0.98}  # missing everything else
        result = check_ship_criteria(metrics, "query_parser")
        assert result.decision == "no_ship"
        assert len(result.blocking_failures) > 0

    def test_partial_mode_skips_missing_metrics(self):
        """In partial mode, missing metrics are not treated as failures."""
        metrics = {"json_valid_rate": 0.98}  # only one metric provided
        result = check_ship_criteria(metrics, "query_parser", partial=True)
        # json_valid_rate passes, missing ones skipped — no blocking failures
        assert result.decision == "ship"

    def test_unknown_task_raises(self):
        with pytest.raises(KeyError):
            check_ship_criteria({}, "nonexistent_task")