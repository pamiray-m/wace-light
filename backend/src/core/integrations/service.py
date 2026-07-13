"""
IntegrationGovernorService — unified facade for Packet 10.

Aggregates IntegrationRegistry, IntegrationGovernor, and SecurityHooks into a
single entry point.  Route handlers and dependency injection should use this
facade rather than importing the three sub-services individually.

Packet 10 §10 canonical interface exposed through this facade:
  register_tool(definition)           → ToolDefinitionRead
  assign_tool(product_id, agent_id, tool_id) → ToolBindingRead
  evaluate_access(agent_id, tool_id)  → bool

All methods in this facade are thin delegators — business logic lives in the
sub-services.  This keeps the boundary clean and testable in isolation.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from src.core.integrations.enums import IntegrationAuthority, ToolStatus
from src.core.integrations.exceptions import ToolAccessDenied, ProductIsolationViolation
from src.core.integrations.governor import IntegrationGovernor, ToolBindingCreate, ToolBindingRead
from src.core.integrations.registry import (
    IntegrationRegistry,
    ToolDefinitionCreate,
    ToolDefinitionRead,
    ToolTransitionRequest,
)
from src.core.integrations.security_hooks import CredentialTicket, SecurityHooks
from src.core.integrations.vault import CredentialVault
from src.core.registry.service import RegistryService


class IntegrationGovernorService:
    """
    Top-level service facade for Integration Governance (Packet 10).

    Parameters
    ----------
    session          : SQLAlchemy session (shared with other P10 sub-services).
    registry_service : Packet 2 RegistryService for agent/product ownership checks.
    """

    def __init__(
        self,
        session:          Session,
        registry_service: RegistryService,
        vault:            Optional[CredentialVault] = None,
    ) -> None:
        self._registry  = IntegrationRegistry(session=session)
        self._governor  = IntegrationGovernor(
            session=session,
            registry_service=registry_service,
            vault=vault,
        )
        self._hooks     = SecurityHooks(session=session, vault=vault)

    # ------------------------------------------------------------------
    # Catalog management (registry.py)
    # ------------------------------------------------------------------

    def register_tool(self, definition: ToolDefinitionCreate) -> ToolDefinitionRead:
        """Register a new tool in DISCOVERED status."""
        return self._registry.register_tool(definition)

    def get_tool(self, tool_id: str) -> ToolDefinitionRead:
        return ToolDefinitionRead.model_validate(self._registry.get_tool(tool_id))

    def list_tools(
        self,
        status:     Optional[ToolStatus] = None,
        product_id: Optional[str]        = None,
    ) -> list[ToolDefinitionRead]:
        return self._registry.list_tools(status=status, product_id=product_id)

    def transition_tool_status(
        self,
        tool_id:       str,
        target_status: ToolStatus,
        authority:     IntegrationAuthority,
    ) -> ToolDefinitionRead:
        """Drive the tool's lifecycle status through the governance policy matrix."""
        return self._registry.transition_status(tool_id, target_status, authority)

    # ------------------------------------------------------------------
    # Binding management (governor.py)
    # ------------------------------------------------------------------

    def assign_tool(
        self,
        product_id:              str,
        agent_id:                str,
        tool_id:                 str,
        vaulted_credentials_ref: Optional[str] = None,
    ) -> ToolBindingRead:
        """
        Bind an approved/enabled tool to an agent within a product.

        Packet 10 §10 required interface.
        """
        return self._governor.assign_tool(
            product_id=product_id,
            agent_id=agent_id,
            tool_id=tool_id,
            vaulted_credentials_ref=vaulted_credentials_ref,
        )

    def revoke_binding(self, binding_id: str, product_id: str) -> None:
        self._governor.revoke_binding(binding_id, product_id)

    def get_binding(self, binding_id: str, product_id: str) -> ToolBindingRead:
        return self._governor.get_binding(binding_id, product_id)

    def list_bindings(
        self,
        product_id: str,
        agent_id:   Optional[str] = None,
        tool_id:    Optional[str] = None,
    ) -> list[ToolBindingRead]:
        return self._governor.list_bindings(
            product_id=product_id,
            agent_id=agent_id,
            tool_id=tool_id,
        )

    # ------------------------------------------------------------------
    # Access evaluation (security_hooks.py)
    # ------------------------------------------------------------------

    def evaluate_access(
        self,
        agent_id:              str,
        tool_id:               str,
        requesting_product_id: Optional[str] = None,
    ) -> bool:
        """
        Check whether agent_id may access tool_id.

        Packet 10 §10 required interface (returns bool, never raises).
        Logs all denials to the Packet 6 observability layer.
        """
        return self._hooks.evaluate_access(
            agent_id=agent_id,
            tool_id=tool_id,
            requesting_product_id=requesting_product_id,
        )

    def issue_credential_ticket(
        self,
        agent_id:   str,
        tool_id:    str,
        product_id: str,
    ) -> CredentialTicket:
        """
        Issue a transient scoped credential ticket for Layer 4 consumption.

        Raises ToolAccessDenied / ProductIsolationViolation if access is denied.
        """
        return self._hooks.issue_credential_ticket(
            agent_id=agent_id,
            tool_id=tool_id,
            product_id=product_id,
        )
