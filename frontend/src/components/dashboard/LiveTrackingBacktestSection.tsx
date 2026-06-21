"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  TaskMap,
  type MapLivePosition,
  type MapTaskPoint,
  type MapTurnpoint,
  type MapUnitPreferences,
  type TrackCollection,
} from "../TaskMap";
import { SectionCard } from "../SectionCard";
import {
  type LivePositionRecord,
  buildTrackCollection,
  colorForSubject,
  convertAltitude,
  convertSpeed,
  displayNameForSubject,
  displayPositionsForLiveTrack,
  resolveApiBase,
  subjectKeyForPosition,
} from "../../lib/live-tracking-utils";
import { computeTaskOptimization } from "../../lib/taskOptimization";

type SourceFilter = "merged" | "cell" | "mesh";

type BacktestPilot = {
  id: number;
  pilot_name: string;
  competition_number: string | null;
  point_count: number;
};

type BacktestTask = {
  id: number;
  event_id: number;
  name: string;
  status: string;
  task_date: string | null;
  pilots: BacktestPilot[];
};

type BacktestEvent = {
  id: number;
  name: string;
  location: string;
  starts_on: string;
  ends_on: string;
  timezone: string;
  tasks: BacktestTask[];
};

type BacktestTaskPoint = {
  position: number;
  name: string;
  point_type: string;
  radius_m: number;
  latitude: number;
  longitude: number;
};

type BacktestPoint = LivePositionRecord & {
  created_at?: string | null;
  battery_level_seen_at?: string | null;
  raw_metadata?: Record<string, unknown>;
};

type BacktestSourcesResponse = {
  events: BacktestEvent[];
};

type BacktestTrackResponse = {
  event: BacktestEvent;
  task: BacktestTask;
  pilot: BacktestPilot;
  task_points: BacktestTaskPoint[];
  raw_points: BacktestPoint[];
};

export interface LiveTrackingBacktestSectionProps {
  token: string;
  units: MapUnitPreferences;
  overlayConfig?: Record<string, boolean>;
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  });
}

function isHc2026(event: BacktestEvent) {
  return /hc\s*2026/i.test(event.name) || (/\bhc\b/i.test(event.name) && /2026/.test(event.name));
}

function firstTaskWithTrackData(event: BacktestEvent | null) {
  if (!event) return null;
  return event.tasks.find((task) => task.pilots.some((pilot) => pilot.point_count > 0)) ?? event.tasks[0] ?? null;
}

function firstPilotWithTrackData(task: BacktestTask | null) {
  if (!task) return null;
  return task.pilots.find((pilot) => pilot.point_count > 0) ?? task.pilots[0] ?? null;
}

function mapTaskPoint(point: BacktestTaskPoint): MapTaskPoint {
  return {
    position: point.position,
    point_type: point.point_type,
    radius_m: point.radius_m,
    name: point.name,
    latitude: point.latitude,
    longitude: point.longitude,
  };
}

function sourceMatches(position: LivePositionRecord, sourceFilter: SourceFilter) {
  if (sourceFilter === "cell") {
    return position.position_source === "cellular" || position.source === "app";
  }
  if (sourceFilter === "mesh") {
    return position.position_source === "mesh" || position.source === "mqtt_gateway" || position.source === "mesh_relay";
  }
  return true;
}

function rawTrackCollection(
  positions: BacktestPoint[],
  sourceFilter: SourceFilter,
  subjectKey: string,
  pilotName: string,
): TrackCollection | null {
  const filtered = positions.filter((position) => sourceMatches(position, sourceFilter));
  if (filtered.length < 2) return null;
  const lineStyle = sourceFilter === "mesh" ? "dashed" : "solid";
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {
          subject_key: subjectKey,
          pilot_id: filtered[filtered.length - 1]?.pilot_id ?? null,
          pilot_name: pilotName,
          color: "#2563eb",
          aircraft_icon: filtered[filtered.length - 1]?.aircraft_icon ?? "hang_glider",
          profile_type: filtered[filtered.length - 1]?.profile_type ?? "pilot",
          timestamps: filtered.map((position) => position.timestamp),
          segment_index: 0,
          segment_count: 1,
          segment_start_timestamp: filtered[0]?.timestamp ?? null,
          segment_end_timestamp: filtered[filtered.length - 1]?.timestamp ?? null,
          display_source: sourceFilter === "mesh" ? "mesh" : "cellular",
          line_style: lineStyle,
        },
        geometry: {
          type: "LineString",
          coordinates: filtered.map((position) => [position.lon, position.lat, position.alt ?? 0] as [number, number, number]),
        },
      },
    ],
  };
}

function diagnosticFlags(points: BacktestPoint[]) {
  const duplicateKeys = new Set<string>();
  const seen = new Set<string>();
  points.forEach((point) => {
    const key = `${point.timestamp}|${point.lat.toFixed(6)}|${point.lon.toFixed(6)}|${point.source ?? ""}|${point.device_id ?? ""}`;
    if (seen.has(key)) duplicateKeys.add(point.id);
    seen.add(key);
  });
  return points.map((point, index) => {
    const flags: string[] = [];
    const previous = points[index - 1];
    if (previous) {
      const currentMs = Date.parse(point.timestamp);
      const previousMs = Date.parse(previous.timestamp);
      if (Number.isFinite(currentMs) && Number.isFinite(previousMs)) {
        if (currentMs < previousMs) flags.push("out-of-order");
        if (currentMs - previousMs > 120_000) flags.push("gap");
      }
    }
    if (duplicateKeys.has(point.id)) flags.push("duplicate");
    return flags;
  });
}

export default function LiveTrackingBacktestSection({ token, units, overlayConfig }: LiveTrackingBacktestSectionProps) {
  const apiBase = useMemo(() => resolveApiBase(), []);
  const [events, setEvents] = useState<BacktestEvent[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [selectedPilotId, setSelectedPilotId] = useState<number | null>(null);
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("merged");
  const [trackData, setTrackData] = useState<BacktestTrackResponse | null>(null);
  const [loadingSources, setLoadingSources] = useState(false);
  const [loadingTrack, setLoadingTrack] = useState(false);
  const [error, setError] = useState("");
  const [currentIndex, setCurrentIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const currentRowRef = useRef<HTMLTableRowElement | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setLoadingSources(true);
    setError("");
    (async () => {
      try {
        const response = await fetch(`${apiBase}/api/admin/live-backtest/sources`, {
          headers: { Authorization: `Bearer ${token}` },
          cache: "no-store",
        });
        if (!response.ok) throw new Error(`Backtest sources failed: ${response.status}`);
        const payload = (await response.json()) as BacktestSourcesResponse;
        if (cancelled) return;
        setEvents(payload.events);
        const defaultEvent = payload.events.find(isHc2026) ?? payload.events[0] ?? null;
        const defaultTask = firstTaskWithTrackData(defaultEvent);
        const defaultPilot = firstPilotWithTrackData(defaultTask);
        setSelectedEventId(defaultEvent?.id ?? null);
        setSelectedTaskId(defaultTask?.id ?? null);
        setSelectedPilotId(defaultPilot?.id ?? null);
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "Backtest sources failed.");
      } finally {
        if (!cancelled) setLoadingSources(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBase, token]);

  const selectedEvent = useMemo(
    () => events.find((event) => event.id === selectedEventId) ?? null,
    [events, selectedEventId],
  );
  const selectedTask = useMemo(
    () => selectedEvent?.tasks.find((task) => task.id === selectedTaskId) ?? null,
    [selectedEvent, selectedTaskId],
  );
  const selectedPilot = useMemo(
    () => selectedTask?.pilots.find((pilot) => pilot.id === selectedPilotId) ?? null,
    [selectedPilotId, selectedTask],
  );

  const handleEventChange = useCallback((eventId: number) => {
    const nextEvent = events.find((event) => event.id === eventId) ?? null;
    const nextTask = firstTaskWithTrackData(nextEvent);
    const nextPilot = firstPilotWithTrackData(nextTask);
    setSelectedEventId(nextEvent?.id ?? null);
    setSelectedTaskId(nextTask?.id ?? null);
    setSelectedPilotId(nextPilot?.id ?? null);
  }, [events]);

  const handleTaskChange = useCallback((taskId: number) => {
    const nextTask = selectedEvent?.tasks.find((task) => task.id === taskId) ?? null;
    const nextPilot = firstPilotWithTrackData(nextTask);
    setSelectedTaskId(nextTask?.id ?? null);
    setSelectedPilotId(nextPilot?.id ?? null);
  }, [selectedEvent]);

  useEffect(() => {
    if (!token || selectedTaskId == null || selectedPilotId == null) {
      setTrackData(null);
      return;
    }
    let cancelled = false;
    setLoadingTrack(true);
    setError("");
    (async () => {
      try {
        const params = new URLSearchParams({ task_id: String(selectedTaskId), pilot_id: String(selectedPilotId) });
        const response = await fetch(`${apiBase}/api/admin/live-backtest/track?${params}`, {
          headers: { Authorization: `Bearer ${token}` },
          cache: "no-store",
        });
        if (!response.ok) throw new Error(`Backtest track failed: ${response.status}`);
        const payload = (await response.json()) as BacktestTrackResponse;
        if (cancelled) return;
        setTrackData(payload);
        setCurrentIndex(0);
        setPlaying(false);
      } catch (caught) {
        if (!cancelled) {
          setTrackData(null);
          setError(caught instanceof Error ? caught.message : "Backtest track failed.");
        }
      } finally {
        if (!cancelled) setLoadingTrack(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBase, selectedPilotId, selectedTaskId, token]);

  const rawPoints = trackData?.raw_points ?? [];
  const safeCurrentIndex = rawPoints.length ? Math.min(currentIndex, rawPoints.length - 1) : 0;
  const currentPoint = rawPoints[safeCurrentIndex] ?? null;
  const replayPoints = rawPoints.slice(0, safeCurrentIndex + 1);
  const subjectKey = currentPoint ? subjectKeyForPosition(currentPoint) : selectedPilotId != null ? `pilot:${selectedPilotId}` : "pilot:backtest";
  const pilotName = trackData?.pilot.pilot_name ?? selectedPilot?.pilot_name ?? "Pilot";
  const pilotNameBySubject = useMemo(() => new Map([[subjectKey, pilotName]]), [pilotName, subjectKey]);
  const activeSubjects = useMemo(() => [subjectKey], [subjectKey]);
  const nowMs = currentPoint ? Date.parse(currentPoint.received_at ?? currentPoint.timestamp) + 2_000 : Date.now();

  const replayTrack = useMemo<TrackCollection | null>(() => {
    if (!replayPoints.length) return null;
    if (sourceFilter === "merged") {
      return buildTrackCollection(new Map([[subjectKey, replayPoints]]), pilotNameBySubject, activeSubjects, { nowMs });
    }
    return rawTrackCollection(replayPoints, sourceFilter, subjectKey, pilotName);
  }, [activeSubjects, nowMs, pilotName, pilotNameBySubject, replayPoints, sourceFilter, subjectKey]);

  const mergedIncludedIds = useMemo(() => {
    return new Set(displayPositionsForLiveTrack(replayPoints, { nowMs }).map((point) => point.id));
  }, [nowMs, replayPoints]);

  const mapTaskPoints = useMemo(() => (trackData?.task_points ?? []).map(mapTaskPoint), [trackData]);
  const mapTurnpoints = useMemo<MapTurnpoint[]>(
    () => mapTaskPoints.map((point) => ({
      id: point.position,
      name: point.name,
      code: null,
      latitude: point.latitude,
      longitude: point.longitude,
    })),
    [mapTaskPoints],
  );
  const taskDistanceMetrics = useMemo(() => computeTaskOptimization(mapTaskPoints), [mapTaskPoints]);
  const markerPoint = useMemo(() => {
    if (!currentPoint) return null;
    if (sourceFilter === "merged") {
      const display = displayPositionsForLiveTrack(replayPoints, { nowMs });
      return display[display.length - 1] ?? currentPoint;
    }
    const filtered = replayPoints.filter((point) => sourceMatches(point, sourceFilter));
    return filtered[filtered.length - 1] ?? currentPoint;
  }, [currentPoint, nowMs, replayPoints, sourceFilter]);
  const livePositions = useMemo<MapLivePosition[]>(() => {
    if (!markerPoint) return [];
    return [{
      id: markerPoint.id,
      subjectKey,
      pilotId: markerPoint.pilot_id,
      userId: markerPoint.user_id ?? null,
      pilotName: displayNameForSubject(markerPoint, pilotNameBySubject),
      latitude: markerPoint.lat,
      longitude: markerPoint.lon,
      altitudeM: markerPoint.alt,
      speedKmh: markerPoint.speed,
      heading: markerPoint.heading,
      timestamp: markerPoint.timestamp,
      batteryLevel: markerPoint.battery_level,
      source: markerPoint.source ?? "unknown",
      color: colorForSubject(subjectKey, activeSubjects),
      aircraftType: markerPoint.aircraft_icon ?? "hang_glider",
      profileType: markerPoint.profile_type ?? "pilot",
      positionSource: markerPoint.position_source ?? "other",
      deviceId: markerPoint.device_id,
    }];
  }, [activeSubjects, markerPoint, pilotNameBySubject, subjectKey]);

  const flagsByIndex = useMemo(() => diagnosticFlags(rawPoints), [rawPoints]);

  useEffect(() => {
    if (!playing || rawPoints.length <= 1) return;
    const interval = window.setInterval(() => {
      setCurrentIndex((index) => {
        if (index >= rawPoints.length - 1) {
          setPlaying(false);
          return index;
        }
        return index + 1;
      });
    }, Math.max(120, 900 / playbackSpeed));
    return () => window.clearInterval(interval);
  }, [playbackSpeed, playing, rawPoints.length]);

  useEffect(() => {
    currentRowRef.current?.scrollIntoView({ block: "nearest" });
  }, [safeCurrentIndex]);

  const pointSummary = rawPoints.length
    ? `${safeCurrentIndex + 1} / ${rawPoints.length} - ${formatTimestamp(currentPoint?.timestamp)}`
    : loadingTrack
      ? "Loading track..."
      : "No points";

  return (
    <div className="section-stack">
      <SectionCard title="Live Backtest">
        <div className="stack form-block">
          <div className="participant-intake-row">
            <label className="stack compact">
              <span>Competition</span>
              <select
                value={selectedEventId ?? ""}
                disabled={loadingSources || !events.length}
                onChange={(event) => handleEventChange(Number(event.target.value))}
              >
                {!events.length ? <option value="">No competitions</option> : null}
                {events.map((event) => (
                  <option key={event.id} value={event.id}>
                    {event.name}{event.location ? ` - ${event.location}` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="stack compact">
              <span>Task</span>
              <select
                value={selectedTaskId ?? ""}
                disabled={!selectedEvent?.tasks.length}
                onChange={(event) => handleTaskChange(Number(event.target.value))}
              >
                {!selectedEvent?.tasks.length ? <option value="">No tasks</option> : null}
                {selectedEvent?.tasks.map((task) => (
                  <option key={task.id} value={task.id}>
                    {task.name} - {task.status}{task.task_date ? ` - ${task.task_date}` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="stack compact">
              <span>Pilot</span>
              <select
                value={selectedPilotId ?? ""}
                disabled={!selectedTask?.pilots.length}
                onChange={(event) => setSelectedPilotId(Number(event.target.value))}
              >
                {!selectedTask?.pilots.length ? <option value="">No pilots</option> : null}
                {selectedTask?.pilots.map((pilot) => (
                  <option key={pilot.id} value={pilot.id}>
                    {pilot.pilot_name}{pilot.competition_number ? ` #${pilot.competition_number}` : ""} ({pilot.point_count})
                  </option>
                ))}
              </select>
            </label>
            <label className="stack compact">
              <span>Source</span>
              <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value as SourceFilter)}>
                <option value="merged">Merged</option>
                <option value="cell">Cell</option>
                <option value="mesh">Mesh</option>
              </select>
            </label>
          </div>

          {error ? <div className="status-chip error">{error}</div> : null}
          {!error && !rawPoints.length && !loadingTrack ? (
            <p className="hint">Choose a task and pilot with saved live tracking points to replay historical data.</p>
          ) : null}

          <div className="results-task-map-layout live-tracking-layout">
            <div className="results-task-map-pilot-list live-tracking-pilot-list">
              <div className="results-task-map-pilot-header">
                <strong>Replay</strong>
                <span>{pointSummary}</span>
              </div>
              <div className="stack compact" style={{ padding: 12 }}>
                <div className="button-row">
                  <button type="button" className="secondary" disabled={!rawPoints.length} onClick={() => setPlaying((value) => !value)}>
                    {playing ? "Pause" : "Play"}
                  </button>
                  <button type="button" className="secondary" disabled={!rawPoints.length} onClick={() => { setCurrentIndex(0); setPlaying(false); }}>
                    Reset
                  </button>
                </div>
                <label className="stack compact">
                  <span>Speed</span>
                  <select value={playbackSpeed} onChange={(event) => setPlaybackSpeed(Number(event.target.value))}>
                    <option value={0.5}>0.5x</option>
                    <option value={1}>1x</option>
                    <option value={2}>2x</option>
                    <option value={4}>4x</option>
                  </select>
                </label>
                <label className="stack compact">
                  <span>Time</span>
                  <input
                    type="range"
                    min={0}
                    max={Math.max(0, rawPoints.length - 1)}
                    step={1}
                    value={safeCurrentIndex}
                    disabled={!rawPoints.length}
                    onChange={(event) => {
                      setCurrentIndex(Number(event.target.value));
                      setPlaying(false);
                    }}
                  />
                </label>
                <div className="live-sidebar-legend" aria-label="Backtest legend">
                  <div className="live-sidebar-legend-title">Track style</div>
                  <div className="live-sidebar-legend-row">
                    <span className="live-sidebar-legend-item">Cell: solid</span>
                    <span className="live-sidebar-legend-item">Mesh: dashed</span>
                  </div>
                </div>
              </div>
            </div>
            <div className="results-task-map-canvas">
              <TaskMap
                turnpoints={mapTurnpoints}
                fitTurnpoints={mapTurnpoints}
                taskPoints={mapTaskPoints}
                optimizedRoute={taskDistanceMetrics.routeCoordinates}
                legMetrics={taskDistanceMetrics.legMetrics}
                track={replayTrack}
                telemetryTrack={replayTrack}
                livePositions={livePositions}
                editable={false}
                mode="live"
                units={units}
                showGpsButton
                overlayConfig={overlayConfig}
                highlightedLiveSubjectKey={subjectKey}
                fitKey={`backtest-${selectedTaskId ?? "task"}-${selectedPilotId ?? "pilot"}`}
              />
            </div>
          </div>

          <div className="live-tracking-table-wrap" style={{ maxHeight: 360, overflow: "auto" }}>
            <table className="results-table live-tracking-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Timestamp</th>
                  <th>Pilot</th>
                  <th>Task</th>
                  <th>Latitude</th>
                  <th>Longitude</th>
                  <th>Altitude</th>
                  <th>Ground speed</th>
                  <th>Heading</th>
                  <th>Source</th>
                  <th>Device</th>
                  <th>Mesh seq</th>
                  <th>Battery</th>
                  <th>Included</th>
                  <th>Diagnostics</th>
                  <th>Received</th>
                </tr>
              </thead>
              <tbody>
                {rawPoints.length ? rawPoints.map((point, index) => {
                  const isCurrent = index === safeCurrentIndex;
                  const included = mergedIncludedIds.has(point.id);
                  return (
                    <tr
                      key={point.id}
                      ref={isCurrent ? currentRowRef : undefined}
                      className={isCurrent ? "is-highlighted" : undefined}
                      style={isCurrent ? { outline: "2px solid var(--accent)", outlineOffset: "-2px" } : undefined}
                    >
                      <td>{index + 1}</td>
                      <td>{formatTimestamp(point.timestamp)}</td>
                      <td>{pilotName}</td>
                      <td>{trackData?.task.name ?? "-"}</td>
                      <td>{point.lat.toFixed(6)}</td>
                      <td>{point.lon.toFixed(6)}</td>
                      <td>{convertAltitude(point.alt, units.altitude)}</td>
                      <td>{convertSpeed(point.speed, units.speed)}</td>
                      <td>{point.heading != null ? `${Math.round(point.heading)} deg` : "-"}</td>
                      <td>{point.position_source ?? point.source ?? "-"}</td>
                      <td>{point.device_id ?? "-"}</td>
                      <td>{point.mesh_seq_number ?? "-"}</td>
                      <td>{point.battery_level != null ? `${point.battery_level}%` : "-"}</td>
                      <td>{included ? "yes" : "no"}</td>
                      <td>{flagsByIndex[index]?.join(", ") || "-"}</td>
                      <td>{formatTimestamp(point.received_at ?? point.created_at)}</td>
                    </tr>
                  );
                }) : (
                  <tr>
                    <td colSpan={16}>{loadingTrack ? "Loading historical tracking data..." : "No raw points found for this pilot and task."}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </SectionCard>
    </div>
  );
}
