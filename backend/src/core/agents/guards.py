"""
D1 — DAG Constraint Hook.

DAGConstraintHook is the single, mandatory control point for all DAG-specific
enforcement.  Every system boundary that is sensitive to agent classification
(Mode Controller, Tool Access, Certification, Console) MUST call
DAGConstraintHook.check() before proceeding.

Design contract
---------------
- check() is a no-op for INTERNAL agents (zero regression risk).
- check() raises DAGConstraintViolation for DAG agents when the requested
  operation is not yet authorised by a D2–D14 validator.
- D2–D14 packets register their validators via register_validator(); until
  a validator is registered, the operation is implicitly blocked for DAG agents
  (fail-closed, not fail-open).
- Validators are callables: (agent_id: str, context: dict) -> None.
  They raise DAGConstraintViolation to block; return normally to allow.

This module intentionally contains NO DAG business logic.  It only establishes
the control point and the registration mechanism so that D2–D14 can plug in
cleanly without touching existing code.

Usage
-----
    from src.core.agents.guards import DAGConstraintHook

    hook = DAGConstraintHook()
    hook.check(agent_type=agent.agent_type, operation="mode_transition",
               agent_id=agent.id, context={"target_mode": "TRAINING"})
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from src.core.agents.types import AgentType

log = logging.getLogger(__name__)

# Validator callable type: (agent_id, context) -> None  (raises on violation)
_ValidatorFn = Callable[[str, dict], None]


class DAGConstraintViolation(Exception):
    """
    Raised by DAGConstraintHook.check() when a DAG-specific rule blocks an
    operation.

    Attributes
    ----------
    operation   : The logical operation name that was blocked (e.g. "mode_transition").
    agent_id    : The agent the check was performed against.
    detail      : Human-readable explanation of the violation.
    """

    def __init__(self, operation: str, agent_id: str, detail: str) -> None:
        self.operation = operation
        self.agent_id  = agent_id
        self.detail    = detail
        super().__init__(
            f"DAG constraint violation for agent '{agent_id}' "
            f"on operation '{operation}': {detail}"
        )


class DAGConstraintHook:
    """
    Central enforcement hook for DAG-agent classification rules.

    Instantiate once per service (or use the module-level singleton
    `dag_hook` defined at the bottom of this file).  D2–D14 validators
    are registered at import time via register_validator().

    Thread-safety: validator registration happens at startup; runtime
    calls are read-only and therefore safe for concurrent use.
    """

    def __init__(self) -> None:
        # operation_name -> list of validator callables
        self._validators: dict[str, list[_ValidatorFn]] = {}

    # ------------------------------------------------------------------
    # Registration (called by D2–D14 at import/startup time)
    # ------------------------------------------------------------------

    def register_validator(self, operation: str, fn: _ValidatorFn) -> None:
        """
        Register a DAG-specific validator for a named operation.

        Parameters
        ----------
        operation : Logical operation name (e.g. "mode_transition", "tool_access").
        fn        : Callable(agent_id, context) -> None.  Raises DAGConstraintViolation
                    to block; returns normally to allow.
        """
        self._validators.setdefault(operation, []).append(fn)
        log.debug("DAGConstraintHook: registered validator for operation '%s'.", operation)

    # ------------------------------------------------------------------
    # Enforcement (called at every system boundary sensitive to agent type)
    # ------------------------------------------------------------------

    def check(
        self,
        agent_type: AgentType,
        operation: str,
        agent_id: str,
        context: Optional[dict] = None,
    ) -> None:
        """
        Enforce DAG constraints for the given operation.

        For INTERNAL agents this is always a no-op.

        For DAG agents:
        - If no validator is registered for *operation*, the operation is
          BLOCKED (fail-closed) because no D2–D14 packet has authorised it.
        - If validators are registered, each is called in registration order.
          Any validator may raise DAGConstraintViolation to block.

        Parameters
        ----------
        agent_type : AgentType value from the agent's registry record.
        operation  : Logical operation name; must be a consistent string across
                     all callers (e.g. "mode_transition", "tool_access",
                     "certification", "console_control").
        agent_id   : ID of the agent being operated on.
        context    : Arbitrary dict of operation-specific data passed to validators.

        Raises
        ------
        DAGConstraintViolation : Operation is blocked for this DAG agent.
        """
        if agent_type != AgentType.DAG:
            # INTERNAL agents pass through unconditionally — zero performance impact.
            return

        ctx = context or {}
        validators = self._validators.get(operation)

        if not validators:
            # Fail-closed: no validator registered means DAG operation is not yet
            # authorised.  A D2–D14 packet must explicitly unlock the operation.
            log.warning(
                "DAGConstraintHook: blocked DAG agent '%s' on operation '%s' "
                "(no validator registered — fail-closed).",
                agent_id, operation,
            )
            raise DAGConstraintViolation(
                operation=operation,
                agent_id=agent_id,
                detail=(
                    f"Operation '{operation}' is not yet authorised for DAG agents. "
                    "A D2–D14 validator must be registered to unlock it."
                ),
            )

        for fn in validators:
            fn(agent_id, ctx)

        log.debug(
            "DAGConstraintHook: DAG agent '%s' passed all validators for '%s'.",
            agent_id, operation,
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
# Import and use this in all callers so that D2–D14 validator registrations
# made at import time accumulate in a single shared instance.
#
#   from src.core.agents.guards import dag_hook
#   dag_hook.check(agent_type=..., operation=..., agent_id=...)
#
dag_hook: DAGConstraintHook = DAGConstraintHook()
