"""
IntegrationGovernor — RBAC binding engine for agent/product integration assignments.

Responsibilities
----------------
- Assign an approved/enabled catalog tool to a specific (agent_id, product_id) pair.
- Revoke an existing binding.
- List all bindings scoped to a product or agent.
- Validate product isolation: agent must belong to the stated product_id (P2 check).
- Validate tool eligibility: tool must be APPROVED or ENABLED before binding.

This module owns ToolBindingRecord writes.
ToolDefinitionRecord reads are delegated to IntegrationRegistry.

Packet 10 §10 required interface:
  assign_tool(product_id, agent_id, tool_id)
  (revoke and list are governance extensions)

Isolation rule
--------------
assign_tool() requires both a product_id and an agent_id.  It verifies that
the agent belongs to product_id by calling RegistryService.get_agent().  A
mismatch raises ProductIsolationViolation before any DB write occurs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from datetime import datetime, timezone

if TYPE_CHECKING:
    from src.core.integrations.vault import CredentialVault

from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.core.integrations.enums import ToolStatus
from src.core.integrations.exceptions import (
    DuplicateToolBinding,
    ProductIsolationViolation,
    ToolBindingNotFound,
    ToolNotApproved,
    VaultError,
)
from src.core.integrations.models import ToolBindingRecord
from src.core.integrations.registry import (
    BINDABLE_STATUSES,
    IntegrationRegistry,
    ToolDefinitionRead,
)
from src.core.registry.service import AgentNotFound, RegistryService


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ToolBindingCreate(BaseModel):
    """Input for binding a catalog tool to an agent within a product."""
    product_id:              str
    agent_id:                str
    tool_id:                 str
    # Stub vault reference — mocked string in early dev per Packet 10 §13
    vaulted_credentials_ref: Optional[str] = None


class ToolBindingRead(BaseModel):
    """Read schema for an existing tool binding."""
    id:                      str
    tool_id:                 str
    agent_id:                str
    product_id:              str
    vaulted_credentials_ref: Optional[str]
    created_at:              datetime
    updated_at:              datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Governor service
# ---------------------------------------------------------------------------

class IntegrationGovernor:
    """
    Manages tool-to-agent bindings with product isolation enforcement.

    Depends on IntegrationRegistry (read tool definitions) and
    RegistryService (verify agent/product ownership from Packet 2).

    Usage
    -----
        governor = IntegrationGovernor(
            session=db_session,
            registry_service=registry,
        )
        binding = governor.assign_tool("product-A", "agent-1", "tool-id")
    """

    def __init__(
        self,
        session:          Session,
        registry_service: RegistryService,
        vault:            "Optional[CredentialVault]" = None,
    ) -> None:
        self._session   = session
        self._registry  = IntegrationRegistry(session=session)
        self._agents    = registry_service
        self._vault     = vault

    # ------------------------------------------------------------------
    # Packet 10 §10 required interface
    # ------------------------------------------------------------------

    def assign_tool(
        self,
        product_id:              str,
        agent_id:                str,
        tool_id:                 str,
        vaulted_credentials_ref: Optional[str] = None,
    ) -> ToolBindingRead:
        """
        Bind a tool to an agent within a product.

        Validation steps (in order):
          1. Agent exists in product_id (Packet 2 check) — raises AgentNotFound /
             ProductIsolationViolation on mismatch.
          2. Tool exists in catalog — raises ToolNotFound.
          3. Tool is APPROVED or ENABLED — raises ToolNotApproved otherwise.
          4. No existing binding — raises DuplicateToolBinding if already bound.

        Assumption
        ----------
        RegistryService.get_agent() scopes its query by product_id.  If the
        caller passes the wrong product_id for a real agent, get_agent() will
        raise AgentNotFound — which we re-raise as ProductIsolationViolation to
        match the Packet 10 acceptance criterion ("assign_tool rejects a
        mismatching Product ID boundary").
        """
        # Step 1 — verify agent belongs to this product via Packet 2 registry
        try:
            self._agents.get_agent(agent_id=agent_id, product_id=product_id)
        except AgentNotFound:
            raise ProductIsolationViolation(
                f"Agent '{agent_id}' does not belong to product '{product_id}'. "
                "Tool assignment rejected — product isolation boundary violated."
            )

        # Step 2 & 3 — verify tool exists and is in a bindable state
        tool_record = self._registry.get_tool(tool_id)
        current_status = ToolStatus(tool_record.status)
        if current_status not in BINDABLE_STATUSES:
            raise ToolNotApproved(
                f"Tool '{tool_record.name}' is in status '{tool_record.status}'. "
                f"Only {[s.value for s in BINDABLE_STATUSES]} tools may be bound to agents."
            )

        # Step 4 — encrypt credentials through vault if provided, then create binding
        if vaulted_credentials_ref is not None:
            if self._vault is None:
                raise VaultError(
                    "A CredentialVault is required to store credentials but none was "
                    "configured. Set AOS_VAULT_KEY and pass a CredentialVault instance."
                )
            vaulted_credentials_ref = self._vault.seal(product_id, vaulted_credentials_ref)

        binding = ToolBindingRecord(
            tool_id                = tool_id,
            agent_id               = agent_id,
            product_id             = product_id,
            vaulted_credentials_ref = vaulted_credentials_ref,
        )
        try:
            self._session.add(binding)
            self._session.commit()
            self._session.refresh(binding)
        except IntegrityError:
            self._session.rollback()
            raise DuplicateToolBinding(
                f"Agent '{agent_id}' in product '{product_id}' is already bound "
                f"to tool '{tool_record.name}'."
            )
        return ToolBindingRead.model_validate(binding)

    # ------------------------------------------------------------------
    # Revocation
    # ------------------------------------------------------------------

    def revoke_binding(self, binding_id: str, product_id: str) -> None:
        """
        Remove a tool binding.

        product_id is required to enforce isolation — a caller cannot revoke
        a binding from a different product even if they know the binding_id.
        """
        binding = self._session.get(ToolBindingRecord, binding_id)
        if binding is None or binding.product_id != product_id:
            raise ToolBindingNotFound(
                f"Binding '{binding_id}' not found for product '{product_id}'."
            )
        self._session.delete(binding)
        self._session.commit()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_binding(self, binding_id: str, product_id: str) -> ToolBindingRead:
        binding = self._session.get(ToolBindingRecord, binding_id)
        if binding is None or binding.product_id != product_id:
            raise ToolBindingNotFound(
                f"Binding '{binding_id}' not found for product '{product_id}'."
            )
        return ToolBindingRead.model_validate(binding)

    def list_bindings(
        self,
        product_id: str,
        agent_id:   Optional[str] = None,
        tool_id:    Optional[str] = None,
    ) -> list[ToolBindingRead]:
        """
        List bindings scoped to a product, optionally filtered by agent or tool.

        product_id is mandatory — no cross-product listing is possible.
        """
        q = (
            self._session.query(ToolBindingRecord)
            .filter(ToolBindingRecord.product_id == product_id)
        )
        if agent_id is not None:
            q = q.filter(ToolBindingRecord.agent_id == agent_id)
        if tool_id is not None:
            q = q.filter(ToolBindingRecord.tool_id == tool_id)
        return [ToolBindingRead.model_validate(r) for r in q.all()]

    def get_tool_definition(self, tool_id: str) -> ToolDefinitionRead:
        """Expose tool metadata for API responses without duplicating the registry."""
        return ToolDefinitionRead.model_validate(self._registry.get_tool(tool_id))
