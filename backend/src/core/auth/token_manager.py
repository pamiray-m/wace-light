"""
P4 — Token Manager.

Orchestrates the dual-token (access + refresh) lifecycle:
  - issue()   — called by POST /auth/login
  - refresh() — called by POST /auth/refresh
  - revoke()  — called by POST /auth/logout

Token design
------------
Access tokens  : Signed HS256 JWTs (existing create_access_token in jwt.py).
                 Short-lived (default 15 min; AOS_JWT_EXPIRY_MINUTES).
                 Stateless — verified by signature alone on every request.
                 Remain valid until expiry after logout; the session gate
                 only blocks refresh, not access-token use.  This is the
                 standard approach for stateless JWTs; P5+ may add a
                 per-request session check if stricter revocation is needed.

Refresh tokens : Opaque cryptographically-random 32-byte URL-safe strings.
                 Never a JWT (avoids confusion / forgery surface).
                 Only the SHA-256 hex digest is stored; the raw token is
                 returned once and never persisted.
                 Longer-lived (default 7 days; AOS_REFRESH_EXPIRY_DAYS).

Refresh token rotation
----------------------
Every call to refresh() issues a NEW refresh token and revokes the old one.
This one-time-use model limits the window for stolen-token abuse: a stolen
refresh token can only be used once before the next legitimate refresh
invalidates it.

Session invalidation triggers
------------------------------
1. Explicit logout (revoke()) — sets is_active=False, revoked_at=now.
2. Operator disabled — detected during refresh(); session revoked.
3. All-session revoke — SessionStore.revoke_all_for_operator() used by
   OperatorService when an operator is disabled or password-reset.
   (Integration with OperatorService is a thin P4 extension — see
   operator_service.py notes.)

Assumptions (P4)
----------------
- Access tokens remain valid until expiry after revocation.  Per-request
  session checks are not performed — that is P5 territory.
- One DB session is shared with OperatorService via FastAPI DI so the
  disable-detect + session-revoke is atomic within one request.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.config import get_settings
from src.core.auth.jwt import create_access_token
from src.core.auth.operator_model import OperatorModel
from src.core.auth.operator_service import OperatorNotFound, OperatorService
from src.core.auth.session_model import SessionModel
from src.core.auth.session_store import SessionStore
from src.core.logging.metrics import login_attempts, session_revocations

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------

class SessionNotFound(Exception):
    """Raised when a refresh token does not match any known session."""


class SessionRevoked(Exception):
    """Raised when the session has been explicitly revoked (logout/disable)."""


class SessionExpired(Exception):
    """Raised when the session's expires_at timestamp is in the past."""


class OperatorInactive(Exception):
    """Raised during refresh when the owning operator is disabled in the DB."""


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TokenPair:
    """Returned by issue() and refresh()."""
    access_token: str
    refresh_token: str     # raw opaque token — return to client, do not log
    expires_in_minutes: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_token(raw: str) -> str:
    """SHA-256 hex digest — stored in place of the plaintext refresh token."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _make_raw_token() -> str:
    """Generate a cryptographically-random 32-byte URL-safe token string."""
    return secrets.token_urlsafe(32)


def _as_utc(dt: datetime) -> datetime:
    """Ensure dt is timezone-aware UTC; handles naive datetimes from SQLite."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Token Manager
# ---------------------------------------------------------------------------

class TokenManager:
    """
    Dual-token lifecycle manager.

    Requires a SessionStore and OperatorService bound to the same DB session
    so that operator lookups and session mutations are in the same transaction.
    """

    def __init__(
        self,
        session_store: SessionStore,
        op_service: OperatorService,
    ) -> None:
        self._store = session_store
        self._op_svc = op_service

    # ------------------------------------------------------------------
    # Issue (login)
    # ------------------------------------------------------------------

    def issue(
        self,
        operator: OperatorModel,
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenPair:
        """
        Create a new session and issue an access + refresh token pair.

        Called by POST /auth/login after credential verification.

        Parameters
        ----------
        operator   : Authenticated OperatorModel from OperatorService.
        user_agent : Optional HTTP User-Agent header value for audit context.
        ip_address : Optional client IP for audit context.

        Returns
        -------
        TokenPair with both tokens.  The refresh_token is the raw value —
        store it nowhere; return it to the client as-is.
        """
        cfg = get_settings().auth

        raw_refresh = _make_raw_token()
        token_hash = _hash_token(raw_refresh)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=cfg.refresh_expiry_days)

        identity = OperatorService.to_identity(operator)

        # Create the session record first so we have its id for the JWT "sid" claim.
        session = SessionModel(
            operator_id=operator.id,
            refresh_token_hash=token_hash,
            issued_at=now,
            expires_at=expires_at,
            is_active=True,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        self._store.add(session)   # flush assigns session.id
        # session.id is now available (flush happened in add())

        # P5: embed session_id as "sid" claim so per-request enforcement can
        # look up and validate the session record on every authenticated call.
        access_token = create_access_token(
            identity,
            expires_minutes=cfg.jwt_expiry_minutes,
            session_id=session.id,
        )
        self._store.commit()

        login_attempts.increment()
        _log.info(
            "session.issued",
            extra={
                "event": "session.issued",
                "operator_id": operator.id,
                "session_id": session.id,
            },
        )

        return TokenPair(
            access_token=access_token,
            refresh_token=raw_refresh,
            expires_in_minutes=cfg.jwt_expiry_minutes,
        )

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self, raw_refresh_token: str) -> TokenPair:
        """
        Validate the refresh token and issue a new token pair (rotation).

        The old session is always revoked, even on failure — this prevents
        token reuse after a network hiccup causes the client to retry.

        Raises
        ------
        SessionNotFound  : token does not match any session.
        SessionRevoked   : session was already revoked (logout or disable).
        SessionExpired   : session has passed its expires_at.
        OperatorInactive : the owning operator was disabled after issuance.
        """
        token_hash = _hash_token(raw_refresh_token)
        session = self._store.get_by_token_hash(token_hash)

        if session is None:
            _log.warning("session.refresh_failed: token not recognised",
                         extra={"event": "session.refresh_failed", "reason": "not_found"})
            raise SessionNotFound("Refresh token is not recognised.")

        if not session.is_active:
            _log.warning("session.refresh_failed: session revoked",
                         extra={"event": "session.refresh_failed",
                                "reason": "revoked",
                                "operator_id": session.operator_id})
            raise SessionRevoked("Session has been revoked.")

        if datetime.now(timezone.utc) > _as_utc(session.expires_at):
            _log.warning("session.refresh_failed: session expired",
                         extra={"event": "session.refresh_failed",
                                "reason": "expired",
                                "operator_id": session.operator_id})
            raise SessionExpired("Refresh token has expired.")

        # Check the owning operator is still active
        try:
            operator = self._op_svc.get_by_id(session.operator_id)
        except OperatorNotFound:
            # Operator was deleted — revoke the orphaned session
            self._revoke_session(session)
            raise OperatorInactive("Operator no longer exists.")

        if not operator.is_active:
            self._revoke_session(session)
            _log.warning("session.refresh_failed: operator inactive",
                         extra={"event": "session.refresh_failed",
                                "reason": "operator_inactive",
                                "operator_id": operator.id})
            raise OperatorInactive(
                "Operator account is disabled. Refresh is not permitted."
            )

        # Rotate: revoke old session before issuing new one
        old_session_id = session.id
        self._revoke_session(session)
        _log.info("session.rotated",
                  extra={"event": "session.rotated",
                         "operator_id": operator.id,
                         "old_session_id": old_session_id})

        return self.issue(operator)

    # ------------------------------------------------------------------
    # Revoke (logout)
    # ------------------------------------------------------------------

    def revoke(self, raw_refresh_token: str) -> None:
        """
        Revoke the session associated with raw_refresh_token.

        Idempotent — if the token is not found or already revoked, this is
        a no-op.  Callers should always return 204 regardless.
        """
        token_hash = _hash_token(raw_refresh_token)
        session = self._store.get_by_token_hash(token_hash)
        if session is None or not session.is_active:
            return  # already gone — idempotent
        self._revoke_session(session)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _revoke_session(self, session: SessionModel) -> None:
        session.is_active = False
        session.revoked_at = datetime.now(timezone.utc)
        self._store.commit()
        session_revocations.increment()
        _log.info(
            "session.revoked",
            extra={
                "event": "session.revoked",
                "session_id": session.id,
                "operator_id": session.operator_id,
            },
        )
