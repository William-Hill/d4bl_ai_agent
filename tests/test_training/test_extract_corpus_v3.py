"""Tests for document corpus extraction (v3)."""

from scripts.training.extract_corpus import EXTRACTORS
from scripts.training.templates import render_document_passage


class TestRenderDocumentPassage:
    def test_wraps_with_metadata(self):
        row = {
            "content": "Eviction rates in Georgia increased 15% in 2023.",
            "title": "Georgia Housing Report",
            "content_type": "research_report",
        }
        passage = render_document_passage(row)
        assert "Georgia Housing Report" in passage
        assert "research_report" in passage
        assert "Eviction rates in Georgia" in passage

    def test_handles_missing_title(self):
        row = {"content": "Some content.", "title": None, "content_type": "news"}
        passage = render_document_passage(row)
        assert "Some content." in passage
        assert "news" in passage

    def test_returns_empty_for_no_content(self):
        row = {"content": "", "title": "Empty", "content_type": "pdf"}
        passage = render_document_passage(row)
        assert passage == ""


class TestDocumentsExtractor:
    def test_documents_in_registry(self):
        assert "documents" in EXTRACTORS

    def test_documents_extractor_has_required_keys(self):
        ext = EXTRACTORS["documents"]
        assert "query" in ext
        assert "template" in ext
        assert ext["template"] is render_document_passage
