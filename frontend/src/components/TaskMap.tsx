"use client";

import { COORDINATE_SYSTEM } from "@deck.gl/core";
import { IconLayer, PathLayer, PolygonLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { MapboxOverlay } from "@deck.gl/mapbox";
import maplibregl, { GeoJSONSource } from "maplibre-gl";
import React, { type ReactNode, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

export type MapTurnpoint = { id: number; name: string; code: string | null; latitude: number; longitude: number };
export type MapTaskPoint = { position: number; point_type: string; radius_m: number; name: string; latitude: number; longitude: number };
export type MapUnitPreferences = {
  altitude: "ft" | "m";
  speed: "kph" | "mph";
  distance: "km" | "mi";
  vario: "fpm" | "ms";
};
export type MapTelemetrySmoothing = {
  telemetry_vario_smoothing_seconds: number;
  telemetry_altitude_smoothing_seconds: number;
  telemetry_speed_smoothing_seconds: number;
  telemetry_glide_ratio_smoothing_seconds: number;
  max_map_pitch_degrees?: number;
};
export type MapLivePositionProfileType = "pilot" | "driver" | "stationary_node";
export type MapLivePositionSource = "cellular" | "mesh" | "other";
export type MapLivePosition = {
  id: string;
  pilotId: number | null;
  pilotName: string;
  latitude: number;
  longitude: number;
  altitudeM: number | null;
  speedKmh: number | null;
  heading: number | null;
  timestamp: string;
  batteryLevel: number | null;
  source: string | null;
  color?: string | null;
  aircraftType?: "hang_glider" | "paraglider" | "sailplane" | null;
  profileType?: MapLivePositionProfileType | null;
  positionSource?: MapLivePositionSource | null;
  deviceId?: string | null;
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
  lower_limit_m: number | null;
  upper_limit_m: number | null;
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
export type MapScoredTrackPoint = {
  id: string;
  uploadId: number | null;
  pilotName: string;
  pointName: string;
  pointType: string;
  direction?: string | null;
  timestamp?: string | null;
  scoredTimestamp?: string | null;
  latitude: number;
  longitude: number;
  altitudeM?: number | null;
  color?: string | null;
};
export type MapLegMetric = { index: number; centerDistanceKm: number; optimizedDistanceKm: number; midpoint: [number, number] };
export type TaskEditorOverlayRenderProps = {
  collapsed: boolean;
  contentId: string;
  overlayId: string;
  toggleButton: ReactNode;
};
export type TaskEditorOverlayContent = ReactNode | ((props: TaskEditorOverlayRenderProps) => ReactNode);
export type FullscreenSidebarRenderProps = {
  contentId: string;
  toggleButton: ReactNode;
};
export type FullscreenSidebarContent = ReactNode | ((props: FullscreenSidebarRenderProps) => ReactNode);
type BasemapMode = "streets" | "satellite" | "terrain";
type AircraftIconType = "hang_glider" | "paraglider" | "sailplane";
const REPLAY_SPEEDS = [1, 2, 5, 10, 15, 30, 45, 60, 120, 300] as const;
const ALTITUDE_MULTIPLIER_OPTIONS = [1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5] as const;
const TERRAIN_SOURCE_ID = "terrain-dem";
const TERRAIN_EXAGGERATION = 1.25;
const DEFAULT_MAX_MAP_PITCH = 75;
const TRACK_WIDTH_PIXELS = 1.25;
const HIGHLIGHTED_TRACK_WIDTH_PIXELS = 2;
const SCALE_BAR_MAX_WIDTH_PIXELS = 96;
const persistedViewStateByKey = new Map<string, { center: [number, number]; zoom: number; bearing: number; pitch: number }>();

// Inline SVG icons used for live-map role markers. Each SVG is white-fill so the
// deck.gl IconLayer (mask: true) can tint them with the pilot's assigned color.
// Pilots get an aircraft-type-specific glyph (HG / PG / sailplane); drivers and
// stationary nodes get their dedicated glyphs.
type LiveMapIconKey = "hang_glider" | "paraglider" | "sailplane" | "driver" | "stationary_node";

const ROLE_ICON_SVGS: Record<LiveMapIconKey, string> = {
  hang_glider:
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path fill="#fff" d="M12 4 L22 20 L12 16 L2 20 Z"/></svg>',
  paraglider:
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path fill="#fff" d="M2 12 Q12 4 22 12 L20 13 Q12 6 4 13 Z M11 15 L13 15 L13 20 L11 20 Z"/></svg>',
  sailplane:
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path fill="#fff" d="M2 11 L11 11 L11 3 L13 3 L13 11 L22 11 L22 13 L13 13 L13 18 L16 18 L16 20 L8 20 L8 18 L11 18 L11 13 L2 13 Z"/></svg>',
  driver:
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path fill="#fff" d="M5 11l1.5-4.5A2 2 0 018.4 5h7.2a2 2 0 011.9 1.5L19 11h1a1 1 0 011 1v4a1 1 0 01-1 1h-1v1a1 1 0 01-1 1h-1a1 1 0 01-1-1v-1H8v1a1 1 0 01-1 1H6a1 1 0 01-1-1v-1H4a1 1 0 01-1-1v-4a1 1 0 011-1h1zm2 4a1.25 1.25 0 100-2.5 1.25 1.25 0 000 2.5zm10 0a1.25 1.25 0 100-2.5 1.25 1.25 0 000 2.5z"/></svg>',
  stationary_node:
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path fill="#fff" d="M12 2l4 6-4 2-4-2 4-6zm-1 8h2v12h-2V10zM5.5 4.2l1.4 1.4a7 7 0 000 9.9l-1.4 1.4a9 9 0 010-12.7zm13 0a9 9 0 010 12.7l-1.4-1.4a7 7 0 000-9.9l1.4-1.4z"/></svg>',
};

const ROLE_ICON_DATA_URIS: Record<LiveMapIconKey, string> = {
  hang_glider: `data:image/svg+xml;utf8,${encodeURIComponent(ROLE_ICON_SVGS.hang_glider)}`,
  paraglider: `data:image/svg+xml;utf8,${encodeURIComponent(ROLE_ICON_SVGS.paraglider)}`,
  sailplane: `data:image/svg+xml;utf8,${encodeURIComponent(ROLE_ICON_SVGS.sailplane)}`,
  driver: `data:image/svg+xml;utf8,${encodeURIComponent(ROLE_ICON_SVGS.driver)}`,
  stationary_node: `data:image/svg+xml;utf8,${encodeURIComponent(ROLE_ICON_SVGS.stationary_node)}`,
};

function resolveLiveMapIconKey(
  profileType: "pilot" | "driver" | "stationary_node" | undefined,
  aircraftType: "hang_glider" | "paraglider" | "sailplane" | undefined,
): LiveMapIconKey {
  if (profileType === "driver") return "driver";
  if (profileType === "stationary_node") return "stationary_node";
  return aircraftType ?? "hang_glider";
}

// Solid ring (cellular fix) vs. dashed ring (mesh-relayed fix) vs. faint solid ring (other/unknown).
const RING_ICON_SVGS: Record<"cellular" | "mesh" | "other", string> = {
  cellular:
    '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48"><circle fill="none" stroke="#fff" stroke-width="3" cx="24" cy="24" r="20"/></svg>',
  mesh:
    '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48"><circle fill="none" stroke="#fff" stroke-width="3" cx="24" cy="24" r="20" stroke-dasharray="7 5"/></svg>',
  other:
    '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48"><circle fill="none" stroke="#fff" stroke-width="2" stroke-opacity="0.6" cx="24" cy="24" r="20" stroke-dasharray="2 3"/></svg>',
};

const RING_ICON_DATA_URIS: Record<"cellular" | "mesh" | "other", string> = {
  cellular: `data:image/svg+xml;utf8,${encodeURIComponent(RING_ICON_SVGS.cellular)}`,
  mesh: `data:image/svg+xml;utf8,${encodeURIComponent(RING_ICON_SVGS.mesh)}`,
  other: `data:image/svg+xml;utf8,${encodeURIComponent(RING_ICON_SVGS.other)}`,
};

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

function normalizeAircraftIcon(value: unknown): AircraftIconType {
  switch (value) {
    case "paraglider":
    case "sailplane":
      return value;
    case "hang_glider":
    default:
      return "hang_glider";
  }
}

function mapLabelFromPilotName(name: string) {
  const trimmed = name.trim();
  if (!trimmed) {
    return "Pilot";
  }
  return trimmed;
}

function aircraftPilotLabel(_kind: AircraftIconType, pilotName: string) {
  return mapLabelFromPilotName(pilotName);
}

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
  const nextData =
    typeof structuredClone === "function"
      ? structuredClone(data)
      : JSON.parse(JSON.stringify(data));
  const source = map.getSource(id) as GeoJSONSource | undefined;
  if (source) {
    source.setData(nextData as never);
    return;
  }
  map.addSource(id, { type: "geojson", data: nextData as never });
}

function hasSource(map: maplibregl.Map, id: string) {
  return !!map.getSource(id);
}

function safeAddLayer(map: maplibregl.Map, layer: Parameters<maplibregl.Map["addLayer"]>[0]) {
  if (map.getLayer(layer.id)) {
    return;
  }
  try {
    map.addLayer(layer);
  } catch (error) {
    console.warn(`Unable to add map layer ${layer.id}.`, error);
  }
}

function removeLayerIfPresent(map: maplibregl.Map, id: string) {
  if (map.getLayer(id)) {
    map.removeLayer(id);
  }
}

function removeSourceIfPresent(map: maplibregl.Map, id: string) {
  if (map.getSource(id)) {
    map.removeSource(id);
  }
}

function rebuildTaskGeometrySources(map: maplibregl.Map) {
  [
    "optimized-leg-labels",
    "optimized-route-points",
    "optimized-route-layer",
    "task-route-layer",
    "task-route-arrows-layer",
    "task-points-layer",
    "task-cylinders-outline",
    "task-cylinders-fill",
  ].forEach((layerId) => removeLayerIfPresent(map, layerId));
  [
    "optimized-leg-labels",
    "optimized-route-points",
    "optimized-route",
    "task-route",
    "task-route-arrows",
    "task-points",
    "task-cylinders",
  ].forEach((sourceId) => removeSourceIfPresent(map, sourceId));
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

function formatScoredTrackTimeLabel(value: string | null | undefined): string {
  if (!value) {
    return "--";
  }
  const timestampMs = Date.parse(value);
  if (Number.isNaN(timestampMs)) {
    return value;
  }
  return formatReplayTimeLabel(timestampMs, true);
}

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

type ScoredTrackDeckPoint = MapScoredTrackPoint & {
  position: [number, number, number];
  deckColor: [number, number, number];
  highlighted: boolean;
  altitudeLabel: string;
};

function scoredTrackPointPopupHtml(point: ScoredTrackDeckPoint): string {
  const coordinateLabel = `${point.latitude.toFixed(5)}, ${point.longitude.toFixed(5)}`;
  const trackTime = formatScoredTrackTimeLabel(point.timestamp);
  const scoredTime = point.scoredTimestamp && point.scoredTimestamp !== point.timestamp
    ? formatScoredTrackTimeLabel(point.scoredTimestamp)
    : "";
  const pointLabel = [point.pointType, point.direction].filter(Boolean).join(" / ");
  return `
    <div style="font: 12px/1.35 system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #0f172a; min-width: 190px;">
      <div style="font-weight: 700; margin-bottom: 4px;">${escapeHtml(point.pointName)}</div>
      <div style="color: #475569; margin-bottom: 6px;">${escapeHtml(point.pilotName)}${pointLabel ? ` - ${escapeHtml(pointLabel)}` : ""}</div>
      <div><strong>Time:</strong> ${escapeHtml(trackTime)}</div>
      ${scoredTime ? `<div><strong>Start Gate:</strong> ${escapeHtml(scoredTime)}</div>` : ""}
      <div><strong>Altitude:</strong> ${escapeHtml(point.altitudeLabel || "--")}</div>
      <div><strong>GPS:</strong> ${escapeHtml(coordinateLabel)}</div>
    </div>
  `;
}

function convertDistance(distanceKm: number, unit: MapUnitPreferences["distance"]) {
  return unit === "mi" ? distanceKm * 0.621371 : distanceKm;
}

function formatDistanceLabel(distanceKm: number, unit: MapUnitPreferences["distance"], decimals = 1) {
  return `${convertDistance(distanceKm, unit).toFixed(decimals)} ${unit}`;
}

function formatScaleStop(value: number) {
  return Number.isInteger(value) ? value.toFixed(0) : String(value);
}

function getDecimalRoundNum(value: number) {
  const multiplier = Math.pow(10, Math.ceil(-Math.log(value) / Math.LN10));
  return Math.round(value * multiplier) / multiplier;
}

function getRoundNum(value: number) {
  const pow10 = Math.pow(10, `${Math.floor(value)}`.length - 1);
  let scaled = value / pow10;
  scaled = scaled >= 10
    ? 10
    : scaled >= 5
      ? 5
      : scaled >= 3
        ? 3
        : scaled >= 2
          ? 2
          : scaled >= 1
            ? 1
            : getDecimalRoundNum(scaled);
  return pow10 * scaled;
}

function computeScaleBar(map: maplibregl.Map, unit: MapUnitPreferences["distance"]) {
  const container = map.getContainer();
  const containerWidth = container.clientWidth;
  const containerHeight = container.clientHeight;
  if (!containerWidth || !containerHeight) {
    return null;
  }

  const targetWidth = Math.min(SCALE_BAR_MAX_WIDTH_PIXELS, containerWidth);
  const x = containerWidth / 2;
  const y = containerHeight / 2;
  const left = map.unproject([x - targetWidth / 2, y]);
  const right = map.unproject([x + targetWidth / 2, y]);
  const projectedWidth = Math.round(map.project(right).x - map.project(left).x);
  const maxWidth = Math.min(targetWidth, projectedWidth, containerWidth);
  const maxMeters = left.distanceTo(right);
  if (!Number.isFinite(maxWidth) || maxWidth <= 0 || !Number.isFinite(maxMeters) || maxMeters <= 0) {
    return null;
  }

  let maxDistance: number;
  let unitLabel: string;
  if (unit === "mi") {
    const maxFeet = maxMeters * 3.280839895;
    if (maxFeet > 5280) {
      maxDistance = maxFeet / 5280;
      unitLabel = "mi";
    } else {
      maxDistance = maxFeet;
      unitLabel = "ft";
    }
  } else if (maxMeters >= 1000) {
    maxDistance = maxMeters / 1000;
    unitLabel = "km";
  } else {
    maxDistance = maxMeters;
    unitLabel = "m";
  }

  const distance = getRoundNum(maxDistance);
  if (!Number.isFinite(distance) || distance <= 0) {
    return null;
  }
  const ratio = distance / maxDistance;

  return {
    label: `${formatScaleStop(distance)} ${unitLabel}`,
    width: Math.max(1, Math.min(SCALE_BAR_MAX_WIDTH_PIXELS, Math.round(maxWidth * ratio))),
  };
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

function formatVarioLabel(verticalSpeedMps: number, unit: MapUnitPreferences["vario"]) {
  if (unit === "fpm") {
    return `${Math.round(verticalSpeedMps * 196.850394).toLocaleString()} ft/min`;
  }
  return `${verticalSpeedMps.toFixed(1)} m/s`;
}

function formatGlideRatioLabel(glideRatio: number) {
  return `${glideRatio.toFixed(1)} : 1`;
}

function resolveAdaptiveTelemetrySmoothing(
  baseSmoothing: MapTelemetrySmoothing,
  mode: "replay" | "live",
  isReplaying: boolean,
  replaySpeed: number,
): MapTelemetrySmoothing {
  if (mode !== "replay" || !isReplaying || replaySpeed <= 1) {
    return baseSmoothing;
  }
  // The original sqrt-only curve was too subtle below 5x, so the displayed
  // telemetry barely changed at 2x-5x. This stronger but still capped curve
  // makes low-speed replay meaningfully calmer without freezing the card.
  const multiplier = Math.min(4, 0.8 + Math.sqrt(replaySpeed));
  return {
    telemetry_vario_smoothing_seconds: baseSmoothing.telemetry_vario_smoothing_seconds * multiplier,
    telemetry_altitude_smoothing_seconds: baseSmoothing.telemetry_altitude_smoothing_seconds * multiplier,
    telemetry_speed_smoothing_seconds: baseSmoothing.telemetry_speed_smoothing_seconds * multiplier,
    telemetry_glide_ratio_smoothing_seconds: baseSmoothing.telemetry_glide_ratio_smoothing_seconds * multiplier,
  };
}

function replayTelemetryThrottleMs(replaySpeed: number) {
  if (replaySpeed <= 2) {
    return 0;
  }
  if (replaySpeed <= 5) {
    return 100;
  }
  if (replaySpeed <= 10) {
    return 125;
  }
  if (replaySpeed <= 30) {
    return 200;
  }
  return 250;
}

type FitTarget = {
  kind: "task" | "turnpoints" | "track" | "livePositions" | "fitTurnpoints" | "fallback";
  coordinates: [number, number][];
  signature: string;
};

function buildTaskGeometrySignature(taskPoints: MapTaskPoint[], optimizedRoute: [number, number][]) {
  return [
    taskPoints
      .map((point) => `${point.position}:${point.point_type}:${point.latitude.toFixed(6)}:${point.longitude.toFixed(6)}:${point.radius_m}`)
      .join("|"),
    optimizedRoute.map((coordinate) => `${coordinate[0].toFixed(6)}:${coordinate[1].toFixed(6)}`).join("|"),
  ].join("::");
}

type RouteArrowFeature = {
  type: "Feature";
  properties: { rotation: number };
  geometry: { type: "Point"; coordinates: [number, number] };
};

function interpolateCoordinate(from: [number, number], to: [number, number], ratio = 0.5): [number, number] {
  return [
    from[0] + (to[0] - from[0]) * ratio,
    from[1] + (to[1] - from[1]) * ratio,
  ];
}

function bearingDegrees(from: [number, number], to: [number, number]) {
  const fromLat = (from[1] * Math.PI) / 180;
  const toLat = (to[1] * Math.PI) / 180;
  const deltaLon = ((to[0] - from[0]) * Math.PI) / 180;
  const y = Math.sin(deltaLon) * Math.cos(toLat);
  const x = Math.cos(fromLat) * Math.sin(toLat) - Math.sin(fromLat) * Math.cos(toLat) * Math.cos(deltaLon);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

function buildRouteArrowData(coordinates: [number, number][]) {
  return {
    type: "FeatureCollection",
    features: coordinates.slice(1).map((coordinate, index) => {
      const previous = coordinates[index];
      return {
        type: "Feature",
        properties: { rotation: bearingDegrees(previous, coordinate) - 90 },
        geometry: {
          type: "Point",
          coordinates: interpolateCoordinate(previous, coordinate, 0.5),
        },
      } as RouteArrowFeature;
    }),
  } as const;
}

function buildTurnpointGeometrySignature(turnpoints: MapTurnpoint[]) {
  return turnpoints.map((turnpoint) => `${turnpoint.id}:${turnpoint.latitude.toFixed(6)}:${turnpoint.longitude.toFixed(6)}`).join("|");
}

function buildTrackGeometrySignature(track: TrackCollection) {
  return track.features
    .map((feature, featureIndex) => {
      if (feature.geometry.type !== "LineString") {
        return `feature:${featureIndex}:non-line`;
      }
      return feature.geometry.coordinates
        .map((coordinate) => `${coordinate[0].toFixed(6)}:${coordinate[1].toFixed(6)}`)
        .join("|");
    })
    .join("::");
}

function resolveFitTarget(
  taskPoints: MapTaskPoint[],
  optimizedRoute: [number, number][],
  turnpoints: MapTurnpoint[],
  track: TrackCollection | null,
  fitTurnpoints?: MapTurnpoint[],
  livePositions?: MapLivePosition[],
): FitTarget {
  if (taskPoints.length) {
    const coordinates: [number, number][] = taskPoints.map((point) => [point.longitude, point.latitude]);
    for (const coordinate of optimizedRoute) {
      coordinates.push(coordinate);
    }
    return {
      kind: "task",
      coordinates,
      signature: `task::${buildTaskGeometrySignature(taskPoints, optimizedRoute)}`,
    };
  }
  if (turnpoints.length) {
    return {
      kind: "turnpoints",
      coordinates: turnpoints.map((turnpoint) => [turnpoint.longitude, turnpoint.latitude]),
      signature: `turnpoints::${buildTurnpointGeometrySignature(turnpoints)}`,
    };
  }
  if (track?.features.length) {
    const coordinates: [number, number][] = [];
    for (const feature of track.features) {
      if (feature.geometry.type !== "LineString") {
        continue;
      }
      for (const coordinate of feature.geometry.coordinates) {
        coordinates.push([coordinate[0], coordinate[1]]);
      }
    }
    if (coordinates.length) {
      return {
        kind: "track",
        coordinates,
        signature: `track::${buildTrackGeometrySignature(track)}`,
      };
    }
  }
  if (livePositions?.length) {
    const coordinates: [number, number][] = livePositions.map((p) => [p.longitude, p.latitude]);
    return {
      kind: "livePositions",
      coordinates,
      signature: `live::${livePositions.length}::${livePositions.map((p) => `${p.latitude.toFixed(4)},${p.longitude.toFixed(4)}`).join("|")}`,
    };
  }
  const fallbackTurnpoints = fitTurnpoints ?? [];
  if (fallbackTurnpoints.length) {
    return {
      kind: "fitTurnpoints",
      coordinates: fallbackTurnpoints.map((turnpoint) => [turnpoint.longitude, turnpoint.latitude]),
      signature: `fit-turnpoints::${buildTurnpointGeometrySignature(fallbackTurnpoints)}`,
    };
  }
  return {
    kind: "fallback",
    coordinates: [],
    signature: "usa-fallback",
  };
}

function buildBoundsOptions(
  coordinates: [number, number][],
  fallbackBounds: [[number, number], [number, number]],
  padding: number,
  maxZoom: number,
) {
  if (!coordinates.length) {
    return {
      bounds: fallbackBounds,
      fitBoundsOptions: {
        padding,
        maxZoom,
        duration: 0,
      },
    } as const;
  }

  if (coordinates.length === 1) {
    return {
      center: coordinates[0],
      zoom: maxZoom,
    } as const;
  }

  const bounds = new maplibregl.LngLatBounds();
  for (const coordinate of coordinates) {
    bounds.extend(coordinate);
  }

  return {
    bounds,
    fitBoundsOptions: {
      padding,
      maxZoom,
      duration: 0,
    },
  } as const;
}

function fitMapToCoordinates(
  map: maplibregl.Map,
  coordinates: [number, number][],
  { padding, maxZoom, duration }: { padding: number; maxZoom: number; duration: number },
) {
  if (coordinates.length === 0) {
    return;
  }
  if (coordinates.length === 1) {
    map.easeTo({
      center: coordinates[0],
      zoom: maxZoom,
      duration,
    });
    return;
  }
  const lngLatBounds = new maplibregl.LngLatBounds();
  for (const coordinate of coordinates) {
    lngLatBounds.extend(coordinate);
  }
  map.fitBounds(lngLatBounds, { padding, maxZoom, duration });
}

function averageWithinWindow(values: Array<number | null>, timestamps: number[], windowMs: number): Array<number | null> {
  if (!values.length) {
    return [];
  }
  if (windowMs <= 0) {
    return values;
  }
  const smoothed = new Array<number | null>(values.length).fill(null);
  let startIndex = 0;
  let sum = 0;
  let count = 0;
  for (let index = 0; index < values.length; index += 1) {
    const currentTimestamp = timestamps[index];
    const sample = values[index];
    if (sample != null) {
      sum += sample;
      count += 1;
    }
    while (startIndex < index && currentTimestamp - timestamps[startIndex] > windowMs) {
      const exiting = values[startIndex];
      if (exiting != null) {
        sum -= exiting;
        count -= 1;
      }
      startIndex += 1;
    }
    smoothed[index] = count > 0 ? sum / count : null;
  }
  return smoothed;
}

type TrackTelemetrySeries = {
  uploadId: number;
  timestamps: number[];
  altitudeM: Array<number | null>;
  speedKmh: Array<number | null>;
  verticalSpeedMps: Array<number | null>;
  glideRatio: Array<number | null>;
};

type HighlightedTrackSnapshot = {
  pilotName: string;
  coordinate: [number, number];
  altitudeM: number | null;
  speedKmh: number | null;
  verticalSpeedMps: number | null;
  glideRatio: number | null;
  color: string;
};

type TaskCylinderVolume = {
  polygon: [number, number][];
  pointType: string;
};

function buildTrackTelemetrySeries(
  coordinates: TrackPosition[],
  timestamps: number[],
  smoothing: MapTelemetrySmoothing,
): {
  altitudeM: Array<number | null>;
  speedKmh: Array<number | null>;
  verticalSpeedMps: Array<number | null>;
  glideRatio: Array<number | null>;
} {
  const altitudeSamples = coordinates.map((coordinate) => (coordinate.length > 2 && Number.isFinite(coordinate[2]) ? coordinate[2] ?? 0 : null));
  const speedSamples = new Array<number | null>(coordinates.length).fill(null);
  const verticalSpeedSamples = new Array<number | null>(coordinates.length).fill(null);
  const glideRatioSamples = new Array<number | null>(coordinates.length).fill(null);

  for (let index = 1; index < coordinates.length; index += 1) {
    const currentTimestamp = timestamps[index];
    const previousTimestamp = timestamps[index - 1];
    if (!Number.isFinite(currentTimestamp) || !Number.isFinite(previousTimestamp) || currentTimestamp <= previousTimestamp) {
      continue;
    }
    const elapsedSeconds = (currentTimestamp - previousTimestamp) / 1000;
    if (elapsedSeconds <= 0) {
      continue;
    }
    const currentCoordinate = coordinates[index];
    const previousCoordinate = coordinates[index - 1];
    const distanceKm = haversineKm([previousCoordinate[0], previousCoordinate[1]], [currentCoordinate[0], currentCoordinate[1]]);
    speedSamples[index] = distanceKm / (elapsedSeconds / 3600);
    if (currentCoordinate.length > 2 && previousCoordinate.length > 2) {
      const altitudeDeltaM = (currentCoordinate[2] ?? 0) - (previousCoordinate[2] ?? 0);
      verticalSpeedSamples[index] = altitudeDeltaM / elapsedSeconds;
      const altitudeLossM = -altitudeDeltaM;
      if (altitudeLossM > 0.1) {
        glideRatioSamples[index] = (distanceKm * 1000) / altitudeLossM;
      }
    }
  }

  return {
    altitudeM: averageWithinWindow(altitudeSamples, timestamps, smoothing.telemetry_altitude_smoothing_seconds * 1000),
    speedKmh: averageWithinWindow(speedSamples, timestamps, smoothing.telemetry_speed_smoothing_seconds * 1000),
    verticalSpeedMps: averageWithinWindow(verticalSpeedSamples, timestamps, smoothing.telemetry_vario_smoothing_seconds * 1000),
    glideRatio: averageWithinWindow(glideRatioSamples, timestamps, smoothing.telemetry_glide_ratio_smoothing_seconds * 1000),
  };
}

function findReplayCoordinateIndex(timestamps: number[], currentReplayTime: number) {
  if (!timestamps.length) {
    return -1;
  }
  if (currentReplayTime < timestamps[0]) {
    return -1;
  }
  let index = 0;
  while (index + 1 < timestamps.length && timestamps[index + 1] <= currentReplayTime) {
    index += 1;
  }
  return index;
}

function pointTypeColor(pointType: string): [number, number, number] {
  switch (pointType) {
    case "launch":
      return [249, 115, 22];
    case "start":
      return [37, 99, 235];
    case "ESS":
      return [124, 58, 237];
    case "goal":
      return [22, 163, 74];
    default:
      return [220, 38, 38];
  }
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

function ensureMapLayers(map: maplibregl.Map, isPerspective3D = false) {
  if (hasSource(map, "airspaces")) {
    if (isPerspective3D) {
      removeLayerIfPresent(map, "airspaces-fill");
      if (!map.getLayer("airspaces-extrusion")) {
        safeAddLayer(map, {
          id: "airspaces-extrusion",
          type: "fill-extrusion",
          source: "airspaces",
          paint: {
            "fill-extrusion-color": [
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
            "fill-extrusion-opacity": [
              "case",
              ["get", "is_restricted_field"],
              0.24,
              0.14,
            ],
            "fill-extrusion-base": [
              "max",
              0,
              ["coalesce", ["get", "lower_limit_m"], 0],
            ],
            "fill-extrusion-height": [
              "max",
              50,
              [
                "-",
                [
                  "coalesce",
                  ["get", "upper_limit_m"],
                  ["+", ["coalesce", ["get", "lower_limit_m"], 0], 1500],
                ],
                ["coalesce", ["get", "lower_limit_m"], 0],
              ],
            ],
          },
        });
      }
    } else {
      removeLayerIfPresent(map, "airspaces-extrusion");
      if (!map.getLayer("airspaces-fill")) {
        safeAddLayer(map, {
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
    }
  }
  if (hasSource(map, "airspaces") && !map.getLayer("airspaces-outline")) {
    safeAddLayer(map, {
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
  if (hasSource(map, "airspace-labels") && !map.getLayer("airspace-labels")) {
    safeAddLayer(map, {
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
  if (hasSource(map, "turnpoints") && !map.getLayer("turnpoints-layer")) {
    safeAddLayer(map, { id: "turnpoints-layer", type: "circle", source: "turnpoints", paint: { "circle-radius": 5, "circle-color": "#0f766e", "circle-stroke-width": 1, "circle-stroke-color": "#ffffff" } });
  }
  if (hasSource(map, "turnpoints") && !map.getLayer("turnpoints-labels")) {
    safeAddLayer(map, {
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
  if (hasSource(map, "task-cylinders") && !map.getLayer("task-cylinders-fill")) {
    safeAddLayer(map, {
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
  if (hasSource(map, "task-cylinders") && !map.getLayer("task-cylinders-outline")) {
    safeAddLayer(map, {
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
  if (hasSource(map, "task-route") && !map.getLayer("task-route-layer")) {
    safeAddLayer(map, { id: "task-route-layer", type: "line", source: "task-route", paint: { "line-color": "#1d4ed8", "line-width": 3 } });
  }
  if (hasSource(map, "task-route-arrows") && !map.getLayer("task-route-arrows-layer")) {
    safeAddLayer(map, {
      id: "task-route-arrows-layer",
      type: "symbol",
      source: "task-route-arrows",
      layout: {
        "text-field": "\u25B6",
        "text-size": 26,
        "text-anchor": "center",
        "text-offset": [0, -0.16],
        "text-rotate": ["coalesce", ["get", "rotation"], 0],
        "text-rotation-alignment": "map",
        "text-pitch-alignment": "map",
        "text-allow-overlap": true,
        "text-ignore-placement": true,
        "text-keep-upright": false,
        "symbol-placement": "point",
      },
      paint: {
        "text-color": "#1d4ed8",
        "text-halo-color": "rgba(255,255,255,0.9)",
        "text-halo-width": 1.2,
      },
    });
  }
  if (hasSource(map, "optimized-route") && !map.getLayer("optimized-route-layer")) {
    safeAddLayer(map, {
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
  if (hasSource(map, "optimized-route-points") && !map.getLayer("optimized-route-points")) {
    safeAddLayer(map, {
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
  if (hasSource(map, "optimized-leg-labels") && !map.getLayer("optimized-leg-labels")) {
    safeAddLayer(map, {
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
  if (hasSource(map, "task-points") && !map.getLayer("task-points-layer")) {
    safeAddLayer(map, {
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
  if (hasSource(map, "live-positions") && !map.getLayer("live-positions-layer")) {
    // Live pilot labels are rendered with deck.gl so they can follow the pilot altitude in 3D.
  }
  if (hasSource(map, "replay-marker") && !map.getLayer("replay-marker-layer")) {
    // Replay pilot labels are rendered with deck.gl so they can follow the pilot altitude in 3D.
  }
  if (hasSource(map, "scored-track-points") && !map.getLayer("scored-track-points-layer")) {
    safeAddLayer(map, {
      id: "scored-track-points-layer",
      type: "circle",
      source: "scored-track-points",
      paint: {
        "circle-radius": [
          "case",
          ["boolean", ["get", "highlighted"], false],
          8,
          6,
        ],
        "circle-color": ["coalesce", ["get", "color"], "#111827"],
        "circle-stroke-width": 2,
        "circle-stroke-color": "#ffffff",
        "circle-opacity": 0.96,
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

const USA_FIT_BOUNDS: [[number, number], [number, number]] = [[-125, 24], [-66.5, 49.5]];

export const TaskMap = React.memo(function TaskMap({
  turnpoints,
  airspaces = [],
  taskPoints,
  optimizedRoute = [],
  legMetrics = [],
  track,
  scoredTrackPoints = [],
  livePositions = [],
  liveMarkerScale = 1,
  editable,
  onSelectTurnpoint,
  taskEditorOverlay,
  fullscreenSidebar,
  fullscreenSidebarLabel = "Pilot list",
  highlightedTrackUploadId,
  fitKey,
  fitOnceKey,
  fitTurnpoints,
  fitMaxZoom = 10,
  viewStateKey,
  preserveViewStateOnRemount = false,
  mode = "replay",
  units = { altitude: "ft", speed: "kph", distance: "km", vario: "fpm" },
  telemetrySmoothing = {
    telemetry_vario_smoothing_seconds: 5,
    telemetry_altitude_smoothing_seconds: 3,
    telemetry_speed_smoothing_seconds: 3,
    telemetry_glide_ratio_smoothing_seconds: 5,
  },
  showGpsButton = false,
  overlayConfig,
  focusPosition,
}: {
  turnpoints: MapTurnpoint[];
  airspaces?: MapAirspaceRegion[];
  taskPoints: MapTaskPoint[];
  optimizedRoute?: [number, number][];
  legMetrics?: MapLegMetric[];
  track: TrackCollection | null;
  scoredTrackPoints?: MapScoredTrackPoint[];
  livePositions?: MapLivePosition[];
  liveMarkerScale?: number;
  editable: boolean;
  onSelectTurnpoint?: (turnpoint: MapTurnpoint) => void;
  taskEditorOverlay?: TaskEditorOverlayContent;
  fullscreenSidebar?: FullscreenSidebarContent;
  fullscreenSidebarLabel?: string;
  highlightedTrackUploadId?: number | null;
  fitKey?: string | number | null;
  fitOnceKey?: string | number | null;
  fitTurnpoints?: MapTurnpoint[];
  fitMaxZoom?: number;
  viewStateKey?: string | number | null;
  preserveViewStateOnRemount?: boolean;
  mode?: "replay" | "live";
  units?: MapUnitPreferences;
  telemetrySmoothing?: MapTelemetrySmoothing;
  showGpsButton?: boolean;
  overlayConfig?: Record<string, boolean>;
  focusPosition?: { lat: number; lon: number; key: string | number } | null;
}) {
  const shellRef = useRef<HTMLDivElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const deckOverlayRef = useRef<MapboxOverlay | null>(null);
  const scoredPointPopupRef = useRef<maplibregl.Popup | null>(null);
  const fullscreenControlRef = useRef<maplibregl.FullscreenControl | null>(null);
  const lastFocusPositionKeyRef = useRef<string | number | null>(null);
  const turnpointsRef = useRef(turnpoints);
  const taskPointsRef = useRef(taskPoints);
  const optimizedRouteRef = useRef(optimizedRoute);
  const trackRef = useRef(track);
  const viewStateKeyRef = useRef(viewStateKey);
  const fitGeometrySignatureRef = useRef("");
  const fitKeyRef = useRef<string>("");
  const fitOnceKeyRef = useRef<string>("");
  const fitPendingForGeometryRef = useRef(false);
  const fitTargetKindRef = useRef<FitTarget["kind"]>("fallback");
  const renderedTaskGeometrySignatureRef = useRef("");
  const programmaticCameraMoveRef = useRef(false);
  const manualViewChangedRef = useRef(false);
  const lastCenteredHighlightRef = useRef<number | null>(null);
  const previousHighlightedTrackUploadIdRef = useRef<number | null | undefined>(undefined);
  const editableRef = useRef(editable);
  const onSelectTurnpointRef = useRef(onSelectTurnpoint);
  const animationFrameRef = useRef<number | null>(null);
  const lastFrameTimeRef = useRef<number | null>(null);
  const replayClockRef = useRef<number | null>(null);
  const replayIndexRef = useRef(0);
  const [basemapMode, setBasemapMode] = useState<BasemapMode>("streets");
  const [altitudeMultiplier, setAltitudeMultiplier] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isTaskEditorOverlayCollapsed, setIsTaskEditorOverlayCollapsed] = useState(false);
  const [isFullscreenSidebarCollapsed, setIsFullscreenSidebarCollapsed] = useState(false);
  const [isPerspective3D, setIsPerspective3D] = useState(false);
  const taskEditorOverlayId = useId();
  const taskEditorOverlayContentId = useId();
  const fullscreenSidebarContentId = useId();
  const fullscreenSidebarPanelContentId = useId();
  const oc = overlayConfig;
  const hasTaskEditorOverlay = Boolean(taskEditorOverlay) && oc?.fullscreen_editor_panel !== false;
  // In 2D mode, collapse all track/marker/label altitudes to 0 so they render
  // flat on the map plane; in 3D they scale by the user-selected multiplier.
  const effectiveAltitudeMultiplier = isPerspective3D ? altitudeMultiplier : 0;
  const [isReplaying, setIsReplaying] = useState(false);
  const [replayIndex, setReplayIndex] = useState(0);
  const [replaySpeed, setReplaySpeed] = useState(10);
  const [replayHasInteracted, setReplayHasInteracted] = useState(false);
  const [displayedHighlightedTrackSnapshot, setDisplayedHighlightedTrackSnapshot] = useState<HighlightedTrackSnapshot | null>(null);
  const [gpsFollowing, setGpsFollowing] = useState(false);
  const [mapReadyNonce, setMapReadyNonce] = useState(0);
  const [scaleBar, setScaleBar] = useState<{ label: string; width: number } | null>(null);
  const gpsWatchIdRef = useRef<number | null>(null);
  const gpsFollowingRef = useRef(false);
  const gpsLocateRequestIdRef = useRef(0);
  const gpsLastCameraCenterRef = useRef<[number, number] | null>(null);
  const gpsHasLocationRef = useRef(false);
  const gpsHighAccuracyReceivedRef = useRef(false);

  // Overlay config: filter data layers based on admin toggle matrix
  const effectiveTurnpoints = oc?.turnpoints === false ? [] : turnpoints;
  const effectiveAirspaces = oc?.airspaces === false ? [] : (airspaces ?? []);
  const effectiveAirspaceLabels = oc?.airspace_labels === false ? [] : effectiveAirspaces;
  const effectiveTrack = oc?.flight_track === false ? null : track;
  const effectiveHighlightedTrackUploadId = oc?.track_highlight === false ? null : highlightedTrackUploadId;
  const effectiveLivePositions = oc?.live_positions === false ? [] : livePositions;
  const effectiveLiveLabelPositions = oc?.live_labels === false ? [] : effectiveLivePositions;
  const effectiveOptimizedRoute = oc?.optimized_route === false ? [] : optimizedRoute;
  const effectiveLegMetrics = oc?.leg_labels === false ? [] : legMetrics;
  const effectiveTaskRoutePoints = oc?.task_route === false ? [] : taskPoints;
  const effectiveTaskCylinderPoints = oc?.task_cylinders === false ? [] : taskPoints;
  const effectiveScoredTrackPoints = oc?.flight_track === false ? [] : scoredTrackPoints;
  const clickToAddTurnpointEnabledRef = useRef(oc?.click_to_add_turnpoint !== false);

  const stopGpsFollowing = useCallback((map: maplibregl.Map) => {
    gpsLocateRequestIdRef.current += 1;
    gpsLastCameraCenterRef.current = null;
    gpsHasLocationRef.current = false;
    gpsHighAccuracyReceivedRef.current = false;
    if (gpsWatchIdRef.current != null) {
      navigator.geolocation.clearWatch(gpsWatchIdRef.current);
      gpsWatchIdRef.current = null;
    }
    try { map.removeLayer("user-location-pulse"); } catch {}
    try { map.removeLayer("user-location-dot"); } catch {}
    try { map.removeSource("user-location"); } catch {}
    gpsFollowingRef.current = false;
    setGpsFollowing(false);
  }, []);

  const fitToCurrentTarget = useCallback((map: maplibregl.Map, duration = 600, includeHiddenTaskGeometry = false) => {
    const target = resolveFitTarget(
      includeHiddenTaskGeometry ? taskPoints : effectiveTaskRoutePoints,
      includeHiddenTaskGeometry ? optimizedRoute : effectiveOptimizedRoute,
      includeHiddenTaskGeometry ? turnpoints : effectiveTurnpoints,
      effectiveTrack,
      fitTurnpoints,
      effectiveLivePositions,
    );
    if (target.kind === "fallback") {
      return false;
    }
    programmaticCameraMoveRef.current = true;
    fitMapToCoordinates(map, target.coordinates, { padding: 60, maxZoom: fitMaxZoom, duration });
    return true;
  }, [effectiveLivePositions, effectiveOptimizedRoute, effectiveTaskRoutePoints, effectiveTrack, effectiveTurnpoints, fitMaxZoom, fitTurnpoints, optimizedRoute, taskPoints, turnpoints]);

  // GPS toggle handler
  const handleGpsToggle = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    if (gpsFollowingRef.current) {
      // Stop following — zoom back to task/turnpoints
      stopGpsFollowing(map);
      // Clear pan-lock so waypoint geometry updates can auto-fit again
      manualViewChangedRef.current = false;
      // Refit to task bounds
      fitToCurrentTarget(map);
    } else {
      // Start following — clear any pan-lock so the button always re-centers
      if (!("geolocation" in navigator)) return;
      manualViewChangedRef.current = false;
      gpsFollowingRef.current = true;
      setGpsFollowing(true);
      map.stop();
      const locateRequestId = gpsLocateRequestIdRef.current + 1;
      gpsLocateRequestIdRef.current = locateRequestId;
      gpsLastCameraCenterRef.current = null;
      gpsHasLocationRef.current = false;
      gpsHighAccuracyReceivedRef.current = false;

      const isCurrentLocateRequest = () => gpsLocateRequestIdRef.current === locateRequestId && mapRef.current === map;
      const applyLocationFix = (pos: GeolocationPosition, accuracyMode: "quick" | "high") => {
        if (!isCurrentLocateRequest()) {
          return;
        }
        if (accuracyMode === "quick" && gpsHighAccuracyReceivedRef.current) {
          return;
        }
        const lngLat: [number, number] = [pos.coords.longitude, pos.coords.latitude];
        const src = map.getSource("user-location") as maplibregl.GeoJSONSource | undefined;
        const geojson = { type: "FeatureCollection" as const, features: [{ type: "Feature" as const, properties: {}, geometry: { type: "Point" as const, coordinates: lngLat } }] };
        if (src) {
          src.setData(geojson);
        } else {
          map.addSource("user-location", { type: "geojson", data: geojson });
          map.addLayer({ id: "user-location-pulse", type: "circle", source: "user-location", paint: { "circle-radius": 18, "circle-color": "#2563eb", "circle-opacity": 0.15 } });
          map.addLayer({ id: "user-location-dot", type: "circle", source: "user-location", paint: { "circle-radius": 7, "circle-color": "#2563eb", "circle-stroke-width": 2, "circle-stroke-color": "#ffffff" } });
        }
        gpsHasLocationRef.current = true;
        if (accuracyMode === "high") {
          gpsHighAccuracyReceivedRef.current = true;
        }

        // Stop centering if user has panned away — they're exploring the map.
        if (manualViewChangedRef.current) {
          return;
        }
        const previousCenter = gpsLastCameraCenterRef.current;
        const movedMeters = previousCenter
          ? new maplibregl.LngLat(previousCenter[0], previousCenter[1]).distanceTo(new maplibregl.LngLat(lngLat[0], lngLat[1]))
          : Number.POSITIVE_INFINITY;
        if (movedMeters <= 30) {
          return;
        }
        gpsLastCameraCenterRef.current = lngLat;
        programmaticCameraMoveRef.current = true;
        map.easeTo({
          center: lngLat,
          zoom: Math.max(map.getZoom(), 13),
          duration: accuracyMode === "quick" ? 250 : 600,
        });
      };

      navigator.geolocation.getCurrentPosition(
        (pos) => applyLocationFix(pos, "quick"),
        () => {},
        { enableHighAccuracy: false, maximumAge: 60000, timeout: 1200 },
      );
      const watchId = navigator.geolocation.watchPosition(
        (pos) => applyLocationFix(pos, "high"),
        () => {
          if (!isCurrentLocateRequest() || gpsHasLocationRef.current) {
            return;
          }
          gpsLocateRequestIdRef.current += 1;
          gpsLastCameraCenterRef.current = null;
          gpsHighAccuracyReceivedRef.current = false;
          if (gpsWatchIdRef.current != null) {
            navigator.geolocation.clearWatch(gpsWatchIdRef.current);
            gpsWatchIdRef.current = null;
          }
          gpsFollowingRef.current = false;
          setGpsFollowing(false);
        },
        { enableHighAccuracy: true, maximumAge: 5000, timeout: 10000 },
      );
      gpsWatchIdRef.current = watchId;
    }
  }, [fitToCurrentTarget, gpsFollowing, stopGpsFollowing]);

  // Cleanup GPS watch on unmount
  useEffect(() => {
    return () => {
      gpsLocateRequestIdRef.current += 1;
      if (gpsWatchIdRef.current != null) {
        navigator.geolocation.clearWatch(gpsWatchIdRef.current);
      }
      gpsFollowingRef.current = false;
    };
  }, []);

  const turnpointData = useMemo(() => ({ type: "FeatureCollection", features: effectiveTurnpoints.map((turnpoint) => ({ type: "Feature", properties: { id: turnpoint.id, name: turnpoint.name, code: turnpoint.code ?? "" }, geometry: { type: "Point", coordinates: [turnpoint.longitude, turnpoint.latitude] } })) }), [effectiveTurnpoints]);
  const livePositionData = useMemo(() => ({
    type: "FeatureCollection",
    features: effectiveLivePositions.map((position) => ({
      type: "Feature",
      properties: {
        id: position.id,
        pilot_id: position.pilotId ?? "",
        name: position.pilotName,
        color: position.color ?? "#0ea5e9",
        aircraft_icon: normalizeAircraftIcon(position.aircraftType),
        battery_level: position.batteryLevel ?? "",
        source: position.source ?? "",
      },
      geometry: {
        type: "Point",
        coordinates: [position.longitude, position.latitude],
      },
    })),
  }), [effectiveLivePositions]);
  const livePilotMarkerData = useMemo(
    () =>
      effectiveLivePositions.map((position) => ({
        nameLabel: aircraftPilotLabel(normalizeAircraftIcon(position.aircraftType), position.pilotName),
        altitudeLabel: position.altitudeM != null ? formatAltitudeLabel(position.altitudeM, units.altitude) : "",
        position: [position.longitude, position.latitude, (position.altitudeM ?? 0) * effectiveAltitudeMultiplier] as [number, number, number],
        color: hexToRgb(String(position.color ?? "#0ea5e9")),
        profileType: (position.profileType ?? "pilot") as "pilot" | "driver" | "stationary_node",
        positionSource: (position.positionSource ?? "other") as "cellular" | "mesh" | "other",
        aircraftType: normalizeAircraftIcon(position.aircraftType),
      })),
    [effectiveAltitudeMultiplier, effectiveLivePositions, units.altitude],
  );
  const livePilotLabelData = useMemo(
    () =>
      effectiveLiveLabelPositions.map((position) => ({
        nameLabel: aircraftPilotLabel(normalizeAircraftIcon(position.aircraftType), position.pilotName),
        altitudeLabel: position.altitudeM != null ? formatAltitudeLabel(position.altitudeM, units.altitude) : "",
        position: [position.longitude, position.latitude, (position.altitudeM ?? 0) * effectiveAltitudeMultiplier] as [number, number, number],
        color: hexToRgb(String(position.color ?? "#0ea5e9")),
        profileType: (position.profileType ?? "pilot") as "pilot" | "driver" | "stationary_node",
        positionSource: (position.positionSource ?? "other") as "cellular" | "mesh" | "other",
        aircraftType: normalizeAircraftIcon(position.aircraftType),
      })),
    [effectiveAltitudeMultiplier, effectiveLiveLabelPositions, units.altitude],
  );
  const airspaceData = useMemo(() => ({
    type: "FeatureCollection",
    features: effectiveAirspaces.map((airspace) => ({
      type: "Feature",
      properties: {
        id: airspace.id,
        name: airspace.name,
        display_category: airspace.display_category,
        class_code: airspace.class_code ?? "",
        type_code: airspace.type_code ?? "",
        lower_limit_label: airspace.lower_limit_label ?? "",
        upper_limit_label: airspace.upper_limit_label ?? "",
        lower_limit_m: airspace.lower_limit_m ?? null,
        upper_limit_m: airspace.upper_limit_m ?? null,
        is_restricted_field: airspace.is_restricted_field,
      },
      geometry: airspace.geometry_json,
    })),
  }), [effectiveAirspaces]);
  const airspaceLabelData = useMemo(() => ({
    type: "FeatureCollection",
    features: effectiveAirspaceLabels
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
  }), [effectiveAirspaceLabels]);
  const taskPointData = useMemo(() => ({ type: "FeatureCollection", features: effectiveTaskRoutePoints.map((point) => ({ type: "Feature", properties: { name: point.name, point_type: point.point_type }, geometry: { type: "Point", coordinates: [point.longitude, point.latitude] } })) }), [effectiveTaskRoutePoints]);
  const scoredTrackPointData = useMemo(() => ({
    type: "FeatureCollection",
    features: effectiveScoredTrackPoints.map((point) => ({
      type: "Feature",
      properties: {
        id: point.id,
        upload_id: point.uploadId,
        pilot_name: point.pilotName,
        point_name: point.pointName,
        point_type: point.pointType,
        direction: point.direction ?? "",
        timestamp: point.timestamp ?? "",
        scored_timestamp: point.scoredTimestamp ?? "",
        altitude_m: point.altitudeM ?? null,
        altitude_label: point.altitudeM != null ? formatAltitudeLabel(point.altitudeM, units.altitude) : "",
        latitude: point.latitude,
        longitude: point.longitude,
        color: point.color ?? "#111827",
        highlighted: point.uploadId != null && point.uploadId === effectiveHighlightedTrackUploadId,
      },
      geometry: { type: "Point", coordinates: [point.longitude, point.latitude] },
    })),
  }), [effectiveHighlightedTrackUploadId, effectiveScoredTrackPoints, units.altitude]);
  const scoredTrackDeckPointData = useMemo<ScoredTrackDeckPoint[]>(
    () =>
      effectiveScoredTrackPoints.map((point) => ({
        ...point,
        position: [point.longitude, point.latitude, (point.altitudeM ?? 0) * effectiveAltitudeMultiplier],
        deckColor: hexToRgb(String(point.color ?? "#111827")),
        highlighted: point.uploadId != null && point.uploadId === effectiveHighlightedTrackUploadId,
        altitudeLabel: point.altitudeM != null ? formatAltitudeLabel(point.altitudeM, units.altitude) : "",
      })),
    [effectiveAltitudeMultiplier, effectiveHighlightedTrackUploadId, effectiveScoredTrackPoints, units.altitude],
  );
  const routeData = useMemo(() => ({ type: "FeatureCollection", features: effectiveTaskRoutePoints.length > 1 ? [{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: effectiveTaskRoutePoints.map((point) => [point.longitude, point.latitude]) } }] : [] }), [effectiveTaskRoutePoints]);
  const routeArrowData = useMemo(() => buildRouteArrowData(effectiveTaskRoutePoints.map((point) => [point.longitude, point.latitude])), [effectiveTaskRoutePoints]);
  const optimizedRouteData = useMemo(() => ({ type: "FeatureCollection", features: effectiveOptimizedRoute.length > 1 ? [{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: effectiveOptimizedRoute } }] : [] }), [effectiveOptimizedRoute]);
  const optimizedRoutePointData = useMemo(() => ({
    type: "FeatureCollection",
    features: effectiveOptimizedRoute.map((coordinate, index) => ({
      type: "Feature",
      properties: { index: index + 1 },
      geometry: { type: "Point", coordinates: coordinate },
    })),
  }), [effectiveOptimizedRoute]);
  const legLabelData = useMemo(() => ({
    type: "FeatureCollection",
    features: effectiveLegMetrics.map((leg) => ({
      type: "Feature",
      properties: { label: formatDistanceLabel(leg.optimizedDistanceKm, units.distance) },
      geometry: { type: "Point", coordinates: leg.midpoint },
    })),
  }), [effectiveLegMetrics, units.distance]);
  const cylinderData = useMemo(() => ({ type: "FeatureCollection", features: effectiveTaskCylinderPoints.map(buildCircle) }), [effectiveTaskCylinderPoints]);
  const taskGeometrySignature = useMemo(() => buildTaskGeometrySignature(effectiveTaskRoutePoints, effectiveOptimizedRoute), [effectiveOptimizedRoute, effectiveTaskRoutePoints]);
  const resolvedFitTarget = useMemo(
    () => resolveFitTarget(effectiveTaskRoutePoints, effectiveOptimizedRoute, effectiveTurnpoints, effectiveTrack, fitTurnpoints, effectiveLivePositions),
    [effectiveLivePositions, effectiveOptimizedRoute, effectiveTaskRoutePoints, effectiveTrack, effectiveTurnpoints, fitTurnpoints],
  );
  const cylinderVolumes = useMemo<TaskCylinderVolume[]>(
    () =>
      effectiveTaskCylinderPoints.map((point) => ({
        polygon: (buildCircle(point).geometry.coordinates[0] as [number, number][]),
        pointType: point.point_type,
      })),
    [effectiveTaskCylinderPoints],
  );
  const trackFeatureTimelines = useMemo(() => {
    if (!effectiveTrack) {
      return [] as Array<{ uploadId: number; timestamps: number[]; coordinateCount: number }>;
    }
    return effectiveTrack.features.map((feature) => {
      const raw = Array.isArray(feature.properties?.timestamps) ? feature.properties.timestamps : [];
      const timestamps = raw
        .slice(0, feature.geometry.coordinates.length)
        .map((value) => Date.parse(String(value)))
        .filter((value) => Number.isFinite(value));
      return {
        uploadId: Number(feature.properties?.upload_id ?? 0),
        timestamps,
        coordinateCount: feature.geometry.coordinates.length,
      };
    });
  }, [effectiveTrack]);
  const effectiveTelemetrySmoothing = useMemo(
    () => resolveAdaptiveTelemetrySmoothing(telemetrySmoothing, mode, isReplaying, replaySpeed),
    [isReplaying, mode, replaySpeed, telemetrySmoothing],
  );
  const smoothedTrackTelemetrySeries = useMemo<TrackTelemetrySeries[]>(() => {
    if (!effectiveTrack) {
      return [];
    }
    return effectiveTrack.features.map((feature, featureIndex) => {
      const timestamps = trackFeatureTimelines[featureIndex]?.timestamps ?? [];
      const limitedCoordinates = feature.geometry.coordinates.slice(0, timestamps.length);
      const series = buildTrackTelemetrySeries(limitedCoordinates, timestamps, effectiveTelemetrySmoothing);
      return {
        uploadId: Number(feature.properties?.upload_id ?? 0),
        timestamps,
        altitudeM: series.altitudeM,
        speedKmh: series.speedKmh,
        verticalSpeedMps: series.verticalSpeedMps,
        glideRatio: series.glideRatio,
      };
    });
  }, [effectiveTelemetrySmoothing, effectiveTrack, trackFeatureTimelines]);
  const replayTimeline = useMemo(() => {
    const unique = new Set<number>();
    trackFeatureTimelines.forEach((feature) => {
      feature.timestamps.forEach((timestamp) => unique.add(timestamp));
    });
    return Array.from(unique).sort((left, right) => left - right);
  }, [trackFeatureTimelines]);
  const replayTotal = replayTimeline.length;
  const maxMapPitch = Math.max(0, Math.min(85, telemetrySmoothing.max_map_pitch_degrees ?? DEFAULT_MAX_MAP_PITCH));
  const visibleTrackLengths = useMemo(() => {
    if (!effectiveTrack) {
      return [] as number[];
    }
    const hasReplay = replayTotal > 0;
    const shouldSliceTrack = hasReplay && (isReplaying || replayHasInteracted);
    const currentReplayTime = hasReplay ? replayTimeline[Math.min(replayIndex, replayTotal - 1)] : null;
    return effectiveTrack.features.map((feature, featureIndex) => {
      if (!shouldSliceTrack || currentReplayTime == null) {
        return feature.geometry.type === "LineString" ? feature.geometry.coordinates.length : 0;
      }
      const parsedFeatureTimestamps = trackFeatureTimelines[featureIndex]?.timestamps ?? [];
      if (!parsedFeatureTimestamps.length) {
        return 0;
      }
      const replayCoordinateIndex = findReplayCoordinateIndex(parsedFeatureTimestamps, currentReplayTime);
      if (replayCoordinateIndex < 0) {
        return 0;
      }
      return Math.min(replayCoordinateIndex + 1, feature.geometry.type === "LineString" ? feature.geometry.coordinates.length : 0);
    });
  }, [effectiveTrack, isReplaying, replayHasInteracted, replayIndex, replayTimeline, replayTotal, trackFeatureTimelines]);
  const fullTrackPathData = useMemo(() => {
    if (!effectiveTrack) {
      return [] as Array<{
        uploadId: number;
        path: [number, number, number][];
        color: [number, number, number];
        highlighted: boolean;
      }>;
    }
    return effectiveTrack.features
      .filter((feature) => feature.geometry.type === "LineString")
      .map((feature, featureIndex) => ({
        uploadId: Number(feature.properties?.upload_id ?? 0),
        path: feature.geometry.coordinates.map((coordinate) => scaleTrackPosition(coordinate, effectiveAltitudeMultiplier) as [number, number, number]),
        color: hexToRgb(String(feature.properties?.color ?? "#ca8a04")),
        highlighted: Number(feature.properties?.upload_id ?? 0) === effectiveHighlightedTrackUploadId,
      }));
  }, [effectiveAltitudeMultiplier, effectiveHighlightedTrackUploadId, effectiveTrack]);
  const displayTrack = useMemo<TrackCollection | null>(() => {
    if (!effectiveTrack) {
      return null;
    }
    return {
      type: "FeatureCollection",
      features: effectiveTrack.features.map((feature, featureIndex) => ({
        ...feature,
        geometry: {
          ...feature.geometry,
          coordinates:
            feature.geometry.type === "LineString"
              ? fullTrackPathData[featureIndex]?.path.slice(0, visibleTrackLengths[featureIndex] ?? 0) ?? []
              : feature.geometry.coordinates,
        },
      })),
    };
  }, [effectiveTrack, fullTrackPathData, visibleTrackLengths]);
  const replayMarkerData = useMemo(() => {
    if (!effectiveTrack || !replayTotal) {
      return { type: "FeatureCollection", features: [] as Array<Record<string, unknown>> };
    }
    const shouldUseReplayPosition = isReplaying || replayHasInteracted;
    const currentReplayTime = replayTimeline[Math.min(replayIndex, replayTotal - 1)];
    const features = effectiveTrack.features.flatMap((feature, featureIndex) => {
      if (feature.geometry.type !== "LineString" || !feature.geometry.coordinates.length) {
        return [];
      }
      const featureTimestamps = trackFeatureTimelines[featureIndex]?.timestamps ?? [];
      if (!featureTimestamps.length) {
        return [];
      }
      let coordinateIndex = featureTimestamps.length - 1;
      if (shouldUseReplayPosition) {
        coordinateIndex = findReplayCoordinateIndex(featureTimestamps, currentReplayTime);
      }
      if (coordinateIndex < 0) {
        return [];
      }
      const coordinate = feature.geometry.coordinates[Math.min(coordinateIndex, feature.geometry.coordinates.length - 1)];
      if (!coordinate) {
        return [];
      }
      return [
        {
          type: "Feature",
          properties: {
            upload_id: Number(feature.properties?.upload_id ?? 0),
            color: String(feature.properties?.color ?? "#2563eb"),
            aircraft_icon: normalizeAircraftIcon(feature.properties?.aircraft_icon),
            highlighted: Number(feature.properties?.upload_id ?? 0) === effectiveHighlightedTrackUploadId,
            label: aircraftPilotLabel(
              normalizeAircraftIcon(feature.properties?.aircraft_icon),
              String(feature.properties?.pilot_name ?? "Pilot"),
            ),
            altitude_label: (() => {
              const telemetrySeries = smoothedTrackTelemetrySeries[featureIndex];
              const smoothedAltitudeM = telemetrySeries?.altitudeM[Math.min(coordinateIndex, telemetrySeries.altitudeM.length - 1)];
              const fallbackAltitudeM = coordinate.length > 2 && Number.isFinite(coordinate[2]) ? Number(coordinate[2] ?? 0) : null;
              const altitudeM = smoothedAltitudeM ?? fallbackAltitudeM;
              return altitudeM != null ? formatAltitudeLabel(altitudeM, units.altitude) : "";
            })(),
          },
          geometry: {
            type: "Point",
            coordinates: scaleTrackPosition(coordinate, effectiveAltitudeMultiplier),
          },
        },
      ];
    });
    return {
      type: "FeatureCollection",
      features,
    };
  }, [effectiveAltitudeMultiplier, effectiveHighlightedTrackUploadId, effectiveTrack, isReplaying, replayHasInteracted, replayIndex, replayTimeline, replayTotal, smoothedTrackTelemetrySeries, trackFeatureTimelines, units.altitude]);
  const replayPilotLabelData = useMemo(
    () =>
      (replayMarkerData.features as Array<{ geometry?: { coordinates?: [number, number, number] | [number, number] }; properties?: Record<string, unknown> }>)
        .flatMap((feature) => {
          const coordinates = feature.geometry?.coordinates;
          if (!coordinates) {
            return [];
          }
          const z = coordinates.length > 2 ? coordinates[2] ?? 0 : 0;
          return [
            {
              nameLabel: String(feature.properties?.label ?? "Pilot"),
              altitudeLabel: String(feature.properties?.altitude_label ?? ""),
              position: [coordinates[0], coordinates[1], z] as [number, number, number],
              color: hexToRgb(String(feature.properties?.color ?? "#2563eb")),
              highlighted: Boolean(feature.properties?.highlighted),
            },
          ];
        }),
    [replayMarkerData],
  );
  const maxScoredTrackAltitudeM = useMemo(() => {
    if (!effectiveTrack) {
      return 15000;
    }
    let maxAltitude = 0;
    for (const feature of effectiveTrack.features) {
      if (feature.geometry.type !== "LineString") {
        continue;
      }
      for (const coordinate of feature.geometry.coordinates) {
        if (coordinate.length > 2 && Number.isFinite(coordinate[2])) {
          maxAltitude = Math.max(maxAltitude, coordinate[2] ?? 0);
        }
      }
    }
    return maxAltitude > 0 ? maxAltitude : 15000;
  }, [effectiveTrack]);
  const deckTrackLayers = useMemo(() => {
    const layers = [];
    if (isPerspective3D && cylinderVolumes.length) {
      layers.push(
        new PolygonLayer({
          id: "task-cylinder-volumes-3d",
          data: cylinderVolumes,
          coordinateSystem: COORDINATE_SYSTEM.LNGLAT,
          extruded: true,
          wireframe: false,
          getPolygon: (item: TaskCylinderVolume) => item.polygon,
          getElevation: maxScoredTrackAltitudeM * altitudeMultiplier,
          getFillColor: (item: TaskCylinderVolume) => [...pointTypeColor(item.pointType), 40],
          getLineColor: (item: TaskCylinderVolume) => pointTypeColor(item.pointType),
          lineWidthUnits: "pixels",
          lineWidthMinPixels: 1,
          pickable: false,
        }),
      );
    }
    if (displayTrack) {
      const pathData = fullTrackPathData
        .map((item, index) => ({
          ...item,
          visibleLength: visibleTrackLengths[index] ?? 0,
        }))
        .filter((item) => item.path.length > 1 && item.visibleLength > 0);
      if (pathData.length) {
        /*
        Previous 3D ribbon experiment, kept here for later tuning if we want to revisit
        extruded replay tracks instead of the flat PathLayer.

        Constants that were used:
          const TRACK_RIBBON_WIDTH_METERS = 8;
          const HIGHLIGHTED_TRACK_RIBBON_WIDTH_METERS = 11;
          const TRACK_RIBBON_ELEVATION_RATIO = 0.3;
          const METERS_PER_DEGREE_LATITUDE = 111320;

        Helper functions that were used:
          metersPerDegreeLongitude(...)
          normalizeVector(...)
          buildTrackRibbonSides(...)
          buildTrackRibbonPolygonFromSides(...)

        if (isPerspective3D) {
          const ribbonBaseData = fullTrackPathData
            .map((item) => {
              const widthMeters = item.highlighted ? HIGHLIGHTED_TRACK_RIBBON_WIDTH_METERS : TRACK_RIBBON_WIDTH_METERS;
              const ribbonSides = buildTrackRibbonSides(item.path, widthMeters);
              if (!ribbonSides) {
                return null;
              }
              return {
                leftSide: ribbonSides.leftSide,
                rightSide: ribbonSides.rightSide,
                color: item.color,
                elevation: widthMeters * TRACK_RIBBON_ELEVATION_RATIO,
              };
            })
            .filter((item) => item != null);

          const ribbonData = ribbonBaseData
            .map((item, index) => ({
              ...item,
              visibleLength: visibleTrackLengths[index] ?? 0,
            }))
            .filter((item) => item.visibleLength > 1);

          layers.push(
            new PolygonLayer({
              id: "igc-track-3d",
              data: ribbonData,
              coordinateSystem: COORDINATE_SYSTEM.LNGLAT,
              extruded: true,
              filled: true,
              wireframe: false,
              getPolygon: (item) =>
                buildTrackRibbonPolygonFromSides(item.leftSide, item.rightSide, item.visibleLength) ?? [],
              getElevation: (item) => item.elevation,
              getFillColor: (item) => [...item.color, 210],
              pickable: false,
              parameters: {
                depthTest: false,
              },
            }),
          );
        } else {
        */
        layers.push(
            new PathLayer({
              id: "igc-track-3d",
              data: pathData,
              coordinateSystem: COORDINATE_SYSTEM.LNGLAT,
              positionFormat: "XYZ",
              getPath: (item: { path: [number, number, number][]; visibleLength: number }) => item.path.slice(0, item.visibleLength),
              getColor: (item: { color: [number, number, number] }) => item.color,
              getWidth: (item: { highlighted: boolean }) =>
                item.highlighted ? HIGHLIGHTED_TRACK_WIDTH_PIXELS : TRACK_WIDTH_PIXELS,
            widthUnits: "pixels",
            widthMinPixels: 1,
            pickable: false,
            jointRounded: true,
            capRounded: true,
            parameters: {
              depthTest: false,
            },
          }),
        );
        // }
      }
    }
    if (scoredTrackDeckPointData.length) {
      layers.push(
        new ScatterplotLayer<ScoredTrackDeckPoint>({
          id: "scored-track-point-markers",
          data: scoredTrackDeckPointData,
          coordinateSystem: COORDINATE_SYSTEM.LNGLAT,
          getPosition: (item: ScoredTrackDeckPoint) => item.position,
          getFillColor: (item: ScoredTrackDeckPoint) => [...item.deckColor, 255] as [number, number, number, number],
          getLineColor: [255, 255, 255, 255],
          getRadius: (item: ScoredTrackDeckPoint) => (item.highlighted ? 8 : 6),
          radiusUnits: "pixels",
          radiusMinPixels: 6,
          radiusMaxPixels: 10,
          stroked: true,
          lineWidthUnits: "pixels",
          lineWidthMinPixels: 2,
          pickable: true,
          onHover: (info: { object?: ScoredTrackDeckPoint; coordinate?: number[] | null }) => {
            const map = mapRef.current;
            if (!map) {
              return;
            }
            if (!info.object || !info.coordinate) {
              map.getCanvas().style.cursor = "";
              scoredPointPopupRef.current?.remove();
              return;
            }
            if (!scoredPointPopupRef.current) {
              scoredPointPopupRef.current = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12 });
            }
            map.getCanvas().style.cursor = "pointer";
            scoredPointPopupRef.current
              .setLngLat([info.object.longitude, info.object.latitude])
              .setHTML(scoredTrackPointPopupHtml(info.object))
              .addTo(map);
          },
        }),
      );
    }
    const labelData = mode === "live" ? livePilotLabelData : replayPilotLabelData;
    const liveMarkerData = mode === "live" ? livePilotMarkerData : [];
    if (liveMarkerData.length) {
      type LiveMarkerItem = {
        position: [number, number, number];
        color: [number, number, number];
        profileType?: "pilot" | "driver" | "stationary_node";
        positionSource?: "cellular" | "mesh" | "other";
        aircraftType?: "hang_glider" | "paraglider" | "sailplane";
      };
      layers.push(
        new IconLayer({
          id: `live-pilot-rings-${mode}`,
          data: liveMarkerData as LiveMarkerItem[],
          coordinateSystem: COORDINATE_SYSTEM.LNGLAT,
          billboard: true,
          getPosition: (item: LiveMarkerItem) => item.position,
          getIcon: (item: LiveMarkerItem) => {
            const source = item.positionSource ?? "other";
            return {
              url: RING_ICON_DATA_URIS[source],
              width: 48,
              height: 48,
              mask: true,
            };
          },
          getColor: (item: LiveMarkerItem) => [...item.color, 255],
          getSize: Math.round(28 * liveMarkerScale),
          sizeUnits: "pixels",
          sizeMinPixels: Math.round(20 * liveMarkerScale),
          pickable: false,
          parameters: {
            depthTest: false,
          },
        }),
      );
      layers.push(
        new IconLayer({
          id: `live-pilot-role-icons-${mode}`,
          data: liveMarkerData as LiveMarkerItem[],
          coordinateSystem: COORDINATE_SYSTEM.LNGLAT,
          billboard: true,
          getPosition: (item: LiveMarkerItem) => item.position,
          getIcon: (item: LiveMarkerItem) => {
            const iconKey = resolveLiveMapIconKey(item.profileType, item.aircraftType);
            return {
              url: ROLE_ICON_DATA_URIS[iconKey],
              width: 48,
              height: 48,
              mask: true,
            };
          },
          getColor: (item: LiveMarkerItem) => [...item.color, 255],
          getSize: Math.round(18 * liveMarkerScale),
          sizeUnits: "pixels",
          sizeMinPixels: Math.round(12 * liveMarkerScale),
          pickable: false,
          parameters: {
            depthTest: false,
          },
        }),
      );
    }
    if (labelData.length) {
      layers.push(
        new TextLayer({
          id: `pilot-name-labels-${mode}`,
          data: labelData,
          coordinateSystem: COORDINATE_SYSTEM.LNGLAT,
          billboard: true,
          getPosition: (item: { position: [number, number, number] }) => item.position,
          getText: (item: { nameLabel: string }) => item.nameLabel,
          getColor: (item: { color: [number, number, number] }) => [...item.color, 255],
          getSize: (item: { highlighted?: boolean }) => (item.highlighted ? 14 : 12),
          sizeUnits: "pixels",
          sizeMinPixels: 12,
          getPixelOffset: mode === "live" ? [0, -30] : [0, -16],
          getTextAnchor: "middle",
          getAlignmentBaseline: "bottom",
          characterSet: "auto",
          fontFamily: "Segoe UI, Arial, sans-serif",
          fontWeight: 700,
          outlineWidth: 2,
          outlineColor: [255, 255, 255, 230],
          pickable: false,
          parameters: {
            depthTest: false,
          },
        }),
      );
      layers.push(
        new TextLayer({
          id: `pilot-altitude-labels-${mode}`,
          data: labelData.filter((item: { altitudeLabel?: string }) => Boolean(item.altitudeLabel)),
          coordinateSystem: COORDINATE_SYSTEM.LNGLAT,
          billboard: true,
          getPosition: (item: { position: [number, number, number] }) => item.position,
          getText: (item: { altitudeLabel: string }) => item.altitudeLabel,
          getColor: (item: { color: [number, number, number] }) => [...item.color, 255],
          getSize: (item: { highlighted?: boolean }) => (item.highlighted ? 11 : 10),
          sizeUnits: "pixels",
          sizeMinPixels: 10,
          getPixelOffset: mode === "live" ? [0, -16] : [0, -3],
          getTextAnchor: "middle",
          getAlignmentBaseline: "bottom",
          characterSet: "auto",
          fontFamily: "Segoe UI, Arial, sans-serif",
          fontWeight: 400,
          outlineWidth: 2,
          outlineColor: [255, 255, 255, 230],
          pickable: false,
          parameters: {
            depthTest: false,
          },
        }),
      );
    }
    return layers;
  }, [cylinderVolumes, displayTrack, fullTrackPathData, livePilotLabelData, livePilotMarkerData, maxScoredTrackAltitudeM, mode, replayPilotLabelData, scoredTrackDeckPointData, visibleTrackLengths]);
  const fitBounds = resolvedFitTarget.coordinates;
  const fitGeometrySignature = resolvedFitTarget.signature;
  const fitTargetKind = resolvedFitTarget.kind;
  const fitKeyValue = String(fitKey ?? "");
  const fitOnceKeyValue = String(fitOnceKey ?? "");

  useEffect(() => {
    turnpointsRef.current = effectiveTurnpoints;
  }, [effectiveTurnpoints]);

  useEffect(() => {
    taskPointsRef.current = effectiveTaskRoutePoints;
  }, [effectiveTaskRoutePoints]);

  useEffect(() => {
    optimizedRouteRef.current = effectiveOptimizedRoute;
  }, [effectiveOptimizedRoute]);

  useEffect(() => {
    trackRef.current = effectiveTrack;
  }, [effectiveTrack]);

  useEffect(() => {
    clickToAddTurnpointEnabledRef.current = oc?.click_to_add_turnpoint !== false;
  }, [oc?.click_to_add_turnpoint]);

  useEffect(() => {
    replayIndexRef.current = replayIndex;
  }, [replayIndex]);

  useEffect(() => {
    editableRef.current = editable;
    onSelectTurnpointRef.current = onSelectTurnpoint;
  }, [editable, onSelectTurnpoint]);

  useEffect(() => {
    viewStateKeyRef.current = viewStateKey;
  }, [viewStateKey]);

  useEffect(() => {
    if (!isFullscreen || !hasTaskEditorOverlay) {
      setIsTaskEditorOverlayCollapsed(false);
    }
  }, [isFullscreen, hasTaskEditorOverlay]);

  useEffect(() => {
    if (!isFullscreen || !fullscreenSidebar) {
      setIsFullscreenSidebarCollapsed(false);
    }
  }, [isFullscreen, fullscreenSidebar]);

  useEffect(() => {
    const nextReplayIndex = replayTotal > 0 ? replayTotal - 1 : 0;
    setIsReplaying(false);
    setReplayHasInteracted(false);
    setReplayIndex(nextReplayIndex);
    replayIndexRef.current = nextReplayIndex;
    replayClockRef.current = replayTotal > 0 ? replayTimeline[nextReplayIndex] ?? null : null;
    lastFrameTimeRef.current = null;
    if (animationFrameRef.current !== null) {
      window.cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
  }, [effectiveTrack, replayTimeline, replayTotal]);

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
        replayClockRef.current = replayTimeline[currentIndex];
      }
      replayClockRef.current += deltaMs * replaySpeed;
      const targetFlightTime = replayClockRef.current;
      let nextIndex = currentIndex;
      while (nextIndex + 1 < replayTotal && replayTimeline[nextIndex + 1] <= targetFlightTime) {
        nextIndex += 1;
      }
      if (nextIndex !== currentIndex) {
        replayIndexRef.current = nextIndex;
        setReplayIndex(nextIndex);
      }
      if (nextIndex >= replayTotal - 1) {
        replayClockRef.current = replayTimeline[replayTotal - 1] ?? replayClockRef.current;
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
  }, [isReplaying, replaySpeed, replayTimeline, replayTotal]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return;
    }
    const container = containerRef.current;
    const shell = shellRef.current;
    try {
      const persistedViewState = viewStateKey != null ? persistedViewStateByKey.get(String(viewStateKey)) : null;
      if (preserveViewStateOnRemount && persistedViewState) {
        fitGeometrySignatureRef.current = fitGeometrySignature;
        fitKeyRef.current = String(fitKey ?? "");
        fitTargetKindRef.current = fitTargetKind;
        manualViewChangedRef.current = true;
      }
      const map = new maplibregl.Map({
        container,
        style: createBasemapStyle(basemapMode) as never,
        ...(persistedViewState
          ? {
              center: persistedViewState.center,
              zoom: persistedViewState.zoom,
              bearing: persistedViewState.bearing,
              pitch: persistedViewState.pitch,
            }
          : buildBoundsOptions(fitBounds, USA_FIT_BOUNDS, fitBounds.length ? 72 : 32, fitBounds.length ? fitMaxZoom : 5)),
        maxPitch: maxMapPitch,
        attributionControl: false,
      });
      const navigationControl = new maplibregl.NavigationControl({ showCompass: true });
      map.addControl(navigationControl, "top-right");
      const deckOverlay = new MapboxOverlay({ interleaved: false, layers: [] });
      map.addControl(deckOverlay);
      deckOverlayRef.current = deckOverlay;
      let compassButton: HTMLButtonElement | null = null;
      let handleCompassClick: ((event: Event) => void) | null = null;
      const syncPerspectiveMode = () => {
        setIsPerspective3D(map.getPitch() > 0.5);
      };
      map.on("styledata", () => {
        map.resize();
      });
      map.on("pitch", syncPerspectiveMode);
      map.on("moveend", () => {
        if (programmaticCameraMoveRef.current) {
          programmaticCameraMoveRef.current = false;
        }
        const persistedViewStateKey = viewStateKeyRef.current;
        if (persistedViewStateKey != null) {
          const center = map.getCenter();
          persistedViewStateByKey.set(String(persistedViewStateKey), {
            center: [center.lng, center.lat],
            zoom: map.getZoom(),
            bearing: map.getBearing(),
            pitch: map.getPitch(),
          });
        }
        syncPerspectiveMode();
      });
      const markManualInteraction = () => {
        if (!programmaticCameraMoveRef.current) {
          manualViewChangedRef.current = true;
        }
      };
      map.on("dragstart", markManualInteraction);
      map.on("zoomstart", markManualInteraction);
      map.on("rotatestart", markManualInteraction);
      map.on("pitchstart", markManualInteraction);
      map.on("click", (event) => {
        if (!editableRef.current || !onSelectTurnpointRef.current || !clickToAddTurnpointEnabledRef.current) {
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
              programmaticCameraMoveRef.current = true;
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
        window.setTimeout(() => map.resize(), 150);
      };
      document.addEventListener("fullscreenchange", handleFullscreenChange);
      document.addEventListener("webkitfullscreenchange", handleFullscreenChange as EventListener);
      window.setTimeout(() => map.resize(), 0);
      mapRef.current = map;
      setMapReadyNonce((value) => value + 1);
      return () => {
        resizeObserver.disconnect();
        if (compassButton && handleCompassClick) {
          compassButton.removeEventListener("click", handleCompassClick);
        }
        document.removeEventListener("fullscreenchange", handleFullscreenChange);
        document.removeEventListener("webkitfullscreenchange", handleFullscreenChange as EventListener);
        map.off("dragstart", markManualInteraction);
        map.off("zoomstart", markManualInteraction);
        map.off("rotatestart", markManualInteraction);
        map.off("pitchstart", markManualInteraction);
        map.off("pitch", syncPerspectiveMode);
        if (deckOverlayRef.current) {
          map.removeControl(deckOverlayRef.current);
          deckOverlayRef.current = null;
        }
        if (fullscreenControlRef.current) {
          map.removeControl(fullscreenControlRef.current);
          fullscreenControlRef.current = null;
        }
        scoredPointPopupRef.current?.remove();
        scoredPointPopupRef.current = null;
        map.remove();
        mapRef.current = null;
      };
    } catch (error) {
      console.error("Map failed to initialize.", error);
      return;
    }
    // Keep the base map instance stable; geometry changes are handled by the source/layer sync effects below.
    }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    const enabled = oc?.fullscreen_toggle !== false;
    if (enabled && !fullscreenControlRef.current) {
      const control = new maplibregl.FullscreenControl({ container: shellRef.current ?? undefined });
      map.addControl(control, "top-right");
      fullscreenControlRef.current = control;
    } else if (!enabled && fullscreenControlRef.current) {
      map.removeControl(fullscreenControlRef.current);
      fullscreenControlRef.current = null;
    }
  }, [oc?.fullscreen_toggle]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    map.setMaxPitch(maxMapPitch);
    if (map.getPitch() > maxMapPitch) {
      programmaticCameraMoveRef.current = true;
      map.easeTo({ pitch: maxMapPitch, duration: 200 });
    }
  }, [maxMapPitch]);

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
    const map = mapRef.current;
    if (!map) {
      return;
    }
    const updateScaleBar = () => {
      setScaleBar(computeScaleBar(map, units.distance));
    };
    updateScaleBar();
    map.on("move", updateScaleBar);
    map.on("resize", updateScaleBar);
    return () => {
      map.off("move", updateScaleBar);
      map.off("resize", updateScaleBar);
    };
  }, [mapReadyNonce, units.distance]);

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
              exaggeration: TERRAIN_EXAGGERATION * Math.max(1, altitudeMultiplier),
            }
          : null,
      );
    };
    if (map.isStyleLoaded()) {
      applyTerrain();
    } else {
      map.once("styledata", applyTerrain);
    }
  }, [altitudeMultiplier, isPerspective3D, styleGeneration]);

  const applyFitBounds = useCallback((map: maplibregl.Map, animate = false) => {
    const ms = animate ? 800 : 0;
    if (fitBounds.length === 0) {
      programmaticCameraMoveRef.current = true;
      map.fitBounds(USA_FIT_BOUNDS, { padding: 32, maxZoom: 5, duration: 0 });
      return;
    }
    programmaticCameraMoveRef.current = true;
    fitMapToCoordinates(map, fitBounds, { padding: 72, maxZoom: fitMaxZoom, duration: ms });
  }, [fitBounds, fitMaxZoom]);

  // Sync turnpoint data to map
  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    const sync = () => {
      ensureGeoJsonSource(map, "turnpoints", turnpointData as never);
      ensureMapLayers(map, isPerspective3D);
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
      ensureMapLayers(map, isPerspective3D);
    };
    if (map.isStyleLoaded()) {
      sync();
    } else {
      map.once("styledata", sync);
    }
  }, [airspaceData, airspaceLabelData, isPerspective3D, styleGeneration]);

  // Sync live position data to map
  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    const sync = () => {
      ensureGeoJsonSource(map, "live-positions", livePositionData as never);
      ensureMapLayers(map, isPerspective3D);
    };
    if (map.isStyleLoaded()) {
      sync();
    } else {
      map.once("styledata", sync);
    }
  }, [livePositionData, styleGeneration]);

  // Sync task route data to map
  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    const sync = () => {
      ensureGeoJsonSource(map, "task-points", taskPointData as never);
      ensureGeoJsonSource(map, "task-route", routeData as never);
      ensureGeoJsonSource(map, "task-route-arrows", routeArrowData as never);
      ensureGeoJsonSource(map, "optimized-route", optimizedRouteData as never);
      ensureGeoJsonSource(map, "optimized-route-points", optimizedRoutePointData as never);
      ensureGeoJsonSource(map, "optimized-leg-labels", legLabelData as never);
      ensureGeoJsonSource(map, "task-cylinders", cylinderData as never);
      ensureMapLayers(map, isPerspective3D);
      map.triggerRepaint();
      renderedTaskGeometrySignatureRef.current = taskGeometrySignature;
    };
    try {
      sync();
    } catch (error) {
      if (!map.isStyleLoaded()) {
        map.once("styledata", sync);
        return;
      }
      console.error("Unable to sync task geometry to the map.", error);
    }
  }, [routeData, routeArrowData, cylinderData, taskPointData, optimizedRouteData, optimizedRoutePointData, legLabelData, styleGeneration, taskGeometrySignature]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !fitOnceKeyValue || fitOnceKeyValue === fitOnceKeyRef.current) {
      return;
    }
    fitOnceKeyRef.current = fitOnceKeyValue;
    if (gpsFollowingRef.current) {
      return;
    }
    manualViewChangedRef.current = false;
    const fitted = fitToCurrentTarget(map, 600, true);
    if (!fitted) {
      fitOnceKeyRef.current = "";
    }
  }, [fitOnceKeyValue, fitToCurrentTarget, gpsFollowing, mapReadyNonce]);

  // Sync track data to map
  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    const sync = () => {
      ensureGeoJsonSource(map, "track", (displayTrack ?? { type: "FeatureCollection", features: [] }) as never);
      ensureGeoJsonSource(map, "replay-marker", replayMarkerData as never);
      ensureGeoJsonSource(map, "scored-track-points", scoredTrackPointData as never);
      ensureMapLayers(map, isPerspective3D);
    };
    if (map.isStyleLoaded()) {
      sync();
    } else {
      map.once("styledata", sync);
    }
  }, [displayTrack, replayMarkerData, scoredTrackPointData, isPerspective3D, styleGeneration]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    const layerId = "scored-track-points-layer";
    const showPopup = (event: maplibregl.MapLayerMouseEvent) => {
      const feature = event.features?.[0];
      if (!feature) {
        return;
      }
      const properties = feature.properties ?? {};
      const latitude = Number(properties.latitude);
      const longitude = Number(properties.longitude);
      const coordinateLabel = Number.isFinite(latitude) && Number.isFinite(longitude)
        ? `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`
        : "--";
      const trackTime = formatScoredTrackTimeLabel(String(properties.timestamp ?? ""));
      const scoredTimeRaw = String(properties.scored_timestamp ?? "");
      const scoredTime = scoredTimeRaw && scoredTimeRaw !== properties.timestamp
        ? formatScoredTrackTimeLabel(scoredTimeRaw)
        : "";
      const direction = String(properties.direction ?? "");
      const pointType = String(properties.point_type ?? "");
      const pointLabel = [pointType, direction].filter(Boolean).join(" / ");
      const html = `
        <div style="font: 12px/1.35 system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #0f172a; min-width: 190px;">
          <div style="font-weight: 700; margin-bottom: 4px;">${escapeHtml(properties.point_name)}</div>
          <div style="color: #475569; margin-bottom: 6px;">${escapeHtml(properties.pilot_name)}${pointLabel ? ` - ${escapeHtml(pointLabel)}` : ""}</div>
          <div><strong>Time:</strong> ${escapeHtml(trackTime)}</div>
          ${scoredTime ? `<div><strong>Start Gate:</strong> ${escapeHtml(scoredTime)}</div>` : ""}
          <div><strong>Altitude:</strong> ${escapeHtml(properties.altitude_label || "--")}</div>
          <div><strong>GPS:</strong> ${escapeHtml(coordinateLabel)}</div>
        </div>
      `;
      if (!scoredPointPopupRef.current) {
        scoredPointPopupRef.current = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12 });
      }
      map.getCanvas().style.cursor = "pointer";
      scoredPointPopupRef.current
        .setLngLat(event.lngLat)
        .setHTML(html)
        .addTo(map);
    };
    const hidePopup = () => {
      map.getCanvas().style.cursor = "";
      scoredPointPopupRef.current?.remove();
    };
    const attach = () => {
      if (!map.getLayer(layerId)) {
        return;
      }
      map.on("mousemove", layerId, showPopup);
      map.on("mouseleave", layerId, hidePopup);
    };
    if (map.isStyleLoaded()) {
      attach();
    } else {
      map.once("styledata", attach);
    }
    return () => {
      try {
        map.off("mousemove", layerId, showPopup);
        map.off("mouseleave", layerId, hidePopup);
      } catch {
        // The layer can disappear while switching base maps.
      }
      map.off("styledata", attach);
      hidePopup();
    };
  }, [scoredTrackPointData, styleGeneration]);

  // Fit map to data when signatures change
  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    const nextFitGeometrySignature = fitGeometrySignature;
    const nextFitKey = fitKeyValue;
    const nextFitTargetKind = fitTargetKind;
    const previousHighlightedTrackUploadId = previousHighlightedTrackUploadIdRef.current;
    const highlightSelectionChanged = previousHighlightedTrackUploadId !== effectiveHighlightedTrackUploadId;
    previousHighlightedTrackUploadIdRef.current = effectiveHighlightedTrackUploadId;
    const previousFitTargetKind = fitTargetKindRef.current;
    const fitKeyChanged = nextFitKey !== fitKeyRef.current;
    const geometryChanged = nextFitGeometrySignature !== fitGeometrySignatureRef.current;
    const shouldFitToTaskContext = fitKeyChanged;
    const shouldFitToTaskAfterFallback = nextFitTargetKind === "task" && previousFitTargetKind !== "task";
    const shouldFitToWaypointGeometry =
      nextFitTargetKind !== "task" &&
      geometryChanged &&
      !manualViewChangedRef.current;
    // When fitKey changes before new geometry arrives, mark a deferred fit
    // so we refit once the new task's data loads.
    const shouldFitDeferredTaskGeometry =
      fitPendingForGeometryRef.current &&
      nextFitTargetKind === "task" &&
      geometryChanged;
    if (fitKeyChanged) {
      fitPendingForGeometryRef.current = true;
    }
    if (gpsFollowingRef.current) {
      fitPendingForGeometryRef.current = false;
      fitGeometrySignatureRef.current = nextFitGeometrySignature;
      fitKeyRef.current = nextFitKey;
      fitTargetKindRef.current = nextFitTargetKind;
      return;
    }
    const highlightOnlySelectionChange =
      highlightSelectionChanged &&
      !fitKeyChanged &&
      !geometryChanged &&
      nextFitTargetKind === fitTargetKindRef.current;

    if (highlightOnlySelectionChange) {
      fitGeometrySignatureRef.current = nextFitGeometrySignature;
      fitKeyRef.current = nextFitKey;
      fitTargetKindRef.current = nextFitTargetKind;
      return;
    }

    if (shouldFitToTaskContext || shouldFitToTaskAfterFallback || shouldFitToWaypointGeometry || shouldFitDeferredTaskGeometry) {
      manualViewChangedRef.current = false;
      if (shouldFitDeferredTaskGeometry || shouldFitToTaskAfterFallback) {
        fitPendingForGeometryRef.current = false;
      }
      const doAnimate = shouldFitToTaskContext || shouldFitDeferredTaskGeometry;
      applyFitBounds(map, doAnimate);
    } else if (manualViewChangedRef.current) {
      fitGeometrySignatureRef.current = nextFitGeometrySignature;
      fitKeyRef.current = nextFitKey;
      fitTargetKindRef.current = nextFitTargetKind;
      return;
    }
    fitGeometrySignatureRef.current = nextFitGeometrySignature;
    fitKeyRef.current = nextFitKey;
    fitTargetKindRef.current = nextFitTargetKind;
  }, [applyFitBounds, effectiveHighlightedTrackUploadId, fitGeometrySignature, fitKeyValue, fitTargetKind, gpsFollowing, mapReadyNonce]);

  const replayVisible = !!effectiveTrack && replayTotal > 0 && oc?.replay_scrubber !== false;
  const replayStartLabel = replayVisible ? formatReplayTimeLabel(replayTimeline[0]) : "--:--";
  const replayEndLabel = replayVisible ? formatReplayTimeLabel(replayTimeline[replayTotal - 1]) : "--:--";
  const replayCurrentLabel = replayVisible ? formatReplayTimeLabel(replayTimeline[Math.min(replayIndex, replayTotal - 1)], true) : "--:--:--";
  const highlightedTrackSnapshot = useMemo<HighlightedTrackSnapshot | null>(() => {
    if (!effectiveTrack || effectiveHighlightedTrackUploadId == null) {
      return null;
    }
    const highlightedFeature = effectiveTrack.features.find((feature) => Number(feature.properties?.upload_id) === effectiveHighlightedTrackUploadId);
    if (!highlightedFeature || highlightedFeature.geometry.type !== "LineString" || !highlightedFeature.geometry.coordinates.length) {
      return null;
    }
    const timestamps = trackFeatureTimelines.find((feature) => feature.uploadId === effectiveHighlightedTrackUploadId)?.timestamps ?? [];
    const shouldUseReplayPosition = replayVisible && (isReplaying || replayHasInteracted);
    const coordinateIndex = timestamps.length
      ? (() => {
          if (!shouldUseReplayPosition) {
            return Math.min(highlightedFeature.geometry.coordinates.length - 1, timestamps.length - 1);
          }
          const replayTime = replayTimeline[Math.min(replayIndex, replayTotal - 1)];
          const index = findReplayCoordinateIndex(timestamps, replayTime);
          return Math.max(0, Math.min(index, highlightedFeature.geometry.coordinates.length - 1, timestamps.length - 1));
        })()
      : highlightedFeature.geometry.coordinates.length - 1;
    const coordinate = highlightedFeature.geometry.coordinates[Math.max(0, coordinateIndex)];
    if (!coordinate) {
      return null;
    }
    const telemetrySeries = smoothedTrackTelemetrySeries.find((series) => series.uploadId === effectiveHighlightedTrackUploadId);
    return {
      pilotName: String(highlightedFeature.properties?.pilot_name ?? "Pilot"),
      coordinate: [coordinate[0], coordinate[1]] as [number, number],
      altitudeM: telemetrySeries?.altitudeM[coordinateIndex] ?? (coordinate.length > 2 ? Math.round(coordinate[2] ?? 0) : null),
      speedKmh: telemetrySeries?.speedKmh[coordinateIndex] ?? null,
      // Vertical speed is derived from the altitude delta between the current replay point
      // and the immediately previous point divided by elapsed seconds; the smoothed display
      // keeps that raw per-point derivation intact and only averages the shown values.
      verticalSpeedMps: telemetrySeries?.verticalSpeedMps[coordinateIndex] ?? null,
      glideRatio: telemetrySeries?.glideRatio[coordinateIndex] ?? null,
      color: String(highlightedFeature.properties?.color ?? "#2563eb"),
    };
  }, [effectiveHighlightedTrackUploadId, effectiveTrack, isReplaying, replayHasInteracted, replayIndex, replayTimeline, replayTotal, replayVisible, smoothedTrackTelemetrySeries, trackFeatureTimelines]);
  const highlightedTrackSnapshotRef = useRef<HighlightedTrackSnapshot | null>(null);
  const telemetryThrottleMs = useMemo(
    () => (mode === "replay" && isReplaying ? replayTelemetryThrottleMs(replaySpeed) : 0),
    [isReplaying, mode, replaySpeed],
  );

  useEffect(() => {
    highlightedTrackSnapshotRef.current = highlightedTrackSnapshot;
  }, [highlightedTrackSnapshot]);

  useEffect(() => {
    if (telemetryThrottleMs <= 0) {
      setDisplayedHighlightedTrackSnapshot(highlightedTrackSnapshot);
      return;
    }
    setDisplayedHighlightedTrackSnapshot(highlightedTrackSnapshotRef.current);
    const intervalId = window.setInterval(() => {
      setDisplayedHighlightedTrackSnapshot(highlightedTrackSnapshotRef.current);
    }, telemetryThrottleMs);
    return () => window.clearInterval(intervalId);
  }, [effectiveHighlightedTrackUploadId, telemetryThrottleMs]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isPerspective3D) {
      return;
    }
    if (effectiveHighlightedTrackUploadId == null || !highlightedTrackSnapshot) {
      lastCenteredHighlightRef.current = null;
      return;
    }
    if (lastCenteredHighlightRef.current === effectiveHighlightedTrackUploadId) {
      return;
    }
    const currentZoom = map.getZoom();
    const currentPitch = map.getPitch();
    const currentBearing = map.getBearing();
    manualViewChangedRef.current = true;
    programmaticCameraMoveRef.current = true;
    map.easeTo({
      center: highlightedTrackSnapshot.coordinate,
      zoom: currentZoom,
      pitch: currentPitch,
      bearing: currentBearing,
      duration: 320,
      easing: (value) => 1 - Math.pow(1 - value, 3),
      essential: true,
    });
    lastCenteredHighlightRef.current = effectiveHighlightedTrackUploadId;
  }, [effectiveHighlightedTrackUploadId, highlightedTrackSnapshot, isPerspective3D]);

  // Fly to a specific position when the parent requests it (e.g. pilot row click).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !focusPosition) return;
    if (lastFocusPositionKeyRef.current === focusPosition.key) return;
    programmaticCameraMoveRef.current = true;
    map.easeTo({
      center: [focusPosition.lon, focusPosition.lat],
      zoom: Math.max(map.getZoom(), 14),
      duration: 600,
      easing: (t: number) => 1 - Math.pow(1 - t, 3),
    });
    lastFocusPositionKeyRef.current = focusPosition.key;
  }, [focusPosition]);

  const telemetryOverlay = displayedHighlightedTrackSnapshot ? (
    <div className="map-track-telemetry" aria-label="Highlighted pilot telemetry">
      <strong style={{ color: displayedHighlightedTrackSnapshot.color }}>{displayedHighlightedTrackSnapshot.pilotName}</strong>
      <div className="map-track-telemetry-grid">
        <span>Speed</span>
        <span>{displayedHighlightedTrackSnapshot.speedKmh != null ? formatSpeedLabel(displayedHighlightedTrackSnapshot.speedKmh, units.speed) : "--"}</span>
        <span>Altitude</span>
        <span>{displayedHighlightedTrackSnapshot.altitudeM != null ? formatAltitudeLabel(displayedHighlightedTrackSnapshot.altitudeM, units.altitude) : "--"}</span>
        <span>Vertical speed</span>
        <span>{displayedHighlightedTrackSnapshot.verticalSpeedMps != null ? formatVarioLabel(displayedHighlightedTrackSnapshot.verticalSpeedMps, units.vario) : "--"}</span>
        <span>L/D</span>
        <span>{displayedHighlightedTrackSnapshot.glideRatio != null ? formatGlideRatioLabel(displayedHighlightedTrackSnapshot.glideRatio) : "--"}</span>
      </div>
    </div>
  ) : null;

  const hasFullscreenTaskEditorOverlay = isFullscreen && hasTaskEditorOverlay;
  const taskEditorToggleLabel = isTaskEditorOverlayCollapsed ? "Expand task turnpoints overlay" : "Collapse task turnpoints overlay";
  const taskEditorOverlayToggleButton = hasFullscreenTaskEditorOverlay ? (
    <button
      type="button"
      className="map-task-editor-collapse-button"
      aria-label={taskEditorToggleLabel}
      aria-controls={taskEditorOverlayContentId}
      aria-expanded={!isTaskEditorOverlayCollapsed}
      title={taskEditorToggleLabel}
      onClick={() => setIsTaskEditorOverlayCollapsed((current) => !current)}
    >
      <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
        <rect x="4" y="5" width="16" height="14" rx="2" fill="none" stroke="currentColor" strokeWidth="2" />
        <path d="M10 5v14" fill="none" stroke="currentColor" strokeWidth="2" />
        <path
          d={isTaskEditorOverlayCollapsed ? "M13 9l4 3-4 3" : "M17 9l-4 3 4 3"}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  ) : null;
  const renderedTaskEditorOverlay =
    hasFullscreenTaskEditorOverlay && taskEditorOverlay
      ? typeof taskEditorOverlay === "function"
        ? taskEditorOverlay({
            collapsed: isTaskEditorOverlayCollapsed,
            contentId: taskEditorOverlayContentId,
            overlayId: taskEditorOverlayId,
            toggleButton: taskEditorOverlayToggleButton,
          })
        : (
          <div id={taskEditorOverlayId} className={`map-task-editor-fallback${isTaskEditorOverlayCollapsed ? " is-collapsed" : ""}`}>
            <div className="map-task-editor-fallback-actions">{taskEditorOverlayToggleButton}</div>
            <div id={taskEditorOverlayContentId} hidden={isTaskEditorOverlayCollapsed}>
              {taskEditorOverlay}
            </div>
          </div>
        )
      : null;

  const fullscreenCompositeOverlay = hasFullscreenTaskEditorOverlay ? (
    <div className={`map-fullscreen-overlay-group${isTaskEditorOverlayCollapsed ? " is-task-editor-collapsed" : ""}`}>
      {renderedTaskEditorOverlay ? (
        <div className="map-fullscreen-overlay-top">
          {renderedTaskEditorOverlay ? <div className="map-task-editor-overlay">{renderedTaskEditorOverlay}</div> : null}
        </div>
      ) : null}
      {telemetryOverlay}
    </div>
  ) : null;
  const hasFullscreenSidebar = isFullscreen && Boolean(fullscreenSidebar);
  const fullscreenSidebarUsesInlineToggle = typeof fullscreenSidebar === "function";
  const fullscreenSidebarToggleLabel = isFullscreenSidebarCollapsed
    ? `Show ${fullscreenSidebarLabel}`
    : `Hide ${fullscreenSidebarLabel}`;
  const fullscreenSidebarToggleButton = (
    <button
      type="button"
      className="map-fullscreen-live-sidebar-toggle"
      aria-label={fullscreenSidebarToggleLabel}
      aria-controls={fullscreenSidebarUsesInlineToggle && !isFullscreenSidebarCollapsed ? fullscreenSidebarContentId : fullscreenSidebarPanelContentId}
      aria-expanded={!isFullscreenSidebarCollapsed}
      title={fullscreenSidebarToggleLabel}
      onClick={() => setIsFullscreenSidebarCollapsed((current) => !current)}
    >
      <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
        <rect x="4" y="5" width="16" height="14" rx="2" fill="none" stroke="currentColor" strokeWidth="2" />
        <path d="M10 5v14" fill="none" stroke="currentColor" strokeWidth="2" />
        <path
          d={isFullscreenSidebarCollapsed ? "M13 9l4 3-4 3" : "M17 9l-4 3 4 3"}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  );
  const renderedFullscreenSidebar =
    fullscreenSidebarUsesInlineToggle && typeof fullscreenSidebar === "function"
      ? fullscreenSidebar({
          contentId: fullscreenSidebarContentId,
          toggleButton: fullscreenSidebarToggleButton,
        })
      : fullscreenSidebar;
  const fullscreenSidebarPanel = hasFullscreenSidebar ? (
    <aside
      className={`map-fullscreen-live-sidebar${fullscreenSidebarUsesInlineToggle ? " has-inline-toggle" : ""}${isFullscreenSidebarCollapsed ? " is-collapsed" : ""}`}
      aria-label={fullscreenSidebarLabel}
    >
      {!fullscreenSidebarUsesInlineToggle || isFullscreenSidebarCollapsed ? (
      <div className="map-fullscreen-live-sidebar-toolbar">
        {fullscreenSidebarToggleButton}
      </div>
      ) : null}
      <div
        id={fullscreenSidebarPanelContentId}
        className="map-fullscreen-live-sidebar-content"
        hidden={isFullscreenSidebarCollapsed}
      >
        {renderedFullscreenSidebar}
      </div>
    </aside>
  ) : null;
  const mapShellClassName = [
    "map-shell",
    isFullscreen ? "map-shell-fullscreen" : "",
    replayVisible && mode === "replay" ? "has-replay" : "",
    hasFullscreenSidebar ? "has-fullscreen-live-sidebar" : "",
    hasFullscreenSidebar && fullscreenSidebarUsesInlineToggle ? "has-inline-fullscreen-sidebar" : "",
    hasFullscreenSidebar && isFullscreenSidebarCollapsed ? "is-fullscreen-live-sidebar-collapsed" : "",
  ].filter(Boolean).join(" ");

  return (
    <div
      className={mapShellClassName}
      ref={shellRef}
      style={isFullscreen ? { width: "100vw", height: "100vh" } : undefined}
    >
      <div
        className="map-card"
        ref={containerRef}
        style={
          isFullscreen
            ? { height: "100vh", minHeight: "100vh" }
            : replayVisible && mode === "replay"
              ? { height: "calc(420px - 104px)", minHeight: "calc(420px - 104px)" }
              : undefined
        }
      />
      {fullscreenSidebarPanel}
      <div className={isFullscreen ? "map-overlay-column map-fullscreen-sidebar" : "map-overlay-column"}>
        {fullscreenCompositeOverlay ?? (
          <>
            {telemetryOverlay}
          </>
        )}
      </div>
      <div className="map-control-stack">
        {oc?.["2d_3d_toggle"] !== false ? (
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
              programmaticCameraMoveRef.current = true;
              map.easeTo({
                pitch: nextIs3D ? maxMapPitch : 0,
                duration: 300,
              });
              setIsPerspective3D(nextIs3D);
            }}
        >
          {isPerspective3D ? "3D" : "2D"}
        </button>
        ) : null}
        {showGpsButton && oc?.gps_button !== false && typeof navigator !== "undefined" && "geolocation" in navigator ? (
          <button
            type="button"
            className={`map-control-button map-control-mode-button${gpsFollowing ? " map-control-gps-active" : ""}`}
            aria-label={gpsFollowing ? "Back to event" : "Center on my location"}
            title={gpsFollowing ? "Back to event" : "My location"}
            onClick={handleGpsToggle}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
            </svg>
          </button>
        ) : null}
      </div>
      <div className="map-picker-stack">
        {isPerspective3D && oc?.altitude_slider !== false ? (
          <label className="map-style-picker">
            <span>Altitude</span>
            <select value={String(altitudeMultiplier)} onChange={(event) => setAltitudeMultiplier(Number(event.target.value))}>
              {ALTITUDE_MULTIPLIER_OPTIONS.map((multiplier) => (
                <option key={multiplier} value={multiplier}>
                  {multiplier}x
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {scaleBar ? (
          <div className="map-scale-bar" aria-label={`Map scale ${scaleBar.label}`}>
            <span className="map-scale-bar-label">{scaleBar.label}</span>
            <span className="map-scale-bar-line" style={{ width: scaleBar.width }} />
          </div>
        ) : null}
        {oc?.basemap_selector !== false ? (
        <label className="map-style-picker">
          <span>Map</span>
          <select value={basemapMode} onChange={(event) => setBasemapMode(event.target.value as BasemapMode)}>
            <option value="streets">Streets</option>
            <option value="satellite">Satellite</option>
            <option value="terrain">Terrain</option>
          </select>
        </label>
        ) : null}
      </div>
      {replayVisible && mode === "replay" ? (
        <div className="replay-bar">
          <div className="replay-bar-main">
            <div className="replay-scrubber-block">
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
                    replayClockRef.current = replayTimeline[nextIndex] ?? null;
                    setReplayIndex(nextIndex);
                  }}
                />
                <span className="replay-time-label">{replayEndLabel}</span>
              </div>
            </div>
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
                  replayClockRef.current = replayTimeline[0] ?? null;
                  lastFrameTimeRef.current = null;
                }}
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                  <rect x="2" y="2" width="2" height="10" fill="currentColor" />
                  <path d="M11 2.5V11.5L5 7L11 2.5Z" fill="currentColor" />
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
                    replayClockRef.current = replayTimeline[0] ?? null;
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
              {oc?.replay_speed !== false ? (
                <label className="replay-speed-select">
                  <select aria-label="Replay speed" value={String(replaySpeed)} onChange={(event) => setReplaySpeed(Number(event.target.value))}>
                    {REPLAY_SPEEDS.map((speed) => (
                      <option key={speed} value={speed}>
                        {speed}x
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
});
