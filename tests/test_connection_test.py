"""Unit tests for the test connection helper."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from d4bl.app.data_routes import _test_connection
from d4bl.app.schemas import ConnectionTestResponse


@pytest.mark.asyncio
async def test_api_no_url():
    result = await _test_connection("api", {})
    assert result.success is False
    assert "No URL" in result.message


@pytest.mark.asyncio
async def test_web_scrape_no_url():
    result = await _test_connection("web_scrape", {})
    assert result.success is False
    assert "No URL" in result.message


@pytest.mark.asyncio
async def test_rss_no_url():
    result = await _test_connection("rss_feed", {})
    assert result.success is False
    assert "No feed URL" in result.message


@pytest.mark.asyncio
async def test_database_no_dsn():
    result = await _test_connection("database", {})
    assert result.success is False
    assert "No connection string" in result.message


@pytest.mark.asyncio
async def test_mcp_no_url():
    result = await _test_connection("mcp", {})
    assert result.success is False
    assert "No URL" in result.message


@pytest.mark.asyncio
async def test_file_upload_no_dir(tmp_path):
    result = await _test_connection("file_upload", {"source_id": "nonexistent"})
    assert result.success is False
    assert "No files found" in result.message


@pytest.mark.asyncio
async def test_unknown_type():
    result = await _test_connection("ftp", {})
    assert result.success is False
    assert "Unknown source type" in result.message


@pytest.mark.asyncio
async def test_api_success():
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.head = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("d4bl.app.data_routes.aiohttp.ClientSession", return_value=mock_session):
        result = await _test_connection("api", {"url": "https://example.com/api"})
    assert result.success is True
    assert "200" in result.message


@pytest.mark.asyncio
async def test_rss_valid_feed():
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text = AsyncMock(return_value='<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>')
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("d4bl.app.data_routes.aiohttp.ClientSession", return_value=mock_session):
        result = await _test_connection("rss_feed", {"feed_url": "https://example.com/feed"})
    assert result.success is True
    assert "Valid RSS" in result.message


@pytest.mark.asyncio
async def test_rss_invalid_feed():
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text = AsyncMock(return_value="<html><body>Not a feed</body></html>")
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("d4bl.app.data_routes.aiohttp.ClientSession", return_value=mock_session):
        result = await _test_connection("rss_feed", {"url": "https://example.com/page"})
    assert result.success is False
    assert "not valid RSS" in result.message
