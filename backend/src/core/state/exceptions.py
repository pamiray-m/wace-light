"""
Exceptions raised by the mAIb Agent State Machine.

All exceptions inherit from PolicyException so callers can catch the entire
class of governance violations with a single except clause when needed.

Packet 1 (Control API) will map these to appropriate HTTP response codes.
"""

from __future__ import annotations


class PolicyException(Exception):
    """
    Base class for all state-machine governance violations.

    Raised whenever the state machine cannot execute a requested transition
    due to policy, authority, or state-model rules.
    """


class InvalidTransitionError(PolicyException):
    """
    The requested (from_state → to_state) pair does not exist in the
    allowed transition matrix regardless of authority.

    Example: TERMINATED → IDLE is structurally impossible.
    """


class UnauthorizedTransitionError(PolicyException):
    """
    The transition pair exists in the matrix but the supplied authority
    does not appear in the authorized set for that edge.

    Example: System attempting BLOCKED → IDLE (only Architect/CEO may do this).
    """


class BlockedTransitionError(PolicyException):
    """
    The agent's current state is BLOCKED or PAUSED and the requesting
    authority is System.  System is explicitly locked out of these states
    regardless of the target state requested.

    This implements the hard constraint from Packet 3:
        "If agent_id's state is currently BLOCKED, the System authority
         CANNOT transition to IDLE."
    """


class TerminalStateError(PolicyException):
    """
    An attempt was made to transition out of the TERMINATED state.
    TERMINATED is a one-way terminal — no authority may exit it.
    """


class AgentStateNotFound(PolicyException):
    """
    The state machine could not resolve the agent's current state from the
    Registry.  Wraps registry-layer AgentNotFound to keep packet boundaries clean.
    """
