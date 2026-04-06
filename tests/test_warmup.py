"""Tests for SearXNG warmup and phase-aware progress messages."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.fixture
def mock_settings_searxng():
    """Settings with SearXNG configured."""
    settings = MagicMock()
    settings.searxng_base_url = "http://searxng:8080"
    settings.search_provider = "searxng"
    return settings


@pytest.fixture
def mock_settings_no_searxng():
    """Settings with SearXNG NOT configured (different provider)."""
    settings = MagicMock()
    settings.searxng_base_url = "http://searxng:8080"
    settings.search_provider = "google"
    return settings


class TestWarmupPing:
    """Test the SearXNG warmup ping behavior."""

    @pytest.mark.asyncio
    async def test_warmup_pings_healthz(self, mock_settings_searxng):
        """Warmup sends GET to SEARXNG_BASE_URL/healthz."""
        from d4bl.services.research_runner import warmup_searxng

        with patch("d4bl.services.research_runner.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_resp = MagicMock(status_code=200, is_success=True)
            mock_client.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await warmup_searxng(mock_settings_searxng)

            mock_client.get.assert_called_once_with(
                "http://searxng:8080/healthz", timeout=15.0
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_warmup_returns_false_on_unhealthy_status(self, mock_settings_searxng):
        """Warmup returns False on non-2xx /healthz responses."""
        from d4bl.services.research_runner import warmup_searxng

        with patch("d4bl.services.research_runner.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_resp = MagicMock(status_code=503, is_success=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await warmup_searxng(mock_settings_searxng)

            assert result is False

    @pytest.mark.asyncio
    async def test_warmup_skipped_when_not_searxng(self, mock_settings_no_searxng):
        """Warmup is skipped when search_provider != 'searxng'."""
        from d4bl.services.research_runner import warmup_searxng

        with patch("d4bl.services.research_runner.httpx.AsyncClient") as MockClient:
            result = await warmup_searxng(mock_settings_no_searxng)

            MockClient.assert_not_called()
            assert result is False

    @pytest.mark.asyncio
    async def test_warmup_skipped_when_url_empty(self):
        """Warmup is skipped when searxng_base_url is empty."""
        from d4bl.services.research_runner import warmup_searxng

        settings = MagicMock()
        settings.searxng_base_url = ""
        settings.search_provider = "searxng"

        with patch("d4bl.services.research_runner.httpx.AsyncClient") as MockClient:
            result = await warmup_searxng(settings)

            MockClient.assert_not_called()
            assert result is False

    @pytest.mark.asyncio
    async def test_warmup_handles_timeout(self, mock_settings_searxng):
        """Warmup returns False on timeout but does not raise."""
        from d4bl.services.research_runner import warmup_searxng

        with patch("d4bl.services.research_runner.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await warmup_searxng(mock_settings_searxng)

            assert result is False

    @pytest.mark.asyncio
    async def test_warmup_handles_connection_error(self, mock_settings_searxng):
        """Warmup returns False on connection error but does not raise."""
        from d4bl.services.research_runner import warmup_searxng

        with patch("d4bl.services.research_runner.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.ConnectError("connection refused")
            )
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await warmup_searxng(mock_settings_searxng)

            assert result is False


class TestPhaseInProgress:
    """Test that progress messages include the phase field."""

    @pytest.mark.asyncio
    async def test_notify_progress_includes_phase(self):
        """notify_progress sends phase in WebSocket update."""
        captured = []

        async def fake_send(job_id, data):
            captured.append(data)

        mock_db = AsyncMock()

        async def fake_get_db():
            yield mock_db

        with patch(
            "d4bl.services.research_runner.send_websocket_update", side_effect=fake_send
        ), patch(
            "d4bl.services.research_runner.update_job_status", new_callable=AsyncMock
        ), patch(
            "d4bl.services.research_runner.get_db", fake_get_db
        ):
            from d4bl.services.research_runner import _make_notify_progress

            notify = _make_notify_progress("test-job-id", None)
            await notify("Warming up search services...", phase="warmup")

            assert len(captured) == 1
            msg = captured[0]
            assert msg["phase"] == "warmup"
            assert msg["message"] == "Warming up search services..."
            assert msg["type"] == "progress"

    @pytest.mark.asyncio
    async def test_notify_progress_omits_phase_when_none(self):
        """notify_progress does not include phase key when phase is None."""
        captured = []

        async def fake_send(job_id, data):
            captured.append(data)

        mock_db = AsyncMock()

        async def fake_get_db():
            yield mock_db

        with patch(
            "d4bl.services.research_runner.send_websocket_update", side_effect=fake_send
        ), patch(
            "d4bl.services.research_runner.update_job_status", new_callable=AsyncMock
        ), patch(
            "d4bl.services.research_runner.get_db", fake_get_db
        ):
            from d4bl.services.research_runner import _make_notify_progress

            notify = _make_notify_progress("test-job-id", None)
            await notify("Some progress message")

            assert len(captured) == 1
            assert "phase" not in captured[0]

