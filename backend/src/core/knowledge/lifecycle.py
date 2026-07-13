"""
SkillLifecycleEngine — governed transition rules for skill package status.

Policy matrix
-------------
Every (from_status, to_status) pair maps to the frozenset of SkillAuthority
values that may authorize the transition.  Any attempt using an authority
not in the set raises UnauthorizedSkillWrite.  Any attempt at an undefined
pair raises InvalidSkillTransition.

Oracle restraint (Packet 8 / architecture doc §3):
  Oracle may PROPOSE a skill (DRAFT → PROPOSED) but cannot progress it
  beyond PROPOSED.  Validation, approval, and deployment require Layer 0
  or Layer 1 governance authorities above Oracle.

Deprecation gate:
  DEPRECATED is a terminal status.  No transitions out of DEPRECATED
  are defined.  Attempting any transition from DEPRECATED raises
  TerminalSkillError.
"""

from __future__ import annotations

from src.core.knowledge.enums import SkillAuthority, SkillStatus
from src.core.knowledge.exceptions import (
    InvalidSkillTransition,
    TerminalSkillError,
    UnauthorizedSkillWrite,
)

# Alias for readability
_A = SkillAuthority
_S = SkillStatus

# ---------------------------------------------------------------------------
# Transition policy matrix
# ---------------------------------------------------------------------------

# Authorities with full governance power (Layer 0)
_SOVEREIGNTY = frozenset({_A.ARCHITECT, _A.DEPUTY})

# Authorities that may perform standards-level validation
_VALIDATORS = frozenset({
    _A.ARCHITECT, _A.DEPUTY,
    _A.KNOWLEDGE_DIRECTOR,
    _A.STANDARDS_AGENT,
    _A.LAWYER,
})

# Authorities that may approve and deploy
_GOVERNORS = frozenset({_A.ARCHITECT, _A.DEPUTY, _A.KNOWLEDGE_DIRECTOR})

# Authorities that may approve (add Lawyer for compliance clearance gate per blueprint §4 Flow A step 5)
_APPROVERS = frozenset({_A.ARCHITECT, _A.DEPUTY, _A.KNOWLEDGE_DIRECTOR, _A.LAWYER})

# All authorities that may propose (everyone above system level incl. Oracle)
_PROPOSERS = frozenset({
    _A.ARCHITECT, _A.DEPUTY,
    _A.KNOWLEDGE_DIRECTOR, _A.STANDARDS_AGENT, _A.ORACLE, _A.LAWYER,
    _A.SYSTEM,
})

TRANSITION_RULES: dict[tuple[SkillStatus, SkillStatus], frozenset[SkillAuthority]] = {
    # Normal promotion path
    (_S.DRAFT,       _S.PROPOSED):    _PROPOSERS,       # anyone can submit for review
    (_S.PROPOSED,    _S.VALIDATED):   _VALIDATORS,      # validation gate (no Oracle)
    (_S.VALIDATED,   _S.APPROVED):    _APPROVERS,       # approval gate (Lawyer + governors)
    (_S.APPROVED,    _S.DEPLOYED):    _GOVERNORS,       # deployment gate
    (_S.DEPLOYED,    _S.DEPRECATED):  _GOVERNORS,       # sunset a live skill

    # Rejection path — send PROPOSED back to DRAFT for rework
    (_S.PROPOSED,    _S.DRAFT):       _VALIDATORS,

    # Approved skill rejected before deployment
    (_S.APPROVED,    _S.DRAFT):       _GOVERNORS,

    # Validated skill needs rework before approval
    (_S.VALIDATED,   _S.DRAFT):       _GOVERNORS,

    # Force-deprecate from any non-deployed state (Layer 0 only)
    (_S.DRAFT,       _S.DEPRECATED):  _SOVEREIGNTY,
    (_S.PROPOSED,    _S.DEPRECATED):  _SOVEREIGNTY,
    (_S.VALIDATED,   _S.DEPRECATED):  _SOVEREIGNTY,
    (_S.APPROVED,    _S.DEPRECATED):  _SOVEREIGNTY,
}

TERMINAL_STATUSES = frozenset({_S.DEPRECATED})


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class SkillLifecycleEngine:
    """
    Stateless policy enforcer for skill status transitions.

    Usage
    -----
        engine = SkillLifecycleEngine()
        engine.validate_transition(current_status, target_status, authority)
        # raises if invalid; returns None on success
    """

    def validate_transition(
        self,
        current_status: SkillStatus,
        target_status:  SkillStatus,
        authority:      SkillAuthority,
    ) -> None:
        """
        Assert the requested transition is permitted.

        Raises
        ------
        TerminalSkillError      : current_status is DEPRECATED (no exit).
        InvalidSkillTransition  : (current, target) pair not in policy matrix.
        UnauthorizedSkillWrite  : authority not permitted for this pair.
        """
        if current_status in TERMINAL_STATUSES:
            raise TerminalSkillError(
                f"Skill is in terminal status {current_status.value}. "
                "No further transitions are permitted."
            )

        key = (current_status, target_status)
        if key not in TRANSITION_RULES:
            raise InvalidSkillTransition(
                f"Transition {current_status.value} → {target_status.value} "
                "is not defined in the skill lifecycle policy."
            )

        allowed = TRANSITION_RULES[key]
        if authority not in allowed:
            raise UnauthorizedSkillWrite(
                f"Authority '{authority.value}' is not permitted to transition "
                f"a skill from {current_status.value} → {target_status.value}. "
                f"Permitted: {[a.value for a in sorted(allowed, key=lambda x: x.value)]}."
            )

    def allowed_transitions(self, current_status: SkillStatus) -> list[SkillStatus]:
        """Return all reachable target statuses from the current status."""
        if current_status in TERMINAL_STATUSES:
            return []
        return [target for (src, target) in TRANSITION_RULES if src == current_status]

    def is_terminal(self, status: SkillStatus) -> bool:
        return status in TERMINAL_STATUSES
