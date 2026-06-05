"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { SectionCard } from "../SectionCard";
import { PilotRoleBadge } from "../PilotRoleBadge";
import {
  TaskMap,
  type MapAirspaceRegion,
  type MapLivePosition,
  type TaskEditorOverlayRenderProps,
  type MapTurnpoint,
  type MapUnitPreferences,
  type TrackCollection,
} from "../TaskMap";
import { computeTaskOptimization } from "../../lib/taskOptimization";
import { TaskTurnpointsTable } from "./TaskTurnpointsTable";
import type { BuddyGroup, TaskPointRecord, TaskRecord } from "./types";
import {
  type LivePositionRecord,
  resolveApiBase,
  resolveStreamApiBase,
  formatRelativeTime,
  convertAltitude,
  convertSpeed,
  colorForSubject,
  displayNameForSubject,
  buildTrackCollection,
  mergePositionGroup,
  latestDisplayPositionsBySubject,
  subjectKeyForPosition,
} from "../../lib/live-tracking-utils";

type MeshConfigRecord = {
  channel_psk: string | null;
  mqtt_host: string | null;
  mqtt_port: number;
  mqtt_tls_enabled: boolean;
  mqtt_username: string | null;
  mqtt_password: string | null;
  topic_prefix: string;
};

type TrackingSource =
  | { type: "task"; taskId: number }
  | { type: "buddy_group"; groupId: number }
  | { type: "all_users" }
  | null;

type LivePositionWithName = LivePositionRecord & { pilot_name?: string | null };

function formatTime(value: string | null | undefined) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
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
  overlayConfig?: Record<string, boolean>;
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
  overlayConfig,
}: LiveTrackingSectionProps) {
  const [positionsByPilot, setPositionsByPilot] = useState<Map<string, LivePositionRecord[]>>(new Map());
  const [igcTracksByPilot, setIgcTracksByPilot] = useState<Map<string, LivePositionRecord[]>>(new Map());
  const [livePositionsByPilot, setLivePositionsByPilot] = useState<Map<string, LivePositionRecord>>(new Map());
  const [liveError, setLiveError] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [meshConfig, setMeshConfig] = useState<MeshConfigRecord | null>(null);
  const [buddyGroups, setBuddyGroups] = useState<BuddyGroup[]>([]);
  const [trackingSource, setTrackingSource] = useState<TrackingSource>(null);
  const [allUsersNameById, setAllUsersNameById] = useState<Map<string, string>>(new Map());
  const [focusPosition, setFocusPosition] = useState<{ lat: number; lon: number; key: string | number } | null>(null);
  const [highlightedSubjectKey, setHighlightedSubjectKey] = useState<string | null>(null);
  const [visibleTrackSubjectKeys, setVisibleTrackSubjectKeys] = useState<Set<string>>(() => new Set());
  const [taskFitRequestId, setTaskFitRequestId] = useState(0);
  const focusRequestIdRef = useRef(0);
  const apiBase = useMemo(() => resolveApiBase(), []);
  const streamApiBase = useMemo(() => resolveStreamApiBase(), []);

  // Fetch buddy groups on mount
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${apiBase}/api/buddies/groups`, {
          headers: { Authorization: `Bearer ${token}` },
          cache: "no-store",
        });
        if (response.ok && !cancelled) {
          setBuddyGroups((await response.json()) as BuddyGroup[]);
        }
      } catch { /* silent */ }
    })();
    return () => { cancelled = true; };
  }, [apiBase, token]);

  // Auto-select task source when selectedTaskId changes from parent
  useEffect(() => {
    if (selectedTaskId && (!trackingSource || trackingSource.type === "task")) {
      setTrackingSource({ type: "task", taskId: selectedTaskId });
      setTaskFitRequestId((current) => current + 1);
    }
  }, [selectedTaskId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Build pilot name map for buddy group / all-users mode
  const activePilotNameById = useMemo(() => {
    if (trackingSource?.type === "buddy_group") {
      const group = buddyGroups.find((g) => g.id === trackingSource.groupId);
      return new Map((group?.members ?? []).map((m) => [`pilot:${m.pilot_id}`, `${m.first_name} ${m.last_name}`]));
    }
    const pilotSubjectNames = Array.from(pilotNameById.entries()).map(([pilotId, name]) => [`pilot:${pilotId}`, name] as const);
    if (trackingSource?.type === "all_users") {
      // Merge SSE-derived names with any known names from parent context
      return new Map<string, string>([...pilotSubjectNames, ...allUsersNameById]);
    }
    return new Map<string, string>(pilotSubjectNames);
  }, [trackingSource, buddyGroups, pilotNameById, allUsersNameById]);

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
    if (value === "all_users") {
      setTrackingSource({ type: "all_users" });
      return;
    }
    if (value.startsWith("task:")) {
      const taskId = Number(value.slice(5));
      const task = tasks.find((t) => t.id === taskId);
      if (task) {
        void loadTask(token, taskId, task, false);
        setTrackingSource({ type: "task", taskId });
        setTaskFitRequestId((current) => current + 1);
      }
    } else if (value.startsWith("buddy:")) {
      const groupId = Number(value.slice(6));
      setTrackingSource({ type: "buddy_group", groupId });
    }
  }, [tasks, token, loadTask]);

  // Fetch IGC track and replace live positions for a pilot
  const fetchIgcTrack = useCallback(async (taskId: number, pilotId: number) => {
    try {
      const response = await fetch(`${apiBase}/api/track/igc/${taskId}/${pilotId}`, {
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
        subject_key: `pilot:${pilotId}`,
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
        next.set(`pilot:${pilotId}`, igcPositions);
        return next;
      });
    } catch { /* silent */ }
  }, [apiBase, token]);

  // Derive dropdown value
  const sourceDropdownValue = useMemo(() => {
    if (!trackingSource) return "";
    if (trackingSource.type === "task") return `task:${trackingSource.taskId}`;
    if (trackingSource.type === "all_users") return "all_users";
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
        const response = await fetch(`${apiBase}/api/config/mesh`, {
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
  }, [apiBase, canManagePlatform, token]);

  // SSE connection - switches between task-scoped and pilot-scoped based on source
  useEffect(() => {
    if (!trackingSource || !token) {
      setPositionsByPilot(new Map());
      setLivePositionsByPilot(new Map());
      setIgcTracksByPilot(new Map());
      setAllUsersNameById(new Map());
      setHighlightedSubjectKey(null);
      setFocusPosition(null);
      setVisibleTrackSubjectKeys(new Set());
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
    setAllUsersNameById(new Map());
    setHighlightedSubjectKey(null);
    setFocusPosition(null);
    setVisibleTrackSubjectKeys(new Set());

    const collectNames = (positions: LivePositionWithName[]): Map<string, string> => {
      const names = new Map<string, string>();
      for (const pos of positions) {
        if (pos.pilot_name) {
          names.set(subjectKeyForPosition(pos), pos.pilot_name);
        }
      }
      return names;
    };

    const handleSnapshot = (positions: LivePositionRecord[]) => {
      if (!active) return;
      setPositionsByPilot((current) => mergePositionGroup(current, positions));
      const names = collectNames(positions as LivePositionWithName[]);
      if (names.size) {
        setAllUsersNameById((prev) => new Map([...prev, ...names]));
      }
    };

    const handlePosition = (position: LivePositionRecord) => {
      if (!active) return;
      setPositionsByPilot((current) => mergePositionGroup(current, [position]));
      const names = collectNames([position as LivePositionWithName]);
      if (names.size) {
        setAllUsersNameById((prev) => new Map([...prev, ...names]));
      }
    };

    const readSse = async () => {
      try {
        // Determine endpoints based on source
        let historyUrl: string;
        let sseUrl: string;
        let useAuth = true;

        if (trackingSource.type === "task") {
          historyUrl = `${apiBase}/api/track/positions/${trackingSource.taskId}`;
          sseUrl = `${streamApiBase}/api/track/live/${trackingSource.taskId}`;
        } else if (trackingSource.type === "all_users") {
          // Reuse the public "show all" endpoints (no auth needed)
          historyUrl = `${apiBase}/api/public/live/all/positions`;
          sseUrl = `${streamApiBase}/api/public/live/all`;
          useAuth = false;
        } else {
          const ids = buddyPilotIds.join(",");
          if (!ids) {
            setLoading(false);
            return;
          }
          historyUrl = `${apiBase}/api/track/positions/pilots?ids=${ids}`;
          sseUrl = `${streamApiBase}/api/track/live/pilots?ids=${ids}`;
        }

        const historyResponse = await fetch(historyUrl, {
          headers: useAuth ? { Authorization: `Bearer ${token}` } : undefined,
          cache: "no-store",
          signal: controller.signal,
        });
        if (historyResponse.ok) {
          const history = (await historyResponse.json()) as LivePositionRecord[];
          handleSnapshot(history);
        }

        const response = await fetch(sseUrl, {
          headers: useAuth
            ? { Authorization: `Bearer ${token}`, Accept: "text/event-stream" }
            : { Accept: "text/event-stream" },
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
  }, [apiBase, streamApiBase, trackingSource, token, buddyPilotIds, fetchIgcTrack]);

  useEffect(() => {
    setLivePositionsByPilot(latestDisplayPositionsBySubject(positionsByPilot));
  }, [positionsByPilot]);

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

  const activeSubjectKeys = useMemo(() => Array.from(effectivePositionsByPilot.keys()).sort(), [effectivePositionsByPilot]);
  const telemetryTrack = useMemo(
    () => buildTrackCollection(effectivePositionsByPilot, activePilotNameById, activeSubjectKeys),
    [activePilotNameById, activeSubjectKeys, effectivePositionsByPilot],
  );
  const visibleTrackPositionsByPilot = useMemo(() => {
    const next = new Map<string, LivePositionRecord[]>();
    for (const [subjectKey, positions] of effectivePositionsByPilot) {
      if (visibleTrackSubjectKeys.has(subjectKey)) {
        next.set(subjectKey, positions);
      }
    }
    return next;
  }, [effectivePositionsByPilot, visibleTrackSubjectKeys]);
  const liveTrack = useMemo(
    () => buildTrackCollection(visibleTrackPositionsByPilot, activePilotNameById, activeSubjectKeys),
    [activePilotNameById, activeSubjectKeys, visibleTrackPositionsByPilot],
  );
  const allLiveTracksChecked = useMemo(
    () => activeSubjectKeys.length > 0 && activeSubjectKeys.every((subjectKey) => visibleTrackSubjectKeys.has(subjectKey)),
    [activeSubjectKeys, visibleTrackSubjectKeys],
  );
  const livePositions = useMemo<MapLivePosition[]>(() => {
    const liveValues = Array.from(livePositionsByPilot.values());
    return liveValues.map((position) => {
      const subjectKey = subjectKeyForPosition(position);
      return {
        id: position.id,
        subjectKey,
        pilotId: position.pilot_id,
        userId: position.user_id ?? null,
        pilotName: displayNameForSubject(position, activePilotNameById),
        latitude: position.lat,
        longitude: position.lon,
        altitudeM: position.alt,
        speedKmh: position.speed,
        heading: position.heading,
        timestamp: position.timestamp,
        batteryLevel: position.battery_level,
        source: position.source,
        color: colorForSubject(subjectKey, activeSubjectKeys),
        aircraftType: position.aircraft_icon ?? "hang_glider",
        profileType: position.profile_type ?? "pilot",
        positionSource: position.position_source ?? "other",
        deviceId: position.device_id,
      };
    });
  }, [activeSubjectKeys, livePositionsByPilot, activePilotNameById]);

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

  const latestPositionForSubject = useCallback((subjectKey: string) => {
    const current = livePositionsByPilot.get(subjectKey);
    if (current) {
      return current;
    }
    const history = effectivePositionsByPilot.get(subjectKey);
    return history && history.length > 0 ? history[history.length - 1] : null;
  }, [effectivePositionsByPilot, livePositionsByPilot]);

  const focusSubjectOnMap = useCallback((subjectKey: string) => {
    const position = latestPositionForSubject(subjectKey);
    if (!position) {
      return;
    }
    focusRequestIdRef.current += 1;
    setFocusPosition({
      lat: position.lat,
      lon: position.lon,
      key: `${subjectKey}:${position.id}:${focusRequestIdRef.current}`,
    });
    setHighlightedSubjectKey((current) => current === subjectKey ? null : subjectKey);
  }, [latestPositionForSubject]);

  const handlePilotClick = useCallback((pilot: MapLivePosition) => {
    focusSubjectOnMap(pilot.subjectKey ?? `position:${pilot.id}`);
  }, [focusSubjectOnMap]);

  const toggleSubjectTrack = useCallback((subjectKey: string, checked: boolean) => {
    setVisibleTrackSubjectKeys((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(subjectKey);
      } else {
        next.delete(subjectKey);
      }
      return next;
    });
  }, []);

  const toggleAllLiveTracks = useCallback(() => {
    setVisibleTrackSubjectKeys(() => {
      if (allLiveTracksChecked) {
        return new Set();
      }
      return new Set(activeSubjectKeys);
    });
  }, [activeSubjectKeys, allLiveTracksChecked]);

  const requestSelectedTaskFit = useCallback(() => {
    if (trackingSource?.type === "task") {
      setTaskFitRequestId((current) => current + 1);
    }
  }, [trackingSource]);

  // Status label for the current tracking source
  const sourceLabel = useMemo(() => {
    if (!trackingSource) return "";
    if (trackingSource.type === "task") {
      const task = tasks.find((t) => t.id === trackingSource.taskId);
      return task ? task.name : `Task ${trackingSource.taskId}`;
    }
    if (trackingSource.type === "all_users") {
      return "All users";
    }
    const group = buddyGroups.find((g) => g.id === trackingSource.groupId);
    return group ? group.name : "Buddy group";
  }, [trackingSource, tasks, buddyGroups]);

  const isSourceActive = trackingSource !== null;
  const showTaskMap = trackingSource?.type === "task" && selectedTask !== null;
  const liveTaskDistanceMetrics = useMemo(() => computeTaskOptimization(showTaskMap ? taskPoints : []), [showTaskMap, taskPoints]);
  const taskFitGeometryKey = useMemo(
    () => taskPoints.map((point) => `${point.position}:${point.latitude.toFixed(6)}:${point.longitude.toFixed(6)}:${point.radius_m}`).join("|"),
    [taskPoints],
  );
  const taskFitOnceKey = trackingSource?.type === "task" && taskPoints.length > 0 && taskFitRequestId > 0
    ? `internal-task-select:${taskFitRequestId}:task:${trackingSource.taskId}:${taskFitGeometryKey}`
    : null;
  const liveTaskFullscreenOverlay = showTaskMap
    ? ({ collapsed, contentId, overlayId, toggleButton }: TaskEditorOverlayRenderProps) => (
        <div id={overlayId} className={`map-task-editor${collapsed ? " is-collapsed" : ""}`}>
          <TaskTurnpointsTable
            points={taskPoints}
            taskPointAdvanced
            turnpoints={turnpoints}
            taskDistanceMetrics={liveTaskDistanceMetrics}
            distanceUnit={units.distance}
            collapsed={collapsed}
            contentId={contentId}
            titleAction={toggleButton}
          />
        </div>
      )
    : undefined;
  const renderPilotSidebar = (className = "live-sidebar") => (
    <div className={className}>
      <div className="live-sidebar-header">
        <div className="live-sidebar-title">
          <strong>{sourceLabel || "Live tracking"}</strong>
          <span>{livePilotRows.length} pilot{livePilotRows.length !== 1 ? "s" : ""}</span>
        </div>
        <label className="live-track-master-toggle" title={allLiveTracksChecked ? "Hide all tracks" : "Show all tracks"}>
          <input
            type="checkbox"
            checked={allLiveTracksChecked}
            disabled={!activeSubjectKeys.length}
            onChange={toggleAllLiveTracks}
          />
          <span>Tracks</span>
        </label>
      </div>
      <div className="live-pilot-list">
        {livePilotRows.length > 0 ? (
          livePilotRows.map((pilot) => {
            const subjectKey = pilot.subjectKey ?? `position:${pilot.id}`;
            const isHighlighted = highlightedSubjectKey === subjectKey;
            const trackChecked = visibleTrackSubjectKeys.has(subjectKey);
            return (
              <div
                key={subjectKey}
                className={`live-pilot-row${isHighlighted ? " is-highlighted" : ""}`}
              >
                <input
                  type="checkbox"
                  className="live-pilot-track-toggle"
                  checked={trackChecked}
                  onChange={(event) => toggleSubjectTrack(subjectKey, event.target.checked)}
                  title={trackChecked ? `Hide track for ${pilot.pilotName}` : `Show track for ${pilot.pilotName}`}
                  aria-label={trackChecked ? `Hide track for ${pilot.pilotName}` : `Show track for ${pilot.pilotName}`}
                />
                <button
                  type="button"
                  className="live-pilot-main"
                  onClick={() => focusSubjectOnMap(subjectKey)}
                  aria-pressed={isHighlighted}
                  title={`${isHighlighted ? "Hide details for" : "Center map on"} ${pilot.pilotName}`}
                >
                  <span className="live-pilot-badge" style={{ color: pilot.color ?? "#2563eb" }}>
                    <PilotRoleBadge
                      profileType={pilot.profileType}
                      aircraftType={pilot.aircraftType}
                      color={pilot.color ?? "#2563eb"}
                      size={16}
                    />
                  </span>
                  <div className="live-pilot-info">
                    <strong>{pilot.pilotName}</strong>
                    <span className="live-pilot-stats">
                      {convertAltitude(pilot.altitudeM, units.altitude)}
                      {pilot.speedKmh != null ? ` - ${convertSpeed(pilot.speedKmh, units.speed)}` : ""}
                      {pilot.timestamp ? ` - ${formatRelativeTime(pilot.timestamp)}` : ""}
                    </span>
                  </div>
                </button>
              </div>
            );
          })
        ) : (
          <div className="live-pilot-empty">
            {loading
              ? "Connecting..."
              : trackingSource?.type === "buddy_group"
                ? "Waiting for buddy group pilots..."
                : trackingSource?.type === "all_users"
                  ? "Waiting for pilots..."
                  : "Waiting for competition pilots..."}
          </div>
        )}
      </div>
      <div className="live-sidebar-legend" aria-label="Map legend">
        <div className="live-sidebar-legend-title">Legend</div>
        <div className="live-sidebar-legend-row">
          <span className="live-sidebar-legend-item">
            <PilotRoleBadge profileType="driver" color="#cbd5e1" size={14} />
            Driver
          </span>
          <span className="live-sidebar-legend-item">
            <PilotRoleBadge profileType="stationary_node" color="#cbd5e1" size={14} />
            Node
          </span>
        </div>
        <div className="live-sidebar-legend-row">
          <span className="live-sidebar-legend-item">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" strokeWidth="2.5" aria-hidden="true">
              <circle cx="12" cy="12" r="9" />
            </svg>
            Cellular
          </span>
          <span className="live-sidebar-legend-item">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" strokeWidth="2.5" strokeDasharray="4 3" aria-hidden="true">
              <circle cx="12" cy="12" r="9" />
            </svg>
            Mesh
          </span>
        </div>
      </div>
    </div>
  );

  return (
    <div className="section-stack">
      <SectionCard
        title="Live tracking"
      >
        <div className="stack form-block">
          <div className="participant-intake-row">
            <label className="stack compact">
              <span>Tracking source</span>
              <select value={sourceDropdownValue} onChange={(e) => handleSourceChange(e.target.value)} onClick={requestSelectedTaskFit}>
                <option value="">Select a source</option>
                <option value="all_users">All users</option>
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
                  {sourceLabel} - {livePilotRows.length} pilot{livePilotRows.length !== 1 ? "s" : ""}
                </span>
              </div>
            ) : null}
          </div>

          {!selectedEventId && !buddyGroups.length ? (
            <p className="hint">Select or create an event, or create buddy groups in Settings to get started.</p>
          ) : null}

          {/* FILTER: Meshtastic mesh config card - hidden while we're in
              "show all devices" debug mode. Un-comment to restore.
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
          */}

          {isSourceActive ? (
            <div className="results-task-map-layout live-tracking-layout">
              <div className="results-task-map-pilot-list live-tracking-pilot-list">
                <div className="results-task-map-pilot-header">
                  <strong>Tracked pilots</strong>
                  <span>{livePilotRows.length} active</span>
                </div>
                <div className="results-task-map-pilot-items">
                  {livePilotRows.length ? (
                    livePilotRows.map((pilot) => {
                      const subjectKey = pilot.subjectKey ?? `position:${pilot.id}`;
                      const trackChecked = visibleTrackSubjectKeys.has(subjectKey);
                      const isHighlighted = highlightedSubjectKey === subjectKey;
                      return (
                        <div
                          key={subjectKey}
                          className={`results-task-map-pilot-item live-tracking-pilot-item${isHighlighted ? " is-highlighted" : ""}`}
                          onClick={() => handlePilotClick(pilot)}
                        >
                          <input
                            type="checkbox"
                            className="live-pilot-track-toggle"
                            checked={trackChecked}
                            onClick={(event) => event.stopPropagation()}
                            onChange={(event) => toggleSubjectTrack(subjectKey, event.target.checked)}
                            title={trackChecked ? `Hide track for ${pilot.pilotName}` : `Show track for ${pilot.pilotName}`}
                            aria-label={trackChecked ? `Hide track for ${pilot.pilotName}` : `Show track for ${pilot.pilotName}`}
                          />
                          <span className="results-task-map-pilot-rank">
                            <PilotRoleBadge
                              profileType={pilot.profileType}
                              aircraftType={pilot.aircraftType}
                              color={pilot.color ?? "#2563eb"}
                              size={16}
                            />
                          </span>
                          <span className="results-task-map-pilot-copy">
                            <strong style={{ color: pilot.color ?? "#2563eb" }}>{pilot.pilotName}</strong>
                            <small className="live-tracking-pilot-source">
                              {pilot.positionSource === "mesh" ? "Mesh" : pilot.positionSource === "cellular" ? "Phone" : ""}
                              {pilot.positionSource === "mesh" && pilot.deviceId ? (
                                <span className="live-tracking-device-id">{pilot.deviceId}</span>
                              ) : null}
                            </small>
                          </span>
                          <span className="live-tracking-pilot-meta">
                            {pilot.subjectKey && igcTracksByPilot.has(pilot.subjectKey) ? (
                              <span className="status-chip success" style={{ fontSize: "0.625rem", padding: "1px 6px" }}>IGC</span>
                            ) : null}
                            <span className="live-tracking-meta-time">{formatRelativeTime(pilot.timestamp)}</span>
                            <span className="live-tracking-meta-battery">{pilot.batteryLevel != null ? `${pilot.batteryLevel}%` : ""}</span>
                          </span>
                        </div>
                      );
                    })
                  ) : (
                    <div className="results-task-map-empty">
                      {loading
                        ? "Connecting to the live position stream..."
                        : trackingSource?.type === "buddy_group"
                          ? "No recent positions from buddy group pilots."
                          : trackingSource?.type === "all_users"
                            ? "No recent positions from any pilot in the last hour."
                            : "No active pilot tracking for this task yet."}
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
                  optimizedRoute={showTaskMap ? liveTaskDistanceMetrics.routeCoordinates : []}
                  legMetrics={showTaskMap ? liveTaskDistanceMetrics.legMetrics : []}
                  track={liveTrack}
                  telemetryTrack={telemetryTrack}
                  livePositions={livePositions}
                  editable={false}
                  taskEditorOverlay={liveTaskFullscreenOverlay}
                  mode="live"
                  units={units}
                  showGpsButton
                  overlayConfig={overlayConfig}
                  fullscreenSidebar={renderPilotSidebar("live-sidebar live-sidebar-fullscreen")}
                  fullscreenSidebarLabel="pilot list"
                  focusPosition={focusPosition}
                  highlightedLiveSubjectKey={highlightedSubjectKey}
                  fitKey={
                    trackingSource.type === "task"
                      ? `live-${trackingSource.taskId}`
                      : trackingSource.type === "all_users"
                        ? "live-all-users"
                        : `live-buddy-${trackingSource.groupId}`
                  }
                  fitOnceKey={taskFitOnceKey}
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
                          <PilotRoleBadge
                            profileType={pilot.profileType}
                            aircraftType={pilot.aircraftType}
                            color={pilot.color ?? "#2563eb"}
                            size={14}
                          />
                          <strong style={{ color: pilot.color ?? "#2563eb" }}>{pilot.pilotName}</strong>
                        </span>
                      </td>
                      <td>{convertAltitude(pilot.altitudeM, units.altitude)}</td>
                      <td>{convertSpeed(pilot.speedKmh, units.speed)}</td>
                      <td>{pilot.heading != null ? `${Math.round(pilot.heading)} deg` : "-"}</td>
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
