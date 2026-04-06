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
const FT_TO_M = 0.3048;
const MAX_PITCH = 75;

// Source & layer IDs
const SRC_AIRSPACE = "faa-airspace";
const SRC_TFR = "faa-tfr";
const LYR_AIRSPACE_FILL = "faa-airspace-fill";
const LYR_AIRSPACE_EXTRUSION = "faa-airspace-extrusion";
const LYR_AIRSPACE_LINE = "faa-airspace-line";
const LYR_AIRSPACE_LABEL = "faa-airspace-label";
const LYR_TFR_FILL = "faa-tfr-fill";
const LYR_TFR_EXTRUSION = "faa-tfr-extrusion";
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
  const [is3D, setIs3D] = useState(false);

  // Data state — accumulated across pan/zoom, never cleared
  const [airspaceData, setAirspaceData] = useState<GeoJSON.FeatureCollection | null>(null);
  const [tfrData, setTfrData] = useState<GeoJSON.FeatureCollection | null>(null);
  const [loading, setLoading] = useState(false);
  const [tfrLoading, setTfrLoading] = useState(false);
  const [featureCount, setFeatureCount] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // Track which bounds have already been loaded so we don't re-fetch
  const loadedBoundsRef = useRef<{ west: number; south: number; east: number; north: number } | null>(null);
  // Accumulated feature map keyed by a stable ID to deduplicate
  const featureMapRef = useRef<Map<string, GeoJSON.Feature>>(new Map());

  // -------------------------------------------------------------------
  // Fetch airspace for current viewport (accumulates, never replaces)
  // -------------------------------------------------------------------

  const fetchViewportAirspace = useCallback(async (map: maplibregl.Map) => {
    const b = map.getBounds();
    const viewBounds = {
      west: b.getWest(),
      south: b.getSouth(),
      east: b.getEast(),
      north: b.getNorth(),
    };

    // Skip if current viewport is fully inside already-loaded bounds
    const lb = loadedBoundsRef.current;
    if (lb && viewBounds.west >= lb.west && viewBounds.south >= lb.south &&
        viewBounds.east <= lb.east && viewBounds.north <= lb.north) {
      return;
    }

    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);

    try {
      const [classData, suaData] = await Promise.all([
        fetchClassAirspace(viewBounds, ctrl.signal),
        fetchSpecialUseAirspace(viewBounds, ctrl.signal),
      ]);

      if (ctrl.signal.aborted) return;

      // Merge new features into the accumulated map (deduplicate by name+category+bounds key)
      for (const f of [...classData.features, ...suaData.features]) {
        const p = f.properties as { name: string; category: string; lowerVal: number | null; upperVal: number | null };
        const key = `${p.category}:${p.name}:${p.lowerVal}:${p.upperVal}:${hashGeometry(f.geometry)}`;
        featureMapRef.current.set(key, f);
      }

      // Expand loaded bounds to cover both old and new areas
      if (lb) {
        loadedBoundsRef.current = {
          west: Math.min(lb.west, viewBounds.west),
          south: Math.min(lb.south, viewBounds.south),
          east: Math.max(lb.east, viewBounds.east),
          north: Math.max(lb.north, viewBounds.north),
        };
      } else {
        loadedBoundsRef.current = { ...viewBounds };
      }

      const merged: GeoJSON.FeatureCollection = {
        type: "FeatureCollection",
        features: Array.from(featureMapRef.current.values()),
      };

      setAirspaceData(merged);
      setFeatureCount(merged.features.length);

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
      maxPitch: MAX_PITCH,
      attributionControl: {},
    });

    map.addControl(new maplibregl.NavigationControl(), "top-right");
    mapRef.current = map;

    map.on("load", () => {
      // -- Airspace source --
      map.addSource(SRC_AIRSPACE, { type: "geojson", data: { type: "FeatureCollection", features: [] } });

      // 2D flat fill (visible by default)
      map.addLayer({
        id: LYR_AIRSPACE_FILL,
        type: "fill",
        source: SRC_AIRSPACE,
        paint: {
          "fill-color": buildColorMatch("category"),
          "fill-opacity": FILL_OPACITY,
        },
      });

      // 3D extrusion (hidden by default)
      map.addLayer({
        id: LYR_AIRSPACE_EXTRUSION,
        type: "fill-extrusion",
        source: SRC_AIRSPACE,
        layout: { visibility: "none" },
        paint: {
          "fill-extrusion-color": buildColorMatch("category"),
          "fill-extrusion-opacity": 0.16,
          "fill-extrusion-base": extrusionBase(),
          "fill-extrusion-height": extrusionHeight(),
        },
      });

      // Outline
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

      // Labels
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

      // 2D flat TFR fill
      map.addLayer({
        id: LYR_TFR_FILL,
        type: "fill",
        source: SRC_TFR,
        paint: {
          "fill-color": CATEGORY_COLORS.TFR,
          "fill-opacity": 0.25,
        },
      });

      // 3D TFR extrusion (hidden by default — TFRs don't have altitude data,
      // so we render a fixed-height column as a visual indicator)
      map.addLayer({
        id: LYR_TFR_EXTRUSION,
        type: "fill-extrusion",
        source: SRC_TFR,
        layout: { visibility: "none" },
        paint: {
          "fill-extrusion-color": CATEGORY_COLORS.TFR,
          "fill-extrusion-opacity": 0.25,
          "fill-extrusion-base": 0,
          "fill-extrusion-height": 5486, // ~18,000 ft (FL180) in meters
        },
      });

      // TFR outline
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

      // TFR labels
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

    // Click to inspect (both flat and extruded layers)
    for (const lyr of [LYR_AIRSPACE_FILL, LYR_AIRSPACE_EXTRUSION]) {
      map.on("click", lyr, (e) => {
        if (!e.features?.length) return;
        showPopup(map, e.lngLat, e.features[0]);
      });
    }
    for (const lyr of [LYR_TFR_FILL, LYR_TFR_EXTRUSION]) {
      map.on("click", lyr, (e) => {
        if (!e.features?.length) return;
        showPopup(map, e.lngLat, e.features[0]);
      });
    }

    // Cursor hint
    for (const lyr of [LYR_AIRSPACE_FILL, LYR_AIRSPACE_EXTRUSION, LYR_TFR_FILL, LYR_TFR_EXTRUSION]) {
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
  // Sync 3D mode — swap fill ↔ extrusion layers, adjust pitch
  // -------------------------------------------------------------------

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (is3D) {
      // Hide flat fills, show extrusions
      map.setLayoutProperty(LYR_AIRSPACE_FILL, "visibility", "none");
      map.setLayoutProperty(LYR_AIRSPACE_EXTRUSION, "visibility", "visible");
      map.setLayoutProperty(LYR_TFR_FILL, "visibility", "none");
      map.setLayoutProperty(LYR_TFR_EXTRUSION, "visibility", "visible");
      // Tilt into 3D perspective
      map.easeTo({ pitch: 55, duration: 600 });
    } else {
      // Show flat fills, hide extrusions
      map.setLayoutProperty(LYR_AIRSPACE_FILL, "visibility", "visible");
      map.setLayoutProperty(LYR_AIRSPACE_EXTRUSION, "visibility", "none");
      map.setLayoutProperty(LYR_TFR_FILL, "visibility", "visible");
      map.setLayoutProperty(LYR_TFR_EXTRUSION, "visibility", "none");
      // Flatten back to 2D
      map.easeTo({ pitch: 0, duration: 600 });
    }
  }, [is3D]);

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

    const airspaceFilter: maplibregl.FilterSpecification = allVisible.length === 0
      ? ["==", "category", "__none__"]
      : ["in", "category", ...allVisible];

    // Apply to both flat and extruded airspace layers
    map.setFilter(LYR_AIRSPACE_FILL, airspaceFilter);
    map.setFilter(LYR_AIRSPACE_EXTRUSION, airspaceFilter);
    map.setFilter(LYR_AIRSPACE_LINE, airspaceFilter);
    map.setFilter(LYR_AIRSPACE_LABEL, airspaceFilter);

    // TFR visibility — respect both master toggle and 3D layer swapping
    const tfrVisible = showTFRs && visibleCategories.has("TFR");
    if (is3D) {
      map.setLayoutProperty(LYR_TFR_FILL, "visibility", "none");
      map.setLayoutProperty(LYR_TFR_EXTRUSION, "visibility", tfrVisible ? "visible" : "none");
    } else {
      map.setLayoutProperty(LYR_TFR_FILL, "visibility", tfrVisible ? "visible" : "none");
      map.setLayoutProperty(LYR_TFR_EXTRUSION, "visibility", "none");
    }
    map.setLayoutProperty(LYR_TFR_LINE, "visibility", tfrVisible ? "visible" : "none");
    map.setLayoutProperty(LYR_TFR_LABEL, "visibility", tfrVisible ? "visible" : "none");
  }, [visibleCategories, showClassAirspace, showSUA, showTFRs, is3D]);

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
      <div className={styles.mapContainer}>
        <div ref={containerRef} style={{ width: "100%", height: "100%" }} />

        {/* 3D toggle button — bottom-left of map */}
        <button
          type="button"
          className={`${styles.mapBtn} ${is3D ? styles.mapBtnActive : ""}`}
          onClick={() => setIs3D((v) => !v)}
          title={is3D ? "Switch to 2D" : "Switch to 3D"}
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            {is3D ? (
              <>
                <text x="4" y="17" fontSize="14" fontWeight="700" fill="currentColor" stroke="none" fontFamily="system-ui">2D</text>
              </>
            ) : (
              <>
                <text x="4" y="17" fontSize="14" fontWeight="700" fill="currentColor" stroke="none" fontFamily="system-ui">3D</text>
              </>
            )}
          </svg>
        </button>
      </div>
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

/** Extrusion base: lowerVal (feet) converted to meters */
function extrusionBase(): maplibregl.ExpressionSpecification {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return ["max", 0, ["*", ["coalesce", ["get", "lowerVal"], 0], FT_TO_M]] as any;
}

/** Extrusion height: upperVal (feet) converted to meters, fallback to lower+1500m */
function extrusionHeight(): maplibregl.ExpressionSpecification {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return [
    "max", 50,
    ["*",
      ["-",
        ["coalesce", ["get", "upperVal"], ["+", ["coalesce", ["get", "lowerVal"], 0], 4921]],
        ["coalesce", ["get", "lowerVal"], 0],
      ],
      FT_TO_M,
    ],
  ] as any;
}

/** Fast stable hash of geometry coordinates for deduplication */
function hashGeometry(geom: GeoJSON.Geometry): string {
  const coords = geom.type === "Polygon"
    ? geom.coordinates[0]
    : geom.type === "MultiPolygon"
      ? geom.coordinates[0]?.[0] ?? []
      : [];
  if (coords.length === 0) return "empty";
  const first = coords[0];
  const last = coords[coords.length - 1];
  return `${coords.length}:${first[0].toFixed(4)},${first[1].toFixed(4)}:${last[0].toFixed(4)},${last[1].toFixed(4)}`;
}
