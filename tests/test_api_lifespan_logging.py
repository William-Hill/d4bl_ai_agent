"""Tests for api.py lifespan migration and structured logging."""
import inspect
import logging
import sys
from unittest.mock import MagicMock

# Stub out langfuse before any d4bl imports so the import chain succeeds.
sys.modules.setdefault("langfuse", MagicMock())
sys.modules.setdefault("langfuse.Langfuse", MagicMock())

sys.path.insert(0, "src")


def test_app_uses_lifespan_not_on_event():
    """app should use lifespan= param, not deprecated @app.on_event."""
    from d4bl.app import api
    # Verify no deprecated on_event handlers are registered
    assert not api.app.router.on_startup, "on_event startup handler found"
    assert not api.app.router.on_shutdown, "on_event shutdown handler found"


def test_api_has_module_level_logger():
    """api module must define logger = logging.getLogger(__name__) at module level."""
    from d4bl.app import api
    assert hasattr(api, "logger")
    assert isinstance(api.logger, logging.Logger)


def test_no_traceback_print_exc_in_api():
    """api.py must not use traceback.print_exc() — use logger.exception() instead."""
    from d4bl.app import api
    source = inspect.getsource(api)
    assert "traceback.print_exc" not in source


def test_exception_chaining_in_500_handlers():
    """All HTTPException(500) raises in api.py must use 'raise ... from e'."""
    import re
    from d4bl.app import api
    source = inspect.getsource(api)
    pattern = re.compile(
        r'raise HTTPException\(status_code=500.*?\)(?:\s*from\s+\w+)?',
        re.DOTALL,
    )
    for match in pattern.finditer(source):
        assert " from " in match.group(), (
            f"Missing 'from e' on:\n{match.group()}"
        )


def test_websocket_uses_session_maker_not_get_db_generator():
    """WebSocket handler must use async_session_maker directly, not async-for-get_db."""
    from d4bl.app import api
    source = inspect.getsource(api.websocket_endpoint)
    assert "async for db in get_db()" not in source
