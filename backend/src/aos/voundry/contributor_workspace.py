"""
Voundry contributor workspaces — the role-scoped surface a contributor works in.

A contributor can hold several role-assignments across ventures (Marketing on
one, Sales on another). Each assignment resolves to a dedicated WORKSPACE keyed
by (discipline × vertical): the tasks to do, the tools to connect (with live
status), the AI agents allocated to assist, the resources to draw on, the
checklist to follow, the discussion thread, and any approval missions routed to
them.

This service only READS and COMPOSES existing state (work units, ventures,
blueprints, judgment queue, threads) — it never mutates. Mutations still flow
through the existing service (apply/submit) and judgment engine (claim/decide).
"""

from __future__ import annotations

from typing import Any, Optional

from src.aos.voundry.contracts import Idea, VentureUnit, WorkspaceFile, WorkUnit
from src.aos.voundry.persistence.repository import voundry_repo
from src.aos.voundry.workspace_blueprint import (
    Vertical,
    agent_catalog_for,
    derive_vertical,
    discipline_from_role_type,
    find_agent,
    resolved_blueprint,
)

# Work-unit statuses that count as an "open" task the contributor still acts on.
_OPEN_STATUSES = {"assigned", "submitted", "under_ai_review", "under_human_review", "disputed", "rejected"}


class WorkspaceNotFound(Exception):
    pass


class ContributorWorkspaceService:
    def __init__(self, repo=voundry_repo) -> None:
        self._repo = repo

    # -- helpers -------------------------------------------------------------

    def _venture_vertical(self, venture: Optional[VentureUnit]) -> Vertical:
        """The venture's vertical: stored value if present/valid, else derived
        from its idea (keeps older/seed ventures working)."""
        if venture is None:
            return Vertical.GENERIC
        stored = (venture.vertical or "").strip().lower()
        try:
            if stored and stored != "generic":
                return Vertical(stored)
        except ValueError:
            pass
        # Derive from the idea behind the venture's candidate.
        cand = self._repo.get_candidate(venture.candidate_id)
        if cand:
            idea_d = self._repo.get_idea(cand.get("idea_id", ""))
            if idea_d:
                idea = Idea(**idea_d)
                return derive_vertical(idea.market, idea.summary, idea.business_model, venture.name)
        if stored:
            try:
                return Vertical(stored)
            except ValueError:
                pass
        return Vertical.GENERIC

    def _venture_for(self, work_unit: WorkUnit) -> Optional[VentureUnit]:
        d = self._repo.get_venture(work_unit.venture_unit_id)
        return VentureUnit(**d) if d else None

    # -- hub -----------------------------------------------------------------

    def list_role_assignments(self, contributor_id: str) -> list[dict]:
        """The contributor's role-assignments across ventures (workspace hub)."""
        out: list[dict] = []
        for w in self._repo.list_work_units():
            if w.get("assigned_to") != contributor_id:
                continue
            wu = WorkUnit(**w)
            venture = self._venture_for(wu)
            discipline = discipline_from_role_type(wu.role_type)
            vertical = self._venture_vertical(venture)
            bp = resolved_blueprint(discipline, vertical)
            out.append({
                "work_unit_id": wu.id,
                "work_unit_title": wu.title,
                "status": wu.status.value,
                "is_open": wu.status.value in _OPEN_STATUSES,
                "venture_id": wu.venture_unit_id,
                "venture_name": venture.name if venture else "—",
                "discipline": discipline.value,
                "vertical": vertical.value,
                "headline": bp.headline,
                "tool_count": len(bp.tools),
                "agent_count": len(bp.agents),
                "connected_tools": sum(1 for t in bp.tools if t.status == "connected"),
            })
        # Open assignments first, then by title for stability.
        out.sort(key=lambda r: (not r["is_open"], r["work_unit_title"]))
        return out

    # -- room ----------------------------------------------------------------

    def role_workspace(self, contributor_id: str, work_unit_id: str) -> dict[str, Any]:
        """The dedicated workspace for one role-assignment. Ownership-checked."""
        w = self._repo.get_work_unit(work_unit_id)
        if w is None:
            raise WorkspaceNotFound(work_unit_id)
        wu = WorkUnit(**w)
        if wu.assigned_to != contributor_id:
            raise WorkspaceNotFound(f"{work_unit_id} (not assigned to you)")

        venture = self._venture_for(wu)
        discipline = discipline_from_role_type(wu.role_type)
        vertical = self._venture_vertical(venture)
        bp = resolved_blueprint(discipline, vertical)

        # Roster = the role's default allocated agents + any the contributor has
        # requested. The catalog offers the rest of the role-relevant skills.
        prof = self._repo.get_contributor(contributor_id)
        added_keys = (prof or {}).get("added_agents", {}).get(discipline.value, []) if prof else []
        allocated = list(bp.agents)
        base_keys = {a.key for a in allocated}
        for key in added_keys:
            if key not in base_keys:
                extra = find_agent(discipline, key)
                if extra is not None:
                    allocated.append(extra)
        catalog = [
            a for a in agent_catalog_for(discipline)
            if a.key not in {ag.key for ag in allocated}
        ]

        from src.aos.voundry.workspace import workspace_service

        thread = workspace_service.thread(work_unit_id)
        # The commercial edition surfaces judgment/approval missions here. The
        # open-source individual edition has no judgment desk.
        try:
            from src.aos.voundry.judgment import judgment_service
            queue = judgment_service.list_queue_for(contributor_id)
            venture_missions = [t for t in queue if t.get("venture_unit_id") == wu.venture_unit_id]
        except ImportError:
            queue, venture_missions = [], []

        return {
            "role": {
                "discipline": discipline.value,
                "vertical": vertical.value,
                "headline": bp.headline,
            },
            "venture": {
                "id": venture.id if venture else wu.venture_unit_id,
                "name": venture.name if venture else "—",
                "status": venture.status.value if venture else "unknown",
                "vertical": vertical.value,
            },
            "task": {
                "work_unit_id": wu.id,
                "title": wu.title,
                "description": wu.description,
                "status": wu.status.value,
                "role_type": wu.role_type,
                "acceptance_criteria": wu.acceptance_criteria,
                "evidence_required": wu.evidence_required,
                "estimated_credits_min": wu.estimated_credits_min,
                "estimated_credits_max": wu.estimated_credits_max,
                "deadline": wu.deadline,
            },
            "toolkit": [t.model_dump(mode="json") for t in bp.tools],
            "agents": [a.model_dump(mode="json") for a in allocated],
            "agent_catalog": [a.model_dump(mode="json") for a in catalog],
            "resources": [r.model_dump(mode="json") for r in bp.resources],
            "checklist": bp.checklist,
            "thread": thread,
            "agent_runs": self._recent_agent_runs(work_unit_id),
            "files": self._repo.list_workspace_files_for_work_unit(work_unit_id),
            "connectors": self._connector_catalog(),
            "connected_tools": self._repo.list_connected_tools_for_work_unit(work_unit_id),
            "write_requests": self._write_requests(contributor_id, work_unit_id),
            "approval_missions": {
                "in_this_venture": len(venture_missions),
                "total_available": len(queue),
                "items": venture_missions[:5],
            },
        }

    def _recent_agent_runs(self, work_unit_id: str, *, limit: int = 5) -> list[dict]:
        from src.aos.voundry.agent_runtime import agent_runtime
        return agent_runtime.list_runs(work_unit_id)[:limit]

    def request_agent(self, contributor_id: str, work_unit_id: str, agent_key: str) -> dict:
        """Contributor requests an extra role-relevant agent for a workspace.
        Ownership-checked; discipline resolved from the assignment."""
        w = self._repo.get_work_unit(work_unit_id)
        if w is None:
            raise WorkspaceNotFound(work_unit_id)
        wu = WorkUnit(**w)
        if wu.assigned_to != contributor_id:
            raise WorkspaceNotFound(f"{work_unit_id} (not assigned to you)")
        discipline = discipline_from_role_type(wu.role_type)
        from src.aos.voundry.contributor import contributor_service
        contributor_service.request_agent(
            contributor_id, discipline=discipline.value, agent_key=agent_key,
        )
        return self.role_workspace(contributor_id, work_unit_id)

    # -- workspace files -----------------------------------------------------

    _MAX_FILE = 20_000

    def _owned_wu(self, contributor_id: str, work_unit_id: str) -> WorkUnit:
        w = self._repo.get_work_unit(work_unit_id)
        if w is None:
            raise WorkspaceNotFound(work_unit_id)
        wu = WorkUnit(**w)
        if wu.assigned_to != contributor_id:
            raise WorkspaceNotFound(f"{work_unit_id} (not assigned to you)")
        return wu

    def save_file(
        self, contributor_id: str, work_unit_id: str, *, name: str, content: str,
        kind: str = "note", source_agent_key: str = "", source_agent_name: str = "",
    ) -> dict:
        self._owned_wu(contributor_id, work_unit_id)
        name = (name or "").strip() or "Untitled"
        f = WorkspaceFile(
            work_unit_id=work_unit_id, contributor_id=contributor_id,
            name=name[:200], kind=kind, content=(content or "")[: self._MAX_FILE],
            source_agent_key=source_agent_key, source_agent_name=source_agent_name,
        )
        self._repo.save_workspace_file(f)
        from src.aos.voundry.governance import voundry_audit
        voundry_audit.append(
            actor_id=contributor_id, actor_type="human", action="workspace.file_saved",
            resource_type="work_unit", resource_id=work_unit_id, detail=f.name[:120],
        )
        return f.model_dump(mode="json")

    def list_files(self, contributor_id: str, work_unit_id: str) -> list[dict]:
        self._owned_wu(contributor_id, work_unit_id)
        return self._repo.list_workspace_files_for_work_unit(work_unit_id)

    def delete_file(self, contributor_id: str, work_unit_id: str, file_id: str) -> None:
        self._owned_wu(contributor_id, work_unit_id)
        existing = self._repo.get_workspace_file(file_id)
        if existing is None or existing.get("work_unit_id") != work_unit_id:
            raise WorkspaceNotFound(f"file {file_id}")
        self._repo.delete_workspace_file(file_id)

    @staticmethod
    def _connector_catalog() -> list[dict]:
        from src.aos.voundry.connectors import connector_service
        return connector_service.catalog()

    @staticmethod
    def _write_requests(contributor_id: str, work_unit_id: str) -> list[dict]:
        from src.aos.voundry.connectors import connector_service
        return connector_service.list_write_requests(contributor_id, work_unit_id)

    def approval_missions(self, contributor_id: str) -> list[dict]:
        """All approval (judgment) missions routed to this contributor."""
        from src.aos.voundry.judgment import judgment_service
        return judgment_service.list_queue_for(contributor_id)


# Module-level singleton
contributor_workspace_service = ContributorWorkspaceService()
