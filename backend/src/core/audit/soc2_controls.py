"""
W3.8 — SOC2 Trust Service Criteria (TSC) control inventory.

Maps each SOC2 Security-category control (CC1–CC8) to the concrete AOS
implementation that satisfies it. Auditors at Vanta/Drata kickoff meetings
ask for exactly this artifact: "show me the matrix of controls to evidence."

This module is the single source of truth — a future packet adding a new
governance feature (new RBAC role, new audit surface, etc.) updates the
relevant entry's `implementations` field so the auditor-facing matrix
stays current.

Scope
-----
Only the Security TSC category (CC1–CC8) is enumerated for V1. The other
categories (Availability A1, Confidentiality C1, Processing Integrity PI1,
Privacy P1–P8) are SOC2 Type II concerns and out of scope for the Type I
readiness pass the consultant plan targets.

Status enum
-----------
implemented — control fully satisfied by the listed implementations.
partial     — meaningful coverage, but at least one sub-criterion is a gap
              (e.g. CC6.7 data-in-transit is TLS but data-at-rest is
              database-default rather than a managed KMS).
not_applicable — control does not apply to AOS's deployment model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ControlStatus = Literal["implemented", "partial", "not_applicable"]


@dataclass(frozen=True)
class SOC2Control:
    """One TSC control with its AOS-side implementation references."""
    control_id:      str          # e.g. "CC6.1"
    category:        str          # e.g. "Logical and Physical Access Controls"
    name:            str
    description:     str
    status:          ControlStatus
    implementations: tuple[str, ...]  # AOS feature names + W-packet references
    notes:           str = ""


_INVENTORY: tuple[SOC2Control, ...] = (
    # ----- CC1 — Control Environment -----
    SOC2Control(
        control_id="CC1.1",
        category="Control Environment",
        name="Commitment to integrity and ethical values",
        description=(
            "The entity demonstrates a commitment to integrity and ethical "
            "values."
        ),
        status="implemented",
        implementations=(
            "Code of conduct documented in CLAUDE.md",
            "Founder Rami Kheir + The Board governance structure",
            "Architecture Review Layer (project_aos_arch_review)",
        ),
    ),
    SOC2Control(
        control_id="CC1.4",
        category="Control Environment",
        name="Attracts, develops, and retains competent individuals",
        description=(
            "The entity demonstrates a commitment to attract, develop, and "
            "retain competent individuals in alignment with objectives."
        ),
        status="implemented",
        implementations=(
            "Operator roles enum: ADMIN / VIEWER / AUDITOR (src/core/auth/models.py)",
            "Per-product operator scoping (product_scope / stream_scope)",
        ),
    ),

    # ----- CC2 — Communication and Information -----
    SOC2Control(
        control_id="CC2.1",
        category="Communication and Information",
        name="Obtains relevant information for control",
        description=(
            "The entity obtains or generates and uses relevant, quality "
            "information to support the functioning of internal control."
        ),
        status="implemented",
        implementations=(
            "Structured logging with correlation IDs (TelemetryMiddleware)",
            "Audit log endpoint (W3.5) GET /governance/audit/export",
            "Cockpit feed service (ML-2)",
        ),
    ),

    # ----- CC3 — Risk Assessment -----
    SOC2Control(
        control_id="CC3.2",
        category="Risk Assessment",
        name="Identifies risks to objectives",
        description=(
            "The entity identifies risks to the achievement of its objectives "
            "across the entity and analyzes risks as a basis for determining "
            "how the risks should be managed."
        ),
        status="implemented",
        implementations=(
            "SAL risk scoring (src/sal/scoring.py)",
            "VE-5 venture governance gate (src/ve/governance_gate.py)",
            "AA-1 safety envelope engine (src/sal_auto/safety_engine.py)",
        ),
    ),

    # ----- CC5 — Control Activities -----
    SOC2Control(
        control_id="CC5.2",
        category="Control Activities",
        name="Selects and develops control activities",
        description=(
            "The entity selects and develops general control activities over "
            "technology to support the achievement of objectives."
        ),
        status="implemented",
        implementations=(
            "W3.1 governance profile master switch (permissive vs strict)",
            "W3.2 SAL → VE-5 bridge enforces autonomy gates",
            "W3.3 AA → proposal-apply bridge enforces safety gates",
        ),
    ),

    # ----- CC6 — Logical and Physical Access Controls -----
    SOC2Control(
        control_id="CC6.1",
        category="Logical and Physical Access Controls",
        name="Logical access security software, infrastructure, and architectures",
        description=(
            "The entity implements logical access security software, "
            "infrastructure, and architectures over protected information "
            "assets to protect them from security events."
        ),
        status="implemented",
        implementations=(
            "JWT-based auth (src/core/auth/jwt.py) with HS256, refresh tokens",
            "Bcrypt password hashing",
            "W3.4 OIDC SSO (src/core/auth/sso/oidc.py) — federated IdP login",
            "OperatorRole RBAC (ADMIN / VIEWER / AUDITOR)",
            "Rate limiting middleware (src/api/middleware/rate_limiter.py)",
        ),
    ),
    SOC2Control(
        control_id="CC6.2",
        category="Logical and Physical Access Controls",
        name="Authorization of credentials and access rights",
        description=(
            "Prior to issuing system credentials, the entity registers and "
            "authorizes new internal and external users."
        ),
        status="implemented",
        implementations=(
            "POST /auth/login (password) and /auth/sso/oidc/exchange (W3.4)",
            "Operator pre-provisioning required by default (auto-provision opt-in)",
            "Per-customer API keys for EGL with hashed storage (gov_api_keys)",
        ),
    ),
    SOC2Control(
        control_id="CC6.3",
        category="Logical and Physical Access Controls",
        name="Manages credentials and access rights",
        description=(
            "The entity authorizes, modifies, or removes access to data, "
            "software, functions, and other protected information assets."
        ),
        status="implemented",
        implementations=(
            "DELETE /auth/logout — session revocation (P5)",
            "DELETE /governance/keys/{id} — API key revocation",
            "OperatorService.deactivate() — soft delete via is_active=False",
            "Refresh token rotation (one-time use)",
        ),
    ),
    SOC2Control(
        control_id="CC6.6",
        category="Logical and Physical Access Controls",
        name="Implements logical access controls to protect against threats",
        description=(
            "The entity implements logical access security measures to "
            "protect against threats from outside the entity's system boundaries."
        ),
        status="implemented",
        implementations=(
            "SSRF protection on webhook URLs (governance_customer)",
            "HMAC signature verification on Stripe webhooks",
            "Email domain whitelist for SSO (AOS_SSO_ALLOWED_EMAIL_DOMAINS)",
            "TLS termination at nginx (deploy/nginx.prod.conf)",
        ),
    ),
    SOC2Control(
        control_id="CC6.7",
        category="Logical and Physical Access Controls",
        name="Transmission and disposal of confidential information",
        description=(
            "The entity restricts the transmission, movement, and removal of "
            "information to authorized internal and external users."
        ),
        status="partial",
        implementations=(
            "HTTPS-only via nginx HSTS",
            "SAIb (Secure AI Bridge) masks PII before LLM calls",
            "W3.5 HMAC-signed audit exports prevent post-download tampering",
        ),
        notes=(
            "Data-at-rest encryption relies on the underlying database default "
            "(PostgreSQL TDE / SQLite file system) rather than a managed KMS. "
            "Type II audit will likely require a hosted KMS rotation policy."
        ),
    ),

    # ----- CC7 — System Operations -----
    SOC2Control(
        control_id="CC7.2",
        category="System Operations",
        name="Monitors system components for anomalies",
        description=(
            "The entity monitors system components and the operation of "
            "those components for anomalies that are indicative of malicious "
            "acts, natural disasters, and errors affecting the entity's "
            "ability to meet its objectives."
        ),
        status="implemented",
        implementations=(
            "AA-6 autonomous mission generator (W4.1) detects override/escalation/inconsistency anomalies",
            "Structured logging with correlation IDs",
            "Mission orchestration watchdog (src/aos/missions/orchestrator.py)",
            "TelemetryMiddleware logs every HTTP request",
        ),
    ),
    SOC2Control(
        control_id="CC7.3",
        category="System Operations",
        name="Evaluates security events",
        description=(
            "The entity evaluates security events to determine whether they "
            "could or have resulted in a failure of the entity to meet its "
            "objectives (security incidents) and, if so, takes actions to "
            "prevent or address such failures."
        ),
        status="implemented",
        implementations=(
            "SAL-5 autonomy audit log (sal_autonomy_audit_records)",
            "AA-5 auto-apply audit log (aa_audit_records + aa_kill_switch_records)",
            "W3.5 unified audit export with HMAC tamper evidence",
            "Login failures counter (src/core/logging/metrics)",
        ),
    ),
    SOC2Control(
        control_id="CC7.4",
        category="System Operations",
        name="Responds to identified security incidents",
        description=(
            "The entity responds to identified security incidents by executing "
            "a defined incident response program to understand, contain, "
            "remediate, and communicate security incidents, as appropriate."
        ),
        status="partial",
        implementations=(
            "AA-2 kill switch service (src/sal_auto/kill_switch.py) — emergency halt",
            "Governance freeze service — operator-controlled write halt",
            "L5 recovery & compensation engine",
        ),
        notes=(
            "Incident response RUNBOOK is not yet codified in operator docs. "
            "Recommendation: produce written IR playbook before Type I evidence collection."
        ),
    ),

    # ----- CC8 — Change Management -----
    SOC2Control(
        control_id="CC8.1",
        category="Change Management",
        name="Authorizes and tracks system changes",
        description=(
            "The entity authorizes, designs, develops or acquires, configures, "
            "documents, tests, approves, and implements changes to "
            "infrastructure, data, software, and procedures."
        ),
        status="implemented",
        implementations=(
            "GEL (Governance Execution Layer) — staged ChangeApplicationContract lifecycle",
            "GEL-3 dual-approval authority gate",
            "L3 lineage enforcement on every governance write",
            "W3.3 AA → proposal-apply bridge with observe + enforce modes",
            "Git history + 11,000+ test suite per code change",
        ),
    ),
)


def get_inventory() -> tuple[SOC2Control, ...]:
    """Return the full immutable control inventory."""
    return _INVENTORY


def inventory_dict() -> list[dict]:
    """Return the inventory as a JSON-serializable list for HTTP responses."""
    return [
        {
            "control_id":      c.control_id,
            "category":        c.category,
            "name":            c.name,
            "description":     c.description,
            "status":          c.status,
            "implementations": list(c.implementations),
            "notes":           c.notes,
        }
        for c in _INVENTORY
    ]


def summary() -> dict:
    """Counts by status — top-of-page summary for SOC2 reports."""
    counts = {"implemented": 0, "partial": 0, "not_applicable": 0}
    for c in _INVENTORY:
        counts[c.status] += 1
    return {
        "total_controls":  len(_INVENTORY),
        "implemented":     counts["implemented"],
        "partial":         counts["partial"],
        "not_applicable":  counts["not_applicable"],
        "categories":      sorted({c.category for c in _INVENTORY}),
    }
