"""
Ops-1 — Liveness health service.

Design intent
-------------
/health is a *liveness* probe: it answers whether the process is alive and
its main goroutine/thread is responsive.  It must not depend on any external
system (DB, vault, OpenClaw) because a temporary downstream outage must not
cause the process to be declared dead and restarted by the orchestrator.

The HealthReport is intentionally minimal — no dependency details, no
internal configuration, no latency figures.  Those belong in /ready.
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HealthReport:
    """
    Liveness probe result.

    Fields
    ------
    status  : Always "ok" when the process is alive.
    service : Human-readable service name for log correlation.
    version : Application version string (informational, from package or env).
    """
    status: str
    service: str
    version: str


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

_SERVICE_NAME = "mAIb Control API"
_VERSION = "0.1.0"


class HealthService:
    """
    Returns an instantaneous liveness report.

    No I/O, no exceptions — if this method can be called at all, the process
    is alive.
    """

    def run(self) -> HealthReport:
        """Return a HealthReport indicating the process is alive."""
        return HealthReport(
            status="ok",
            service=_SERVICE_NAME,
            version=_VERSION,
        )
