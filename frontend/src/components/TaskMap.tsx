"use client";

import maplibregl, { GeoJSONSource } from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";

export type MapTurnpoint = { id: number; name: string; code: string | null; latitude: number; longitude: number };
export type MapTaskPoint = { position: number; point_type: string; radius_m: number; name: string; latitude: number; longitude: number };
export type TrackCollection = { type: "FeatureCollection"; features: Array<{ type: "Feature"; properties: Record<string, unknown>; geometry: { type: string; coordinates: number[][] } }> };
type BasemapMode = "streets" | "satellite" | "terrain";

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

function ensureMapLayers(map: maplibregl.Map) {
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
    map.addLayer({ id: "track-layer", type: "line", source: "track", paint: { "line-color": "#ca8a04", "line-width": 3 } });
  }
}

function fitToData(map: maplibregl.Map, turnpoints: MapTurnpoint[], taskPoints: MapTaskPoint[], track: TrackCollection | null) {
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
  if (track) {
    for (const feature of track.features) {
      if (feature.geometry.type !== "LineString") {
        continue;
      }
      for (const coordinate of feature.geometry.coordinates) {
        bounds.extend(coordinate as [number, number]);
        hasData = true;
      }
    }
  }

  if (!hasData) {
    return;
  }
  map.fitBounds(bounds, { padding: 48, maxZoom: 11, duration: 0 });
}

export function TaskMap({ turnpoints, taskPoints, track, editable, onSelectTurnpoint }: { turnpoints: MapTurnpoint[]; taskPoints: MapTaskPoint[]; track: TrackCollection | null; editable: boolean; onSelectTurnpoint?: (turnpoint: MapTurnpoint) => void }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const turnpointsRef = useRef(turnpoints);
  const turnpointSignatureRef = useRef("");
  const trackSignatureRef = useRef("");
  const editableRef = useRef(editable);
  const onSelectTurnpointRef = useRef(onSelectTurnpoint);
  const [basemapMode, setBasemapMode] = useState<BasemapMode>("streets");

  const turnpointData = useMemo(() => ({ type: "FeatureCollection", features: turnpoints.map((turnpoint) => ({ type: "Feature", properties: { id: turnpoint.id, name: turnpoint.name, code: turnpoint.code ?? "" }, geometry: { type: "Point", coordinates: [turnpoint.longitude, turnpoint.latitude] } })) }), [turnpoints]);
  const taskPointData = useMemo(() => ({ type: "FeatureCollection", features: taskPoints.map((point) => ({ type: "Feature", properties: { name: point.name, point_type: point.point_type }, geometry: { type: "Point", coordinates: [point.longitude, point.latitude] } })) }), [taskPoints]);
  const routeData = useMemo(() => ({ type: "FeatureCollection", features: taskPoints.length > 1 ? [{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: taskPoints.map((point) => [point.longitude, point.latitude]) } }] : [] }), [taskPoints]);
  const cylinderData = useMemo(() => ({ type: "FeatureCollection", features: taskPoints.map(buildCircle) }), [taskPoints]);

  useEffect(() => {
    turnpointsRef.current = turnpoints;
  }, [turnpoints]);

  useEffect(() => {
    editableRef.current = editable;
    onSelectTurnpointRef.current = onSelectTurnpoint;
  }, [editable, onSelectTurnpoint]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return;
    }
    const container = containerRef.current;
    try {
      const map = new maplibregl.Map({
        container,
        style: createBasemapStyle(basemapMode) as never,
        center: [-118.18, 36.73],
        zoom: 9,
        attributionControl: false,
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      map.addControl(new maplibregl.FullscreenControl(), "top-right");
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
      window.setTimeout(() => map.resize(), 0);
      mapRef.current = map;
      return () => {
        resizeObserver.disconnect();
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
    const nextTrackSignature = track ? `${track.features.length}:${JSON.stringify(track.features[0]?.geometry?.coordinates?.[0] ?? [])}` : "";
    const shouldFitToTurnpoints = nextTurnpointSignature !== turnpointSignatureRef.current;
    const shouldFitToTrack = nextTrackSignature !== trackSignatureRef.current;

    const syncData = () => {
      ensureGeoJsonSource(map, "turnpoints", turnpointData as never);
      ensureGeoJsonSource(map, "task-points", taskPointData as never);
      ensureGeoJsonSource(map, "task-route", routeData as never);
      ensureGeoJsonSource(map, "task-cylinders", cylinderData as never);
      ensureGeoJsonSource(map, "track", (track ?? { type: "FeatureCollection", features: [] }) as never);
      ensureMapLayers(map);
      map.resize();
      if (shouldFitToTurnpoints || shouldFitToTrack) {
        fitToData(map, turnpoints, taskPoints, track);
      }
      window.setTimeout(() => {
        map.resize();
        if (shouldFitToTurnpoints || shouldFitToTrack) {
          fitToData(map, turnpoints, taskPoints, track);
        }
      }, 100);
      turnpointSignatureRef.current = nextTurnpointSignature;
      trackSignatureRef.current = nextTrackSignature;
    };
    if (map.isStyleLoaded()) {
      syncData();
    } else {
      map.once("styledata", syncData);
    }
  }, [basemapMode, turnpointData, taskPointData, routeData, cylinderData, track, turnpoints, taskPoints]);

  return (
    <div className="map-shell">
      <div className="map-card" ref={containerRef} />
      <label className="map-style-picker">
        <span>Map</span>
        <select value={basemapMode} onChange={(event) => setBasemapMode(event.target.value as BasemapMode)}>
          <option value="streets">Streets</option>
          <option value="satellite">Satellite</option>
          <option value="terrain">Terrain</option>
        </select>
      </label>
    </div>
  );
}
