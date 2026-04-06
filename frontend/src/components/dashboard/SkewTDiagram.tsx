"use client";

import { useRef, useEffect, useState, useCallback } from "react";

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */
export type SoundingLevel = {
  pressure: number;      // mb
  temperature: number;   // °C
  dewpoint: number;      // °C
  windSpeed: number;     // m/s
  windDirection: number; // degrees (meteorological, from)
  height: number;        // m
};

type Units = { altitude: "ft" | "m"; vario: "fpm" | "ms" };

type Props = {
  levels: SoundingLevel[];
  units: Units;
  title: string;
  onClose: () => void;
};

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */
const W = 420;
const H = 540;
const PAD = { top: 38, bottom: 38, left: 48, right: 58 };
const PW = W - PAD.left - PAD.right; // plot width
const PH = H - PAD.top - PAD.bottom; // plot height
const P_TOP = 200;
const P_BOT = 1050;
const T_MIN = -40; // °C
const T_MAX = 50;
const SKEW = 0.85;

/* ------------------------------------------------------------------ */
/* Coordinate transforms                                               */
/* ------------------------------------------------------------------ */
function pToY(p: number): number {
  return PAD.top + PH * (Math.log(p) - Math.log(P_TOP)) / (Math.log(P_BOT) - Math.log(P_TOP));
}

function yToP(y: number): number {
  const frac = (y - PAD.top) / PH;
  return Math.exp(Math.log(P_TOP) + frac * (Math.log(P_BOT) - Math.log(P_TOP)));
}

function tToX(t: number, p: number): number {
  const yFrac = (pToY(p) - PAD.top) / PH; // 0=top, 1=bottom
  const tFrac = (t - T_MIN) / (T_MAX - T_MIN);
  return PAD.left + (tFrac + SKEW * (1 - yFrac)) * PW / (1 + SKEW);
}

/* ------------------------------------------------------------------ */
/* Unit helpers                                                        */
/* ------------------------------------------------------------------ */
function cToF(c: number): number { return c * 9 / 5 + 32; }
function mToFt(m: number): number { return m * 3.28084; }
function msToKt(ms: number): number { return ms * 1.944; }

/** Dry adiabat: T at pressure p given theta (°C at 1000mb) */
function dryAdiabatT(theta_C: number, p: number): number {
  return (theta_C + 273.15) * Math.pow(p / 1000, 0.286) - 273.15;
}

/** Interpolate a field between two bracketing levels (log-p) */
function interpAtP(sorted: SoundingLevel[], p: number, field: keyof SoundingLevel): number | null {
  for (let i = 0; i < sorted.length - 1; i++) {
    const lo = sorted[i];     // higher pressure (lower alt)
    const hi = sorted[i + 1]; // lower pressure (higher alt)
    if (p <= lo.pressure && p >= hi.pressure) {
      const f = (Math.log(p) - Math.log(lo.pressure)) / (Math.log(hi.pressure) - Math.log(lo.pressure));
      return (lo[field] as number) + f * ((hi[field] as number) - (lo[field] as number));
    }
  }
  return null;
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */
export function SkewTDiagram({ levels, units, title, onClose }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [cursorY, setCursorY] = useState<number | null>(null);

  const useF = units.altitude === "ft";
  const useFt = units.altitude === "ft";
  const tUnit = useF ? "\u00b0F" : "\u00b0C";
  const dispT = (c: number) => useF ? Math.round(cToF(c)) : Math.round(c);
  const dispH = (m: number) => useFt ? Math.round(mToFt(m)).toLocaleString() : Math.round(m).toLocaleString();
  const hUnit = useFt ? "ft" : "m";

  // Sort: highest pressure (surface) first
  const sorted = [...levels].sort((a, b) => b.pressure - a.pressure);

  const draw = useCallback(() => {
    const cvs = canvasRef.current;
    if (!cvs) return;
    const dpr = window.devicePixelRatio || 1;
    cvs.width = W * dpr;
    cvs.height = H * dpr;
    cvs.style.width = `${W}px`;
    cvs.style.height = `${H}px`;
    const ctx = cvs.getContext("2d")!;
    ctx.scale(dpr, dpr);

    // Background
    ctx.fillStyle = "#f8fafc";
    ctx.fillRect(0, 0, W, H);

    // --- Clipped plot area ---
    ctx.save();
    ctx.beginPath();
    ctx.rect(PAD.left, PAD.top, PW, PH);
    ctx.clip();

    // Isotherms (tilted)
    for (let t = T_MIN; t <= T_MAX; t += 10) {
      ctx.strokeStyle = t === 0 ? "#94a3b8" : "#e2e8f0";
      ctx.lineWidth = t === 0 ? 1 : 0.5;
      ctx.beginPath();
      ctx.moveTo(tToX(t, P_BOT), pToY(P_BOT));
      ctx.lineTo(tToX(t, P_TOP), pToY(P_TOP));
      ctx.stroke();
    }

    // Dry adiabats
    ctx.strokeStyle = "rgba(234,179,8,0.25)";
    ctx.lineWidth = 0.7;
    for (let theta = -30; theta <= 80; theta += 10) {
      ctx.beginPath();
      let first = true;
      for (let p = P_BOT; p >= P_TOP; p -= 10) {
        const x = tToX(dryAdiabatT(theta, p), p);
        const y = pToY(p);
        if (first) { ctx.moveTo(x, y); first = false; } else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }

    // Temperature profile (red)
    if (sorted.length > 1) {
      ctx.strokeStyle = "#ef4444";
      ctx.lineWidth = 2.5;
      ctx.lineJoin = "round";
      ctx.beginPath();
      sorted.forEach((lev, i) => {
        const x = tToX(lev.temperature, lev.pressure);
        const y = pToY(lev.pressure);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.stroke();

      // Dew point profile (green)
      ctx.strokeStyle = "#16a34a";
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      sorted.forEach((lev, i) => {
        const x = tToX(lev.dewpoint, lev.pressure);
        const y = pToY(lev.pressure);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.stroke();
    }

    ctx.restore(); // unclip

    // --- Isobars & labels ---
    const isobars = [1000, 900, 800, 700, 600, 500, 400, 300, 200];
    ctx.font = "10px system-ui, sans-serif";
    for (const p of isobars) {
      const y = pToY(p);
      ctx.strokeStyle = "#e2e8f0";
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(PAD.left, y);
      ctx.lineTo(PAD.left + PW, y);
      ctx.stroke();
      ctx.fillStyle = "#64748b";
      ctx.textAlign = "right";
      ctx.fillText(`${p}`, PAD.left - 5, y + 3);
    }

    // Height labels on right for key levels
    ctx.textAlign = "left";
    ctx.fillStyle = "#94a3b8";
    ctx.font = "9px system-ui, sans-serif";
    for (const lev of sorted) {
      if ([1000, 925, 850, 700, 500, 300, 200].includes(lev.pressure)) {
        const y = pToY(lev.pressure);
        ctx.fillText(`${dispH(lev.height)}`, PAD.left + PW + 3, y + 3);
      }
    }

    // Temperature axis labels
    ctx.fillStyle = "#64748b";
    ctx.font = "9px system-ui, sans-serif";
    ctx.textAlign = "center";
    for (let t = T_MIN; t <= T_MAX; t += 10) {
      const x = tToX(t, P_BOT);
      if (x >= PAD.left - 5 && x <= PAD.left + PW + 5) {
        const label = useF ? `${Math.round(cToF(t))}` : `${t}`;
        ctx.fillText(label, x, PAD.top + PH + 14);
      }
    }
    ctx.fillText(`Temperature (${tUnit})`, W / 2, H - 6);

    // --- Wind barbs ---
    const barbX = PAD.left + PW + 38;
    ctx.lineWidth = 1.5;
    ctx.lineCap = "round";
    for (const lev of sorted) {
      // Only draw at key levels to avoid clutter
      if (![1000, 925, 850, 700, 600, 500, 400, 300, 250, 200].includes(lev.pressure)) continue;
      const y = pToY(lev.pressure);
      const dir = lev.windDirection;
      const spd = Math.round(msToKt(lev.windSpeed));
      const rad = (dir * Math.PI) / 180;
      const len = 10;
      const dx = Math.sin(rad);
      const dy = -Math.cos(rad);

      ctx.strokeStyle = "#334155";
      ctx.beginPath();
      ctx.moveTo(barbX, y);
      ctx.lineTo(barbX + dx * len, y + dy * len);
      // arrowhead
      const ha = 0.5;
      ctx.moveTo(barbX, y);
      ctx.lineTo(barbX + 4 * Math.sin(rad + Math.PI + ha), y - 4 * Math.cos(rad + Math.PI + ha));
      ctx.moveTo(barbX, y);
      ctx.lineTo(barbX + 4 * Math.sin(rad + Math.PI - ha), y - 4 * Math.cos(rad + Math.PI - ha));
      ctx.stroke();

      ctx.fillStyle = "#334155";
      ctx.font = "8px system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(`${spd}`, barbX, y - 12);
    }

    // --- Interactive cursor ---
    if (cursorY !== null && cursorY >= PAD.top && cursorY <= PAD.top + PH) {
      const p = yToP(cursorY);
      // Dashed horizontal line
      ctx.strokeStyle = "rgba(15,23,42,0.35)";
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(PAD.left, cursorY);
      ctx.lineTo(PAD.left + PW, cursorY);
      ctx.stroke();
      ctx.setLineDash([]);

      const tVal = interpAtP(sorted, p, "temperature");
      const tdVal = interpAtP(sorted, p, "dewpoint");
      const hVal = interpAtP(sorted, p, "height");

      if (tVal !== null && tdVal !== null) {
        // Temperature dot + label
        const tX = tToX(tVal, p);
        ctx.fillStyle = "#ef4444";
        ctx.beginPath(); ctx.arc(tX, cursorY, 4, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = "#0f172a";
        ctx.font = "bold 11px system-ui, sans-serif";
        ctx.textAlign = "left";
        // Background for readability
        const tLabel = `${dispT(tVal)}${tUnit}`;
        const tLabelW = ctx.measureText(tLabel).width;
        ctx.fillStyle = "rgba(255,255,255,0.85)";
        ctx.fillRect(tX + 6, cursorY - 14, tLabelW + 4, 16);
        ctx.fillStyle = "#ef4444";
        ctx.fillText(tLabel, tX + 8, cursorY - 2);

        // Dew point dot + label
        const tdX = tToX(tdVal, p);
        ctx.fillStyle = "#16a34a";
        ctx.beginPath(); ctx.arc(tdX, cursorY, 4, 0, Math.PI * 2); ctx.fill();
        const tdLabel = `${dispT(tdVal)}${tUnit}`;
        const tdLabelW = ctx.measureText(tdLabel).width;
        ctx.fillStyle = "rgba(255,255,255,0.85)";
        ctx.fillRect(tdX - tdLabelW - 10, cursorY - 14, tdLabelW + 4, 16);
        ctx.fillStyle = "#16a34a";
        ctx.textAlign = "right";
        ctx.fillText(tdLabel, tdX - 8, cursorY - 2);

        // Pressure + height label top-left
        ctx.fillStyle = "rgba(255,255,255,0.85)";
        const infoLabel = `${Math.round(p)} mb${hVal !== null ? ` \u00b7 ${dispH(hVal)} ${hUnit}` : ""}`;
        const infoW = ctx.measureText(infoLabel).width;
        ctx.fillRect(PAD.left + 2, cursorY - 18, infoW + 6, 14);
        ctx.fillStyle = "#475569";
        ctx.font = "10px system-ui, sans-serif";
        ctx.textAlign = "left";
        ctx.fillText(infoLabel, PAD.left + 5, cursorY - 7);
      }
    }

    // --- Title ---
    ctx.fillStyle = "#0f172a";
    ctx.font = "bold 12px system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(title, PAD.left, 16);

    // Legend
    ctx.font = "10px system-ui, sans-serif";
    const ly = 28;
    ctx.fillStyle = "#ef4444"; ctx.fillRect(PAD.left, ly - 5, 14, 3);
    ctx.fillStyle = "#64748b"; ctx.fillText("Temp", PAD.left + 18, ly);
    ctx.fillStyle = "#16a34a"; ctx.fillRect(PAD.left + 58, ly - 5, 14, 3);
    ctx.fillStyle = "#64748b"; ctx.fillText("Dew Pt.", PAD.left + 76, ly);

    // Surface callout
    if (sorted.length > 0) {
      const sfc = sorted[0];
      ctx.fillStyle = "#0f172a";
      ctx.font = "bold 10px system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(
        `${dispH(sfc.height)} ${hUnit}    ${dispT(sfc.temperature)}${tUnit}    Dp ${dispT(sfc.dewpoint)}${tUnit}    ${Math.round(msToKt(sfc.windSpeed))} kt`,
        W / 2, PAD.top + PH + 30
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sorted, units, cursorY, title]);

  useEffect(() => { draw(); }, [draw]);

  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={onClose}
        style={{ position: "absolute", top: 6, right: 6, width: 22, height: 22, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(15,23,42,0.08)", border: "none", borderRadius: 4, cursor: "pointer", fontSize: 14, color: "#64748b", zIndex: 2 }}
        title="Close"
      >{"\u00d7"}</button>
      <canvas
        ref={canvasRef}
        style={{ display: "block", cursor: "crosshair" }}
        onMouseMove={e => {
          const rect = e.currentTarget.getBoundingClientRect();
          setCursorY((e.clientY - rect.top) * (H / rect.height));
        }}
        onMouseLeave={() => setCursorY(null)}
      />
    </div>
  );
}
