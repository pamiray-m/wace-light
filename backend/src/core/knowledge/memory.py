"""
Memory context schemas and service (Packet 8).

MemoryContext — Pydantic view of an agent's memory summary.
MemoryService — governed service for storing and retrieving agent memory.

Architecture constraints
------------------------
- Memory is mAIb-owned.  The runtime engine reads compiled `narrative` strings
  but never writes them.
- Product isolation is strict: query_memory() with mismatched product_id
  raises CrossProductAccessError before any data is returned.
- vector_embed is a JSON stub (list of keyword tags).  query_memory() performs
  basic keyword matching against the stub.  Packet 9/10 or a future embedding
  backend can replace this without changing the service interface.

Packet 8 interface: `query_memory(product_id, agent_id, query)`
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.core.knowledge.exceptions import (
    CrossProductAccessError,
    MemoryContextNotFound,
)
from src.core.knowledge.models import MemoryContextRecord


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class MemoryContext(BaseModel):
    """
    Read-view of an agent's memory/knowledge context entry.

    narrative    : human-readable summary consumed by the execution adapter.
    vector_embed : stub embedding (keyword list); future FAISS/Pinecone payload.
    """

    id:           str
    agent_id:     str
    product_id:   str
    context_key:  Optional[str]        = None
    narrative:    str                  = ""
    vector_embed: Optional[list[Any]]  = None
    created_at:   datetime
    updated_at:   datetime

    model_config = {"frozen": True}


class MemoryContextCreate(BaseModel):
    """Input schema for creating a new memory context entry."""

    agent_id:     str
    product_id:   str
    context_key:  Optional[str]       = None
    narrative:    str                  = ""
    vector_embed: Optional[list[Any]]  = None


class MemorySummary(BaseModel):
    """
    Aggregated summary for the /memory/summary API surface.

    Returned by the Control API (Packet 1) to the GUI (Packet 7).
    Owned and populated by Packet 8 — replaces the prior stub.
    """

    product_id:    str
    total_entries: int
    last_updated:  Optional[str]  = None
    note:          str            = ""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class MemoryService:
    """
    Governed service for agent memory context storage and retrieval.

    All public methods enforce product isolation.  No cross-product
    reads are ever returned; instead CrossProductAccessError is raised.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def create_context(self, data: MemoryContextCreate) -> MemoryContext:
        """Persist a new memory context entry for an agent."""
        _require_product(data.product_id)
        record = MemoryContextRecord(
            id=str(uuid.uuid4()),
            agent_id=data.agent_id,
            product_id=data.product_id,
            context_key=data.context_key,
            narrative=data.narrative,
            vector_embed=data.vector_embed,
        )
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return _to_schema(record)

    def update_narrative(
        self,
        context_id: str,
        product_id: str,
        narrative:  str,
    ) -> MemoryContext:
        """Replace the narrative of an existing memory context record."""
        record = self._require_context(context_id, product_id)
        record.narrative   = narrative
        record.updated_at  = datetime.now(timezone.utc)
        self._session.commit()
        self._session.refresh(record)
        return _to_schema(record)

    # ------------------------------------------------------------------
    # Read operations (Packet 8 interface)
    # ------------------------------------------------------------------

    def query_memory(
        self,
        product_id: str,
        agent_id:   str,
        query:      str,
    ) -> list[MemoryContext]:
        """
        Packet 8 interface: `query_memory(product_id, agent_id, query)`.

        Returns memory context entries for the agent whose narrative or
        vector_embed keywords match the query string.

        Stub implementation: case-insensitive substring search over narrative
        and keyword match against vector_embed tags.
        Full vector similarity search is deferred to a future embedding backend.

        Raises CrossProductAccessError if agent's contexts belong to a
        different product_id.
        """
        _require_product(product_id)
        rows = (
            self._session.query(MemoryContextRecord)
            .filter(
                MemoryContextRecord.product_id == product_id,
                MemoryContextRecord.agent_id == agent_id,
            )
            .all()
        )

        if not query:
            return [_to_schema(r) for r in rows]

        q_lower = query.lower()
        results = []
        for row in rows:
            if q_lower in (row.narrative or "").lower():
                results.append(_to_schema(row))
                continue
            # Keyword stub: check vector_embed list
            if row.vector_embed:
                tags = [str(t).lower() for t in row.vector_embed]
                if any(q_lower in tag for tag in tags):
                    results.append(_to_schema(row))
        return results

    def list_contexts(
        self,
        product_id: str,
        agent_id:   Optional[str] = None,
    ) -> list[MemoryContext]:
        """Return all memory contexts for the product, optionally filtered by agent."""
        _require_product(product_id)
        q = (
            self._session.query(MemoryContextRecord)
            .filter(MemoryContextRecord.product_id == product_id)
        )
        if agent_id is not None:
            q = q.filter(MemoryContextRecord.agent_id == agent_id)
        return [_to_schema(r) for r in q.order_by(MemoryContextRecord.created_at).all()]

    def get_summary(self, product_id: str) -> MemorySummary:
        """
        Return an aggregated summary for the /memory/summary API surface.

        Replaces the Packet 1 stub with real data from the persistent store.
        """
        _require_product(product_id)
        rows = (
            self._session.query(MemoryContextRecord)
            .filter(MemoryContextRecord.product_id == product_id)
            .order_by(MemoryContextRecord.updated_at.desc())
            .all()
        )
        last = rows[0].updated_at.isoformat() if rows else None
        return MemorySummary(
            product_id=product_id,
            total_entries=len(rows),
            last_updated=last,
            note="Owned by Packet 8 (Knowledge & Skill System).",
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _require_context(self, context_id: str, product_id: str) -> MemoryContextRecord:
        _require_product(product_id)
        record = self._session.get(MemoryContextRecord, context_id)
        if record is None:
            raise MemoryContextNotFound(f"Memory context '{context_id}' not found.")
        if record.product_id != product_id:
            raise CrossProductAccessError(
                f"Memory context '{context_id}' does not belong to product '{product_id}'."
            )
        return record


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _require_product(product_id: str) -> None:
    if not product_id or product_id == "*":
        raise ValueError("product_id must be a non-empty, non-wildcard string.")


def _to_schema(r: MemoryContextRecord) -> MemoryContext:
    return MemoryContext(
        id=r.id,
        agent_id=r.agent_id,
        product_id=r.product_id,
        context_key=r.context_key,
        narrative=r.narrative,
        vector_embed=r.vector_embed,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )
