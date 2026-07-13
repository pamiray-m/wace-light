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


@router.get("/me")
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
        return connector_service.connect(_cid(p), work_unit_id, connector_key=body.connector_key)
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
