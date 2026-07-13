"""
H1 — JWT access token generation and verification.

All tokens are signed with HMAC-SHA256 (HS256).  The signing secret is read
from the central config (AOS_JWT_SECRET env var, loaded via src.config).
The application fails fast at startup if the variable is absent — hardcoded
secrets are not permitted.

Token claims
------------
sub         : operator_id  (unique identifier, used for lookup)
username    : human-readable name (carried in token to avoid DB round-trip)
role        : OperatorRole value string
product_scope : str or null
stream_scope  : str or null
exp         : UNIX timestamp (UTC) at which the token expires
iat         : UNIX timestamp of issuance

Assumptions (H1)
----------------
- Only access tokens are implemented.  Refresh tokens are an H2+ concern.
- Token revocation (blocklist) is not implemented at H1.
- The secret must be at least 32 characters; shorter values are rejected.

P2 note
-------
This module no longer reads os.environ directly.  All configuration is
accessed through get_settings() from src.config.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from src.core.auth.models import OperatorIdentity, OperatorRole

# ---------------------------------------------------------------------------
# Module-level constants (non-secret)
# ---------------------------------------------------------------------------

_ALGORITHM = "HS256"
_MIN_SECRET_LEN = 32
_DEFAULT_EXPIRY_MINUTES = 60


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_secret() -> str:
    """
    Return the JWT signing secret from config.

    Raises RuntimeError with a clear message if the secret is absent or
    too short.  Called on every token operation so that tests using
    monkeypatch.setenv("AOS_JWT_SECRET", ...) pick up the value without
    any cache invalidation.
    """
    from src.config import get_settings
    secret = get_settings().auth.jwt_secret
    if not secret:
        raise RuntimeError(
            "AOS_JWT_SECRET is not set. "
            "The AOS auth layer requires a cryptographic signing secret."
        )
    if len(secret) < _MIN_SECRET_LEN:
        raise RuntimeError(
            f"AOS_JWT_SECRET must be at least {_MIN_SECRET_LEN} characters long "
            f"(got {len(secret)})."
        )
    return secret


# ---------------------------------------------------------------------------
# Public exceptions
# ---------------------------------------------------------------------------

class TokenExpiredError(Exception):
    """Raised when a token's exp claim is in the past."""


class TokenInvalidError(Exception):
    """Raised for any structurally invalid or tampered token."""


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------

def create_access_token(
    identity: OperatorIdentity,
    expires_minutes: int | None = None,
    *,
    session_id: str | None = None,
) -> str:
    """
    Create and sign a JWT access token for *identity*.

    Parameters
    ----------
    identity        : Verified OperatorIdentity to embed in claims.
    expires_minutes : Token lifetime in minutes.  Defaults to the configured
                      AOS_JWT_EXPIRY_MINUTES value (fallback: 15 minutes).
    session_id      : P5 — session UUID embedded as the "sid" claim.  When
                      present, get_current_identity() validates the session
                      record on every request (revocation enforcement).

    Returns
    -------
    Signed JWT string (compact serialization).
    """
    from src.config import get_settings
    secret = _load_secret()

    ttl = expires_minutes
    if ttl is None:
        ttl = get_settings().auth.jwt_expiry_minutes

    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=ttl)

    claims: dict[str, Any] = {
        "sub": identity.operator_id,
        "username": identity.username,
        "role": identity.role.value,
        "product_scope": identity.product_scope,
        "stream_scope": identity.stream_scope,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if session_id:
        claims["sid"] = session_id

    return jwt.encode(claims, secret, algorithm=_ALGORITHM)


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------

def verify_access_token(token: str) -> OperatorIdentity:
    """
    Verify *token* and return the embedded OperatorIdentity.

    Raises
    ------
    TokenExpiredError  — token has passed its expiry timestamp.
    TokenInvalidError  — token is malformed, signature invalid, or missing claims.
    """
    secret = _load_secret()

    try:
        payload = jwt.decode(token, secret, algorithms=[_ALGORITHM])
    except JWTError as exc:
        # python-jose raises ExpiredSignatureError (subclass of JWTError) for
        # expired tokens, and other JWTError subclasses for tampered/malformed ones.
        msg = str(exc).lower()
        if "expired" in msg or "exp" in msg:
            raise TokenExpiredError("Access token has expired.") from exc
        raise TokenInvalidError(f"Token is invalid: {exc}") from exc

    # Validate required claims are present
    missing = [f for f in ("sub", "username", "role") if f not in payload]
    if missing:
        raise TokenInvalidError(f"Token is missing required claims: {missing}")

    try:
        role = OperatorRole(payload["role"])
    except ValueError:
        raise TokenInvalidError(f"Unknown role in token: {payload['role']!r}")

    return OperatorIdentity(
        operator_id=payload["sub"],
        username=payload["username"],
        role=role,
        product_scope=payload.get("product_scope"),
        stream_scope=payload.get("stream_scope"),
        session_id=payload.get("sid"),   # P5: may be None for pre-P5 tokens
    )
