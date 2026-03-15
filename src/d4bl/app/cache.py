"""In-memory TTL cache for explore API endpoints."""
from __future__ import annotations

import logging
import time

from cachetools import TTLCache

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 300  # 5 minutes
_DEFAULT_MAXSIZE = 200


class ExploreCache:
    """Thread-safe TTL cache with ingestion-aware invalidation."""

    def __init__(
        self, ttl_seconds: int = _DEFAULT_TTL, maxsize: int = _DEFAULT_MAXSIZE
    ):
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl_seconds)
        self._created_at: dict[str, float] = {}

    def get(self, key: str):
        """Return cached value or ``None`` if missing / expired."""
        return self._cache.get(key)

    def set(self, key: str, value):
        """Store *value* under *key* and record creation time."""
        self._cache[key] = value
        self._created_at[key] = time.time()

    def invalidate_if_stale(self, newer_than: float):
        """Clear entries created before *newer_than* epoch timestamp."""
        stale_keys = [
            k
            for k, created in self._created_at.items()
            if created < newer_than
        ]
        for k in stale_keys:
            self._cache.pop(k, None)
            self._created_at.pop(k, None)
        if stale_keys:
            logger.info("Cache: invalidated %d stale entries", len(stale_keys))

    def clear(self):
        """Remove all cached entries."""
        self._cache.clear()
        self._created_at.clear()


# Singleton instance used by the API layer.
explore_cache = ExploreCache()
