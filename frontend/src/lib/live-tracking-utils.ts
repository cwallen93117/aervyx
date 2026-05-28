import type { MapUnitPreferences, TrackCollection } from "../components/TaskMap";

export const TRACK_COLORS = ["#2563eb", "#dc2626", "#16a34a", "#7c3aed", "#d97706", "#0891b2", "#db2777", "#65a30d", "#0f766e", "#c2410c"];
const LIVE_TRACK_CELLULAR_PRIORITY_WINDOW_MS = 120_000;
const LIVE_TRACK_MAX_SPEED_KMH = 104.607;

export type ProfileType = "pilot" | "driver" | "stationary_node";
export type PositionSource = "cellular" | "mesh" | "other";

export type LivePositionRecord = {
  id: string;
  subject_key?: string | null;
  pilot_id: number | null;
  user_id?: number | null;
  pilot_name?: string | null;
  task_id: number | null;
  lat: number;
  lon: number;
  alt: number | null;
  speed: number | null;
  heading: number | null;
  accuracy: number | null;
  timestamp: string;
  source: string | null;
  device_id: string | null;
  battery_level: number | null;
  aircraft_icon: "hang_glider" | "paraglider" | "sailplane";
  profile_type?: ProfileType | null;
  position_source?: PositionSource | null;
  received_at?: string | null;
};

function resolveConfiguredBase(configured: string | undefined, fallback: string) {
  if (configured?.startsWith("/")) {
    return configured;
  }
  if (typeof window !== "undefined") {
    if (configured) {
      try {
        const parsed = new URL(configured);
        if (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1") {
          return `${window.location.protocol}//${window.location.hostname}:${parsed.port || "8000"}`;
        }
      } catch {
        return configured;
      }
      return configured;
    }
    return fallback;
  }
  return configured ?? fallback;
}

export function resolveApiBase() {
  return resolveConfiguredBase(process.env.NEXT_PUBLIC_API_BASE_URL?.trim(), "/backend");
}

export function resolveStreamApiBase() {
  const configured = process.env.NEXT_PUBLIC_STREAM_API_BASE_URL?.trim();
  if (configured) {
    return resolveConfiguredBase(configured, resolveApiBase());
  }
  if (typeof window !== "undefined") {
    if (window.location.hostname === "aervyx.net" || window.location.hostname === "www.aervyx.net") {
      return `${window.location.protocol}//api.aervyx.net`;
    }
    if (window.location.hostname === "staging.aervyx.net") {
      return `${window.location.protocol}//api-staging.aervyx.net`;
    }
  }
  return resolveApiBase();
}

export function formatRelativeTime(value: string | null | undefined) {
  if (!value) return "-";
  const parsed = new Date(value).getTime();
  if (!Number.isFinite(parsed)) return "-";
  const deltaSeconds = Math.max(0, Math.round((Date.now() - parsed) / 1000));
  if (deltaSeconds < 10) return "just now";
  if (deltaSeconds < 60) return `${deltaSeconds}s ago`;
  if (deltaSeconds < 3600) return `${Math.round(deltaSeconds / 60)}m ago`;
  return `${Math.round(deltaSeconds / 3600)}h ago`;
}

export function convertAltitude(altitudeM: number | null, unit: MapUnitPreferences["altitude"]) {
  if (altitudeM == null) return "-";
  if (unit === "ft") {
    return `${Math.round(altitudeM * 3.28084).toLocaleString()} ft`;
  }
  return `${Math.round(altitudeM).toLocaleString()} m`;
}

export function convertSpeed(speedKmh: number | null, unit: MapUnitPreferences["speed"]) {
  if (speedKmh == null) return "-";
  if (unit === "mph") {
    return `${(speedKmh * 0.621371).toFixed(1)} mph`;
  }
  return `${speedKmh.toFixed(1)} km/h`;
}

export function colorForPilot(pilotId: number | null, pilotIds: number[]): string {
  const normalizedId = pilotId ?? 0;
  const index = Math.max(0, pilotIds.indexOf(normalizedId));
  return TRACK_COLORS[index % TRACK_COLORS.length];
}

export function subjectKeyForPosition(position: LivePositionRecord): string {
  if (position.subject_key) return position.subject_key;
  if (position.pilot_id != null) return `pilot:${position.pilot_id}`;
  if (position.user_id != null) return `user:${position.user_id}`;
  if (position.device_id) return `device:${position.device_id}`;
  return `position:${position.id}`;
}

export function colorForSubject(subjectKey: string, subjectKeys: string[]): string {
  const index = Math.max(0, subjectKeys.indexOf(subjectKey));
  return TRACK_COLORS[index % TRACK_COLORS.length];
}

export function displayNameForSubject(position: LivePositionRecord, namesBySubject: Map<string, string>): string {
  const subjectKey = subjectKeyForPosition(position);
  if (namesBySubject.has(subjectKey)) {
    return namesBySubject.get(subjectKey) as string;
  }
  if (position.pilot_name) {
    return position.pilot_name;
  }
  if (position.profile_type === "driver") {
    return position.user_id != null ? `Driver ${position.user_id}` : "Driver";
  }
  if (position.pilot_id != null) {
    return `Pilot ${position.pilot_id}`;
  }
  return position.device_id ?? "Tracker";
}

function timestampMs(value: string | null | undefined): number {
  if (!value) return Number.NaN;
  return Date.parse(value);
}

function sortableMs(value: string | null | undefined, fallback: string | null | undefined): number {
  const parsed = timestampMs(value);
  if (Number.isFinite(parsed)) return parsed;
  const fallbackParsed = timestampMs(fallback);
  return Number.isFinite(fallbackParsed) ? fallbackParsed : 0;
}

function haversineMeters(left: LivePositionRecord, right: LivePositionRecord): number {
  const radiusM = 6371000;
  const leftLat = (left.lat * Math.PI) / 180;
  const rightLat = (right.lat * Math.PI) / 180;
  const deltaLat = ((right.lat - left.lat) * Math.PI) / 180;
  const deltaLon = ((right.lon - left.lon) * Math.PI) / 180;
  const a = Math.sin(deltaLat / 2) ** 2 + Math.cos(leftLat) * Math.cos(rightLat) * Math.sin(deltaLon / 2) ** 2;
  return 2 * radiusM * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function isCellularPosition(position: LivePositionRecord): boolean {
  return position.position_source === "cellular" || position.source === "app";
}

function isMeshPosition(position: LivePositionRecord): boolean {
  return position.position_source === "mesh" || position.source === "mesh_relay" || position.source === "mqtt_gateway";
}

function sourceBucketForLiveTrack(position: LivePositionRecord): PositionSource | "igc" {
  if (position.source === "igc") {
    return "igc";
  }
  if (isCellularPosition(position)) {
    return "cellular";
  }
  if (isMeshPosition(position)) {
    return "mesh";
  }
  return "other";
}

function shouldSplitLiveTrackSegment(previous: LivePositionRecord, next: LivePositionRecord): boolean {
  if (previous.source === "igc" || next.source === "igc") {
    return false;
  }
  const previousTimestamp = timestampMs(previous.timestamp);
  const nextTimestamp = timestampMs(next.timestamp);
  if (!Number.isFinite(previousTimestamp) || !Number.isFinite(nextTimestamp)) {
    return false;
  }
  const gapSeconds = (nextTimestamp - previousTimestamp) / 1000;
  if (gapSeconds <= 0) {
    return false;
  }
  const distanceMeters = haversineMeters(previous, next);
  const speedKmh = (distanceMeters / gapSeconds) * 3.6;
  return speedKmh > LIVE_TRACK_MAX_SPEED_KMH;
}

export function displayPositionsForLiveTrack(positions: LivePositionRecord[]): LivePositionRecord[] {
  const positionsBySource = new Map<string, Array<{ position: LivePositionRecord; index: number }>>();
  positions.forEach((position, index) => {
    const bucket = sourceBucketForLiveTrack(position);
    const sourcePositions = positionsBySource.get(bucket) ?? [];
    sourcePositions.push({ position, index });
    positionsBySource.set(bucket, sourcePositions);
  });

  const display: LivePositionRecord[] = [];
  for (const sourcePositions of positionsBySource.values()) {
    const byReceiveOrder = sourcePositions.sort((left, right) => {
      const leftReceived = sortableMs(left.position.received_at, left.position.timestamp);
      const rightReceived = sortableMs(right.position.received_at, right.position.timestamp);
      if (leftReceived !== rightReceived) {
        return leftReceived - rightReceived;
      }
      return left.index - right.index;
    });

    let latestTimestamp = Number.NEGATIVE_INFINITY;
    for (const { position } of byReceiveOrder) {
      const parsedTimestamp = timestampMs(position.timestamp);
      const nextTimestamp = Number.isFinite(parsedTimestamp) ? parsedTimestamp : latestTimestamp;
      if (nextTimestamp < latestTimestamp) {
        continue;
      }
      display.push(position);
      latestTimestamp = nextTimestamp;
    }
  }
  return display.sort((left, right) => {
    const leftTimestamp = sortableMs(left.timestamp, left.received_at);
    const rightTimestamp = sortableMs(right.timestamp, right.received_at);
    if (leftTimestamp !== rightTimestamp) {
      return leftTimestamp - rightTimestamp;
    }
    const leftReceived = sortableMs(left.received_at, left.timestamp);
    const rightReceived = sortableMs(right.received_at, right.timestamp);
    return leftReceived - rightReceived;
  });
}

function contiguousSegmentsForLiveTrack(displayPositions: LivePositionRecord[]): LivePositionRecord[][] {
  const segments: LivePositionRecord[][] = [];
  let current: LivePositionRecord[] = [];
  for (const position of displayPositions) {
    const previous = current[current.length - 1];
    if (previous && shouldSplitLiveTrackSegment(previous, position)) {
      if (current.length > 1) {
        segments.push(current);
      }
      current = [];
    }
    current.push(position);
  }
  if (current.length > 1) {
    segments.push(current);
  }
  return segments;
}

export function segmentPositionsForLiveTrack(positions: LivePositionRecord[]): LivePositionRecord[][] {
  const displayPositions = displayPositionsForLiveTrack(positions);
  const positionsBySource = new Map<string, LivePositionRecord[]>();
  for (const position of displayPositions) {
    const bucket = sourceBucketForLiveTrack(position);
    const sourcePositions = positionsBySource.get(bucket) ?? [];
    sourcePositions.push(position);
    positionsBySource.set(bucket, sourcePositions);
  }
  return Array.from(positionsBySource.values()).flatMap((sourcePositions) =>
    contiguousSegmentsForLiveTrack(
      sourcePositions.sort((left, right) => {
        const leftTimestamp = sortableMs(left.timestamp, left.received_at);
        const rightTimestamp = sortableMs(right.timestamp, right.received_at);
        if (leftTimestamp !== rightTimestamp) {
          return leftTimestamp - rightTimestamp;
        }
        return sortableMs(left.received_at, left.timestamp) - sortableMs(right.received_at, right.timestamp);
      }),
    ),
  );
}

function latestByTimestamp(positions: LivePositionRecord[]): LivePositionRecord | null {
  return positions.reduce<LivePositionRecord | null>((latest, position) => {
    if (!latest) {
      return position;
    }
    const latestTimestamp = sortableMs(latest.timestamp, latest.received_at);
    const positionTimestamp = sortableMs(position.timestamp, position.received_at);
    if (positionTimestamp !== latestTimestamp) {
      return positionTimestamp > latestTimestamp ? position : latest;
    }
    return sortableMs(position.received_at, position.timestamp) > sortableMs(latest.received_at, latest.timestamp) ? position : latest;
  }, null);
}

function latestLivePositionForMarker(positions: LivePositionRecord[]): LivePositionRecord | null {
  const latestOverall = latestByTimestamp(positions);
  if (!latestOverall) {
    return null;
  }
  const latestCellular = latestByTimestamp(positions.filter(isCellularPosition));
  if (!latestCellular) {
    return latestOverall;
  }
  const overallTimestamp = timestampMs(latestOverall.timestamp);
  const cellularTimestamp = timestampMs(latestCellular.timestamp);
  if (
    latestOverall !== latestCellular &&
    Number.isFinite(overallTimestamp) &&
    Number.isFinite(cellularTimestamp) &&
    Math.abs(overallTimestamp - cellularTimestamp) <= LIVE_TRACK_CELLULAR_PRIORITY_WINDOW_MS
  ) {
    return latestCellular;
  }
  return latestOverall;
}

export function latestDisplayPositionsBySubject(
  positionsBySubject: Map<string, LivePositionRecord[]>,
): Map<string, LivePositionRecord> {
  const latest = new Map<string, LivePositionRecord>();
  for (const [subjectKey, positions] of positionsBySubject) {
    const displayPositions = displayPositionsForLiveTrack(positions);
    const position = latestLivePositionForMarker(displayPositions);
    if (position) {
      latest.set(subjectKey, position);
    }
  }
  return latest;
}

export function buildTrackCollection(
  positionsBySubject: Map<string, LivePositionRecord[]>,
  subjectNameByKey: Map<string, string>,
): TrackCollection | null {
  const subjectKeys = Array.from(positionsBySubject.keys()).sort();
  const features = subjectKeys.flatMap((subjectKey) => {
    const segments = segmentPositionsForLiveTrack(positionsBySubject.get(subjectKey) ?? []);
    if (!segments.length) {
      return [];
    }
    return segments.map((positions, segmentIndex) => {
      const latest = positions[positions.length - 1];
      return {
        type: "Feature" as const,
        properties: {
          subject_key: subjectKey,
          pilot_id: latest?.pilot_id ?? null,
          user_id: latest?.user_id ?? null,
          pilot_name: latest ? displayNameForSubject(latest, subjectNameByKey) : subjectKey,
          color: colorForSubject(subjectKey, subjectKeys),
          aircraft_icon: latest?.aircraft_icon ?? "hang_glider",
          profile_type: latest?.profile_type ?? "pilot",
          timestamps: positions.map((position) => position.timestamp),
          segment_index: segmentIndex,
          segment_count: segments.length,
          segment_start_timestamp: positions[0]?.timestamp ?? null,
          segment_end_timestamp: latest?.timestamp ?? null,
          source_bucket: latest ? sourceBucketForLiveTrack(latest) : "other",
        },
        geometry: {
          type: "LineString" as const,
          coordinates: positions.map((position) => [position.lon, position.lat, position.alt ?? 0] as [number, number, number]),
        },
      };
    });
  });
  return features.length ? { type: "FeatureCollection", features } : null;
}

export function mergePositionGroup(
  current: Map<string, LivePositionRecord[]>,
  incoming: LivePositionRecord[],
): Map<string, LivePositionRecord[]> {
  const next = new Map(current);
  for (const position of incoming) {
    const subjectKey = subjectKeyForPosition(position);
    const existing = [...(next.get(subjectKey) ?? [])];
    const existingIndex = existing.findIndex((item) => item.id === position.id);
    if (existingIndex >= 0) {
      existing[existingIndex] = position;
    } else {
      existing.push(position);
    }
    next.set(subjectKey, existing);
  }
  return next;
}
