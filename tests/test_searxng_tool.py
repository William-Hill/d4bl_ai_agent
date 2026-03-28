"""Tests for SearXNG search tool."""

import json
from unittest.mock import MagicMock, patch

from d4bl.agents.tools.crawl_tools.searxng import SearXNGSearchTool


def test_searxng_tool_has_name():
    """Tool has expected name and description."""
    tool = SearXNGSearchTool(base_url="http://localhost:8080")
    assert "searxng" in tool.name.lower() or "search" in tool.name.lower()
    assert tool.description


def test_searxng_tool_default_category():
    """Default category is general."""
    tool = SearXNGSearchTool(base_url="http://localhost:8080")
    assert tool.default_category == "general"


def test_searxng_tool_custom_category():
    """Category can be set to news."""
    tool = SearXNGSearchTool(base_url="http://localhost:8080", default_category="news")
    assert tool.default_category == "news"


@patch("d4bl.agents.tools.crawl_tools.searxng.httpx")
def test_searxng_tool_run_returns_results(mock_httpx):
    """_run queries SearXNG and returns formatted results."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "title": "Racial Equity Report",
                "url": "https://example.com/report",
                "content": "A report on racial equity in housing.",
            },
            {
                "title": "Justice Data",
                "url": "https://example.com/data",
                "content": "Criminal justice data by race.",
            },
        ]
    }
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response
    mock_httpx.Client.return_value = mock_client

    tool = SearXNGSearchTool(base_url="http://localhost:8080")
    result = tool._run("racial equity housing")

    parsed = json.loads(result)
    assert len(parsed) == 2
    assert parsed[0]["title"] == "Racial Equity Report"
    assert parsed[0]["url"] == "https://example.com/report"

    # Verify correct URL called
    call_args = mock_client.get.call_args
    assert "search" in call_args[0][0]


@patch("d4bl.agents.tools.crawl_tools.searxng.httpx")
def test_searxng_tool_handles_error(mock_httpx):
    """_run returns error message on failure."""
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.side_effect = Exception("Connection refused")
    mock_httpx.Client.return_value = mock_client

    tool = SearXNGSearchTool(base_url="http://localhost:8080")
    result = tool._run("test query")

    assert "error" in result.lower() or "failed" in result.lower()
