"""
Ops-2 — In-process operational metrics counters.

Provides lightweight thread-safe counters for key operational events.
These are NOT a replacement for a full metrics system (Prometheus etc.) —
they are coarse-grained signals usable for:
  - Health/readiness diagnostics
  - Alerting thresholds in simple deployments
  - Test assertions

Counter semantics
-----------------
Each counter is process-local and resets on restart.  They are incremented
by the code paths that own the events:

  login_attempts        — incremented by token_manager.issue()
  login_failures        — incremented by auth route on credential rejection
  policy_denials        — incremented by policy engine on PolicyViolation
  session_revocations   — incremented by token_manager._revoke_session()

Usage
-----
    from src.core.logging.metrics import login_attempts, login_failures
    login_attempts.increment()

Reading / resetting (e.g. for test isolation)
----------------------------------------------
    count = login_failures.value       # read without resetting
    count = login_failures.reset()     # read and reset to 0
"""

from __future__ import annotations

import threading


class _Counter:
    """
    Thread-safe integer counter.

    Attributes
    ----------
    name  : Human-readable label (for logging / debugging).
    value : Current count (property, thread-safe read).
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._lock = threading.Lock()
        self._value = 0

    @property
    def value(self) -> int:
        with self._lock:
            return self._value

    def increment(self, by: int = 1) -> None:
        """Atomically add *by* to the counter."""
        with self._lock:
            self._value += by

    def reset(self) -> int:
        """Atomically read the current value and reset to zero."""
        with self._lock:
            v = self._value
            self._value = 0
            return v


# ---------------------------------------------------------------------------
# Module-level singletons — import and use directly
# ---------------------------------------------------------------------------

login_attempts: _Counter = _Counter("login_attempts_total")
"""Incremented on every login attempt (success or failure)."""

login_failures: _Counter = _Counter("login_failures_total")
"""Incremented when a login attempt fails (bad credentials or disabled account)."""

policy_denials: _Counter = _Counter("policy_denials_total")
"""Incremented each time the policy engine denies an action."""

session_revocations: _Counter = _Counter("session_revocations_total")
"""Incremented each time a session is actively revoked (logout, disable, password reset)."""
