"use client";

import { COORDINATE_SYSTEM } from "@deck.gl/core";
import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import { MapboxOverlay } from "@deck.gl/mapbox";
import maplibregl, { GeoJSONSource } from "maplibre-gl";
import React, { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";

export type MapTurnpoint = { id: number; name: string; code: string | null; latitude: number; longitude: number };
export type MapTaskPoint = { position: number; point_type: string; radius_m: number; name: string; latitude: number; longitude: number };
export type MapUnitPreferences = {
  altitude: "ft" | "m";
  speed: "kph" | "mph";
  distance: "km" | "mi";
  vario: "fpm" | "ms";
};
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
const TERRAIN_SOURCE_ID = "terrain-dem";
const TERRAIN_EXAGGERATION = 1.25;

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
      [TERRAIN_SOURCE_ID]: {
        type: "raster-dem",
        tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
        tileSize: 256,
        encoding: "terrarium",
        maxzoom: 15,
        attribution: "Mapzen Terrarium / AWS Open Data",
      },
    },
    layers: [
      { id: "map-background", type: "background", paint: { "background-color": "#e7eef5" } },
      { id: "basemap", type: "raster", source: "basemap" },
    ],
  } as const;
}

const buildCircleCache = new Map<string, number[][]>();

function buildCircle(point: MapTaskPoint) {
  const cacheKey = `${point.latitude}:${point.longitude}:${point.radius_m}`;
  let coordinates = buildCircleCache.get(cacheKey);
  if (!coordinates) {
    const earthRadius = 6378137;
    const angularDistance = point.radius_m / earthRadius;
    const lat = (point.latitude * Math.PI) / 180;
    const lon = (point.longitude * Math.PI) / 180;
    coordinates = [];
    for (let step = 0; step <= 48; step += 1) {
      const bearing = (2 * Math.PI * step) / 48;
      const nextLat = Math.asin(Math.sin(lat) * Math.cos(angularDistance) + Math.cos(lat) * Math.sin(angularDistance) * Math.cos(bearing));
      const nextLon = lon + Math.atan2(Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(lat), Math.cos(angularDistance) - Math.sin(lat) * Math.sin(nextLat));
      coordinates.push([(nextLon * 180) / Math.PI, (nextLat * 180) / Math.PI]);
    }
    buildCircleCache.set(cacheKey, coordinates);
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

function haversineKm(a: [number, number], b: [number, number]) {
  const toRadians = (value: number) => (value * Math.PI) / 180;
  const earthRadiusKm = 6371;
  const deltaLat = toRadians(b[1] - a[1]);
  const deltaLon = toRadians(b[0] - a[0]);
  const latA = toRadians(a[1]);
  const latB = toRadians(b[1]);
  const sinLat = Math.sin(deltaLat / 2);
  const sinLon = Math.sin(deltaLon / 2);
  const arc = sinLat * sinLat + Math.cos(latA) * Math.cos(latB) * sinLon * sinLon;
  return earthRadiusKm * 2 * Math.atan2(Math.sqrt(arc), Math.sqrt(1 - arc));
}

function formatReplayTimeLabel(timestampMs: number | null | undefined, includeSeconds = false): string {
  if (timestampMs == null || Number.isNaN(timestampMs)) {
    return "--:--";
  }
  return new Date(timestampMs).toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
    second: includeSeconds ? "2-digit" : undefined,
    hour12: true,
  });
}

function convertDistance(distanceKm: number, unit: MapUnitPreferences["distance"]) {
  return unit === "mi" ? distanceKm * 0.621371 : distanceKm;
}

function formatDistanceLabel(distanceKm: number, unit: MapUnitPreferences["distance"], decimals = 1) {
  return `${convertDistance(distanceKm, unit).toFixed(decimals)} ${unit}`;
}

function formatAltitudeLabel(altitudeM: number, unit: MapUnitPreferences["altitude"]) {
  if (unit === "ft") {
    return `${Math.round(altitudeM * 3.28084).toLocaleString()} ft`;
  }
  return `${Math.round(altitudeM).toLocaleString()} m`;
}

function formatSpeedLabel(speedKmh: number, unit: MapUnitPreferences["speed"]) {
  if (unit === "mph") {
    return `${(speedKmh * 0.621371).toFixed(1)} mph`;
  }
  return `${speedKmh.toFixed(1)} km/h`;
}

function hexToRgb(hex: string): [number, number, number] {
  const normalized = hex.trim().replace("#", "");
  const expanded = normalized.length === 3
    ? normalized.split("").map((value) => `${value}${value}`).join("")
    : normalized.padEnd(6, "0").slice(0, 6);
  const parsed = Number.parseInt(expanded, 16);
  if (Number.isNaN(parsed)) {
    return [37, 99, 235];
  }
  return [(parsed >> 16) & 255, (parsed >> 8) & 255, parsed & 255];
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

export const TaskMap = React.memo(function TaskMap({
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
  hideFullscreenDistanceOverlay = false,
  highlightedTrackUploadId,
  fitKey,
  mode = "replay",
  units = { altitude: "ft", speed: "kph", distance: "km", vario: "fpm" },
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
  hideFullscreenDistanceOverlay?: boolean;
  highlightedTrackUploadId?: number | null;
  fitKey?: string | number | null;
  mode?: "replay" | "live";
  units?: MapUnitPreferences;
}) {
  const shellRef = useRef<HTMLDivElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const deckOverlayRef = useRef<MapboxOverlay | null>(null);
  const turnpointsRef = useRef(turnpoints);
  const taskPointsRef = useRef(taskPoints);
  const optimizedRouteRef = useRef(optimizedRoute);
  const trackRef = useRef(track);
  const turnpointSignatureRef = useRef("");
  const fitKeyRef = useRef<string>("");
  const editableRef = useRef(editable);
  const onSelectTurnpointRef = useRef(onSelectTurnpoint);
  const animationFrameRef = useRef<number | null>(null);
  const lastFrameTimeRef = useRef<number | null>(null);
  const replayClockRef = useRef<number | null>(null);
  const replayIndexRef = useRef(0);
  const [basemapMode, setBasemapMode] = useState<BasemapMode>("streets");
  const [altitudeMultiplier, setAltitudeMultiplier] = useState(10);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isPerspective3D, setIsPerspective3D] = useState(false);
  const [isReplaying, setIsReplaying] = useState(false);
  const [replayIndex, setReplayIndex] = useState(0);
  const [replaySpeed, setReplaySpeed] = useState(10);
  const [replayHasInteracted, setReplayHasInteracted] = useState(false);

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
      properties: { label: formatDistanceLabel(leg.optimizedDistanceKm, units.distance) },
      geometry: { type: "Point", coordinates: leg.midpoint },
    })),
  }), [legMetrics, units.distance]);
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
    const shouldSliceTrack = hasReplay && (isReplaying || replayHasInteracted);
    return {
      type: "FeatureCollection",
      features: track.features.map((feature) => {
        const featureTimestamps = Array.isArray(feature.properties?.timestamps) ? feature.properties.timestamps : [];
        const visibleLength = shouldSliceTrack
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
  }, [altitudeMultiplier, isReplaying, replayHasInteracted, replayIndex, replayTotal, track]);
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
  const deckTrackLayers = useMemo(() => {
    const layers = [];
    if (displayTrack) {
      const pathData = displayTrack.features
        .filter((feature) => feature.geometry.type === "LineString" && feature.geometry.coordinates.length > 1)
        .map((feature) => ({
          uploadId: Number(feature.properties?.upload_id ?? 0),
          path: feature.geometry.coordinates as [number, number, number][],
          color: hexToRgb(String(feature.properties?.color ?? "#ca8a04")),
          highlighted: Number(feature.properties?.upload_id ?? 0) === highlightedTrackUploadId,
        }));
      if (pathData.length) {
        layers.push(
          new PathLayer({
            id: "igc-track-3d",
            data: pathData,
            coordinateSystem: COORDINATE_SYSTEM.LNGLAT,
            positionFormat: "XYZ",
            getPath: (item: { path: [number, number, number][] }) => item.path,
            getColor: (item: { color: [number, number, number] }) => item.color,
            getWidth: (item: { highlighted: boolean }) => (item.highlighted ? 5 : 3),
            widthUnits: "pixels",
            widthMinPixels: 2,
            pickable: false,
            jointRounded: true,
            capRounded: true,
          }),
        );
      }
    }
    const replayMarkerFeatures = replayMarkerData.features as Array<{
      geometry?: { coordinates?: [number, number, number] };
    }>;
    if (replayMarkerFeatures.length) {
      layers.push(
        new ScatterplotLayer({
          id: "igc-replay-marker-3d",
          data: replayMarkerFeatures,
          coordinateSystem: COORDINATE_SYSTEM.LNGLAT,
          getPosition: (item: { geometry?: { coordinates?: [number, number, number] } }) => item.geometry?.coordinates ?? [0, 0, 0],
          getRadius: 9,
          radiusUnits: "pixels",
          radiusMinPixels: 8,
          stroked: true,
          filled: true,
          getFillColor: [255, 255, 255],
          getLineColor: [37, 99, 235],
          lineWidthUnits: "pixels",
          lineWidthMinPixels: 3,
          pickable: false,
        }),
      );
    }
    return layers;
  }, [displayTrack, highlightedTrackUploadId, replayMarkerData]);

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
    const nextReplayIndex = replayTotal > 0 ? replayTotal - 1 : 0;
    setIsReplaying(false);
    setReplayHasInteracted(false);
    setReplayIndex(nextReplayIndex);
    replayIndexRef.current = nextReplayIndex;
    replayClockRef.current = replayTotal > 0 ? replayTimestamps[nextReplayIndex] ?? null : null;
    lastFrameTimeRef.current = null;
    if (animationFrameRef.current !== null) {
      window.cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
  }, [track, replayTotal]);

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
      if (replayClockRef.current == null) {
        replayClockRef.current = replayTimestamps[currentIndex];
      }
      replayClockRef.current += deltaMs * replaySpeed;
      const targetFlightTime = replayClockRef.current;
      let nextIndex = currentIndex;
      while (nextIndex + 1 < replayTotal && replayTimestamps[nextIndex + 1] <= targetFlightTime) {
        nextIndex += 1;
      }
      if (nextIndex !== currentIndex) {
        replayIndexRef.current = nextIndex;
        setReplayIndex(nextIndex);
      }
      if (nextIndex >= replayTotal - 1) {
        replayClockRef.current = replayTimestamps[replayTotal - 1] ?? replayClockRef.current;
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
      const navigationControl = new maplibregl.NavigationControl({ showCompass: true });
      map.addControl(navigationControl, "top-right");
      map.addControl(new maplibregl.FullscreenControl({ container: shell ?? undefined }), "top-right");
      const deckOverlay = new MapboxOverlay({ interleaved: false, layers: [] });
      map.addControl(deckOverlay);
      deckOverlayRef.current = deckOverlay;
      let compassButton: HTMLButtonElement | null = null;
      let handleCompassClick: ((event: Event) => void) | null = null;
      map.on("styledata", () => {
        map.resize();
      });
      map.on("moveend", () => {
        setIsPerspective3D(map.getPitch() >= 40);
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
      window.setTimeout(() => {
        compassButton = container.closest(".map-shell")?.querySelector(".maplibregl-ctrl-compass") as HTMLButtonElement | null;
        if (compassButton) {
          handleCompassClick = () => {
            window.setTimeout(() => {
              map.easeTo({ bearing: 0, pitch: 0, duration: 300 });
              setIsPerspective3D(false);
            }, 0);
          };
          compassButton.addEventListener("click", handleCompassClick);
        }
      }, 0);
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
        if (compassButton && handleCompassClick) {
          compassButton.removeEventListener("click", handleCompassClick);
        }
        document.removeEventListener("fullscreenchange", handleFullscreenChange);
        document.removeEventListener("webkitfullscreenchange", handleFullscreenChange as EventListener);
        if (deckOverlayRef.current) {
          map.removeControl(deckOverlayRef.current);
          deckOverlayRef.current = null;
        }
        map.remove();
        mapRef.current = null;
      };
    } catch (error) {
      console.error("Map failed to initialize.", error);
      return;
    }
  }, []);

  const [styleGeneration, setStyleGeneration] = useState(0);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    map.setStyle(createBasemapStyle(basemapMode) as never);
    map.once("styledata", () => {
      setStyleGeneration((prev) => prev + 1);
    });
  }, [basemapMode]);

  useEffect(() => {
    const deckOverlay = deckOverlayRef.current;
    if (!deckOverlay) {
      return;
    }
    deckOverlay.setProps({ interleaved: false, layers: deckTrackLayers });
  }, [deckTrackLayers]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    const applyTerrain = () => {
      const hasTerrainSource = !!map.getSource(TERRAIN_SOURCE_ID);
      if (!hasTerrainSource) {
        return;
      }
      map.setTerrain(
        isPerspective3D
          ? {
              source: TERRAIN_SOURCE_ID,
              exaggeration: TERRAIN_EXAGGERATION,
            }
          : null,
      );
    };
    if (map.isStyleLoaded()) {
      applyTerrain();
    } else {
      map.once("styledata", applyTerrain);
    }
  }, [isPerspective3D, styleGeneration]);

  const fitBounds = useMemo(() => {
    const bounds: [number, number][] = [];
    for (const turnpoint of turnpoints) {
      bounds.push([turnpoint.longitude, turnpoint.latitude]);
    }
    for (const point of taskPoints) {
      bounds.push([point.longitude, point.latitude]);
    }
    for (const coordinate of optimizedRoute) {
      bounds.push(coordinate);
    }
    if (track) {
      for (const feature of track.features) {
        if (feature.geometry.type !== "LineString") {
          continue;
        }
        for (const coordinate of feature.geometry.coordinates) {
          bounds.push([coordinate[0], coordinate[1]]);
        }
      }
    }
    return bounds;
  }, [turnpoints, taskPoints, optimizedRoute, track]);

  const applyFitBounds = useCallback((map: maplibregl.Map) => {
    if (fitBounds.length === 0) {
      return;
    }
    const lngLatBounds = new maplibregl.LngLatBounds();
    for (const coordinate of fitBounds) {
      lngLatBounds.extend(coordinate);
    }
    map.fitBounds(lngLatBounds, { padding: 48, maxZoom: 11, duration: 0 });
  }, [fitBounds]);

  // Sync turnpoint data to map
  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    const sync = () => {
      ensureGeoJsonSource(map, "turnpoints", turnpointData as never);
      ensureMapLayers(map);
    };
    if (map.isStyleLoaded()) {
      sync();
    } else {
      map.once("styledata", sync);
    }
  }, [turnpointData, styleGeneration]);

  // Sync airspace data to map
  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    const sync = () => {
      ensureGeoJsonSource(map, "airspaces", airspaceData as never);
      ensureGeoJsonSource(map, "airspace-labels", airspaceLabelData as never);
      ensureMapLayers(map);
    };
    if (map.isStyleLoaded()) {
      sync();
    } else {
      map.once("styledata", sync);
    }
  }, [airspaceData, airspaceLabelData, styleGeneration]);

  // Sync task route data to map
  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    const sync = () => {
      ensureGeoJsonSource(map, "task-points", taskPointData as never);
      ensureGeoJsonSource(map, "task-route", routeData as never);
      ensureGeoJsonSource(map, "optimized-route", optimizedRouteData as never);
      ensureGeoJsonSource(map, "optimized-route-points", optimizedRoutePointData as never);
      ensureGeoJsonSource(map, "optimized-leg-labels", legLabelData as never);
      ensureGeoJsonSource(map, "task-cylinders", cylinderData as never);
      ensureMapLayers(map);
    };
    if (map.isStyleLoaded()) {
      sync();
    } else {
      map.once("styledata", sync);
    }
  }, [routeData, cylinderData, taskPointData, optimizedRouteData, optimizedRoutePointData, legLabelData, styleGeneration]);

  // Sync track data to map
  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    const sync = () => {
      ensureGeoJsonSource(map, "track", (displayTrack ?? { type: "FeatureCollection", features: [] }) as never);
      ensureGeoJsonSource(map, "replay-marker", replayMarkerData as never);
      ensureMapLayers(map);
    };
    if (map.isStyleLoaded()) {
      sync();
    } else {
      map.once("styledata", sync);
    }
  }, [displayTrack, replayMarkerData, styleGeneration]);

  // Fit map to data when signatures change
  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    const nextTurnpointSignature = turnpoints.map((turnpoint) => `${turnpoint.id}:${turnpoint.latitude.toFixed(4)}:${turnpoint.longitude.toFixed(4)}`).join("|");
    const nextFitKey = String(fitKey ?? "");
    const shouldFitToTurnpoints = nextTurnpointSignature !== turnpointSignatureRef.current;
    const shouldFitToTask = nextFitKey !== fitKeyRef.current;

    if (shouldFitToTurnpoints || shouldFitToTask) {
      const doFit = () => {
        applyFitBounds(map);
      };
      if (map.isStyleLoaded()) {
        doFit();
      } else {
        map.once("styledata", doFit);
      }
    }
    turnpointSignatureRef.current = nextTurnpointSignature;
    fitKeyRef.current = nextFitKey;
  }, [turnpoints, fitKey, applyFitBounds]);

  const replayVisible = !!track && replayTotal > 0;
  const replayStartLabel = replayVisible ? formatReplayTimeLabel(replayTimestamps[0]) : "--:--";
  const replayEndLabel = replayVisible ? formatReplayTimeLabel(replayTimestamps[replayTotal - 1]) : "--:--";
  const replayCurrentLabel = replayVisible ? formatReplayTimeLabel(replayTimestamps[Math.min(replayIndex, replayTotal - 1)], true) : "--:--:--";
  const highlightedTrackTelemetry = useMemo(() => {
    if (!track || highlightedTrackUploadId == null) {
      return null;
    }
    const highlightedFeature = track.features.find((feature) => Number(feature.properties?.upload_id) === highlightedTrackUploadId);
    if (!highlightedFeature || highlightedFeature.geometry.type !== "LineString" || !highlightedFeature.geometry.coordinates.length) {
      return null;
    }
    const timestamps = Array.isArray(highlightedFeature.properties?.timestamps)
      ? highlightedFeature.properties.timestamps.map((value) => Date.parse(String(value))).filter((value) => Number.isFinite(value))
      : [];
    const coordinateIndex = timestamps.length
      ? Math.min(replayIndex, highlightedFeature.geometry.coordinates.length - 1, timestamps.length - 1)
      : highlightedFeature.geometry.coordinates.length - 1;
    const coordinate = highlightedFeature.geometry.coordinates[Math.max(0, coordinateIndex)];
    if (!coordinate) {
      return null;
    }
    const previousIndex = Math.max(0, coordinateIndex - 1);
    const previousCoordinate = highlightedFeature.geometry.coordinates[previousIndex];
    const currentTimestamp = timestamps[coordinateIndex];
    const previousTimestamp = timestamps[previousIndex];
    let speedKmh: number | null = null;
    if (previousCoordinate && currentTimestamp && previousTimestamp && currentTimestamp > previousTimestamp) {
      const distanceKm = haversineKm(
        [previousCoordinate[0], previousCoordinate[1]],
        [coordinate[0], coordinate[1]],
      );
      const elapsedHours = (currentTimestamp - previousTimestamp) / 3_600_000;
      if (elapsedHours > 0) {
        speedKmh = distanceKm / elapsedHours;
      }
    }
    return {
      pilotName: String(highlightedFeature.properties?.pilot_name ?? "Pilot"),
      timeLabel: currentTimestamp ? formatReplayTimeLabel(currentTimestamp, true) : "--:--:--",
      altitudeM: coordinate.length > 2 ? Math.round(coordinate[2] ?? 0) : 0,
      speedKmh,
      color: String(highlightedFeature.properties?.color ?? "#2563eb"),
    };
  }, [highlightedTrackUploadId, replayIndex, track]);

  function setReplaySpeedStep(direction: -1 | 1) {
    const currentIndex = REPLAY_SPEEDS.indexOf(replaySpeed as (typeof REPLAY_SPEEDS)[number]);
    const nextIndex = Math.min(REPLAY_SPEEDS.length - 1, Math.max(0, currentIndex + direction));
    setReplaySpeed(REPLAY_SPEEDS[nextIndex]);
  }

  return (
    <div
      className={`${isFullscreen ? "map-shell map-shell-fullscreen" : "map-shell"}${replayVisible && mode === "replay" ? " has-replay" : ""}`}
      ref={shellRef}
      style={isFullscreen ? { width: "100vw", height: "100vh" } : undefined}
    >
      <div
        className="map-card"
        ref={containerRef}
        style={
          isFullscreen
            ? { height: replayVisible && mode === "replay" ? "calc(100vh - 104px)" : "100vh", minHeight: replayVisible && mode === "replay" ? "calc(100vh - 104px)" : "100vh" }
            : replayVisible && mode === "replay"
              ? { height: "calc(420px - 104px)", minHeight: "calc(420px - 104px)" }
              : undefined
        }
      />
      <div className={isFullscreen ? "map-fullscreen-sidebar" : undefined}>
        {isFullscreen && taskEditorOverlay ? <div className="map-task-editor-overlay">{taskEditorOverlay}</div> : null}
        {!(isFullscreen && hideFullscreenDistanceOverlay) ? (
          <div className={isFullscreen ? "map-distance-overlay map-distance-overlay-stacked" : "map-distance-overlay"} aria-label="Task distance summary">
            <div className="map-distance-box">
              <strong>Total task</strong>
              <span>{formatDistanceLabel(totalDistanceKm, units.distance)}</span>
            </div>
            <div className="map-distance-box">
              <strong>Optimized</strong>
              <span>{formatDistanceLabel(optimizedDistanceKm, units.distance)}</span>
            </div>
          </div>
        ) : null}
        {highlightedTrackTelemetry ? (
          <div className="map-track-telemetry" aria-label="Highlighted pilot telemetry">
            <strong style={{ color: highlightedTrackTelemetry.color }}>{highlightedTrackTelemetry.pilotName}</strong>
            <div className="map-track-telemetry-grid">
              <span>Time</span>
              <span>{highlightedTrackTelemetry.timeLabel}</span>
              <span>Altitude</span>
              <span>{formatAltitudeLabel(highlightedTrackTelemetry.altitudeM, units.altitude)}</span>
              <span>Speed</span>
              <span>{highlightedTrackTelemetry.speedKmh != null ? formatSpeedLabel(highlightedTrackTelemetry.speedKmh, units.speed) : "--"}</span>
            </div>
          </div>
        ) : null}
      </div>
      <div className="map-control-stack">
        <button
          type="button"
          className="map-control-button map-control-mode-button"
          aria-label={isPerspective3D ? "Switch to 2D view" : "Switch to 3D view"}
          title={isPerspective3D ? "2D view" : "3D view"}
          onClick={() => {
            const map = mapRef.current;
            if (!map) {
              return;
            }
            const nextIs3D = !isPerspective3D;
            map.easeTo({
              pitch: nextIs3D ? 60 : 0,
              duration: 300,
            });
            setIsPerspective3D(nextIs3D);
          }}
        >
          {isPerspective3D ? "2D" : "3D"}
        </button>
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
      {replayVisible && mode === "replay" ? (
        <div className="replay-bar">
          <div className="replay-controls">
            <button
              type="button"
              className="replay-btn"
              aria-label="Reset replay to start"
              title="Reset to start"
              onClick={() => {
                setIsReplaying(false);
                setReplayHasInteracted(true);
                setReplayIndex(0);
                replayIndexRef.current = 0;
                replayClockRef.current = replayTimestamps[0] ?? null;
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
                  replayClockRef.current = replayTimestamps[0] ?? null;
                }
                setReplayHasInteracted(true);
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
          <div className="replay-current-time">{replayCurrentLabel}</div>
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
                setReplayHasInteracted(true);
                lastFrameTimeRef.current = null;
                replayIndexRef.current = nextIndex;
                replayClockRef.current = replayTimestamps[nextIndex] ?? null;
                setReplayIndex(nextIndex);
              }}
            />
            <span className="replay-time-label">{replayEndLabel}</span>
          </div>
        </div>
      ) : null}
    </div>
  );
});
