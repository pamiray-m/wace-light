"""
P5 — Dependency Checker.

Probes runtime dependencies to support the /ready endpoint.  Checks are
intentionally lightweight — they verify connectivity, not functional
correctness.

Checks performed
----------------
db       : Execute a trivial SELECT to confirm the DB connection is alive.
config   : Verify required AOS_JWT_SECRET is present (vault key is optional).
vault    : If AOS_VAULT_KEY is configured, validate it is well-formed base64
           decoding to 32 bytes.

Design
------
- Each check returns a DependencyStatus tuple (name, ok, detail).
- check_all() aggregates results; overall readiness is True only when every
  mandatory check passes (db, config).  Vault is optional — its absence
  degrades gracefully (vault operations will fail at use time).
- Exceptions in individual checks are caught and reported as failures so
  a broken dependency never crashes the /ready endpoint itself.
- No secrets are surfaced in detail strings.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DependencyStatus:
    name: str
    ok: bool
    detail: str


def check_db() -> DependencyStatus:
    """Verify the database connection by executing a trivial query."""
    try:
        from src.core.registry.database import get_session
        session = get_session()
        try:
            session.execute(__import__("sqlalchemy").text("SELECT 1"))
            return DependencyStatus(name="db", ok=True, detail="connected")
        finally:
            session.close()
    except Exception as exc:
        return DependencyStatus(name="db", ok=False, detail=f"unreachable: {type(exc).__name__}")


def check_config() -> DependencyStatus:
    """Verify that the required AOS_JWT_SECRET is set and long enough."""
    try:
        from src.config import get_settings
        cfg = get_settings().auth
        if not cfg.jwt_secret:
            return DependencyStatus(name="config", ok=False, detail="AOS_JWT_SECRET not set")
        if len(cfg.jwt_secret) < 32:
            return DependencyStatus(name="config", ok=False, detail="AOS_JWT_SECRET too short")
        return DependencyStatus(name="config", ok=True, detail="required vars present")
    except Exception as exc:
        return DependencyStatus(name="config", ok=False, detail=f"error: {type(exc).__name__}")


def check_vault() -> DependencyStatus:
    """Verify AOS_VAULT_KEY format if configured.  Absence is not a failure."""
    try:
        import base64
        from src.config import get_settings
        vault_key = get_settings().vault.vault_key
        if not vault_key:
            return DependencyStatus(name="vault", ok=True, detail="not configured (optional)")
        decoded = base64.b64decode(vault_key)
        if len(decoded) != 32:
            return DependencyStatus(
                name="vault", ok=False,
                detail=f"AOS_VAULT_KEY decodes to {len(decoded)} bytes (expected 32)"
            )
        return DependencyStatus(name="vault", ok=True, detail="key configured and valid")
    except Exception as exc:
        return DependencyStatus(name="vault", ok=False, detail=f"invalid key: {type(exc).__name__}")


def check_all() -> tuple[bool, list[DependencyStatus]]:
    """
    Run all dependency checks.

    Returns
    -------
    (ready, statuses)
        ready    : True only if db and config checks pass (vault is optional).
        statuses : List of DependencyStatus for all checks.
    """
    statuses = [check_db(), check_config(), check_vault()]
    mandatory_names = {"db", "config"}
    ready = all(s.ok for s in statuses if s.name in mandatory_names)
    return ready, statuses
