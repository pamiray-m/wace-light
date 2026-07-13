/* STANDALONE preview harness for the Voundry app portals (Foundry Blueprint).
 * Stubs window.fetch + a token so the real App/portals render populated, with
 * ?view=auth|founder|contributor|investor|public selecting the surface.
 * UNTRACKED — do not commit. */
import { createRoot } from "react-dom/client";
import { VoundryApp } from "./App";
import { PublicLeaderboard } from "./pages/PublicLeaderboard";
import { BpScreen, BpButton } from "./blueprint";

const view = new URLSearchParams(location.search).get("view") || "auth";

const CAND = { id: "c1", title: "SignalForge AI", candidate_score: 92, ai_viability_score: 80, aos_strategic_fit_score: 80, risk_level: "low", status: "activated", contributor_interest_count: 5 };
const CAND2 = { id: "c2", title: "Aegis Compliance Copilot", candidate_score: 81, ai_viability_score: 78, aos_strategic_fit_score: 88, risk_level: "low", status: "activation_ready", contributor_interest_count: 6 };
const CAND3 = { id: "c3", title: "LedgerLoom", candidate_score: 64, ai_viability_score: 61, aos_strategic_fit_score: 58, risk_level: "medium", status: "voting", contributor_interest_count: 2 };
const VEN = { id: "v1", name: "SignalForge AI", status: "active", human_governor_id: "gov", created_at: "2026-06-27T10:05:00" };
const WU = (id: string, title: string, d: number, i: number) => ({ id, venture_unit_id: "v1", milestone_id: "m1", title, role_type: "engineering", difficulty_score: d, impact_score: i, estimated_credits_min: d * 75, estimated_credits_max: d * 200, evidence_required: ["url"], status: "open", assigned_to: null });
const MYWU = { ...WU("wu9", "MVP landing page", 3, 4), status: "assigned", assigned_to: "a1" };
const CREDIT = { id: "r1", work_unit_id: "wu1", base_points: 100, quality_multiplier: 1.3, impact_multiplier: 1.4, timeliness_multiplier: 1.1, scarcity_multiplier: 1.0, approval_confidence: 0.9, final_credits: 180, approval_status: "approved" };
const PLEDGE = { id: "p1", investor_id: "a1", venture_unit_id: "v1", pledge_type: "pledge_interest", amount: 50000, status: "pledged", legal_review_required: true, created_at: "2026-06-27T11:00:00" };
const PLEDGE2 = { id: "p2", investor_id: "a1", venture_unit_id: "v1", pledge_type: "watch", amount: null, status: "interest", legal_review_required: false, created_at: "2026-06-27T11:02:00" };
const IDEA = { id: "i1", title: "SignalForge AI", summary: "AI early market-signal platform for regulated enterprise teams.", status: "ai_screened", created_at: "2026-06-27T10:00:00" };
const RISK = "Voundry MVP does not offer public securities, equity, investment advice, or guaranteed returns. Investor actions represent interest, pledge intent, sponsorship, or milestone support only.";

function principal(role: string) {
  return { account_id: "a1", email: `${role}@example.com`, role, display_name: role[0].toUpperCase() + role.slice(1) + " Demo", contributor_id: role === "contributor" ? "a1" : null, investor_id: role === "investor" ? "a1" : null };
}

function body(path: string): unknown {
  if (path.endsWith("/auth/me")) return principal(view);
  if (path.endsWith("/my-ideas")) return [IDEA];
  if (path.endsWith("/portal/work-units")) return [WU("wu1", "Customer research brief", 2, 4), WU("wu2", "MVP landing page", 3, 4), WU("wu3", "Competitor scan", 2, 3)];
  if (path.endsWith("/my-work")) return [MYWU];
  if (path.endsWith("/my-credits")) return [CREDIT];
  if (path.endsWith("/portal/candidates")) return [CAND, CAND2, CAND3];
  if (path.endsWith("/portal/ventures")) return [VEN];
  if (path.endsWith("/my-pledges")) return [PLEDGE, PLEDGE2];
  if (path.endsWith("/risk-notice")) return { risk_notice: RISK };
  if (path.endsWith("/public/leaderboard")) return [CAND, CAND2, CAND3];
  return [];
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
(window as any).fetch = async (url: string) => ({ ok: true, json: async () => body(String(url)), text: async () => JSON.stringify(body(String(url))) });

try {
  if (view === "auth" || view === "public") localStorage.removeItem("voundry_token");
  else localStorage.setItem("voundry_token", "preview-token");
} catch { /* ignore */ }

const root = createRoot(document.getElementById("root")!);
if (view === "public") {
  root.render(<BpScreen><BpButton style={{ marginBottom: 14 }}>← Sign in</BpButton><PublicLeaderboard /></BpScreen>);
} else {
  root.render(<VoundryApp />);
}
