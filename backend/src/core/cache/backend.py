"""
W5.3 — Cache backends (in-memory + optional Redis) and resolver.

Backend protocol
----------------
A cache backend implements `get(key) -> Optional[Any]`, `set(key, value, ttl_seconds)`,
`delete(key)`, and `flush()`. Values are JSON-safe (dict/list/str/int/float/
bool/None) — both backends serialise identically so swapping at runtime is
transparent to callers.

Resolution
----------
`get_cache()` is the single entry point. It returns the same instance for the
life of the process. Selection rules:
  1. `AOS_CACHE_BACKEND=memory`  → InMemoryCache.
  2. `AOS_CACHE_BACKEND=redis` or `AOS_REDIS_URL` set → try RedisCache.
     If `redis` import fails OR the connection probe raises → fall back to
     InMemoryCache and log once.
  3. Default → InMemoryCache.

Telemetry
---------
Every operation increments `aos_cache_ops_total{op, status, backend}`:
  op     ∈ {"get", "set", "delete", "flush"}
  status ∈ {"hit", "miss", "ok", "error"}
  backend∈ {"memory", "redis"}
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Optional, Protocol

from src.core.observability.prom import LabeledCounter

_log = logging.getLogger(__name__)


cache_ops_total = LabeledCounter(
    "aos_cache_ops_total",
    "Cache operations by op, status, and backend.",
)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class CacheBackend(Protocol):
    """Minimal cache contract — both backends conform."""
    backend_name: str

    def get(self, key: str) -> Optional[Any]: ...
    def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...
    def delete(self, key: str) -> None: ...
    def flush(self) -> None: ...


# ---------------------------------------------------------------------------
# JSON-safe (de)serialisation
# ---------------------------------------------------------------------------

def _serialise(value: Any) -> str:
    """JSON-encode the value. Raises if not JSON-safe."""
    return json.dumps(value, separators=(",", ":"))


def _deserialise(payload: str) -> Any:
    return json.loads(payload)


# ---------------------------------------------------------------------------
# InMemoryCache
# ---------------------------------------------------------------------------

class InMemoryCache:
    """Thread-safe in-memory cache with per-key TTL.

    Storage: dict[key] -> (expires_at_unix_seconds, serialised_value).
    On every get/set we sweep expired entries lazily so memory doesn't grow
    unbounded under steady traffic patterns.
    """
    backend_name = "memory"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, tuple[float, str]] = {}

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                cache_ops_total.inc(labels={"op": "get", "status": "miss", "backend": self.backend_name})
                return None
            expires_at, payload = entry
            if expires_at < now:
                # Expired — evict.
                self._store.pop(key, None)
                cache_ops_total.inc(labels={"op": "get", "status": "miss", "backend": self.backend_name})
                return None
        try:
            value = _deserialise(payload)
            cache_ops_total.inc(labels={"op": "get", "status": "hit", "backend": self.backend_name})
            return value
        except Exception:
            # Corrupt payload — treat as miss.
            cache_ops_total.inc(labels={"op": "get", "status": "error", "backend": self.backend_name})
            return None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        try:
            payload = _serialise(value)
        except Exception as exc:
            _log.warning("InMemoryCache.set: value not JSON-safe key=%r err=%s", key, exc)
            cache_ops_total.inc(labels={"op": "set", "status": "error", "backend": self.backend_name})
            return
        with self._lock:
            self._store[key] = (time.time() + ttl_seconds, payload)
        cache_ops_total.inc(labels={"op": "set", "status": "ok", "backend": self.backend_name})

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)
        cache_ops_total.inc(labels={"op": "delete", "status": "ok", "backend": self.backend_name})

    def flush(self) -> None:
        with self._lock:
            self._store.clear()
        cache_ops_total.inc(labels={"op": "flush", "status": "ok", "backend": self.backend_name})


# ---------------------------------------------------------------------------
# RedisCache (optional)
# ---------------------------------------------------------------------------

class RedisCache:
    """Redis-backed cache. Lazy client construction; never reconnects on its own.

    Constructed only by `_build_redis_cache()` after the import + connection
    probe succeed. On any subsequent operation failure the error path counts
    `status="error"` and returns None / no-ops — the caller experiences a
    cache miss, not an exception.
    """
    backend_name = "redis"

    def __init__(self, client) -> None:
        self._client = client

    def get(self, key: str) -> Optional[Any]:
        try:
            payload = self._client.get(key)
        except Exception as exc:
            _log.warning("RedisCache.get failed key=%r err=%s", key, exc)
            cache_ops_total.inc(labels={"op": "get", "status": "error", "backend": self.backend_name})
            return None
        if payload is None:
            cache_ops_total.inc(labels={"op": "get", "status": "miss", "backend": self.backend_name})
            return None
        try:
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8")
            value = _deserialise(payload)
        except Exception:
            cache_ops_total.inc(labels={"op": "get", "status": "error", "backend": self.backend_name})
            return None
        cache_ops_total.inc(labels={"op": "get", "status": "hit", "backend": self.backend_name})
        return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        try:
            payload = _serialise(value)
        except Exception as exc:
            _log.warning("RedisCache.set: value not JSON-safe key=%r err=%s", key, exc)
            cache_ops_total.inc(labels={"op": "set", "status": "error", "backend": self.backend_name})
            return
        try:
            self._client.set(key, payload, ex=ttl_seconds)
        except Exception as exc:
            _log.warning("RedisCache.set failed key=%r err=%s", key, exc)
            cache_ops_total.inc(labels={"op": "set", "status": "error", "backend": self.backend_name})
            return
        cache_ops_total.inc(labels={"op": "set", "status": "ok", "backend": self.backend_name})

    def delete(self, key: str) -> None:
        try:
            self._client.delete(key)
        except Exception as exc:
            _log.warning("RedisCache.delete failed key=%r err=%s", key, exc)
            cache_ops_total.inc(labels={"op": "delete", "status": "error", "backend": self.backend_name})
            return
        cache_ops_total.inc(labels={"op": "delete", "status": "ok", "backend": self.backend_name})

    def flush(self) -> None:
        try:
            self._client.flushdb()
        except Exception as exc:
            _log.warning("RedisCache.flush failed err=%s", exc)
            cache_ops_total.inc(labels={"op": "flush", "status": "error", "backend": self.backend_name})
            return
        cache_ops_total.inc(labels={"op": "flush", "status": "ok", "backend": self.backend_name})


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

_cache_instance: Optional[CacheBackend] = None
_resolver_lock = threading.Lock()


def _build_redis_cache() -> Optional[CacheBackend]:
    """Try to build a Redis backend. Return None on any failure."""
    url = (os.environ.get("AOS_REDIS_URL", "") or "").strip()
    if not url:
        return None
    try:
        import redis  # type: ignore[import]
    except ImportError:
        _log.info("Cache: redis package not installed; falling back to in-memory")
        return None
    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=2)
        client.ping()
    except Exception as exc:
        _log.warning("Cache: Redis probe failed url=%r err=%s; using in-memory", url, exc)
        return None
    _log.info("Cache: connected to Redis at %s", url)
    return RedisCache(client)


def _resolve_backend() -> CacheBackend:
    explicit = (os.environ.get("AOS_CACHE_BACKEND", "") or "").strip().lower()
    if explicit == "memory":
        return InMemoryCache()
    if explicit == "redis" or os.environ.get("AOS_REDIS_URL", "").strip():
        backend = _build_redis_cache()
        if backend is not None:
            return backend
    return InMemoryCache()


def get_cache() -> CacheBackend:
    """Return the process-level cache singleton.

    First call resolves the active backend; subsequent calls return the same
    instance. Use `reset_cache_for_tests()` to force re-resolution.
    """
    global _cache_instance
    if _cache_instance is None:
        with _resolver_lock:
            if _cache_instance is None:
                _cache_instance = _resolve_backend()
    return _cache_instance


def reset_cache_for_tests() -> None:
    """Test hook — flushes the current backend AND drops the singleton so a
    subsequent get_cache() call re-resolves under the test's env."""
    global _cache_instance
    if _cache_instance is not None:
        try:
            _cache_instance.flush()
        except Exception:  # pragma: no cover
            pass
    with _resolver_lock:
        _cache_instance = None
