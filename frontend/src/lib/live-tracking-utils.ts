import type { MapUnitPreferences, TrackCollection } from "../components/TaskMap";

export const TRACK_COLORS = ["#2563eb", "#dc2626", "#16a34a", "#7c3aed", "#d97706", "#0891b2", "#db2777", "#65a30d", "#0f766e", "#c2410c"];

export type ProfileType = "pilot" | "driver" | "stationary_node";
export type PositionSource = "cellular" | "mesh" | "other";

export type LivePositionRecord = {
  id: string;
  pilot_id: number | null;
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

export function resolveApiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
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
    return "/backend";
  }
  return configured ?? "/backend";
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

export function buildTrackCollection(
  positionsByPilot: Map<number, LivePositionRecord[]>,
  pilotNameById: Map<number, string>,
): TrackCollection | null {
  const pilotIds = Array.from(positionsByPilot.keys()).sort((a, b) => a - b);
  const features = pilotIds.flatMap((pilotId) => {
    const positions = [...(positionsByPilot.get(pilotId) ?? [])].sort(
      (left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp),
    );
    if (!positions.length) {
      return [];
    }
    return [
      {
        type: "Feature" as const,
        properties: {
          pilot_id: pilotId,
          pilot_name: pilotNameById.get(pilotId) ?? `Pilot ${pilotId}`,
          color: colorForPilot(pilotId, pilotIds),
          aircraft_icon: positions[positions.length - 1]?.aircraft_icon ?? "hang_glider",
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
  current: Map<number, LivePositionRecord[]>,
  incoming: LivePositionRecord[],
): Map<number, LivePositionRecord[]> {
  const next = new Map(current);
  for (const position of incoming) {
    const pilotId = position.pilot_id ?? 0;
    const existing = [...(next.get(pilotId) ?? [])];
    const existingIndex = existing.findIndex((item) => item.id === position.id);
    if (existingIndex >= 0) {
      existing[existingIndex] = position;
    } else {
      existing.push(position);
    }
    existing.sort((left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp));
    next.set(pilotId, existing);
  }
  return next;
}
