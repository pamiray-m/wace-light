"""
P3 — Persistent Operator Model.

SQLAlchemy ORM table for human operators.  Replaces the ephemeral in-memory
OperatorRecord/store.py pattern from H1.

Design decisions
----------------
- Uses the shared Base from src.core.registry.database so that init_db()
  creates this table alongside agent/observability/integration tables.
- hashed_password is stored bcrypt-hashed; the column is excluded from all
  response schemas and never appears in log output.
- is_active is the lifecycle gate: disabled operators cannot authenticate
  regardless of correct credentials.
- last_login_at is set by OperatorService.authenticate() on successful login.
- role is stored as a plain string (not a SQLAlchemy Enum) so that adding
  new OperatorRole values does not require a DB migration.

Relationship to H1 OperatorRecord
-----------------------------------
OperatorRecord (models.py dataclass) is retained only for tests that import it
directly.  All production code must use OperatorModel + OperatorService.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String

from src.core.registry.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OperatorModel(Base):
    """
    Persistent operator record.

    Columns
    -------
    id              : UUID string primary key.
    username        : Unique login name.  Case-sensitive.
    hashed_password : bcrypt hash — NEVER the plaintext credential.
    role            : OperatorRole string value ("admin" / "viewer" / "auditor").
    product_scope   : If set, restricts the operator to one product tenant.
                      None = global (no product restriction).
    stream_scope    : If set, restricts to one stream.  None = unrestricted.
    is_active       : False = operator is disabled; login is rejected.
    created_at      : UTC timestamp of creation.
    updated_at      : UTC timestamp of last mutation (role/password/status change).
    last_login_at   : UTC timestamp of most recent successful authentication.
                      Null until first login.
    """

    __tablename__ = "operators"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    username = Column(String(255), nullable=False, unique=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(64), nullable=False, default="admin")
    product_scope = Column(String(255), nullable=True)
    stream_scope = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
