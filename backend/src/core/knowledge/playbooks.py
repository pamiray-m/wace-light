"""
Playbook schemas and service (Packet 8).

Playbook       — Pydantic view of a structured instruction sequence.
PlaybookService — governed service for playbook storage and retrieval.

A playbook bundles an ordered list of steps (instruction strings) and
optional references to SkillPackage IDs.  It is a composition artifact
that future orchestration layers (Packet 9/10) will read and execute via
the execution adapter.

Playbooks are mAIb-owned.  Direct runtime writes are rejected at the
service boundary (same principle as skills and memory).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.core.knowledge.exceptions import (
    CrossProductAccessError,
    PlaybookNotFound,
)
from src.core.knowledge.models import PlaybookRecord


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class Playbook(BaseModel):
    """Read-view of a playbook record."""

    id:          str
    name:        str
    product_id:  str
    agent_id:    Optional[str]        = None
    description: Optional[str]       = None
    steps:       Optional[list[str]]  = None  # ordered instruction strings
    skill_refs:  Optional[list[str]]  = None  # SkillPackage IDs referenced
    version:     int                  = 1
    created_at:  datetime
    updated_at:  datetime

    model_config = {"frozen": True}


class PlaybookCreate(BaseModel):
    """Input schema for creating a new playbook."""

    name:        str
    product_id:  str
    agent_id:    Optional[str]        = None
    description: Optional[str]       = None
    steps:       Optional[list[str]]  = None
    skill_refs:  Optional[list[str]]  = None
    version:     int                  = 1


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class PlaybookService:
    """
    Governed service for playbook storage and retrieval.

    All public methods enforce product isolation.
    Playbook content is never modified by the runtime layer.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def create_playbook(self, data: PlaybookCreate) -> Playbook:
        """Persist a new playbook."""
        _require_product(data.product_id)
        record = PlaybookRecord(
            id=str(uuid.uuid4()),
            name=data.name,
            product_id=data.product_id,
            agent_id=data.agent_id,
            description=data.description,
            steps=data.steps,
            skill_refs=data.skill_refs,
            version=data.version,
        )
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return _to_schema(record)

    def update_steps(
        self,
        playbook_id: str,
        product_id:  str,
        steps:       list[str],
    ) -> Playbook:
        """Replace the steps of an existing playbook."""
        record = self._require_playbook(playbook_id, product_id)
        record.steps      = steps
        record.updated_at = datetime.now(timezone.utc)
        self._session.commit()
        self._session.refresh(record)
        return _to_schema(record)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_playbook(self, playbook_id: str, product_id: str) -> Playbook:
        """Return a playbook by ID, enforcing product isolation."""
        return _to_schema(self._require_playbook(playbook_id, product_id))

    def list_playbooks(
        self,
        product_id: str,
        agent_id:   Optional[str] = None,
    ) -> list[Playbook]:
        """Return all playbooks for the product, optionally filtered by agent."""
        _require_product(product_id)
        q = (
            self._session.query(PlaybookRecord)
            .filter(PlaybookRecord.product_id == product_id)
        )
        if agent_id is not None:
            q = q.filter(PlaybookRecord.agent_id == agent_id)
        return [_to_schema(r) for r in q.order_by(PlaybookRecord.name).all()]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _require_playbook(self, playbook_id: str, product_id: str) -> PlaybookRecord:
        _require_product(product_id)
        record = self._session.get(PlaybookRecord, playbook_id)
        if record is None:
            raise PlaybookNotFound(f"Playbook '{playbook_id}' not found.")
        if record.product_id != product_id:
            raise CrossProductAccessError(
                f"Playbook '{playbook_id}' does not belong to product '{product_id}'."
            )
        return record


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _require_product(product_id: str) -> None:
    if not product_id or product_id == "*":
        raise ValueError("product_id must be a non-empty, non-wildcard string.")


def _to_schema(r: PlaybookRecord) -> Playbook:
    return Playbook(
        id=r.id,
        name=r.name,
        product_id=r.product_id,
        agent_id=r.agent_id,
        description=r.description,
        steps=r.steps,
        skill_refs=r.skill_refs,
        version=r.version,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )
