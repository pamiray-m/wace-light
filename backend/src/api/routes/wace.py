"""
WACE Light — the open-source HTTP API (individual edition).

A focused FastAPI router over the governed engine: register/sign in, provision a
personal desk, connect governed tools, run a governed AI agent, drop content
into the Smart Workspace, preview SAIb redaction, set your BYOK key, and read
your WORM receipts. Every tool is read-only by default, SAIb-scrubbed, and
receipted; writes go through a human-approval gate.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel

from src.aos.voundry.auth import VoundryAuthError, VoundryRole, voundry_auth_service

router = APIRouter(prefix="/voundry", tags=["wace"])


def principal(authorization: str = Header(default="")):
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="Sign in required.")
    try:
        return voundry_auth_service.principal_from_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")


def _cid(p) -> str:
    return p.contributor_id or p.account_id


def _own(cid: str, work_unit_id: str) -> None:
    from src.aos.voundry.persistence.repository import voundry_repo
    w = voundry_repo.get_work_unit(work_unit_id)
    if w is None or w.get("assigned_to") != cid:
        raise HTTPException(status_code=404, detail="Not your desk.")


# --- auth ------------------------------------------------------------------

class RegisterBody(BaseModel):
    email: str
    password: str
    display_name: str = ""


class LoginBody(BaseModel):
    email: str
    password: str


@router.post("/auth/register")
def register(body: RegisterBody) -> dict[str, Any]:
    try:
        p, token = voundry_auth_service.register(
            email=body.email, password=body.password,
            role=VoundryRole.CONTRIBUTOR, display_name=body.display_name, accepted_terms=True)
    except VoundryAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"token": token, "principal": _pub(p)}


@router.post("/auth/login")
def login(body: LoginBody) -> dict[str, Any]:
    try:
        p, token = voundry_auth_service.login(email=body.email, password=body.password)
    except VoundryAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    return {"token": token, "principal": _pub(p)}


@router.get("/auth/me")
def me(p=Depends(principal)) -> dict[str, Any]:
    return _pub(p)


def _pub(p) -> dict[str, Any]:
    return {"account_id": p.account_id, "email": p.email, "role": p.role.value,
            "display_name": p.display_name, "contributor_id": p.contributor_id,
            "investor_id": getattr(p, "investor_id", None), "can_govern": True}


# --- onboarding + personal desk -------------------------------------------

class DeskBody(BaseModel):
    role: str = ""


@router.get("/portal/onboarding-suite")
def onboarding_suite(role: str = "", p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.connectors import connector_service
    from src.aos.voundry.onboarding_suite import onboarding_suite as suite
    return suite(role, connector_service.catalog())


@router.post("/portal/my-desk")
def my_desk(body: DeskBody, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.onboarding_suite import ensure_personal_desk
    return {"work_unit_id": ensure_personal_desk(_cid(p), body.role or "")}


@router.get("/portal/workspaces")
def workspaces(p=Depends(principal)) -> list[dict]:
    from src.aos.voundry.contributor_workspace import contributor_workspace_service
    return contributor_workspace_service.list_role_assignments(_cid(p))


@router.get("/portal/workspaces/{work_unit_id}")
def workspace_room(work_unit_id: str, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.contributor_workspace import contributor_workspace_service
    _own(_cid(p), work_unit_id)
    return contributor_workspace_service.role_workspace(_cid(p), work_unit_id)


# --- governed connectors ---------------------------------------------------

class ConnectBody(BaseModel):
    connector_key: str
    label: str = ""
    bridge_id: str = ""
    custom_spec: Optional[dict] = None
    cloud_config: Optional[dict] = None


class InvokeBody(BaseModel):
    action: str
    params: dict[str, str] = {}


@router.get("/portal/connectors/catalog")
def catalog(p=Depends(principal)) -> list[dict]:
    from src.aos.voundry.connectors import connector_service
    return connector_service.catalog()


@router.post("/portal/workspaces/{work_unit_id}/connectors")
def connect(work_unit_id: str, body: ConnectBody, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.connectors import ConnectorError, connector_service
    _own(_cid(p), work_unit_id)
    try:
        return connector_service.connect(_cid(p), work_unit_id, connector_key=body.connector_key,
                                         label=body.label, bridge_id=body.bridge_id,
                                         custom_spec=body.custom_spec, cloud_config=body.cloud_config)
    except ConnectorError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/portal/workspaces/{work_unit_id}/connectors/{connected_id}/authorize-url")
def authorize_url(work_unit_id: str, connected_id: str, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.connectors import ConnectorError, connector_service
    _own(_cid(p), work_unit_id)
    try:
        return {"authorize_url": connector_service.authorize_url_for(_cid(p), work_unit_id, connected_id)}
    except ConnectorError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


class CustomTestBody(BaseModel):
    custom_spec: dict
    bridge_id: str = ""


@router.post("/portal/workspaces/{work_unit_id}/custom-test")
def custom_test(work_unit_id: str, body: CustomTestBody, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.connectors import ConnectorError, connector_service
    _own(_cid(p), work_unit_id)
    try:
        return connector_service.test_custom_spec(_cid(p), work_unit_id, custom_spec=body.custom_spec, bridge_id=body.bridge_id)
    except ConnectorError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/portal/workspaces/{work_unit_id}/connectors/{connected_id}/invoke")
def invoke(work_unit_id: str, connected_id: str, body: InvokeBody, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.connectors import ConnectorError, connector_service
    _own(_cid(p), work_unit_id)
    try:
        return connector_service.invoke(_cid(p), work_unit_id, connected_id, action=body.action, params=body.params)
    except ConnectorError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.delete("/portal/workspaces/{work_unit_id}/connectors/{connected_id}")
def disconnect(work_unit_id: str, connected_id: str, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.connectors import connector_service
    _own(_cid(p), work_unit_id)
    connector_service.disconnect(_cid(p), work_unit_id, connected_id)
    return {"ok": True}


# --- governed AI agent -----------------------------------------------------

class AnalyzeBody(BaseModel):
    agent_key: str
    source: str
    data: str


@router.post("/portal/workspaces/{work_unit_id}/agents/analyze")
def analyze(work_unit_id: str, body: AnalyzeBody, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.agent_runtime import AgentRunError, agent_runtime
    _own(_cid(p), work_unit_id)
    try:
        return agent_runtime.analyze_data(contributor_id=_cid(p), work_unit_id=work_unit_id,
                                          agent_key=body.agent_key, source=body.source, data=body.data)
    except AgentRunError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# --- Smart Workspace: ingest + SAIb preview --------------------------------

class SaibBody(BaseModel):
    text: str = ""


@router.post("/portal/saib-preview")
def saib_preview(body: SaibBody, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.ingest import preview_redaction
    return preview_redaction((body.text or "")[:20000])


@router.post("/portal/workspaces/{work_unit_id}/ingest")
async def ingest(work_unit_id: str, file: UploadFile = File(...), p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.ingest import IngestError, ingest_file
    _own(_cid(p), work_unit_id)
    data = await file.read()
    try:
        return ingest_file(_cid(p), work_unit_id, file.filename or "file", data)
    except IngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# --- BYOK ------------------------------------------------------------------

class LlmKeyBody(BaseModel):
    api_key: str = ""
    allow_platform_fallback: bool = True


@router.get("/portal/llm-config")
def llm_config(p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.byok import llm_config as cfg
    return cfg()


@router.post("/portal/llm-key")
def set_llm_key(body: LlmKeyBody, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.byok import ByokError, set_llm_key as setk
    try:
        return setk(_cid(p), body.api_key, body.allow_platform_fallback)
    except ByokError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.delete("/portal/llm-key")
def clear_llm_key(p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.byok import clear_llm_key as clr
    return clr(_cid(p))


# --- WORM receipts ---------------------------------------------------------

@router.get("/portal/workspaces/{work_unit_id}/receipts")
def receipts(work_unit_id: str, p=Depends(principal)) -> list[dict]:
    from src.aos.voundry.governance import voundry_audit
    _own(_cid(p), work_unit_id)
    return voundry_audit.list_for_resource(work_unit_id, limit=200)


# --- agents: request / run / investigate / shift-report --------------------

class AgentKeyBody(BaseModel):
    agent_key: str


class RunBody(BaseModel):
    agent_key: str
    brief: str


class InvestigateBody(BaseModel):
    agent_key: str
    incident: str


@router.post("/portal/workspaces/{work_unit_id}/agents/request")
def request_agent(work_unit_id: str, body: AgentKeyBody, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.contributor_workspace import contributor_workspace_service
    _own(_cid(p), work_unit_id)
    try:
        return contributor_workspace_service.request_agent(_cid(p), work_unit_id, body.agent_key)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/portal/workspaces/{work_unit_id}/agents/run")
def run_agent(work_unit_id: str, body: RunBody, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.agent_runtime import AgentRunError, agent_runtime
    _own(_cid(p), work_unit_id)
    try:
        return agent_runtime.run(contributor_id=_cid(p), work_unit_id=work_unit_id,
                                 agent_key=body.agent_key, brief=body.brief).model_dump(mode="json")
    except AgentRunError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/portal/workspaces/{work_unit_id}/agents/investigate")
def investigate(work_unit_id: str, body: InvestigateBody, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.agent_runtime import AgentRunError, agent_runtime
    _own(_cid(p), work_unit_id)
    try:
        return agent_runtime.investigate(contributor_id=_cid(p), work_unit_id=work_unit_id,
                                         agent_key=body.agent_key, incident=body.incident)
    except AgentRunError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/portal/workspaces/{work_unit_id}/agents/shift-report")
def shift_report(work_unit_id: str, body: AgentKeyBody, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.agent_runtime import AgentRunError, agent_runtime
    _own(_cid(p), work_unit_id)
    try:
        return agent_runtime.shift_report(contributor_id=_cid(p), work_unit_id=work_unit_id, agent_key=body.agent_key)
    except AgentRunError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# --- Flight Recorder: saved files ------------------------------------------

class SaveFileBody(BaseModel):
    name: str
    content: str
    kind: str = "note"
    source_agent_key: str = ""
    source_agent_name: str = ""


@router.post("/portal/workspaces/{work_unit_id}/files")
def save_file(work_unit_id: str, body: SaveFileBody, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.contributor_workspace import contributor_workspace_service
    _own(_cid(p), work_unit_id)
    return contributor_workspace_service.save_file(
        _cid(p), work_unit_id, name=body.name, content=body.content, kind=body.kind,
        source_agent_key=body.source_agent_key, source_agent_name=body.source_agent_name)


@router.delete("/portal/workspaces/{work_unit_id}/files/{file_id}")
def delete_file(work_unit_id: str, file_id: str, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.contributor_workspace import contributor_workspace_service
    _own(_cid(p), work_unit_id)
    contributor_workspace_service.delete_file(_cid(p), work_unit_id, file_id)
    return {"ok": True, "deleted": file_id}


# --- governed write-back approvals -----------------------------------------

class DecideBody(BaseModel):
    approve: bool
    reason: str = ""


@router.get("/portal/approvals")
def approvals(p=Depends(principal)) -> list[dict]:
    from src.aos.voundry.connectors import connector_service
    return connector_service.list_pending_write_backs()


@router.post("/portal/approvals/{request_id}/decide")
def decide(request_id: str, body: DecideBody, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.connectors import ConnectorError, connector_service
    try:
        return connector_service.decide_write_back(_cid(p), request_id, approve=body.approve, reason=body.reason)
    except ConnectorError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/portal/receipts")
def all_receipts(p=Depends(principal)) -> list[dict]:
    from src.aos.voundry.governance import voundry_audit
    return voundry_audit.list_recent(limit=500)


# --- desk thread (comms) ---------------------------------------------------

class PostMsgBody(BaseModel):
    body: str


@router.get("/portal/work-units/{work_unit_id}/messages")
def thread(work_unit_id: str, p=Depends(principal)) -> list[dict]:
    from src.aos.voundry.workspace import workspace_service
    _own(_cid(p), work_unit_id)
    return workspace_service.thread(work_unit_id)


@router.post("/portal/work-units/{work_unit_id}/messages")
def post_message(work_unit_id: str, body: PostMsgBody, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.workspace import WorkspaceError, workspace_service
    _own(_cid(p), work_unit_id)
    try:
        return workspace_service.post(work_unit_id, author_id=_cid(p), author_role="contributor", body=body.body).model_dump(mode="json")
    except WorkspaceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# --- saved SQL queries -----------------------------------------------------

class SaveQueryBody(BaseModel):
    name: str
    sql: str


@router.get("/portal/workspaces/{work_unit_id}/sql/queries")
def list_queries(work_unit_id: str, p=Depends(principal)) -> list[dict]:
    from src.aos.voundry.persistence.repository import voundry_repo
    _own(_cid(p), work_unit_id)
    return voundry_repo.list_queries_for_work_unit(work_unit_id)


@router.post("/portal/workspaces/{work_unit_id}/sql/queries")
def save_query(work_unit_id: str, body: SaveQueryBody, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.contracts import SavedQuery
    from src.aos.voundry.persistence.repository import voundry_repo
    _own(_cid(p), work_unit_id)
    q = SavedQuery(work_unit_id=work_unit_id, contributor_id=_cid(p), name=body.name, sql=body.sql)
    voundry_repo.save_query(q)
    return q.model_dump(mode="json")


@router.delete("/portal/workspaces/{work_unit_id}/sql/queries/{query_id}")
def delete_query(work_unit_id: str, query_id: str, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.persistence.repository import voundry_repo
    _own(_cid(p), work_unit_id)
    voundry_repo.delete_query(query_id)
    return {"ok": True, "deleted": query_id}


# --- governed terminal: explain + saved runbooks ---------------------------

class ExplainBody(BaseModel):
    host: str = ""
    command: str = ""
    output: str = ""


@router.post("/portal/workspaces/{work_unit_id}/terminal/explain")
def explain(work_unit_id: str, body: ExplainBody, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.agent_runtime import agent_runtime
    _own(_cid(p), work_unit_id)
    return agent_runtime.explain_terminal(contributor_id=_cid(p), work_unit_id=work_unit_id,
                                          host=body.host, command=body.command, output=body.output)


class SaveRunbookBody(BaseModel):
    name: str
    commands: list[str] = []


@router.get("/portal/workspaces/{work_unit_id}/terminal/runbooks")
def list_runbooks(work_unit_id: str, p=Depends(principal)) -> list[dict]:
    from src.aos.voundry.persistence.repository import voundry_repo
    _own(_cid(p), work_unit_id)
    return voundry_repo.list_runbooks_for_work_unit(work_unit_id)


@router.post("/portal/workspaces/{work_unit_id}/terminal/runbooks")
def save_runbook(work_unit_id: str, body: SaveRunbookBody, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.contracts import TerminalRunbook
    from src.aos.voundry.persistence.repository import voundry_repo
    _own(_cid(p), work_unit_id)
    rb = TerminalRunbook(work_unit_id=work_unit_id, contributor_id=_cid(p), name=body.name, commands=body.commands)
    voundry_repo.save_runbook(rb)
    return rb.model_dump(mode="json")


@router.delete("/portal/workspaces/{work_unit_id}/terminal/runbooks/{runbook_id}")
def delete_runbook(work_unit_id: str, runbook_id: str, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.persistence.repository import voundry_repo
    _own(_cid(p), work_unit_id)
    voundry_repo.delete_runbook(runbook_id)
    return {"ok": True, "deleted": runbook_id}


@router.get("/portal/workspaces/{work_unit_id}/terminal/hosts")
def terminal_hosts(work_unit_id: str, p=Depends(principal)) -> list[dict]:
    return []   # SSH hosts come via an on-prem bridge; none by default in the individual edition.


# --- on-prem connector bridges ---------------------------------------------

class PairBridgeBody(BaseModel):
    name: str = "On-prem bridge"


@router.get("/portal/workspaces/{work_unit_id}/bridges")
def list_bridges(work_unit_id: str, p=Depends(principal)) -> list[dict]:
    from src.aos.voundry.bridge import bridge_service
    _own(_cid(p), work_unit_id)
    return bridge_service.list_for(work_unit_id)


@router.post("/portal/workspaces/{work_unit_id}/bridge")
def pair_bridge(work_unit_id: str, body: PairBridgeBody, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.bridge import bridge_service
    _own(_cid(p), work_unit_id)
    return bridge_service.pair(_cid(p), work_unit_id, name=body.name)


@router.get("/portal/workspaces/{work_unit_id}/bridge/activity")
def bridge_activity(work_unit_id: str, bridgeId: str = "", p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.bridge import bridge_service
    _own(_cid(p), work_unit_id)
    return bridge_service.activity(work_unit_id, bridgeId or None)


@router.delete("/portal/workspaces/{work_unit_id}/bridge/{bridge_id}")
def revoke_bridge(work_unit_id: str, bridge_id: str, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.bridge import bridge_service
    _own(_cid(p), work_unit_id)
    bridge_service.revoke(work_unit_id, bridge_id)
    return {"ok": True, "revoked": bridge_id}


# --- command center: telemetry + org policy + org tools --------------------

class OrgToolBody(BaseModel):
    name: str
    category: str = "data"
    custom_spec: dict


@router.get("/portal/command-center")
def command_center(p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.connectors import connector_service
    return connector_service.command_center()


@router.get("/portal/policy")
def get_policy(p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.connectors import get_org_policy
    return get_org_policy()


@router.post("/portal/policy")
def set_policy(patch: dict, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.connectors import set_org_policy
    return set_org_policy(patch)


@router.post("/portal/org-tools")
def add_org_tool(body: OrgToolBody, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.connectors import add_org_tool as add
    return add(body.name, body.custom_spec, body.category)


@router.delete("/portal/org-tools/{key}")
def remove_org_tool(key: str, p=Depends(principal)) -> dict[str, Any]:
    from src.aos.voundry.connectors import remove_org_tool as rm
    rm(key)
    return {"ok": True, "removed": key}


# --- enterprise identity (commercial edition only) -------------------------
# The individual edition has no team management; these degrade gracefully so
# the console's admin panels render "not available" instead of erroring.

@router.get("/portal/users")
def users(p=Depends(principal)) -> list[dict]:
    return []


@router.get("/portal/groups")
def groups(p=Depends(principal)) -> list[dict]:
    return []


@router.get("/portal/scim-token")
def scim_token(p=Depends(principal)) -> dict[str, Any]:
    return {"configured": False, "enterprise_only": True}


@router.get("/portal/sso-config")
def sso_config(p=Depends(principal)) -> dict[str, Any]:
    return {"enabled": False, "enterprise_only": True}


@router.get("/portal/saml-config")
def saml_config(p=Depends(principal)) -> dict[str, Any]:
    return {"enabled": False, "enterprise_only": True}


# --- enterprise mutations (commercial edition only) ------------------------
# The console's SSO/SCIM/SAML/user-management panels post here. In the
# individual edition they degrade to a clear 422 instead of a 404 crash.

_ENTERPRISE = "This is available in the commercial (team) edition of WACE, not the individual edition."


@router.post("/portal/sso-config")
@router.post("/portal/saml-config")
@router.post("/portal/scim-token")
@router.post("/portal/governor-group")
@router.post("/portal/users/bulk-active")
def _enterprise_post(p=Depends(principal)) -> dict[str, Any]:
    raise HTTPException(status_code=422, detail=_ENTERPRISE)


@router.post("/portal/users/{account_id}/active")
def _enterprise_user_active(account_id: str, p=Depends(principal)) -> dict[str, Any]:
    raise HTTPException(status_code=422, detail=_ENTERPRISE)


@router.get("/portal/users.csv")
def _enterprise_users_csv(p=Depends(principal)) -> dict[str, Any]:
    raise HTTPException(status_code=422, detail=_ENTERPRISE)
