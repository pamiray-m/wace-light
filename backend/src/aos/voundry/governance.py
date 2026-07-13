"""
WACE governance — the open-source edition.

Keeps WACE's governed core intact:
  - Append-only WORM audit (VoundryAuditService -> voundry_audit_events table).
  - Kill switch (src/core/safety/autonomy_gate): AI/autonomous steps refuse to
    act when halted.
  - A simple, self-contained human-approval gate for connector write-backs: the
    individual approves their own writes; a pending write never executes until
    approved. (The commercial edition backs this with the GEL authority stack.)
"""

from __future__ import annotations

from typing import Any, Optional

from src.core.safety.autonomy_gate import halt_reasons, is_autonomy_halted

from src.aos.voundry.contracts import VoundryAuditEvent
from src.aos.voundry.persistence.repository import voundry_repo

VOUNDRY_AUTONOMY_SCOPE = None


class AutonomyHaltedError(Exception):
    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("WACE autonomy is halted by the kill switch: " + (", ".join(reasons) or "halted"))


class HumanApprovalRequiredError(Exception):
    def __init__(self, contract_id: str, what: str) -> None:
        self.contract_id = contract_id
        super().__init__(f"Human approval required for {what} (id='{contract_id}'). Approve it first.")


def require_autonomy_available(scope: str = VOUNDRY_AUTONOMY_SCOPE) -> None:
    if is_autonomy_halted(scope):
        raise AutonomyHaltedError(halt_reasons(scope))


class VoundryAuditService:
    """Append-only audit trail - every governed action, on the record."""

    def __init__(self, repo=voundry_repo) -> None:
        self._repo = repo

    def append(self, *, actor_id: str, actor_type: str, action: str, resource_type: str,
               resource_id: str, detail: str = "", metadata: Optional[dict[str, Any]] = None) -> VoundryAuditEvent:
        event = VoundryAuditEvent(
            actor_id=actor_id, actor_type=actor_type, action=action,
            resource_type=resource_type, resource_id=resource_id,
            detail=detail, metadata=metadata or {},
        )
        self._repo.append_audit(event)
        return event

    def list_events(self, *, limit: int = 500) -> list[dict]:
        return self._repo.list_audit(limit=limit)

    def list_for_resource(self, resource_id: str, *, limit: int = 120) -> list[dict]:
        events = self._repo.list_audit_recent(limit=800)
        return [e for e in events if e.get("resource_id") == resource_id][:limit]

    def list_recent(self, *, limit: int = 150) -> list[dict]:
        return self._repo.list_audit_recent(limit=limit)


voundry_audit = VoundryAuditService()


def _key(request_id: str) -> str:
    return f"connwrite:{request_id}"


def request_connector_write_approval(request_id: str, summary: str, lineage_id: str = "", repo=voundry_repo) -> str:
    repo.save_kv(_key(request_id), {"status": "pending", "summary": summary, "lineage_id": lineage_id})
    return request_id


def connector_write_contract_id(request_id: str, repo=voundry_repo) -> str:
    return request_id


def is_connector_write_approved(request_id: str, repo=voundry_repo) -> bool:
    return (repo.get_kv(_key(request_id)) or {}).get("status") == "approved"


def approve_gel_task(task_id: str, approver_id: str, repo=voundry_repo) -> None:
    rec = repo.get_kv(_key(task_id)) or {}
    rec.update({"status": "approved", "approver_id": approver_id})
    repo.save_kv(_key(task_id), rec)


def reject_gel_task(task_id: str, approver_id: str, reason: str = "", repo=voundry_repo) -> None:
    rec = repo.get_kv(_key(task_id)) or {}
    rec.update({"status": "rejected", "approver_id": approver_id, "reason": reason})
    repo.save_kv(_key(task_id), rec)


def list_pending_tasks(*, limit: int = 100) -> list[dict]:
    return []
