"""
Ops-1 — Readiness service and component checks.

Design intent
-------------
/ready is a *readiness* probe: it checks whether this node can safely receive
traffic by actively probing each critical dependency.  A single critical
failure flips overall_status to "unavailable" and the HTTP response to 503,
signalling load balancers to stop routing traffic.

Check isolation
---------------
Each check function catches all exceptions internally.  A buggy or crashing
check never propagates an unhandled exception to the caller — it returns a
ComponentStatus with status="unavailable".  This means /ready always returns
a structured response regardless of what individual checks do.

Criticality model
-----------------
  critical=True  : failure → overall "unavailable" → HTTP 503
  critical=False : failure → individual status shows degraded/unavailable,
                   but overall may still be "ready" if all critical deps pass.

Secret safety
-------------
No check emits raw connection strings, API keys, vault keys, or passwords
in any message field.  Only exception class names and human-readable
diagnostics are surfaced.

Structured logging
------------------
Each failed check logs at WARNING level with a structured message so that
log-aggregation systems can alert on readiness transitions.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class ComponentStatus:
    """
    Result of a single dependency probe.

    Fields
    ------
    name        : Stable identifier (e.g. "database", "vault").
    status      : "ok" | "degraded" | "unavailable"
    critical    : If True, this component's failure makes the node unready.
    message     : Human-readable detail — no secrets allowed here.
    latency_ms  : Round-trip latency for I/O-bound checks; None for instant checks.
    """
    name: str
    status: str           # "ok" | "degraded" | "unavailable"
    critical: bool
    message: str
    latency_ms: float | None = None


@dataclass
class ReadinessReport:
    """
    Aggregated readiness result for the /ready endpoint.

    Fields
    ------
    overall_status : "ready" | "degraded" | "unavailable"
    ready          : True iff overall_status is "ready" or "degraded"
                     (i.e. no critical failure).  Kept for backward compat.
    timestamp      : ISO 8601 UTC timestamp of the probe run.
    components     : Per-component results in probe order.
    """
    overall_status: str
    ready: bool
    timestamp: str
    components: list[ComponentStatus] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------
# Convention: each function returns a ComponentStatus and never raises.
# Callers should treat the returned status as the sole signal of health.

def _ms(start: float) -> float:
    """Compute elapsed milliseconds since *start* (monotonic)."""
    return round((time.monotonic() - start) * 1000, 2)


def check_database() -> ComponentStatus:
    """
    Execute a trivial SELECT 1 to confirm the DB connection is alive.

    Critical — the AOS registry is the authoritative source of truth.
    A dead DB means no reliable state can be served.
    """
    t = time.monotonic()
    try:
        import sqlalchemy
        from src.core.registry.database import get_session
        session = get_session()
        try:
            session.execute(sqlalchemy.text("SELECT 1"))
            return ComponentStatus(
                name="database", status="ok", critical=True,
                message="connected", latency_ms=_ms(t),
            )
        finally:
            session.close()
    except Exception as exc:
        _log.warning("readiness check FAILED [database]: %s", type(exc).__name__,
                     extra={"check": "database", "exc_type": type(exc).__name__})
        return ComponentStatus(
            name="database", status="unavailable", critical=True,
            message=f"unreachable: {type(exc).__name__}", latency_ms=_ms(t),
        )


def check_config() -> ComponentStatus:
    """
    Verify that required AOS_JWT_SECRET is present and long enough.

    Critical — without a valid signing secret, no tokens can be issued or
    verified, making the auth subsystem non-functional.
    """
    try:
        from src.config import get_settings
        cfg = get_settings().auth
        if not cfg.jwt_secret:
            _log.warning("readiness check FAILED [config]: AOS_JWT_SECRET not set",
                         extra={"check": "config"})
            return ComponentStatus(
                name="config", status="unavailable", critical=True,
                message="AOS_JWT_SECRET not set",
            )
        if len(cfg.jwt_secret) < 32:
            _log.warning("readiness check FAILED [config]: AOS_JWT_SECRET too short",
                         extra={"check": "config"})
            return ComponentStatus(
                name="config", status="unavailable", critical=True,
                message="AOS_JWT_SECRET too short (minimum 32 characters)",
            )
        return ComponentStatus(
            name="config", status="ok", critical=True,
            message="required vars present",
        )
    except Exception as exc:
        _log.warning("readiness check FAILED [config]: %s", type(exc).__name__,
                     extra={"check": "config", "exc_type": type(exc).__name__})
        return ComponentStatus(
            name="config", status="unavailable", critical=True,
            message=f"config error: {type(exc).__name__}",
        )


def check_vault() -> ComponentStatus:
    """
    Verify AOS_VAULT_KEY format if configured.

    Non-critical — the vault is optional.  If it is not configured, the
    credential encryption subsystem is simply unavailable, but core AOS
    routing and registry functions remain operational.

    If configured, the key must decode to exactly 32 bytes (AES-256).
    The raw key value is never included in any message field.
    """
    try:
        import base64
        from src.config import get_settings
        vault_key = get_settings().vault.vault_key
        if not vault_key:
            return ComponentStatus(
                name="vault", status="ok", critical=False,
                message="not configured (optional)",
            )
        decoded = base64.b64decode(vault_key)
        if len(decoded) != 32:
            _log.warning(
                "readiness check FAILED [vault]: key length %d (expected 32)",
                len(decoded), extra={"check": "vault"},
            )
            return ComponentStatus(
                name="vault", status="unavailable", critical=False,
                message=f"key decodes to {len(decoded)} bytes (expected 32)",
            )
        return ComponentStatus(
            name="vault", status="ok", critical=False,
            message="key configured and valid",
        )
    except Exception as exc:
        _log.warning("readiness check FAILED [vault]: %s", type(exc).__name__,
                     extra={"check": "vault", "exc_type": type(exc).__name__})
        return ComponentStatus(
            name="vault", status="unavailable", critical=False,
            message=f"invalid key: {type(exc).__name__}",
        )


def check_auth_subsystem() -> ComponentStatus:
    """
    Verify the operators table is queryable.

    Critical — without a functional auth subsystem, no authenticated requests
    can be served.  This check goes one layer above the raw DB check to
    confirm that the ORM mapping and schema are consistent.
    """
    t = time.monotonic()
    try:
        from src.core.auth.operator_model import OperatorModel
        from src.core.registry.database import get_session
        session = get_session()
        try:
            session.query(OperatorModel).limit(0).all()
            return ComponentStatus(
                name="auth", status="ok", critical=True,
                message="operators table accessible", latency_ms=_ms(t),
            )
        finally:
            session.close()
    except Exception as exc:
        _log.warning("readiness check FAILED [auth]: %s", type(exc).__name__,
                     extra={"check": "auth", "exc_type": type(exc).__name__})
        return ComponentStatus(
            name="auth", status="unavailable", critical=True,
            message=f"operators table error: {type(exc).__name__}", latency_ms=_ms(t),
        )


def check_session_subsystem() -> ComponentStatus:
    """
    Verify the operator_sessions table is queryable.

    Critical — session-bound tokens (P5) require this table on every
    authenticated request.  An inaccessible sessions table means all P5
    token enforcement fails.
    """
    t = time.monotonic()
    try:
        from src.core.auth.session_model import SessionModel
        from src.core.registry.database import get_session
        session = get_session()
        try:
            session.query(SessionModel).limit(0).all()
            return ComponentStatus(
                name="sessions", status="ok", critical=True,
                message="sessions table accessible", latency_ms=_ms(t),
            )
        finally:
            session.close()
    except Exception as exc:
        _log.warning("readiness check FAILED [sessions]: %s", type(exc).__name__,
                     extra={"check": "sessions", "exc_type": type(exc).__name__})
        return ComponentStatus(
            name="sessions", status="unavailable", critical=True,
            message=f"sessions table error: {type(exc).__name__}", latency_ms=_ms(t),
        )


def check_openclaw() -> ComponentStatus:
    """
    Ping the OpenClaw runtime if configured.

    Non-critical — OpenClaw is a supplemental runtime.  Its absence or
    unavailability degrades functionality (runtime dispatch fails) but the
    AOS control plane, registry, and auth subsystems remain functional.

    If OPENCLAW_ENABLED is false (default), the check reports "not configured"
    without making any network calls.
    """
    try:
        from src.config import get_settings
        cfg = get_settings().openclaw
        if not cfg.enabled:
            return ComponentStatus(
                name="openclaw", status="ok", critical=False,
                message="not configured (optional)",
            )
        # OpenClaw is configured — try to ping.  Import the client boundary only
        # when OpenClaw is enabled to avoid unnecessary import overhead.
        from src.adapters.runtime.openclaw_client import OpenClawClient
        t = time.monotonic()
        client = OpenClawClient(
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            timeout_secs=cfg.timeout_secs,
        )
        reachable = client.ping()
        lat = _ms(t)
        if reachable:
            return ComponentStatus(
                name="openclaw", status="ok", critical=False,
                message="ping successful", latency_ms=lat,
            )
        _log.warning("readiness check DEGRADED [openclaw]: ping returned false",
                     extra={"check": "openclaw"})
        return ComponentStatus(
            name="openclaw", status="degraded", critical=False,
            message="ping returned false", latency_ms=lat,
        )
    except Exception as exc:
        _log.warning("readiness check FAILED [openclaw]: %s", type(exc).__name__,
                     extra={"check": "openclaw", "exc_type": type(exc).__name__})
        return ComponentStatus(
            name="openclaw", status="degraded", critical=False,
            message=f"unreachable: {type(exc).__name__}",
        )


def check_integration_governance() -> ComponentStatus:
    """
    Verify the integration-governance tables are queryable.

    Non-critical — integration governance is a feature-level concern.
    Core agent routing and auth remain functional even if integration tables
    are inaccessible.
    """
    t = time.monotonic()
    try:
        from src.core.integrations.models import ToolDefinitionRecord
        from src.core.registry.database import get_session
        session = get_session()
        try:
            session.query(ToolDefinitionRecord).limit(0).all()
            return ComponentStatus(
                name="integrations", status="ok", critical=False,
                message="integrations table accessible", latency_ms=_ms(t),
            )
        finally:
            session.close()
    except Exception as exc:
        _log.warning("readiness check FAILED [integrations]: %s", type(exc).__name__,
                     extra={"check": "integrations", "exc_type": type(exc).__name__})
        return ComponentStatus(
            name="integrations", status="degraded", critical=False,
            message=f"integrations table error: {type(exc).__name__}", latency_ms=_ms(t),
        )


# ---------------------------------------------------------------------------
# Readiness service
# ---------------------------------------------------------------------------

#: Default ordered check pipeline.  Tests may supply a subset or override.
_DEFAULT_CHECKS = [
    check_database,
    check_config,
    check_vault,
    check_auth_subsystem,
    check_session_subsystem,
    check_openclaw,
    check_integration_governance,
]


class ReadinessService:
    """
    Aggregates component checks into a single ReadinessReport.

    Parameters
    ----------
    checks : Ordered list of zero-argument callables that return ComponentStatus.
             Defaults to the standard AOS check pipeline.
             Tests pass a subset to exercise specific scenarios in isolation.

    Overall status rules
    --------------------
    - "unavailable" if any critical component is not "ok".
    - "degraded"    if all critical components are "ok" but at least one
                    non-critical component is not "ok".
    - "ready"       if every component is "ok".

    HTTP surface
    ------------
    The route translates "unavailable" → 503; "ready"/"degraded" → 200.
    This means a degraded (non-critical failure only) node still receives
    traffic — it can serve requests, just with reduced functionality.
    Operators are alerted via the structured component list.
    """

    def __init__(self, checks=None) -> None:
        self._checks = checks if checks is not None else _DEFAULT_CHECKS

    def run(self) -> ReadinessReport:
        """
        Execute all registered checks and return an aggregated ReadinessReport.

        Exceptions from individual checks are already caught inside each
        check function.  This method itself will not raise.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        components: list[ComponentStatus] = []

        for check_fn in self._checks:
            try:
                result = check_fn()
            except Exception as exc:
                # Belt-and-suspenders: check functions should catch internally,
                # but if one escapes we still produce a structured failure.
                name = getattr(check_fn, "__name__", "unknown").removeprefix("check_")
                _log.error(
                    "readiness check raised unexpectedly [%s]: %s",
                    name, type(exc).__name__,
                    extra={"check": name, "exc_type": type(exc).__name__},
                )
                result = ComponentStatus(
                    name=name, status="unavailable", critical=True,
                    message=f"check raised unexpectedly: {type(exc).__name__}",
                )
            components.append(result)

        # Derive overall status from component results.
        critical_failure = any(
            c.status != "ok" for c in components if c.critical
        )
        any_degraded = any(
            c.status != "ok" for c in components
        )

        if critical_failure:
            overall = "unavailable"
        elif any_degraded:
            overall = "degraded"
        else:
            overall = "ready"

        ready = not critical_failure

        if not ready:
            _log.warning(
                "readiness probe: UNAVAILABLE — critical component(s) failed: %s",
                [c.name for c in components if c.critical and c.status != "ok"],
                extra={"overall_status": overall},
            )
        elif any_degraded:
            _log.info(
                "readiness probe: DEGRADED — non-critical component(s) failed: %s",
                [c.name for c in components if not c.critical and c.status != "ok"],
                extra={"overall_status": overall},
            )

        return ReadinessReport(
            overall_status=overall,
            ready=ready,
            timestamp=timestamp,
            components=components,
        )
