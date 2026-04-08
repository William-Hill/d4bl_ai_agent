"""Tests for document persistence from research jobs."""

from __future__ import annotations

import pytest

from d4bl.services.document_persistence import normalize_url


class TestNormalizeUrl:
    """URL normalization strips tracking params, normalizes scheme/host/path."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("http://Example.COM/path", "https://example.com/path"),
            ("https://example.com/path/", "https://example.com/path"),
            (
                "https://example.com/page?utm_source=google&utm_medium=cpc&id=123",
                "https://example.com/page?id=123",
            ),
            ("https://example.com/page?fbclid=abc123", "https://example.com/page"),
            ("https://example.com/page?gclid=xyz&ref=twitter", "https://example.com/page"),
            ("https://example.com/page?z=1&a=2", "https://example.com/page?a=2&z=1"),
            (
                "https://api.census.gov/data?get=NAME&for=county:*",
                "https://api.census.gov/data?for=county%3A%2A&get=NAME",
            ),
            ("https://example.com/report", "https://example.com/report"),
            ("https://example.com", "https://example.com"),
            ("https://example.com/", "https://example.com"),
        ],
    )
    def test_normalize_url(self, raw: str, expected: str):
        assert normalize_url(raw) == expected


from d4bl.services.document_persistence import chunk_text


class TestChunkText:
    """Paragraph-based chunking with size cap."""

    def test_empty_content(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_single_short_paragraph(self):
        result = chunk_text("Hello world.")
        assert len(result) == 1
        assert result[0][0] == "Hello world."
        assert result[0][1] == len("Hello world.") // 4

    def test_multiple_paragraphs_under_limit(self):
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        result = chunk_text(text, max_chars=2000)
        assert len(result) == 1
        assert "Paragraph one." in result[0][0]
        assert "Paragraph three." in result[0][0]

    def test_paragraphs_exceed_limit(self):
        para = "A" * 1200
        text = f"{para}\n\n{para}\n\n{para}"
        result = chunk_text(text, max_chars=2000)
        assert len(result) >= 2
        for content, token_count in result:
            assert len(content) <= 2500
            assert token_count == len(content) // 4

    def test_single_oversized_paragraph_splits_on_sentences(self):
        sentences = ". ".join(f"Sentence {i} with some words" for i in range(80))
        result = chunk_text(sentences, max_chars=500)
        assert len(result) >= 3
        for content, _ in result:
            assert len(content) <= 600

    def test_preserves_all_content(self):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        result = chunk_text(text, max_chars=30)
        reassembled = "\n\n".join(content for content, _ in result)
        assert "First paragraph." in reassembled
        assert "Second paragraph." in reassembled
        assert "Third paragraph." in reassembled
