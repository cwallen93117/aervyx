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
  | { type: "none" }
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
const noSource: SelectedSource = { type: "none" };
const allUsersSource: SelectedSource = { type: "all_users" };

function readNumericSearchParam(name: string): number | null {
  if (typeof window === "undefined") {
    return null;
  }
  const value = new URLSearchParams(window.location.search).get(name);
  if (!value) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function collectPilotNames(positions: LivePositionWithName[]) {
  const names = new Map<string, string>();
  for (const pos of positions) {
    if (pos.pilot_name) {
      names.set(subjectKeyForPosition(pos), pos.pilot_name);
    }
  }
  return names;
}

export function LiveWatchClient() {
  const [sources, setSources] = useState<PublicSources>({ events: [], buddy_groups: [] });
  const [selected, setSelected] = useState<SelectedSource>(allUsersSource);
  const [positionsByPilot, setPositionsByPilot] = useState<Map<string, LivePositionRecord[]>>(new Map());
  const [livePositionsByPilot, setLivePositionsByPilot] = useState<Map<string, LivePositionRecord>>(new Map());
  const [pilotNameById, setPilotNameById] = useState<Map<string, string>>(new Map());
  const [turnpoints, setTurnpoints] = useState<MapTurnpoint[]>([]);
  const [taskPoints, setTaskPoints] = useState<MapTaskPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [sourcesLoaded, setSourcesLoaded] = useState(false);
  const [eventFitRequestId, setEventFitRequestId] = useState(0);
  const [overlayConfig, setOverlayConfig] = useState<Record<string, boolean> | undefined>(undefined);
  const [hasInitialEventParam, setHasInitialEventParam] = useState(false);
  const [initialEventId, setInitialEventId] = useState<number | null>(null);
  const [returnScoresEventId, setReturnScoresEventId] = useState<number | null>(null);
  const [hasAppliedInitialEvent, setHasAppliedInitialEvent] = useState(false);
  const [focusPosition, setFocusPosition] = useState<{ lat: number; lon: number; key: string | number } | null>(null);
  const [highlightedSubjectKey, setHighlightedSubjectKey] = useState<string | null>(null);
  const [visibleTrackSubjectKeys, setVisibleTrackSubjectKeys] = useState<Set<string>>(() => new Set());
  const sseControllerRef = useRef<AbortController | null>(null);
  const focusRequestIdRef = useRef(0);

  const apiBase = useMemo(() => resolveApiBase(), []);
  const streamApiBase = useMemo(() => resolveStreamApiBase(), []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    setHasInitialEventParam(params.has("event_id"));
    setInitialEventId(readNumericSearchParam("event_id"));
    setReturnScoresEventId(readNumericSearchParam("scores_event_id") ?? readNumericSearchParam("event_id"));
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${apiBase}/api/public/live/sources`, { cache: "no-store" });
        if (response.ok && !cancelled) {
          setSources((await response.json()) as PublicSources);
        }
      } catch {
        // Keep the public watch header quiet if sources are temporarily unavailable.
      } finally {
        if (!cancelled) {
          setSourcesLoaded(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBase]);

  const activePilotIds = useMemo(() => {
    return Array.from(positionsByPilot.keys()).sort();
  }, [positionsByPilot]);

  const livePositions: MapLivePosition[] = useMemo(() => {
    return Array.from(livePositionsByPilot.entries()).map(([subjectKey, pos]) => ({
      id: pos.id,
      subjectKey,
      pilotId: pos.pilot_id,
      userId: pos.user_id ?? null,
      pilotName: displayNameForSubject(pos, pilotNameById),
      latitude: pos.lat,
      longitude: pos.lon,
      altitudeM: pos.alt,
      speedKmh: pos.speed,
      heading: pos.heading,
      timestamp: pos.timestamp,
      batteryLevel: pos.battery_level,
      source: pos.source ?? "unknown",
      color: colorForSubject(subjectKey, activePilotIds),
      aircraftType: pos.aircraft_icon ?? "hang_glider",
      profileType: pos.profile_type ?? "pilot",
      positionSource: pos.position_source ?? "other",
    }));
  }, [livePositionsByPilot, pilotNameById, activePilotIds]);

  const telemetryTrack = useMemo(() => buildTrackCollection(positionsByPilot, pilotNameById), [positionsByPilot, pilotNameById]);
  const visibleTrackPositionsByPilot = useMemo(() => {
    const next = new Map<string, LivePositionRecord[]>();
    for (const [subjectKey, positions] of positionsByPilot) {
      if (visibleTrackSubjectKeys.has(subjectKey)) {
        next.set(subjectKey, positions);
      }
    }
    return next;
  }, [positionsByPilot, visibleTrackSubjectKeys]);
  const visibleTrack = useMemo(
    () => buildTrackCollection(visibleTrackPositionsByPilot, pilotNameById),
    [pilotNameById, visibleTrackPositionsByPilot],
  );
  const allLiveTracksChecked = useMemo(
    () => activePilotIds.length > 0 && activePilotIds.every((subjectKey) => visibleTrackSubjectKeys.has(subjectKey)),
    [activePilotIds, visibleTrackSubjectKeys],
  );
  const selectedEventId = selected.type === "event" ? selected.eventId : null;
  const selectedEvent = useMemo(
    () => sources.events.find((event) => event.id === selectedEventId) ?? null,
    [selectedEventId, sources.events],
  );
  const selectedMapTaskId = selectedEvent?.map_task?.id ?? null;
  const taskDistanceMetrics = useMemo(() => computeTaskOptimization(taskPoints), [taskPoints]);
  const taskFitGeometryKey = useMemo(
    () => taskPoints.map((point) => `${point.position}:${point.latitude.toFixed(6)}:${point.longitude.toFixed(6)}:${point.radius_m}`).join("|"),
    [taskPoints],
  );

  useEffect(() => {
    setLivePositionsByPilot(latestDisplayPositionsBySubject(positionsByPilot));
  }, [positionsByPilot]);

  const sourceLabel = useMemo(() => {
    if (selected.type === "event") {
      return selected.eventName;
    }
    if (selected.type === "buddies") {
      return selected.groupName;
    }
    if (selected.type === "none") {
      return "Select a live source";
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
    if (selected.type === "none") {
      return "";
    }
    return "all_users";
  }, [selected]);
  const eventFitOnceKey = selected.type === "event" && selectedMapTaskId && taskPoints.length > 0 && eventFitRequestId > 0
    ? `event-select:${eventFitRequestId}:task:${selectedMapTaskId}:${taskFitGeometryKey}`
    : null;

  const connectSSE = useCallback((source: SelectedSource) => {
    sseControllerRef.current?.abort();
    setPositionsByPilot(new Map());
    setLivePositionsByPilot(new Map());
    setPilotNameById(new Map());
    setHighlightedSubjectKey(null);
    setFocusPosition(null);
    setVisibleTrackSubjectKeys(new Set());

    if (source.type === "none") {
      setLoading(false);
      return () => {};
    }

    const controller = new AbortController();
    sseControllerRef.current = controller;
    setLoading(true);

    const sourcePath =
      source.type === "event"
        ? `events/${source.eventId}`
        : source.type === "buddies"
          ? `buddies/${source.groupId}`
          : "all";
    const sseUrl = `${streamApiBase}/api/public/live/${sourcePath}`;
    const historyUrl = `${apiBase}/api/public/live/${sourcePath}/positions`;

    const mergePositions = (positions: LivePositionWithName[]) => {
      if (controller.signal.aborted || !positions.length) {
        return;
      }
      const publicPositions = positions.filter((position) => position.pilot_id != null || position.user_id != null);
      if (!publicPositions.length) {
        return;
      }
      setPositionsByPilot((current) => mergePositionGroup(current, publicPositions));
      const names = collectPilotNames(publicPositions);
      if (names.size) {
        setPilotNameById((prev) => new Map([...prev, ...names]));
      }
    };

    fetch(historyUrl, { cache: "no-store", signal: controller.signal })
      .then((r) => (r.ok ? r.json() : []))
      .then((positions: LivePositionWithName[]) => mergePositions(positions))
      .catch(() => {});

    const eventSource = new EventSource(sseUrl);

    eventSource.onopen = () => {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    };

    eventSource.onerror = () => {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    };

    const handleSnapshot = (event: MessageEvent<string>) => {
      if (controller.signal.aborted) {
        return;
      }
      try {
        const parsed = JSON.parse(event.data);
        if (Array.isArray(parsed)) {
          mergePositions(parsed);
        }
      } catch {
        // Ignore malformed event payloads without breaking the stream.
      }
    };

    const handlePosition = (event: MessageEvent<string>) => {
      if (controller.signal.aborted) {
        return;
      }
      try {
        const parsed = JSON.parse(event.data);
        if (parsed) {
          mergePositions([parsed]);
        }
      } catch {
        // Ignore malformed event payloads without breaking the stream.
      }
    };

    eventSource.addEventListener("snapshot", handleSnapshot);
    eventSource.addEventListener("position", handlePosition);

    return () => {
      controller.abort();
      eventSource.close();
    };
  }, [apiBase, streamApiBase]);

  useEffect(() => {
    if (!sourcesLoaded || hasAppliedInitialEvent || !hasInitialEventParam) {
      return;
    }
    if (initialEventId != null) {
      const event = sources.events.find((item) => item.id === initialEventId);
      if (event) {
        setSelected({ type: "event", eventId: event.id, eventName: event.name });
        setEventFitRequestId((current) => current + 1);
      } else {
        setSelected(noSource);
      }
    } else {
      setSelected(noSource);
    }
    setHasAppliedInitialEvent(true);
  }, [hasAppliedInitialEvent, hasInitialEventParam, initialEventId, sources.events, sourcesLoaded]);

  useEffect(() => {
    const cleanup = connectSSE(selected);
    return cleanup;
  }, [connectSSE, selected]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedMapTaskId) {
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
  }, [apiBase, selectedMapTaskId]);

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
    if (value === "") {
      setSelected(noSource);
      return;
    }
    if (value === "all_users") {
      setSelected(allUsersSource);
      return;
    }
    if (value.startsWith("event:")) {
      const eventId = Number(value.slice(6));
      const event = sources.events.find((item) => item.id === eventId);
      if (event) {
        setSelected({ type: "event", eventId, eventName: event.name });
        setEventFitRequestId((current) => current + 1);
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

  const requestSelectedEventFit = useCallback(() => {
    if (selected.type === "event") {
      setEventFitRequestId((current) => current + 1);
    }
  }, [selected]);

  const latestPositionForSubject = useCallback((subjectKey: string) => {
    const current = livePositionsByPilot.get(subjectKey);
    if (current) {
      return current;
    }
    const history = positionsByPilot.get(subjectKey);
    return history && history.length > 0 ? history[history.length - 1] : null;
  }, [livePositionsByPilot, positionsByPilot]);

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
      return new Set(activePilotIds);
    });
  }, [activePilotIds, allLiveTracksChecked]);

  const compScoresHref = useMemo(() => {
    const eventId = returnScoresEventId ?? selectedEventId;
    return eventId != null ? `/scores?event_id=${encodeURIComponent(String(eventId))}` : "/scores";
  }, [returnScoresEventId, selectedEventId]);

  const renderPilotSidebar = (className = "live-sidebar") => (
    <div className={className}>
      <div className="live-sidebar-header">
        <div className="live-sidebar-title">
          <strong>{sourceLabel}</strong>
          <span>{activePilotIds.length} pilot{activePilotIds.length !== 1 ? "s" : ""}</span>
        </div>
        <label className="live-track-master-toggle" title={allLiveTracksChecked ? "Hide all tracks" : "Show all tracks"}>
          <input
            type="checkbox"
            checked={allLiveTracksChecked}
            disabled={!activePilotIds.length}
            onChange={toggleAllLiveTracks}
          />
          <span>Tracks</span>
        </label>
      </div>
      <div className="live-pilot-list">
        {activePilotIds.length > 0 ? (
          activePilotIds.map((pilotId) => {
            const pos = latestPositionForSubject(pilotId);
            const name = pos ? displayNameForSubject(pos, pilotNameById) : pilotNameById.get(pilotId) ?? pilotId;
            const color = colorForSubject(pilotId, activePilotIds);
            const isHighlighted = highlightedSubjectKey === pilotId;
            const trackChecked = visibleTrackSubjectKeys.has(pilotId);
            return (
              <div
                key={pilotId}
                className={`live-pilot-row${isHighlighted ? " is-highlighted" : ""}`}
              >
                <input
                  type="checkbox"
                  className="live-pilot-track-toggle"
                  checked={trackChecked}
                  onChange={(event) => toggleSubjectTrack(pilotId, event.target.checked)}
                  title={trackChecked ? `Hide track for ${name}` : `Show track for ${name}`}
                  aria-label={trackChecked ? `Hide track for ${name}` : `Show track for ${name}`}
                />
                <button
                  type="button"
                  className="live-pilot-main"
                  onClick={() => focusSubjectOnMap(pilotId)}
                  aria-pressed={isHighlighted}
                  disabled={!pos}
                  title={pos ? `${isHighlighted ? "Hide details for" : "Center map on"} ${name}` : undefined}
                >
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
                </button>
              </div>
            );
          })
        ) : (
          <div className="live-pilot-empty">
            {loading
              ? "Connecting..."
              : selected.type === "none"
                ? "Choose a live source."
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
            onClick={requestSelectedEventFit}
          >
            {selected.type === "none" ? <option value="">Select live source</option> : null}
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
        <a href={compScoresHref} className="public-header-link public-header-link-scores">Comp Scores</a>
      </header>

      <div className="live-body">
        <div className="live-map" style={{ position: "relative" }}>
          <TaskMap
            turnpoints={turnpoints}
            taskPoints={taskPoints}
            livePositions={livePositions}
            track={visibleTrack}
            telemetryTrack={telemetryTrack}
            optimizedRoute={taskDistanceMetrics.routeCoordinates}
            legMetrics={taskDistanceMetrics.legMetrics}
            mode="live"
            units={defaultUnits}
            editable={false}
            showGpsButton
            enableLivePositionPopups
            overlayConfig={overlayConfig}
            fullscreenSidebar={renderPilotSidebar("live-sidebar live-sidebar-fullscreen")}
            fullscreenSidebarLabel="pilot list"
            focusPosition={focusPosition}
            highlightedLiveSubjectKey={highlightedSubjectKey}
            fitKey={sourceDropdownValue}
            fitOnceKey={eventFitOnceKey}
          />
        </div>

        {renderPilotSidebar()}
      </div>
    </div>
  );
}
