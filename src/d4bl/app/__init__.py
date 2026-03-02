"""
Application package for the D4BL FastAPI backend.

Tests patch `d4bl.app.api.*`, so this module ensures the `api` submodule
is imported and available as an attribute on `d4bl.app`.
"""

from . import api  # noqa: F401  (re-export for test patching)

