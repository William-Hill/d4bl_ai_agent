"""Tests for news search ingestion."""

import pytest
from unittest.mock import patch, MagicMock
from scripts.ingestion.ingest_news_search import (
    search_news,
    deduplicate_urls,
)


def test_deduplicate_urls_removes_duplicates():
    """deduplicate_urls removes entries with duplicate URLs."""
    results = [
        {"url": "https://example.com/a", "title": "First"},
        {"url": "https://example.com/b", "title": "Second"},
        {"url": "https://example.com/a", "title": "Duplicate"},
    ]
    deduped = deduplicate_urls(results)
    assert len(deduped) == 2
    assert deduped[0]["title"] == "First"
    assert deduped[1]["title"] == "Second"


def test_deduplicate_urls_empty():
    """deduplicate_urls handles empty list."""
    assert deduplicate_urls([]) == []


@patch("scripts.ingestion.ingest_news_search.httpx")
def test_search_news_queries_searxng(mock_httpx):
    """search_news calls SearXNG with news category."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {"title": "News 1", "url": "https://news.com/1", "content": "snippet"},
        ]
    }
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response
    mock_httpx.Client.return_value = mock_client

    results = search_news("racial equity", "http://localhost:8080")
    assert len(results) == 1
    assert results[0]["title"] == "News 1"

    call_kwargs = mock_client.get.call_args
    params = call_kwargs[1].get("params") or call_kwargs.kwargs.get("params")
    assert params["categories"] == "news"
