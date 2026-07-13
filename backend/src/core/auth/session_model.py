"""
P4 — Session Model.

Persistent record for each active operator session (i.e. each issued refresh
token).  One login = one session.  Multiple sessions per operator are allowed
(multi-device).

Refresh token security
----------------------
The raw refresh token is a cryptographically random 32-byte URL-safe string.
Only the SHA-256 hex digest is stored here — the plaintext token is returned
to the client at issuance and never persisted.

Session lifecycle
-----------------
ACTIVE  → issued, not yet revoked or expired.
REVOKED → logout was called, or an operator was disabled during a refresh
           attempt.  is_active=False, revoked_at is set.
EXPIRED → expires_at is in the past.  is_active remains True; TokenManager
          treats expired sessions as invalid without setting revoked_at.

Relationship to P3 OperatorModel
---------------------------------
operator_id references OperatorModel.id.  No SQLAlchemy ForeignKey is
declared to keep the auth package boundary clean; integrity is enforced
at the service layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String

from src.core.registry.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SessionModel(Base):
    """
    One record per issued refresh token.

    Columns
    -------
    id                  : UUID primary key.
    operator_id         : Owner of this session (references operators.id).
    refresh_token_hash  : SHA-256 hex digest of the raw refresh token.
                          Used as the lookup key on /auth/refresh.
    issued_at           : UTC timestamp when the session was created.
    expires_at          : UTC timestamp after which refresh is rejected.
    revoked_at          : UTC timestamp of explicit revocation (logout / disable).
                          Null while session is still valid.
    is_active           : False once the session is revoked.  Expired sessions
                          keep is_active=True; the check is by timestamp.
    user_agent          : Optional HTTP User-Agent string at login time.
    ip_address          : Optional client IP at login time.
    """

    __tablename__ = "operator_sessions"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    operator_id = Column(String(36), nullable=False, index=True)
    refresh_token_hash = Column(String(64), nullable=False, unique=True, index=True)
    issued_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    user_agent = Column(String(512), nullable=True)
    ip_address = Column(String(45), nullable=True)   # IPv4 (15) or IPv6 (39) with margin
