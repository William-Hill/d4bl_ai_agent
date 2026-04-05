"""Tests for regression detection between eval runs."""

from __future__ import annotations

from scripts.training.run_eval_harness import detect_regressions


class TestDetectRegressions:
    def test_no_regression_when_improved(self):
        previous = {"json_valid_rate": 0.90, "entity_f1": 0.80}
        current = {"json_valid_rate": 0.95, "entity_f1": 0.85}
        alerts = detect_regressions(current, previous, task="query_parser")
        assert alerts == []

    def test_regression_detected(self):
        previous = {"json_valid_rate": 0.95, "entity_f1": 0.85}
        current = {"json_valid_rate": 0.85, "entity_f1": 0.75}
        alerts = detect_regressions(current, previous, task="query_parser")
        assert len(alerts) == 2
        assert all(a.direction == "decreased" for a in alerts)

    def test_latency_regression_is_increase(self):
        previous = {"p95_latency_ms": 500}
        current = {"p95_latency_ms": 1200}
        alerts = detect_regressions(current, previous, task="query_parser")
        assert len(alerts) == 1
        assert alerts[0].direction == "increased"

    def test_no_previous_returns_empty(self):
        current = {"json_valid_rate": 0.95}
        alerts = detect_regressions(current, None, task="query_parser")
        assert alerts == []

    def test_threshold_tolerance(self):
        """Small changes (<2%) should not trigger alerts."""
        previous = {"json_valid_rate": 0.95}
        current = {"json_valid_rate": 0.94}  # -1%, within tolerance
        alerts = detect_regressions(current, previous, task="query_parser", tolerance=0.02)
        assert alerts == []
