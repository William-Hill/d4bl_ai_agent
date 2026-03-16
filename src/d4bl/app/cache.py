"""In-memory TTL cache for explore API endpoints."""
from __future__ import annotations

import logging
from typing import Any

from cachetools import TTLCache

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 300  # 5 minutes
_DEFAULT_MAXSIZE = 200


class ExploreCache:
    """TTL cache with ingestion-aware invalidation.

    Individual get/set/clear operations are atomic. Compound check-then-set
    patterns in calling code may require external synchronization.
    """

    def __init__(
        self, ttl_seconds: int = _DEFAULT_TTL, maxsize: int = _DEFAULT_MAXSIZE
    ):
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl_seconds)
        self._last_ingestion_ts: float = 0.0

    def get(self, key: str) -> Any | None:
        """Return cached value or ``None`` if missing / expired."""
        return self._cache.get(key)

    def set(self, key: str, value: Any) -> None:
        """Store *value* under *key*."""
        self._cache[key] = value

    def invalidate_if_stale(self, newer_than: float):
        """Clear all entries if ingestion completed after our last check."""
        if newer_than > self._last_ingestion_ts:
            self._cache.clear()
            self._last_ingestion_ts = newer_than
            logger.info("Cache cleared: new ingestion detected")

    def clear(self):
        """Remove all cached entries."""
        self._cache.clear()
        self._last_ingestion_ts = 0.0


# Singleton instance used by the API layer.
explore_cache = ExploreCache()
