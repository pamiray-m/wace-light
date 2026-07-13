"""
Voundry collaboration workspace — threaded discussion per work unit.

Turns the work unit from a drop-box into a collaboration surface: contributors,
reviewers, and the AI Venture Manager exchange comments and notes against a
specific work unit, all persisted and ordered. Every message is tied to its
venture for the cockpit activity view.
"""

from __future__ import annotations

from src.aos.voundry.contracts import WorkspaceKind, WorkspaceMessage
from src.aos.voundry.governance import voundry_audit
from src.aos.voundry.persistence.repository import voundry_repo


class WorkspaceError(Exception):
    pass


class WorkUnitNotFound(Exception):
    pass


class WorkspaceService:
    def __init__(self, repo=voundry_repo, audit=voundry_audit) -> None:
        self._repo = repo
        self._audit = audit

    def post(
        self, work_unit_id: str, *, author_id: str, author_role: str = "contributor",
        body: str, kind: WorkspaceKind = WorkspaceKind.COMMENT,
    ) -> WorkspaceMessage:
        if not body or not body.strip():
            raise WorkspaceError("Message body is required")
        wu = self._repo.get_work_unit(work_unit_id)
        if wu is None:
            raise WorkUnitNotFound(work_unit_id)
        msg = WorkspaceMessage(
            work_unit_id=work_unit_id, venture_unit_id=wu.get("venture_unit_id", ""),
            author_id=author_id, author_role=author_role, kind=kind, body=body.strip(),
        )
        self._repo.save_message(msg)
        self._audit.append(
            actor_id=author_id, actor_type="ai" if author_role == "ai" else "human",
            action="workspace.message_posted", resource_type="work_unit", resource_id=work_unit_id,
            detail=kind.value,
        )
        return msg

    def thread(self, work_unit_id: str) -> list[dict]:
        return self._repo.list_messages_for_work_unit(work_unit_id)


workspace_service = WorkspaceService()
