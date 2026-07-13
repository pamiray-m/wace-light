"""
Voundry governed connector layer — how a contributor connects EXTERNAL tools
to their workspace (WACE) and lets agents use them, safely.

This is the "governed MCP" idea: connectors expose a small set of typed ACTIONS
(exactly like MCP tools), and a real MCP client can be dropped in behind the
same `ToolConnector` interface later. What makes it Voundry's, not a me-too, is
that EVERY invocation is wrapped in AOS governance:

- READ-ONLY by default — a connector declares each action's access; write
  actions are refused in this release (they will route through a GEL approval
  gate, never fire autonomously).
- SSRF-guarded — anything that reaches out validates the target against the
  public-internet policy first (reuses the smart-scraper guard).
- SAIb-guarded — external data is scrubbed for secrets/PII before it reaches
  the contributor or an agent.
- KILL-SWITCHED — a global autonomy halt blocks every invocation.
- RECEIPTED — connect / invoke / disconnect all write WORM audit events.

Two real read-only connectors ship today (a web-page reader and a read-only
HTTP-JSON fetcher); both take an injectable transport so they are fully
testable offline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.aos.voundry.contracts import (
    ConnectedTool, ConnectorWriteRequest, WorkUnit, WriteRequestStatus,
)
from src.aos.voundry.governance import voundry_audit
from src.aos.voundry.persistence.repository import voundry_repo

_MAX_RESULT = 8000

# url -> (final_url, text). Defaults to the SSRF-safe smart-scraper fetcher.
FetchFn = Callable[[str], tuple[str, str]]


class ConnectorError(Exception):
    pass


class ConnectorNotFound(ConnectorError):
    pass


def _default_fetch(url: str) -> tuple[str, str]:
    from src.aos.tools.smart_scraper.fetcher import fetch, validate_url
    validate_url(url)                       # SSRF policy — raises on internal/unsafe hosts
    return fetch(url)


@dataclass
class ConnectorAction:
    key:    str
    label:  str
    access: str = "read"          # "read" | "write"
    params: tuple[str, ...] = ()  # param names, for the connect/use form
    # `direct` writes execute immediately (still SSRF-guarded, kill-switched and
    # WORM-receipted) — for routine actions the USER performs on their own account
    # (send their email, update their ticket). Non-direct writes route through the
    # human-approval gate (agent-initiated / high-risk).
    direct: bool = False


@dataclass
class ToolConnector:
    key:         str
    name:        str
    description: str
    category:    str                      # web | data | email | calendar | files | ...
    actions:     tuple[ConnectorAction, ...]
    needs_auth:  bool = False             # OAuth connectors (Microsoft) need a signed-in account
    provider:    str = ""                 # "" | "microsoft"
    # Operator-configured connectors (Remedy, SQL, KB) gate on server-side env
    # rather than per-user OAuth. `enabled_check` returns False until configured.
    enabled_check: Optional[Callable[[], bool]] = field(default=None, repr=False)
    config_hint:   str = ""
    _run:        Callable[..., dict] = field(repr=False, default=lambda a, p, ctx=None: {})

    def is_enabled(self) -> bool:
        return self.enabled_check() if self.enabled_check else True

    def action(self, key: str) -> Optional[ConnectorAction]:
        return next((a for a in self.actions if a.key == key), None)

    def invoke(self, action_key: str, params: dict, ctx: Optional[dict] = None) -> dict:
        return self._run(action_key, params, ctx)

    def describe(self) -> dict:
        return {
            "key": self.key, "name": self.name, "description": self.description,
            "category": self.category, "needs_auth": self.needs_auth, "provider": self.provider,
            "enabled": self.is_enabled(),
            "actions": [{"key": a.key, "label": a.label, "access": a.access, "params": list(a.params), "direct": a.direct}
                        for a in self.actions],
        }


# ---------------------------------------------------------------------------
# Built-in read-only connectors
# ---------------------------------------------------------------------------

def _web_read_connector(fetch: FetchFn) -> ToolConnector:
    def run(action_key: str, params: dict, ctx: Optional[dict] = None) -> dict:
        if action_key != "fetch":
            raise ConnectorError(f"Unknown action {action_key!r}.")
        url = (params.get("url") or "").strip()
        if not url:
            raise ConnectorError("Provide a URL to read.")
        final_url, text = fetch(url)
        return {"final_url": final_url, "text": text}
    return ToolConnector(
        key="web_read", name="Web Page Reader", category="web",
        description="Read a public web page and return its text — governed and SSRF-safe.",
        actions=(ConnectorAction(key="fetch", label="Read a page", access="read", params=("url",)),),
        _run=run,
    )


def _http_json_connector(fetch: FetchFn) -> ToolConnector:
    def run(action_key: str, params: dict, ctx: Optional[dict] = None) -> dict:
        if action_key != "get":
            raise ConnectorError(f"Unknown action {action_key!r}.")
        url = (params.get("url") or "").strip()
        if not url:
            raise ConnectorError("Provide a JSON API URL.")
        final_url, body = fetch(url)
        try:
            parsed = json.loads(body)
            pretty = json.dumps(parsed, indent=2)[:_MAX_RESULT]
        except (ValueError, TypeError):
            pretty = body
        return {"final_url": final_url, "text": pretty}
    return ToolConnector(
        key="http_json", name="HTTP JSON (read-only)", category="data",
        description="GET a read-only JSON endpoint and return the response — governed and SSRF-safe.",
        actions=(ConnectorAction(key="get", label="GET JSON", access="read", params=("url",)),),
        _run=run,
    )


# ---------------------------------------------------------------------------
# Microsoft 365 / Outlook — governed connectors via Microsoft Graph (OAuth)
# ---------------------------------------------------------------------------
# The contributor connects their own Microsoft account (OAuth 2.0 auth-code
# flow); read-only scopes only. Every Graph call still flows through the SAME
# governance wrapper (read-only, SAIb scrub, kill-switch, WORM). Going LIVE
# needs an Azure AD app registration in the operator's tenant — set
# MS_GRAPH_CLIENT_ID / MS_GRAPH_CLIENT_SECRET / MS_GRAPH_REDIRECT_URI (and
# optionally MS_GRAPH_TENANT). Until then the connectors appear in the catalog
# but "dock" returns a clear "ask your operator to enable Microsoft" message.

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MS_SCOPES = "offline_access User.Read Mail.Read Mail.Send Calendars.Read Files.Read.All"

GraphGet = Callable[[str, str], dict]        # (graph_path, access_token) -> json
ExchangeFn = Callable[[str], dict]           # (auth_code) -> token dict


def _ms_env() -> dict:
    import os
    return {
        "client_id": os.getenv("MS_GRAPH_CLIENT_ID", "").strip(),
        "client_secret": os.getenv("MS_GRAPH_CLIENT_SECRET", "").strip(),
        "redirect_uri": os.getenv("MS_GRAPH_REDIRECT_URI", "").strip(),
        "tenant": os.getenv("MS_GRAPH_TENANT", "common").strip() or "common",
    }


def microsoft_enabled() -> bool:
    e = _ms_env()
    return bool(e["client_id"] and e["client_secret"] and e["redirect_uri"])


def microsoft_authorize_url(state: str) -> str:
    from urllib.parse import urlencode
    e = _ms_env()
    q = urlencode({
        "client_id": e["client_id"], "response_type": "code",
        "redirect_uri": e["redirect_uri"], "response_mode": "query",
        "scope": MS_SCOPES, "state": state,
    })
    return f"https://login.microsoftonline.com/{e['tenant']}/oauth2/v2.0/authorize?{q}"


def _default_exchange_code(code: str) -> dict:  # pragma: no cover — needs live Azure app
    import httpx
    e = _ms_env()
    r = httpx.post(
        f"https://login.microsoftonline.com/{e['tenant']}/oauth2/v2.0/token",
        data={"client_id": e["client_id"], "client_secret": e["client_secret"],
              "redirect_uri": e["redirect_uri"], "grant_type": "authorization_code",
              "code": code, "scope": MS_SCOPES},
        timeout=20.0)
    r.raise_for_status()
    return r.json()


def _default_graph_get(path: str, token: str) -> dict:  # pragma: no cover — needs live token
    import httpx
    r = httpx.get(f"{GRAPH_BASE}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=20.0)
    r.raise_for_status()
    return r.json()


GraphPost = Callable[[str, dict, str], dict]     # (path, body, token) -> json


def _default_graph_post(path: str, body: dict, token: str) -> dict:  # pragma: no cover
    import httpx
    r = httpx.post(f"{GRAPH_BASE}{path}", json=body,
                   headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, timeout=20.0)
    r.raise_for_status()
    return {"ok": True}


def _path_keys(path: str) -> list[str]:
    import re as _re
    return _re.findall(r"\{(\w+)\}", path)


def _fmt_mail(d: dict) -> str:
    rows = [f"• [{(m.get('receivedDateTime','') or '')[:16].replace('T',' ')}] "
            f"{((m.get('from',{}) or {}).get('emailAddress',{}) or {}).get('address','?')} — "
            f"{m.get('subject','(no subject)')}" for m in (d.get("value") or [])[:15]]
    return "\n".join(rows) or "No recent messages."


def _fmt_events(d: dict) -> str:
    rows = [f"• [{((ev.get('start',{}) or {}).get('dateTime','') or '')[:16].replace('T',' ')}] "
            f"{ev.get('subject','(no title)')}" for ev in (d.get("value") or [])[:15]]
    return "\n".join(rows) or "No upcoming events."


def _fmt_files(d: dict) -> str:
    rows = [f"• {f.get('name','?')}  ({f.get('size') or 0} bytes)" for f in (d.get("value") or [])[:20]]
    return "\n".join(rows) or "No recent files."


def _fmt_range(d: dict) -> str:
    vals = d.get("values")
    if isinstance(vals, list):
        return "\n".join(", ".join(str(c) for c in row) for row in vals) or "Empty range."
    return str(d.get("text") or vals or "No data.")


def _strip_html(s: str) -> str:
    """Turn an HTML email body into readable plain text (no HTML rendered — safe)."""
    import html
    import re as _re
    s = _re.sub(r"(?is)<(script|style|head).*?</\1>", " ", s or "")
    s = _re.sub(r"(?is)<br\s*/?>", "\n", s)
    s = _re.sub(r"(?is)</(p|div|tr|li|h[1-6])>", "\n", s)
    s = _re.sub(r"(?s)<[^>]+>", " ", s)
    s = html.unescape(s)
    s = _re.sub(r"[ \t]+", " ", s)
    s = _re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", s)
    return s.strip()


def _mail_rows(d: dict) -> list:
    out = []
    for m in (d.get("value") or [])[:25]:
        ea = ((m.get("from", {}) or {}).get("emailAddress", {}) or {})
        out.append({
            "id": m.get("id", ""),
            "primary": ea.get("name") or ea.get("address") or "Unknown sender",
            "secondary": m.get("subject") or "(no subject)",
            "meta": (m.get("receivedDateTime", "") or "")[:16].replace("T", " "),
            "preview": (m.get("bodyPreview", "") or "").strip()[:180],
        })
    return out


def _events_rows(d: dict) -> list:
    out = []
    for ev in (d.get("value") or [])[:25]:
        out.append({
            "id": ev.get("id", ""),
            "primary": ev.get("subject") or "(no title)",
            "secondary": ((ev.get("location", {}) or {}).get("displayName") or ""),
            "meta": (((ev.get("start", {}) or {}).get("dateTime", "")) or "")[:16].replace("T", " "),
            "preview": "",
        })
    return out


def _files_rows(d: dict) -> list:
    out = []
    for f in (d.get("value") or [])[:30]:
        out.append({
            "id": f.get("id", ""),
            "primary": f.get("name") or "?",
            "secondary": ((f.get("parentReference", {}) or {}).get("name") or ""),
            "meta": f"{(f.get('size') or 0):,} bytes",
            "preview": "",
        })
    return out


def _graph_connector(key, name, description, category, action, label, path, fmt, graph_get: GraphGet,
                     rows_fn=None) -> ToolConnector:
    def run(action_key: str, params: dict, ctx: Optional[dict] = None) -> dict:
        if action_key != action:
            raise ConnectorError(f"Unknown action {action_key!r}.")
        token = (ctx or {}).get("token") or ""
        get = (ctx or {}).get("graph_get") or graph_get
        resolved = (path.format(**{k: (params.get(k) or "").strip() for k in _path_keys(path)})
                    if "{" in path else path)
        data = get(resolved, token)
        out = {"text": fmt(data)}
        if rows_fn is not None:
            out["rows"] = rows_fn(data)
        return out
    return ToolConnector(
        key=key, name=name, description=description, category=category,
        needs_auth=True, provider="microsoft",
        actions=(ConnectorAction(key=action, label=label, access="read",
                                 params=tuple(_path_keys(path))),),
        _run=run,
    )


def _outlook_mail_connector(graph_get: GraphGet, graph_post: GraphPost) -> ToolConnector:
    """Mail as a clickable inbox: `recent` lists, `open` reads, `send` (write) composes."""
    def run(action_key: str, params: dict, ctx: Optional[dict] = None) -> dict:
        token = (ctx or {}).get("token") or ""
        get = (ctx or {}).get("graph_get") or graph_get
        post = (ctx or {}).get("graph_post") or graph_post
        if action_key == "send":                          # WRITE — routes through the GEL gate
            to = (params.get("to") or "").strip()
            subject = (params.get("subject") or "").strip()
            body = (params.get("body") or "").strip()
            if not to or not subject:
                raise ConnectorError("Need a recipient and a subject.")
            recipients = [{"emailAddress": {"address": a.strip()}} for a in to.replace(";", ",").split(",") if a.strip()]
            post("/me/sendMail", {"message": {"subject": subject[:255],
                                              "body": {"contentType": "Text", "content": body[:100000]},
                                              "toRecipients": recipients}, "saveToSentItems": True}, token)
            return {"text": f"Email sent to {to}: {subject}"}
        if action_key == "recent":
            data = get("/me/messages?$top=25&$select=id,subject,from,receivedDateTime,bodyPreview"
                       "&$orderby=receivedDateTime%20desc", token)
            return {"text": _fmt_mail(data), "rows": _mail_rows(data)}
        if action_key == "open":
            mid = (params.get("message_id") or "").strip()
            if not mid:
                raise ConnectorError("Which message? (missing id)")
            d = get(f"/me/messages/{mid}?$select=subject,from,toRecipients,receivedDateTime,body", token)
            ea = ((d.get("from", {}) or {}).get("emailAddress", {}) or {})
            to = ", ".join((r.get("emailAddress", {}) or {}).get("address", "")
                           for r in (d.get("toRecipients") or []))
            body = _strip_html((d.get("body", {}) or {}).get("content", "") or "")[:20000]
            detail = {
                "subject": d.get("subject") or "(no subject)",
                "from": ea.get("address", ""), "from_name": ea.get("name", ""),
                "to": to, "received": (d.get("receivedDateTime", "") or "")[:16].replace("T", " "),
                "body": body or "(empty message)",
            }
            return {"text": f"{detail['subject']}\nFrom: {detail['from']}\n\n{detail['body']}", "detail": detail}
        raise ConnectorError(f"Unknown action {action_key!r}.")
    return ToolConnector(
        key="outlook_mail", name="Outlook Mail",
        description="Read your recent Outlook email and open any message. Governed, read-only.",
        category="email", needs_auth=True, provider="microsoft",
        actions=(ConnectorAction(key="recent", label="Recent messages", access="read", params=()),
                 ConnectorAction(key="open", label="Open message", access="read", params=("message_id",)),
                 ConnectorAction(key="send", label="Send email", access="write", params=("to", "subject", "body"), direct=True)),
        _run=run,
    )


def _microsoft_connectors(graph_get: GraphGet, graph_post: GraphPost) -> list[ToolConnector]:
    return [
        _outlook_mail_connector(graph_get, graph_post),
        _graph_connector("outlook_calendar", "Outlook Calendar", "Read your upcoming Outlook events — governed, read-only.",
                         "calendar", "upcoming", "Upcoming events",
                         "/me/events?$top=15&$select=subject,start,location&$orderby=start/dateTime",
                         _fmt_events, graph_get, rows_fn=_events_rows),
        _graph_connector("onedrive", "OneDrive / SharePoint", "List your recent OneDrive & SharePoint files — governed, read-only.",
                         "files", "recent", "Recent files", "/me/drive/recent", _fmt_files, graph_get, rows_fn=_files_rows),
        _graph_connector("excel", "Excel (OneDrive)", "Read a range from an Excel workbook — governed, read-only.",
                         "spreadsheet", "read", "Read range",
                         "/me/drive/items/{item_id}/workbook/worksheets/{sheet}/range(address='{range}')",
                         _fmt_range, graph_get),
    ]


# ---------------------------------------------------------------------------
# Enterprise connectors (operator-configured) — Remedy, read-only SQL, KB
# ---------------------------------------------------------------------------
# The WACE IT/BSS-Ops connectors. Configured by the OPERATOR via env (not
# per-user OAuth): until configured they show in the catalog but connect/invoke
# refuse with a clear "ask your operator" hint. Every call still flows through
# the governance wrapper. Transports are injectable → fully testable offline.

RemedyFetch = Callable[[str], dict]         # (path) -> json  (read)
RemedyWrite = Callable[[str, dict], dict]   # (path, body) -> json  (write, PUT)
SnFetch = Callable[[str], dict]             # ServiceNow read
SnWrite = Callable[[str, dict], dict]       # ServiceNow write (PATCH)
SqlQuery = Callable[[str], list]            # (sql) -> list[dict rows]

_SN_STATE = {"1": "New", "2": "In Progress", "3": "On Hold", "6": "Resolved", "7": "Closed", "8": "Canceled"}


def _remedy_env() -> dict:
    import os
    return {"base": os.getenv("REMEDY_BASE_URL", "").strip(), "user": os.getenv("REMEDY_USER", "").strip(),
            "password": os.getenv("REMEDY_PASSWORD", "").strip(), "token": os.getenv("REMEDY_TOKEN", "").strip()}


def remedy_enabled() -> bool:
    e = _remedy_env()
    return bool(e["base"] and (e["token"] or (e["user"] and e["password"])))


def _remedy_token() -> tuple[str, str]:  # pragma: no cover — needs a live Remedy
    import httpx
    e = _remedy_env()
    token = e["token"]
    if not token:
        r = httpx.post(f"{e['base']}/api/jwt/login", data={"username": e["user"], "password": e["password"]}, timeout=20.0)
        r.raise_for_status(); token = r.text.strip()
    return e["base"], token


def _default_remedy_fetch(path: str) -> dict:  # pragma: no cover
    import httpx
    base, token = _remedy_token()
    r = httpx.get(f"{base}{path}", headers={"Authorization": f"AR-JWT {token}"}, timeout=20.0)
    r.raise_for_status()
    return r.json()


def _default_remedy_write(path: str, body: dict) -> dict:  # pragma: no cover
    import httpx
    base, token = _remedy_token()
    r = httpx.put(f"{base}{path}", json=body,
                  headers={"Authorization": f"AR-JWT {token}", "Content-Type": "application/json"}, timeout=20.0)
    r.raise_for_status()
    return {"ok": True}


def _incident_rows(d: dict) -> list:
    out = []
    for e in (d.get("entries") or d.get("value") or [])[:30]:
        v = e.get("values", e) if isinstance(e, dict) else {}
        out.append({
            "id": str(v.get("Incident Number") or v.get("id") or ""),
            "primary": str(v.get("Incident Number") or "INC"),
            "secondary": str(v.get("Description") or v.get("summary") or "(no summary)"),
            "meta": str(v.get("Priority") or v.get("Status") or ""),
            "preview": str(v.get("Status") or ""),
        })
    return out


def _fmt_incidents(d: dict) -> str:
    return "\n".join(f"• {r['primary']} [{r['meta']}] — {r['secondary']}" for r in _incident_rows(d)) or "No open incidents."


def _remedy_connector(fetch: RemedyFetch, write: RemedyWrite) -> ToolConnector:
    def run(action_key: str, params: dict, ctx: Optional[dict] = None) -> dict:
        if action_key == "incidents":
            data = fetch("/api/arsys/v1/entry/HPD:IncidentInterface?$top=30"
                         "&fields=values(Incident Number,Description,Priority,Status)")
            return {"text": _fmt_incidents(data), "rows": _incident_rows(data)}
        if action_key == "open":
            iid = (params.get("incident_id") or "").strip()
            if not iid:
                raise ConnectorError("Which incident? (missing id)")
            data = fetch(f"/api/arsys/v1/entry/HPD:IncidentInterface/{iid}")
            v = data.get("values") or data
            detail = {"subject": str(v.get("Incident Number") or iid), "from": str(v.get("Assignee") or ""),
                      "from_name": str(v.get("Assigned Group") or ""), "to": "",
                      "received": str(v.get("Submit Date") or ""),
                      "body": f"{v.get('Description') or ''}\n\nStatus: {v.get('Status') or ''}\nPriority: {v.get('Priority') or ''}"}
            return {"text": detail["body"], "detail": detail}
        if action_key == "set_status":       # WRITE — only runs after human approval
            iid = (params.get("incident_id") or "").strip()
            status = (params.get("status") or "").strip()
            if not iid or not status:
                raise ConnectorError("Need both incident_id and status.")
            write(f"/api/arsys/v1/entry/HPD:IncidentInterface/{iid}", {"values": {"Status": status}})
            return {"text": f"Incident {iid} status set to '{status}'."}
        if action_key == "add_note":          # WRITE — human-approved work note
            iid = (params.get("incident_id") or "").strip()
            note = (params.get("note") or "").strip()
            if not iid or not note:
                raise ConnectorError("Need both incident_id and note.")
            write(f"/api/arsys/v1/entry/HPD:IncidentInterface/{iid}", {"values": {"Work Info Summary": note[:2000]}})
            return {"text": f"Work note added to {iid}."}
        raise ConnectorError(f"Unknown action {action_key!r}.")
    return ToolConnector(
        key="remedy", name="Remedy Incidents", category="ticketing",
        description="Read open incidents & changes from BMC Remedy, set status, and add work notes — you do it, receipted. Governed.",
        enabled_check=remedy_enabled,
        config_hint="Remedy isn't connected yet — ask your operator to set REMEDY_BASE_URL and credentials.",
        actions=(ConnectorAction(key="incidents", label="Open incidents", access="read", params=()),
                 ConnectorAction(key="open", label="Open incident", access="read", params=("incident_id",)),
                 ConnectorAction(key="set_status", label="Set incident status", access="write",
                                 params=("incident_id", "status"), direct=True),
                 ConnectorAction(key="add_note", label="Add work note", access="write",
                                 params=("incident_id", "note"), direct=True)),
        _run=run,
    )


def _sql_env() -> dict:
    import os
    try:
        max_rows = int(os.getenv("OPS_SQL_MAX_ROWS", "200") or "200")
    except ValueError:
        max_rows = 200
    return {"dsn": os.getenv("OPS_SQL_DSN", "").strip(), "max_rows": max_rows}


def sql_enabled() -> bool:
    return bool(_sql_env()["dsn"])


def _is_read_only_sql(sql: str) -> bool:
    """A single read-only SELECT/CTE only — writes, DDL, and multi-statements blocked."""
    import re as _re
    s = _re.sub(r"(?s)/\*.*?\*/", " ", sql or "")   # block comments
    s = _re.sub(r"--[^\n]*", " ", s)                 # line comments
    s = s.strip().rstrip(";").strip()
    if not s or ";" in s:                            # single statement only
        return False
    if not (s[:7].lower().startswith("select") or s[:5].lower().startswith("with")):
        return False
    words = set(_re.findall(r"[a-z_]+", s.lower()))
    banned = {"insert", "update", "delete", "drop", "alter", "create", "truncate",
              "grant", "revoke", "merge", "exec", "execute", "call", "attach", "pragma", "into"}
    return not (words & banned)


def _default_sql_query(sql: str) -> list:  # pragma: no cover — needs a live DB
    from sqlalchemy import create_engine, text
    e = _sql_env()
    eng = create_engine(e["dsn"])
    with eng.connect() as conn:
        rows = conn.execute(text(sql)).mappings().all()
    return [dict(r) for r in rows[: e["max_rows"]]]


def _sql_rows(rows: list) -> list:
    out = []
    for r in rows[:50]:
        items = list(r.items())
        out.append({"id": "", "primary": str(items[0][1]) if items else "",
                    "secondary": " · ".join(f"{k}={v}" for k, v in items[1:4]), "meta": "", "preview": ""})
    return out


def _sql_connector(query_fn: SqlQuery) -> ToolConnector:
    def run(action_key: str, params: dict, ctx: Optional[dict] = None) -> dict:
        if action_key != "query":
            raise ConnectorError(f"Unknown action {action_key!r}.")
        sql = (params.get("sql") or "").strip()
        if not sql:
            raise ConnectorError("Enter a SELECT query.")
        if not _is_read_only_sql(sql):
            raise ConnectorError("Only a single read-only SELECT is allowed — writes and multiple statements are blocked.")
        rows = query_fn(sql)
        text_out = "\n".join(" · ".join(f"{k}={v}" for k, v in r.items()) for r in rows[:50]) or "No rows."
        return {"text": text_out, "rows": _sql_rows(rows)}
    return ToolConnector(
        key="sql_read", name="Read-only SQL", category="data",
        description="Run a governed, read-only SELECT against an approved database.",
        enabled_check=sql_enabled,
        config_hint="No database connected — ask your operator to set OPS_SQL_DSN (read-only).",
        actions=(ConnectorAction(key="query", label="Run SELECT", access="read", params=("sql",)),),
        _run=run,
    )


def _kb_rows(d: dict) -> list:
    return [{"id": f.get("id", ""), "primary": f.get("name", "?"),
             "secondary": ((f.get("parentReference", {}) or {}).get("name") or ""),
             "meta": "", "preview": (f.get("webUrl") or "")} for f in (d.get("value") or [])[:20]]


def _sharepoint_kb_connector(graph_get: GraphGet) -> ToolConnector:
    def run(action_key: str, params: dict, ctx: Optional[dict] = None) -> dict:
        if action_key != "search":
            raise ConnectorError(f"Unknown action {action_key!r}.")
        q = (params.get("query") or "").strip()
        if not q:
            raise ConnectorError("Enter a search term.")
        from urllib.parse import quote
        token = (ctx or {}).get("token") or ""
        get = (ctx or {}).get("graph_get") or graph_get
        data = get(f"/me/drive/root/search(q='{quote(q)}')?$top=15", token)
        rows = _kb_rows(data)
        return {"text": "\n".join(f"• {r['primary']}" for r in rows) or "No matches.", "rows": rows}
    return ToolConnector(
        key="sharepoint_kb", name="Knowledge Base (SharePoint)", category="document",
        description="Search runbooks & documents in SharePoint / OneDrive. Governed, read-only.",
        needs_auth=True, provider="microsoft",
        actions=(ConnectorAction(key="search", label="Search KB", access="read", params=("query",)),),
        _run=run,
    )


def _sn_env() -> dict:
    import os
    return {"base": os.getenv("SERVICENOW_INSTANCE_URL", "").rstrip("/"), "user": os.getenv("SERVICENOW_USER", ""),
            "password": os.getenv("SERVICENOW_PASSWORD", ""), "token": os.getenv("SERVICENOW_TOKEN", "")}


def servicenow_enabled() -> bool:
    e = _sn_env()
    return bool(e["base"] and (e["token"] or (e["user"] and e["password"])))


def _sn_auth_headers(e: dict) -> dict:  # pragma: no cover — needs a live ServiceNow
    import base64
    h = {"Accept": "application/json"}
    if e["token"]:
        h["Authorization"] = f"Bearer {e['token']}"
    elif e["user"]:
        h["Authorization"] = "Basic " + base64.b64encode(f"{e['user']}:{e['password']}".encode()).decode()
    return h


def _default_sn_fetch(path: str) -> dict:  # pragma: no cover
    import httpx
    e = _sn_env()
    r = httpx.get(f"{e['base']}{path}", headers=_sn_auth_headers(e), timeout=20.0)
    r.raise_for_status()
    return r.json()


def _default_sn_write(path: str, body: dict) -> dict:  # pragma: no cover
    import httpx
    e = _sn_env()
    headers = {**_sn_auth_headers(e), "Content-Type": "application/json"}
    r = httpx.patch(f"{e['base']}{path}", json=body, headers=headers, timeout=20.0)
    r.raise_for_status()
    return {"ok": True}


def _sn_rows(d: dict) -> list:
    out = []
    for r in (d.get("result") or [])[:30]:
        out.append({"id": str(r.get("sys_id") or r.get("number") or ""),
                    "primary": str(r.get("number") or "INC"),
                    "secondary": str(r.get("short_description") or "(no summary)"),
                    "meta": str(r.get("priority") or ""),
                    "preview": _SN_STATE.get(str(r.get("state") or ""), str(r.get("state") or ""))})
    return out


def _servicenow_connector(fetch: SnFetch, write: SnWrite) -> ToolConnector:
    def run(action_key: str, params: dict, ctx: Optional[dict] = None) -> dict:
        if action_key == "incidents":
            d = fetch("/api/now/table/incident?sysparm_limit=30&sysparm_query=active=true"
                      "&sysparm_fields=sys_id,number,short_description,priority,state")
            rows = _sn_rows(d)
            return {"text": "\n".join(f"• {r['primary']} [{r['meta']}] — {r['secondary']}" for r in rows) or "No active incidents.",
                    "rows": rows}
        if action_key == "open":
            sid = (params.get("sys_id") or "").strip()
            if not sid:
                raise ConnectorError("Which incident? (missing sys_id)")
            r = (fetch(f"/api/now/table/incident/{sid}?sysparm_display_value=true").get("result") or {})
            detail = {"subject": str(r.get("number") or sid), "from": str(r.get("assigned_to") or ""),
                      "from_name": str(r.get("assignment_group") or ""), "to": "",
                      "received": str(r.get("opened_at") or ""),
                      "body": f"{r.get('short_description') or ''}\n\n{r.get('description') or ''}\n\n"
                              f"State: {_SN_STATE.get(str(r.get('state') or ''), r.get('state') or '')}\nPriority: {r.get('priority') or ''}"}
            return {"text": detail["body"], "detail": detail}
        if action_key == "set_state":
            sid = (params.get("sys_id") or "").strip()
            state = (params.get("state") or "").strip()
            if not sid or not state:
                raise ConnectorError("Need both sys_id and state (e.g. 6 = Resolved).")
            write(f"/api/now/table/incident/{sid}", {"state": state})
            return {"text": f"Incident {sid} state set to {_SN_STATE.get(state, state)}."}
        if action_key == "add_note":          # WRITE — human-approved work note
            sid = (params.get("sys_id") or "").strip()
            note = (params.get("note") or "").strip()
            if not sid or not note:
                raise ConnectorError("Need both sys_id and note.")
            write(f"/api/now/table/incident/{sid}", {"work_notes": note[:4000]})
            return {"text": f"Work note added to {sid}."}
        raise ConnectorError(f"Unknown action {action_key!r}.")
    return ToolConnector(
        key="servicenow", name="ServiceNow Incidents", category="ticketing",
        description="Read active incidents from ServiceNow, set state, and add work notes — you do it, receipted. Governed.",
        enabled_check=servicenow_enabled,
        config_hint="ServiceNow isn't connected — set SERVICENOW_INSTANCE_URL + credentials, or connect via a bridge.",
        actions=(ConnectorAction(key="incidents", label="Active incidents", access="read", params=()),
                 ConnectorAction(key="open", label="Open incident", access="read", params=("sys_id",)),
                 ConnectorAction(key="set_state", label="Set incident state", access="write", params=("sys_id", "state"), direct=True),
                 ConnectorAction(key="add_note", label="Add work note", access="write", params=("sys_id", "note"), direct=True)),
        _run=run,
    )


CustomFetch = Callable[[str, str], dict]   # (url, auth_header) -> json  (cloud-direct custom)


def _default_custom_fetch(url: str, auth_header: str) -> dict:  # pragma: no cover — live HTTP
    from src.aos.tools.smart_scraper.fetcher import safe_request
    headers = {"Accept": "application/json"}
    if auth_header and ":" in auth_header:
        k, v = auth_header.split(":", 1)
        headers[k.strip()] = v.strip()
    r = safe_request("GET", url, headers=headers, timeout=20.0)   # IP-pinned SSRF guard
    r.raise_for_status()
    return r.json()


WebhookPost = Callable[[str, dict], dict]   # (url, payload) -> result


def _default_webhook_post(url: str, payload: dict) -> dict:  # pragma: no cover — live HTTP
    from src.aos.tools.smart_scraper.fetcher import safe_request
    r = safe_request("POST", url, json=payload, timeout=15.0)   # IP-pinned SSRF guard
    r.raise_for_status()
    return {"ok": True}


CustomPost = Callable[[str, str, dict], dict]   # (url, auth_header, body) -> result


def _default_custom_post(url: str, auth_header: str, body: dict) -> dict:  # pragma: no cover — live HTTP
    from src.aos.tools.smart_scraper.fetcher import safe_request
    headers = {"Content-Type": "application/json"}
    if auth_header and ":" in auth_header:
        k, v = auth_header.split(":", 1)
        headers[k.strip()] = v.strip()
    r = safe_request("POST", url, json=body, headers=headers, timeout=20.0)   # IP-pinned SSRF guard
    r.raise_for_status()
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {"ok": True}


def _webhook_connector(post: WebhookPost) -> ToolConnector:
    def run(action_key: str, params: dict, ctx: Optional[dict] = None) -> dict:
        if action_key != "notify":
            raise ConnectorError(f"Unknown action {action_key!r}.")
        url = (params.get("webhook_url") or "").strip()
        message = (params.get("message") or "").strip()
        if not url or not message:
            raise ConnectorError("Need a webhook URL and a message.")
        post(url, {"text": message[:4000]})
        return {"text": "Alert sent."}
    return ToolConnector(
        key="webhook", name="On-call Notify", category="notify",
        description="Send a governed alert to a Slack / Teams / incoming webhook — you send it, receipted.",
        actions=(ConnectorAction(key="notify", label="Send alert", access="write", params=("webhook_url", "message"), direct=True),),
        _run=run,
    )


# First-class cloud SaaS apps — quick-connect with a base URL + token, then they
# run cloud-direct (read-only, SSRF-guarded, governed) via the custom executor.
CLOUD_APP_SPECS: dict = {
    "jira":      {"name": "Jira", "category": "ticketing", "spec": {"name": "Jira", "list_path": "/rest/api/2/search",
                  "list_result_path": "issues", "open_path": "/rest/api/2/issue/{id}", "map": {"id": "id", "primary": "key", "secondary": "fields.summary"}}},
    "github":    {"name": "GitHub", "category": "code", "spec": {"name": "GitHub", "list_path": "/issues",
                  "list_result_path": "", "map": {"id": "id", "primary": "number", "secondary": "title"}}},
    "gitlab":    {"name": "GitLab", "category": "code", "spec": {"name": "GitLab", "list_path": "/api/v4/issues",
                  "list_result_path": "", "map": {"id": "id", "primary": "iid", "secondary": "title"}}},
    "pagerduty": {"name": "PagerDuty", "category": "notify", "spec": {"name": "PagerDuty", "list_path": "/incidents",
                  "list_result_path": "incidents", "open_path": "/incidents/{id}", "map": {"id": "id", "primary": "title", "secondary": "status"}}},
    "datadog":   {"name": "Datadog", "category": "data", "spec": {"name": "Datadog", "list_path": "/api/v1/monitor",
                  "list_result_path": "", "map": {"id": "id", "primary": "name", "secondary": "overall_state"}}},
    "grafana":   {"name": "Grafana", "category": "data", "spec": {"name": "Grafana", "list_path": "/api/search",
                  "list_result_path": "", "map": {"id": "uid", "primary": "title", "secondary": "folderTitle"}}},
    "zoom":      {"name": "Zoom", "category": "meeting", "spec": {"name": "Zoom", "list_path": "/v2/users/me/meetings",
                  "list_result_path": "meetings", "open_path": "/v2/meetings/{id}", "map": {"id": "id", "primary": "topic", "secondary": "start_time"}},
                  "writes": {"create_meeting": {"label": "Schedule a meeting", "params": ("topic", "start_time"), "direct": True,
                             "path": "/v2/users/me/meetings", "body": {"topic": "{topic}", "type": 2, "start_time": "{start_time}"}}}},
    "teams":     {"name": "Microsoft Teams", "category": "comms", "spec": {"name": "Microsoft Teams", "list_path": "/v1.0/me/joinedTeams",
                  "list_result_path": "value", "open_path": "/v1.0/teams/{id}", "map": {"id": "id", "primary": "displayName", "secondary": "description"}},
                  "reads": {"messages": {"label": "Read channel messages", "params": ("team_id", "channel_id"),
                             "path": "/v1.0/teams/{team_id}/channels/{channel_id}/messages", "result_path": "value",
                             "map": {"id": "id", "primary": "from.user.displayName", "secondary": "body.content"}}},
                  "writes": {"post_message": {"label": "Reply", "params": ("team_id", "channel_id", "message"), "direct": True,
                             "path": "/v1.0/teams/{team_id}/channels/{channel_id}/messages", "body": {"body": {"content": "{message}"}}}}},

    # --- ITSM / service desks used across GCC · Europe · UK · Americas · Asia ---
    "bmc_helix": {"name": "BMC Helix ITSM", "category": "ticketing", "spec": {"name": "BMC Helix ITSM",
                  "list_path": "/api/arsys/v1/entry/HPD:Help Desk?$top=30", "list_result_path": "entries",
                  "open_path": "/api/arsys/v1/entry/HPD:Help Desk/{id}", "map": {"id": "values.Request ID", "primary": "values.Incident Number", "secondary": "values.Description"}}},
    "freshservice": {"name": "Freshservice", "category": "ticketing", "spec": {"name": "Freshservice",
                  "list_path": "/api/v2/tickets", "list_result_path": "tickets", "open_path": "/api/v2/tickets/{id}", "map": {"id": "id", "primary": "id", "secondary": "subject"}},
                  "writes": {"add_note": {"label": "Add a note", "params": ("ticket_id", "message"), "direct": True,
                             "path": "/api/v2/tickets/{ticket_id}/notes", "body": {"body": "{message}", "private": False}}}},
    "zendesk":   {"name": "Zendesk", "category": "ticketing", "spec": {"name": "Zendesk",
                  "list_path": "/api/v2/tickets.json", "list_result_path": "tickets", "open_path": "/api/v2/tickets/{id}.json", "map": {"id": "id", "primary": "id", "secondary": "subject"}}},
    "topdesk":   {"name": "TOPdesk", "category": "ticketing", "spec": {"name": "TOPdesk",
                  "list_path": "/tas/api/incidents", "list_result_path": "", "open_path": "/tas/api/incidents/id/{id}", "map": {"id": "id", "primary": "number", "secondary": "briefDescription"}}},
    "servicedesk": {"name": "ManageEngine ServiceDesk", "category": "ticketing", "spec": {"name": "ManageEngine ServiceDesk Plus",
                  "list_path": "/api/v3/requests", "list_result_path": "requests", "open_path": "/api/v3/requests/{id}", "map": {"id": "id", "primary": "id", "secondary": "subject"}}},
    "ivanti":    {"name": "Ivanti Neurons ITSM", "category": "ticketing", "spec": {"name": "Ivanti Neurons ITSM",
                  "list_path": "/api/odata/businessobject/incidents", "list_result_path": "value", "open_path": "/api/odata/businessobject/incidents('{id}')", "map": {"id": "RecId", "primary": "IncidentNumber", "secondary": "Subject"}}},
    "halo":      {"name": "HaloITSM", "category": "ticketing", "spec": {"name": "HaloITSM",
                  "list_path": "/api/Tickets", "list_result_path": "tickets", "open_path": "/api/Tickets/{id}", "map": {"id": "id", "primary": "id", "secondary": "summary"}}},
    "jira_sm":   {"name": "Jira Service Management", "category": "ticketing", "spec": {"name": "Jira Service Management",
                  "list_path": "/rest/servicedeskapi/request", "list_result_path": "values", "open_path": "/rest/servicedeskapi/request/{id}", "map": {"id": "issueId", "primary": "issueKey", "secondary": "currentStatus.status"}},
                  "writes": {"add_comment": {"label": "Add a comment", "params": ("issue_id", "message"), "direct": True,
                             "path": "/rest/servicedeskapi/request/{issue_id}/comment", "body": {"body": "{message}", "public": True}}}},
    "easyvista": {"name": "EasyVista", "category": "ticketing", "spec": {"name": "EasyVista",
                  "list_path": "/api/v1/incidents", "list_result_path": "records", "open_path": "/api/v1/incidents/{id}", "map": {"id": "RFC_NUMBER", "primary": "RFC_NUMBER", "secondary": "DESCRIPTION"}}},
    "solarwinds_sd": {"name": "SolarWinds Service Desk", "category": "ticketing", "spec": {"name": "SolarWinds Service Desk",
                  "list_path": "/api/incidents.json", "list_result_path": "", "open_path": "/api/incidents/{id}.json", "map": {"id": "id", "primary": "number", "secondary": "name"}}},
    "zoho_desk": {"name": "Zoho Desk", "category": "ticketing", "spec": {"name": "Zoho Desk",
                  "list_path": "/api/v1/tickets", "list_result_path": "data", "open_path": "/api/v1/tickets/{id}", "map": {"id": "id", "primary": "ticketNumber", "secondary": "subject"}}},

    # --- other commonly-used tools ---
    "slack":      {"name": "Slack", "category": "comms", "spec": {"name": "Slack",
                  "list_path": "/api/conversations.list", "list_result_path": "channels", "map": {"id": "id", "primary": "name", "secondary": "purpose.value"}},
                  "reads": {"messages": {"label": "Read channel messages", "params": ("channel",),
                             "path": "/api/conversations.history?channel={channel}", "result_path": "messages",
                             "map": {"id": "ts", "primary": "user", "secondary": "text"}}},
                  "writes": {"post_message": {"label": "Reply", "params": ("channel", "message"), "direct": True,
                             "path": "/api/chat.postMessage", "body": {"channel": "{channel}", "text": "{message}"}}}},
    "confluence": {"name": "Confluence", "category": "document", "spec": {"name": "Confluence",
                  "list_path": "/wiki/rest/api/content", "list_result_path": "results", "open_path": "/wiki/rest/api/content/{id}", "map": {"id": "id", "primary": "title", "secondary": "type"}}},
    "salesforce": {"name": "Salesforce", "category": "data", "spec": {"name": "Salesforce",
                  "list_path": "/services/data/v59.0/query?q=SELECT+Id,CaseNumber,Subject+FROM+Case+LIMIT+30", "list_result_path": "records", "map": {"id": "Id", "primary": "CaseNumber", "secondary": "Subject"}}},
    "asana":      {"name": "Asana", "category": "code", "spec": {"name": "Asana",
                  "list_path": "/api/1.0/tasks?limit=30", "list_result_path": "data", "map": {"id": "gid", "primary": "name", "secondary": "resource_type"}}},
}


def _cloud_app_connector(key: str, name: str, category: str) -> ToolConnector:
    def run(action_key: str, params: dict, ctx: Optional[dict] = None) -> dict:
        raise ConnectorError(f"Connect {name} first — enter its base URL and an auth token.")
    reads = (CLOUD_APP_SPECS.get(key) or {}).get("reads") or {}
    read_actions = tuple(
        ConnectorAction(key=rk, label=r.get("label", rk), access="read", params=tuple(r.get("params", ())))
        for rk, r in reads.items()
    )
    writes = (CLOUD_APP_SPECS.get(key) or {}).get("writes") or {}
    write_actions = tuple(
        ConnectorAction(key=wk, label=w.get("label", wk), access="write", params=tuple(w.get("params", ())), direct=bool(w.get("direct")))
        for wk, w in writes.items()
    )
    return ToolConnector(
        key=key, name=name, category=category, needs_auth=False,
        description=f"Connect {name} with your base URL + token — cloud, governed + receipted.",
        config_hint=f"Quick-connect {name}: enter its base URL and an auth token.",
        actions=(ConnectorAction(key="list", label="List records", access="read", params=()),
                 ConnectorAction(key="open", label="Open record", access="read", params=("id",)),
                 *read_actions, *write_actions),
        _run=run,
    )


class ConnectorRegistry:
    """The catalog of connectors a contributor can add to a desk. New connectors
    (including a real MCP-client connector) register here behind ToolConnector."""

    def __init__(self, fetch: FetchFn = _default_fetch, *,
                 graph_get: GraphGet = _default_graph_get,
                 graph_post: GraphPost = _default_graph_post,
                 exchange_code: ExchangeFn = _default_exchange_code,
                 remedy_fetch: RemedyFetch = _default_remedy_fetch,
                 remedy_write: RemedyWrite = _default_remedy_write,
                 sn_fetch: SnFetch = _default_sn_fetch,
                 sn_write: SnWrite = _default_sn_write,
                 custom_fetch: CustomFetch = _default_custom_fetch,
                 custom_post: CustomPost = _default_custom_post,
                 webhook_post: WebhookPost = _default_webhook_post,
                 sql_query: SqlQuery = _default_sql_query) -> None:
        self.custom_fetch = custom_fetch
        self.custom_post = custom_post
        self._connectors: dict[str, ToolConnector] = {}
        for c in (_web_read_connector(fetch), _http_json_connector(fetch),
                  *_microsoft_connectors(graph_get, graph_post), _sharepoint_kb_connector(graph_get),
                  _remedy_connector(remedy_fetch, remedy_write),
                  _servicenow_connector(sn_fetch, sn_write), _sql_connector(sql_query),
                  _webhook_connector(webhook_post),
                  *(_cloud_app_connector(k, a["name"], a["category"]) for k, a in CLOUD_APP_SPECS.items())):
            self._connectors[c.key] = c
        self.exchange_code = exchange_code

    def get(self, key: str) -> Optional[ToolConnector]:
        return self._connectors.get(key)

    def get(self, key: str) -> Optional[ToolConnector]:
        return self._connectors.get(key)

    def catalog(self) -> list[dict]:
        return [c.describe() for c in self._connectors.values()]


# ---------------------------------------------------------------------------
# The governed service the portal calls
# ---------------------------------------------------------------------------

def _mask(text: str) -> tuple[str, int]:
    """Scrub secrets/PII out of external data before it reaches a human/agent."""
    if not text:
        return text, 0
    try:
        from src.saib.guard import saib_guard
        result = saib_guard.process(text, "")
        masked = getattr(result, "safe_prompt", None)
        entities = len(getattr(result, "entities", []) or [])
        if masked:
            return masked[:_MAX_RESULT], entities
    except Exception:  # noqa: BLE001 — guard must never break a read
        pass
    return text[:_MAX_RESULT], 0


def _dig(obj, path: str):
    cur = obj
    for part in (path or "").split("."):
        if not part:
            continue
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


def _custom_rows(arr: list, m: dict) -> list:
    out = []
    for it in (arr or [])[:30]:
        out.append({"id": str(_dig(it, m.get("id") or "id") or ""),
                    "primary": str(_dig(it, m.get("primary") or "id") or "?"),
                    "secondary": str(_dig(it, m.get("secondary") or "") or ""),
                    "meta": str(_dig(it, m.get("meta") or "") or ""),
                    "preview": str(_dig(it, m.get("preview") or "") or "")})
    return out


# Catastrophic-command backstop — blocked even in a bridge's "full" SSH mode.
# The primary policy (read-only allowlist) lives on the agent; this is a net.
_TERMINAL_BLOCK = [
    r"rm\s+-[a-z]*[rf][a-z]*\s+(-[a-z]+\s+)*(/|/\*|~|\$home)(\s|$)",
    r"\bmkfs", r"\bwipefs\b", r"\bdd\b[^|]*of=/dev/", r">\s*/dev/(sd|nvme|hd)",
    r"\bshutdown\b", r"\breboot\b", r"\bpoweroff\b", r"\bhalt\b", r"\binit\s+0\b",
    r":\s*\(\s*\)\s*\{", r"\bchmod\s+-r\s+[0-7]*777\s+/(\s|$)",
]


def terminal_precheck(command: str) -> bool:
    import re
    low = (command or "").lower()
    return not any(re.search(p, low) for p in _TERMINAL_BLOCK)


def _clean_custom_spec(s: dict) -> dict:
    """Validate + normalise a no-code custom-connector definition."""
    base = (s.get("base_url") or "").strip()
    list_path = (s.get("list_path") or "").strip()
    if not base or not list_path:
        raise ConnectorError("A custom connector needs a base URL and a list path.")
    m = s.get("map") or {}
    return {
        "name": (s.get("name") or "Custom API").strip()[:80],
        "base_url": base[:300], "list_path": list_path[:300],
        "list_result_path": (s.get("list_result_path") or "").strip()[:120],
        "open_path": (s.get("open_path") or "").strip()[:300],
        "map": {"id": (m.get("id") or "id").strip()[:80], "primary": (m.get("primary") or "id").strip()[:80],
                "secondary": (m.get("secondary") or "").strip()[:80], "meta": (m.get("meta") or "").strip()[:80],
                "preview": (m.get("preview") or "").strip()[:80]},
    }


# --- Org-wide governance policy (WACE admin) --------------------------------
# The org control plane: an admin can tighten the posture for the whole org —
# force every write through human approval, block connectors, disable the terminal.
_POLICY_DEFAULTS = {"require_approval_for_writes": False, "blocked_connectors": [], "block_terminal": False}


def get_org_policy(repo=voundry_repo) -> dict:
    saved = repo.get_org_policy() or {}
    return {**_POLICY_DEFAULTS, **saved}


def set_org_policy(patch: dict, repo=voundry_repo) -> dict:
    cur = get_org_policy(repo)
    if "require_approval_for_writes" in patch:
        cur["require_approval_for_writes"] = bool(patch["require_approval_for_writes"])
    if "block_terminal" in patch:
        cur["block_terminal"] = bool(patch["block_terminal"])
    if "blocked_connectors" in patch:
        cur["blocked_connectors"] = [str(x) for x in (patch.get("blocked_connectors") or [])][:60]
    repo.save_org_policy(cur)
    return cur


# --- Org-shared tools (an admin adds a connector once; the whole org gets it) --
_KV_ORG_TOOLS = "org_tools"


def get_org_tools(repo=voundry_repo) -> list:
    return (repo.get_kv(_KV_ORG_TOOLS) or {}).get("tools", [])


def add_org_tool(name: str, spec: dict, category: str = "data", repo=voundry_repo) -> dict:
    import uuid as _uuid
    clean = _clean_custom_spec({**spec, "name": name or spec.get("name") or "Org Tool"})
    entry = {"key": "org_" + _uuid.uuid4().hex[:8], "name": clean["name"], "category": (category or "data"),
             "spec": clean, "auth_header": (spec.get("auth_header") or "").strip()[:500]}
    tools = get_org_tools(repo)
    tools.append(entry)
    repo.save_kv(_KV_ORG_TOOLS, {"tools": tools[:100]})
    return {k: v for k, v in entry.items() if k != "auth_header"}   # never echo the shared token


def remove_org_tool(key: str, repo=voundry_repo) -> None:
    repo.save_kv(_KV_ORG_TOOLS, {"tools": [t for t in get_org_tools(repo) if t.get("key") != key]})


class ConnectorService:
    def __init__(self, repo=voundry_repo, audit=voundry_audit,
                 registry: Optional[ConnectorRegistry] = None) -> None:
        self._repo = repo
        self._audit = audit
        self._registry = registry or ConnectorRegistry()

    def catalog(self) -> list[dict]:
        base = self._registry.catalog()
        for t in get_org_tools(self._repo):
            base.append({
                "key": t["key"], "name": t["name"], "description": f"{t['name']} — added by your organization.",
                "category": t.get("category", "data"), "needs_auth": False, "provider": "", "enabled": True, "org_tool": True,
                "actions": [{"key": "list", "label": "List records", "access": "read", "params": [], "direct": False},
                            {"key": "open", "label": "Open record", "access": "read", "params": ["id"], "direct": False}],
            })
        return base

    def _owned_wu(self, contributor_id: str, work_unit_id: str) -> WorkUnit:
        w = self._repo.get_work_unit(work_unit_id)
        if w is None:
            raise ConnectorNotFound(work_unit_id)
        wu = WorkUnit(**w)
        if wu.assigned_to != contributor_id:
            raise ConnectorNotFound(f"{work_unit_id} (not your assignment)")
        return wu

    def connect(self, contributor_id: str, work_unit_id: str, *,
                connector_key: str, label: str = "", bridge_id: str = "",
                custom_spec: Optional[dict] = None, cloud_config: Optional[dict] = None) -> dict:
        self._owned_wu(contributor_id, work_unit_id)

        # Org policy — an admin may block specific connectors org-wide.
        if connector_key and connector_key in set(get_org_policy(self._repo).get("blocked_connectors") or []):
            raise ConnectorError(f"{connector_key} is blocked by your organization's WACE policy.")

        # Org-shared tool — the admin defined it once; connect with the stored spec.
        if connector_key.startswith("org_"):
            org = next((t for t in get_org_tools(self._repo) if t.get("key") == connector_key), None)
            if org is None:
                raise ConnectorNotFound(f"org tool {connector_key!r}")
            tool = ConnectedTool(
                work_unit_id=work_unit_id, contributor_id=contributor_id, connector_key=connector_key,
                label=(label.strip() or org["name"])[:120], scope="read", status="connected", auth_status="connected",
                config={"custom_spec": org["spec"], "custom_auth": org.get("auth_header", "")},
            )
            self._repo.save_connected_tool(tool)
            self._audit.append(
                actor_id=contributor_id, actor_type="human", action="connector.org_tool_connected",
                resource_type="work_unit", resource_id=work_unit_id, detail=f"connected org tool {org['name']}",
                metadata={"connector_key": connector_key})
            return tool.model_dump(mode="json")

        # First-class cloud SaaS app — quick-connect (base URL + token) → cloud-direct.
        if connector_key in CLOUD_APP_SPECS:
            cc = cloud_config or {}
            base = (cc.get("base_url") or "").strip()
            if not base:
                raise ConnectorError(f"Enter the base URL and a token to connect {CLOUD_APP_SPECS[connector_key]['name']}.")
            try:
                from src.aos.tools.smart_scraper.fetcher import validate_url
                validate_url(base)
            except ConnectorError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise ConnectorError(f"That base URL isn't allowed: {exc}")
            app = CLOUD_APP_SPECS[connector_key]
            spec = _clean_custom_spec({**app["spec"], "base_url": base})
            tool = ConnectedTool(
                work_unit_id=work_unit_id, contributor_id=contributor_id, connector_key=connector_key,
                label=(label.strip() or app["name"])[:120], scope="read", status="connected", auth_status="connected",
                config={"custom_spec": spec, "custom_auth": (cc.get("auth_header") or "").strip()[:500]},
            )
            self._repo.save_connected_tool(tool)
            self._audit.append(
                actor_id=contributor_id, actor_type="human", action="connector.cloud_app_connected",
                resource_type="work_unit", resource_id=work_unit_id, detail=f"connected {app['name']} (cloud)",
                metadata={"connector_key": connector_key, "base_url": base},
            )
            return tool.model_dump(mode="json")

        # No-code custom connector — the spec defines it; it runs read-only through
        # a bridge (the agent holds the base-URL auth). No registry entry needed.
        if custom_spec:
            spec = _clean_custom_spec(custom_spec)
            if bridge_id:                          # via on-prem bridge (internal systems)
                bdict = self._repo.get_bridge(bridge_id)
                if bdict is None or bdict.get("work_unit_id") != work_unit_id:
                    raise ConnectorError("That bridge isn't paired to this desk.")
                config = {"bridge_id": bridge_id, "custom_spec": spec}
                via = "bridge"
            else:                                  # cloud-direct (external SaaS) — SSRF-guard the host
                try:
                    from src.aos.tools.smart_scraper.fetcher import validate_url
                    validate_url(spec["base_url"])
                except ConnectorError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    raise ConnectorError(f"That base URL isn't allowed: {exc}")
                config = {"custom_spec": spec, "custom_auth": (custom_spec.get("auth_header") or "").strip()[:500]}
                via = "cloud"
            tool = ConnectedTool(
                work_unit_id=work_unit_id, contributor_id=contributor_id, connector_key="custom",
                label=(label.strip() or spec["name"])[:120], scope="read", status="connected",
                auth_status="connected", config=config,
            )
            self._repo.save_connected_tool(tool)
            self._audit.append(
                actor_id=contributor_id, actor_type="human", action="connector.custom_connected",
                resource_type="work_unit", resource_id=work_unit_id,
                detail=f"custom connector '{spec['name']}' via {via}",
                metadata={"connector_key": "custom", "via": via, "base_url": spec["base_url"]},
            )
            return tool.model_dump(mode="json")

        connector = self._registry.get(connector_key)
        if connector is None:
            raise ConnectorNotFound(f"connector {connector_key!r}")

        # Bridge-backed → the on-prem agent holds the credentials + reaches the
        # system locally. No WACE env, no OAuth. Verify the bridge serves it.
        if bridge_id:
            bdict = self._repo.get_bridge(bridge_id)
            if bdict is None or bdict.get("work_unit_id") != work_unit_id:
                raise ConnectorError("That bridge isn't paired to this desk.")
            from src.aos.voundry.contracts import ConnectorBridge as _CB
            bridge = _CB(**bdict)
            if bridge.capabilities and connector_key not in bridge.capabilities:
                raise ConnectorError(f"Your bridge doesn't serve {connector.name} yet.")
            tool = ConnectedTool(
                work_unit_id=work_unit_id, contributor_id=contributor_id,
                connector_key=connector_key, label=(label.strip() or f"{connector.name} (bridge)")[:120],
                scope="read", status="connected", auth_status="connected", config={"bridge_id": bridge_id},
            )
            self._repo.save_connected_tool(tool)
            self._audit.append(
                actor_id=contributor_id, actor_type="human", action="connector.connected_via_bridge",
                resource_type="work_unit", resource_id=work_unit_id,
                detail=f"connected {connector.name} via bridge (read-only)",
                metadata={"connector_key": connector_key, "bridge_id": bridge_id},
            )
            return tool.model_dump(mode="json")

        # OAuth connectors (Microsoft 365) → create a PENDING tool + hand back an
        # authorize URL for the contributor's browser to complete consent.
        if connector.needs_auth:
            if connector.provider == "microsoft" and not microsoft_enabled():
                raise ConnectorError(
                    "Microsoft 365 isn't enabled on this deployment yet — an operator must add the "
                    "Microsoft app credentials (MS_GRAPH_CLIENT_ID / MS_GRAPH_CLIENT_SECRET / MS_GRAPH_REDIRECT_URI)."
                )
            tool = ConnectedTool(
                work_unit_id=work_unit_id, contributor_id=contributor_id,
                connector_key=connector_key, label=(label.strip() or connector.name)[:120],
                scope="read", status="pending", provider=connector.provider, auth_status="pending",
            )
            self._repo.save_connected_tool(tool)
            self._audit.append(
                actor_id=contributor_id, actor_type="human", action="connector.oauth_started",
                resource_type="work_unit", resource_id=work_unit_id,
                detail=f"{connector.name} authorization started",
                metadata={"connector_key": connector_key, "provider": connector.provider},
            )
            out = tool.model_dump(mode="json")
            out["authorize_url"] = microsoft_authorize_url(tool.id)
            return out

        # Operator-configured connectors (Remedy / SQL / KB) refuse until wired.
        if not connector.is_enabled():
            raise ConnectorError(connector.config_hint or f"{connector.name} isn't configured on this deployment yet.")

        tool = ConnectedTool(
            work_unit_id=work_unit_id, contributor_id=contributor_id,
            connector_key=connector_key, label=(label.strip() or connector.name)[:120],
            scope="read", status="connected", auth_status="connected",
        )
        self._repo.save_connected_tool(tool)
        self._audit.append(
            actor_id=contributor_id, actor_type="human", action="connector.connected",
            resource_type="work_unit", resource_id=work_unit_id,
            detail=f"connected {connector.name} (read-only)",
            metadata={"connector_key": connector_key, "scope": "read"},
        )
        return tool.model_dump(mode="json")

    def authorize_url_for(self, contributor_id: str, work_unit_id: str, connected_id: str) -> str:
        """Re-issue the provider consent URL for a pending OAuth tool."""
        self._owned_wu(contributor_id, work_unit_id)
        d = self._repo.get_connected_tool(connected_id)
        if d is None or d.get("work_unit_id") != work_unit_id:
            raise ConnectorNotFound(f"connected tool {connected_id}")
        tool = ConnectedTool(**d)
        if tool.provider != "microsoft":
            raise ConnectorError("Not a Microsoft connector.")
        return microsoft_authorize_url(tool.id)

    def complete_oauth(self, *, state: str, code: str) -> dict:
        """Called by the provider redirect: exchange the code and store the token.
        `state` is the pending ConnectedTool id (capability); `code` is the auth
        code. No work-unit auth here — the browser hitting the redirect URI has
        no bearer token; the unguessable state id gates it."""
        d = self._repo.get_connected_tool(state)
        if d is None:
            raise ConnectorNotFound(f"connected tool {state}")
        tool = ConnectedTool(**d)
        if not tool.provider:
            raise ConnectorError("Not an OAuth connector.")
        token = self._registry.exchange_code(code)
        tool.config = {"token": token}
        tool.auth_status = "connected"
        tool.status = "connected"
        self._repo.save_connected_tool(tool)
        self._audit.append(
            actor_id=tool.contributor_id, actor_type="human", action="connector.oauth_completed",
            resource_type="work_unit", resource_id=tool.work_unit_id,
            detail=f"{tool.label} account connected",
            metadata={"connector_key": tool.connector_key, "provider": tool.provider},
        )
        return {"ok": True, "connected_id": tool.id, "connector_key": tool.connector_key,
                "work_unit_id": tool.work_unit_id}

    def list_connected(self, contributor_id: str, work_unit_id: str) -> list[dict]:
        self._owned_wu(contributor_id, work_unit_id)
        return self._repo.list_connected_tools_for_work_unit(work_unit_id)

    def disconnect(self, contributor_id: str, work_unit_id: str, connected_id: str) -> None:
        self._owned_wu(contributor_id, work_unit_id)
        existing = self._repo.get_connected_tool(connected_id)
        if existing is None or existing.get("work_unit_id") != work_unit_id:
            raise ConnectorNotFound(f"connected tool {connected_id}")
        self._repo.delete_connected_tool(connected_id)
        self._audit.append(
            actor_id=contributor_id, actor_type="human", action="connector.disconnected",
            resource_type="work_unit", resource_id=work_unit_id, detail=connected_id,
        )

    def invoke(self, contributor_id: str, work_unit_id: str, connected_id: str, *,
               action: str, params: dict) -> dict:
        self._owned_wu(contributor_id, work_unit_id)

        # 1) Global kill switch — a halt blocks every external call.
        from src.core.safety.autonomy_gate import is_autonomy_halted
        if is_autonomy_halted(None):
            raise ConnectorError("Autonomy is halted (kill switch active) — external tool calls are blocked.")

        d = self._repo.get_connected_tool(connected_id)
        if d is None or d.get("work_unit_id") != work_unit_id:
            raise ConnectorNotFound(f"connected tool {connected_id}")
        tool = ConnectedTool(**d)

        # Org policy — an admin can force EVERY write through the approval gate,
        # overriding the per-action `direct` flag (strict enterprise posture).
        force_approval = bool(get_org_policy(self._repo).get("require_approval_for_writes"))

        # No-code custom / cloud-app connector — spec on the tool. Reads run
        # cloud-direct; declared WRITE actions route through human approval.
        spec = (tool.config or {}).get("custom_spec")
        if spec:
            cloud_conn = self._registry.get(tool.connector_key)
            wact = cloud_conn.action(action) if cloud_conn else None
            if wact is not None and wact.access == "write":
                if not wact.direct or force_approval:
                    return self._request_write(contributor_id, work_unit_id, tool, cloud_conn, action, wact, params or {})
                # Direct user write → execute the cloud POST now + receipt.
                if is_autonomy_halted(None):
                    raise ConnectorError("Autonomy is halted (kill switch active).")
                raw = self._run_custom_write(spec, tool.connector_key, action, params or {}, (tool.config or {}).get("custom_auth", ""))
                self._audit.append(
                    actor_id=contributor_id, actor_type="human", action="connector.invoked",
                    resource_type="work_unit", resource_id=work_unit_id,
                    detail=f"{spec.get('name', tool.connector_key)}:{action} (direct write)",
                    metadata={"connector_key": tool.connector_key, "action": action, "direct": True},
                )
                return {"connected_id": tool.id, "connector_key": tool.connector_key, "action": action,
                        "result": {**raw, "text": str(raw.get("text", ""))[:_MAX_RESULT]}, "masked_entities": 0,
                        "governed": True, "executed": True}
            # Parameterized cloud read (e.g. read a Slack/Teams channel's messages).
            reads = (CLOUD_APP_SPECS.get(tool.connector_key) or {}).get("reads") or {}
            if action in reads:
                raw = self._run_custom_read(spec, tool.connector_key, action, params or {}, (tool.config or {}).get("custom_auth", ""))
                self._audit.append(
                    actor_id=contributor_id, actor_type="human", action="connector.invoked",
                    resource_type="work_unit", resource_id=work_unit_id,
                    detail=f"{spec.get('name', tool.connector_key)}:{action} (cloud read)",
                    metadata={"connector_key": tool.connector_key, "action": action},
                )
                return {"connected_id": tool.id, "connector_key": tool.connector_key, "action": action,
                        "result": {**raw, "text": str(raw.get("text", ""))[:_MAX_RESULT]}, "masked_entities": 0, "governed": True}
            return self._invoke_custom(contributor_id, work_unit_id, tool, action, params or {}, spec)

        connector = self._registry.get(tool.connector_key)
        if connector is None:
            raise ConnectorNotFound(f"connector {tool.connector_key!r}")

        # 2) Read-only enforcement — writes route through approval, not here.
        act = connector.action(action)
        if act is None:
            raise ConnectorError(f"Unknown action {action!r} for {connector.name}.")
        if act.access != "read" and (not act.direct or force_approval):
            # Agent-initiated / high-risk WRITE, or an org policy forcing approval →
            # never fires now. Create a GEL task; executes only once a governor approves.
            return self._request_write(contributor_id, work_unit_id, tool, connector, action, act, params or {})
        # A `direct` write (the user updating their own ticket / sending their own
        # mail) falls through to the run path below — executed now, still guarded +
        # receipted, no separate approval.

        # 2b) OAuth connectors need a signed-in account before they'll run.
        ctx: Optional[dict] = None
        if connector.needs_auth:
            token = (tool.config.get("token") or {}).get("access_token", "")
            if tool.auth_status != "connected" or not token:
                raise ConnectorError(
                    f"Connect your account first — the {connector.name} uplink is still pending authorization."
                )
            ctx = {"token": token}
        # 2c) Operator-configured connectors must still be configured at run time —
        #     UNLESS a bridge serves them (then the bridge holds the config, not WACE).
        elif not (tool.config or {}).get("bridge_id") and not connector.is_enabled():
            raise ConnectorError(connector.config_hint or f"{connector.name} isn't configured on this deployment yet.")

        # 3) Run the connector — locally, or through the on-prem bridge if paired.
        try:
            raw = self._run_tool(tool, connector, action, params or {}, ctx)
        except ConnectorError:
            raise
        except Exception:  # noqa: BLE001 — generic message; don't leak transport/internal detail
            raise ConnectorError(f"{connector.name} could not complete the request. Check the connection and try again.")

        # 4) SAIb scrub — ONLY for un-owned external data (web/http). A contributor
        #    reading their OWN authorized account (Outlook/OneDrive) sees it in the
        #    clear; masking is for when data leaves to an AGENT, not for the owner
        #    viewing their own inbox. Structured rows/detail pass through untouched.
        text = str(raw.get("text", ""))
        if connector.needs_auth or (tool.config or {}).get("bridge_id"):
            masked_text, masked_entities = text[:_MAX_RESULT], 0   # owner's own system
        else:
            masked_text, masked_entities = _mask(text)
        result = {**raw, "text": masked_text}

        # 5) Receipt.
        self._audit.append(
            actor_id=contributor_id, actor_type="human", action="connector.invoked",
            resource_type="work_unit", resource_id=work_unit_id,
            detail=f"{connector.name}:{action} ({masked_entities} masked)",
            metadata={"connector_key": tool.connector_key, "action": action,
                      "masked_entities": masked_entities},
        )
        return {
            "connected_id": connected_id, "connector_key": tool.connector_key,
            "action": action, "result": result, "masked_entities": masked_entities,
            "governed": True,
            **({"executed": True} if act.access != "read" else {}),
        }

    # -- Governed write-back (human-approved Execution layer) -----------------

    def _request_write(self, contributor_id: str, work_unit_id: str, tool, connector,
                       action: str, act, params: dict) -> dict:
        from src.aos.voundry.governance import request_connector_write_approval
        summary = f"{connector.name} · {act.label} — " + ", ".join(f"{k}={v}" for k, v in params.items())
        req = ConnectorWriteRequest(
            work_unit_id=work_unit_id, contributor_id=contributor_id, connected_id=tool.id,
            connector_key=tool.connector_key, action=action, params=params, summary=summary[:300],
        )
        req.gel_task_id = request_connector_write_approval(req.id, summary, lineage_id=work_unit_id)
        self._repo.save_write_request(req)
        self._audit.append(
            actor_id=contributor_id, actor_type="human", action="connector.write_requested",
            resource_type="work_unit", resource_id=work_unit_id, detail=summary[:120],
            metadata={"request_id": req.id, "connector_key": tool.connector_key, "action": action},
        )
        return {"governed": True, "pending_approval": True, "request_id": req.id,
                "gel_task_id": req.gel_task_id, "summary": summary,
                "connector_key": tool.connector_key, "action": action}

    def list_write_requests(self, contributor_id: str, work_unit_id: str) -> list[dict]:
        """Pending/settled write-backs on this desk — settling any that got approved."""
        self._owned_wu(contributor_id, work_unit_id)
        out = []
        for d in self._repo.list_write_requests_for_work_unit(work_unit_id):
            req = ConnectorWriteRequest(**d)
            if req.status is WriteRequestStatus.PENDING:
                req = self._settle_write_request(req)
            out.append(req.model_dump(mode="json"))
        return out

    def _invoke_custom(self, contributor_id: str, work_unit_id: str, tool, action: str,
                       params: dict, spec: dict) -> dict:
        """Run a no-code custom connector (list/open, read-only) through its bridge."""
        if action not in ("list", "open"):
            raise ConnectorError(f"Custom connectors support list/open, not {action!r}.")
        bridge_id = (tool.config or {}).get("bridge_id")
        if bridge_id:
            from src.aos.voundry.bridge import bridge_service
            raw = bridge_service.run_via_bridge(bridge_id, "custom", action, params, spec=spec)
            via = "bridge"
        else:                                     # cloud-direct — auth held in WACE, SSRF-guarded
            raw = self._run_custom_direct(spec, action, params, (tool.config or {}).get("custom_auth", ""))
            via = "cloud"
        result = {**raw, "text": str(raw.get("text", ""))[:_MAX_RESULT]}
        self._audit.append(
            actor_id=contributor_id, actor_type="human", action="connector.invoked",
            resource_type="work_unit", resource_id=work_unit_id,
            detail=f"{spec.get('name', 'custom')}:{action} (custom via {via})",
            metadata={"connector_key": "custom", "action": action, "via": via},
        )
        return {"connected_id": tool.id, "connector_key": "custom", "action": action,
                "result": result, "masked_entities": 0, "governed": True}

    def test_custom_spec(self, contributor_id: str, work_unit_id: str, *, custom_spec: dict,
                         bridge_id: str = "") -> dict:
        """Dry-run a custom spec's list call (no save) so the builder can preview + validate."""
        self._owned_wu(contributor_id, work_unit_id)
        try:
            spec = _clean_custom_spec(custom_spec)
        except ConnectorError as exc:
            return {"ok": False, "error": str(exc)}
        try:
            if bridge_id:
                from src.aos.voundry.bridge import bridge_service
                raw = bridge_service.run_via_bridge(bridge_id, "custom", "list", {}, spec=spec)
            else:
                from src.aos.tools.smart_scraper.fetcher import validate_url
                validate_url(spec["base_url"])
                raw = self._run_custom_direct(spec, "list", {}, (custom_spec.get("auth_header") or "").strip())
            rows = raw.get("rows") or []
            return {"ok": True, "count": len(rows), "rows": rows[:5]}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)[:300]}

    def save_query(self, contributor_id: str, work_unit_id: str, name: str, sql: str) -> dict:
        self._owned_wu(contributor_id, work_unit_id)
        from src.aos.voundry.contracts import SavedQuery
        sql = (sql or "").strip()
        if not (name or "").strip() or not sql:
            raise ConnectorError("A saved query needs a name and a SELECT.")
        if not _is_read_only_sql(sql):
            raise ConnectorError("Only a single read-only SELECT can be saved.")
        q = SavedQuery(work_unit_id=work_unit_id, contributor_id=contributor_id, name=name.strip()[:60], sql=sql[:4000])
        self._repo.save_query(q)
        return q.model_dump(mode="json")

    def list_queries(self, contributor_id: str, work_unit_id: str) -> list:
        self._owned_wu(contributor_id, work_unit_id)
        return self._repo.list_queries_for_work_unit(work_unit_id)

    def delete_query(self, contributor_id: str, work_unit_id: str, query_id: str) -> None:
        self._owned_wu(contributor_id, work_unit_id)
        d = self._repo.get_query(query_id)
        if d is None or d.get("work_unit_id") != work_unit_id:
            raise ConnectorNotFound(f"query {query_id}")
        self._repo.delete_query(query_id)

    def save_runbook(self, contributor_id: str, work_unit_id: str, name: str, commands: list) -> dict:
        self._owned_wu(contributor_id, work_unit_id)
        from src.aos.voundry.contracts import TerminalRunbook
        cmds = [str(c).strip() for c in (commands or []) if str(c).strip()][:20]
        if not (name or "").strip() or not cmds:
            raise ConnectorError("A runbook needs a name and at least one command.")
        rb = TerminalRunbook(work_unit_id=work_unit_id, contributor_id=contributor_id,
                             name=name.strip()[:60], commands=cmds)
        self._repo.save_runbook(rb)
        return rb.model_dump(mode="json")

    def list_runbooks(self, contributor_id: str, work_unit_id: str) -> list:
        self._owned_wu(contributor_id, work_unit_id)
        return self._repo.list_runbooks_for_work_unit(work_unit_id)

    def delete_runbook(self, contributor_id: str, work_unit_id: str, runbook_id: str) -> None:
        self._owned_wu(contributor_id, work_unit_id)
        d = self._repo.get_runbook(runbook_id)
        if d is None or d.get("work_unit_id") != work_unit_id:
            raise ConnectorNotFound(f"runbook {runbook_id}")
        self._repo.delete_runbook(runbook_id)

    def terminal_hosts(self, contributor_id: str, work_unit_id: str, bridge_id: str) -> list:
        """SSH hosts a bridge can reach (governor-gated at the route)."""
        self._owned_wu(contributor_id, work_unit_id)
        from src.aos.voundry.bridge import BridgeError, bridge_service
        try:
            raw = bridge_service.run_via_bridge(bridge_id, "ssh", "hosts", {})
        except BridgeError as exc:
            raise ConnectorError(str(exc))
        return raw.get("rows") or []

    def terminal_exec(self, contributor_id: str, work_unit_id: str, bridge_id: str,
                      host: str, command: str) -> dict:
        """Run one command on a UNIX/Linux host via the bridge's SSH — governed."""
        self._owned_wu(contributor_id, work_unit_id)
        if get_org_policy(self._repo).get("block_terminal"):
            raise ConnectorError("The server terminal is disabled by your organization's WACE policy.")
        command = (command or "").strip()
        if not command:
            raise ConnectorError("Empty command.")
        if not terminal_precheck(command):
            raise ConnectorError("That command is blocked by WACE's safety backstop (destructive/system-level).")
        from src.core.safety.autonomy_gate import is_autonomy_halted
        if is_autonomy_halted(None):
            raise ConnectorError("Autonomy is halted (kill switch) — the terminal is blocked.")
        from src.aos.voundry.bridge import BridgeError, bridge_service
        try:
            raw = bridge_service.run_via_bridge(bridge_id, "ssh", "exec", {"host": host, "command": command}, timeout=50.0)
        except BridgeError as exc:
            raise ConnectorError(str(exc))
        self._audit.append(
            actor_id=contributor_id, actor_type="human", action="terminal.ssh_exec",
            resource_type="work_unit", resource_id=work_unit_id, detail=f"{host}$ {command}"[:200],
            metadata={"bridge_id": bridge_id, "host": host, "exit_code": raw.get("exit_code")},
        )
        return {"output": raw.get("text", ""), "exit_code": raw.get("exit_code"), "host": host}

    def _run_custom_direct(self, spec: dict, action: str, params: dict, auth_header: str) -> dict:
        """Cloud-direct custom connector — SSRF-guarded GET + field mapping in WACE."""
        fetch = self._registry.custom_fetch
        base = (spec.get("base_url") or "").rstrip("/")
        rp = spec.get("list_result_path") or ""
        m = spec.get("map") or {}
        if action == "list":
            d = fetch(f"{base}{spec['list_path']}", auth_header)
            arr = _dig(d, rp) if rp else d
            rows = _custom_rows(arr if isinstance(arr, list) else [], m)
            return {"text": "\n".join(f"• {r['primary']} — {r['secondary']}" for r in rows) or "No records.", "rows": rows}
        op = spec.get("open_path") or ""
        if not op:
            raise ConnectorError("This custom connector has no open path.")
        from urllib.parse import quote
        rid = (params.get("id") or "").strip()
        d = fetch(f"{base}{op.replace('{id}', quote(rid, safe=''))}", auth_header)
        rec = _dig(d, rp) if rp else d
        body = "\n".join(f"{k}: {v}" for k, v in (rec.items() if isinstance(rec, dict) else []))[:_MAX_RESULT]
        return {"text": body, "detail": {"subject": rid, "from": "", "from_name": "", "to": "", "received": "", "body": body}}

    def _run_tool(self, tool, connector, action: str, params: dict, ctx) -> dict:
        """Execute an action locally, or route it to the desk's on-prem bridge."""
        bridge_id = (tool.config or {}).get("bridge_id")
        if bridge_id:
            from src.aos.voundry.bridge import bridge_service
            return bridge_service.run_via_bridge(bridge_id, tool.connector_key, action, params or {})
        # Cloud-app approved write → POST to the app's API (auth held in WACE).
        spec = (tool.config or {}).get("custom_spec")
        if spec and tool.connector_key in CLOUD_APP_SPECS:
            return self._run_custom_write(spec, tool.connector_key, action, params or {},
                                          (tool.config or {}).get("custom_auth", ""))
        return connector.invoke(action, params or {}, ctx)

    def _run_custom_write(self, spec: dict, connector_key: str, action: str, params: dict, auth_header: str) -> dict:
        """POST an approved write to a cloud app, substituting params into path + body."""
        w = ((CLOUD_APP_SPECS.get(connector_key) or {}).get("writes") or {}).get(action)
        if not w:
            raise ConnectorError(f"No write path for {action!r}.")
        from urllib.parse import quote

        def sub(v):
            if isinstance(v, str):
                for k, pv in params.items():
                    v = v.replace("{" + k + "}", str(pv))
                return v
            if isinstance(v, dict):
                return {k: sub(x) for k, x in v.items()}
            return v

        path = w["path"]
        for k, pv in params.items():
            path = path.replace("{" + k + "}", quote(str(pv), safe=""))
        base = (spec.get("base_url") or "").rstrip("/")
        resp = self._registry.custom_post(f"{base}{path}", auth_header, sub(w.get("body") or {}))
        name = (CLOUD_APP_SPECS.get(connector_key) or {}).get("name", connector_key)
        return {"text": f"{name}: {w.get('label', action)} done ✓", "detail": resp if isinstance(resp, dict) else {}}

    def _run_custom_read(self, spec: dict, connector_key: str, action: str, params: dict, auth_header: str) -> dict:
        """Parameterized cloud read (SSRF-guarded GET + field mapping) — e.g. a chat channel's messages."""
        r = ((CLOUD_APP_SPECS.get(connector_key) or {}).get("reads") or {}).get(action)
        if not r:
            raise ConnectorError(f"No read path for {action!r}.")
        from urllib.parse import quote
        path = r["path"]
        for k, pv in params.items():
            path = path.replace("{" + k + "}", quote(str(pv), safe=""))
        base = (spec.get("base_url") or "").rstrip("/")
        d = self._registry.custom_fetch(f"{base}{path}", auth_header)
        rp = r.get("result_path") or ""
        arr = _dig(d, rp) if rp else d
        rows = _custom_rows(arr if isinstance(arr, list) else [], r.get("map") or {})
        return {"text": "\n".join(f"• {x['primary']}: {x['secondary']}" for x in rows) or "No messages.", "rows": rows}

    def command_center(self, *, window: int = 800) -> dict:
        """Org-wide WACE telemetry for a governor — coverage, activity, value, receipts.
        The enterprise control plane: what's connected, what happened, what it's worth."""
        from collections import Counter
        events = self._audit.list_recent(limit=window)
        cats: Counter = Counter()
        desks: set = set()
        n_tools = 0
        for w in self._repo.list_work_units():
            wu_tools = self._repo.list_connected_tools_for_work_unit(w["id"])
            if wu_tools:
                desks.add(w["id"])
            for t in wu_tools:
                n_tools += 1
                conn = self._registry.get(t.get("connector_key") or "")
                cats[conn.category if conn else (t.get("connector_key") or "other")] += 1
        actions = writes = agent_runs = terminal = 0
        usage: Counter = Counter()
        for e in events:
            a = e.get("action") or ""
            meta = e.get("metadata") or {}
            if a == "connector.invoked":
                actions += 1
                usage[meta.get("connector_key") or "?"] += 1
                if meta.get("direct"):
                    writes += 1
            elif a == "connector.write_executed":
                writes += 1
            elif a.startswith("agent."):
                agent_runs += 1
            elif a == "terminal.ssh_exec":
                terminal += 1
        bridges = self._repo.list_all_bridges()
        automated = actions + agent_runs + terminal + writes
        return {
            "desks": len(desks), "connections": n_tools, "by_category": dict(cats.most_common()),
            "top_apps": [{"key": k, "count": n} for k, n in usage.most_common(8)],
            "bridges": {"total": len(bridges), "online": sum(1 for b in bridges if b.get("status") == "online")},
            "actions": actions, "writes": writes, "agent_runs": agent_runs, "terminal": terminal,
            "approvals_pending": len(self._repo.list_pending_write_requests()),
            "policy": get_org_policy(self._repo),
            "value": {"actions_automated": automated, "hours_saved": round(automated * 4 / 60.0, 1),
                      "note": "Estimate: ~4 min of manual work saved per governed action — every one receipted."},
            "recent": [{"action": e.get("action"), "actor_id": e.get("actor_id"), "actor_type": e.get("actor_type"),
                        "detail": e.get("detail"), "created_at": e.get("created_at"), "metadata": e.get("metadata")}
                       for e in events[:24]],
        }

    def list_pending_write_backs(self) -> list[dict]:
        """Every write-back awaiting a human governor (the approval queue)."""
        return [ConnectorWriteRequest(**d).model_dump(mode="json")
                for d in self._repo.list_pending_write_requests()]

    def decide_write_back(self, approver_id: str, request_id: str, *, approve: bool,
                          reason: str = "") -> dict:
        """A governor approves (→ executes now) or rejects a pending write-back.
        Authorization (can_govern) is enforced at the route."""
        from datetime import datetime, timezone
        from src.aos.voundry.governance import approve_gel_task, reject_gel_task
        d = self._repo.get_write_request(request_id)
        if d is None:
            raise ConnectorNotFound(f"write request {request_id}")
        req = ConnectorWriteRequest(**d)
        if req.status is not WriteRequestStatus.PENDING:
            raise ConnectorError(f"This write-back is already {req.status.value}.")
        if approve and approver_id == req.contributor_id:
            # Separation of duties: the maker cannot be the checker.
            raise ConnectorError("You cannot approve your own write-back — a different governor must approve it.")
        req.approver_id = approver_id
        if approve:
            approve_gel_task(req.gel_task_id, approver_id)      # record governor approval at the gate
            req = self._settle_write_request(req)               # gate now approved → executes once
        else:
            reject_gel_task(req.gel_task_id, approver_id, reason or "rejected by approver")
            req.status = WriteRequestStatus.REJECTED
            req.reject_reason = reason or "rejected by approver"
            req.decided_at = datetime.now(timezone.utc)
            self._repo.save_write_request(req)
            self._audit.append(
                actor_id=approver_id, actor_type="human", action="connector.write_rejected",
                resource_type="work_unit", resource_id=req.work_unit_id, detail=req.summary[:120],
                metadata={"request_id": req.id, "self_approved": approver_id == req.contributor_id},
            )
        return req.model_dump(mode="json")

    def _settle_write_request(self, req: ConnectorWriteRequest) -> ConnectorWriteRequest:
        """If the GEL gate approved it, execute the external write now; else leave pending."""
        from datetime import datetime, timezone
        from src.aos.voundry.governance import is_connector_write_approved
        from src.core.safety.autonomy_gate import is_autonomy_halted
        if not is_connector_write_approved(req.id):
            return req                                  # still awaiting a human governor
        d = self._repo.get_connected_tool(req.connected_id)
        connector = self._registry.get(req.connector_key)
        try:
            if is_autonomy_halted(None):
                raise ConnectorError("autonomy halted")
            if d is None or connector is None:
                raise ConnectorError("connector no longer available")
            tool = ConnectedTool(**d)
            ctx = None
            if connector.needs_auth:
                ctx = {"token": (tool.config.get("token") or {}).get("access_token", "")}
            req.result = self._run_tool(tool, connector, req.action, req.params, ctx)
            req.status = WriteRequestStatus.EXECUTED
        except Exception as exc:  # noqa: BLE001
            req.status = WriteRequestStatus.FAILED
            req.reject_reason = str(exc)
        req.decided_at = datetime.now(timezone.utc)
        self._repo.save_write_request(req)
        self._audit.append(
            actor_id="gel-gate", actor_type="system",
            action="connector.write_executed" if req.status is WriteRequestStatus.EXECUTED else "connector.write_failed",
            resource_type="work_unit", resource_id=req.work_unit_id, detail=req.summary[:120],
            metadata={"request_id": req.id, "status": req.status.value},
        )
        return req


# Module-level singleton
connector_service = ConnectorService()
