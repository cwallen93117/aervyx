"use client";

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState, useCallback } from "react";
import styles from "./AirspaceExplorerMap.module.css";
import {
  type AirspaceCategory,
  CATEGORY_COLORS,
  CATEGORY_LABELS,
  fetchClassAirspace,
  fetchSpecialUseAirspace,
  fetchTFRs,
  downloadOpenAir,
} from "../../lib/faaAirspace";

// ---------------------------------------------------------------------------
// Category groups for the sidebar controls
// ---------------------------------------------------------------------------

const CLASS_CATEGORIES: AirspaceCategory[] = ["B", "C", "D"];
const SUA_CATEGORIES: AirspaceCategory[] = ["P", "R", "W", "A", "MOA"];
const TFR_CATEGORIES: AirspaceCategory[] = ["TFR"];

const ALL_CATEGORIES = [...CLASS_CATEGORIES, ...SUA_CATEGORIES, ...TFR_CATEGORIES];

// ---------------------------------------------------------------------------
// Map style constants
// ---------------------------------------------------------------------------

const FILL_OPACITY = 0.18;
const OUTLINE_WIDTH = 1.5;
const CONUS_CENTER: [number, number] = [-98.5, 39.8];
const INITIAL_ZOOM = 5;

// Source & layer IDs
const SRC_AIRSPACE = "faa-airspace";
const SRC_TFR = "faa-tfr";
const LYR_AIRSPACE_FILL = "faa-airspace-fill";
const LYR_AIRSPACE_LINE = "faa-airspace-line";
const LYR_AIRSPACE_LABEL = "faa-airspace-label";
const LYR_TFR_FILL = "faa-tfr-fill";
const LYR_TFR_LINE = "faa-tfr-line";
const LYR_TFR_LABEL = "faa-tfr-label";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AirspaceExplorerMap() {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const [visibleCategories, setVisibleCategories] = useState<Set<AirspaceCategory>>(
    () => new Set(ALL_CATEGORIES),
  );
  const [showClassAirspace, setShowClassAirspace] = useState(true);
  const [showSUA, setShowSUA] = useState(true);
  const [showTFRs, setShowTFRs] = useState(true);

  // Data state
  const [airspaceData, setAirspaceData] = useState<GeoJSON.FeatureCollection | null>(null);
  const [tfrData, setTfrData] = useState<GeoJSON.FeatureCollection | null>(null);
  const [loading, setLoading] = useState(false);
  const [tfrLoading, setTfrLoading] = useState(false);
  const [featureCount, setFeatureCount] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // -------------------------------------------------------------------
  // Fetch airspace for current viewport
  // -------------------------------------------------------------------

  const fetchViewportAirspace = useCallback(async (map: maplibregl.Map) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const b = map.getBounds();
    const bounds = {
      west: b.getWest(),
      south: b.getSouth(),
      east: b.getEast(),
      north: b.getNorth(),
    };

    setLoading(true);
    setError(null);

    try {
      const [classData, suaData] = await Promise.all([
        fetchClassAirspace(bounds, ctrl.signal),
        fetchSpecialUseAirspace(bounds, ctrl.signal),
      ]);

      if (ctrl.signal.aborted) return;

      const merged: GeoJSON.FeatureCollection = {
        type: "FeatureCollection",
        features: [...classData.features, ...suaData.features],
      };

      setAirspaceData(merged);
      setFeatureCount(merged.features.length);

      // Update map source
      const src = map.getSource(SRC_AIRSPACE) as maplibregl.GeoJSONSource | undefined;
      if (src) {
        src.setData(merged);
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      setError(e instanceof Error ? e.message : "Failed to load airspace");
    } finally {
      if (!ctrl.signal.aborted) setLoading(false);
    }
  }, []);

  // -------------------------------------------------------------------
  // Fetch TFRs (once on mount, refresh every 5 min)
  // -------------------------------------------------------------------

  const fetchTfrData = useCallback(async () => {
    setTfrLoading(true);
    try {
      const data = await fetchTFRs();
      setTfrData(data);

      const map = mapRef.current;
      if (map) {
        const src = map.getSource(SRC_TFR) as maplibregl.GeoJSONSource | undefined;
        if (src) src.setData(data);
      }
    } catch {
      // TFR fetch failure is non-critical
    } finally {
      setTfrLoading(false);
    }
  }, []);

  // -------------------------------------------------------------------
  // Initialize map
  // -------------------------------------------------------------------

  useEffect(() => {
    if (!containerRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "&copy; OpenStreetMap contributors",
          },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
      center: CONUS_CENTER,
      zoom: INITIAL_ZOOM,
      attributionControl: {},
    });

    map.addControl(new maplibregl.NavigationControl(), "top-right");
    mapRef.current = map;

    map.on("load", () => {
      // -- Airspace source + layers --
      map.addSource(SRC_AIRSPACE, { type: "geojson", data: { type: "FeatureCollection", features: [] } });

      map.addLayer({
        id: LYR_AIRSPACE_FILL,
        type: "fill",
        source: SRC_AIRSPACE,
        paint: {
          "fill-color": buildColorMatch("category"),
          "fill-opacity": FILL_OPACITY,
        },
      });

      map.addLayer({
        id: LYR_AIRSPACE_LINE,
        type: "line",
        source: SRC_AIRSPACE,
        paint: {
          "line-color": buildColorMatch("category"),
          "line-width": OUTLINE_WIDTH,
          "line-opacity": 0.7,
        },
      });

      map.addLayer({
        id: LYR_AIRSPACE_LABEL,
        type: "symbol",
        source: SRC_AIRSPACE,
        layout: {
          "text-field": ["get", "name"],
          "text-size": 11,
          "text-allow-overlap": false,
          "text-ignore-placement": false,
          "symbol-placement": "point",
        },
        paint: {
          "text-color": "#e2e8f0",
          "text-halo-color": "#0f172a",
          "text-halo-width": 1.2,
        },
        minzoom: 8,
      });

      // -- TFR source + layers --
      map.addSource(SRC_TFR, { type: "geojson", data: { type: "FeatureCollection", features: [] } });

      map.addLayer({
        id: LYR_TFR_FILL,
        type: "fill",
        source: SRC_TFR,
        paint: {
          "fill-color": CATEGORY_COLORS.TFR,
          "fill-opacity": 0.25,
        },
      });

      map.addLayer({
        id: LYR_TFR_LINE,
        type: "line",
        source: SRC_TFR,
        paint: {
          "line-color": CATEGORY_COLORS.TFR,
          "line-width": 2,
          "line-dasharray": [4, 2],
        },
      });

      map.addLayer({
        id: LYR_TFR_LABEL,
        type: "symbol",
        source: SRC_TFR,
        layout: {
          "text-field": ["get", "name"],
          "text-size": 12,
          "text-font": ["Open Sans Bold"],
          "text-allow-overlap": false,
          "symbol-placement": "point",
        },
        paint: {
          "text-color": "#fca5a5",
          "text-halo-color": "#450a0a",
          "text-halo-width": 1.2,
        },
        minzoom: 6,
      });

      // Initial fetch
      void fetchViewportAirspace(map);
      void fetchTfrData();
    });

    // Reload airspace when user stops panning/zooming
    let debounce: ReturnType<typeof setTimeout>;
    map.on("moveend", () => {
      clearTimeout(debounce);
      debounce = setTimeout(() => void fetchViewportAirspace(map), 400);
    });

    // Click to inspect
    map.on("click", LYR_AIRSPACE_FILL, (e) => {
      if (!e.features?.length) return;
      showPopup(map, e.lngLat, e.features[0]);
    });
    map.on("click", LYR_TFR_FILL, (e) => {
      if (!e.features?.length) return;
      showPopup(map, e.lngLat, e.features[0]);
    });

    // Cursor hint
    for (const lyr of [LYR_AIRSPACE_FILL, LYR_TFR_FILL]) {
      map.on("mouseenter", lyr, () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", lyr, () => { map.getCanvas().style.cursor = ""; });
    }

    // TFR refresh interval
    const tfrInterval = setInterval(() => void fetchTfrData(), 5 * 60 * 1000);

    return () => {
      clearInterval(tfrInterval);
      clearTimeout(debounce);
      abortRef.current?.abort();
      map.remove();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // -------------------------------------------------------------------
  // Sync layer visibility with category toggles
  // -------------------------------------------------------------------

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    // Build a filter for the airspace source based on visible categories
    const classVisible = showClassAirspace ? CLASS_CATEGORIES.filter((c) => visibleCategories.has(c)) : [];
    const suaVisible = showSUA ? SUA_CATEGORIES.filter((c) => visibleCategories.has(c)) : [];
    const allVisible = [...classVisible, ...suaVisible];

    if (allVisible.length === 0) {
      map.setFilter(LYR_AIRSPACE_FILL, ["==", "category", "__none__"]);
      map.setFilter(LYR_AIRSPACE_LINE, ["==", "category", "__none__"]);
      map.setFilter(LYR_AIRSPACE_LABEL, ["==", "category", "__none__"]);
    } else {
      const filter: maplibregl.FilterSpecification = ["in", "category", ...allVisible];
      map.setFilter(LYR_AIRSPACE_FILL, filter);
      map.setFilter(LYR_AIRSPACE_LINE, filter);
      map.setFilter(LYR_AIRSPACE_LABEL, filter);
    }

    // TFR visibility
    const tfrVisible = showTFRs && visibleCategories.has("TFR");
    map.setLayoutProperty(LYR_TFR_FILL, "visibility", tfrVisible ? "visible" : "none");
    map.setLayoutProperty(LYR_TFR_LINE, "visibility", tfrVisible ? "visible" : "none");
    map.setLayoutProperty(LYR_TFR_LABEL, "visibility", tfrVisible ? "visible" : "none");
  }, [visibleCategories, showClassAirspace, showSUA, showTFRs]);

  // -------------------------------------------------------------------
  // Popup helper
  // -------------------------------------------------------------------

  function showPopup(map: maplibregl.Map, lngLat: maplibregl.LngLat, feature: maplibregl.MapGeoJSONFeature) {
    popupRef.current?.remove();
    const p = feature.properties;
    const cat = p.category as AirspaceCategory;
    const color = CATEGORY_COLORS[cat] ?? "#94a3b8";
    const label = CATEGORY_LABELS[cat] ?? cat;

    const upper = p.upperVal != null && Number(p.upperVal) > 0 ? `${p.upperVal} ${p.upperUom}` : "Unlimited";
    const lower = p.lowerVal != null && Number(p.lowerVal) > 0 ? `${p.lowerVal} ${p.lowerUom}` : "SFC";
    const loc = [p.city, p.state].filter(Boolean).join(", ");

    const html = `
      <div style="font-family:var(--ff-body,system-ui);font-size:13px;max-width:260px">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
          <span style="width:10px;height:10px;border-radius:2px;background:${color};flex-shrink:0"></span>
          <strong>${label}</strong>
        </div>
        <div style="font-weight:600;margin-bottom:2px">${p.name ?? "Unknown"}</div>
        ${loc ? `<div style="color:#94a3b8;font-size:12px;margin-bottom:4px">${loc}</div>` : ""}
        <div style="font-size:12px;color:#cbd5e1">
          <span>Floor: ${lower}</span> · <span>Ceiling: ${upper}</span>
        </div>
      </div>
    `;

    popupRef.current = new maplibregl.Popup({ closeButton: true, maxWidth: "300px" })
      .setLngLat(lngLat)
      .setHTML(html)
      .addTo(map);
  }

  // -------------------------------------------------------------------
  // Category toggle handler
  // -------------------------------------------------------------------

  function toggleCategory(cat: AirspaceCategory) {
    setVisibleCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  }

  // -------------------------------------------------------------------
  // Export handler
  // -------------------------------------------------------------------

  function handleExport() {
    const allFeatures = [
      ...(airspaceData?.features ?? []),
      ...(showTFRs ? tfrData?.features ?? [] : []),
    ].filter((f) => {
      const cat = (f.properties as { category: AirspaceCategory }).category;
      return visibleCategories.has(cat);
    });

    if (allFeatures.length === 0) return;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    downloadOpenAir(allFeatures as any, "airspace-export.txt");
  }

  // -------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------

  return (
    <div className={styles.shell}>
      {/* Left sidebar controls */}
      <div className={styles.leftPanel}>
        {/* Status */}
        <div className={styles.statusRow}>
          <span className={`${styles.dot} ${loading || tfrLoading ? styles.dotLoading : error ? styles.dotError : styles.dotReady}`} />
          {loading ? "Loading airspace..." : error ? error : `${featureCount} features loaded`}
        </div>

        {/* Controlled airspace */}
        <div className={styles.section}>
          <div className={styles.sectionLabel}>Controlled Airspace</div>
          <label className={styles.categoryRow} style={{ marginBottom: 6, fontWeight: 600 }}>
            <input type="checkbox" checked={showClassAirspace} onChange={() => setShowClassAirspace((v) => !v)} />
            Show All
          </label>
          {CLASS_CATEGORIES.map((cat) => (
            <label key={cat} className={styles.categoryRow}>
              <input
                type="checkbox"
                checked={visibleCategories.has(cat) && showClassAirspace}
                onChange={() => toggleCategory(cat)}
                disabled={!showClassAirspace}
              />
              <span className={styles.swatch} style={{ background: CATEGORY_COLORS[cat] }} />
              {CATEGORY_LABELS[cat]}
            </label>
          ))}
        </div>

        {/* Special Use Airspace */}
        <div className={styles.section}>
          <div className={styles.sectionLabel}>Special Use Airspace</div>
          <label className={styles.categoryRow} style={{ marginBottom: 6, fontWeight: 600 }}>
            <input type="checkbox" checked={showSUA} onChange={() => setShowSUA((v) => !v)} />
            Show All
          </label>
          {SUA_CATEGORIES.map((cat) => (
            <label key={cat} className={styles.categoryRow}>
              <input
                type="checkbox"
                checked={visibleCategories.has(cat) && showSUA}
                onChange={() => toggleCategory(cat)}
                disabled={!showSUA}
              />
              <span className={styles.swatch} style={{ background: CATEGORY_COLORS[cat] }} />
              {CATEGORY_LABELS[cat]}
            </label>
          ))}
        </div>

        {/* TFRs */}
        <div className={styles.section}>
          <div className={styles.sectionLabel}>Temporary Flight Restrictions</div>
          <label className={styles.categoryRow}>
            <input type="checkbox" checked={showTFRs} onChange={() => setShowTFRs((v) => !v)} />
            <span className={styles.swatch} style={{ background: CATEGORY_COLORS.TFR }} />
            Active TFRs
          </label>
          <div style={{ fontSize: "0.72rem", color: "var(--muted)", marginTop: 4 }}>
            Defense airspace TFRs &middot; refreshes every 5 min
          </div>
        </div>

        {/* Export */}
        <div className={styles.section}>
          <button
            type="button"
            className={styles.exportBtn}
            onClick={handleExport}
            disabled={featureCount === 0 && !tfrData?.features.length}
          >
            <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M8 2v8M5 7l3 3 3-3M3 12h10" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Export OpenAir (.txt)
          </button>
          <div style={{ fontSize: "0.72rem", color: "var(--muted)", marginTop: 6 }}>
            Exports visible airspace in OpenAir format for XC Tracer, Flymaster, Syride, etc.
          </div>
        </div>

        {/* Legend */}
        <div className={styles.legend}>
          <div className={styles.legendTitle}>Legend</div>
          {ALL_CATEGORIES.filter((c) => visibleCategories.has(c)).map((cat) => (
            <div key={cat} className={styles.legendItem}>
              <span className={styles.swatch} style={{ background: CATEGORY_COLORS[cat] }} />
              {CATEGORY_LABELS[cat]}
            </div>
          ))}
        </div>
      </div>

      {/* Map */}
      <div ref={containerRef} className={styles.mapContainer} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildColorMatch(prop: string): maplibregl.ExpressionSpecification {
  const entries: (string)[] = [];
  for (const [cat, color] of Object.entries(CATEGORY_COLORS)) {
    entries.push(cat, color);
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return ["match", ["get", prop], ...entries, "#94a3b8"] as any;
}
