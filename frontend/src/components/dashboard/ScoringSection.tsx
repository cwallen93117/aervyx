"use client";

import { useId, useMemo, useState, type ReactNode } from "react";
import { computeTaskOptimization } from "../../lib/taskOptimization";
import { formatCalendarDateLabel } from "../../lib/dateLabels";
import { formatPenaltyPoints, formatScorePoints, hasPenaltyDetails, prePenaltyTotalPoints } from "../../lib/scorePenalties";
import { SectionCard } from "../SectionCard";
import { TaskMap, type MapLegMetric, type MapTurnpoint, type TaskEditorOverlayRenderProps, type TrackCollection } from "../TaskMap";
import ScoringOperationsPanel from "./ScoringOperationsPanel";
import { TaskTurnpointsTable } from "./TaskTurnpointsTable";
import type {
  AccountSettingsRecord,
  EventFormState,
  PilotRecord,
  PilotSummaryRecord,
  ResultRecord,
  SiteSettingsRecord,
  ScoresPortalTab,
  ScoringTab,
  TaskResultSummaryRecord,
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

function taskTypeLabelWithGateCount(task: TaskRecord): string {
  const label = taskTypeLabel(task.task_type);
  if (normalizeTaskType(task.task_type) === "race_to_goal_with_gates" && task.start_gate_count > 1) {
    return `${label} with ${task.start_gate_count} start gates`;
  }
  return label;
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
      hour12: true,
      timeZone: timeZone || undefined,
    }).format(parsed);
  } catch {
    return parsed.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: includeSeconds ? "2-digit" : undefined, hour12: true });
  }
}

function resultScoringTimezone(result: ResultRecord, fallback?: string): string | undefined {
  const timezone = result.details_json?.scoring_timezone;
  return typeof timezone === "string" && timezone.trim() ? timezone : fallback;
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

function formatOverallTaskScore(summary: PilotSummaryRecord, taskId: number): string {
  const taskKey = String(taskId);
  const score = summary.task_scores[taskKey];
  if (score == null) return "-";
  const status = summary.task_statuses?.[taskKey];
  if (score === 0 && (status === "absent" || status === "did_not_fly")) {
    return statusAbbreviation(status) ?? formatResultPoints(score);
  }
  return formatResultPoints(score);
}

function formatSpeedKmh(distanceKm: number, elapsedSeconds: number | null | undefined): string {
  if (!elapsedSeconds || elapsedSeconds <= 0) return "-";
  return (distanceKm / (elapsedSeconds / 3600)).toFixed(1);
}

function formatDateLabel(value: string | null | undefined): string {
  return formatCalendarDateLabel(value);
}

function formatMeters(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(Math.max(0, Math.round(value || 0)));
}

function formatDayQualityPercent(value: number | null | undefined): string {
  const dayQuality = Number(value ?? NaN);
  if (!Number.isFinite(dayQuality)) return "-";
  const percent = dayQuality * 100;
  return `${percent.toFixed(2).replace(/\.00$/, "").replace(/(\.\d)0$/, "$1")}%`;
}

function formatTaskStatisticLabel(key: string): string {
  const acronyms = new Map([
    ["ss", "SS"],
    ["ess", "ESS"],
    ["es", "ES"],
    ["qnh", "QNH"],
    ["ftv", "FTV"],
    ["lc", "LC"],
  ]);
  return key
    .replace(/^no_of_/, "number_of_")
    .split("_")
    .filter(Boolean)
    .map((part) => acronyms.get(part.toLowerCase()) ?? part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatTaskStatisticValue(value: unknown): string {
  if (value == null) return "-";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "-";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string") {
    const parsed = new Date(value);
    if (/^\d{4}-\d{2}-\d{2}T/.test(value) && !Number.isNaN(parsed.getTime())) {
      return parsed.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
    }
    return value;
  }
  return JSON.stringify(value);
}

function taskStatisticRows(statistics: Record<string, unknown> | undefined): Array<{ param: string; value: string }> {
  return Object.entries(statistics ?? {})
    .filter(([, value]) => value !== undefined)
    .map(([param, value]) => ({ param, value: formatTaskStatisticValue(value) }));
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

function TaskStatisticsButton({
  taskName,
  statistics,
  onClick,
}: {
  taskName: string;
  statistics: Record<string, unknown> | undefined;
  onClick: (title: string, statistics: Record<string, unknown> | undefined) => void;
}) {
  return (
    <button
      type="button"
      className="field-help-button public-scoring-info-button task-statistics-info-button"
      aria-label={`Show statistics for ${taskName}`}
      aria-haspopup="dialog"
      onClick={(event) => {
        event.stopPropagation();
        onClick(taskName, statistics);
      }}
    >
      i
    </button>
  );
}

function overallTaskHeader(task: TaskRecord, resultState: string | null): ReactNode {
  const stateClassName = resultState === "provisional" ? "provisional" : resultState === "official" ? "official" : "";
  const stateLabel = resultState === "provisional" ? "Provisional" : resultState === "official" ? "Official" : "";
  const dateLabel = formatDateLabel(task.task_date) !== "-" ? formatDateLabel(task.task_date) : formatDateLabel(task.published_at);
  return (
    <span className="results-header-stack">
      <span className={task.is_practice ? "practice-task-label" : undefined}>{task.name}</span>
      <span>{dateLabel}</span>
      {stateLabel ? <span className={`result-state-badge ${stateClassName}`}>{stateLabel}</span> : null}
    </span>
  );
}

function sortOverallPilotSummary(
  summaries: PilotSummaryRecord[],
  scoredTasks: TaskRecord[],
): PilotSummaryRecord[] {
  const practiceTasks = scoredTasks.filter((task) => task.is_practice);
  const latestPracticeTask = practiceTasks[practiceTasks.length - 1];
  const hasCompetitionScores = scoredTasks.some((task) => !task.is_practice);
  if (!hasCompetitionScores && latestPracticeTask) {
    const taskKey = String(latestPracticeTask.id);
    return [...summaries].sort((left, right) => {
      const scoreDiff = (right.task_scores[taskKey] ?? 0) - (left.task_scores[taskKey] ?? 0);
      if (scoreDiff !== 0) return scoreDiff;
      const totalDiff = right.total_score_points - left.total_score_points;
      if (totalDiff !== 0) return totalDiff;
      return left.pilot_name.localeCompare(right.pilot_name);
    });
  }
  return [...summaries].sort((left, right) => {
    const totalDiff = right.total_score_points - left.total_score_points;
    if (totalDiff !== 0) return totalDiff;
    return left.pilot_name.localeCompare(right.pilot_name);
  });
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
              <div><span>Total</span><strong>{formatScorePoints(prePenaltyTotalPoints(result))}</strong></div>
              <div><span>Automatic Penalties</span><strong className="score-penalty-amount">{formatPenaltyPoints({ score_points: 0, penalty_calculation: { ...calculation, total_display_penalty_points: calculation.engine_penalty_points } })}</strong></div>
              <div><span>Manual Penalties</span><strong className="score-penalty-amount">{formatPenaltyPoints({ score_points: 0, penalty_calculation: { ...calculation, total_display_penalty_points: calculation.manual_penalty_points } })}</strong></div>
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
                    <strong className="score-penalty-amount">{formatPenaltyPoints({ score_points: 0, penalty_calculation: { ...calculation, total_display_penalty_points: line.amount_points } })}</strong>
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

function TaskStatisticsModal({
  title,
  statistics,
  onClose,
}: {
  title: string;
  statistics: Record<string, unknown> | undefined;
  onClose: () => void;
}) {
  const rows = taskStatisticRows(statistics);
  return (
    <div className="public-scoring-modal-overlay active" onClick={onClose}>
      <div className="public-scoring-modal task-statistics-modal" onClick={(event) => event.stopPropagation()}>
        <div className="public-scoring-modal-header">
          <div>
            <div className="public-scoring-modal-title">Task statistics</div>
            <div className="public-scoring-modal-subtitle">{title}</div>
          </div>
          <button type="button" className="public-scoring-modal-close" onClick={onClose} aria-label="Close task statistics">x</button>
        </div>
        <div className="public-scoring-table-wrap">
          <table className="public-scoring-table">
            <thead>
              <tr>
                <th>param</th>
                <th>value</th>
              </tr>
            </thead>
            <tbody>
              {rows.length ? rows.map((row) => (
                <tr key={row.param}>
                  <td>{formatTaskStatisticLabel(row.param)}</td>
                  <td>{row.value}</td>
                </tr>
              )) : (
                <tr>
                  <td colSpan={2}>No task statistics are available yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
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
  taskResultSummary: TaskResultSummaryRecord[];
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
    taskResultSummary,
    scoredTasks,
    taskMetricsById,
    taskDraft,
    taskDistanceMetrics,
    taskDefinitionRows,
    startGateLabels,
    taskResultsColumns,
    eventForm,
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
  const fullscreenPilotTracksContentId = useId();
  const [isFullscreenPilotTracksCollapsed, setIsFullscreenPilotTracksCollapsed] = useState(false);
  const [penaltyDetailsResult, setPenaltyDetailsResult] = useState<ResultRecord | null>(null);
  const [taskStatisticsModal, setTaskStatisticsModal] = useState<{ title: string; statistics?: Record<string, unknown> } | null>(null);
  const publishedTasks = tasks.filter((task) => task.status === "published");
  const scoringSelectedTaskId = selectedTask?.status === "published" ? selectedTaskId ?? "" : "";
  const scoringTaskPoints = taskDraft.points.length ? taskDraft.points : (selectedTask?.points ?? []);
  const scoringTaskMetrics = computeTaskOptimization(scoringTaskPoints);
  const taskResultSummaryById = useMemo(() => new Map(taskResultSummary.map((summary) => [summary.task_id, summary])), [taskResultSummary]);
  const showTaskStatistics = (title: string, statistics: Record<string, unknown> | undefined) => setTaskStatisticsModal({ title, statistics });
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
  const overallPilotSummary = useMemo(
    () => sortOverallPilotSummary(pilotSummary, scoredTasks),
    [pilotSummary, scoredTasks],
  );
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
  const taskResultsIncludePenalty = results.some((result) => formatPenaltyPoints(result) !== "-");
  const fullscreenPilotTracksToggleLabel = isFullscreenPilotTracksCollapsed ? "Expand pilot tracks" : "Collapse pilot tracks";
  const fullscreenPilotTracksToggleButton = (
    <button
      type="button"
      className="map-task-editor-collapse-button results-task-map-pilot-collapse-button"
      aria-label={fullscreenPilotTracksToggleLabel}
      aria-controls={fullscreenPilotTracksContentId}
      aria-expanded={!isFullscreenPilotTracksCollapsed}
      title={fullscreenPilotTracksToggleLabel}
      onClick={() => setIsFullscreenPilotTracksCollapsed((current) => !current)}
    >
      <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
        <rect x="4" y="5" width="16" height="14" rx="2" fill="none" stroke="currentColor" strokeWidth="2" />
        <path d="M10 5v14" fill="none" stroke="currentColor" strokeWidth="2" />
        <path
          d={isFullscreenPilotTracksCollapsed ? "M13 9l4 3-4 3" : "M17 9l-4 3 4 3"}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  );
  const renderResultsTrackPilotList = ({
    collapsed = false,
    contentId,
    titleAction,
    className = "",
  }: {
    collapsed?: boolean;
    contentId?: string;
    titleAction?: ReactNode;
    className?: string;
  } = {}) => (
    <div className={`results-task-map-pilot-list${className ? ` ${className}` : ""}${collapsed ? " is-collapsed" : ""}`}>
      <div className="results-task-map-pilot-header">
        <strong>Show pilot tracks</strong>
        <div className="results-task-map-pilot-header-actions">
          <label className="results-task-map-pilot-master-toggle">
            <input
              type="checkbox"
              checked={allResultTracksChecked}
              disabled={!scoredTrackResults.length}
              onChange={() => void toggleAllResultTracks()}
            />
          </label>
          {titleAction}
        </div>
      </div>
      <div id={contentId} className="results-task-map-pilot-items" hidden={collapsed}>
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
  );
  const scoringFullscreenOverlay = ({ collapsed, contentId, overlayId, toggleButton }: TaskEditorOverlayRenderProps) => (
    <div className="scoring-fullscreen-overlay">
      <div id={overlayId} className={`map-task-editor scoring-fullscreen-turnpoints-card${collapsed ? " is-collapsed" : ""}`}>
        <TaskTurnpointsTable
          points={scoringTaskPoints}
          taskPointAdvanced
          turnpoints={allTurnpoints}
          taskDistanceMetrics={scoringTaskMetrics}
          distanceUnit={settingsForm.distance_unit}
          collapsed={collapsed}
          contentId={contentId}
          titleAction={toggleButton}
        />
      </div>
      {renderResultsTrackPilotList({
        collapsed: isFullscreenPilotTracksCollapsed,
        contentId: fullscreenPilotTracksContentId,
        titleAction: fullscreenPilotTracksToggleButton,
        className: "scoring-fullscreen-pilot-tracks-card",
      })}
    </div>
  );

  if (!selectedEventId) return <SectionCard title="Scoring" description="Create or select an event first."><p className="hint">Scoring depends on an event and, usually, a selected task.</p></SectionCard>;
  const taskDefinitionTitle = selectedTask?.name ?? taskDraft.name;
  const taskDefinitionPrimaryMetaParts = [
    taskTypeLabel(selectedTask?.task_type ?? taskDraft.task_type),
    formatDateLabel(selectedTask?.task_date) !== "-" ? formatDateLabel(selectedTask?.task_date) : null,
  ].filter(Boolean);
  const taskDefinitionGatesLabel = startGateLabels.length ? `Start gates: ${startGateLabels.join(", ")}` : null;
  const selectedTaskSummary = selectedTask ? taskResultSummaryById.get(selectedTask.id) : undefined;
  const openTaskResults = (task: TaskRecord) => {
    setScoresPortalTab("results");
    setScoringTab("task");
    setHighlightedResultUploadId(null);
    if (token) {
      void loadTask(token, task.id, task, true);
    }
  };

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
                  {taskDefinitionTitle || taskDefinitionPrimaryMetaParts.length || taskDefinitionGatesLabel ? (
                    <div className="task-definition-heading">
                      {taskDefinitionTitle ? (
                        <div className="task-definition-title-row">
                          <span className="task-definition-title">{taskDefinitionTitle}</span>
                          {selectedTask ? (
                            <TaskStatisticsButton
                              taskName={selectedTask.name}
                              statistics={selectedTaskSummary?.statistics}
                              onClick={showTaskStatistics}
                            />
                          ) : null}
                        </div>
                      ) : null}
                      {taskDefinitionPrimaryMetaParts.length ? <div className="task-definition-meta">{taskDefinitionPrimaryMetaParts.join(" - ")}</div> : null}
                      {taskDefinitionGatesLabel ? <div className="task-definition-meta">{taskDefinitionGatesLabel}</div> : null}
                    </div>
                  ) : null}
                  <div className="results-table-wrap">
                    <table className="results-table results-table-compact overall-task-summary-table">
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
                </div>
              ) : null}
              {results.length ? (
                <div className="results-sheet">
                  <div className="results-sheet-header-actions results-sheet-toolbar">
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
                                <td>{isUnscored ? "-" : formatClockTime(result.started_at, true, resultScoringTimezone(result, eventForm.timezone))}</td>
                                <td>{isUnscored ? "-" : formatClockTime(result.goal_at ?? result.ess_at, true, resultScoringTimezone(result, eventForm.timezone))}</td>
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
                                    {hasPenaltyDetails(result) ? (
                                      <button type="button" className="score-penalty-link" onClick={() => setPenaltyDetailsResult(result)}>
                                        {formatPenaltyPoints(result)}
                                      </button>
                                    ) : (
                                      formatPenaltyPoints(result)
                                    )}
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
                        {renderResultsTrackPilotList()}
                      <TaskMap
                        key={`scoring-map-${selectedTaskId ?? "none"}`}
                        turnpoints={scoringTaskMapTurnpoints}
                        airspaces={[]}
                        taskPoints={scoringTaskPoints}
                          optimizedRoute={scoringTaskMetrics.routeCoordinates}
                          legMetrics={scoringTaskMetrics.legMetrics}
                          track={resultsTrackOverlay}
                          editable={false}
                        taskEditorOverlay={scoringFullscreenOverlay}
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
                    <table className="results-table results-table-compact overall-task-summary-table">
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
                        {scoredTasks.map((task) => {
                          const summary = taskResultSummaryById.get(task.id);
                          return (
                          <tr key={task.id}>
                            <td>
                              <span className="task-statistics-label-row">
                                <a
                                  href="#task-results"
                                  className="overall-task-results-link"
                                  onClick={(event) => {
                                    event.preventDefault();
                                    openTaskResults(task);
                                  }}
                                >
                                  <strong className={task.is_practice ? "practice-task-label" : undefined}>{task.name}</strong>
                                </a>
                                <TaskStatisticsButton taskName={task.name} statistics={summary?.statistics} onClick={showTaskStatistics} />
                              </span>
                            </td>
                            <td>{formatDateLabel(task.task_date) !== "-" ? formatDateLabel(task.task_date) : formatDateLabel(task.published_at)}</td>
                            <td>{(taskMetricsById.get(task.id)?.optimizedDistanceKm ?? 0).toFixed(1)}</td>
                            <td>{formatDayQualityPercent(summary?.day_quality)}</td>
                            <td>{taskTypeLabelWithGateCount(task)}</td>
                          </tr>
                          );
                        })}
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
                        {overallPilotSummary.map((summary, index) => {
                          const pilot = pilotById.get(summary.pilot_id);
                          return (
                            <tr key={summary.pilot_id}>
                              <td><span className="scoring-ops-rank-badge">{index + 1}</span></td>
                              <td><strong>{summary.pilot_name}</strong></td>
                              <td>{pilot?.nation ?? "-"}</td>
                              <td>-</td>
                              {scoredTasks.map((task) => <td key={task.id}>{formatOverallTaskScore(summary, task.id)}</td>)}
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
      {penaltyDetailsResult ? (
        <PenaltyDetailsModal
          result={penaltyDetailsResult}
          taskName={selectedTask?.name ?? "Task"}
          onClose={() => setPenaltyDetailsResult(null)}
        />
      ) : null}
      {taskStatisticsModal ? (
        <TaskStatisticsModal
          title={taskStatisticsModal.title}
          statistics={taskStatisticsModal.statistics}
          onClose={() => setTaskStatisticsModal(null)}
        />
      ) : null}
    </div>
  );
}
