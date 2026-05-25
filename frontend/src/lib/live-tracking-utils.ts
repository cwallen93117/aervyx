import type { MapUnitPreferences, TrackCollection } from "../components/TaskMap";

export const TRACK_COLORS = ["#2563eb", "#dc2626", "#16a34a", "#7c3aed", "#d97706", "#0891b2", "#db2777", "#65a30d", "#0f766e", "#c2410c"];

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

export function buildTrackCollection(
  positionsBySubject: Map<string, LivePositionRecord[]>,
  subjectNameByKey: Map<string, string>,
): TrackCollection | null {
  const subjectKeys = Array.from(positionsBySubject.keys()).sort();
  const features = subjectKeys.flatMap((subjectKey) => {
    const positions = [...(positionsBySubject.get(subjectKey) ?? [])].sort(
      (left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp),
    );
    if (!positions.length) {
      return [];
    }
    const latest = positions[positions.length - 1];
    return [
      {
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
        },
        geometry: {
          type: "LineString" as const,
          coordinates: positions.map((position) => [position.lon, position.lat, position.alt ?? 0] as [number, number, number]),
        },
      },
    ];
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
    existing.sort((left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp));
    next.set(subjectKey, existing);
  }
  return next;
}
