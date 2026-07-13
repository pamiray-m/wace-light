"""
Enumerations for the Integration Governance System (Packet 10).

ToolStatus        — approval/lifecycle states for a tool definition in the catalog.
SecurityLevel     — risk classification for third-party tool connectors.
ToolCategory      — functional category grouping for catalog organization.
IntegrationAuthority — who may authorize integration lifecycle transitions.

Design note
-----------
IntegrationAuthority mirrors the authority taxonomy from Packet 8 (SkillAuthority)
but adds INTEGRATION_GOVERNOR — the new Layer 1 role introduced in the architecture
document for owning integration policy.  It is intentionally a separate enum so
that Packet 10 governance rules are decoupled from skill lifecycle rules.
"""

from __future__ import annotations

from enum import Enum


class ToolStatus(str, Enum):
    """
    Approval lifecycle for a ToolDefinition in the integration catalog.

    State machine (see governor.py TRANSITION_RULES):
      DISCOVERED → PROPOSED → REVIEWED → APPROVED → ENABLED
      ENABLED ↔ DISABLED  (temporary suspension)
      Any non-terminal → REVOKED  (forced removal by governance)
    """
    DISCOVERED  = "DISCOVERED"   # tool known but not yet submitted for governance
    PROPOSED    = "PROPOSED"     # submitted for review
    REVIEWED    = "REVIEWED"     # technical/legal review complete, awaiting approval
    APPROVED    = "APPROVED"     # governance-approved, not yet enabled for agent use
    ENABLED     = "ENABLED"      # active — agents may be bound to this tool
    DISABLED    = "DISABLED"     # temporarily suspended, bindings frozen
    REVOKED     = "REVOKED"      # permanently removed; terminal state


class SecurityLevel(str, Enum):
    """Risk classification assigned to a tool during catalog registration."""
    LOW      = "LOW"       # read-only or informational connectors
    MEDIUM   = "MEDIUM"    # write actions; limited credential scope
    HIGH     = "HIGH"      # broad write/delete; requires elevated approval
    CRITICAL = "CRITICAL"  # production finance/legal/data systems; sovereignty-only approval


class ToolCategory(str, Enum):
    """Functional grouping for catalog organisation and entitlement policy."""
    AUTOMATION    = "AUTOMATION"    # e.g. Zapier, Make
    CRM           = "CRM"           # e.g. HubSpot, Salesforce
    COMMUNICATION = "COMMUNICATION" # e.g. Slack, email APIs
    DATA          = "DATA"          # e.g. Apollo, databases
    ANALYTICS     = "ANALYTICS"     # reporting/BI connectors
    PRODUCTIVITY  = "PRODUCTIVITY"  # e.g. Notion, Google Workspace
    OTHER         = "OTHER"


class IntegrationAuthority(str, Enum):
    """
    Authority classes that may authorize integration lifecycle transitions.

    Layer 0 (sovereignty) has full governance rights everywhere.
    Layer 1 Integration-Governor owns the integration policy surface.
    Oracle may PROPOSE integrations but cannot APPROVE or ENABLE them —
    mirroring the Oracle restraint principle from the architecture doc.
    """
    # Layer 0 — full authority (sovereignty)
    ARCHITECT            = "Architect"
    DEPUTY               = "Deputy"

    # Layer 1 — integration governance owner
    INTEGRATION_GOVERNOR = "IntegrationGovernor"

    # Layer 1 — review/validation roles
    STANDARDS_AGENT      = "StandardsAgent"
    LAWYER               = "Lawyer"

    # Layer 1 — Oracle can propose, cannot approve/enable
    ORACLE               = "Oracle"

    # Internal system calls (seeding catalog entries programmatically)
    SYSTEM               = "System"
