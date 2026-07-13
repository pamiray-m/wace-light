"""
ORM models for the Agent Registry.

These are the mAIb-owned source-of-truth records for every agent node.
They are intentionally execution-free: no Celery task IDs, no queue depths,
no OpenClaw internal state lives here.

Packet 3 (State Machine) will extend the lifecycle logic that builds on AgentModel.
Packet 4 (Execution Adapter) will reference agent IDs but never mutate these records.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, JSON, DateTime, ForeignKey, Enum as SAEnum, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base
from .schemas import LayerLevel, OwnerAuthority, AgentLifecycleState
from src.core.agents.types import AgentType  # D1 — agent classification


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AgentModel(Base):
    """
    Central registry record for every agent node in the mAIb hierarchy.

    Fields
    ------
    id              : Globally unique agent identifier (UUID string).
    name            : Human-readable agent name (unique per product_id + layer).
    layer_level     : Integer 0-4 matching the architecture layer boundaries.
    product_id      : Tenant isolation key. ALL queries MUST filter on this.
    stream          : Optional stream label (Layer 2 managers carry a stream name).
    owner_authority : The mAIb authority role that owns this agent record.
    lifecycle_state : Current lifecycle status (stub; full transitions in Packet 3).
    configuration   : Arbitrary JSON blob for agent-specific parameters.
    created_at      : UTC timestamp of registry insertion.
    updated_at      : UTC timestamp of last mutation.
    """

    __tablename__ = "agents"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name = Column(String(255), nullable=False)
    layer_level = Column(
        SAEnum(LayerLevel, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    product_id = Column(String(255), nullable=False, index=True)
    stream = Column(String(255), nullable=True)
    owner_authority = Column(
        SAEnum(OwnerAuthority, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    lifecycle_state = Column(
        SAEnum(AgentLifecycleState, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=AgentLifecycleState.PROVISIONING,
    )
    # D1 — agent classification.  INTERNAL is the default for all pre-D1 agents;
    # DAG agents are set explicitly at creation time and cannot be changed
    # without going through the governance layer.
    agent_type = Column(
        SAEnum(AgentType, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=AgentType.INTERNAL,
    )
    configuration = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    # Relationships
    children = relationship(
        "HierarchyMap",
        foreign_keys="HierarchyMap.parent_agent_id",
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    parents = relationship(
        "HierarchyMap",
        foreign_keys="HierarchyMap.child_agent_id",
        back_populates="child",
        cascade="all, delete-orphan",
    )

    # An agent name must be unique within its own tenant + layer combination.
    __table_args__ = (
        UniqueConstraint("name", "product_id", "layer_level", name="uq_agent_name_tenant_layer"),
    )

    def __repr__(self) -> str:
        return (
            f"<AgentModel id={self.id!r} name={self.name!r} "
            f"layer={self.layer_level} product={self.product_id!r} "
            f"type={self.agent_type}>"
        )


class HierarchyMap(Base):
    """
    Directed edge in the agent hierarchy graph.

    Represents a parent→child authority relationship between two registered
    agents that MUST share the same product_id (cross-tenant links are forbidden).

    relationship_type examples: "direct_report", "delegated", "watcher_scope"
    """

    __tablename__ = "hierarchy_map"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    parent_agent_id = Column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    child_agent_id = Column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship_type = Column(String(64), nullable=False, default="direct_report")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    parent = relationship(
        "AgentModel", foreign_keys=[parent_agent_id], back_populates="children"
    )
    child = relationship(
        "AgentModel", foreign_keys=[child_agent_id], back_populates="parents"
    )

    # A parent→child pair must be unique (no duplicate edges).
    __table_args__ = (
        UniqueConstraint("parent_agent_id", "child_agent_id", name="uq_hierarchy_edge"),
    )

    def __repr__(self) -> str:
        return (
            f"<HierarchyMap {self.parent_agent_id!r} → {self.child_agent_id!r} "
            f"({self.relationship_type!r})>"
        )
