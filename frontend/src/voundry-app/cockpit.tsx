import React from "react";
import { MONO } from "./blueprint";

/* WACE Cockpit — the lit console a contributor steps into to fly a desk.
 *
 * The Voundry hub stays "paper blueprint"; the room switches to this dark HUD
 * so entering a desk feels like sitting down at a workstation. Pure inline
 * styles + a keyframes block (motion gated by prefers-reduced-motion). The
 * per-desk discipline accent is threaded through as the "system signature
 * colour" so every desk lights up in its own hue. */

export const CK = {
  space:   "#070f1c",   // outside the console
  shell:   "#0a1728",   // console shell
  panel:   "#0d2036",   // instrument face
  panelHi: "#123152",   // raised / hover
  line:    "#204a72",   // panel edge
  lineSoft:"#16334f",   // hairline
  ink:     "#d8e8fc",   // primary readout (ice)
  inkSoft: "#8aa6ca",   // secondary
  inkDim:  "#5c789d",   // labels
  cyan:    "#38d6ec",   // HUD primary
  green:   "#37e0a1",   // nominal / live
  amber:   "#f7c453",   // caution
  red:     "#ff6f6b",   // alert
};

/* Animations — only run when the user hasn't asked for reduced motion. */
export function CkKeyframes(): React.ReactElement {
  return (
    <style>{`
      @media (prefers-reduced-motion: no-preference) {
        @keyframes ck-led   { 0%,100%{opacity:1} 50%{opacity:.35} }
        @keyframes ck-scan  { 0%{transform:translateY(-100%)} 100%{transform:translateY(2400%)} }
        @keyframes ck-sweep { 0%{left:-40%} 100%{left:120%} }
        @keyframes ck-tel   { 0%,100%{transform:scaleY(.35)} 50%{transform:scaleY(1)} }
        @keyframes ck-boot  { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:none} }
        .ck-led    { animation: ck-led 1.8s ease-in-out infinite; }
        .ck-panel  { animation: ck-boot .35s ease both; }
        .ck-scanline::after {
          content:""; position:absolute; left:0; right:0; height:14px; pointer-events:none;
          background:linear-gradient(180deg, transparent, ${CK.cyan}22, transparent);
          animation: ck-scan 6s linear infinite; opacity:.5;
        }
        .ck-sweep::before {
          content:""; position:absolute; top:0; bottom:0; width:35%; pointer-events:none;
          background:linear-gradient(90deg, transparent, var(--acc, ${CK.cyan})22, transparent);
          animation: ck-sweep 3.6s ease-in-out infinite;
        }
        .ck-tel i { animation: ck-tel .9s ease-in-out infinite; }
        .ck-tel i:nth-child(2){ animation-delay:.15s } .ck-tel i:nth-child(3){ animation-delay:.3s }
        .ck-tel i:nth-child(4){ animation-delay:.45s } .ck-tel i:nth-child(5){ animation-delay:.6s }
      }
      .ck-tel { display:inline-flex; align-items:flex-end; gap:2px; height:12px; }
      .ck-tel i { display:block; width:2px; height:100%; background:var(--acc, ${CK.cyan}); transform:scaleY(.4); transform-origin:bottom; }
    `}</style>
  );
}

/* 4 L-shaped corner brackets — the "instrument" tell. */
function Corners({ color }: { color: string }): React.ReactElement {
  const c: React.CSSProperties = { position: "absolute", width: 9, height: 9, borderColor: color, pointerEvents: "none" };
  return (
    <>
      <span style={{ ...c, top: -1, left: -1, borderTop: `2px solid ${color}`, borderLeft: `2px solid ${color}` }} />
      <span style={{ ...c, top: -1, right: -1, borderTop: `2px solid ${color}`, borderRight: `2px solid ${color}` }} />
      <span style={{ ...c, bottom: -1, left: -1, borderBottom: `2px solid ${color}`, borderLeft: `2px solid ${color}` }} />
      <span style={{ ...c, bottom: -1, right: -1, borderBottom: `2px solid ${color}`, borderRight: `2px solid ${color}` }} />
    </>
  );
}

export function CkLed({ color = CK.green, size = 8 }: { color?: string; size?: number }): React.ReactElement {
  return <span className="ck-led" style={{
    width: size, height: size, borderRadius: "50%", background: color,
    boxShadow: `0 0 6px ${color}, 0 0 2px ${color}`, display: "inline-block", flexShrink: 0,
  }} />;
}

export function CkStat({ label, value, color = CK.cyan, led }: {
  label: string; value: React.ReactNode; color?: string; led?: string;
}): React.ReactElement {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      {led && <CkLed color={led} size={7} />}
      <span style={{ fontFamily: MONO, fontSize: 8.5, color: CK.inkDim, letterSpacing: "0.14em", textTransform: "uppercase" }}>{label}</span>
      <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 800, color, textShadow: `0 0 8px ${color}66` }}>{value}</span>
    </span>
  );
}

/* Instrument panel — BpPlate-compatible API so the room swaps 1:1. */
export function CkPanel(props: {
  title: string; plate?: string; testid?: string; accent?: string;
  right?: React.ReactNode; glyph?: string; children: React.ReactNode;
}): React.ReactElement {
  const acc = props.accent || CK.cyan;
  return (
    <div data-testid={props.testid} className="ck-panel" style={{
      position: "relative", background: CK.panel, border: `1px solid ${CK.line}`,
      borderLeft: `3px solid ${acc}`, height: "100%",
      boxShadow: `inset 0 0 40px ${CK.space}, 0 0 0 1px ${CK.space}`,
      ["--acc" as string]: acc,
    } as React.CSSProperties}>
      <Corners color={acc} />
      <div style={{
        display: "flex", alignItems: "center", gap: 9, padding: "8px 12px",
        borderBottom: `1px solid ${CK.lineSoft}`,
        background: `linear-gradient(90deg, ${acc}1c, transparent 60%)`,
      }}>
        <CkLed color={acc} />
        {props.glyph && <span style={{ color: acc, fontSize: 14 }}>{props.glyph}</span>}
        <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 800, color: CK.ink,
          letterSpacing: "0.14em", textTransform: "uppercase", textShadow: `0 0 10px ${acc}55` }}>
          {props.title}
        </span>
        {props.plate && <span style={{
          fontFamily: MONO, fontSize: 8, fontWeight: 700, color: acc, letterSpacing: "0.14em",
          textTransform: "uppercase", border: `1px solid ${acc}`, padding: "1px 6px", background: `${acc}12`,
        }}>{props.plate}</span>}
        <span style={{ marginLeft: "auto" }}>{props.right}</span>
      </div>
      {props.children}
    </div>
  );
}

/* Cockpit primary inputs/buttons. */
export function CkInput(props: React.InputHTMLAttributes<HTMLInputElement>): React.ReactElement {
  const { style, ...rest } = props;
  return <input {...rest} style={{
    fontFamily: MONO, fontSize: 12, color: CK.ink, background: CK.shell,
    border: `1px solid ${CK.line}`, padding: "7px 10px", outline: "none", boxSizing: "border-box",
    ...style,
  }} />;
}

export const CkTextArea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function CkTextArea(props, ref): React.ReactElement {
    const { style, ...rest } = props;
    return <textarea ref={ref} {...rest} style={{
      width: "100%", boxSizing: "border-box", fontFamily: MONO, fontSize: 12, color: CK.ink,
      background: CK.shell, border: `1px solid ${CK.line}`, padding: "8px 10px", outline: "none",
      resize: "vertical", minHeight: 46, ...style,
    }} />;
  },
);

export function CkButton(props: React.ButtonHTMLAttributes<HTMLButtonElement> & { tone?: "cyan" | "green" | "amber" | "red" | "ghost" }): React.ReactElement {
  const { tone = "ghost", style, ...rest } = props;
  const map = { cyan: CK.cyan, green: CK.green, amber: CK.amber, red: CK.red, ghost: CK.inkSoft };
  const c = map[tone];
  const solid = tone !== "ghost";
  return <button {...rest} style={{
    fontFamily: MONO, fontSize: 10.5, fontWeight: 700, letterSpacing: "0.06em", cursor: "pointer",
    color: solid ? CK.space : CK.ink, background: solid ? c : "transparent",
    border: `1px solid ${c}`, padding: "4px 12px", borderRadius: 0,
    boxShadow: solid ? `0 0 10px ${c}55` : "none", textShadow: solid ? "none" : `0 0 8px ${c}55`,
    ...style,
  }} />;
}

/* Small readout chip (credits, due date, etc.). */
export function CkChip({ color, label }: { color: string; label: string }): React.ReactElement {
  return <span style={{
    fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: "0.06em", color,
    border: `1px solid ${color}`, background: `${color}12`, padding: "1px 8px",
    textShadow: `0 0 6px ${color}55`,
  }}>{label}</span>;
}

/* Running telemetry bars (agent working indicator). */
export function CkTelemetry({ color }: { color: string }): React.ReactElement {
  return <span className="ck-tel" style={{ ["--acc" as string]: color } as React.CSSProperties}>
    <i /><i /><i /><i /><i />
  </span>;
}
