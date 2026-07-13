"""
W3.8 — SOC2 runtime readiness manifest.

Real-time aggregation of "where do we stand?" signals across every governance
feature shipped in W3.1–W3.7. Operators run `GET /governance/soc2/readiness`
to get a single red/yellow/green snapshot they can paste into a kickoff deck
or hand to an internal compliance lead before paying for an auditor.

This module is intentionally pure — it reads env vars + module-level state
and never mutates anything. Safe to call on every request.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal


SignalStatus = Literal["green", "yellow", "red"]


@dataclass(frozen=True)
class ReadinessSignal:
    """One named readiness check with status + a short reason."""
    name:    str
    status:  SignalStatus
    reason:  str
    detail:  dict


def _green(name: str, reason: str, **detail) -> ReadinessSignal:
    return ReadinessSignal(name=name, status="green", reason=reason, detail=detail)


def _yellow(name: str, reason: str, **detail) -> ReadinessSignal:
    return ReadinessSignal(name=name, status="yellow", reason=reason, detail=detail)


def _red(name: str, reason: str, **detail) -> ReadinessSignal:
    return ReadinessSignal(name=name, status="red", reason=reason, detail=detail)


# ---------------------------------------------------------------------------
# Individual signal checks
# ---------------------------------------------------------------------------

def _check_sso() -> ReadinessSignal:
    """W3.4 — OIDC SSO must be enabled for enterprise procurement."""
    try:
        from src.core.auth.sso.oidc import (
            allowed_email_domains, auto_provision_enabled, sso_enabled,
        )
    except Exception as exc:
        return _red("sso_enabled", f"SSO module import failed: {exc}", error=str(exc))

    if not sso_enabled():
        return _red(
            "sso_enabled",
            "SSO is disabled. Federated IdP login required for SOC2 Type I.",
            provider=os.environ.get("AOS_SSO_PROVIDER", ""),
        )
    domains = allowed_email_domains()
    if not domains:
        return _yellow(
            "sso_enabled",
            "SSO is on but AOS_SSO_ALLOWED_EMAIL_DOMAINS is unset — any IdP-signed email can log in.",
        )
    return _green(
        "sso_enabled",
        "OIDC SSO active with email domain whitelist.",
        domains=sorted(domains),
        auto_provision=auto_provision_enabled(),
    )


def _check_audit_export() -> ReadinessSignal:
    """W3.5 — audit export secret must be set for tamper-proof evidence."""
    secret = (os.environ.get("AOS_AUDIT_HMAC_SECRET", "") or "").strip()
    if not secret:
        return _red(
            "audit_export_hmac",
            "AOS_AUDIT_HMAC_SECRET is unset. /governance/audit/export will 503.",
        )
    if len(secret) < 32:
        return _red(
            "audit_export_hmac",
            f"AOS_AUDIT_HMAC_SECRET is too short ({len(secret)} chars; min 32).",
        )
    return _green(
        "audit_export_hmac",
        "Audit HMAC secret configured with sufficient length.",
        secret_length=len(secret),
    )


def _check_governance_profile() -> ReadinessSignal:
    """W3.1 — strict profile is the production target."""
    try:
        from src.config.loader import _governance_profile
        profile = _governance_profile()
    except Exception as exc:
        return _red("governance_profile", f"Profile resolution failed: {exc}")

    if profile == "strict":
        return _green(
            "governance_profile",
            "Governance profile is STRICT — all four enforcement modes active.",
            profile=profile,
        )
    return _yellow(
        "governance_profile",
        f"Profile is {profile!r}. Production target is `strict`.",
        profile=profile,
    )


def _check_sal_ve_gate() -> ReadinessSignal:
    """W3.2 — SAL gate on VE-5 should be enabled in production."""
    try:
        from src.sal.ve_bridge import is_ve_gate_enabled
        enabled = is_ve_gate_enabled()
    except Exception as exc:
        return _red("sal_ve_gate", f"SAL bridge import failed: {exc}")
    if enabled:
        return _green("sal_ve_gate", "SAL is gating venture governance decisions.")
    return _yellow(
        "sal_ve_gate",
        "SAL VE gate is OFF. Set AOS_SAL_VE_GATE_ENABLED=true (or strict profile).",
    )


def _check_aa_proposal_gate() -> ReadinessSignal:
    """W3.3 — AA gate on proposal application should be enabled."""
    try:
        from src.sal_auto.proposal_bridge import (
            is_aa_proposal_enforce_enabled,
            is_aa_proposal_gate_enabled,
        )
        gate    = is_aa_proposal_gate_enabled()
        enforce = is_aa_proposal_enforce_enabled()
    except Exception as exc:
        return _red("aa_proposal_gate", f"AA bridge import failed: {exc}")
    if gate and enforce:
        return _green(
            "aa_proposal_gate",
            "AA gate is ON in enforce mode — blocked verdicts hard-stop apply.",
            gate_enabled=True, enforce_enabled=True,
        )
    if gate:
        return _yellow(
            "aa_proposal_gate",
            "AA gate is ON in observe-only mode. Flip AOS_AA_PROPOSAL_GATE_ENFORCE=true to enforce.",
            gate_enabled=True, enforce_enabled=False,
        )
    return _yellow(
        "aa_proposal_gate",
        "AA gate is OFF. Set AOS_AA_PROPOSAL_GATE_ENABLED=true (or strict profile).",
        gate_enabled=False, enforce_enabled=False,
    )


def _check_tenant_isolation() -> ReadinessSignal:
    """W3.6 — every governance table must have a tenant-scoping decision."""
    try:
        from src.core.audit.tenant_isolation import summary as iso_summary
        s = iso_summary()
    except Exception as exc:
        return _red("tenant_isolation", f"Tenant matrix import failed: {exc}")
    if s["review_required"] > 0:
        return _red(
            "tenant_isolation",
            f"{s['review_required']} table(s) flagged review_required.",
            **s,
        )
    return _green(
        "tenant_isolation",
        f"{s['tenant_scoped']} tenant-scoped tables, {s['global']} intentionally global, 0 unreviewed.",
        **s,
    )


def _check_jwt_secret() -> ReadinessSignal:
    """CC6.1 — JWT secret must be present + sufficiently long."""
    secret = (os.environ.get("AOS_JWT_SECRET", "") or "").strip()
    if not secret:
        return _red("jwt_secret", "AOS_JWT_SECRET is unset. Login will fail.")
    if len(secret) < 32:
        return _red("jwt_secret", f"AOS_JWT_SECRET too short ({len(secret)} chars).")
    return _green("jwt_secret", "JWT signing secret configured.", length=len(secret))


def _check_egl_tiers_configured() -> ReadinessSignal:
    """W3.7 — EGL tier model loadable."""
    try:
        from src.aos.governance_customer.tiers import all_tiers
        tiers = all_tiers()
    except Exception as exc:
        return _red("egl_tiers", f"Tier model import failed: {exc}")
    if len(tiers) != 3:
        return _yellow(
            "egl_tiers",
            f"Expected 3 tiers, got {len(tiers)}.",
            tier_count=len(tiers),
        )
    return _green(
        "egl_tiers",
        "EGL pricing tiers (FREE/PRO/ENTERPRISE) loaded.",
        tier_count=len(tiers),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def collect_signals() -> list[ReadinessSignal]:
    """Run every readiness check and return the structured signal list."""
    return [
        _check_jwt_secret(),
        _check_sso(),
        _check_audit_export(),
        _check_governance_profile(),
        _check_sal_ve_gate(),
        _check_aa_proposal_gate(),
        _check_tenant_isolation(),
        _check_egl_tiers_configured(),
    ]


def _overall_status(signals: list[ReadinessSignal]) -> SignalStatus:
    """Worst-of-all: any RED → red, any YELLOW → yellow, else green."""
    if any(s.status == "red" for s in signals):
        return "red"
    if any(s.status == "yellow" for s in signals):
        return "yellow"
    return "green"


def readiness_dict() -> dict:
    """Build the JSON-serializable readiness response."""
    signals = collect_signals()
    return {
        "overall_status": _overall_status(signals),
        "signal_counts": {
            "green":  sum(1 for s in signals if s.status == "green"),
            "yellow": sum(1 for s in signals if s.status == "yellow"),
            "red":    sum(1 for s in signals if s.status == "red"),
        },
        "signals": [
            {
                "name":   s.name,
                "status": s.status,
                "reason": s.reason,
                "detail": s.detail,
            }
            for s in signals
        ],
    }
