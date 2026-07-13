"""
WACE Light — onboarding tool suites + a personal desk.

The light edition (wace.maib.io) greets a new seat with a short "connect your
day-to-day tools" flow, then — once it knows the person's role — offers the
specialized tools that role actually uses, and drops them into their console.

This module is pure mapping + idempotent desk provisioning; the actual connect
uses the existing governed connector flow, so every tool stays read-only by
default, SAIb-scrubbed, and receipted.
"""

from __future__ import annotations

from src.aos.voundry.contracts import (
    Milestone,
    VentureUnit,
    WorkUnit,
    WorkUnitStatus,
)
from src.aos.voundry.persistence.repository import voundry_repo

# The built-in governed AI assistant is always available (it is the LLM gateway,
# not an external service) — surfaced as a tile so onboarding can show it "ready".
AI_ASSISTANT = {"key": "ai_assistant", "name": "AI Assistant", "category": "ai",
                "needs_auth": False, "provider": "", "builtin": True,
                "blurb": "Your governed AI — drafts you own and edit, every run receipted."}

# Day-to-day tools every WACE seat is offered at onboarding (the "light" set).
BASIC_TOOLS: list[str] = [
    "outlook_mail",       # Mail
    "onedrive",           # Microsoft 365 — files
    "outlook_calendar",   # Microsoft 365 — calendar
    "servicenow",         # ServiceNow
    "zoom",               # Zoom
    "slack",              # Slack
    "teams",              # Microsoft Teams
    "web_read",           # basic web reader
]

# After the role is known, the specialized tools that role actually reaches for.
ROLE_TOOLS: dict[str, list[str]] = {
    "it_ops":      ["remedy", "servicenow", "sql_read", "webhook", "jira_sm", "sharepoint_kb"],
    "support":     ["servicenow", "remedy", "jira_sm", "sharepoint_kb", "confluence"],
    "engineering": ["jira", "confluence", "sql_read", "http_json"],
    "data":        ["sql_read", "excel", "http_json", "confluence"],
    "finance":     ["excel", "sql_read", "sharepoint_kb"],
    "sales":       ["zoom", "outlook_calendar", "confluence"],
    "marketing":   ["web_read", "confluence", "excel"],
    "product":     ["jira", "confluence", "zoom"],
    "operations":  ["servicenow", "sql_read", "sharepoint_kb", "jira_sm"],
    "research":    ["web_read", "http_json", "confluence"],
    "legal":       ["sharepoint_kb", "confluence", "web_read"],
    "design":      ["confluence", "onedrive"],
    "content":     ["web_read", "confluence", "sharepoint_kb"],
}

DEFAULT_ROLE = "it_ops"


def _meta(key: str, by_key: dict) -> dict | None:
    if key == "ai_assistant":
        return dict(AI_ASSISTANT)
    c = by_key.get(key)
    if not c:
        return None
    return {"key": key, "name": c.get("name", key), "category": c.get("category", ""),
            "needs_auth": bool(c.get("needs_auth")), "provider": c.get("provider", ""),
            "builtin": False, "blurb": c.get("description", "")}


def onboarding_suite(role: str, catalog: list[dict]) -> dict:
    """Return the {basic, specialized} tool tiles for the light onboarding.

    `catalog` is the governed connector catalog (ConnectorService.catalog()).
    Unknown role → no specialized set (the basics still apply).
    """
    by_key = {c["key"]: c for c in (catalog or [])}
    basic = [AI_ASSISTANT] + [m for k in BASIC_TOOLS if (m := _meta(k, by_key))]
    role = (role or "").strip().lower()
    seen = set(BASIC_TOOLS) | {"ai_assistant"}
    specialized = [m for k in ROLE_TOOLS.get(role, [])
                   if k not in seen and (m := _meta(k, by_key))]
    return {"role": role, "basic": basic, "specialized": specialized,
            "roles": sorted(ROLE_TOOLS.keys())}


def ensure_personal_desk(contributor_id: str, role: str = DEFAULT_ROLE, repo=voundry_repo) -> str:
    """Idempotently provision the seat's personal 'My Workspace' desk and return
    its work-unit id. Light-edition seats aren't assigned venture work, so this
    gives them a durable desk to connect tools to and do their day-to-day work."""
    role = (role or DEFAULT_ROLE).strip().lower() or DEFAULT_ROLE
    wu_id = f"wace-desk-{contributor_id}"
    existing = repo.get_work_unit(wu_id)
    if existing:
        if existing.get("role_type") != role:
            existing["role_type"] = role
            repo.save_work_unit(WorkUnit(**existing))
        return wu_id
    v_id = f"wace-venture-{contributor_id}"
    if not repo.get_venture(v_id):
        repo.save_venture(VentureUnit(id=v_id, candidate_id="wace", name="My Workspace", vertical="generic"))
    ms_id = f"wace-ms-{contributor_id}"
    repo.save_milestone(Milestone(id=ms_id, venture_unit_id=v_id, name="Operations"))
    repo.save_work_unit(WorkUnit(
        id=wu_id, venture_unit_id=v_id, milestone_id=ms_id, title="My Workspace",
        role_type=role, status=WorkUnitStatus.ASSIGNED, assigned_to=contributor_id))
    return wu_id
