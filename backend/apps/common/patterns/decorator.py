"""Decorator pattern — wrap callables with extra behavior."""

from __future__ import annotations

import time
from functools import wraps
from typing import Callable, TypeVar

T = TypeVar("T")


def with_ttl_cache(ttl_seconds: float = 30.0):
    """Memoize a function result for ttl_seconds (process-local)."""

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        bucket: dict[str, tuple[float, T]] = {}

        @wraps(fn)
        def wrapped(*args, **kwargs) -> T:
            key = repr((args, tuple(sorted(kwargs.items()))))
            now = time.monotonic()
            hit = bucket.get(key)
            if hit and hit[0] > now:
                return hit[1]
            value = fn(*args, **kwargs)
            bucket[key] = (now + ttl_seconds, value)
            return value

        wrapped.cache_clear = bucket.clear  # type: ignore[attr-defined]
        return wrapped

    return decorator
