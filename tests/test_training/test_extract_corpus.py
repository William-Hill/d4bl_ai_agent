"""Tests for corpus extraction."""

import json

from scripts.training.extract_corpus import (
    EXTRACTORS,
    write_passages_jsonl,
)


class TestWritePassagesJsonl:
    def test_writes_jsonl_format(self, tmp_path):
        passages = ["Passage one.", "Passage two."]
        outfile = tmp_path / "test.jsonl"
        count = write_passages_jsonl(passages, outfile)
        assert count == 2
        lines = outfile.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"text": "Passage one."}
        assert json.loads(lines[1]) == {"text": "Passage two."}

    def test_skips_empty_passages(self, tmp_path):
        passages = ["Good passage.", "", "  ", "Another good one."]
        outfile = tmp_path / "test.jsonl"
        count = write_passages_jsonl(passages, outfile)
        assert count == 2

    def test_creates_parent_dirs(self, tmp_path):
        outfile = tmp_path / "sub" / "dir" / "test.jsonl"
        write_passages_jsonl(["Hello."], outfile)
        assert outfile.exists()


class TestExtractors:
    def test_all_tables_have_extractors(self):
        expected_tables = [
            "census_indicators",
            "cdc_health_outcomes",
            "epa_environmental_justice",
            "police_violence_incidents",
            "bjs_incarceration",
            "fbi_crime_stats",
        ]
        for table in expected_tables:
            assert table in EXTRACTORS, f"Missing extractor for {table}"

    def test_extractor_has_required_keys(self):
        for table, ext in EXTRACTORS.items():
            assert "query" in ext, f"{table} missing 'query'"
            assert "template" in ext, f"{table} missing 'template'"
            assert callable(ext["template"]), f"{table} template not callable"
