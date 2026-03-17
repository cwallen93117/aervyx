"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import maplibregl, { GeoJSONSource } from "maplibre-gl";
import { useEffect, useMemo, useRef } from "react";

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

export function TaskMap({ turnpoints, taskPoints, track, editable, onAddPoint }: { turnpoints: MapTurnpoint[]; taskPoints: MapTaskPoint[]; track: TrackCollection | null; editable: boolean; onAddPoint?: (longitude: number, latitude: number) => void }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  const turnpointData = useMemo(() => ({ type: "FeatureCollection", features: turnpoints.map((turnpoint) => ({ type: "Feature", properties: { name: turnpoint.name, code: turnpoint.code ?? "" }, geometry: { type: "Point", coordinates: [turnpoint.longitude, turnpoint.latitude] } })) }), [turnpoints]);
  const taskPointData = useMemo(() => ({ type: "FeatureCollection", features: taskPoints.map((point) => ({ type: "Feature", properties: { name: point.name, point_type: point.point_type }, geometry: { type: "Point", coordinates: [point.longitude, point.latitude] } })) }), [taskPoints]);
  const routeData = useMemo(() => ({ type: "FeatureCollection", features: taskPoints.length > 1 ? [{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: taskPoints.map((point) => [point.longitude, point.latitude]) } }] : [] }), [taskPoints]);
  const cylinderData = useMemo(() => ({ type: "FeatureCollection", features: taskPoints.map(buildCircle) }), [taskPoints]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return;
    }
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "OpenStreetMap contributors" },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      } as never,
      center: [-118.18, 36.73],
      zoom: 9,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.on("click", (event) => {
      if (editable && onAddPoint) {
        onAddPoint(event.lngLat.lng, event.lngLat.lat);
      }
    });
    mapRef.current = map;
    return () => map.remove();
  }, [editable, onAddPoint]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    const syncSource = (id: string, data: Record<string, unknown>) => {
      const source = map.getSource(id) as GeoJSONSource | undefined;
      if (source) {
        source.setData(data as never);
      } else {
        map.addSource(id, { type: "geojson", data: data as never });
      }
    };
    const ensureLayers = () => {
      syncSource("turnpoints", turnpointData as never);
      syncSource("task-points", taskPointData as never);
      syncSource("task-route", routeData as never);
      syncSource("task-cylinders", cylinderData as never);
      syncSource("track", (track ?? { type: "FeatureCollection", features: [] }) as never);
      if (!map.getLayer("turnpoints-layer")) {
        map.addLayer({ id: "turnpoints-layer", type: "circle", source: "turnpoints", paint: { "circle-radius": 5, "circle-color": "#0f766e", "circle-stroke-width": 1, "circle-stroke-color": "#ffffff" } });
        map.addLayer({ id: "task-cylinders-fill", type: "fill", source: "task-cylinders", paint: { "fill-color": "#ef4444", "fill-opacity": 0.12 } });
        map.addLayer({ id: "task-cylinders-outline", type: "line", source: "task-cylinders", paint: { "line-color": "#ef4444", "line-width": 2 } });
        map.addLayer({ id: "task-route-layer", type: "line", source: "task-route", paint: { "line-color": "#1d4ed8", "line-width": 3 } });
        map.addLayer({ id: "task-points-layer", type: "circle", source: "task-points", paint: { "circle-radius": 6, "circle-color": "#1d4ed8", "circle-stroke-width": 1, "circle-stroke-color": "#ffffff" } });
        map.addLayer({ id: "track-layer", type: "line", source: "track", paint: { "line-color": "#ca8a04", "line-width": 3 } });
      }
    };
    if (map.isStyleLoaded()) {
      ensureLayers();
    } else {
      map.once("load", ensureLayers);
    }
  }, [turnpointData, taskPointData, routeData, cylinderData, track]);

  return <div className="map-card" ref={containerRef} />;
}