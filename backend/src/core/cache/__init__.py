"""
W5.3 — Cache abstraction.

Public API:
    from src.core.cache import get_cache, cached_json
    cache = get_cache()
    cache.set("k", value, ttl_seconds=60)
    cache.get("k")            # returns None on miss / expiry

`get_cache()` resolves to:
  - RedisCache when `AOS_CACHE_BACKEND=redis` (or `AOS_REDIS_URL` is set) and
    the `redis` package is importable + reachable.
  - InMemoryCache otherwise (default — no infra needed for tests/dev).

All ops increment `aos_cache_ops_total{op, status, backend}` so /metrics
shows hit ratios. Cache writes serialise JSON-safe values (dict/list/str/
int/float/bool/None) so the Redis path is symmetric with the memory one.
"""
from src.core.cache.backend import (
    CacheBackend,
    InMemoryCache,
    cache_ops_total,
    get_cache,
    reset_cache_for_tests,
)

__all__ = [
    "CacheBackend",
    "InMemoryCache",
    "cache_ops_total",
    "get_cache",
    "reset_cache_for_tests",
]
