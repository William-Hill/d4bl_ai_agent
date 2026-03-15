"""Tests for the in-memory TTL cache used by explore endpoints."""
from __future__ import annotations

import time

import pytest

from d4bl.app.cache import ExploreCache


class TestExploreCacheBasics:
    """Basic get / set / miss behaviour."""

    def test_get_returns_cached_value(self):
        cache = ExploreCache(ttl_seconds=60, maxsize=10)
        cache.set("key1", {"rows": [1, 2, 3]})
        assert cache.get("key1") == {"rows": [1, 2, 3]}

    def test_get_returns_none_for_missing_key(self):
        cache = ExploreCache(ttl_seconds=60, maxsize=10)
        assert cache.get("nonexistent") is None

    def test_clear_removes_all_entries(self):
        cache = ExploreCache(ttl_seconds=60, maxsize=10)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None


class TestExploreCacheTTL:
    """TTL expiry behaviour."""

    def test_entry_expires_after_ttl(self):
        cache = ExploreCache(ttl_seconds=1, maxsize=10)
        cache.set("ephemeral", "data")
        assert cache.get("ephemeral") == "data"
        time.sleep(1.1)
        assert cache.get("ephemeral") is None


class TestExploreCacheInvalidation:
    """Ingestion-aware invalidation via invalidate_if_stale."""

    def test_invalidates_entries_created_before_timestamp(self):
        cache = ExploreCache(ttl_seconds=300, maxsize=10)
        cache.set("old", "stale-data")
        cutoff = time.time() + 1  # everything so far is older
        cache.invalidate_if_stale(newer_than=cutoff)
        assert cache.get("old") is None

    def test_preserves_entries_created_after_timestamp(self):
        cache = ExploreCache(ttl_seconds=300, maxsize=10)
        cutoff = time.time() - 1  # cutoff is in the past
        cache.set("fresh", "good-data")
        cache.invalidate_if_stale(newer_than=cutoff)
        assert cache.get("fresh") == "good-data"

    def test_mixed_stale_and_fresh(self):
        cache = ExploreCache(ttl_seconds=300, maxsize=10)
        cache.set("old1", "a")
        cache.set("old2", "b")
        cutoff = time.time() + 0.01
        time.sleep(0.02)
        cache.set("new1", "c")
        cache.invalidate_if_stale(newer_than=cutoff)
        assert cache.get("old1") is None
        assert cache.get("old2") is None
        assert cache.get("new1") == "c"
