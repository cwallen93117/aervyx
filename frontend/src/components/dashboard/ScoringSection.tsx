"use client";

import { useMemo, type ReactNode } from "react";
import { computeTaskOptimization } from "../../lib/taskOptimization";
import { SectionCard } from "../SectionCard";
import { TaskMap, type MapLegMetric, type MapTurnpoint, type TrackCollection } from "../TaskMap";
import ScoringOperationsPanel from "./ScoringOperationsPanel";
import type {
  AccountSettingsRecord,
  EventFormState,
  PilotRecord,
  PilotSummaryRecord,
  ResultRecord,
  SiteSettingsRecord,
  ScoresPortalTab,
  ScoringTab,
  TaskDraftState,
  TaskRecord,
  UploadRecord,
} from "./types";

const taskTypeOptions = [
  { value: "race_to_goal_with_gates", label: "Race to Goal" },
  { value: "elapsed_time", label: "Elapsed Time" },
  { value: "open_distance", label: "Open Distance" },
] as const;

function normalizeTaskType(value: string | null | undefined): string {
  switch (value) {
    case "race":
    case "race_to_goal":
      return "race_to_goal_with_gates";
    case "speedrun": return "elapsed_time";
    case "speedrun_interval": return "race_to_goal_with_gates";
    default: return value ?? "race_to_goal_with_gates";
  }
}

function taskTypeLabel(value: string): string {
  return taskTypeOptions.find((option) => option.value === normalizeTaskType(value))?.label ?? value;
}

function formatClockTime(value: string | null | undefined, includeSeconds = false): string {
  if (!value) return "-";
  return new Date(value).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: includeSeconds ? "2-digit" : undefined, hour12: true });
}

function formatTaskClockLabel(value: string | null | undefined): string {
  if (!value) return "-";
  const trimmed = value.trim();
  const match = trimmed.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
  if (!match) return value;
  const hours24 = Number(match[1]);
  const minutes = match[2];
  const suffix = hours24 >= 12 ? "PM" : "AM";
  const hours12 = hours24 % 12 || 12;
  return `${hours12}:${minutes} ${suffix}`;
}

function formatElapsedSeconds(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "-";
  const totalSeconds = Math.max(0, Math.round(value));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function formatResultPoints(value: number | null | undefined): string {
  return (value ?? 0).toFixed(1);
}

function formatPointsWithComma(value: number): string {
  const fixed = value.toFixed(1);
  const [int, dec] = fixed.split(".");
  const intWithComma = Number(int).toLocaleString("en-US");
  return `${intWithComma}.${dec}`;
}

function statusAbbreviation(status: string): string | null {
  switch (status) {
    case "absent": return "ABS";
    case "did_not_fly": return "DNF";
    case "minimum_distance": return "MinD";
    default: return null;
  }
}

function formatPenaltyPoints(result: ResultRecord): string {
  const rawScore = Number(result.raw_score_points ?? result.score_points ?? 0);
  const finalScore = Number(result.score_points ?? 0);
  const penalty = rawScore - finalScore;
  return penalty > 0.05 ? `-${penalty.toFixed(1)}` : "-";
}

function formatSpeedKmh(distanceKm: number, elapsedSeconds: number | null | undefined): string {
  if (!elapsedSeconds || elapsedSeconds <= 0) return "-";
  return (distanceKm / (elapsedSeconds / 3600)).toFixed(1);
}

function formatDateLabel(value: string | null | undefined): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString([], { year: "numeric", month: "2-digit", day: "2-digit" });
}

function formatMeters(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(Math.max(0, Math.round(value || 0)));
}

function taskDayQuality(results: ResultRecord[]): string {
  const firstGap = results.find((result) => result.details_json?.gap)?.details_json?.gap as
    | { validity?: { overall?: number } }
    | undefined;
  const overall = Number(firstGap?.validity?.overall ?? NaN);
  return Number.isFinite(overall) ? overall.toFixed(3) : "-";
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

function gapAwardedPoints(result: ResultRecord, key: "distance" | "speed" | "arrival" | "departure" | "leading") {
  const gap = result.details_json?.gap as { awarded_points?: Record<string, number> } | undefined;
  return Number(gap?.awarded_points?.[key] ?? 0);
}

function overallTaskHeader(task: TaskRecord, resultState: string | null): ReactNode {
  const stateClassName = resultState === "provisional" ? "provisional" : resultState === "official" ? "official" : "";
  const stateLabel = resultState === "provisional" ? "Provisional" : resultState === "official" ? "Official" : "";
  const dateLabel = formatDateLabel(task.task_date) !== "-" ? formatDateLabel(task.task_date) : formatDateLabel(task.published_at);
  return (
    <span className="results-header-stack">
      <span>{task.name}</span>
      <span>{dateLabel}</span>
      {stateLabel ? <span className={`result-state-badge ${stateClassName}`}>{stateLabel}</span> : null}
    </span>
  );
}

export interface ScoringSectionProps {
  selectedEventId: number | null;
  selectedTaskId: number | null;
  selectedTask: TaskRecord | null;
  tasks: TaskRecord[];
  results: ResultRecord[];
  uploads: UploadRecord[];
  pilots: PilotRecord[];
  pilotById: Map<number, PilotRecord>;
  pilotNameById: Map<number, string>;
  uploadById: Map<number, UploadRecord>;
  pilotSummary: PilotSummaryRecord[];
  scoredTasks: TaskRecord[];
  taskMetricsById: Map<number, { totalDistanceKm: number; optimizedDistanceKm: number; routeCoordinates: [number, number][]; legMetrics: MapLegMetric[] }>;
  taskDraft: TaskDraftState;
  taskDistanceMetrics: {
    totalDistanceKm: number;
    optimizedDistanceKm: number;
    routeCoordinates: [number, number][];
    legMetrics: MapLegMetric[];
  };
  taskDefinitionRows: Array<{
    label: string;
    legDistanceKm: number;
    identifier: string;
    radiusLabel: string;
    openLabel: string;
    closeLabel: string;
  }>;
  startGateLabels: string[];
  taskResultsColumns: Array<{ key: "distance" | "speed" | "arrival" | "departure" | "leading"; label: string }>;
  eventForm: EventFormState;
  settingsForm: AccountSettingsRecord;
  siteSettings: SiteSettingsRecord;
  canManagePlatform: boolean;
  scoresPortalTab: ScoresPortalTab;
  setScoresPortalTab: (tab: ScoresPortalTab) => void;
  scoringTab: ScoringTab;
  setScoringTab: (tab: ScoringTab) => void;
  adminUploadPilotId: number | null;
  setAdminUploadPilotId: (id: number | null) => void;
  uploadFeedback: { type: "success" | "error" | "pending"; text: string } | null;
  scoringFeedback: { type: "success" | "error"; text: string } | null;
  resultsDownloadFeedback: { type: "success" | "error" | "pending"; text: string; uploadId: number | null; all: boolean } | null;
  selectedResultUploadIds: number[];
  allResultTracksChecked: boolean;
  resultTrackColorsByUploadId: Map<number, string>;
  resultTrackPalette: string[];
  highlightedResultUploadId: number | null;
  setHighlightedResultUploadId: (id: number | null) => void;
  resultsTrackOverlay: TrackCollection | null;
  resultsTrackPilotList: ReactNode;
  resultsTaskMapTurnpoints: MapTurnpoint[];
  allTurnpoints: MapTurnpoint[];
  token: string;
  activeSection: string;
  loadTask: (activeToken: string, taskId: number, loadedTask?: TaskRecord, includeScoringData?: boolean) => Promise<void>;
  refreshPilotSummary: (activeToken: string, eventId: number) => Promise<unknown>;
  uploadIgc: (file: File, pilotId?: number | null) => void;
  uploadIgcBatch: (files: FileList | File[]) => void;
  deleteUpload: (upload: UploadRecord) => void;
  deleteScoredTask: () => void;
  downloadUploadFile: (uploadId: number, filename: string) => void;
  downloadAllIgcFiles: () => void;
  toggleResultTrack: (uploadId: number, checked: boolean) => void;
  toggleAllResultTracks: () => void;
  overlayConfig?: Record<string, boolean>;
}

export default function ScoringSection(props: ScoringSectionProps) {
  const {
    selectedEventId,
    selectedTaskId,
    selectedTask,
    tasks,
    results,
    uploads,
    pilots,
    pilotById,
    pilotNameById,
    uploadById,
    pilotSummary,
    scoredTasks,
    taskMetricsById,
    taskDraft,
    taskDistanceMetrics,
    taskDefinitionRows,
    startGateLabels,
    taskResultsColumns,
    settingsForm,
    siteSettings,
    canManagePlatform,
    scoresPortalTab,
    setScoresPortalTab,
    scoringTab,
    setScoringTab,
    adminUploadPilotId,
    setAdminUploadPilotId,
    uploadFeedback,
    scoringFeedback,
    resultsDownloadFeedback,
    selectedResultUploadIds,
    allResultTracksChecked,
    resultTrackColorsByUploadId,
    resultTrackPalette,
    highlightedResultUploadId,
    setHighlightedResultUploadId,
    resultsTrackOverlay,
    resultsTrackPilotList,
    resultsTaskMapTurnpoints,
    allTurnpoints,
    token,
    activeSection,
    loadTask,
    refreshPilotSummary,
    uploadIgc,
    uploadIgcBatch,
    deleteUpload,
    deleteScoredTask,
    downloadUploadFile,
    downloadAllIgcFiles,
    toggleResultTrack,
    toggleAllResultTracks,
    overlayConfig,
  } = props;
  const publishedTasks = tasks.filter((task) => task.status === "published");
  const scoringSelectedTaskId = selectedTask?.status === "published" ? selectedTaskId ?? "" : "";
  const scoringTaskPoints = taskDraft.points.length ? taskDraft.points : (selectedTask?.points ?? []);
  const scoringTaskMetrics = computeTaskOptimization(scoringTaskPoints);
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
  const selectedTaskResultsOfficial = useMemo(
    () => results.some((result) => result.result_state !== "unscored") && results.every((result) => result.result_state === "official" || result.result_state === "unscored"),
    [results],
  );
  const scoringTaskMapTurnpoints = scoringTaskPoints.map((point, index) => ({
    id: point.turnpoint_id ?? -(index + 1),
    name: point.name,
    code: allTurnpoints.find((turnpoint) => turnpoint.id === point.turnpoint_id)?.code ?? null,
    latitude: point.latitude,
    longitude: point.longitude,
  }));
  const scoredTrackResults = results.filter((result): result is ResultRecord & { upload_id: number } => result.upload_id != null);
  const taskResultsIncludePenalty = results.some((result) => Number(result.raw_score_points ?? result.score_points ?? 0) - Number(result.score_points ?? 0) > 0.05);

  if (!selectedEventId) return <SectionCard title="Scoring" description="Create or select an event first."><p className="hint">Scoring depends on an event and, usually, a selected task.</p></SectionCard>;
  return (
    <div className="section-stack">
      {canManagePlatform ? (
        <div className="tab-row">
          <button type="button" className={scoresPortalTab === "admin" ? "tab-button active" : "tab-button"} onClick={() => setScoresPortalTab("admin")}>Operations</button>
          <button type="button" className={scoresPortalTab === "results" ? "tab-button active" : "tab-button"} onClick={() => setScoresPortalTab("results")}>Results</button>
        </div>
      ) : null}
      {canManagePlatform && scoresPortalTab === "admin" ? (
        <ScoringOperationsPanel
          selectedEventId={selectedEventId}
          selectedTaskId={selectedTaskId}
          selectedTask={selectedTask}
          tasks={tasks}
          token={token}
            activeSection={activeSection}
            loadTask={loadTask}
            refreshPilotSummary={refreshPilotSummary}
          />
        ) : null}
      {!canManagePlatform || scoresPortalTab === "results" ? (
        <div className="stack">
          <div className="scoring-nav">
            {publishedTasks.map((task) => (
              <button
                key={task.id}
                type="button"
                className={scoringTab === "task" && Number(scoringSelectedTaskId) === task.id ? "scoring-nav-btn active" : "scoring-nav-btn"}
                onClick={() => {
                  setScoringTab("task");
                  void loadTask(token, task.id, task, activeSection === "scoring");
                }}
              >
                {task.name}
              </button>
            ))}
            <button
              type="button"
              className={scoringTab === "overall" ? "scoring-nav-btn scoring-nav-overall active" : "scoring-nav-btn scoring-nav-overall"}
              onClick={() => setScoringTab("overall")}
            >
              Overall
            </button>
          </div>
          {scoringTab === "task" ? (
            <div className="stack form-block">
              {taskDefinitionRows.length ? (
                <div className="results-sheet task-definition-sheet">
                  <div className="results-sheet-header">
                    <h3>Task definition {formatDateLabel(selectedTask?.task_date) !== "-" ? <span className="results-header-date">{formatDateLabel(selectedTask?.task_date)}</span> : null}</h3>
                    <p>{selectedTask?.name ?? taskDraft.name} {taskTypeLabel(selectedTask?.task_type ?? taskDraft.task_type) ? `- ${taskTypeLabel(selectedTask?.task_type ?? taskDraft.task_type)}` : ""}</p>
                  </div>
                  <div className="results-table-wrap">
                    <table className="results-table results-table-compact">
                      <thead>
                        <tr>
                          <th>No</th>
                          <th>Leg Dist.</th>
                          <th>Id</th>
                          <th>Radius</th>
                          <th>Open</th>
                          <th>Close</th>
                        </tr>
                      </thead>
                      <tbody>
                        {taskDefinitionRows.map((row) => (
                          <tr key={row.label}>
                            <td><strong>{row.label}</strong></td>
                            <td>{row.legDistanceKm.toFixed(1)} km</td>
                            <td>{row.identifier}</td>
                            <td>{row.radiusLabel}</td>
                            <td>{row.openLabel}</td>
                            <td>{row.closeLabel}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {startGateLabels.length ? <p className="hint task-definition-gates">Start gates: {startGateLabels.join(", ")}</p> : null}
                </div>
              ) : null}
              {results.length ? (
                <div className="results-sheet">
                  <div className="results-sheet-header results-sheet-header-actions">
                    <div>
                      <h3>{selectedTask?.name ?? "Task results"}</h3>
                    </div>
                    <div className="button-row">
                      <button
                        type="button"
                        className="ghost-button"
                        onClick={() => void downloadAllIgcFiles()}
                        disabled={resultsDownloadFeedback?.type === "pending" && resultsDownloadFeedback.all}
                      >
                        {resultsDownloadFeedback?.type === "pending" && resultsDownloadFeedback.all ? "Preparing..." : "Download all IGC"}
                      </button>
                      {resultsDownloadFeedback?.all ? <div className={`status-chip ${resultsDownloadFeedback.type}`}>{resultsDownloadFeedback.text}</div> : null}
                    </div>
                  </div>
                  <div className="results-table-wrap">
                    <table className="results-table results-table-task">
                        <thead>
                          <tr>
                            <th>#</th>
                            <th>Name</th>
                            <th>Nat</th>
                            <th>Glider</th>
                            <th>SS</th>
                            <th>ES</th>
                            <th><span className="results-header-stack"><span>Time</span><span>[h:m:s]</span></span></th>
                            <th><span className="results-header-stack"><span>Speed</span><span>[km/h]</span></span></th>
                            <th><span className="results-header-stack"><span>Distance</span><span>[km]</span></span></th>
                            {taskResultsColumns.map((column) => <th key={column.key}>{taskResultsHeaderLabel(column.key)}</th>)}
                            {taskResultsIncludePenalty ? <th>Penalty</th> : null}
                            <th>Total</th>
                            <th>Download IGC</th>
                            {canManagePlatform ? <th>State</th> : null}
                          </tr>
                        </thead>
                        <tbody>
                          {results.map((result) => {
                            const pilot = pilotById.get(result.pilot_id);
                            const isUnscored = result.result_state === "unscored";
                            const hideUnscoredState = isUnscored && selectedTaskResultsOfficial;
                            const statusLabel = isUnscored ? null : statusAbbreviation(result.status);
                            const stateClassName = hideUnscoredState ? "" : isUnscored ? "unscored" : result.result_state === "official" ? "official" : "provisional";
                            const stateLabel = hideUnscoredState ? "" : isUnscored ? "Unscored" : result.result_state === "official" ? "Official" : "Provisional";
                            const taskPoints = isUnscored ? "-" : formatResultPoints(gapAwardedPoints(result, "distance"));
                            const timePoints = isUnscored ? "-" : formatResultPoints(gapAwardedPoints(result, "speed"));
                            const arrivalPoints = isUnscored ? "-" : formatResultPoints(gapAwardedPoints(result, "arrival"));
                            const departurePoints = isUnscored ? "-" : formatResultPoints(gapAwardedPoints(result, "departure"));
                            const leadingPoints = isUnscored ? "-" : formatResultPoints(gapAwardedPoints(result, "leading"));
                            return (
                              <tr key={result.id}>
                                <td><span className="scoring-ops-rank-badge">{result.rank ?? "-"}</span></td>
                                <td>
                                  <strong>{result.pilot_name}</strong>
                                  {statusLabel ? <span className="results-status-badge">{statusLabel}</span> : null}
                                </td>
                              <td>{pilot?.nation ?? "-"}</td>
                              <td>-</td>
                              <td>{isUnscored ? "-" : formatClockTime(result.started_at, true)}</td>
                                <td>{isUnscored ? "-" : formatClockTime(result.goal_at ?? result.ess_at, true)}</td>
                                <td>{isUnscored ? "-" : formatElapsedSeconds(result.elapsed_seconds)}</td>
                                <td>{isUnscored ? "-" : formatSpeedKmh(result.distance_flown_km, result.elapsed_seconds)}</td>
                                <td>{isUnscored ? "-" : result.distance_flown_km.toFixed(1)}</td>
                                {taskResultsColumns.map((column) => (
                                  <td key={column.key}>
                                    {column.key === "distance" ? taskPoints : column.key === "speed" ? timePoints : column.key === "arrival" ? arrivalPoints : column.key === "departure" ? departurePoints : leadingPoints}
                                  </td>
                                ))}
                                {taskResultsIncludePenalty ? (
                                  <td className={formatPenaltyPoints(result) !== "-" ? "results-table-penalty" : undefined}>
                                    {formatPenaltyPoints(result)}
                                  </td>
                                ) : null}
                                <td className={`results-table-total${isUnscored ? " scoring-ops-muted" : ""}`}>{isUnscored ? "-" : formatPointsWithComma(result.score_points)}</td>
                                <td>
                                  <button
                                    type="button"
                                    className="results-igc-btn"
                                    disabled={result.upload_id == null || isUnscored || (resultsDownloadFeedback?.type === "pending" && resultsDownloadFeedback.uploadId === result.upload_id)}
                                    onClick={() => {
                                      if (result.upload_id == null) return;
                                      void downloadUploadFile(result.upload_id, uploadById.get(result.upload_id)?.filename ?? `${result.pilot_name}.igc`);
                                    }}
                                  >
                                    {resultsDownloadFeedback?.type === "pending" && resultsDownloadFeedback.uploadId === result.upload_id ? "..." : "IGC"}
                                  </button>
                                </td>
                                {canManagePlatform ? (
                                  <td>{stateLabel ? <span className={`result-state-badge ${stateClassName}`}>{stateLabel}</span> : null}</td>
                                ) : null}
                              </tr>
                            );
                        })}
                      </tbody>
                    </table>
                  </div>
                  {scoringTaskPoints.length ? (
                    <div className="results-task-map">
                      <div className="results-task-map-layout">
                        <div className="results-task-map-pilot-list">
                          <div className="results-task-map-pilot-header">
                            <strong>Show pilot tracks</strong>
                            <label className="results-task-map-pilot-master-toggle">
                              <input
                                type="checkbox"
                                checked={allResultTracksChecked}
                                disabled={!results.length}
                                onChange={() => void toggleAllResultTracks()}
                              />
                            </label>
                          </div>
                          <div className="results-task-map-pilot-items">
                            {scoredTrackResults.map((result) => {
                              const isChecked = selectedResultUploadIds.includes(result.upload_id);
                              const pilotTrackColor = resultTrackColorsByUploadId.get(result.upload_id) ?? resultTrackPalette[0];
                              return (
                                <div key={result.id} className={`results-task-map-pilot-item${highlightedResultUploadId === result.upload_id ? " is-highlighted" : ""}`}>
                                  <input
                                    type="checkbox"
                                    checked={isChecked}
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
                            })}
                          </div>
                        </div>
                      <TaskMap
                        key={`scoring-map-${selectedTaskId ?? "none"}`}
                        turnpoints={scoringTaskMapTurnpoints}
                        airspaces={[]}
                        taskPoints={scoringTaskPoints}
                          optimizedRoute={scoringTaskMetrics.routeCoordinates}
                          legMetrics={scoringTaskMetrics.legMetrics}
                          totalDistanceKm={scoringTaskMetrics.totalDistanceKm}
                          optimizedDistanceKm={scoringTaskMetrics.optimizedDistanceKm}
                          track={resultsTrackOverlay}
                          editable={false}
                        taskEditorOverlay={resultsTrackPilotList}
                        highlightedTrackUploadId={highlightedResultUploadId}
                        fitKey={selectedTaskId}
                        fitTurnpoints={allTurnpoints}
                        units={{
                          altitude: settingsForm.altitude_unit,
                            speed: settingsForm.speed_unit,
                            distance: settingsForm.distance_unit,
                            vario: settingsForm.vario_unit,
                          }}
                          telemetrySmoothing={siteSettings}
                          overlayConfig={overlayConfig}
                        />
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : <p className="hint">No scored task results are available yet for the selected task.</p>}
            </div>
          ) : (
            <div className="stack form-block">
              {pilotSummary.length ? (
                <>
                  <div className="results-table-wrap">
                    <table className="results-table results-table-compact">
                      <thead>
                        <tr>
                          <th>Task</th>
                          <th>Date</th>
                          <th>Distance [km]</th>
                          <th>Day Quality</th>
                          <th>Type</th>
                        </tr>
                      </thead>
                      <tbody>
                        {scoredTasks.map((task) => (
                          <tr key={task.id}>
                            <td><strong>{task.name}</strong></td>
                            <td>{formatDateLabel(task.task_date) !== "-" ? formatDateLabel(task.task_date) : formatDateLabel(task.published_at)}</td>
                            <td>{(taskMetricsById.get(task.id)?.optimizedDistanceKm ?? 0).toFixed(1)}</td>
                            <td>{selectedTaskId === task.id ? taskDayQuality(results) : "-"}</td>
                            <td>{taskTypeLabel(task.task_type)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="results-table-wrap">
                    <table className="results-table results-table-task">
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>Name</th>
                          <th>Nat</th>
                          <th>Glider</th>
                          {scoredTasks.map((task) => <th key={task.id}>{overallTaskHeader(task, overallTaskResultStates.get(task.id) ?? null)}</th>)}
                          <th>Total</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pilotSummary.map((summary, index) => {
                          const pilot = pilotById.get(summary.pilot_id);
                          return (
                            <tr key={summary.pilot_id}>
                              <td><span className="scoring-ops-rank-badge">{index + 1}</span></td>
                              <td><strong>{summary.pilot_name}</strong></td>
                              <td>{pilot?.nation ?? "-"}</td>
                              <td>-</td>
                              {scoredTasks.map((task) => <td key={task.id}>{summary.task_scores[String(task.id)] != null ? formatResultPoints(summary.task_scores[String(task.id)]) : "-"}</td>)}
                              <td className="results-table-total">{formatPointsWithComma(summary.total_score_points)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : <p className="hint">No overall event results are available yet.</p>}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
