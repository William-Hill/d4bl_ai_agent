"""Tests for schedule admin API routes."""

import importlib
import sys
import types
from pathlib import Path


def _load_router():
    """Load the schedule_routes router, bypassing d4bl.app.__init__ if needed."""
    # If d4bl.app hasn't been imported yet, insert a stub to prevent
    # __init__.py from pulling in api.py (which triggers CrewAI imports).
    if "d4bl.app" not in sys.modules:
        stub = types.ModuleType("d4bl.app")
        # Point __path__ at the actual package directory so sub-modules resolve.
        pkg_dir = str(Path(__file__).resolve().parent.parent / "src" / "d4bl" / "app")
        stub.__path__ = [pkg_dir]
        stub.__package__ = "d4bl.app"
        sys.modules["d4bl.app"] = stub

    mod = importlib.import_module("d4bl.app.schedule_routes")
    return mod.router


def test_router_has_expected_routes():
    """Router defines the expected schedule management endpoints."""
    router = _load_router()
    paths = [r.path for r in router.routes]
    assert "/api/admin/schedules" in paths
    assert "/api/admin/schedules/{schedule_id}" in paths


def test_router_methods():
    """Router has GET, POST, DELETE methods."""
    router = _load_router()
    methods = set()
    for route in router.routes:
        if hasattr(route, "methods"):
            methods.update(route.methods)
    assert "GET" in methods
    assert "POST" in methods
    assert "DELETE" in methods


def test_router_has_trigger_route():
    """Router defines the trigger endpoint."""
    router = _load_router()
    paths = [r.path for r in router.routes]
    assert "/api/admin/schedules/{schedule_id}/run" in paths


def test_all_routes_tagged_admin():
    """All routes are tagged with 'admin'."""
    router = _load_router()
    for route in router.routes:
        if hasattr(route, "tags"):
            assert "admin" in route.tags
