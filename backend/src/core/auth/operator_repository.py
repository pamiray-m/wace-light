"""
P3 — Operator Repository.

Thin data-access layer: all SQL lives here, services stay SQL-free.
Every method operates within the caller-supplied session — no session
lifecycle management happens inside this class (the FastAPI dependency
provider owns that via get_db).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.core.auth.operator_model import OperatorModel


class OperatorRepository:
    """Data-access wrapper for the 'operators' table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_by_id(self, operator_id: str) -> OperatorModel | None:
        """Return the operator with the given id, or None."""
        return self._session.get(OperatorModel, operator_id)

    def get_by_username(self, username: str) -> OperatorModel | None:
        """Return the operator with the given username (case-sensitive), or None."""
        return (
            self._session.query(OperatorModel)
            .filter(OperatorModel.username == username)
            .first()
        )

    def list_all(self) -> list[OperatorModel]:
        """Return all operator records ordered by username."""
        return (
            self._session.query(OperatorModel)
            .order_by(OperatorModel.username)
            .all()
        )

    def count(self) -> int:
        """Return the total number of operator records."""
        return self._session.query(OperatorModel).count()

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def add(self, operator: OperatorModel) -> OperatorModel:
        """Persist a new operator and flush so the id is available."""
        self._session.add(operator)
        self._session.flush()
        return operator

    def commit(self) -> None:
        """Commit the current transaction."""
        self._session.commit()

    def refresh(self, operator: OperatorModel) -> OperatorModel:
        """Reload the operator from the DB after a commit."""
        self._session.refresh(operator)
        return operator
