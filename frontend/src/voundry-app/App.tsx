import React from "react";
import * as api from "./api";
import { AuthProvider, useAuth } from "./AuthContext";
import { AuthScreen } from "./pages/AuthScreen";
import { LightOnboarding, hasLightOnboarded } from "./pages/LightOnboarding";
import { WorkspacePage } from "./pages/WorkspacePage";
import { BpScreen, BpButton, BpStamp, BpToastHost, BpKeyframes, INK, INK_SOFT, MONO, PAPER_2 } from "./blueprint";

/* WACE Light — open-source individual edition. Sign in, connect your own tools
 * with your own LLM key, and work alongside a governed AI in a single console. */

export function WaceLogo({ size = 28 }: { size?: number }): React.ReactElement {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-label="WACE" style={{ display: "block", flexShrink: 0 }}>
      <rect x="3" y="3" width="58" height="58" rx="15" fill="#16315B" />
      <path d="M15 19 L23.5 44 L32 29.5 L40.5 44 L49 19" fill="none" stroke="#35D0E0" strokeWidth="4.4" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="32" cy="29.5" r="3.4" fill="#37C08A" />
      <line x1="15" y1="51" x2="49" y2="51" stroke="#35D0E0" strokeWidth="2.4" strokeLinecap="round" strokeOpacity="0.75" />
    </svg>
  );
}

function Console(): React.ReactElement {
  const { principal, logout } = useAuth();
  const [lightDone, setLightDone] = React.useState(false);
  // principal resolves asynchronously (after /auth/me), so read the onboarded
  // flag once it lands — not in a useState initializer while it's still null.
  React.useEffect(() => {
    if (principal) setLightDone(hasLightOnboarded(principal.account_id));
  }, [principal]);
  if (!principal) return <AuthScreen onBrowsePublic={() => undefined} />;
  if (!lightDone) {
    return (
      <BpScreen>
        <LightOnboarding accountId={principal.account_id} onDone={() => setLightDone(true)} />
        <BpToastHost /><BpKeyframes />
      </BpScreen>
    );
  }
  return (
    <BpScreen>
      <header style={{ border: `1.5px solid ${INK}`, background: PAPER_2, padding: "10px 14px", display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
          <WaceLogo size={28} />
          <span style={{ fontFamily: MONO, color: INK, fontSize: 18, fontWeight: 800, letterSpacing: "0.16em" }}>
            <span style={{ color: "#1287A0" }}>W</span>ACE
          </span>
          <span style={{ fontFamily: MONO, color: INK_SOFT, fontSize: 9, letterSpacing: "0.18em", textTransform: "uppercase" }}>Light</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, fontFamily: MONO, fontSize: 11, color: INK_SOFT }}>
          <BpStamp value={principal.role} />
          <span>{principal.display_name || principal.email}</span>
          <BpButton tone="sienna" onClick={logout} data-testid="voundry-logout" style={{ padding: "3px 10px" }}>Sign out</BpButton>
        </div>
      </header>
      <WorkspacePage />
      <BpToastHost /><BpKeyframes />
    </BpScreen>
  );
}

export function VoundryApp(): React.ReactElement {
  React.useEffect(() => {
    document.title = "WACE Light";
    (window as unknown as { __WACE_LIGHT__?: boolean }).__WACE_LIGHT__ = true;
  }, []);
  return (
    <AuthProvider>
      <Console />
    </AuthProvider>
  );
}

export default VoundryApp;
