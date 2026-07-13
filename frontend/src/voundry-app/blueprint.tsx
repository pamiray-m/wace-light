import React from "react";
import maibLogo from "@frontend/assets/maib-logo.png";
import aos1Logo from "@frontend/assets/aos1-logo.png";

/* Voundry "Foundry Blueprint" shared design system — used across every portal.
 * Parchment + blueprint grid, drafting-blue ink, monospace, drawing plates,
 * stamp-seal chips, score bars. */

export const INK = "#16315b";
export const INK_SOFT = "#51648a";
export const PAPER = "#efeadd";
export const PAPER_2 = "#e7e1d1";
export const LINE = "rgba(22,49,91,0.30)";
export const HAIR = "rgba(22,49,91,0.16)";
export const GRID = "rgba(22,49,91,0.07)";
export const SIENNA = "#9a3b2e";
export const GREEN = "#2f6b46";
export const MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

const TONE: Record<string, string> = {
  approved: GREEN, activated: GREEN, active: GREEN, achieved: GREEN, accepted: GREEN, verified: GREEN,
  pledged: INK, interest: INK, open: INK, submitted: INK, pending: INK_SOFT, voting: INK_SOFT,
  applicant: INK_SOFT, observer: INK_SOFT, ai_screened: INK,
  rejected: SIENNA, critical: SIENNA, disputed: SIENNA, killed: SIENNA, escalated: SIENNA,
  withdrawn: INK_SOFT, low: GREEN, medium: "#9a7b16", high: SIENNA,
  founder: INK, contributor: GREEN, investor: "#6b3fa0", operator: SIENNA,
};

export function toneOf(value: string): string {
  const k = (value || "").toLowerCase().replace(/[-\s]/g, "_");
  return TONE[k] ?? TONE[(value || "").toLowerCase()] ?? INK_SOFT;
}

/* ---------------------------------------------------------------------------
 * Colour system — coloured drafting pencils on parchment. Muted, on-theme
 * accents that give disciplines, item-types, and statuses their own colour so
 * a busy workspace is easy to scan. Each page also gets a signature ACCENT so
 * the app feels like a flowing sequence of rooms, not one repeated screen.
 * ------------------------------------------------------------------------ */

export const AMBER = "#9a7b16";
export const PLUM  = "#6b3fa0";

// Discipline → accent (used across the workspace for instant recognition).
export const DISCIPLINE_ACCENT: Record<string, string> = {
  marketing: "#c0603f", sales: "#5a7d3c", engineering: "#3a5a8c", design: "#7a4b8c",
  product: "#2f7d78", operations: "#9a7b16", research: "#46557f", data: "#2f6b78",
  finance: "#2f6b46", legal: "#7a3b4a", support: "#b07a2e", content: "#a63f6b",
  it_ops: "#2b8ca6",
};
export function accentFor(discipline: string): string {
  return DISCIPLINE_ACCENT[(discipline || "").toLowerCase()] ?? INK;
}

const DISCIPLINE_GLYPH: Record<string, string> = {
  marketing: "◈", sales: "↗", engineering: "⚙", design: "✎", product: "▢",
  operations: "⛭", research: "⌕", data: "▦", finance: "₵", legal: "§",
  support: "☎", content: "¶", it_ops: "▚",
};
export function disciplineGlyph(d: string): string {
  return DISCIPLINE_GLYPH[(d || "").toLowerCase()] ?? "⟐";
}

// Tool connect status → colour (ease-of-sight: green ready, amber setup, blue connect).
export function toolStatusColor(status: string): string {
  return status === "connected" ? GREEN : status === "needs_setup" ? AMBER : INK;
}

// Resource kind → colour so item TYPES read differently at a glance.
export function resourceKindColor(kind: string, accent: string): string {
  return kind === "playbook" ? accent
    : kind === "template" ? INK
    : kind === "checklist" ? GREEN
    : INK_SOFT;
}

/** Global keyframes for the "living instrument" agent cards. Mounted once in
 * the app shell. Motion is gated behind prefers-reduced-motion; the accent is
 * read from a per-card --acc custom property so each discipline glows its own
 * colour. On-theme: energised ink on parchment, not neon. */
export function BpKeyframes(): React.ReactElement {
  return <style>{`
    .vsk-agent{position:relative;overflow:hidden;transition:transform .22s ease,box-shadow .22s ease}
    .vsk-agent::before{content:"";position:absolute;inset:0;pointer-events:none;z-index:0;
      background:radial-gradient(150px 74px at 12% -12%, color-mix(in srgb, var(--acc,#16315b) 12%, transparent), transparent 72%)}
    .vsk-agent > *{position:relative;z-index:1}
    .vsk-sheen{position:absolute;top:0;bottom:0;left:-60%;width:45%;pointer-events:none;z-index:0;opacity:0;
      background:linear-gradient(100deg,transparent,color-mix(in srgb, var(--acc,#16315b) 16%, transparent),transparent)}
    .vsk-live::after{content:"";position:absolute;right:-2px;top:-2px;width:7px;height:7px;border-radius:50%;
      background:var(--acc,#2f6b46)}
    .vsk-think i{font-style:normal}
    @media (prefers-reduced-motion: no-preference){
      .vsk-agent:hover{transform:translateY(-2px);box-shadow:0 0 0 1px var(--acc,#16315b),5px 7px 0 rgba(22,49,91,.12)}
      .vsk-avatar{animation:vskFloat 4.5s ease-in-out infinite}
      .vsk-live::after{animation:vskPulse 2s ease-in-out infinite}
      .vsk-agent.run{box-shadow:0 0 0 1px var(--acc,#16315b)}
      .vsk-agent.run .vsk-sheen{opacity:1;animation:vskSheen 1.3s linear infinite}
      .vsk-agent.run .vsk-avatar{animation:vskSpin 2.4s linear infinite}
      .vsk-think i{animation:vskBlink 1.1s ease-in-out infinite;display:inline-block}
      .vsk-think i:nth-child(2){animation-delay:.18s}
      .vsk-think i:nth-child(3){animation-delay:.36s}
    }
    @keyframes vskFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-1.5px)}}
    @keyframes vskSpin{0%{box-shadow:0 0 0 1px var(--acc,#16315b)}50%{box-shadow:0 0 0 3px color-mix(in srgb,var(--acc,#16315b) 30%,transparent)}100%{box-shadow:0 0 0 1px var(--acc,#16315b)}}
    @keyframes vskPulse{0%{box-shadow:0 0 0 0 var(--acc,#2f6b46)}70%{box-shadow:0 0 0 6px transparent}100%{box-shadow:0 0 0 0 transparent}}
    @keyframes vskSheen{0%{left:-60%}100%{left:120%}}
    @keyframes vskBlink{0%,100%{opacity:.25}50%{opacity:1}}
  `}</style>;
}

/** A slim coloured page ribbon — gives each page a signature and a sense of place. */
export function BpRibbon(
  { accent = INK, label, sub }: { accent?: string; label: string; sub?: string },
): React.ReactElement {
  return (
    <div data-testid="page-ribbon" style={{
      display: "flex", alignItems: "baseline", gap: 10, marginBottom: 14,
      borderLeft: `4px solid ${accent}`, background: `${accent}12`,
      padding: "7px 12px",
    }}>
      <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 800, letterSpacing: "0.2em",
        textTransform: "uppercase", color: accent }}>{label}</span>
      {sub && <span style={{ fontFamily: MONO, fontSize: 10, color: INK_SOFT }}>{sub}</span>}
    </div>
  );
}

export function BpStamp({ value }: { value: string }): React.ReactElement {
  const c = toneOf(value);
  return (
    <span style={{
      display: "inline-block", fontFamily: MONO, fontSize: 9.5, fontWeight: 700,
      letterSpacing: "0.12em", textTransform: "uppercase", color: c,
      border: `1px solid ${c}`, boxShadow: `2px 2px 0 ${c}22`,
      padding: "1px 6px", borderRadius: 1, whiteSpace: "nowrap",
    }}>{value}</span>
  );
}

export function BpScoreBar({ n }: { n: number }): React.ReactElement {
  const filled = Math.max(0, Math.min(6, Math.round((n / 100) * 6)));
  return (
    <span style={{ fontFamily: MONO, color: INK, fontSize: 12, whiteSpace: "nowrap" }}>
      <span style={{ letterSpacing: "1px" }}>
        {"▓".repeat(filled)}<span style={{ color: HAIR }}>{"░".repeat(6 - filled)}</span>
      </span>{" "}<strong>{Number.isInteger(n) ? n : n.toFixed(0)}</strong>
    </span>
  );
}

export function BpButton(
  props: React.ButtonHTMLAttributes<HTMLButtonElement> & { tone?: "ink" | "green" | "sienna" },
): React.ReactElement {
  const { tone = "ink", style, children, ...rest } = props;
  const c = tone === "green" ? GREEN : tone === "sienna" ? SIENNA : INK;
  return (
    <button {...rest} style={{
      fontFamily: MONO, fontSize: 11, letterSpacing: "0.12em", textTransform: "uppercase",
      color: c, background: PAPER, border: `1px solid ${c}`, boxShadow: `2px 2px 0 ${c}22`,
      padding: "5px 14px", cursor: "pointer", ...style,
    }}>{children}</button>
  );
}

export function BpField(
  { label, children }: { label: string; children: React.ReactNode },
): React.ReactElement {
  return (
    <label style={{ display: "block", marginBottom: 12 }}>
      <span style={{ display: "block", fontFamily: MONO, fontSize: 9.5, fontWeight: 700,
        letterSpacing: "0.14em", textTransform: "uppercase", color: INK_SOFT, marginBottom: 4 }}>{label}</span>
      {children}
    </label>
  );
}

export function BpInput(props: React.InputHTMLAttributes<HTMLInputElement>): React.ReactElement {
  const { style, ...rest } = props;
  return (
    <input {...rest} style={{
      width: "100%", boxSizing: "border-box", fontFamily: MONO, fontSize: 13, color: INK,
      background: PAPER, border: `1px solid ${LINE}`, padding: "7px 9px", borderRadius: 1,
      outline: "none", ...style,
    }} />
  );
}

export const BpTextArea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function BpTextArea(props, ref): React.ReactElement {
    const { style, ...rest } = props;
    return (
      <textarea ref={ref} {...rest} style={{
        width: "100%", boxSizing: "border-box", fontFamily: MONO, fontSize: 13, color: INK,
        background: PAPER, border: `1px solid ${LINE}`, padding: "7px 9px", borderRadius: 1,
        outline: "none", minHeight: 64, resize: "vertical", ...style,
      }} />
    );
  },
);

export interface BpCol<T> { key: string; label: string; render?: (r: T) => React.ReactNode; }

export function BpPlate(props: {
  title: string; plate?: string; testid?: string; children: React.ReactNode;
  right?: React.ReactNode; accent?: string; glyph?: string;
}): React.ReactElement {
  const a = props.accent;
  return (
    <section data-testid={props.testid} style={{
      border: `1.5px solid ${INK}`,
      borderLeft: a ? `4px solid ${a}` : `1.5px solid ${INK}`,
      background: PAPER, boxShadow: `3px 3px 0 ${INK}1a`, marginBottom: 16,
    }}>
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "6px 10px", borderBottom: `1px solid ${LINE}`, background: a ? `${a}12` : PAPER_2 }}>
        <span style={{ fontFamily: MONO, color: INK, fontSize: 12, fontWeight: 700,
          letterSpacing: "0.18em", textTransform: "uppercase" }}>
          <span style={{ color: a ?? INK_SOFT, marginRight: 8 }}>{props.glyph ?? "⟐"}</span>{props.title}
        </span>
        {props.right ?? (props.plate ? <span style={{ fontFamily: MONO, color: a ?? INK_SOFT, fontSize: 9, letterSpacing: "0.15em" }}>{props.plate}</span> : null)}
      </header>
      {props.children}
    </section>
  );
}

export function BpTable<T>(props: {
  columns: BpCol<T>[]; rows: T[]; empty: string; loading?: boolean; error?: string | null;
}): React.ReactElement {
  const { columns, rows, empty, loading, error } = props;
  if (error) return <div style={{ padding: "10px 12px", fontFamily: MONO, fontSize: 11, color: SIENNA }}>⚠ {error}</div>;
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: MONO, fontSize: 11.5 }}>
      <thead><tr>{columns.map((c) => (
        <th key={c.key} style={{ textAlign: "left", padding: "6px 10px", color: INK_SOFT, fontSize: 9.5,
          fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase",
          borderBottom: `1px solid ${LINE}`, whiteSpace: "nowrap" }}>{c.label}</th>))}</tr></thead>
      <tbody>
        {rows.length === 0 ? (
          <tr><td colSpan={columns.length} style={{ padding: 12, color: INK_SOFT, fontStyle: "italic" }}>
            {loading ? "— loading —" : empty}</td></tr>
        ) : rows.map((r, i) => (
          <tr key={i} style={{ background: i % 2 ? "transparent" : "rgba(22,49,91,0.03)" }}>
            {columns.map((c) => (
              <td key={c.key} style={{ padding: "6px 10px", color: INK, borderBottom: `1px solid ${HAIR}`, verticalAlign: "top" }}>
                {c.render ? c.render(r) : String((r as Record<string, unknown>)[c.key] ?? "—")}
              </td>))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ---------------------------------------------------------------------------
 * Branding — Voundry is an AOS-1 venture, operated by mAIb Tech. Present it
 * consistently everywhere so the lineage (and the governance credibility it
 * carries) is visible on every page.
 * ------------------------------------------------------------------------ */

// WACE Light edition (wace.maib.io / wace.html) — detected via the entry-page
// flag, with a hostname fallback. Shared so any surface can branch on it.
export function isWaceLight(): boolean {
  if (typeof window === "undefined") return false;
  if ((window as unknown as { __WACE_LIGHT__?: boolean }).__WACE_LIGHT__ === true) return true;
  return (window.location.hostname.split(".")[0] || "").toLowerCase() === "wace";
}

export const BRAND = {
  product: "WACE",
  tagline: "The governed AI command environment",
  operator: "mAIb Tech",
  platform: "AOS-1",
  lineage: "An AOS-1 venture · operated by mAIb Tech",
} as const;

/** The two parent logos (mAIb + AOS-1), height-constrained. `prominent` is the
 * big landing-page treatment; the default footer size is small. */
export function BpLogos(
  { height = 22, label = false }: { height?: number; label?: boolean },
): React.ReactElement {
  const imgStyle: React.CSSProperties = { height, width: "auto", display: "block", objectFit: "contain" };
  return (
    <div data-testid="brand-logos" style={{ display: "inline-flex", alignItems: "center", gap: height * 0.6 }}>
      <span style={{ display: "inline-flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
        <img src={maibLogo} alt="mAIb Tech" title="mAIb Tech" style={imgStyle} />
        {label && <span style={{ fontFamily: MONO, fontSize: 8, color: INK_SOFT, letterSpacing: "0.1em" }}>OPERATOR</span>}
      </span>
      <span aria-hidden style={{ color: INK_SOFT, fontFamily: MONO, fontSize: height * 0.5 }}>×</span>
      <span style={{ display: "inline-flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
        <img src={aos1Logo} alt="AOS-1" title="AOS-1 Operating System" style={imgStyle} />
        {label && <span style={{ fontFamily: MONO, fontSize: 8, color: INK_SOFT, letterSpacing: "0.1em" }}>PLATFORM</span>}
      </span>
    </div>
  );
}

/** Small lineage chip: "AOS-1 · mAIb". Sits next to the wordmark in headers. */
export function BpBrandMark({ compact = false }: { compact?: boolean }): React.ReactElement {
  return (
    <span data-testid="brand-mark" style={{
      display: "inline-flex", alignItems: "center", gap: 6, fontFamily: MONO,
      fontSize: 8.5, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase",
      color: INK_SOFT, border: `1px solid ${LINE}`, padding: "2px 7px", whiteSpace: "nowrap",
    }}>
      <span style={{ color: INK }}>{BRAND.platform}</span>
      <span aria-hidden>·</span>
      <span>{compact ? "mAIb" : BRAND.operator}</span>
    </span>
  );
}

/** Footer strip: parent logos + the full lineage + governance line, shown on
 * every screen. On non-landing pages this is the only place the logos appear. */
export function BpBrandFooter(): React.ReactElement {
  return (
    <footer data-testid="brand-footer" style={{
      marginTop: 20, paddingTop: 12, borderTop: `1px solid ${HAIR}`,
      display: "flex", justifyContent: "space-between", alignItems: "center",
      flexWrap: "wrap", gap: 12, fontFamily: MONO, fontSize: 9.5, color: INK_SOFT,
    }}>
      <span style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <BpLogos height={20} />
        <span>
          <b style={{ color: INK, letterSpacing: "0.18em" }}>{BRAND.product}</b>{" "}
          — {BRAND.lineage}.
        </span>
      </span>
      <span style={{ letterSpacing: "0.06em" }}>
        Governed by the {BRAND.platform} stack · every decision on the record.
      </span>
    </footer>
  );
}

export function BpScreen({ children }: { children: React.ReactNode }): React.ReactElement {
  return (
    <div style={{
      minHeight: "100vh", background: PAPER,
      backgroundImage: `linear-gradient(${GRID} 1px, transparent 1px), linear-gradient(90deg, ${GRID} 1px, transparent 1px)`,
      backgroundSize: "24px 24px", padding: 18,
    }}>
      <div style={{ maxWidth: 1040, margin: "0 auto" }}>{children}</div>
    </div>
  );
}

export function BpBanner(
  { tone = "sienna", children, ...rest }:
  { tone?: "sienna" | "ink"; children: React.ReactNode; "data-testid"?: string },
): React.ReactElement {
  const c = tone === "ink" ? INK : SIENNA;
  return (
    <div {...rest} style={{ margin: "10px 12px", padding: "8px 12px", background: "#f6ecdf",
      border: `1px dashed ${c}`, color: c, fontFamily: MONO, fontSize: 10.5, lineHeight: 1.55 }}>
      {children}
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Toasts — visible confirmation for every action.
 * Any component calls notify("green" | "sienna" | "ink", "message"); the
 * BpToastHost (mounted once in the app shell) renders a bottom-right stack
 * with a slide-in and auto-dismiss. Errors linger longer than successes.
 * ------------------------------------------------------------------------ */

export type ToastTone = "green" | "sienna" | "ink";
export interface BpToast { id: number; tone: ToastTone; message: string; }

type ToastListener = (toasts: BpToast[]) => void;
let _toastSeq = 0;
let _toasts: BpToast[] = [];
const _listeners = new Set<ToastListener>();

function _emitToasts(): void {
  for (const fn of _listeners) fn([..._toasts]);
}

export function notify(tone: ToastTone, message: string): void {
  const toast: BpToast = { id: ++_toastSeq, tone, message };
  _toasts = [..._toasts, toast].slice(-4); // never stack more than 4
  _emitToasts();
  const ttl = tone === "sienna" ? 7000 : 4000;
  setTimeout(() => {
    _toasts = _toasts.filter((t) => t.id !== toast.id);
    _emitToasts();
  }, ttl);
}

export function dismissToast(id: number): void {
  _toasts = _toasts.filter((t) => t.id !== id);
  _emitToasts();
}

/** Test helper: clear the module-level toast store between test cases. */
export function clearToasts(): void {
  _toasts = [];
  _emitToasts();
}

const TOAST_GLYPH: Record<ToastTone, string> = { green: "✓", sienna: "⚠", ink: "⟐" };

export function BpToastHost(): React.ReactElement {
  const [toasts, setToasts] = React.useState<BpToast[]>([]);
  React.useEffect(() => {
    const fn: ToastListener = (t) => setToasts(t);
    _listeners.add(fn);
    return () => { _listeners.delete(fn); };
  }, []);
  return (
    <div data-testid="bp-toast-host" style={{
      position: "fixed", right: 16, bottom: 16, zIndex: 1000,
      display: "flex", flexDirection: "column", gap: 8, maxWidth: 380,
    }}>
      <style>{`@keyframes bpToastIn { from { transform: translateX(24px); opacity: 0; }
        to { transform: translateX(0); opacity: 1; } }`}</style>
      {toasts.map((t) => {
        const c = t.tone === "green" ? GREEN : t.tone === "sienna" ? SIENNA : INK;
        return (
          <div key={t.id} data-testid="bp-toast" role="status" onClick={() => dismissToast(t.id)} style={{
            fontFamily: MONO, fontSize: 11.5, lineHeight: 1.5, color: c, cursor: "pointer",
            background: PAPER, border: `1.5px solid ${c}`, boxShadow: `3px 3px 0 ${c}33`,
            padding: "9px 12px", animation: "bpToastIn 160ms ease-out",
          }}>
            <span style={{ fontWeight: 800, marginRight: 8 }}>{TOAST_GLYPH[t.tone]}</span>
            {t.message}
          </div>
        );
      })}
    </div>
  );
}
