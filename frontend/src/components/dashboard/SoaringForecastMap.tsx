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
  gfs: "gfs_seamless", nam3km: "nam_conus", nam: "nam_conus", rap: null, hrrr: "hrrr", nbm: null,
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
  { id: "convective_cloud_top",  label: "Top of Lift",             unit: "m",    unitType: "altitude", group: "Thermal / Lift",  variable: "convective_cloud_top",     legendMinVal: 0,   legendMaxVal: 5500, gradient: steppedGradient(["#9ca3af","#22c55e","#60a5fa","#a78bfa","#ec4899"]), colors: ["#9ca3af","#22c55e","#60a5fa","#a78bfa","#ec4899"], tierValues: [0, 1000, 2000, 3000, 4000, 5500], excludeModels: ["nbm"] },
  { id: "thermal_strength",      label: "Thermal Strength",        unit: "m/s",  unitType: "vario",    group: "Thermal / Lift",  variable: "thermal_updraft",          legendMinVal: 0,   legendMaxVal: 6.096, gradient: steppedGradient(["rgb(200,220,255)","rgb(130,180,240)","rgb(60,160,220)","rgb(40,180,140)","rgb(80,190,60)","rgb(180,210,40)","rgb(240,190,30)","rgb(230,110,20)","rgb(210,30,30)"]), colors: ["#c8dcff","#82b4f0","#3ca0dc","#28b48c","#50be3c","#b4d228","#f0be1e","#e66e14","#d21e1e"], tierValues: [0, 100, 200, 300, 400, 500, 700, 900, 1200], excludeModels: ["nbm"] },
  { id: "bsratio",               label: "B:S Ratio",               unit: "",     unitType: "none",     group: "Thermal / Lift",  variable: "bsratio",                  legendMinVal: 0,   legendMaxVal: 20,   gradient: steppedGradient(["#dc3c3c","#e68c28","#dcc828","#78c83c","#3cb48c","#2878c8"]), colors: ["#dc3c3c","#e68c28","#dcc828","#78c83c","#3cb48c","#2878c8"], tierValues: [0, 3, 5, 7, 10, 15, 20], excludeModels: ["nbm"] },
  { id: "wind_surface",          label: "Surface Wind",            unit: "kt",   unitType: "speed",    group: "Wind",            variable: "wind_speed_10m",           legendMinVal: 0,   legendMaxVal: 60,   gradient: steppedGradient(["#22c55e","#84cc16","#eab308","#f97316","#ef4444"]), colors: ["#22c55e","#eab308","#ef4444","#ef4444"], excludeModels: ["nbm"] },
  { id: "wind_850",              label: "Wind ~1500m (850hPa)",    unit: "kt",   unitType: "speed",    group: "Wind",            variable: "wind_speed_850hPa",        legendMinVal: 0,   legendMaxVal: 60,   gradient: steppedGradient(["#22c55e","#84cc16","#eab308","#f97316","#ef4444"]), colors: ["#22c55e","#eab308","#ef4444","#ef4444"], excludeModels: ["nbm"] },
  { id: "wind_700",              label: "Wind ~3000m (700hPa)",    unit: "kt",   unitType: "speed",    group: "Wind",            variable: "wind_speed_700hPa",        legendMinVal: 0,   legendMaxVal: 80,   gradient: steppedGradient(["#22c55e","#84cc16","#eab308","#f97316","#ef4444"]), colors: ["#22c55e","#eab308","#ef4444","#ef4444"], excludeModels: ["nbm"] },
  { id: "wind_500",              label: "Wind ~5500m (500hPa)",    unit: "kt",   unitType: "speed",    group: "Wind",            variable: "wind_speed_500hPa",        legendMinVal: 0,   legendMaxVal: 100,  gradient: steppedGradient(["#22c55e","#84cc16","#eab308","#f97316","#ef4444"]), colors: ["#22c55e","#eab308","#ef4444","#ef4444"], excludeModels: ["nbm"] },
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
const OVERLAY_SRC = "soaring-overlay-src";

function safeRemove(map: maplibregl.Map, blobRef?: React.MutableRefObject<string | null>) {
  try { if (map.getLayer(OVERLAY_LAYER)) map.removeLayer(OVERLAY_LAYER); } catch { /* */ }
  try { if (map.getSource(OVERLAY_SRC)) map.removeSource(OVERLAY_SRC); } catch { /* */ }
  if (blobRef?.current) { URL.revokeObjectURL(blobRef.current); blobRef.current = null; }
}

/* ------------------------------------------------------------------ */
/* Mini Skew-T drawing (imperative, for popup canvas)                  */
/* ------------------------------------------------------------------ */
type SLevel = { pressure: number; temperature: number; dewpoint: number; windSpeed: number; windDirection: number; height: number };

const SK_W = 180, SK_H = 200;
const SK_PAD = { t: 20, b: 16, l: 28, r: 4 };
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
export function SoaringForecastMap({ units }: { units: Units }) {
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
  const [activeOverlay, setActiveOverlay] = useState<string>("convective_cloud_top");
  const [opacity, setOpacity] = useState(85);
  const [gridLoading, setGridLoading] = useState(false);
  const [mapReady, setMapReady] = useState(0);
  const [dataRange, setDataRange] = useState<{ min: number; max: number; mean: number; scale_min: number; scale_max: number } | null>(null);
  const [tiers, setTiers] = useState<{ value: number; color: string }[] | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);

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

  // Fetch raster overlay and display as image layer
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
    const url = `${api}/api/weather/raster?model=${activeModel}&date=${activeRun.date}&hour=${activeRun.hour}&fh=${fh}&variable=${ov.variable}`;

    let cancelled = false;

    fetch(url)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(async (data: { image: string; coordinates: [number, number][]; meta: Record<string, unknown>; data_range?: { min: number; max: number; mean: number; scale_min: number; scale_max: number }; tiers?: { value: number; color: string }[] }) => {
        if (cancelled) return;
        safeRemove(map, blobUrlRef);

        // Store data range and tier info for legend
        if (data.data_range) setDataRange(data.data_range);
        if (data.tiers) setTiers(data.tiers);

        // Convert base64 data URI to blob URL for MapLibre compatibility
        const b64 = (data.image as string).split(",")[1];
        const bin = atob(b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        const blob = new Blob([bytes], { type: "image/png" });
        const blobUrl = URL.createObjectURL(blob);

        // Wait for the image to actually load before adding to map
        await new Promise<void>((resolve, reject) => {
          const img = new Image();
          img.onload = () => resolve();
          img.onerror = () => reject(new Error("Image load failed"));
          img.src = blobUrl;
        });

        if (cancelled) { URL.revokeObjectURL(blobUrl); return; }

        blobUrlRef.current = blobUrl;
        try {
          const coords = data.coordinates as [[number, number], [number, number], [number, number], [number, number]];
          map.addSource(OVERLAY_SRC, {
            type: "image",
            url: blobUrl,
            coordinates: coords,
          });
          map.addLayer({
            id: OVERLAY_LAYER,
            type: "raster",
            source: OVERLAY_SRC,
            paint: {
              "raster-opacity": opacity / 100,
              "raster-fade-duration": 0,
            },
          });

        } catch (err) {
          console.warn("[SoaringForecast] raster layer error:", err);
          URL.revokeObjectURL(blobUrl);
        }
      })
      .catch(err => console.warn("[SoaringForecast] raster fetch error:", err))
      .finally(() => { if (!cancelled) setGridLoading(false); });

    return () => { cancelled = true; safeRemove(map, blobUrlRef); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeModel, activeOverlay, selectedTimeIdx, opacity, activeRun, validTimes, mapReady]);

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

  // Click handler — open popup with Skew-T
  const handleMapClick = useCallback((e: maplibregl.MapMouseEvent) => {
    const map = mapRef.current;
    if (!map) return;
    const { lat, lng } = e.lngLat;
    const useF = units.altitude === "ft";

    // Models that have sounding data
    const soundingModels = MODEL_IDS.filter(id => SOUNDING_MODEL[id] !== null);

    // Build popup container: info left + skew-t right
    const wrap = document.createElement("div");
    wrap.style.cssText = "display:flex;gap:0";

    // Left: info + model pills
    const info = document.createElement("div");
    info.style.cssText = "width:100px;padding:6px 8px;border-right:1px solid #e2e8f0;display:flex;flex-direction:column;justify-content:flex-start;gap:4px";

    const timeStr = formatVT(validTimes[selectedTimeIdx] || "");
    info.innerHTML =
      `<strong class="skt-active-label" style="font-size:0.75rem">${MODEL_LABELS[activeModel].label}</strong>` +
      `<p style="font-size:0.6rem;color:#64748b;margin:0;line-height:1.3">${timeStr}</p>` +
      `<p class="sounding-status" style="font-size:0.58rem;color:#94a3b8;margin:0">Loading\u2026</p>` +
      `<div class="skt-model-pills" style="display:flex;flex-direction:column;gap:2px;margin-top:auto"></div>`;
    wrap.appendChild(info);

    // Right: canvas
    const cvs = document.createElement("canvas");
    const dpr = window.devicePixelRatio || 1;
    cvs.width = SK_W * dpr; cvs.height = SK_H * dpr;
    cvs.style.cssText = `width:${SK_W}px;height:${SK_H}px;cursor:crosshair;display:block`;
    wrap.appendChild(cvs);

    const popup = new maplibregl.Popup({ closeButton: true, maxWidth: "330px" })
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
  }, [activeModel, selectedTimeIdx, validTimes, units]);

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

        {/* Overlay list */}
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

        {/* Opacity slider */}
        <div className={styles.section}>
          <p className={styles.sectionLabel}>Opacity</p>
          <div className={styles.opacityRow}>
            <input type="range" className={styles.opacitySlider} min={0} max={100} value={opacity} onChange={e => setOpacity(Number(e.target.value))} />
            <span className={styles.opacityVal}>{opacity}%</span>
          </div>
        </div>

      </div>

      {/* Map area — flex column: timeline on top, map below */}
      <div className={styles.mapContainer}>

        {/* Timeline bar */}
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

        {/* Map */}
        <div ref={containerRef} className={styles.mapFill} />

        {/* Loading indicator */}
        {gridLoading && (
          <div style={{ position: "absolute", top: 70, left: "50%", transform: "translateX(-50%)", background: "rgba(15,23,42,0.85)", color: "#e2e8f0", padding: "6px 18px", borderRadius: 8, fontSize: "0.8rem", zIndex: 10 }}>
            Loading {MODEL_LABELS[activeModel].label} data&hellip;
          </div>
        )}

        {/* Legend — vertical bar on the right side of the map */}
        {activeOv && (() => {
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
                    <div key={i} style={{ flex: 1, background: c }} />
                  ))}
                </div>
                {/* Labels — one per band, right-aligned to band center */}
                <div className={styles.mapLegendVerticalLabelsCol}>
                  {labelVals.map((v, i) => (
                    <div key={i} className={styles.mapLegendVerticalLabelSlot} style={{ flex: 1 }}>
                      <span className={styles.mapLegendVerticalLabel}>{v}</span>
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
