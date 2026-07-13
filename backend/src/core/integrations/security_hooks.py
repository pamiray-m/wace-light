"""
SecurityHooks — access evaluation and credential ticket issuance (Packet 10).

Responsibilities
----------------
- evaluate_access(agent_id, tool_id) → bool
  Determines whether an agent holds an active binding for a tool.
  Optionally checks the requesting_product_id to detect cross-product attempts.

- issue_credential_ticket(agent_id, tool_id, product_id) → CredentialTicket
  Issues a transient, scoped credential reference for Layer 4 consumption.
  The ticket carries ONLY the vaulted_credentials_ref for the specific binding;
  it never exposes another product's credentials.

Contract reference (integration-governance-contract.md):
  "If OpenClaw requests execution of a Zap, the Integration API first checks
   evaluate_access(agent_id, tool_id).  If the request originates from a rogue
   cross-product process, it returns a hard 403 Forbidden and logs a high
   severity event in the observability layer."

Observability integration
--------------------------
All security decisions (allow, deny, isolation-violation) are logged using the
Packet 6 structured logger so that the observability layer captures a durable
audit trail of every access evaluation.  This satisfies Packet 10 §15:
"Failures should generate Observability Layer tags."

No execution authority
-----------------------
SecurityHooks never executes tool actions.  It is a read-only policy oracle
that returns a bool and issues ticket stubs.  Actual execution falls to Layer 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
import uuid

if TYPE_CHECKING:
    from src.core.integrations.vault import CredentialVault

from sqlalchemy.orm import Session

from src.core.integrations.enums import ToolStatus
from src.core.integrations.exceptions import (
    ProductIsolationViolation,
    ToolAccessDenied,
    ToolBindingNotFound,
)
from src.core.integrations.models import ToolBindingRecord, ToolDefinitionRecord
from src.observability.logger import get_logger

_log = get_logger(__name__)

# Tool bindings are only considered active when the tool itself is ENABLED.
# APPROVED tools may not yet be enabled for runtime use.
_ACTIVE_TOOL_STATUS = ToolStatus.ENABLED


@dataclass(frozen=True)
class CredentialTicket:
    """
    Transient, scoped credential stub for Layer 4 consumption.

    In production this would contain a short-lived token or vault lease.
    In early dev the vaulted_credentials_ref field is a plain mock string
    per Packet 10 §13.

    The ticket is bound to a single (agent_id, tool_id, product_id) triple —
    it MUST NOT be reused for a different product's execution context.
    """
    ticket_id:               str
    agent_id:                str
    tool_id:                 str
    product_id:              str
    vaulted_credentials_ref: Optional[str]
    issued_at:               datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SecurityHooks:
    """
    Read-only access evaluator for integration governance.

    Takes a SQLAlchemy session for direct DB reads.  All writes happen in
    IntegrationRegistry / IntegrationGovernor; SecurityHooks is read-only.

    Usage
    -----
        hooks = SecurityHooks(session=db_session)
        allowed = hooks.evaluate_access("agent-1", "tool-id-xyz")
        if allowed:
            ticket = hooks.issue_credential_ticket("agent-1", "tool-id-xyz", "product-A")
    """

    def __init__(
        self,
        session: Session,
        vault:   "Optional[CredentialVault]" = None,
    ) -> None:
        self._session = session
        self._vault   = vault

    # ------------------------------------------------------------------
    # Packet 10 §10 required interface
    # ------------------------------------------------------------------

    def evaluate_access(
        self,
        agent_id:             str,
        tool_id:              str,
        requesting_product_id: Optional[str] = None,
    ) -> bool:
        """
        Return True if agent_id holds an ENABLED binding for tool_id.

        Parameters
        ----------
        agent_id              : The agent requesting tool access.
        tool_id               : The catalog tool ID being checked.
        requesting_product_id : If supplied, the binding's product_id must match
                                this value; mismatch triggers a CRITICAL security log
                                and returns False (cross-product isolation violation).

        Returns False (never raises) on all denial paths so that the contract
        `evaluate_access → bool` is preserved.  Callers that need to raise
        HTTP 403 should inspect the return value and raise themselves.

        Observability: every denial is logged at WARNING level; cross-product
        violations are logged at CRITICAL level with a security tag.
        """
        binding = (
            self._session.query(ToolBindingRecord)
            .filter(
                ToolBindingRecord.agent_id == agent_id,
                ToolBindingRecord.tool_id  == tool_id,
            )
            .first()
        )

        if binding is None:
            _log.warning(
                "integration_access_denied",
                extra={
                    "agent_id": agent_id,
                    "tool_id":  tool_id,
                    "reason":   "no_binding",
                },
            )
            return False

        # Cross-product check — must come before tool-status check so isolation
        # violations are always caught regardless of tool state.
        if requesting_product_id is not None and binding.product_id != requesting_product_id:
            _log.critical(
                "integration_isolation_violation",
                extra={
                    "agent_id":             agent_id,
                    "tool_id":              tool_id,
                    "bound_product":        binding.product_id,
                    "requesting_product":   requesting_product_id,
                    "severity":             "HIGH",
                    "security_event":       True,
                },
            )
            return False

        # Verify the tool itself is still ENABLED (not DISABLED or REVOKED)
        tool = self._session.get(ToolDefinitionRecord, tool_id)
        if tool is None or ToolStatus(tool.status) != _ACTIVE_TOOL_STATUS:
            tool_status = tool.status if tool else "NOT_FOUND"
            _log.warning(
                "integration_access_denied",
                extra={
                    "agent_id":    agent_id,
                    "tool_id":     tool_id,
                    "tool_status": tool_status,
                    "reason":      "tool_not_active",
                },
            )
            return False

        _log.info(
            "integration_access_granted",
            extra={"agent_id": agent_id, "tool_id": tool_id, "product_id": binding.product_id},
        )
        return True

    # ------------------------------------------------------------------
    # Credential ticket issuance (Layer 4 integration stub)
    # ------------------------------------------------------------------

    def issue_credential_ticket(
        self,
        agent_id:   str,
        tool_id:    str,
        product_id: str,
    ) -> CredentialTicket:
        """
        Issue a transient credential ticket for Layer 4 tool execution.

        Raises
        ------
        ToolAccessDenied         : evaluate_access returned False.
        ProductIsolationViolation: binding's product_id != product_id.
        ToolBindingNotFound      : no binding exists for (agent_id, tool_id).

        The ticket carries ONLY the vaulted_credentials_ref for the requesting
        agent/product combination — never another product's credentials.
        """
        if not self.evaluate_access(agent_id, tool_id, requesting_product_id=product_id):
            # Determine the specific reason for a more informative exception
            binding = (
                self._session.query(ToolBindingRecord)
                .filter(
                    ToolBindingRecord.agent_id == agent_id,
                    ToolBindingRecord.tool_id  == tool_id,
                )
                .first()
            )
            if binding is None:
                raise ToolBindingNotFound(
                    f"No binding for agent '{agent_id}' and tool '{tool_id}'."
                )
            if binding.product_id != product_id:
                raise ProductIsolationViolation(
                    f"Agent '{agent_id}' tool binding belongs to product "
                    f"'{binding.product_id}', not '{product_id}'."
                )
            raise ToolAccessDenied(
                f"Access denied for agent '{agent_id}' to tool '{tool_id}'."
            )

        binding = (
            self._session.query(ToolBindingRecord)
            .filter(
                ToolBindingRecord.agent_id  == agent_id,
                ToolBindingRecord.tool_id   == tool_id,
                ToolBindingRecord.product_id == product_id,
            )
            .first()
        )

        # Unseal the stored credential if a vault is configured.
        # The plaintext is returned in the ticket for Layer 4 consumption.
        # If no vault is present the stored ref is returned as-is (legacy/test path).
        credential_ref = binding.vaulted_credentials_ref
        if credential_ref is not None and self._vault is not None:
            credential_ref = self._vault.unseal(product_id, credential_ref)

        return CredentialTicket(
            ticket_id               = str(uuid.uuid4()),
            agent_id                = agent_id,
            tool_id                 = tool_id,
            product_id              = product_id,
            vaulted_credentials_ref = credential_ref,
        )
