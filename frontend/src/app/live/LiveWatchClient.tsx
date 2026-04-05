"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  TaskMap,
  type MapLivePosition,
  type MapTaskPoint,
  type MapTurnpoint,
  type MapUnitPreferences,
} from "../../components/TaskMap";
import {
  TRACK_COLORS,
  type LivePositionRecord,
  resolveApiBase,
  formatRelativeTime,
  convertAltitude,
  convertSpeed,
  colorForPilot,
  buildTrackCollection,
  mergePositionGroup,
} from "../../lib/live-tracking-utils";

type PublicEventSource = {
  id: number;
  name: string;
  location: string;
  starts_on: string;
  ends_on: string;
  tasks: { id: number; name: string; status: string; task_date: string | null }[];
};

type PublicBuddySource = {
  id: number;
  name: string;
  member_count: number;
};

type PublicSources = {
  events: PublicEventSource[];
  buddy_groups: PublicBuddySource[];
};

type TaskInfoResponse = {
  name: string;
  task_type: string;
  task_date: string | null;
  turnpoints: { position: number; name: string; point_type: string; radius_m: number; latitude: number; longitude: number }[];
};

type SelectedSource =
  | { type: "task"; taskId: number; eventName: string }
  | { type: "buddies"; groupId: number; groupName: string }
  | null;

const defaultUnits: MapUnitPreferences = { altitude: "ft", speed: "mph", distance: "mi", vario: "fpm" };

export function LiveWatchClient() {
  const [sources, setSources] = useState<PublicSources | null>(null);
  const [selected, setSelected] = useState<SelectedSource>(null);
  const [positionsByPilot, setPositionsByPilot] = useState<Map<number, LivePositionRecord[]>>(new Map());
  const [livePositionsByPilot, setLivePositionsByPilot] = useState<Map<number, LivePositionRecord>>(new Map());
  const [pilotNameById, setPilotNameById] = useState<Map<number, string>>(new Map());
  const [turnpoints, setTurnpoints] = useState<MapTurnpoint[]>([]);
  const [taskPoints, setTaskPoints] = useState<MapTaskPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const sseControllerRef = useRef<AbortController | null>(null);

  const apiBase = useMemo(() => resolveApiBase(), []);

  // Fetch available public sources on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${apiBase}/api/public/live/sources`, { cache: "no-store" });
        if (response.ok && !cancelled) {
          setSources(await response.json());
        }
      } catch {
        if (!cancelled) setError("Unable to load live sources");
      }
    })();
    return () => { cancelled = true; };
  }, [apiBase]);

  // Derived: active pilot IDs sorted for consistent coloring
  const activePilotIds = useMemo(() => {
    return Array.from(positionsByPilot.keys()).sort((a, b) => a - b);
  }, [positionsByPilot]);

  // Build live position markers for map
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
    }));
  }, [livePositionsByPilot, pilotNameById, activePilotIds]);

  // Build track collection for map
  const track = useMemo(() => buildTrackCollection(positionsByPilot, pilotNameById), [positionsByPilot, pilotNameById]);

  // Update latest position per pilot when positionsByPilot changes
  useEffect(() => {
    const latest = new Map<number, LivePositionRecord>();
    for (const [pilotId, positions] of positionsByPilot) {
      if (positions.length) {
        latest.set(pilotId, positions[positions.length - 1]);
      }
    }
    setLivePositionsByPilot(latest);
  }, [positionsByPilot]);

  // Connect SSE when source changes
  const connectSSE = useCallback((source: SelectedSource) => {
    sseControllerRef.current?.abort();
    setPositionsByPilot(new Map());
    setLivePositionsByPilot(new Map());
    setPilotNameById(new Map());
    setTurnpoints([]);
    setTaskPoints([]);
    setError("");

    if (!source) return;

    const controller = new AbortController();
    sseControllerRef.current = controller;
    setLoading(true);

    const sseUrl = source.type === "task"
      ? `${apiBase}/api/public/live/task/${source.taskId}`
      : `${apiBase}/api/public/live/buddies/${source.groupId}`;

    const historyUrl = source.type === "task"
      ? `${apiBase}/api/public/live/task/${source.taskId}/positions`
      : `${apiBase}/api/public/live/buddies/${source.groupId}/positions`;

    // Fetch task info for turnpoints
    if (source.type === "task") {
      fetch(`${apiBase}/api/public/live/task/${source.taskId}/info`, { cache: "no-store", signal: controller.signal })
        .then((r) => r.ok ? r.json() : null)
        .then((info: TaskInfoResponse | null) => {
          if (info && !controller.signal.aborted) {
            setTurnpoints(info.turnpoints.map((tp) => ({
              id: tp.position,
              name: tp.name,
              code: "",
              latitude: tp.latitude,
              longitude: tp.longitude,
            })));
            setTaskPoints(info.turnpoints.map((tp) => ({
              position: tp.position,
              point_type: tp.point_type,
              radius_m: tp.radius_m,
              name: tp.name,
              latitude: tp.latitude,
              longitude: tp.longitude,
            })));
          }
        })
        .catch(() => {});
    }

    // Fetch position history
    fetch(historyUrl, { cache: "no-store", signal: controller.signal })
      .then((r) => r.ok ? r.json() : [])
      .then((positions: LivePositionRecord[]) => {
        if (!controller.signal.aborted && positions.length) {
          setPositionsByPilot((current) => mergePositionGroup(current, positions));
          // Build pilot name map from position data
          const names = new Map<number, string>();
          for (const pos of positions) {
            const pid = pos.pilot_id ?? 0;
            if (!names.has(pid)) {
              names.set(pid, (pos as Record<string, unknown>).pilot_name as string ?? `Pilot ${pid}`);
            }
          }
          if (names.size) setPilotNameById((prev) => new Map([...prev, ...names]));
        }
      })
      .catch(() => {});

    // Open SSE connection
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
                    const names = new Map<number, string>();
                    for (const pos of parsed) {
                      const pid = pos.pilot_id ?? 0;
                      if (pos.pilot_name) names.set(pid, pos.pilot_name);
                    }
                    if (names.size) setPilotNameById((prev) => new Map([...prev, ...names]));
                  } else if (eventType === "position" && parsed) {
                    setPositionsByPilot((current) => mergePositionGroup(current, [parsed]));
                    if (parsed.pilot_name && parsed.pilot_id != null) {
                      setPilotNameById((prev) => new Map([...prev, [parsed.pilot_id, parsed.pilot_name]]));
                    }
                  }
                } catch { /* ignore parse errors */ }
                eventType = "";
              }
            }
          }
        } catch (err) {
          if (controller.signal.aborted) break;
          retryCount++;
          setLoading(false);
          const delay = Math.min(3000 * retryCount, 15000);
          await new Promise((resolve) => setTimeout(resolve, delay));
        }
      }
    })();

    return () => {
      controller.abort();
    };
  }, [apiBase]);

  // Reconnect when selection changes
  useEffect(() => {
    const cleanup = connectSSE(selected);
    return cleanup;
  }, [selected, connectSSE]);

  // Handle dropdown change
  function handleSourceChange(value: string) {
    if (!value) {
      setSelected(null);
      return;
    }
    if (value.startsWith("task:")) {
      const taskId = Number(value.slice(5));
      const event = sources?.events.find((e) => e.tasks.some((t) => t.id === taskId));
      setSelected({ type: "task", taskId, eventName: event?.name ?? "Event" });
    } else if (value.startsWith("buddies:")) {
      const groupId = Number(value.slice(8));
      const group = sources?.buddy_groups.find((g) => g.id === groupId);
      setSelected({ type: "buddies", groupId, groupName: group?.name ?? "Group" });
    }
  }

  const hasAnySources = (sources?.events.length ?? 0) > 0 || (sources?.buddy_groups.length ?? 0) > 0;
  const dropdownValue = selected
    ? selected.type === "task" ? `task:${selected.taskId}` : `buddies:${selected.groupId}`
    : "";

  return (
    <div className="live-page">
      {/* Header */}
      <header className="live-header">
        <a href="/" className="live-brand" title="Back to Aervyx">
          <svg viewBox="0 0 30 30" width="24" height="24" fill="none">
            <path d="M15 3L27 25L15 19L3 25Z" stroke="#00e5ff" strokeWidth="1.5" fill="none" strokeLinejoin="round"/>
            <circle cx="15" cy="15" r="2.2" fill="#00e5ff" opacity=".85"/>
          </svg>
        </a>
        <span className="live-title">Watch Live</span>
        <div className="live-source-picker">
          <select value={dropdownValue} onChange={(e) => handleSourceChange(e.target.value)}>
            <option value="">Select a source...</option>
            {sources?.events.map((event) =>
              event.tasks.map((task) => (
                <option key={`task:${task.id}`} value={`task:${task.id}`}>
                  {event.name} — {task.name}
                </option>
              ))
            )}
            {sources?.buddy_groups.map((group) => (
              <option key={`buddies:${group.id}`} value={`buddies:${group.id}`}>
                Buddy: {group.name} ({group.member_count})
              </option>
            ))}
          </select>
        </div>
        {loading ? <span className="live-status">Connecting...</span> : null}
        {error ? <span className="live-status live-status-error">{error}</span> : null}
      </header>

      {/* Body */}
      <div className="live-body">
        <div className="live-map">
          {selected ? (
            <TaskMap
              turnpoints={turnpoints}
              taskPoints={taskPoints}
              livePositions={livePositions}
              track={track}
              mode="live"
              units={defaultUnits}
              editable={false}
              showGpsButton
            />
          ) : (
            <div className="live-empty">
              <svg viewBox="0 0 48 48" width="48" height="48" fill="none" style={{ opacity: 0.3, marginBottom: 12 }}>
                <path d="M24 4L44 40L24 32L4 40Z" stroke="currentColor" strokeWidth="2" fill="none" strokeLinejoin="round"/>
                <circle cx="24" cy="24" r="3" fill="currentColor" opacity=".6"/>
              </svg>
              {hasAnySources ? (
                <p>Select an event or buddy group above to watch live tracking.</p>
              ) : sources ? (
                <>
                  <p>No public live tracking sources are currently available.</p>
                  <p style={{ fontSize: "0.8125rem", marginTop: 8, opacity: 0.6 }}>Event organizers can enable public tracking in their event settings.</p>
                </>
              ) : (
                <p>Loading...</p>
              )}
            </div>
          )}
        </div>

        {/* Pilot sidebar */}
        {selected && activePilotIds.length > 0 ? (
          <div className="live-sidebar">
            <div className="live-sidebar-header">
              <strong>{selected.type === "task" ? selected.eventName : selected.groupName}</strong>
              <span>{activePilotIds.length} pilot{activePilotIds.length !== 1 ? "s" : ""}</span>
            </div>
            <div className="live-pilot-list">
              {activePilotIds.map((pilotId) => {
                const pos = livePositionsByPilot.get(pilotId);
                const name = pilotNameById.get(pilotId) ?? `Pilot ${pilotId}`;
                const color = colorForPilot(pilotId, activePilotIds);
                return (
                  <div key={pilotId} className="live-pilot-row">
                    <span className="live-pilot-dot" style={{ background: color }} />
                    <div className="live-pilot-info">
                      <strong>{name}</strong>
                      <span className="live-pilot-stats">
                        {convertAltitude(pos?.alt ?? null, defaultUnits.altitude)}
                        {pos?.speed != null ? ` · ${convertSpeed(pos.speed, defaultUnits.speed)}` : ""}
                        {pos?.timestamp ? ` · ${formatRelativeTime(pos.timestamp)}` : ""}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
