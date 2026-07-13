"""
KnowledgeStore — unified persistence coordinator for Packet 8.

This module satisfies the packet's required `storage.py` surface.  It
provides a single session-scoped entry point that owns all three knowledge
sub-services (skills, memory, playbooks).  Callers may use this facade or
import the sub-services directly.

Required packet interface: `add_skill(agent_id, package)` and
`query_memory(product_id, agent_id, query)` are exposed here as top-level
methods for the canonical Packet 8 interface.

Future packets (9, 10) should interact with this surface rather than
instantiating sub-services independently.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from src.core.knowledge.enums import SkillAuthority, SkillStatus
from src.core.knowledge.memory import MemoryContext, MemoryContextCreate, MemoryService, MemorySummary
from src.core.knowledge.playbooks import Playbook, PlaybookCreate, PlaybookService
from src.core.knowledge.skills import (
    SkillCreate,
    SkillPackage,
    SkillService,
    SkillTransitionRequest,
)


class KnowledgeStore:
    """
    Unified facade for the Knowledge & Skill System.

    Provides the canonical Packet 8 interfaces:
      add_skill(agent_id, package)
      query_memory(product_id, agent_id, query)

    Also exposes the full sub-service APIs for richer access.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self.skills   = SkillService(session=session)
        self.memory   = MemoryService(session=session)
        self.playbooks = PlaybookService(session=session)

    # ------------------------------------------------------------------
    # Packet 8 canonical interfaces
    # ------------------------------------------------------------------

    def add_skill(self, agent_id: str, package: SkillCreate) -> SkillPackage:
        """
        Packet 8 interface: `add_skill(agent_id, package)`.

        Persists a new skill package in DRAFT status associated with the agent.
        Returns the created SkillPackage.
        """
        return self.skills.add_skill(agent_id=agent_id, package=package)

    def query_memory(
        self,
        product_id: str,
        agent_id:   str,
        query:      str,
    ) -> list[MemoryContext]:
        """
        Packet 8 interface: `query_memory(product_id, agent_id, query)`.

        Returns memory contexts matching the query for the given agent/product.
        Cross-product access raises CrossProductAccessError.
        """
        return self.memory.query_memory(
            product_id=product_id,
            agent_id=agent_id,
            query=query,
        )

    # ------------------------------------------------------------------
    # Convenience delegation methods
    # ------------------------------------------------------------------

    def get_memory_summary(self, product_id: str) -> MemorySummary:
        """Aggregate memory summary for the /memory/summary API surface."""
        return self.memory.get_summary(product_id=product_id)

    def transition_skill(
        self,
        skill_id:   str,
        product_id: str,
        request:    SkillTransitionRequest,
    ) -> SkillPackage:
        """Delegate to SkillService.transition_status()."""
        return self.skills.transition_status(
            skill_id=skill_id,
            product_id=product_id,
            request=request,
        )
