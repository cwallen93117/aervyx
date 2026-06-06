"use client";

import { useCallback, useEffect, useId, useMemo, useState, type ReactNode } from "react";

import { TaskMap, type MapTaskPoint, type MapTurnpoint, type MapUnitPreferences, type TrackCollection } from "../../components/TaskMap";
import type { EventRecord } from "../../components/dashboard/types";
import { TRACK_COLORS, resolveApiBase } from "../../lib/live-tracking-utils";
import { formatCalendarDateLabel } from "../../lib/dateLabels";
import { formatPenaltyPoints, formatScorePoints, prePenaltyTotalPoints, type ScorePenaltyCalculation, type ScorePenaltyRecord } from "../../lib/scorePenalties";
import { FieldHelp, type ScoringHelpId } from "../../lib/scoringParameters";
import { computeTaskOptimization } from "../../lib/taskOptimization";

type PublicEvent = EventRecord;

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
  task_statuses?: Record<string, string>;
};

type TaskResultSummaryRecord = { task_id: number; day_quality: number | null; statistics?: Record<string, unknown> };
type TaskSubTab = "results" | "map";

const defaultUnits: MapUnitPreferences = { altitude: "ft", speed: "mph", distance: "mi", vario: "fpm" };
type ScoringParameterRow = { param: string; value: string; helpId: ScoringHelpId };
type ScoringParameterDefinition = { param: string; field: keyof PublicEvent; helpId: ScoringHelpId };

const scoringParameterDefinitions: ScoringParameterDefinition[] = [
  { param: "id", field: "scoring_formula", helpId: "scoring_formula" },
  { param: "day_quality_override", field: "day_quality_override", helpId: "day_quality_override" },
  { param: "bonus_gr", field: "stopped_glide_bonus", helpId: "stopped_glide_bonus" },
  { param: "jump_the_gun_factor", field: "jump_the_gun_factor", helpId: "jump_the_gun_factor" },
  { param: "jump_the_gun_max", field: "jump_the_gun_max_seconds", helpId: "jump_the_gun_max_seconds" },
  { param: "min_dist", field: "minimum_distance_km", helpId: "minimum_distance_km" },
  { param: "nom_dist", field: "nominal_distance_km", helpId: "nominal_distance_km" },
  { param: "nom_goal", field: "nominal_goal_percent", helpId: "nominal_goal_percent" },
  { param: "nom_launch", field: "nominal_launch", helpId: "nominal_launch" },
  { param: "nom_time", field: "nominal_time_hours", helpId: "nominal_time_hours" },
  { param: "normalize_1000_before_day_quality", field: "normalize_1000_before_day_quality", helpId: "normalize_1000_before_day_quality" },
  { param: "time_points_if_not_in_goal", field: "time_points_if_not_in_goal", helpId: "time_points_if_not_in_goal" },
  { param: "use_1000_points_for_max_day_quality", field: "use_1000_points_for_max_day_quality", helpId: "use_1000_points_for_max_day_quality" },
  { param: "use_arrival_position_points", field: "use_arrival_position_points", helpId: "use_arrival_position_points" },
  { param: "use_arrival_time_points", field: "use_arrival_time_points", helpId: "use_arrival_time_points" },
  { param: "use_departure_points", field: "use_departure_points", helpId: "use_departure_points" },
  { param: "use_difficulty_for_distance_points", field: "use_difficulty_for_distance_points", helpId: "use_difficulty_for_distance_points" },
  { param: "use_distance_points", field: "use_distance_points", helpId: "use_distance_points" },
  { param: "use_distance_squared_for_lc", field: "use_distance_squared_for_lc", helpId: "use_distance_squared_for_lc" },
  { param: "use_leading_points", field: "use_leading_points", helpId: "use_leading_points" },
  { param: "use_semi_circle_control_zone_for_goal_line", field: "use_semi_circle_control_zone_for_goal_line", helpId: "use_semi_circle_control_zone_for_goal_line" },
  { param: "use_time_points", field: "use_time_points", helpId: "use_time_points" },
  { param: "scoring_altitude", field: "scoring_altitude", helpId: "scoring_altitude" },
  { param: "final_glide_decelerator", field: "final_glide_decelerator", helpId: "final_glide_decelerator" },
  { param: "no_final_glide_decelerator_reason", field: "no_final_glide_decelerator_reason", helpId: "no_final_glide_decelerator_reason" },
  { param: "min_time_span_for_valid_task", field: "min_time_span_for_valid_task_minutes", helpId: "min_time_span_for_valid_task_minutes" },
  { param: "score_back_time", field: "score_back_time_minutes", helpId: "score_back_time_minutes" },
  { param: "use_proportional_leading_weight_if_nobody_in_goal", field: "use_proportional_leading_weight_if_nobody_in_goal", helpId: "use_proportional_leading_weight_if_nobody_in_goal" },
  { param: "leading_weight_factor", field: "leading_weight_factor", helpId: "leading_weight_factor" },
  { param: "turnpoint_radius_tolerance", field: "turnpoint_radius_tolerance", helpId: "turnpoint_radius_tolerance" },
  { param: "turnpoint_radius_minimum_absolute_tolerance", field: "turnpoint_radius_minimum_absolute_tolerance_m", helpId: "turnpoint_radius_minimum_absolute_tolerance_m" },
  { param: "number_of_decimals_task_results", field: "number_of_decimals_task_results", helpId: "number_of_decimals_task_results" },
  { param: "number_of_decimals_competition_results", field: "number_of_decimals_competition_results", helpId: "number_of_decimals_competition_results" },
  { param: "redistribute_removed_time_points_as_distance_points", field: "redistribute_removed_time_points_as_distance_points", helpId: "redistribute_removed_time_points_as_distance_points" },
  { param: "use_best_score_for_ftv_validity", field: "use_best_score_for_ftv_validity", helpId: "use_best_score_for_ftv_validity" },
  { param: "use_constant_leading_weight", field: "use_constant_leading_weight", helpId: "use_constant_leading_weight" },
  { param: "use_flat_decline_of_timepoints", field: "use_flat_decline_of_timepoints", helpId: "use_flat_decline_of_timepoints" },
];

function formatScoringParameterValue(value: PublicEvent[keyof PublicEvent]): string {
  if (typeof value === "boolean") return value ? "1" : "0";
  if (value == null) return "";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

function scoringParameterRows(event: PublicEvent): ScoringParameterRow[] {
  return scoringParameterDefinitions.map((definition) => ({
    param: definition.param,
    value: formatScoringParameterValue(event[definition.field]),
    helpId: definition.helpId,
  }));
}

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
  return formatCalendarDateLabel(value);
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

function formatMeters(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(Math.max(0, Math.round(value || 0)));
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

function overallTaskHeader(task: PublicTask, resultState: string | null | undefined): ReactNode {
  const state = resultStateLabel(resultState);
  const dateLabel = formatDateLabel(task.task_date) !== "-" ? formatDateLabel(task.task_date) : formatDateLabel(task.published_at);
  return (
    <span className="results-header-stack">
      <span className={task.is_practice ? "practice-task-label" : undefined}>{task.name}</span>
      <span>{dateLabel}</span>
      {state ? <span className={`result-state-badge ${state.className}`}>{state.label}</span> : null}
    </span>
  );
}

function sortOverallPilotSummary(
  summaries: PilotSummaryRecord[],
  scoredTasks: PublicTask[],
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
      hour12: true,
      timeZone: timeZone || undefined,
    }).format(parsed);
  } catch {
    return parsed.toLocaleTimeString([], {
      hour: "numeric",
      minute: "2-digit",
      second: includeSeconds ? "2-digit" : undefined,
      hour12: true,
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

function startGateLabelsForTask(task: PublicTask): string[] {
  if (task.task_type !== "race_to_goal_with_gates" || !task.start_open_time || !task.start_gate_count) {
    return [];
  }
  const [hoursText, minutesText] = task.start_open_time.split(":");
  const baseMinutes = Number(hoursText) * 60 + Number(minutesText);
  if (!Number.isFinite(baseMinutes)) return [];
  if (task.start_gate_count === 1) {
    return [formatTaskClockLabel(task.start_open_time)];
  }
  if (task.start_gate_interval_seconds == null) {
    return [];
  }
  const intervalMinutes = task.start_gate_interval_seconds / 60;
  return Array.from({ length: task.start_gate_count }, (_, index) => {
    const totalMinutes = baseMinutes + index * intervalMinutes;
    const hours = Math.floor(totalMinutes / 60) % 24;
    const minutes = Math.round(totalMinutes % 60);
    return formatTaskClockLabel(`${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`);
  });
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

function formatOverallTaskScore(summary: PilotSummaryRecord, taskId: number, formatter: (value: number) => string): string {
  const taskKey = String(taskId);
  const score = summary.task_scores[taskKey];
  if (score == null) return "-";
  const status = summary.task_statuses?.[taskKey];
  if (score === 0 && (status === "absent" || status === "did_not_fly")) {
    return statusAbbreviation(status) ?? formatter(score);
  }
  return formatter(score);
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

function ScoringParametersModal({
  event,
  activeHelpId,
  setActiveHelpId,
  onClose,
}: {
  event: PublicEvent;
  activeHelpId: ScoringHelpId | null;
  setActiveHelpId: (value: ScoringHelpId | null) => void;
  onClose: () => void;
}) {
  const rows = scoringParameterRows(event);
  return (
    <div className="public-scoring-modal-overlay active" onClick={onClose}>
      <div className="public-scoring-modal" onClick={(clickEvent) => clickEvent.stopPropagation()}>
        <div className="public-scoring-modal-header">
          <div>
            <div className="public-scoring-modal-title">Scoring formula settings</div>
            <div className="public-scoring-modal-subtitle">{event.name}</div>
          </div>
          <button type="button" className="public-scoring-modal-close" onClick={onClose} aria-label="Close scoring parameters">x</button>
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
              {rows.map((row) => (
                <tr key={row.param}>
                  <td>
                    <span className="public-scoring-param-name scoring-help-open-right">
                      <span>{row.param}</span>
                      <FieldHelp helpId={row.helpId} activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                    </span>
                  </td>
                  <td>{row.value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
  const [showScoringParameters, setShowScoringParameters] = useState(false);
  const [activeScoringParameterHelpId, setActiveScoringParameterHelpId] = useState<ScoringHelpId | null>(null);
  const [taskStatisticsModal, setTaskStatisticsModal] = useState<{ title: string; statistics?: Record<string, unknown> } | null>(null);

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
  const showTaskStatistics = (title: string, statistics: Record<string, unknown> | undefined) => setTaskStatisticsModal({ title, statistics });
  const taskMetricsById = useMemo(
    () => new Map(tasks.map((task) => [task.id, computeTaskOptimization(task.points)])),
    [tasks],
  );
  const scoredTasks = useMemo(
    () => tasks.filter((task) => pilotSummary.some((summary) => summary.task_scores[String(task.id)] != null)).sort(compareTasksForScores),
    [tasks, pilotSummary],
  );
  const visiblePilotSummary = useMemo(
    () => sortOverallPilotSummary(pilotSummary, scoredTasks),
    [pilotSummary, scoredTasks],
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
    () => taskResults.filter((result): result is ResultRecord & { upload_id: number } => result.upload_id != null && result.result_state !== "unscored"),
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
  const selectedTaskDefinitionRows = useMemo(() => {
    if (!selectedTask || !selectedTaskMetrics) return [];
    let cumulativeDistance = 0;
    return selectedTask.points.map((point, index) => {
      if (index > 0) {
        cumulativeDistance += selectedTaskMetrics.legMetrics[index - 1]?.optimizedDistanceKm ?? 0;
      }
      const pointType = point.point_type.toLowerCase();
      const suffix = pointType === "launch" || pointType === "start"
        ? "SS"
        : pointType === "ess" || pointType === "goal"
          ? "ES"
          : "";
      return {
        label: `${index + 1}${suffix ? ` ${suffix}` : ""}`,
        legDistanceKm: cumulativeDistance,
        identifier: point.name,
        radiusLabel: `${formatMeters(point.radius_m)} m`,
        openLabel: formatTaskClockLabel((selectedTask.task_type === "race_to_goal_with_gates" ? selectedTask.start_open_time : selectedTask.task_start_time) || selectedTask.task_start_time || "-"),
        closeLabel: formatTaskClockLabel(selectedTask.start_close_time || selectedTask.task_finish_time || "-"),
      };
    });
  }, [selectedTask, selectedTaskMetrics]);
  const selectedTaskStartGateLabels = useMemo(
    () => (selectedTask ? startGateLabelsForTask(selectedTask) : []),
    [selectedTask],
  );
  const selectedTaskDefinitionPrimaryMetaParts = useMemo(() => {
    if (!selectedTask) return [];
    return [
      taskTypeLabel(selectedTask.task_type),
      formatDateLabel(selectedTask.task_date) !== "-" ? formatDateLabel(selectedTask.task_date) : null,
    ].filter(Boolean);
  }, [selectedTask]);
  const selectedTaskDefinitionGatesLabel = selectedTaskStartGateLabels.length ? `Start gates: ${selectedTaskStartGateLabels.join(", ")}` : null;
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
    setShowScoringParameters(false);
    setActiveScoringParameterHelpId(null);
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

  const openTaskResults = useCallback((taskId: number) => {
    setTaskTab("results");
    selectTask(taskId);
  }, [selectTask]);

  const renderOverall = () => (
    <div className="scores-panel">
      <div className="scores-panel-header">
        <div>
          <div className="public-overall-title-row">
            <h1>Overall</h1>
            <button
              type="button"
              className="field-help-button public-scoring-info-button"
              aria-label="Show scoring parameters"
              aria-haspopup="dialog"
              aria-expanded={showScoringParameters}
              onClick={() => {
                setActiveScoringParameterHelpId(null);
                setShowScoringParameters(true);
              }}
            >
              i
            </button>
          </div>
          <p>{selectedEvent?.name ?? "Competition"} {selectedEvent?.location ? `- ${selectedEvent.location}` : ""}</p>
        </div>
      </div>
      {scoredTasks.length ? (
        <div className="results-table-wrap scores-summary-table-wrap">
          <table className="results-table results-table-compact overall-task-summary-table overall-score-task-summary-table">
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
                          openTaskResults(task.id);
                        }}
                      >
                        <strong className={task.is_practice ? "practice-task-label" : undefined}>{task.name}</strong>
                      </a>
                      <TaskStatisticsButton taskName={task.name} statistics={summary?.statistics} onClick={showTaskStatistics} />
                    </span>
                  </td>
                  <td>{formatDateLabel(task.task_date) !== "-" ? formatDateLabel(task.task_date) : formatDateLabel(task.published_at)}</td>
                  <td>{(taskMetricsById.get(task.id)?.optimizedDistanceKm ?? 0).toFixed(1)} km</td>
                  <td>{formatDayQualityPercent(summary?.day_quality)}</td>
                  <td>{taskTypeLabelWithGateCount(task)}</td>
                </tr>
                );
              })}
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
                {scoredTasks.map((task) => <th key={task.id}>{overallTaskHeader(task, overallTaskResultStates.get(task.id))}</th>)}
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
                  {scoredTasks.map((task) => <td key={task.id}>{formatOverallTaskScore(summary, task.id, formatPoints)}</td>)}
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
    return (
      <div className="scores-panel">
        {selectedTaskDefinitionRows.length ? (
          <div className="results-sheet task-definition-sheet">
            {selectedTask.name || selectedTaskDefinitionPrimaryMetaParts.length || selectedTaskDefinitionGatesLabel ? (
              <div className="task-definition-heading">
                <div className="task-definition-title-row">
                  <span className="task-definition-title">{selectedTask.name}</span>
                  <TaskStatisticsButton
                    taskName={selectedTask.name}
                    statistics={taskResultSummaryById.get(selectedTask.id)?.statistics}
                    onClick={showTaskStatistics}
                  />
                </div>
                {selectedTaskDefinitionPrimaryMetaParts.length ? (
                  <div className="task-definition-meta">{selectedTaskDefinitionPrimaryMetaParts.join(" - ")}</div>
                ) : null}
                {selectedTaskDefinitionGatesLabel ? <div className="task-definition-meta">{selectedTaskDefinitionGatesLabel}</div> : null}
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
                  {selectedTaskDefinitionRows.map((row) => (
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
                  const isUnscored = result.result_state === "unscored";
                  const statusLabel = statusAbbreviation(result.status);
                  const penaltyLabel = formatPenaltyPoints(result);
                  return (
                    <tr key={result.id}>
                      <td><span className="scoring-ops-rank-badge">{result.rank ?? "-"}</span></td>
                      <td>
                        <strong>{result.pilot_name}</strong>
                        {statusLabel ? <span className="results-status-badge">{statusLabel}</span> : null}
                      </td>
                      <td>{isUnscored ? "-" : formatClockTime(result.started_at, true, resultScoringTimezone(result, selectedEvent?.timezone))}</td>
                      <td>{isUnscored ? "-" : formatClockTime(result.goal_at ?? result.ess_at, true, resultScoringTimezone(result, selectedEvent?.timezone))}</td>
                      <td>{isUnscored ? "-" : formatElapsedSeconds(result.elapsed_seconds)}</td>
                      <td>{isUnscored ? "-" : formatSpeedKmh(result.distance_flown_km, result.elapsed_seconds)}</td>
                      <td>{isUnscored ? "-" : result.distance_flown_km.toFixed(1)}</td>
                      {taskResultsColumns.map((column) => <td key={column}>{isUnscored ? "-" : formatPoints(gapAwardedPoints(result, column))}</td>)}
                      {taskResultsIncludePenalty ? (
                        <td className={penaltyLabel !== "-" ? "results-table-penalty" : undefined}>
                          {penaltyLabel !== "-" ? (
                            <a
                              href="#"
                              className="score-penalty-link"
                              onClick={(event) => {
                                event.preventDefault();
                                setPenaltyDetailsResult(result);
                              }}
                            >
                              {penaltyLabel}
                            </a>
                          ) : (
                            penaltyLabel
                          )}
                        </td>
                      ) : null}
                      <td className={`results-table-total${isUnscored ? " scoring-ops-muted" : ""}`}>{isUnscored ? "-" : formatPointsWithComma(result.score_points)}</td>
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
        <div className="scores-header-controls">
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
          <a href={watchLiveHref} className="public-header-link public-header-link-live">Live</a>
        </div>
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
      {showScoringParameters && selectedEvent ? (
        <ScoringParametersModal
          event={selectedEvent}
          activeHelpId={activeScoringParameterHelpId}
          setActiveHelpId={setActiveScoringParameterHelpId}
          onClose={() => {
            setShowScoringParameters(false);
            setActiveScoringParameterHelpId(null);
          }}
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
