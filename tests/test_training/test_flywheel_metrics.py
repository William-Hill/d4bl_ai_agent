"""Tests for flywheel metrics query functions."""

from scripts.training.flywheel_metrics import (
    build_corpus_stats,
)


class TestBuildCorpusStats:
    def test_computes_stats_from_rows(self):
        rows = [
            {"content_type": "policy_bill", "chunk_count": 100, "total_tokens": 5000},
            {"content_type": "research_report", "chunk_count": 50, "total_tokens": 25000},
            {"content_type": "html", "chunk_count": 200, "total_tokens": 100000},
        ]
        stats = build_corpus_stats(rows)
        assert stats["total_chunks"] == 350
        assert stats["total_tokens"] == 130000
        assert stats["content_types"]["policy_bill"] == 100
        assert stats["content_types"]["research_report"] == 50
        assert stats["content_types"]["html"] == 200

    def test_empty_rows(self):
        stats = build_corpus_stats([])
        assert stats["total_chunks"] == 0
        assert stats["total_tokens"] == 0
        assert stats["content_types"] == {}
