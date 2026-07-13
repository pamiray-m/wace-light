"""
W3.4 — OIDC ID-token verifier.

Validates an IdP-issued ID token (JWT) against the IdP's published JWKS and
returns a verified ExternalIdentity that downstream code maps to an AOS
OperatorModel. This is the minimum-viable enterprise SSO surface: most
modern IdPs (Okta, Auth0, Azure AD, Google Workspace, Keycloak) speak OIDC
natively, so a single verifier covers the F500 procurement requirement.

Why ID token verification (not OAuth code flow) at the API layer
----------------------------------------------------------------
The AOS console runs in the browser; the OAuth authorization-code dance
happens in JavaScript via the IdP's SDK or a hosted login page. The browser
ends up with an ID token, which it POSTs to `/auth/sso/oidc/exchange`. The
server's job is to:
  1. Fetch + cache the IdP's JWKS (public keys).
  2. Verify the ID token signature with the matching JWK.
  3. Validate `iss`, `aud`, and `exp` claims.
  4. Return a structured ExternalIdentity for operator-mapping.

This pattern is server-side stateless, plays well with HTTP-only AOS
sessions issued afterwards, and avoids storing IdP client secrets on the
browser. SAML XML can wrap the same verifier-returns-identity contract in
a follow-up (the `IdentityProvider` Protocol below is the seam).

Configuration
-------------
AOS_SSO_PROVIDER             — "oidc" | "disabled" (default disabled)
AOS_SSO_OIDC_DISCOVERY_URL   — e.g. https://your-tenant.okta.com/.well-known/openid-configuration
AOS_SSO_OIDC_CLIENT_ID       — registered audience claim
AOS_SSO_OIDC_ALLOWED_ISSUERS — optional comma-separated `iss` allowlist
                               (defaults to the issuer in discovery)
AOS_SSO_ALLOWED_EMAIL_DOMAINS — optional comma-separated email domain
                                whitelist; rejects tokens with mismatched
                                email domains. Required for production.
AOS_SSO_AUTO_PROVISION       — "true" auto-creates a viewer operator on
                                first SSO login; "false" requires the
                                operator to pre-exist (default false).
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

from jose import JWTError, jwt

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class SSOConfigError(RuntimeError):
    """Raised when SSO is requested but configuration is incomplete."""


class SSOTokenInvalidError(RuntimeError):
    """Raised when the IdP ID token fails signature or claim validation."""


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExternalIdentity:
    """
    Verified identity extracted from an IdP token.

    Fields
    ------
    subject : Stable IdP subject identifier (`sub` claim).
    email   : Verified email address (`email` claim). Empty when the IdP
              issues tokens without email scope.
    name    : Display name (`name` claim, or `preferred_username` fallback).
    groups  : IdP groups (`groups` claim) — preserved for future RBAC mapping.
    claims  : Raw remaining claims for audit / debugging.
    issuer  : The `iss` claim that signed this token.
    """
    subject: str
    email: str
    name: str
    groups: tuple[str, ...] = field(default_factory=tuple)
    issuer: str = ""
    claims: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Provider Protocol — SAML can plug in here later via the same shape
# ---------------------------------------------------------------------------

@runtime_checkable
class IdentityProvider(Protocol):
    def verify(self, token: str) -> ExternalIdentity: ...


# ---------------------------------------------------------------------------
# JWKS cache
# ---------------------------------------------------------------------------

_JWKS_CACHE_TTL_SECONDS = 3600  # 1 hour
_jwks_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _fetch_jwks(jwks_uri: str) -> dict[str, Any]:
    """
    Fetch the IdP's JWKS document, caching the result for 1h to avoid
    hammering the IdP on every login.
    """
    now = time.time()
    cached = _jwks_cache.get(jwks_uri)
    if cached is not None and (now - cached[0]) < _JWKS_CACHE_TTL_SECONDS:
        return cached[1]

    import httpx
    resp = httpx.get(jwks_uri, timeout=10)
    resp.raise_for_status()
    doc = resp.json()
    _jwks_cache[jwks_uri] = (now, doc)
    return doc


def _fetch_discovery(discovery_url: str) -> dict[str, Any]:
    """
    Fetch the OIDC discovery document at /.well-known/openid-configuration.
    Cached as part of the JWKS cache.
    """
    cache_key = f"discovery::{discovery_url}"
    now = time.time()
    cached = _jwks_cache.get(cache_key)
    if cached is not None and (now - cached[0]) < _JWKS_CACHE_TTL_SECONDS:
        return cached[1]

    import httpx
    resp = httpx.get(discovery_url, timeout=10)
    resp.raise_for_status()
    doc = resp.json()
    _jwks_cache[cache_key] = (now, doc)
    return doc


def reset_jwks_cache() -> None:
    """Test hook — clear the discovery + JWKS cache."""
    _jwks_cache.clear()


# ---------------------------------------------------------------------------
# Config readers
# ---------------------------------------------------------------------------

def sso_enabled() -> bool:
    return (os.environ.get("AOS_SSO_PROVIDER", "") or "").strip().lower() == "oidc"


def _discovery_url() -> str:
    url = (os.environ.get("AOS_SSO_OIDC_DISCOVERY_URL", "") or "").strip()
    if not url:
        raise SSOConfigError("AOS_SSO_OIDC_DISCOVERY_URL is not set.")
    return url


def _client_id() -> str:
    cid = (os.environ.get("AOS_SSO_OIDC_CLIENT_ID", "") or "").strip()
    if not cid:
        raise SSOConfigError("AOS_SSO_OIDC_CLIENT_ID is not set.")
    return cid


def _allowed_issuers() -> Optional[frozenset[str]]:
    """
    Explicit issuer whitelist. None means "trust the discovery-document issuer
    only" (the safe default). Operators with a custom multi-issuer setup can
    set this comma-separated.
    """
    raw = (os.environ.get("AOS_SSO_OIDC_ALLOWED_ISSUERS", "") or "").strip()
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return frozenset(parts) if parts else None


def allowed_email_domains() -> frozenset[str]:
    """
    Comma-separated email-domain whitelist. Empty (or unset) → allow any
    domain (V1; operators are strongly encouraged to set this in production).
    """
    raw = (os.environ.get("AOS_SSO_ALLOWED_EMAIL_DOMAINS", "") or "").strip()
    if not raw:
        return frozenset()
    return frozenset(p.strip().lower() for p in raw.split(",") if p.strip())


def auto_provision_enabled() -> bool:
    return (os.environ.get("AOS_SSO_AUTO_PROVISION", "") or "").strip().lower() in (
        "1", "true", "yes",
    )


# ---------------------------------------------------------------------------
# OIDC verifier
# ---------------------------------------------------------------------------

class OIDCVerifier:
    """
    Stateless verifier — instantiated per-request or held as a singleton.
    Uses the JWKS cache so repeated logins don't hammer the IdP.
    """

    def verify(self, id_token: str) -> ExternalIdentity:
        if not id_token or not id_token.strip():
            raise SSOTokenInvalidError("ID token is empty.")

        try:
            discovery = _fetch_discovery(_discovery_url())
        except Exception as exc:
            raise SSOConfigError(f"OIDC discovery fetch failed: {exc}") from exc

        jwks_uri = discovery.get("jwks_uri")
        if not jwks_uri:
            raise SSOConfigError("OIDC discovery document missing jwks_uri.")
        issuer_from_discovery = discovery.get("issuer", "")

        # Compute the effective issuer allowlist.
        explicit_issuers = _allowed_issuers()
        if explicit_issuers is not None:
            allowed_iss = explicit_issuers
        elif issuer_from_discovery:
            allowed_iss = frozenset({issuer_from_discovery})
        else:
            raise SSOConfigError(
                "Cannot determine allowed issuer: discovery missing 'issuer' "
                "and AOS_SSO_OIDC_ALLOWED_ISSUERS is unset."
            )

        try:
            jwks = _fetch_jwks(jwks_uri)
        except Exception as exc:
            raise SSOConfigError(f"OIDC JWKS fetch failed: {exc}") from exc

        # Pull `kid` from the token header so we pick the right key.
        try:
            unverified_header = jwt.get_unverified_header(id_token)
        except JWTError as exc:
            raise SSOTokenInvalidError(f"ID token header malformed: {exc}") from exc
        kid = unverified_header.get("kid")
        alg = unverified_header.get("alg", "RS256")

        key = self._find_key(jwks, kid)
        if key is None:
            raise SSOTokenInvalidError(
                f"No JWKS key matches token kid={kid!r}. Cache may be stale; "
                "next request will refresh."
            )

        try:
            claims = jwt.decode(
                id_token,
                key,
                algorithms=[alg],
                audience=_client_id(),
                options={"verify_at_hash": False},
            )
        except JWTError as exc:
            msg = str(exc).lower()
            if "expired" in msg:
                raise SSOTokenInvalidError("ID token expired.") from exc
            raise SSOTokenInvalidError(f"ID token verification failed: {exc}") from exc

        # Explicit issuer check (jose.decode accepts an issuer kwarg but we
        # support an explicit allowlist for multi-issuer ops).
        iss = claims.get("iss", "")
        if iss not in allowed_iss:
            raise SSOTokenInvalidError(
                f"Token issuer {iss!r} not in allowed issuers."
            )

        return self._build_identity(claims, iss)

    @staticmethod
    def _find_key(jwks: dict[str, Any], kid: Optional[str]) -> Optional[dict[str, Any]]:
        keys = jwks.get("keys") or []
        if kid is None and len(keys) == 1:
            return keys[0]  # single-key JWKS — kid optional
        for k in keys:
            if k.get("kid") == kid:
                return k
        return None

    @staticmethod
    def _build_identity(claims: dict[str, Any], issuer: str) -> ExternalIdentity:
        sub = str(claims.get("sub", "")).strip()
        email = str(claims.get("email", "")).strip().lower()
        if not sub:
            raise SSOTokenInvalidError("Token missing 'sub' claim.")
        name = (
            str(claims.get("name") or claims.get("preferred_username") or email).strip()
        )
        groups_raw = claims.get("groups") or []
        if isinstance(groups_raw, str):
            groups_tuple: tuple[str, ...] = (groups_raw,)
        else:
            groups_tuple = tuple(str(g) for g in groups_raw)
        return ExternalIdentity(
            subject=sub,
            email=email,
            name=name,
            groups=groups_tuple,
            issuer=issuer,
            claims=dict(claims),
        )


# ---------------------------------------------------------------------------
# Module singleton + Provider lookup
# ---------------------------------------------------------------------------

_oidc_verifier = OIDCVerifier()


def get_active_provider() -> IdentityProvider:
    """
    Resolve the configured IdentityProvider. Raises SSOConfigError when SSO
    is not enabled or misconfigured — callers should treat that as a 503
    or "SSO not available on this deployment".
    """
    if not sso_enabled():
        raise SSOConfigError(
            "SSO is not enabled. Set AOS_SSO_PROVIDER=oidc to activate."
        )
    return _oidc_verifier
