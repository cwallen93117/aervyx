"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { SectionCard } from "../SectionCard";
import {
  TaskMap,
  type MapAirspaceRegion,
  type MapLivePosition,
  type MapTurnpoint,
  type MapUnitPreferences,
  type TrackCollection,
} from "../TaskMap";
import type { BuddyGroup, TaskPointRecord, TaskRecord } from "./types";

const TRACK_COLORS = ["#2563eb", "#dc2626", "#16a34a", "#7c3aed", "#d97706", "#0891b2", "#db2777", "#65a30d", "#0f766e", "#c2410c"];

type LivePositionRecord = {
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
};

type MeshConfigRecord = {
  channel_psk: string | null;
  mqtt_host: string | null;
  mqtt_port: number;
  topic_prefix: string;
};

type TrackingSource =
  | { type: "task"; taskId: number }
  | { type: "buddy_group"; groupId: number }
  | null;

function resolveApiBase() {
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

function formatTime(value: string | null | undefined) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

function formatRelativeTime(value: string | null | undefined) {
  if (!value) return "-";
  const parsed = new Date(value).getTime();
  if (!Number.isFinite(parsed)) return "-";
  const deltaSeconds = Math.max(0, Math.round((Date.now() - parsed) / 1000));
  if (deltaSeconds < 10) return "just now";
  if (deltaSeconds < 60) return `${deltaSeconds}s ago`;
  if (deltaSeconds < 3600) return `${Math.round(deltaSeconds / 60)}m ago`;
  return `${Math.round(deltaSeconds / 3600)}h ago`;
}

function convertAltitude(altitudeM: number | null, unit: MapUnitPreferences["altitude"]) {
  if (altitudeM == null) return "-";
  if (unit === "ft") {
    return `${Math.round(altitudeM * 3.28084).toLocaleString()} ft`;
  }
  return `${Math.round(altitudeM).toLocaleString()} m`;
}

function convertSpeed(speedKmh: number | null, unit: MapUnitPreferences["speed"]) {
  if (speedKmh == null) return "-";
  if (unit === "mph") {
    return `${(speedKmh * 0.621371).toFixed(1)} mph`;
  }
  return `${speedKmh.toFixed(1)} km/h`;
}

function colorForPilot(pilotId: number | null, pilotIds: number[]): string {
  const normalizedId = pilotId ?? 0;
  const index = Math.max(0, pilotIds.indexOf(normalizedId));
  return TRACK_COLORS[index % TRACK_COLORS.length];
}

function buildTrackCollection(
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

function mergePositionGroup(
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

export interface LiveTrackingSectionProps {
  selectedEventId: number | null;
  selectedTaskId: number | null;
  selectedTask: TaskRecord | null;
  tasks: TaskRecord[];
  turnpoints: MapTurnpoint[];
  visibleAirspaces: MapAirspaceRegion[];
  pilotNameById: Map<number, string>;
  token: string;
  canManagePlatform: boolean;
  units: MapUnitPreferences;
  loadTask: (activeToken: string, taskId: number, loadedTask?: TaskRecord, includeScoringData?: boolean) => Promise<void>;
}

export default function LiveTrackingSection({
  selectedEventId,
  selectedTaskId,
  selectedTask,
  tasks,
  turnpoints,
  visibleAirspaces,
  pilotNameById,
  token,
  canManagePlatform,
  units,
  loadTask,
}: LiveTrackingSectionProps) {
  const [positionsByPilot, setPositionsByPilot] = useState<Map<number, LivePositionRecord[]>>(new Map());
  const [igcTracksByPilot, setIgcTracksByPilot] = useState<Map<number, LivePositionRecord[]>>(new Map());
  const [livePositionsByPilot, setLivePositionsByPilot] = useState<Map<number, LivePositionRecord>>(new Map());
  const [liveError, setLiveError] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [meshConfig, setMeshConfig] = useState<MeshConfigRecord | null>(null);
  const [buddyGroups, setBuddyGroups] = useState<BuddyGroup[]>([]);
  const [trackingSource, setTrackingSource] = useState<TrackingSource>(null);

  // Fetch buddy groups on mount
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${resolveApiBase()}/api/buddies/groups`, {
          headers: { Authorization: `Bearer ${token}` },
          cache: "no-store",
        });
        if (response.ok && !cancelled) {
          setBuddyGroups((await response.json()) as BuddyGroup[]);
        }
      } catch { /* silent */ }
    })();
    return () => { cancelled = true; };
  }, [token]);

  // Auto-select task source when selectedTaskId changes from parent
  useEffect(() => {
    if (selectedTaskId && (!trackingSource || trackingSource.type === "task")) {
      setTrackingSource({ type: "task", taskId: selectedTaskId });
    }
  }, [selectedTaskId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Build pilot name map for buddy group mode
  const activePilotNameById = useMemo(() => {
    if (trackingSource?.type === "buddy_group") {
      const group = buddyGroups.find((g) => g.id === trackingSource.groupId);
      return new Map((group?.members ?? []).map((m) => [m.pilot_id, `${m.first_name} ${m.last_name}`]));
    }
    return pilotNameById;
  }, [trackingSource, buddyGroups, pilotNameById]);

  // Derive active pilot IDs for buddy group
  const buddyPilotIds = useMemo(() => {
    if (trackingSource?.type !== "buddy_group") return [];
    const group = buddyGroups.find((g) => g.id === trackingSource.groupId);
    return (group?.members ?? []).map((m) => m.pilot_id);
  }, [trackingSource, buddyGroups]);

  // Handle source dropdown change
  const handleSourceChange = useCallback((value: string) => {
    if (!value) {
      setTrackingSource(null);
      return;
    }
    if (value.startsWith("task:")) {
      const taskId = Number(value.slice(5));
      const task = tasks.find((t) => t.id === taskId);
      if (task) {
        void loadTask(token, taskId, task, false);
        setTrackingSource({ type: "task", taskId });
      }
    } else if (value.startsWith("buddy:")) {
      const groupId = Number(value.slice(6));
      setTrackingSource({ type: "buddy_group", groupId });
    }
  }, [tasks, token, loadTask]);

  // Fetch IGC track and replace live positions for a pilot
  const fetchIgcTrack = useCallback(async (taskId: number, pilotId: number) => {
    try {
      const response = await fetch(`${resolveApiBase()}/api/track/igc/${taskId}/${pilotId}`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (!response.ok) return;
      const geojson = await response.json();
      const feature = geojson?.features?.[0];
      if (!feature?.geometry?.coordinates?.length) return;
      const coords = feature.geometry.coordinates as [number, number, number][];
      const timestamps = (feature.properties?.timestamps ?? []) as string[];
      const igcPositions: LivePositionRecord[] = coords.map((coord, i) => ({
        id: `igc-${pilotId}-${i}`,
        pilot_id: pilotId,
        task_id: taskId,
        lat: coord[1],
        lon: coord[0],
        alt: coord[2] ?? null,
        speed: null,
        heading: null,
        accuracy: null,
        timestamp: timestamps[i] ?? "",
        source: "igc",
        device_id: null,
        battery_level: null,
        aircraft_icon: "hang_glider",
      }));
      setIgcTracksByPilot((current) => {
        const next = new Map(current);
        next.set(pilotId, igcPositions);
        return next;
      });
    } catch { /* silent */ }
  }, [token]);

  // Derive dropdown value
  const sourceDropdownValue = useMemo(() => {
    if (!trackingSource) return "";
    if (trackingSource.type === "task") return `task:${trackingSource.taskId}`;
    return `buddy:${trackingSource.groupId}`;
  }, [trackingSource]);

  useEffect(() => {
    if (!canManagePlatform) {
      setMeshConfig(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${resolveApiBase()}/api/config/mesh`, {
          headers: { Authorization: `Bearer ${token}` },
          cache: "no-store",
        });
        if (!response.ok) {
          return;
        }
        const payload = (await response.json()) as MeshConfigRecord;
        if (!cancelled) {
          setMeshConfig(payload);
        }
      } catch {
        // Mesh config is optional; keep UI quiet if unavailable.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [canManagePlatform, token]);

  // SSE connection — switches between task-scoped and pilot-scoped based on source
  useEffect(() => {
    if (!trackingSource || !token) {
      setPositionsByPilot(new Map());
      setLivePositionsByPilot(new Map());
      setIgcTracksByPilot(new Map());
      setLiveError("");
      return;
    }

    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setLiveError("");
    setPositionsByPilot(new Map());
    setLivePositionsByPilot(new Map());
    setIgcTracksByPilot(new Map());

    const handleSnapshot = (positions: LivePositionRecord[]) => {
      if (!active) return;
      setPositionsByPilot((current) => mergePositionGroup(current, positions));
      setLivePositionsByPilot((current) => {
        const next = new Map(current);
        for (const position of positions) {
          next.set(position.pilot_id ?? 0, position);
        }
        return next;
      });
    };

    const handlePosition = (position: LivePositionRecord) => {
      if (!active) return;
      setPositionsByPilot((current) => mergePositionGroup(current, [position]));
      setLivePositionsByPilot((current) => {
        const next = new Map(current);
        next.set(position.pilot_id ?? 0, position);
        return next;
      });
    };

    const readSse = async () => {
      try {
        // Determine endpoints based on source
        let historyUrl: string;
        let sseUrl: string;

        if (trackingSource.type === "task") {
          historyUrl = `${resolveApiBase()}/api/track/positions/${trackingSource.taskId}?limit=10000`;
          sseUrl = `${resolveApiBase()}/api/track/live/${trackingSource.taskId}`;
        } else {
          const ids = buddyPilotIds.join(",");
          if (!ids) {
            setLoading(false);
            return;
          }
          historyUrl = `${resolveApiBase()}/api/track/positions/pilots?ids=${ids}&limit=10000`;
          sseUrl = `${resolveApiBase()}/api/track/live/pilots?ids=${ids}`;
        }

        const historyResponse = await fetch(historyUrl, {
          headers: { Authorization: `Bearer ${token}` },
          cache: "no-store",
          signal: controller.signal,
        });
        if (historyResponse.ok) {
          const history = (await historyResponse.json()) as LivePositionRecord[];
          handleSnapshot(history);
        }

        const response = await fetch(sseUrl, {
          headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`Connection failed: ${response.status}`);
        }
        setLoading(false);
        const reader = response.body?.getReader();
        if (!reader) {
          return;
        }

        const decoder = new TextDecoder();
        let buffer = "";
        while (active) {
          const { done, value } = await reader.read();
          if (done) {
            break;
          }
          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split("\n\n");
          buffer = blocks.pop() ?? "";
          for (const block of blocks) {
            const lines = block.split(/\r?\n/);
            let eventName = "message";
            const dataLines: string[] = [];
            for (const line of lines) {
              if (!line || line.startsWith(":")) {
                continue;
              }
              if (line.startsWith("event:")) {
                eventName = line.slice(6).trim();
              } else if (line.startsWith("data:")) {
                dataLines.push(line.slice(5).trim());
              }
            }
            if (!dataLines.length) {
              continue;
            }
            try {
              const payload = JSON.parse(dataLines.join("\n"));
              if (eventName === "snapshot" && Array.isArray(payload)) {
                handleSnapshot(payload as LivePositionRecord[]);
              } else if (eventName === "position" && payload && typeof payload === "object") {
                handlePosition(payload as LivePositionRecord);
              } else if (eventName === "igc_available" && payload && typeof payload === "object") {
                const { task_id: igcTaskId, pilot_id: igcPilotId } = payload as { task_id: number; pilot_id: number };
                if (igcTaskId && igcPilotId) {
                  fetchIgcTrack(igcTaskId, igcPilotId);
                }
              }
            } catch {
              // Ignore malformed event payloads without breaking the stream.
            }
          }
        }
      } catch (error) {
        if (!controller.signal.aborted && active) {
          setLiveError(error instanceof Error ? error.message : "Live tracking connection failed.");
          setLoading(false);
        }
      }
    };

    void readSse();
    return () => {
      active = false;
      controller.abort();
    };
  }, [trackingSource, token, buddyPilotIds, fetchIgcTrack]);

  const taskPoints = useMemo<TaskPointRecord[]>(() => selectedTask?.points ?? [], [selectedTask]);
  const taskTurnpoints = useMemo<MapTurnpoint[]>(() => {
    const unique = new Map<string, MapTurnpoint>();
    for (const point of taskPoints) {
      const key = `${point.turnpoint_id ?? point.name}-${point.position}`;
      unique.set(key, {
        id: point.turnpoint_id ?? point.position,
        name: point.name,
        code: turnpoints.find((turnpoint) => turnpoint.id === point.turnpoint_id)?.code ?? null,
        latitude: point.latitude,
        longitude: point.longitude,
      });
    }
    return Array.from(unique.values());
  }, [taskPoints, turnpoints]);

  // Merge IGC tracks over live tracks when available
  const effectivePositionsByPilot = useMemo(() => {
    if (igcTracksByPilot.size === 0) return positionsByPilot;
    const merged = new Map(positionsByPilot);
    for (const [pilotId, igcPositions] of igcTracksByPilot) {
      merged.set(pilotId, igcPositions);
    }
    return merged;
  }, [positionsByPilot, igcTracksByPilot]);

  const liveTrack = useMemo(() => buildTrackCollection(effectivePositionsByPilot, activePilotNameById), [activePilotNameById, effectivePositionsByPilot]);
  const livePositions = useMemo<MapLivePosition[]>(() => {
    const liveValues = Array.from(livePositionsByPilot.values());
    const pilotIds = liveValues.map((position) => position.pilot_id ?? 0).sort((a, b) => a - b);
    return liveValues.map((position) => ({
      id: position.id,
      pilotId: position.pilot_id,
      pilotName: activePilotNameById.get(position.pilot_id ?? 0) ?? `Pilot ${position.pilot_id ?? 0}`,
      latitude: position.lat,
      longitude: position.lon,
      altitudeM: position.alt,
      speedKmh: position.speed,
      heading: position.heading,
      timestamp: position.timestamp,
      batteryLevel: position.battery_level,
      source: position.source,
      color: colorForPilot(position.pilot_id, pilotIds),
      aircraftType: position.aircraft_icon ?? "hang_glider",
    }));
  }, [livePositionsByPilot, activePilotNameById]);

  const livePilotRows = useMemo(() => {
    return [...livePositions].sort((left, right) => {
      const rightTime = Date.parse(right.timestamp) || 0;
      const leftTime = Date.parse(left.timestamp) || 0;
      if (rightTime !== leftTime) {
        return rightTime - leftTime;
      }
      return left.pilotName.localeCompare(right.pilotName);
    });
  }, [livePositions]);

  // Status label for the current tracking source
  const sourceLabel = useMemo(() => {
    if (!trackingSource) return "";
    if (trackingSource.type === "task") {
      const task = tasks.find((t) => t.id === trackingSource.taskId);
      return task ? task.name : `Task ${trackingSource.taskId}`;
    }
    const group = buddyGroups.find((g) => g.id === trackingSource.groupId);
    return group ? group.name : "Buddy group";
  }, [trackingSource, tasks, buddyGroups]);

  const isSourceActive = trackingSource !== null;
  const showTaskMap = trackingSource?.type === "task" && selectedTask;
  const showBuddyMap = trackingSource?.type === "buddy_group";

  return (
    <div className="section-stack">
      <SectionCard
        title="Live tracking"
        description="Stream pilot positions for a competition task or buddy group."
      >
        <div className="stack form-block">
          <div className="participant-intake-row">
            <label className="stack compact">
              <span>Tracking source</span>
              <select value={sourceDropdownValue} onChange={(e) => handleSourceChange(e.target.value)}>
                <option value="">Select a source</option>
                {tasks.length > 0 ? (
                  <optgroup label="Competition tasks">
                    {tasks.map((task) => (
                      <option key={`task:${task.id}`} value={`task:${task.id}`}>
                        {task.name} - {task.status}
                      </option>
                    ))}
                  </optgroup>
                ) : null}
                {buddyGroups.length > 0 ? (
                  <optgroup label="Buddy groups">
                    {buddyGroups.map((group) => (
                      <option key={`buddy:${group.id}`} value={`buddy:${group.id}`}>
                        {group.name} ({group.members.length} pilot{group.members.length !== 1 ? "s" : ""})
                      </option>
                    ))}
                  </optgroup>
                ) : null}
              </select>
            </label>
            {isSourceActive ? (
              <div className="live-tracking-status-block">
                <span className={`status-chip ${liveError ? "error" : "success"}`}>
                  {liveError ? "Disconnected" : loading ? "Connecting" : "Live"}
                </span>
                <span className="hint">
                  {sourceLabel} — {livePilotRows.length} pilot{livePilotRows.length !== 1 ? "s" : ""}
                </span>
              </div>
            ) : null}
          </div>

          {!selectedEventId && !buddyGroups.length ? (
            <p className="hint">Select or create an event, or create buddy groups in Settings to get started.</p>
          ) : null}

          {meshConfig && canManagePlatform ? (
            <div className="live-tracking-mesh-card">
              <div>
                <strong>Meshtastic mesh config</strong>
                <p className="hint">Mobile clients can auto-configure from the server-side mesh settings.</p>
              </div>
              <div className="live-tracking-mesh-grid">
                <span>MQTT host</span>
                <span>{meshConfig.mqtt_host || "Not configured"}</span>
                <span>MQTT port</span>
                <span>{meshConfig.mqtt_port}</span>
                <span>Topic prefix</span>
                <span>{meshConfig.topic_prefix}</span>
                <span>Channel PSK</span>
                <span>{meshConfig.channel_psk ? "Configured" : "Not configured"}</span>
              </div>
            </div>
          ) : null}

          {isSourceActive ? (
            <div className="results-task-map-layout live-tracking-layout">
              <div className="results-task-map-pilot-list live-tracking-pilot-list">
                <div className="results-task-map-pilot-header">
                  <strong>Tracked pilots</strong>
                  <span>{livePilotRows.length} active</span>
                </div>
                <div className="results-task-map-pilot-items">
                  {livePilotRows.length ? (
                    livePilotRows.map((pilot) => (
                      <div key={pilot.id} className="results-task-map-pilot-item live-tracking-pilot-item">
                        <span className="results-task-map-pilot-rank">
                          <span className="live-tracking-dot" style={{ backgroundColor: pilot.color ?? "#2563eb" }} />
                        </span>
                        <span className="results-task-map-pilot-copy">
                          <strong style={{ color: pilot.color ?? "#2563eb" }}>{pilot.pilotName}</strong>
                          <small>
                            {convertAltitude(pilot.altitudeM, units.altitude)} · {convertSpeed(pilot.speedKmh, units.speed)}
                          </small>
                        </span>
                        <span className="live-tracking-pilot-meta">
                          {igcTracksByPilot.has(pilot.pilotId ?? 0) ? <span className="status-chip success" style={{ fontSize: "0.625rem", padding: "1px 6px" }}>IGC</span> : null}
                          <span>{formatRelativeTime(pilot.timestamp)}</span>
                          {pilot.batteryLevel != null ? <span>{pilot.batteryLevel}%</span> : null}
                        </span>
                      </div>
                    ))
                  ) : (
                    <div className="results-task-map-empty">
                      {loading ? "Connecting to the live position stream..." : trackingSource?.type === "buddy_group" ? "No recent positions from buddy group pilots." : "No active pilot tracking for this task yet."}
                    </div>
                  )}
                </div>
              </div>
              <div className="results-task-map-canvas">
                <TaskMap
                  turnpoints={showTaskMap ? taskTurnpoints : []}
                  fitTurnpoints={showTaskMap ? turnpoints : []}
                  airspaces={showTaskMap ? visibleAirspaces : []}
                  taskPoints={showTaskMap ? taskPoints : []}
                  track={liveTrack}
                  livePositions={livePositions}
                  editable={false}
                  mode="live"
                  units={units}
                  fitKey={trackingSource.type === "task" ? `live-${trackingSource.taskId}` : `live-buddy-${trackingSource.groupId}`}
                />
              </div>
            </div>
          ) : (
            <p className="hint">Choose a tracking source to start the live position stream and map overlays.</p>
          )}

          {liveError ? <div className="status-chip error">{liveError}</div> : null}

          {isSourceActive && livePilotRows.length ? (
            <div className="live-tracking-table-wrap">
              <table className="results-table live-tracking-table">
                <thead>
                  <tr>
                    <th>Pilot</th>
                    <th>Altitude</th>
                    <th>Speed</th>
                    <th>Heading</th>
                    <th>Battery</th>
                    <th>Last fix</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {livePilotRows.map((pilot) => (
                    <tr key={`table-${pilot.id}`}>
                      <td>
                        <span className="live-tracking-table-pilot">
                          <span className="live-tracking-dot" style={{ backgroundColor: pilot.color ?? "#2563eb" }} />
                          <strong style={{ color: pilot.color ?? "#2563eb" }}>{pilot.pilotName}</strong>
                        </span>
                      </td>
                      <td>{convertAltitude(pilot.altitudeM, units.altitude)}</td>
                      <td>{convertSpeed(pilot.speedKmh, units.speed)}</td>
                      <td>{pilot.heading != null ? `${Math.round(pilot.heading)}°` : "-"}</td>
                      <td>{pilot.batteryLevel != null ? `${pilot.batteryLevel}%` : "-"}</td>
                      <td>{formatTime(pilot.timestamp)}</td>
                      <td>{pilot.source ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      </SectionCard>
    </div>
  );
}
