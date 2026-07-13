"""
Domain exceptions for the Integration Governance System (Packet 10).

All exceptions derive from IntegrationError so callers can catch the family.

Contract reference (integration-governance-contract.md):
  "If the request originates from a rogue cross-product process, it returns a
   hard 403 Forbidden and logs a high severity event in the observability layer."
  → ProductIsolationViolation maps to 403.
  → ToolAccessDenied maps to 403 for access checks.
  → ToolNotApproved maps to 409 (binding to unapproved tool is a conflict).
"""

from __future__ import annotations


class IntegrationError(Exception):
    """Base exception for all Packet 10 domain errors."""


class ToolNotFound(IntegrationError):
    """Tool definition does not exist in the catalog."""


class ToolBindingNotFound(IntegrationError):
    """No active binding exists for the requested (agent_id, tool_id) pair."""


class ToolAccessDenied(IntegrationError):
    """
    Access evaluation returned denial.

    Raised by SecurityHooks when evaluate_access() determines the agent
    does not hold a valid binding for the requested tool.
    """


class ProductIsolationViolation(IntegrationError):
    """
    Raised when a tool assignment or access check would cross product boundaries.

    Per architecture doc §5: "Tools mapped to a Product ID fail instantly when
    requested by differing Product IDs."

    Per contract: cross-product access generates a high-severity observability event.
    """


class ToolNotApproved(IntegrationError):
    """
    Raised when attempting to bind an agent to a tool that has not been
    APPROVED or ENABLED in the catalog lifecycle.

    Bindings to DISCOVERED/PROPOSED/REVIEWED tools are forbidden until
    governance approval is complete.
    """


class DuplicateToolBinding(IntegrationError):
    """
    Raised when attempting to create a binding that already exists for
    the (agent_id, tool_id, product_id) combination.
    """


class InvalidToolTransition(IntegrationError):
    """
    Raised when a requested lifecycle transition is not permitted by the
    IntegrationGovernorEngine policy matrix.
    """


class TerminalToolError(IntegrationError):
    """Raised when attempting to transition a REVOKED tool (terminal state)."""


class UnauthorizedToolWrite(IntegrationError):
    """
    Raised when a write is attempted by an authority that does not hold
    the required permission for that lifecycle transition.
    """


# ---------------------------------------------------------------------------
# H4 — Credential Vault exceptions
# ---------------------------------------------------------------------------

class VaultError(IntegrationError):
    """Base exception for credential vault failures (H4)."""


class VaultKeyMissing(VaultError):
    """
    AOS_VAULT_KEY is not set or is not a valid base64-encoded 32-byte key.

    Raised at encryption/decryption time (lazy key loading) so that service
    startup does not require the key unless credentials are actually handled.
    """


class CredentialDecryptionError(VaultError):
    """
    Decryption failed — wrong key, wrong product_id (AES-GCM AAD mismatch),
    or corrupted ciphertext.

    A wrong product_id triggers this exception because the AAD tag embedded
    in the AES-GCM ciphertext will not verify, giving product isolation a
    cryptographic guarantee rather than just a DB-level check.
    """
