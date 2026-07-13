"""
RegistryService — the single authoritative write/read interface to the Agent Registry.

All queries are unconditionally scoped by product_id to enforce multi-tenant
isolation at the service layer (not just the DB layer). Cross-tenant reads are
structurally impossible through this service.

Packet 3 (State Machine) will call update_lifecycle_state() to drive transitions.
Packet 1 (Control API) will call create_agent() / list_tenant_agents() via HTTP handlers.
"""

from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session

from .database import get_session
from .models import AgentModel, HierarchyMap
from .schemas import (
    AgentCreate,
    AgentRead,
    AgentLifecycleState,
    HierarchyLinkCreate,
    HierarchyLinkRead,
    HierarchyNode,
)


class RegistryError(Exception):
    """Base exception for registry violations."""


class AgentNotFound(RegistryError):
    """Raised when an agent lookup finds no record scoped to the given product_id."""


class TenantMismatch(RegistryError):
    """Raised when a hierarchy link would bridge two different product_id tenants."""


class DuplicateAgent(RegistryError):
    """Raised when name+product_id+layer collision is detected before DB insert."""


class RegistryService:
    """
    Facade over the Agent Registry data layer.

    Usage (production)
    ------------------
        svc = RegistryService()              # uses module-level session factory
        agent = svc.create_agent(data)

    Usage (tests)
    -------------
        svc = RegistryService(session=test_session)
    """

    def __init__(self, session: Optional[Session] = None) -> None:
        self._external_session = session

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    def _get_session(self) -> tuple[Session, bool]:
        """Return (session, owned). If owned=True the caller must close it."""
        if self._external_session is not None:
            return self._external_session, False
        return get_session(), True

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def create_agent(self, data: AgentCreate) -> AgentRead:
        """
        Register a new agent in the mAIb registry.

        Raises DuplicateAgent if (name, product_id, layer_level) already exists.
        Initial lifecycle state is always PROVISIONING; Packet 3 drives it to ACTIVE.
        """
        session, owned = self._get_session()
        try:
            existing = (
                session.query(AgentModel)
                .filter(
                    AgentModel.name == data.name,
                    AgentModel.product_id == data.product_id,
                    AgentModel.layer_level == data.layer_level,
                )
                .first()
            )
            if existing:
                raise DuplicateAgent(
                    f"Agent '{data.name}' already registered for product_id='{data.product_id}' "
                    f"at layer {data.layer_level}."
                )

            agent = AgentModel(
                name=data.name,
                layer_level=data.layer_level,
                product_id=data.product_id,
                stream=data.stream,
                owner_authority=data.owner_authority,
                lifecycle_state=AgentLifecycleState.PROVISIONING,
                agent_type=data.agent_type,  # D1 — persisted at creation; immutable after
                configuration=data.configuration,
            )
            session.add(agent)
            session.commit()
            session.refresh(agent)
            return AgentRead.model_validate(agent)
        finally:
            if owned:
                session.close()

    def get_agent(self, agent_id: str, product_id: str) -> AgentRead:
        """
        Fetch a single agent by ID, scoped to product_id.

        Raises AgentNotFound if the record does not exist or belongs to a
        different tenant (identical error to prevent tenant enumeration).
        """
        session, owned = self._get_session()
        try:
            agent = self._require_agent(session, agent_id, product_id)
            return AgentRead.model_validate(agent)
        finally:
            if owned:
                session.close()

    def list_tenant_agents(self, product_id: str) -> list[AgentRead]:
        """
        Return all agents registered under product_id.

        This is the primary multi-tenancy query. product_id is never optional.
        """
        session, owned = self._get_session()
        try:
            agents = (
                session.query(AgentModel)
                .filter(AgentModel.product_id == product_id)
                .order_by(AgentModel.layer_level, AgentModel.name)
                .all()
            )
            return [AgentRead.model_validate(a) for a in agents]
        finally:
            if owned:
                session.close()

    def list_root_agents(self, product_id: Optional[str] = None) -> list[AgentModel]:
        """
        Return agents with no parent in HierarchyMap, optionally filtered by product_id.
        Used to seed the full hierarchy view when no root agent_id is specified.
        """
        session, owned = self._get_session()
        try:
            child_ids_q = session.query(HierarchyMap.child_agent_id)
            q = session.query(AgentModel).filter(
                AgentModel.id.notin_(child_ids_q)
            )
            if product_id:
                q = q.filter(AgentModel.product_id == product_id)
            return q.order_by(AgentModel.layer_level, AgentModel.name).all()
        finally:
            if owned:
                session.close()

    def get_hierarchy(self, agent_id: str, product_id: str) -> HierarchyNode:
        """
        Build the full downward hierarchy tree rooted at agent_id.

        Recursively follows HierarchyMap edges. All traversed nodes must share
        product_id — cross-tenant edges cannot exist by construction, but are
        validated defensively.

        Raises AgentNotFound if the root agent does not exist under product_id.
        """
        session, owned = self._get_session()
        try:
            root = self._require_agent(session, agent_id, product_id)
            return self._build_hierarchy_node(session, root, product_id, visited=set())
        finally:
            if owned:
                session.close()

    def add_hierarchy_link(
        self, data: HierarchyLinkCreate, product_id: str
    ) -> HierarchyLinkRead:
        """
        Add a parent→child directed edge between two agents in the same tenant.

        Raises TenantMismatch if the two agents belong to different product_ids.
        Raises AgentNotFound if either agent does not exist under product_id.
        """
        session, owned = self._get_session()
        try:
            parent = self._require_agent(session, data.parent_agent_id, product_id)
            child = self._require_agent(session, data.child_agent_id, product_id)

            if parent.product_id != child.product_id:
                raise TenantMismatch(
                    f"Cannot link agents across tenants: "
                    f"'{parent.product_id}' → '{child.product_id}'"
                )

            link = HierarchyMap(
                parent_agent_id=parent.id,
                child_agent_id=child.id,
                relationship_type=data.relationship_type,
            )
            session.add(link)
            session.commit()
            session.refresh(link)
            return HierarchyLinkRead.model_validate(link)
        finally:
            if owned:
                session.close()

    def update_lifecycle_state(
        self,
        agent_id: str,
        product_id: str,
        new_state: AgentLifecycleState,
    ) -> AgentRead:
        """
        Persist a lifecycle state transition decided by the State Machine (Packet 3).

        This method is intentionally thin — it applies the transition but does NOT
        validate authority or guard rules. That logic belongs entirely to Packet 3.

        Packet 3 calls this after its own transition guards have passed.
        """
        session, owned = self._get_session()
        try:
            agent = self._require_agent(session, agent_id, product_id)
            agent.lifecycle_state = new_state
            session.commit()
            session.refresh(agent)
            return AgentRead.model_validate(agent)
        finally:
            if owned:
                session.close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _require_agent(
        self, session: Session, agent_id: str, product_id: str
    ) -> AgentModel:
        """
        Fetch an AgentModel filtered by both id AND product_id.
        Using both prevents cross-tenant lookup via guessed UUIDs.
        """
        agent = (
            session.query(AgentModel)
            .filter(
                AgentModel.id == agent_id,
                AgentModel.product_id == product_id,
            )
            .first()
        )
        if agent is None:
            raise AgentNotFound(
                f"Agent '{agent_id}' not found for product_id='{product_id}'."
            )
        return agent

    def _build_hierarchy_node(
        self,
        session: Session,
        agent: AgentModel,
        product_id: str,
        visited: set[str],
    ) -> HierarchyNode:
        """Recursively build a HierarchyNode tree, guarding against cycles."""
        visited.add(agent.id)

        child_nodes: list[HierarchyNode] = []
        for edge in agent.children:
            child_agent = edge.child
            if child_agent.id in visited:
                # Cycle guard — should never happen in a well-formed registry.
                continue
            if child_agent.product_id != product_id:
                # Defensive: skip any cross-tenant edge that slipped through.
                continue
            child_nodes.append(
                self._build_hierarchy_node(session, child_agent, product_id, visited)
            )

        return HierarchyNode(
            agent=AgentRead.model_validate(agent),
            children=child_nodes,
        )
