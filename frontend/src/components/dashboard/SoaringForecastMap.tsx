"use client";

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState, useCallback } from "react";
import styles from "./SoaringForecastMap.module.css";

type Units = { altitude: "ft" | "m"; vario: "fpm" | "ms" };

/* ------------------------------------------------------------------ */
/* API helper                                                          */
/* ------------------------------------------------------------------ */
function resolveApiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured?.startsWith("/")) return configured;
  if (typeof window !== "undefined") {
    if (configured) {
      try {
        const parsed = new URL(configured);
        if (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1") {
          return `${window.location.protocol}//${window.location.hostname}:${parsed.port || "8000"}`;
        }
      } catch { return configured; }
      return configured;
    }
    return "/backend";
  }
  return configured ?? "/backend";
}

/* ------------------------------------------------------------------ */
/* Model + overlay definitions                                         */
/* ------------------------------------------------------------------ */
const MODEL_IDS = ["gfs", "nam3km", "nam", "rap", "hrrr", "nbm"] as const;
type ModelId = (typeof MODEL_IDS)[number];

const MODEL_LABELS: Record<ModelId, { label: string; sub: string }> = {
  gfs:    { label: "GFS",     sub: "25km \u00b7 Global" },
  nam3km: { label: "NAM 3km", sub: "3km \u00b7 CONUS" },
  nam:    { label: "NAM",     sub: "12km \u00b7 N. America" },
  rap:    { label: "RAP",     sub: "13km \u00b7 N. America" },
  hrrr:   { label: "HRRR",    sub: "3km \u00b7 CONUS" },
  nbm:    { label: "NBM",     sub: "2.5km \u00b7 CONUS" },
};

/* Open-Meteo model IDs for sounding (pressure-level point forecast) */
const SOUNDING_MODEL: Record<ModelId, string | null> = {
  gfs: "gfs_seamless", nam3km: null, nam: null, rap: null, hrrr: "ncep_hrrr_conus", nbm: null,
};
const SOUNDING_PRESSURES = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200];

function dewpointFromRH(t: number, rh: number): number {
  const a = 17.27, b = 237.7;
  const alpha = (a * t) / (b + t) + Math.log(rh / 100);
  return (b * alpha) / (a - alpha);
}

type OverlayDef = {
  id: string;
  label: string;
  unit: string;
  unitType: "altitude" | "vario" | "none" | "percent" | "mm" | "speed" | "jkg";
  group: string;
  variable: string;
  legendMinVal: number;
  legendMaxVal: number;
  gradient: string;
  colors: string[];
  /** Fixed tier boundary values in display units (e.g. fpm for vario).
   *  One label per color band (length = colors.length). */
  tierValues?: number[];
  excludeModels?: string[];
};

/** Build a stepped/tiered CSS gradient from an array of color strings.
 *  Each color gets an equal-width discrete band with hard boundaries. */
function steppedGradient(colors: string[]): string {
  const n = colors.length;
  const stops: string[] = [];
  for (let i = 0; i < n; i++) {
    const pctStart = ((i / n) * 100).toFixed(1);
    const pctEnd = (((i + 1) / n) * 100).toFixed(1);
    stops.push(`${colors[i]} ${pctStart}% ${pctEnd}%`);
  }
  return `linear-gradient(to right,${stops.join(",")})`;
}

const OVERLAYS: OverlayDef[] = [
  { id: "convective_cloud_top",  label: "Cloud Top Height",             unit: "m",    unitType: "altitude", group: "Thermal / Lift",  variable: "convective_cloud_top",     legendMinVal: 0,   legendMaxVal: 6096, gradient: steppedGradient([
    "#645a78","#78649b","#a08cbe","#8278c8","#506ec8","#5a96d2","#64b9dc","#3cb4b4","#3cb98c","#46b45a",
    "#64c83c","#a0d232","#d2d232","#dcc846","#e1b432","#e6aa64","#dc9678","#d7a0a0","#c8c3c3","#d7d2d2","#f0f0e6"]),
    colors: [
      "#645a78","#78649b","#a08cbe","#8278c8","#506ec8","#5a96d2","#64b9dc","#3cb4b4","#3cb98c","#46b45a",
      "#64c83c","#a0d232","#d2d232","#dcc846","#e1b432","#e6aa64","#dc9678","#d7a0a0","#c8c3c3","#d7d2d2","#f0f0e6"],
    tierValues: [0, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000, 11000, 12000, 13000, 14000, 15000, 16000, 17000, 18000, 19000, 20000], excludeModels: ["nbm"] },
  { id: "thermal_strength",      label: "Thermal Strength",        unit: "m/s",  unitType: "vario",    group: "Thermal / Lift",  variable: "thermal_updraft",          legendMinVal: 0,   legendMaxVal: 6.096, gradient: steppedGradient(["rgb(200,220,255)","rgb(130,180,240)","rgb(60,160,220)","rgb(40,180,140)","rgb(80,190,60)","rgb(180,210,40)","rgb(240,190,30)","rgb(230,110,20)","rgb(210,30,30)"]), colors: ["#c8dcff","#82b4f0","#3ca0dc","#28b48c","#50be3c","#b4d228","#f0be1e","#e66e14","#d21e1e"], tierValues: [0, 100, 200, 300, 400, 500, 700, 900, 1200], excludeModels: ["nbm"] },
  { id: "bsratio",               label: "B:S Ratio",               unit: "",     unitType: "none",     group: "Thermal / Lift",  variable: "bsratio",                  legendMinVal: 0,   legendMaxVal: 20,   gradient: steppedGradient(["#dc3c3c","#e68c28","#dcc828","#78c83c","#3cb48c","#2878c8"]), colors: ["#dc3c3c","#e68c28","#dcc828","#78c83c","#3cb48c","#2878c8"], tierValues: [0, 3, 5, 7, 10, 15, 20], excludeModels: ["nbm"] },
  // Wind speed overlays removed — wind barb altitude slider covers all levels
];

/* ------------------------------------------------------------------ */
/* Unit helpers                                                        */
/* ------------------------------------------------------------------ */
function displayUnit(ov: OverlayDef, units: Units): string {
  if (ov.unitType === "altitude") return units.altitude === "ft" ? "ft" : "m";
  if (ov.unitType === "vario") return units.vario === "fpm" ? "ft/min" : "m/s";
  return ov.unit;
}

function legendValue(val: number, ov: OverlayDef, units: Units): string {
  let v = val;
  if (ov.unitType === "vario" && units.vario === "fpm") v = Math.round(val * 196.85);
  else if (ov.unitType === "altitude" && units.altitude === "ft") v = Math.round(val * 3.28084);
  else v = Math.round(val);
  const u = displayUnit(ov, units);
  return u ? `${v} ${u}` : String(v);
}

function formatVT(iso: string) {
  try { return new Date(iso).toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZoneName: "short" }); }
  catch { return iso; }
}

/* ------------------------------------------------------------------ */
/* Map layer IDs                                                       */
/* ------------------------------------------------------------------ */
const OVERLAY_LAYER = "soaring-overlay-layer";
const OVERLAY_LABELS_LAYER = "soaring-overlay-labels";
const OVERLAY_SRC = "soaring-overlay-src";

/** Convert raw SI value to display units for tier matching */
function rawToDisplay(rawValue: number, ov: OverlayDef): number {
  if (ov.unitType === "vario") return rawValue * 196.85;          // m/s → fpm
  if (ov.unitType === "altitude") return rawValue * 3.28084;      // m → ft
  return rawValue;
}

/** Discrete floor-step: find highest tierValue ≤ displayVal, return that tier's color */
function getDebugColor(rawValue: number, ov: OverlayDef): string {
  const displayVal = rawToDisplay(rawValue, ov);
  const tiers = ov.tierValues ?? [];
  const colors = ov.colors ?? [];
  let idx = 0;
  for (let i = tiers.length - 1; i >= 0; i--) {
    if (displayVal >= tiers[i]) { idx = i; break; }
  }
  return colors[Math.min(idx, colors.length - 1)] ?? "#888";
}

/** Format a raw value into a short display label */
function formatDebugLabel(rawValue: number, ov: OverlayDef): string {
  const dv = rawToDisplay(rawValue, ov);
  if (ov.unitType === "vario") return `${Math.round(dv)}`;
  if (ov.unitType === "altitude") return `${Math.round(dv).toLocaleString()}`;
  return dv.toFixed(1);
}

function safeRemove(map: maplibregl.Map, blobRef?: React.MutableRefObject<string | null>) {
  try { if (map.getLayer(OVERLAY_LABELS_LAYER)) map.removeLayer(OVERLAY_LABELS_LAYER); } catch { /* */ }
  try { if (map.getLayer(OVERLAY_LAYER)) map.removeLayer(OVERLAY_LAYER); } catch { /* */ }
  try { if (map.getSource(OVERLAY_SRC)) map.removeSource(OVERLAY_SRC); } catch { /* */ }
  if (blobRef?.current) { URL.revokeObjectURL(blobRef.current); blobRef.current = null; }
}

/* ------------------------------------------------------------------ */
/* Mini Skew-T drawing (imperative, for popup canvas)                  */
/* ------------------------------------------------------------------ */
type SLevel = { pressure: number; temperature: number; dewpoint: number; windSpeed: number; windDirection: number; height: number };

const SK_W = 135, SK_H = 200;
const SK_PAD = { t: 20, b: 16, l: 26, r: 3 };
const SK_PW = SK_W - SK_PAD.l - SK_PAD.r;
const SK_PH = SK_H - SK_PAD.t - SK_PAD.b;
const SK_PTOP = 200, SK_PBOT = 1050;
const SK_TMIN = -40, SK_TMAX = 50, SK_SKEW = 0.85;

function skPtoY(p: number) { return SK_PAD.t + SK_PH * (Math.log(p) - Math.log(SK_PTOP)) / (Math.log(SK_PBOT) - Math.log(SK_PTOP)); }
function skYtoP(y: number) { return Math.exp(Math.log(SK_PTOP) + ((y - SK_PAD.t) / SK_PH) * (Math.log(SK_PBOT) - Math.log(SK_PTOP))); }
function skTtoX(t: number, p: number) {
  const yf = (skPtoY(p) - SK_PAD.t) / SK_PH;
  return SK_PAD.l + ((t - SK_TMIN) / (SK_TMAX - SK_TMIN) + SK_SKEW * (1 - yf)) * SK_PW / (1 + SK_SKEW);
}
function skDryT(theta: number, p: number) { return (theta + 273.15) * Math.pow(p / 1000, 0.286) - 273.15; }
function skInterp(sorted: SLevel[], p: number, f: "temperature" | "dewpoint" | "height"): number | null {
  for (let i = 0; i < sorted.length - 1; i++) {
    if (p <= sorted[i].pressure && p >= sorted[i + 1].pressure) {
      const frac = (Math.log(p) - Math.log(sorted[i].pressure)) / (Math.log(sorted[i + 1].pressure) - Math.log(sorted[i].pressure));
      return (sorted[i][f] as number) + frac * ((sorted[i + 1][f] as number) - (sorted[i][f] as number));
    }
  }
  return null;
}

function drawMiniSkewT(ctx: CanvasRenderingContext2D, sorted: SLevel[], useF: boolean, cursorY: number | null) {
  const dT = (c: number) => useF ? Math.round(c * 9 / 5 + 32) : Math.round(c);
  const tU = useF ? "\u00b0F" : "\u00b0C";

  ctx.clearRect(0, 0, SK_W, SK_H);
  ctx.fillStyle = "#f8fafc";
  ctx.fillRect(0, 0, SK_W, SK_H);

  // Clip
  ctx.save();
  ctx.beginPath(); ctx.rect(SK_PAD.l, SK_PAD.t, SK_PW, SK_PH); ctx.clip();

  // Isotherms
  for (let t = SK_TMIN; t <= SK_TMAX; t += 10) {
    ctx.strokeStyle = t === 0 ? "#94a3b8" : "#e2e8f0";
    ctx.lineWidth = t === 0 ? 0.8 : 0.4;
    ctx.beginPath(); ctx.moveTo(skTtoX(t, SK_PBOT), skPtoY(SK_PBOT)); ctx.lineTo(skTtoX(t, SK_PTOP), skPtoY(SK_PTOP)); ctx.stroke();
  }

  // Dry adiabats
  ctx.strokeStyle = "rgba(234,179,8,0.2)"; ctx.lineWidth = 0.5;
  for (let th = -30; th <= 80; th += 10) {
    ctx.beginPath(); let first = true;
    for (let p = SK_PBOT; p >= SK_PTOP; p -= 15) {
      const x = skTtoX(skDryT(th, p), p), y = skPtoY(p);
      first ? ctx.moveTo(x, y) : ctx.lineTo(x, y); first = false;
    }
    ctx.stroke();
  }

  // Profiles
  if (sorted.length > 1) {
    // Temperature
    ctx.strokeStyle = "#ef4444"; ctx.lineWidth = 2; ctx.lineJoin = "round"; ctx.beginPath();
    sorted.forEach((l, i) => { const x = skTtoX(l.temperature, l.pressure), y = skPtoY(l.pressure); i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y); });
    ctx.stroke();
    // Dew point
    ctx.strokeStyle = "#16a34a"; ctx.lineWidth = 2; ctx.beginPath();
    sorted.forEach((l, i) => { const x = skTtoX(l.dewpoint, l.pressure), y = skPtoY(l.pressure); i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y); });
    ctx.stroke();
  }
  ctx.restore();

  // Isobars + labels
  ctx.font = "9px system-ui,sans-serif"; ctx.fillStyle = "#64748b"; ctx.textAlign = "right";
  for (const p of [1000, 850, 700, 500, 300]) {
    const y = skPtoY(p);
    ctx.strokeStyle = "#e2e8f0"; ctx.lineWidth = 0.4; ctx.beginPath(); ctx.moveTo(SK_PAD.l, y); ctx.lineTo(SK_PAD.l + SK_PW, y); ctx.stroke();
    ctx.fillText(`${p}`, SK_PAD.l - 3, y + 3);
  }

  // Cursor
  if (cursorY !== null && cursorY >= SK_PAD.t && cursorY <= SK_PAD.t + SK_PH) {
    const p = skYtoP(cursorY);
    ctx.strokeStyle = "rgba(15,23,42,0.3)"; ctx.lineWidth = 1; ctx.setLineDash([3, 2]);
    ctx.beginPath(); ctx.moveTo(SK_PAD.l, cursorY); ctx.lineTo(SK_PAD.l + SK_PW, cursorY); ctx.stroke();
    ctx.setLineDash([]);
    const tV = skInterp(sorted, p, "temperature"), tdV = skInterp(sorted, p, "dewpoint");
    if (tV !== null && tdV !== null) {
      const tX = skTtoX(tV, p), tdX = skTtoX(tdV, p);
      ctx.fillStyle = "#ef4444"; ctx.beginPath(); ctx.arc(tX, cursorY, 3, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "#16a34a"; ctx.beginPath(); ctx.arc(tdX, cursorY, 3, 0, Math.PI * 2); ctx.fill();
      ctx.font = "bold 9px system-ui,sans-serif";
      ctx.fillStyle = "#ef4444"; ctx.textAlign = "left"; ctx.fillText(`${dT(tV)}${tU}`, tX + 5, cursorY - 3);
      ctx.fillStyle = "#16a34a"; ctx.textAlign = "right"; ctx.fillText(`${dT(tdV)}${tU}`, tdX - 5, cursorY - 3);
    }
  }

  // Title
  ctx.fillStyle = "#64748b"; ctx.font = "9px system-ui,sans-serif"; ctx.textAlign = "left";
  ctx.fillText("Temp", SK_PAD.l + 2, 12);
  ctx.fillStyle = "#ef4444"; ctx.fillRect(SK_PAD.l + 30, 8, 10, 2);
  ctx.fillStyle = "#64748b"; ctx.fillText("Dew", SK_PAD.l + 46, 12);
  ctx.fillStyle = "#16a34a"; ctx.fillRect(SK_PAD.l + 68, 8, 10, 2);
}

/* ------------------------------------------------------------------ */
/* Types from backend                                                  */
/* ------------------------------------------------------------------ */
type RunInfo = { date: string; hour: string; valid_times: string[]; max_fxx: number; fxx_step: number };

/* ------------------------------------------------------------------ */
/* Timeline helpers                                                    */
/* ------------------------------------------------------------------ */

/** Group valid_times by UTC date string ("Mon 6", "Tue 7", etc.)
 *  startPct/endPct express position as % of the full time range */
type DayGroup = { label: string; startPct: number; widthPct: number };

function buildDayGroups(validTimes: string[]): DayGroup[] {
  if (validTimes.length < 2) {
    if (validTimes.length === 1) {
      const d = new Date(validTimes[0]);
      return [{ label: `${d.toLocaleDateString("en-US", { weekday: "short" })} ${d.getDate()}`, startPct: 0, widthPct: 100 }];
    }
    return [];
  }
  const startMs = new Date(validTimes[0]).getTime();
  const endMs = new Date(validTimes[validTimes.length - 1]).getTime();
  const spanMs = endMs - startMs;

  const groups: DayGroup[] = [];
  let currentDate = "";
  let groupStartMs = startMs;
  validTimes.forEach((iso, i) => {
    const d = new Date(iso);
    // Use local date for grouping
    const dateKey = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
    const label = `${d.toLocaleDateString("en-US", { weekday: "short" })} ${d.getDate()}`;
    if (dateKey !== currentDate) {
      if (currentDate !== "" && groups.length > 0) {
        const prevEndMs = new Date(validTimes[i - 1]).getTime();
        const boundaryMs = (prevEndMs + d.getTime()) / 2;
        groups[groups.length - 1].widthPct = ((boundaryMs - groupStartMs) / spanMs) * 100;
        groupStartMs = boundaryMs;
      }
      currentDate = dateKey;
      groups.push({ label, startPct: ((groupStartMs - startMs) / spanMs) * 100, widthPct: 0 });
    }
  });
  if (groups.length > 0) {
    groups[groups.length - 1].widthPct = 100 - groups[groups.length - 1].startPct;
  }
  return groups;
}

function getLocalHour(iso: string): number {
  return new Date(iso).getHours();
}

function getLocalMinute(iso: string): number {
  return new Date(iso).getMinutes();
}

/* Find closest index in validTimes to a target ISO datetime string */
function findClosestTimeIdx(validTimes: string[], target: string): number {
  if (validTimes.length === 0) return 0;
  const targetMs = new Date(target).getTime();
  let best = Infinity;
  let bestIdx = 0;
  validTimes.forEach((t, i) => {
    const diff = Math.abs(new Date(t).getTime() - targetMs);
    if (diff < best) { best = diff; bestIdx = i; }
  });
  return bestIdx;
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */
export function SoaringForecastMap({ units, overlayConfig }: { units: Units; overlayConfig?: Record<string, boolean> }) {
  const oc = overlayConfig;
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const blobUrlRef = useRef<string | null>(null);
  const targetTimeRef = useRef<string | null>(null);
  const timelineRef = useRef<HTMLDivElement>(null);
  const playTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isDraggingRef = useRef(false);

  const [activeModel, setActiveModel] = useState<ModelId>("gfs");
  const [activeRun, setActiveRun] = useState<RunInfo | null>(null);
  const [selectedTimeIdx, setSelectedTimeIdx] = useState(0);
  const [metaLoading, setMetaLoading] = useState(false);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [activeOverlay, setActiveOverlay] = useState<string>("thermal_strength");
  const [opacity, setOpacity] = useState(85);
  const [gridLoading, setGridLoading] = useState(false);
  const [mapReady, setMapReady] = useState(0);
  const [dataRange, setDataRange] = useState<{ min: number; max: number; mean: number; scale_min: number; scale_max: number } | null>(null);
  const [tiers, setTiers] = useState<{ value: number; color: string }[] | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [showWindBarbs, setShowWindBarbs] = useState(true);
  const [windBarbLevel, setWindBarbLevel] = useState("10m");
  const [barbBoundsKey, setBarbBoundsKey] = useState(0); // increments on moveend to trigger refetch
  const windBarbsRef = useRef<{ lat: number; lng: number; u: number; v: number }[]>([]);
  const barbCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const barbRafRef = useRef<number | null>(null);
  const barbLoadingRef = useRef(false);

  const validTimes = activeRun?.valid_times ?? [];

  // Init map
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const savedView = (() => {
      try {
        const raw = localStorage.getItem("aervyx-weather-map-view");
        if (raw) { const v = JSON.parse(raw); return { center: v.center, zoom: v.zoom }; }
      } catch { /* */ }
      return { center: [-98, 39] as [number, number], zoom: 4 };
    })();
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: { basemap: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256 } },
        layers: [{ id: "bg", type: "background", paint: { "background-color": "#e7eef5" } }, { id: "basemap", type: "raster", source: "basemap" }],
      },
      center: savedView.center, zoom: savedView.zoom,
      attributionControl: false,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 200, unit: "metric" }), "bottom-left");
    map.on("load", () => setMapReady(1));
    map.on("moveend", () => {
      const c = map.getCenter();
      localStorage.setItem("aervyx-weather-map-view", JSON.stringify({
        center: [c.lng, c.lat],
        zoom: map.getZoom(),
      }));
    });
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; setMapReady(0); };
  }, []);

  // Fetch available runs when model changes — snap to closest time, auto-select most recent
  useEffect(() => {
    setActiveRun(null);
    setMetaError(null); setMetaLoading(true);

    const api = resolveApiBase();
    fetch(`${api}/api/weather/available?model=${activeModel}`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((d: { model: string; runs: RunInfo[] }) => {
        if (d.runs.length === 0) { setMetaError("No runs available"); return; }
        const run = d.runs[0];
        setActiveRun(run);
        // Snap selectedTimeIdx to the saved target time if present
        if (targetTimeRef.current && run.valid_times.length > 0) {
          const snapIdx = findClosestTimeIdx(run.valid_times, targetTimeRef.current);
          setSelectedTimeIdx(snapIdx);
          targetTimeRef.current = null;
        } else {
          setSelectedTimeIdx(0);
        }
      })
      .catch((e: unknown) => setMetaError(String(e)))
      .finally(() => setMetaLoading(false));
  }, [activeModel]);

  // DEBUG: Fetch grid points and display as color-coded dots with value labels
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !activeRun) return;

    const vt = validTimes[selectedTimeIdx];
    if (!vt) return;
    const ov = OVERLAYS.find(o => o.id === activeOverlay);
    if (!ov) return;

    const runDt = new Date(`${activeRun.date.slice(0,4)}-${activeRun.date.slice(4,6)}-${activeRun.date.slice(6,8)}T${activeRun.hour}:00:00Z`);
    const vtDt = new Date(vt);
    const fh = Math.round((vtDt.getTime() - runDt.getTime()) / 3600000);

    setGridLoading(true);
    const api = resolveApiBase();
    // Debug: step=1 for all models (full native resolution), viewport-bounded
    const map2 = mapRef.current;
    const bounds = map2?.getBounds();
    const bboxParam = bounds ? `&lat_min=${bounds.getSouth().toFixed(2)}&lat_max=${bounds.getNorth().toFixed(2)}&lon_min=${bounds.getWest().toFixed(2)}&lon_max=${bounds.getEast().toFixed(2)}` : "";
    const url = `${api}/api/weather/grid?model=${activeModel}&date=${activeRun.date}&hour=${activeRun.hour}&fh=${fh}&variable=${ov.variable}&step=1${bboxParam}`;

    let cancelled = false;

    fetch(url)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((data: { type: string; features: { type: string; geometry: { type: string; coordinates: number[] }; properties: { value: number } }[]; meta: Record<string, unknown> }) => {
        if (cancelled) return;
        safeRemove(map, blobUrlRef);

        // Pre-compute color and label for each feature
        for (const f of data.features) {
          const raw = f.properties.value;
          (f.properties as Record<string, unknown>).color = getDebugColor(raw, ov);
          (f.properties as Record<string, unknown>).label = formatDebugLabel(raw, ov);
        }

        try {
          map.addSource(OVERLAY_SRC, {
            type: "geojson",
            data: data as unknown as GeoJSON.FeatureCollection,
          });

          // Circle layer — 12px radius (4x previous debug size), colored by tier
          map.addLayer({
            id: OVERLAY_LAYER,
            type: "circle",
            source: OVERLAY_SRC,
            paint: {
              "circle-radius": 12,
              "circle-color": ["get", "color"],
              "circle-opacity": opacity / 100,
              "circle-stroke-width": 0.5,
              "circle-stroke-color": "rgba(0,0,0,0.3)",
            },
          });

          // Text label layer — show the value on top of each dot
          map.addLayer({
            id: OVERLAY_LABELS_LAYER,
            type: "symbol",
            source: OVERLAY_SRC,
            layout: {
              "text-field": ["get", "label"],
              "text-size": 9,
              "text-font": ["Open Sans Regular", "Arial Unicode MS Regular"],
              "text-allow-overlap": true,
              "text-ignore-placement": true,
            },
            paint: {
              "text-color": "#000",
              "text-halo-color": "rgba(255,255,255,0.85)",
              "text-halo-width": 1,
            },
          });

          console.log(`[SoaringForecast] DEBUG: ${data.features.length} grid points rendered`);
        } catch (err) {
          console.warn("[SoaringForecast] debug layer error:", err);
        }
      })
      .catch(err => console.warn("[SoaringForecast] grid fetch error:", err))
      .finally(() => { if (!cancelled) setGridLoading(false); });

    return () => { cancelled = true; safeRemove(map, blobUrlRef); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeModel, activeOverlay, selectedTimeIdx, activeRun, validTimes, mapReady, barbBoundsKey]);

  // Update opacity without refetching
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    if (map.getLayer(OVERLAY_LAYER)) {
      map.setPaintProperty(OVERLAY_LAYER, "circle-opacity", opacity / 100);
    }
  }, [opacity, mapReady]);

  // Play/pause animation
  useEffect(() => {
    if (isPlaying && validTimes.length > 0) {
      playTimerRef.current = setInterval(() => {
        setSelectedTimeIdx(i => {
          const next = i + 1;
          if (next >= validTimes.length) return 0; // loop back
          return next;
        });
      }, 1000);
    } else {
      if (playTimerRef.current) { clearInterval(playTimerRef.current); playTimerRef.current = null; }
    }
    return () => { if (playTimerRef.current) { clearInterval(playTimerRef.current); playTimerRef.current = null; } };
  }, [isPlaying, validTimes.length]);

  /* ---------------------------------------------------------------- */
  /* Wind barb canvas overlay                                         */
  /* ---------------------------------------------------------------- */

  // Draw wind barbs on the canvas overlay using the current map projection
  const drawWindBarbs = useCallback(() => {
    const map = mapRef.current;
    const canvas = barbCanvasRef.current;
    if (!map || !canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    if (!showWindBarbs || windBarbsRef.current.length === 0) return;

    const dpr = window.devicePixelRatio || 1;
    ctx.save();
    ctx.scale(dpr, dpr);

    const cssW = W / dpr;
    const cssH = H / dpr;

    // Zoom-based density: skip points when zoomed out to avoid visual clutter.
    // At zoom ≥10 draw every point; zoomed out → progressively skip more.
    const zoom = map.getZoom();
    // Desired minimum pixel spacing between barbs (screen px)
    const MIN_PX_GAP = 28;
    // At high zoom one grid cell is many pixels → step=1.
    // At low zoom cells overlap → step increases.
    // Use a spatial grid to thin points: bucket by screen-pixel cell.
    const useSpatialThin = zoom < 10;
    const occupied = useSpatialThin ? new Set<string>() : null;

    let drawn = 0;
    for (const pt of windBarbsRef.current) {
      const px = map.project([pt.lng, pt.lat]);
      const x = px.x;
      const y = px.y;

      // Skip points outside the visible canvas area (with margin)
      if (x < -40 || x > cssW + 40 || y < -40 || y > cssH + 40) continue;

      // Spatial thinning: only draw one barb per MIN_PX_GAP×MIN_PX_GAP screen cell
      if (occupied) {
        const cellKey = `${Math.floor(x / MIN_PX_GAP)},${Math.floor(y / MIN_PX_GAP)}`;
        if (occupied.has(cellKey)) continue;
        occupied.add(cellKey);
      }

      drawn++;
      // Convert m/s to knots
      const speedKt = Math.sqrt(pt.u * pt.u + pt.v * pt.v) * 1.94384;

      // Meteorological convention: direction wind comes FROM (degrees clockwise from N)
      // atan2(-u, -v) gives direction wind comes from in math convention;
      // we add 180 to flip U/V to "from" direction
      const dirRad = Math.atan2(-pt.u, -pt.v); // radians, math convention (0=North)
      const dirDeg = (dirRad * 180 / Math.PI + 360) % 360;

      const color = "rgba(0,0,0,0.7)";

      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = 1.2;
      ctx.lineCap = "round";

      if (speedKt < 3) {
        // Calm: draw a small circle only
        ctx.beginPath();
        ctx.arc(x, y, 4, 0, Math.PI * 2);
        ctx.stroke();
        continue;
      }

      // Staff: line in the direction the wind comes FROM (into the wind)
      const STAFF_LEN = 18;
      const RAD = Math.PI / 180;
      // dirDeg: 0=from N, 90=from E, 180=from S, 270=from W
      // Screen: y increases downward, so "from N" means staff points upward (negative dy)
      const sinD = Math.sin(dirDeg * RAD);
      const cosD = Math.cos(dirDeg * RAD);

      // Staff tip (the end where barbs are placed)
      const tx = x + sinD * STAFF_LEN;
      const ty = y - cosD * STAFF_LEN;

      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(tx, ty);
      ctx.stroke();

      // Now draw barbs along the staff from tip toward base
      // Barb direction is to the LEFT of the staff (Northern Hemisphere convention)
      // Left of staff = perpendicular rotated -90 degrees from staff direction
      // Staff direction vector: (sinD, -cosD) in screen coords
      // Left perpendicular: rotate +90° in screen space: (-(-cosD), sinD) = (cosD, sinD) ... wait
      // In screen coords (y-down), rotate staff direction 90° CCW (which is left):
      //   (dx, dy) -> (-dy, dx)
      // Staff direction: dx=sinD, dy=-cosD
      // Left perp: -(-cosD), sinD) = (cosD, sinD)
      const BARB_W = 8;    // length of long barb
      const BARB_SHORT = 4; // length of short barb (5kt)
      const BARB_STEP = 5; // spacing along staff

      let remaining = speedKt;
      let pos = 0; // position along staff from tip

      // Place 50-kt flags first (triangles)
      while (remaining >= 50) {
        const bx = tx - sinD * pos;
        const by = ty + cosD * pos;
        const bx2 = tx - sinD * (pos + BARB_STEP);
        const by2 = ty + cosD * (pos + BARB_STEP);
        // Flag tip
        const ftx = bx + cosD * BARB_W;
        const fty = by + sinD * BARB_W;
        ctx.beginPath();
        ctx.moveTo(bx, by);
        ctx.lineTo(bx2, by2);
        ctx.lineTo(ftx, fty);
        ctx.closePath();
        ctx.fill();
        pos += BARB_STEP + 2;
        remaining -= 50;
      }

      // Add a gap after flags if any were drawn
      if (speedKt >= 50) pos += 2;

      // Long barbs (10kt each)
      while (remaining >= 10) {
        const bx = tx - sinD * pos;
        const by = ty + cosD * pos;
        ctx.beginPath();
        ctx.moveTo(bx, by);
        ctx.lineTo(bx + cosD * BARB_W, by + sinD * BARB_W);
        ctx.stroke();
        pos += BARB_STEP;
        remaining -= 10;
      }

      // Short barb (5kt)
      if (remaining >= 5) {
        const bx = tx - sinD * pos;
        const by = ty + cosD * pos;
        ctx.beginPath();
        ctx.moveTo(bx, by);
        ctx.lineTo(bx + cosD * BARB_SHORT, by + sinD * BARB_SHORT);
        ctx.stroke();
      }

      // Speed label — small text offset to the right of the base
      const labelText = Math.round(speedKt).toString();
      ctx.font = "bold 8px sans-serif";
      ctx.fillStyle = "rgba(0,0,0,0.65)";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText(labelText, x + 6, y + 10);
    }

    ctx.restore();
  }, [showWindBarbs]);

  // Schedule a redraw via rAF
  const scheduleDrawBarbs = useCallback(() => {
    if (barbRafRef.current !== null) return; // already scheduled
    barbRafRef.current = requestAnimationFrame(() => {
      barbRafRef.current = null;
      drawWindBarbs();
    });
  }, [drawWindBarbs]);

  // Create/resize the barb canvas when the map container mounts/resizes
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const canvas = document.createElement("canvas");
    canvas.style.cssText = "position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:3";
    container.appendChild(canvas);
    barbCanvasRef.current = canvas;

    const resizeCanvas = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = container.clientWidth;
      const h = container.clientHeight;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      scheduleDrawBarbs();
    };

    resizeCanvas();
    const ro = new ResizeObserver(resizeCanvas);
    ro.observe(container);

    return () => {
      ro.disconnect();
      canvas.remove();
      barbCanvasRef.current = null;
      if (barbRafRef.current !== null) { cancelAnimationFrame(barbRafRef.current); barbRafRef.current = null; }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Hook map move/zoom events to redraw barbs + refetch on moveend
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    const onMove = () => scheduleDrawBarbs();
    const onMoveEnd = () => setBarbBoundsKey(k => k + 1);
    map.on("move", onMove);
    map.on("zoom", onMove);
    map.on("moveend", onMoveEnd);
    return () => { map.off("move", onMove); map.off("zoom", onMove); map.off("moveend", onMoveEnd); };
  }, [mapReady, scheduleDrawBarbs]);

  // Fetch wind barb data when relevant params change
  useEffect(() => {
    if (!mapReady || !activeRun || !showWindBarbs) {
      if (!showWindBarbs) {
        windBarbsRef.current = [];
        scheduleDrawBarbs();
      }
      return;
    }
    if (activeModel === "nbm") {
      windBarbsRef.current = [];
      scheduleDrawBarbs();
      return;
    }

    const vt = validTimes[selectedTimeIdx];
    if (!vt) return;

    const runDt = new Date(`${activeRun.date.slice(0,4)}-${activeRun.date.slice(4,6)}-${activeRun.date.slice(6,8)}T${activeRun.hour}:00:00Z`);
    const fh = Math.round((new Date(vt).getTime() - runDt.getTime()) / 3600000);

    const map = mapRef.current;
    const api = resolveApiBase();
    // Send viewport bounds so backend returns only visible points
    const bounds = map?.getBounds();
    const bboxParam = bounds ? `&lat_min=${bounds.getSouth().toFixed(2)}&lat_max=${bounds.getNorth().toFixed(2)}&lon_min=${bounds.getWest().toFixed(2)}&lon_max=${bounds.getEast().toFixed(2)}` : "";
    const url = `${api}/api/weather/wind-barbs?model=${activeModel}&date=${activeRun.date}&hour=${activeRun.hour}&fh=${fh}&level=${windBarbLevel}${bboxParam}`;

    let cancelled = false;
    barbLoadingRef.current = true;

    fetch(url)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((data: { points: { lat: number; lng: number; u: number; v: number }[] }) => {
        if (cancelled) return;
        windBarbsRef.current = data.points ?? [];
        barbLoadingRef.current = false;
        scheduleDrawBarbs();
      })
      .catch(() => {
        if (!cancelled) { windBarbsRef.current = []; barbLoadingRef.current = false; scheduleDrawBarbs(); }
      });

    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeModel, activeRun, selectedTimeIdx, windBarbLevel, showWindBarbs, mapReady, validTimes, barbBoundsKey]);

  // Redraw when showWindBarbs toggles
  useEffect(() => { scheduleDrawBarbs(); }, [showWindBarbs, scheduleDrawBarbs]);

  // Click handler — open popup with Skew-T + point forecast values
  const handleMapClick = useCallback((e: maplibregl.MapMouseEvent) => {
    if (oc?.sounding_popup === false) return;
    const map = mapRef.current;
    if (!map) return;
    const { lat, lng } = e.lngLat;
    const useF = units.altitude === "ft";

    // Models that have sounding data
    const soundingModels = MODEL_IDS.filter(id => SOUNDING_MODEL[id] !== null);

    // Compute current fh for point value fetch
    const currentVt = validTimes[selectedTimeIdx];
    const currentOv = OVERLAYS.find(o => o.id === activeOverlay);
    let currentFh = 0;
    if (activeRun && currentVt) {
      const runDt = new Date(`${activeRun.date.slice(0,4)}-${activeRun.date.slice(4,6)}-${activeRun.date.slice(6,8)}T${activeRun.hour}:00:00Z`);
      currentFh = Math.round((new Date(currentVt).getTime() - runDt.getTime()) / 3600000);
    }

    // Build popup container: info left + skew-t right
    const wrap = document.createElement("div");
    wrap.style.cssText = "display:flex;gap:0";

    // Left: info + point values + model pills
    const info = document.createElement("div");
    info.style.cssText = "width:118px;padding:6px 8px;border-right:1px solid #e2e8f0;display:flex;flex-direction:column;justify-content:flex-start;gap:4px;overflow:hidden";

    const timeStr = formatVT(currentVt || "");
    info.innerHTML =
      `<strong class="skt-active-label" style="font-size:0.75rem">${MODEL_LABELS[activeModel].label}</strong>` +
      `<p style="font-size:0.6rem;color:#64748b;margin:0;line-height:1.3">${timeStr}</p>` +
      `<p class="sounding-status" style="font-size:0.58rem;color:#94a3b8;margin:0">Loading\u2026</p>` +
      `<div class="pt-values-table" style="display:flex;flex-direction:column;gap:1px;border-top:1px solid #e2e8f0;padding-top:4px;margin-top:2px"><span style="font-size:0.55rem;color:#94a3b8">Loading values\u2026</span></div>` +
      `<div class="skt-model-pills" style="display:flex;flex-direction:column;gap:2px;margin-top:auto"></div>`;
    wrap.appendChild(info);

    // Right: canvas
    const cvs = document.createElement("canvas");
    const dpr = window.devicePixelRatio || 1;
    cvs.width = SK_W * dpr; cvs.height = SK_H * dpr;
    cvs.style.cssText = `width:${SK_W}px;height:${SK_H}px;cursor:crosshair;display:block`;
    wrap.appendChild(cvs);

    const popup = new maplibregl.Popup({ closeButton: true, maxWidth: "290px" })
      .setLngLat([lng, lat])
      .setDOMContent(wrap)
      .addTo(map);

    // Sounding fetch + draw function (reusable for model switching)
    function fetchAndDrawSounding(modelId: ModelId) {
      const omModel = SOUNDING_MODEL[modelId];
      if (!omModel) return;

      // Update active label
      const lbl = info.querySelector(".skt-active-label") as HTMLElement;
      if (lbl) lbl.textContent = MODEL_LABELS[modelId].label;

      const st = info.querySelector(".sounding-status") as HTMLElement;
      if (st) st.textContent = "Loading\u2026";

      // Update pill active states
      info.querySelectorAll(".skt-pill").forEach(btn => {
        (btn as HTMLElement).style.background = (btn as HTMLElement).dataset.model === modelId ? "#2563eb" : "none";
        (btn as HTMLElement).style.color = (btn as HTMLElement).dataset.model === modelId ? "#fff" : "#64748b";
      });

      const tVars = SOUNDING_PRESSURES.map(p => `temperature_${p}hPa`).join(",");
      const rhVars = SOUNDING_PRESSURES.map(p => `relative_humidity_${p}hPa`).join(",");
      const wsVars = SOUNDING_PRESSURES.map(p => `windspeed_${p}hPa`).join(",");
      const wdVars = SOUNDING_PRESSURES.map(p => `winddirection_${p}hPa`).join(",");
      const ghVars = SOUNDING_PRESSURES.map(p => `geopotential_height_${p}hPa`).join(",");
      const hourly = [tVars, rhVars, wsVars, wdVars, ghVars].join(",");

      fetch(`https://api.open-meteo.com/v1/forecast?latitude=${lat.toFixed(4)}&longitude=${lng.toFixed(4)}&hourly=${hourly}&models=${omModel}&forecast_days=3&timezone=auto`)
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
        .then((d: { hourly?: Record<string, (number | null)[]> }) => {
          if (!d.hourly) throw new Error("No data");

          const vt = validTimes[selectedTimeIdx];
          const times = d.hourly.time as unknown as string[];
          let timeIdx = 0;
          if (vt && times) {
            const vtMs = new Date(vt).getTime();
            let best = Infinity;
            times.forEach((t, i) => { const diff = Math.abs(new Date(t).getTime() - vtMs); if (diff < best) { best = diff; timeIdx = i; } });
          }

          const levels: SLevel[] = [];
          for (const p of SOUNDING_PRESSURES) {
            const t = d.hourly[`temperature_${p}hPa`]?.[timeIdx];
            const rh = d.hourly[`relative_humidity_${p}hPa`]?.[timeIdx];
            const ws = d.hourly[`windspeed_${p}hPa`]?.[timeIdx];
            const wd = d.hourly[`winddirection_${p}hPa`]?.[timeIdx];
            const gh = d.hourly[`geopotential_height_${p}hPa`]?.[timeIdx];
            if (t == null || rh == null) continue;
            levels.push({ pressure: p, temperature: t, dewpoint: dewpointFromRH(t, rh), windSpeed: ws != null ? ws / 3.6 : 0, windDirection: wd ?? 0, height: gh ?? 0 });
          }

          const sorted = levels.sort((a, b) => b.pressure - a.pressure);
          if (st) {
            if (sorted.length < 3) { st.textContent = "Insufficient data"; return; }
            st.textContent = "";
          }

          // Draw
          const ctx = cvs.getContext("2d")!;
          ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
          drawMiniSkewT(ctx, sorted, useF, null);

          // Interactive cursor
          const moveHandler = (me: MouseEvent) => {
            const rect = cvs.getBoundingClientRect();
            const cy = (me.clientY - rect.top) * (SK_H / rect.height);
            const c2 = cvs.getContext("2d")!;
            c2.setTransform(dpr, 0, 0, dpr, 0, 0);
            drawMiniSkewT(c2, sorted, useF, cy);
          };
          const leaveHandler = () => {
            const c2 = cvs.getContext("2d")!;
            c2.setTransform(dpr, 0, 0, dpr, 0, 0);
            drawMiniSkewT(c2, sorted, useF, null);
          };
          // Remove old listeners by replacing canvas event listeners
          cvs.onmousemove = moveHandler;
          cvs.onmouseleave = leaveHandler;
        })
        .catch(() => {
          if (st) st.textContent = "Fetch failed";
        });
    }

    // Build model pills
    const pillContainer = info.querySelector(".skt-model-pills") as HTMLElement;
    soundingModels.forEach(id => {
      const btn = document.createElement("button");
      btn.className = "skt-pill";
      btn.dataset.model = id;
      btn.textContent = MODEL_LABELS[id].label;
      btn.style.cssText = `font-size:0.58rem;padding:2px 6px;border:1px solid #e2e8f0;border-radius:3px;cursor:pointer;background:${id === activeModel ? "#2563eb" : "none"};color:${id === activeModel ? "#fff" : "#64748b"};white-space:nowrap`;
      btn.addEventListener("click", () => fetchAndDrawSounding(id));
      pillContainer.appendChild(btn);
    });

    // Initial fetch
    const omModel = SOUNDING_MODEL[activeModel];
    if (!omModel) {
      const st = info.querySelector(".sounding-status") as HTMLElement;
      if (st) st.textContent = "No sounding for " + MODEL_LABELS[activeModel].label;
      // Auto-select first available model
      if (soundingModels.length > 0) fetchAndDrawSounding(soundingModels[0]);
    } else {
      fetchAndDrawSounding(activeModel);
    }

    popup.on("close", () => { /* no-op */ });

    // Fetch point forecast values for the active overlay across all models
    if (currentOv && activeRun) {
      const ptTable = info.querySelector(".pt-values-table") as HTMLElement;

      // Helper: convert a raw SI value to display string
      function fmtPointVal(rawVal: number, ov: OverlayDef, u: Units): string {
        let v = rawVal;
        const du = displayUnit(ov, u);
        if (ov.unitType === "vario" && u.vario === "fpm") v = Math.round(rawVal * 196.85);
        else if (ov.unitType === "altitude" && u.altitude === "ft") v = Math.round(rawVal * 3.28084);
        else if (ov.unitType === "speed") {
          // raw is m/s, overlay unit is kt
          v = Math.round(rawVal * 1.94384);
        } else {
          v = Math.round(rawVal * 10) / 10;
        }
        return du ? `${v} ${du}` : String(v);
      }

      const api = resolveApiBase();
      const ptUrl = `${api}/api/weather/point?lat=${lat.toFixed(5)}&lng=${lng.toFixed(5)}&variable=${currentOv.variable}&date=${activeRun.date}&hour=${activeRun.hour}&fh=${currentFh}`;

      fetch(ptUrl)
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
        .then((d: { values: { model: string; label: string; value: number; unit: string }[] }) => {
          if (!ptTable) return;
          if (!d.values || d.values.length === 0) {
            ptTable.style.display = "none";
            return;
          }
          ptTable.innerHTML = "";
          d.values.forEach(entry => {
            const row = document.createElement("div");
            const isActive = entry.model === activeModel;
            row.style.cssText = `display:flex;justify-content:space-between;align-items:baseline;gap:6px;padding:1px 3px;border-radius:3px;background:${isActive ? "#eff6ff" : "transparent"}`;
            const lbl = document.createElement("span");
            lbl.style.cssText = `font-size:0.58rem;color:${isActive ? "#1d4ed8" : "#64748b"};white-space:nowrap;font-weight:${isActive ? "600" : "400"}`;
            lbl.textContent = entry.label;
            const val = document.createElement("span");
            val.style.cssText = `font-size:0.6rem;color:${isActive ? "#1e40af" : "#0f172a"};font-weight:${isActive ? "700" : "500"};white-space:nowrap`;
            val.textContent = fmtPointVal(entry.value, currentOv, units);
            row.appendChild(lbl);
            row.appendChild(val);
            ptTable.appendChild(row);
          });
        })
        .catch(() => {
          if (ptTable) ptTable.style.display = "none";
        });
    }
  }, [activeModel, activeOverlay, activeRun, selectedTimeIdx, validTimes, units]);

  // Bind click handler
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const handler = (e: maplibregl.MapMouseEvent) => { handleMapClick(e); };
    map.on("click", handler);
    return () => { map.off("click", handler); };
  }, [handleMapClick]);

  /* ---------------------------------------------------------------- */
  /* Timeline interaction helpers                                      */
  /* ---------------------------------------------------------------- */
  const getIdxFromPointer = useCallback((clientX: number): number => {
    const el = timelineRef.current;
    if (!el || validTimes.length === 0) return 0;
    const rect = el.getBoundingClientRect();
    const frac = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    // Map frac to a timestamp, then find closest valid time
    const startMs = new Date(validTimes[0]).getTime();
    const endMs = new Date(validTimes[validTimes.length - 1]).getTime();
    const targetMs = startMs + frac * (endMs - startMs);
    let best = Infinity;
    let bestIdx = 0;
    validTimes.forEach((t, i) => {
      const diff = Math.abs(new Date(t).getTime() - targetMs);
      if (diff < best) { best = diff; bestIdx = i; }
    });
    return bestIdx;
  }, [validTimes]);

  const handleTimelinePointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    isDraggingRef.current = true;
    (e.currentTarget as HTMLDivElement).setPointerCapture(e.pointerId);
    const idx = getIdxFromPointer(e.clientX);
    setSelectedTimeIdx(idx);
    setIsPlaying(false);
  }, [getIdxFromPointer]);

  const handleTimelinePointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDraggingRef.current) return;
    const idx = getIdxFromPointer(e.clientX);
    setSelectedTimeIdx(idx);
  }, [getIdxFromPointer]);

  const handleTimelinePointerUp = useCallback(() => {
    isDraggingRef.current = false;
  }, []);

  const groups = [...new Set(OVERLAYS.map(o => o.group))];
  const activeOv = OVERLAYS.find(o => o.id === activeOverlay);
  const dayGroups = buildDayGroups(validTimes);

  /* ---------------------------------------------------------------- */
  /* Timeline rendering — position ticks by actual time               */
  /* ---------------------------------------------------------------- */
  // Compute time range for the full timeline
  const timeRangeMs = (() => {
    if (validTimes.length < 2) return { startMs: 0, spanMs: 1 };
    const startMs = new Date(validTimes[0]).getTime();
    const endMs = new Date(validTimes[validTimes.length - 1]).getTime();
    return { startMs, spanMs: Math.max(endMs - startMs, 1) };
  })();

  const timePct = (iso: string) => {
    const ms = new Date(iso).getTime();
    return ((ms - timeRangeMs.startMs) / timeRangeMs.spanMs) * 100;
  };

  const scrubberPct = validTimes[selectedTimeIdx]
    ? timePct(validTimes[selectedTimeIdx])
    : 0;


  return (
    <div className={styles.shell}>
      <div className={styles.leftPanel}>
        {/* Model selector */}
        {oc?.model_selector !== false && (
        <div className={styles.section}>
          <p className={styles.sectionLabel}>Model</p>
          <div className={styles.modelPills}>
            {MODEL_IDS.map((id) => (
              <button key={id}
                className={[styles.pill, id === activeModel ? styles.pillActive : ""].join(" ")}
                onClick={() => {
                  // Save current selected time before switching
                  if (validTimes[selectedTimeIdx]) {
                    targetTimeRef.current = validTimes[selectedTimeIdx];
                  }
                  setActiveModel(id);
                  // If current overlay is excluded for the new model, switch to first available
                  const curOv = OVERLAYS.find(o => o.id === activeOverlay);
                  if (curOv?.excludeModels?.includes(id)) {
                    const fallback = OVERLAYS.find(o => !o.excludeModels?.includes(id));
                    if (fallback) setActiveOverlay(fallback.id);
                  }
                }}
              >
                {MODEL_LABELS[id].label}<span className={styles.pillSub}>{MODEL_LABELS[id].sub}</span>
              </button>
            ))}
          </div>
        </div>
        )}

        {/* Overlay list */}
        {oc?.overlay_tabs !== false && (
        <div>
          {groups.map(group => (
            <div key={group}>
              <p className={styles.groupHeader}>{group}</p>
              {OVERLAYS.filter(o => o.group === group).map(ov => {
                const excluded = ov.excludeModels?.includes(activeModel) ?? false;
                return (
                <div key={ov.id}
                  className={[styles.overlayRow, ov.id === activeOverlay ? styles.overlayRowActive : ""].join(" ")}
                  onClick={() => { if (!excluded) setActiveOverlay(ov.id); }}
                  style={excluded ? { opacity: 0.35, pointerEvents: "none" } : undefined}
                >
                  <span>{ov.label}</span>
                  <span className={styles.overlayUnit}>{displayUnit(ov, units)}</span>
                </div>
                );
              })}
            </div>
          ))}
        </div>
        )}

        {/* Wind barbs */}
        {oc?.wind_barb_toggle !== false && (
        <div className={styles.section}>
          <p className={styles.sectionLabel}>Wind Barbs</p>
          <label className={styles.windBarbToggle}>
            <input
              type="checkbox"
              checked={showWindBarbs}
              onChange={e => setShowWindBarbs(e.target.checked)}
              style={{ marginRight: 6 }}
            />
            Show barbs
          </label>
          {showWindBarbs && (() => {
            const BARB_LEVELS: { id: string; hpa: string; altM: number; altFt: number }[] = [
              { id: "10m",    hpa: "Surface", altM: 10,   altFt: 33 },
              { id: "975hPa", hpa: "975 hPa", altM: 300,  altFt: 1000 },
              { id: "950hPa", hpa: "950 hPa", altM: 600,  altFt: 2000 },
              { id: "925hPa", hpa: "925 hPa", altM: 750,  altFt: 2500 },
              { id: "900hPa", hpa: "900 hPa", altM: 1000, altFt: 3300 },
              { id: "850hPa", hpa: "850 hPa", altM: 1500, altFt: 5000 },
              { id: "800hPa", hpa: "800 hPa", altM: 2000, altFt: 6500 },
              { id: "700hPa", hpa: "700 hPa", altM: 3000, altFt: 10000 },
              { id: "600hPa", hpa: "600 hPa", altM: 4200, altFt: 14000 },
              { id: "500hPa", hpa: "500 hPa", altM: 5500, altFt: 18000 },
            ];
            const useFt = units.altitude === "ft";
            const currentIdx = BARB_LEVELS.findIndex(l => l.id === windBarbLevel);
            const safeIdx = currentIdx === -1 ? 0 : currentIdx;
            const current = BARB_LEVELS[safeIdx];
            const altLabel = current.id === "10m"
              ? (useFt ? "33 ft" : "10 m")
              : (useFt ? `${current.altFt.toLocaleString()} ft` : `${current.altM.toLocaleString()} m`);
            const displayLabel = current.id === "10m"
              ? `Surface · ${altLabel}`
              : `${current.hpa} · ${altLabel}`;
            const isDisabled = activeModel === "nbm";
            return (
              <div className={styles.windBarbSliderWrap}>
                <div className={styles.windBarbSliderLabel} title={displayLabel}>
                  {displayLabel}
                </div>
                <div className={styles.windBarbSliderTrack}>
                  <input
                    type="range"
                    className={styles.windBarbSlider}
                    min={0}
                    max={BARB_LEVELS.length - 1}
                    step={1}
                    value={safeIdx}
                    disabled={isDisabled}
                    onChange={e => setWindBarbLevel(BARB_LEVELS[Number(e.target.value)].id)}
                  />
                </div>
              </div>
            );
          })()}
          {/* Color toggle and legend removed — barbs always black */}
        </div>
        )}

        {/* Opacity slider */}
        {oc?.opacity_slider !== false && (
        <div className={styles.section}>
          <p className={styles.sectionLabel}>Opacity</p>
          <div className={styles.opacityRow}>
            <input type="range" className={styles.opacitySlider} min={0} max={100} value={opacity} onChange={e => setOpacity(Number(e.target.value))} />
            <span className={styles.opacityVal}>{opacity}%</span>
          </div>
        </div>
        )}

      </div>

      {/* Map area — flex column: timeline on top, map below */}
      <div className={styles.mapContainer}>

        {/* Timeline bar */}
        {oc?.time_scrubber !== false && (
        <div className={styles.timelineBar}>
          {/* Play button */}
          <button
            className={styles.timelinePlayBtn}
            onClick={() => setIsPlaying(p => !p)}
            disabled={validTimes.length === 0}
            title={isPlaying ? "Pause" : "Play"}
          >
            {isPlaying ? (
              /* Pause icon */
              <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
                <rect x="2" y="1" width="4" height="12" rx="1"/>
                <rect x="8" y="1" width="4" height="12" rx="1"/>
              </svg>
            ) : (
              /* Play icon */
              <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
                <polygon points="2,1 12,7 2,13"/>
              </svg>
            )}
          </button>

          {/* Timeline track area */}
          <div className={styles.timelineTrackArea}>
            {/* Loading / error states */}
            {metaLoading && (
              <div className={styles.timelineStatus}>Loading model data&hellip;</div>
            )}
            {metaError && (
              <div className={styles.timelineStatus} style={{ color: "#f87171" }}>{metaError}</div>
            )}

            {validTimes.length > 0 && (
              <>
                {/* Day headers row */}
                <div className={styles.timelineDays}>
                  {dayGroups.map((dg) => (
                    <div
                      key={dg.label}
                      className={styles.timelineDayCell}
                      style={{ position: "absolute", left: `${dg.startPct}%`, width: `${dg.widthPct}%` }}
                    >
                      {dg.label}
                    </div>
                  ))}
                </div>

                {/* Hour ticks row — draggable */}
                <div
                  ref={timelineRef}
                  className={styles.timelineHours}
                  onPointerDown={handleTimelinePointerDown}
                  onPointerMove={handleTimelinePointerMove}
                  onPointerUp={handleTimelinePointerUp}
                  onPointerCancel={handleTimelinePointerUp}
                >
                  {/* Tick marks — only where data exists, local time labels */}
                  {validTimes.map((iso, i) => {
                    const h = getLocalHour(iso);
                    const m = getLocalMinute(iso);
                    // Only show ticks at round hours (skip sub-hour times)
                    if (m !== 0) return null;
                    const pct = timePct(iso);
                    const isMidnight = h === 0;
                    // Format as 12h: 12a, 3p, etc.
                    const ampm = h < 12 ? "a" : "p";
                    const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h;
                    const label = `${h12}${ampm}`;
                    return (
                      <div
                        key={i}
                        className={styles.timelineTick}
                        style={{ left: `${pct}%` }}
                      >
                        <div
                          className={[
                            styles.timelineTickMark,
                            isMidnight ? styles.timelineTickMidnight : "",
                            styles.timelineTickLabeled,
                          ].join(" ")}
                        />
                        <span className={styles.timelineTickLabel}>
                          {label}
                        </span>
                      </div>
                    );
                  })}

                  {/* Scrubber */}
                  <div
                    className={styles.timelineScrubber}
                    style={{ left: `${scrubberPct}%` }}
                  />
                </div>

                {/* Current time badge */}
                <div className={styles.timelineCurrentLabel}>
                  {validTimes[selectedTimeIdx]
                    ? formatVT(validTimes[selectedTimeIdx])
                    : ""}
                  {activeRun && (
                    <span className={styles.timelineRunBadge}>
                      {activeRun.date.slice(0,4)}-{activeRun.date.slice(4,6)}-{activeRun.date.slice(6,8)} {activeRun.hour}Z
                    </span>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
        )}

        {/* Map */}
        <div ref={containerRef} className={styles.mapFill} />

        {/* Loading indicator */}
        {gridLoading && (
          <div style={{ position: "absolute", top: 70, left: "50%", transform: "translateX(-50%)", background: "rgba(15,23,42,0.85)", color: "#e2e8f0", padding: "6px 18px", borderRadius: 8, fontSize: "0.8rem", zIndex: 10 }}>
            Loading {MODEL_LABELS[activeModel].label} data&hellip;
          </div>
        )}

        {/* Legend — vertical bar on the right side of the map */}
        {oc?.legend !== false && activeOv && (() => {
          // Build bands + labels from tierValues or tiers or evenly-spaced fallback
          // bandColors: highest-first (top of legend), labelVals: one per band (highest-first)
          let bandColors: string[];
          let labelVals: number[];

          if (activeOv.tierValues && activeOv.tierValues.length === activeOv.colors.length) {
            // Preferred: use predefined tier values (already in display units like fpm)
            bandColors = [...activeOv.colors].reverse();
            labelVals = [...activeOv.tierValues].reverse();
          } else if (tiers && tiers.length > 1) {
            // Backend tiers: convert physical values to display units
            bandColors = tiers.map(t => t.color).reverse();
            labelVals = [...tiers].reverse().map(tier => {
              let v = tier.value;
              if (activeOv.unitType === "vario" && units.vario === "fpm") v = Math.round(v * 196.85);
              else if (activeOv.unitType === "altitude" && units.altitude === "ft") v = Math.round(v * 3.28084);
              else v = Math.round(v);
              return v;
            });
          } else {
            // Last resort: evenly-spaced
            bandColors = [...activeOv.colors].reverse();
            const n = activeOv.colors.length;
            const minV = dataRange ? dataRange.scale_min : activeOv.legendMinVal;
            const maxV = dataRange ? dataRange.scale_max : activeOv.legendMaxVal;
            labelVals = [];
            for (let i = n - 1; i >= 0; i--) {
              let v = minV + (i / (n - 1)) * (maxV - minV);
              if (activeOv.unitType === "vario" && units.vario === "fpm") v = Math.round(v * 196.85);
              else if (activeOv.unitType === "altitude" && units.altitude === "ft") v = Math.round(v * 3.28084);
              else v = Math.round(v);
              labelVals.push(v);
            }
          }

          return (
            <div className={styles.mapLegendVertical}>
              <div className={styles.mapLegendVerticalInner}>
                {/* Color bar */}
                <div className={styles.mapLegendVerticalBar}>
                  {bandColors.map((c, i) => (
                    <div key={i} style={{ height: 18, background: c }} />
                  ))}
                </div>
                {/* Labels — one per band, right-aligned to band center */}
                <div className={styles.mapLegendVerticalLabelsCol}>
                  {labelVals.map((v, i) => (
                    <div key={i} className={styles.mapLegendVerticalLabelSlot} style={{ height: 18 }}>
                      <span className={styles.mapLegendVerticalLabel}>{v.toLocaleString()}</span>
                    </div>
                  ))}
                </div>
              </div>
              {/* Title — rotated vertically */}
              <p className={styles.mapLegendVerticalTitle}>
                {activeOv.label}{activeOv.unit ? ` (${displayUnit(activeOv, units)})` : ""}
              </p>
            </div>
          );
        })()}
      </div>
    </div>
  );
}
