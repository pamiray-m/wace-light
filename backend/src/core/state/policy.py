"""
Transition policy matrix for the mAIb Agent State Machine.

This module is the single authoritative source for:
  1. Which (from_state, to_state) pairs are structurally allowed.
  2. Which Authority values may assert each allowed transition.

Source of truth: /docs/contracts/agent-state-model.md
Additions beyond the contract are clearly marked with [ASSUMPTION].

Rules
-----
TRANSITION_RULES
    Dict mapping (AgentState, AgentState) → frozenset[Authority].
    A transition NOT in this dict is unconditionally invalid.
    A transition IN this dict is only valid if the requesting authority
    is a member of the frozenset.

SYSTEM_LOCKED_STATES
    States from which System authority is completely blocked, per Packet 3
    constraint: "System authority CANNOT transition out of BLOCKED or PAUSED."

TERMINAL_STATES
    States that have no valid outbound transitions.  Enforced before the
    matrix lookup so terminal checks are always explicit.
"""

from __future__ import annotations

from typing import FrozenSet

from .enums import AgentState, Authority


# ---------------------------------------------------------------------------
# Sentinel sets (re-used across the matrix for readability)
# ---------------------------------------------------------------------------

_HUMAN_OVERRIDE: FrozenSet[Authority] = frozenset({Authority.ARCHITECT, Authority.CEO})
_GOVERNANCE:     FrozenSet[Authority] = frozenset({Authority.LAWYER, Authority.WATCHER})


# ---------------------------------------------------------------------------
# Transition rule matrix
# (from_state, to_state) → frozenset of authorities that may assert it
# ---------------------------------------------------------------------------

TRANSITION_RULES: dict[tuple[AgentState, AgentState], FrozenSet[Authority]] = {

    # -- System authority: operational lifecycle ---------------------------
    # Contract: IDLE ↔ BUSY, BUSY → DEGRADED
    (AgentState.IDLE,         AgentState.BUSY):        frozenset({Authority.SYSTEM}),
    (AgentState.BUSY,         AgentState.IDLE):        frozenset({Authority.SYSTEM}),
    (AgentState.BUSY,         AgentState.DEGRADED):    frozenset({Authority.SYSTEM}),

    # [ASSUMPTION] System brings a newly registered agent online.
    # PROVISIONING → ACTIVE is a system startup event; no human override
    # is defined in the contract for this edge.
    (AgentState.PROVISIONING, AgentState.ACTIVE):      frozenset({Authority.SYSTEM}),

    # -- Governance authority: risk blocks ---------------------------------
    # Contract: IDLE → BLOCKED, BUSY → BLOCKED (Lawyer or Watcher)
    (AgentState.IDLE,         AgentState.BLOCKED):     _GOVERNANCE,
    (AgentState.BUSY,         AgentState.BLOCKED):     _GOVERNANCE,

    # -- Human override authority ------------------------------------------
    # Contract: BLOCKED → IDLE, ACTIVE → PAUSED, PAUSED → IDLE
    (AgentState.BLOCKED,      AgentState.IDLE):        _HUMAN_OVERRIDE,
    (AgentState.ACTIVE,       AgentState.PAUSED):      _HUMAN_OVERRIDE,
    (AgentState.PAUSED,       AgentState.IDLE):        _HUMAN_OVERRIDE,

    # [ASSUMPTION] Recovery from DEGRADED: Watcher alerts, human clears.
    # Contract does not assign this explicitly; minimal assignment is
    # Architect/CEO (human oversight) + Watcher (alerted party).
    (AgentState.DEGRADED,     AgentState.IDLE):        _HUMAN_OVERRIDE | {Authority.WATCHER},

    # -- Permanent termination ---------------------------------------------
    # Contract: System "cannot assert TERMINATED" → human-only authority.
    # [ASSUMPTION] Architect/CEO are the only authorities that may permanently
    # terminate an agent.  Any non-TERMINATED state may be terminated by them.
    (AgentState.ACTIVE,       AgentState.TERMINATED):  _HUMAN_OVERRIDE,
    (AgentState.IDLE,         AgentState.TERMINATED):  _HUMAN_OVERRIDE,
    (AgentState.BUSY,         AgentState.TERMINATED):  _HUMAN_OVERRIDE,
    (AgentState.DEGRADED,     AgentState.TERMINATED):  _HUMAN_OVERRIDE,
    (AgentState.BLOCKED,      AgentState.TERMINATED):  _HUMAN_OVERRIDE,
    (AgentState.PAUSED,       AgentState.TERMINATED):  _HUMAN_OVERRIDE,
    (AgentState.PROVISIONING, AgentState.TERMINATED):  _HUMAN_OVERRIDE,
}


# ---------------------------------------------------------------------------
# Special-case guard sets
# ---------------------------------------------------------------------------

# States from which System authority is unconditionally locked out.
# Packet 3 constraint: "If agent_id's state is currently BLOCKED, the System
# authority CANNOT transition to IDLE."  The contract extends this to PAUSED too.
SYSTEM_LOCKED_STATES: FrozenSet[AgentState] = frozenset({
    AgentState.BLOCKED,
    AgentState.PAUSED,
})

# One-way terminal states — no outbound transitions for any authority.
TERMINAL_STATES: FrozenSet[AgentState] = frozenset({
    AgentState.TERMINATED,
})


# ---------------------------------------------------------------------------
# Policy query helpers (used by machine.py)
# ---------------------------------------------------------------------------

def is_terminal(state: AgentState) -> bool:
    """Return True if the state permits no further transitions."""
    return state in TERMINAL_STATES


def is_system_locked(state: AgentState) -> bool:
    """Return True if System authority is completely blocked from this state."""
    return state in SYSTEM_LOCKED_STATES


def allowed_authorities(
    from_state: AgentState, to_state: AgentState
) -> FrozenSet[Authority]:
    """
    Return the frozenset of authorities permitted to make this transition.
    Returns an empty frozenset if the edge is not in the matrix (invalid transition).
    """
    return TRANSITION_RULES.get((from_state, to_state), frozenset())


def is_transition_defined(from_state: AgentState, to_state: AgentState) -> bool:
    """Return True if the (from, to) pair exists in the transition matrix."""
    return (from_state, to_state) in TRANSITION_RULES


def is_authority_permitted(
    from_state: AgentState, to_state: AgentState, authority: Authority
) -> bool:
    """
    Return True if:
      - the transition pair is in the matrix, AND
      - the authority is in the permitted set for that edge.
    Does NOT check terminal or system-locked guards; machine.py does those first.
    """
    return authority in allowed_authorities(from_state, to_state)
