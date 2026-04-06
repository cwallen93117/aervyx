"use client";

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import styles from "./SoaringForecastMap.module.css";

const META_URLS: Record<string, string> = {
  ncep_hrrr_conus: "https://map-tiles.open-meteo.com/data_spatial/ncep_hrrr_conus/latest.json",
  ncep_gfs025:     "https://map-tiles.open-meteo.com/data_spatial/ncep_gfs025/latest.json",
  dwd_icon:        "https://map-tiles.open-meteo.com/data_spatial/dwd_icon/latest.json",
  ncep_nam_conus:  "https://map-tiles.open-meteo.com/data_spatial/ncep_nam_conus/latest.json",
  rap:             "/api/weather/rap/available",
};

const MODEL_LABELS: Record<string, { label: string; sub: string }> = {
  ncep_hrrr_conus: { label: "HRRR", sub: "3km · CONUS" },
  ncep_gfs025:     { label: "GFS",  sub: "25km · Global" },
  dwd_icon:        { label: "ICON", sub: "11km · Global" },
  ncep_nam_conus:  { label: "NAM",  sub: "3km · CONUS" },
  rap:             { label: "RAP",  sub: "13km · CONUS" },
};

const POINT_API_MODEL: Record<string, string> = {
  ncep_hrrr_conus: "hrrr",
  ncep_gfs025:     "gfs_025",
  dwd_icon:        "icon_seamless",
  ncep_nam_conus:  "nam_conus",
  rap:             "gfs_seamless",
};

const OVERLAYS = [
  { id: "cape",                  label: "Thermal Strength",      unit: "J/kg", group: "Thermal / Lift",  omVar: "cape",                    legendMin: "0",  legendMax: "2000 J/kg", gradient: "linear-gradient(to right,#3b82f6,#22c55e,#eab308,#ef4444)" },
  { id: "convective_cloud_top",  label: "Top of Lift",           unit: "m",    group: "Thermal / Lift",  omVar: "convective_cloud_top",    legendMin: "0",  legendMax: "4000 m",    gradient: "linear-gradient(to right,#ef4444,#eab308,#22c55e,#3b82f6)" },
  { id: "boundary_layer_height", label: "Boundary Layer Height", unit: "m",    group: "Thermal / Lift",  omVar: "boundary_layer_height",   legendMin: "0",  legendMax: "3500 m",    gradient: "linear-gradient(to right,#ef4444,#eab308,#22c55e)" },
  { id: "lifted_index",          label: "Lifted Index",          unit: "",     group: "Thermal / Lift",  omVar: "lifted_index",            legendMin: "−8", legendMax: "+4",        gradient: "linear-gradient(to right,#ef4444,#f97316,#22c55e,#3b82f6)" },
  { id: "cloud_cover",           label: "Cloud Cover",           unit: "%",    group: "Cloud / Weather", omVar: "cloud_cover",             legendMin: "0%", legendMax: "100%",      gradient: "linear-gradient(to right,#f8fafc,#94a3b8,#1e293b)" },
  { id: "convective_cloud_base", label: "Cumulus Cloud Base",    unit: "m",    group: "Cloud / Weather", omVar: "convective_cloud_base",   legendMin: "0",  legendMax: "3000 m",    gradient: "linear-gradient(to right,#22c55e,#3b82f6)" },
  { id: "precipitation",         label: "Precipitation",         unit: "mm",   group: "Cloud / Weather", omVar: "precipitation",           legendMin: "0",  legendMax: "20 mm",     gradient: "linear-gradient(to right,#f8fafc,#3b82f6,#7c3aed)" },
  { id: "wind_surface",          label: "Surface Wind",          unit: "kt",   group: "Wind",            omVar: "wind_u_component_10m",    legendMin: "0",  legendMax: "60 kt",     gradient: "linear-gradient(to right,#22c55e,#eab308,#ef4444)" },
  { id: "wind_850",              label: "Wind ~1500m (850hPa)",  unit: "kt",   group: "Wind",            omVar: "wind_u_component_850hPa", legendMin: "0",  legendMax: "60 kt",     gradient: "linear-gradient(to right,#22c55e,#eab308,#ef4444)" },
  { id: "wind_700",              label: "Wind ~3000m (700hPa)",  unit: "kt",   group: "Wind",            omVar: "wind_u_component_700hPa", legendMin: "0",  legendMax: "80 kt",     gradient: "linear-gradient(to right,#22c55e,#eab308,#ef4444)" },
  { id: "wind_500",              label: "Wind ~5500m (500hPa)",  unit: "kt",   group: "Wind",            omVar: "wind_u_component_500hPa", legendMin: "0",  legendMax: "100 kt",    gradient: "linear-gradient(to right,#22c55e,#eab308,#ef4444)" },
] as const;

type OverlayId = (typeof OVERLAYS)[number]["id"];

function formatVT(iso: string) {
  try { return new Date(iso).toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZoneName: "short" }); }
  catch { return iso; }
}

function removeLayers(map: maplibregl.Map) {
  ["soaring-rap-layer","soaring-overlay-layer","soaring-wind-layer"].forEach(id => { try { if (map.getLayer(id)) map.removeLayer(id); } catch {} });
  ["soaring-rap-src","soaring-overlay-src","soaring-wind-src"].forEach(id => { try { if (map.getSource(id)) map.removeSource(id); } catch {} });
}

export function SoaringForecastMap() {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const protocolRef = useRef(false);

  const [activeModel, setActiveModel] = useState("ncep_hrrr_conus");
  const [modelMeta, setModelMeta] = useState<{ validTimes: string[]; variables: string[] } | null>(null);
  const [metaLoading, setMetaLoading] = useState(false);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [modelAvail, setModelAvail] = useState<Record<string, boolean>>({});
  const [selectedTimeIdx, setSelectedTimeIdx] = useState(0);
  const [activeOverlay, setActiveOverlay] = useState<OverlayId>("cape");
  const [opacity, setOpacity] = useState(70);
  const [showWindArrows, setShowWindArrows] = useState(false);
  const [rapData, setRapData] = useState<object | null>(null);
  const [rapLoading, setRapLoading] = useState(false);

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
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  // Register om:// protocol
  useEffect(() => {
    if (protocolRef.current) return;
    import("@openmeteo/weather-map-layer").then(mod => {
      const p = mod.omProtocol ?? (mod as unknown as { default?: { omProtocol?: unknown } }).default?.omProtocol;
      if (p) { try { maplibregl.addProtocol("om", p as Parameters<typeof maplibregl.addProtocol>[1]); } catch {} protocolRef.current = true; }
    }).catch(() => {});
  }, []);

  // Fetch model metadata
  useEffect(() => {
    setModelMeta(null); setMetaError(null); setMetaLoading(true); setSelectedTimeIdx(0);
    fetch(META_URLS[activeModel])
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((d: { valid_times?: string[]; variables?: string[] }) => { setModelMeta({ validTimes: d.valid_times ?? [], variables: d.variables ?? [] }); setModelAvail(p => ({ ...p, [activeModel]: true })); })
      .catch((e: unknown) => { setMetaError(String(e)); setModelAvail(p => ({ ...p, [activeModel]: false })); })
      .finally(() => setMetaLoading(false));
  }, [activeModel]);

  // Fetch RAP GeoJSON
  useEffect(() => {
    if (activeModel !== "rap" || !modelMeta) return;
    const vt = modelMeta.validTimes[selectedTimeIdx];
    const ov = OVERLAYS.find(o => o.id === activeOverlay);
    if (!vt || !ov) return;
    setRapLoading(true);
    fetch(`/api/weather/rap/grid?variable=${encodeURIComponent(ov.omVar)}&valid_time=${encodeURIComponent(vt)}`)
      .then(r => r.json()).then((d: object) => setRapData(d)).catch(() => setRapData(null)).finally(() => setRapLoading(false));
  }, [activeModel, activeOverlay, selectedTimeIdx, modelMeta]);

  // Update map overlay
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded() || !modelMeta) return;
    removeLayers(map);
    const vt = modelMeta.validTimes[selectedTimeIdx];
    const ov = OVERLAYS.find(o => o.id === activeOverlay);
    if (!vt || !ov) return;
    const sym = map.getStyle().layers?.find(l => l.type === "symbol")?.id;

    if (activeModel === "rap") {
      if (!rapData) return;
      map.addSource("soaring-rap-src", { type: "geojson", data: rapData as GeoJSON.FeatureCollection });
      map.addLayer({ id: "soaring-rap-layer", type: "heatmap", source: "soaring-rap-src", paint: {
        "heatmap-weight": ["interpolate", ["linear"], ["get", "value"], 0, 0, 2000, 1],
        "heatmap-intensity": 0.9,
        "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(59,130,246,0)", 0.25, "#3b82f6", 0.5, "#22c55e", 0.75, "#eab308", 1, "#ef4444"],
        "heatmap-radius": 32, "heatmap-opacity": opacity / 100,
      }}, sym);
      return;
    }

    if (!protocolRef.current) return;
    const base = `https://map-tiles.open-meteo.com/data_spatial/${activeModel}/latest.json`;
    try {
      map.addSource("soaring-overlay-src", { type: "raster", url: `om://${base}?variable=${ov.omVar}&valid_time=${encodeURIComponent(vt)}`, tileSize: 256, maxzoom: 12 } as maplibregl.RasterSourceSpecification);
      map.addLayer({ id: "soaring-overlay-layer", type: "raster", source: "soaring-overlay-src", paint: { "raster-opacity": opacity / 100 } }, sym);
    } catch {}

    if (showWindArrows) {
      const lvl = activeOverlay.includes("850") ? "850hPa" : activeOverlay.includes("700") ? "700hPa" : activeOverlay.includes("500") ? "500hPa" : "10m";
      const uVar = lvl === "10m" ? "wind_u_component_10m" : `wind_u_component_${lvl}`;
      try {
        map.addSource("soaring-wind-src", { type: "vector", url: `om://${base}?variable=${uVar}&valid_time=${encodeURIComponent(vt)}` } as maplibregl.VectorSourceSpecification);
        map.addLayer({ id: "soaring-wind-layer", type: "line", source: "soaring-wind-src", "source-layer": "wind_arrows", paint: { "line-color": "#0f172a", "line-width": 1.5, "line-opacity": 0.75 } }, sym);
      } catch {}
    }
  }, [activeModel, activeOverlay, selectedTimeIdx, opacity, showWindArrows, modelMeta, rapData]);

  async function handleMapClick(e: maplibregl.MapMouseEvent) {
    const map = mapRef.current;
    if (!map) return;
    const { lat, lng } = e.lngLat;
    const ov = OVERLAYS.find(o => o.id === activeOverlay);
    const hourly = "cape,boundary_layer_height,convective_cloud_top,lifted_index,cloud_cover,precipitation,wind_speed_850hPa,wind_direction_850hPa";
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
      const display = value !== null ? `${Math.round(value as number)} ${ov?.unit ?? ""}` : "N/A";
      return `<tr><td style="padding:3px 8px 3px 0;color:#64748b;font-size:0.78rem">${label}</td><td style="font-weight:600;font-size:0.78rem">${display}</td></tr>`;
    }).join("");
    popup.setHTML(`<div style="padding:4px"><strong style="font-size:0.8rem">${ov?.label ?? activeOverlay}</strong><p style="font-size:0.7rem;color:#64748b;margin:2px 0 8px">${lat.toFixed(3)}N ${Math.abs(lng).toFixed(3)}${lng < 0 ? "W" : "E"}</p><table style="border-collapse:collapse;width:100%">${rows}</table></div>`);
  }

  // Bind click handler
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const handler = (e: maplibregl.MapMouseEvent) => { void handleMapClick(e); };
    map.on("click", handler);
    return () => { map.off("click", handler); };
  });

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
                const unavail = variables.length > 0 && !variables.includes(ov.omVar);
                return (
                  <div key={ov.id}
                    className={[styles.overlayRow, ov.id === activeOverlay ? styles.overlayRowActive : "", unavail ? styles.overlayRowUnavailable : ""].join(" ")}
                    onClick={() => !unavail && setActiveOverlay(ov.id as OverlayId)}
                  >
                    <span>{ov.label}</span>
                    <span className={styles.overlayUnit}>{ov.unit}</span>
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

        {activeOv && (
          <div className={styles.legend}>
            <p className={styles.sectionLabel}>{activeOv.label}</p>
            <div className={styles.legendBar} style={{ background: activeOv.gradient }} />
            <div className={styles.legendLabels}><span>{activeOv.legendMin}</span><span>{activeOv.legendMax}</span></div>
          </div>
        )}
      </div>

      <div className={styles.mapContainer}>
        <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
        {rapLoading && (
          <div style={{ position: "absolute", top: 12, left: "50%", transform: "translateX(-50%)", background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "var(--r-md)", padding: "6px 14px", fontSize: "0.78rem", color: "var(--muted)" }}>
            Fetching RAP data…
          </div>
        )}
      </div>
    </div>
  );
}
