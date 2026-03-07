"""Tests for the observability module."""

from unittest.mock import MagicMock, patch

import d4bl.observability.langfuse as langfuse_mod
from d4bl.observability.langfuse import (
    check_langfuse_service_available,
    resolve_langfuse_host,
)


class TestResolveLangfuseHost:
    """Tests for resolve_langfuse_host Docker host adjustment."""

    def test_non_docker_returns_host_unchanged(self):
        """When not in Docker, the host should be returned as-is."""
        host = "http://localhost:3002"
        assert resolve_langfuse_host(host, is_docker=False) == host

    def test_docker_replaces_localhost_with_service_name(self):
        """In Docker, localhost should be replaced with langfuse-web."""
        result = resolve_langfuse_host(
            "http://localhost:3000", is_docker=True
        )
        assert result == "http://langfuse-web:3000"

    def test_docker_replaces_localhost_and_adjusts_port_3002(self):
        """In Docker, localhost:3002 should become langfuse-web:3000."""
        result = resolve_langfuse_host(
            "http://localhost:3002", is_docker=True
        )
        assert result == "http://langfuse-web:3000"

    def test_docker_without_localhost_returns_unchanged(self):
        """In Docker, a non-localhost host should be returned as-is."""
        host = "http://langfuse-web:3000"
        assert resolve_langfuse_host(host, is_docker=True) == host


class TestCheckLangfuseServiceAvailable:
    """Tests for check_langfuse_service_available."""

    def test_returns_false_for_unreachable_host(self):
        """Should return False when the host is not reachable."""
        with patch("urllib.request.urlopen", side_effect=OSError("Connection refused")):
            result = check_langfuse_service_available(
                "http://127.0.0.1:19999", timeout=0.5
            )
        assert result is False

    def test_returns_true_on_successful_health_check(self):
        """Should return True when the health endpoint responds."""
        mock_resp = MagicMock()
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            result = check_langfuse_service_available("http://localhost:3000")
        assert result is True
        mock_urlopen.assert_called_once_with(
            "http://localhost:3000/api/public/health", timeout=3.0
        )
        mock_resp.close.assert_called_once()

    def test_returns_false_on_exception(self):
        """Should return False when urlopen raises any exception."""
        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            result = check_langfuse_service_available("http://localhost:3000")
        assert result is False

    def test_rejects_non_http_scheme(self):
        """Should return False for non-HTTP schemes (S310 URL audit)."""
        assert check_langfuse_service_available("ftp://evil.com") is False
        assert check_langfuse_service_available("file:///etc/passwd") is False


class TestInitializeLangfuseSentinel:
    """Tests for the three-state init sentinel."""

    def _reset_module_state(self) -> None:
        """Reset module-level sentinel and client to pristine state."""
        langfuse_mod._langfuse_init_state = None
        langfuse_mod._langfuse_client = None

    def test_init_not_reattempted_after_failure(self):
        """After a failed init, subsequent calls should not re-attempt."""
        self._reset_module_state()

        # Use a counter to track how many times the try-block body runs.
        # We patch builtins.__import__ to raise ImportError for 'langfuse',
        # which is the first import inside initialize_langfuse's try block.
        import builtins

        real_import = builtins.__import__
        call_count = 0

        def counting_import(name, *args, **kwargs):
            nonlocal call_count
            if name == "langfuse":
                call_count += 1
                raise ImportError("simulated: no langfuse")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=counting_import):
            # First call triggers init and fails via ImportError
            result1 = langfuse_mod.initialize_langfuse()
            assert result1 is None
            assert langfuse_mod._langfuse_init_state is False
            assert call_count == 1

            # Second call should short-circuit, not re-attempt
            result2 = langfuse_mod.initialize_langfuse()
            assert result2 is None
            assert call_count == 1  # still 1, not 2

        self._reset_module_state()

    def test_get_langfuse_client_skips_init_after_failure(self):
        """get_langfuse_client should not re-init after a failure."""
        self._reset_module_state()

        import builtins

        real_import = builtins.__import__
        call_count = 0

        def counting_import(name, *args, **kwargs):
            nonlocal call_count
            if name == "langfuse":
                call_count += 1
                raise ImportError("simulated: no langfuse")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=counting_import):
            # First call via get_langfuse_client triggers init
            client1 = langfuse_mod.get_langfuse_client()
            assert client1 is None
            assert call_count == 1

            # Second call should not re-trigger init
            client2 = langfuse_mod.get_langfuse_client()
            assert client2 is None
            assert call_count == 1

        self._reset_module_state()

    def test_sentinel_none_means_untried(self):
        """When sentinel is None, init should be attempted."""
        self._reset_module_state()
        assert langfuse_mod._langfuse_init_state is None

        import builtins

        real_import = builtins.__import__

        def fail_import(name, *args, **kwargs):
            if name == "langfuse":
                raise ImportError("simulated")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fail_import):
            langfuse_mod.initialize_langfuse()

        # After attempt (even failed), sentinel is no longer None
        assert langfuse_mod._langfuse_init_state is not None

        self._reset_module_state()
