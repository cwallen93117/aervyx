"use client";

import maplibregl, { GeoJSONSource } from "maplibre-gl";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";

export type MapTurnpoint = { id: number; name: string; code: string | null; latitude: number; longitude: number };
export type MapTaskPoint = { position: number; point_type: string; radius_m: number; name: string; latitude: number; longitude: number };
type TrackPosition = [number, number] | [number, number, number];
export type MapAirspaceRegion = {
  id: number;
  source_id: number;
  name: string;
  class_code: string | null;
  type_code: string | null;
  display_category: string;
  lower_limit_label: string | null;
  upper_limit_label: string | null;
  geometry_json: { type: string; coordinates: number[][][] };
  label_latitude: number | null;
  label_longitude: number | null;
  is_restricted_field: boolean;
};
export type TrackCollection = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    properties: Record<string, unknown> & { timestamps?: string[] };
    geometry: { type: string; coordinates: TrackPosition[] };
  }>;
};
export type MapLegMetric = { index: number; centerDistanceKm: number; optimizedDistanceKm: number; midpoint: [number, number] };
type BasemapMode = "streets" | "satellite" | "terrain";
const REPLAY_SPEEDS = [1, 2, 5, 10, 30, 60, 120, 300] as const;

function createBasemapStyle(basemapMode: BasemapMode) {
  const basemapSourceByMode: Record<BasemapMode, { tiles: string[]; attribution: string }> = {
    streets: {
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      attribution: "OpenStreetMap contributors",
    },
    satellite: {
      tiles: ["https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
      attribution: "Esri World Imagery",
    },
    terrain: {
      tiles: ["https://tile.opentopomap.org/{z}/{x}/{y}.png"],
      attribution: "OpenTopoMap contributors",
    },
  };

  return {
    version: 8,
    sources: {
      basemap: {
        type: "raster",
        tiles: basemapSourceByMode[basemapMode].tiles,
        tileSize: 256,
        attribution: basemapSourceByMode[basemapMode].attribution,
      },
    },
    layers: [
      { id: "map-background", type: "background", paint: { "background-color": "#e7eef5" } },
      { id: "basemap", type: "raster", source: "basemap" },
    ],
  } as const;
}

function buildCircle(point: MapTaskPoint) {
  const earthRadius = 6378137;
  const angularDistance = point.radius_m / earthRadius;
  const lat = (point.latitude * Math.PI) / 180;
  const lon = (point.longitude * Math.PI) / 180;
  const coordinates: number[][] = [];
  for (let step = 0; step <= 48; step += 1) {
    const bearing = (2 * Math.PI * step) / 48;
    const nextLat = Math.asin(Math.sin(lat) * Math.cos(angularDistance) + Math.cos(lat) * Math.sin(angularDistance) * Math.cos(bearing));
    const nextLon = lon + Math.atan2(Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(lat), Math.cos(angularDistance) - Math.sin(lat) * Math.sin(nextLat));
    coordinates.push([(nextLon * 180) / Math.PI, (nextLat * 180) / Math.PI]);
  }
  return { type: "Feature", properties: { name: point.name, point_type: point.point_type }, geometry: { type: "Polygon", coordinates: [coordinates] } };
}

function ensureGeoJsonSource(map: maplibregl.Map, id: string, data: Record<string, unknown>) {
  const source = map.getSource(id) as GeoJSONSource | undefined;
  if (source) {
    source.setData(data as never);
    return;
  }
  map.addSource(id, { type: "geojson", data: data as never });
}

function scaleTrackPosition(position: TrackPosition, altitudeMultiplier: number): TrackPosition {
  if (position.length < 3) {
    return position;
  }
  const altitude = position[2] ?? 0;
  return [position[0], position[1], altitude * altitudeMultiplier];
}

function formatUtcTimeLabel(timestampMs: number | null | undefined, includeSeconds = false): string {
  if (timestampMs == null || Number.isNaN(timestampMs)) {
    return "--:--";
  }
  return new Date(timestampMs).toLocaleTimeString([], {
    timeZone: "UTC",
    hour: "2-digit",
    minute: "2-digit",
    second: includeSeconds ? "2-digit" : undefined,
    hour12: false,
  });
}

function ensureMapLayers(map: maplibregl.Map) {
  if (!map.getLayer("airspaces-fill")) {
    map.addLayer({
      id: "airspaces-fill",
      type: "fill",
      source: "airspaces",
      paint: {
        "fill-color": [
          "match",
          ["get", "display_category"],
          "B", "#2563eb",
          "C", "#f59e0b",
          "D", "#14b8a6",
          "P", "#dc2626",
          "Q", "#db2777",
          "R", "#7c3aed",
          "TFR", "#0f172a",
          "RESTRICTED_FIELD", "#b91c1c",
          "#64748b",
        ],
        "fill-opacity": [
          "case",
          ["get", "is_restricted_field"],
          0.22,
          0.12,
        ],
      },
    });
  }
  if (!map.getLayer("airspaces-outline")) {
    map.addLayer({
      id: "airspaces-outline",
      type: "line",
      source: "airspaces",
      paint: {
        "line-color": [
          "match",
          ["get", "display_category"],
          "B", "#2563eb",
          "C", "#d97706",
          "D", "#0f766e",
          "P", "#dc2626",
          "Q", "#db2777",
          "R", "#7c3aed",
          "TFR", "#0f172a",
          "RESTRICTED_FIELD", "#991b1b",
          "#475569",
        ],
        "line-width": [
          "case",
          ["get", "is_restricted_field"],
          2.5,
          1.5,
        ],
        "line-dasharray": [
          "case",
          ["get", "is_restricted_field"],
          ["literal", [2, 1]],
          ["literal", [1, 0]],
        ],
      },
    });
  }
  if (!map.getLayer("airspace-labels")) {
    map.addLayer({
      id: "airspace-labels",
      type: "symbol",
      source: "airspace-labels",
      layout: {
        "text-field": ["get", "label"],
        "text-size": 10,
        "text-anchor": "center",
        "text-allow-overlap": false,
        "text-max-width": 14,
      },
      paint: {
        "text-color": "#0f172a",
        "text-halo-color": "rgba(255,255,255,0.96)",
        "text-halo-width": 1.2,
      },
    });
  }
  if (!map.getLayer("turnpoints-layer")) {
    map.addLayer({ id: "turnpoints-layer", type: "circle", source: "turnpoints", paint: { "circle-radius": 5, "circle-color": "#0f766e", "circle-stroke-width": 1, "circle-stroke-color": "#ffffff" } });
  }
  if (!map.getLayer("turnpoints-labels")) {
    map.addLayer({
      id: "turnpoints-labels",
      type: "symbol",
      source: "turnpoints",
      layout: {
        "text-field": ["get", "name"],
        "text-size": 11,
        "text-offset": [0, 1.15],
        "text-anchor": "top",
        "text-optional": true,
      },
      paint: {
        "text-color": "#10203a",
        "text-halo-color": "#ffffff",
        "text-halo-width": 1.2,
      },
    });
  }
  if (!map.getLayer("task-cylinders-fill")) {
    map.addLayer({
      id: "task-cylinders-fill",
      type: "fill",
      source: "task-cylinders",
      paint: {
        "fill-color": [
          "match",
          ["get", "point_type"],
          "launch", "#f97316",
          "start", "#2563eb",
          "ESS", "#7c3aed",
          "goal", "#16a34a",
          "#ef4444",
        ],
        "fill-opacity": 0.12,
      },
    });
  }
  if (!map.getLayer("task-cylinders-outline")) {
    map.addLayer({
      id: "task-cylinders-outline",
      type: "line",
      source: "task-cylinders",
      paint: {
        "line-color": [
          "match",
          ["get", "point_type"],
          "launch", "#f97316",
          "start", "#2563eb",
          "ESS", "#7c3aed",
          "goal", "#16a34a",
          "#ef4444",
        ],
        "line-width": 2,
      },
    });
  }
  if (!map.getLayer("task-route-layer")) {
    map.addLayer({ id: "task-route-layer", type: "line", source: "task-route", paint: { "line-color": "#1d4ed8", "line-width": 3 } });
  }
  if (!map.getLayer("optimized-route-layer")) {
    map.addLayer({
      id: "optimized-route-layer",
      type: "line",
      source: "optimized-route",
      layout: {
        "line-cap": "round",
        "line-join": "round",
      },
      paint: {
        "line-color": "#2563eb",
        "line-width": 2,
        "line-dasharray": [2, 2],
      },
    });
  }
  if (!map.getLayer("optimized-route-points")) {
    map.addLayer({
      id: "optimized-route-points",
      type: "circle",
      source: "optimized-route-points",
      paint: {
        "circle-radius": 4,
        "circle-color": "#2563eb",
        "circle-stroke-width": 1.2,
        "circle-stroke-color": "#ffffff",
      },
    });
  }
  if (!map.getLayer("optimized-leg-labels")) {
    map.addLayer({
      id: "optimized-leg-labels",
      type: "symbol",
      source: "optimized-leg-labels",
      layout: {
        "text-field": ["get", "label"],
        "text-size": 11,
        "text-anchor": "center",
        "text-offset": [0, -0.2],
        "text-allow-overlap": true,
        "text-ignore-placement": true,
      },
      paint: {
        "text-color": "#0f172a",
        "text-halo-color": "rgba(255,255,255,0.96)",
        "text-halo-width": 1.4,
      },
    });
  }
  if (!map.getLayer("task-points-layer")) {
    map.addLayer({
      id: "task-points-layer",
      type: "circle",
      source: "task-points",
      paint: {
        "circle-radius": 7,
        "circle-color": [
          "match",
          ["get", "point_type"],
          "launch", "#f97316",
          "start", "#2563eb",
          "ESS", "#7c3aed",
          "goal", "#16a34a",
          "#dc2626",
        ],
        "circle-stroke-width": 1.5,
        "circle-stroke-color": "#ffffff",
      },
    });
  }
  if (!map.getLayer("track-layer")) {
    map.addLayer({
      id: "track-layer",
      type: "line",
      source: "track",
      paint: {
        "line-color": ["coalesce", ["get", "color"], "#ca8a04"],
        "line-width": 3,
      },
    });
  }
  if (!map.getLayer("replay-marker-layer")) {
    map.addLayer({
      id: "replay-marker-layer",
      type: "circle",
      source: "replay-marker",
      paint: {
        "circle-radius": 8,
        "circle-color": "#ffffff",
        "circle-stroke-width": 3,
        "circle-stroke-color": "#2563eb",
      },
    });
  }
}

function fitToData(map: maplibregl.Map, turnpoints: MapTurnpoint[], taskPoints: MapTaskPoint[], optimizedRoute: [number, number][], track: TrackCollection | null) {
  const bounds = new maplibregl.LngLatBounds();
  let hasData = false;

  for (const turnpoint of turnpoints) {
    bounds.extend([turnpoint.longitude, turnpoint.latitude]);
    hasData = true;
  }
  for (const point of taskPoints) {
    bounds.extend([point.longitude, point.latitude]);
    hasData = true;
  }
  for (const coordinate of optimizedRoute) {
    bounds.extend(coordinate);
    hasData = true;
  }
  if (track) {
    for (const feature of track.features) {
      if (feature.geometry.type !== "LineString") {
        continue;
      }
      for (const coordinate of feature.geometry.coordinates) {
        bounds.extend([coordinate[0], coordinate[1]]);
        hasData = true;
      }
    }
  }

  if (!hasData) {
    return;
  }
  map.fitBounds(bounds, { padding: 48, maxZoom: 11, duration: 0 });
}

export function TaskMap({
  turnpoints,
  airspaces = [],
  taskPoints,
  optimizedRoute = [],
  legMetrics = [],
  totalDistanceKm = 0,
  optimizedDistanceKm = 0,
  track,
  editable,
  onSelectTurnpoint,
  taskEditorOverlay,
  fitKey,
}: {
  turnpoints: MapTurnpoint[];
  airspaces?: MapAirspaceRegion[];
  taskPoints: MapTaskPoint[];
  optimizedRoute?: [number, number][];
  legMetrics?: MapLegMetric[];
  totalDistanceKm?: number;
  optimizedDistanceKm?: number;
  track: TrackCollection | null;
  editable: boolean;
  onSelectTurnpoint?: (turnpoint: MapTurnpoint) => void;
  taskEditorOverlay?: ReactNode;
  fitKey?: string | number | null;
}) {
  const shellRef = useRef<HTMLDivElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const turnpointsRef = useRef(turnpoints);
  const taskPointsRef = useRef(taskPoints);
  const optimizedRouteRef = useRef(optimizedRoute);
  const trackRef = useRef(track);
  const turnpointSignatureRef = useRef("");
  const taskSignatureRef = useRef("");
  const trackSignatureRef = useRef("");
  const fitKeyRef = useRef<string>("");
  const editableRef = useRef(editable);
  const onSelectTurnpointRef = useRef(onSelectTurnpoint);
  const animationFrameRef = useRef<number | null>(null);
  const lastFrameTimeRef = useRef<number | null>(null);
  const replayIndexRef = useRef(0);
  const [basemapMode, setBasemapMode] = useState<BasemapMode>("streets");
  const [altitudeMultiplier, setAltitudeMultiplier] = useState(10);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isReplaying, setIsReplaying] = useState(false);
  const [replayIndex, setReplayIndex] = useState(0);
  const [replaySpeed, setReplaySpeed] = useState(10);

  const turnpointData = useMemo(() => ({ type: "FeatureCollection", features: turnpoints.map((turnpoint) => ({ type: "Feature", properties: { id: turnpoint.id, name: turnpoint.name, code: turnpoint.code ?? "" }, geometry: { type: "Point", coordinates: [turnpoint.longitude, turnpoint.latitude] } })) }), [turnpoints]);
  const airspaceData = useMemo(() => ({
    type: "FeatureCollection",
    features: airspaces.map((airspace) => ({
      type: "Feature",
      properties: {
        id: airspace.id,
        name: airspace.name,
        display_category: airspace.display_category,
        class_code: airspace.class_code ?? "",
        type_code: airspace.type_code ?? "",
        lower_limit_label: airspace.lower_limit_label ?? "",
        upper_limit_label: airspace.upper_limit_label ?? "",
        is_restricted_field: airspace.is_restricted_field,
      },
      geometry: airspace.geometry_json,
    })),
  }), [airspaces]);
  const airspaceLabelData = useMemo(() => ({
    type: "FeatureCollection",
    features: airspaces
      .filter((airspace) => airspace.label_latitude !== null && airspace.label_longitude !== null)
      .map((airspace) => ({
        type: "Feature",
        properties: {
          label: `${airspace.name}\n${airspace.lower_limit_label ?? "SFC"} - ${airspace.upper_limit_label ?? "UNL"}`,
        },
        geometry: {
          type: "Point",
          coordinates: [airspace.label_longitude as number, airspace.label_latitude as number],
        },
      })),
  }), [airspaces]);
  const taskPointData = useMemo(() => ({ type: "FeatureCollection", features: taskPoints.map((point) => ({ type: "Feature", properties: { name: point.name, point_type: point.point_type }, geometry: { type: "Point", coordinates: [point.longitude, point.latitude] } })) }), [taskPoints]);
  const routeData = useMemo(() => ({ type: "FeatureCollection", features: taskPoints.length > 1 ? [{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: taskPoints.map((point) => [point.longitude, point.latitude]) } }] : [] }), [taskPoints]);
  const optimizedRouteData = useMemo(() => ({ type: "FeatureCollection", features: optimizedRoute.length > 1 ? [{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: optimizedRoute } }] : [] }), [optimizedRoute]);
  const optimizedRoutePointData = useMemo(() => ({
    type: "FeatureCollection",
    features: optimizedRoute.map((coordinate, index) => ({
      type: "Feature",
      properties: { index: index + 1 },
      geometry: { type: "Point", coordinates: coordinate },
    })),
  }), [optimizedRoute]);
  const legLabelData = useMemo(() => ({
    type: "FeatureCollection",
    features: legMetrics.map((leg) => ({
      type: "Feature",
      properties: { label: `${leg.optimizedDistanceKm.toFixed(1)} km` },
      geometry: { type: "Point", coordinates: leg.midpoint },
    })),
  }), [legMetrics]);
  const cylinderData = useMemo(() => ({ type: "FeatureCollection", features: taskPoints.map(buildCircle) }), [taskPoints]);
  const replayTimestamps = useMemo(() => {
    const firstFeature = track?.features[0];
    const raw = firstFeature?.properties?.timestamps;
    if (!Array.isArray(raw)) {
      return [];
    }
    return raw
      .map((value) => Date.parse(String(value)))
      .filter((value) => Number.isFinite(value));
  }, [track]);
  const replayTotal = replayTimestamps.length;
  const displayTrack = useMemo<TrackCollection | null>(() => {
    if (!track) {
      return null;
    }
    const hasReplay = replayTotal > 0;
    return {
      type: "FeatureCollection",
      features: track.features.map((feature) => {
        const featureTimestamps = Array.isArray(feature.properties?.timestamps) ? feature.properties.timestamps : [];
        const visibleLength = hasReplay
          ? Math.min(replayIndex + 1, featureTimestamps.length || feature.geometry.coordinates.length)
          : feature.geometry.coordinates.length;
        return {
          ...feature,
          geometry: {
            ...feature.geometry,
            coordinates: feature.geometry.coordinates
              .slice(0, visibleLength)
              .map((coordinate) => scaleTrackPosition(coordinate, altitudeMultiplier)),
          },
        };
      }),
    };
  }, [altitudeMultiplier, replayIndex, replayTotal, track]);
  const replayMarkerData = useMemo(() => {
    if (!track || !replayTotal) {
      return { type: "FeatureCollection", features: [] as Array<Record<string, unknown>> };
    }
    const firstFeature = track.features[0];
    const coordinate = firstFeature?.geometry.coordinates[Math.min(replayIndex, firstFeature.geometry.coordinates.length - 1)];
    if (!coordinate) {
      return { type: "FeatureCollection", features: [] as Array<Record<string, unknown>> };
    }
    return {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: {},
          geometry: {
            type: "Point",
            coordinates: scaleTrackPosition(coordinate, altitudeMultiplier),
          },
        },
      ],
    };
  }, [altitudeMultiplier, replayIndex, replayTotal, track]);

  useEffect(() => {
    turnpointsRef.current = turnpoints;
  }, [turnpoints]);

  useEffect(() => {
    taskPointsRef.current = taskPoints;
  }, [taskPoints]);

  useEffect(() => {
    optimizedRouteRef.current = optimizedRoute;
  }, [optimizedRoute]);

  useEffect(() => {
    trackRef.current = track;
  }, [track]);

  useEffect(() => {
    replayIndexRef.current = replayIndex;
  }, [replayIndex]);

  useEffect(() => {
    editableRef.current = editable;
    onSelectTurnpointRef.current = onSelectTurnpoint;
  }, [editable, onSelectTurnpoint]);

  useEffect(() => {
    setIsReplaying(false);
    setReplayIndex(0);
    replayIndexRef.current = 0;
    lastFrameTimeRef.current = null;
    if (animationFrameRef.current !== null) {
      window.cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
  }, [track]);

  useEffect(() => {
    if (!isReplaying || replayTotal <= 1) {
      if (animationFrameRef.current !== null) {
        window.cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
      lastFrameTimeRef.current = null;
      return;
    }

    const step = (now: number) => {
      if (lastFrameTimeRef.current == null) {
        lastFrameTimeRef.current = now;
        animationFrameRef.current = window.requestAnimationFrame(step);
        return;
      }
      const deltaMs = now - lastFrameTimeRef.current;
      lastFrameTimeRef.current = now;
      const currentIndex = replayIndexRef.current;
      if (currentIndex >= replayTotal - 1) {
        setIsReplaying(false);
        animationFrameRef.current = null;
        return;
      }
      const currentFlightTime = replayTimestamps[currentIndex];
      const targetFlightTime = currentFlightTime + deltaMs * replaySpeed;
      let nextIndex = currentIndex;
      while (nextIndex + 1 < replayTotal && replayTimestamps[nextIndex + 1] <= targetFlightTime) {
        nextIndex += 1;
      }
      if (nextIndex !== currentIndex) {
        replayIndexRef.current = nextIndex;
        setReplayIndex(nextIndex);
      }
      if (nextIndex >= replayTotal - 1) {
        setIsReplaying(false);
        animationFrameRef.current = null;
        return;
      }
      animationFrameRef.current = window.requestAnimationFrame(step);
    };

    animationFrameRef.current = window.requestAnimationFrame(step);
    return () => {
      if (animationFrameRef.current !== null) {
        window.cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
      lastFrameTimeRef.current = null;
    };
  }, [isReplaying, replaySpeed, replayTimestamps, replayTotal]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return;
    }
    const container = containerRef.current;
    const shell = shellRef.current;
    try {
      const map = new maplibregl.Map({
        container,
        style: createBasemapStyle(basemapMode) as never,
        center: [-118.18, 36.73],
        zoom: 9,
        attributionControl: false,
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-right");
      map.addControl(new maplibregl.FullscreenControl({ container: shell ?? undefined }), "top-right");
      map.on("styledata", () => {
        map.resize();
      });
      map.on("click", (event) => {
        if (!editableRef.current || !onSelectTurnpointRef.current) {
          return;
        }
        const features = map.queryRenderedFeatures(event.point, { layers: ["turnpoints-layer"] });
        const turnpointId = Number(features[0]?.properties?.id);
        if (!turnpointId) {
          return;
        }
        const selectedTurnpoint = turnpointsRef.current.find((turnpoint) => turnpoint.id === turnpointId);
        if (selectedTurnpoint) {
          onSelectTurnpointRef.current(selectedTurnpoint);
        }
      });
      const resizeObserver = new ResizeObserver(() => {
        map.resize();
      });
      resizeObserver.observe(container);
      if (shell) {
        resizeObserver.observe(shell);
      }
      const handleFullscreenChange = () => {
        const fullscreenElement = document.fullscreenElement ?? ((document as Document & { webkitFullscreenElement?: Element | null }).webkitFullscreenElement ?? null);
        setIsFullscreen(fullscreenElement === shell);
        window.setTimeout(() => map.resize(), 0);
        window.setTimeout(() => {
          map.resize();
          fitToData(map, turnpointsRef.current, taskPointsRef.current, optimizedRouteRef.current, trackRef.current ?? null);
        }, 150);
      };
      document.addEventListener("fullscreenchange", handleFullscreenChange);
      document.addEventListener("webkitfullscreenchange", handleFullscreenChange as EventListener);
      window.setTimeout(() => map.resize(), 0);
      mapRef.current = map;
      return () => {
        resizeObserver.disconnect();
        document.removeEventListener("fullscreenchange", handleFullscreenChange);
        document.removeEventListener("webkitfullscreenchange", handleFullscreenChange as EventListener);
        map.remove();
        mapRef.current = null;
      };
    } catch (error) {
      console.error("Map failed to initialize.", error);
      return;
    }
  }, []);

  useEffect(() => {
    if (mapRef.current) {
      mapRef.current.setStyle(createBasemapStyle(basemapMode) as never);
    }
  }, [basemapMode]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    const nextTurnpointSignature = turnpoints.map((turnpoint) => `${turnpoint.id}:${turnpoint.latitude.toFixed(4)}:${turnpoint.longitude.toFixed(4)}`).join("|");
    const nextTaskSignature = taskPoints
      .map((point, index) => `${index}:${point.position}:${point.name}:${point.latitude.toFixed(5)}:${point.longitude.toFixed(5)}`)
      .join("|");
    const nextTrackSignature = track ? `${track.features.length}:${JSON.stringify(track.features[0]?.geometry?.coordinates?.[0] ?? [])}` : "";
    const nextFitKey = String(fitKey ?? "");
    const shouldFitToTurnpoints = nextTurnpointSignature !== turnpointSignatureRef.current;
    const shouldFitToTask = nextFitKey !== fitKeyRef.current;
    const shouldFitToTrack = nextTrackSignature !== trackSignatureRef.current;

    const syncData = () => {
      ensureGeoJsonSource(map, "turnpoints", turnpointData as never);
      ensureGeoJsonSource(map, "airspaces", airspaceData as never);
      ensureGeoJsonSource(map, "airspace-labels", airspaceLabelData as never);
      ensureGeoJsonSource(map, "task-points", taskPointData as never);
      ensureGeoJsonSource(map, "task-route", routeData as never);
      ensureGeoJsonSource(map, "optimized-route", optimizedRouteData as never);
      ensureGeoJsonSource(map, "optimized-route-points", optimizedRoutePointData as never);
      ensureGeoJsonSource(map, "optimized-leg-labels", legLabelData as never);
      ensureGeoJsonSource(map, "task-cylinders", cylinderData as never);
      ensureGeoJsonSource(map, "track", (displayTrack ?? { type: "FeatureCollection", features: [] }) as never);
      ensureGeoJsonSource(map, "replay-marker", replayMarkerData as never);
      ensureMapLayers(map);
      map.resize();
      if (shouldFitToTurnpoints || shouldFitToTask || shouldFitToTrack) {
        fitToData(map, turnpoints, taskPoints, optimizedRoute, track ?? null);
      }
      window.setTimeout(() => {
        map.resize();
        if (shouldFitToTurnpoints || shouldFitToTask || shouldFitToTrack) {
          fitToData(map, turnpoints, taskPoints, optimizedRoute, track ?? null);
        }
      }, 100);
      turnpointSignatureRef.current = nextTurnpointSignature;
      taskSignatureRef.current = nextTaskSignature;
      trackSignatureRef.current = nextTrackSignature;
      fitKeyRef.current = nextFitKey;
    };
    if (map.isStyleLoaded()) {
      syncData();
    } else {
      map.once("styledata", syncData);
    }
  }, [airspaceData, airspaceLabelData, basemapMode, cylinderData, displayTrack, fitKey, legLabelData, optimizedRoute, optimizedRouteData, optimizedRoutePointData, replayMarkerData, routeData, taskPointData, taskPoints, track, turnpointData, turnpoints]);

  const replayVisible = !!track && replayTotal > 0;
  const replayStartLabel = replayVisible ? formatUtcTimeLabel(replayTimestamps[0]) : "--:--";
  const replayEndLabel = replayVisible ? formatUtcTimeLabel(replayTimestamps[replayTotal - 1]) : "--:--";
  const replayCurrentLabel = replayVisible ? formatUtcTimeLabel(replayTimestamps[Math.min(replayIndex, replayTotal - 1)], true) : "--:--:--";

  function setTopDownView() {
    mapRef.current?.easeTo({ pitch: 0, duration: 300 });
  }

  function setNorthUp() {
    mapRef.current?.easeTo({ bearing: 0, duration: 300 });
  }

  function setReplaySpeedStep(direction: -1 | 1) {
    const currentIndex = REPLAY_SPEEDS.indexOf(replaySpeed as (typeof REPLAY_SPEEDS)[number]);
    const nextIndex = Math.min(REPLAY_SPEEDS.length - 1, Math.max(0, currentIndex + direction));
    setReplaySpeed(REPLAY_SPEEDS[nextIndex]);
  }

  return (
    <div
      className={`${isFullscreen ? "map-shell map-shell-fullscreen" : "map-shell"}${replayVisible ? " has-replay" : ""}`}
      ref={shellRef}
      style={isFullscreen ? { width: "100vw", height: "100vh" } : undefined}
    >
      <div
        className="map-card"
        ref={containerRef}
        style={
          isFullscreen
            ? { height: replayVisible ? "calc(100vh - 104px)" : "100vh", minHeight: replayVisible ? "calc(100vh - 104px)" : "100vh" }
            : replayVisible
              ? { height: "calc(420px - 104px)", minHeight: "calc(420px - 104px)" }
              : undefined
        }
      />
      <div className="map-control-stack">
        <button type="button" className="map-control-button" aria-label="Reset to top-down view" title="Top-down view" onClick={setTopDownView}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <rect x="3" y="3" width="10" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.4" />
            <circle cx="8" cy="8" r="1.8" fill="currentColor" />
          </svg>
        </button>
        <button type="button" className="map-control-button" aria-label="Set north up" title="North up" onClick={setNorthUp}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M8 2L10.8 8H8.9V14H7.1V8H5.2L8 2Z" fill="currentColor" />
            <path d="M11.8 4.2V11H13.1V6.5L13.7 7.3H15L13.4 5.2L15 3.1H13.7L13.1 3.9V4.2H11.8Z" fill="currentColor" />
          </svg>
        </button>
      </div>
      <div className={isFullscreen ? "map-fullscreen-sidebar" : undefined}>
        {isFullscreen && taskEditorOverlay ? <div className="map-task-editor-overlay">{taskEditorOverlay}</div> : null}
        <div className={isFullscreen ? "map-distance-overlay map-distance-overlay-stacked" : "map-distance-overlay"} aria-label="Task distance summary">
          <div className="map-distance-box">
            <strong>Total task</strong>
            <span>{totalDistanceKm.toFixed(1)} km</span>
          </div>
          <div className="map-distance-box">
            <strong>Optimized</strong>
            <span>{optimizedDistanceKm.toFixed(1)} km</span>
          </div>
        </div>
      </div>
      <div className="map-picker-stack">
        {track ? (
          <label className="map-style-picker">
            <span>Altitude</span>
            <select value={String(altitudeMultiplier)} onChange={(event) => setAltitudeMultiplier(Number(event.target.value))}>
              <option value="1">1×</option>
              <option value="2">2×</option>
              <option value="5">5×</option>
              <option value="10">10×</option>
              <option value="20">20×</option>
              <option value="50">50×</option>
            </select>
          </label>
        ) : null}
        <label className="map-style-picker">
          <span>Map</span>
          <select value={basemapMode} onChange={(event) => setBasemapMode(event.target.value as BasemapMode)}>
            <option value="streets">Streets</option>
            <option value="satellite">Satellite</option>
            <option value="terrain">Terrain</option>
          </select>
        </label>
      </div>
      {replayVisible ? (
        <div className="replay-bar">
          <div className="replay-controls">
            <button
              type="button"
              className="replay-btn"
              aria-label="Reset replay to start"
              title="Reset to start"
              onClick={() => {
                setIsReplaying(false);
                setReplayIndex(0);
                replayIndexRef.current = 0;
                lastFrameTimeRef.current = null;
              }}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                <rect x="2" y="2" width="2" height="10" fill="currentColor" />
                <path d="M11 2.5V11.5L5 7L11 2.5Z" fill="currentColor" />
              </svg>
            </button>
            <button type="button" className="replay-btn" aria-label="Slower replay" title="Slower" onClick={() => setReplaySpeedStep(-1)}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                <path d="M10.5 2.5V11.5L5.5 7L10.5 2.5Z" fill="currentColor" />
                <path d="M7.5 2.5V11.5L2.5 7L7.5 2.5Z" fill="currentColor" />
              </svg>
            </button>
            <button
              type="button"
              className="replay-btn replay-btn-primary"
              aria-label={isReplaying ? "Pause replay" : "Play replay"}
              title={isReplaying ? "Pause" : "Play"}
              onClick={() => {
                if (replayIndex >= replayTotal - 1) {
                  setReplayIndex(0);
                  replayIndexRef.current = 0;
                }
                lastFrameTimeRef.current = null;
                setIsReplaying((current) => !current);
              }}
            >
              {isReplaying ? (
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                  <rect x="3" y="2.5" width="3" height="9" fill="currentColor" />
                  <rect x="8" y="2.5" width="3" height="9" fill="currentColor" />
                </svg>
              ) : (
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                  <path d="M4 2.5L11 7L4 11.5V2.5Z" fill="currentColor" />
                </svg>
              )}
            </button>
            <button type="button" className="replay-btn" aria-label="Faster replay" title="Faster" onClick={() => setReplaySpeedStep(1)}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                <path d="M3.5 2.5V11.5L8.5 7L3.5 2.5Z" fill="currentColor" />
                <path d="M6.5 2.5V11.5L11.5 7L6.5 2.5Z" fill="currentColor" />
              </svg>
            </button>
            <span className="replay-speed-label">{replaySpeed}×</span>
          </div>
          <div className="replay-current-time">{replayCurrentLabel} UTC</div>
          <div className="replay-scrubber-row">
            <span className="replay-time-label">{replayStartLabel}</span>
            <input
              className="replay-scrubber"
              type="range"
              min={0}
              max={Math.max(0, replayTotal - 1)}
              value={replayIndex}
              onChange={(event) => {
                const nextIndex = Number(event.target.value);
                setIsReplaying(false);
                lastFrameTimeRef.current = null;
                replayIndexRef.current = nextIndex;
                setReplayIndex(nextIndex);
              }}
            />
            <span className="replay-time-label">{replayEndLabel}</span>
          </div>
        </div>
      ) : null}
    </div>
  );
}
