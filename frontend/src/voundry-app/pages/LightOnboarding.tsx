import React from "react";
import * as api from "../api";
import {
  BpButton, BpPlate, BpStamp, notify,
  GREEN, INK, INK_SOFT, LINE, MONO, PAPER_2, SIENNA,
} from "../blueprint";

/* WACE Light — a short, guided first run for an enterprise seat:
 *   1 Basics   → connect your day-to-day tools (mail, ServiceNow, Zoom, Slack,
 *                 Teams, Microsoft 365) + the built-in governed AI.
 *   2 Role     → tell us what you do.
 *   3 Tools    → connect the specialized tools your role actually uses.
 *   4 Console  → drop into your workspace with everything WACE offers.
 * Connecting uses the existing governed flow, so every tool is read-only by
 * default, SAIb-scrubbed, and receipted. Tools that need credentials can be
 * finished later in the console — onboarding never blocks on them. */

type Step = "basics" | "role" | "tools" | "done";
type TileState = "idle" | "busy" | "connected" | "setup";

const CAT_GLYPH: Record<string, string> = {
  ai: "✦", email: "✉", comms: "◆", meeting: "◉", ticketing: "🎫",
  data: "▦", document: "🗎", web: "🌐", notify: "🔔", productivity: "◧",
};

function lightOnboardKey(accountId: string): string { return `wace_light_onboarded_${accountId}`; }
export function hasLightOnboarded(accountId: string): boolean {
  try { return localStorage.getItem(lightOnboardKey(accountId)) === "1"; } catch { return false; }
}

function Tile({ tile, state, onConnect }: { tile: api.ToolTile; state: TileState; onConnect: () => void }): React.ReactElement {
  const done = state === "connected" || tile.builtin;
  const setup = state === "setup";
  const border = done ? GREEN : setup ? "#9a7b16" : LINE;
  return (
    <div data-testid={`wace-tile-${tile.key}`} style={{
      border: `1px solid ${border}`, borderLeft: `3px solid ${border}`, background: PAPER_2,
      padding: "10px 12px", display: "flex", flexDirection: "column", gap: 6,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 15, color: INK }}>{CAT_GLYPH[tile.category] || "◦"}</span>
        <span style={{ flex: 1, fontFamily: MONO, fontSize: 12, fontWeight: 700, color: INK }}>{tile.name}</span>
        {done && <BpStamp value={tile.builtin ? "ready" : "connected"} />}
        {setup && <span style={{ fontFamily: MONO, fontSize: 8, color: "#9a7b16", border: "1px solid #9a7b1655", borderRadius: 3, padding: "0 5px" }}>finish in console</span>}
      </div>
      {tile.blurb && <div style={{ fontFamily: MONO, fontSize: 9.5, color: INK_SOFT, lineHeight: 1.5 }}>{tile.blurb.slice(0, 90)}</div>}
      {!done && (
        <BpButton tone={setup ? "ink" : "green"} data-testid={`wace-connect-${tile.key}`} disabled={state === "busy"} onClick={onConnect}>
          {state === "busy" ? "…" : setup ? "retry connect" : tile.needs_auth ? `connect ${tile.provider || tile.name}` : "connect"}
        </BpButton>
      )}
    </div>
  );
}

export function LightOnboarding({ accountId, onDone }: { accountId: string; onDone: (workUnitId: string) => void }): React.ReactElement {
  const [step, setStep] = React.useState<Step>("basics");
  const [suite, setSuite] = React.useState<api.OnboardingSuite | null>(null);
  const [wuId, setWuId] = React.useState<string>("");
  const [role, setRole] = React.useState<string>("");
  const [states, setStates] = React.useState<Record<string, TileState>>({});

  // Ensure a personal desk (default role) + load the basic suite up front.
  React.useEffect(() => {
    (async () => {
      try {
        const d = await api.ensureMyDesk("");
        setWuId(d.work_unit_id);
        setSuite(await api.onboardingSuite(""));
      } catch (e) { notify("sienna", (e as Error).message); }
    })();
  }, []);

  const connect = async (tile: api.ToolTile) => {
    if (tile.builtin || !wuId) return;
    setStates((s) => ({ ...s, [tile.key]: "busy" }));
    try {
      await api.connectTool(wuId, tile.key);
      setStates((s) => ({ ...s, [tile.key]: "connected" }));
    } catch {
      // Needs credentials (OAuth / base-url+token) — mark it and let them finish
      // in the console. Onboarding never blocks on a credentialed tool.
      setStates((s) => ({ ...s, [tile.key]: "setup" }));
    }
  };

  const pickRole = async (r: string) => {
    setRole(r);
    try {
      const d = await api.ensureMyDesk(r); setWuId(d.work_unit_id);
      setSuite(await api.onboardingSuite(r));
      setStep("tools");
    } catch (e) { notify("sienna", (e as Error).message); }
  };

  const finish = () => {
    try { localStorage.setItem(lightOnboardKey(accountId), "1"); } catch { /* ignore */ }
    onDone(wuId);
  };

  const rail = (["basics", "role", "tools", "done"] as Step[]);
  const railLabel: Record<Step, string> = { basics: "Basics", role: "Your role", tools: "Role tools", done: "Console" };

  return (
    <div style={{ maxWidth: 720, margin: "4vh auto 0" }} data-testid="wace-light-onboarding">
      <div style={{ textAlign: "center", marginBottom: 14 }}>
        <div style={{ fontFamily: MONO, color: INK, fontSize: 26, fontWeight: 800, letterSpacing: "0.3em" }}>
          <span style={{ color: "#1287A0" }}>W</span>ACE
        </div>
        <div style={{ fontFamily: MONO, color: INK_SOFT, fontSize: 10, letterSpacing: "0.16em", marginTop: 3 }}>
          LET'S CONNECT YOUR TOOLS — TWO MINUTES
        </div>
      </div>

      <div data-testid="wace-rail" style={{ display: "flex", gap: 6, justifyContent: "center", flexWrap: "wrap", marginBottom: 14 }}>
        {rail.map((s, i) => {
          const cur = s === step; const done = rail.indexOf(s) < rail.indexOf(step);
          const c = cur ? GREEN : done ? INK : INK_SOFT;
          return <span key={s} style={{ fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: c, border: `1px solid ${c}`, padding: "2px 9px", background: cur ? PAPER_2 : "transparent" }}>{i + 1} · {railLabel[s]}{done ? " ✓" : ""}</span>;
        })}
      </div>

      {step === "basics" && (
        <BpPlate title="Connect your day-to-day tools" plate="STEP 1 OF 4">
          <div style={{ padding: 14 }}>
            <div style={{ fontFamily: MONO, fontSize: 11, color: INK_SOFT, lineHeight: 1.6, marginBottom: 12 }}>
              These are the basics most seats use every day. Your <b style={{ color: INK }}>AI Assistant</b> is already on. Connect what you use — you can add or finish any of these later in the console. Everything is read-only by default, guarded, and receipted.
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 10 }}>
              {(suite?.basic || []).map((t) => <Tile key={t.key} tile={t} state={states[t.key] || "idle"} onConnect={() => void connect(t)} />)}
            </div>
            {!suite && <div style={{ fontFamily: MONO, fontSize: 10, color: INK_SOFT, padding: 8 }}>— loading —</div>}
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 14 }}>
              <BpButton tone="green" data-testid="wace-basics-next" onClick={() => setStep("role")}>Continue →</BpButton>
            </div>
          </div>
        </BpPlate>
      )}

      {step === "role" && (
        <BpPlate title="What do you do?" plate="STEP 2 OF 4">
          <div style={{ padding: 14 }}>
            <div style={{ fontFamily: MONO, fontSize: 11, color: INK_SOFT, lineHeight: 1.6, marginBottom: 12 }}>
              Pick your role and WACE will bring in the specialized tools it actually uses — and tune your desk's agents to match.
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 8 }}>
              {(suite?.roles || []).map((r) => (
                <button key={r} type="button" data-testid={`wace-role-${r}`} onClick={() => void pickRole(r)} style={{
                  textAlign: "left", cursor: "pointer", background: role === r ? PAPER_2 : "transparent",
                  border: `1px solid ${role === r ? INK : LINE}`, padding: "9px 11px", fontFamily: MONO,
                  fontSize: 11.5, fontWeight: 700, color: INK, textTransform: "capitalize",
                }}>{r.replace(/_/g, " ")}</button>
              ))}
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 14 }}>
              <BpButton data-testid="wace-role-back" onClick={() => setStep("basics")}>← Back</BpButton>
            </div>
          </div>
        </BpPlate>
      )}

      {step === "tools" && (
        <BpPlate title="Your role's specialized tools" plate="STEP 3 OF 4">
          <div style={{ padding: 14 }}>
            <div style={{ fontFamily: MONO, fontSize: 11, color: INK_SOFT, lineHeight: 1.6, marginBottom: 12 }}>
              Based on <b style={{ color: INK, textTransform: "capitalize" }}>{(role || "your role").replace(/_/g, " ")}</b>, here are the tools this role reaches for. Connect the ones you need.
            </div>
            {(suite?.specialized || []).length === 0
              ? <div style={{ fontFamily: MONO, fontSize: 10.5, color: INK_SOFT, padding: 8 }}>No extra tools needed beyond the basics for this role — you're all set.</div>
              : <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 10 }}>
                  {(suite?.specialized || []).map((t) => <Tile key={t.key} tile={t} state={states[t.key] || "idle"} onConnect={() => void connect(t)} />)}
                </div>}
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 14 }}>
              <BpButton data-testid="wace-tools-back" onClick={() => setStep("role")}>← Back</BpButton>
              <BpButton tone="green" data-testid="wace-tools-next" onClick={() => setStep("done")}>Continue →</BpButton>
            </div>
          </div>
        </BpPlate>
      )}

      {step === "done" && (
        <BpPlate title="You're set up" plate="STEP 4 OF 4">
          <div style={{ padding: 18, textAlign: "center" }}>
            <div style={{ fontFamily: MONO, fontSize: 30, color: GREEN, marginBottom: 8 }}>✓</div>
            <div style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: INK, marginBottom: 6 }}>Your WACE console is ready.</div>
            <div style={{ fontFamily: MONO, fontSize: 11, color: INK_SOFT, lineHeight: 1.6, maxWidth: 460, margin: "0 auto 16px" }}>
              Your workspace, connected tools, and governed AI agents are waiting. Drop a ticket, a file, or a question into the Smart Workspace and get to work — every action stays on the record.
            </div>
            <BpButton tone="green" data-testid="wace-enter-console" onClick={finish} style={{ padding: "9px 22px" }}>Enter my console →</BpButton>
            <div style={{ marginTop: 10 }}>
              <button type="button" data-testid="wace-done-back" onClick={() => setStep("tools")} style={{ background: "none", border: "none", color: INK_SOFT, cursor: "pointer", fontFamily: MONO, fontSize: 10, textDecoration: "underline" }}>← back to tools</button>
            </div>
          </div>
        </BpPlate>
      )}
      <div style={{ textAlign: "center", marginTop: 14, fontFamily: MONO, fontSize: 9, color: INK_SOFT }}>
        <span style={{ color: SIENNA }}>●</span> Governed · SAIb-guarded · receipted — the only AI workspace your compliance officer will approve.
      </div>
    </div>
  );
}
