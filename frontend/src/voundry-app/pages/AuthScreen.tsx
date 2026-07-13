import React from "react";
import { useAuth } from "../AuthContext";
import * as api from "../api";
import type { Role } from "../api";
import { BpScreen, BpPlate, BpField, BpInput, BpButton, BpStamp, BpLogos, BpBrandFooter, BRAND, isWaceLight, INK, INK_SOFT, MONO, PAPER_2, LINE } from "../blueprint";

// Investor self-signup is hidden in the investor-less pivot (contributors +
// agents build ventures). The investor portal code is preserved for Phase 2.
const ROLES: { role: Role; label: string; blurb: string }[] = [
  { role: "founder", label: "Founder", blurb: "Submit venture ideas; track AI screening." },
  { role: "contributor", label: "Contributor", blurb: "Work with AI agents; earn credits for deliverables AND judgment." },
];

const RESET_TOKEN = new URLSearchParams(typeof location !== "undefined" ? location.search : "").get("reset");

export function AuthScreen({ onBrowsePublic }: { onBrowsePublic: () => void }): React.ReactElement {
  const { login, register, error } = useAuth();
  const light = isWaceLight();
  const [mode, setMode] = React.useState<"login" | "register" | "forgot" | "reset">(RESET_TOKEN ? "reset" : "login");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [name, setName] = React.useState("");
  // WACE Light seats are plain enterprise users — no founder/contributor choice.
  const [role, setRole] = React.useState<Role>(light ? "contributor" : "founder");
  const [agree, setAgree] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [notice, setNotice] = React.useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setNotice(null);
    try {
      if (mode === "login") await login(email, password);
      else if (mode === "register") await register(email, password, role, name, agree);
      else if (mode === "forgot") {
        const r = await api.requestPasswordReset(email);
        setNotice(r.detail); setMode("login");
      } else if (mode === "reset") {
        await api.resetPassword(RESET_TOKEN || "", password);
        setNotice("Password reset. You can sign in now."); setMode("login");
      }
    } catch (err) {
      if (mode === "forgot" || mode === "reset") setNotice(err instanceof Error ? err.message : "Failed");
    } finally { setBusy(false); }
  };

  return (
    <BpScreen>
      <div style={{ maxWidth: 440, margin: "6vh auto 0" }}>
        <div style={{ textAlign: "center", marginBottom: 18 }}>
          {/* Landing page: the parent logos are shown prominently. */}
          <div data-testid="landing-logos" style={{
            display: "flex", justifyContent: "center", alignItems: "center",
            gap: 4, marginBottom: 16,
          }}>
            <BpLogos height={52} label />
          </div>
          <div style={{ fontFamily: MONO, color: INK, fontSize: 30, fontWeight: 800, letterSpacing: "0.34em" }}>
            <span style={{ color: "#1287A0" }}>W</span>ACE
          </div>
          <div style={{ fontFamily: MONO, color: INK_SOFT, fontSize: 10.5, letterSpacing: "0.18em", textTransform: "uppercase", marginTop: 3 }}>
            {BRAND.tagline}
          </div>
          <div style={{ fontFamily: MONO, color: INK_SOFT, fontSize: 9.5, letterSpacing: "0.14em", marginTop: 6 }}>
            An <b style={{ color: INK }}>AOS-1</b> product · operated by <b style={{ color: INK }}>mAIb Tech</b>
          </div>
        </div>

        <BpPlate
          title={mode === "login" ? "Sign in" : mode === "register" ? "Create account" : mode === "forgot" ? "Reset password" : "Set a new password"}
          plate="ACCESS"
        >
          <form onSubmit={submit} data-testid="voundry-auth-form" style={{ padding: 14 }}>
            {mode === "register" && (
              <>
                <BpField label="Display name">
                  <BpInput value={name} onChange={(e) => setName(e.target.value)} placeholder="Ada Lovelace" />
                </BpField>
                {!light && (
                <BpField label="I am a">
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {ROLES.map((r) => (
                      <button key={r.role} type="button" onClick={() => setRole(r.role)} style={{
                        textAlign: "left", cursor: "pointer", background: role === r.role ? PAPER_2 : "transparent",
                        border: `1px solid ${role === r.role ? INK : LINE}`, padding: "7px 10px", fontFamily: MONO,
                      }}>
                        <span style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <strong style={{ color: INK, fontSize: 12 }}>{r.label}</strong>
                          {role === r.role && <BpStamp value="selected" />}
                        </span>
                        <span style={{ color: INK_SOFT, fontSize: 10.5 }}>{r.blurb}</span>
                      </button>
                    ))}
                  </div>
                </BpField>
                )}
              </>
            )}
            {mode !== "reset" && (
              <BpField label="Email">
                <BpInput type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" data-testid="auth-email" />
              </BpField>
            )}
            {mode !== "forgot" && (
              <BpField label={mode === "reset" ? "New password" : "Password"}>
                <BpInput type="password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" data-testid="auth-password" />
              </BpField>
            )}

            {mode === "register" && (
              <label style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 12, fontFamily: MONO, fontSize: 10.5, color: INK_SOFT, lineHeight: 1.5 }}>
                <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} data-testid="auth-consent" style={{ marginTop: 2 }} />
                <span>I agree to the WACE <b style={{ color: INK }}>Terms</b> and Trust Center: any contribution credits are non-transferable recognition units (not equity, securities, wages, or guaranteed returns); AI assists and humans approve all material decisions; my submitted work is governed by the work-unit IP terms.</span>
              </label>
            )}

            {error && <div style={{ color: "#9a3b2e", fontFamily: MONO, fontSize: 11, marginBottom: 10 }} data-testid="auth-error">⚠ {error}</div>}
            {notice && <div style={{ color: INK, fontFamily: MONO, fontSize: 11, marginBottom: 10 }} data-testid="auth-notice">{notice}</div>}

            <BpButton type="submit" tone="green" disabled={busy || (mode === "register" && !agree)} style={{ width: "100%", padding: "8px" }} data-testid="auth-submit">
              {busy ? "…" : mode === "login" ? "Sign in" : mode === "register" ? "Create account & enter"
                : mode === "forgot" ? "Email me a reset link" : "Set new password"}
            </BpButton>
          </form>

          <div style={{ padding: "0 14px 14px", display: "flex", justifyContent: "space-between", fontFamily: MONO, fontSize: 11, flexWrap: "wrap", gap: 8 }}>
            <button type="button" onClick={() => { setNotice(null); setMode(mode === "login" ? "register" : "login"); }}
              style={{ background: "none", border: "none", color: INK, cursor: "pointer", textDecoration: "underline" }} data-testid="auth-toggle">
              {mode === "login" ? "Need an account? Register" : "Have an account? Sign in"}
            </button>
            {mode === "login" && (
              <button type="button" onClick={() => { setNotice(null); setMode("forgot"); }}
                style={{ background: "none", border: "none", color: INK_SOFT, cursor: "pointer" }} data-testid="auth-forgot">
                Forgot password?
              </button>
            )}
            {!light && (
              <button type="button" onClick={onBrowsePublic}
                style={{ background: "none", border: "none", color: INK_SOFT, cursor: "pointer" }}>
                Browse ventures →
              </button>
            )}
          </div>
        </BpPlate>
        <BpBrandFooter />
      </div>
    </BpScreen>
  );
}
