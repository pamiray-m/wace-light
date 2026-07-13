"""
Voundry standalone-app authentication — accounts, register/login, JWT, principal.

This is the auth layer for the standalone Voundry app (voundry.aos-1.com), distinct
from AOS-1's operator auth. External users (founders, contributors, investors)
register and log in here; the operator/governor still uses the AOS-1 admin console.

Reuses AOS-1 crypto primitives (bcrypt via src.core.auth.password, HS256 JWT signed
with the same AOS_JWT_SECRET) — no new cryptography is invented. Voundry tokens carry
Voundry-specific claims (role + linked contributor_id/investor_id) under a distinct
issuer/audience so they can't be confused with operator tokens.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional
import uuid

from jose import jwt as jose_jwt

from src.config import get_settings
from src.core.auth.password import hash_password, verify_password
from src.aos.voundry.contracts import ContributorTier
from src.aos.voundry.contributor import contributor_service
from src.aos.voundry.governance import voundry_audit
from src.aos.voundry.persistence.repository import voundry_repo

_ALG = "HS256"
_ISS = "voundry"
_AUD = "voundry-app"
_TTL_MIN = 720  # 12h
_RESET_TTL_MIN = 30
_RESET_AUD = "voundry-pwreset"

TERMS_VERSION = "1.0"  # bump when contributor terms change → re-consent required


class VoundryRole(str, Enum):
    FOUNDER     = "founder"
    CONTRIBUTOR = "contributor"
    INVESTOR    = "investor"
    OPERATOR    = "operator"


# Roles a member of the public may self-register as (OPERATOR is never self-serve).
# INVESTOR self-registration is hidden in the investor-less pivot; the code is
# preserved behind an env flag for a possible Phase 2 re-enable.
_BASE_SELF_REGISTERABLE = {VoundryRole.FOUNDER, VoundryRole.CONTRIBUTOR}


def _investor_signup_enabled() -> bool:
    return os.environ.get("AOS_VOUNDRY_INVESTOR_SIGNUP", "").strip().lower() in {"1", "true", "on"}


def self_registerable_roles() -> set[VoundryRole]:
    roles = set(_BASE_SELF_REGISTERABLE)
    if _investor_signup_enabled():
        roles.add(VoundryRole.INVESTOR)
    return roles


# Backwards-compatible name (evaluated dynamically in register()).
SELF_REGISTERABLE = _BASE_SELF_REGISTERABLE | {VoundryRole.INVESTOR}


@dataclass(frozen=True)
class VoundryPrincipal:
    """What authenticated Voundry-app routes receive. Never carries the password."""
    account_id: str
    email: str
    role: VoundryRole
    display_name: str
    contributor_id: Optional[str]
    investor_id: Optional[str]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class VoundryAuthError(Exception):
    pass


class EmailTaken(VoundryAuthError):
    pass


class InvalidCredentials(VoundryAuthError):
    pass


class InvalidToken(VoundryAuthError):
    pass


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _secret() -> str:
    secret = get_settings().auth.jwt_secret
    if not secret:
        raise VoundryAuthError("AOS_JWT_SECRET is not configured")
    return secret


class VoundryAuthService:
    def __init__(self, repo=voundry_repo, audit=voundry_audit) -> None:
        self._repo = repo
        self._audit = audit

    # -- token --------------------------------------------------------------

    def issue_token(self, account: dict) -> str:
        now = _now()
        claims = {
            "iss": _ISS, "aud": _AUD,
            "sub": account["account_id"],
            "email": account["email"],
            "role": account["role"],
            "cid": account.get("contributor_id"),
            "iid": account.get("investor_id"),
            "name": account.get("display_name", ""),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=_TTL_MIN)).timestamp()),
        }
        return jose_jwt.encode(claims, _secret(), algorithm=_ALG)

    def principal_from_token(self, token: str) -> VoundryPrincipal:
        try:
            payload = jose_jwt.decode(token, _secret(), algorithms=[_ALG], audience=_AUD, issuer=_ISS)
        except Exception as exc:  # jose raises JWTError subclasses
            raise InvalidToken(str(exc))
        try:
            return VoundryPrincipal(
                account_id=payload["sub"], email=payload["email"],
                role=VoundryRole(payload["role"]), display_name=payload.get("name", ""),
                contributor_id=payload.get("cid"), investor_id=payload.get("iid"),
            )
        except (KeyError, ValueError) as exc:
            raise InvalidToken(f"malformed claims: {exc}")

    # -- register / login ---------------------------------------------------

    def register(
        self, *, email: str, password: str, role: VoundryRole, display_name: str = "",
        accepted_terms: bool = False, ip_address: str = "", user_agent: str = "",
    ) -> tuple[VoundryPrincipal, str]:
        email = email.strip().lower()
        if not email or "@" not in email:
            raise VoundryAuthError("A valid email is required")
        if len(password) < 8:
            raise VoundryAuthError("Password must be at least 8 characters")
        if not accepted_terms:
            raise VoundryAuthError("You must accept the Voundry contributor terms to register")
        if role not in self_registerable_roles():
            raise VoundryAuthError(f"Role '{role.value}' cannot be self-registered")
        if self._repo.get_voundry_account_by_email(email) is not None:
            raise EmailTaken(email)

        account_id = str(uuid.uuid4())
        contributor_id = account_id if role == VoundryRole.CONTRIBUTOR else None
        investor_id = account_id if role == VoundryRole.INVESTOR else None
        account = {
            "account_id": account_id, "email": email,
            "hashed_password": hash_password(password), "role": role.value,
            "display_name": display_name or email.split("@")[0],
            "contributor_id": contributor_id, "investor_id": investor_id,
            "accepted_terms": True, "terms_version": TERMS_VERSION,
            "accepted_at": _now().isoformat(),
            "created_at": _now().isoformat(),
        }
        self._repo.save_voundry_account(account)

        # Auto-provision the linked domain record.
        if role == VoundryRole.CONTRIBUTOR:
            contributor_service.register(
                contributor_id, display_name=account["display_name"], tier=ContributorTier.APPLICANT,
            )

        self._audit.append(
            actor_id=account_id, actor_type="human", action="account.registered",
            resource_type="account", resource_id=account_id,
            detail=f"{role.value} terms={TERMS_VERSION}",
        )

        # The commercial edition auto-signs a versioned legal pack here. The
        # open-source individual edition has no contributor agreements, so this
        # is a no-op when the legal module is absent.
        try:
            from src.aos.voundry.legal import legal_consent_service
            for doc in legal_consent_service.ensure_platform_pack():
                legal_consent_service.sign_document(
                    account_id=account_id, document_id=doc.id,
                    typed_name=account["display_name"],
                    ip_address=ip_address, user_agent=user_agent,
                )
        except ImportError:
            pass

        try:  # fire-and-forget welcome email
            from src.aos.voundry.notifications import voundry_notifier
            voundry_notifier.send_welcome(account)
        except Exception:  # pragma: no cover
            pass
        return self._principal(account), self.issue_token(account)

    # -- Password reset -----------------------------------------------------

    def request_password_reset(self, *, email: str) -> bool:
        """Email a reset link if the account exists. Always returns True (no
        account-existence leak). The token is a short-lived signed JWT."""
        account = self._repo.get_voundry_account_by_email(email.strip().lower())
        if account is not None:
            now = _now()
            token = jose_jwt.encode(
                {"iss": _ISS, "aud": _RESET_AUD, "sub": account["account_id"],
                 "iat": int(now.timestamp()),
                 "exp": int((now + timedelta(minutes=_RESET_TTL_MIN)).timestamp())},
                _secret(), algorithm=_ALG,
            )
            try:
                from src.aos.voundry.notifications import _send, _wrap, _app_url
                link = f"{_app_url()}?reset={token}"
                _send(account["email"], "Reset your Voundry password",
                      _wrap("Password reset",
                            "<p>Use the button below to set a new password. "
                            f"This link expires in {_RESET_TTL_MIN} minutes.</p>",
                            "Reset password", link))
            except Exception:  # pragma: no cover
                pass
        return True

    def reset_password(self, *, token: str, new_password: str) -> None:
        if len(new_password) < 8:
            raise VoundryAuthError("Password must be at least 8 characters")
        try:
            payload = jose_jwt.decode(token, _secret(), algorithms=[_ALG], audience=_RESET_AUD, issuer=_ISS)
        except Exception as exc:
            raise InvalidToken(f"invalid or expired reset token: {exc}")
        account = self._repo.get_voundry_account(payload.get("sub", ""))
        if account is None:
            raise InvalidToken("account not found")
        account["hashed_password"] = hash_password(new_password)
        self._repo.save_voundry_account(account)
        self._audit.append(
            actor_id=account["account_id"], actor_type="human", action="password.reset",
            resource_type="account", resource_id=account["account_id"],
        )

    def login(self, *, email: str, password: str) -> tuple[VoundryPrincipal, str]:
        email = email.strip().lower()
        account = self._repo.get_voundry_account_by_email(email)
        if account is None or not verify_password(password, account.get("hashed_password", "")):
            raise InvalidCredentials("Invalid email or password")
        return self._principal(account), self.issue_token(account)

    def get_account(self, account_id: str) -> Optional[dict]:
        return self._repo.get_voundry_account(account_id)

    @staticmethod
    def _principal(account: dict) -> VoundryPrincipal:
        return VoundryPrincipal(
            account_id=account["account_id"], email=account["email"],
            role=VoundryRole(account["role"]), display_name=account.get("display_name", ""),
            contributor_id=account.get("contributor_id"), investor_id=account.get("investor_id"),
        )


voundry_auth_service = VoundryAuthService()
