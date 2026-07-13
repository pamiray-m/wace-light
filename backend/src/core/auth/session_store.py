"""
P4 — Session Store (repository for operator_sessions table).

Named session_store.py per Packet P4 specification.  Thin data-access layer —
all SQL lives here; TokenManager stays SQL-free.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.core.auth.session_model import SessionModel


class SessionStore:
    """Data-access wrapper for the 'operator_sessions' table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_by_id(self, session_id: str) -> SessionModel | None:
        return self._session.get(SessionModel, session_id)

    def get_by_token_hash(self, token_hash: str) -> SessionModel | None:
        """Return the session whose refresh_token_hash matches, or None."""
        return (
            self._session.query(SessionModel)
            .filter(SessionModel.refresh_token_hash == token_hash)
            .first()
        )

    def list_by_operator(self, operator_id: str) -> list[SessionModel]:
        """Return all sessions for an operator, ordered by issued_at desc."""
        return (
            self._session.query(SessionModel)
            .filter(SessionModel.operator_id == operator_id)
            .order_by(SessionModel.issued_at.desc())
            .all()
        )

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def add(self, session: SessionModel) -> SessionModel:
        self._session.add(session)
        self._session.flush()
        return session

    def revoke_all_for_operator(self, operator_id: str) -> int:
        """
        Revoke every active session for operator_id.

        Returns the number of sessions revoked.  Used when an operator is
        disabled or their password is reset (all active sessions invalidated).
        """
        from datetime import datetime, timezone

        active = (
            self._session.query(SessionModel)
            .filter(
                SessionModel.operator_id == operator_id,
                SessionModel.is_active.is_(True),
            )
            .all()
        )
        now = datetime.now(timezone.utc)
        for s in active:
            s.is_active = False
            s.revoked_at = now
        self._session.flush()
        return len(active)

    def commit(self) -> None:
        self._session.commit()

    def refresh(self, session: SessionModel) -> SessionModel:
        self._session.refresh(session)
        return session
