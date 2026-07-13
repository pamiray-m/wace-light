"""
Pydantic schemas for the Agent Registry.

These are the public data contracts consumed by the Control API (Packet 1),
the State Machine (Packet 3), and any governance service that needs to inspect
or create agent records.

Enums defined here are imported by models.py to avoid circular imports.

NOTE (Packet 3 update): AgentLifecycleState is now re-exported from
src.core.state.enums.AgentState so there is exactly one canonical definition
of lifecycle states across the system.  The alias keeps Packet 2 call-sites
unchanged.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# Re-export canonical state definition owned by Packet 3.
from src.core.state.enums import AgentState as AgentLifecycleState  # noqa: F401

# D1 — agent type classification.
from src.core.agents.types import AgentType  # noqa: F401


# ---------------------------------------------------------------------------
# Enums (shared with ORM models via import)
# ---------------------------------------------------------------------------

class LayerLevel(str, Enum):
    """Architecture layer boundaries (frozen doctrine from architecture doc)."""
    SOVEREIGNTY = "0"   # Layer 0: Architect, Deputy, Watcher
    EXECUTIVE   = "1"   # Layer 1: Lawyer, Knowledge-Director, Standards-Agent, Oracle-Intelligence, Integration-Governor
    STREAMS     = "2"   # Layer 2: Stream Managers
    PRODUCTS    = "3"   # Layer 3: Product Companies (tenant-isolated)
    EXECUTION   = "4"   # Layer 4: Execution (OpenClaw abstraction, network connectors)


class OwnerAuthority(str, Enum):
    """mAIb authority roles that can own an agent record."""
    ARCHITECT             = "Architect"
    DEPUTY                = "Deputy"
    WATCHER               = "Watcher"
    LAWYER                = "Lawyer"
    KNOWLEDGE_DIRECTOR    = "Knowledge-Director"
    STANDARDS_AGENT       = "Standards-Agent"
    ORACLE_INTELLIGENCE   = "Oracle-Intelligence"
    INTEGRATION_GOVERNOR  = "Integration-Governor"
    STREAM_MANAGER        = "StreamManager"
    PRODUCT_COMPANY       = "ProductCompany"
    SYSTEM                = "System"


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class AgentCreate(BaseModel):
    """Input schema for registering a new agent."""

    name: str = Field(..., min_length=1, max_length=255)
    layer_level: LayerLevel
    product_id: str = Field(..., min_length=1, max_length=255)
    stream: Optional[str] = Field(default=None, max_length=255)
    owner_authority: OwnerAuthority
    # D1 — agent_type defaults to INTERNAL so all existing callers require no change.
    agent_type: AgentType = Field(default=AgentType.INTERNAL)
    configuration: dict[str, Any] = Field(default_factory=dict)

    @field_validator("product_id")
    @classmethod
    def product_id_no_wildcards(cls, v: str) -> str:
        if "*" in v or v.strip() == "":
            raise ValueError("product_id must not contain wildcards or be blank")
        return v

    @model_validator(mode="after")
    def stream_required_for_layer2(self) -> "AgentCreate":
        if self.layer_level == LayerLevel.STREAMS and not self.stream:
            raise ValueError("stream is required for Layer 2 (STREAMS) agents")
        return self


class AgentRead(BaseModel):
    """Output schema returned after creation or lookup."""

    id: str
    name: str
    layer_level: LayerLevel
    product_id: str
    stream: Optional[str]
    owner_authority: OwnerAuthority
    lifecycle_state: AgentLifecycleState
    agent_type: AgentType  # D1 — always present; INTERNAL for pre-D1 agents
    configuration: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HierarchyLinkCreate(BaseModel):
    """Input schema for adding a parent→child edge in the hierarchy."""

    parent_agent_id: str
    child_agent_id: str
    relationship_type: str = Field(default="direct_report", max_length=64)

    @model_validator(mode="after")
    def no_self_loop(self) -> "HierarchyLinkCreate":
        if self.parent_agent_id == self.child_agent_id:
            raise ValueError("parent_agent_id and child_agent_id must differ (no self-loops)")
        return self


class HierarchyLinkRead(BaseModel):
    """Output schema for a single hierarchy edge."""

    id: str
    parent_agent_id: str
    child_agent_id: str
    relationship_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


class HierarchyNode(BaseModel):
    """
    Recursive tree node returned by RegistryService.get_hierarchy().
    Children list is populated one level deep per call; deeper traversal
    is done recursively by the caller.
    """

    agent: AgentRead
    children: list["HierarchyNode"] = Field(default_factory=list)


HierarchyNode.model_rebuild()  # required for self-referential Pydantic v2 model
