"""
Skill package schemas and service (Packet 8).

SkillPackage — immutable Pydantic view of a skill record.
SkillService  — governed CRUD + lifecycle transition service.

Write path
----------
All mutations must come through SkillService.  The service enforces:
  1. Product isolation — no write/read across product boundaries.
  2. Lifecycle governance — status transitions validated by SkillLifecycleEngine.
  3. Oracle restraint — Oracle can submit DRAFT→PROPOSED but cannot approve
     or deploy (enforced by the lifecycle engine transition rules).

Per contract: "If OpenClaw tries to push back or write modifications directly
to the memory arrays, the Knowledge API physically rejects the requests."
The physical rejection is implemented by UnauthorizedSkillWrite at the
lifecycle engine layer before any DB write is attempted.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.knowledge.enums import SkillAuthority, SkillStatus
from src.core.knowledge.exceptions import (
    CrossProductAccessError,
    InvalidSkillTransition,
    SkillNotFound,
    UnauthorizedSkillWrite,
)
from src.core.knowledge.lifecycle import SkillLifecycleEngine
from src.core.knowledge.models import SkillPackageRecord


# ---------------------------------------------------------------------------
# Pydantic schemas (stable API surface for Packet 9 / Packet 10)
# ---------------------------------------------------------------------------

class SkillPackage(BaseModel):
    """
    Canonical read-view of a skill package.

    Fields per contract schema:
      id, name, instructions, constraints
    Additional governance fields:
      product_id, agent_id, expected_params, source_instruction, status, timestamps
    """

    id:                 str
    name:               str
    product_id:         str
    agent_id:           Optional[str]           = None
    instructions:       str                     = ""
    constraints:        Optional[list[Any]]     = None
    expected_params:    Optional[dict[str, Any]] = None
    source_instruction: Optional[str]           = None
    status:             SkillStatus             = SkillStatus.DRAFT
    created_at:         datetime
    updated_at:         datetime

    model_config = {"frozen": True}


class SkillCreate(BaseModel):
    """Input schema for creating a new skill package (starts as DRAFT)."""

    name:               str
    product_id:         str
    agent_id:           Optional[str]            = None
    instructions:       str                      = ""
    constraints:        Optional[list[Any]]      = None
    expected_params:    Optional[dict[str, Any]] = None
    source_instruction: Optional[str]            = None


class SkillTransitionRequest(BaseModel):
    """Request to move a skill through a lifecycle transition."""

    target_status: SkillStatus
    authority:     SkillAuthority
    actor:         str  # identity string (e.g. "user:director-01", "system:oracle")
    reason:        str = ""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

_engine = SkillLifecycleEngine()


class SkillService:
    """
    Governed service for skill package storage and lifecycle management.

    All public methods enforce product isolation and lifecycle rules.
    No raw DB access is permitted outside this class.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def create_skill(
        self, data: SkillCreate, authority: SkillAuthority = SkillAuthority.SYSTEM
    ) -> SkillPackage:
        """
        Persist a new skill package in DRAFT status.

        Any authority may create a draft (including SYSTEM for seeding).
        """
        _require_no_wildcard_product(data.product_id)
        record = SkillPackageRecord(
            id=str(uuid.uuid4()),
            name=data.name,
            product_id=data.product_id,
            agent_id=data.agent_id,
            instructions=data.instructions,
            constraints=data.constraints,
            expected_params=data.expected_params,
            source_instruction=data.source_instruction,
            status=SkillStatus.DRAFT.value,
        )
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return _to_schema(record)

    def transition_status(
        self,
        skill_id:   str,
        product_id: str,
        request:    SkillTransitionRequest,
    ) -> SkillPackage:
        """
        Advance or revert a skill through its lifecycle.

        Validates authority against the lifecycle policy matrix before
        any DB write.  Raises before touching the DB if unauthorized.
        """
        record = self._require_skill(skill_id, product_id)
        current = SkillStatus(record.status)
        _engine.validate_transition(current, request.target_status, request.authority)

        record.status = request.target_status.value
        record.updated_at = datetime.now(timezone.utc)
        self._session.commit()
        self._session.refresh(record)
        return _to_schema(record)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_skill(self, skill_id: str, product_id: str) -> SkillPackage:
        """Return a skill by ID, enforcing product isolation."""
        return _to_schema(self._require_skill(skill_id, product_id))

    def list_skills(
        self,
        product_id: str,
        agent_id:   Optional[str] = None,
        status:     Optional[SkillStatus] = None,
    ) -> list[SkillPackage]:
        """Return skills for the product, optionally filtered by agent and/or status."""
        _require_no_wildcard_product(product_id)
        q = (
            self._session.query(SkillPackageRecord)
            .filter(SkillPackageRecord.product_id == product_id)
        )
        if agent_id is not None:
            q = q.filter(SkillPackageRecord.agent_id == agent_id)
        if status is not None:
            q = q.filter(SkillPackageRecord.status == status.value)
        return [_to_schema(r) for r in q.order_by(SkillPackageRecord.name).all()]

    def add_skill(self, agent_id: str, package: SkillCreate) -> SkillPackage:
        """
        Packet 8 interface: `add_skill(agent_id, package)`.

        Convenience wrapper that forces agent_id onto the package.
        """
        data = SkillCreate(
            name=package.name,
            product_id=package.product_id,
            agent_id=agent_id,
            instructions=package.instructions,
            constraints=package.constraints,
            expected_params=package.expected_params,
            source_instruction=package.source_instruction,
        )
        return self.create_skill(data)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _require_skill(self, skill_id: str, product_id: str) -> SkillPackageRecord:
        """Fetch skill; raise SkillNotFound if absent or wrong tenant."""
        _require_no_wildcard_product(product_id)
        record = self._session.get(SkillPackageRecord, skill_id)
        if record is None:
            raise SkillNotFound(f"Skill '{skill_id}' not found.")
        if record.product_id != product_id:
            raise CrossProductAccessError(
                f"Skill '{skill_id}' does not belong to product '{product_id}'."
            )
        return record


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _require_no_wildcard_product(product_id: str) -> None:
    if not product_id or product_id == "*":
        raise ValueError("product_id must be a non-empty, non-wildcard string.")


def _to_schema(r: SkillPackageRecord) -> SkillPackage:
    return SkillPackage(
        id=r.id,
        name=r.name,
        product_id=r.product_id,
        agent_id=r.agent_id,
        instructions=r.instructions,
        constraints=r.constraints,
        expected_params=r.expected_params,
        source_instruction=r.source_instruction,
        status=SkillStatus(r.status),
        created_at=r.created_at,
        updated_at=r.updated_at,
    )
