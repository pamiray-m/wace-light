"""
Ops-4 — In-memory rate limiter for AOS API protection.

Design
------
Fixed-window counter per (bucket, key) pair.  The window resets when the
current time exceeds window_start + window_seconds.  Thread-safe via a single
Lock; the critical section is minimal (dict lookup + integer increment).

In-memory storage is appropriate for AOS MVP:
  - The packet explicitly lists "isolated memory arrays" as a valid store.
  - Stateless rate limiting (per-process) is acceptable for single-instance
    deployments; a Redis store would be required for multi-replica.
  - On process restart counters reset — this is acceptable given the short
    window durations (≤ 60 s).

Bucket classes
--------------
Each protected route family maps to a named bucket.  Buckets are independent:
hitting the auth login limit does not affect the control bucket.

  AUTH_LOGIN    POST /auth/login           — tightest limit, brute-force target
  AUTH_REFRESH  POST /auth/refresh         — tight limit, token cycling abuse
  AUTH_LOGOUT   POST /auth/logout          — relaxed, logout must not be blocked
  CONTROL       agent prompt/pause/resume/shutdown  — command spam prevention
  MUTATION      operator mgmt + integrations/skills write paths
  DEFAULT       all other authenticated routes

Rate limit key
--------------
The key is derived from the client IP address.  For auth endpoints, per-IP
is the correct axis — operators don't have a token yet on login.  For control
endpoints, per-IP prevents command spam from a single source regardless of
how many operator accounts exist.

Production note: when AOS is deployed behind a trusted reverse proxy, the
real client IP arrives in X-Real-IP or X-Forwarded-For.  Without proxy
awareness, request.client.host is the proxy IP and rate limiting degrades to
per-proxy limiting.  Set AOS_RATE_LIMIT_TRUSTED_PROXY=true (future packet)
to enable X-Real-IP reading after confirming proxy trust.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bucket names
# ---------------------------------------------------------------------------

BUCKET_AUTH_LOGIN   = "auth_login"
BUCKET_AUTH_REFRESH = "auth_refresh"
BUCKET_AUTH_LOGOUT  = "auth_logout"
BUCKET_CONTROL      = "control"
BUCKET_MUTATION     = "mutation"
BUCKET_STATUS_POLL  = "status_poll"   # mission/job status polling — higher limit
BUCKET_DEFAULT      = "default"


# ---------------------------------------------------------------------------
# Core rate limiter
# ---------------------------------------------------------------------------

@dataclass
class _Window:
    """Mutable sliding-window state for a single (bucket, key) pair."""
    count: int
    window_start: float


class RateLimiter:
    """
    Thread-safe fixed-window rate limiter.

    Each (bucket, key) pair gets an independent counter.  When the current
    time passes window_start + window_seconds, the counter resets and a new
    window begins.

    Parameters
    ----------
    None — the limiter is a clean counter store; limits are injected at
    check() call time so callers (middleware) can drive them from config.
    """

    def __init__(self) -> None:
        # key: "{bucket}:{key}" → _Window
        self._windows: dict[str, _Window] = {}
        self._lock = threading.Lock()

    def check(self, bucket: str, key: str, limit: int, window_seconds: int) -> bool:
        """
        Record a request hit and return whether it is within the allowed rate.

        Parameters
        ----------
        bucket         : Rate limit bucket name (e.g. BUCKET_AUTH_LOGIN).
        key            : Per-caller identifier (typically the client IP).
        limit          : Maximum number of allowed requests per window.
        window_seconds : Duration of each counting window in seconds.

        Returns
        -------
        True if the request is allowed.
        False if the rate limit has been exceeded — caller must return 429.
        """
        if limit <= 0:
            return True  # limit=0 means disabled for this bucket

        slot = f"{bucket}:{key}"
        now = time.monotonic()

        with self._lock:
            win = self._windows.get(slot)
            if win is None or (now - win.window_start) >= window_seconds:
                # First request or new window — reset counter
                self._windows[slot] = _Window(count=1, window_start=now)
                return True

            if win.count >= limit:
                return False  # limit exceeded; window still active

            win.count += 1
            return True

    def reset(self) -> None:
        """
        Clear all counters.

        Call this in tests between test cases to guarantee isolation.
        Not recommended in production; restart process instead.
        """
        with self._lock:
            self._windows.clear()

    def current_count(self, bucket: str, key: str) -> int:
        """Return the current hit count for (bucket, key). Zero if not seen."""
        slot = f"{bucket}:{key}"
        with self._lock:
            win = self._windows.get(slot)
            return win.count if win else 0


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
# Middleware and tests share this instance.  Tests call reset() between cases.

_limiter = RateLimiter()


def get_limiter() -> RateLimiter:
    """Return the process-global RateLimiter singleton."""
    return _limiter


def reset_limiter() -> None:
    """
    Clear all rate-limit counters.

    Call from test fixtures to ensure isolation between test cases.
    """
    _limiter.reset()
