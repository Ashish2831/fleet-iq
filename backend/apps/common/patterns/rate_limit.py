"""Rate-limit store strategies — memory vs Django cache (Redis in prod)."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from threading import Lock


class RateLimitStore(ABC):
    @abstractmethod
    def incr(self, key: str, window_seconds: int) -> int:
        """Increment counter in window; return current count."""


class MemoryRateLimitStore(RateLimitStore):
    def __init__(self):
        self._buckets: dict[str, tuple[float, int]] = {}
        self._lock = Lock()

    def incr(self, key: str, window_seconds: int) -> int:
        now = time.monotonic()
        with self._lock:
            starts, count = self._buckets.get(key, (now, 0))
            if now - starts >= window_seconds:
                starts, count = now, 0
            count += 1
            self._buckets[key] = (starts, count)
            return count


class CacheRateLimitStore(RateLimitStore):
    """Uses Django CACHES (Redis in deployed roles)."""

    def incr(self, key: str, window_seconds: int) -> int:
        from django.core.cache import cache

        cache_key = f"rl:{key}"
        # add() only succeeds on first create in the window
        if cache.add(cache_key, 1, timeout=window_seconds):
            return 1
        try:
            return int(cache.incr(cache_key))
        except ValueError:
            cache.set(cache_key, 1, timeout=window_seconds)
            return 1


class RedisRateLimitStore(RateLimitStore):
    """Direct Redis (tracking live state client) for sub-second GPS windows."""

    def incr(self, key: str, window_seconds: int) -> int:
        from apps.tracking.redis_state import get_redis

        r = get_redis()
        cache_key = f"rl:{key}"
        n = int(r.incr(cache_key))
        if n == 1:
            r.expire(cache_key, max(1, int(window_seconds)))
        return n


def allow_request(store: RateLimitStore, key: str, *, limit: int, window_seconds: int) -> bool:
    return store.incr(key, window_seconds) <= limit
