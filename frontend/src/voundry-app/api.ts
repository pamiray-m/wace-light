/* Voundry standalone-app API client — auth + role-scoped portal calls.
 * Token persisted in localStorage; sent as Bearer on every request. */

declare const __VITE_API_BASE_URL__: string | undefined;
const BASE_URL: string = typeof __VITE_API_BASE_URL__ !== "undefined" ? __VITE_API_BASE_URL__ : "";
const TOKEN_KEY = "voundry_token";

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t: string | null): void {
  try { if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
}

function hdrs(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const t = getToken();
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
}

/** Error carrying the HTTP status + structured detail. 428 (Precondition
 * Required) signals a consent/NDA sign flow: `detail` is then an object like
 * {error: "nda_required", candidate_id, document_id}. */
export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE_URL}${path}`, {
    method, headers: hdrs(), body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    let detail: unknown = `HTTP ${r.status}`;
    try { detail = (await r.json()).detail ?? detail; } catch { /* ignore */ }
    throw new ApiError(r.status, detail);
  }
  return r.json() as Promise<T>;
}
const get = <T>(p: string) => req<T>("GET", p);
const post = <T>(p: string, b?: unknown) => req<T>("POST", p, b);

export type Role = "founder" | "contributor" | "investor" | "operator";

export interface Principal {
  account_id: string; email: string; role: Role; display_name: string;
  contributor_id: string | null; investor_id: string | null;
  can_govern?: boolean;   // may approve governed write-backs
}
export interface AuthResult { token: string; principal: Principal; }

// ---- Auth ----
export async function register(email: string, password: string, role: Role, display_name: string, accepted_terms: boolean): Promise<AuthResult> {
  const res = await post<AuthResult>("/voundry/auth/register", { email, password, role, display_name, accepted_terms });
  setToken(res.token); return res;
}
export const requestPasswordReset = (email: string) => post<{ ok: boolean; detail: string }>("/voundry/auth/request-password-reset", { email });
export const resetPassword = (token: string, new_password: string) => post<{ ok: boolean }>("/voundry/auth/reset-password", { token, new_password });
export async function login(email: string, password: string): Promise<AuthResult> {
  const res = await post<AuthResult>("/voundry/auth/login", { email, password });
  setToken(res.token); return res;
}
export async function me(): Promise<Principal> { return get<Principal>("/voundry/auth/me"); }
export function logout(): void { setToken(null); }

// ---- Founder ----
export interface Idea { id: string; title: string; summary: string; status: string; created_at: string; }
export const submitIdea = (b: Record<string, unknown>) => post<Idea>("/voundry/portal/ideas", b);
export const myIdeas = () => get<Idea[]>("/voundry/portal/my-ideas");

// ---- Contributor ----
export interface WorkUnit {
  id: string; venture_unit_id: string; milestone_id: string; title: string; role_type: string;
  difficulty_score: number; impact_score: number; estimated_credits_min: number; estimated_credits_max: number;
  evidence_required: string[]; status: string; assigned_to: string | null;
}
export interface CreditRow {
  id: string; work_unit_id: string; base_points: number; quality_multiplier: number; impact_multiplier: number;
  timeliness_multiplier: number; scarcity_multiplier: number; approval_confidence: number;
  final_credits: number; approval_status: string;
}
export const openWork = () => get<WorkUnit[]>("/voundry/portal/work-units");
export const myWork = () => get<WorkUnit[]>("/voundry/portal/my-work");
export const myCredits = () => get<CreditRow[]>("/voundry/portal/my-credits");
export const applyToWork = (id: string, application_text: string) => post(`/voundry/portal/work-units/${id}/apply`, { application_text });
export const submitDeliverable = (id: string, b: Record<string, unknown>) => post(`/voundry/portal/work-units/${id}/submit`, b);
export const raiseDispute = (recordId: string, reason: string) => post(`/voundry/portal/contributions/${recordId}/dispute`, { reason });

// ---- Verification / vetting ----
export interface VerificationAssessment {
  score: number; band: string; signals: string[]; tips: string[];
  corroborated_skills: string[];
  components: { portfolio: boolean; linkedin: boolean; cv: boolean; extra_credentials: number };
}
export interface VerificationRequestResult {
  id: string; contributor_id: string; portfolio_url: string; linkedin_url: string;
  credentials: string[]; cv_filename: string; status: string;
  assessment: VerificationAssessment | null;
}
export interface CvExtract { filename: string; cv_text: string; chars: number; }
export const requestVerification = (body: {
  portfolio_url?: string; linkedin_url?: string; credentials?: string[];
  cv_filename?: string; cv_text?: string; note?: string;
}) => post<VerificationRequestResult>("/voundry/portal/request-verification", body);
export async function extractCv(file: File): Promise<CvExtract> {
  const form = new FormData();
  form.append("file", file);
  const t = getToken();
  const r = await fetch(`${BASE_URL}/voundry/portal/cv-extract`, {
    method: "POST",
    headers: t ? { Authorization: `Bearer ${t}` } : {},
    body: form,
  });
  if (!r.ok) {
    let detail: unknown = `HTTP ${r.status}`;
    try { detail = (await r.json()).detail ?? detail; } catch { /* ignore */ }
    throw new ApiError(r.status, detail);
  }
  return r.json() as Promise<CvExtract>;
}
// -- Adaptive intake interview -------------------------------------------------
export interface InterviewTurn { index: number; question: string; answer: string; }
export interface InterviewSession {
  id: string; contributor_id: string; discipline: string; focus: string;
  skills: string[]; turns: InterviewTurn[]; max_turns: number;
  status: "in_progress" | "completed";
  dimension_scores: Record<string, number>; composite: number; summary: string; mode: string;
}
export const startInterview = (body: { discipline?: string; focus?: string }) =>
  post<InterviewSession>("/voundry/portal/interview/start", body);
export const answerInterview = (id: string, answer: string) =>
  post<InterviewSession>(`/voundry/portal/interview/${id}/answer`, { answer });
export const getInterview = (id: string) =>
  get<InterviewSession>(`/voundry/portal/interview/${id}`);

export interface WorkspaceMsg { id: string; work_unit_id: string; author_id: string; author_role: string; kind: string; body: string; created_at: string; }
export const workUnitMessages = (id: string) => get<WorkspaceMsg[]>(`/voundry/portal/work-units/${id}/messages`);
export const postMessage = (id: string, body: string) => post<WorkspaceMsg>(`/voundry/portal/work-units/${id}/messages`, { body });

// ---- Role-scoped workspaces (discipline × vertical) ----
export interface RoleAssignment {
  work_unit_id: string; work_unit_title: string; status: string; is_open: boolean;
  venture_id: string; venture_name: string; discipline: string; vertical: string;
  headline: string; tool_count: number; agent_count: number; connected_tools: number;
}
export interface WsTool {
  key: string; name: string; purpose: string; kind: string;
  env_var: string | null; link: string | null; connect_hint: string; status: string;
}
export interface WsAgent { key: string; name: string; does: string; powered_by: string; live: boolean; }
export interface WsResource { key: string; title: string; kind: string; summary: string; }
export interface AgentRun {
  id: string; contributor_id: string; work_unit_id: string; agent_key: string;
  agent_name: string; capability: string; brief: string; output: string;
  mode: string; created_at: string;
}
export interface WorkspaceFile {
  id: string; work_unit_id: string; contributor_id: string; name: string;
  kind: string; content: string; source_agent_key: string; source_agent_name: string;
  created_at: string;
}
export interface ConnectorAction { key: string; label: string; access: string; params: string[]; direct?: boolean; }
export interface Connector {
  key: string; name: string; description: string; category: string;
  needs_auth: boolean; provider: string; actions: ConnectorAction[];
}
export interface ConnectedTool {
  id: string; work_unit_id: string; contributor_id: string; connector_key: string;
  label: string; scope: string; status: string; provider: string; auth_status: string; created_at: string;
  config?: Record<string, unknown>;
}
export interface CustomSpec {
  name: string; base_url: string; list_path: string; list_result_path?: string; open_path?: string;
  auth_header?: string;   // cloud-direct only (e.g. "Authorization: Bearer …")
  map: { id?: string; primary?: string; secondary?: string; meta?: string; preview?: string };
}
export interface ConnectorRow { id: string; primary: string; secondary: string; meta: string; preview: string; }
export interface ConnectorDetail { subject: string; from: string; from_name: string; to: string; received: string; body: string; }
export interface ConnectorInvokeResult {
  connected_id: string; connector_key: string; action: string;
  result?: { final_url?: string; text: string; rows?: ConnectorRow[]; detail?: ConnectorDetail };
  masked_entities?: number; governed: boolean;
  // Write actions return this instead of a result — queued for human approval.
  pending_approval?: boolean; request_id?: string; summary?: string;
}
export interface WriteRequest {
  id: string; work_unit_id: string; contributor_id: string; connected_id: string;
  connector_key: string; action: string; summary: string;
  status: "pending" | "executed" | "rejected" | "failed";
  gel_task_id: string; reject_reason: string; requested_at: string;
}
export interface RoleWorkspace {
  role: { discipline: string; vertical: string; headline: string };
  venture: { id: string; name: string; status: string; vertical: string };
  task: {
    work_unit_id: string; title: string; description: string; status: string; role_type: string;
    acceptance_criteria: string[]; evidence_required: string[];
    estimated_credits_min: number; estimated_credits_max: number; deadline: string | null;
  };
  toolkit: WsTool[];
  agents: WsAgent[];
  agent_catalog: WsAgent[];
  resources: WsResource[];
  checklist: string[];
  thread: WorkspaceMsg[];
  agent_runs: AgentRun[];
  files: WorkspaceFile[];
  connectors: Connector[];
  connected_tools: ConnectedTool[];
  write_requests: WriteRequest[];
  approval_missions: { in_this_venture: number; total_available: number; items: JudgmentTaskRow[] };
}
export const myWorkspaces = () => get<RoleAssignment[]>("/voundry/portal/workspaces");
export const workspaceRoom = (workUnitId: string) => get<RoleWorkspace>(`/voundry/portal/workspaces/${workUnitId}`);
export const requestAgent = (workUnitId: string, agent_key: string) =>
  post<RoleWorkspace>(`/voundry/portal/workspaces/${workUnitId}/agents/request`, { agent_key });
export interface Citation { claim: string; lines: number[]; confidence: "high" | "medium" | "low" }
export const analyzeData = (workUnitId: string, agent_key: string, source: string, data: string) =>
  post<{ agent_name: string; analysis: string; mode: string; citations?: Citation[] }>(`/voundry/portal/workspaces/${workUnitId}/agents/analyze`, { agent_key, source, data });

export interface SaibPreview { count: number; spans: { type: string; start: number; end: number }[]; by_type: Record<string, number>; masked: string }
export const saibPreview = (text: string) =>
  post<SaibPreview>(`/voundry/portal/saib-preview`, { text });

// WACE Light — onboarding tool suites + a personal desk.
export interface ToolTile { key: string; name: string; category: string; needs_auth: boolean; provider: string; builtin: boolean; blurb: string }
export interface OnboardingSuite { role: string; basic: ToolTile[]; specialized: ToolTile[]; roles: string[] }
export const onboardingSuite = (role: string) =>
  get<OnboardingSuite>(`/voundry/portal/onboarding-suite?role=${encodeURIComponent(role)}`);
export const ensureMyDesk = (role: string) =>
  post<{ work_unit_id: string }>(`/voundry/portal/my-desk`, { role });

// BYOK — the tenant's own Anthropic key (governor-only).
export interface LlmConfig { configured: boolean; hint: string; allow_platform_fallback: boolean }
export const llmConfig = () => get<LlmConfig>(`/voundry/portal/llm-config`);
export const setLlmKey = (api_key: string, allow_platform_fallback: boolean) =>
  post<LlmConfig>(`/voundry/portal/llm-key`, { api_key, allow_platform_fallback });
export const clearLlmKey = () => req<LlmConfig>("DELETE", `/voundry/portal/llm-key`);
export const investigate = (workUnitId: string, agent_key: string, incident: string) =>
  post<{ agent_name: string; hypothesis: string; commands: string[]; mode: string }>(`/voundry/portal/workspaces/${workUnitId}/agents/investigate`, { agent_key, incident });
export const runAgent = (workUnitId: string, agent_key: string, brief: string) =>
  post<AgentRun>(`/voundry/portal/workspaces/${workUnitId}/agents/run`, { agent_key, brief });
export const saveWorkspaceFile = (workUnitId: string, body: {
  name: string; content: string; kind?: string; source_agent_key?: string; source_agent_name?: string;
}) => post<WorkspaceFile>(`/voundry/portal/workspaces/${workUnitId}/files`, body);
export const deleteWorkspaceFile = (workUnitId: string, fileId: string) =>
  req<{ ok: boolean; deleted: string }>("DELETE", `/voundry/portal/workspaces/${workUnitId}/files/${fileId}`);
// -- Governed external connectors ---------------------------------------------
export const connectorCatalog = () => get<Connector[]>("/voundry/portal/connectors/catalog");
export const connectTool = (workUnitId: string, connector_key: string, label?: string, bridge_id?: string, custom_spec?: CustomSpec, cloud_config?: { base_url: string; auth_header?: string }) =>
  post<ConnectedTool & { authorize_url?: string }>(`/voundry/portal/workspaces/${workUnitId}/connectors`, { connector_key, label, bridge_id, custom_spec, cloud_config });
export const connectorAuthorizeUrl = (workUnitId: string, connectedId: string) =>
  get<{ authorize_url: string }>(`/voundry/portal/workspaces/${workUnitId}/connectors/${connectedId}/authorize-url`);
export interface SavedQuery { id: string; work_unit_id: string; contributor_id: string; name: string; sql: string; created_at: string; }
export const listQueries = (workUnitId: string) => get<SavedQuery[]>(`/voundry/portal/workspaces/${workUnitId}/sql/queries`);
export const saveQuery = (workUnitId: string, name: string, sql: string) =>
  post<SavedQuery>(`/voundry/portal/workspaces/${workUnitId}/sql/queries`, { name, sql });
export const deleteQuery = (workUnitId: string, id: string) =>
  req<{ ok: boolean; deleted: string }>("DELETE", `/voundry/portal/workspaces/${workUnitId}/sql/queries/${id}`);
export const invokeConnector = (workUnitId: string, connectedId: string, action: string, params: Record<string, string>) =>
  post<ConnectorInvokeResult>(`/voundry/portal/workspaces/${workUnitId}/connectors/${connectedId}/invoke`, { action, params });
export const disconnectTool = (workUnitId: string, connectedId: string) =>
  req<{ ok: boolean; disconnected: string }>("DELETE", `/voundry/portal/workspaces/${workUnitId}/connectors/${connectedId}`);

// ---- On-prem connector bridge (plug-n-play) ----
export interface Bridge {
  id: string; work_unit_id: string; name: string; capabilities: string[];
  status: "unpaired" | "online" | "offline" | "none"; last_seen: string | null;
  allowed_actions?: string[];
  summary?: { total: number; pending: number; running: number; done: number; failed: number };
}
export const listBridges = (workUnitId: string) =>
  get<Bridge[]>(`/voundry/portal/workspaces/${workUnitId}/bridges`);
export interface Receipt { action: string; actor_id: string; actor_type: string; detail: string; created_at: string; metadata?: Record<string, unknown>; }
export const listReceipts = (workUnitId: string) =>
  get<Receipt[]>(`/voundry/portal/workspaces/${workUnitId}/receipts`);
export const allReceipts = () => get<Receipt[]>("/voundry/portal/receipts");

export interface OrgPolicy { require_approval_for_writes: boolean; block_terminal: boolean; blocked_connectors: string[]; }
export interface CommandCenter {
  desks: number; connections: number; by_category: Record<string, number>;
  bridges: { total: number; online: number };
  actions: number; writes: number; agent_runs: number; terminal: number;
  approvals_pending: number; policy: OrgPolicy;
  top_apps: { key: string; count: number }[];
  value: { actions_automated: number; hours_saved: number; note: string };
  recent: Receipt[];
}
export const commandCenter = () => get<CommandCenter>("/voundry/portal/command-center");
export interface AccessGroup { id: string; displayName: string; is_governor: boolean; member_count: number; }
export const getGroups = () => get<AccessGroup[]>("/voundry/portal/groups");
export interface SamlConfig { enabled: boolean; idp_entity_id: string; idp_sso_url: string; idp_cert: string; sp_entity_id: string; acs_url: string; allowed_domain: string; app_url: string; }
export const getSamlConfig = () => get<SamlConfig>("/voundry/portal/saml-config");
export const setSamlConfig = (patch: Partial<SamlConfig>) => post<SamlConfig>("/voundry/portal/saml-config", patch);
export const getGovernorGroup = () => get<{ token: string }>("/voundry/portal/governor-group");
export const setGovernorGroup = (token: string) => post<{ token: string }>("/voundry/portal/governor-group", { token });
export interface DirUser { account_id: string; email: string; role: string; display_name: string; disabled: boolean; scim_provisioned: boolean; created_at: string; last_seen?: string | null; }
export const listUsers = () => get<DirUser[]>("/voundry/portal/users");
export const setUserActive = (accountId: string, active: boolean) => post<{ ok: boolean; account_id: string; active: boolean }>(`/voundry/portal/users/${accountId}/active`, { active });
export const bulkSetUsersActive = (accountIds: string[], active: boolean) => post<{ ok: boolean; updated: string[]; skipped: string[]; active: boolean }>("/voundry/portal/users/bulk-active", { account_ids: accountIds, active });
export interface IngestResult { name: string; kind: string; text: string; masked_entities: number; chars: number; table?: string[][]; }
export async function ingestFile(workUnitId: string, file: File): Promise<IngestResult> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${BASE_URL}/voundry/portal/workspaces/${workUnitId}/ingest`, { method: "POST", headers: { Authorization: `Bearer ${getToken() || ""}` }, body: fd });
  if (!r.ok) { let d: unknown = `HTTP ${r.status}`; try { d = (await r.json()).detail ?? d; } catch { /* ignore */ } throw new ApiError(r.status, d); }
  return r.json() as Promise<IngestResult>;
}
export async function downloadUsersCsv(): Promise<void> {
  const r = await fetch(`${BASE_URL}/voundry/portal/users.csv`, { headers: { Authorization: `Bearer ${getToken() || ""}` } });
  if (!r.ok) throw new ApiError(r.status, `HTTP ${r.status}`);
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "wace-users.csv";
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}
export interface OrgTool { key: string; name: string; category: string; base_url: string; }
export const getOrgTools = () => get<OrgTool[]>("/voundry/portal/org-tools");
export const addOrgTool = (name: string, category: string, custom_spec: CustomSpec) => post<OrgTool>("/voundry/portal/org-tools", { name, category, custom_spec });
export const removeOrgTool = (key: string) => req<{ ok: boolean; removed: string }>("DELETE", `/voundry/portal/org-tools/${key}`);
export const setPolicy = (patch: Partial<OrgPolicy>) => post<OrgPolicy>("/voundry/portal/policy", patch);
export const mintScimToken = () => post<{ token: string; endpoint: string; note: string }>("/voundry/portal/scim-token");
export interface SsoConfig { enabled: boolean; issuer: string; authorize_url: string; token_url: string; userinfo_url: string; client_id: string; client_secret: string; redirect_uri: string; allowed_domain: string; app_url: string; }
export const getSsoConfig = () => get<SsoConfig>("/voundry/portal/sso-config");
export const setSsoConfig = (patch: Partial<SsoConfig>) => post<SsoConfig>("/voundry/portal/sso-config", patch);
export interface VerifyResult { verified?: boolean; files_ok: boolean; signature_ok: boolean; kid?: string; org?: string; generated_at?: string; counts?: Record<string, number>; error?: string; }
export async function verifyAuditExport(file: File): Promise<VerifyResult> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${BASE_URL}/voundry/public/verify-audit-export`, { method: "POST", body: fd });
  if (!r.ok) throw new ApiError(r.status, `HTTP ${r.status}`);
  return r.json() as Promise<VerifyResult>;
}
export async function downloadAuditExport(): Promise<void> {
  const r = await fetch(`${BASE_URL}/voundry/portal/audit-export`, { headers: { Authorization: `Bearer ${getToken() || ""}` } });
  if (!r.ok) throw new ApiError(r.status, `HTTP ${r.status}`);
  const blob = await r.blob();
  const cd = r.headers.get("Content-Disposition") || "";
  const m = cd.match(/filename="?([^"]+)"?/);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = m ? m[1] : "wace-audit-export.zip";
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}
export const shiftReport = (workUnitId: string, agent_key: string) =>
  post<{ agent_name: string; report: string; mode: string }>(`/voundry/portal/workspaces/${workUnitId}/agents/shift-report`, { agent_key });
export interface PairBridgeResult { bridge: Bridge; pairing_token: string; pairing_code: string; run_command: string; }
export const pairBridge = (workUnitId: string, name = "On-prem bridge") =>
  post<PairBridgeResult>(`/voundry/portal/workspaces/${workUnitId}/bridge`, { name });
export const bridgeStatus = (workUnitId: string) =>
  get<Bridge>(`/voundry/portal/workspaces/${workUnitId}/bridge`);
export const revokeBridge = (workUnitId: string, bridgeId: string) =>
  req<{ ok: boolean; revoked: string }>("DELETE", `/voundry/portal/workspaces/${workUnitId}/bridge/${bridgeId}`);
export interface BridgeJobRow { id: string; connector_key: string; action: string; status: string; created_at: string; latency_s: number | null; error: string; }
export interface BridgeActivity {
  status: string; name?: string; capabilities?: string[]; last_seen?: string | null;
  summary: { total: number; pending: number; running: number; done: number; failed: number };
  jobs: BridgeJobRow[];
}
export const bridgeActivity = (workUnitId: string, bridgeId?: string) =>
  get<BridgeActivity>(`/voundry/portal/workspaces/${workUnitId}/bridge/activity${bridgeId ? `?bridge_id=${encodeURIComponent(bridgeId)}` : ""}`);
export interface CustomTestResult { ok: boolean; count?: number; rows?: ConnectorRow[]; error?: string; }
export const testCustomSpec = (workUnitId: string, custom_spec: CustomSpec, bridge_id?: string) =>
  post<CustomTestResult>(`/voundry/portal/workspaces/${workUnitId}/custom-test`, { custom_spec, bridge_id });

// ---- Governed server terminal (SSH via bridge; governor only) ----
export const terminalHosts = (workUnitId: string, bridge_id: string) =>
  post<{ hosts: ConnectorRow[] }>(`/voundry/portal/workspaces/${workUnitId}/terminal/hosts`, { bridge_id });
export const terminalExec = (workUnitId: string, bridge_id: string, host: string, command: string) =>
  post<{ output: string; exit_code: number | null; host: string }>(`/voundry/portal/workspaces/${workUnitId}/terminal/exec`, { bridge_id, host, command });
export const terminalExplain = (workUnitId: string, host: string, command: string, output: string) =>
  post<{ analysis: string; mode: string }>(`/voundry/portal/workspaces/${workUnitId}/terminal/explain`, { host, command, output });
export interface Runbook { id: string; work_unit_id: string; contributor_id: string; name: string; commands: string[]; created_at: string; }
export const listRunbooks = (workUnitId: string) => get<Runbook[]>(`/voundry/portal/workspaces/${workUnitId}/terminal/runbooks`);
export const saveRunbook = (workUnitId: string, name: string, commands: string[]) =>
  post<Runbook>(`/voundry/portal/workspaces/${workUnitId}/terminal/runbooks`, { name, commands });
export const deleteRunbook = (workUnitId: string, id: string) =>
  req<{ ok: boolean; deleted: string }>("DELETE", `/voundry/portal/workspaces/${workUnitId}/terminal/runbooks/${id}`);

// ---- Governed write-back approvals (governor only) ----
export const pendingApprovals = () => get<WriteRequest[]>("/voundry/portal/approvals");
export const decideWriteBack = (requestId: string, approve: boolean, reason = "") =>
  post<WriteRequest>(`/voundry/portal/approvals/${requestId}/decide`, { approve, reason });

// ---- Investor ----
export interface Candidate {
  id: string; title: string; candidate_score: number; ai_viability_score: number;
  aos_strategic_fit_score: number; risk_level: string; status: string; contributor_interest_count: number;
}
export interface Venture { id: string; name: string; status: string; human_governor_id: string | null; created_at: string; }
export interface Pledge { id: string; investor_id: string; venture_unit_id: string | null; pledge_type: string; amount: number | null; status: string; legal_review_required: boolean; created_at: string; }
export const voteCandidate = (id: string, vote_type: "interest" | "support" | "concern", pledged_hours = 0, rationale = "") =>
  post<Candidate>(`/voundry/portal/candidates/${id}/vote`, { vote_type, pledged_hours, rationale });
export const investorCandidates = () => get<Candidate[]>("/voundry/portal/candidates");
export const investorVentures = () => get<Venture[]>("/voundry/portal/ventures");
export const myPledges = () => get<Pledge[]>("/voundry/portal/my-pledges");
export const riskNotice = () => get<{ risk_notice: string }>("/voundry/portal/risk-notice");
export const watchVenture = (id: string) => post<Pledge>(`/voundry/portal/ventures/${id}/watch`);
export const pledgeInterest = (id: string, amount: number | null) => post<Pledge>(`/voundry/portal/ventures/${id}/pledge-interest`, { amount });
export const sponsorBounty = (id: string, amount: number) => post<Pledge>(`/voundry/portal/ventures/${id}/sponsor-bounty-intent`, { amount });
export const requestDiligence = (id: string) => post<Pledge>(`/voundry/portal/ventures/${id}/request-diligence`);
export const diligencePack = (id: string) => get<Record<string, unknown>>(`/voundry/portal/ventures/${id}/diligence-pack`);

// ---- Legal pack + e-signatures ----
export interface LegalDoc {
  id: string; kind: string; scope: string; version: string; title: string;
  body: string; content_sha256: string; candidate_id: string | null;
  active: boolean; signed?: boolean;
}
export interface LegalStatus { complete: boolean; missing: string[]; signed: string[]; }
export const legalPack = () => get<LegalDoc[]>("/voundry/portal/legal/pack");
export const legalStatus = () => get<LegalStatus>("/voundry/portal/legal/status");
export const signLegal = (document_id: string, typed_name: string) =>
  post<{ ok: boolean; signature_id: string }>("/voundry/portal/legal/sign", { document_id, typed_name });
export const ventureNda = (candidateId: string) => get<LegalDoc>(`/voundry/portal/candidates/${candidateId}/nda`);
export const signVentureNda = (candidateId: string, typed_name: string) =>
  post<{ ok: boolean; document_id: string }>(`/voundry/portal/candidates/${candidateId}/nda/sign`, { typed_name });

// ---- Judgment Desk ----
export interface JudgmentTaskRow {
  id: string; judgment_type: string; subject_type: string; subject_id: string;
  venture_unit_id: string | null; stake_multiplier: number; required_judgments: number;
  min_tier: string; status: string; consensus_verdict: string | null; created_at: string;
  active_claims: { judge_id: string; claimed_at: string; deadline: string }[];
}
export interface JudgmentRecordRow {
  id: string; judgment_task_id: string; judgment_type: string; verdict: string;
  rationale: string; total_credits: number; vested_credits: number; unvested_credits: number;
  slash_credits: number; vesting_status: string; window_ends_at: string; outcome: string;
  created_at: string;
}
export interface JudgmentBalance {
  total_earned: number; vested: number; unvested_pending: number; slashed: number; net: number;
}
export interface MyJudgments { records: JudgmentRecordRow[]; claims: JudgmentTaskRow[]; balance: JudgmentBalance; accuracy: number | null; }
export const judgmentQueue = () => get<JudgmentTaskRow[]>("/voundry/portal/judgments/queue");
export const claimJudgment = (id: string) => post<JudgmentTaskRow>(`/voundry/portal/judgments/${id}/claim`);
export const decideJudgment = (id: string, verdict: string, rationale: string) =>
  post<JudgmentRecordRow>(`/voundry/portal/judgments/${id}/decide`, { verdict, rationale });
export const myJudgments = () => get<MyJudgments>("/voundry/portal/my-judgments");
export interface CreditSummary {
  deliverable: { records: CreditRow[]; approved_credits: number };
  judgment: JudgmentBalance;
  accuracy: number | null;
}
export const creditSummary = () => get<CreditSummary>("/voundry/portal/my-credit-summary");

// ---- Candidate board (contributor) ----
export interface CandidateTeaser {
  id: string; title: string; status: string; candidate_score: number;
  risk_level: string; contributor_interest_count: number; created_at: string;
}
export interface CandidateDetail {
  candidate: Candidate & { idea_id: string };
  idea: Record<string, unknown> | null;
  votes: { total: number; by_type: Record<string, number> };
  venture: Venture | null;
}
export const browseCandidates = () => get<CandidateTeaser[]>("/voundry/portal/browse-candidates");
export const contributorCandidateDetail = (id: string) =>
  get<CandidateDetail>(`/voundry/portal/candidates/${id}/contributor-detail`);

// ---- Transparency ----
export interface FeedEvent {
  id: string; at: string; action: string; resource_type: string;
  resource_id: string; resource_label: string; actor: string;
  actor_kind: "member" | "ai" | "system"; summary: string;
}
export const feed = (limit = 100) => get<FeedEvent[]>(`/voundry/portal/feed?limit=${limit}`);
export const publicFeed = (limit = 50) => get<FeedEvent[]>(`/voundry/public/feed?limit=${limit}`);
export const ventureTimeline = (ventureId: string) => get<FeedEvent[]>(`/voundry/portal/ventures/${ventureId}/timeline`);
export interface TrustPage { slug: string; title: string; body: string; }
export const trustPages = () => get<TrustPage[]>("/voundry/public/trust");
export const trustPage = (slug: string) => get<TrustPage>(`/voundry/public/trust/${slug}`);

// ---- Founder venture visibility ----
export interface MyVenture {
  idea: Idea & { status: string };
  candidate: Candidate | null;
  venture: Venture | null;
}
export const myVentures = () => get<MyVenture[]>("/voundry/portal/my-ventures");

// ---- Contributor profile ----
export interface ContributorProfile {
  id: string; contributor_id: string; display_name: string; tier: string;
  skills: string[]; credits_total: number;
}
export const myProfile = () => get<ContributorProfile>("/voundry/portal/my-profile");
export const updateProfile = (b: { display_name?: string; skills?: string[] }) =>
  post<ContributorProfile>("/voundry/portal/my-profile", b);

// ---- Public ----
export const publicLeaderboard = () => get<Candidate[]>("/voundry/public/leaderboard");
