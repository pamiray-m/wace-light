import React from "react";
import { createPortal } from "react-dom";
import * as api from "../api";
import {
  BpButton, BpPlate, BpStamp,
  notify, accentFor, disciplineGlyph, toolStatusColor, resourceKindColor,
  GREEN, INK, INK_SOFT, LINE, MONO, PAPER, PAPER_2,
} from "../blueprint";
import {
  CK, CkButton, CkChip, CkInput, CkKeyframes, CkLed, CkPanel, CkStat, CkTelemetry, CkTextArea,
} from "../cockpit";

/* Role-scoped Workspace — designed to feel like a working desk, not a form.
 * Each discipline carries its own accent colour so a busy room is easy to
 * scan; tools, agents and resources each read as a distinct, colour-coded
 * item type. Hub: your role-assignments across ventures. Room: one
 * assignment's desk — task, colour-coded toolkit (with live status), the AI
 * agents allocated to you, resources, checklist, thread, approval missions. */

const statusLabel = (s: string) =>
  s === "connected" ? "ready" : s === "needs_setup" ? "needs setup" : "connect";

const poweredLabel: Record<string, string> = {
  "content-engine": "Content Studio", "smart-scraper": "Web Research",
  "llm-gateway": "AI", "assistant": "Assistant",
};

// Connector categories → cockpit hue + glyph for the Uplink Bay.
function connectorHue(category: string): string {
  return ({
    web: CK.cyan, data: CK.green, email: CK.amber, calendar: "#7db4ff",
    files: "#b28bff", spreadsheet: CK.green, document: "#7db4ff", chat: "#c78bff",
    ticketing: CK.amber, productivity: CK.cyan,
  } as Record<string, string>)[category] || CK.cyan;
}
function connectorGlyph(category: string): string {
  return ({
    web: "🌐", data: "▦", email: "✉", calendar: "🗓", files: "🗂",
    spreadsheet: "▦", document: "🗎", chat: "✦", ticketing: "🎫", productivity: "◆",
  } as Record<string, string>)[category] || "◆";
}

export function WorkspacePage(props: { onGoToJudgment?: () => void }): React.ReactElement {
  const [hub, setHub] = React.useState<api.RoleAssignment[]>([]);
  const [openId, setOpenId] = React.useState<string | null>(null);
  const [room, setRoom] = React.useState<api.RoleWorkspace | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [roomLoading, setRoomLoading] = React.useState(false);

  const loadHub = React.useCallback(async () => {
    setLoading(true);
    try { setHub((await api.myWorkspaces()) ?? []); }
    catch (e) { notify("sienna", (e as Error).message); }
    finally { setLoading(false); }
  }, []);
  React.useEffect(() => { void loadHub(); }, [loadHub]);

  // Returning from a Microsoft OAuth redirect (?ms=connected|error).
  React.useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("ms");
    if (p === "connected") notify("green", "Microsoft account connected ✓ — the uplink is live and governed.");
    else if (p === "error") notify("sienna", "Microsoft sign-in didn't complete. Try connecting again.");
    if (p) window.history.replaceState({}, "", window.location.pathname);
  }, []);

  const openRoom = async (id: string) => {
    setOpenId(id); setRoomLoading(true); setRoom(null);
    try { setRoom(await api.workspaceRoom(id)); }
    catch (e) { notify("sienna", (e as Error).message); setOpenId(null); }
    finally { setRoomLoading(false); }
  };

  if (openId) {
    return (
      <RoomView
        room={room}
        loading={roomLoading}
        onBack={() => { setOpenId(null); setRoom(null); void loadHub(); }}
        onRefresh={() => void openRoom(openId)}
        onGoToJudgment={props.onGoToJudgment}
      />
    );
  }

  return (
    <div data-testid="voundry-workspace">
      <BpPlate title="Your Workspaces" plate="ROLE DESKS"
        right={<BpButton style={{ padding: "2px 8px" }} onClick={() => void loadHub()}>⟳</BpButton>}>
        <div style={{ padding: "8px 12px", fontFamily: MONO, fontSize: 10.5, color: INK_SOFT, lineHeight: 1.6 }}>
          Each card is a role — a discipline in a venture's industry — with its own colour,
          tools, AI agents, and playbook. Open one to get to work.
        </div>
        {loading ? (
          <div style={{ padding: 12, fontFamily: MONO, fontSize: 11, color: INK_SOFT }}>— loading —</div>
        ) : hub.length === 0 ? (
          <div style={{ padding: 12, fontFamily: MONO, fontSize: 11, color: INK_SOFT, fontStyle: "italic" }}>
            No role assignments yet. Get Verified and apply to open work on the Find Work tab —
            once you're assigned, your role desk appears here.
          </div>
        ) : (
          <div style={{ padding: 12, display: "flex", flexWrap: "wrap", gap: 12 }}>
            {hub.map((a) => {
              const accent = accentFor(a.discipline);
              return (
                <button key={a.work_unit_id} type="button" data-testid={`ws-card-${a.work_unit_id}`}
                  onClick={() => void openRoom(a.work_unit_id)}
                  style={{
                    flex: "1 1 300px", textAlign: "left", cursor: "pointer", fontFamily: MONO,
                    border: `1px solid ${LINE}`, borderTop: `4px solid ${accent}`,
                    background: `linear-gradient(180deg, ${accent}0d, ${PAPER})`,
                    padding: "12px 14px", boxShadow: `2px 2px 0 ${INK}14`,
                  }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                    <span style={{
                      width: 34, height: 34, display: "flex", alignItems: "center", justifyContent: "center",
                      background: `${accent}1a`, border: `1px solid ${accent}`, color: accent, fontSize: 18,
                    }}>{disciplineGlyph(a.discipline)}</span>
                    <span>
                      <span style={{ display: "block", fontSize: 12.5, fontWeight: 800, color: accent, textTransform: "capitalize" }}>
                        {a.discipline} · {a.vertical}
                      </span>
                      <span style={{ fontSize: 9.5, color: INK_SOFT }}>{a.venture_name}</span>
                    </span>
                    <span style={{ marginLeft: "auto" }}><BpStamp value={a.status} /></span>
                  </div>
                  <div style={{ fontSize: 11, color: INK, marginBottom: 8 }}>{a.work_unit_title}</div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <MiniStat color={GREEN} label={`${a.connected_tools}/${a.tool_count} tools ready`} />
                    <MiniStat color={accent} label={`${a.agent_count} AI agents`} />
                    <span style={{ fontFamily: MONO, fontSize: 9, color: accent, marginLeft: "auto", alignSelf: "center" }}>open →</span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </BpPlate>
    </div>
  );
}

function MiniStat({ color, label }: { color: string; label: string }): React.ReactElement {
  return (
    <span style={{
      fontFamily: MONO, fontSize: 8.5, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase",
      color, background: `${color}14`, border: `1px solid ${color}`, padding: "2px 6px",
    }}>{label}</span>
  );
}

// ---------------------------------------------------------------------------
// Command palette (⌘K) + intent routing — everything on the desk from one
// keyboard-first surface, and "state the outcome → the right agent opens".
// ---------------------------------------------------------------------------

interface Cmd { id: string; label: string; hint?: string; group: string; run: () => void; }

function _tokens(s: string): string[] {
  return (s || "").toLowerCase().split(/[^a-z0-9]+/).filter((t) => t.length >= 2);
}

/** Pick the best-fitting agent for a natural-language intent (deterministic,
 *  offline). Scores token overlap against each agent's name/does/capability. */
function matchAgent(query: string, agents: api.WsAgent[]): api.WsAgent | null {
  if (!agents.length) return null;
  const q = _tokens(query);
  if (!q.length) return agents[0];
  let best = agents[0], bestScore = -1;
  for (const a of agents) {
    const hay = _tokens(`${a.name} ${a.does} ${a.powered_by}`);
    // Prefix/substring both ways so "draft"/"post" match "drafter"/"posts".
    const score = q.reduce((n, t) => n + (hay.some((h) => h.includes(t) || t.includes(h)) ? 1 : 0), 0);
    if (score > bestScore) { best = a; bestScore = score; }
  }
  return best;
}

function scrollToTestid(id: string): void {
  const el = document.querySelector(`[data-testid="${id}"]`) as HTMLElement | null;
  el?.scrollIntoView?.({ behavior: "smooth", block: "start" });
}

function CommandPalette({ open, onClose, commands, onIntent, accent }: {
  open: boolean; onClose: () => void; commands: Cmd[];
  onIntent: (q: string) => void; accent: string;
}): React.ReactElement | null {
  const [q, setQ] = React.useState("");
  const [active, setActive] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    if (open) { setQ(""); setActive(0); window.setTimeout(() => inputRef.current?.focus(), 30); }
  }, [open]);

  const filtered = React.useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter((c) => `${c.label} ${c.hint ?? ""} ${c.group}`.toLowerCase().includes(needle));
  }, [commands, q]);

  const hasIntent = q.trim().length >= 2;
  const rows = filtered.length + (hasIntent ? 1 : 0);

  const activate = (idx: number) => {
    if (hasIntent && idx === 0) { onIntent(q.trim()); onClose(); return; }
    const c = filtered[idx - (hasIntent ? 1 : 0)];
    if (c) { c.run(); onClose(); }
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { onClose(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, rows - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); activate(active); }
  };

  if (!open) return null;
  return (
    <div data-testid="ws-palette-overlay" onClick={onClose} style={{
      position: "fixed", inset: 0, background: "#16315b22", zIndex: 90,
      display: "flex", alignItems: "flex-start", justifyContent: "center", paddingTop: "10vh",
    }}>
      <div data-testid="ws-palette" onClick={(e) => e.stopPropagation()} onKeyDown={onKey} style={{
        width: "min(560px, 92vw)", background: PAPER, border: `1.5px solid ${INK}`,
        boxShadow: `5px 5px 0 ${INK}22`, maxHeight: "70vh", display: "flex", flexDirection: "column",
      }}>
        <input ref={inputRef} data-testid="ws-palette-input" value={q}
          onChange={(e) => { setQ(e.target.value); setActive(0); }}
          placeholder="Search agents, tools, files — or type what you want to get done…"
          style={{
            fontFamily: MONO, fontSize: 13, color: INK, background: PAPER_2, border: "none",
            borderBottom: `1px solid ${LINE}`, padding: "12px 14px", outline: "none", width: "100%", boxSizing: "border-box",
          }} />
        <div style={{ overflowY: "auto" }}>
          {hasIntent && (
            <button type="button" data-testid="ws-palette-intent"
              onClick={() => activate(0)} onMouseEnter={() => setActive(0)} style={rowStyle(active === 0, accent)}>
              <span style={{ color: accent, fontWeight: 800 }}>→ Send to the best agent:</span>
              <span style={{ color: INK }}> "{q.trim()}"</span>
            </button>
          )}
          {filtered.map((c, i) => {
            const idx = i + (hasIntent ? 1 : 0);
            return (
              <button key={c.id} type="button" data-testid={`ws-palette-cmd-${c.id}`}
                onClick={() => activate(idx)} onMouseEnter={() => setActive(idx)} style={rowStyle(active === idx, accent)}>
                <span style={{ color: INK_SOFT, fontSize: 8.5, letterSpacing: "0.1em", textTransform: "uppercase", minWidth: 66 }}>{c.group}</span>
                <span style={{ color: INK, flex: 1 }}>{c.label}</span>
                {c.hint && <span style={{ color: INK_SOFT, fontSize: 9 }}>{c.hint}</span>}
              </button>
            );
          })}
          {rows === 0 && (
            <div style={{ padding: "14px", fontFamily: MONO, fontSize: 11, color: INK_SOFT }}>No matches.</div>
          )}
        </div>
        <div style={{ borderTop: `1px solid ${LINE}`, padding: "5px 12px", fontFamily: MONO, fontSize: 8.5, color: INK_SOFT, letterSpacing: "0.08em" }}>
          ↑↓ move · ↵ select · esc close
        </div>
      </div>
    </div>
  );
}

function rowStyle(activeRow: boolean, accent: string): React.CSSProperties {
  return {
    display: "flex", gap: 10, alignItems: "center", width: "100%", textAlign: "left",
    padding: "8px 14px", fontFamily: MONO, fontSize: 11.5, cursor: "pointer",
    background: activeRow ? `${accent}18` : "transparent",
    border: "none", borderLeft: `3px solid ${activeRow ? accent : "transparent"}`,
  };
}

/* A docked uplink rendered as a LIVE dashboard card. No-param connectors
 * (Outlook Mail / Calendar, OneDrive) auto-load their content the moment the
 * desk opens, so the contributor SEES their data ready to work — not just a
 * connection. Param connectors (web page, Excel) show a quick run form.
 * Every read is governed (read-only, SAIb-scrubbed, receipted). */
// App-dock: per-connector icon + role-based ordering (most role-relevant first).
const CONNECTOR_ICON: Record<string, string> = {
  outlook_mail: "✉️", outlook_calendar: "📅", onedrive: "🗂️", excel: "📊", sharepoint_kb: "📚",
  remedy: "🎫", servicenow: "🧩", sql_read: "🗄️", web_read: "🌐", http_json: "🔌", webhook: "🔔",
  jira: "🟦", github: "🐙", gitlab: "🦊", pagerduty: "📟", datadog: "🐶", grafana: "📈",
  zoom: "🎥", teams: "👥",
  bmc_helix: "🛎️", freshservice: "🍃", zendesk: "🎧", topdesk: "📇", servicedesk: "🛠️", ivanti: "🧭",
  halo: "🌀", jira_sm: "🔷", easyvista: "📋", solarwinds_sd: "☀️", zoho_desk: "📨",
  slack: "💬", confluence: "📘", salesforce: "☁️", asana: "🔺",
};
const CLOUD_APP_KEYS = new Set([
  "jira", "github", "gitlab", "pagerduty", "datadog", "grafana", "zoom", "teams",
  "bmc_helix", "freshservice", "zendesk", "topdesk", "servicedesk", "ivanti", "halo", "jira_sm",
  "easyvista", "solarwinds_sd", "zoho_desk", "slack", "confluence", "salesforce", "asana",
]);
const ROLE_APP_PRIORITY: Record<string, string[]> = {
  it_ops: ["remedy", "bmc_helix", "servicenow", "pagerduty", "sql_read", "sharepoint_kb", "grafana", "datadog", "ivanti", "webhook", "outlook_mail", "teams", "slack", "http_json"],
  support: ["servicenow", "remedy", "freshservice", "zendesk", "jira_sm", "halo", "topdesk", "zoho_desk", "outlook_mail", "teams", "slack", "zoom", "sharepoint_kb", "webhook"],
  data: ["sql_read", "datadog", "grafana", "http_json", "excel", "sharepoint_kb"],
  engineering: ["github", "gitlab", "jira", "pagerduty", "datadog", "sql_read", "teams"],
  marketing: ["outlook_mail", "web_read", "sharepoint_kb"],
  sales: ["outlook_mail", "web_read"],
  finance: ["excel", "sql_read", "outlook_mail"],
};
const CATEGORY_LABEL: Record<string, string> = {
  ticketing: "Tickets", data: "Data", email: "Mail", code: "Code", notify: "Alerts",
  document: "Docs", web: "Web", calendar: "Calendar", files: "Files", spreadsheet: "Sheets",
  meeting: "Meetings", comms: "Chat",
};
// Group role-ordered apps by category, preserving order (role-relevance) of first appearance.
function groupByCategory(orderedApps: api.Connector[]): [string, api.Connector[]][] {
  const order: string[] = []; const map: Record<string, api.Connector[]> = {};
  for (const a of orderedApps) {
    const cat = a.category || "other";
    if (!map[cat]) { map[cat] = []; order.push(cat); }
    map[cat].push(a);
  }
  return order.map((c) => [c, map[c]]);
}
function orderApps(connectors: api.Connector[], connectedKeys: Set<string>, discipline: string): api.Connector[] {
  const prio = ROLE_APP_PRIORITY[discipline] || [];
  const rank = (k: string) => (prio.indexOf(k) < 0 ? 99 : prio.indexOf(k));
  return [...connectors].sort((a, b) => {
    const ca = connectedKeys.has(a.key) ? 0 : 1, cb = connectedKeys.has(b.key) ? 0 : 1;
    if (ca !== cb) return ca - cb;                    // connected first
    if (rank(a.key) !== rank(b.key)) return rank(a.key) - rank(b.key);   // role-priority
    return a.name.localeCompare(b.name);
  });
}

// Prebuilt starting points for the no-code connector — fill domain/creds and go.
const CUSTOM_TEMPLATES: { label: string; spec: Record<string, string> }[] = [
  { label: "Jira", spec: { name: "Jira", base_url: "https://your-domain.atlassian.net", list_path: "/rest/api/2/search",
    list_result_path: "issues", primary: "key", secondary: "fields.summary", open_path: "/rest/api/2/issue/{id}" } },
  { label: "ServiceNow", spec: { name: "ServiceNow", base_url: "https://your-instance.service-now.com",
    list_path: "/api/now/table/incident?sysparm_limit=30", list_result_path: "result", primary: "number",
    secondary: "short_description", open_path: "/api/now/table/incident/{id}" } },
  { label: "GitHub", spec: { name: "GitHub Issues", base_url: "https://api.github.com",
    list_path: "/repos/OWNER/REPO/issues", list_result_path: "", primary: "number", secondary: "title", open_path: "" } },
  { label: "GitLab", spec: { name: "GitLab Issues", base_url: "https://gitlab.com",
    list_path: "/api/v4/projects/PROJECT_ID/issues", list_result_path: "", primary: "iid", secondary: "title", open_path: "" } },
  { label: "Zendesk", spec: { name: "Zendesk", base_url: "https://your.zendesk.com", list_path: "/api/v2/tickets.json",
    list_result_path: "tickets", primary: "id", secondary: "subject", open_path: "/api/v2/tickets/{id}.json" } },
  { label: "Confluence", spec: { name: "Confluence", base_url: "https://your-domain.atlassian.net",
    list_path: "/wiki/rest/api/content?limit=30", list_result_path: "results", primary: "title", secondary: "type", open_path: "" } },
  { label: "PagerDuty", spec: { name: "PagerDuty", base_url: "https://api.pagerduty.com", list_path: "/incidents",
    list_result_path: "incidents", primary: "title", secondary: "status", open_path: "/incidents/{id}" } },
  { label: "Datadog", spec: { name: "Datadog Monitors", base_url: "https://api.datadoghq.com",
    list_path: "/api/v1/monitor", list_result_path: "", primary: "name", secondary: "overall_state", open_path: "" } },
  { label: "Grafana", spec: { name: "Grafana", base_url: "https://your-grafana", list_path: "/api/search?type=dash-db",
    list_result_path: "", primary: "title", secondary: "folderTitle", open_path: "" } },
  { label: "Salesforce", spec: { name: "Salesforce", base_url: "https://your-instance.my.salesforce.com",
    list_path: "/services/data/v59.0/query?q=SELECT+Id,Name+FROM+Case+LIMIT+30", list_result_path: "records", primary: "Name", secondary: "Id", open_path: "" } },
  { label: "Prometheus", spec: { name: "Prometheus Alerts", base_url: "https://your-prometheus",
    list_path: "/api/v1/alerts", list_result_path: "data.alerts", primary: "labels.alertname", secondary: "state", open_path: "" } },
  { label: "Kibana", spec: { name: "Kibana Saved", base_url: "https://your-kibana",
    list_path: "/api/saved_objects/_find?type=index-pattern", list_result_path: "saved_objects", primary: "id", secondary: "type", open_path: "" } },
];

// One-click diagnostic command sets for the terminal (pipe-free → work in read-only mode).
const RUNBOOKS: { label: string; cmds: string[] }[] = [
  { label: "Health", cmds: ["uptime", "df -h", "free -m", "w"] },
  { label: "Services", cmds: ["systemctl list-units --type=service --state=running"] },
  { label: "Disk & logs", cmds: ["df -h", "lsblk", "journalctl -n 50", "dmesg"] },
  { label: "Network", cmds: ["ss -tuln", "ip a"] },
  { label: "Containers", cmds: ["docker ps", "kubectl get pods"] },
];

// A no-code custom connector has no registry entry — synthesise its actions
// from the spec stored on the connected tool (list, and open if it has a path).
function customConnectorFor(t: api.ConnectedTool): api.Connector {
  const spec = ((t.config?.custom_spec as api.CustomSpec | undefined)) || ({} as Partial<api.CustomSpec>);
  const actions: api.ConnectorAction[] = [{ key: "list", label: "List records", access: "read", params: [] }];
  if (spec.open_path) actions.push({ key: "open", label: "Open", access: "read", params: ["id"] });
  return { key: "custom", name: spec.name || t.label, description: "Custom REST connector (via bridge)",
    category: "web", needs_auth: false, provider: "", actions };
}

function ToolWidget({ tool, connector, workUnitId, onDisconnect, onSaved, agents, onSuggestCommand, onData }: {
  tool: api.ConnectedTool; connector?: api.Connector; workUnitId: string;
  onDisconnect: (id: string) => void; onSaved: () => void; agents: api.WsAgent[];
  onSuggestCommand?: (cmd: string) => void; onData?: (summary: string) => void;
}): React.ReactElement {
  const action = connector?.actions.find((a) => a.access === "read");   // primary = first read
  const pending = tool.auth_status === "pending";
  const needsParams = !!action && action.params.length > 0;
  // Chat connectors (Slack / Teams) get a two-way channel panel instead of the generic form.
  const isChat = connector?.category === "comms"
    && !!connector.actions.find((a) => a.key === "messages")
    && !!connector.actions.find((a) => a.key === "post_message");
  const autoload = !!action && !needsParams && !pending && !isChat;
  const hue = connectorHue(connector?.category || "web");
  const [params, setParams] = React.useState<Record<string, string>>({});
  const [busy, setBusy] = React.useState(false);
  const [result, setResult] = React.useState<api.ConnectorInvokeResult | null>(null);
  const [detail, setDetail] = React.useState<api.ConnectorDetail | null>(null);
  const [opening, setOpening] = React.useState(false);
  const ranRef = React.useRef(false);
  const openAction = connector?.actions.find((a) => a.key === "open");   // e.g. open an email
  const writeActions = (connector?.actions || []).filter((a) => a.access === "write");
  const [writeParams, setWriteParams] = React.useState<Record<string, string>>({});
  const [writing, setWriting] = React.useState(false);

  const requestWrite = async (act: api.ConnectorAction) => {
    setWriting(true);
    try {
      const res = await api.invokeConnector(workUnitId, tool.id, act.key, writeParams);
      notify("green", res.pending_approval
        ? "Queued for approval — a governor must approve before it runs."
        : "Done ✓ — executed and receipted.");
      setWriteParams({});
      onSaved();
    } catch (e) { notify("sienna", (e as Error).message); } finally { setWriting(false); }
  };

  const run = React.useCallback(async () => {
    if (!action) return;
    setBusy(true); setDetail(null);
    try { setResult(await api.invokeConnector(workUnitId, tool.id, action.key, params)); }
    catch (e) { notify("sienna", (e as Error).message); } finally { setBusy(false); }
  }, [action, params, workUnitId, tool.id]);

  // Report the panel's latest data upward so a wired agent below it can read it.
  React.useEffect(() => {
    if (!onData || !result) return;
    const r = (result.result || {}) as { text?: string; rows?: api.ConnectorRow[] };
    const txt = r.text || (r.rows || []).map((x) => `${x.primary}${x.secondary ? ` — ${x.secondary}` : ""}`).join("\n");
    if (txt) onData(txt.slice(0, 4000));
  }, [result]);

  const openRow = async (id: string) => {
    if (!openAction) return;
    setOpening(true);
    try {
      const r = await api.invokeConnector(workUnitId, tool.id, openAction.key, { [openAction.params[0] || "id"]: id });
      setDetail(r.result?.detail || null);
    } catch (e) { notify("sienna", (e as Error).message); } finally { setOpening(false); }
  };

  // Auto-pull once on open for no-param uplinks (mail/calendar/files).
  React.useEffect(() => {
    if (autoload && !ranRef.current) { ranRef.current = true; void run(); }
  }, [autoload, run]);

  const authorize = async () => {
    try {
      const { authorize_url } = await api.connectorAuthorizeUrl(workUnitId, tool.id);
      window.location.href = authorize_url;
    } catch (e) { notify("sienna", (e as Error).message); }
  };

  const save = async () => {
    const content = detail ? `${detail.subject}\nFrom: ${detail.from_name || detail.from}\n${detail.received}\n\n${detail.body}` : result?.result?.text;
    if (!content) return;
    try {
      await api.saveWorkspaceFile(workUnitId, {
        name: detail ? detail.subject.slice(0, 80) : `${tool.label} result`, content, kind: "data", source_agent_name: tool.label,
      });
      notify("green", "Saved to your Flight Recorder ✓");
      onSaved();
    } catch (e) { notify("sienna", (e as Error).message); }
  };

  // A desk agent reads this connector's data (governed AI over governed data).
  const [analysis, setAnalysis] = React.useState("");
  const [analyzing, setAnalyzing] = React.useState(false);
  const [investigation, setInvestigation] = React.useState<{ hypothesis: string; commands: string[] } | null>(null);
  const [investigating, setInvestigating] = React.useState(false);
  const [drafting, setDrafting] = React.useState(false);
  const draftReply = async () => {
    if (!detail) return;
    const agent = agents.find((a) => a.live) || agents[0];
    if (!agent) return;
    setDrafting(true);
    try {
      const r = await api.runAgent(workUnitId, agent.key, `Draft a concise, professional reply to this email. Return only the reply body.\n\n${detail.body}`);
      setWriteParams({ to: detail.from, subject: /^re:/i.test(detail.subject) ? detail.subject : `Re: ${detail.subject}`, body: r.output });
      notify("green", "Reply drafted below — review, then Request Send.");
    } catch (e) { notify("sienna", (e as Error).message); } finally { setDrafting(false); }
  };

  // Saved SQL queries (only on the read-only SQL connector).
  const isSql = connector?.key === "sql_read";
  const [queries, setQueries] = React.useState<api.SavedQuery[]>([]);
  const [qName, setQName] = React.useState("");
  React.useEffect(() => {
    if (isSql) Promise.resolve(api.listQueries(workUnitId)).then((q) => setQueries(q || [])).catch(() => setQueries([]));
  }, [isSql, workUnitId]);
  const runSaved = async (sql: string) => {
    setParams({ sql }); setBusy(true);
    try { setResult(await api.invokeConnector(workUnitId, tool.id, "query", { sql })); }
    catch (e) { notify("sienna", (e as Error).message); } finally { setBusy(false); }
  };
  const saveQueryFn = async () => {
    if (!qName.trim() || !(params.sql || "").trim()) { notify("sienna", "Name it, and enter a SELECT above."); return; }
    try { await api.saveQuery(workUnitId, qName.trim(), params.sql); setQName(""); setQueries(await api.listQueries(workUnitId)); notify("green", "Query saved ✓"); }
    catch (e) { notify("sienna", (e as Error).message); }
  };
  const delQueryFn = async (id: string) => {
    try { await api.deleteQuery(workUnitId, id); setQueries((q) => q.filter((x) => x.id !== id)); }
    catch (e) { notify("sienna", (e as Error).message); }
  };
  React.useEffect(() => { setAnalysis(""); setInvestigation(null); }, [result, detail]);
  const isTicketing = connector?.category === "ticketing";
  const doInvestigate = async () => {
    const agent = agents.find((a) => a.live) || agents[0];
    const data = detail ? detail.body : (result?.result?.text || "");
    if (!agent || !data) return;
    setInvestigating(true);
    try {
      const r = await api.investigate(workUnitId, agent.key, data);
      setInvestigation({ hypothesis: `${r.agent_name}: ${r.hypothesis}`, commands: r.commands });
    } catch (e) { notify("sienna", (e as Error).message); } finally { setInvestigating(false); }
  };
  const analyze = async () => {
    const agent = agents.find((a) => a.live) || agents[0];
    const data = detail ? detail.body : (result?.result?.text || "");
    if (!agent || !data) return;
    setAnalyzing(true);
    try {
      const r = await api.analyzeData(workUnitId, agent.key, tool.label, data);
      setAnalysis(`${r.agent_name}: ${r.analysis}`);
    } catch (e) { notify("sienna", (e as Error).message); } finally { setAnalyzing(false); }
  };

  return (
    <CkPanel title={tool.label} plate={pending ? "PENDING" : "LIVE UPLINK"} accent={hue}
      glyph={connectorGlyph(connector?.category || "web")} testid={`ws-connected-${tool.id}`}
      right={<CkButton tone="red" data-testid={`ws-disconnect-${tool.id}`}
        onClick={() => onDisconnect(tool.id)}>UNDOCK</CkButton>}>
      <div style={{ padding: 11 }}>
        {pending && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <span style={{ fontFamily: MONO, fontSize: 10, color: CK.inkSoft, lineHeight: 1.5 }}>
              Finish signing in to {tool.provider} to bring this uplink online (read-only).
            </span>
            <CkButton tone="cyan" data-testid={`ws-authorize-${tool.id}`} onClick={() => void authorize()}>
              ▸ AUTHORIZE {tool.provider.toUpperCase()}
            </CkButton>
          </div>
        )}
        {!pending && isChat && connector && (
          <ChatPanel tool={tool} connector={connector} workUnitId={workUnitId} />
        )}
        {!pending && !isChat && needsParams && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
            {action!.params.map((p) => (
              <CkInput key={p} data-testid={`ws-connector-${tool.id}-${p}`} placeholder={p}
                value={params[p] ?? ""} onChange={(e) => setParams({ ...params, [p]: e.target.value })}
                style={{ flex: "1 1 150px" }} />
            ))}
            <CkButton tone="cyan" disabled={busy} data-testid={`ws-connector-use-${tool.id}`} onClick={() => void run()}>
              {busy ? "▸ …" : `▸ ${action!.label.toUpperCase()}`}
            </CkButton>
          </div>
        )}
        {!pending && isSql && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
            <span style={{ fontFamily: MONO, fontSize: 8.5, color: CK.inkDim }}>saved:</span>
            {queries.length === 0 && <span style={{ fontFamily: MONO, fontSize: 8.5, color: CK.inkDim }}>none yet</span>}
            {queries.map((q) => (
              <span key={q.id} style={{ display: "inline-flex", alignItems: "center", border: `1px solid ${CK.line}` }}>
                <button type="button" title={q.sql} data-testid={`ws-sql-run-${q.id}`} disabled={busy} onClick={() => void runSaved(q.sql)}
                  style={{ background: "none", border: "none", color: CK.cyan, cursor: "pointer", fontFamily: MONO, fontSize: 9, padding: "2px 7px" }}>▶ {q.name}</button>
                <button type="button" data-testid={`ws-sql-del-${q.id}`} onClick={() => void delQueryFn(q.id)}
                  style={{ background: "none", border: "none", borderLeft: `1px solid ${CK.line}`, color: CK.red, cursor: "pointer", fontFamily: MONO, fontSize: 9, padding: "2px 6px" }}>×</button>
              </span>
            ))}
            {(params.sql || "").trim() && (
              <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
                <CkInput data-testid={`ws-sql-name-${tool.id}`} placeholder="save as…" value={qName} onChange={(e) => setQName(e.target.value)} style={{ width: 120, fontSize: 9 }} />
                <button type="button" data-testid={`ws-sql-save-${tool.id}`} onClick={() => void saveQueryFn()}
                  style={{ background: "none", border: `1px solid ${CK.line}`, color: CK.green, cursor: "pointer", fontFamily: MONO, fontSize: 9, padding: "3px 8px" }}>save</button>
              </span>
            )}
          </div>
        )}
        {!pending && (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
              <CkLed color={busy || opening ? CK.amber : CK.green} size={6} />
              <span style={{ flex: 1, fontFamily: MONO, fontSize: 8.5, color: CK.inkDim, letterSpacing: "0.1em", textTransform: "uppercase" }}>
                {opening ? "opening…" : busy ? "reading…" : detail ? "message · read-only" : result ? "governed · read-only · receipted" : autoload ? "loading…" : "ready"}
              </span>
              {detail && (
                <button type="button" data-testid={`ws-connector-back-${tool.id}`} onClick={() => setDetail(null)}
                  style={{ background: "none", border: `1px solid ${CK.line}`, color: CK.cyan, cursor: "pointer",
                    fontFamily: MONO, fontSize: 9, padding: "1px 8px" }}>← inbox</button>
              )}
              {detail && agents.length > 0 && (connector?.actions || []).some((a) => a.key === "send") && (
                <button type="button" data-testid={`ws-connector-draft-${tool.id}`} disabled={drafting} onClick={() => void draftReply()}
                  style={{ background: "none", border: `1px solid ${CK.line}`, color: CK.cyan, cursor: "pointer",
                    fontFamily: MONO, fontSize: 9, padding: "1px 8px" }}>{drafting ? "…" : "✨ draft reply"}</button>
              )}
              {!detail && (autoload || result) && (
                <button type="button" title="refresh" data-testid={`ws-connector-refresh-${tool.id}`} onClick={() => void run()}
                  style={{ background: "none", border: `1px solid ${CK.line}`, color: CK.inkSoft, cursor: "pointer",
                    fontFamily: MONO, fontSize: 10, padding: "0 7px" }}>↻</button>
              )}
            </div>

            {/* Reading pane — a single opened message */}
            {detail && (
              <div data-testid={`ws-connector-detail-${tool.id}`} style={{ border: `1px solid ${CK.line}`, background: CK.space }}>
                <div style={{ padding: "9px 11px", borderBottom: `1px solid ${CK.line}` }}>
                  <div style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 800, color: CK.ink, lineHeight: 1.4 }}>{detail.subject}</div>
                  <div style={{ fontFamily: MONO, fontSize: 9.5, color: CK.cyan, marginTop: 4 }}>
                    {detail.from_name ? `${detail.from_name} · ` : ""}{detail.from}
                  </div>
                  <div style={{ fontFamily: MONO, fontSize: 9, color: CK.inkDim, marginTop: 2 }}>
                    {detail.received}{detail.to ? ` · to ${detail.to}` : ""}
                  </div>
                </div>
                <pre style={{
                  maxHeight: 300, overflowY: "auto", margin: 0, padding: "10px 12px", background: CK.space,
                  fontFamily: MONO, fontSize: 10.5, color: CK.ink, whiteSpace: "pre-wrap", lineHeight: 1.55,
                }}>{detail.body}</pre>
              </div>
            )}

            {/* Inbox / list of rows — click a row to open it */}
            {!detail && result?.result?.rows && (
              <div data-testid={`ws-connector-result-${tool.id}`} style={{ border: `1px solid ${CK.line}`, maxHeight: 320, overflowY: "auto" }}>
                {result.result.rows.length === 0 && (
                  <div style={{ padding: "12px", fontFamily: MONO, fontSize: 10, color: CK.inkSoft }}>Nothing here right now.</div>
                )}
                {result.result.rows.map((row) => (
                  <button key={row.id || row.secondary} type="button" data-testid={`ws-row-${tool.id}-${row.id}`}
                    disabled={!openAction} onClick={() => openAction && void openRow(row.id)}
                    style={{
                      display: "block", width: "100%", textAlign: "left", background: "transparent",
                      border: "none", borderBottom: `1px solid ${CK.lineSoft}`, padding: "7px 11px",
                      cursor: openAction ? "pointer" : "default", color: CK.ink, fontFamily: MONO,
                    }}>
                    <div style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: CK.ink, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.primary}</span>
                      <span style={{ fontSize: 8.5, color: CK.inkDim, whiteSpace: "nowrap" }}>{row.meta}</span>
                    </div>
                    <div style={{ fontSize: 10.5, color: CK.inkSoft, marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.secondary}</div>
                    {row.preview && <div style={{ fontSize: 9, color: CK.inkDim, marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.preview}</div>}
                  </button>
                ))}
              </div>
            )}

            {/* Plain-text fallback (web page, http json, excel range) */}
            {!detail && result && !result.result?.rows && (
              <pre data-testid={`ws-connector-result-${tool.id}`} style={{
                maxHeight: 200, overflowY: "auto", margin: 0, padding: "8px 10px", background: CK.space,
                border: `1px solid ${CK.line}`, fontFamily: MONO, fontSize: 10, color: CK.inkSoft, whiteSpace: "pre-wrap",
              }}>{result.result?.text}</pre>
            )}

            {(result || detail) && (
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 6, marginTop: 6 }}>
                {agents.length > 0 && (result?.result?.text || detail?.body) && (
                  <CkButton tone="cyan" disabled={analyzing} data-testid={`ws-connector-analyze-${tool.id}`} onClick={() => void analyze()}>{analyzing ? "…" : "✨ ANALYZE"}</CkButton>
                )}
                {isTicketing && agents.length > 0 && (result?.result?.text || detail?.body) && (
                  <CkButton tone="amber" disabled={investigating} data-testid={`ws-connector-investigate-${tool.id}`} onClick={() => void doInvestigate()}>{investigating ? "…" : "🔍 INVESTIGATE"}</CkButton>
                )}
                <CkButton tone="green" data-testid={`ws-connector-save-${tool.id}`} onClick={() => void save()}>SAVE</CkButton>
              </div>
            )}
            {analysis && (
              <div data-testid={`ws-connector-analysis-${tool.id}`} style={{ marginTop: 6, borderLeft: `2px solid ${CK.cyan}`, paddingLeft: 9, fontFamily: MONO, fontSize: 10, color: CK.inkSoft, whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{analysis}</div>
            )}
            {investigation && (
              <div data-testid={`ws-connector-investigation-${tool.id}`} style={{ marginTop: 6, borderLeft: `2px solid ${CK.amber}`, paddingLeft: 9 }}>
                <div style={{ fontFamily: MONO, fontSize: 10, color: CK.inkSoft, whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{investigation.hypothesis}</div>
                {investigation.commands.length > 0 && (
                  <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: 5 }}>
                    {investigation.commands.map((c, i) => (
                      <button key={i} type="button" data-testid={`ws-invest-cmd-${tool.id}-${i}`}
                        onClick={() => { if (onSuggestCommand) onSuggestCommand(c); else { void navigator.clipboard?.writeText(c); notify("green", "Copied"); } }}
                        title={onSuggestCommand ? "send to terminal" : "copy"}
                        style={{ background: "none", border: `1px solid ${CK.line}`, color: CK.green, cursor: "pointer", fontFamily: MONO, fontSize: 9, padding: "2px 7px" }}>{onSuggestCommand ? "▸ " : "⧉ "}{c}</button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Governed write-back — never fires directly; queues for approval */}
            {writeActions.length > 0 && !isChat && (
              <div style={{ marginTop: 10, borderTop: `1px solid ${CK.lineSoft}`, paddingTop: 8 }}>
                <div style={{ fontFamily: MONO, fontSize: 8.5, color: writeActions.every((a) => a.direct) ? CK.green : CK.amber, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 5 }}>
                  {writeActions.every((a) => a.direct) ? "Actions · you do it — governed + receipted" : "Governed actions · human-approved"}
                </div>
                {writeActions.map((act) => (
                  <div key={act.key} style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 6 }}>
                    {act.params.map((p) => (
                      <CkInput key={p} data-testid={`ws-write-${tool.id}-${p}`} placeholder={p}
                        value={writeParams[p] ?? ""} onChange={(e) => setWriteParams({ ...writeParams, [p]: e.target.value })}
                        style={{ flex: "1 1 120px" }} />
                    ))}
                    <CkButton tone={act.direct ? "green" : "amber"} disabled={writing} data-testid={`ws-write-go-${tool.id}-${act.key}`}
                      onClick={() => void requestWrite(act)}>▸ {act.direct ? "" : "REQUEST "}{act.label.toUpperCase()}</CkButton>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </CkPanel>
  );
}

/* A control-bar toggle — reveals a secondary panel (catalog, playbook, comms)
 * on demand so the desk stays uncluttered. */
function CkTab({ active, hue = CK.cyan, onClick, children, testid }: {
  active?: boolean; hue?: string; onClick: () => void; children: React.ReactNode; testid?: string;
}): React.ReactElement {
  return (
    <button type="button" data-testid={testid} onClick={onClick} style={{
      fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: "0.04em", cursor: "pointer",
      color: active ? CK.space : CK.ink, background: active ? hue : "transparent",
      border: `1px solid ${active ? hue : CK.line}`, padding: "5px 11px", whiteSpace: "nowrap",
      boxShadow: active ? `0 0 10px ${hue}55` : "none",
    }}>{children}</button>
  );
}

/* A labelled zone divider — "YOUR TOOLS", "YOUR CREW" — with an optional action. */
function SectionHead({ label, hue, count, action }: {
  label: string; hue: string; count?: React.ReactNode; action?: React.ReactNode;
}): React.ReactElement {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "20px 0 10px" }}>
      <span style={{ width: 9, height: 9, background: hue, boxShadow: `0 0 8px ${hue}`, flexShrink: 0 }} />
      <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 800, letterSpacing: "0.18em",
        textTransform: "uppercase", color: CK.ink, textShadow: `0 0 12px ${hue}55`, whiteSpace: "nowrap" }}>{label}</span>
      {count != null && <span style={{ fontFamily: MONO, fontSize: 9.5, color: CK.inkDim, whiteSpace: "nowrap" }}>{count}</span>}
      <span style={{ flex: 1, height: 1, background: `linear-gradient(90deg, ${hue}55, transparent)` }} />
      {action}
    </div>
  );
}

// Two-way chat for Slack / Teams — read a channel's messages and reply, in-workspace.
function ChatPanel({ tool, connector, workUnitId }: {
  tool: api.ConnectedTool; connector: api.Connector; workUnitId: string;
}): React.ReactElement {
  const msgAction = connector.actions.find((a) => a.key === "messages");
  const chanParams = msgAction?.params || [];
  const [chan, setChan] = React.useState<Record<string, string>>({});
  const [rows, setRows] = React.useState<api.ConnectorRow[]>([]);
  const [reply, setReply] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const ready = chanParams.length > 0 && chanParams.every((p) => (chan[p] || "").trim());
  const load = async () => {
    if (!ready) { notify("sienna", "Enter the channel first."); return; }
    setBusy(true);
    try { const r = await api.invokeConnector(workUnitId, tool.id, "messages", chan); setRows(r.result?.rows || []); }
    catch (e) { notify("sienna", (e as Error).message); } finally { setBusy(false); }
  };
  const send = async () => {
    if (!ready || !reply.trim()) { notify("sienna", "Enter the channel and a message."); return; }
    setBusy(true);
    try {
      await api.invokeConnector(workUnitId, tool.id, "post_message", { ...chan, message: reply.trim() });
      setReply(""); notify("green", "Sent ✓ — receipted."); void load();
    } catch (e) { notify("sienna", (e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div data-testid={`ws-chat-${tool.id}`}>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
        {chanParams.map((p) => (
          <CkInput key={p} data-testid={`ws-chat-${tool.id}-${p}`} placeholder={p}
            value={chan[p] ?? ""} onChange={(e) => setChan({ ...chan, [p]: e.target.value })} style={{ flex: "1 1 120px" }} />
        ))}
        <CkButton tone="cyan" disabled={busy} data-testid={`ws-chat-load-${tool.id}`} onClick={() => void load()}>{busy ? "…" : "▸ LOAD"}</CkButton>
      </div>
      <div data-testid={`ws-chat-msgs-${tool.id}`} style={{ border: `1px solid ${CK.line}`, maxHeight: 260, overflowY: "auto", marginBottom: 8, background: CK.shell }}>
        {rows.length === 0 ? (
          <div style={{ fontFamily: MONO, fontSize: 9.5, color: CK.inkDim, padding: 10, lineHeight: 1.5 }}>Enter a channel and hit LOAD to read the conversation.</div>
        ) : rows.map((m, i) => (
          <div key={i} style={{ padding: "6px 10px", borderBottom: `1px solid ${CK.lineSoft}` }}>
            <div style={{ fontFamily: MONO, fontSize: 8.5, color: CK.cyan }}>{m.primary || "—"}</div>
            <div style={{ fontFamily: MONO, fontSize: 9.5, color: CK.ink, whiteSpace: "pre-wrap", lineHeight: 1.4 }}>{m.secondary}</div>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <CkInput data-testid={`ws-chat-reply-${tool.id}`} placeholder="Reply in this channel…" value={reply}
          onChange={(e) => setReply(e.target.value)} style={{ flex: 1 }} />
        <CkButton tone="green" disabled={busy} data-testid={`ws-chat-send-${tool.id}`} onClick={() => void send()}>▸ SEND</CkButton>
      </div>
      <div style={{ fontFamily: MONO, fontSize: 8, color: CK.inkDim, marginTop: 5 }}>You post as yourself · every message receipted.</div>
    </div>
  );
}

// Add-your-own-tool builder — a no-code REST connector (governed, read-only).
function AddToolPanel({ workUnitId, onAdd, onClose }: {
  workUnitId: string; onAdd: (spec: api.CustomSpec) => void; onClose: () => void;
}): React.ReactElement {
  const [f, setF] = React.useState({ name: "", base_url: "", list_path: "", list_result_path: "", auth_header: "", primary: "", secondary: "", id: "" });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF((s) => ({ ...s, [k]: e.target.value }));
  const [testRes, setTestRes] = React.useState("");
  const ready = !!(f.name.trim() && f.base_url.trim() && f.list_path.trim());
  const spec = (): api.CustomSpec => ({
    name: f.name.trim(), base_url: f.base_url.trim(), list_path: f.list_path.trim(),
    list_result_path: f.list_result_path.trim() || undefined, auth_header: f.auth_header.trim() || undefined,
    map: { id: f.id.trim() || undefined, primary: f.primary.trim() || undefined, secondary: f.secondary.trim() || undefined },
  });
  const test = async () => {
    if (!ready) { setTestRes("Fill name, base URL and list path first."); return; }
    try { const r = await api.testCustomSpec(workUnitId, spec()); setTestRes(r.ok ? `✓ ${r.count} rows found` : `✗ ${r.error}`); }
    catch (e) { setTestRes((e as Error).message); }
  };
  return (
    <div data-testid="ck-add-tool-panel" style={{ border: `1px solid ${CK.cyan}`, borderRadius: 10, background: CK.panel, padding: "10px 12px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 7 }}>
        <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: "0.12em", color: CK.cyan }}>ADD YOUR OWN TOOL · REST API</span>
        <button type="button" data-testid="ck-add-tool-close" onClick={onClose} style={{ marginLeft: "auto", background: "none", border: `1px solid ${CK.line}`, color: CK.inkSoft, cursor: "pointer", fontFamily: MONO, fontSize: 10, padding: "2px 8px" }}>×</button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
        <CkInput data-testid="ck-add-name" placeholder="Name (e.g. Internal API)" value={f.name} onChange={set("name")} />
        <CkInput data-testid="ck-add-base" placeholder="Base URL (https://…)" value={f.base_url} onChange={set("base_url")} />
        <CkInput data-testid="ck-add-list" placeholder="List path (/api/items)" value={f.list_path} onChange={set("list_path")} />
        <CkInput placeholder="Result path (optional, e.g. data)" value={f.list_result_path} onChange={set("list_result_path")} />
        <CkInput placeholder="Auth header (Authorization: Bearer …)" value={f.auth_header} onChange={set("auth_header")} />
        <CkInput placeholder="ID field (e.g. id)" value={f.id} onChange={set("id")} />
        <CkInput placeholder="Primary field (e.g. title)" value={f.primary} onChange={set("primary")} />
        <CkInput placeholder="Secondary field (e.g. status)" value={f.secondary} onChange={set("secondary")} />
      </div>
      <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 8 }}>
        <CkButton tone="cyan" data-testid="ck-add-test" onClick={() => void test()}>▸ TEST</CkButton>
        <CkButton tone="green" data-testid="ck-add-go" onClick={() => { if (ready) onAdd(spec()); else setTestRes("Name, base URL and list path are required."); }}>＋ ADD TOOL</CkButton>
        {testRes && <span style={{ fontFamily: MONO, fontSize: 9, color: testRes.startsWith("✓") ? CK.green : CK.red }}>{testRes}</span>}
      </div>
      <div style={{ fontFamily: MONO, fontSize: 8, color: CK.inkDim, marginTop: 5 }}>Governed & read-only — SSRF-checked, SAIb-scrubbed, receipted. For internal systems, connect via a bridge.</div>
    </div>
  );
}

// Smart Intake — classify a dropped/pasted token, route it to the right governed
// connector, auto-run READS (never writes/commands), and auto-assist.
function classifyIntake(raw: string): { kind: string; value: string } {
  const t = (raw || "").trim();
  if (!t) return { kind: "text", value: t };
  if (/^https?:\/\/\S+$/i.test(t)) return { kind: "url", value: t };
  if (/^\s*(select|with)\b/i.test(t)) return { kind: "sql", value: t };
  const nospace = t.replace(/\s+/g, "");
  if (/^(inc|chg|crq|req|ritm|tkt|sr)-?\d{3,}$/i.test(nospace) || /^\d{4,}$/.test(nospace)) return { kind: "ticket", value: nospace };
  if (/^(sudo |ssh |systemctl|journalctl|tail |grep |cat |df|du |top|ps |netstat|ss |ping |traceroute|curl |wget |kubectl|docker |uptime|free|iostat|vmstat|dmesg|ls |cd |echo )/i.test(t) || t.startsWith("$ ")) {
    return { kind: "ssh", value: t.replace(/^\$\s*/, "") };
  }
  return { kind: "text", value: t };
}
const INTAKE_LABEL: Record<string, string> = { url: "🌐 Web page", sql: "🗄️ SQL", ticket: "🎫 Ticket", ssh: "⌘ Command", text: "📝 Note", file: "📎 File", case: "⧉ Case" };

type IntakeItem = { id: number; kind: string; value: string; status: string; result?: string; rows?: api.ConnectorRow[]; assist?: string;
  table?: string[][]; citations?: api.Citation[]; act?: { toolId: string; param: string; id: string }; acted?: string };

function SmartWorkspace(props: {
  room: api.RoleWorkspace; workUnitId: string;
  connectRaw: (key: string) => Promise<api.ConnectedTool | null>;
  onRefresh: () => void; onPrepareTerminal?: (cmd: string) => void;
}): React.ReactElement {
  const { room, workUnitId } = props;
  const [input, setInput] = React.useState("");
  const [items, setItems] = React.useState<IntakeItem[]>([]);
  const [drag, setDrag] = React.useState(false);
  const [preview, setPreview] = React.useState<api.SaibPreview | null>(null);
  const [previewText, setPreviewText] = React.useState("");
  const idRef = React.useRef(0);
  const agent = room.agents.find((a) => a.live) || room.agents[0];

  // SAIb Preview — show, before any agent sees it, exactly what will be masked.
  const runPreview = async () => {
    const t = input.trim();
    if (!t) { notify("sienna", "Type or paste something to preview."); return; }
    try {
      const p = await api.saibPreview(input);
      setPreview(p); setPreviewText(input);
      notify(p.count ? "green" : "green", p.count ? `${p.count} item${p.count === 1 ? "" : "s"} will be masked` : "Nothing sensitive detected");
    } catch (e) { notify("sienna", (e as Error).message); }
  };
  // Highlight the masked spans over the previewed text.
  const previewSegments = React.useMemo(() => {
    if (!preview) return null;
    const spans = [...preview.spans].sort((a, b) => a.start - b.start);
    const segs: { text: string; masked: boolean; type?: string }[] = [];
    let cur = 0;
    for (const s of spans) {
      if (s.start < cur || s.start > previewText.length) continue;
      if (s.start > cur) segs.push({ text: previewText.slice(cur, s.start), masked: false });
      segs.push({ text: previewText.slice(s.start, s.end), masked: true, type: s.type });
      cur = s.end;
    }
    if (cur < previewText.length) segs.push({ text: previewText.slice(cur), masked: false });
    return segs;
  }, [preview, previewText]);

  const runRead = async (key: string, action: string, params: Record<string, string>) => {
    let tool = room.connected_tools.find((t) => t.connector_key === key);
    if (!tool) { const res = await props.connectRaw(key); if (!res || !res.id) throw new Error(`Connect ${key} first.`); props.onRefresh(); tool = res; }
    const r = await api.invokeConnector(workUnitId, tool.id, action, params);
    return (r.result || {}) as { text?: string; rows?: api.ConnectorRow[]; detail?: { body?: string } };
  };

  const process = async (raw: string) => {
    const c = classifyIntake(raw);
    if (!c.value) return;
    if (c.kind === "ssh") {
      setItems((a) => [{ id: ++idRef.current, kind: "ssh", value: c.value, status: "prepared",
        assist: props.onPrepareTerminal ? "Prepared in the governed Terminal — review, then run it yourself." : "Connect an SSH bridge to run this (governed)." }, ...a]);
      if (props.onPrepareTerminal) { props.onPrepareTerminal(c.value); notify("green", "Command sent to the governed Terminal — review + run."); }
      else notify("sienna", "Connect an SSH bridge to run commands.");
      return;
    }
    const id = ++idRef.current;
    setItems((a) => [{ id, kind: c.kind, value: c.value, status: "working" }, ...a]);
    const patch = (p: Partial<IntakeItem>) => setItems((a) => a.map((x) => (x.id === id ? { ...x, ...p } : x)));
    try {
      let text = ""; let rows: api.ConnectorRow[] | undefined; let label = c.kind;
      if (c.kind === "url") { const r = await runRead("web_read", "fetch", { url: c.value }); text = String(r.text || ""); label = "web page"; }
      else if (c.kind === "sql") { const r = await runRead("sql_read", "query", { sql: c.value }); text = String(r.text || ""); rows = r.rows; label = "query result"; }
      else if (c.kind === "ticket") {
        const rt = room.connected_tools.find((t) => t.connector_key === "servicenow") ? { key: "servicenow", param: "sys_id" }
          : room.connected_tools.find((t) => t.connector_key === "remedy") ? { key: "remedy", param: "incident_id" } : null;
        if (!rt) throw new Error("Connect Remedy or ServiceNow to open a ticket.");
        const r = await runRead(rt.key, "open", { [rt.param]: c.value }); text = String(r.detail?.body || r.text || ""); label = "ticket";
        const tk = room.connected_tools.find((t) => t.connector_key === rt.key);
        if (tk) patch({ act: { toolId: tk.id, param: rt.param, id: c.value } });
      } else { text = c.value; label = "note"; }
      patch({ status: "read", result: text, rows });
      if (agent && text.trim()) {
        const a = await api.analyzeData(workUnitId, agent.key, label, text);
        patch({ assist: `${a.agent_name}: ${a.analysis}`, citations: a.citations, status: "done" });
      } else patch({ status: "done" });
    } catch (e) { patch({ status: "error", assist: (e as Error).message }); notify("sienna", (e as Error).message); }
  };

  const ingestOne = async (file: File) => {
    const id = ++idRef.current;
    setItems((a) => [{ id, kind: "file", value: file.name, status: "working" }, ...a]);
    const patch = (p: Partial<IntakeItem>) => setItems((a) => a.map((x) => (x.id === id ? { ...x, ...p } : x)));
    try {
      const r = await api.ingestFile(workUnitId, file);
      patch({ status: "read", result: r.text, table: r.table, value: `${file.name} · ${r.kind}${r.masked_entities ? ` · ${r.masked_entities} scrubbed` : ""}` });
      if (agent && r.text.trim()) {
        const a = await api.analyzeData(workUnitId, agent.key, r.name, r.text);
        patch({ assist: `${a.agent_name}: ${a.analysis}`, citations: a.citations, status: "done" });
      } else patch({ status: "done" });
    } catch (e) { patch({ status: "error", assist: (e as Error).message }); notify("sienna", (e as Error).message); }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDrag(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length) { Array.from(e.dataTransfer.files).slice(0, 8).forEach((f) => void ingestOne(f)); return; }
    const t = e.dataTransfer.getData("text/plain"); if (t) void process(t);
  };

  // Assemble a case — cross-reference several intake items into one synthesis.
  const [sel, setSel] = React.useState<Set<number>>(new Set());
  const toggleSel = (id: number) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const assembleCase = async () => {
    const chosen = items.filter((x) => sel.has(x.id) && (x.result || x.assist));
    if (chosen.length < 2) return;
    if (!agent) { notify("sienna", "No agent on this desk."); return; }
    const ctx = chosen.map((x) => `## ${INTAKE_LABEL[x.kind] || x.kind} — ${x.value}\n${x.result || x.assist || ""}`).join("\n\n").slice(0, 12000);
    const id = ++idRef.current;
    setItems((a) => [{ id, kind: "case", value: `Case assembled from ${chosen.length} items`, status: "working" }, ...a]);
    const patch = (p: Partial<IntakeItem>) => setItems((a) => a.map((x) => (x.id === id ? { ...x, ...p } : x)));
    try {
      const r = await api.analyzeData(workUnitId, agent.key, "case file", `Cross-reference these items and give one combined analysis — the situation, how they relate, and the recommended next step:\n\n${ctx}`);
      patch({ status: "done", assist: `${r.agent_name}: ${r.analysis}`, citations: r.citations }); setSel(new Set());
    } catch (e) { patch({ status: "error", assist: (e as Error).message }); notify("sienna", (e as Error).message); }
  };

  const saveCard = async (it: IntakeItem) => {
    // Ephemeral policy: a dropped file's contents are never persisted — save the
    // ANALYSIS only. Governed connector reads (web/ticket/sql) may include their data.
    const body = it.kind === "file"
      ? `${it.value}\n\n${it.assist || ""}\n\n(Source file was ephemeral — analysis only.)`
      : `${it.value}\n\n${it.assist || ""}${it.result ? `\n\n---\n${it.result.slice(0, 4000)}` : ""}`;
    try {
      await api.saveWorkspaceFile(workUnitId, {
        name: `${it.kind === "case" ? "Case" : "Analysis"} — ${it.value}`.slice(0, 120),
        content: body, kind: it.kind === "case" ? "case" : "report",
        source_agent_name: (it.assist || "").split(":")[0],
      });
      notify("green", "Saved to Flight Recorder ✓"); props.onRefresh();
    } catch (e) { notify("sienna", (e as Error).message); }
  };

  // Prepared write — from a ticket card, add a governed work note (direct or
  // approval-gated per org policy). Never fires until the operator clicks.
  const [notes, setNotes] = React.useState<Record<number, string>>({});
  const sendNote = async (it: IntakeItem) => {
    if (!it.act) return;
    const note = (notes[it.id] || "").trim();
    if (!note) { notify("sienna", "Write the note first."); return; }
    const patch = (p: Partial<IntakeItem>) => setItems((a) => a.map((x) => (x.id === it.id ? { ...x, ...p } : x)));
    try {
      const r = await api.invokeConnector(workUnitId, it.act.toolId, "add_note", { [it.act.param]: it.act.id, note });
      patch({ acted: r.pending_approval ? "Work note queued — a governor must approve it." : "Work note added ✓ — receipted." });
      setNotes((n) => ({ ...n, [it.id]: "" }));
      notify("green", r.pending_approval ? "Queued for approval." : "Work note added ✓");
    } catch (e) { notify("sienna", (e as Error).message); }
  };
  const [showHistory, setShowHistory] = React.useState(false);
  const [openFile, setOpenFile] = React.useState<string | null>(null);
  const savedCases = room.files.filter((f) => f.kind === "case" || f.kind === "report");
  const [statusSel, setStatusSel] = React.useState<Record<number, string>>({});
  const sendStatus = async (it: IntakeItem) => {
    if (!it.act) return;
    const status = statusSel[it.id] || "Resolved";
    const patch = (p: Partial<IntakeItem>) => setItems((a) => a.map((x) => (x.id === it.id ? { ...x, ...p } : x)));
    try {
      const r = await api.invokeConnector(workUnitId, it.act.toolId, "set_status", { [it.act.param]: it.act.id, status });
      patch({ acted: r.pending_approval ? `Status → ${status} queued — a governor must approve it.` : `Status set to ${status} ✓ — receipted.` });
      notify("green", r.pending_approval ? "Queued for approval." : `Status → ${status} ✓`);
    } catch (e) { notify("sienna", (e as Error).message); }
  };

  return (
    <div data-testid="ws-smart">
      <div data-testid="ws-smart-drop" onDrop={onDrop}
        onDragOver={(e) => { e.preventDefault(); if (!drag) setDrag(true); }} onDragLeave={() => setDrag(false)}
        style={{ border: `1.5px dashed ${drag ? CK.cyan : CK.line}`, borderRadius: 12, background: drag ? `${CK.cyan}10` : CK.space, padding: 14, marginBottom: 12 }}>
        <div style={{ fontFamily: MONO, fontSize: 11, color: CK.ink, letterSpacing: "0.06em", marginBottom: 3 }}>⌁ SMART WORKSPACE</div>
        <div style={{ fontFamily: MONO, fontSize: 9.5, color: CK.inkSoft, lineHeight: 1.5, marginBottom: 8 }}>Drop or paste anything — a URL, ticket number, SQL query, server command, or a <b style={{ color: CK.ink }}>file</b> (Excel / Word / PDF / text). WACE detects it, runs the governed read, and an agent assists. Files are parsed in-memory and SAIb-scrubbed before any agent sees them — nothing is stored. Writes & commands are prepared for you, never auto-run.</div>
        <textarea data-testid="ws-smart-input" value={input} onChange={(e) => setInput(e.target.value)}
          placeholder={"https://…   ·   INC0012345   ·   SELECT … FROM …   ·   systemctl status nginx"}
          style={{ width: "100%", minHeight: 54, background: CK.shell, border: `1px solid ${CK.line}`, color: CK.ink, fontFamily: MONO, fontSize: 10.5, padding: 8, resize: "vertical" }} />
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
          {input.trim() && <span style={{ fontFamily: MONO, fontSize: 8.5, color: CK.cyan }}>detected: {INTAKE_LABEL[classifyIntake(input).kind]}</span>}
          <label style={{ marginLeft: input.trim() ? undefined : "auto", fontFamily: MONO, fontSize: 9, color: CK.cyan, border: `1px solid ${CK.line}`, padding: "3px 9px", cursor: "pointer" }}>
            📎 file<input type="file" data-testid="ws-smart-file" style={{ display: "none" }} accept=".xlsx,.xlsm,.docx,.pdf,.txt,.csv,.md,.log,.json"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void ingestOne(f); e.target.value = ""; }} />
          </label>
          {input.trim() && (
            <button type="button" data-testid="ws-smart-preview-btn" onClick={() => void runPreview()}
              style={{ background: "none", border: `1px solid ${CK.line}`, color: CK.inkSoft, cursor: "pointer", fontFamily: MONO, fontSize: 9, padding: "3px 9px" }}>🛡 preview redaction</button>
          )}
          <CkButton tone="cyan" data-testid="ws-smart-go" onClick={() => { const v = input; setInput(""); void process(v); setPreview(null); }}>▸ PROCESS</CkButton>
        </div>
        {preview && previewSegments && (
          <div data-testid="ws-smart-preview" style={{ marginTop: 10, border: `1px solid ${CK.line}`, borderRadius: 8, background: CK.shell, padding: "9px 11px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
              <span style={{ fontFamily: MONO, fontSize: 9, color: preview.count ? CK.amber : CK.green, letterSpacing: "0.06em" }}>
                🛡 {preview.count ? `${preview.count} item${preview.count === 1 ? "" : "s"} MASKED before any agent sees this` : "NOTHING SENSITIVE DETECTED"}
              </span>
              {Object.entries(preview.by_type).map(([t, n]) => (
                <span key={t} style={{ fontFamily: MONO, fontSize: 7.5, color: CK.amber, border: `1px solid ${CK.amber}55`, borderRadius: 3, padding: "0 5px" }}>{t}·{n}</span>
              ))}
              <button type="button" data-testid="ws-smart-preview-close" onClick={() => setPreview(null)}
                style={{ marginLeft: "auto", background: "none", border: "none", color: CK.inkDim, cursor: "pointer", fontFamily: MONO, fontSize: 8.5 }}>dismiss</button>
            </div>
            <div style={{ fontFamily: MONO, fontSize: 9.5, color: CK.inkSoft, lineHeight: 1.6, whiteSpace: "pre-wrap", maxHeight: 150, overflowY: "auto" }}>
              {previewSegments.map((seg, si) => seg.masked
                ? <mark key={si} title={seg.type} style={{ background: `${CK.amber}33`, color: CK.amber, borderRadius: 2, padding: "0 2px", textDecoration: "line-through" }}>{seg.text}</mark>
                : <span key={si}>{seg.text}</span>)}
            </div>
          </div>
        )}
      </div>
      {savedCases.length > 0 && (
        <div data-testid="ws-smart-history" style={{ marginBottom: 12, border: `1px solid ${CK.line}`, borderRadius: 9, background: CK.space }}>
          <button type="button" data-testid="ws-smart-history-toggle" onClick={() => setShowHistory((v) => !v)}
            style={{ width: "100%", display: "flex", alignItems: "center", gap: 8, background: "none", border: "none", cursor: "pointer", padding: "8px 11px", fontFamily: MONO, fontSize: 9.5, color: CK.ink }}>
            <span style={{ color: CK.green }}>▤</span>
            <span style={{ letterSpacing: "0.06em" }}>FLIGHT RECORDER — {savedCases.length} saved case{savedCases.length === 1 ? "" : "s"}</span>
            <span style={{ marginLeft: "auto", color: CK.inkSoft }}>{showHistory ? "▾ hide" : "▸ show"}</span>
          </button>
          {showHistory && (
            <div style={{ padding: "0 11px 10px", display: "flex", flexDirection: "column", gap: 6 }}>
              {savedCases.map((f) => (
                <div key={f.id} data-testid={`ws-smart-case-${f.id}`} style={{ border: `1px solid ${CK.lineSoft}`, borderLeft: `3px solid ${f.kind === "case" ? CK.amber : CK.green}`, borderRadius: 6, background: CK.panel }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 9px", flexWrap: "wrap" }}>
                    <span style={{ fontFamily: MONO, fontSize: 8, color: f.kind === "case" ? CK.amber : CK.green }}>{f.kind === "case" ? "⧉ CASE" : "▤ REPORT"}</span>
                    <span style={{ flex: 1, minWidth: 140, fontFamily: MONO, fontSize: 9.5, color: CK.ink, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.name}</span>
                    <span style={{ fontFamily: MONO, fontSize: 8, color: CK.inkDim }}>{(f.created_at || "").slice(0, 16).replace("T", " ")}</span>
                    <button type="button" data-testid={`ws-smart-case-open-${f.id}`} onClick={() => setOpenFile((o) => (o === f.id ? null : f.id))}
                      style={{ background: "none", border: `1px solid ${CK.line}`, color: CK.cyan, cursor: "pointer", fontFamily: MONO, fontSize: 8, padding: "2px 7px" }}>{openFile === f.id ? "close" : "open"}</button>
                    <button type="button" onClick={() => void copyText(f.content)}
                      style={{ background: "none", border: `1px solid ${CK.line}`, color: CK.inkSoft, cursor: "pointer", fontFamily: MONO, fontSize: 8, padding: "2px 7px" }}>copy</button>
                    <button type="button" onClick={() => downloadText(f.name, f.content)}
                      style={{ background: "none", border: `1px solid ${CK.line}`, color: CK.inkSoft, cursor: "pointer", fontFamily: MONO, fontSize: 8, padding: "2px 7px" }}>download</button>
                  </div>
                  {openFile === f.id && (
                    <div style={{ padding: "0 9px 8px", maxHeight: 220, overflowY: "auto", fontFamily: MONO, fontSize: 9, color: CK.inkSoft, whiteSpace: "pre-wrap", lineHeight: 1.5, borderTop: `1px solid ${CK.lineSoft}`, paddingTop: 7 }}>{f.content}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {items.length === 0 && <div style={{ fontFamily: MONO, fontSize: 9.5, color: CK.inkDim, padding: "4px 2px" }}>Everything you drop appears here — analyzed, receipted, and yours to act on.</div>}
      {sel.size >= 2 && (
        <div data-testid="ws-smart-assemblebar" style={{ display: "flex", gap: 8, alignItems: "center", padding: "5px 9px", marginBottom: 8, background: `${CK.cyan}12`, border: `1px solid ${CK.cyan}44`, borderRadius: 8 }}>
          <span style={{ fontFamily: MONO, fontSize: 9, color: CK.cyan }}>{sel.size} selected</span>
          <CkButton tone="cyan" data-testid="ws-smart-assemble" onClick={() => void assembleCase()}>⧉ ASSEMBLE CASE</CkButton>
          <button type="button" onClick={() => setSel(new Set())} style={{ marginLeft: "auto", background: "none", border: `1px solid ${CK.line}`, color: CK.inkSoft, cursor: "pointer", fontFamily: MONO, fontSize: 8.5, padding: "2px 8px" }}>clear</button>
        </div>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {items.map((it) => (
          <div key={it.id} data-testid={`ws-smart-item-${it.id}`} style={{ border: `1px solid ${CK.line}`, borderLeft: `3px solid ${it.status === "error" ? CK.red : it.kind === "case" ? CK.amber : CK.cyan}`, borderRadius: 9, background: CK.panel, padding: "9px 11px" }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              {(it.result || it.assist) && it.kind !== "case" && (
                <input type="checkbox" data-testid={`ws-smart-sel-${it.id}`} checked={sel.has(it.id)} onChange={() => toggleSel(it.id)} style={{ cursor: "pointer", flexShrink: 0 }} />
              )}
              <span style={{ fontFamily: MONO, fontSize: 9, color: it.kind === "case" ? CK.amber : CK.cyan }}>{INTAKE_LABEL[it.kind] || it.kind}</span>
              <span style={{ fontFamily: MONO, fontSize: 9, color: CK.inkSoft, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{it.value}</span>
              <span style={{ fontFamily: MONO, fontSize: 8, color: it.status === "error" ? CK.red : it.status === "done" || it.status === "prepared" ? CK.green : CK.amber }}>{it.status}</span>
            </div>
            {it.rows && it.rows.length > 0 && (
              <div style={{ marginTop: 6, maxHeight: 150, overflowY: "auto", border: `1px solid ${CK.lineSoft}` }}>
                {it.rows.slice(0, 20).map((r, i) => (
                  <div key={i} style={{ padding: "2px 8px", borderBottom: `1px solid ${CK.lineSoft}`, fontFamily: MONO, fontSize: 8.5, color: CK.inkSoft, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.primary}{r.secondary ? ` · ${r.secondary}` : ""}</div>
                ))}
              </div>
            )}
            {it.table && it.table.length > 0 && (
              <div data-testid={`ws-smart-table-${it.id}`} style={{ marginTop: 6, maxHeight: 200, overflow: "auto", border: `1px solid ${CK.lineSoft}`, borderRadius: 4 }}>
                <table style={{ borderCollapse: "collapse", width: "100%", fontFamily: MONO, fontSize: 8.5 }}>
                  <tbody>
                    {it.table.slice(0, 60).map((row, ri) => (
                      <tr key={ri} style={{ background: ri === 0 ? `${CK.cyan}18` : ri % 2 ? `${CK.ink}05` : "transparent" }}>
                        {row.slice(0, 20).map((cell, ci) => (
                          ri === 0
                            ? <th key={ci} style={{ padding: "2px 7px", borderRight: `1px solid ${CK.lineSoft}`, borderBottom: `1px solid ${CK.line}`, textAlign: "left", color: CK.cyan, fontWeight: 700, whiteSpace: "nowrap" }}>{cell}</th>
                            : <td key={ci} style={{ padding: "2px 7px", borderRight: `1px solid ${CK.lineSoft}`, borderBottom: `1px solid ${CK.lineSoft}`, color: CK.inkSoft, whiteSpace: "nowrap", maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis" }}>{cell}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {it.table.length > 60 && <div style={{ padding: "3px 7px", fontFamily: MONO, fontSize: 8, color: CK.inkDim }}>… {it.table.length - 60} more rows (full text scrubbed & sent to the agent)</div>}
              </div>
            )}
            {it.result && !it.rows && !it.table && <div style={{ marginTop: 6, maxHeight: 130, overflowY: "auto", fontFamily: MONO, fontSize: 9, color: CK.inkSoft, whiteSpace: "pre-wrap", lineHeight: 1.45 }}>{it.result.slice(0, 1200)}</div>}
            {it.assist && <div style={{ marginTop: 6, borderLeft: `2px solid ${it.status === "error" ? CK.red : CK.cyan}`, paddingLeft: 9, fontFamily: MONO, fontSize: 9.5, color: it.status === "error" ? CK.red : CK.ink, whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{it.assist}</div>}
            {it.citations && it.citations.length > 0 && (
              <div data-testid={`ws-smart-cites-${it.id}`} style={{ marginTop: 7 }}>
                <div style={{ fontFamily: MONO, fontSize: 8, color: CK.inkSoft, letterSpacing: "0.1em", marginBottom: 3 }}>GROUNDING · CLAIMS TRACED TO THE SOURCE</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                  {it.citations.map((c, ci) => {
                    const hue = c.confidence === "high" ? CK.green : c.confidence === "low" ? CK.red : CK.amber;
                    return (
                      <div key={ci} style={{ display: "flex", gap: 6, alignItems: "baseline", fontFamily: MONO, fontSize: 9 }}>
                        <span title={`${c.confidence} confidence`} style={{ flexShrink: 0, color: hue, border: `1px solid ${hue}66`, borderRadius: 3, padding: "0 5px", fontSize: 7.5, letterSpacing: "0.06em", textTransform: "uppercase" }}>{c.confidence}</span>
                        <span style={{ flex: 1, color: CK.inkSoft, lineHeight: 1.45 }}>{c.claim}</span>
                        {c.lines.length > 0 && <span style={{ flexShrink: 0, color: CK.cyan, fontSize: 8 }}>L{c.lines.join(",")}</span>}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            {it.assist && it.status !== "error" && (
              <div style={{ marginTop: 6, textAlign: "right" }}>
                <button type="button" data-testid={`ws-smart-save-${it.id}`} onClick={() => void saveCard(it)}
                  style={{ background: "none", border: `1px solid ${CK.green}66`, color: CK.green, cursor: "pointer", fontFamily: MONO, fontSize: 8.5, padding: "2px 9px" }}>⤓ SAVE TO FLIGHT RECORDER</button>
              </div>
            )}
            {it.act && it.status !== "error" && (
              <div style={{ marginTop: 8, borderTop: `1px dashed ${CK.line}`, paddingTop: 7 }}>
                <div style={{ fontFamily: MONO, fontSize: 8, color: CK.inkSoft, letterSpacing: "0.1em", marginBottom: 4 }}>ACT ON THIS TICKET · GOVERNED WRITE-BACK</div>
                {it.acted ? (
                  <div data-testid={`ws-smart-acted-${it.id}`} style={{ fontFamily: MONO, fontSize: 9, color: it.acted.includes("queued") ? CK.amber : CK.green }}>{it.acted}</div>
                ) : (
                  <div style={{ display: "flex", gap: 6, alignItems: "stretch" }}>
                    <input data-testid={`ws-smart-note-${it.id}`} value={notes[it.id] || ""}
                      onChange={(e) => setNotes((n) => ({ ...n, [it.id]: e.target.value }))}
                      placeholder="Add a work note to the ticket…"
                      style={{ flex: 1, background: CK.shell, border: `1px solid ${CK.line}`, color: CK.ink, fontFamily: MONO, fontSize: 9, padding: "3px 7px", borderRadius: 4 }} />
                    <button type="button" data-testid={`ws-smart-sendnote-${it.id}`} onClick={() => void sendNote(it)}
                      style={{ background: "none", border: `1px solid ${CK.cyan}66`, color: CK.cyan, cursor: "pointer", fontFamily: MONO, fontSize: 8.5, padding: "2px 9px", whiteSpace: "nowrap" }}>▸ ADD NOTE</button>
                  </div>
                )}
                {!it.acted && (
                  <div style={{ display: "flex", gap: 6, alignItems: "stretch", marginTop: 6 }}>
                    <select data-testid={`ws-smart-status-${it.id}`} value={statusSel[it.id] || "Resolved"}
                      onChange={(e) => setStatusSel((s) => ({ ...s, [it.id]: e.target.value }))}
                      style={{ flex: 1, background: CK.shell, border: `1px solid ${CK.line}`, color: CK.ink, fontFamily: MONO, fontSize: 9, padding: "3px 7px", borderRadius: 4 }}>
                      {["Acknowledged", "In Progress", "Pending", "Resolved", "Closed"].map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                    <button type="button" data-testid={`ws-smart-sendstatus-${it.id}`} onClick={() => void sendStatus(it)}
                      style={{ background: "none", border: `1px solid ${CK.amber}66`, color: CK.amber, cursor: "pointer", fontFamily: MONO, fontSize: 8.5, padding: "2px 9px", whiteSpace: "nowrap" }}>▸ SET STATUS</button>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function RoomView(props: {
  room: api.RoleWorkspace | null;
  loading: boolean;
  onBack: () => void;
  onRefresh: () => void;
  onGoToJudgment?: () => void;
}): React.ReactElement {
  const { room } = props;
  const [evidence, setEvidence] = React.useState("");
  const [draft, setDraft] = React.useState("");
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  const [focus, setFocus] = React.useState<{ key: string; brief?: string; nonce: number } | null>(null);
  const [panel, setPanel] = React.useState<string | null>(null);   // which secondary panel is open
  const togglePanel = (p: string) => setPanel((cur) => (cur === p ? null : p));
  const accent = room ? accentFor(room.role.discipline) : INK;
  const [focusedToolId, setFocusedToolId] = React.useState<string>("");
  const focused = focusedToolId && room ? room.connected_tools.find((t) => t.id === focusedToolId) : undefined;
  const [viewMode, setViewMode] = React.useState<"classic" | "cockpit" | "smart">(() => {
    try { return (localStorage.getItem("wace_viewmode") as "classic" | "cockpit" | "smart") || "smart"; } catch { return "smart"; }
  });
  const setView = (m: "classic" | "cockpit" | "smart") => { setViewMode(m); try { localStorage.setItem("wace_viewmode", m); } catch { /* noop */ } };
  const [qcApp, setQcApp] = React.useState<{ key: string; name: string } | null>(null);
  const [qcBase, setQcBase] = React.useState("");
  const [qcAuth, setQcAuth] = React.useState("");
  // Live per-app badges (open counts) for incident-style apps.
  const [badges, setBadges] = React.useState<Record<string, number>>({});
  const badgeKey = room ? room.connected_tools.map((t) => t.id).join(",") : "";
  React.useEffect(() => {
    if (!room) return;
    const BADGEABLE: Record<string, string> = { servicenow: "incidents", remedy: "incidents", pagerduty: "list" };
    room.connected_tools.forEach((t) => {
      const act = BADGEABLE[t.connector_key];
      if (!act) return;
      api.invokeConnector(room.task.work_unit_id, t.id, act, {})
        .then((r) => setBadges((b) => ({ ...b, [t.connector_key]: (r.result?.rows?.length ?? 0) })))
        .catch(() => undefined);
    });
  }, [badgeKey]);
  const doQuickConnect = async () => {
    if (!room || !qcApp || !qcBase.trim()) { notify("sienna", "Enter the base URL."); return; }
    try {
      await api.connectTool(room.task.work_unit_id, qcApp.key, undefined, undefined, undefined, { base_url: qcBase.trim(), auth_header: qcAuth.trim() });
      notify("green", `${qcApp.name} connected ✓ — cloud, read-only.`);
      setQcApp(null); setQcBase(""); setQcAuth(""); props.onRefresh();
    } catch (e) { notify("sienna", (e as Error).message); }
  };
  const [receipts, setReceipts] = React.useState<api.Receipt[]>([]);
  const [rcpScope, setRcpScope] = React.useState<"desk" | "all">("desk");
  const [shiftRpt, setShiftRpt] = React.useState<{ agent_name: string; report: string } | null>(null);
  const [shiftBusy, setShiftBusy] = React.useState(false);
  const genShiftReport = async () => {
    if (!room) return;
    const agent = room.agents.find((a) => a.live) || room.agents[0];
    if (!agent) { notify("sienna", "No agent on this desk to write the report."); return; }
    setShiftBusy(true);
    try { setShiftRpt(await api.shiftReport(room.task.work_unit_id, agent.key)); }
    catch (e) { notify("sienna", (e as Error).message); } finally { setShiftBusy(false); }
  };
  const saveShiftReport = async () => {
    if (!room || !shiftRpt) return;
    try {
      await api.saveWorkspaceFile(room.task.work_unit_id, { name: "Shift report", content: shiftRpt.report, kind: "report", source_agent_name: shiftRpt.agent_name });
      notify("green", "Shift report saved to Flight Recorder ✓"); props.onRefresh();
    } catch (e) { notify("sienna", (e as Error).message); }
  };
  React.useEffect(() => {
    if ((panel === "receipts" || panel === "replay") && room) {
      const p = (panel === "receipts" && rcpScope === "all") ? api.allReceipts() : api.listReceipts(room.task.work_unit_id);
      Promise.resolve(p).then((r) => setReceipts(r || [])).catch(() => setReceipts([]));
    }
  }, [panel, room, rcpScope]);

  const [cc, setCc] = React.useState<api.CommandCenter | null>(null);

  // ⌘K / Ctrl+K opens the palette from anywhere in the room.
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault(); setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const routeIntent = React.useCallback((q: string) => {
    if (!room) return;
    const a = matchAgent(q, room.agents);
    if (!a) { notify("sienna", "No agents on this desk yet — request one from the catalog."); return; }
    setFocus({ key: a.key, brief: q, nonce: Date.now() });
    notify("green", `Routing to ${a.name} — review the brief and run it.`);
  }, [room]);

  const commands: Cmd[] = React.useMemo(() => {
    if (!room) return [];
    const cmds: Cmd[] = [];
    for (const a of room.agents)
      cmds.push({ id: `run-${a.key}`, group: "Agent", label: `Run ${a.name}`, hint: a.does,
        run: () => setFocus({ key: a.key, nonce: Date.now() }) });
    for (const a of room.agent_catalog)
      cmds.push({ id: `req-${a.key}`, group: "Add", label: `Request ${a.name}`, hint: "add to desk",
        run: () => void requestAgent(a) });
    for (const t of room.toolkit)
      cmds.push({ id: `tool-${t.key}`, group: "Tool", label: t.name, hint: t.status,
        run: () => scrollToTestid("ws-toolkit") });
    for (const f of room.files)
      cmds.push({ id: `file-${f.id}`, group: "File", label: `Copy: ${f.name}`,
        run: () => void copyText(f.content) });
    for (const [label, id] of [["Task", "ws-task"], ["Agents", "ws-agents"], ["Work Files", "ws-files"],
                               ["Connectors", "ws-connectors"], ["Resources", "ws-resources"],
                               ["Discussion", "ws-thread"]] as const)
      cmds.push({ id: `go-${id}`, group: "Go to", label, run: () => scrollToTestid(id) });
    return cmds;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [room]);

  const submit = async () => {
    if (!room) return;
    if (!evidence.trim()) { notify("sienna", "Add an evidence link before submitting."); return; }
    try {
      await api.submitDeliverable(room.task.work_unit_id, { submission_text: "Submitted from workspace.", evidence: [evidence.trim()] });
      notify("green", "Deliverable submitted ✓ — it's now in review.");
      setEvidence(""); props.onRefresh();
    } catch (e) { notify("sienna", (e as Error).message); }
  };

  const postMsg = async () => {
    if (!room || !draft.trim()) return;
    try {
      await api.postMessage(room.task.work_unit_id, draft.trim());
      notify("green", "Message posted ✓");
      setDraft(""); props.onRefresh();
    } catch (e) { notify("sienna", (e as Error).message); }
  };

  const requestAgent = async (a: api.WsAgent) => {
    if (!room) return;
    try {
      await api.requestAgent(room.task.work_unit_id, a.key);
      notify("green", `${a.name} added to your workspace ✓ — you can run it now.`);
      props.onRefresh();
    } catch (e) { notify("sienna", (e as Error).message); }
  };

  const saveAgentOutput = async (a: api.WsAgent, content: string) => {
    if (!room) return;
    if (!content.trim()) { notify("sienna", "Nothing to save yet."); return; }
    try {
      await api.saveWorkspaceFile(room.task.work_unit_id, {
        name: `${a.name} draft`, content, kind: "draft",
        source_agent_key: a.key, source_agent_name: a.name,
      });
      notify("green", "Saved to your Work Files ✓ — reuse it any time.");
      props.onRefresh();
    } catch (e) { notify("sienna", (e as Error).message); }
  };

  const deleteFile = async (id: string) => {
    if (!room) return;
    try {
      await api.deleteWorkspaceFile(room.task.work_unit_id, id);
      notify("green", "File deleted ✓");
      props.onRefresh();
    } catch (e) { notify("sienna", (e as Error).message); }
  };

  const connectTool = async (key: string) => {
    if (!room) return;
    try {
      const res = await api.connectTool(room.task.work_unit_id, key);
      if (res.authorize_url) {
        notify("green", "Redirecting to Microsoft to authorize (read-only)…");
        window.location.href = res.authorize_url;
        return;
      }
      notify("green", "Tool docked ✓ — read-only and governed.");
      props.onRefresh();
    } catch (e) { notify("sienna", (e as Error).message); }
  };

  // Connect (or reuse) a tool and hand back the connected record — for the cockpit's
  // drag-to-open. Cloud apps open the quick-connect form; OAuth redirects.
  const connectRaw = async (key: string): Promise<api.ConnectedTool | null> => {
    if (!room) return null;
    const existing = room.connected_tools.find((t) => t.connector_key === key);
    if (existing) return existing;
    if (CLOUD_APP_KEYS.has(key)) { setQcApp({ key, name: room.connectors.find((c) => c.key === key)?.name || key }); return null; }
    try {
      const res = await api.connectTool(room.task.work_unit_id, key);
      if (res.authorize_url) { window.location.href = res.authorize_url; return null; }
      props.onRefresh();
      return res;
    } catch (e) { notify("sienna", (e as Error).message); return null; }
  };

  const disconnectTool = async (id: string) => {
    if (!room) return;
    try {
      await api.disconnectTool(room.task.work_unit_id, id);
      notify("green", "Tool disconnected ✓");
      props.onRefresh();
    } catch (e) { notify("sienna", (e as Error).message); }
  };

  // On-prem bridge (plug-n-play, network-local connectivity).
  const [bridges, setBridges] = React.useState<api.Bridge[]>([]);
  const [selId, setSelId] = React.useState<string>("");
  const [pairing, setPairing] = React.useState<api.PairBridgeResult | null>(null);
  const [activity, setActivity] = React.useState<api.BridgeActivity | null>(null);
  // The bridge that connect/custom actions target: explicit selection, else first online.
  const bridge = React.useMemo(
    () => bridges.find((b) => b.id === selId) || bridges.find((b) => b.status === "online") || bridges[0] || null,
    [bridges, selId]);
  const loadBridge = React.useCallback(async () => {
    if (!room) return;
    try { setBridges((await api.listBridges(room.task.work_unit_id)) || []); } catch { setBridges([]); }
  }, [room]);
  React.useEffect(() => { void loadBridge(); }, [loadBridge]);   // on mount → toggles reflect bridges
  React.useEffect(() => {
    if (panel === "bridge" && bridge && room) api.bridgeActivity(room.task.work_unit_id, bridge.id).then(setActivity).catch(() => setActivity(null));
  }, [panel, bridge, room]);
  const doPair = async () => {
    if (!room) return;
    try {
      const r = await api.pairBridge(room.task.work_unit_id);
      setPairing(r); setSelId(r.bridge.id); await loadBridge();
      notify("green", "Bridge paired — run the agent inside your network.");
    } catch (e) { notify("sienna", (e as Error).message); }
  };
  const connectViaBridge = async (key: string) => {
    if (!room || !bridge) return;
    try {
      await api.connectTool(room.task.work_unit_id, key, undefined, bridge.id);
      notify("green", "Connected via your bridge ✓ — governed, read-only.");
      props.onRefresh();
    } catch (e) { notify("sienna", (e as Error).message); }
  };
  const revokeBridge = async (bridgeId: string) => {
    if (!room) return;
    try {
      await api.revokeBridge(room.task.work_unit_id, bridgeId);
      setPairing(null); await loadBridge();
      notify("green", "Bridge revoked — its token is dead.");
    } catch (e) { notify("sienna", (e as Error).message); }
  };
  // Governed server terminal (SSH via bridge; governor-only).
  const [canGovern, setCanGovern] = React.useState(false);
  React.useEffect(() => { api.me().then((m) => setCanGovern(!!m.can_govern)).catch(() => undefined); }, []);
  const [ssoCfg, setSsoCfg] = React.useState<api.SsoConfig | null>(null);
  const [samlCfg, setSamlCfg] = React.useState<api.SamlConfig | null>(null);
  const saveSaml = async () => {
    if (!samlCfg) return;
    try { setSamlCfg(await api.setSamlConfig(samlCfg)); notify("green", "SAML config saved ✓"); }
    catch (e) { notify("sienna", (e as Error).message); }
  };
  const [orgTools, setOrgTools] = React.useState<api.OrgTool[]>([]);
  const [orgAddOpen, setOrgAddOpen] = React.useState(false);
  const loadOrgTools = React.useCallback(() => {
    Promise.resolve(api.getOrgTools()).then((r) => setOrgTools(r || [])).catch(() => setOrgTools([]));
  }, []);
  const [users, setUsers] = React.useState<api.DirUser[]>([]);
  const [groups, setGroups] = React.useState<api.AccessGroup[]>([]);
  const [userQ, setUserQ] = React.useState("");
  const [userFilter, setUserFilter] = React.useState<"all" | "active" | "disabled">("all");
  const [govToken, setGovToken] = React.useState("");
  const loadUsers = React.useCallback(() => {
    Promise.resolve(api.listUsers()).then((r) => setUsers(r || [])).catch(() => setUsers([]));
    Promise.resolve(api.getGroups()).then((r) => setGroups(r || [])).catch(() => setGroups([]));
    Promise.resolve(api.getGovernorGroup()).then((r) => setGovToken(r?.token || "")).catch(() => undefined);
  }, []);
  const saveGovToken = async () => {
    try { const r = await api.setGovernorGroup(govToken.trim()); setGovToken(r.token); loadUsers(); notify("green", `Governor group set to “${r.token}” ✓`); }
    catch (e) { notify("sienna", (e as Error).message); }
  };
  const toggleUser = async (u: api.DirUser) => {
    try { await api.setUserActive(u.account_id, u.disabled); loadUsers(); notify("green", `${u.email} ${u.disabled ? "enabled" : "disabled"} ✓`); }
    catch (e) { notify("sienna", (e as Error).message); }
  };
  const [selUsers, setSelUsers] = React.useState<Set<string>>(new Set());
  const toggleSel = (id: string) => setSelUsers((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const selectStale = (list: api.DirUser[]) => {
    const cutoff = Date.now() - 30 * 24 * 3600 * 1000;
    setSelUsers(new Set(list.filter((u) => !u.disabled && (!u.last_seen || new Date(u.last_seen).getTime() < cutoff)).map((u) => u.account_id)));
  };
  const doBulkUsers = async (active: boolean) => {
    const ids = [...selUsers];
    if (!ids.length) return;
    try { const r = await api.bulkSetUsersActive(ids, active); setSelUsers(new Set()); loadUsers(); notify("green", `${r.updated.length} user(s) ${active ? "enabled" : "disabled"} ✓${r.skipped.length ? ` · ${r.skipped.length} skipped` : ""}`); }
    catch (e) { notify("sienna", (e as Error).message); }
  };
  const doUsersCsv = async () => {
    try { await api.downloadUsersCsv(); notify("green", "User directory exported (CSV) ✓"); }
    catch (e) { notify("sienna", (e as Error).message); }
  };
  React.useEffect(() => {
    if (panel === "command" && canGovern) {
      Promise.resolve(api.commandCenter()).then((r) => setCc(r || null)).catch(() => setCc(null));
      Promise.resolve(api.getSsoConfig()).then((r) => setSsoCfg(r || null)).catch(() => setSsoCfg(null));
      Promise.resolve(api.getSamlConfig()).then((r) => setSamlCfg(r || null)).catch(() => setSamlCfg(null));
      loadOrgTools(); loadUsers();
    }
  }, [panel, canGovern, loadOrgTools, loadUsers]);
  const addOrgToolFn = async (spec: api.CustomSpec) => {
    try { await api.addOrgTool(spec.name, "data", spec); setOrgAddOpen(false); loadOrgTools(); props.onRefresh(); notify("green", `${spec.name} added for the whole org ✓`); }
    catch (e) { notify("sienna", (e as Error).message); }
  };
  const removeOrgToolFn = async (key: string) => {
    try { await api.removeOrgTool(key); loadOrgTools(); props.onRefresh(); notify("green", "Org tool removed ✓"); }
    catch (e) { notify("sienna", (e as Error).message); }
  };
  const saveSso = async () => {
    if (!ssoCfg) return;
    const patch: Partial<api.SsoConfig> = { ...ssoCfg };
    if (patch.client_secret === "***") delete patch.client_secret;   // don't overwrite with the mask
    try { setSsoCfg(await api.setSsoConfig(patch)); notify("green", "SSO config saved ✓"); }
    catch (e) { notify("sienna", (e as Error).message); }
  };
  const savePolicy = async (patch: Partial<api.OrgPolicy>) => {
    try { await api.setPolicy(patch); const r = await api.commandCenter(); setCc(r || null); notify("green", "Org policy updated ✓"); }
    catch (e) { notify("sienna", (e as Error).message); }
  };
  const [exporting, setExporting] = React.useState(false);
  const doExport = async () => {
    setExporting(true);
    try { await api.downloadAuditExport(); notify("green", "Signed audit bundle downloaded ✓"); }
    catch (e) { notify("sienna", (e as Error).message); } finally { setExporting(false); }
  };
  const [verifyRes, setVerifyRes] = React.useState<api.VerifyResult | null>(null);
  const doVerify = async (file?: File) => {
    if (!file) return;
    setVerifyRes(null);
    try { setVerifyRes(await api.verifyAuditExport(file)); }
    catch (e) { notify("sienna", (e as Error).message); }
  };
  const [scimTok, setScimTok] = React.useState<string>("");
  const doMintScim = async () => {
    try { const r = await api.mintScimToken(); setScimTok(r.token); notify("green", "SCIM token minted — copy it now, shown once."); }
    catch (e) { notify("sienna", (e as Error).message); }
  };
  const sshBridges = bridges.filter((b) => (b.capabilities || []).includes("ssh"));
  const [tBridgeId, setTBridgeId] = React.useState("");
  const [tHosts, setTHosts] = React.useState<api.ConnectorRow[]>([]);
  const [tHost, setTHost] = React.useState("");
  const [tLog, setTLog] = React.useState<{ cmd: string; out: string; code: number | null; analysis?: string }[]>([]);
  const [tExplaining, setTExplaining] = React.useState(-1);
  const [tCmd, setTCmd] = React.useState("");
  const [tBusy, setTBusy] = React.useState(false);
  const tBridge = sshBridges.find((b) => b.id === tBridgeId) || sshBridges.find((b) => b.status === "online") || sshBridges[0] || null;
  React.useEffect(() => {
    if (panel === "terminal" && tBridge && room) {
      api.terminalHosts(room.task.work_unit_id, tBridge.id)
        .then((r) => { setTHosts(r.hosts); if (r.hosts[0] && !tHost) setTHost(r.hosts[0].id); })
        .catch((e) => notify("sienna", (e as Error).message));
    }
  }, [panel, tBridge, room]);
  const [tHist, setTHist] = React.useState<string[]>([]);
  const [tHistIdx, setTHistIdx] = React.useState(-1);
  const execOne = async (cmd: string) => {
    if (!room || !tBridge || !tHost) return;
    try {
      const r = await api.terminalExec(room.task.work_unit_id, tBridge.id, tHost, cmd);
      setTLog((l) => [...l, { cmd, out: r.output, code: r.exit_code }]);
    } catch (e) { setTLog((l) => [...l, { cmd, out: (e as Error).message, code: -1 }]); }
  };
  const runCmd = async () => {
    if (!tCmd.trim() || !tBridge || !tHost) return;
    const cmd = tCmd.trim();
    setTBusy(true);
    await execOne(cmd);
    setTHist((h) => [...h.filter((c) => c !== cmd), cmd].slice(-50));
    setTHistIdx(-1); setTCmd(""); setTBusy(false);
  };
  const runRunbook = async (label: string, cmds: string[]) => {
    if (!tBridge || !tHost) return;
    setTBusy(true);
    setTLog((l) => [...l, { cmd: `# runbook — ${label}`, out: "", code: 0 }]);
    for (const cmd of cmds) await execOne(cmd);
    setTBusy(false);
  };
  const [runbooks, setRunbooks] = React.useState<api.Runbook[]>([]);
  const [rbName, setRbName] = React.useState("");
  React.useEffect(() => {
    if (panel === "terminal" && room && canGovern) {
      Promise.resolve(api.listRunbooks(room.task.work_unit_id)).then((r) => setRunbooks(r || [])).catch(() => setRunbooks([]));
    }
  }, [panel, room, canGovern]);
  const saveRunbook = async () => {
    if (!room) return;
    if (!rbName.trim() || tHist.length === 0) { notify("sienna", "Name it, and run a few commands first — they become the runbook."); return; }
    try {
      await api.saveRunbook(room.task.work_unit_id, rbName.trim(), tHist);
      setRbName(""); setRunbooks(await api.listRunbooks(room.task.work_unit_id));
      notify("green", "Runbook saved ✓");
    } catch (e) { notify("sienna", (e as Error).message); }
  };
  const delRunbook = async (id: string) => {
    if (!room) return;
    try { await api.deleteRunbook(room.task.work_unit_id, id); setRunbooks((rb) => rb.filter((x) => x.id !== id)); }
    catch (e) { notify("sienna", (e as Error).message); }
  };
  const explainEntry = async (i: number) => {
    if (!room) return;
    const e = tLog[i];
    if (!e || !e.out) return;
    setTExplaining(i);
    try {
      const r = await api.terminalExplain(room.task.work_unit_id, tHost, e.cmd, e.out);
      setTLog((l) => l.map((x, j) => (j === i ? { ...x, analysis: r.analysis } : x)));
    } catch (err) { notify("sienna", (err as Error).message); } finally { setTExplaining(-1); }
  };
  const termKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") { void runCmd(); return; }
    if (e.key === "ArrowUp" && tHist.length) {
      e.preventDefault();
      const i = tHistIdx < 0 ? tHist.length - 1 : Math.max(0, tHistIdx - 1);
      setTHistIdx(i); setTCmd(tHist[i]);
    } else if (e.key === "ArrowDown" && tHistIdx >= 0) {
      e.preventDefault();
      const i = tHistIdx + 1;
      if (i >= tHist.length) { setTHistIdx(-1); setTCmd(""); } else { setTHistIdx(i); setTCmd(tHist[i]); }
    }
  };

  // No-code custom REST connector builder (cloud-direct or via bridge).
  const emptyCf = { name: "", base_url: "", list_path: "", list_result_path: "", primary: "", secondary: "", open_path: "", auth_header: "" };
  const [cf, setCf] = React.useState(emptyCf);
  const [cfTest, setCfTest] = React.useState<api.CustomTestResult | null>(null);
  const specFromForm = (viaBridge: boolean): api.CustomSpec => ({
    name: cf.name || "Custom API", base_url: cf.base_url.trim(), list_path: cf.list_path.trim(),
    list_result_path: cf.list_result_path.trim(), open_path: cf.open_path.trim(),
    map: { id: "id", primary: cf.primary.trim() || "id", secondary: cf.secondary.trim() },
    ...(viaBridge ? {} : { auth_header: cf.auth_header.trim() }),
  });
  const testCustom = async (viaBridge: boolean) => {
    if (!room) return;
    if (!cf.base_url.trim() || !cf.list_path.trim()) { notify("sienna", "Base URL and list path are required."); return; }
    setCfTest(null);
    try { setCfTest(await api.testCustomSpec(room.task.work_unit_id, specFromForm(viaBridge), viaBridge ? bridge?.id : undefined)); }
    catch (e) { setCfTest({ ok: false, error: (e as Error).message }); }
  };
  const buildCustom = async (viaBridge: boolean) => {
    if (!room) return;
    if (!cf.base_url.trim() || !cf.list_path.trim()) { notify("sienna", "Base URL and list path are required."); return; }
    if (viaBridge && (!bridge || bridge.status !== "online")) { notify("sienna", "No bridge online to route through."); return; }
    const spec: api.CustomSpec = specFromForm(viaBridge);
    try {
      await api.connectTool(room.task.work_unit_id, "custom", cf.name || "Custom API", viaBridge ? bridge!.id : undefined, spec);
      notify("green", `Custom connector connected ✓ (${viaBridge ? "via bridge" : "cloud"}) — under Your Tools.`);
      setCf(emptyCf); setCfTest(null); props.onRefresh();
    } catch (e) { notify("sienna", (e as Error).message); }
  };

  const connectedTools = room ? room.toolkit.filter((t) => t.status === "connected").length : 0;

  return (
    <div data-testid="voundry-workspace-room">
      <CkKeyframes />
      {/* Full-bleed: break out of the app's 1040px column to use the whole page. */}
      <div style={{
        position: "relative", width: "100vw", left: "50%", transform: "translateX(-50%)",
        background: `radial-gradient(1500px 520px at 50% -12%, ${CK.shell}, ${CK.space})`,
        borderTop: `1px solid ${CK.line}`, borderBottom: `1px solid ${CK.line}`,
        boxShadow: `inset 0 0 90px ${CK.space}`, padding: "18px clamp(16px, 3.5vw, 60px)", boxSizing: "border-box",
      }}>
        <div style={{ marginBottom: 12, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <CkButton data-testid="ws-room-back" onClick={props.onBack}>← ALL DESKS</CkButton>
          {room && (
            <>
              <div style={{ position: "relative", flex: "1 1 260px", display: "flex", alignItems: "center" }}>
                <span style={{ position: "absolute", left: 10, color: accent, fontSize: 13, textShadow: `0 0 8px ${accent}` }}>⌖</span>
                <input
                  data-testid="ws-intent-input"
                  placeholder="STATE YOUR OBJECTIVE — the console routes it   ·   ⌘K"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      const v = (e.target as HTMLInputElement).value.trim();
                      if (v) { routeIntent(v); (e.target as HTMLInputElement).value = ""; }
                    }
                  }}
                  style={{
                    flex: 1, fontFamily: MONO, fontSize: 12, color: CK.ink, background: CK.shell,
                    border: `1px solid ${accent}`, borderLeft: `3px solid ${accent}`,
                    padding: "8px 10px 8px 30px", outline: "none", boxSizing: "border-box",
                    boxShadow: `inset 0 0 22px ${accent}1c`,
                  }}
                />
              </div>
              <CkButton tone="cyan" data-testid="ws-palette-open" onClick={() => setPaletteOpen(true)}>⌘K</CkButton>
            </>
          )}
        </div>

        <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)}
          commands={commands} onIntent={routeIntent} accent={accent} />

        {props.loading || !room ? (
          <CkPanel title="Workstation" plate="LINK">
            <div style={{ padding: 14, fontFamily: MONO, fontSize: 11, color: CK.inkSoft }}>— booting console —</div>
          </CkPanel>
        ) : (
          <>
          {/* HUD strip — the workstation's identity + live systems readout */}
          <div data-testid="ws-room-header" className="ck-scanline" style={{
            position: "relative", overflow: "hidden", marginBottom: 14,
            border: `1px solid ${accent}`, borderLeft: `4px solid ${accent}`,
            background: `linear-gradient(180deg, ${accent}22, ${CK.panel})`,
            boxShadow: `0 0 34px ${accent}22, inset 0 0 50px ${CK.space}`,
            display: "flex", gap: 14, alignItems: "center", padding: "13px 16px", flexWrap: "wrap",
          }}>
            <span style={{
              width: 54, height: 54, display: "flex", alignItems: "center", justifyContent: "center",
              background: CK.space, border: `1.5px solid ${accent}`, color: accent, fontSize: 27, borderRadius: "50%",
              boxShadow: `0 0 20px ${accent}55, inset 0 0 14px ${accent}33`,
            }}>{disciplineGlyph(room.role.discipline)}</span>
            <div style={{ flex: 1, minWidth: 220 }}>
              <div style={{ fontFamily: MONO, fontSize: 8.5, color: CK.inkDim, letterSpacing: "0.22em" }}>
                WACE · WORKSTATION ONLINE
              </div>
              <div style={{ fontFamily: MONO, fontSize: 18, fontWeight: 800, letterSpacing: "0.06em",
                textTransform: "capitalize", color: accent, textShadow: `0 0 14px ${accent}66` }}>
                {room.role.discipline} · {room.role.vertical}
              </div>
              <div style={{ fontFamily: MONO, fontSize: 10.5, color: CK.inkSoft, marginTop: 2 }}>{room.role.headline}</div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, alignItems: "flex-end" }}>
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap", justifyContent: "flex-end" }}>
                <CkStat label="Venture" value={room.venture.name} color={CK.ink} led={CK.green} />
                <CkStat label="Agents" value={room.agents.length} color={accent} />
                <CkStat label="Tools" value={`${connectedTools}/${room.toolkit.length}`} color={CK.cyan} />
                <CkStat label="Links" value={room.connected_tools.length} color={CK.cyan} />
                <CkStat label="Runs" value={room.agent_runs.length} color={accent} />
                <CkStat label="Files" value={room.files.length} color={CK.green} />
                {room.write_requests.length > 0 && (
                  <CkStat label="Write-backs"
                    value={`${room.write_requests.filter((w) => w.status === "executed").length}/${room.write_requests.length}`}
                    color={CK.amber}
                    led={room.write_requests.some((w) => w.status === "pending") ? CK.amber : CK.green} />
                )}
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <CkLed color={CK.green} size={7} />
                <span style={{ fontFamily: MONO, fontSize: 8.5, color: CK.green, letterSpacing: "0.14em" }}>
                  GOVERNANCE ACTIVE · SAIb · WORM · KILL-SWITCH
                </span>
              </div>
            </div>
          </div>

          {/* View mode — on its OWN line so the smart / cockpit / classic switch
              reads as a distinct control, not just another tool tab. */}
          <div data-testid="ws-view-row" style={{
            display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 8,
            padding: "7px 14px", background: CK.space, border: `1px solid ${CK.line}`, borderLeft: `3px solid ${CK.cyan}`,
          }}>
            <span style={{ fontFamily: MONO, fontSize: 9, color: CK.inkSoft, letterSpacing: "0.18em" }}>VIEW</span>
            <CkTab active={viewMode === "smart"} hue={CK.cyan} testid="ws-ctl-smart" onClick={() => setView("smart")}>⌁ Smart</CkTab>
            <CkTab active={viewMode === "cockpit"} hue={CK.cyan} testid="ws-ctl-cockpit" onClick={() => setView("cockpit")}>⊞ Cockpit</CkTab>
            <CkTab active={viewMode === "classic"} hue={CK.cyan} testid="ws-ctl-classic" onClick={() => setView("classic")}>≣ Classic</CkTab>
          </div>

          {/* Control bar — tools + panels. Catalogs + secondary info sit behind
              these toggles, so the desk stays clean. */}
          <div style={{
            display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 12,
            padding: "9px 14px", background: CK.panel, border: `1px solid ${CK.line}`, borderLeft: `3px solid ${accent}`,
          }}>
            <span style={{ color: accent, fontSize: 15 }}>◇</span>
            <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 800, color: CK.ink }}>{room.task.title}</span>
            <CkChip color={CK.green} label={`${room.task.estimated_credits_min}–${room.task.estimated_credits_max} cr`} />
            <span style={{ marginLeft: "auto", display: "flex", gap: 6, flexWrap: "wrap" }}>
              <CkTab active={panel === "connect"} hue={CK.cyan} testid="ws-ctl-connect" onClick={() => togglePanel("connect")}>＋ Connect Tool</CkTab>
              {room.agent_catalog.length > 0 && (
                <CkTab active={panel === "agent"} hue={accent} testid="ws-ctl-agent" onClick={() => togglePanel("agent")}>＋ Add Agent</CkTab>
              )}
              <CkTab active={panel === "instruments"} testid="ws-ctl-instruments" onClick={() => togglePanel("instruments")}>⚙ Instruments · {connectedTools}/{room.toolkit.length}</CkTab>
              {room.files.length > 0 && (
                <CkTab active={panel === "files"} testid="ws-ctl-files" onClick={() => togglePanel("files")}>▤ Files · {room.files.length}</CkTab>
              )}
              <CkTab active={panel === "resources"} testid="ws-ctl-resources" onClick={() => togglePanel("resources")}>✦ Playbook</CkTab>
              <CkTab active={panel === "comms"} testid="ws-ctl-comms" onClick={() => togglePanel("comms")}>✉ Comms{room.thread.length ? ` · ${room.thread.length}` : ""}</CkTab>
              <CkTab active={panel === "receipts"} testid="ws-ctl-receipts" onClick={() => togglePanel("receipts")}>▤ Receipts</CkTab>
              <CkTab active={panel === "replay"} testid="ws-ctl-replay" onClick={() => togglePanel("replay")}>⏮ Replay</CkTab>
              {canGovern && (
                <CkTab active={panel === "command"} hue={CK.cyan} testid="ws-ctl-command" onClick={() => togglePanel("command")}>⌘ Command Center</CkTab>
              )}
              <CkTab active={panel === "bridge"} hue={CK.amber} testid="ws-ctl-bridge" onClick={() => togglePanel("bridge")}>🔌 Bridges{bridges.length ? ` · ${bridges.filter((b) => b.status === "online").length}/${bridges.length}` : ""}</CkTab>
              {canGovern && sshBridges.length > 0 && (
                <CkTab active={panel === "terminal"} hue={CK.green} testid="ws-ctl-terminal" onClick={() => togglePanel("terminal")}>⌘ Terminal</CkTab>
              )}
            </span>
          </div>

          {/* Secondary panels — one at a time, right under the controls. */}
          {panel === "connect" && (
            <CkPanel title="Connect a Tool" plate="CATALOG" testid="ws-connectors" accent={CK.cyan}
              right={<CkStat label="Links" value={room.connected_tools.length} color={CK.cyan} led={room.connected_tools.length ? CK.green : CK.inkDim} />}>
              <div style={{ padding: "8px 12px 0", fontFamily: MONO, fontSize: 10, color: CK.inkSoft, lineHeight: 1.6 }}>
                Dock a tool and it appears as a live card under <b style={{ color: CK.ink }}>Your Tools</b>. Every uplink is
                read-only, SSRF-checked, SAIb-scrubbed and receipted.
              </div>
              <div style={{ padding: 12, display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: 10 }}>
                {room.connectors.map((c) => (
                  <div key={c.key} data-testid={`ws-connector-cat-${c.key}`} style={{
                    border: `1px solid ${CK.line}`, borderTop: `2px solid ${connectorHue(c.category)}`, padding: "10px",
                    background: `linear-gradient(180deg, ${connectorHue(c.category)}12, ${CK.shell})`,
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 4 }}>
                      <span style={{ color: connectorHue(c.category), fontSize: 14 }}>{connectorGlyph(c.category)}</span>
                      <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: CK.ink }}>{c.name}</span>
                    </div>
                    <div style={{ fontFamily: MONO, fontSize: 9.5, color: CK.inkSoft, lineHeight: 1.5, margin: "0 0 9px" }}>{c.description}</div>
                    <CkButton tone="cyan" data-testid={`ws-connect-${c.key}`} onClick={() => void connectTool(c.key)}>
                      {c.needs_auth ? `▸ CONNECT ${c.provider.toUpperCase()}` : "▸ DOCK"}
                    </CkButton>
                  </div>
                ))}
              </div>
            </CkPanel>
          )}

          {panel === "bridge" && (
            <CkPanel title="On-Prem Bridge" plate="PLUG-N-PLAY · NETWORK-LOCAL" testid="ws-bridge" accent={CK.amber}>
              <div style={{ padding: "8px 12px 0", fontFamily: MONO, fontSize: 10, color: CK.inkSoft, lineHeight: 1.6 }}>
                Reach systems that live <b style={{ color: CK.ink }}>inside your network</b> — Remedy, databases, internal
                APIs — without exposing them. Run a tiny agent on any machine there; it dials out to WACE (nothing
                inbound), and your credentials + data never leave your network.
              </div>
              <div style={{ padding: 12 }}>
                {bridges.length === 0 && (
                  <CkButton tone="amber" data-testid="ws-bridge-pair" onClick={() => void doPair()}>▸ PAIR A BRIDGE</CkButton>
                )}
                {bridges.length > 0 && (
                  <div style={{ marginBottom: 8 }}>
                    {bridges.map((b) => {
                      const on = b.status === "online"; const sel = bridge?.id === b.id;
                      return (
                        <div key={b.id} data-testid={`ws-bridge-row-${b.id}`} onClick={() => setSelId(b.id)} style={{
                          display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", padding: "6px 9px", marginBottom: 5,
                          border: `1px solid ${sel ? CK.cyan : CK.line}`, background: sel ? `${CK.cyan}12` : CK.space, cursor: "pointer" }}>
                          <CkLed color={on ? CK.green : CK.amber} size={7} />
                          <span style={{ fontFamily: MONO, fontSize: 11, color: CK.ink, fontWeight: 700 }}>{b.name}</span>
                          <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: "0.1em", textTransform: "uppercase", color: on ? CK.green : CK.amber }}>{b.status}</span>
                          {b.capabilities?.length ? <span style={{ fontFamily: MONO, fontSize: 8.5, color: CK.inkDim, flex: 1 }}>{b.capabilities.join(" · ")}</span> : <span style={{ flex: 1 }} />}
                          {b.summary && b.summary.total > 0 && <span style={{ fontFamily: MONO, fontSize: 8.5, color: CK.inkDim }}>{b.summary.done}✓{b.summary.failed ? ` ${b.summary.failed}✗` : ""}</span>}
                          <button type="button" data-testid={`ws-bridge-revoke-${b.id}`} onClick={(e) => { e.stopPropagation(); void revokeBridge(b.id); }}
                            style={{ background: "none", border: `1px solid ${CK.red}`, color: CK.red, cursor: "pointer", fontFamily: MONO, fontSize: 9, padding: "0 7px" }}>revoke</button>
                        </div>
                      );
                    })}
                    <div style={{ display: "flex", gap: 8 }}>
                      <CkButton tone="amber" data-testid="ws-bridge-pair" onClick={() => void doPair()}>＋ PAIR ANOTHER</CkButton>
                      <button type="button" data-testid="ws-bridge-refresh" onClick={() => void loadBridge()}
                        style={{ background: "none", border: `1px solid ${CK.line}`, color: CK.inkSoft, cursor: "pointer", fontFamily: MONO, fontSize: 10, padding: "0 9px" }}>↻</button>
                    </div>
                  </div>
                )}
                {bridge && bridge.status !== "none" && activity && activity.summary.total > 0 && (
                  <div data-testid="ws-bridge-activity" style={{ marginTop: 6, border: `1px solid ${CK.line}`, background: CK.space, padding: "8px 11px" }}>
                    <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontFamily: MONO, fontSize: 9.5, marginBottom: 6 }}>
                      <span style={{ color: CK.inkSoft, letterSpacing: "0.1em" }}>ACTIVITY</span>
                      <span style={{ color: CK.green }}>{activity.summary.done} done</span>
                      {activity.summary.failed > 0 && <span style={{ color: CK.red }}>{activity.summary.failed} failed</span>}
                      {(activity.summary.running + activity.summary.pending) > 0 && <span style={{ color: CK.amber }}>{activity.summary.running + activity.summary.pending} in-flight</span>}
                    </div>
                    {activity.jobs.slice(0, 5).map((j) => {
                      const c = j.status === "done" ? CK.green : j.status === "failed" ? CK.red : CK.amber;
                      return (
                        <div key={j.id} style={{ display: "flex", alignItems: "center", gap: 8, fontFamily: MONO, fontSize: 9.5, padding: "2px 0", color: CK.inkSoft }}>
                          <CkLed color={c} size={5} />
                          <span style={{ flex: 1 }}>{j.connector_key}:{j.action}</span>
                          <span style={{ color: CK.inkDim }}>{j.latency_s != null ? `${j.latency_s}s` : j.status}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
                {pairing && (
                  <div data-testid="ws-bridge-cmd" style={{ marginTop: 8, border: `1px solid ${CK.line}`, background: CK.space, padding: "10px 12px" }}>
                    <div style={{ fontFamily: MONO, fontSize: 8.5, color: CK.amber, letterSpacing: "0.1em", marginBottom: 6 }}>
                      QUICK PAIR — RUN ON A MACHINE INSIDE YOUR NETWORK (code valid 30 min)
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                      <span style={{ fontFamily: MONO, fontSize: 9, color: CK.inkDim }}>pairing code</span>
                      <span data-testid="ws-bridge-code" style={{ fontFamily: MONO, fontSize: 15, fontWeight: 800, color: CK.cyan, letterSpacing: "0.14em" }}>{pairing.pairing_code}</span>
                      <button type="button" onClick={() => { void navigator.clipboard?.writeText(pairing.pairing_code); notify("green", "Code copied"); }}
                        style={{ background: "none", border: `1px solid ${CK.line}`, color: CK.cyan, cursor: "pointer", fontFamily: MONO, fontSize: 9, padding: "1px 7px" }}>⧉</button>
                    </div>
                    <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-all", fontFamily: MONO, fontSize: 10, color: CK.inkSoft }}>{`docker run --rm -e WACE_URL=${window.location.origin} -e WACE_PAIR_CODE=${pairing.pairing_code} \\
  -e SERVICENOW_INSTANCE_URL=... -e SERVICENOW_USER=... -e SERVICENOW_PASSWORD=... \\
  wace-bridge`}</pre>
                    <div style={{ fontFamily: MONO, fontSize: 8.5, color: CK.inkDim, margin: "6px 0" }}>Durable install (survives restarts) — use the token + docker compose instead:</div>
                    <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-all", fontFamily: MONO, fontSize: 9.5, color: CK.inkDim }}>{pairing.run_command}</pre>
                    <button type="button" onClick={() => { void navigator.clipboard?.writeText(pairing.run_command); notify("green", "Command copied"); }}
                      style={{ marginTop: 7, background: "none", border: `1px solid ${CK.line}`, color: CK.cyan, cursor: "pointer", fontFamily: MONO, fontSize: 10, padding: "2px 9px" }}>⧉ Copy</button>
                    <div style={{ fontFamily: MONO, fontSize: 8.5, color: CK.inkDim, marginTop: 6 }}>The agent is <b>deploy/wace-bridge/bridge.py</b>. Once it checks in, this desk shows it <b style={{ color: CK.green }}>online</b>.</div>
                  </div>
                )}
                {bridge && bridge.status === "online" && bridge.capabilities?.length > 0 && (
                  <div style={{ marginTop: 12 }}>
                    <div style={{ fontFamily: MONO, fontSize: 9, color: CK.inkSoft, marginBottom: 6, letterSpacing: "0.1em" }}>CONNECT VIA YOUR BRIDGE</div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      {bridge.capabilities.filter((c) => c !== "custom").map((cap) => (
                        <CkButton key={cap} tone="cyan" data-testid={`ws-bridge-connect-${cap}`} onClick={() => void connectViaBridge(cap)}>▸ {cap}</CkButton>
                      ))}
                    </div>
                  </div>
                )}

                {/* No-code custom connector builder — wire ANY REST API, cloud or via bridge */}
                <div data-testid="ws-bridge-custom" style={{ marginTop: 14, borderTop: `1px solid ${CK.lineSoft}`, paddingTop: 10 }}>
                    <div style={{ fontFamily: MONO, fontSize: 9, color: CK.cyan, marginBottom: 2, letterSpacing: "0.1em" }}>BUILD A CUSTOM CONNECTOR — NO CODE</div>
                    <div style={{ fontFamily: MONO, fontSize: 8.5, color: CK.inkDim, marginBottom: 8 }}>
                      Point at any REST API. <b>Cloud</b>: external SaaS, token stays in WACE. <b>Via bridge</b>: internal systems, auth stays on the agent.
                    </div>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
                      <span style={{ fontFamily: MONO, fontSize: 8.5, color: CK.inkDim }}>start from:</span>
                      {CUSTOM_TEMPLATES.map((t) => (
                        <button key={t.label} type="button" data-testid={`ws-custom-tmpl-${t.label.split(" ")[0]}`}
                          onClick={() => setCf({ ...emptyCf, ...t.spec })}
                          style={{ background: "none", border: `1px solid ${CK.line}`, color: CK.cyan, cursor: "pointer", fontFamily: MONO, fontSize: 9, padding: "2px 8px" }}>{t.label}</button>
                      ))}
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 6 }}>
                      {([["name", "Name (e.g. Jira)"], ["base_url", "Base URL (https://…)"], ["list_path", "List path (/rest/api/2/search)"],
                        ["list_result_path", "Array field (e.g. issues)"], ["primary", "Title field (e.g. key)"], ["secondary", "Subtitle field (fields.summary)"],
                        ["open_path", "Open path (/issue/{id}) — optional"], ["auth_header", "Auth header (cloud only: Authorization: Bearer …)"]] as const).map(([k, ph]) => (
                        <CkInput key={k} data-testid={`ws-custom-${k}`} placeholder={ph}
                          value={(cf as Record<string, string>)[k]} onChange={(e) => setCf({ ...cf, [k]: e.target.value })} />
                      ))}
                    </div>
                    <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                      <CkButton tone="ghost" data-testid="ws-custom-test" onClick={() => void testCustom(!!(bridge && bridge.status === "online"))}>◇ TEST</CkButton>
                      <CkButton tone="cyan" data-testid="ws-custom-build-cloud" onClick={() => void buildCustom(false)}>▸ CONNECT (CLOUD)</CkButton>
                      {bridge && bridge.status === "online" && (
                        <CkButton tone="amber" data-testid="ws-custom-build-bridge" onClick={() => void buildCustom(true)}>▸ CONNECT VIA BRIDGE</CkButton>
                      )}
                    </div>
                    {cfTest && (
                      <div data-testid="ws-custom-test-result" style={{ marginTop: 8, border: `1px solid ${cfTest.ok ? CK.line : CK.red}`, background: CK.space, padding: "8px 11px" }}>
                        {cfTest.ok ? (
                          <>
                            <div style={{ fontFamily: MONO, fontSize: 9, color: CK.green, marginBottom: 5 }}>✓ {cfTest.count} record(s) — preview:</div>
                            {(cfTest.rows || []).map((r, i) => (
                              <div key={i} style={{ fontFamily: MONO, fontSize: 10, color: CK.ink }}>
                                <b>{r.primary}</b>{r.secondary ? <span style={{ color: CK.inkSoft }}> — {r.secondary}</span> : null}
                              </div>
                            ))}
                            {(cfTest.rows || []).length === 0 && <div style={{ fontFamily: MONO, fontSize: 9.5, color: CK.inkSoft }}>Reached it, but no rows mapped — check the array field &amp; title field.</div>}
                          </>
                        ) : (
                          <div style={{ fontFamily: MONO, fontSize: 9.5, color: CK.red }}>✗ {cfTest.error}</div>
                        )}
                      </div>
                    )}
                  </div>
              </div>
            </CkPanel>
          )}

          {panel === "receipts" && (
            <CkPanel title="Receipts" plate="WORM · EVERY ACTION ON THE RECORD" testid="ws-receipts" accent={accent}>
              <div style={{ padding: "8px 12px 0", fontFamily: MONO, fontSize: 10, color: CK.inkSoft, lineHeight: 1.6 }}>
                Every connect, read, agent run, approval, terminal command and send {rcpScope === "all" ? "across all desks" : "on this desk"} — append-only and receipted.
              </div>
              {canGovern && (
                <div style={{ padding: "6px 12px 0", display: "flex", gap: 6 }}>
                  {(["desk", "all"] as const).map((s) => (
                    <button key={s} type="button" data-testid={`ws-receipts-scope-${s}`} onClick={() => setRcpScope(s)}
                      style={{ background: rcpScope === s ? `${CK.cyan}18` : "none", border: `1px solid ${rcpScope === s ? CK.cyan : CK.line}`, color: rcpScope === s ? CK.cyan : CK.inkSoft, cursor: "pointer", fontFamily: MONO, fontSize: 9, padding: "2px 9px" }}>{s === "desk" ? "this desk" : "all desks"}</button>
                  ))}
                </div>
              )}
              <div style={{ padding: 12, maxHeight: 340, overflowY: "auto" }}>
                {receipts.length === 0 && <div style={{ fontFamily: MONO, fontSize: 10, color: CK.inkDim }}>No activity yet.</div>}
                {receipts.map((r, i) => {
                  const write = /write|send|set_status|set_state|executed/.test(r.action);
                  const c = r.action.includes("approved") || r.action.includes("executed") ? CK.green
                    : write || r.action.includes("requested") ? CK.amber
                    : r.action.includes("rejected") || r.action.includes("failed") ? CK.red : CK.cyan;
                  return (
                    <div key={i} data-testid="ws-receipt-row" style={{ display: "flex", gap: 9, alignItems: "baseline", padding: "4px 0", borderBottom: `1px solid ${CK.lineSoft}` }}>
                      <CkLed color={c} size={5} />
                      <span style={{ fontFamily: MONO, fontSize: 9, color: c, minWidth: 130 }}>{r.action}</span>
                      <span style={{ flex: 1, fontFamily: MONO, fontSize: 9.5, color: CK.inkSoft, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.detail}</span>
                      <span style={{ fontFamily: MONO, fontSize: 8, color: CK.inkDim, whiteSpace: "nowrap" }}>{(r.created_at || "").slice(0, 16).replace("T", " ")}</span>
                    </div>
                  );
                })}
              </div>
              <div style={{ padding: "0 12px 12px", display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <CkButton tone="cyan" disabled={shiftBusy} data-testid="ws-shift-report" onClick={() => void genShiftReport()}>{shiftBusy ? "…" : "✦ SHIFT REPORT"}</CkButton>
                {shiftRpt && <CkButton tone="green" data-testid="ws-shift-save" onClick={() => void saveShiftReport()}>SAVE TO FLIGHT RECORDER</CkButton>}
              </div>
              {shiftRpt && (
                <div data-testid="ws-shift-report-out" style={{ margin: "0 12px 12px", border: `1px solid ${CK.line}`, background: CK.space, padding: "10px 12px", fontFamily: MONO, fontSize: 10.5, color: CK.ink, whiteSpace: "pre-wrap", lineHeight: 1.55, maxHeight: 260, overflowY: "auto" }}>
                  <div style={{ fontSize: 8.5, color: CK.cyan, letterSpacing: "0.1em", marginBottom: 6 }}>{shiftRpt.agent_name.toUpperCase()} · SHIFT REPORT</div>
                  {shiftRpt.report}
                </div>
              )}
            </CkPanel>
          )}

          {panel === "replay" && (
            <CkPanel title="Session Replay" plate="TIME MACHINE · SCRUB THE RECEIPTED RECORD" testid="ws-replay" accent={accent}>
              <SessionReplay receipts={receipts} accent={accent} />
            </CkPanel>
          )}

          {panel === "command" && (
            <CkPanel title="Command Center" plate="ORG-WIDE · GOVERNED · RECEIPTED" testid="ws-command" accent={CK.cyan}>
              {!cc ? (
                <div style={{ padding: 14, fontFamily: MONO, fontSize: 10, color: CK.inkDim }}>Loading org telemetry…</div>
              ) : (
                <div style={{ padding: 12 }}>
                  {/* Value banner — the buyer's proof */}
                  <div data-testid="ws-cc-value" style={{ border: `1px solid ${CK.cyan}`, background: `${CK.cyan}12`, borderRadius: 10, padding: "12px 14px", marginBottom: 12 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.14em", color: CK.cyan }}>VALUE DELIVERED</div>
                      <CkButton tone="cyan" data-testid="ws-cc-export" disabled={exporting} onClick={() => void doExport()} style={{ marginLeft: "auto" }}>{exporting ? "…" : "⤓ SIGNED AUDIT EXPORT"}</CkButton>
                    </div>
                    <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "baseline", marginTop: 4 }}>
                      <div><span style={{ fontFamily: MONO, fontSize: 26, fontWeight: 800, color: CK.ink }}>{cc.value.hours_saved}</span> <span style={{ fontFamily: MONO, fontSize: 10, color: CK.inkSoft }}>hours saved</span></div>
                      <div><span style={{ fontFamily: MONO, fontSize: 20, fontWeight: 800, color: CK.ink }}>{cc.value.actions_automated}</span> <span style={{ fontFamily: MONO, fontSize: 10, color: CK.inkSoft }}>governed actions</span></div>
                    </div>
                    <div style={{ fontFamily: MONO, fontSize: 8, color: CK.inkDim, marginTop: 4 }}>{cc.value.note}</div>
                  </div>
                  {/* BYOK — the tenant's own LLM key */}
                  <ByokCard />
                  {/* Verify a bundle — reads the public verifier so anyone can confirm authenticity */}
                  <div data-testid="ws-cc-verify" style={{ border: `1px solid ${CK.line}`, borderRadius: 10, padding: "10px 12px", marginBottom: 12 }}>
                    <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.12em", color: CK.inkDim }}>VERIFY A BUNDLE</span>
                      <input type="file" accept=".zip" data-testid="ws-cc-verify-file"
                        onChange={(e) => void doVerify(e.target.files?.[0])}
                        style={{ fontFamily: MONO, fontSize: 9, color: CK.inkSoft }} />
                      {verifyRes && (
                        <span data-testid="ws-cc-verify-result" style={{ fontFamily: MONO, fontSize: 9.5, color: verifyRes.verified ? CK.green : CK.red }}>
                          {verifyRes.verified ? `✓ AUTHENTIC · ${verifyRes.org || ""} · ${(verifyRes.generated_at || "").slice(0, 10)} · key ${verifyRes.kid}` : `✗ ${verifyRes.error || "TAMPERED — digests or signature don't match"}`}
                        </span>
                      )}
                    </div>
                    <div style={{ fontFamily: MONO, fontSize: 8, color: CK.inkDim, marginTop: 4 }}>Drop any WACE audit export to confirm its Ed25519 signature — same check an auditor runs offline.</div>
                  </div>
                  {/* Metric tiles */}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(112px, 1fr))", gap: 8, marginBottom: 12 }}>
                    {([
                      ["Desks", cc.desks], ["Connections", cc.connections], ["Actions", cc.actions],
                      ["Writes", cc.writes], ["Agent runs", cc.agent_runs], ["Terminal", cc.terminal],
                      ["Approvals pending", cc.approvals_pending], ["Bridges", `${cc.bridges.online}/${cc.bridges.total}`],
                    ] as [string, number | string][]).map(([label, val]) => (
                      <div key={label} data-testid={`ws-cc-${label.toLowerCase().replace(/ /g, "-")}`} style={{ border: `1px solid ${CK.line}`, background: CK.shell, borderRadius: 9, padding: "9px 10px" }}>
                        <div style={{ fontFamily: MONO, fontSize: 18, fontWeight: 800, color: CK.ink }}>{val}</div>
                        <div style={{ fontFamily: MONO, fontSize: 7.5, letterSpacing: "0.08em", textTransform: "uppercase", color: CK.inkDim }}>{label}</div>
                      </div>
                    ))}
                  </div>
                  {/* Governance policy — the org control plane */}
                  <div data-testid="ws-cc-policy" style={{ border: `1px solid ${CK.amber}55`, borderRadius: 10, padding: "10px 12px", marginBottom: 12 }}>
                    <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.14em", color: CK.amber, marginBottom: 7 }}>GOVERNANCE POLICY · ORG-WIDE</div>
                    {([
                      ["require_approval_for_writes", "Require approval for every write", "Forces all sends/updates through a human governor — overrides direct actions."],
                      ["block_terminal", "Disable the server terminal", "Turns off governed SSH across the org."],
                    ] as [keyof api.OrgPolicy, string, string][]).map(([key, label, hint]) => {
                      const active = !!cc.policy[key];
                      return (
                        <div key={key} style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 7 }}>
                          <button type="button" data-testid={`ws-cc-policy-${key}`} onClick={() => void savePolicy({ [key]: !active } as Partial<api.OrgPolicy>)}
                            style={{ flexShrink: 0, width: 38, height: 20, borderRadius: 10, border: `1px solid ${active ? CK.green : CK.line}`, background: active ? `${CK.green}22` : CK.shell, cursor: "pointer", position: "relative" }}>
                            <span style={{ position: "absolute", top: 2, left: active ? 20 : 2, width: 14, height: 14, borderRadius: "50%", background: active ? CK.green : CK.inkDim, transition: "left .12s" }} />
                          </button>
                          <span style={{ minWidth: 0 }}>
                            <div style={{ fontFamily: MONO, fontSize: 9.5, color: CK.ink }}>{label} <span style={{ color: active ? CK.green : CK.inkDim }}>· {active ? "ON" : "OFF"}</span></div>
                            <div style={{ fontFamily: MONO, fontSize: 8, color: CK.inkDim, lineHeight: 1.4 }}>{hint}</div>
                          </span>
                        </div>
                      );
                    })}
                    {cc.policy.blocked_connectors.length > 0 && (
                      <div style={{ fontFamily: MONO, fontSize: 8, color: CK.inkSoft, marginTop: 2 }}>Blocked apps: {cc.policy.blocked_connectors.join(", ")}</div>
                    )}
                  </div>
                  {/* Enterprise provisioning (SCIM) */}
                  <div data-testid="ws-cc-scim" style={{ border: `1px solid ${CK.line}`, borderRadius: 10, padding: "10px 12px", marginBottom: 12 }}>
                    <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.12em", color: CK.inkDim }}>SCIM PROVISIONING</span>
                      <CkButton tone="cyan" data-testid="ws-cc-scim-mint" onClick={() => void doMintScim()}>⚿ ROTATE SCIM TOKEN</CkButton>
                      <span style={{ fontFamily: MONO, fontSize: 8, color: CK.inkDim }}>Endpoint: <b style={{ color: CK.inkSoft }}>/voundry/scim/v2/Users</b></span>
                    </div>
                    {scimTok && (
                      <div data-testid="ws-cc-scim-token" style={{ marginTop: 6, fontFamily: MONO, fontSize: 9, color: CK.green, wordBreak: "break-all", border: `1px solid ${CK.green}44`, background: `${CK.green}10`, padding: "6px 8px", borderRadius: 6 }}>{scimTok}<div style={{ color: CK.inkDim, fontSize: 7.5, marginTop: 2 }}>Copy now — shown once. Paste into your IdP's SCIM connector as the bearer token.</div></div>
                    )}
                    <div style={{ fontFamily: MONO, fontSize: 8, color: CK.inkDim, marginTop: 4 }}>Auto-provision & deprovision users from Okta / Entra / OneLogin — disabling a user in your IdP locks them out of WACE everywhere.</div>
                  </div>
                  {/* Single sign-on (OIDC) */}
                  {ssoCfg && (
                    <div data-testid="ws-cc-sso" style={{ border: `1px solid ${CK.line}`, borderRadius: 10, padding: "10px 12px", marginBottom: 12 }}>
                      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 7 }}>
                        <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.12em", color: CK.inkDim }}>SINGLE SIGN-ON · OIDC</span>
                        <button type="button" data-testid="ws-cc-sso-enabled" onClick={() => setSsoCfg((c) => c ? { ...c, enabled: !c.enabled } : c)}
                          style={{ width: 38, height: 20, borderRadius: 10, border: `1px solid ${ssoCfg.enabled ? CK.green : CK.line}`, background: ssoCfg.enabled ? `${CK.green}22` : CK.shell, cursor: "pointer", position: "relative" }}>
                          <span style={{ position: "absolute", top: 2, left: ssoCfg.enabled ? 20 : 2, width: 14, height: 14, borderRadius: "50%", background: ssoCfg.enabled ? CK.green : CK.inkDim }} />
                        </button>
                        <span style={{ fontFamily: MONO, fontSize: 9, color: ssoCfg.enabled ? CK.green : CK.inkDim }}>{ssoCfg.enabled ? "ON" : "OFF"}</span>
                        <CkButton tone="cyan" data-testid="ws-cc-sso-save" onClick={() => void saveSso()} style={{ marginLeft: "auto" }}>SAVE</CkButton>
                      </div>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                        {([
                          ["authorize_url", "Authorize URL"], ["token_url", "Token URL"], ["userinfo_url", "Userinfo URL"],
                          ["client_id", "Client ID"], ["client_secret", "Client secret"], ["redirect_uri", "Redirect URI"],
                          ["allowed_domain", "Allowed email domain"],
                        ] as [keyof api.SsoConfig, string][]).map(([k, label]) => (
                          <CkInput key={k} data-testid={`ws-cc-sso-${k}`} placeholder={label} value={String(ssoCfg[k] ?? "")}
                            onChange={(e) => setSsoCfg((c) => c ? { ...c, [k]: e.target.value } : c)} />
                        ))}
                      </div>
                      <div style={{ fontFamily: MONO, fontSize: 8, color: CK.inkDim, marginTop: 5 }}>Point your IdP redirect URI to <b style={{ color: CK.inkSoft }}>/voundry/sso/callback</b>. Users then sign in at <b style={{ color: CK.inkSoft }}>/voundry/sso/start</b> — provisioned + domain-gated + deprovisioning-aware.</div>
                    </div>
                  )}
                  {/* Single sign-on (SAML) */}
                  {samlCfg && (
                    <div data-testid="ws-cc-saml" style={{ border: `1px solid ${CK.line}`, borderRadius: 10, padding: "10px 12px", marginBottom: 12 }}>
                      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 7 }}>
                        <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.12em", color: CK.inkDim }}>SINGLE SIGN-ON · SAML 2.0</span>
                        <button type="button" data-testid="ws-cc-saml-enabled" onClick={() => setSamlCfg((c) => c ? { ...c, enabled: !c.enabled } : c)}
                          style={{ width: 38, height: 20, borderRadius: 10, border: `1px solid ${samlCfg.enabled ? CK.green : CK.line}`, background: samlCfg.enabled ? `${CK.green}22` : CK.shell, cursor: "pointer", position: "relative" }}>
                          <span style={{ position: "absolute", top: 2, left: samlCfg.enabled ? 20 : 2, width: 14, height: 14, borderRadius: "50%", background: samlCfg.enabled ? CK.green : CK.inkDim }} />
                        </button>
                        <span style={{ fontFamily: MONO, fontSize: 9, color: samlCfg.enabled ? CK.green : CK.inkDim }}>{samlCfg.enabled ? "ON" : "OFF"}</span>
                        <CkButton tone="cyan" data-testid="ws-cc-saml-save" onClick={() => void saveSaml()} style={{ marginLeft: "auto" }}>SAVE</CkButton>
                      </div>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                        {([
                          ["idp_sso_url", "IdP SSO URL"], ["idp_entity_id", "IdP entity ID"],
                          ["sp_entity_id", "SP entity ID"], ["acs_url", "ACS URL (…/voundry/saml/acs)"],
                          ["allowed_domain", "Allowed email domain"],
                        ] as [keyof api.SamlConfig, string][]).map(([k, label]) => (
                          <CkInput key={k} data-testid={`ws-cc-saml-${k}`} placeholder={label} value={String(samlCfg[k] ?? "")}
                            onChange={(e) => setSamlCfg((c) => c ? { ...c, [k]: e.target.value } : c)} />
                        ))}
                      </div>
                      <textarea data-testid="ws-cc-saml-cert" placeholder="IdP X.509 certificate (PEM or base64)" value={samlCfg.idp_cert}
                        onChange={(e) => setSamlCfg((c) => c ? { ...c, idp_cert: e.target.value } : c)}
                        style={{ width: "100%", minHeight: 54, marginTop: 6, background: CK.shell, border: `1px solid ${CK.line}`, color: CK.inkSoft, fontFamily: MONO, fontSize: 8, padding: 6, resize: "vertical" }} />
                      <div style={{ fontFamily: MONO, fontSize: 8, color: CK.inkDim, marginTop: 5 }}>Set your IdP ACS to <b style={{ color: CK.inkSoft }}>/voundry/saml/acs</b>; users start at <b style={{ color: CK.inkSoft }}>/voundry/saml/login</b>. Assertions are signature-verified, condition-checked, replay-guarded, domain-gated.</div>
                    </div>
                  )}
                  {/* User directory — governor sees + controls every account */}
                  {(() => {
                    const q = userQ.trim().toLowerCase();
                    const filtered = users.filter((u) =>
                      (userFilter === "all" || (userFilter === "disabled") === u.disabled)
                      && (!q || `${u.email} ${u.display_name}`.toLowerCase().includes(q)));
                    return (
                  <div data-testid="ws-cc-users" style={{ border: `1px solid ${CK.line}`, borderRadius: 10, padding: "10px 12px", marginBottom: 12 }}>
                    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
                      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.12em", color: CK.inkDim }}>USER DIRECTORY · {filtered.length}/{users.length}</span>
                      <CkInput data-testid="ws-cc-user-search" placeholder="search email/name…" value={userQ} onChange={(e) => setUserQ(e.target.value)} style={{ flex: "1 1 140px", maxWidth: 220 }} />
                      {(["all", "active", "disabled"] as const).map((s) => (
                        <button key={s} type="button" data-testid={`ws-cc-user-filter-${s}`} onClick={() => setUserFilter(s)}
                          style={{ background: userFilter === s ? `${CK.cyan}18` : "none", border: `1px solid ${userFilter === s ? CK.cyan : CK.line}`, color: userFilter === s ? CK.cyan : CK.inkSoft, cursor: "pointer", fontFamily: MONO, fontSize: 8.5, padding: "2px 8px" }}>{s}</button>
                      ))}
                      <button type="button" data-testid="ws-cc-user-select-stale" onClick={() => selectStale(filtered)}
                        style={{ background: "none", border: `1px solid ${CK.amber}66`, color: CK.amber, cursor: "pointer", fontFamily: MONO, fontSize: 8.5, padding: "2px 8px" }}>select inactive 30d+</button>
                      <button type="button" data-testid="ws-cc-user-csv" onClick={() => void doUsersCsv()}
                        style={{ background: "none", border: `1px solid ${CK.line}`, color: CK.inkSoft, cursor: "pointer", fontFamily: MONO, fontSize: 8.5, padding: "2px 8px" }}>⤓ CSV</button>
                    </div>
                    {selUsers.size > 0 && (
                      <div data-testid="ws-cc-user-bulkbar" style={{ display: "flex", gap: 8, alignItems: "center", padding: "5px 8px", marginBottom: 6, background: `${CK.cyan}12`, border: `1px solid ${CK.cyan}44`, borderRadius: 7 }}>
                        <span style={{ fontFamily: MONO, fontSize: 9, color: CK.cyan }}>{selUsers.size} selected</span>
                        <CkButton tone="red" data-testid="ws-cc-user-bulk-disable" onClick={() => void doBulkUsers(false)}>DISABLE</CkButton>
                        <CkButton tone="green" data-testid="ws-cc-user-bulk-enable" onClick={() => void doBulkUsers(true)}>ENABLE</CkButton>
                        <button type="button" data-testid="ws-cc-user-bulk-clear" onClick={() => setSelUsers(new Set())} style={{ marginLeft: "auto", background: "none", border: `1px solid ${CK.line}`, color: CK.inkSoft, cursor: "pointer", fontFamily: MONO, fontSize: 8.5, padding: "2px 8px" }}>clear</button>
                      </div>
                    )}
                    <div style={{ maxHeight: 200, overflowY: "auto" }}>
                      {filtered.length === 0 && <div style={{ fontFamily: MONO, fontSize: 8.5, color: CK.inkDim }}>{users.length === 0 ? "No accounts yet." : "No matches."}</div>}
                      {filtered.map((u) => (
                        <div key={u.account_id} data-testid={`ws-cc-user-${u.account_id}`} style={{ display: "flex", gap: 8, alignItems: "center", padding: "3px 0", borderBottom: `1px solid ${CK.lineSoft}` }}>
                          <input type="checkbox" data-testid={`ws-cc-user-sel-${u.account_id}`} checked={selUsers.has(u.account_id)} onChange={() => toggleSel(u.account_id)} style={{ cursor: "pointer", flexShrink: 0 }} />
                          <span style={{ width: 7, height: 7, borderRadius: "50%", background: u.disabled ? CK.red : CK.green, flexShrink: 0 }} />
                          <span style={{ fontFamily: MONO, fontSize: 9.5, color: CK.ink, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{u.email}</span>
                          <span style={{ fontFamily: MONO, fontSize: 8, color: CK.inkDim, whiteSpace: "nowrap" }}>{u.role}{u.scim_provisioned ? " · scim" : ""}{u.disabled ? " · disabled" : ""} · seen {u.last_seen ? (u.last_seen).slice(0, 10) : "never"}</span>
                          <button type="button" data-testid={`ws-cc-user-toggle-${u.account_id}`} onClick={() => void toggleUser(u)}
                            style={{ marginLeft: "auto", background: "none", border: `1px solid ${CK.line}`, color: u.disabled ? CK.green : CK.red, cursor: "pointer", fontFamily: MONO, fontSize: 9, padding: "1px 8px" }}>{u.disabled ? "enable" : "disable"}</button>
                        </div>
                      ))}
                    </div>
                    <div style={{ fontFamily: MONO, fontSize: 8, color: CK.inkDim, marginTop: 4 }}>Disabling locks the user out everywhere instantly — pairs with SCIM/SSO deprovisioning.</div>
                  </div>
                    );
                  })()}
                  {/* Access groups — from the IdP via SCIM; which ones confer governor */}
                  {groups.length > 0 && (
                    <div data-testid="ws-cc-groups" style={{ border: `1px solid ${CK.line}`, borderRadius: 10, padding: "10px 12px", marginBottom: 12 }}>
                      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
                        <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.12em", color: CK.inkDim }}>ACCESS GROUPS · {groups.length} <span style={{ color: CK.inkDim }}>(from your IdP)</span></span>
                        <span style={{ marginLeft: "auto", fontFamily: MONO, fontSize: 8, color: CK.inkDim }}>governor group name contains:</span>
                        <CkInput data-testid="ws-cc-govgroup" placeholder="govern" value={govToken} onChange={(e) => setGovToken(e.target.value)} style={{ width: 110 }} />
                        <CkButton tone="cyan" data-testid="ws-cc-govgroup-save" onClick={() => void saveGovToken()}>SET</CkButton>
                      </div>
                      {groups.map((g) => (
                        <div key={g.id} data-testid={`ws-cc-group-${g.id}`} style={{ display: "flex", gap: 8, alignItems: "center", padding: "3px 0", borderBottom: `1px solid ${CK.lineSoft}` }}>
                          <span style={{ fontFamily: MONO, fontSize: 9.5, color: CK.ink }}>{g.displayName}</span>
                          {g.is_governor && <span style={{ fontFamily: MONO, fontSize: 7.5, color: CK.amber, border: `1px solid ${CK.amber}66`, borderRadius: 5, padding: "0 5px" }}>GOVERNOR</span>}
                          <span style={{ marginLeft: "auto", fontFamily: MONO, fontSize: 8.5, color: CK.inkDim }}>{g.member_count} member{g.member_count === 1 ? "" : "s"}</span>
                        </div>
                      ))}
                      <div style={{ fontFamily: MONO, fontSize: 8, color: CK.inkDim, marginTop: 4 }}>Members of a group named “…governor…” may approve governed writes — managed in your IdP.</div>
                    </div>
                  )}
                  {/* Organization tools — an admin adds a tool once, the whole org gets it */}
                  <div data-testid="ws-cc-orgtools" style={{ border: `1px solid ${CK.line}`, borderRadius: 10, padding: "10px 12px", marginBottom: 12 }}>
                    <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 6 }}>
                      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.12em", color: CK.inkDim }}>ORGANIZATION TOOLS</span>
                      <CkButton tone="cyan" data-testid="ws-cc-orgtool-add" onClick={() => setOrgAddOpen((o) => !o)} style={{ marginLeft: "auto" }}>＋ ADD FOR ORG</CkButton>
                    </div>
                    {orgTools.length === 0 && !orgAddOpen && <div style={{ fontFamily: MONO, fontSize: 8.5, color: CK.inkDim }}>None yet — add a tool once and it appears on every desk in your org.</div>}
                    {orgTools.map((t) => (
                      <div key={t.key} style={{ display: "flex", gap: 8, alignItems: "center", padding: "3px 0", borderBottom: `1px solid ${CK.lineSoft}` }}>
                        <span style={{ fontFamily: MONO, fontSize: 9.5, color: CK.ink }}>{t.name}</span>
                        <span style={{ fontFamily: MONO, fontSize: 8, color: CK.inkDim, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.base_url}</span>
                        <button type="button" data-testid={`ws-cc-orgtool-rm-${t.key}`} onClick={() => void removeOrgToolFn(t.key)}
                          style={{ marginLeft: "auto", background: "none", border: `1px solid ${CK.line}`, color: CK.red, cursor: "pointer", fontFamily: MONO, fontSize: 9, padding: "1px 7px" }}>remove</button>
                      </div>
                    ))}
                    {orgAddOpen && <div style={{ marginTop: 8 }}><AddToolPanel workUnitId={room.task.work_unit_id} onAdd={(s) => void addOrgToolFn(s)} onClose={() => setOrgAddOpen(false)} /></div>}
                  </div>
                  {/* Coverage by category + usage */}
                  {(Object.keys(cc.by_category).length > 0 || (cc.top_apps || []).length > 0) && (
                    <div style={{ marginBottom: 12, display: "flex", gap: 18, flexWrap: "wrap" }}>
                      {Object.keys(cc.by_category).length > 0 && (
                        <div>
                          <div style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: "0.12em", color: CK.inkDim, marginBottom: 5 }}>CONNECTIONS BY TYPE</div>
                          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                            {Object.entries(cc.by_category).map(([k, n]) => (
                              <span key={k} style={{ fontFamily: MONO, fontSize: 9, color: CK.inkSoft, border: `1px solid ${CK.line}`, borderRadius: 6, padding: "2px 8px" }}>{CATEGORY_LABEL[k] || k} · {n}</span>
                            ))}
                          </div>
                        </div>
                      )}
                      {(cc.top_apps || []).length > 0 && (
                        <div data-testid="ws-cc-topapps">
                          <div style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: "0.12em", color: CK.inkDim, marginBottom: 5 }}>TOP APPS BY USAGE</div>
                          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                            {cc.top_apps.map((a) => (
                              <span key={a.key} style={{ fontFamily: MONO, fontSize: 9, color: CK.cyan, border: `1px solid ${CK.cyan}44`, borderRadius: 6, padding: "2px 8px" }}>{a.key} · {a.count}</span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                  {/* Recent org-wide activity */}
                  <div style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: "0.12em", color: CK.inkDim, marginBottom: 5 }}>RECENT ACTIVITY (ORG-WIDE)</div>
                  <div style={{ maxHeight: 240, overflowY: "auto", border: `1px solid ${CK.line}` }}>
                    {cc.recent.length === 0 && <div style={{ fontFamily: MONO, fontSize: 9.5, color: CK.inkDim, padding: 10 }}>No activity yet.</div>}
                    {cc.recent.map((r, i) => (
                      <div key={i} style={{ display: "flex", gap: 9, alignItems: "baseline", padding: "4px 10px", borderBottom: `1px solid ${CK.lineSoft}` }}>
                        <span style={{ fontFamily: MONO, fontSize: 8.5, color: CK.cyan, minWidth: 130 }}>{r.action}</span>
                        <span style={{ flex: 1, fontFamily: MONO, fontSize: 9, color: CK.inkSoft, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.detail}</span>
                        <span style={{ fontFamily: MONO, fontSize: 8, color: CK.inkDim, whiteSpace: "nowrap" }}>{(r.created_at || "").slice(0, 16).replace("T", " ")}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CkPanel>
          )}

          {panel === "terminal" && (
            <CkPanel title="Server Terminal" plate="GOVERNED SSH · VIA BRIDGE" testid="ws-terminal" accent={CK.green}>
              <div style={{ padding: "8px 12px 0", fontFamily: MONO, fontSize: 10, color: CK.inkSoft, lineHeight: 1.6 }}>
                Run commands on your UNIX/Linux servers through the bridge. <b style={{ color: CK.ink }}>Read-only by default</b>,
                catastrophic commands blocked, every command receipted. Set <b>SSH_MODE=full</b> on the bridge for unrestricted shells.
              </div>
              <div style={{ padding: 12 }}>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
                  {sshBridges.length > 1 && (
                    <select data-testid="ws-terminal-bridge" value={tBridge?.id || ""} onChange={(e) => { setTBridgeId(e.target.value); setTHost(""); }}
                      style={{ background: CK.space, color: CK.ink, border: `1px solid ${CK.line}`, fontFamily: MONO, fontSize: 10, padding: "3px 6px" }}>
                      {sshBridges.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                    </select>
                  )}
                  <select data-testid="ws-terminal-host" value={tHost} onChange={(e) => setTHost(e.target.value)}
                    style={{ background: CK.space, color: CK.ink, border: `1px solid ${CK.line}`, fontFamily: MONO, fontSize: 10, padding: "3px 6px" }}>
                    {tHosts.length === 0 && <option value="">no hosts</option>}
                    {tHosts.map((h) => <option key={h.id} value={h.id}>{h.primary} ({h.secondary})</option>)}
                  </select>
                  {tHosts.find((h) => h.id === tHost)?.meta && (
                    <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: "0.1em", textTransform: "uppercase",
                      color: tHosts.find((h) => h.id === tHost)?.meta === "full" ? CK.amber : CK.green }}>{tHosts.find((h) => h.id === tHost)?.meta}</span>
                  )}
                </div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
                  <span style={{ fontFamily: MONO, fontSize: 8.5, color: CK.inkDim }}>runbooks:</span>
                  {RUNBOOKS.map((rb) => (
                    <button key={rb.label} type="button" data-testid={`ws-terminal-rb-${rb.label.split(" ")[0]}`} disabled={tBusy || !tHost}
                      onClick={() => void runRunbook(rb.label, rb.cmds)}
                      style={{ background: "none", border: `1px solid ${CK.line}`, color: CK.green, cursor: "pointer", fontFamily: MONO, fontSize: 9, padding: "2px 8px" }}>▶ {rb.label}</button>
                  ))}
                </div>
                {(runbooks.length > 0 || tHist.length > 0) && (
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
                    <span style={{ fontFamily: MONO, fontSize: 8.5, color: CK.inkDim }}>saved:</span>
                    {runbooks.map((rb) => (
                      <span key={rb.id} style={{ display: "inline-flex", alignItems: "center", border: `1px solid ${CK.line}` }}>
                        <button type="button" data-testid={`ws-rb-run-${rb.id}`} disabled={tBusy || !tHost} onClick={() => void runRunbook(rb.name, rb.commands)}
                          style={{ background: "none", border: "none", color: CK.cyan, cursor: "pointer", fontFamily: MONO, fontSize: 9, padding: "2px 7px" }}>▶ {rb.name}</button>
                        <button type="button" data-testid={`ws-rb-del-${rb.id}`} onClick={() => void delRunbook(rb.id)}
                          style={{ background: "none", border: "none", borderLeft: `1px solid ${CK.line}`, color: CK.red, cursor: "pointer", fontFamily: MONO, fontSize: 9, padding: "2px 6px" }}>×</button>
                      </span>
                    ))}
                    {tHist.length > 0 && (
                      <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
                        <CkInput data-testid="ws-rb-name" placeholder={`name (saves ${tHist.length} cmd${tHist.length > 1 ? "s" : ""})`} value={rbName}
                          onChange={(e) => setRbName(e.target.value)} style={{ width: 170, fontSize: 9 }} />
                        <button type="button" data-testid="ws-rb-save" onClick={() => void saveRunbook()}
                          style={{ background: "none", border: `1px solid ${CK.line}`, color: CK.green, cursor: "pointer", fontFamily: MONO, fontSize: 9, padding: "3px 8px" }}>save</button>
                      </span>
                    )}
                  </div>
                )}
                <div data-testid="ws-terminal-log" style={{ background: "#040a12", border: `1px solid ${CK.line}`, maxHeight: 300, overflowY: "auto", padding: "10px 12px", fontFamily: MONO, fontSize: 11, lineHeight: 1.5 }}>
                  {tLog.length === 0 && <div style={{ color: CK.inkDim }}>— ready — type a command below (try: df -h, systemctl status, tail -n 50 /var/log/…)</div>}
                  {tLog.map((e, i) => (
                    <div key={i} style={{ marginBottom: 8 }}>
                      <div style={{ color: e.cmd.startsWith("#") ? CK.amber : CK.green }}>{e.cmd.startsWith("#") ? e.cmd : <>{tHost}$ <span style={{ color: CK.ink }}>{e.cmd}</span></>}</div>
                      {e.out && <pre style={{ margin: "2px 0 0", whiteSpace: "pre-wrap", wordBreak: "break-word", color: e.code === 0 ? CK.inkSoft : CK.red }}>{e.out}</pre>}
                      {!e.cmd.startsWith("#") && e.out && !e.analysis && (
                        <button type="button" data-testid={`ws-terminal-explain-${i}`} disabled={tExplaining === i} onClick={() => void explainEntry(i)}
                          style={{ marginTop: 3, background: "none", border: `1px solid ${CK.line}`, color: CK.cyan, cursor: "pointer", fontFamily: MONO, fontSize: 9, padding: "1px 7px" }}>{tExplaining === i ? "…" : "✨ Explain"}</button>
                      )}
                      {e.analysis && (
                        <div style={{ marginTop: 4, borderLeft: `2px solid ${CK.cyan}`, paddingLeft: 8, color: CK.inkSoft, whiteSpace: "pre-wrap", fontSize: 10.5 }}>{e.analysis}</div>
                      )}
                    </div>
                  ))}
                </div>
                <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                  <span style={{ fontFamily: MONO, fontSize: 12, color: CK.green, alignSelf: "center" }}>$</span>
                  <CkInput data-testid="ws-terminal-cmd" placeholder="command…  (↑ recalls history)" value={tCmd}
                    onChange={(e) => setTCmd(e.target.value)} onKeyDown={termKey} style={{ flex: 1 }} />
                  <CkButton tone="green" disabled={tBusy} data-testid="ws-terminal-run" onClick={() => void runCmd()}>{tBusy ? "…" : "RUN"}</CkButton>
                </div>
              </div>
            </CkPanel>
          )}

          {panel === "agent" && room.agent_catalog.length > 0 && (
            <CkPanel title="Add an Agent" plate="SKILLS CATALOG" testid="ws-catalog" accent={accent}>
              <div style={{ padding: "8px 12px 0", fontFamily: MONO, fontSize: 10, color: CK.inkSoft, lineHeight: 1.6 }}>
                Extra {room.role.discipline} agents you can bring online. Instant and on the record.
              </div>
              <div style={{ padding: 12, display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: 10 }}>
                {room.agent_catalog.map((a) => (
                  <div key={a.key} data-testid={`ws-catalog-${a.key}`} style={{
                    border: `1px dashed ${accent}`, background: `${accent}0c`, padding: "8px 10px",
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ color: accent, fontSize: 13 }}>＋</span>
                      <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: CK.ink }}>{a.name}</span>
                      <CkButton style={{ marginLeft: "auto" }} data-testid={`ws-request-${a.key}`} onClick={() => void requestAgent(a)}>REQUEST</CkButton>
                    </div>
                    <div style={{ fontFamily: MONO, fontSize: 10, color: CK.inkSoft, marginTop: 5 }}>{a.does}</div>
                    <div style={{ fontFamily: MONO, fontSize: 8.5, color: accent, marginTop: 4 }}>⚡ {poweredLabel[a.powered_by] ?? a.powered_by}</div>
                  </div>
                ))}
              </div>
            </CkPanel>
          )}

          {panel === "instruments" && (
            <CkPanel title="Instruments" plate="BUILT-IN TOOLS" testid="ws-toolkit" accent={accent}>
              <div style={{ padding: 12, display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: 10 }}>
                {room.toolkit.map((t) => {
                  const sc = toolStatusColor(t.status);
                  const on = t.status === "connected";
                  return (
                    <div key={t.key} data-testid={`ws-tool-${t.key}`} style={{
                      border: `1px solid ${CK.line}`, borderLeft: `4px solid ${sc}`,
                      background: on ? `${sc}14` : CK.shell, padding: "8px 10px",
                      boxShadow: on ? `inset 0 0 20px ${sc}18` : "none",
                    }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                        <span style={{ display: "flex", alignItems: "center", gap: 7 }}>
                          {on ? <CkLed color={sc} size={8} /> : <span style={{ width: 8, height: 8, background: sc, display: "inline-block", borderRadius: "50%", opacity: 0.7 }} />}
                          <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: CK.ink }}>{t.name}</span>
                        </span>
                        <span style={{ fontFamily: MONO, fontSize: 8.5, fontWeight: 700, letterSpacing: "0.1em",
                          textTransform: "uppercase", color: sc, background: `${sc}14`, border: `1px solid ${sc}`, padding: "1px 6px" }}>{statusLabel(t.status)}</span>
                      </div>
                      <div style={{ fontFamily: MONO, fontSize: 10, color: CK.inkSoft, marginTop: 4 }}>{t.purpose}</div>
                      {t.status !== "connected" && (t.connect_hint || t.link) && (
                        <div style={{ fontFamily: MONO, fontSize: 9, color: sc, marginTop: 4 }}>
                          {t.link
                            ? <a href={t.link} target="_blank" rel="noreferrer" style={{ color: sc }}>{t.connect_hint || "Open →"}</a>
                            : t.connect_hint}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </CkPanel>
          )}

          {panel === "files" && room.files.length > 0 && (
            <CkPanel title={`Flight Recorder — ${room.files.length}`} plate="SAVED OUTPUTS" testid="ws-files" accent={accent}>
              <div style={{ padding: 12 }}>
                {room.files.map((f) => (
                  <div key={f.id} data-testid={`ws-file-${f.id}`} style={{
                    display: "flex", alignItems: "center", gap: 10, padding: "7px 10px",
                    border: `1px solid ${CK.line}`, borderLeft: `4px solid ${accent}`, marginBottom: 8,
                    background: `${accent}0c`, flexWrap: "wrap",
                  }}>
                    <span style={{ color: accent, fontSize: 14 }}>▤</span>
                    <span style={{ flex: 1, minWidth: 160 }}>
                      <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: CK.ink }}>{f.name}</span>
                      <div style={{ fontFamily: MONO, fontSize: 9, color: CK.inkSoft }}>
                        {f.source_agent_name ? `from ${f.source_agent_name} · ` : ""}{(f.created_at || "").slice(0, 16).replace("T", " ")} · {f.content.length} chars
                      </div>
                    </span>
                    <span style={{ display: "flex", gap: 6 }}>
                      <CkButton data-testid={`ws-file-copy-${f.id}`} onClick={() => void copyText(f.content)}>COPY</CkButton>
                      <CkButton data-testid={`ws-file-download-${f.id}`} onClick={() => downloadText(f.name, f.content)}>DOWNLOAD</CkButton>
                      <CkButton tone="red" data-testid={`ws-file-delete-${f.id}`} onClick={() => void deleteFile(f.id)}>DELETE</CkButton>
                    </span>
                  </div>
                ))}
              </div>
            </CkPanel>
          )}

          {panel === "resources" && (
            <CkPanel title="Playbook" plate="RESOURCES + CHECKLIST" testid="ws-resources" accent={accent}>
              <div style={{ padding: 12, display: "flex", gap: 16, flexWrap: "wrap" }}>
                <div style={{ flex: "1 1 300px" }}>
                  <SectionLabel accent={accent}>Resources</SectionLabel>
                  {room.resources.map((r) => {
                    const kc = resourceKindColor(r.kind, accent);
                    return (
                      <div key={r.key} style={{ display: "flex", gap: 8, padding: "5px 0", borderBottom: `1px solid ${CK.lineSoft}` }}>
                        <span style={{ width: 4, background: kc, flexShrink: 0 }} />
                        <span>
                          <span style={{ fontFamily: MONO, fontSize: 11, color: CK.ink, fontWeight: 700 }}>{r.title} </span>
                          <span style={{ fontFamily: MONO, fontSize: 8, fontWeight: 700, letterSpacing: "0.08em",
                            textTransform: "uppercase", color: kc, border: `1px solid ${kc}`, padding: "0 5px" }}>{r.kind}</span>
                          <div style={{ fontFamily: MONO, fontSize: 9.5, color: CK.inkSoft }}>{r.summary}</div>
                        </span>
                      </div>
                    );
                  })}
                </div>
                <div style={{ flex: "1 1 300px" }}>
                  <SectionLabel accent={accent}>Checklist</SectionLabel>
                  {room.checklist.map((c, i) => (
                    <div key={i} style={{ display: "flex", gap: 8, fontFamily: MONO, fontSize: 10.5, color: CK.ink, padding: "3px 0" }}>
                      <span style={{ width: 18, height: 18, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center",
                        border: `1px solid ${accent}`, color: accent, fontSize: 9, fontWeight: 700 }}>{i + 1}</span>
                      <span>{c}</span>
                    </div>
                  ))}
                </div>
              </div>
            </CkPanel>
          )}

          {panel === "comms" && (
            <CkPanel title="Comms" plate="COLLAB" testid="ws-thread" accent={accent}>
              <div style={{ padding: 12 }}>
                {room.thread.length === 0 ? (
                  <div style={{ fontFamily: MONO, fontSize: 11, color: CK.inkSoft, fontStyle: "italic" }}>Channel open — no traffic yet.</div>
                ) : room.thread.map((m) => (
                  <div key={m.id} style={{ borderBottom: `1px solid ${CK.lineSoft}`, padding: "6px 0", fontFamily: MONO, fontSize: 11.5 }}>
                    <span style={{ color: m.author_role === "ai" ? "#c78bff" : CK.inkSoft, fontWeight: 700, marginRight: 8 }}>
                      {m.author_role === "ai" ? "AI Venture Manager" : m.author_role}
                    </span>
                    <span style={{ color: CK.ink }}>{m.body}</span>
                  </div>
                ))}
                <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                  <CkTextArea value={draft} onChange={(e) => setDraft(e.target.value)}
                    placeholder="Transmit to the venture team…" style={{ flex: 1, minHeight: 44 }} data-testid="ws-msg-draft" />
                  <CkButton tone="green" data-testid="ws-msg-post" onClick={() => void postMsg()}>SEND</CkButton>
                </div>
              </div>
            </CkPanel>
          )}

          {/* Approval missions — always visible when present */}
          {room.approval_missions.total_available > 0 && (
            <div data-testid="ws-approvals" style={{
              display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", margin: "0 0 14px",
              border: `1px solid ${CK.amber}`, borderLeft: `4px solid ${CK.amber}`, background: `${CK.amber}12`,
              padding: "9px 12px", fontFamily: MONO, fontSize: 10.5, color: CK.ink,
            }}>
              <CkLed color={CK.amber} />
              <span>{room.approval_missions.total_available} approval mission(s) inbound
              {room.approval_missions.in_this_venture > 0 ? ` (${room.approval_missions.in_this_venture} in this venture)` : ""}.</span>
              {props.onGoToJudgment && (
                <button type="button" data-testid="ws-goto-judgment" onClick={props.onGoToJudgment}
                  style={{ marginLeft: "auto", background: "none", border: `1px solid ${CK.amber}`, color: CK.amber,
                    cursor: "pointer", fontFamily: MONO, fontSize: 10, padding: "3px 10px", letterSpacing: "0.06em" }}>
                  JUDGMENT DESK →
                </button>
              )}
            </div>
          )}

          {/* Governed write-backs — the Execution layer, human-approved */}
          {room.write_requests.length > 0 && (
            <CkPanel title="Governed Write-backs" plate="EXECUTION · HUMAN-APPROVED" testid="ws-writebacks" accent={CK.amber}>
              <div style={{ padding: "8px 12px 0", fontFamily: MONO, fontSize: 9.5, color: CK.inkSoft, lineHeight: 1.6 }}>
                Write actions never fire on request — they wait at the approval gate for a human governor,
                then execute and receipt.
              </div>
              <div style={{ padding: 12 }}>
                {room.write_requests.slice(0, 8).map((w) => {
                  const c = w.status === "executed" ? CK.green : w.status === "pending" ? CK.amber : CK.red;
                  return (
                    <div key={w.id} data-testid={`ws-writeback-${w.id}`} style={{
                      display: "flex", alignItems: "center", gap: 10, padding: "7px 10px",
                      border: `1px solid ${CK.line}`, borderLeft: `4px solid ${c}`, marginBottom: 6,
                      background: `${c}0e`, flexWrap: "wrap",
                    }}>
                      <CkLed color={c} size={7} />
                      <span style={{ flex: 1, minWidth: 180 }}>
                        <span style={{ fontFamily: MONO, fontSize: 10.5, color: CK.ink }}>{w.summary}</span>
                        <div style={{ fontFamily: MONO, fontSize: 8.5, color: CK.inkDim }}>
                          {(w.requested_at || "").slice(0, 16).replace("T", " ")}{w.reject_reason ? ` · ${w.reject_reason}` : ""}
                        </div>
                      </span>
                      <span style={{ fontFamily: MONO, fontSize: 8.5, fontWeight: 700, letterSpacing: "0.1em",
                        textTransform: "uppercase", color: c, border: `1px solid ${c}`, padding: "1px 7px" }}>
                        {w.status === "pending" ? "awaiting approval" : w.status}
                      </span>
                    </div>
                  );
                })}
              </div>
            </CkPanel>
          )}

          {viewMode === "smart" ? (
            <SmartWorkspace room={room} workUnitId={room.task.work_unit_id}
              connectRaw={connectRaw} onRefresh={props.onRefresh}
              onPrepareTerminal={canGovern && sshBridges.length > 0 ? (cmd) => { setTCmd(cmd); setPanel("terminal"); } : undefined} />
          ) : viewMode === "cockpit" ? (
            <Cockpit3 room={room} workUnitId={room.task.work_unit_id} canGovern={canGovern}
              connectRaw={connectRaw} onConnect={connectTool} onDisconnect={disconnectTool}
              onRefresh={props.onRefresh} saveAgentOutput={saveAgentOutput} />
          ) : (<>
          {/* MISSION — the task, front and centre */}
          <CkPanel title="Mission" plate="DELIVERABLE" testid="ws-task" accent={accent}
            right={<CkStat label="Status" value={room.task.status} color={CK.amber} />}>
            <div style={{ padding: 12, fontFamily: MONO, fontSize: 11.5, color: CK.ink, lineHeight: 1.6 }}>
              {room.task.description && <div style={{ color: CK.inkSoft, marginBottom: 8 }}>{room.task.description}</div>}
              {room.task.deadline && <div style={{ marginBottom: 8 }}><CkChip color={CK.amber} label={`due ${room.task.deadline}`} /></div>}
              {room.task.acceptance_criteria.length > 0 && (
                <div style={{ marginBottom: 8 }}>
                  <SectionLabel accent={accent}>Acceptance criteria</SectionLabel>
                  {room.task.acceptance_criteria.map((c, i) => (
                    <div key={i} style={{ fontSize: 10.5, color: CK.ink }}>
                      <span style={{ color: accent }}>✓</span> {c}
                    </div>
                  ))}
                </div>
              )}
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8, flexWrap: "wrap" }}>
                <CkInput data-testid="ws-evidence" value={evidence}
                  onChange={(e) => setEvidence(e.target.value)}
                  placeholder="Evidence link (repo, doc, deploy…)" style={{ flex: 1, minWidth: 220 }} />
                <CkButton tone="green" data-testid="ws-submit" onClick={() => void submit()}>SUBMIT DELIVERABLE</CkButton>
              </div>
            </div>
          </CkPanel>

          {/* APPLICATIONS — the workstation dock: icons with a live status light.
              Green = connected → click to open in WACE. Red = click to connect. */}
          <SectionHead label="Applications" hue={CK.cyan} count={`${room.connected_tools.length} connected`}
            action={<CkTab active={panel === "connect"} hue={CK.cyan} testid="ws-tools-add" onClick={() => togglePanel("connect")}>＋ Catalog</CkTab>} />
          {(() => {
            const connectedKeys = new Set(room.connected_tools.map((t) => t.connector_key));
            const apps = orderApps(room.connectors, connectedKeys, room.role.discipline);
            const groups = groupByCategory(apps);
            return (
              <div data-testid="ws-app-dock" style={{ position: "relative", overflow: "hidden", border: `1px solid ${CK.line}`, borderRadius: 12, background: `linear-gradient(180deg, ${CK.shell}, ${CK.space})`, padding: "12px 12px 5px", marginBottom: 14 }}>
                {groups.map(([cat, catApps]) => (
                  <div key={cat} style={{ marginBottom: 9 }}>
                    <div style={{ fontFamily: MONO, fontSize: 8, letterSpacing: "0.18em", textTransform: "uppercase", color: CK.inkDim, marginBottom: 6 }}>{CATEGORY_LABEL[cat] || cat}</div>
                    <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                      {catApps.map((c) => {
                        const t = room.connected_tools.find((x) => x.connector_key === c.key);
                        const st = t ? (t.auth_status === "pending" ? "amber" : "green") : "red";
                        const col = st === "green" ? CK.green : st === "amber" ? CK.amber : CK.red;
                        const foc = focusedToolId && t && t.id === focusedToolId;
                        const badge = t ? badges[c.key] : undefined;
                        return (
                          <button key={c.key} type="button" data-testid={`ws-app-${c.key}`}
                            title={`${c.name} — ${c.description || CATEGORY_LABEL[c.category] || c.category}\n${t ? "Connected · click to open in WACE" : "Not connected · click to connect"}`}
                            onClick={() => { if (t) setFocusedToolId(t.id); else if (CLOUD_APP_KEYS.has(c.key)) setQcApp({ key: c.key, name: c.name }); else void connectTool(c.key); }}
                            style={{ position: "relative", width: 96, padding: "13px 8px 9px",
                              background: foc ? `${CK.cyan}18` : st === "green" ? `linear-gradient(180deg, ${CK.green}0f, ${CK.shell})` : `linear-gradient(180deg, #ffffff08, ${CK.shell})`,
                              border: `1px solid ${foc ? CK.cyan : st === "green" ? `${CK.green}66` : CK.line}`, borderRadius: 12, cursor: "pointer",
                              display: "flex", flexDirection: "column", alignItems: "center", gap: 6,
                              boxShadow: st === "green" ? `inset 0 0 12px ${CK.green}14` : "none",
                              transition: "transform .12s, border-color .12s, box-shadow .12s" }}
                            onMouseEnter={(e) => { e.currentTarget.style.transform = "translateY(-4px)"; e.currentTarget.style.borderColor = CK.cyan; e.currentTarget.style.boxShadow = `0 8px 24px ${CK.cyan}2a`; }}
                            onMouseLeave={(e) => { e.currentTarget.style.transform = ""; e.currentTarget.style.borderColor = foc ? CK.cyan : st === "green" ? `${CK.green}66` : CK.line; e.currentTarget.style.boxShadow = st === "green" ? `inset 0 0 12px ${CK.green}14` : "none"; }}>
                            <span style={{ fontSize: 27, lineHeight: 1, filter: st === "red" ? "grayscale(0.5) opacity(0.72)" : "none" }}>{CONNECTOR_ICON[c.key] || connectorGlyph(c.category)}</span>
                            <span style={{ fontFamily: MONO, fontSize: 9, color: CK.ink, textAlign: "center", lineHeight: 1.2, maxWidth: 82, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</span>
                            <span data-testid={`ws-app-led-${c.key}`} className={st === "green" ? "ck-led" : undefined}
                              style={{ position: "absolute", top: 8, right: 8, width: 9, height: 9, borderRadius: "50%", background: col, boxShadow: `0 0 8px ${col}, 0 0 2px ${col}` }} />
                            {badge != null && badge > 0 && (
                              <span data-testid={`ws-app-badge-${c.key}`} style={{ position: "absolute", top: 6, left: 6, minWidth: 15, height: 15, padding: "0 4px", borderRadius: 8, background: CK.amber, color: "#1a1206", fontFamily: MONO, fontSize: 8.5, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center", boxShadow: `0 0 8px ${CK.amber}66` }}>{badge > 99 ? "99+" : badge}</span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            );
          })()}
          {qcApp && (
            <div data-testid="ws-quickconnect" style={{ border: `1px solid ${CK.cyan}`, background: CK.space, padding: "10px 12px", marginBottom: 12 }}>
              <div style={{ fontFamily: MONO, fontSize: 9, color: CK.cyan, letterSpacing: "0.1em", marginBottom: 6 }}>CONNECT {qcApp.name.toUpperCase()} — BASE URL + TOKEN (CLOUD, READ-ONLY)</div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                <CkInput data-testid="ws-qc-base" placeholder="Base URL (https://…)" value={qcBase} onChange={(e) => setQcBase(e.target.value)} style={{ flex: "1 1 220px" }} />
                <CkInput data-testid="ws-qc-auth" placeholder="Auth header (Authorization: Bearer …)" value={qcAuth} onChange={(e) => setQcAuth(e.target.value)} style={{ flex: "1 1 220px" }} />
                <CkButton tone="cyan" data-testid="ws-qc-go" onClick={() => void doQuickConnect()}>▸ CONNECT</CkButton>
                <button type="button" data-testid="ws-qc-cancel" onClick={() => setQcApp(null)}
                  style={{ background: "none", border: `1px solid ${CK.line}`, color: CK.inkSoft, cursor: "pointer", fontFamily: MONO, fontSize: 10, padding: "3px 9px" }}>×</button>
              </div>
            </div>
          )}
          {focused ? (
            <div>
              <button type="button" data-testid="ws-app-back" onClick={() => setFocusedToolId("")}
                style={{ background: "none", border: `1px solid ${CK.line}`, color: CK.cyan, cursor: "pointer", fontFamily: MONO, fontSize: 10, padding: "3px 11px", marginBottom: 8 }}>← all apps</button>
              <ToolWidget key={focused.id} tool={focused}
                connector={focused.connector_key === "custom" ? customConnectorFor(focused) : room.connectors.find((c) => c.key === focused.connector_key)}
                workUnitId={room.task.work_unit_id} onDisconnect={(id) => { setFocusedToolId(""); void disconnectTool(id); }} onSaved={props.onRefresh} agents={room.agents}
                onSuggestCommand={canGovern && sshBridges.length > 0 ? (cmd) => { setTCmd(cmd); setPanel("terminal"); } : undefined} />
            </div>
          ) : (
            <div data-testid="ws-tools-hint" style={{
              fontFamily: MONO, fontSize: 10, color: CK.inkDim, padding: "2px 2px 4px", letterSpacing: "0.04em",
            }}>
              {room.connected_tools.length === 0
                ? "Click a red app to connect it — then it turns green and opens here."
                : "Click a green app to open it in WACE · click red to connect."}
            </div>
          )}

          {/* YOUR AI CREW — the agents, runnable */}
          <SectionHead label="Your AI Crew" hue={accent} count={`${room.agents.length} online · you own the output`}
            action={room.agent_catalog.length > 0
              ? <CkTab active={panel === "agent"} hue={accent} testid="ws-crew-add" onClick={() => togglePanel("agent")}>＋ Add Agent</CkTab>
              : undefined} />
          <div data-testid="ws-agents" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 12, alignItems: "start" }}>
            {room.agents.map((a) => (
              <AgentCard key={a.key} agent={a} accent={accent} workUnitId={room.task.work_unit_id} onSave={saveAgentOutput}
                focus={focus && focus.key === a.key ? { nonce: focus.nonce, brief: focus.brief } : undefined} />
            ))}
          </div>
          </>)}
          </>
        )}
      </div>
    </div>
  );
}

// A compact connector read (calendar events / recent mail / incidents) for the cockpit side panels.
function MiniList({ workUnitId, tool, action, empty, onOpen, onConnect }: {
  workUnitId: string; tool?: api.ConnectedTool; action: string; empty: string; onOpen?: () => void; onConnect?: () => void;
}): React.ReactElement {
  const [rows, setRows] = React.useState<api.ConnectorRow[]>([]);
  const [busy, setBusy] = React.useState(true);
  React.useEffect(() => {
    if (!tool) { setBusy(false); return; }
    let live = true;
    api.invokeConnector(workUnitId, tool.id, action, {})
      .then((r) => { if (live) setRows(r.result?.rows || []); })
      .catch(() => undefined).finally(() => { if (live) setBusy(false); });
    return () => { live = false; };
  }, [tool?.id]);
  if (!tool) return (
    <button type="button" onClick={onConnect} data-testid="ck-mini-connect"
      style={{ width: "100%", textAlign: "left", background: "none", border: `1px dashed ${CK.line}`, borderRadius: 7, color: CK.inkSoft, cursor: onConnect ? "pointer" : "default", fontFamily: MONO, fontSize: 8.5, padding: "7px 8px", lineHeight: 1.4 }}>{empty}</button>
  );
  if (busy) return <div style={{ fontFamily: MONO, fontSize: 8.5, color: CK.inkDim }}>loading…</div>;
  if (rows.length === 0) return <div style={{ fontFamily: MONO, fontSize: 8.5, color: CK.inkDim }}>nothing right now</div>;
  return (
    <div>
      {rows.slice(0, 5).map((r, i) => (
        <div key={i} onClick={onOpen} style={{ padding: "3px 0", borderBottom: `1px solid ${CK.lineSoft}`, cursor: onOpen ? "pointer" : "default" }}>
          <div style={{ fontFamily: MONO, fontSize: 8.5, color: CK.ink, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.primary}{r.meta ? <span style={{ color: CK.inkDim }}> · {r.meta}</span> : null}</div>
          {r.secondary && <div style={{ fontFamily: MONO, fontSize: 7.5, color: CK.inkSoft, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.secondary}</div>}
        </div>
      ))}
    </div>
  );
}

// The 3-column drag-and-drop cockpit: tools+calendar | tickets+workspace+recommendation | agents+mail.
function Cockpit3(props: {
  room: api.RoleWorkspace; workUnitId: string; canGovern: boolean;
  connectRaw: (key: string) => Promise<api.ConnectedTool | null>;
  onConnect: (key: string) => void; onDisconnect: (id: string) => void; onRefresh: () => void;
  saveAgentOutput: (a: api.WsAgent, content: string) => void;
}): React.ReactElement {
  const { room, workUnitId } = props;
  const accent = accentFor(room.role.discipline);
  type WsItem = { kind: "tool"; toolId: string } | { kind: "agent"; agentKey: string; nonce: number };
  const wsKey = `wace_ws_${workUnitId}`;
  // Keep the open workspace across refresh — persist per desk, filtering out
  // anything that's since been disconnected/removed.
  const validItem = React.useCallback((x: WsItem) =>
    (x.kind === "tool" && room.connected_tools.some((t) => t.id === x.toolId)) ||
    (x.kind === "agent" && room.agents.some((a) => a.key === x.agentKey)), [room]);
  const [active, setActive] = React.useState<WsItem[]>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(wsKey) || "[]");
      return Array.isArray(saved) ? saved.filter(validItem) : [];
    } catch { return []; }
  });
  React.useEffect(() => {
    try { localStorage.setItem(wsKey, JSON.stringify(active)); } catch { /* noop */ }
  }, [active, wsKey]);
  // Prune items whose tool/agent no longer exists after a room refresh.
  const rosterKey = room.connected_tools.map((t) => t.id).join(",") + "|" + room.agents.map((a) => a.key).join(",");
  React.useEffect(() => {
    setActive((a) => { const f = a.filter(validItem); return f.length === a.length ? a : f; });
  }, [rosterKey]);
  const [reco, setReco] = React.useState(""); const [recoBusy, setRecoBusy] = React.useState(false);
  const [ticketsOpen, setTicketsOpen] = React.useState(false);
  const [panelData, setPanelData] = React.useState<Record<string, string>>({});   // toolId → latest loaded data
  const [hoverTool, setHoverTool] = React.useState<{ key: string; x: number; y: number } | null>(null);
  const [dragIdx, setDragIdx] = React.useState<number | null>(null);
  // Resizable navbars, remembered per desk.
  const colsKey = `wace_cols_${workUnitId}`;
  const [cols, setCols] = React.useState<{ l: number; r: number }>(() => {
    try { const s = JSON.parse(localStorage.getItem(colsKey) || "null"); if (s && typeof s.l === "number" && typeof s.r === "number") return s; } catch { /* noop */ }
    return { l: 108, r: 124 };
  });
  React.useEffect(() => { try { localStorage.setItem(colsKey, JSON.stringify(cols)); } catch { /* noop */ } }, [cols, colsKey]);
  const startResize = (which: "l" | "r") => (e: React.MouseEvent) => {
    e.preventDefault();
    const sx = e.clientX; const s0 = cols;
    const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
    const onMove = (ev: MouseEvent) => setCols(which === "l"
      ? { ...s0, l: clamp(s0.l + (ev.clientX - sx), 84, 320) }
      : { ...s0, r: clamp(s0.r - (ev.clientX - sx), 84, 340) });
    const onUp = () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
    window.addEventListener("mousemove", onMove); window.addEventListener("mouseup", onUp);
  };
  const divider = (which: "l" | "r") => (
    <div data-testid={`ck-resize-${which}`} onMouseDown={startResize(which)} title="Drag to resize"
      style={{ cursor: "col-resize", alignSelf: "stretch", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ width: 3, height: 44, borderRadius: 3, background: CK.line }} />
    </div>
  );
  const [overIdx, setOverIdx] = React.useState<number | null>(null);
  const moveItem = (from: number, to: number) => setActive((a) => {
    if (from === to || from < 0 || to < 0 || from >= a.length || to >= a.length) return a;
    const b = [...a]; const [x] = b.splice(from, 1); b.splice(to, 0, x); return b;
  });
  const byKey = (key: string) => room.connected_tools.find((t) => t.connector_key === key);
  const calTool = byKey("outlook_calendar");
  const mailTool = byKey("outlook_mail");
  const ticketTool = byKey("servicenow") || byKey("remedy");

  const useKey = `wace_tool_use_${workUnitId}`;
  const [useCounts, setUseCounts] = React.useState<Record<string, number>>(() => {
    try { return JSON.parse(localStorage.getItem(useKey) || "{}") || {}; } catch { return {}; }
  });
  const bumpUse = (key: string) => setUseCounts((c) => {
    const next = { ...c, [key]: (c[key] || 0) + 1 };
    try { localStorage.setItem(useKey, JSON.stringify(next)); } catch { /* noop */ }
    return next;
  });
  const addTool = async (key: string) => {
    let t = byKey(key);
    if (!t) { const res = await props.connectRaw(key); if (!res || !res.id) return; t = res; }
    setActive((a) => (a.some((x) => x.kind === "tool" && x.toolId === t!.id) ? a : [...a, { kind: "tool", toolId: t!.id }]));
    bumpUse(key);
  };
  const [addOpen, setAddOpen] = React.useState(false);
  // Saved layouts — capture the open tools/agents (by key) as a named preset.
  const presetsKey = `wace_presets_${workUnitId}`;
  const [presets, setPresets] = React.useState<{ name: string; items: { kind: string; key: string }[] }[]>(() => {
    try { return JSON.parse(localStorage.getItem(presetsKey) || "[]") || []; } catch { return []; }
  });
  const [presetName, setPresetName] = React.useState("");
  const persistPresets = (list: { name: string; items: { kind: string; key: string }[] }[]) => {
    setPresets(list); try { localStorage.setItem(presetsKey, JSON.stringify(list)); } catch { /* noop */ }
  };
  const savePreset = () => {
    const name = presetName.trim();
    if (!name) { notify("sienna", "Name the layout first."); return; }
    const items = active.map((x) => x.kind === "tool"
      ? { kind: "tool", key: room.connected_tools.find((t) => t.id === x.toolId)?.connector_key || "" }
      : { kind: "agent", key: x.agentKey }).filter((p) => p.key);
    if (!items.length) { notify("sienna", "Open some tools or agents first."); return; }
    persistPresets([...presets.filter((p) => p.name !== name), { name, items }]);
    setPresetName(""); notify("green", `Layout “${name}” saved ✓`);
  };
  const openPreset = (p: { items: { kind: string; key: string }[] }) => {
    p.items.forEach((it) => { if (it.kind === "tool") void addTool(it.key); else addAgent(it.key); });
  };
  const addCustomTool = async (spec: api.CustomSpec) => {
    try {
      const t = await api.connectTool(workUnitId, "custom", spec.name, undefined, spec);
      props.onRefresh();
      if (t && t.id) { setActive((a) => [...a, { kind: "tool", toolId: t.id }]); bumpUse("custom"); }
      setAddOpen(false);
      notify("green", `${spec.name} added ✓ — governed & read-only.`);
    } catch (e) { notify("sienna", (e as Error).message); }
  };
  const addAgent = (key: string) => setActive((a) => [...a, { kind: "agent", agentKey: key, nonce: Date.now() + a.length }]);
  const removeAt = (i: number) => setActive((a) => a.filter((_, j) => j !== i));
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const raw = e.dataTransfer.getData("application/wace"); if (!raw) return;
    try { const d = JSON.parse(raw); if (d.kind === "tool") void addTool(d.key); else if (d.kind === "agent") addAgent(d.key); } catch { /* noop */ }
  };
  const drag = (kind: string, key: string) => (e: React.DragEvent) => {
    e.dataTransfer.setData("application/wace", JSON.stringify({ kind, key })); e.dataTransfer.effectAllowed = "copy";
  };
  const getReco = async () => {
    const agent = room.agents.find((a) => a.live) || room.agents[0]; if (!agent) return;
    const ctx = active.map((x) => x.kind === "tool" ? room.connected_tools.find((t) => t.id === x.toolId)?.label : `agent ${x.agentKey}`).filter(Boolean).join(", ") || "an empty workspace";
    setRecoBusy(true);
    try { const r = await api.analyzeData(workUnitId, agent.key, "workspace", `The operator has these open in their workspace: ${ctx}. In one or two sentences, recommend the single most useful next action.`); setReco(`${r.agent_name}: ${r.analysis}`); }
    catch (e) { notify("sienna", (e as Error).message); } finally { setRecoBusy(false); }
  };

  const tools = orderApps(room.connectors, new Set(room.connected_tools.map((t) => t.connector_key)), room.role.discipline);
  const railLabel: React.CSSProperties = { fontFamily: MONO, fontSize: 8, letterSpacing: "0.16em", textTransform: "uppercase", color: CK.inkDim };
  const rail: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 8, background: CK.panel, border: `1px solid ${CK.line}`, borderRadius: 10, padding: 9, alignSelf: "stretch" };
  // Categorise the tool rail: Most Used (by this desk's open-count), Role Related, then the rest.
  const rolePrio = ROLE_APP_PRIORITY[room.role.discipline] || [];
  const mostUsed = [...tools].filter((c) => (useCounts[c.key] || 0) > 0).sort((a, b) => (useCounts[b.key] || 0) - (useCounts[a.key] || 0)).slice(0, 6);
  const muKeys = new Set(mostUsed.map((c) => c.key));
  const roleRelated = tools.filter((c) => !muKeys.has(c.key) && rolePrio.includes(c.key));
  const rrKeys = new Set(roleRelated.map((c) => c.key));
  const others = tools.filter((c) => !muKeys.has(c.key) && !rrKeys.has(c.key));
  const toolGroups = ([["Most Used", mostUsed], ["Role Related", roleRelated], ["All Tools", others]] as [string, api.Connector[]][]).filter(([, g]) => g.length > 0);
  const toolTile = (c: api.Connector) => {
    const on = !!byKey(c.key);
    return (
      <div key={c.key} draggable data-testid={`ck-tool-${c.key}`} onDragStart={drag("tool", c.key)}
        onClick={() => void addTool(c.key)}
        onMouseEnter={(e) => { const r = e.currentTarget.getBoundingClientRect(); setHoverTool({ key: c.key, x: r.right + 8, y: r.top }); }}
        onMouseLeave={() => setHoverTool((h) => (h && h.key === c.key ? null : h))}
        title={`${c.name} — ${c.description || CATEGORY_LABEL[c.category] || c.category}`}
        style={{ position: "relative", width: 36, height: 36, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18,
          borderRadius: 9, cursor: "grab", background: on ? `${CK.green}12` : CK.shell, border: `1px solid ${on ? `${CK.green}55` : CK.line}`,
          filter: on ? "none" : "grayscale(0.5) opacity(0.75)" }}>
        {CONNECTOR_ICON[c.key] || connectorGlyph(c.category)}
        <span className={on ? "ck-led" : undefined} style={{ position: "absolute", top: -2, right: -2, width: 7, height: 7, borderRadius: "50%", background: on ? CK.green : CK.red, boxShadow: `0 0 5px ${on ? CK.green : CK.red}`, filter: "none" }} />
      </div>
    );
  };

  return (
    <div data-testid="ws-cockpit3" style={{ display: "grid", gridTemplateColumns: `${cols.l}px 6px minmax(0,1fr) 6px ${cols.r}px`, gap: 4, alignItems: "stretch", minHeight: 620 }}>
      {/* LEFT NAVBAR — tool icons (slim rail) + calendar */}
      <div style={rail}>
        {toolGroups.map(([label, gtools]) => (
          <div key={label}>
            <div style={{ ...railLabel, marginBottom: 5 }}>{label}</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>{gtools.map(toolTile)}</div>
          </div>
        ))}
        <button type="button" data-testid="ck-add-tool" onClick={() => setAddOpen((o) => !o)}
          title="Add your own tool (custom REST connector)"
          style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2, padding: "6px 8px", borderRadius: 8, cursor: "pointer",
            background: addOpen ? `${CK.cyan}18` : "transparent", border: `1px dashed ${CK.cyan}`, color: CK.cyan, fontFamily: MONO, fontSize: 9 }}>
          <span style={{ fontSize: 14, lineHeight: 1 }}>＋</span> Add a tool
        </button>
        <div style={{ ...railLabel, marginTop: 4, borderTop: `1px solid ${CK.lineSoft}`, paddingTop: 7 }}>Calendar</div>
        <MiniList workUnitId={workUnitId} tool={calTool} action="upcoming" empty="📅 Connect Outlook Calendar" onConnect={() => void addTool("outlook_calendar")} onOpen={() => calTool && void addTool("outlook_calendar")} />
      </div>

      {divider("l")}

      {/* MIDDLE — minimized tickets · big workspace · AI recommendation */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10, minWidth: 0 }}>
        {addOpen && <AddToolPanel workUnitId={workUnitId} onAdd={(s) => void addCustomTool(s)} onClose={() => setAddOpen(false)} />}
        <div style={{ border: `1px solid ${CK.line}`, borderRadius: 9, background: CK.panel }}>
          <button type="button" data-testid="ck-tickets-toggle" onClick={() => setTicketsOpen((o) => !o)}
            style={{ width: "100%", display: "flex", alignItems: "center", gap: 8, padding: "7px 11px", background: "none", border: "none", color: CK.ink, cursor: "pointer", fontFamily: MONO, fontSize: 10 }}>
            <span style={{ color: CK.amber }}>🎫</span> Priority Tickets
            <span style={{ marginLeft: "auto", color: CK.inkDim, fontSize: 9 }}>{ticketTool ? (ticketsOpen ? "▾ hide" : "▸ show") : "not connected"}</span>
          </button>
          {ticketsOpen && ticketTool && (
            <div style={{ padding: "0 11px 8px" }}>
              <MiniList workUnitId={workUnitId} tool={ticketTool} action="incidents" empty="Connect Remedy/ServiceNow" onOpen={() => void addTool(ticketTool.connector_key)} />
            </div>
          )}
        </div>
        <div data-testid="ck-layouts" style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontFamily: MONO, fontSize: 8, letterSpacing: "0.14em", color: CK.inkDim }}>LAYOUTS</span>
          {presets.map((p) => (
            <span key={p.name} data-testid={`ck-layout-${p.name}`} style={{ display: "inline-flex", gap: 5, alignItems: "center", border: `1px solid ${CK.cyan}44`, borderRadius: 12, padding: "2px 4px 2px 9px", background: `${CK.cyan}10` }}>
              <button type="button" data-testid={`ck-layout-open-${p.name}`} onClick={() => openPreset(p)} style={{ background: "none", border: "none", color: CK.cyan, cursor: "pointer", fontFamily: MONO, fontSize: 9 }}>{p.name} · {p.items.length}</button>
              <button type="button" data-testid={`ck-layout-del-${p.name}`} onClick={() => persistPresets(presets.filter((x) => x.name !== p.name))} style={{ background: "none", border: "none", color: CK.inkDim, cursor: "pointer", fontFamily: MONO, fontSize: 9 }}>×</button>
            </span>
          ))}
          <CkInput data-testid="ck-layout-name" placeholder="name this layout…" value={presetName} onChange={(e) => setPresetName(e.target.value)} style={{ width: 130, marginLeft: "auto" }} />
          <CkButton tone="cyan" data-testid="ck-layout-save" onClick={savePreset}>＋ SAVE</CkButton>
        </div>
        <div data-testid="ck-workspace" onDrop={onDrop} onDragOver={(e) => e.preventDefault()}
          style={{ flex: 1, minHeight: 440, border: `1.5px dashed ${active.length ? CK.line : CK.cyan}`, borderRadius: 12, background: CK.space, padding: active.length ? 12 : 0 }}>
          {active.length === 0 ? (
            <div style={{ height: "100%", minHeight: 440, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, fontFamily: MONO, color: CK.inkSoft, textAlign: "center", padding: 24 }}>
              <div style={{ fontSize: 36, color: CK.cyan }}>⊹</div>
              <div style={{ fontSize: 13, color: CK.ink, letterSpacing: "0.12em" }}>WORKSPACE</div>
              <div style={{ fontSize: 10, color: CK.inkDim, maxWidth: 320, lineHeight: 1.6 }}>Drag a <b style={{ color: CK.cyan }}>tool</b> from the left or an <b style={{ color: accent }}>agent</b> from the right into here. SQL to query · Remedy to triage · an agent to run. Stack as many as you like.</div>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {active.map((item, i) => (
                <div key={item.kind === "tool" ? `t${item.toolId}` : `a${item.agentKey}${item.nonce}`}
                  data-testid={`ck-item-${i}`}
                  onDragOver={(e) => { if (dragIdx !== null) { e.preventDefault(); if (overIdx !== i) setOverIdx(i); } }}
                  onDrop={(e) => { if (dragIdx !== null) { e.preventDefault(); e.stopPropagation(); moveItem(dragIdx, i); setDragIdx(null); setOverIdx(null); } }}
                  style={{ position: "relative", borderRadius: 12, outline: overIdx === i && dragIdx !== null && dragIdx !== i ? `2px dashed ${CK.cyan}` : "none", opacity: dragIdx === i ? 0.5 : 1 }}>
                  <span draggable data-testid={`ck-grip-${i}`}
                    onDragStart={(e) => { setDragIdx(i); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("application/wace-reorder", String(i)); }}
                    onDragEnd={() => { setDragIdx(null); setOverIdx(null); }}
                    title="Drag to reorder"
                    style={{ position: "absolute", top: -6, left: -6, zIndex: 2, width: 20, height: 20, borderRadius: "50%", background: CK.panel, border: `1px solid ${CK.line}`, color: CK.inkSoft, cursor: "grab", fontFamily: MONO, fontSize: 11, lineHeight: "18px", textAlign: "center" }}>⠿</span>
                  <button type="button" data-testid={`ck-close-${i}`} onClick={() => removeAt(i)}
                    style={{ position: "absolute", top: -6, right: -6, zIndex: 2, width: 18, height: 18, borderRadius: "50%", background: CK.panel, border: `1px solid ${CK.line}`, color: CK.inkSoft, cursor: "pointer", fontFamily: MONO, fontSize: 10, lineHeight: 1 }}>✕</button>
                  {item.kind === "tool" ? (() => {
                    const t = room.connected_tools.find((x) => x.id === item.toolId); if (!t) return null;
                    return <ToolWidget tool={t} connector={t.connector_key === "custom" ? customConnectorFor(t) : room.connectors.find((c) => c.key === t.connector_key)}
                      workUnitId={workUnitId} onDisconnect={props.onDisconnect} onSaved={props.onRefresh} agents={room.agents}
                      onData={(txt) => setPanelData((d) => (d[t.id] === txt ? d : { ...d, [t.id]: txt }))} />;
                  })() : (() => {
                    const a = room.agents.find((x) => x.key === item.agentKey); if (!a) return null;
                    // Wire an agent to the panel directly above it: if that's a tool with
                    // loaded data, auto-brief the agent to read it.
                    const prev = active[i - 1];
                    const wiredTool = prev && prev.kind === "tool" ? room.connected_tools.find((x) => x.id === prev.toolId) : undefined;
                    const wiredData = wiredTool ? panelData[wiredTool.id] : undefined;
                    return (
                      <div>
                        {wiredData && (
                          <div data-testid={`ck-wired-${i}`} style={{ fontFamily: MONO, fontSize: 8.5, color: CK.cyan, letterSpacing: "0.08em", margin: "0 0 4px 2px" }}>⇡ WIRED TO {(wiredTool?.label || "panel").toUpperCase()} — reading it automatically</div>
                        )}
                        <AgentCard agent={a} accent={accent} workUnitId={workUnitId} onSave={props.saveAgentOutput}
                          focus={wiredData && wiredTool
                            ? { nonce: item.nonce, brief: `Read the ${wiredTool.label} panel above and give me the key points + anything that needs attention:\n\n${wiredData}`, run: true, wireKey: wiredTool.id }
                            : { nonce: item.nonce }} />
                      </div>
                    );
                  })()}
                </div>
              ))}
            </div>
          )}
        </div>
        <div style={{ border: `1px solid ${CK.line}`, borderRadius: 9, background: CK.panel, padding: "8px 11px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: "0.14em", color: CK.inkSoft }}>AI RECOMMENDATION</span>
            <CkButton tone="cyan" data-testid="ck-reco" disabled={recoBusy} onClick={() => void getReco()} style={{ marginLeft: "auto" }}>{recoBusy ? "…" : "✦ WHAT NEXT"}</CkButton>
          </div>
          {reco && <div data-testid="ck-reco-out" style={{ marginTop: 7, borderLeft: `2px solid ${CK.cyan}`, paddingLeft: 9, fontFamily: MONO, fontSize: 10, color: CK.inkSoft, whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{reco}</div>}
        </div>
      </div>

      {divider("r")}

      {/* RIGHT NAVBAR — agent icons (slim) + mail */}
      <div style={rail}>
        <div style={railLabel}>AI Crew · drag →</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {room.agents.map((a) => (
            <div key={a.key} draggable data-testid={`ck-agent-${a.key}`} onDragStart={drag("agent", a.key)} onClick={() => addAgent(a.key)}
              title={`${a.name} — ${a.does}`}
              style={{ display: "flex", gap: 7, alignItems: "center", padding: "5px 7px", borderRadius: 7, cursor: "grab", border: `1px solid ${CK.line}` }}>
              <span style={{ fontSize: 14, lineHeight: 1 }}>🤖</span>
              <span style={{ minWidth: 0 }}>
                <div style={{ fontFamily: MONO, fontSize: 8.5, fontWeight: 700, color: CK.ink, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.name}</div>
                <div style={{ fontFamily: MONO, fontSize: 7, color: CK.inkSoft, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.does}</div>
              </span>
            </div>
          ))}
        </div>
        <div style={{ ...railLabel, marginTop: 4, borderTop: `1px solid ${CK.lineSoft}`, paddingTop: 7 }}>Mail</div>
        <MiniList workUnitId={workUnitId} tool={mailTool} action="recent" empty="✉️ Connect Outlook Mail" onConnect={() => void addTool("outlook_mail")} onOpen={() => mailTool && void addTool("outlook_mail")} />
      </div>

      {/* Tooltip layer — portaled to <body> so no transformed/clipping ancestor can
          re-anchor the fixed position (was rendering at the top of the page). */}
      {hoverTool && (() => {
        const c = room.connectors.find((x) => x.key === hoverTool.key); if (!c) return null;
        const on = !!byKey(c.key);
        return createPortal(
          <div data-testid={`ck-tip-${c.key}`} style={{ position: "fixed", left: hoverTool.x, top: hoverTool.y, zIndex: 99999, width: 176, padding: "7px 10px",
            background: CK.space, border: `1px solid ${CK.cyan}`, borderRadius: 8, boxShadow: `0 8px 26px #000a`, pointerEvents: "none" }}>
            <div style={{ fontFamily: MONO, fontSize: 9.5, fontWeight: 800, color: CK.ink }}>{c.name}</div>
            <div style={{ fontFamily: MONO, fontSize: 8, color: CK.inkSoft, lineHeight: 1.45, marginTop: 2 }}>{c.description || CATEGORY_LABEL[c.category] || c.category}</div>
            <div style={{ fontFamily: MONO, fontSize: 7.5, color: on ? CK.green : CK.red, marginTop: 3 }}>{on ? "● connected — drag in or click to open" : "○ click to connect"}</div>
          </div>, document.body);
      })()}
    </div>
  );
}

function SectionLabel({ accent, children }: { accent: string; children: React.ReactNode }): React.ReactElement {
  return (
    <div style={{ fontFamily: MONO, fontSize: 9.5, color: accent, letterSpacing: "0.12em",
      textTransform: "uppercase", marginBottom: 6, borderBottom: `1px solid ${accent}44`, paddingBottom: 3 }}>
      {children}
    </div>
  );
}

/* Session Replay — because every action is WORM-receipted, an operator (or an
 * auditor) can scrub through a work session step by step: what was read, drafted,
 * approved, sent — reconstructing any AI-assisted decision, provably. */
function SessionReplay({ receipts, accent }: { receipts: api.Receipt[]; accent: string }): React.ReactElement {
  const ordered = React.useMemo(
    () => [...receipts].sort((a, b) => (a.created_at || "").localeCompare(b.created_at || "")),
    [receipts],
  );
  const [idx, setIdx] = React.useState(0);
  React.useEffect(() => { setIdx(ordered.length ? ordered.length - 1 : 0); }, [ordered.length]);
  if (ordered.length === 0) {
    return <div style={{ padding: 14, fontFamily: MONO, fontSize: 10, color: CK.inkDim }}>Nothing to replay yet — every action you take appears here, on the record.</div>;
  }
  const at = Math.min(idx, ordered.length - 1);
  const cur = ordered[at];
  const write = /write|send|set_status|set_state|executed/.test(cur.action);
  const hue = cur.action.includes("approved") || cur.action.includes("executed") ? CK.green
    : write || cur.action.includes("requested") ? CK.amber
    : cur.action.includes("rejected") || cur.action.includes("failed") ? CK.red : CK.cyan;
  const meta = cur.metadata && Object.keys(cur.metadata).length
    ? Object.entries(cur.metadata).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join("  ·  ")
    : "";
  return (
    <div style={{ padding: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <button type="button" data-testid="ws-replay-prev" disabled={at === 0} onClick={() => setIdx((i) => Math.max(0, i - 1))}
          style={{ background: "none", border: `1px solid ${CK.line}`, color: at === 0 ? CK.inkDim : CK.ink, cursor: at === 0 ? "default" : "pointer", fontFamily: MONO, fontSize: 10, padding: "2px 9px" }}>◀ prev</button>
        <input type="range" data-testid="ws-replay-scrubber" min={0} max={ordered.length - 1} value={at}
          onChange={(e) => setIdx(Number(e.target.value))} style={{ flex: 1, accentColor: accent }} />
        <button type="button" data-testid="ws-replay-next" disabled={at >= ordered.length - 1} onClick={() => setIdx((i) => Math.min(ordered.length - 1, i + 1))}
          style={{ background: "none", border: `1px solid ${CK.line}`, color: at >= ordered.length - 1 ? CK.inkDim : CK.ink, cursor: at >= ordered.length - 1 ? "default" : "pointer", fontFamily: MONO, fontSize: 10, padding: "2px 9px" }}>next ▶</button>
      </div>
      {/* Timeline of dots — the whole session at a glance. */}
      <div style={{ display: "flex", gap: 2, flexWrap: "wrap", marginBottom: 10 }}>
        {ordered.map((r, i) => {
          const w = /write|send|set_status|set_state|executed/.test(r.action);
          const c = r.action.includes("approved") || r.action.includes("executed") ? CK.green
            : w || r.action.includes("requested") ? CK.amber
            : r.action.includes("rejected") || r.action.includes("failed") ? CK.red : CK.cyan;
          return <button key={i} type="button" title={r.action} onClick={() => setIdx(i)}
            style={{ width: 9, height: 9, borderRadius: "50%", border: i === at ? `2px solid ${CK.ink}` : "none", background: c, opacity: i === at ? 1 : 0.55, cursor: "pointer", padding: 0 }} />;
        })}
      </div>
      <div data-testid="ws-replay-step" style={{ border: `1px solid ${CK.line}`, borderLeft: `3px solid ${hue}`, borderRadius: 8, background: CK.panel, padding: "10px 12px" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 5, flexWrap: "wrap" }}>
          <span style={{ fontFamily: MONO, fontSize: 8, color: CK.inkDim }}>STEP {at + 1} / {ordered.length}</span>
          <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: hue }}>{cur.action}</span>
          <span style={{ marginLeft: "auto", fontFamily: MONO, fontSize: 8.5, color: CK.inkDim }}>{(cur.created_at || "").slice(0, 19).replace("T", " ")}</span>
        </div>
        <div style={{ fontFamily: MONO, fontSize: 10, color: CK.ink, lineHeight: 1.5, whiteSpace: "pre-wrap" }}>{cur.detail || "—"}</div>
        <div style={{ marginTop: 6, fontFamily: MONO, fontSize: 8.5, color: CK.inkSoft }}>by {cur.actor_type}:{cur.actor_id}</div>
        {meta && <div style={{ marginTop: 5, fontFamily: MONO, fontSize: 8, color: CK.inkDim, wordBreak: "break-word" }}>{meta}</div>}
      </div>
    </div>
  );
}

/* BYOK — a governor points WACE at the tenant's OWN Anthropic key, so agent
 * runs bill to their account (still SAIb-scrubbed + receipted). The key is
 * sealed server-side; only a masked hint ever returns here. */
function ByokCard(): React.ReactElement {
  const [cfg, setCfg] = React.useState<api.LlmConfig | null>(null);
  const [key, setKey] = React.useState("");
  const [fallback, setFallback] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { Promise.resolve(api.llmConfig()).then(setCfg).catch(() => undefined); }, []);
  const save = async () => {
    if (!key.trim()) { notify("sienna", "Paste your Anthropic API key first."); return; }
    setBusy(true);
    try { setCfg(await api.setLlmKey(key.trim(), fallback)); setKey(""); notify("green", "LLM key saved ✓ — your agents now use your Anthropic account."); }
    catch (e) { notify("sienna", (e as Error).message); } finally { setBusy(false); }
  };
  const remove = async () => {
    setBusy(true);
    try { setCfg(await api.clearLlmKey()); notify("green", "LLM key removed — back to the shared platform AI."); }
    catch (e) { notify("sienna", (e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div data-testid="ws-cc-byok" style={{ border: `1px solid ${CK.line}`, borderRadius: 10, padding: "10px 12px", marginBottom: 12 }}>
      <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.12em", color: CK.cyan, marginBottom: 6 }}>AI · YOUR LLM KEY (BYOK)</div>
      {cfg?.configured ? (
        <div data-testid="ws-cc-byok-status" style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 6 }}>
          <span style={{ fontFamily: MONO, fontSize: 10, color: CK.green }}>✓ Using your Anthropic key <b>{cfg.hint}</b></span>
          <span style={{ fontFamily: MONO, fontSize: 9, color: cfg.allow_platform_fallback ? CK.inkSoft : CK.amber }}>{cfg.allow_platform_fallback ? "platform fallback: on" : "strict — your key only"}</span>
          <button type="button" data-testid="ws-cc-byok-remove" disabled={busy} onClick={() => void remove()}
            style={{ background: "none", border: `1px solid ${CK.red}66`, color: CK.red, cursor: "pointer", fontFamily: MONO, fontSize: 8.5, padding: "2px 8px" }}>remove</button>
        </div>
      ) : (
        <div style={{ fontFamily: MONO, fontSize: 9.5, color: CK.inkSoft, lineHeight: 1.5, marginBottom: 6 }}>Agents currently use the shared platform AI. Add your own Anthropic key so runs bill to your account.</div>
      )}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        <input type="password" data-testid="ws-cc-byok-input" value={key} onChange={(e) => setKey(e.target.value)} placeholder="sk-ant-…"
          style={{ flex: 1, minWidth: 180, background: CK.shell, border: `1px solid ${CK.line}`, color: CK.ink, fontFamily: MONO, fontSize: 10, padding: "4px 8px", borderRadius: 4 }} />
        <label style={{ fontFamily: MONO, fontSize: 9, color: CK.inkSoft, display: "flex", gap: 4, alignItems: "center", cursor: "pointer" }}>
          <input type="checkbox" data-testid="ws-cc-byok-fallback" checked={fallback} onChange={(e) => setFallback(e.target.checked)} /> allow platform fallback
        </label>
        <CkButton tone="cyan" data-testid="ws-cc-byok-save" disabled={busy} onClick={() => void save()}>{busy ? "…" : cfg?.configured ? "REPLACE KEY" : "SET KEY"}</CkButton>
      </div>
      <div style={{ fontFamily: MONO, fontSize: 8, color: CK.inkDim, marginTop: 5 }}>Sealed with AES-256-GCM before storage · sent only to Anthropic · every run SAIb-scrubbed + receipted.</div>
    </div>
  );
}

async function copyText(t: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(t);
    notify("green", "Copied to clipboard ✓");
  } catch { notify("sienna", "Couldn't copy — select the text and copy manually."); }
}

function downloadText(name: string, content: string): void {
  const safe = name.replace(/[^\w.\- ]+/g, "_").trim() || "workspace-file";
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = safe.endsWith(".txt") ? safe : `${safe}.txt`;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

/* A runnable agent — brief it in plain words, get a governed AI draft you own
 * and edit. The output is yours; the agent assists, it never acts on its own. */
function AgentCard({ agent, accent, workUnitId, onSave, focus }: {
  agent: api.WsAgent; accent: string; workUnitId: string;
  onSave: (agent: api.WsAgent, content: string) => void;
  focus?: { nonce: number; brief?: string; run?: boolean; wireKey?: string };
}): React.ReactElement {
  const [open, setOpen] = React.useState(false);
  const [brief, setBrief] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [run, setRun] = React.useState<api.AgentRun | null>(null);
  const [edited, setEdited] = React.useState("");
  const cardRef = React.useRef<HTMLDivElement>(null);
  const briefRef = React.useRef<HTMLTextAreaElement>(null);
  const lastWireRef = React.useRef<string>("");

  // The command palette / intent bar can command this card to open + prefill.
  React.useEffect(() => {
    if (!focus) return;
    setOpen(true);
    if (focus.brief) setBrief(focus.brief);
    cardRef.current?.scrollIntoView?.({ behavior: "smooth", block: "center" });
    window.setTimeout(() => briefRef.current?.focus?.(), 60);
  }, [focus?.nonce]); // eslint-disable-line react-hooks/exhaustive-deps

  const go = async (briefOverride?: string) => {
    const b = (briefOverride ?? brief).trim();
    if (!b) { notify("sienna", "Tell the agent what you need."); return; }
    setBusy(true);
    try {
      const r = await api.runAgent(workUnitId, agent.key, b);
      setRun(r); setEdited(r.output);
      notify("green", `${agent.name} produced a draft ✓ — it's yours to edit.`);
    } catch (e) { notify("sienna", (e as Error).message); }
    finally { setBusy(false); }
  };

  // Agent↔panel wiring: read the panel above automatically. Re-fires when wired to
  // a *different* panel (e.g. the agent is reordered under another data panel).
  React.useEffect(() => {
    if (focus?.run && focus.brief && focus.wireKey && focus.wireKey !== lastWireRef.current) {
      lastWireRef.current = focus.wireKey;
      setOpen(true); setBrief(focus.brief);
      void go(focus.brief);
    }
  }, [focus?.run, focus?.wireKey]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div ref={cardRef} data-testid={`ws-agent-${agent.key}`} className={`ck-sweep${busy ? "" : ""}`}
      style={{
        position: "relative", overflow: "hidden",
        gridColumn: open ? "1 / -1" : "auto", border: `1px solid ${busy ? accent : CK.line}`,
        borderLeft: `3px solid ${accent}`, padding: "9px 11px",
        background: `linear-gradient(180deg, ${accent}16, ${CK.shell})`,
        boxShadow: busy ? `0 0 24px ${accent}44, inset 0 0 26px ${accent}18` : `inset 0 0 22px ${CK.space}`,
        ["--acc" as string]: accent,
      } as React.CSSProperties}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{
          width: 28, height: 28, display: "flex", alignItems: "center", justifyContent: "center",
          background: CK.space, border: `1.5px solid ${accent}`, color: accent, fontSize: 14, borderRadius: "50%",
          boxShadow: `0 0 12px ${accent}66, inset 0 0 8px ${accent}44`,
        }}>◉</span>
        <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: CK.ink }}>{agent.name}</span>
        {agent.live && <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontFamily: MONO, fontSize: 8, fontWeight: 700, letterSpacing: "0.12em", color: CK.green }}><CkLed color={CK.green} size={6} />ONLINE</span>}
        <CkButton tone={open ? "amber" : "cyan"} style={{ marginLeft: "auto" }}
          data-testid={`ws-agent-run-${agent.key}`} onClick={() => setOpen((v) => !v)}>
          {open ? "CLOSE" : "▸ RUN"}
        </CkButton>
      </div>
      <div style={{ fontFamily: MONO, fontSize: 10, color: CK.inkSoft, marginTop: 5 }}>{agent.does}</div>
      <div style={{ fontFamily: MONO, fontSize: 8.5, color: accent, marginTop: 4 }}>
        ⚡ {poweredLabel[agent.powered_by] ?? agent.powered_by}
      </div>

      {open && (
        <div style={{ marginTop: 8, borderTop: `1px solid ${accent}44`, paddingTop: 8 }}>
          <CkTextArea ref={briefRef} data-testid={`ws-agent-brief-${agent.key}`} value={brief}
            onChange={(e) => setBrief(e.target.value)}
            placeholder={`Brief ${agent.name} — e.g. "${agent.does}"`}
            style={{ minHeight: 46 }} />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 6, gap: 8 }}>
            <span style={{ fontFamily: MONO, fontSize: 8.5, color: CK.inkDim }}>
              {busy
                ? <span style={{ display: "inline-flex", alignItems: "center", gap: 6, color: accent }}><CkTelemetry color={accent} />{agent.name.toUpperCase()} WORKING</span>
                : "GOVERNED RUN · SAIb · RECEIPTED"}
            </span>
            <CkButton tone="green" disabled={busy} data-testid={`ws-agent-go-${agent.key}`} onClick={() => void go()}>
              {busy ? "▸ …" : "▸ EXECUTE"}
            </CkButton>
          </div>
          {run && (
            <div style={{ marginTop: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                <span style={{ fontFamily: MONO, fontSize: 9, color: accent, letterSpacing: "0.1em", textTransform: "uppercase" }}>
                  Your draft — edit freely
                </span>
                <span style={{ fontFamily: MONO, fontSize: 8.5, color: run.mode === "ai" ? CK.green : CK.amber }}>
                  {run.mode === "ai" ? "AI DRAFT" : "STARTER — connect the AI gateway for a full draft"}
                </span>
              </div>
              <CkTextArea data-testid={`ws-agent-output-${agent.key}`} value={edited}
                onChange={(e) => setEdited(e.target.value)} style={{ minHeight: 120 }} />
              <div style={{ display: "flex", gap: 8, marginTop: 6, justifyContent: "flex-end" }}>
                <CkButton data-testid={`ws-agent-copy-${agent.key}`}
                  onClick={() => void copyText(edited)}>COPY</CkButton>
                <CkButton tone="green" data-testid={`ws-agent-save-${agent.key}`}
                  onClick={() => onSave(agent, edited)}>SAVE TO RECORDER</CkButton>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
