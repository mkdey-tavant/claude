"""A tiny thread-safe TTL cache wrapper.

yfinance calls are slow and rate-limited, so we memoise both raw frames and derived
analysis for a short window. The cache is process-local and intentionally simple.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, TypeVar

from cachetools import TTLCache

from .config import get_settings

T = TypeVar("T")

_settings = get_settings()
_cache: TTLCache = TTLCache(maxsize=_settings.cache_maxsize, ttl=_settings.cache_ttl_seconds)
_lock = threading.RLock()


def get_or_set(key: str, producer: Callable[[], T]) -> T:
    """Return the cached value for ``key`` or compute, store, and return it.

    ``producer`` is only invoked on a miss and is called while holding the lock, so
    concurrent requests for the same key will not stampede the provider.
    """
    with _lock:
        if key in _cache:
            return _cache[key]
        value = producer()
        _cache[key] = value
        return value


def invalidate(key: str | None = None) -> None:
    """Drop a single key, or clear the whole cache when ``key`` is ``None``."""
    with _lock:
        if key is None:
            _cache.clear()
        else:
            _cache.pop(key, None)


def stats() -> dict[str, Any]:
    with _lock:
        return {"size": len(_cache), "maxsize": _cache.maxsize, "ttl": _cache.ttl}
