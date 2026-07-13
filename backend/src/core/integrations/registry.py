"""
IntegrationRegistry — catalog management for third-party tool definitions.

Responsibilities
----------------
- Register new tools in the catalog (initially DISCOVERED).
- Retrieve individual tool definitions by id or name.
- List tools filtered by status and/or product_id.
- Drive the approval lifecycle via IntegrationGovernorEngine.

This module owns only ToolDefinitionRecord writes.  ToolBindingRecord is
owned by governor.py.  SecurityHooks (security_hooks.py) evaluates access
using both tables in read-only mode.

Packet 10 §10 required interface:
  register_tool(definition) → ToolDefinitionRead
  (get/list are extensions needed by all dependent services)
"""

from __future__ import annotations

from typing import Optional
from datetime import datetime, timezone

from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.core.integrations.enums import (
    IntegrationAuthority,
    SecurityLevel,
    ToolCategory,
    ToolStatus,
)
from src.core.integrations.exceptions import (
    InvalidToolTransition,
    TerminalToolError,
    ToolNotFound,
    UnauthorizedToolWrite,
)
from src.core.integrations.models import ToolDefinitionRecord


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ToolDefinitionCreate(BaseModel):
    """Input schema for registering a new tool in the catalog."""
    name:           str
    provider:       str
    category:       ToolCategory  = ToolCategory.OTHER
    scope:          str           = ""
    security_level: SecurityLevel = SecurityLevel.MEDIUM
    description:    Optional[str] = None
    # None = global catalog entry available to any product
    product_id:     Optional[str] = None


class ToolDefinitionRead(BaseModel):
    """Read schema returned by catalog queries."""
    id:             str
    name:           str
    provider:       str
    category:       str
    scope:          str
    security_level: str
    status:         str
    description:    Optional[str]
    product_id:     Optional[str]
    created_at:     datetime
    updated_at:     datetime

    model_config = {"from_attributes": True}


class ToolTransitionRequest(BaseModel):
    """Request to drive a tool's lifecycle status to a new state."""
    target_status: ToolStatus
    authority:     IntegrationAuthority


# ---------------------------------------------------------------------------
# Lifecycle policy matrix (mirrors SkillLifecycleEngine pattern from P8)
# ---------------------------------------------------------------------------

_A = IntegrationAuthority
_S = ToolStatus

# Layer 0 sovereignty — unrestricted governance
_SOVEREIGNTY = frozenset({_A.ARCHITECT, _A.DEPUTY})

# Layer 1 governance owners
_GOVERNORS = frozenset({_A.ARCHITECT, _A.DEPUTY, _A.INTEGRATION_GOVERNOR})

# Reviewers include legal and standards roles
_REVIEWERS = frozenset({
    _A.ARCHITECT, _A.DEPUTY,
    _A.INTEGRATION_GOVERNOR, _A.STANDARDS_AGENT, _A.LAWYER,
})

# Proposers: anyone above system level may submit for governance (incl. Oracle)
_PROPOSERS = frozenset({
    _A.ARCHITECT, _A.DEPUTY,
    _A.INTEGRATION_GOVERNOR, _A.STANDARDS_AGENT, _A.ORACLE, _A.LAWYER,
    _A.SYSTEM,
})

TRANSITION_RULES: dict[tuple[ToolStatus, ToolStatus], frozenset[IntegrationAuthority]] = {
    # Forward approval path
    (_S.DISCOVERED, _S.PROPOSED):   _PROPOSERS,    # submit for governance review
    (_S.PROPOSED,   _S.REVIEWED):   _REVIEWERS,    # legal/standards review complete
    (_S.REVIEWED,   _S.APPROVED):   _GOVERNORS,    # governance approval granted
    (_S.APPROVED,   _S.ENABLED):    _GOVERNORS,    # activate for agent bindings

    # Suspension / re-activation
    (_S.ENABLED,    _S.DISABLED):   _GOVERNORS,    # temporarily suspend
    (_S.DISABLED,   _S.ENABLED):    _GOVERNORS,    # re-activate

    # Rejection / send-back paths
    (_S.PROPOSED,   _S.DISCOVERED): _REVIEWERS,    # reject submission, reset to catalog
    (_S.REVIEWED,   _S.PROPOSED):   _REVIEWERS,    # send back for rework before approval

    # Revocation (permanent) — from any active state
    (_S.ENABLED,    _S.REVOKED):    _GOVERNORS,
    (_S.DISABLED,   _S.REVOKED):    _GOVERNORS,
    (_S.APPROVED,   _S.REVOKED):    _GOVERNORS,
    # Sovereignty-only revocation from pre-approval states
    (_S.REVIEWED,   _S.REVOKED):    _SOVEREIGNTY,
    (_S.PROPOSED,   _S.REVOKED):    _SOVEREIGNTY,
    (_S.DISCOVERED, _S.REVOKED):    _SOVEREIGNTY,
}

TERMINAL_STATUSES = frozenset({_S.REVOKED})

# Tools must be in one of these states before agents can be bound to them
BINDABLE_STATUSES = frozenset({_S.APPROVED, _S.ENABLED})


class IntegrationGovernorEngine:
    """
    Stateless lifecycle policy enforcer for tool definitions.

    Raises domain exceptions rather than returning error codes so the
    service layer can map them cleanly to HTTP responses.
    """

    def validate_transition(
        self,
        current_status: ToolStatus,
        target_status:  ToolStatus,
        authority:      IntegrationAuthority,
    ) -> None:
        if current_status in TERMINAL_STATUSES:
            raise TerminalToolError(
                f"Tool is in terminal status {current_status.value}. "
                "No further transitions are permitted."
            )

        key = (current_status, target_status)
        if key not in TRANSITION_RULES:
            raise InvalidToolTransition(
                f"Transition {current_status.value} → {target_status.value} "
                "is not defined in the integration governance policy."
            )

        allowed = TRANSITION_RULES[key]
        if authority not in allowed:
            raise UnauthorizedToolWrite(
                f"Authority '{authority.value}' is not permitted to transition "
                f"a tool from {current_status.value} → {target_status.value}. "
                f"Permitted: {sorted(a.value for a in allowed)}."
            )

    def allowed_transitions(self, current_status: ToolStatus) -> list[ToolStatus]:
        """Return all reachable target statuses from the current status."""
        if current_status in TERMINAL_STATUSES:
            return []
        return [tgt for (src, tgt) in TRANSITION_RULES if src == current_status]

    def is_terminal(self, status: ToolStatus) -> bool:
        return status in TERMINAL_STATUSES

    def is_bindable(self, status: ToolStatus) -> bool:
        """True if agents may be assigned to a tool in this status."""
        return status in BINDABLE_STATUSES


# ---------------------------------------------------------------------------
# IntegrationRegistry service
# ---------------------------------------------------------------------------

class IntegrationRegistry:
    """
    Manages the tool definition catalog (ToolDefinitionRecord).

    Usage
    -----
        registry = IntegrationRegistry(session=db_session)
        tool = registry.register_tool(ToolDefinitionCreate(name="Zapier", ...))
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._engine  = IntegrationGovernorEngine()

    # ------------------------------------------------------------------
    # Packet 10 §10 required interface
    # ------------------------------------------------------------------

    def register_tool(self, definition: ToolDefinitionCreate) -> ToolDefinitionRead:
        """
        Add a new tool to the catalog in DISCOVERED status.

        The tool enters governance at DISCOVERED — it must pass through
        PROPOSED → REVIEWED → APPROVED before agents may be bound to it.
        """
        record = ToolDefinitionRecord(
            name           = definition.name,
            provider       = definition.provider,
            category       = definition.category.value,
            scope          = definition.scope,
            security_level = definition.security_level.value,
            status         = ToolStatus.DISCOVERED.value,
            description    = definition.description,
            product_id     = definition.product_id,
        )
        try:
            self._session.add(record)
            self._session.commit()
            self._session.refresh(record)
        except IntegrityError:
            self._session.rollback()
            raise ValueError(
                f"A tool named '{definition.name}' already exists in the catalog."
            )
        return ToolDefinitionRead.model_validate(record)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_tool(self, tool_id: str) -> ToolDefinitionRecord:
        """Return the ORM record for internal service use; raises ToolNotFound."""
        record = self._session.get(ToolDefinitionRecord, tool_id)
        if record is None:
            raise ToolNotFound(f"Tool '{tool_id}' not found in the catalog.")
        return record

    def get_tool_by_name(self, name: str) -> ToolDefinitionRecord:
        record = (
            self._session.query(ToolDefinitionRecord)
            .filter(ToolDefinitionRecord.name == name)
            .first()
        )
        if record is None:
            raise ToolNotFound(f"Tool named '{name}' not found in the catalog.")
        return record

    def list_tools(
        self,
        status:     Optional[ToolStatus] = None,
        product_id: Optional[str]        = None,
    ) -> list[ToolDefinitionRead]:
        """
        List catalog entries filtered by optional status and/or product_id.

        product_id filter returns tools that are either global (product_id=None)
        or explicitly scoped to that product.
        """
        q = self._session.query(ToolDefinitionRecord)
        if status is not None:
            q = q.filter(ToolDefinitionRecord.status == status.value)
        if product_id is not None:
            q = q.filter(
                (ToolDefinitionRecord.product_id == None) |  # noqa: E711
                (ToolDefinitionRecord.product_id == product_id)
            )
        return [ToolDefinitionRead.model_validate(r) for r in q.all()]

    # ------------------------------------------------------------------
    # Lifecycle transition
    # ------------------------------------------------------------------

    def transition_status(
        self,
        tool_id:       str,
        target_status: ToolStatus,
        authority:     IntegrationAuthority,
    ) -> ToolDefinitionRead:
        """
        Drive a tool's status through the governed lifecycle.

        Delegates all policy checks to IntegrationGovernorEngine.
        """
        record = self.get_tool(tool_id)
        current = ToolStatus(record.status)
        self._engine.validate_transition(current, target_status, authority)

        record.status = target_status.value
        record.updated_at = datetime.now(timezone.utc)
        self._session.commit()
        self._session.refresh(record)
        return ToolDefinitionRead.model_validate(record)
