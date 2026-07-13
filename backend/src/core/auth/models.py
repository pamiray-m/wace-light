"""
H1 — Operator Identity Model.

Defines the canonical in-memory representation of an authenticated operator.
No ORM model is needed at H1 scope: operators are loaded from configuration
(environment) rather than a database, keeping the hardening surface minimal.

Design decisions
----------------
- OperatorRole is a string enum so it travels cleanly through JWT claims
  without requiring a separate deserialization step.
- product_scope / stream_scope are optional; None means "no restriction"
  (global operator).  Authorization logic enforcing those scopes is H2 territory.
- hashed_password is stored on OperatorRecord (the "persistence" shape) and
  never surfaces on OperatorIdentity (the "session" shape returned to routes).
  This hard split ensures passwords cannot leak through response serialization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Role enum
# ---------------------------------------------------------------------------

class OperatorRole(str, Enum):
    """
    Operator privilege levels.

    ADMIN   — full read/write access to all console operations.
    VIEWER  — read-only; may not issue control actions (Pause, Shutdown, Prompt).
    AUDITOR — read-only, focused on observability surfaces (events, tasks, risks).
    """
    ADMIN   = "admin"
    VIEWER  = "viewer"
    AUDITOR = "auditor"


# ---------------------------------------------------------------------------
# Persistence record (credential store shape)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OperatorRecord:
    """
    Full credential record for an operator.

    Stored in the operator store (environment-seeded at H1).
    hashed_password is produced by the password module — plain text is
    never persisted here.

    Assumptions (H1)
    ----------------
    Operators are seeded via environment variables.  A proper database-backed
    operator table with migration history is an H2+ concern.
    """
    id: str
    username: str
    hashed_password: str
    role: OperatorRole
    product_scope: str | None = field(default=None)
    stream_scope: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Session identity (what get_current_identity() returns to routes)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OperatorIdentity:
    """
    Cryptographically verified operator identity extracted from a JWT.

    Routes receive this object via Depends(get_current_identity).
    It intentionally omits hashed_password — the credential is verified once
    at login and then represented only by the signed token.

    P5: session_id carries the "sid" JWT claim so that get_current_identity()
    can look up the session record and enforce revocation per-request.
    Defaults to None for backward compatibility with tokens issued before P5.
    """
    operator_id: str
    username: str
    role: OperatorRole
    product_scope: str | None
    stream_scope: str | None
    session_id: str | None = field(default=None)
