"""
SQLAlchemy ORM models for the Integration Governance System (Packet 10).

Two tables:
  tool_definitions  — catalog of known/approved third-party connectors.
  tool_bindings     — product- and agent-scoped assignments of catalog tools.

All tables are registered on the shared Base from the Registry database so a
single init_db() call creates every table across all packets.

Isolation rule
--------------
product_id on ToolBindingRecord is the enforcement boundary.  The service
layer checks agent ownership via the Packet 2 registry before creating a
binding; it never trusts the caller-supplied product_id alone.

vaulted_credentials_ref
-----------------------
Intentionally a plain string stub per Packet 10 §13: "vaulted_credentials_ref
can be plain mocked strings in early dev."  A production vault integration
(HashiCorp Vault, AWS Secrets Manager, etc.) replaces this field's semantics
without changing the schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, UniqueConstraint

from src.core.registry.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ToolDefinitionRecord(Base):
    """
    Catalog entry for a third-party integration tool.

    Fields defined in Packet 10 §9:
      id, name, scope, security_level
    Extended with governance metadata:
      provider, category, status, description, product_id (optional scoping)

    product_id is nullable — None means the tool is available in the global
    catalog and any product may request a binding.  When set, only the
    specified product_id may bind to this tool (exclusive / private tool).
    """

    __tablename__ = "tool_definitions"

    id             = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name           = Column(String, nullable=False, unique=True, index=True)
    provider       = Column(String, nullable=False)              # vendor / author name
    category       = Column(String, nullable=False, default="OTHER")
    scope          = Column(String, nullable=False, default="")  # permission scope description
    security_level = Column(String, nullable=False, default="MEDIUM")
    status         = Column(String, nullable=False, default="DISCOVERED", index=True)
    description    = Column(String, nullable=True)
    # None = global catalog entry; non-null = exclusive to this product
    product_id     = Column(String, nullable=True, index=True)
    created_at     = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at     = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class ToolBindingRecord(Base):
    """
    Product- and agent-scoped assignment of a catalog tool.

    Fields defined in Packet 10 §9:
      agent_id, product_id, tool_id, vaulted_credentials_ref

    The compound unique constraint prevents double-binding the same
    (agent, product, tool) combination.

    Isolation guarantee: every binding MUST carry a product_id.  The governor
    validates that the agent identified by agent_id belongs to the stated
    product_id via the Packet 2 registry before inserting.
    """

    __tablename__ = "tool_bindings"

    id                     = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tool_id                = Column(String, nullable=False, index=True)
    agent_id               = Column(String, nullable=False, index=True)
    product_id             = Column(String, nullable=False, index=True)
    # Stub credential reference — replaced by vault secret path in production
    vaulted_credentials_ref = Column(String, nullable=True)
    created_at             = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at             = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint(
            "tool_id", "agent_id", "product_id",
            name="uq_tool_binding_tool_agent_product",
        ),
    )
