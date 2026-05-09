"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  TaskMap,
  type MapLivePosition,
  type MapTaskPoint,
  type MapTurnpoint,
  type MapUnitPreferences,
} from "../../components/TaskMap";
import { PilotRoleBadge } from "../../components/PilotRoleBadge";
import {
  type LivePositionRecord,
  resolveApiBase,
  formatRelativeTime,
  convertAltitude,
  convertSpeed,
  colorForPilot,
  buildTrackCollection,
  mergePositionGroup,
} from "../../lib/live-tracking-utils";
import { computeTaskOptimization } from "../../lib/taskOptimization";

type PublicEventSource = {
  id: number;
  name: string;
  location: string;
  starts_on: string;
  ends_on: string;
  timezone: string;
  map_task: PublicTaskSource | null;
  tasks: PublicTaskSource[];
};

type PublicTaskSource = { id: number; name: string; status: string; task_date: string | null };

type PublicBuddySource = {
  id: number;
  name: string;
  member_count: number;
};

type PublicSources = {
  events: PublicEventSource[];
  buddy_groups: PublicBuddySource[];
};

type SelectedSource =
  | { type: "all_users" }
  | { type: "event"; eventId: number; eventName: string }
  | { type: "buddies"; groupId: number; groupName: string };

type LivePositionWithName = LivePositionRecord & { pilot_name?: string | null };
type TaskInfoResponse = {
  id: number;
  name: string;
  task_type: string;
  task_date: string | null;
  turnpoints: { position: number; name: string; point_type: string; radius_m: number; latitude: number; longitude: number }[];
};

const defaultUnits: MapUnitPreferences = { altitude: "ft", speed: "mph", distance: "mi", vario: "fpm" };
const allUsersSource: SelectedSource = { type: "all_users" };

function collectPilotNames(positions: LivePositionWithName[]) {
  const names = new Map<number, string>();
  for (const pos of positions) {
    const pilotId = pos.pilot_id;
    if (pilotId != null && pos.pilot_name) {
      names.set(pilotId, pos.pilot_name);
    }
  }
  return names;
}

export function LiveWatchClient() {
  const [sources, setSources] = useState<PublicSources>({ events: [], buddy_groups: [] });
  const [selected, setSelected] = useState<SelectedSource>(allUsersSource);
  const [positionsByPilot, setPositionsByPilot] = useState<Map<number, LivePositionRecord[]>>(new Map());
  const [livePositionsByPilot, setLivePositionsByPilot] = useState<Map<number, LivePositionRecord>>(new Map());
  const [pilotNameById, setPilotNameById] = useState<Map<number, string>>(new Map());
  const [turnpoints, setTurnpoints] = useState<MapTurnpoint[]>([]);
  const [taskPoints, setTaskPoints] = useState<MapTaskPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [overlayConfig, setOverlayConfig] = useState<Record<string, boolean> | undefined>(undefined);
  const sseControllerRef = useRef<AbortController | null>(null);

  const apiBase = useMemo(() => resolveApiBase(), []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${apiBase}/api/public/live/sources`, { cache: "no-store" });
        if (response.ok && !cancelled) {
          setSources((await response.json()) as PublicSources);
        } else if (!response.ok && !cancelled) {
          setError("Unable to load live sources.");
        }
      } catch {
        if (!cancelled) {
          setError("Unable to load live sources.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBase]);

  const activePilotIds = useMemo(() => {
    return Array.from(positionsByPilot.keys()).sort((a, b) => a - b);
  }, [positionsByPilot]);

  const livePositions: MapLivePosition[] = useMemo(() => {
    return Array.from(livePositionsByPilot.entries()).map(([pilotId, pos]) => ({
      id: pos.id,
      pilotId,
      pilotName: pilotNameById.get(pilotId) ?? `Pilot ${pilotId}`,
      latitude: pos.lat,
      longitude: pos.lon,
      altitudeM: pos.alt,
      speedKmh: pos.speed,
      heading: pos.heading,
      timestamp: pos.timestamp,
      batteryLevel: pos.battery_level,
      source: pos.source ?? "unknown",
      color: colorForPilot(pilotId, activePilotIds),
      aircraftType: pos.aircraft_icon ?? "hang_glider",
      profileType: pos.profile_type ?? "pilot",
      positionSource: pos.position_source ?? "other",
    }));
  }, [livePositionsByPilot, pilotNameById, activePilotIds]);

  const track = useMemo(() => buildTrackCollection(positionsByPilot, pilotNameById), [positionsByPilot, pilotNameById]);
  const selectedEventId = selected.type === "event" ? selected.eventId : null;
  const selectedEvent = useMemo(
    () => sources.events.find((event) => event.id === selectedEventId) ?? null,
    [selectedEventId, sources.events],
  );
  const selectedMapTaskId = selectedEvent?.map_task?.id ?? null;
  const taskOverlaysEnabled = overlayConfig
    ? overlayConfig.turnpoints !== false || overlayConfig.task_route !== false || overlayConfig.task_cylinders !== false
    : true;
  const taskDistanceMetrics = useMemo(() => computeTaskOptimization(taskPoints), [taskPoints]);

  useEffect(() => {
    const latest = new Map<number, LivePositionRecord>();
    for (const [pilotId, positions] of positionsByPilot) {
      if (positions.length) {
        latest.set(pilotId, positions[positions.length - 1]);
      }
    }
    setLivePositionsByPilot(latest);
  }, [positionsByPilot]);

  const sourceLabel = useMemo(() => {
    if (selected.type === "event") {
      return selected.eventName;
    }
    if (selected.type === "buddies") {
      return selected.groupName;
    }
    return "All users";
  }, [selected]);

  const sourceDropdownValue = useMemo(() => {
    if (selected.type === "event") {
      return `event:${selected.eventId}`;
    }
    if (selected.type === "buddies") {
      return `buddies:${selected.groupId}`;
    }
    return "all_users";
  }, [selected]);
  const liveMapFitKey = selected.type === "event" && selectedMapTaskId
    ? `${sourceDropdownValue}:task:${selectedMapTaskId}:points:${taskPoints.length}`
    : sourceDropdownValue;

  const connectSSE = useCallback((source: SelectedSource) => {
    sseControllerRef.current?.abort();
    setPositionsByPilot(new Map());
    setLivePositionsByPilot(new Map());
    setPilotNameById(new Map());
    setError("");

    const controller = new AbortController();
    sseControllerRef.current = controller;
    setLoading(true);

    const sourcePath =
      source.type === "event"
        ? `events/${source.eventId}`
        : source.type === "buddies"
          ? `buddies/${source.groupId}`
          : "all";
    const sseUrl = `${apiBase}/api/public/live/${sourcePath}`;
    const historyUrl = `${apiBase}/api/public/live/${sourcePath}/positions?minutes=60&limit=10000`;

    fetch(historyUrl, { cache: "no-store", signal: controller.signal })
      .then((r) => (r.ok ? r.json() : []))
      .then((positions: LivePositionWithName[]) => {
        if (!controller.signal.aborted && positions.length) {
          setPositionsByPilot((current) => mergePositionGroup(current, positions));
          const names = collectPilotNames(positions);
          if (names.size) {
            setPilotNameById((prev) => new Map([...prev, ...names]));
          }
        }
      })
      .catch(() => {});

    (async () => {
      let retryCount = 0;
      while (!controller.signal.aborted) {
        try {
          const response = await fetch(sseUrl, {
            headers: { Accept: "text/event-stream" },
            cache: "no-store",
            signal: controller.signal,
          });
          if (!response.ok || !response.body) {
            throw new Error(`SSE failed: ${response.status}`);
          }
          setLoading(false);
          setError("");
          retryCount = 0;
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          let eventType = "";

          while (!controller.signal.aborted) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() ?? "";
            for (const line of lines) {
              if (line.startsWith("event:")) {
                eventType = line.slice(6).trim();
              } else if (line.startsWith("data:")) {
                const data = line.slice(5).trim();
                if (!data) continue;
                try {
                  const parsed = JSON.parse(data);
                  if (eventType === "snapshot" && Array.isArray(parsed)) {
                    setPositionsByPilot((current) => mergePositionGroup(current, parsed));
                    const names = collectPilotNames(parsed);
                    if (names.size) {
                      setPilotNameById((prev) => new Map([...prev, ...names]));
                    }
                  } else if (eventType === "position" && parsed) {
                    setPositionsByPilot((current) => mergePositionGroup(current, [parsed]));
                    const names = collectPilotNames([parsed]);
                    if (names.size) {
                      setPilotNameById((prev) => new Map([...prev, ...names]));
                    }
                  }
                } catch {
                  // Ignore malformed event payloads without breaking the stream.
                }
                eventType = "";
              }
            }
          }
        } catch {
          if (controller.signal.aborted) break;
          retryCount++;
          setLoading(false);
          setError("Live connection interrupted; retrying...");
          const delay = Math.min(3000 * retryCount, 15000);
          await new Promise((resolve) => setTimeout(resolve, delay));
        }
      }
    })();

    return () => {
      controller.abort();
    };
  }, [apiBase]);

  useEffect(() => {
    const cleanup = connectSSE(selected);
    return cleanup;
  }, [connectSSE, selected]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedMapTaskId || !taskOverlaysEnabled) {
      setTurnpoints([]);
      setTaskPoints([]);
      return () => {
        cancelled = true;
      };
    }

    setTurnpoints([]);
    setTaskPoints([]);
    (async () => {
      try {
        const response = await fetch(`${apiBase}/api/public/live/task/${selectedMapTaskId}/info`, { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`Task info failed: ${response.status}`);
        }
        const task = (await response.json()) as TaskInfoResponse;
        if (cancelled) return;
        const points: MapTaskPoint[] = task.turnpoints.map((point) => ({
          position: point.position,
          point_type: point.point_type,
          radius_m: point.radius_m,
          name: point.name,
          latitude: point.latitude,
          longitude: point.longitude,
        }));
        setTaskPoints(points);
        setTurnpoints(points.map((point) => ({
          id: point.position,
          name: point.name,
          code: null,
          latitude: point.latitude,
          longitude: point.longitude,
        })));
      } catch {
        if (!cancelled) {
          setTurnpoints([]);
          setTaskPoints([]);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [apiBase, selectedMapTaskId, taskOverlaysEnabled]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${apiBase}/api/map-overlay-config/public`);
        if (res.ok) {
          const data = await res.json();
          if (!cancelled && data?.config?.public_live) {
            setOverlayConfig(data.config.public_live);
          }
        }
      } catch {
        // Use map defaults if public overlay configuration is unavailable.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBase]);

  const handleSourceChange = useCallback((value: string) => {
    if (value === "all_users") {
      setSelected(allUsersSource);
      return;
    }
    if (value.startsWith("event:")) {
      const eventId = Number(value.slice(6));
      const event = sources.events.find((item) => item.id === eventId);
      if (event) {
        setSelected({ type: "event", eventId, eventName: event.name });
      }
      return;
    }
    if (value.startsWith("buddies:")) {
      const groupId = Number(value.slice(8));
      const group = sources.buddy_groups.find((item) => item.id === groupId);
      if (group) {
        setSelected({ type: "buddies", groupId, groupName: group.name });
      }
    }
  }, [sources]);

  const renderPilotSidebar = (className = "live-sidebar") => (
    <div className={className}>
      <div className="live-sidebar-header">
        <strong>{sourceLabel}</strong>
        <span>{activePilotIds.length} pilot{activePilotIds.length !== 1 ? "s" : ""}</span>
      </div>
      <div className="live-pilot-list">
        {activePilotIds.length > 0 ? (
          activePilotIds.map((pilotId) => {
            const pos = livePositionsByPilot.get(pilotId);
            const name = pilotNameById.get(pilotId) ?? `Pilot ${pilotId}`;
            const color = colorForPilot(pilotId, activePilotIds);
            return (
              <div key={pilotId} className="live-pilot-row">
                <span className="live-pilot-badge" style={{ color }}>
                  <PilotRoleBadge
                    profileType={pos?.profile_type}
                    aircraftType={pos?.aircraft_icon}
                    color={color}
                    size={16}
                  />
                </span>
                <div className="live-pilot-info">
                  <strong>{name}</strong>
                  <span className="live-pilot-stats">
                    {convertAltitude(pos?.alt ?? null, defaultUnits.altitude)}
                    {pos?.speed != null ? ` - ${convertSpeed(pos.speed, defaultUnits.speed)}` : ""}
                    {pos?.timestamp ? ` - ${formatRelativeTime(pos.timestamp)}` : ""}
                  </span>
                </div>
              </div>
            );
          })
        ) : (
          <div className="live-pilot-empty">
            {loading
              ? "Connecting..."
              : selected.type === "event"
                ? "Waiting for competition pilots..."
                : selected.type === "buddies"
                  ? "Waiting for group pilots..."
                  : "Waiting for pilots..."}
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
    <div className="live-page">
      <header className="live-header">
        <a href="/" className="live-brand" title="Back to Aervyx">
          <svg viewBox="0 0 30 30" width="24" height="24" fill="none">
            <path d="M15 3L27 25L15 19L3 25Z" stroke="#00e5ff" strokeWidth="1.5" fill="none" strokeLinejoin="round"/>
            <circle cx="15" cy="15" r="2.2" fill="#00e5ff" opacity=".85"/>
          </svg>
        </a>
        <span className="live-title">Watch Live</span>
        <div className="live-source-picker">
          <select
            aria-label="Live tracking source"
            value={sourceDropdownValue}
            onChange={(event) => handleSourceChange(event.target.value)}
          >
            <option value="all_users">All users</option>
            {sources.events.length > 0 ? (
              <optgroup label="Competitions">
                {sources.events.map((event) => (
                  <option key={`event:${event.id}`} value={`event:${event.id}`}>
                    {event.name}
                  </option>
                ))}
              </optgroup>
            ) : null}
            {sources.buddy_groups.length > 0 ? (
              <optgroup label="Buddy groups">
                {sources.buddy_groups.map((group) => (
                  <option key={`buddies:${group.id}`} value={`buddies:${group.id}`}>
                    {group.name} ({group.member_count})
                  </option>
                ))}
              </optgroup>
            ) : null}
          </select>
        </div>
      </header>

      <div className="live-body">
        <div className="live-map" style={{ position: "relative" }}>
          <TaskMap
            turnpoints={turnpoints}
            taskPoints={taskPoints}
            livePositions={livePositions}
            track={track}
            optimizedRoute={taskDistanceMetrics.routeCoordinates}
            legMetrics={taskDistanceMetrics.legMetrics}
            mode="live"
            units={defaultUnits}
            editable={false}
            showGpsButton
            overlayConfig={overlayConfig}
            fullscreenSidebar={renderPilotSidebar("live-sidebar live-sidebar-fullscreen")}
            fullscreenSidebarLabel="pilot list"
            fitKey={liveMapFitKey}
          />
        </div>

        {renderPilotSidebar()}
      </div>
    </div>
  );
}
