"use client";

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState, useCallback } from "react";
import styles from "./SoaringForecastMap.module.css";

type Units = { altitude: "ft" | "m"; vario: "fpm" | "ms" };

const META_URLS: Record<string, string> = {
  ncep_hrrr_conus: "https://map-tiles.open-meteo.com/data_spatial/ncep_hrrr_conus/latest.json",
  ncep_gfs025:     "https://map-tiles.open-meteo.com/data_spatial/ncep_gfs025/latest.json",
  dwd_icon:        "https://map-tiles.open-meteo.com/data_spatial/dwd_icon/latest.json",
  ncep_nam_conus:  "https://map-tiles.open-meteo.com/data_spatial/ncep_nam_conus/latest.json",
};

const MODEL_LABELS: Record<string, { label: string; sub: string }> = {
  ncep_hrrr_conus: { label: "HRRR", sub: "3km · CONUS" },
  ncep_gfs025:     { label: "GFS",  sub: "25km · Global" },
  dwd_icon:        { label: "ICON", sub: "11km · Global" },
  ncep_nam_conus:  { label: "NAM",  sub: "3km · CONUS" },
};

const POINT_API_MODEL: Record<string, string> = {
  ncep_hrrr_conus: "hrrr",
  ncep_gfs025:     "gfs_025",
  dwd_icon:        "icon_seamless",
  ncep_nam_conus:  "nam_conus",
};

type OverlayDef = {
  id: string;
  label: string;
  unit: string;
  unitType: "altitude" | "none" | "percent" | "mm" | "speed" | "jkg";
  group: string;
  omVar: string;
  tileVar: string;
  legendMinVal: number;
  legendMaxVal: number;
  gradient: string;
};

const OVERLAYS: OverlayDef[] = [
  { id: "cape",                  label: "Thermal Strength (CAPE)", unit: "J/kg", unitType: "jkg",     group: "Thermal / Lift",  omVar: "cape",                    tileVar: "cape",                    legendMinVal: 0,    legendMaxVal: 2000, gradient: "linear-gradient(to right,#3b82f6,#22c55e,#eab308,#ef4444)" },
  { id: "convective_cloud_top",  label: "Top of Lift",             unit: "m",    unitType: "altitude", group: "Thermal / Lift",  omVar: "convective_cloud_top",    tileVar: "convective_cloud_top",    legendMinVal: 0,    legendMaxVal: 4000, gradient: "linear-gradient(to right,#ef4444,#eab308,#22c55e,#3b82f6)" },
  { id: "boundary_layer_height", label: "Boundary Layer Height",   unit: "m",    unitType: "altitude", group: "Thermal / Lift",  omVar: "boundary_layer_height",   tileVar: "boundary_layer_height",   legendMinVal: 0,    legendMaxVal: 3500, gradient: "linear-gradient(to right,#ef4444,#eab308,#22c55e)" },
  { id: "lifted_index",          label: "Lifted Index",            unit: "",     unitType: "none",     group: "Thermal / Lift",  omVar: "lifted_index",            tileVar: "lifted_index",            legendMinVal: -8,   legendMaxVal: 4,    gradient: "linear-gradient(to right,#ef4444,#f97316,#22c55e,#3b82f6)" },
  { id: "cloud_cover",           label: "Cloud Cover",             unit: "%",    unitType: "percent",  group: "Cloud / Weather", omVar: "cloud_cover",             tileVar: "cloud_cover",             legendMinVal: 0,    legendMaxVal: 100,  gradient: "linear-gradient(to right,#f8fafc,#94a3b8,#1e293b)" },
  { id: "convective_cloud_base", label: "Cumulus Cloud Base",      unit: "m",    unitType: "altitude", group: "Cloud / Weather", omVar: "convective_cloud_base",   tileVar: "convective_cloud_base",   legendMinVal: 0,    legendMaxVal: 3000, gradient: "linear-gradient(to right,#22c55e,#3b82f6)" },
  { id: "precipitation",         label: "Precipitation",           unit: "mm",   unitType: "mm",       group: "Cloud / Weather", omVar: "precipitation",           tileVar: "precipitation",           legendMinVal: 0,    legendMaxVal: 20,   gradient: "linear-gradient(to right,#f8fafc,#3b82f6,#7c3aed)" },
  { id: "wind_surface",          label: "Surface Wind",            unit: "kt",   unitType: "speed",    group: "Wind",            omVar: "wind_speed_10m",          tileVar: "wind_u_component_10m",    legendMinVal: 0,    legendMaxVal: 60,   gradient: "linear-gradient(to right,#22c55e,#eab308,#ef4444)" },
  { id: "wind_850",              label: "Wind ~1500m (850hPa)",    unit: "kt",   unitType: "speed",    group: "Wind",            omVar: "wind_speed_850hPa",       tileVar: "wind_u_component_850hPa", legendMinVal: 0,    legendMaxVal: 60,   gradient: "linear-gradient(to right,#22c55e,#eab308,#ef4444)" },
  { id: "wind_700",              label: "Wind ~3000m (700hPa)",    unit: "kt",   unitType: "speed",    group: "Wind",            omVar: "wind_speed_700hPa",       tileVar: "wind_u_component_700hPa", legendMinVal: 0,    legendMaxVal: 80,   gradient: "linear-gradient(to right,#22c55e,#eab308,#ef4444)" },
  { id: "wind_500",              label: "Wind ~5500m (500hPa)",    unit: "kt",   unitType: "speed",    group: "Wind",            omVar: "wind_speed_500hPa",       tileVar: "wind_u_component_500hPa", legendMinVal: 0,    legendMaxVal: 100,  gradient: "linear-gradient(to right,#22c55e,#eab308,#ef4444)" },
];

function displayUnit(ov: OverlayDef, units: Units): string {
  if (ov.unitType === "altitude") return units.altitude === "ft" ? "ft" : "m";
  return ov.unit;
}

function convertValue(val: number, ov: OverlayDef, units: Units): number {
  if (ov.unitType === "altitude" && units.altitude === "ft") return Math.round(val * 3.28084);
  return Math.round(val);
}

function legendMin(ov: OverlayDef, units: Units): string {
  const v = convertValue(ov.legendMinVal, ov, units);
  const u = displayUnit(ov, units);
  return u ? `${v} ${u}` : String(v);
}

function legendMax(ov: OverlayDef, units: Units): string {
  const v = convertValue(ov.legendMaxVal, ov, units);
  const u = displayUnit(ov, units);
  return u ? `${v} ${u}` : String(v);
}

function formatVT(iso: string) {
  try { return new Date(iso).toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZoneName: "short" }); }
  catch { return iso; }
}

const OVERLAY_LAYER = "soaring-overlay-layer";
const OVERLAY_SRC = "soaring-overlay-src";
const WIND_LAYER = "soaring-wind-layer";
const WIND_SRC = "soaring-wind-src";

function safeRemove(map: maplibregl.Map) {
  for (const id of [OVERLAY_LAYER, WIND_LAYER]) {
    try { if (map.getLayer(id)) map.removeLayer(id); } catch {}
  }
  for (const id of [OVERLAY_SRC, WIND_SRC]) {
    try { if (map.getSource(id)) map.removeSource(id); } catch {}
  }
}

function createArrowImageData(): ImageData {
  const size = 32;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  ctx.translate(size / 2, size / 2);
  ctx.strokeStyle = "#0f172a";
  ctx.lineWidth = 2;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  ctx.moveTo(0, 8);
  ctx.lineTo(0, -8);
  ctx.moveTo(-4, -4);
  ctx.lineTo(0, -8);
  ctx.lineTo(4, -4);
  ctx.stroke();
  return ctx.getImageData(0, 0, size, size);
}

export function SoaringForecastMap({ units }: { units: Units }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const protocolRef = useRef(false);
  const mapLoaded = useRef(false);

  const [activeModel, setActiveModel] = useState("ncep_hrrr_conus");
  const [modelMeta, setModelMeta] = useState<{ validTimes: string[]; variables: string[] } | null>(null);
  const [metaLoading, setMetaLoading] = useState(false);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [modelAvail, setModelAvail] = useState<Record<string, boolean>>({});
  const [selectedTimeIdx, setSelectedTimeIdx] = useState(0);
  const [activeOverlay, setActiveOverlay] = useState<string>("cape");
  const [opacity, setOpacity] = useState(70);
  const [showWindArrows, setShowWindArrows] = useState(false);
  // Counter to force re-render when map finishes loading
  const [, setMapReady] = useState(0);

  // Init map
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: { basemap: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© OpenStreetMap contributors" } },
        layers: [{ id: "bg", type: "background", paint: { "background-color": "#e7eef5" } }, { id: "basemap", type: "raster", source: "basemap" }],
      },
      center: [-98, 39], zoom: 4,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
      mapLoaded.current = true;
      const arrowData = createArrowImageData();
      map.addImage("wind-arrow", arrowData);
      setMapReady(n => n + 1);
    });
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; mapLoaded.current = false; };
  }, []);

  // Register om:// protocol
  useEffect(() => {
    if (protocolRef.current) return;
    import("@openmeteo/weather-map-layer").then(mod => {
      const p = mod.omProtocol ?? (mod as unknown as { default?: { omProtocol?: unknown } }).default?.omProtocol;
      if (p) {
        try { maplibregl.addProtocol("om", p as Parameters<typeof maplibregl.addProtocol>[1]); } catch {}
        protocolRef.current = true;
        setMapReady(n => n + 1);
      }
    }).catch(() => {});
  }, []);

  // Fetch model metadata
  useEffect(() => {
    setModelMeta(null); setMetaError(null); setMetaLoading(true); setSelectedTimeIdx(0);
    fetch(META_URLS[activeModel])
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((d: { valid_times?: string[]; variables?: string[] }) => {
        setModelMeta({ validTimes: d.valid_times ?? [], variables: d.variables ?? [] });
        setModelAvail(p => ({ ...p, [activeModel]: true }));
      })
      .catch((e: unknown) => { setMetaError(String(e)); setModelAvail(p => ({ ...p, [activeModel]: false })); })
      .finally(() => setMetaLoading(false));
  }, [activeModel]);

  // Update map overlay — runs whenever model, variable, or time changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded.current || !protocolRef.current || !modelMeta) return;
    safeRemove(map);
    const vt = modelMeta.validTimes[selectedTimeIdx];
    const ov = OVERLAYS.find(o => o.id === activeOverlay);
    if (!vt || !ov) return;

    const base = `https://map-tiles.open-meteo.com/data_spatial/${activeModel}/latest.json`;
    try {
      map.addSource(OVERLAY_SRC, {
        type: "raster",
        url: `om://${base}?variable=${ov.tileVar}&valid_time=${encodeURIComponent(vt)}`,
        tileSize: 256,
        maxzoom: 12,
      } as maplibregl.RasterSourceSpecification);
      map.addLayer({
        id: OVERLAY_LAYER,
        type: "raster",
        source: OVERLAY_SRC,
        paint: { "raster-opacity": opacity / 100 },
      });
    } catch {}
  }, [activeModel, activeOverlay, selectedTimeIdx, opacity, modelMeta]);

  // Wind arrows via Open-Meteo point API
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded.current || !showWindArrows || !modelMeta) return;

    const lvl = activeOverlay.includes("850") ? "850hPa" : activeOverlay.includes("700") ? "700hPa" : activeOverlay.includes("500") ? "500hPa" : "10m";
    const speedVar = lvl === "10m" ? "wind_speed_10m" : `wind_speed_${lvl}`;
    const dirVar = lvl === "10m" ? "wind_direction_10m" : `wind_direction_${lvl}`;
    const vt = modelMeta.validTimes[selectedTimeIdx];
    if (!vt) return;

    const bounds = map.getBounds();
    const west = bounds.getWest(), east = bounds.getEast();
    const south = bounds.getSouth(), north = bounds.getNorth();
    const steps = 6;
    const latStep = (north - south) / steps;
    const lonStep = (east - west) / steps;

    const points: Array<{ lat: number; lon: number }> = [];
    for (let i = 0; i <= steps; i++) {
      for (let j = 0; j <= steps; j++) {
        points.push({ lat: south + i * latStep, lon: west + j * lonStep });
      }
    }

    const vtDate = new Date(vt);
    const now = new Date();
    const hourOffset = Math.max(0, Math.round((vtDate.getTime() - now.getTime()) / 3600000));

    let cancelled = false;
    const model = POINT_API_MODEL[activeModel] ?? "gfs_025";

    Promise.allSettled(
      points.map(pt =>
        fetch(`https://api.open-meteo.com/v1/forecast?latitude=${pt.lat.toFixed(2)}&longitude=${pt.lon.toFixed(2)}&hourly=${speedVar},${dirVar}&models=${model}&forecast_days=3&timezone=auto`)
          .then(r => r.json())
          .then((d: { hourly?: Record<string, (number | null)[]> }) => {
            const speed = d.hourly?.[speedVar]?.[hourOffset];
            const dir = d.hourly?.[dirVar]?.[hourOffset];
            if (speed == null || dir == null) return null;
            return { lat: pt.lat, lon: pt.lon, speed, dir };
          })
      )
    ).then(results => {
      if (cancelled || !mapLoaded.current) return;
      const features: GeoJSON.Feature[] = [];
      for (const r of results) {
        if (r.status !== "fulfilled" || !r.value) continue;
        const { lat, lon, speed, dir } = r.value;
        features.push({
          type: "Feature",
          geometry: { type: "Point", coordinates: [lon, lat] },
          properties: { speed: Math.round(speed), direction: dir, label: `${Math.round(speed * 1.944)} kt` },
        });
      }
      if (cancelled) return;
      try { if (map.getLayer(WIND_LAYER)) map.removeLayer(WIND_LAYER); } catch {}
      try { if (map.getSource(WIND_SRC)) map.removeSource(WIND_SRC); } catch {}

      map.addSource(WIND_SRC, { type: "geojson", data: { type: "FeatureCollection", features } });
      if (map.hasImage("wind-arrow")) {
        map.addLayer({
          id: WIND_LAYER,
          type: "symbol",
          source: WIND_SRC,
          layout: {
            "icon-image": "wind-arrow",
            "icon-size": 1,
            "icon-rotate": ["get", "direction"],
            "icon-rotation-alignment": "map",
            "icon-allow-overlap": true,
            "text-field": ["get", "label"],
            "text-size": 10,
            "text-offset": [0, 1.5],
            "text-allow-overlap": false,
          },
          paint: {
            "icon-opacity": 0.85,
            "text-color": "#0f172a",
            "text-halo-color": "#ffffff",
            "text-halo-width": 1,
          },
        });
      }
    });

    return () => {
      cancelled = true;
      try { if (map.getLayer(WIND_LAYER)) map.removeLayer(WIND_LAYER); } catch {}
      try { if (map.getSource(WIND_SRC)) map.removeSource(WIND_SRC); } catch {}
    };
  }, [showWindArrows, activeModel, activeOverlay, selectedTimeIdx, modelMeta]);

  const handleMapClick = useCallback(async (e: maplibregl.MapMouseEvent) => {
    const map = mapRef.current;
    if (!map) return;
    const { lat, lng } = e.lngLat;
    const ov = OVERLAYS.find(o => o.id === activeOverlay);
    const hourly = "cape,boundary_layer_height,convective_cloud_top,lifted_index,cloud_cover,precipitation,wind_speed_10m,wind_direction_10m,wind_speed_850hPa,wind_direction_850hPa";
    const popup = new maplibregl.Popup({ closeButton: true, maxWidth: "300px" })
      .setLngLat([lng, lat])
      .setHTML(`<div style="padding:6px;font-size:0.78rem;color:#64748b">Loading all models…</div>`)
      .addTo(map);
    const results = await Promise.allSettled(
      Object.entries(MODEL_LABELS).map(([id, meta]) =>
        fetch(`https://api.open-meteo.com/v1/forecast?latitude=${lat.toFixed(4)}&longitude=${lng.toFixed(4)}&hourly=${hourly}&models=${POINT_API_MODEL[id] ?? "gfs_025"}&timezone=auto&forecast_days=3`)
          .then(r => r.json()).then((d: { hourly?: Record<string, (number | null)[]> }) => ({ label: meta.label, value: d.hourly?.[ov?.omVar ?? "cape"]?.[selectedTimeIdx] ?? null }))
      )
    );
    const rows = results.map(r => {
      if (r.status === "rejected") return "";
      const { label, value } = r.value;
      if (value === null) return `<tr><td style="padding:3px 8px 3px 0;color:#64748b;font-size:0.78rem">${label}</td><td style="font-weight:600;font-size:0.78rem">N/A</td></tr>`;
      const converted = ov ? convertValue(value, ov, units) : Math.round(value);
      const u = ov ? displayUnit(ov, units) : "";
      return `<tr><td style="padding:3px 8px 3px 0;color:#64748b;font-size:0.78rem">${label}</td><td style="font-weight:600;font-size:0.78rem">${converted} ${u}</td></tr>`;
    }).join("");
    popup.setHTML(`<div style="padding:4px"><strong style="font-size:0.8rem">${ov?.label ?? activeOverlay}</strong><p style="font-size:0.7rem;color:#64748b;margin:2px 0 8px">${lat.toFixed(3)}°N ${Math.abs(lng).toFixed(3)}°${lng < 0 ? "W" : "E"}</p><table style="border-collapse:collapse;width:100%">${rows}</table></div>`);
  }, [activeOverlay, selectedTimeIdx, units]);

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
  const validTimes = modelMeta?.validTimes ?? [];
  const variables = modelMeta?.variables ?? [];

  return (
    <div className={styles.shell}>
      <div className={styles.leftPanel}>
        <div className={styles.section}>
          <p className={styles.sectionLabel}>Model</p>
          <div className={styles.modelPills}>
            {Object.entries(MODEL_LABELS).map(([id, meta]) => (
              <button key={id}
                className={[styles.pill, id === activeModel ? styles.pillActive : "", modelAvail[id] === false ? styles.pillDisabled : ""].join(" ")}
                onClick={() => modelAvail[id] !== false && setActiveModel(id)}
                disabled={modelAvail[id] === false}
              >
                {meta.label}<span className={styles.pillSub}>{meta.sub}</span>
              </button>
            ))}
          </div>
        </div>

        <div className={styles.section}>
          <p className={styles.sectionLabel}>Forecast Time</p>
          {metaLoading && <div className={styles.loadingState}>Loading model data…</div>}
          {metaError && <div className={styles.errorBadge}>Unavailable: {metaError}</div>}
          {modelMeta && validTimes.length > 0 && (
            <>
              <p className={styles.timeLabel}>{formatVT(validTimes[selectedTimeIdx])}</p>
              <div className={styles.timeNav}>
                <button className={styles.timeNavBtn} disabled={selectedTimeIdx === 0} onClick={() => setSelectedTimeIdx(i => Math.max(0, i - 1))}>&#8249;</button>
                <input type="range" className={styles.timeSlider} min={0} max={validTimes.length - 1} value={selectedTimeIdx} onChange={e => setSelectedTimeIdx(Number(e.target.value))} />
                <button className={styles.timeNavBtn} disabled={selectedTimeIdx === validTimes.length - 1} onClick={() => setSelectedTimeIdx(i => Math.min(validTimes.length - 1, i + 1))}>&#8250;</button>
              </div>
            </>
          )}
        </div>

        <div>
          {groups.map(group => (
            <div key={group}>
              <p className={styles.groupHeader}>{group}</p>
              {OVERLAYS.filter(o => o.group === group).map(ov => {
                const tileV = ov.tileVar;
                const unavail = variables.length > 0 && !variables.includes(tileV);
                return (
                  <div key={ov.id}
                    className={[styles.overlayRow, ov.id === activeOverlay ? styles.overlayRowActive : "", unavail ? styles.overlayRowUnavailable : ""].join(" ")}
                    onClick={() => !unavail && setActiveOverlay(ov.id)}
                  >
                    <span>{ov.label}</span>
                    <span className={styles.overlayUnit}>{displayUnit(ov, units)}</span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>

        <div className={styles.section}>
          <p className={styles.sectionLabel}>Opacity</p>
          <div className={styles.opacityRow}>
            <input type="range" className={styles.opacitySlider} min={0} max={100} value={opacity} onChange={e => setOpacity(Number(e.target.value))} />
            <span className={styles.opacityVal}>{opacity}%</span>
          </div>
        </div>

        <div className={styles.section}>
          <label className={styles.windToggleLabel}>
            <input type="checkbox" checked={showWindArrows} onChange={e => setShowWindArrows(e.target.checked)} />
            Show wind arrows
          </label>
        </div>
      </div>

      <div className={styles.mapContainer}>
        <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
        {activeOv && (
          <div className={styles.mapLegend}>
            <p className={styles.mapLegendTitle}>{activeOv.label}</p>
            <div className={styles.legendBar} style={{ background: activeOv.gradient }} />
            <div className={styles.legendLabels}><span>{legendMin(activeOv, units)}</span><span>{legendMax(activeOv, units)}</span></div>
          </div>
        )}
      </div>
    </div>
  );
}
