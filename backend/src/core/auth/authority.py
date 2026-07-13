"""
H2 — Operator-to-Authority mapping.

This is the single authoritative mapping from OperatorRole to the mAIb State
Machine's Authority enum.  It is computed server-side from the verified JWT
identity and is never controllable by the client.

Design rules
------------
- The mapping is explicit and centralized here; no route may inline role checks.
- Only OperatorRole.ADMIN carries transition authority (Authority.ARCHITECT).
- VIEWER and AUDITOR roles are read-only; they hold no state-machine authority.
- If a role has no transition authority, resolve_authority() raises PolicyViolation
  so the caller's 403 path is exercised before any service call.

H3 note: this mapping may be extended with a more granular authority matrix
(e.g., CEO authority for a specific ADMIN sub-role) — the interface is stable.
"""

from __future__ import annotations

from src.core.auth.models import OperatorIdentity, OperatorRole
from src.core.state.enums import Authority


# ---------------------------------------------------------------------------
# Explicit role → authority table
# ---------------------------------------------------------------------------

_ROLE_AUTHORITY: dict[OperatorRole, Authority | None] = {
    OperatorRole.ADMIN:   Authority.ARCHITECT,   # full lifecycle control
    OperatorRole.VIEWER:  None,                  # read-only — no transition rights
    OperatorRole.AUDITOR: None,                  # read-only — observability only
}


def role_authority(role: OperatorRole) -> Authority | None:
    """
    Return the State Machine Authority for the given operator role.

    Returns None if the role carries no transition rights.
    """
    return _ROLE_AUTHORITY.get(role)


def resolve_authority(identity: OperatorIdentity) -> Authority:
    """
    Resolve the transition Authority from a verified OperatorIdentity.

    Raises
    ------
    PolicyViolation — if the operator's role carries no transition authority.
                      Callers should convert this to HTTP 403.
    """
    # Import here to avoid circular import (policy imports authority)
    from src.core.auth.policy import PolicyViolation

    auth = role_authority(identity.role)
    if auth is None:
        raise PolicyViolation(
            f"Operator role '{identity.role.value}' has no transition authority. "
            "Only ADMIN operators may issue state-change commands."
        )
    return auth


def actor_label(identity: OperatorIdentity) -> str:
    """
    Derive a canonical actor string from verified identity.

    This is stored in transition event records as the actor field.
    It is always server-derived — client-supplied 'actor' fields are ignored.
    """
    return f"operator:{identity.username}"
