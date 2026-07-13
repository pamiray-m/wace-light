"""
H2 — Policy Engine.

enforce_policy() is the central authorization gate for all Control API
operations.  It is called from route handlers before any service invocation.

Design principles
-----------------
1. Default DENY — any uncovered case raises PolicyViolation.
2. Scope checks are additive: role check first, then product scope, then stream
   scope.  All must pass; any failure is an immediate PolicyViolation.
3. The engine is stateless and deterministic — identical inputs always produce
   identical outcomes.  No DB lookups, no mutable state.
4. The engine knows nothing about the domain (agents, state machine).  It only
   evaluates identity + action + resource metadata.

Actions
-------
Actions map 1-to-1 with the HTTP operations that mutate or read state.
READ is used for all GET endpoints.  Each mutating command has its own Action
variant so future H5/H6 can add finer-grained rules.

Resource
--------
A lightweight TargetResource carries the metadata the engine needs to evaluate
scope: the product_id of the thing being acted on, and the optional stream_id.
Routes populate it from path/query params or from registry lookups.

H3 note: audit emission is NOT done here — that is H3 scope.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from src.core.auth.models import OperatorIdentity, OperatorRole

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class PolicyViolation(Exception):
    """
    Raised by enforce_policy() when a request is denied.

    Route exception handlers convert this to HTTP 403 Forbidden.
    """


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

class Action(str, Enum):
    """Discrete operations that can be authorized by the policy engine."""
    READ          = "read"
    CREATE_AGENT  = "create_agent"
    PROMPT        = "prompt"
    PAUSE         = "pause"
    RESUME        = "resume"
    SHUTDOWN      = "shutdown"
    LINK_AGENT    = "link_agent"        # hierarchy link creation
    ASSIGN_TOOL   = "assign_tool"       # integration governance
    MANAGE_SKILL  = "manage_skill"      # knowledge system write
    PROPOSE       = "propose"           # oracle proposals


# ---------------------------------------------------------------------------
# Role permission table (default-deny — only listed actions are allowed)
# ---------------------------------------------------------------------------

_ROLE_ALLOWED_ACTIONS: dict[OperatorRole, frozenset[Action]] = {
    OperatorRole.ADMIN: frozenset(Action),          # all actions
    OperatorRole.VIEWER: frozenset({Action.READ}),  # read-only
    OperatorRole.AUDITOR: frozenset({Action.READ}), # observability read-only
}


# ---------------------------------------------------------------------------
# Resource model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TargetResource:
    """
    Minimal resource context needed by the policy engine.

    product_id — the owning tenant of the resource.  None means "not scoped to
                 a specific product" (e.g., a global health check).
    stream_id  — optional stream label for stream-scoped resources.
    """
    product_id: str | None = field(default=None)
    stream_id: str | None = field(default=None)

    @classmethod
    def agent(cls, product_id: str, stream_id: str | None = None) -> "TargetResource":
        return cls(product_id=product_id, stream_id=stream_id)

    @classmethod
    def product(cls, product_id: str) -> "TargetResource":
        return cls(product_id=product_id)

    @classmethod
    def unscoped(cls) -> "TargetResource":
        """For resources that carry no product/stream restriction (e.g. /health)."""
        return cls()


# ---------------------------------------------------------------------------
# Policy Engine
# ---------------------------------------------------------------------------

class PolicyEngine:
    """
    Stateless authorization policy enforcer.

    All decisions are synchronous and side-effect-free.  The engine raises
    PolicyViolation on any denial; returning normally means "allowed".
    """

    def enforce(
        self,
        identity: OperatorIdentity,
        action: Action,
        resource: TargetResource,
    ) -> None:
        """
        Enforce authorization policy for *identity* performing *action* on *resource*.

        Raises
        ------
        PolicyViolation on any denial.
        """
        try:
            self._check_role_action(identity, action)
            self._check_product_scope(identity, resource)
            self._check_stream_scope(identity, resource)
        except PolicyViolation as exc:
            from src.core.logging.metrics import policy_denials
            policy_denials.increment()
            _log.warning(
                "policy.denied",
                extra={
                    "event": "policy.denied",
                    "operator_id": identity.operator_id,
                    "operator_role": identity.role.value,
                    "action": action.value,
                    "product_id": resource.product_id,
                    "reason": str(exc),
                },
            )
            raise

    # ------------------------------------------------------------------
    # Checks (each raises PolicyViolation on failure)
    # ------------------------------------------------------------------

    def _check_role_action(self, identity: OperatorIdentity, action: Action) -> None:
        """Step 1: Does the operator's role permit this action?"""
        allowed = _ROLE_ALLOWED_ACTIONS.get(identity.role, frozenset())
        if action not in allowed:
            raise PolicyViolation(
                f"Role '{identity.role.value}' is not permitted to perform "
                f"action '{action.value}'. "
                f"Required: ADMIN."
            )

    def _check_product_scope(
        self, identity: OperatorIdentity, resource: TargetResource
    ) -> None:
        """
        Step 2: If the operator has a product scope, the resource must be in it.

        An operator with product_scope=None is a global operator with no product
        restriction.  An operator with product_scope="X" may only act on resources
        owned by product "X".
        """
        if identity.product_scope is None:
            return  # global operator — no restriction
        if resource.product_id is None:
            return  # resource has no product scope — unscoped resource
        if identity.product_scope != resource.product_id:
            raise PolicyViolation(
                f"Cross-product access denied: operator '{identity.username}' is "
                f"scoped to product '{identity.product_scope}' but attempted to "
                f"act on product '{resource.product_id}'."
            )

    def _check_stream_scope(
        self, identity: OperatorIdentity, resource: TargetResource
    ) -> None:
        """
        Step 3: If the operator has a stream scope, the resource must be in it.

        An operator with stream_scope=None has no stream restriction.
        """
        if identity.stream_scope is None:
            return  # no stream restriction
        if resource.stream_id is None:
            return  # resource carries no stream label — no check needed
        if identity.stream_scope != resource.stream_id:
            raise PolicyViolation(
                f"Stream boundary violation: operator '{identity.username}' is "
                f"scoped to stream '{identity.stream_scope}' but attempted to "
                f"act on stream '{resource.stream_id}'."
            )


# ---------------------------------------------------------------------------
# Module-level singleton and convenience function
# ---------------------------------------------------------------------------

_engine = PolicyEngine()


def enforce_policy(
    identity: OperatorIdentity,
    action: Action,
    resource: TargetResource | None = None,
) -> None:
    """
    Convenience wrapper around PolicyEngine.enforce().

    resource defaults to TargetResource.unscoped() if omitted (safe for
    endpoints that carry no product/stream context).

    Raises PolicyViolation on denial.
    """
    _engine.enforce(identity, action, resource or TargetResource.unscoped())
