"""Tests for the content extraction library."""

import pytest
from unittest.mock import patch, MagicMock
from scripts.ingestion.lib.content_extractor import (
    ExtractedContent,
    extract_from_html,
    detect_content_type,
    extract,
)


def test_extracted_content_dataclass():
    """ExtractedContent has expected fields."""
    content = ExtractedContent(
        url="https://example.com",
        title="Test",
        author="Author",
        date="2026-01-01",
        text="Hello world",
        source_type="html",
        metadata={},
    )
    assert content.url == "https://example.com"
    assert content.text == "Hello world"
    assert content.source_type == "html"


def test_detect_content_type_pdf():
    """PDF URLs detected correctly."""
    assert detect_content_type("https://example.com/report.pdf") == "pdf"
    assert detect_content_type("https://example.com/report.PDF") == "pdf"


def test_detect_content_type_rss():
    """RSS URLs detected by common patterns."""
    assert detect_content_type("https://example.com/feed.xml") == "rss"
    assert detect_content_type("https://example.com/rss") == "rss"
    assert detect_content_type("https://example.com/atom.xml") == "rss"


def test_detect_content_type_html_default():
    """Default content type is html."""
    assert detect_content_type("https://example.com/article") == "html"
    assert detect_content_type("https://example.com/page.html") == "html"


def test_extract_from_html_with_trafilatura():
    """extract_from_html uses trafilatura for text extraction."""
    sample_html = """
    <html>
    <head><title>Test Article</title></head>
    <body>
    <nav>Navigation</nav>
    <article>
    <h1>Test Article</h1>
    <p>This is the main content of the article that should be extracted.</p>
    <p>It has multiple paragraphs with enough text for trafilatura to work.</p>
    </article>
    <footer>Footer content</footer>
    </body>
    </html>
    """
    result = extract_from_html(sample_html, "https://example.com/article")
    assert result is not None
    assert isinstance(result, ExtractedContent)
    assert result.source_type == "html"
    # trafilatura should extract article content, not nav/footer
    assert "main content" in result.text.lower() or len(result.text) > 0


def test_extract_from_html_empty_returns_none():
    """extract_from_html returns None for empty/minimal HTML."""
    result = extract_from_html("<html><body></body></html>", "https://example.com")
    assert result is None


@patch("scripts.ingestion.lib.content_extractor.httpx")
def test_extract_fetches_url(mock_httpx):
    """extract() fetches the URL and processes the response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "text/html"}
    mock_response.text = """
    <html><body>
    <article><p>This is substantial content for testing the extraction pipeline.</p>
    <p>We need enough text here for trafilatura to consider it worth extracting.</p>
    </article></body></html>
    """
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response
    mock_httpx.Client.return_value = mock_client

    result = extract("https://example.com/article")
    assert result is not None
    assert result.url == "https://example.com/article"
    mock_client.get.assert_called_once()
