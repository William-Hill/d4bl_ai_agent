"""Tests for the in-memory TTL cache used by explore endpoints."""
from __future__ import annotations

import time

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
    """Ingestion-aware invalidation via invalidate_if_stale.

    The simplified cache clears ALL entries when a newer ingestion
    timestamp is detected (rather than per-entry staleness tracking).
    """

    def test_clears_all_entries_on_newer_ingestion(self):
        cache = ExploreCache(ttl_seconds=300, maxsize=10)
        cache.set("old", "stale-data")
        cutoff = time.time() + 1  # newer than _last_ingestion_ts (0.0)
        cache.invalidate_if_stale(newer_than=cutoff)
        assert cache.get("old") is None

    def test_no_op_when_ingestion_ts_not_newer(self):
        """If newer_than <= _last_ingestion_ts, cache is untouched."""
        cache = ExploreCache(ttl_seconds=300, maxsize=10)
        # First invalidation sets _last_ingestion_ts
        cache.invalidate_if_stale(newer_than=100.0)
        cache.set("fresh", "good-data")
        # Same timestamp — should NOT clear
        cache.invalidate_if_stale(newer_than=100.0)
        assert cache.get("fresh") == "good-data"

    def test_clears_on_strictly_newer_timestamp(self):
        """A strictly newer timestamp clears the cache again."""
        cache = ExploreCache(ttl_seconds=300, maxsize=10)
        cache.invalidate_if_stale(newer_than=100.0)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.invalidate_if_stale(newer_than=200.0)
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_clear_resets_last_ingestion_ts(self):
        """After clear(), even an old timestamp triggers invalidation."""
        cache = ExploreCache(ttl_seconds=300, maxsize=10)
        cache.invalidate_if_stale(newer_than=500.0)
        cache.clear()
        cache.set("after-clear", "value")
        # 100 < 500 normally wouldn't trigger, but clear() reset to 0
        cache.invalidate_if_stale(newer_than=100.0)
        assert cache.get("after-clear") is None
