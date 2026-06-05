import type { MapUnitPreferences, TrackCollection } from "../components/TaskMap";

export const TRACK_COLORS = ["#2563eb", "#dc2626", "#16a34a", "#7c3aed", "#d97706", "#0891b2", "#db2777", "#65a30d", "#0f766e", "#c2410c"];
const LIVE_TRACK_MAX_SPEED_KMH = 104.607;
const LIVE_TRACK_STATIONARY_MAX_SPEED_KMH = 16.0934;
const LIVE_TRACK_CONFLICT_WINDOW_MS = 2_000;
const LIVE_TRACK_DUPLICATE_WINDOW_MS = 1_000;
const LIVE_TRACK_DUPLICATE_DISTANCE_M = 3;
const LIVE_TRACK_CELLULAR_TIE_BREAK_M = 15;

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
  mesh_seq_number?: number | null;
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

function maxSpeedKmhForLiveTrack(position: LivePositionRecord): number {
  return position.profile_type === "stationary_node" ? LIVE_TRACK_STATIONARY_MAX_SPEED_KMH : LIVE_TRACK_MAX_SPEED_KMH;
}

function speedKmhBetween(previous: LivePositionRecord, next: LivePositionRecord): number | null {
  if (previous.source === "igc" || next.source === "igc") {
    return null;
  }
  const previousTimestamp = timestampMs(previous.timestamp);
  const nextTimestamp = timestampMs(next.timestamp);
  if (!Number.isFinite(previousTimestamp) || !Number.isFinite(nextTimestamp)) {
    return null;
  }
  const gapSeconds = (nextTimestamp - previousTimestamp) / 1000;
  if (gapSeconds <= 0) {
    return null;
  }
  const distanceMeters = haversineMeters(previous, next);
  return (distanceMeters / gapSeconds) * 3.6;
}

function isImplausibleLiveTrackStep(previous: LivePositionRecord, next: LivePositionRecord): boolean {
  const speedKmh = speedKmhBetween(previous, next);
  if (speedKmh == null) {
    return false;
  }
  return speedKmh > Math.min(maxSpeedKmhForLiveTrack(previous), maxSpeedKmhForLiveTrack(next));
}

function liveTrackSort(left: LivePositionRecord, right: LivePositionRecord): number {
  const leftTimestamp = sortableMs(left.timestamp, left.received_at);
  const rightTimestamp = sortableMs(right.timestamp, right.received_at);
  if (leftTimestamp !== rightTimestamp) {
    return leftTimestamp - rightTimestamp;
  }
  if (
    isMeshPosition(left) &&
    isMeshPosition(right) &&
    left.device_id != null &&
    left.device_id === right.device_id &&
    left.mesh_seq_number != null &&
    right.mesh_seq_number != null &&
    left.mesh_seq_number !== right.mesh_seq_number
  ) {
    return left.mesh_seq_number - right.mesh_seq_number;
  }
  const leftReceived = sortableMs(left.received_at, left.timestamp);
  const rightReceived = sortableMs(right.received_at, right.timestamp);
  return leftReceived - rightReceived;
}

function displayReceivedSort(
  left: { position: LivePositionRecord; index: number },
  right: { position: LivePositionRecord; index: number },
): number {
  const leftReceived = sortableMs(left.position.received_at, left.position.timestamp);
  const rightReceived = sortableMs(right.position.received_at, right.position.timestamp);
  if (leftReceived !== rightReceived) {
    return leftReceived - rightReceived;
  }
  return left.index - right.index;
}

function dedupeKeyForLiveTrack(position: LivePositionRecord): string {
  if (isMeshPosition(position) && position.device_id && position.mesh_seq_number != null) {
    return `mesh-seq:${position.device_id}:${position.mesh_seq_number}`;
  }
  return `${sourceBucketForLiveTrack(position)}:${position.device_id ?? position.source ?? "unknown"}`;
}

function hasSameMeshSequence(previous: LivePositionRecord, next: LivePositionRecord): boolean {
  return (
    isMeshPosition(previous) &&
    isMeshPosition(next) &&
    previous.device_id != null &&
    next.device_id != null &&
    previous.device_id === next.device_id &&
    previous.mesh_seq_number != null &&
    previous.mesh_seq_number === next.mesh_seq_number
  );
}

function isDuplicateLiveTrackObservation(previous: LivePositionRecord, next: LivePositionRecord): boolean {
  if (dedupeKeyForLiveTrack(previous) !== dedupeKeyForLiveTrack(next)) {
    return false;
  }
  if (hasSameMeshSequence(previous, next)) {
    return true;
  }
  const previousTimestamp = timestampMs(previous.timestamp);
  const nextTimestamp = timestampMs(next.timestamp);
  if (!Number.isFinite(previousTimestamp) || !Number.isFinite(nextTimestamp)) {
    return false;
  }
  return Math.abs(nextTimestamp - previousTimestamp) <= LIVE_TRACK_DUPLICATE_WINDOW_MS && haversineMeters(previous, next) <= LIVE_TRACK_DUPLICATE_DISTANCE_M;
}

function replaceWithBetterDuplicate(previous: LivePositionRecord, next: LivePositionRecord): LivePositionRecord {
  const previousReceived = sortableMs(previous.received_at, previous.timestamp);
  const nextReceived = sortableMs(next.received_at, next.timestamp);
  const previousTimestamp = timestampMs(previous.timestamp);
  const nextTimestamp = timestampMs(next.timestamp);
  const previousLatency = Number.isFinite(previousTimestamp) ? Math.abs(previousReceived - previousTimestamp) : Number.POSITIVE_INFINITY;
  const nextLatency = Number.isFinite(nextTimestamp) ? Math.abs(nextReceived - nextTimestamp) : Number.POSITIVE_INFINITY;
  if (nextLatency !== previousLatency) {
    return nextLatency < previousLatency ? next : previous;
  }
  const previousCompleteness = [previous.alt, previous.speed, previous.heading, previous.accuracy, previous.battery_level].filter((value) => value != null).length;
  const nextCompleteness = [next.alt, next.speed, next.heading, next.accuracy, next.battery_level].filter((value) => value != null).length;
  if (nextCompleteness !== previousCompleteness) {
    return nextCompleteness > previousCompleteness ? next : previous;
  }
  return nextReceived >= previousReceived ? next : previous;
}

function dedupeLiveTrackObservations(positions: LivePositionRecord[]): LivePositionRecord[] {
  const deduped: LivePositionRecord[] = [];
  const lastIndexByKey = new Map<string, number>();
  for (const position of [...positions].sort(liveTrackSort)) {
    const key = dedupeKeyForLiveTrack(position);
    const previousIndex = lastIndexByKey.get(key);
    const previous = previousIndex == null ? null : deduped[previousIndex];
    if (previousIndex != null && previous && isDuplicateLiveTrackObservation(previous, position)) {
      deduped[previousIndex] = replaceWithBetterDuplicate(previous, position);
      continue;
    }
    lastIndexByKey.set(key, deduped.length);
    deduped.push(position);
  }
  return deduped.sort(liveTrackSort);
}

function predictedPositionFromTrack(previousPrevious: LivePositionRecord | null, previous: LivePositionRecord, timestamp: number): LivePositionRecord {
  if (!previousPrevious) {
    return previous;
  }
  const previousPreviousTimestamp = timestampMs(previousPrevious.timestamp);
  const previousTimestamp = timestampMs(previous.timestamp);
  if (!Number.isFinite(previousPreviousTimestamp) || !Number.isFinite(previousTimestamp) || previousTimestamp <= previousPreviousTimestamp) {
    return previous;
  }
  const ratio = Math.max(0, Math.min(3, (timestamp - previousTimestamp) / (previousTimestamp - previousPreviousTimestamp)));
  return {
    ...previous,
    lat: previous.lat + (previous.lat - previousPrevious.lat) * ratio,
    lon: previous.lon + (previous.lon - previousPrevious.lon) * ratio,
  };
}

function observationScore(
  candidate: LivePositionRecord,
  previousPrevious: LivePositionRecord | null,
  previous: LivePositionRecord | null,
): number {
  if (!previous) {
    return isCellularPosition(candidate) ? 0 : LIVE_TRACK_CELLULAR_TIE_BREAK_M;
  }
  const candidateTimestamp = timestampMs(candidate.timestamp);
  const predicted = predictedPositionFromTrack(previousPrevious, previous, Number.isFinite(candidateTimestamp) ? candidateTimestamp : timestampMs(previous.timestamp));
  const speed = speedKmhBetween(previous, candidate);
  const speedPenalty = speed != null && speed > maxSpeedKmhForLiveTrack(candidate) ? 10_000 + (speed - maxSpeedKmhForLiveTrack(candidate)) * 100 : 0;
  const sourcePenalty = isCellularPosition(candidate) ? 0 : LIVE_TRACK_CELLULAR_TIE_BREAK_M;
  return haversineMeters(predicted, candidate) + sourcePenalty + speedPenalty;
}

export function displayPositionsForLiveTrack(positions: LivePositionRecord[]): LivePositionRecord[] {
  const byReceiveOrder = positions.map((position, index) => ({ position, index })).sort(displayReceivedSort);
  const display: LivePositionRecord[] = [];
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
  return dedupeLiveTrackObservations(display);
}

function appendFusedCandidate(segments: LivePositionRecord[][], candidate: LivePositionRecord) {
  const current = segments[segments.length - 1];
  if (!current) {
    segments.push([candidate]);
    return;
  }
  const previous = current[current.length - 1];
  const previousPrevious = current[current.length - 2] ?? null;
  const previousTimestamp = timestampMs(previous.timestamp);
  const candidateTimestamp = timestampMs(candidate.timestamp);
  const sameWindow =
    sourceBucketForLiveTrack(previous) !== sourceBucketForLiveTrack(candidate) &&
    Number.isFinite(previousTimestamp) &&
    Number.isFinite(candidateTimestamp) &&
    Math.abs(candidateTimestamp - previousTimestamp) <= LIVE_TRACK_CONFLICT_WINDOW_MS;

  if (sameWindow) {
    const beforeConflict = current[current.length - 2] ?? null;
    const previousScore = observationScore(previous, current[current.length - 3] ?? null, beforeConflict);
    const candidateScore = observationScore(candidate, current[current.length - 3] ?? null, beforeConflict);
    if (candidateScore + 0.001 < previousScore) {
      current[current.length - 1] = candidate;
    }
    return;
  }

  if (isImplausibleLiveTrackStep(previous, candidate)) {
    segments.push([candidate]);
    return;
  }
  current.push(candidate);
}

function fusedSegmentsForLiveTrack(displayPositions: LivePositionRecord[], includeSingletonSegments = false): LivePositionRecord[][] {
  const segments: LivePositionRecord[][] = [];
  for (const position of dedupeLiveTrackObservations(displayPositions)) {
    appendFusedCandidate(segments, position);
  }
  return includeSingletonSegments ? segments : segments.filter((segment) => segment.length > 1);
}

export function segmentPositionsForLiveTrack(positions: LivePositionRecord[]): LivePositionRecord[][] {
  const displayPositions = displayPositionsForLiveTrack(positions);
  return fusedSegmentsForLiveTrack(displayPositions);
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

export function latestDisplayPositionsBySubject(
  positionsBySubject: Map<string, LivePositionRecord[]>,
): Map<string, LivePositionRecord> {
  const latest = new Map<string, LivePositionRecord>();
  for (const [subjectKey, positions] of positionsBySubject) {
    const position = latestByTimestamp(positions);
    if (position) {
      latest.set(subjectKey, position);
    }
  }
  return latest;
}

export function buildTrackCollection(
  positionsBySubject: Map<string, LivePositionRecord[]>,
  subjectNameByKey: Map<string, string>,
  colorSubjectKeys: string[] = Array.from(positionsBySubject.keys()).sort(),
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
          color: colorForSubject(subjectKey, colorSubjectKeys),
          aircraft_icon: latest?.aircraft_icon ?? "hang_glider",
          profile_type: latest?.profile_type ?? "pilot",
          timestamps: positions.map((position) => position.timestamp),
          segment_index: segmentIndex,
          segment_count: segments.length,
          segment_start_timestamp: positions[0]?.timestamp ?? null,
          segment_end_timestamp: latest?.timestamp ?? null,
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
