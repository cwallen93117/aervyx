"use client";

import maplibregl, { GeoJSONSource } from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";

export type MapTurnpoint = { id: number; name: string; code: string | null; latitude: number; longitude: number };
export type MapTaskPoint = { position: number; point_type: string; radius_m: number; name: string; latitude: number; longitude: number };
export type TrackCollection = { type: "FeatureCollection"; features: Array<{ type: "Feature"; properties: Record<string, unknown>; geometry: { type: string; coordinates: number[][] } }> };

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
    map.addLayer({ id: "task-cylinders-fill", type: "fill", source: "task-cylinders", paint: { "fill-color": "#ef4444", "fill-opacity": 0.12 } });
  }
  if (!map.getLayer("task-cylinders-outline")) {
    map.addLayer({ id: "task-cylinders-outline", type: "line", source: "task-cylinders", paint: { "line-color": "#ef4444", "line-width": 2 } });
  }
  if (!map.getLayer("task-route-layer")) {
    map.addLayer({ id: "task-route-layer", type: "line", source: "task-route", paint: { "line-color": "#1d4ed8", "line-width": 3 } });
  }
  if (!map.getLayer("task-points-layer")) {
    map.addLayer({ id: "task-points-layer", type: "circle", source: "task-points", paint: { "circle-radius": 6, "circle-color": "#1d4ed8", "circle-stroke-width": 1, "circle-stroke-color": "#ffffff" } });
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

export function TaskMap({ turnpoints, taskPoints, track, editable, onAddPoint }: { turnpoints: MapTurnpoint[]; taskPoints: MapTaskPoint[]; track: TrackCollection | null; editable: boolean; onAddPoint?: (longitude: number, latitude: number) => void }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const editableRef = useRef(editable);
  const onAddPointRef = useRef(onAddPoint);
  const [mapNotice, setMapNotice] = useState<string | null>(null);
  const [mapReady, setMapReady] = useState(false);

  const turnpointData = useMemo(() => ({ type: "FeatureCollection", features: turnpoints.map((turnpoint) => ({ type: "Feature", properties: { name: turnpoint.name, code: turnpoint.code ?? "" }, geometry: { type: "Point", coordinates: [turnpoint.longitude, turnpoint.latitude] } })) }), [turnpoints]);
  const taskPointData = useMemo(() => ({ type: "FeatureCollection", features: taskPoints.map((point) => ({ type: "Feature", properties: { name: point.name, point_type: point.point_type }, geometry: { type: "Point", coordinates: [point.longitude, point.latitude] } })) }), [taskPoints]);
  const routeData = useMemo(() => ({ type: "FeatureCollection", features: taskPoints.length > 1 ? [{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: taskPoints.map((point) => [point.longitude, point.latitude]) } }] : [] }), [taskPoints]);
  const cylinderData = useMemo(() => ({ type: "FeatureCollection", features: taskPoints.map(buildCircle) }), [taskPoints]);

  useEffect(() => {
    editableRef.current = editable;
    onAddPointRef.current = onAddPoint;
  }, [editable, onAddPoint]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return;
    }
    const container = containerRef.current;
    try {
      const map = new maplibregl.Map({
        container,
        style: {
          version: 8,
          sources: {
            osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "OpenStreetMap contributors" },
          },
          layers: [
            { id: "map-background", type: "background", paint: { "background-color": "#e7eef5" } },
            { id: "osm", type: "raster", source: "osm" },
          ],
        } as never,
        center: [-118.18, 36.73],
        zoom: 9,
      });
      setMapReady(true);
      setMapNotice("Basemap loading...");
      map.addControl(new maplibregl.NavigationControl(), "top-right");
      map.on("styledata", () => {
        setMapNotice(null);
        map.resize();
        fitToData(map, turnpoints, taskPoints, track);
        window.setTimeout(() => {
          map.resize();
          fitToData(map, turnpoints, taskPoints, track);
        }, 150);
      });
      map.on("error", (event) => {
        const sourceId = "sourceId" in event ? event.sourceId : undefined;
        if (sourceId === "osm") {
          setMapNotice("Basemap tiles are unavailable right now, but your turnpoints and task overlays should still appear.");
        }
      });
      map.on("click", (event) => {
        if (editableRef.current && onAddPointRef.current) {
          onAddPointRef.current(event.lngLat.lng, event.lngLat.lat);
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
        setMapReady(false);
      };
    } catch (error) {
      setMapNotice(error instanceof Error ? `Map failed to initialize: ${error.message}` : "Map failed to initialize.");
      setMapReady(false);
      return;
    }
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    const syncData = () => {
      ensureGeoJsonSource(map, "turnpoints", turnpointData as never);
      ensureGeoJsonSource(map, "task-points", taskPointData as never);
      ensureGeoJsonSource(map, "task-route", routeData as never);
      ensureGeoJsonSource(map, "task-cylinders", cylinderData as never);
      ensureGeoJsonSource(map, "track", (track ?? { type: "FeatureCollection", features: [] }) as never);
      ensureMapLayers(map);
      fitToData(map, turnpoints, taskPoints, track);
      map.resize();
      window.setTimeout(() => {
        map.resize();
        fitToData(map, turnpoints, taskPoints, track);
      }, 100);
    };
    if (map.isStyleLoaded()) {
      syncData();
    } else {
      map.once("styledata", syncData);
    }
  }, [turnpointData, taskPointData, routeData, cylinderData, track, turnpoints, taskPoints]);

  return (
    <div className="map-shell">
      <div className="map-card" ref={containerRef} />
      <div className="map-toolbar">
        <button type="button" className="map-tool-button" onClick={() => mapRef.current?.zoomIn()} disabled={!mapRef.current && !mapReady}>+</button>
        <button type="button" className="map-tool-button" onClick={() => mapRef.current?.zoomOut()} disabled={!mapRef.current && !mapReady}>-</button>
        <button type="button" className="map-tool-button wide" onClick={() => { if (mapRef.current) fitToData(mapRef.current, turnpoints, taskPoints, track); }} disabled={!mapRef.current && !mapReady}>Fit to data</button>
      </div>
      <div className="map-badge">{mapReady ? `${turnpoints.length} turnpoints available` : "Loading map..."}</div>
      {mapNotice ? <div className="map-notice">{mapNotice}</div> : null}
    </div>
  );
}
