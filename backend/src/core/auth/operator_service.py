"""
P3 — Operator Service.

Business logic for operator lifecycle: creation, authentication, disabling,
role changes, and password rotation.  All password operations go through
src.core.auth.password — no bcrypt calls appear here directly.

Security invariants
-------------------
- Plaintext passwords are hashed immediately on entry and never stored.
- authenticate() checks is_active before verifying the password so that a
  timing oracle cannot distinguish "disabled" from "wrong password" based on
  bcrypt latency (both return None after the same logical path).
- Password reset replaces hashed_password atomically; the old hash is gone.
- Role changes take effect on the next login (existing JWTs still carry the
  old role — token revocation is a P4 concern).

Assumptions (P3)
----------------
- Concurrent writes are serialised at the DB level via row-level locking; no
  application-level lock is needed for SQLite (test) or PostgreSQL (prod).
- Username uniqueness is enforced by the DB UNIQUE constraint; the service
  raises OperatorConflict if the constraint fires.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.auth.models import OperatorIdentity, OperatorRole
from src.core.auth.operator_model import OperatorModel
from src.core.auth.operator_repository import OperatorRepository
from src.core.auth.password import hash_password, verify_password


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------

class OperatorNotFound(Exception):
    """Raised when an operator lookup by id/username returns nothing."""


class OperatorConflict(Exception):
    """Raised when a username uniqueness constraint is violated on create."""


class OperatorDisabled(Exception):
    """Raised when an operation requires an active operator but it is disabled."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class OperatorService:
    """
    Operator lifecycle manager.

    Accepts an open SQLAlchemy session from the caller (FastAPI dependency).
    """

    def __init__(self, session: Session) -> None:
        self._repo = OperatorRepository(session)

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def create(
        self,
        *,
        username: str,
        password: str,
        role: str | OperatorRole = OperatorRole.ADMIN,
        product_scope: str | None = None,
        stream_scope: str | None = None,
    ) -> OperatorModel:
        """
        Create a new active operator.

        Parameters
        ----------
        username      : Must be unique (case-sensitive).
        password      : Plaintext — hashed before storage.
        role          : OperatorRole or its string value.  Defaults to ADMIN.
        product_scope : Optional product isolation key.
        stream_scope  : Optional stream isolation key.

        Raises
        ------
        ValueError       : username or password is blank.
        OperatorConflict : username already exists.
        """
        if not username or not username.strip():
            raise ValueError("username must not be blank.")
        if not password:
            raise ValueError("password must not be blank.")

        # Accept either an OperatorRole enum or its string value
        role_value = role.value if isinstance(role, OperatorRole) else str(role)

        operator = OperatorModel(
            username=username.strip(),
            hashed_password=hash_password(password),
            role=role_value,
            product_scope=product_scope or None,
            stream_scope=stream_scope or None,
            is_active=True,
        )
        try:
            self._repo.add(operator)
            self._repo.commit()
        except IntegrityError:
            # Username UNIQUE constraint fired
            raise OperatorConflict(
                f"An operator with username '{username}' already exists."
            )
        self._repo.refresh(operator)
        return operator

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self, username: str, password: str) -> OperatorModel | None:
        """
        Verify credentials and return the matching OperatorModel.

        Returns None on any failure:
          - user not found
          - account disabled
          - wrong password

        Never raises — callers translate None to HTTP 401.
        is_active check is done before password verify to avoid bcrypt latency
        creating a timing side-channel that reveals account existence.
        """
        operator = self._repo.get_by_username(username)
        if operator is None:
            # Run a dummy verify to normalise timing (no real hash to compare)
            verify_password("dummy", "$2b$12$invalidhashpaddingtomatchlength1234567")
            return None

        # Reject disabled accounts with the same code path as wrong passwords
        if not operator.is_active:
            verify_password(password, operator.hashed_password)  # normalise timing
            return None

        if not verify_password(password, operator.hashed_password):
            return None

        # Record last login timestamp
        operator.last_login_at = datetime.now(timezone.utc)
        self._repo.commit()
        return operator

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_by_id(self, operator_id: str) -> OperatorModel:
        """
        Raises OperatorNotFound if not found.
        """
        op = self._repo.get_by_id(operator_id)
        if op is None:
            raise OperatorNotFound(f"No operator with id '{operator_id}'.")
        return op

    def get_by_username(self, username: str) -> OperatorModel:
        """
        Raises OperatorNotFound if not found.
        """
        op = self._repo.get_by_username(username)
        if op is None:
            raise OperatorNotFound(f"No operator with username '{username}'.")
        return op

    def list_all(self) -> list[OperatorModel]:
        """Return all operator records (ordered by username)."""
        return self._repo.list_all()

    def has_any(self) -> bool:
        """Return True if at least one operator exists in the DB."""
        return self._repo.count() > 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def disable(self, operator_id: str) -> OperatorModel:
        """
        Mark the operator as inactive.  Future login attempts will be rejected.

        Raises OperatorNotFound if operator does not exist.
        """
        op = self.get_by_id(operator_id)
        op.is_active = False
        self._repo.commit()
        return op

    def enable(self, operator_id: str) -> OperatorModel:
        """
        Re-activate a previously disabled operator.

        Raises OperatorNotFound if operator does not exist.
        """
        op = self.get_by_id(operator_id)
        op.is_active = True
        self._repo.commit()
        return op

    # ------------------------------------------------------------------
    # Role management
    # ------------------------------------------------------------------

    def update_role(self, operator_id: str, new_role: str | OperatorRole) -> OperatorModel:
        """
        Change the operator's role.

        The change takes effect immediately in the DB.  Existing JWTs still
        carry the old role; revocation is a P4 concern.

        Raises
        ------
        OperatorNotFound : operator does not exist.
        ValueError       : new_role is not a valid OperatorRole value.
        """
        # Validate the role value before touching the DB
        role_value = new_role.value if isinstance(new_role, OperatorRole) else str(new_role)
        try:
            OperatorRole(role_value)
        except ValueError:
            raise ValueError(
                f"'{role_value}' is not a valid role. "
                f"Valid values: {[r.value for r in OperatorRole]}"
            )

        op = self.get_by_id(operator_id)
        op.role = role_value
        self._repo.commit()
        return op

    # ------------------------------------------------------------------
    # Password rotation
    # ------------------------------------------------------------------

    def reset_password(self, operator_id: str, new_password: str) -> None:
        """
        Replace the operator's password hash.

        After this call the old password is irrecoverably gone — the bcrypt
        hash is overwritten.  The operator must use the new password on next
        login.

        Raises
        ------
        OperatorNotFound : operator does not exist.
        ValueError       : new_password is blank.
        """
        if not new_password:
            raise ValueError("New password must not be blank.")
        op = self.get_by_id(operator_id)
        op.hashed_password = hash_password(new_password)
        self._repo.commit()

    # ------------------------------------------------------------------
    # Conversion helper
    # ------------------------------------------------------------------

    @staticmethod
    def to_identity(operator: OperatorModel) -> OperatorIdentity:
        """
        Convert a DB-fetched OperatorModel to a JWT-friendly OperatorIdentity.

        hashed_password is intentionally absent from OperatorIdentity.
        """
        try:
            role = OperatorRole(operator.role)
        except ValueError:
            role = OperatorRole.VIEWER  # unknown role → least-privilege fallback

        return OperatorIdentity(
            operator_id=operator.id,
            username=operator.username,
            role=role,
            product_scope=operator.product_scope,
            stream_scope=operator.stream_scope,
        )
