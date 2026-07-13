"""
SQLAlchemy ORM models for the Knowledge & Skill System (Packet 8).

Three tables:
  skill_packages   — canonical skill definitions with lifecycle status.
  memory_contexts  — per-agent memory summaries and narrative context.
  playbooks        — structured instruction sequences referencing skill packages.

All tables are registered on the shared Base from the Registry so a single
init_db() call creates all tables together.

Isolation rule enforced at query time (not at DB level): every service method
requires product_id, and queries filter by it.  Cross-product reads are
rejected by the service layer before hitting the DB.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON

from src.core.registry.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SkillPackageRecord(Base):
    """
    Persistent canonical definition of a skill package.

    A skill is an abstract capability description — JSON/schema data that
    the execution adapter converts into runtime instructions.  It is NOT
    executable Python; it is a governed instruction artifact.

    Fields mirror the contract schema definition:
      id, name, instructions, constraints (contract)
      + expected_params, source_instruction (packet)
      + agent_id, product_id, status, created_at, updated_at (governance)
    """

    __tablename__ = "skill_packages"

    id                = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name              = Column(String, nullable=False)
    product_id        = Column(String, nullable=False, index=True)
    agent_id          = Column(String, nullable=True, index=True)   # None = product-level skill
    instructions      = Column(String, nullable=False, default="")  # prompts provided to adapter
    constraints       = Column(JSON, nullable=True)                 # rules parsed by State Machine
    expected_params   = Column(JSON, nullable=True)                 # parameter schema
    source_instruction = Column(String, nullable=True)              # provenance / origin description
    status            = Column(String, nullable=False, default="DRAFT", index=True)
    created_at        = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at        = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        # Unique skill name per product (agent_id may be NULL — product-level skill)
        UniqueConstraint("name", "product_id", "agent_id", name="uq_skill_name_product_agent"),
    )


class MemoryContextRecord(Base):
    """
    Per-agent memory summary and narrative context.

    Stores the mAIb-owned summary of what an agent knows / has experienced.
    The runtime engine consumes the compiled `narrative` string; it never
    writes back to this table directly.

    vector_embed is a JSON stub for future FAISS/Pinecone integration.  In
    the P8 implementation it is a plain list/dict that query_memory() scans
    with basic JSON matching.
    """

    __tablename__ = "memory_contexts"

    id            = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id      = Column(String, nullable=False, index=True)
    product_id    = Column(String, nullable=False, index=True)
    context_key   = Column(String, nullable=True, index=True)  # optional label for retrieval
    narrative     = Column(String, nullable=False, default="")
    vector_embed  = Column(JSON, nullable=True)               # stub: keyword tags / JSON payload
    created_at    = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at    = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class PlaybookRecord(Base):
    """
    Structured instruction sequence associated with an agent or product.

    A playbook bundles an ordered list of steps plus optional references
    to SkillPackage IDs.  It is a higher-level composition artifact that
    orchestrators (future Packet 9/10) will read to plan execution.
    """

    __tablename__ = "playbooks"

    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name        = Column(String, nullable=False)
    product_id  = Column(String, nullable=False, index=True)
    agent_id    = Column(String, nullable=True, index=True)    # None = product-level playbook
    description = Column(String, nullable=True)
    steps       = Column(JSON, nullable=True)                  # ordered list of instruction strings
    skill_refs  = Column(JSON, nullable=True)                  # list of SkillPackage IDs used
    version     = Column(Integer, nullable=False, default=1)
    created_at  = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at  = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("name", "product_id", "version", name="uq_playbook_name_product_ver"),
    )
