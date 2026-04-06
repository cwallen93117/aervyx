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
  hrrr: { label: "HRRR", sub: "3km · CONUS" },
  rap:  { label: "RAP",  sub: "13km · N. America" },
  gfs:  { label: "GFS",  sub: "25km · Global" },
  nam:  { label: "NAM",  sub: "3-12km · N. America" },
  nbm:  { label: "NBM",  sub: "2.5km · CONUS" },
};

type OverlayDef = {
  id: string;
  label: string;
  unit: string;
  unitType: "altitude" | "vario" | "none" | "percent" | "mm" | "speed" | "jkg";
  group: string;
  variable: string; // backend variable name
  legendMinVal: number;
  legendMaxVal: number;
  gradient: string;
  colors: [string, string, string, string]; // 4-stop for map interpolation
};

const OVERLAYS: OverlayDef[] = [
  { id: "thermal_strength",      label: "Thermal Strength",        unit: "m/s",  unitType: "vario",    group: "Thermal / Lift",  variable: "vertical_velocity_700hPa", legendMinVal: 0,   legendMaxVal: 5,    gradient: "linear-gradient(to right,#3b82f6,#22c55e,#eab308,#ef4444)", colors: ["#3b82f6","#22c55e","#eab308","#ef4444"] },
  { id: "cape",                  label: "CAPE",                    unit: "J/kg", unitType: "jkg",      group: "Thermal / Lift",  variable: "cape",                     legendMinVal: 0,   legendMaxVal: 2000, gradient: "linear-gradient(to right,#3b82f6,#22c55e,#eab308,#ef4444)", colors: ["#3b82f6","#22c55e","#eab308","#ef4444"] },
  { id: "convective_cloud_top",  label: "Top of Lift",             unit: "m",    unitType: "altitude", group: "Thermal / Lift",  variable: "convective_cloud_top",     legendMinVal: 0,   legendMaxVal: 4000, gradient: "linear-gradient(to right,#ef4444,#eab308,#22c55e,#3b82f6)", colors: ["#ef4444","#eab308","#22c55e","#3b82f6"] },
  { id: "boundary_layer_height", label: "Boundary Layer Height",   unit: "m",    unitType: "altitude", group: "Thermal / Lift",  variable: "boundary_layer_height",    legendMinVal: 0,   legendMaxVal: 3500, gradient: "linear-gradient(to right,#ef4444,#eab308,#22c55e,#3b82f6)", colors: ["#ef4444","#eab308","#22c55e","#3b82f6"] },
  { id: "lifted_index",          label: "Lifted Index",            unit: "",     unitType: "none",     group: "Thermal / Lift",  variable: "lifted_index",             legendMinVal: -8,  legendMaxVal: 4,    gradient: "linear-gradient(to right,#ef4444,#f97316,#22c55e,#3b82f6)", colors: ["#ef4444","#f97316","#22c55e","#3b82f6"] },
  { id: "cloud_cover",           label: "Cloud Cover",             unit: "%",    unitType: "percent",  group: "Cloud / Weather", variable: "cloud_cover",              legendMinVal: 0,   legendMaxVal: 100,  gradient: "linear-gradient(to right,#f8fafc,#94a3b8,#1e293b,#0f172a)", colors: ["#f8fafc","#94a3b8","#1e293b","#0f172a"] },
  { id: "convective_cloud_base", label: "Cumulus Cloud Base",      unit: "m",    unitType: "altitude", group: "Cloud / Weather", variable: "convective_cloud_base",    legendMinVal: 0,   legendMaxVal: 3000, gradient: "linear-gradient(to right,#22c55e,#3b82f6,#3b82f6,#7c3aed)", colors: ["#22c55e","#3b82f6","#3b82f6","#7c3aed"] },
  { id: "precipitation",         label: "Precipitation",           unit: "mm",   unitType: "mm",       group: "Cloud / Weather", variable: "precipitation",            legendMinVal: 0,   legendMaxVal: 20,   gradient: "linear-gradient(to right,#f8fafc,#3b82f6,#7c3aed,#7c3aed)", colors: ["#f8fafc","#3b82f6","#7c3aed","#7c3aed"] },
  { id: "wind_surface",          label: "Surface Wind",            unit: "kt",   unitType: "speed",    group: "Wind",            variable: "wind_speed_10m",           legendMinVal: 0,   legendMaxVal: 60,   gradient: "linear-gradient(to right,#22c55e,#eab308,#ef4444,#ef4444)", colors: ["#22c55e","#eab308","#ef4444","#ef4444"] },
  { id: "wind_850",              label: "Wind ~1500m (850hPa)",    unit: "kt",   unitType: "speed",    group: "Wind",            variable: "wind_speed_850hPa",        legendMinVal: 0,   legendMaxVal: 60,   gradient: "linear-gradient(to right,#22c55e,#eab308,#ef4444,#ef4444)", colors: ["#22c55e","#eab308","#ef4444","#ef4444"] },
  { id: "wind_700",              label: "Wind ~3000m (700hPa)",    unit: "kt",   unitType: "speed",    group: "Wind",            variable: "wind_speed_700hPa",        legendMinVal: 0,   legendMaxVal: 80,   gradient: "linear-gradient(to right,#22c55e,#eab308,#ef4444,#ef4444)", colors: ["#22c55e","#eab308","#ef4444","#ef4444"] },
  { id: "wind_500",              label: "Wind ~5500m (500hPa)",    unit: "kt",   unitType: "speed",    group: "Wind",            variable: "wind_speed_500hPa",        legendMinVal: 0,   legendMaxVal: 100,  gradient: "linear-gradient(to right,#22c55e,#eab308,#ef4444,#ef4444)", colors: ["#22c55e","#eab308","#ef4444","#ef4444"] },
];

/* ------------------------------------------------------------------ */
/* Unit helpers                                                        */
/* ------------------------------------------------------------------ */
function displayUnit(ov: OverlayDef, units: Units): string {
  if (ov.unitType === "altitude") return units.altitude === "ft" ? "ft" : "m";
  if (ov.unitType === "vario") return units.vario === "fpm" ? "ft/min" : "m/s";
  return ov.unit;
}

// Backend returns raw model values. Convert for display.
// vertical_velocity_700hPa is in Pa/s (negative = upward).
function convertValue(val: number, ov: OverlayDef, units: Units): number {
  if (ov.unitType === "vario") {
    const ms = -val / 10; // Pa/s -> m/s (approx at 700hPa)
    if (units.vario === "fpm") return Math.round(ms * 196.85);
    return Math.round(ms * 10) / 10;
  }
  if (ov.unitType === "altitude" && units.altitude === "ft") return Math.round(val * 3.28084);
  if (ov.unitType === "speed") return Math.round(val * 1.944); // m/s -> kt
  return Math.round(val);
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

function safeRemove(map: maplibregl.Map) {
  try { if (map.getLayer(OVERLAY_LAYER)) map.removeLayer(OVERLAY_LAYER); } catch { /* */ }
  try { if (map.getSource(OVERLAY_SRC)) map.removeSource(OVERLAY_SRC); } catch { /* */ }
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
  const mapLoaded = useRef(false);

  const [activeModel, setActiveModel] = useState<ModelId>("hrrr");
  const [runs, setRuns] = useState<RunInfo[]>([]);
  const [selectedRunIdx, setSelectedRunIdx] = useState(0);
  const [selectedTimeIdx, setSelectedTimeIdx] = useState(0);
  const [metaLoading, setMetaLoading] = useState(false);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [activeOverlay, setActiveOverlay] = useState<string>("thermal_strength");
  const [opacity, setOpacity] = useState(70);
  const [gridLoading, setGridLoading] = useState(false);
  const [, setMapReady] = useState(0);

  const activeRun = runs[selectedRunIdx] ?? null;
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
    map.on("load", () => { mapLoaded.current = true; setMapReady(n => n + 1); });
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; mapLoaded.current = false; };
  }, []);

  // Fetch available runs when model changes
  useEffect(() => {
    setRuns([]); setSelectedRunIdx(0); setSelectedTimeIdx(0);
    setMetaError(null); setMetaLoading(true);

    const api = resolveApiBase();
    fetch(`${api}/api/weather/available?model=${activeModel}`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((d: { model: string; runs: RunInfo[] }) => {
        setRuns(d.runs);
        if (d.runs.length === 0) setMetaError("No runs available");
      })
      .catch((e: unknown) => setMetaError(String(e)))
      .finally(() => setMetaLoading(false));
  }, [activeModel]);

  // Fetch grid data and update map overlay
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded.current || !activeRun) return;

    const vt = validTimes[selectedTimeIdx];
    if (!vt) return;

    const ov = OVERLAYS.find(o => o.id === activeOverlay);
    if (!ov) return;

    // Compute forecast hour from run time and valid time
    const runDt = new Date(`${activeRun.date.slice(0,4)}-${activeRun.date.slice(4,6)}-${activeRun.date.slice(6,8)}T${activeRun.hour}:00:00Z`);
    const vtDt = new Date(vt);
    const fh = Math.round((vtDt.getTime() - runDt.getTime()) / 3600000);

    setGridLoading(true);
    const api = resolveApiBase();
    const url = `${api}/api/weather/grid?model=${activeModel}&date=${activeRun.date}&hour=${activeRun.hour}&fh=${fh}&variable=${ov.variable}`;

    let cancelled = false;

    fetch(url)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((geojson: GeoJSON.FeatureCollection) => {
        if (cancelled || !mapLoaded.current) return;
        safeRemove(map);

        // Use requestAnimationFrame to ensure removal is processed
        requestAnimationFrame(() => {
          if (cancelled) return;
          try {
            map.addSource(OVERLAY_SRC, { type: "geojson", data: geojson });
            map.addLayer({
              id: OVERLAY_LAYER,
              type: "circle",
              source: OVERLAY_SRC,
              paint: {
                "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 3, 6, 7, 9, 14, 12, 24],
                "circle-color": [
                  "interpolate", ["linear"], ["get", "value"],
                  ov.legendMinVal, ov.colors[0],
                  ov.legendMinVal + (ov.legendMaxVal - ov.legendMinVal) * 0.33, ov.colors[1],
                  ov.legendMinVal + (ov.legendMaxVal - ov.legendMinVal) * 0.66, ov.colors[2],
                  ov.legendMaxVal, ov.colors[3],
                ] as unknown as maplibregl.ExpressionSpecification,
                "circle-opacity": opacity / 100,
                "circle-blur": 0.6,
              },
            });
          } catch (err) {
            console.warn("[SoaringForecast] layer add error:", err);
          }
        });
      })
      .catch(err => console.warn("[SoaringForecast] grid fetch error:", err))
      .finally(() => { if (!cancelled) setGridLoading(false); });

    return () => {
      cancelled = true;
      safeRemove(map);
    };
  }, [activeModel, activeOverlay, selectedTimeIdx, selectedRunIdx, opacity, activeRun, validTimes]);

  // Click handler — compare all models at a point
  const handleMapClick = useCallback(async (e: maplibregl.MapMouseEvent) => {
    const map = mapRef.current;
    if (!map || !activeRun) return;
    const { lat, lng } = e.lngLat;
    const ov = OVERLAYS.find(o => o.id === activeOverlay);
    if (!ov) return;

    const popup = new maplibregl.Popup({ closeButton: true, maxWidth: "300px" })
      .setLngLat([lng, lat])
      .setHTML(`<div style="padding:6px;font-size:0.78rem;color:#64748b">Loading…</div>`)
      .addTo(map);

    // For the clicked point, show the value from the current overlay
    const vt = validTimes[selectedTimeIdx];
    if (!vt) return;

    const runDt = new Date(`${activeRun.date.slice(0,4)}-${activeRun.date.slice(4,6)}-${activeRun.date.slice(6,8)}T${activeRun.hour}:00:00Z`);
    const vtDt = new Date(vt);
    const fh = Math.round((vtDt.getTime() - runDt.getTime()) / 3600000);

    // Query each model for comparison
    const api = resolveApiBase();
    const results = await Promise.allSettled(
      MODEL_IDS.map(async (mid) => {
        // Use same time index — find closest run for this model
        const resp = await fetch(`${api}/api/weather/available?model=${mid}`);
        if (!resp.ok) throw new Error("unavailable");
        const avail = await resp.json() as { runs: RunInfo[] };
        const run = avail.runs[0]; // most recent
        if (!run) throw new Error("no runs");
        // Find forecast hour for closest valid time
        const runDate = new Date(`${run.date.slice(0,4)}-${run.date.slice(4,6)}-${run.date.slice(6,8)}T${run.hour}:00:00Z`);
        const targetFh = Math.round((vtDt.getTime() - runDate.getTime()) / 3600000);
        if (targetFh < 0 || targetFh > run.max_fxx) throw new Error("out of range");
        return { label: MODEL_LABELS[mid].label, model: mid, run, fh: targetFh };
      })
    );

    const rows: string[] = [];
    for (const r of results) {
      if (r.status === "rejected") continue;
      const { label } = r.value;
      // Just show the model name — full grid comparison is expensive
      // Instead show what data is available
      rows.push(`<tr><td style="padding:3px 8px 3px 0;color:#64748b;font-size:0.78rem">${label}</td><td style="font-weight:600;font-size:0.78rem">Available</td></tr>`);
    }

    popup.setHTML(
      `<div style="padding:4px">` +
      `<strong style="font-size:0.8rem">${ov.label}</strong>` +
      `<p style="font-size:0.7rem;color:#64748b;margin:2px 0 8px">${lat.toFixed(3)}\u00b0N ${Math.abs(lng).toFixed(3)}\u00b0${lng < 0 ? "W" : "E"}</p>` +
      `<table style="border-collapse:collapse;width:100%">${rows.join("")}</table>` +
      `<p style="font-size:0.65rem;color:#94a3b8;margin:6px 0 0">Click a grid point on the map for exact values</p>` +
      `</div>`
    );
  }, [activeOverlay, selectedTimeIdx, activeRun, validTimes]);

  // Bind click handler
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const handler = (e: maplibregl.MapMouseEvent) => { void handleMapClick(e); };
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
                onClick={() => setActiveModel(id)}
              >
                {MODEL_LABELS[id].label}<span className={styles.pillSub}>{MODEL_LABELS[id].sub}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Run selector */}
        {runs.length > 1 && (
          <div className={styles.section}>
            <p className={styles.sectionLabel}>Model Run</p>
            <select
              style={{ width: "100%", padding: "4px 8px", fontSize: "0.8rem", background: "var(--panel)", color: "var(--ink)", border: "1px solid var(--line)", borderRadius: "var(--r-sm)" }}
              value={selectedRunIdx}
              onChange={e => { setSelectedRunIdx(Number(e.target.value)); setSelectedTimeIdx(0); }}
            >
              {runs.map((r, i) => (
                <option key={i} value={i}>{r.date} {r.hour}Z</option>
              ))}
            </select>
          </div>
        )}

        {/* Forecast time slider */}
        <div className={styles.section}>
          <p className={styles.sectionLabel}>Forecast Time</p>
          {metaLoading && <div className={styles.loadingState}>Loading model data…</div>}
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
              {OVERLAYS.filter(o => o.group === group).map(ov => (
                <div key={ov.id}
                  className={[styles.overlayRow, ov.id === activeOverlay ? styles.overlayRowActive : ""].join(" ")}
                  onClick={() => setActiveOverlay(ov.id)}
                >
                  <span>{ov.label}</span>
                  <span className={styles.overlayUnit}>{displayUnit(ov, units)}</span>
                </div>
              ))}
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

      {/* Map */}
      <div className={styles.mapContainer}>
        <div ref={containerRef} style={{ width: "100%", height: "100%" }} />

        {/* Loading indicator */}
        {gridLoading && (
          <div style={{ position: "absolute", top: 12, left: "50%", transform: "translateX(-50%)", background: "rgba(15,23,42,0.85)", color: "#e2e8f0", padding: "6px 18px", borderRadius: 8, fontSize: "0.8rem", zIndex: 10 }}>
            Loading {MODEL_LABELS[activeModel].label} data…
          </div>
        )}

        {/* Legend */}
        {activeOv && (
          <div className={styles.mapLegend}>
            <p className={styles.mapLegendTitle}>{activeOv.label}</p>
            <div className={styles.legendBar} style={{ background: activeOv.gradient }} />
            <div className={styles.legendLabels}>
              <span>{legendValue(activeOv.legendMinVal, activeOv, units)}</span>
              <span>{legendValue(activeOv.legendMaxVal, activeOv, units)}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
