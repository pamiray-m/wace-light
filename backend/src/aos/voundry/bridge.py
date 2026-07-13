"""
Voundry / WACE connector bridge — plug-n-play on-prem connectivity.

A bridge is a tiny agent the customer runs INSIDE their network. It dials home
to WACE (outbound only — no inbound firewall holes) and executes connector jobs
against local systems (Remedy, databases, internal APIs). Credentials and data
never leave the customer's network; WACE holds only a hash of the pairing secret
and orchestrates a job queue.

Trust model
-----------
- Pairing mints a one-time secret `bridge_id.secret`; WACE stores only
  sha256(secret). The agent authenticates every call with it.
- The agent reports which connectors it can serve (`capabilities`) at hello.
- Reads run on the agent; writes still route through the GEL approval gate in
  WACE and are only enqueued to the agent AFTER a human governor approves.
- The agent re-enforces read-only guards locally (it is the system of record for
  its own database).
"""
from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from src.aos.voundry.contracts import BridgeJob, BridgeJobStatus, ConnectorBridge
from src.aos.voundry.persistence.repository import voundry_repo

_ONLINE_WINDOW = timedelta(seconds=45)   # last_seen within this → "online"


class BridgeError(Exception):
    pass


class BridgeAuthError(Exception):
    pass


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class BridgeService:
    def __init__(self, repo=voundry_repo) -> None:
        self._repo = repo

    # -- pairing (contributor side) -----------------------------------------

    def pair(self, contributor_id: str, work_unit_id: str, *, name: str = "On-prem bridge") -> dict:
        """Create a bridge; return the durable token AND a short one-time pair code."""
        bridge = ConnectorBridge(work_unit_id=work_unit_id, contributor_id=contributor_id,
                                 name=(name or "On-prem bridge")[:80])
        secret = secrets.token_urlsafe(32)
        bridge.token_hash = _sha(secret)
        bridge.pair_secret = secret                       # transient — cleared on claim/expiry
        bridge.pair_code = secrets.token_hex(4).upper()   # e.g. "A1B2C3D4"
        bridge.pair_expires = _now() + timedelta(minutes=30)
        self._repo.save_bridge(bridge)
        return {"bridge": self._public(bridge), "pairing_token": f"{bridge.id}.{secret}",
                "pairing_code": bridge.pair_code}

    def claim(self, code: str) -> dict:
        """A self-pairing agent exchanges a one-time code for its token."""
        code = (code or "").strip().upper()
        if not code:
            raise BridgeError("Missing pairing code.")
        for row in self._repo.list_all_bridges():
            b = ConnectorBridge(**row)
            if b.pair_code and b.pair_code == code:
                if not b.pair_secret:
                    raise BridgeError("This pairing code was already used.")
                exp = b.pair_expires
                if exp and (exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)) < _now():
                    raise BridgeError("This pairing code has expired — pair again.")
                token = f"{b.id}.{b.pair_secret}"
                b.pair_secret, b.pair_expires = "", None    # single-use; keep code for a clear re-claim msg
                self._repo.save_bridge(b)
                return {"token": token}
        raise BridgeError("Unknown pairing code.")

    def status_for(self, work_unit_id: str) -> Optional[dict]:
        """The first bridge paired to this desk (back-compat single-bridge view)."""
        rows = self._repo.list_bridges_for_work_unit(work_unit_id)
        return self._public(ConnectorBridge(**rows[0])) if rows else None

    def list_for(self, work_unit_id: str) -> list[dict]:
        """All bridges on this desk, each with a light job summary (multi-bridge)."""
        out = []
        for row in self._repo.list_bridges_for_work_unit(work_unit_id):
            bridge = ConnectorBridge(**row)
            pub = self._public(bridge)
            summary = {"total": 0, "pending": 0, "running": 0, "done": 0, "failed": 0}
            for jd in self._repo.list_recent_jobs_for_bridge(bridge.id, limit=50):
                job = BridgeJob(**jd)
                summary["total"] += 1
                summary[job.status.value] = summary.get(job.status.value, 0) + 1
            pub["summary"] = summary
            out.append(pub)
        return out

    def activity(self, work_unit_id: str, bridge_id: Optional[str] = None) -> dict:
        """Health + recent-job view for a bridge on the desk (observability)."""
        rows = self._repo.list_bridges_for_work_unit(work_unit_id)
        row = (next((r for r in rows if r.get("id") == bridge_id), None) if bridge_id else (rows[0] if rows else None))
        if row is None:
            return {"status": "none", "jobs": [], "summary": {"total": 0, "done": 0, "failed": 0, "running": 0, "pending": 0}}
        bridge = ConnectorBridge(**row)
        summary = {"total": 0, "pending": 0, "running": 0, "done": 0, "failed": 0}
        jobs = []
        for jd in self._repo.list_recent_jobs_for_bridge(bridge.id, limit=20):
            job = BridgeJob(**jd)
            summary["total"] += 1
            summary[job.status.value] = summary.get(job.status.value, 0) + 1
            lat = None
            if job.updated_at and job.created_at:
                lat = round((job.updated_at - job.created_at).total_seconds(), 2)
            jobs.append({"id": job.id, "connector_key": job.connector_key, "action": job.action,
                         "status": job.status.value,
                         "created_at": job.created_at.isoformat() if job.created_at else "",
                         "latency_s": lat, "error": job.error[:200]})
        pub = self._public(bridge)
        return {"status": pub["status"], "name": pub["name"], "capabilities": pub["capabilities"],
                "last_seen": pub["last_seen"], "allowed_actions": pub["allowed_actions"],
                "summary": summary, "jobs": jobs}

    def set_allowed_actions(self, work_unit_id: str, bridge_id: str, actions: list) -> dict:
        """Restrict a bridge to specific 'connector:action' pairs (empty = allow all)."""
        d = self._repo.get_bridge(bridge_id)
        if d is None or d.get("work_unit_id") != work_unit_id:
            raise BridgeError("No such bridge on this desk.")
        bridge = ConnectorBridge(**d)
        bridge.allowed_actions = [str(a).strip() for a in (actions or []) if str(a).strip()][:100]
        self._repo.save_bridge(bridge)
        return self._public(bridge)

    def revoke(self, work_unit_id: str, bridge_id: str) -> None:
        """Kill a bridge — its token stops working immediately (agent gets 401)."""
        d = self._repo.get_bridge(bridge_id)
        if d is None or d.get("work_unit_id") != work_unit_id:
            raise BridgeError("No such bridge on this desk.")
        self._repo.delete_bridge(bridge_id)

    def _public(self, bridge: ConnectorBridge) -> dict:
        d = bridge.model_dump(mode="json")
        for secret in ("token_hash", "pair_secret", "pair_code", "pair_expires"):
            d.pop(secret, None)                          # never expose secrets
        d["status"] = self._derived_status(bridge)
        return d

    def _derived_status(self, bridge: ConnectorBridge) -> str:
        if bridge.last_seen is None:
            return "unpaired"
        seen = bridge.last_seen if bridge.last_seen.tzinfo else bridge.last_seen.replace(tzinfo=timezone.utc)
        return "online" if _now() - seen <= _ONLINE_WINDOW else "offline"

    # -- authentication (agent side) ----------------------------------------

    def _auth(self, token: str) -> ConnectorBridge:
        bid, _, secret = (token or "").partition(".")
        d = self._repo.get_bridge(bid) if bid and secret else None
        if d is None or not secrets.compare_digest(ConnectorBridge(**d).token_hash, _sha(secret)):
            raise BridgeAuthError("Invalid bridge token.")
        return ConnectorBridge(**d)

    def hello(self, token: str, *, capabilities: Optional[list] = None) -> dict:
        """Agent check-in: refresh last_seen + report which connectors it serves."""
        bridge = self._auth(token)
        if capabilities is not None:
            bridge.capabilities = [str(c) for c in capabilities][:50]
        bridge.last_seen = _now()
        self._repo.save_bridge(bridge)
        return self._public(bridge)

    # -- job queue ----------------------------------------------------------

    def claim_jobs(self, token: str) -> list[dict]:
        """Agent polls for pending work; claimed jobs flip to RUNNING."""
        bridge = self._auth(token)
        bridge.last_seen = _now()
        self._repo.save_bridge(bridge)
        claimed = []
        for row in self._repo.list_pending_jobs_for_bridge(bridge.id):
            job = BridgeJob(**row)
            job.status = BridgeJobStatus.RUNNING
            job.updated_at = _now()
            self._repo.save_bridge_job(job)
            claimed.append({"id": job.id, "connector_key": job.connector_key,
                            "action": job.action, "params": job.params, "spec": job.spec})
        return claimed

    def submit_result(self, token: str, job_id: str, *, result: Optional[dict] = None, error: str = "") -> None:
        bridge = self._auth(token)
        d = self._repo.get_bridge_job(job_id)
        if d is None or d.get("bridge_id") != bridge.id:
            raise BridgeError("Unknown job for this bridge.")
        job = BridgeJob(**d)
        if error:
            job.status, job.error = BridgeJobStatus.FAILED, str(error)[:2000]
        else:
            job.status, job.result = BridgeJobStatus.DONE, (result or {})
        job.updated_at = _now()
        self._repo.save_bridge_job(job)

    def enqueue(self, bridge_id: str, connector_key: str, action: str, params: dict,
                spec: Optional[dict] = None) -> BridgeJob:
        if self._repo.get_bridge(bridge_id) is None:
            raise BridgeError("No such bridge.")
        job = BridgeJob(bridge_id=bridge_id, connector_key=connector_key, action=action,
                        params=params or {}, spec=spec)
        self._repo.save_bridge_job(job)
        return job

    def run_via_bridge(self, bridge_id: str, connector_key: str, action: str, params: dict, *,
                       spec: Optional[dict] = None, timeout: float = 12.0,
                       sleep: Callable[[float], None] = time.sleep,
                       clock: Callable[[], float] = time.monotonic) -> dict:
        """Enqueue a job and wait (bounded) for the agent to return its result."""
        d = self._repo.get_bridge(bridge_id)
        if d is None:
            raise BridgeError("No such bridge.")
        bridge = ConnectorBridge(**d)
        if self._derived_status(bridge) != "online":
            raise BridgeError("Your bridge is offline — start the WACE bridge agent in your network.")
        if bridge.allowed_actions and f"{connector_key}:{action}" not in bridge.allowed_actions:
            raise BridgeError(f"'{connector_key}:{action}' isn't on this bridge's allowlist.")
        job = self.enqueue(bridge_id, connector_key, action, params, spec=spec)
        deadline = clock() + timeout
        while clock() < deadline:
            row = self._repo.get_bridge_job(job.id)
            j = BridgeJob(**row)
            if j.status is BridgeJobStatus.DONE:
                return j.result or {"text": ""}
            if j.status is BridgeJobStatus.FAILED:
                raise BridgeError(j.error or "bridge job failed")
            sleep(0.4)
        raise BridgeError("The bridge did not respond in time (it may be offline or busy).")


bridge_service = BridgeService()
