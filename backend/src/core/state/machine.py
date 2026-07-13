"""
StateMachine — the mAIb-owned enforcement engine for agent lifecycle transitions.

This is the only place in the system allowed to change an agent's lifecycle state.
No runtime engine, adapter, or API handler may mutate state by any other path.

Execution path for transition_state()
--------------------------------------
1. Resolve current agent state from the Registry (tenant-scoped).
2. Apply terminal-state guard (TERMINATED → anything is always illegal).
3. Apply System-locked-state guard (System authority cannot act on BLOCKED/PAUSED).
4. Validate the (from, to) pair exists in the TRANSITION_RULES matrix.
5. Validate the requesting authority is in the permitted set for that edge.
6. Commit the new state to the Registry via RegistryService.update_lifecycle_state().
7. Emit an immutable TransitionEvent to the audit log.
8. Return the TransitionEvent to the caller.

The caller never needs to touch the Registry directly — the state machine owns
the full write path for lifecycle state changes.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from src.core.registry.service import RegistryService
from src.core.registry.service import AgentNotFound as RegistryAgentNotFound

from .enums import AgentState, Authority
from .events import TransitionEvent, record_event
from .exceptions import (
    AgentStateNotFound,
    BlockedTransitionError,
    InvalidTransitionError,
    TerminalStateError,
    UnauthorizedTransitionError,
)
from .policy import (
    is_authority_permitted,
    is_system_locked,
    is_terminal,
    is_transition_defined,
)


class StateMachine:
    """
    Enforces the mAIb agent lifecycle policy.

    Usage (production)
    ------------------
        sm = StateMachine()
        event = sm.transition_state(
            agent_id="...",
            product_id="tenant-A",
            target_state=AgentState.BUSY,
            authority=Authority.SYSTEM,
            actor="system:execution-adapter",
        )

    Usage (tests)
    -------------
        sm = StateMachine(registry=RegistryService(session=test_session))

    Parameters
    ----------
    registry : RegistryService, optional
        Injected registry service.  If not supplied, a default instance is
        created (which uses the module-level session factory from Packet 2).
    """

    def __init__(self, registry: Optional[RegistryService] = None) -> None:
        self._registry = registry or RegistryService()

    # ------------------------------------------------------------------
    # Public interface (as specified by Packet 3)
    # ------------------------------------------------------------------

    def transition_state(
        self,
        agent_id:     str,
        product_id:   str,
        target_state: AgentState,
        authority:    Authority,
        actor:        str,
        reason:       str = "",
    ) -> TransitionEvent:
        """
        Attempt to transition agent_id to target_state under the given authority.

        Parameters
        ----------
        agent_id     : Registry ID of the agent to transition.
        product_id   : Tenant scope.  Must match the agent's registered product_id.
        target_state : The desired new lifecycle state.
        authority    : mAIb authority class asserting this transition.
        actor        : Specific identity string (e.g. "system:adapter", "user:ceo").
        reason       : Optional human-readable justification.

        Returns
        -------
        TransitionEvent — immutable audit record of the completed transition.

        Raises
        ------
        AgentStateNotFound        : agent_id not found in the Registry under product_id.
        TerminalStateError        : current state is TERMINATED.
        BlockedTransitionError    : current state is BLOCKED/PAUSED and authority is System.
        InvalidTransitionError    : (from, to) pair not in the transition matrix.
        UnauthorizedTransitionError : transition defined but authority not permitted.
        """
        # Step 1: resolve current state from Registry (tenant-scoped)
        current_state = self._resolve_current_state(agent_id, product_id)

        # Step 2: terminal-state guard
        if is_terminal(current_state):
            raise TerminalStateError(
                f"Agent '{agent_id}' is in terminal state {current_state.value}. "
                "No transitions are permitted from a TERMINATED agent."
            )

        # Step 3: System-locked-state guard (Packet 3 hard constraint)
        if authority == Authority.SYSTEM and is_system_locked(current_state):
            raise BlockedTransitionError(
                f"System authority is locked out of agent '{agent_id}' while it is "
                f"in state {current_state.value}. "
                "Only Architect or CEO may act on a BLOCKED or PAUSED agent."
            )

        # Step 4: transition pair existence check
        if not is_transition_defined(current_state, target_state):
            raise InvalidTransitionError(
                f"Transition {current_state.value} → {target_state.value} is not "
                "defined in the mAIb transition matrix."
            )

        # Step 5: authority permission check
        if not is_authority_permitted(current_state, target_state, authority):
            raise UnauthorizedTransitionError(
                f"Authority '{authority.value}' is not permitted to perform "
                f"{current_state.value} → {target_state.value}. "
                f"This transition requires one of: "
                f"{[a.value for a in self._permitted_authorities(current_state, target_state)]}."
            )

        # Step 6: commit new state to Registry
        self._registry.update_lifecycle_state(
            agent_id=agent_id,
            product_id=product_id,
            new_state=target_state,  # type: ignore[arg-type]
            # registry/schemas.py imports AgentState from here; same type
        )

        # Step 7: emit immutable audit event
        event = TransitionEvent(
            agent_id=agent_id,
            product_id=product_id,
            from_state=current_state,
            to_state=target_state,
            authority=authority,
            actor=actor,
            reason=reason,
        )
        record_event(event)

        # Step 8: return event to caller
        return event

    def current_state(self, agent_id: str, product_id: str) -> AgentState:
        """
        Read the current lifecycle state of an agent from the Registry.

        Convenience method for callers (e.g. Packet 1 GET endpoints) that need
        to inspect state without triggering a transition.
        """
        return self._resolve_current_state(agent_id, product_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_current_state(self, agent_id: str, product_id: str) -> AgentState:
        """
        Fetch the agent's lifecycle_state from the Registry.
        Wraps AgentNotFound → AgentStateNotFound to keep packet boundaries clean.
        """
        try:
            agent_read = self._registry.get_agent(agent_id, product_id)
        except RegistryAgentNotFound as exc:
            raise AgentStateNotFound(
                f"Cannot resolve state for agent '{agent_id}' under "
                f"product_id='{product_id}': {exc}"
            ) from exc

        # registry/schemas.AgentLifecycleState is now AgentState (same type after Packet 2 refactor)
        raw = agent_read.lifecycle_state
        return AgentState(raw.value)

    @staticmethod
    def _permitted_authorities(
        from_state: AgentState, to_state: AgentState
    ) -> list[Authority]:
        """Return the list of authorities permitted for a given edge (for error messages)."""
        from .policy import allowed_authorities
        return sorted(allowed_authorities(from_state, to_state), key=lambda a: a.value)
