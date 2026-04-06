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
const MODEL_IDS = ["hrrr", "rap", "gfs", "nam", "nbm"] as const;
type ModelId = (typeof MODEL_IDS)[number];

const MODEL_LABELS: Record<ModelId, { label: string; sub: string }> = {
  hrrr: { label: "HRRR", sub: "3km \u00b7 CONUS" },
  rap:  { label: "RAP",  sub: "13km \u00b7 N. America" },
  gfs:  { label: "GFS",  sub: "25km \u00b7 Global" },
  nam:  { label: "NAM",  sub: "3-12km \u00b7 N. America" },
  nbm:  { label: "NBM",  sub: "2.5km \u00b7 CONUS" },
};

/* Open-Meteo model IDs for sounding (pressure-level point forecast) */
const SOUNDING_MODEL: Record<ModelId, string | null> = {
  hrrr: "hrrr", rap: null, gfs: "gfs_seamless", nam: "nam_conus", nbm: null,
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
  colors: [string, string, string, string];
  excludeModels?: string[];
};

const OVERLAYS: OverlayDef[] = [
  { id: "thermal_strength",      label: "Thermal Strength",        unit: "m/s",  unitType: "vario",    group: "Thermal / Lift",  variable: "vertical_velocity_700hPa", legendMinVal: 0,   legendMaxVal: 5,    gradient: "linear-gradient(to right,#3b82f6,#22c55e,#eab308,#ef4444)", colors: ["#3b82f6","#22c55e","#eab308","#ef4444"], excludeModels: ["nbm"] },
  { id: "cape",                  label: "CAPE",                    unit: "J/kg", unitType: "jkg",      group: "Thermal / Lift",  variable: "cape",                     legendMinVal: 0,   legendMaxVal: 2000, gradient: "linear-gradient(to right,#3b82f6,#22c55e,#eab308,#ef4444)", colors: ["#3b82f6","#22c55e","#eab308","#ef4444"] },
  { id: "convective_cloud_top",  label: "Top of Lift",             unit: "m",    unitType: "altitude", group: "Thermal / Lift",  variable: "convective_cloud_top",     legendMinVal: 0,   legendMaxVal: 7000, gradient: "linear-gradient(to right,#9ca3af,#22c55e,#60a5fa,#a78bfa,#ec4899)", colors: ["#9ca3af","#22c55e","#60a5fa","#ec4899"], excludeModels: ["nbm"] },
  { id: "boundary_layer_height", label: "Boundary Layer Height",   unit: "m",    unitType: "altitude", group: "Thermal / Lift",  variable: "boundary_layer_height",    legendMinVal: 0,   legendMaxVal: 5000, gradient: "linear-gradient(to right,#9ca3af,#22c55e,#60a5fa,#a78bfa,#ec4899)", colors: ["#9ca3af","#22c55e","#60a5fa","#ec4899"], excludeModels: ["nbm"] },
  { id: "lifted_index",          label: "Lifted Index",            unit: "",     unitType: "none",     group: "Thermal / Lift",  variable: "lifted_index",             legendMinVal: -8,  legendMaxVal: 4,    gradient: "linear-gradient(to right,#ef4444,#f97316,#22c55e,#3b82f6)", colors: ["#ef4444","#f97316","#22c55e","#3b82f6"], excludeModels: ["nbm"] },
  { id: "cloud_cover",           label: "Cloud Cover",             unit: "%",    unitType: "percent",  group: "Cloud / Weather", variable: "cloud_cover",              legendMinVal: 0,   legendMaxVal: 100,  gradient: "linear-gradient(to right,#f8fafc,#94a3b8,#1e293b,#0f172a)", colors: ["#f8fafc","#94a3b8","#1e293b","#0f172a"], excludeModels: ["nbm"] },
  { id: "precipitation",         label: "Precipitation",           unit: "mm",   unitType: "mm",       group: "Cloud / Weather", variable: "precipitation",            legendMinVal: 0,   legendMaxVal: 20,   gradient: "linear-gradient(to right,#f8fafc,#3b82f6,#7c3aed,#7c3aed)", colors: ["#f8fafc","#3b82f6","#7c3aed","#7c3aed"] },
  { id: "wind_surface",          label: "Surface Wind",            unit: "kt",   unitType: "speed",    group: "Wind",            variable: "wind_speed_10m",           legendMinVal: 0,   legendMaxVal: 60,   gradient: "linear-gradient(to right,#22c55e,#eab308,#ef4444,#ef4444)", colors: ["#22c55e","#eab308","#ef4444","#ef4444"], excludeModels: ["nbm"] },
  { id: "wind_850",              label: "Wind ~1500m (850hPa)",    unit: "kt",   unitType: "speed",    group: "Wind",            variable: "wind_speed_850hPa",        legendMinVal: 0,   legendMaxVal: 60,   gradient: "linear-gradient(to right,#22c55e,#eab308,#ef4444,#ef4444)", colors: ["#22c55e","#eab308","#ef4444","#ef4444"], excludeModels: ["nbm"] },
  { id: "wind_700",              label: "Wind ~3000m (700hPa)",    unit: "kt",   unitType: "speed",    group: "Wind",            variable: "wind_speed_700hPa",        legendMinVal: 0,   legendMaxVal: 80,   gradient: "linear-gradient(to right,#22c55e,#eab308,#ef4444,#ef4444)", colors: ["#22c55e","#eab308","#ef4444","#ef4444"], excludeModels: ["nbm"] },
  { id: "wind_500",              label: "Wind ~5500m (500hPa)",    unit: "kt",   unitType: "speed",    group: "Wind",            variable: "wind_speed_500hPa",        legendMinVal: 0,   legendMaxVal: 100,  gradient: "linear-gradient(to right,#22c55e,#eab308,#ef4444,#ef4444)", colors: ["#22c55e","#eab308","#ef4444","#ef4444"], excludeModels: ["nbm"] },
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

const SK_W = 240, SK_H = 260;
const SK_PAD = { t: 24, b: 20, l: 32, r: 8 };
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
/* Component                                                           */
/* ------------------------------------------------------------------ */
export function SoaringForecastMap({ units }: { units: Units }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const blobUrlRef = useRef<string | null>(null);

  const [activeModel, setActiveModel] = useState<ModelId>("hrrr");
  const [activeRun, setActiveRun] = useState<RunInfo | null>(null);
  const [selectedTimeIdx, setSelectedTimeIdx] = useState(0);
  const [metaLoading, setMetaLoading] = useState(false);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [activeOverlay, setActiveOverlay] = useState<string>("thermal_strength");
  const [opacity, setOpacity] = useState(85);
  const [gridLoading, setGridLoading] = useState(false);
  const [mapReady, setMapReady] = useState(0);
  const [dataRange, setDataRange] = useState<{ min: number; max: number; mean: number; p2: number; p98: number; scale_min: number; scale_max: number } | null>(null);
  const [showDebugLabels, setShowDebugLabels] = useState(false);

  const validTimes = activeRun?.valid_times ?? [];

  // Init map
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: { basemap: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "\u00a9 OpenStreetMap contributors" } },
        layers: [{ id: "bg", type: "background", paint: { "background-color": "#e7eef5" } }, { id: "basemap", type: "raster", source: "basemap" }],
      },
      center: [-98, 39], zoom: 4,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => setMapReady(1));
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; setMapReady(0); };
  }, []);

  // Fetch available runs when model changes — auto-select most recent
  useEffect(() => {
    setActiveRun(null); setSelectedTimeIdx(0);
    setMetaError(null); setMetaLoading(true);

    const api = resolveApiBase();
    fetch(`${api}/api/weather/available?model=${activeModel}`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((d: { model: string; runs: RunInfo[] }) => {
        if (d.runs.length === 0) { setMetaError("No runs available"); return; }
        setActiveRun(d.runs[0]);
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
      .then(async (data: { image: string; coordinates: [number, number][]; meta: Record<string, unknown>; data_range?: { min: number; max: number; mean: number; p2: number; p98: number; scale_min: number; scale_max: number }; debug_labels?: { lat: number; lon: number; val: number }[] }) => {
        if (cancelled) return;
        safeRemove(map, blobUrlRef);

        // Store data range for legend
        if (data.data_range) setDataRange(data.data_range);

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

          // Debug labels: add as a GeoJSON source + symbol layer
          const DEBUG_SRC = "soaring-debug-labels-src";
          const DEBUG_LAYER = "soaring-debug-labels-layer";
          try { if (map.getLayer(DEBUG_LAYER)) map.removeLayer(DEBUG_LAYER); } catch { /* */ }
          try { if (map.getSource(DEBUG_SRC)) map.removeSource(DEBUG_SRC); } catch { /* */ }

          if (data.debug_labels && data.debug_labels.length > 0) {
            map.addSource(DEBUG_SRC, {
              type: "geojson",
              data: {
                type: "FeatureCollection",
                features: data.debug_labels.map(lb => ({
                  type: "Feature" as const,
                  geometry: { type: "Point" as const, coordinates: [lb.lon, lb.lat] },
                  properties: { label: String(lb.val) },
                })),
              },
            });
            map.addLayer({
              id: DEBUG_LAYER,
              type: "symbol",
              source: DEBUG_SRC,
              layout: {
                "text-field": ["get", "label"],
                "text-size": 11,
                "text-allow-overlap": true,
                "text-ignore-placement": true,
              },
              paint: {
                "text-color": "#0f172a",
                "text-halo-color": "#ffffff",
                "text-halo-width": 1.5,
              },
              minzoom: 0,
              maxzoom: 24,
            });
            // Visibility based on debug toggle
            map.setLayoutProperty(DEBUG_LAYER, "visibility", "visible");
          }
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

  // Toggle debug label visibility
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const DEBUG_LAYER = "soaring-debug-labels-layer";
    try {
      if (map.getLayer(DEBUG_LAYER)) {
        map.setLayoutProperty(DEBUG_LAYER, "visibility", showDebugLabels ? "visible" : "none");
      }
    } catch { /* layer may not exist yet */ }
  }, [showDebugLabels, mapReady]);

  // Click handler — open popup with Skew-T
  const handleMapClick = useCallback((e: maplibregl.MapMouseEvent) => {
    const map = mapRef.current;
    if (!map) return;
    const { lat, lng } = e.lngLat;
    const useF = units.altitude === "ft";

    // Build popup container: info left + skew-t right
    const wrap = document.createElement("div");
    wrap.style.cssText = "display:flex;gap:0;min-height:260px";

    // Left: info
    const info = document.createElement("div");
    info.style.cssText = "width:130px;padding:8px 10px;border-right:1px solid #e2e8f0;display:flex;flex-direction:column;justify-content:center";
    info.innerHTML =
      `<strong style="font-size:0.82rem">${MODEL_LABELS[activeModel].label}</strong>` +
      `<p style="font-size:0.68rem;color:#64748b;margin:3px 0">${lat.toFixed(3)}\u00b0N<br>${Math.abs(lng).toFixed(3)}\u00b0${lng < 0 ? "W" : "E"}</p>` +
      `<p style="font-size:0.68rem;color:#64748b;margin:3px 0">${formatVT(validTimes[selectedTimeIdx] || "")}</p>` +
      `<p class="sounding-status" style="font-size:0.65rem;color:#94a3b8;margin:8px 0 0">Loading sounding\u2026</p>`;
    wrap.appendChild(info);

    // Right: canvas
    const cvs = document.createElement("canvas");
    const dpr = window.devicePixelRatio || 1;
    cvs.width = SK_W * dpr; cvs.height = SK_H * dpr;
    cvs.style.cssText = `width:${SK_W}px;height:${SK_H}px;cursor:crosshair;display:block`;
    wrap.appendChild(cvs);

    const popup = new maplibregl.Popup({ closeButton: true, maxWidth: "420px" })
      .setLngLat([lng, lat])
      .setDOMContent(wrap)
      .addTo(map);

    // Fetch sounding
    const omModel = SOUNDING_MODEL[activeModel];
    if (!omModel) {
      const st = info.querySelector(".sounding-status") as HTMLElement;
      if (st) st.textContent = "Sounding unavailable for " + MODEL_LABELS[activeModel].label;
      return;
    }

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

        // Find closest time index
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

        const st = info.querySelector(".sounding-status") as HTMLElement;
        if (sorted.length < 3) { if (st) st.textContent = "Insufficient data"; return; }
        if (st) st.textContent = "Hover chart for values";

        // Draw
        const ctx = cvs.getContext("2d")!;
        ctx.scale(dpr, dpr);
        drawMiniSkewT(ctx, sorted, useF, null);

        // Interactive cursor
        cvs.addEventListener("mousemove", (me) => {
          const rect = cvs.getBoundingClientRect();
          const cy = (me.clientY - rect.top) * (SK_H / rect.height);
          const c2 = cvs.getContext("2d")!;
          c2.setTransform(dpr, 0, 0, dpr, 0, 0);
          drawMiniSkewT(c2, sorted, useF, cy);
        });
        cvs.addEventListener("mouseleave", () => {
          const c2 = cvs.getContext("2d")!;
          c2.setTransform(dpr, 0, 0, dpr, 0, 0);
          drawMiniSkewT(c2, sorted, useF, null);
        });
      })
      .catch(() => {
        const st = info.querySelector(".sounding-status") as HTMLElement;
        if (st) st.textContent = "Sounding fetch failed";
      });

    // Clean up popup ref (MapLibre handles DOM removal)
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

  const groups = [...new Set(OVERLAYS.map(o => o.group))];
  const activeOv = OVERLAYS.find(o => o.id === activeOverlay);

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

        {/* Run info */}
        {activeRun && (
          <div className={styles.section} style={{ paddingTop: 6, paddingBottom: 6 }}>
            <p style={{ margin: 0, fontSize: "0.72rem", color: "var(--muted)" }}>
              Run: {activeRun.date} {activeRun.hour}Z &middot; {activeRun.fxx_step}h steps &middot; {validTimes.length} forecasts
            </p>
          </div>
        )}

        {/* Forecast time slider */}
        <div className={styles.section}>
          <p className={styles.sectionLabel}>Forecast Time</p>
          {metaLoading && <div className={styles.loadingState}>Loading model data\u2026</div>}
          {metaError && <div className={styles.errorBadge}>{metaError}</div>}
          {validTimes.length > 0 && (
            <>
              <p className={styles.timeLabel}>{formatVT(validTimes[selectedTimeIdx])}</p>
              <p className={styles.timeRef}>+{selectedTimeIdx * (activeRun?.fxx_step ?? 1)}h forecast</p>
              <div className={styles.timeNav}>
                <button className={styles.timeNavBtn} disabled={selectedTimeIdx === 0} onClick={() => setSelectedTimeIdx(i => Math.max(0, i - 1))}>{"\u2039"}</button>
                <input type="range" className={styles.timeSlider} min={0} max={validTimes.length - 1} value={selectedTimeIdx} onChange={e => setSelectedTimeIdx(Number(e.target.value))} />
                <button className={styles.timeNavBtn} disabled={selectedTimeIdx === validTimes.length - 1} onClick={() => setSelectedTimeIdx(i => Math.min(validTimes.length - 1, i + 1))}>{"\u203a"}</button>
              </div>
            </>
          )}
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

        {/* Debug toggle */}
        <div className={styles.section}>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.72rem", color: "var(--muted)", cursor: "pointer" }}>
            <input type="checkbox" checked={showDebugLabels} onChange={e => setShowDebugLabels(e.target.checked)} />
            Show values on map
          </label>
        </div>
      </div>

      {/* Map */}
      <div className={styles.mapContainer}>
        <div ref={containerRef} style={{ width: "100%", height: "100%" }} />

        {/* Loading indicator */}
        {gridLoading && (
          <div style={{ position: "absolute", top: 12, left: "50%", transform: "translateX(-50%)", background: "rgba(15,23,42,0.85)", color: "#e2e8f0", padding: "6px 18px", borderRadius: 8, fontSize: "0.8rem", zIndex: 10 }}>
            Loading {MODEL_LABELS[activeModel].label} data\u2026
          </div>
        )}

        {/* Legend */}
        {activeOv && (
          <div className={styles.mapLegend}>
            <p className={styles.mapLegendTitle}>{activeOv.label}</p>
            <div className={styles.legendBar} style={{ background: activeOv.gradient }} />
            <div className={styles.legendLabels}>
              <span>{legendValue(dataRange ? dataRange.scale_min : activeOv.legendMinVal, activeOv, units)}</span>
              <span>{legendValue(dataRange ? dataRange.scale_max : activeOv.legendMaxVal, activeOv, units)}</span>
            </div>
            {dataRange && (
              <p style={{ margin: "2px 0 0", fontSize: "0.6rem", color: "#94a3b8" }}>
                data: {dataRange.min.toFixed(2)}–{dataRange.max.toFixed(2)} (mean {dataRange.mean.toFixed(2)})
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
