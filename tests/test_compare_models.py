"""Tests for the model comparison evaluation script."""
from __future__ import annotations

from scripts.training.compare_models import (
    ComparisonResult,
    format_report,
)


class TestComparisonResult:
    def test_delta(self):
        r = ComparisonResult(
            prompt="test", task="query_parser",
            baseline_valid=True, baseline_latency=1.0,
            finetuned_valid=True, finetuned_latency=0.5,
        )
        assert r.latency_delta == -0.5

    def test_validity_improvement(self):
        r = ComparisonResult(
            prompt="test", task="query_parser",
            baseline_valid=False, baseline_latency=1.0,
            finetuned_valid=True, finetuned_latency=0.5,
        )
        assert r.validity_improved is True


class TestFormatReport:
    def test_report_structure(self):
        results = [
            ComparisonResult(
                prompt="p1", task="query_parser",
                baseline_valid=True, baseline_latency=1.0,
                finetuned_valid=True, finetuned_latency=0.5,
            ),
        ]
        report = format_report(results)
        assert "query_parser" in report
        assert "Latency" in report
