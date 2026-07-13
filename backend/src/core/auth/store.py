"""
H1 — Operator credential store.

At H1, operators are seeded from the central configuration (AOS_OPERATOR_*
environment variables, accessed via src.config) rather than a database.
The store is a module-level in-memory dict built once at import time.

Configuration
-------------
All operator seed values are read through get_settings() from src.config:
    AOS_OPERATOR_USERNAME      (default: "admin")
    AOS_OPERATOR_PASSWORD      (required — no seed if absent)
    AOS_OPERATOR_ROLE          (default: "admin")
    AOS_OPERATOR_PRODUCT_SCOPE (optional — None means unrestricted)
    AOS_OPERATOR_STREAM_SCOPE  (optional — None means unrestricted)

P2 note
-------
This module no longer reads os.environ directly.  All configuration is
accessed through get_settings() from src.config.

H2 note
-------
This module will be replaced by a SQLAlchemy-backed OperatorRepository
without changing the interface consumed by the auth dependency.
"""

from __future__ import annotations

import uuid

from src.core.auth.models import OperatorRecord, OperatorRole
from src.core.auth.password import hash_password, verify_password

# Module-level store: username → OperatorRecord
_STORE: dict[str, OperatorRecord] = {}


def _seed_from_env() -> None:
    """Seed the store from the central config.  Called once at import time."""
    from src.config import get_settings
    cfg = get_settings().operator

    if not cfg.password:
        # Not fatal at import time — the /auth/login endpoint will return 401
        # if no operators are configured.  validate_settings() in create_app()
        # catches this for production deployments.
        return

    try:
        role = OperatorRole(cfg.role)
    except ValueError:
        role = OperatorRole.ADMIN

    record = OperatorRecord(
        id=str(uuid.uuid4()),
        username=cfg.username,
        hashed_password=hash_password(cfg.password),
        role=role,
        product_scope=cfg.product_scope,
        stream_scope=cfg.stream_scope,
    )
    _STORE[cfg.username] = record


_seed_from_env()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register_operator(record: OperatorRecord) -> None:
    """Add or replace an operator record.  Used in tests and H2 migrations."""
    _STORE[record.username] = record


def get_by_username(username: str) -> OperatorRecord | None:
    """Return the OperatorRecord for *username*, or None if not found."""
    return _STORE.get(username)


def authenticate(username: str, password: str) -> OperatorRecord | None:
    """
    Verify *username* / *password* and return the matching OperatorRecord.

    Returns None on any failure (user not found, wrong password).
    Never raises — callers translate None to a 401 response.
    """
    record = get_by_username(username)
    if record is None:
        return None
    if not verify_password(password, record.hashed_password):
        return None
    return record


def clear_store() -> None:
    """Clear all operators.  Test-only — allows isolated test fixtures."""
    _STORE.clear()
