"""Smoke test for the BJS explore endpoint registration."""

import pytest


def test_bjs_endpoint_exists():
    """Verify the BJS explore endpoint is registered on the app."""
    from d4bl.app.api import app

    routes = [r.path for r in app.routes]
    assert "/api/explore/bjs" in routes


def test_bjs_frontend_config():
    """Verify BJS is in the expected frontend config shape."""
    import json
    from pathlib import Path

    config_path = Path(__file__).parent.parent / "ui-nextjs" / "lib" / "explore-config.ts"
    content = config_path.read_text()
    assert '"bjs"' in content
    assert "/api/explore/bjs" in content
