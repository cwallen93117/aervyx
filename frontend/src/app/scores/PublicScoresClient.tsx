"use client";

import { useCallback, useEffect, useId, useMemo, useState, type ReactNode } from "react";

import { TaskMap, type MapTaskPoint, type MapTurnpoint, type MapUnitPreferences, type TrackCollection } from "../../components/TaskMap";
import { TRACK_COLORS, resolveApiBase } from "../../lib/live-tracking-utils";
import { formatPenaltyPoints, formatScorePoints, hasPenaltyDetails, type ScorePenaltyCalculation, type ScorePenaltyRecord } from "../../lib/scorePenalties";
import { computeTaskOptimization } from "../../lib/taskOptimization";

type PublicEvent = {
  id: number;
  name: string;
  location: string;
  starts_on: string;
  ends_on: string;
  timezone: string;
  use_distance_points?: boolean;
  use_time_points?: boolean;
  use_leading_points?: boolean;
  use_arrival_position_points?: boolean;
  use_arrival_time_points?: boolean;
  use_departure_points?: boolean;
};

type PublicTaskPoint = MapTaskPoint & {
  id: number;
  turnpoint_id: number | null;
  direction: "enter" | "exit";
};

type PublicTask = {
  id: number;
  event_id: number;
  name: string;
  task_date: string | null;
  is_practice: boolean;
  status: string;
  task_type: string;
  task_start_time: string | null;
  task_finish_time: string | null;
  start_open_time: string | null;
  start_close_time: string | null;
  start_gate_count: number;
  start_gate_interval_seconds: number | null;
  published_at: string | null;
  points: PublicTaskPoint[];
};

type ResultRecord = {
  id: number;
  upload_id: number | null;
  pilot_id: number;
  pilot_name: string;
  competition_number?: string | null;
  status: string;
  distance_flown_km: number;
  elapsed_seconds?: number | null;
  started_at?: string | null;
  ess_at?: string | null;
  goal_at?: string | null;
  raw_score_points?: number;
  score_points: number;
  rank: number | null;
  details_json: Record<string, unknown>;
  result_state?: string;
  penalties?: ScorePenaltyRecord[];
  penalty_summary?: string | null;
  penalty_calculation?: ScorePenaltyCalculation | null;
};

type PilotSummaryRecord = {
  pilot_id: number;
  pilot_name: string;
  competition_number?: string | null;
  total_score_points: number;
  tasks_scored: number;
  best_distance_km: number;
  task_scores: Record<string, number>;
  task_result_states: Record<string, string>;
};

type TaskResultSummaryRecord = { task_id: number; day_quality: number | null };
type TaskSubTab = "results" | "map";

const defaultUnits: MapUnitPreferences = { altitude: "ft", speed: "mph", distance: "mi", vario: "fpm" };

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

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

function formatDateLabel(value: string | null | undefined): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString([], { year: "numeric", month: "2-digit", day: "2-digit" });
}

function compareTasksForScores(a: PublicTask, b: PublicTask): number {
  if (a.is_practice !== b.is_practice) return a.is_practice ? -1 : 1;
  const aHasDate = Boolean(a.task_date);
  const bHasDate = Boolean(b.task_date);
  if (aHasDate !== bHasDate) return aHasDate ? -1 : 1;
  if (a.task_date && b.task_date) {
    const dateComparison = a.task_date.localeCompare(b.task_date);
    if (dateComparison !== 0) return dateComparison;
  }
  return a.id - b.id;
}

function resultStateLabel(resultState: string | null | undefined): { label: string; className: string } | null {
  if (resultState === "provisional") return { label: "Provisional", className: "provisional" };
  if (resultState === "official") return { label: "Official", className: "official" };
  return null;
}

function sortPublicEventsByDate(events: PublicEvent[]): PublicEvent[] {
  return [...events].sort((a, b) => (
    b.starts_on.localeCompare(a.starts_on)
    || b.ends_on.localeCompare(a.ends_on)
    || a.name.localeCompare(b.name)
  ));
}

function formatClockTime(value: string | null | undefined, includeSeconds = false, timeZone?: string): string {
  if (!value) return "-";
  const normalizedValue = /T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(value) ? `${value}Z` : value;
  const parsed = new Date(normalizedValue);
  if (Number.isNaN(parsed.getTime())) return value;
  try {
    return new Intl.DateTimeFormat("en-US", {
      hour: "numeric",
      minute: "2-digit",
      second: includeSeconds ? "2-digit" : undefined,
      hour12: false,
      timeZone: timeZone || undefined,
    }).format(parsed);
  } catch {
    return parsed.toLocaleTimeString([], {
      hour: "numeric",
      minute: "2-digit",
      second: includeSeconds ? "2-digit" : undefined,
      hour12: false,
    });
  }
}

function formatElapsedSeconds(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "-";
  const totalSeconds = Math.max(0, Math.round(value));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function formatPoints(value: number | null | undefined): string {
  const safe = Number(value ?? 0);
  return safe.toFixed(1);
}

function formatPointsWithComma(value: number): string {
  const fixed = value.toFixed(1);
  const [int, dec] = fixed.split(".");
  return `${Number(int).toLocaleString("en-US")}.${dec}`;
}

function formatSpeedKmh(distanceKm: number, elapsedSeconds: number | null | undefined): string {
  if (!elapsedSeconds || elapsedSeconds <= 0) return "-";
  return (distanceKm / (elapsedSeconds / 3600)).toFixed(1);
}

function formatDayQualityPercent(value: number | null | undefined): string {
  const dayQuality = Number(value ?? NaN);
  if (!Number.isFinite(dayQuality)) return "-";
  const percent = dayQuality * 100;
  return `${percent.toFixed(2).replace(/\.00$/, "").replace(/(\.\d)0$/, "$1")}%`;
}

function taskTypeLabel(value: string): string {
  switch (value) {
    case "race":
    case "race_to_goal":
    case "race_to_goal_with_gates":
      return "Race to Goal";
    case "speedrun":
    case "elapsed_time":
      return "Elapsed Time";
    case "open_distance":
      return "Open Distance";
    default:
      return value;
  }
}

function taskTypeLabelWithGateCount(task: PublicTask): string {
  const label = taskTypeLabel(task.task_type);
  if (task.task_type === "race_to_goal_with_gates" && task.start_gate_count > 1) {
    return `${label} with ${task.start_gate_count} start gates`;
  }
  return label;
}

function statusAbbreviation(status: string): string | null {
  switch (status) {
    case "absent":
      return "ABS";
    case "did_not_fly":
      return "DNF";
    case "minimum_distance":
      return "MinD";
    default:
      return null;
  }
}

function gapAwardedPoints(result: ResultRecord, key: "distance" | "speed" | "arrival" | "departure" | "leading") {
  const gap = result.details_json?.gap as { awarded_points?: Record<string, number> } | undefined;
  return Number(gap?.awarded_points?.[key] ?? 0);
}

function resultScoringTimezone(result: ResultRecord, fallback?: string): string | undefined {
  const timezone = result.details_json?.scoring_timezone;
  return typeof timezone === "string" && timezone.trim() ? timezone : fallback;
}

function taskResultsHeaderLabel(key: "distance" | "speed" | "arrival" | "departure" | "leading"): ReactNode {
  switch (key) {
    case "distance":
      return <span className="results-header-stack"><span>Dist.</span><span>Points</span></span>;
    case "speed":
      return <span className="results-header-stack"><span>Time</span><span>Points</span></span>;
    case "arrival":
      return <span className="results-header-stack"><span>Arrival</span><span>Points</span></span>;
    case "departure":
      return <span className="results-header-stack"><span>Departure</span><span>Points</span></span>;
    case "leading":
      return <span className="results-header-stack"><span>Leading</span><span>Points</span></span>;
    default:
      return key;
  }
}

function taskMapTurnpoints(task: PublicTask): MapTurnpoint[] {
  return task.points.map((point, index) => ({
    id: point.turnpoint_id ?? -(index + 1),
    name: point.name,
    code: null,
    latitude: point.latitude,
    longitude: point.longitude,
  }));
}

function PenaltyDetailsModal({
  result,
  taskName,
  onClose,
}: {
  result: ResultRecord;
  taskName: string;
  onClose: () => void;
}) {
  const calculation = result.penalty_calculation;
  return (
    <div className="score-penalty-modal-overlay active" onClick={onClose}>
      <div className="score-penalty-modal" onClick={(event) => event.stopPropagation()}>
        <div className="score-penalty-modal-header">
          <div>
            <div className="score-penalty-modal-title">{result.pilot_name}</div>
            <div className="score-penalty-modal-subtitle">{taskName}</div>
          </div>
          <button type="button" className="score-penalty-modal-close" onClick={onClose} aria-label="Close penalty details">x</button>
        </div>
        {calculation ? (
          <>
            <div className="score-penalty-score-strip">
              <div><span>Raw</span><strong>{formatScorePoints(calculation.raw_score_points)}</strong></div>
              <div><span>Engine</span><strong>{formatPenaltyPoints({ score_points: 0, penalty_calculation: { ...calculation, total_display_penalty_points: calculation.engine_penalty_points } })}</strong></div>
              <div><span>Manual</span><strong>{formatPenaltyPoints({ score_points: 0, penalty_calculation: { ...calculation, total_display_penalty_points: calculation.manual_penalty_points } })}</strong></div>
              <div><span>Final</span><strong>{formatScorePoints(calculation.final_score_points)}</strong></div>
            </div>
            <div className="score-penalty-lines">
              {calculation.lines.map((line, index) => (
                <div key={`${line.kind}-${index}`} className="score-penalty-line">
                  <div>
                    <strong>{line.label}</strong>
                    {line.detail ? <span>{line.detail}</span> : null}
                  </div>
                  <div>
                    <strong>{formatPenaltyPoints({ score_points: 0, penalty_calculation: { ...calculation, total_display_penalty_points: line.amount_points } })}</strong>
                    {line.running_score_points != null ? <span>{formatScorePoints(line.running_score_points)} running</span> : null}
                  </div>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="score-penalty-empty">{formatPenaltyPoints(result)}</div>
        )}
      </div>
    </div>
  );
}

export function PublicScoresClient() {
  const apiBase = useMemo(() => resolveApiBase(), []);
  const pilotTracksContentId = useId();
  const [events, setEvents] = useState<PublicEvent[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [tasks, setTasks] = useState<PublicTask[]>([]);
  const [pilotSummary, setPilotSummary] = useState<PilotSummaryRecord[]>([]);
  const [taskResultSummary, setTaskResultSummary] = useState<TaskResultSummaryRecord[]>([]);
  const [activeTaskId, setActiveTaskId] = useState<number | null>(null);
  const [taskTab, setTaskTab] = useState<TaskSubTab>("results");
  const [taskResults, setTaskResults] = useState<ResultRecord[]>([]);
  const [taskResultsTaskId, setTaskResultsTaskId] = useState<number | null>(null);
  const [penaltyDetailsResult, setPenaltyDetailsResult] = useState<ResultRecord | null>(null);
  const [selectedResultUploadIds, setSelectedResultUploadIds] = useState<number[]>([]);
  const [resultTracksByUploadId, setResultTracksByUploadId] = useState<Record<number, TrackCollection>>({});
  const [highlightedResultUploadId, setHighlightedResultUploadId] = useState<number | null>(null);
  const [loadingEvents, setLoadingEvents] = useState(true);
  const [loadingEvent, setLoadingEvent] = useState(false);
  const [loadingResults, setLoadingResults] = useState(false);
  const [error, setError] = useState("");
  const [overlayConfig, setOverlayConfig] = useState<Record<string, boolean> | undefined>(undefined);
  const [hasRequestedEventParam, setHasRequestedEventParam] = useState(false);
  const [requestedEventId, setRequestedEventId] = useState<number | null>(null);
  const [hasAppliedRequestedEvent, setHasAppliedRequestedEvent] = useState(false);

  const selectedEvent = useMemo(
    () => events.find((event) => event.id === selectedEventId) ?? null,
    [events, selectedEventId],
  );
  const selectedTask = useMemo(
    () => tasks.find((task) => task.id === activeTaskId) ?? null,
    [activeTaskId, tasks],
  );
  const taskResultSummaryById = useMemo(
    () => new Map(taskResultSummary.map((summary) => [summary.task_id, summary])),
    [taskResultSummary],
  );
  const taskMetricsById = useMemo(
    () => new Map(tasks.map((task) => [task.id, computeTaskOptimization(task.points)])),
    [tasks],
  );
  const scoredTasks = useMemo(
    () => tasks.filter((task) => pilotSummary.some((summary) => summary.task_scores[String(task.id)] != null)).sort(compareTasksForScores),
    [tasks, pilotSummary],
  );
  const visiblePilotSummary = useMemo(
    () => pilotSummary.filter((summary) => Object.keys(summary.task_scores).length > 0),
    [pilotSummary],
  );
  const overallTaskResultStates = useMemo(() => {
    const states = new Map<number, string>();
    for (const task of scoredTasks) {
      const taskId = String(task.id);
      let resolved: string | null = null;
      for (const summary of pilotSummary) {
        const next = summary.task_result_states?.[taskId];
        if (!next) continue;
        if (next === "provisional") {
          resolved = "provisional";
          break;
        }
        if (next === "official") {
          resolved = "official";
        }
      }
      if (resolved) states.set(task.id, resolved);
    }
    return states;
  }, [pilotSummary, scoredTasks]);
  const selectedTaskResultState = useMemo(() => {
    if (!taskResults.length) return null;
    return taskResults.some((result) => result.result_state === "provisional") ? "provisional" : "official";
  }, [taskResults]);
  const taskResultsColumns = useMemo(() => {
    const columns: Array<"distance" | "speed" | "arrival" | "departure" | "leading"> = [];
    if (selectedEvent?.use_distance_points ?? true) columns.push("distance");
    if (selectedEvent?.use_leading_points ?? true) columns.push("leading");
    if (selectedEvent?.use_time_points ?? true) columns.push("speed");
    if (selectedEvent?.use_arrival_position_points || selectedEvent?.use_arrival_time_points) columns.push("arrival");
    if (selectedEvent?.use_departure_points) columns.push("departure");
    return columns;
  }, [selectedEvent]);
  const taskResultsIncludePenalty = useMemo(
    () => taskResults.some((result) => formatPenaltyPoints(result) !== "-"),
    [taskResults],
  );
  const trackableResults = useMemo(
    () => taskResults.filter((result): result is ResultRecord & { upload_id: number } => result.upload_id != null && result.result_state === "official"),
    [taskResults],
  );
  const resultByUploadId = useMemo(
    () => new Map(trackableResults.map((result) => [result.upload_id, result])),
    [trackableResults],
  );
  const resultTrackColorsByUploadId = useMemo(() => {
    const colorMap = new Map<number, string>();
    trackableResults.forEach((result, index) => {
      colorMap.set(result.upload_id, TRACK_COLORS[index % TRACK_COLORS.length]);
    });
    return colorMap;
  }, [trackableResults]);
  const allResultTrackIds = useMemo(() => trackableResults.map((result) => result.upload_id), [trackableResults]);
  const allResultTracksChecked = useMemo(
    () => allResultTrackIds.length > 0 && allResultTrackIds.every((uploadId) => selectedResultUploadIds.includes(uploadId)),
    [allResultTrackIds, selectedResultUploadIds],
  );
  const resultsTrackOverlay = useMemo<TrackCollection | null>(() => {
    if (!selectedResultUploadIds.length) {
      return null;
    }
    const features = selectedResultUploadIds.flatMap((uploadId) => {
      const collection = resultTracksByUploadId[uploadId];
      if (!collection) {
        return [];
      }
      const result = resultByUploadId.get(uploadId);
      const color = resultTrackColorsByUploadId.get(uploadId) ?? TRACK_COLORS[0];
      return collection.features.map((feature) => ({
        ...feature,
        properties: {
          ...feature.properties,
          color,
          pilot_name: result?.pilot_name.trim() || feature.properties?.pilot_name || `Pilot ${uploadId}`,
          upload_id: uploadId,
        },
      }));
    });
    return { type: "FeatureCollection", features };
  }, [resultByUploadId, resultTrackColorsByUploadId, resultTracksByUploadId, selectedResultUploadIds]);
  const selectedTaskMetrics = useMemo(
    () => (selectedTask ? computeTaskOptimization(selectedTask.points) : null),
    [selectedTask],
  );
  const scoresMapOverlayConfig = useMemo<Record<string, boolean>>(() => ({
    turnpoints: true,
    task_route: true,
    task_cylinders: true,
    optimized_route: true,
    leg_labels: true,
    distance_summary: true,
    flight_track: overlayConfig?.flight_track ?? true,
    track_highlight: overlayConfig?.track_highlight ?? true,
    replay_scrubber: overlayConfig?.replay_scrubber ?? true,
    live_positions: false,
    live_labels: false,
    gps_button: false,
    fullscreen_toggle: overlayConfig?.fullscreen_toggle ?? true,
    "2d_3d_toggle": overlayConfig?.["2d_3d_toggle"] ?? true,
    basemap_selector: overlayConfig?.basemap_selector ?? true,
    altitude_slider: overlayConfig?.altitude_slider ?? true,
  }), [overlayConfig]);
  const watchLiveHref = useMemo(() => (
    selectedEventId != null
      ? `/live?event_id=${encodeURIComponent(String(selectedEventId))}&scores_event_id=${encodeURIComponent(String(selectedEventId))}`
      : "/live"
  ), [selectedEventId]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    setHasRequestedEventParam(params.has("event_id"));
    setRequestedEventId(readNumericSearchParam("event_id"));
  }, []);

  const loadResultTrack = useCallback(async (uploadId: number) => {
    if (resultTracksByUploadId[uploadId]) {
      return;
    }
    const collection = await fetchJson<TrackCollection>(`${apiBase}/api/public/uploads/${uploadId}/track`);
    setResultTracksByUploadId((current) => (
      current[uploadId] ? current : { ...current, [uploadId]: collection }
    ));
  }, [apiBase, resultTracksByUploadId]);

  const toggleResultTrack = useCallback(async (uploadId: number, checked: boolean) => {
    if (!checked) {
      setSelectedResultUploadIds((current) => current.filter((id) => id !== uploadId));
      setHighlightedResultUploadId((current) => (current === uploadId ? null : current));
      return;
    }
    setSelectedResultUploadIds((current) => (current.includes(uploadId) ? current : [...current, uploadId]));
    setHighlightedResultUploadId(uploadId);
    try {
      await loadResultTrack(uploadId);
    } catch {
      setSelectedResultUploadIds((current) => current.filter((id) => id !== uploadId));
      setHighlightedResultUploadId((current) => (current === uploadId ? null : current));
      setError("Unable to load the selected pilot track.");
    }
  }, [loadResultTrack]);

  const toggleAllResultTracks = useCallback(async () => {
    if (!allResultTrackIds.length) {
      return;
    }
    if (allResultTracksChecked) {
      setSelectedResultUploadIds([]);
      setHighlightedResultUploadId(null);
      return;
    }
    setSelectedResultUploadIds(allResultTrackIds);
    const missingUploadIds = allResultTrackIds.filter((uploadId) => !resultTracksByUploadId[uploadId]);
    if (!missingUploadIds.length) {
      return;
    }
    try {
      await Promise.all(missingUploadIds.map((uploadId) => loadResultTrack(uploadId)));
    } catch {
      setSelectedResultUploadIds([]);
      setHighlightedResultUploadId(null);
      setError("Unable to load all pilot tracks.");
    }
  }, [allResultTrackIds, allResultTracksChecked, loadResultTrack, resultTracksByUploadId]);

  useEffect(() => {
    let cancelled = false;
    setLoadingEvents(true);
    setError("");
    (async () => {
      try {
        const loadedEvents = await fetchJson<PublicEvent[]>(`${apiBase}/api/public/events`);
        if (cancelled) return;
        setEvents(sortPublicEventsByDate(loadedEvents));
      } catch {
        if (!cancelled) {
          setError("Unable to load public competitions.");
        }
      } finally {
        if (!cancelled) {
          setLoadingEvents(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBase]);

  useEffect(() => {
    if (loadingEvents || hasAppliedRequestedEvent || !hasRequestedEventParam) {
      return;
    }
    if (requestedEventId != null && events.some((event) => event.id === requestedEventId)) {
      setSelectedEventId(requestedEventId);
    } else {
      setSelectedEventId(null);
    }
    setHasAppliedRequestedEvent(true);
  }, [events, hasAppliedRequestedEvent, hasRequestedEventParam, loadingEvents, requestedEventId]);

  useEffect(() => {
    let cancelled = false;
    if (selectedEventId == null) {
      setTasks([]);
      setPilotSummary([]);
      setTaskResultSummary([]);
      setActiveTaskId(null);
      setLoadingEvent(false);
      setSelectedResultUploadIds([]);
      setResultTracksByUploadId({});
      setHighlightedResultUploadId(null);
      return () => {
        cancelled = true;
      };
    }
    setLoadingEvent(true);
    setError("");
    setActiveTaskId(null);
    setTaskTab("results");
    setTaskResults([]);
    setTaskResultsTaskId(null);
    setSelectedResultUploadIds([]);
    setResultTracksByUploadId({});
    setHighlightedResultUploadId(null);
    (async () => {
      try {
        const [loadedTasks, loadedPilotSummary, loadedTaskResultSummary] = await Promise.all([
          fetchJson<PublicTask[]>(`${apiBase}/api/public/events/${selectedEventId}/tasks`),
          fetchJson<PilotSummaryRecord[]>(`${apiBase}/api/public/events/${selectedEventId}/pilot-summary`),
          fetchJson<TaskResultSummaryRecord[]>(`${apiBase}/api/public/events/${selectedEventId}/task-result-summary`),
        ]);
        if (cancelled) return;
        setTasks(loadedTasks);
        setPilotSummary(loadedPilotSummary);
        setTaskResultSummary(loadedTaskResultSummary);
      } catch {
        if (!cancelled) {
          setTasks([]);
          setPilotSummary([]);
          setTaskResultSummary([]);
          setError("Unable to load scores for this competition.");
        }
      } finally {
        if (!cancelled) {
          setLoadingEvent(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBase, selectedEventId]);

  useEffect(() => {
    let cancelled = false;
    if (activeTaskId == null) {
      setTaskResults([]);
      setTaskResultsTaskId(null);
      setSelectedResultUploadIds([]);
      setResultTracksByUploadId({});
      setHighlightedResultUploadId(null);
      return () => {
        cancelled = true;
      };
    }
    setLoadingResults(true);
    setError("");
    setSelectedResultUploadIds([]);
    setResultTracksByUploadId({});
    setHighlightedResultUploadId(null);
    (async () => {
      try {
        const loadedResults = await fetchJson<ResultRecord[]>(`${apiBase}/api/public/tasks/${activeTaskId}/results`);
        if (cancelled) return;
        setTaskResults(loadedResults);
        setTaskResultsTaskId(activeTaskId);
      } catch {
        if (!cancelled) {
          setTaskResults([]);
          setTaskResultsTaskId(null);
          setError("Unable to load task results.");
        }
      } finally {
        if (!cancelled) {
          setLoadingResults(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBase, activeTaskId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await fetchJson<{ config?: { public_live?: Record<string, boolean> } }>(`${apiBase}/api/map-overlay-config/public`);
        if (!cancelled && data.config?.public_live) {
          setOverlayConfig(data.config.public_live);
        }
      } catch {
        // Map defaults keep the public route map usable without this optional config.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBase]);

  const selectOverall = useCallback(() => {
    setActiveTaskId(null);
    setTaskResults([]);
    setTaskResultsTaskId(null);
    setSelectedResultUploadIds([]);
    setResultTracksByUploadId({});
    setHighlightedResultUploadId(null);
  }, []);

  const selectTask = useCallback((taskId: number) => {
    setActiveTaskId(taskId);
    setTaskResults([]);
    setTaskResultsTaskId(null);
    setSelectedResultUploadIds([]);
    setResultTracksByUploadId({});
    setHighlightedResultUploadId(null);
  }, []);

  const renderOverall = () => (
    <div className="scores-panel">
      <div className="scores-panel-header">
        <div>
          <h1>Overall</h1>
          <p>{selectedEvent?.name ?? "Competition"} {selectedEvent?.location ? `- ${selectedEvent.location}` : ""}</p>
        </div>
      </div>
      {scoredTasks.length ? (
        <div className="results-table-wrap scores-summary-table-wrap">
          <table className="results-table results-table-compact overall-task-summary-table">
            <thead>
              <tr>
                <th>Task</th>
                <th>Date</th>
                <th>Distance</th>
                <th>Day Quality</th>
                <th>Type</th>
              </tr>
            </thead>
            <tbody>
              {scoredTasks.map((task) => (
                <tr key={task.id}>
                  <td><strong>{task.name}</strong>{task.is_practice ? <span className="practice-task-badge">Practice</span> : null}</td>
                  <td>{formatDateLabel(task.task_date) !== "-" ? formatDateLabel(task.task_date) : formatDateLabel(task.published_at)}</td>
                  <td>{(taskMetricsById.get(task.id)?.optimizedDistanceKm ?? 0).toFixed(1)} km</td>
                  <td>{formatDayQualityPercent(taskResultSummaryById.get(task.id)?.day_quality)}</td>
                  <td>{taskTypeLabelWithGateCount(task)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {visiblePilotSummary.length ? (
        <div className="results-table-wrap">
          <table className="results-table results-table-task scores-results-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Name</th>
                {scoredTasks.map((task) => {
                  const state = resultStateLabel(overallTaskResultStates.get(task.id));
                  return (
                    <th key={task.id}>
                      <span className="results-header-stack">
                        <span>{task.name}</span>
                        {task.is_practice ? <span className="practice-task-badge">Practice</span> : null}
                        {state ? <span className={`result-state-badge ${state.className}`}>{state.label}</span> : null}
                      </span>
                    </th>
                  );
                })}
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              {visiblePilotSummary.map((summary, index) => (
                <tr key={summary.pilot_id}>
                  <td><span className="scoring-ops-rank-badge">{index + 1}</span></td>
                  <td>
                    <strong>{summary.pilot_name}</strong>
                  </td>
                  {scoredTasks.map((task) => (
                    <td key={task.id}>{summary.task_scores[String(task.id)] != null ? formatPoints(summary.task_scores[String(task.id)]) : "-"}</td>
                  ))}
                  <td className="results-table-total">{formatPointsWithComma(summary.total_score_points)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="scores-empty">No overall results are available yet.</div>
      )}
    </div>
  );

  const renderTaskResults = () => {
    if (!selectedTask) return null;
    const selectedState = resultStateLabel(selectedTaskResultState);
    return (
      <div className="scores-panel">
        <div className="scores-panel-header">
          <div>
            <h1>{selectedTask.name} {selectedTask.is_practice ? <span className="practice-task-badge">Practice</span> : null} {selectedState ? <span className={`result-state-badge ${selectedState.className}`}>{selectedState.label}</span> : null}</h1>
            <p>{formatDateLabel(selectedTask.task_date)} - {taskTypeLabelWithGateCount(selectedTask)}</p>
          </div>
        </div>
        {loadingResults || taskResultsTaskId !== selectedTask.id ? (
          <div className="scores-empty">Loading task results...</div>
        ) : taskResults.length ? (
          <div className="results-table-wrap">
            <table className="results-table results-table-task scores-results-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Name</th>
                  <th>SS</th>
                  <th>ES</th>
                  <th><span className="results-header-stack"><span>Time</span><span>[h:m:s]</span></span></th>
                  <th><span className="results-header-stack"><span>Speed</span><span>[km/h]</span></span></th>
                  <th><span className="results-header-stack"><span>Distance</span><span>[km]</span></span></th>
                  {taskResultsColumns.map((column) => <th key={column}>{taskResultsHeaderLabel(column)}</th>)}
                  {taskResultsIncludePenalty ? <th>Penalty</th> : null}
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                {taskResults.map((result) => {
                  const statusLabel = statusAbbreviation(result.status);
                  return (
                    <tr key={result.id}>
                      <td><span className="scoring-ops-rank-badge">{result.rank ?? "-"}</span></td>
                      <td>
                        <strong>{result.pilot_name}</strong>
                        {statusLabel ? <span className="results-status-badge">{statusLabel}</span> : null}
                      </td>
                      <td>{formatClockTime(result.started_at, true, resultScoringTimezone(result, selectedEvent?.timezone))}</td>
                      <td>{formatClockTime(result.goal_at ?? result.ess_at, true, resultScoringTimezone(result, selectedEvent?.timezone))}</td>
                      <td>{formatElapsedSeconds(result.elapsed_seconds)}</td>
                      <td>{formatSpeedKmh(result.distance_flown_km, result.elapsed_seconds)}</td>
                      <td>{result.distance_flown_km.toFixed(1)}</td>
                      {taskResultsColumns.map((column) => <td key={column}>{formatPoints(gapAwardedPoints(result, column))}</td>)}
                      {taskResultsIncludePenalty ? (
                        <td className={formatPenaltyPoints(result) !== "-" ? "results-table-penalty" : undefined}>
                          {hasPenaltyDetails(result) ? (
                            <button type="button" className="score-penalty-link" onClick={() => setPenaltyDetailsResult(result)}>
                              {formatPenaltyPoints(result)}
                            </button>
                          ) : (
                            formatPenaltyPoints(result)
                          )}
                        </td>
                      ) : null}
                      <td className="results-table-total">{formatPointsWithComma(result.score_points)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="scores-empty">No results are available yet for this task.</div>
        )}
      </div>
    );
  };

  const renderResultsTrackPilotList = ({
    collapsed = false,
    className = "",
    contentId,
    titleAction,
  }: {
    collapsed?: boolean;
    className?: string;
    contentId?: string;
    titleAction?: ReactNode;
  } = {}) => (
    <div className={`results-task-map-pilot-list${className ? ` ${className}` : ""}${collapsed ? " is-collapsed" : ""}`}>
      <div className="results-task-map-pilot-header">
        <strong>Show pilot tracks</strong>
        <div className="results-task-map-pilot-header-actions">
          <label className="results-task-map-pilot-master-toggle" aria-label="Show all pilot tracks">
            <input
              type="checkbox"
              checked={allResultTracksChecked}
              disabled={!trackableResults.length}
              onChange={() => void toggleAllResultTracks()}
            />
          </label>
          {titleAction}
        </div>
      </div>
      <div id={contentId} className="results-task-map-pilot-items" hidden={collapsed}>
        {trackableResults.length ? trackableResults.map((result) => {
          const isChecked = selectedResultUploadIds.includes(result.upload_id);
          const pilotTrackColor = resultTrackColorsByUploadId.get(result.upload_id) ?? TRACK_COLORS[0];
          return (
            <div key={result.id} className={`results-task-map-pilot-item${highlightedResultUploadId === result.upload_id ? " is-highlighted" : ""}`}>
              <input
                type="checkbox"
                checked={isChecked}
                aria-label={`Show ${result.pilot_name} track`}
                onChange={(event) => void toggleResultTrack(result.upload_id, event.target.checked)}
              />
              <span className="results-task-map-pilot-rank">{result.rank ?? "-"}</span>
              <button
                type="button"
                className="results-task-map-pilot-button"
                onClick={() =>
                  setHighlightedResultUploadId(
                    highlightedResultUploadId === result.upload_id ? null : result.upload_id,
                  )
                }
              >
                <span className="results-task-map-pilot-copy">
                  <strong style={{ color: pilotTrackColor }}>{result.pilot_name}</strong>
                  <small>{result.status.toUpperCase()} &middot; {result.score_points.toFixed(1)} pts</small>
                </span>
              </button>
            </div>
          );
        }) : (
          <div className="results-task-map-empty">No public pilot tracks are available.</div>
        )}
      </div>
    </div>
  );

  const renderTaskMap = () => {
    if (!selectedTask || !selectedTaskMetrics) return null;
    if (!selectedTask.points.length) {
      return <div className="scores-empty">This task does not have public route geometry yet.</div>;
    }
    const turnpoints = taskMapTurnpoints(selectedTask);
    return (
      <div className="scores-map-panel results-task-map">
        <div className="results-task-map-layout scores-task-map-layout">
          {renderResultsTrackPilotList({ contentId: pilotTracksContentId })}
          <TaskMap
            key={`public-scores-map-${selectedTask.id}`}
            turnpoints={turnpoints}
            taskPoints={selectedTask.points}
            optimizedRoute={selectedTaskMetrics.routeCoordinates}
            legMetrics={selectedTaskMetrics.legMetrics}
            track={resultsTrackOverlay}
            editable={false}
            fullscreenSidebar={({ contentId, toggleButton }) =>
              renderResultsTrackPilotList({
                className: "scores-fullscreen-pilot-tracks-card",
                contentId,
                titleAction: toggleButton,
              })
            }
            fullscreenSidebarLabel="pilot tracks"
            highlightedTrackUploadId={highlightedResultUploadId}
            fitKey={selectedTask.id}
            fitTurnpoints={turnpoints}
            units={defaultUnits}
            overlayConfig={scoresMapOverlayConfig}
          />
        </div>
      </div>
    );
  };

  return (
    <div className="live-page scores-page">
      <header className="live-header scores-header">
        <a href="/" className="live-brand" title="Back to Aervyx">
          <svg viewBox="0 0 30 30" width="24" height="24" fill="none" aria-hidden="true">
            <path d="M15 3L27 25L15 19L3 25Z" stroke="#00e5ff" strokeWidth="1.5" fill="none" strokeLinejoin="round"/>
            <circle cx="15" cy="15" r="2.2" fill="#00e5ff" opacity=".85"/>
          </svg>
        </a>
        <span className="live-title scores-title">Comp Scores</span>
        <div className="live-source-picker">
          <select
            aria-label="Competition scores event"
            value={selectedEventId ?? ""}
            onChange={(event) => setSelectedEventId(Number(event.target.value) || null)}
            disabled={loadingEvents || !events.length}
          >
            <option value="">Select a competition</option>
            {events.length ? events.map((event) => (
              <option key={event.id} value={event.id}>{event.name}</option>
            )) : <option value="">No public competitions</option>}
          </select>
        </div>
        <a href={watchLiveHref} className="public-header-link public-header-link-live">Watch Live</a>
        {error ? <span className="live-status live-status-error">{error}</span> : null}
      </header>

      <div className="scores-body">
        <aside className="scores-sidebar" aria-label="Score views">
          {selectedEvent ? (
            <>
              <button
                type="button"
                className={activeTaskId == null ? "scores-nav-item active" : "scores-nav-item"}
                onClick={selectOverall}
              >
                <span>Overall</span>
                <small>{visiblePilotSummary.length} pilot{visiblePilotSummary.length === 1 ? "" : "s"}</small>
              </button>
              <div className="scores-nav-divider">Tasks</div>
              {tasks.map((task) => (
                <button
                  key={task.id}
                  type="button"
                  className={activeTaskId === task.id ? "scores-nav-item active" : "scores-nav-item"}
                  onClick={() => selectTask(task.id)}
                >
                  <span>{task.name}</span>
                  <small>{formatDateLabel(task.task_date)}</small>
                </button>
              ))}
              {!loadingEvent && !tasks.length ? <div className="scores-sidebar-empty">No published tasks</div> : null}
            </>
          ) : null}
        </aside>

        <main className="scores-main">
          {loadingEvents || loadingEvent ? (
            <div className="scores-empty">Loading public scores...</div>
          ) : !selectedEvent ? (
            <div className="scores-empty">{events.length ? "Select a public competition." : "No public competitions are available yet."}</div>
          ) : activeTaskId == null ? (
            renderOverall()
          ) : selectedTask ? (
            <>
              <div className="scores-sub-tabs" role="tablist" aria-label={`${selectedTask.name} views`}>
                <button
                  type="button"
                  role="tab"
                  aria-selected={taskTab === "results"}
                  className={taskTab === "results" ? "scores-sub-tab active" : "scores-sub-tab"}
                  onClick={() => setTaskTab("results")}
                >
                  Results
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={taskTab === "map"}
                  className={taskTab === "map" ? "scores-sub-tab active" : "scores-sub-tab"}
                  onClick={() => setTaskTab("map")}
                >
                  Map
                </button>
              </div>
              {taskTab === "results" ? renderTaskResults() : renderTaskMap()}
            </>
          ) : (
            <div className="scores-empty">Select a published task.</div>
          )}
        </main>
      </div>
      {penaltyDetailsResult ? (
        <PenaltyDetailsModal
          result={penaltyDetailsResult}
          taskName={selectedTask?.name ?? "Task"}
          onClose={() => setPenaltyDetailsResult(null)}
        />
      ) : null}
    </div>
  );
}
