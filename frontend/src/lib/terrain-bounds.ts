export type TerrainBounds = [number, number, number, number];

type TrackPosition = [number, number] | [number, number, number];

type TerrainTrackCollection = {
  features: Array<{
    geometry: { type: string; coordinates: TrackPosition[] };
  }>;
} | null;

type TerrainTaskPoint = { latitude: number; longitude: number };
type TerrainLivePosition = { latitude: number; longitude: number };

const WEB_MERCATOR_MAX_LAT = 85.051129;
const TERRAIN_BOUNDS_PADDING_RATIO = 0.1;
const TERRAIN_BOUNDS_MIN_BUFFER_DEGREES = 0.02;
export const DEFAULT_TERRAIN_TILE_WARNING_THRESHOLD = 96;
export const TERRAIN_DEM_MAX_ZOOM = 15;

function finiteCoordinate(lon: number, lat: number) {
  return Number.isFinite(lon) && Number.isFinite(lat) && lon >= -180 && lon <= 180 && lat >= -90 && lat <= 90;
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function addCoordinate(bounds: { west: number; south: number; east: number; north: number } | null, lon: number, lat: number) {
  if (!finiteCoordinate(lon, lat)) {
    return bounds;
  }
  if (!bounds) {
    return { west: lon, south: lat, east: lon, north: lat };
  }
  bounds.west = Math.min(bounds.west, lon);
  bounds.south = Math.min(bounds.south, lat);
  bounds.east = Math.max(bounds.east, lon);
  bounds.north = Math.max(bounds.north, lat);
  return bounds;
}

export function padTerrainBounds(bounds: TerrainBounds): TerrainBounds {
  const [west, south, east, north] = bounds;
  const lonBuffer = Math.max((east - west) * TERRAIN_BOUNDS_PADDING_RATIO, TERRAIN_BOUNDS_MIN_BUFFER_DEGREES);
  const latBuffer = Math.max((north - south) * TERRAIN_BOUNDS_PADDING_RATIO, TERRAIN_BOUNDS_MIN_BUFFER_DEGREES);
  return [
    clamp(west - lonBuffer, -180, 180),
    clamp(south - latBuffer, -WEB_MERCATOR_MAX_LAT, WEB_MERCATOR_MAX_LAT),
    clamp(east + lonBuffer, -180, 180),
    clamp(north + latBuffer, -WEB_MERCATOR_MAX_LAT, WEB_MERCATOR_MAX_LAT),
  ];
}

export function collectTerrainBounds({
  track,
  taskPoints,
  optimizedRoute,
  livePositions,
}: {
  track: TerrainTrackCollection;
  taskPoints: TerrainTaskPoint[];
  optimizedRoute: [number, number][];
  livePositions: TerrainLivePosition[];
}): TerrainBounds | null {
  let bounds: { west: number; south: number; east: number; north: number } | null = null;
  for (const feature of track?.features ?? []) {
    if (feature.geometry.type !== "LineString") {
      continue;
    }
    for (const coordinate of feature.geometry.coordinates) {
      bounds = addCoordinate(bounds, coordinate[0], coordinate[1]);
    }
  }
  for (const point of taskPoints) {
    bounds = addCoordinate(bounds, point.longitude, point.latitude);
  }
  for (const coordinate of optimizedRoute) {
    bounds = addCoordinate(bounds, coordinate[0], coordinate[1]);
  }
  for (const position of livePositions) {
    bounds = addCoordinate(bounds, position.longitude, position.latitude);
  }
  return bounds ? padTerrainBounds([bounds.west, bounds.south, bounds.east, bounds.north]) : null;
}

function lonToTileX(lon: number, zoom: number) {
  return Math.floor(((lon + 180) / 360) * 2 ** zoom);
}

function latToTileY(lat: number, zoom: number) {
  const clampedLat = clamp(lat, -WEB_MERCATOR_MAX_LAT, WEB_MERCATOR_MAX_LAT);
  const rad = (clampedLat * Math.PI) / 180;
  return Math.floor(((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * 2 ** zoom);
}

export function intersectTerrainBounds(left: TerrainBounds | null, right: TerrainBounds | null): TerrainBounds | null {
  if (!left || !right) {
    return null;
  }
  const west = Math.max(left[0], right[0]);
  const south = Math.max(left[1], right[1]);
  const east = Math.min(left[2], right[2]);
  const north = Math.min(left[3], right[3]);
  return west <= east && south <= north ? [west, south, east, north] : null;
}

export function estimateTerrainTileCount(bounds: TerrainBounds | null, zoom: number) {
  if (!bounds) {
    return 0;
  }
  const tileZoom = clamp(Math.ceil(zoom), 0, TERRAIN_DEM_MAX_ZOOM);
  const maxTile = 2 ** tileZoom - 1;
  const westX = clamp(lonToTileX(bounds[0], tileZoom), 0, maxTile);
  const eastX = clamp(lonToTileX(bounds[2], tileZoom), 0, maxTile);
  const northY = clamp(latToTileY(bounds[3], tileZoom), 0, maxTile);
  const southY = clamp(latToTileY(bounds[1], tileZoom), 0, maxTile);
  return Math.max(0, eastX - westX + 1) * Math.max(0, southY - northY + 1);
}

export function terrainBoundsKey(bounds: TerrainBounds | null) {
  return bounds ? bounds.map((value) => value.toFixed(5)).join(",") : "global";
}
