"use client";

import { type FormEvent, type KeyboardEvent, type ReactNode, useEffect, useMemo, useState } from "react";

import { AppSidebar } from "../../components/AppSidebar";
import { SectionCard } from "../../components/SectionCard";
import { TaskMap, type MapAirspaceRegion, type MapTaskPoint, type MapTurnpoint, type TrackCollection } from "../../components/TaskMap";
import { computeTaskOptimization } from "../../lib/taskOptimization";

type SidebarSection = "events" | "tasks" | "scoring" | "live_tracking" | "drivers" | "settings" | "admin";
type EventTab = "details" | "turnpoints" | "airspace" | "participants" | "scoring";
type User = { id: number; username: string; full_name: string; role: "admin" | "organizer" | "pilot"; profile_type: "pilot" | "driver"; pilot_id: number | null };
type AccountSettingsRecord = {
  username: string;
  full_name: string;
  role: "admin" | "organizer" | "pilot";
  profile_type: "pilot" | "driver";
  email: string | null;
  first_name: string | null;
  last_name: string | null;
  nation: string | null;
  competition_number: string | null;
  civl_id: string | null;
  access_token?: string | null;
};
type AdminUserRecord = {
  id: number;
  username: string;
  full_name: string;
  role: "admin" | "organizer" | "pilot";
  profile_type: "pilot" | "driver";
  pilot_id: number | null;
  email: string | null;
  pilot_name: string | null;
  competition_number: string | null;
  is_active: boolean;
  created_at: string;
};
type EventRecord = {
  id: number;
  name: string;
  location: string;
  starts_on: string;
  ends_on: string;
  timezone: string;
  scoring_formula: string;
  nominal_distance_km: number;
  nominal_time_hours: number;
  nominal_launch: number;
  minimum_distance_km: number;
  nominal_goal_percent: number;
  score_back_time_minutes: number;
  goal_ss_penalty: number;
  day_quality_override: number;
  time_points_if_not_in_goal: number;
  jump_the_gun_factor: number;
  jump_the_gun_max_seconds: number;
  stopped_glide_bonus: number;
  use_1000_points_for_max_day_quality: boolean;
  normalize_1000_before_day_quality: boolean;
  use_distance_points: boolean;
  use_time_points: boolean;
  use_leading_points: boolean;
  use_arrival_position_points: boolean;
  use_arrival_time_points: boolean;
  use_departure_points: boolean;
  use_difficulty_for_distance_points: boolean;
  use_distance_squared_for_lc: boolean;
  use_semi_circle_control_zone_for_goal_line: boolean;
  use_proportional_leading_weight_if_nobody_in_goal: boolean;
  redistribute_removed_time_points_as_distance_points: boolean;
  use_best_score_for_ftv_validity: boolean;
  use_constant_leading_weight: boolean;
  use_pwca2019_for_lc: boolean;
  use_flat_decline_of_timepoints: boolean;
  scoring_altitude: string;
  final_glide_decelerator: string;
  no_final_glide_decelerator_reason: string;
  min_time_span_for_valid_task_minutes: number;
  leading_weight_factor: number;
  turnpoint_radius_tolerance: number;
  turnpoint_radius_minimum_absolute_tolerance_m: number;
  number_of_decimals_task_results: number;
  number_of_decimals_competition_results: number;
  visible_airspace_classes_json: string[];
  show_restricted_fields: boolean;
  penalties_json: Record<string, unknown>;
  updated_at: string;
  pilot_count: number;
  task_count: number;
  turnpoint_count: number;
  airspace_count: number;
  restricted_field_count: number;
};
type PilotRecord = { id: number; first_name: string; last_name: string; email?: string | null; nation?: string | null; competition_number: string | null; civl_id?: string | null; portal_username: string | null; temp_password: string | null };
type TurnpointRecord = MapTurnpoint & { event_id: number; source_id: number | null; elevation_m: number | null };
type TurnpointSourceRecord = { id: number; event_id: number; filename: string; file_format: string; sha256: string; enabled: boolean; uploaded_at: string; turnpoint_count: number };
type TaskPointRecord = MapTaskPoint & { id?: number; turnpoint_id: number | null };
type TaskRecord = {
  id: number;
  event_id: number;
  name: string;
  status: string;
  task_type: string;
  task_start_time: string | null;
  task_finish_time: string | null;
  start_open_time: string | null;
  start_close_time: string | null;
  start_gate_count: number;
  start_gate_interval_seconds: number | null;
  version: number;
  nominal_distance_km: number;
  nominal_time_hours: number;
  nominal_launch: number;
  minimum_distance_km: number;
  penalties_json: Record<string, unknown>;
  published_at: string | null;
  points: TaskPointRecord[];
};
type ResultRecord = { id: number; upload_id: number; pilot_id: number; pilot_name: string; competition_number?: string | null; status: string; distance_flown_km: number; elapsed_seconds?: number | null; started_at?: string | null; ess_at?: string | null; goal_at?: string | null; score_points: number; rank: number | null; details_json: Record<string, unknown> };
type PilotSummaryRecord = { pilot_id: number; pilot_name: string; competition_number?: string | null; total_score_points: number; tasks_scored: number; best_distance_km: number; task_scores: Record<string, number> };
type UploadRecord = { id: number; pilot_id: number; filename: string; sha256: string; uploaded_at: string; metadata_json: Record<string, unknown> };
type TurnpointUploadResponse = { source_id: number; format: string; imported_count: number; sha256: string; filename: string };
type BulkUploadItemRecord = { filename: string; matched: boolean; upload_id?: number | null; pilot_id?: number | null; pilot_name?: string | null; message: string };
type AirspaceSourceRecord = {
  id: number;
  event_id: number;
  kind: "airspace" | "restricted_field";
  filename: string;
  file_format: string;
  sha256: string;
  uploaded_at: string;
  region_count: number;
  enabled?: boolean;
};
type AirspaceUploadResponse = { source_id: number; kind: "airspace" | "restricted_field"; format: string; imported_count: number; sha256: string; filename: string };
type TaskDraftState = {
  id: number | null;
  name: string;
  task_type: string;
  task_start_time: string;
  task_finish_time: string;
  start_open_time: string;
  start_close_time: string;
  start_gate_count: number;
  start_gate_interval_minutes: number | "";
  nominal_distance_km: number;
  nominal_time_hours: number;
  nominal_launch: number;
  minimum_distance_km: number;
  penalties_text: string;
  points: TaskPointRecord[];
};
type ScoresPortalTab = "admin" | "results";
type ScoringTab = "task" | "overall";
type AirspaceCategoryOption = "B" | "C" | "D" | "P" | "Q" | "R" | "TFR" | "OTHER";
type TaskPointMode = "simple" | "advanced";

function resolveApiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
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
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return configured ?? "http://localhost:8000";
}
const TOKEN_KEY = "flightcomp-platform-token";
const SIDEBAR_COMPACT_KEY = "flightcomp-platform-sidebar-compact";
const LAST_EVENT_KEY = "flightcomp-platform-last-event-id";
const ACTIVE_SECTION_KEY = "flightcomp-platform-active-section";
const SESSION_COOKIE = "flightcomp_session";
const DEFAULT_MESSAGE = "Use admin / admin1234 or pilot-demo / pilot1234 after the backend seed runs.";
const adminSidebarItems = [
  { id: "events", label: "Events" },
  { id: "tasks", label: "Tasks" },
  { id: "scoring", label: "Scores" },
  { id: "live_tracking", label: "Live Tracking" },
  { id: "drivers", label: "Drivers" },
  { id: "settings", label: "Settings" },
  { id: "admin", label: "Admin" },
] satisfies Array<{ id: SidebarSection; label: string; description?: string }>;
const organizerSidebarItems = [
  { id: "events", label: "Events" },
  { id: "tasks", label: "Tasks" },
  { id: "scoring", label: "Scores" },
  { id: "live_tracking", label: "Live Tracking" },
  { id: "drivers", label: "Drivers" },
  { id: "settings", label: "Settings" },
] satisfies Array<{ id: SidebarSection; label: string; description?: string }>;
const pilotSidebarItems = [
  { id: "tasks", label: "Tasks" },
  { id: "scoring", label: "Scores" },
  { id: "live_tracking", label: "Live Tracking" },
  { id: "drivers", label: "Drivers" },
  { id: "settings", label: "Settings" },
] satisfies Array<{ id: SidebarSection; label: string; description?: string }>;
const guestSidebarItems = [
  { id: "scoring", label: "Scores" },
  { id: "live_tracking", label: "Live Tracking" },
] satisfies Array<{ id: SidebarSection; label: string; description?: string }>;

function normalizeSectionForRole(section: string | null, role: User["role"] | null): SidebarSection {
  if (role === "pilot") {
    if (section === "tasks" || section === "scoring" || section === "live_tracking" || section === "drivers" || section === "settings") {
      return section;
    }
    return "tasks";
  }
  if (role === "organizer") {
    if (section === "events" || section === "tasks" || section === "scoring" || section === "live_tracking" || section === "drivers" || section === "settings") {
      return section;
    }
    return "events";
  }
  if (section === "events" || section === "tasks" || section === "scoring" || section === "live_tracking" || section === "drivers" || section === "settings" || section === "admin") {
    return section;
  }
  return "events";
}

const scoringFormulaOptions = [
  { value: "GAP2021", label: "GAP 2021" },
  { value: "GAP2020", label: "GAP 2020" },
  { value: "GAP2018", label: "GAP 2018" },
  { value: "GAP2016", label: "GAP 2016" },
  { value: "GAP2008", label: "GAP 2008" },
  { value: "OzGAP2005", label: "OzGAP 2005" },
  { value: "PWC2016", label: "PWC 2016" },
] as const;
const scoringAltitudeOptions = [
  { value: "GPS", label: "GPS altitude" },
  { value: "QNH", label: "QNH altitude" },
  { value: "pressure", label: "Pressure altitude" },
] as const;
const finalGlideDeceleratorOptions = [
  { value: "none", label: "None" },
  { value: "default", label: "Default decelerator" },
  { value: "stopped_task", label: "Stopped-task decelerator" },
] as const;
const eventTabItems = [
  { id: "details", label: "Event Details" },
  { id: "turnpoints", label: "Turnpoint Files" },
  { id: "airspace", label: "Airspace / Restricted Fields" },
  { id: "participants", label: "Participants" },
  { id: "scoring", label: "Scoring Parameters" },
] satisfies Array<{ id: EventTab; label: string }>;
const airspaceCategoryOptions = [
  { value: "B", label: "Class B" },
  { value: "C", label: "Class C" },
  { value: "D", label: "Class D" },
  { value: "P", label: "Prohibited" },
  { value: "Q", label: "Danger" },
  { value: "R", label: "Restricted" },
  { value: "TFR", label: "TFR" },
  { value: "OTHER", label: "Other / advisory" },
] satisfies Array<{ value: AirspaceCategoryOption; label: string }>;

const pointTypeLabels: Record<string, string> = {
  launch: "Launch",
  start: "Start",
  turnpoint: "Turnpoint",
  ESS: "ESS",
  goal: "Goal",
};
const taskTypeOptions = [
  { value: "race_to_goal_with_gates", label: "Race to Goal with Gates" },
  { value: "race_to_goal", label: "Race to Goal" },
  { value: "elapsed_time", label: "Elapsed Time" },
  { value: "open_distance", label: "Open Distance" },
] as const;
const meterFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

function blankEventForm() {
  return {
    name: "",
    location: "",
    starts_on: "2026-04-18",
    ends_on: "2026-04-24",
    timezone: "",
    scoring_formula: "GAP2021",
    nominal_distance_km: 60,
    nominal_time_hours: 1.5,
    nominal_launch: 0.95,
    minimum_distance_km: 5,
    nominal_goal_percent: 0.3,
    score_back_time_minutes: 15,
    goal_ss_penalty: 0,
    day_quality_override: 0,
    time_points_if_not_in_goal: 1,
    jump_the_gun_factor: 0,
    jump_the_gun_max_seconds: 0,
    stopped_glide_bonus: 0,
    use_1000_points_for_max_day_quality: false,
    normalize_1000_before_day_quality: false,
    use_distance_points: true,
    use_time_points: true,
    use_leading_points: true,
    use_arrival_position_points: false,
    use_arrival_time_points: false,
    use_departure_points: false,
    use_difficulty_for_distance_points: true,
    use_distance_squared_for_lc: false,
    use_semi_circle_control_zone_for_goal_line: true,
    use_proportional_leading_weight_if_nobody_in_goal: true,
    redistribute_removed_time_points_as_distance_points: false,
    use_best_score_for_ftv_validity: true,
    use_constant_leading_weight: false,
    use_pwca2019_for_lc: false,
    use_flat_decline_of_timepoints: false,
    scoring_altitude: "GPS",
    final_glide_decelerator: "none",
    no_final_glide_decelerator_reason: "",
    min_time_span_for_valid_task_minutes: 60,
    leading_weight_factor: 1,
    turnpoint_radius_tolerance: 0.0005,
    turnpoint_radius_minimum_absolute_tolerance_m: 5,
    number_of_decimals_task_results: 2,
    number_of_decimals_competition_results: 1,
    visible_airspace_classes_json: ["B", "C", "D", "P", "Q", "R", "TFR", "OTHER"],
    show_restricted_fields: true,
    penalties_text: "{}",
  };
}

function nextDraftEventName(events: EventRecord[]) {
  const existingNames = new Set(events.map((event) => event.name.trim().toLowerCase()));
  if (!existingNames.has("new event")) {
    return "New event";
  }
  let suffix = 2;
  while (existingNames.has(`new event ${suffix}`)) {
    suffix += 1;
  }
  return `New event ${suffix}`;
}

function blankTaskDraft(overrides: Partial<TaskDraftState> = {}): TaskDraftState {
  return {
    id: null,
    name: "New Task",
    task_type: "race_to_goal",
    task_start_time: "",
    task_finish_time: "",
    start_open_time: "",
    start_close_time: "",
    start_gate_count: 1,
    start_gate_interval_minutes: "",
    nominal_distance_km: 60,
    nominal_time_hours: 1.5,
    nominal_launch: 0.95,
    minimum_distance_km: 5,
    penalties_text: "{}",
    points: [],
    ...overrides,
  };
}

function blankSettingsForm(): AccountSettingsRecord {
  return {
    username: "",
    full_name: "",
    role: "pilot",
    profile_type: "pilot",
    email: "",
    first_name: "",
    last_name: "",
    nation: "",
    competition_number: "",
    civl_id: "",
  };
}

function normalizeIdentityEmail(value: string): string {
  return value.trim().toLowerCase();
}

function normalizeTaskType(value: string | null | undefined): string {
  switch (value) {
    case "race":
      return "race_to_goal";
    case "speedrun":
      return "elapsed_time";
    case "speedrun_interval":
      return "race_to_goal_with_gates";
    default:
      return value ?? "race_to_goal";
  }
}

function taskDraftFromEvent(event: EventRecord | null | undefined): TaskDraftState {
  return blankTaskDraft({
    nominal_distance_km: event?.nominal_distance_km ?? 60,
    nominal_time_hours: event?.nominal_time_hours ?? 1.5,
    nominal_launch: event?.nominal_launch ?? 0.95,
    minimum_distance_km: event?.minimum_distance_km ?? 5,
    penalties_text: JSON.stringify(event?.penalties_json ?? {}, null, 2),
  });
}

function formatMeters(value: number): string {
  return meterFormatter.format(Math.max(0, Math.round(value || 0)));
}

function formatClockTime(value: string | null | undefined, includeSeconds = false): string {
  if (!value) return "-";
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: includeSeconds ? "2-digit" : undefined });
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

function taskTypeLabel(value: string): string {
  return taskTypeOptions.find((option) => option.value === normalizeTaskType(value))?.label ?? value;
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

function taskDayQuality(results: ResultRecord[]): string {
  const firstGap = results.find((result) => result.details_json?.gap)?.details_json?.gap as
    | { validity?: { overall?: number } }
    | undefined;
  const overall = Number(firstGap?.validity?.overall ?? NaN);
  return Number.isFinite(overall) ? overall.toFixed(3) : "-";
}

function isAdvancedPointType(pointType: string): boolean {
  return pointType === "launch" || pointType === "ESS";
}

function toSimplePointType(pointType: string): string {
  if (pointType === "launch") return "start";
  if (pointType === "ESS") return "goal";
  return pointType;
}

function pointTypeOptionsForMode(mode: TaskPointMode): Array<{ value: string; label: string }> {
  return mode === "advanced"
    ? [
        { value: "launch", label: "Launch" },
        { value: "start", label: "Start" },
        { value: "turnpoint", label: "Turnpoint" },
        { value: "ESS", label: "ESS" },
        { value: "goal", label: "Goal" },
      ]
    : [
        { value: "start", label: "Start" },
        { value: "turnpoint", label: "Turnpoint" },
        { value: "goal", label: "Goal" },
      ];
}

function sanitizeMeterInput(rawValue: string): string {
  return rawValue.replace(/[^\d]/g, "").replace(/^0+(?=\d)/, "");
}

function taskPointInputKey(point: TaskPointRecord, index: number): string {
  return `${point.id ?? point.turnpoint_id ?? point.name}-${index}`;
}

function normalizeTimeValue(value: string | null | undefined): string {
  if (!value) return "";
  const trimmed = value.trim();
  if (/^\d{2}:\d{2}:\d{2}$/.test(trimmed)) {
    return trimmed.slice(0, 5);
  }
  return trimmed;
}

function timeOrNull(value: string): string | null {
  return value.trim() ? value : null;
}

function taskTypeBehavior(taskType: string) {
  switch (taskType) {
    case "race_to_goal_with_gates":
      return { usesStartWindow: true, usesMultipleGates: true };
    case "race_to_goal":
      return { usesStartWindow: true, usesMultipleGates: false };
    case "elapsed_time":
    case "open_distance":
    default:
      return { usesStartWindow: false, usesMultipleGates: false };
  }
}

function eventToForm(event: EventRecord | null | undefined) {
  return event
    ? {
        name: event.name,
        location: event.location,
        starts_on: event.starts_on,
        ends_on: event.ends_on,
        timezone: event.timezone,
        scoring_formula: event.scoring_formula,
        nominal_distance_km: event.nominal_distance_km,
        nominal_time_hours: event.nominal_time_hours,
        nominal_launch: event.nominal_launch,
        minimum_distance_km: event.minimum_distance_km,
        nominal_goal_percent: event.nominal_goal_percent,
        score_back_time_minutes: event.score_back_time_minutes,
        goal_ss_penalty: event.goal_ss_penalty,
        day_quality_override: event.day_quality_override,
        time_points_if_not_in_goal: event.time_points_if_not_in_goal,
        jump_the_gun_factor: event.jump_the_gun_factor,
        jump_the_gun_max_seconds: event.jump_the_gun_max_seconds,
        stopped_glide_bonus: event.stopped_glide_bonus,
        use_1000_points_for_max_day_quality: event.use_1000_points_for_max_day_quality,
        normalize_1000_before_day_quality: event.normalize_1000_before_day_quality,
        use_distance_points: event.use_distance_points,
        use_time_points: event.use_time_points,
        use_leading_points: event.use_leading_points,
        use_arrival_position_points: event.use_arrival_position_points,
        use_arrival_time_points: event.use_arrival_time_points,
        use_departure_points: event.use_departure_points,
        use_difficulty_for_distance_points: event.use_difficulty_for_distance_points,
        use_distance_squared_for_lc: event.use_distance_squared_for_lc,
        use_semi_circle_control_zone_for_goal_line: event.use_semi_circle_control_zone_for_goal_line,
        use_proportional_leading_weight_if_nobody_in_goal: event.use_proportional_leading_weight_if_nobody_in_goal,
        redistribute_removed_time_points_as_distance_points: event.redistribute_removed_time_points_as_distance_points,
        use_best_score_for_ftv_validity: event.use_best_score_for_ftv_validity,
        use_constant_leading_weight: event.use_constant_leading_weight,
        use_pwca2019_for_lc: event.use_pwca2019_for_lc,
        use_flat_decline_of_timepoints: event.use_flat_decline_of_timepoints,
        scoring_altitude: event.scoring_altitude,
        final_glide_decelerator: event.final_glide_decelerator,
        no_final_glide_decelerator_reason: event.no_final_glide_decelerator_reason,
        min_time_span_for_valid_task_minutes: event.min_time_span_for_valid_task_minutes,
        leading_weight_factor: event.leading_weight_factor,
        turnpoint_radius_tolerance: event.turnpoint_radius_tolerance,
        turnpoint_radius_minimum_absolute_tolerance_m: event.turnpoint_radius_minimum_absolute_tolerance_m,
        number_of_decimals_task_results: event.number_of_decimals_task_results,
        number_of_decimals_competition_results: event.number_of_decimals_competition_results,
        visible_airspace_classes_json: event.visible_airspace_classes_json,
        show_restricted_fields: event.show_restricted_fields,
        penalties_text: JSON.stringify(event.penalties_json ?? {}, null, 2),
      }
    : blankEventForm();
}

function sortEventsByUpdatedAt(eventList: EventRecord[]): EventRecord[] {
  return [...eventList].sort((left, right) => {
    const leftTime = Date.parse(left.updated_at || "") || 0;
    const rightTime = Date.parse(right.updated_at || "") || 0;
    if (leftTime !== rightTime) return rightTime - leftTime;
    return left.name.localeCompare(right.name);
  });
}

async function apiFetch<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  headers.set("Authorization", `Bearer ${token}`);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${resolveApiBase()}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) throw new Error((await response.text()) || `Request failed: ${response.status}`);
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

async function apiFetchBlob(path: string, token: string, init: RequestInit = {}): Promise<{ blob: Blob; filename: string | null }> {
  const headers = new Headers(init.headers ?? {});
  headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${resolveApiBase()}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) throw new Error((await response.text()) || `Request failed: ${response.status}`);
  const disposition = response.headers.get("content-disposition");
  const match = disposition?.match(/filename="?([^"]+)"?/i);
  return { blob: await response.blob(), filename: match?.[1] ?? null };
}

async function apiFetchPublic<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${resolveApiBase()}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) throw new Error((await response.text()) || `Request failed: ${response.status}`);
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export default function HomePage() {
  const [token, setToken] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [activeSection, setActiveSection] = useState<SidebarSection>("events");
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [eventEditorId, setEventEditorId] = useState<number | null>(null);
  const [eventTab, setEventTab] = useState<EventTab>("details");
  const [pilots, setPilots] = useState<PilotRecord[]>([]);
  const [pilotDirectory, setPilotDirectory] = useState<PilotRecord[]>([]);
  const [turnpoints, setTurnpoints] = useState<TurnpointRecord[]>([]);
  const [turnpointSources, setTurnpointSources] = useState<TurnpointSourceRecord[]>([]);
  const [airspaces, setAirspaces] = useState<MapAirspaceRegion[]>([]);
  const [airspaceSources, setAirspaceSources] = useState<AirspaceSourceRecord[]>([]);
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [results, setResults] = useState<ResultRecord[]>([]);
  const [pilotSummary, setPilotSummary] = useState<PilotSummaryRecord[]>([]);
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [track, setTrack] = useState<TrackCollection | null>(null);
  const [selectedResultUploadIds, setSelectedResultUploadIds] = useState<number[]>([]);
  const [resultTracksByUploadId, setResultTracksByUploadId] = useState<Record<number, TrackCollection>>({});
  const [message, setMessage] = useState(DEFAULT_MESSAGE);
  const [error, setError] = useState("");
  const [authChecking, setAuthChecking] = useState(true);
  const [eventForm, setEventForm] = useState(blankEventForm());
    const [pilotForm, setPilotForm] = useState({ first_name: "", last_name: "", email: "", nation: "", competition_number: "", civl_id: "" });
    const [selectedDirectoryPilotId, setSelectedDirectoryPilotId] = useState<number | null>(null);
    const [taskDraft, setTaskDraft] = useState<TaskDraftState>(blankTaskDraft());
  const [radiusDrafts, setRadiusDrafts] = useState<Record<string, string>>({});
  const [turnpointSearch, setTurnpointSearch] = useState("");
  const [taskAdvancedOpen, setTaskAdvancedOpen] = useState(false);
  const [taskPointAdvanced, setTaskPointAdvanced] = useState(false);
  const [scoringFeedback, setScoringFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [eventFormFeedback, setEventFormFeedback] = useState<Record<"details" | "scoring" | "airspace", { type: "success" | "error"; text: string } | null>>({
    details: null,
    scoring: null,
    airspace: null,
  });
  const [taskFeedback, setTaskFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [uploadFeedback, setUploadFeedback] = useState<{ type: "success" | "error" | "pending"; text: string } | null>(null);
  const [resultsDownloadFeedback, setResultsDownloadFeedback] = useState<{
    type: "success" | "error" | "pending";
    text: string;
    uploadId: number | null;
    all: boolean;
  } | null>(null);
  const [sidebarCompact, setSidebarCompact] = useState(false);
  const [authPanelOpen, setAuthPanelOpen] = useState(false);
  const [scoresPortalTab, setScoresPortalTab] = useState<ScoresPortalTab>("results");
  const [scoringTab, setScoringTab] = useState<ScoringTab>("task");
  const [adminUploadPilotId, setAdminUploadPilotId] = useState<number | null>(null);
  const [settingsForm, setSettingsForm] = useState<AccountSettingsRecord>(blankSettingsForm());
  const [settingsPasswordForm, setSettingsPasswordForm] = useState({ current_password: "", new_password: "", confirm_password: "" });
  const [settingsFeedback, setSettingsFeedback] = useState<{
    profile: { type: "success" | "error"; text: string } | null;
    password: { type: "success" | "error"; text: string } | null;
  }>({ profile: null, password: null });
  const [adminUsers, setAdminUsers] = useState<AdminUserRecord[]>([]);
  const [adminFeedback, setAdminFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const resultTrackPalette = useMemo(() => ["#2563eb", "#dc2626", "#16a34a", "#7c3aed", "#d97706", "#0891b2", "#db2777", "#65a30d"], []);

  const selectedEvent = useMemo(() => events.find((event) => event.id === selectedEventId) ?? null, [events, selectedEventId]);
    const selectedTask = useMemo(() => tasks.find((task) => task.id === selectedTaskId) ?? null, [tasks, selectedTaskId]);
    const taskDistanceMetrics = useMemo(() => computeTaskOptimization(taskDraft.points), [taskDraft.points]);
    const currentTaskTypeBehavior = useMemo(() => taskTypeBehavior(taskDraft.task_type), [taskDraft.task_type]);
    const taskPointMode: TaskPointMode = taskPointAdvanced ? "advanced" : "simple";
    const taskPointTypeOptions = useMemo(() => pointTypeOptionsForMode(taskPointMode), [taskPointMode]);
    const availableDirectoryPilots = useMemo(
      () => pilotDirectory.filter((candidate) => !pilots.some((pilot) => pilot.id === candidate.id)),
      [pilotDirectory, pilots],
    );
  const pilotById = useMemo(() => new Map(pilots.map((pilot) => [pilot.id, pilot])), [pilots]);
  const pilotNameById = useMemo(() => new Map(pilots.map((pilot) => [pilot.id, `${pilot.first_name} ${pilot.last_name}`.trim()])), [pilots]);
  const uploadById = useMemo(() => new Map(uploads.map((upload) => [upload.id, upload])), [uploads]);
  const resultTrackColorsByUploadId = useMemo(() => {
    const colorMap = new Map<number, string>();
    results.forEach((result, index) => {
      colorMap.set(result.upload_id, resultTrackPalette[index % resultTrackPalette.length]);
    });
    return colorMap;
  }, [resultTrackPalette, results]);
  const filteredTurnpoints = useMemo(() => {
      const query = turnpointSearch.trim().toLowerCase();
      if (!query) return [];
      return turnpoints
        .filter((turnpoint) => {
          const haystack = `${turnpoint.name} ${turnpoint.code ?? ""}`.toLowerCase();
          return haystack.includes(query);
        })
        .slice(0, 12);
  }, [turnpointSearch, turnpoints]);
  const resultsTrackOverlay = useMemo<TrackCollection | null>(() => {
    if (!selectedResultUploadIds.length) {
      return null;
    }
    const features = selectedResultUploadIds.flatMap((uploadId) => {
      const collection = resultTracksByUploadId[uploadId];
      if (!collection) {
        return [];
      }
      const upload = uploadById.get(uploadId);
      const pilotName = upload ? pilotNameById.get(upload.pilot_id) ?? `Pilot ${upload.pilot_id}` : `Pilot ${uploadId}`;
      const color = resultTrackColorsByUploadId.get(uploadId) ?? resultTrackPalette[0];
      return collection.features.map((feature) => ({
        ...feature,
        properties: {
          ...feature.properties,
          color,
          pilot_name: pilotName,
          upload_id: uploadId,
        },
      }));
    });
    return { type: "FeatureCollection", features };
  }, [pilotNameById, resultTrackColorsByUploadId, resultTrackPalette, resultTracksByUploadId, selectedResultUploadIds, uploadById]);
  const taskDefinitionRows = useMemo(() => {
    let cumulativeDistance = 0;
    return taskDraft.points.map((point, index) => {
      if (index > 0) {
        cumulativeDistance += taskDistanceMetrics.legMetrics[index - 1]?.optimizedDistanceKm ?? 0;
      }
      const sourceTurnpoint = turnpoints.find((turnpoint) => turnpoint.id === point.turnpoint_id);
      const suffix = point.point_type === "launch" || point.point_type === "start"
        ? "SS"
        : point.point_type === "ESS" || point.point_type === "goal"
          ? "ES"
          : "";
      return {
        label: `${index + 1}${suffix ? ` ${suffix}` : ""}`,
        legDistanceKm: cumulativeDistance,
        identifier: sourceTurnpoint?.code || point.name,
        radiusLabel: `${formatMeters(point.radius_m)} m`,
        openLabel: formatTaskClockLabel(taskDraft.start_open_time || taskDraft.task_start_time || "-"),
        closeLabel: formatTaskClockLabel(taskDraft.start_close_time || taskDraft.task_finish_time || "-"),
      };
    });
  }, [taskDistanceMetrics.legMetrics, taskDraft.points, taskDraft.start_open_time, taskDraft.start_close_time, taskDraft.task_finish_time, taskDraft.task_start_time, turnpoints]);
  const startGateLabels = useMemo(() => {
    if (!currentTaskTypeBehavior.usesMultipleGates || !taskDraft.start_open_time || !taskDraft.start_gate_count || taskDraft.start_gate_interval_minutes === "") {
      return [];
    }
    const [hoursText, minutesText] = taskDraft.start_open_time.split(":");
    const baseMinutes = Number(hoursText) * 60 + Number(minutesText);
    return Array.from({ length: taskDraft.start_gate_count }, (_, index) => {
      const totalMinutes = baseMinutes + index * Number(taskDraft.start_gate_interval_minutes || 0);
      const hours = Math.floor(totalMinutes / 60) % 24;
      const minutes = totalMinutes % 60;
      return formatTaskClockLabel(`${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`);
    });
  }, [currentTaskTypeBehavior.usesMultipleGates, taskDraft.start_gate_count, taskDraft.start_gate_interval_minutes, taskDraft.start_open_time]);
  const visibleAirspaces = useMemo(() => {
    const enabled = new Set<string>(eventForm.visible_airspace_classes_json ?? []);
    const enabledSourceIds = new Set(airspaceSources.filter((source) => source.enabled ?? true).map((source) => source.id));
    return airspaces.filter((region) => {
      if (!enabledSourceIds.has(region.source_id)) {
        return false;
      }
      if (region.is_restricted_field) {
        return eventForm.show_restricted_fields;
      }
      return enabled.has(region.display_category);
    });
  }, [airspaces, airspaceSources, eventForm.show_restricted_fields, eventForm.visible_airspace_classes_json]);
  const taskResultsColumns = useMemo(() => {
    const columns: Array<{ key: "distance" | "speed" | "arrival" | "departure" | "leading"; label: string }> = [];
    if (eventForm.use_distance_points) columns.push({ key: "distance", label: "Dist. Points" });
    if (eventForm.use_time_points) columns.push({ key: "speed", label: "Time Points" });
    if (eventForm.use_arrival_position_points || eventForm.use_arrival_time_points) columns.push({ key: "arrival", label: "Arrival Points" });
    if (eventForm.use_departure_points) columns.push({ key: "departure", label: "Departure Points" });
    if (eventForm.use_leading_points) columns.push({ key: "leading", label: "Leading Points" });
    return columns;
  }, [
    eventForm.use_arrival_position_points,
    eventForm.use_arrival_time_points,
    eventForm.use_departure_points,
    eventForm.use_distance_points,
    eventForm.use_leading_points,
    eventForm.use_time_points,
  ]);
  const scoredTasks = useMemo(
    () => tasks.filter((task) => pilotSummary.some((summary) => summary.task_scores[String(task.id)] != null)).sort((left, right) => left.id - right.id),
    [tasks, pilotSummary],
  );
  const taskMetricsById = useMemo(() => new Map(tasks.map((task) => [task.id, computeTaskOptimization(task.points)])), [tasks]);
  const isAdmin = user?.role === "admin";
  const canManagePlatform = user?.role === "admin" || user?.role === "organizer";
  const resultsTaskMapTurnpoints = useMemo<MapTurnpoint[]>(
    () =>
      taskDraft.points.map((point, index) => ({
        id: point.turnpoint_id ?? -(index + 1),
        name: point.name,
        code: turnpoints.find((turnpoint) => turnpoint.id === point.turnpoint_id)?.code ?? null,
        latitude: point.latitude,
        longitude: point.longitude,
      })),
    [taskDraft.points, turnpoints],
  );
  const taskSectionMapTurnpoints = useMemo<MapTurnpoint[]>(
    () => (
      canManagePlatform
        ? turnpoints
        : taskDraft.points.map((point, index) => ({
            id: point.turnpoint_id ?? -(index + 1),
            name: point.name,
            code: turnpoints.find((turnpoint) => turnpoint.id === point.turnpoint_id)?.code ?? null,
            latitude: point.latitude,
            longitude: point.longitude,
          }))
    ),
    [canManagePlatform, taskDraft.points, turnpoints],
  );
  const sidebarItems = user?.role === "admin" ? adminSidebarItems : user?.role === "organizer" ? organizerSidebarItems : pilotSidebarItems;

  useEffect(() => {
    const savedToken = window.localStorage.getItem(TOKEN_KEY);
    setSidebarCompact(window.localStorage.getItem(SIDEBAR_COMPACT_KEY) === "true");
    if (!savedToken) {
      setAuthChecking(false);
      window.location.replace("/login?next=/dashboard");
      return;
    }

    void bootstrap(savedToken)
      .catch(() => {
        window.localStorage.removeItem(TOKEN_KEY);
        document.cookie = `${SESSION_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax`;
        setToken("");
        setUser(null);
        setError("");
        window.location.replace("/login?next=/dashboard");
      })
      .finally(() => setAuthChecking(false));
  }, []);

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_COMPACT_KEY, String(sidebarCompact));
  }, [sidebarCompact]);

  useEffect(() => {
    if (!user) return;
    window.localStorage.setItem(ACTIVE_SECTION_KEY, activeSection);
  }, [activeSection, user]);

  useEffect(() => {
    if (user?.role === "pilot" && activeSection === "events") {
      setActiveSection("tasks");
    }
  }, [activeSection, user]);

  useEffect(() => {
    if (!canManagePlatform) {
      setAdminUploadPilotId(null);
      return;
    }
    if (!pilots.length) {
      setAdminUploadPilotId(null);
      return;
    }
    if (adminUploadPilotId && pilots.some((pilot) => pilot.id === adminUploadPilotId)) {
      return;
    }
    setAdminUploadPilotId(pilots[0].id);
  }, [adminUploadPilotId, canManagePlatform, pilots]);

  async function bootstrap(activeToken: string) {
    document.cookie = `${SESSION_COOKIE}=1; Path=/; Max-Age=2592000; SameSite=Lax`;
    setToken(activeToken);
    setError("");
    const [me, rawEvents, settings] = await Promise.all([
      apiFetch<User>("/api/auth/me", activeToken),
      apiFetch<EventRecord[]>("/api/events", activeToken),
      apiFetch<AccountSettingsRecord>("/api/auth/settings", activeToken),
    ]);
    const loadedEvents = sortEventsByUpdatedAt(rawEvents);
    const storedEventId = Number(window.localStorage.getItem(LAST_EVENT_KEY) ?? "");
    const storedSection = window.localStorage.getItem(ACTIVE_SECTION_KEY);
    const preferredEvent = loadedEvents.find((event) => event.id === storedEventId) ?? loadedEvents[0] ?? null;
    setUser(me);
    setSettingsForm(settings);
    setActiveSection(normalizeSectionForRole(storedSection, me.role));
    setEvents(loadedEvents);
    await refreshPilotDirectory(activeToken, me);
    await refreshAdminUsers(activeToken, me);
    if (preferredEvent) {
      window.localStorage.setItem(LAST_EVENT_KEY, String(preferredEvent.id));
      setSelectedEventId(preferredEvent.id);
      setEventEditorId(preferredEvent.id);
      setEventForm(eventToForm(preferredEvent));
      await loadEvent(activeToken, preferredEvent.id, preferredEvent, me);
    } else {
      setSelectedEventId(null);
      setEventEditorId(null);
      setEventForm(blankEventForm());
      setPilots([]);
      setTurnpoints([]);
      setTurnpointSources([]);
      setAirspaces([]);
      setAirspaceSources([]);
      setTasks([]);
      setPilotSummary([]);
      setResults([]);
      setUploads([]);
      setTrack(null);
      setSelectedResultUploadIds([]);
      setResultTracksByUploadId({});
      setRadiusDrafts({});
      setTaskDraft(taskDraftFromEvent(null));
    }
  }

  async function refreshEvents(activeToken: string) {
    const loadedEvents = sortEventsByUpdatedAt(await apiFetch<EventRecord[]>("/api/events", activeToken));
    setEvents(loadedEvents);
    return loadedEvents;
  }

  async function refreshPilotDirectory(activeToken: string, activeUser?: User | null) {
    if (!["admin", "organizer"].includes((activeUser ?? user)?.role ?? "")) {
      setPilotDirectory([]);
      return [];
    }
    const loadedPilots = await apiFetch<PilotRecord[]>("/api/pilots", activeToken);
    setPilotDirectory(loadedPilots);
    return loadedPilots;
  }

  async function refreshAdminUsers(activeToken: string, activeUser?: User | null) {
    if ((activeUser ?? user)?.role !== "admin") {
      setAdminUsers([]);
      return [];
    }
    const loadedUsers = await apiFetch<AdminUserRecord[]>("/api/auth/users", activeToken);
    setAdminUsers(loadedUsers);
    return loadedUsers;
  }

  async function loadEvent(activeToken: string, eventId: number, currentEvent?: EventRecord | null, activeUser?: User | null, preferredTaskId?: number | null) {
    setSelectedEventId(eventId);
    window.localStorage.setItem(LAST_EVENT_KEY, String(eventId));
    const activeEvent = currentEvent ?? events.find((event) => event.id === eventId) ?? null;
    setEventEditorId(eventId);
    setEventForm(eventToForm(activeEvent));
    const [loadedPilots, loadedTurnpoints, loadedTurnpointSources, loadedAirspaces, loadedAirspaceSources, loadedTasks, loadedSummary] = await Promise.all([
      apiFetch<PilotRecord[]>(`/api/events/${eventId}/pilots`, activeToken),
      apiFetch<TurnpointRecord[]>(`/api/events/${eventId}/turnpoints`, activeToken),
      apiFetch<TurnpointSourceRecord[]>(`/api/events/${eventId}/turnpoint-sources`, activeToken),
      apiFetch<MapAirspaceRegion[]>(`/api/events/${eventId}/airspaces`, activeToken),
      apiFetch<AirspaceSourceRecord[]>(`/api/events/${eventId}/airspace-sources`, activeToken),
      apiFetch<TaskRecord[]>(`/api/events/${eventId}/tasks`, activeToken),
      apiFetch<PilotSummaryRecord[]>(`/api/events/${eventId}/pilot-summary`, activeToken),
    ]);
    const viewer = activeUser ?? user;
    const visibleTasks = viewer?.role === "pilot" ? loadedTasks.filter((task) => task.status === "published") : loadedTasks;
    setPilots(loadedPilots);
    setTurnpoints(loadedTurnpoints);
    setTurnpointSources(loadedTurnpointSources);
    setAirspaces(loadedAirspaces);
    setAirspaceSources(loadedAirspaceSources);
    setTasks(visibleTasks);
    setPilotSummary(loadedSummary);
    setTrack(null);
    setSelectedResultUploadIds([]);
    setResultTracksByUploadId({});
    setRadiusDrafts({});
    const nextTask = visibleTasks.find((task) => task.id === preferredTaskId)
      ?? visibleTasks.find((task) => task.id === selectedTaskId)
      ?? visibleTasks[0];
    if (nextTask) {
      await loadTask(activeToken, nextTask.id, nextTask);
    } else {
      setSelectedTaskId(null);
      setResults([]);
      setUploads([]);
      setTaskPointAdvanced(false);
      setScoringFeedback(null);
      setTaskFeedback(null);
      setEventFormFeedback({ details: null, scoring: null, airspace: null });
      setTaskDraft(taskDraftFromEvent(activeEvent));
    }
  }

  async function selectEvent(event: EventRecord) {
    if (!token) return;
    setEventEditorId(event.id);
    setEventForm(eventToForm(event));
    await loadEvent(token, event.id, event);
  }

  async function loadTask(activeToken: string, taskId: number, loadedTask?: TaskRecord) {
    const task = loadedTask ?? (await apiFetch<TaskRecord>(`/api/tasks/${taskId}`, activeToken));
    const [loadedResults, loadedUploads] = await Promise.all([
      apiFetch<ResultRecord[]>(`/api/tasks/${taskId}/results`, activeToken),
      apiFetch<UploadRecord[]>(`/api/tasks/${taskId}/uploads`, activeToken),
    ]);
    setSelectedTaskId(taskId);
    setResults(loadedResults);
    setUploads(loadedUploads);
    setTrack(null);
    setSelectedResultUploadIds([]);
    setResultTracksByUploadId({});
    setResultsDownloadFeedback(null);
    setRadiusDrafts({});
    setTaskPointAdvanced(task.points.some((point) => isAdvancedPointType(point.point_type)));
    setScoringFeedback(null);
    setTaskFeedback(null);
    setTaskDraft({
      id: task.id,
      name: task.name,
      task_type: normalizeTaskType(task.task_type),
      task_start_time: normalizeTimeValue(task.task_start_time),
      task_finish_time: normalizeTimeValue(task.task_finish_time),
      start_open_time: normalizeTimeValue(task.start_open_time),
      start_close_time: normalizeTimeValue(task.start_close_time),
      start_gate_count: task.start_gate_count || 1,
      start_gate_interval_minutes: task.start_gate_interval_seconds == null ? "" : task.start_gate_interval_seconds / 60,
      nominal_distance_km: task.nominal_distance_km,
      nominal_time_hours: task.nominal_time_hours,
      nominal_launch: task.nominal_launch,
      minimum_distance_km: task.minimum_distance_km,
      penalties_text: JSON.stringify(task.penalties_json, null, 2),
      points: task.points,
    });
  }

  function signOut() {
    window.localStorage.removeItem(TOKEN_KEY);
    document.cookie = `${SESSION_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax`;
    window.location.replace("/login");
  }

  async function saveAccountSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setSettingsFeedback((current) => ({ ...current, profile: null }));
    try {
      const payload = await apiFetch<AccountSettingsRecord>("/api/auth/settings", token, {
        method: "PATCH",
        body: JSON.stringify({
          username: normalizeIdentityEmail(settingsForm.username),
          full_name: settingsForm.full_name,
          profile_type: settingsForm.profile_type,
          email: normalizeIdentityEmail(settingsForm.username) || null,
          first_name: settingsForm.first_name || null,
          last_name: settingsForm.last_name || null,
          nation: settingsForm.nation || null,
          competition_number: settingsForm.competition_number || null,
          civl_id: settingsForm.civl_id || null,
        }),
      });
      setSettingsForm({
        username: payload.username,
        full_name: payload.full_name,
        role: payload.role,
        profile_type: payload.profile_type,
        email: payload.email,
        first_name: payload.first_name,
        last_name: payload.last_name,
        nation: payload.nation,
        competition_number: payload.competition_number,
        civl_id: payload.civl_id,
      });
      if (payload.access_token) {
        window.localStorage.setItem(TOKEN_KEY, payload.access_token);
        document.cookie = `${SESSION_COOKIE}=1; Path=/; Max-Age=2592000; SameSite=Lax`;
        setToken(payload.access_token);
      }
      setUser((current) => (current ? { ...current, username: payload.username, full_name: payload.full_name, profile_type: payload.profile_type } : current));
      setSettingsFeedback((current) => ({ ...current, profile: { type: "success", text: "Account settings saved." } }));
    } catch (caught) {
      setSettingsFeedback((current) => ({
        ...current,
        profile: { type: "error", text: caught instanceof Error ? caught.message : "Could not save account settings." },
      }));
    }
  }

  async function savePasswordSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setSettingsFeedback((current) => ({ ...current, password: null }));
    if (settingsPasswordForm.new_password.length < 8) {
      setSettingsFeedback((current) => ({ ...current, password: { type: "error", text: "New password must be at least 8 characters." } }));
      return;
    }
    if (settingsPasswordForm.new_password !== settingsPasswordForm.confirm_password) {
      setSettingsFeedback((current) => ({ ...current, password: { type: "error", text: "New password and confirmation do not match." } }));
      return;
    }
    try {
      await apiFetch<{ status: string }>("/api/auth/change-password", token, {
        method: "POST",
        body: JSON.stringify({
          current_password: settingsPasswordForm.current_password,
          new_password: settingsPasswordForm.new_password,
        }),
      });
      setSettingsPasswordForm({ current_password: "", new_password: "", confirm_password: "" });
      setSettingsFeedback((current) => ({ ...current, password: { type: "success", text: "Password updated successfully." } }));
    } catch (caught) {
      setSettingsFeedback((current) => ({
        ...current,
        password: { type: "error", text: caught instanceof Error ? caught.message : "Could not update password." },
      }));
    }
  }

  async function saveAdminUser(userRecord: AdminUserRecord) {
    if (!token) return;
    setAdminFeedback(null);
    try {
      const payload = await apiFetch<AdminUserRecord>(`/api/auth/users/${userRecord.id}`, token, {
        method: "PATCH",
        body: JSON.stringify({
          role: userRecord.role,
          profile_type: userRecord.profile_type,
          is_active: userRecord.is_active,
        }),
      });
      setAdminUsers((current) => current.map((entry) => (entry.id === payload.id ? payload : entry)));
      setAdminFeedback({ type: "success", text: `Updated ${payload.full_name}.` });
    } catch (caught) {
      setAdminFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not update that user." });
    }
  }

  async function deleteAdminUser(userRecord: AdminUserRecord) {
    if (!token) return;
    setAdminFeedback(null);
    try {
      await apiFetch<void>(`/api/auth/users/${userRecord.id}`, token, { method: "DELETE" });
      setAdminUsers((current) => current.filter((entry) => entry.id !== userRecord.id));
      setAdminFeedback({ type: "success", text: `Deleted ${userRecord.full_name}.` });
    } catch (caught) {
      setAdminFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not delete that user." });
    }
  }

  async function saveEvent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    let penaltiesJson: Record<string, unknown>;
    try {
      penaltiesJson = JSON.parse(eventForm.penalties_text || "{}") as Record<string, unknown>;
    } catch {
      setError("Scoring penalties must be valid JSON before saving the event.");
      return;
    }
    const payload = {
      name: eventForm.name,
      location: eventForm.location,
      starts_on: eventForm.starts_on,
      ends_on: eventForm.ends_on,
      timezone: eventForm.timezone,
      scoring_formula: eventForm.scoring_formula,
      nominal_distance_km: eventForm.nominal_distance_km,
      nominal_time_hours: eventForm.nominal_time_hours,
      nominal_launch: eventForm.nominal_launch,
      minimum_distance_km: eventForm.minimum_distance_km,
      nominal_goal_percent: eventForm.nominal_goal_percent,
      score_back_time_minutes: eventForm.score_back_time_minutes,
      goal_ss_penalty: eventForm.goal_ss_penalty,
      day_quality_override: eventForm.day_quality_override,
      time_points_if_not_in_goal: eventForm.time_points_if_not_in_goal,
      jump_the_gun_factor: eventForm.jump_the_gun_factor,
      jump_the_gun_max_seconds: eventForm.jump_the_gun_max_seconds,
      stopped_glide_bonus: eventForm.stopped_glide_bonus,
      use_1000_points_for_max_day_quality: eventForm.use_1000_points_for_max_day_quality,
      normalize_1000_before_day_quality: eventForm.normalize_1000_before_day_quality,
      use_distance_points: eventForm.use_distance_points,
      use_time_points: eventForm.use_time_points,
      use_leading_points: eventForm.use_leading_points,
      use_arrival_position_points: eventForm.use_arrival_position_points,
      use_arrival_time_points: eventForm.use_arrival_time_points,
      use_departure_points: eventForm.use_departure_points,
      use_difficulty_for_distance_points: eventForm.use_difficulty_for_distance_points,
      use_distance_squared_for_lc: eventForm.use_distance_squared_for_lc,
      use_semi_circle_control_zone_for_goal_line: eventForm.use_semi_circle_control_zone_for_goal_line,
      use_proportional_leading_weight_if_nobody_in_goal: eventForm.use_proportional_leading_weight_if_nobody_in_goal,
      redistribute_removed_time_points_as_distance_points: eventForm.redistribute_removed_time_points_as_distance_points,
      use_best_score_for_ftv_validity: eventForm.use_best_score_for_ftv_validity,
      use_constant_leading_weight: eventForm.use_constant_leading_weight,
      use_pwca2019_for_lc: eventForm.use_pwca2019_for_lc,
      use_flat_decline_of_timepoints: eventForm.use_flat_decline_of_timepoints,
      scoring_altitude: eventForm.scoring_altitude,
      final_glide_decelerator: eventForm.final_glide_decelerator,
      no_final_glide_decelerator_reason: eventForm.no_final_glide_decelerator_reason,
      min_time_span_for_valid_task_minutes: eventForm.min_time_span_for_valid_task_minutes,
      leading_weight_factor: eventForm.leading_weight_factor,
      turnpoint_radius_tolerance: eventForm.turnpoint_radius_tolerance,
      turnpoint_radius_minimum_absolute_tolerance_m: eventForm.turnpoint_radius_minimum_absolute_tolerance_m,
      number_of_decimals_task_results: eventForm.number_of_decimals_task_results,
      number_of_decimals_competition_results: eventForm.number_of_decimals_competition_results,
      visible_airspace_classes_json: eventForm.visible_airspace_classes_json,
      show_restricted_fields: eventForm.show_restricted_fields,
      penalties_json: penaltiesJson,
    };
    const savedEvent = await apiFetch<EventRecord>(eventEditorId ? `/api/events/${eventEditorId}` : "/api/events", token, { method: eventEditorId ? "PUT" : "POST", body: JSON.stringify(payload) });
    const loadedEvents = await refreshEvents(token);
    const nextEvent = loadedEvents.find((candidate) => candidate.id === savedEvent.id) ?? savedEvent;
    setEventEditorId(nextEvent.id);
    setEventForm(eventToForm(nextEvent));
    window.localStorage.setItem(LAST_EVENT_KEY, String(nextEvent.id));
    setMessage(`${eventEditorId ? "Updated" : "Created"} event ${savedEvent.name}.`);
    await loadEvent(token, nextEvent.id, nextEvent);
    if (!selectedTaskId) {
      setTaskDraft(taskDraftFromEvent(nextEvent));
    }
  }

  async function createEventDraft() {
    if (!token) return;
    const template = blankEventForm();
    const savedEvent = await apiFetch<EventRecord>("/api/events", token, {
      method: "POST",
      body: JSON.stringify({
        ...template,
        name: nextDraftEventName(events),
        penalties_json: {},
      }),
    });
    const loadedEvents = await refreshEvents(token);
    const nextEvent = loadedEvents.find((candidate) => candidate.id === savedEvent.id) ?? savedEvent;
    setEventTab("details");
    setEventEditorId(nextEvent.id);
    setEventForm(eventToForm(nextEvent));
    window.localStorage.setItem(LAST_EVENT_KEY, String(nextEvent.id));
    setMessage(`Created event ${nextEvent.name}.`);
    await loadEvent(token, nextEvent.id, nextEvent);
  }

  async function duplicateSelectedEvent() {
    if (!token || !eventEditorId) return;
    const duplicatedEvent = await apiFetch<EventRecord>(`/api/events/${eventEditorId}/duplicate`, token, {
      method: "POST",
    });
    const loadedEvents = await refreshEvents(token);
    const nextEvent = loadedEvents.find((candidate) => candidate.id === duplicatedEvent.id) ?? duplicatedEvent;
    setEventTab("details");
    setEventEditorId(nextEvent.id);
    setEventForm(eventToForm(nextEvent));
    window.localStorage.setItem(LAST_EVENT_KEY, String(nextEvent.id));
    setMessage(`Duplicated event ${selectedEvent?.name ?? duplicatedEvent.name} into ${duplicatedEvent.name}.`);
    await loadEvent(token, nextEvent.id, nextEvent);
  }

  async function deleteEvent() {
    if (!token || !eventEditorId) return;
    const eventToDelete = events.find((event) => event.id === eventEditorId);
    const confirmed = window.confirm(`Delete event "${eventToDelete?.name ?? "this event"}"? This will remove its tasks, turnpoints, uploads, and scoring records.`);
    if (!confirmed) return;
    await apiFetch<void>(`/api/events/${eventEditorId}`, token, { method: "DELETE" });
    const loadedEvents = await refreshEvents(token);
    if (loadedEvents[0]) {
      const nextEvent = loadedEvents[0];
      setMessage(`Deleted event ${eventToDelete?.name ?? ""}.`);
      setEventEditorId(nextEvent.id);
      setEventForm(eventToForm(nextEvent));
      window.localStorage.setItem(LAST_EVENT_KEY, String(nextEvent.id));
      await loadEvent(token, nextEvent.id, nextEvent);
    } else {
      setMessage(`Deleted event ${eventToDelete?.name ?? ""}.`);
      setSelectedEventId(null);
      setEventEditorId(null);
      window.localStorage.removeItem(LAST_EVENT_KEY);
      setEventForm(blankEventForm());
      setPilots([]);
      setTurnpoints([]);
      setTurnpointSources([]);
      setAirspaces([]);
      setAirspaceSources([]);
      setTasks([]);
      setResults([]);
      setPilotSummary([]);
      setUploads([]);
      setTrack(null);
      setTaskPointAdvanced(false);
      setTaskDraft(taskDraftFromEvent(null));
    }
  }

  async function createPilot(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedEventId) return;
    const payload = await apiFetch<PilotRecord>(`/api/events/${selectedEventId}/pilots`, token, { method: "POST", body: JSON.stringify(pilotForm) });
    setPilotForm({ first_name: "", last_name: "", email: "", nation: "", competition_number: "", civl_id: "" });
    setMessage(`Created pilot ${payload.first_name} ${payload.last_name}${payload.temp_password ? ` with temp password ${payload.temp_password}` : ""}.`);
    await loadEvent(token, selectedEventId);
    await refreshPilotDirectory(token);
    await refreshEvents(token);
  }

  async function assignExistingPilot() {
    if (!token || !selectedEventId || !selectedDirectoryPilotId) return;
    const payload = await apiFetch<PilotRecord>(`/api/events/${selectedEventId}/pilots/${selectedDirectoryPilotId}/assign`, token, { method: "POST" });
    setSelectedDirectoryPilotId(null);
    setMessage(`Added ${payload.first_name} ${payload.last_name} to ${selectedEvent?.name ?? "the event"}.`);
    await loadEvent(token, selectedEventId);
    await refreshPilotDirectory(token);
    await refreshEvents(token);
  }

  async function removePilot(pilot: PilotRecord) {
    if (!token || !selectedEventId) return;
    await apiFetch<void>(`/api/events/${selectedEventId}/pilots/${pilot.id}`, token, { method: "DELETE" });
    setMessage(`Removed ${pilot.first_name} ${pilot.last_name} from ${selectedEvent?.name ?? "the event"}.`);
    await loadEvent(token, selectedEventId);
    await refreshPilotDirectory(token);
    await refreshEvents(token);
  }

  async function uploadFile<T>(path: string, file: File): Promise<T> {
    if (!token) throw new Error("You must be signed in to upload files.");
    const formData = new FormData();
    formData.append("file", file);
    return apiFetch<T>(path, token, { method: "POST", body: formData });
  }

  async function toggleTurnpointSource(source: TurnpointSourceRecord, enabled: boolean) {
    if (!token || !selectedEventId) return;
    await apiFetch<TurnpointSourceRecord>(`/api/events/${selectedEventId}/turnpoint-sources/${source.id}`, token, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    });
    setMessage(`${enabled ? "Enabled" : "Hidden"} ${source.filename} on the event map.`);
    await loadEvent(token, selectedEventId, selectedEvent);
  }

  async function deleteTurnpointSource(source: TurnpointSourceRecord) {
    if (!token || !selectedEventId) return;
    const confirmed = window.confirm(`Delete ${source.filename}? This removes its imported waypoints from the database.`);
    if (!confirmed) return;
    await apiFetch<void>(`/api/events/${selectedEventId}/turnpoint-sources/${source.id}`, token, { method: "DELETE" });
    setMessage(`Deleted ${source.filename}.`);
    await loadEvent(token, selectedEventId, selectedEvent);
    await refreshEvents(token);
  }

  async function uploadAirspaceFile(kind: "airspace" | "restricted_field", file: File) {
    if (!selectedEventId) return;
    const response = await uploadFile<AirspaceUploadResponse>(`/api/events/${selectedEventId}/airspaces/upload?kind=${kind}`, file);
    setMessage(`Stored ${response.imported_count} ${kind === "airspace" ? "airspace regions" : "restricted fields"} from ${file.name}.`);
    await loadEvent(token, selectedEventId, selectedEvent);
    await refreshEvents(token);
  }

  async function deleteAirspaceSource(source: AirspaceSourceRecord) {
    if (!token || !selectedEventId) return;
    const confirmed = window.confirm(`Delete ${source.filename}? This removes its ${source.kind === "airspace" ? "airspace polygons" : "restricted fields"} from the database.`);
    if (!confirmed) return;
    await apiFetch<void>(`/api/events/${selectedEventId}/airspace-sources/${source.id}`, token, { method: "DELETE" });
    setMessage(`Deleted ${source.filename}.`);
    await loadEvent(token, selectedEventId, selectedEvent);
    await refreshEvents(token);
  }

  async function toggleAirspaceSource(source: AirspaceSourceRecord, enabled: boolean) {
    if (!token || !selectedEventId) return;
    await apiFetch<AirspaceSourceRecord>(`/api/events/${selectedEventId}/airspace-sources/${source.id}`, token, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    });
    setMessage(`${enabled ? "Enabled" : "Hidden"} ${source.filename} on the event map.`);
    await loadEvent(token, selectedEventId, selectedEvent);
  }

  function toggleVisibleAirspaceClass(category: AirspaceCategoryOption) {
    const existing = new Set(eventForm.visible_airspace_classes_json);
    if (existing.has(category)) {
      existing.delete(category);
    } else {
      existing.add(category);
    }
    setEventForm({ ...eventForm, visible_airspace_classes_json: Array.from(existing) });
  }

  function startNewTask() {
    const nextTaskNumber = tasks.length + 1;
    setSelectedTaskId(null);
    setTrack(null);
    setResults([]);
    setUploads([]);
    setTaskPointAdvanced(false);
    setScoringFeedback(null);
    setTaskFeedback(null);
    setRadiusDrafts({});
    setTaskDraft({
      ...taskDraftFromEvent(selectedEvent),
      name: `Task ${nextTaskNumber}`,
    });
    setMessage(`Started a new draft for ${selectedEvent?.name ?? "this event"}.`);
  }

  function addTurnpoint(turnpoint: MapTurnpoint) {
      setRadiusDrafts({});
      setTaskDraft((current) => {
        return {
          ...current,
          points: [
            ...current.points,
            {
              position: current.points.length + 1,
              point_type: current.points.length === 0 ? (taskPointAdvanced ? "launch" : "start") : "turnpoint",
              radius_m: current.points.length === 0 ? 300 : 400,
              turnpoint_id: turnpoint.id,
              name: turnpoint.name,
            latitude: turnpoint.latitude,
            longitude: turnpoint.longitude,
          },
        ],
      };
    });
  }

  function updatePoint(index: number, patch: Partial<TaskPointRecord>) {
    setTaskDraft((current) => ({ ...current, points: current.points.map((point, pointIndex) => (pointIndex === index ? { ...point, ...patch } : point)).map((point, pointIndex) => ({ ...point, position: pointIndex + 1 })) }));
  }

  function handleRadiusInputChange(index: number, point: TaskPointRecord, rawValue: string) {
    const key = taskPointInputKey(point, index);
    const sanitized = sanitizeMeterInput(rawValue);
    if (!sanitized) {
      setRadiusDrafts((current) => ({ ...current, [key]: "" }));
      return;
    }
    const nextRadius = Number(sanitized);
    updatePoint(index, { radius_m: nextRadius });
    setRadiusDrafts((current) => ({ ...current, [key]: formatMeters(nextRadius) }));
  }

  function handleRadiusInputBlur(index: number, point: TaskPointRecord) {
    const key = taskPointInputKey(point, index);
    const sanitized = sanitizeMeterInput(radiusDrafts[key] ?? "");
    if (!sanitized) {
      setRadiusDrafts((current) => {
        const next = { ...current };
        delete next[key];
        return next;
      });
      return;
    }
    const nextRadius = Number(sanitized);
    updatePoint(index, { radius_m: nextRadius });
    setRadiusDrafts((current) => ({ ...current, [key]: formatMeters(nextRadius) }));
  }

  function handleRadiusInputKeyDown(event: KeyboardEvent<HTMLInputElement>, index: number, point: TaskPointRecord) {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault();
    const key = taskPointInputKey(point, index);
    const draftValue = sanitizeMeterInput(radiusDrafts[key] ?? "");
    const baseRadius = draftValue ? Number(draftValue) : Math.max(0, Math.round(point.radius_m || 0));
    const nextRadius = Math.max(0, baseRadius + (event.key === "ArrowUp" ? 100 : -100));
    updatePoint(index, { radius_m: nextRadius });
    setRadiusDrafts((current) => ({ ...current, [key]: formatMeters(nextRadius) }));
  }

  function radiusInputValue(index: number, point: TaskPointRecord) {
    return radiusDrafts[taskPointInputKey(point, index)] ?? formatMeters(point.radius_m);
  }

  function removePoint(index: number) {
    setRadiusDrafts({});
    setTaskDraft((current) => ({ ...current, points: current.points.filter((_, pointIndex) => pointIndex !== index).map((point, pointIndex) => ({ ...point, position: pointIndex + 1 })) }));
  }

  function movePoint(fromIndex: number, toIndex: number) {
    if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0) {
      return;
    }
    setRadiusDrafts({});
    setTaskDraft((current) => {
      const points = [...current.points];
      const [movedPoint] = points.splice(fromIndex, 1);
      points.splice(toIndex, 0, movedPoint);
      return { ...current, points: points.map((point, pointIndex) => ({ ...point, position: pointIndex + 1 })) };
    });
  }

  async function saveTask() {
    if (!token || !selectedEventId) return;
    try {
      setTaskFeedback(null);
      const payload = {
        name: taskDraft.name,
        status: "draft",
        task_type: taskDraft.task_type,
        task_start_time: timeOrNull(taskDraft.task_start_time),
        task_finish_time: timeOrNull(taskDraft.task_finish_time),
        start_open_time: timeOrNull(taskDraft.start_open_time),
        start_close_time: timeOrNull(taskDraft.start_close_time),
        start_gate_count: taskDraft.start_gate_count,
        start_gate_interval_seconds: taskDraft.start_gate_interval_minutes === "" ? null : taskDraft.start_gate_interval_minutes * 60,
        nominal_distance_km: taskDraft.nominal_distance_km,
        nominal_time_hours: taskDraft.nominal_time_hours,
        nominal_launch: taskDraft.nominal_launch,
        minimum_distance_km: taskDraft.minimum_distance_km,
        penalties_json: JSON.parse(taskDraft.penalties_text || "{}"),
        points: taskDraft.points.map((point, index) => ({ ...point, position: index + 1 })),
      };
      let savedTask: TaskRecord;
      if (taskDraft.id) {
        savedTask = await apiFetch<TaskRecord>(`/api/tasks/${taskDraft.id}`, token, { method: "PUT", body: JSON.stringify(payload) });
        setTaskFeedback({ type: "success", text: `Updated task ${taskDraft.name}.` });
      } else {
        savedTask = await apiFetch<TaskRecord>(`/api/events/${selectedEventId}/tasks`, token, { method: "POST", body: JSON.stringify(payload) });
        setTaskFeedback({ type: "success", text: `Created task ${taskDraft.name}.` });
      }
      await loadEvent(token, selectedEventId, undefined, undefined, savedTask.id);
      await refreshEvents(token);
      setActiveSection("tasks");
    } catch (caught) {
      setTaskFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Task save failed." });
    }
  }

  async function publishTask() {
    if (!token || !taskDraft.id) return;
    try {
      setTaskFeedback(null);
      const publishedTask = await apiFetch<TaskRecord>(`/api/tasks/${taskDraft.id}/publish`, token, { method: "POST" });
      setTaskFeedback({ type: "success", text: `Published task ${taskDraft.name}.` });
      if (selectedEventId) await loadEvent(token, selectedEventId, undefined, undefined, publishedTask.id);
    } catch (caught) {
      setTaskFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Task publish failed." });
    }
  }

  async function unpublishTask() {
    if (!token || !taskDraft.id) return;
    try {
      setTaskFeedback(null);
      const unpublishedTask = await apiFetch<TaskRecord>(`/api/tasks/${taskDraft.id}/unpublish`, token, { method: "POST" });
      setTaskFeedback({ type: "success", text: `Unpublished task ${taskDraft.name}.` });
      if (selectedEventId) await loadEvent(token, selectedEventId, undefined, undefined, unpublishedTask.id);
    } catch (caught) {
      setTaskFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Task unpublish failed." });
    }
  }

  async function deleteTask() {
    if (!token || !taskDraft.id || !selectedEventId) return;
    const confirmed = window.confirm(`Delete task "${taskDraft.name}"? This will remove its uploaded tracks and score results for this task.`);
    if (!confirmed) return;
    try {
      setTaskFeedback(null);
      const remainingTasks = tasks.filter((task) => task.id !== taskDraft.id);
      const fallbackTaskId = remainingTasks[0]?.id ?? null;
      await apiFetch<void>(`/api/tasks/${taskDraft.id}`, token, { method: "DELETE" });
      setTaskFeedback({ type: "success", text: `Deleted task ${taskDraft.name}.` });
      await loadEvent(token, selectedEventId, undefined, undefined, fallbackTaskId);
      await refreshEvents(token);
      setActiveSection("tasks");
    } catch (caught) {
      setTaskFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Task delete failed." });
    }
  }

  async function uploadIgc(file: File, pilotId?: number | null) {
    if (!token || !selectedTaskId) return;
    setUploadFeedback({ type: "pending", text: `Uploading ${file.name}...` });
    const formData = new FormData();
    formData.append("file", file);
    if (pilotId) {
      formData.append("pilot_id", String(pilotId));
    }
    await apiFetch(`/api/tasks/${selectedTaskId}/uploads`, token, { method: "POST", body: formData });
    const pilotLabel = pilotId ? pilotNameById.get(pilotId) ?? `pilot ${pilotId}` : "pilot";
    setUploadFeedback({ type: "success", text: `Uploaded ${file.name} for ${pilotLabel}.` });
    await loadTask(token, selectedTaskId);
  }

  async function uploadIgcBatch(files: FileList | File[]) {
    if (!token || !selectedTaskId) return;
    try {
      setUploadFeedback({ type: "pending", text: `Uploading ${Array.from(files).length} IGC files...` });
      const formData = new FormData();
      Array.from(files).forEach((file) => formData.append("files", file));
      const batchResults = await apiFetch<BulkUploadItemRecord[]>(`/api/tasks/${selectedTaskId}/uploads/bulk`, token, {
        method: "POST",
        body: formData,
      });
      const matchedCount = batchResults.filter((item) => item.matched).length;
      const unmatched = batchResults.filter((item) => !item.matched);
      const unmatchedSummary = unmatched.length
        ? ` Unmatched: ${unmatched.map((item) => `${item.filename} (${item.message})`).join("; ")}`
        : "";
      setUploadFeedback({ type: "success", text: `Uploaded ${matchedCount} of ${batchResults.length} IGC files automatically.${unmatchedSummary}` });
      await loadTask(token, selectedTaskId);
      if (selectedEventId) {
        const loadedSummary = await apiFetch<PilotSummaryRecord[]>(`/api/events/${selectedEventId}/pilot-summary`, token);
        setPilotSummary(loadedSummary);
      }
    } catch (caught) {
      setUploadFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Bulk upload failed." });
    }
  }

  async function deleteUpload(upload: UploadRecord) {
    if (!token || !selectedTaskId) return;
    await apiFetch(`/api/uploads/${upload.id}`, token, { method: "DELETE" });
    setMessage(`Deleted ${upload.filename}.`);
    await loadTask(token, selectedTaskId);
    if (selectedEventId) {
      const loadedSummary = await apiFetch<PilotSummaryRecord[]>(`/api/events/${selectedEventId}/pilot-summary`, token);
      setPilotSummary(loadedSummary);
    }
    setTrack(null);
  }

  function downloadBlobFile(blob: Blob, filename: string) {
    const objectUrl = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 0);
  }

  async function downloadUploadFile(uploadId: number, filename: string) {
    if (!token) return;
    try {
      setResultsDownloadFeedback({ type: "pending", text: `Preparing ${filename}...`, uploadId, all: false });
      const { blob, filename: responseFilename } = await apiFetchBlob(`/api/uploads/${uploadId}/download`, token);
      downloadBlobFile(blob, responseFilename ?? filename);
      setResultsDownloadFeedback({ type: "success", text: `Download started for ${responseFilename ?? filename}.`, uploadId, all: false });
    } catch (caught) {
      setResultsDownloadFeedback({
        type: "error",
        text: caught instanceof Error ? caught.message : "Could not download the IGC file.",
        uploadId,
        all: false,
      });
    }
  }

  async function downloadAllIgcFiles() {
    if (!token || !selectedTaskId) return;
    try {
      const taskName = (selectedTask?.name ?? "task").replace(/[^a-z0-9._-]+/gi, "-");
      setResultsDownloadFeedback({ type: "pending", text: "Preparing all IGC files...", uploadId: null, all: true });
      const { blob, filename } = await apiFetchBlob(`/api/tasks/${selectedTaskId}/uploads/download-all`, token);
      downloadBlobFile(blob, filename ?? `${taskName}-igc-files.zip`);
      setResultsDownloadFeedback({ type: "success", text: "Started downloading all IGC files.", uploadId: null, all: true });
    } catch (caught) {
      setResultsDownloadFeedback({
        type: "error",
        text: caught instanceof Error ? caught.message : "Could not download all IGC files.",
        uploadId: null,
        all: true,
      });
    }
  }

  async function toggleResultTrack(uploadId: number, checked: boolean) {
    if (!token) return;
    if (!checked) {
      setSelectedResultUploadIds((current) => current.filter((id) => id !== uploadId));
      return;
    }
    if (!resultTracksByUploadId[uploadId]) {
      try {
        const collection = await apiFetch<TrackCollection>(`/api/uploads/${uploadId}/track`, token);
        setResultTracksByUploadId((current) => ({ ...current, [uploadId]: collection }));
      } catch (caught) {
        setScoringFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not load the selected pilot track." });
        return;
      }
    }
    setSelectedResultUploadIds((current) => (current.includes(uploadId) ? current : [...current, uploadId]));
  }

  function toggleTaskPointAdvanced(checked: boolean) {
    setTaskPointAdvanced(checked);
    if (!checked) {
      setTaskDraft((current) => ({
        ...current,
        points: current.points.map((point) => ({ ...point, point_type: toSimplePointType(point.point_type) })),
      }));
    }
  }

  async function rescoreSelectedTask() {
    if (!token) return;
    if (!selectedTaskId) {
      setScoringFeedback({ type: "error", text: "Select a task before running scoring." });
      return;
    }
    try {
      setScoringFeedback(null);
      await apiFetch(`/api/tasks/${selectedTaskId}/rescore`, token, { method: "POST" });
      await loadTask(token, selectedTaskId);
      if (selectedEventId) {
        const loadedSummary = await apiFetch<PilotSummaryRecord[]>(`/api/events/${selectedEventId}/pilot-summary`, token);
        setPilotSummary(loadedSummary);
      }
      setScoringFeedback({ type: "success", text: "Scoring completed for the selected task." });
    } catch (caught) {
      setScoringFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Scoring failed." });
    }
  }

  function renderParticipantCards() {
    if (!selectedEventId) {
      return (
        <SectionCard title="Participants" description="Create or select an event first.">
          <p className="hint">An event must be selected before participants can be managed.</p>
        </SectionCard>
      );
    }
    return (
      <div className="participant-workspace">
        <SectionCard title="Participant intake" description="Add a pilot manually or import a roster CSV for the selected event.">
          {canManagePlatform ? (
            <div className="participant-intake-stack">
              <div className="record-card stack compact participant-directory-card">
                <strong>Add existing person</strong>
                <span>Select from the global people directory, including pilots who created their own accounts.</span>
                <div className="participant-intake-row">
                  <select value={selectedDirectoryPilotId ?? ""} onChange={(event) => setSelectedDirectoryPilotId(event.target.value ? Number(event.target.value) : null)}>
                    <option value="">Select a person</option>
                    {availableDirectoryPilots.map((pilot) => (
                      <option key={pilot.id} value={pilot.id}>
                        {pilot.first_name} {pilot.last_name}{pilot.email ? ` - ${pilot.email}` : ""}{pilot.competition_number ? ` - #${pilot.competition_number}` : ""}
                      </option>
                    ))}
                  </select>
                  <button type="button" onClick={() => void assignExistingPilot()} disabled={!selectedDirectoryPilotId}>Add to event</button>
                </div>
              </div>
              <form className="stack form-block compact participant-intake-form" onSubmit={createPilot}>
                <div className="participant-intake-grid participant-intake-grid--two">
                  <input placeholder="First name" value={pilotForm.first_name} onChange={(event) => setPilotForm({ ...pilotForm, first_name: event.target.value })} />
                  <input placeholder="Last name" value={pilotForm.last_name} onChange={(event) => setPilotForm({ ...pilotForm, last_name: event.target.value })} />
                </div>
                <div className="participant-intake-grid participant-intake-grid--three">
                  <input placeholder="Email" value={pilotForm.email} onChange={(event) => setPilotForm({ ...pilotForm, email: event.target.value })} />
                  <input placeholder="Nation" value={pilotForm.nation} onChange={(event) => setPilotForm({ ...pilotForm, nation: event.target.value })} />
                  <input placeholder="Competition #" value={pilotForm.competition_number} onChange={(event) => setPilotForm({ ...pilotForm, competition_number: event.target.value })} />
                  <input placeholder="CIVL ID" value={pilotForm.civl_id} onChange={(event) => setPilotForm({ ...pilotForm, civl_id: event.target.value })} />
                </div>
                <div className="button-row participant-intake-actions">
                  <button type="submit">Create new pilot</button>
                  <label className="file-input">
                    Import CSV
                    <input
                      type="file"
                      accept=".csv"
                      onChange={async (event) => {
                        const file = event.target.files?.[0];
                        if (!file) return;
                        await uploadFile<unknown>(`/api/events/${selectedEventId}/pilots/import-csv`, file);
                        setMessage(`Imported pilots from ${file.name}.`);
                        await loadEvent(token, selectedEventId);
                        await refreshPilotDirectory(token);
                        await refreshEvents(token);
                        event.currentTarget.value = "";
                      }}
                    />
                  </label>
                </div>
              </form>
            </div>
          ) : (
            <p className="hint">Pilot management is available to organizers and admins. Pilots can still review the roster below.</p>
          )}
        </SectionCard>
        <SectionCard title="Current participants" description={`${pilots.length} pilots assigned to ${selectedEvent?.name ?? "this event"}.`}>
          <div className="participant-table-wrap">
            <table className="participant-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Competition #</th>
                  <th>Email</th>
                  <th>Portal</th>
                  {canManagePlatform ? <th className="participant-table-actions">Actions</th> : null}
                </tr>
              </thead>
              <tbody>
                {pilots.length ? (
                  pilots.map((pilot) => (
                    <tr key={pilot.id}>
                      <td>
                        <strong>{pilot.first_name} {pilot.last_name}</strong>
                      </td>
                      <td>{pilot.competition_number ?? "No comp #"}</td>
                      <td>{pilot.email ?? "No email"}</td>
                      <td>{pilot.portal_username ?? "No portal user"}</td>
                      {canManagePlatform ? (
                        <td className="participant-table-actions">
                          <button type="button" className="ghost-button danger-button" onClick={() => removePilot(pilot)}>Remove</button>
                        </td>
                      ) : null}
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={canManagePlatform ? 5 : 4} className="participant-table-empty">No participants assigned to this event yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </SectionCard>
      </div>
    );
  }

  function renderEventsSection() {
    return (
      <div className="section-stack">
        <SectionCard title="Event selection" description="Choose an event from the database or start a new one. Everything below follows the currently selected event.">
          <div className="event-selector-bar">
            <label className="stack compact event-selector-field">
              <span>Current event</span>
              <select value={selectedEventId ?? (events[0]?.id ?? "")} onChange={(event) => { const nextId = Number(event.target.value); const nextEvent = events.find((candidate) => candidate.id === nextId); if (nextEvent) void selectEvent(nextEvent); }}>
                {events.length === 0 ? <option value="">No events yet</option> : null}
                {events.map((event) => (
                  <option key={event.id} value={event.id}>
                    {event.location ? `${event.name} - ${event.location}` : event.name}
                  </option>
                ))}
              </select>
            </label>
            {canManagePlatform ? (
              <button className="event-selector-link" type="button" onClick={() => void createEventDraft()}>Create a New Event</button>
            ) : null}
          </div>
          <div className="event-summary-strip">
            <div className="record-card compact-stat">
              <strong>{selectedEvent?.pilot_count ?? 0}</strong>
              <span>Pilots</span>
            </div>
            <div className="record-card compact-stat">
              <strong>{selectedEvent?.task_count ?? 0}</strong>
              <span>Tasks</span>
            </div>
            <div className="record-card compact-stat">
              <strong>{turnpoints.length}</strong>
              <span>Turnpoints</span>
            </div>
            <div className="record-card compact-stat">
              <strong>{selectedEvent ? `${selectedEvent.starts_on} to ${selectedEvent.ends_on}` : "--"}</strong>
              <span>Dates</span>
            </div>
          </div>
        </SectionCard>
        <div className="tab-row">
          {eventTabItems.map((tab) => (
            <button key={tab.id} type="button" className={eventTab === tab.id ? "tab-button active" : "tab-button"} onClick={() => setEventTab(tab.id)}>
              {tab.label}
            </button>
          ))}
        </div>
        <div className="event-workspace-grid event-three-up">
          {eventTab === "details" ? (
          <SectionCard title={eventEditorId ? "Event details" : "Create event"} description="Keep the active event compact and quick to edit.">
            <form className="stack form-block compact-event-form" onSubmit={saveEvent}>
              <label className="stack compact">
                <span>Event name</span>
                <input placeholder="Enter event name" value={eventForm.name} onChange={(event) => setEventForm({ ...eventForm, name: event.target.value })} />
              </label>
              <label className="stack compact">
                <span>Location</span>
                <input placeholder="Enter location" value={eventForm.location} onChange={(event) => setEventForm({ ...eventForm, location: event.target.value })} />
              </label>
              <div className="inline-grid">
                <label className="stack compact">
                  <span>Starts on</span>
                  <input type="date" value={eventForm.starts_on} onChange={(event) => setEventForm({ ...eventForm, starts_on: event.target.value })} />
                </label>
                <label className="stack compact">
                  <span>Ends on</span>
                  <input type="date" value={eventForm.ends_on} onChange={(event) => setEventForm({ ...eventForm, ends_on: event.target.value })} />
                </label>
              </div>
              <label className="stack compact">
                <span>Timezone</span>
                <input placeholder="Enter timezone" value={eventForm.timezone} onChange={(event) => setEventForm({ ...eventForm, timezone: event.target.value })} />
              </label>
              {canManagePlatform ? (
                <div className="button-row">
                  <button type="submit">{eventEditorId ? "Save event" : "Create event"}</button>
                  {eventEditorId ? <button type="button" className="ghost-button" onClick={() => void duplicateSelectedEvent()}>Duplicate event</button> : null}
                  {isAdmin && eventEditorId ? <button type="button" className="ghost-button danger-button" onClick={() => void deleteEvent()}>Delete event</button> : null}
                </div>
              ) : null}
            </form>
          </SectionCard>
          ) : null}
          {eventTab === "scoring" ? (
          <SectionCard title="Scoring parameters" description="Event-level GAP defaults.">
            {eventEditorId ? (
              <form className="stack form-block compact-scoring-form" onSubmit={saveEvent}>
                <label className="stack compact">
                  <span>Scoring formula</span>
                  <select value={eventForm.scoring_formula} onChange={(event) => setEventForm({ ...eventForm, scoring_formula: event.target.value })}>
                    {scoringFormulaOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                </label>
                <div className="inline-grid">
                  <label className="stack compact">
                    <span>Nominal distance (km)</span>
                    <input type="number" value={eventForm.nominal_distance_km} onChange={(event) => setEventForm({ ...eventForm, nominal_distance_km: Number(event.target.value) })} />
                  </label>
                  <label className="stack compact">
                    <span>Nominal time (hours)</span>
                    <input type="number" step="0.1" value={eventForm.nominal_time_hours} onChange={(event) => setEventForm({ ...eventForm, nominal_time_hours: Number(event.target.value) })} />
                  </label>
                </div>
                <div className="inline-grid">
                  <label className="stack compact">
                    <span>Nominal launch</span>
                    <input type="number" step="0.01" value={eventForm.nominal_launch} onChange={(event) => setEventForm({ ...eventForm, nominal_launch: Number(event.target.value) })} />
                  </label>
                  <label className="stack compact">
                    <span>Minimum distance (km)</span>
                    <input type="number" value={eventForm.minimum_distance_km} onChange={(event) => setEventForm({ ...eventForm, minimum_distance_km: Number(event.target.value) })} />
                  </label>
                </div>
                <div className="inline-grid">
                  <label className="stack compact">
                    <span>Nominal goal (%)</span>
                    <input type="number" step="0.01" value={eventForm.nominal_goal_percent} onChange={(event) => setEventForm({ ...eventForm, nominal_goal_percent: Number(event.target.value) })} />
                  </label>
                  <label className="stack compact">
                    <span>Score-back time (minutes)</span>
                    <input type="number" value={eventForm.score_back_time_minutes} onChange={(event) => setEventForm({ ...eventForm, score_back_time_minutes: Number(event.target.value) })} />
                  </label>
                </div>
                <div className="inline-grid">
                  <label className="stack compact">
                    <span>Goal / SS penalty</span>
                    <input type="number" step="0.1" value={eventForm.goal_ss_penalty} onChange={(event) => setEventForm({ ...eventForm, goal_ss_penalty: Number(event.target.value) })} />
                  </label>
                  <label className="stack compact">
                    <span>Stopped-task glide bonus</span>
                    <input type="number" step="0.1" value={eventForm.stopped_glide_bonus} onChange={(event) => setEventForm({ ...eventForm, stopped_glide_bonus: Number(event.target.value) })} />
                  </label>
                </div>
                <div className="inline-grid">
                  <label className="stack compact">
                    <span>Jump-the-gun factor</span>
                    <input type="number" step="0.1" value={eventForm.jump_the_gun_factor} onChange={(event) => setEventForm({ ...eventForm, jump_the_gun_factor: Number(event.target.value) })} />
                  </label>
                  <label className="stack compact">
                    <span>Jump-the-gun max (seconds)</span>
                    <input type="number" value={eventForm.jump_the_gun_max_seconds} onChange={(event) => setEventForm({ ...eventForm, jump_the_gun_max_seconds: Number(event.target.value) })} />
                  </label>
                </div>
                <div className="three-up compact-checkbox-grid">
                  <label className="record-card checkbox-card">
                    <input type="checkbox" checked={eventForm.use_distance_points} onChange={(event) => setEventForm({ ...eventForm, use_distance_points: event.target.checked })} />
                    <span>Distance points</span>
                  </label>
                  <label className="record-card checkbox-card">
                    <input type="checkbox" checked={eventForm.use_time_points} onChange={(event) => setEventForm({ ...eventForm, use_time_points: event.target.checked })} />
                    <span>Time points</span>
                  </label>
                  <label className="record-card checkbox-card">
                    <input type="checkbox" checked={eventForm.use_leading_points} onChange={(event) => setEventForm({ ...eventForm, use_leading_points: event.target.checked })} />
                    <span>Leading points</span>
                  </label>
                  <label className="record-card checkbox-card">
                    <input type="checkbox" checked={eventForm.use_arrival_position_points} onChange={(event) => setEventForm({ ...eventForm, use_arrival_position_points: event.target.checked })} />
                    <span>Arrival position points</span>
                  </label>
                  <label className="record-card checkbox-card">
                    <input type="checkbox" checked={eventForm.use_arrival_time_points} onChange={(event) => setEventForm({ ...eventForm, use_arrival_time_points: event.target.checked })} />
                    <span>Arrival time points</span>
                  </label>
                  <label className="record-card checkbox-card">
                    <input type="checkbox" checked={eventForm.use_departure_points} onChange={(event) => setEventForm({ ...eventForm, use_departure_points: event.target.checked })} />
                    <span>Departure points</span>
                  </label>
                </div>
                <p className="hint">The FS scoring sheet also shows computed outputs like day validity and available points. Only the editable AirScore formula settings are exposed here.</p>
                  <div className="inline-grid">
                    <label className="stack compact">
                      <span>Day quality override</span>
                      <input type="number" step="0.01" value={eventForm.day_quality_override} onChange={(event) => setEventForm({ ...eventForm, day_quality_override: Number(event.target.value) })} />
                    </label>
                    <label className="stack compact">
                      <span>Time points if not in goal</span>
                      <input type="number" step="0.01" value={eventForm.time_points_if_not_in_goal} onChange={(event) => setEventForm({ ...eventForm, time_points_if_not_in_goal: Number(event.target.value) })} />
                    </label>
                  </div>
                  <div className="inline-grid">
                    <label className="stack compact">
                      <span>Min time span for valid task (minutes)</span>
                      <input type="number" value={eventForm.min_time_span_for_valid_task_minutes} onChange={(event) => setEventForm({ ...eventForm, min_time_span_for_valid_task_minutes: Number(event.target.value) })} />
                    </label>
                    <label className="stack compact">
                      <span>Leading weight factor</span>
                      <input type="number" step="0.01" value={eventForm.leading_weight_factor} onChange={(event) => setEventForm({ ...eventForm, leading_weight_factor: Number(event.target.value) })} />
                    </label>
                  </div>
                  <div className="inline-grid">
                    <label className="stack compact">
                      <span>Turnpoint radius tolerance</span>
                      <input type="number" step="0.0001" value={eventForm.turnpoint_radius_tolerance} onChange={(event) => setEventForm({ ...eventForm, turnpoint_radius_tolerance: Number(event.target.value) })} />
                    </label>
                    <label className="stack compact">
                      <span>Turnpoint min absolute tolerance (m)</span>
                      <input type="number" step="0.1" value={eventForm.turnpoint_radius_minimum_absolute_tolerance_m} onChange={(event) => setEventForm({ ...eventForm, turnpoint_radius_minimum_absolute_tolerance_m: Number(event.target.value) })} />
                    </label>
                  </div>
                  <div className="inline-grid">
                    <label className="stack compact">
                      <span>Task results decimals</span>
                      <input type="number" min={0} max={6} value={eventForm.number_of_decimals_task_results} onChange={(event) => setEventForm({ ...eventForm, number_of_decimals_task_results: Number(event.target.value) })} />
                    </label>
                    <label className="stack compact">
                      <span>Competition results decimals</span>
                      <input type="number" min={0} max={6} value={eventForm.number_of_decimals_competition_results} onChange={(event) => setEventForm({ ...eventForm, number_of_decimals_competition_results: Number(event.target.value) })} />
                    </label>
                  </div>
                  <div className="inline-grid">
                    <label className="stack compact">
                      <span>Scoring altitude</span>
                      <select value={eventForm.scoring_altitude} onChange={(event) => setEventForm({ ...eventForm, scoring_altitude: event.target.value })}>
                        {scoringAltitudeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                      </select>
                    </label>
                    <label className="stack compact">
                      <span>Final glide decelerator</span>
                      <select value={eventForm.final_glide_decelerator} onChange={(event) => setEventForm({ ...eventForm, final_glide_decelerator: event.target.value })}>
                        {finalGlideDeceleratorOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                      </select>
                    </label>
                  </div>
                  <label className="stack compact">
                    <span>No final glide decelerator reason</span>
                    <input type="text" value={eventForm.no_final_glide_decelerator_reason} onChange={(event) => setEventForm({ ...eventForm, no_final_glide_decelerator_reason: event.target.value })} placeholder="Optional override note" />
                  </label>
                  <div className="three-up compact-checkbox-grid">
                    <label className="record-card checkbox-card">
                      <input type="checkbox" checked={eventForm.use_1000_points_for_max_day_quality} onChange={(event) => setEventForm({ ...eventForm, use_1000_points_for_max_day_quality: event.target.checked })} />
                      <span>Use 1000 points for max day quality</span>
                    </label>
                    <label className="record-card checkbox-card">
                      <input type="checkbox" checked={eventForm.normalize_1000_before_day_quality} onChange={(event) => setEventForm({ ...eventForm, normalize_1000_before_day_quality: event.target.checked })} />
                      <span>Normalize 1000 before day quality</span>
                    </label>
                    <label className="record-card checkbox-card">
                      <input type="checkbox" checked={eventForm.use_difficulty_for_distance_points} onChange={(event) => setEventForm({ ...eventForm, use_difficulty_for_distance_points: event.target.checked })} />
                      <span>Use difficulty for distance points</span>
                    </label>
                    <label className="record-card checkbox-card">
                      <input type="checkbox" checked={eventForm.use_distance_squared_for_lc} onChange={(event) => setEventForm({ ...eventForm, use_distance_squared_for_lc: event.target.checked })} />
                      <span>Use distance squared for LC</span>
                    </label>
                    <label className="record-card checkbox-card">
                      <input type="checkbox" checked={eventForm.use_semi_circle_control_zone_for_goal_line} onChange={(event) => setEventForm({ ...eventForm, use_semi_circle_control_zone_for_goal_line: event.target.checked })} />
                      <span>Use semi-circle goal line control zone</span>
                    </label>
                    <label className="record-card checkbox-card">
                      <input type="checkbox" checked={eventForm.use_proportional_leading_weight_if_nobody_in_goal} onChange={(event) => setEventForm({ ...eventForm, use_proportional_leading_weight_if_nobody_in_goal: event.target.checked })} />
                      <span>Proportional leading weight if nobody in goal</span>
                    </label>
                    <label className="record-card checkbox-card">
                      <input type="checkbox" checked={eventForm.redistribute_removed_time_points_as_distance_points} onChange={(event) => setEventForm({ ...eventForm, redistribute_removed_time_points_as_distance_points: event.target.checked })} />
                      <span>Redistribute removed time points as distance points</span>
                    </label>
                    <label className="record-card checkbox-card">
                      <input type="checkbox" checked={eventForm.use_best_score_for_ftv_validity} onChange={(event) => setEventForm({ ...eventForm, use_best_score_for_ftv_validity: event.target.checked })} />
                      <span>Use best score for FTV validity</span>
                    </label>
                    <label className="record-card checkbox-card">
                      <input type="checkbox" checked={eventForm.use_constant_leading_weight} onChange={(event) => setEventForm({ ...eventForm, use_constant_leading_weight: event.target.checked })} />
                      <span>Use constant leading weight</span>
                    </label>
                    <label className="record-card checkbox-card">
                      <input type="checkbox" checked={eventForm.use_pwca2019_for_lc} onChange={(event) => setEventForm({ ...eventForm, use_pwca2019_for_lc: event.target.checked })} />
                      <span>Use PWCA 2019 for LC</span>
                    </label>
                    <label className="record-card checkbox-card">
                      <input type="checkbox" checked={eventForm.use_flat_decline_of_timepoints} onChange={(event) => setEventForm({ ...eventForm, use_flat_decline_of_timepoints: event.target.checked })} />
                      <span>Use flat decline of time points</span>
                    </label>
                  </div>
                <label className="stack compact">
                  <span>Penalty rules JSON</span>
                  <textarea value={eventForm.penalties_text} onChange={(event) => setEventForm({ ...eventForm, penalties_text: event.target.value })} rows={3} placeholder='{"jump_the_gun": 0, "airspace": 0}' />
                </label>
                {canManagePlatform ? <button type="submit">Save scoring parameters</button> : null}
              </form>
            ) : (
              <p className="hint">Create or select an event to define its scoring defaults.</p>
            )}
          </SectionCard>
          ) : null}
          {eventTab === "turnpoints" ? (
          <SectionCard title="Turnpoint files" description="Upload as many waypoint files as you need for the event, then control which ones are visible on the map.">
            {eventEditorId ? (
              <div className="stack form-block">
                {canManagePlatform ? (
                  <div className="participant-intake-row">
                    <div className="stack compact">
                      <span>Upload turnpoint file</span>
                      <p className="hint">CSV, GeoJSON, or GPX. Each upload is stored separately so you can mix multiple waypoint datasets on the same event.</p>
                    </div>
                    <label className="file-input">
                      Upload turnpoints
                      <input
                        type="file"
                        accept=".csv,.geojson,.json,.gpx"
                        onChange={async (event) => {
                          const file = event.target.files?.[0];
                          if (!file || !selectedEventId) return;
                          try {
                            setError("");
                            const response = await uploadFile<TurnpointUploadResponse>(`/api/events/${selectedEventId}/turnpoints/upload`, file);
                            setMessage(`Stored ${response.imported_count} turnpoints from ${file.name}.`);
                            await loadEvent(token, selectedEventId);
                            await refreshEvents(token);
                          } catch (caught) {
                            setError(caught instanceof Error ? caught.message : `Failed to import ${file.name}.`);
                          } finally {
                            event.currentTarget.value = "";
                          }
                        }}
                      />
                    </label>
                  </div>
                ) : null}
                <div className="participant-table-wrap">
                  <table className="participant-table">
                    <thead>
                      <tr>
                        <th>File name</th>
                        <th>Format</th>
                        <th>Turnpoints</th>
                        <th>Visible</th>
                        <th>Uploaded</th>
                        {canManagePlatform ? <th className="participant-table-actions">Actions</th> : null}
                      </tr>
                    </thead>
                    <tbody>
                      {turnpointSources.length ? (
                        turnpointSources.map((source) => (
                          <tr key={source.id}>
                            <td><strong>{source.filename}</strong></td>
                            <td>{source.file_format.toUpperCase()}</td>
                            <td>{source.turnpoint_count}</td>
                            <td>
                              <label className="task-advanced-toggle">
                                <input
                                  type="checkbox"
                                  checked={source.enabled}
                                  disabled={!canManagePlatform}
                                  onChange={(event) => void toggleTurnpointSource(source, event.target.checked)}
                                />
                                <span>{source.enabled ? "Visible" : "Hidden"}</span>
                              </label>
                            </td>
                            <td>{new Date(source.uploaded_at).toLocaleString()}</td>
                            {canManagePlatform ? (
                              <td className="participant-table-actions">
                                <button type="button" className="ghost-button danger-button" onClick={() => void deleteTurnpointSource(source)}>Delete</button>
                              </td>
                            ) : null}
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan={canManagePlatform ? 6 : 5} className="participant-table-empty">No turnpoint files uploaded for this event yet.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <p className="hint">Create or select an event before uploading turnpoint files.</p>
            )}
          </SectionCard>
          ) : null}
        </div>
        {eventTab === "airspace" ? (
          <div className="section-grid two-column">
            <SectionCard title="Overlay settings" description="Choose which airspace classes should appear on the task map for this event.">
              {eventEditorId ? (
                <form className="stack form-block" onSubmit={saveEvent}>
                  <div className="three-up compact-checkbox-grid">
                    {airspaceCategoryOptions.map((option) => (
                      <label key={option.value} className="record-card checkbox-card">
                        <input
                          type="checkbox"
                          checked={eventForm.visible_airspace_classes_json.includes(option.value)}
                          onChange={() => toggleVisibleAirspaceClass(option.value)}
                        />
                        <span>{option.label}</span>
                      </label>
                    ))}
                    <label className="record-card checkbox-card">
                      <input
                        type="checkbox"
                        checked={eventForm.show_restricted_fields}
                        onChange={(event) => setEventForm({ ...eventForm, show_restricted_fields: event.target.checked })}
                      />
                      <span>Restricted fields</span>
                    </label>
                  </div>
                  <div className="record-card">
                    <strong>{visibleAirspaces.length} visible overlays</strong>
                    <span>{selectedEvent?.airspace_count ?? 0} airspace regions and {selectedEvent?.restricted_field_count ?? 0} restricted fields stored for this event.</span>
                  </div>
                  {canManagePlatform ? <button type="submit">Save overlay settings</button> : null}
                </form>
              ) : (
                <p className="hint">Create or select an event to configure airspace overlays.</p>
              )}
            </SectionCard>
            <SectionCard title="Upload datasets" description="Use OpenAir for airspace and restricted field polygons. GeoJSON is also accepted for general airspace overlays.">
              <div className="stack form-block">
                {canManagePlatform ? (
                  <>
                    <div className="record-card">
                      <strong>Competition airspace</strong>
                      <span>Upload OpenAir or GeoJSON around the selected event.</span>
                      <label className="file-input">
                        Upload airspace
                        <input
                          type="file"
                          accept=".txt,.openair,.air,.geojson,.json"
                          onChange={async (event) => {
                            const file = event.target.files?.[0];
                            if (!file) return;
                            try {
                              setError("");
                              await uploadAirspaceFile("airspace", file);
                            } catch (caught) {
                              setError(caught instanceof Error ? caught.message : `Failed to import ${file.name}.`);
                            } finally {
                              event.currentTarget.value = "";
                            }
                          }}
                        />
                      </label>
                    </div>
                    <div className="record-card">
                      <strong>Restricted landing fields</strong>
                      <span>Upload OpenAir polygons for do-not-land or field exclusion zones.</span>
                      <label className="file-input">
                        Upload restricted fields
                        <input
                          type="file"
                          accept=".txt,.openair,.air"
                          onChange={async (event) => {
                            const file = event.target.files?.[0];
                            if (!file) return;
                            try {
                              setError("");
                              await uploadAirspaceFile("restricted_field", file);
                            } catch (caught) {
                              setError(caught instanceof Error ? caught.message : `Failed to import ${file.name}.`);
                            } finally {
                              event.currentTarget.value = "";
                            }
                          }}
                        />
                      </label>
                    </div>
                  </>
                ) : (
                  <p className="hint">Only organizers and admins can upload airspace files. Pilots still see the saved overlays on the task map.</p>
                )}
              </div>
            </SectionCard>
            <SectionCard title="Stored airspace files" description="Uploaded overlays attached to this event.">
              <div className="stack form-block">
                {airspaceSources.filter((source) => source.kind === "airspace").length ? (
                  airspaceSources.filter((source) => source.kind === "airspace").map((source) => (
                    <div key={source.id} className="record-card roster-row">
                      <div>
                        <strong>{source.filename}</strong>
                        <span>{source.region_count} regions - {source.file_format} - uploaded {new Date(source.uploaded_at).toLocaleString()}</span>
                      </div>
                      <div className="compact-slot-actions">
                        <label className="task-advanced-toggle">
                          <input
                            type="checkbox"
                            checked={source.enabled ?? true}
                            disabled={!canManagePlatform}
                            onChange={(event) => void toggleAirspaceSource(source, event.target.checked)}
                          />
                          <span>{source.enabled ?? true ? "Visible" : "Hidden"}</span>
                        </label>
                        {canManagePlatform ? <button type="button" className="ghost-button danger-button" onClick={() => void deleteAirspaceSource(source)}>Delete</button> : null}
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="hint">No airspace overlays uploaded yet.</p>
                )}
              </div>
            </SectionCard>
            <SectionCard title="Stored restricted fields" description="Do-not-land and restricted field polygons for this event.">
              <div className="stack form-block">
                {airspaceSources.filter((source) => source.kind === "restricted_field").length ? (
                  airspaceSources.filter((source) => source.kind === "restricted_field").map((source) => (
                    <div key={source.id} className="record-card roster-row">
                      <div>
                        <strong>{source.filename}</strong>
                        <span>{source.region_count} fields - {source.file_format} - uploaded {new Date(source.uploaded_at).toLocaleString()}</span>
                      </div>
                      <div className="compact-slot-actions">
                        <label className="task-advanced-toggle">
                          <input
                            type="checkbox"
                            checked={source.enabled ?? true}
                            disabled={!canManagePlatform}
                            onChange={(event) => void toggleAirspaceSource(source, event.target.checked)}
                          />
                          <span>{source.enabled ?? true ? "Visible" : "Hidden"}</span>
                        </label>
                        {canManagePlatform ? <button type="button" className="ghost-button danger-button" onClick={() => void deleteAirspaceSource(source)}>Delete</button> : null}
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="hint">No restricted field files uploaded yet.</p>
                )}
              </div>
            </SectionCard>
          </div>
        ) : null}
        {eventTab === "participants" ? renderParticipantCards() : null}
      </div>
    );
  }

  function renderTasksSection() {
      if (!selectedEventId) return <SectionCard title="Tasks" description="Create or select an event first."><p className="hint">Tasks need an event context before they can be built.</p></SectionCard>;
      const fullscreenTaskEditor = canManagePlatform ? (
        <div className="map-task-editor">
          <div className="map-task-editor-header">
            <strong>Task turnpoints</strong>
            <span>{taskDraft.points.length ? `${taskDraft.points.length} in task` : "No turnpoints yet"}</span>
          </div>
          <div className="map-task-editor-table-wrap">
            <table className="map-task-editor-table">
              <thead>
                <tr>
                  <th></th>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Radius (m)</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {taskDraft.points.length ? (
                  taskDraft.points.map((point, index) => (
                    <tr
                      key={`fullscreen-${point.turnpoint_id ?? point.name}-${index}`}
                      draggable
                      onDragStart={(event) => event.dataTransfer.setData("text/plain", String(index))}
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={(event) => {
                        event.preventDefault();
                        movePoint(Number(event.dataTransfer.getData("text/plain")), index);
                      }}
                    >
                      <td className="map-task-editor-drag">{point.position}. ⋮⋮</td>
                      <td className="map-task-editor-name">
                        <strong>{point.name}</strong>
                      </td>
                      <td className="map-task-editor-type">
                        <select value={taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type)} onChange={(event) => updatePoint(index, { point_type: event.target.value })}>
                          {taskPointTypeOptions.map((option) => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                          ))}
                        </select>
                      </td>
                      <td className="map-task-editor-radius">
                        <input
                          value={radiusInputValue(index, point)}
                          onChange={(event) => handleRadiusInputChange(index, point, event.target.value)}
                          onFocus={(event) => event.currentTarget.select()}
                          onBlur={() => handleRadiusInputBlur(index, point)}
                          onKeyDown={(event) => handleRadiusInputKeyDown(event, index, point)}
                          inputMode="numeric"
                        />
                      </td>
                      <td className="map-task-editor-actions">
                        <button type="button" className="ghost-button danger-button" onClick={() => removePoint(index)}>Remove</button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="map-task-editor-empty">Click turnpoints on the map or add them from search.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : undefined;
      return (
        <div className="section-stack">
        <SectionCard title="Task details" description={canManagePlatform ? "Choose a task, review its scoring fields, and manage the ordered task turnpoints." : "Review the selected task, turnpoints, and route geometry."}>
          <div className="stack form-block">
            <div className="participant-intake-row">
              <label className="stack compact">
                <span>Selected task</span>
                <select value={selectedTaskId ?? ""} onChange={(event) => { const nextId = Number(event.target.value); const nextTask = tasks.find((task) => task.id === nextId); if (nextTask) void loadTask(token, nextId, nextTask); }}>
                  <option value="">Select a task</option>
                  {tasks.map((task) => <option key={task.id} value={task.id}>{task.name} - {task.status}</option>)}
                </select>
              </label>
              {canManagePlatform ? (
                <button type="button" className="ghost-button" onClick={startNewTask}>
                  New task
                </button>
              ) : null}
            </div>
            <label className="stack compact">
              <span>Task name</span>
              <input value={taskDraft.name} onChange={(event) => setTaskDraft({ ...taskDraft, name: event.target.value })} placeholder="Task name" disabled={!canManagePlatform} />
            </label>
            <div className="inline-grid">
              <label className={canManagePlatform ? "stack compact" : "stack compact field-disabled"}>
                <span>Task type</span>
                <select value={taskDraft.task_type} onChange={(event) => setTaskDraft({ ...taskDraft, task_type: event.target.value })} disabled={!canManagePlatform}>
                  {taskTypeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
              <label className={canManagePlatform ? "stack compact" : "stack compact field-disabled"}>
                <span>Task start (launch open)</span>
                <input type="time" step={60} value={taskDraft.task_start_time} onChange={(event) => setTaskDraft({ ...taskDraft, task_start_time: event.target.value })} disabled={!canManagePlatform} />
              </label>
            </div>
            <div className="inline-grid">
              <label className={canManagePlatform ? "stack compact" : "stack compact field-disabled"}>
                <span>Task finish (goal close)</span>
                <input type="time" step={60} value={taskDraft.task_finish_time} onChange={(event) => setTaskDraft({ ...taskDraft, task_finish_time: event.target.value })} disabled={!canManagePlatform} />
              </label>
              <label className={currentTaskTypeBehavior.usesStartWindow ? "stack compact" : "stack compact field-disabled"}>
                <span>Start open</span>
                <input type="time" step={60} value={taskDraft.start_open_time} onChange={(event) => setTaskDraft({ ...taskDraft, start_open_time: event.target.value })} disabled={!currentTaskTypeBehavior.usesStartWindow} />
              </label>
            </div>
            <div className="inline-grid">
              <label className={currentTaskTypeBehavior.usesStartWindow ? "stack compact" : "stack compact field-disabled"}>
                <span>Start close</span>
                <input type="time" step={60} value={taskDraft.start_close_time} onChange={(event) => setTaskDraft({ ...taskDraft, start_close_time: event.target.value })} disabled={!currentTaskTypeBehavior.usesStartWindow} />
              </label>
              <label className={currentTaskTypeBehavior.usesMultipleGates ? "stack compact" : "stack compact field-disabled"}>
                <span>Number of start gates</span>
                <input type="number" min={1} value={taskDraft.start_gate_count} onChange={(event) => setTaskDraft({ ...taskDraft, start_gate_count: Math.max(1, Number(event.target.value) || 1) })} disabled={!currentTaskTypeBehavior.usesMultipleGates} />
              </label>
            </div>
            <div className="inline-grid">
              <label className={currentTaskTypeBehavior.usesMultipleGates ? "stack compact" : "stack compact field-disabled"}>
                <span>Gate interval (minutes)</span>
                <input type="number" min={0} value={taskDraft.start_gate_interval_minutes} onChange={(event) => setTaskDraft({ ...taskDraft, start_gate_interval_minutes: event.target.value === "" ? "" : Math.max(0, Number(event.target.value) || 0) })} placeholder="15" disabled={!currentTaskTypeBehavior.usesMultipleGates} />
              </label>
              <div className="distance-summary-grid">
                <div className="record-card">
                  <strong>Total task distance</strong>
                  <span>{taskDistanceMetrics.totalDistanceKm.toFixed(1)} km center-to-center</span>
                </div>
                <div className="record-card">
                  <strong>Optimized distance</strong>
                  <span>{taskDistanceMetrics.optimizedDistanceKm.toFixed(1)} km shortest path through cylinders</span>
                </div>
              </div>
            </div>
            <div className="task-builder-layout">
                <div className="task-turnpoint-rail">
                  <div className="section-header">
                    <h3>Task turnpoints</h3>
                    <div className="task-turnpoint-toolbar">
                      {canManagePlatform ? (
                      <label className="task-advanced-toggle">
                          <input type="checkbox" checked={taskPointAdvanced} onChange={(event) => toggleTaskPointAdvanced(event.target.checked)} />
                          <span>Advanced</span>
                        </label>
                      ) : null}
                    </div>
                  </div>
                  <p className="hint">{canManagePlatform ? "Click waypoint markers on the map to add them. Drag cards to reorder the task." : "Published task turnpoints are shown here in route order."}</p>
                  {canManagePlatform ? (
                    <div className="task-search-panel">
                      <label className="stack compact">
                        <span>Search turnpoints</span>
                        <input
                          type="text"
                          value={turnpointSearch}
                          onChange={(event) => setTurnpointSearch(event.target.value)}
                          placeholder="Search by name or waypoint code"
                        />
                      </label>
                      {turnpointSearch.trim() ? (
                        filteredTurnpoints.length ? (
                          <div className="task-search-results">
                            {filteredTurnpoints.map((turnpoint) => (
                              <div key={`search-${turnpoint.id}`} className="task-search-row">
                                <div>
                                  <strong>{turnpoint.name}</strong>
                                  <span>{turnpoint.code ?? ""}</span>
                                </div>
                                <button type="button" className="ghost-button" onClick={() => addTurnpoint(turnpoint)}>Add</button>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="hint">No turnpoints match that search.</p>
                        )
                      ) : null}
                    </div>
                  ) : null}
                  <div className="task-point-list-table-wrap">
                    {taskDraft.points.length ? (
                      <table className="task-point-list-table">
                        <thead>
                          <tr>
                            <th></th>
                            <th>Name</th>
                            <th>Type</th>
                            <th>Radius (m)</th>
                            {canManagePlatform ? <th></th> : null}
                          </tr>
                        </thead>
                        <tbody>
                          {taskDraft.points.map((point, index) => {
                            const waypointCode = turnpoints.find((turnpoint) => turnpoint.id === point.turnpoint_id)?.code;
                            return (
                              <tr
                                key={`compact-${point.turnpoint_id ?? point.name}-${index}`}
                                className={`point-type-${(taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type)).toLowerCase()}`}
                                draggable={canManagePlatform}
                                onDragStart={(event) => event.dataTransfer.setData("text/plain", String(index))}
                                onDragOver={(event) => event.preventDefault()}
                                onDrop={(event) => {
                                  event.preventDefault();
                                  movePoint(Number(event.dataTransfer.getData("text/plain")), index);
                                }}
                              >
                                <td className="task-point-row-order">
                                  <span className="drag-handle" title="Drag to reorder">{point.position}. :::</span>
                                </td>
                                <td className="task-point-row-name">
                                  <strong>{point.name}</strong>
                                  {waypointCode ? <span>{waypointCode}</span> : null}
                                </td>
                                <td className="task-point-row-type">
                                  {canManagePlatform ? (
                                    <select value={taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type)} onChange={(event) => updatePoint(index, { point_type: event.target.value })}>
                                      {taskPointTypeOptions.map((option) => (
                                        <option key={option.value} value={option.value}>{option.label}</option>
                                      ))}
                                    </select>
                                  ) : (
                                    <span className="task-point-type-badge">{pointTypeLabels[taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type)] ?? (taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type))}</span>
                                  )}
                                </td>
                                <td className="task-point-row-radius">
                                  {canManagePlatform ? (
                                    <input
                                      type="text"
                                      inputMode="numeric"
                                      value={radiusInputValue(index, point)}
                                      onFocus={(event) => event.currentTarget.select()}
                                      onChange={(event) => handleRadiusInputChange(index, point, event.target.value)}
                                      onBlur={() => handleRadiusInputBlur(index, point)}
                                      onKeyDown={(event) => handleRadiusInputKeyDown(event, index, point)}
                                      placeholder="400"
                                      aria-label={`Radius in meters for ${point.name}`}
                                    />
                                  ) : (
                                    <span>{formatMeters(point.radius_m)}</span>
                                  )}
                                </td>
                                {canManagePlatform ? (
                                  <td className="task-point-row-actions">
                                    <button type="button" className="ghost-button danger-button" onClick={() => removePoint(index)}>Remove</button>
                                  </td>
                                ) : null}
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    ) : null}
                  </div>
                  <div className="task-point-list task-point-list-legacy" aria-hidden="true">
                    {taskDraft.points.map((point, index) => (
                      <div
                        key={`${point.turnpoint_id ?? point.name}-${index}`}
                        className={`task-point-card point-type-${(taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type)).toLowerCase()}`}
                        draggable={canManagePlatform}
                        onDragStart={(event) => event.dataTransfer.setData("text/plain", String(index))}
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={(event) => {
                        event.preventDefault();
                        movePoint(Number(event.dataTransfer.getData("text/plain")), index);
                      }}
                    >
                        <div className="task-point-card-top">
                          <span className="drag-handle" title="Drag to reorder">{point.position}. ⋮⋮</span>
                          <strong>{point.name}</strong>
                          <span className="task-point-description">{turnpoints.find((turnpoint) => turnpoint.id === point.turnpoint_id)?.code ?? ""}</span>
                          <span className="task-point-type-badge">{pointTypeLabels[taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type)] ?? (taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type))}</span>
                        </div>
                        <div className="task-point-card-grid">
                          {canManagePlatform ? (
                            <>
                              <label className="stack compact">
                                <span>Type</span>
                                <select value={taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type)} onChange={(event) => updatePoint(index, { point_type: event.target.value })}>
                                  {taskPointTypeOptions.map((option) => (
                                    <option key={option.value} value={option.value}>{option.label}</option>
                                  ))}
                                </select>
                              </label>
                            <label className="stack compact">
                              <span>Radius (m)</span>
                              <input
                                type="text"
                                inputMode="numeric"
                                value={radiusInputValue(index, point)}
                                onFocus={(event) => event.currentTarget.select()}
                                onChange={(event) => handleRadiusInputChange(index, point, event.target.value)}
                                onBlur={() => handleRadiusInputBlur(index, point)}
                                onKeyDown={(event) => handleRadiusInputKeyDown(event, index, point)}
                                placeholder="400"
                                aria-label={`Radius in meters for ${point.name}`}
                              />
                            </label>
                          </>
                        ) : (
                          <>
                            <div className="record-card">
                              <strong>Type</strong>
                              <span>{pointTypeLabels[taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type)] ?? (taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type))}</span>
                            </div>
                            <div className="record-card">
                              <strong>Radius</strong>
                              <span>{point.radius_m.toFixed(0)} m</span>
                            </div>
                          </>
                        )}
                      </div>
                      {canManagePlatform ? (
                        <div className="task-point-card-actions">
                          <button type="button" className="ghost-button danger-button" onClick={() => removePoint(index)}>Remove</button>
                        </div>
                      ) : null}
                    </div>
                  ))}
                  {taskDraft.points.length === 0 ? <p className="hint">No turnpoints selected yet. Click waypoint markers on the map to add them to this task.</p> : null}
                </div>
                <p className="hint">{taskPointAdvanced ? "Advanced mode keeps Launch, Start, ESS, and Goal separate for scoring." : "Simple mode uses Start, Turnpoint, and Goal only. Launch scores as Start, and ESS scores as Goal."}</p>
              </div>
              <div className="task-map-panel">
                  <TaskMap
                    turnpoints={taskSectionMapTurnpoints}
                    airspaces={visibleAirspaces}
                    taskPoints={taskDraft.points}
                    optimizedRoute={taskDistanceMetrics.routeCoordinates}
                    legMetrics={taskDistanceMetrics.legMetrics}
                    totalDistanceKm={taskDistanceMetrics.totalDistanceKm}
                    optimizedDistanceKm={taskDistanceMetrics.optimizedDistanceKm}
                    track={track}
                    editable={canManagePlatform}
                    onSelectTurnpoint={canManagePlatform ? addTurnpoint : undefined}
                    taskEditorOverlay={fullscreenTaskEditor}
                    fitKey={selectedTaskId}
                  />
                </div>
              </div>
            <div className="stack">
              <button type="button" className="ghost-button advanced-toggle" onClick={() => setTaskAdvancedOpen((current) => !current)}>
                {taskAdvancedOpen ? "Hide Advanced Settings" : "Advanced Settings"}
              </button>
              {taskAdvancedOpen ? (
                <div className="stack">
                  <div className="inline-grid">
                    <label className={canManagePlatform ? "stack compact" : "stack compact field-disabled"}>
                      <span>Nominal distance (km)</span>
                      <input type="number" value={taskDraft.nominal_distance_km} onChange={(event) => setTaskDraft({ ...taskDraft, nominal_distance_km: Number(event.target.value) })} disabled={!canManagePlatform} />
                    </label>
                    <label className={canManagePlatform ? "stack compact" : "stack compact field-disabled"}>
                      <span>Nominal time (hours)</span>
                      <input type="number" value={taskDraft.nominal_time_hours} onChange={(event) => setTaskDraft({ ...taskDraft, nominal_time_hours: Number(event.target.value) })} disabled={!canManagePlatform} />
                    </label>
                    <label className={canManagePlatform ? "stack compact" : "stack compact field-disabled"}>
                      <span>Nominal launch</span>
                      <input type="number" step="0.01" value={taskDraft.nominal_launch} onChange={(event) => setTaskDraft({ ...taskDraft, nominal_launch: Number(event.target.value) })} disabled={!canManagePlatform} />
                    </label>
                    <label className={canManagePlatform ? "stack compact" : "stack compact field-disabled"}>
                      <span>Minimum distance (km)</span>
                      <input type="number" value={taskDraft.minimum_distance_km} onChange={(event) => setTaskDraft({ ...taskDraft, minimum_distance_km: Number(event.target.value) })} disabled={!canManagePlatform} />
                    </label>
                  </div>
                  <label className={canManagePlatform ? "stack compact" : "stack compact field-disabled"}>
                    <span>Task penalty / notes JSON</span>
                    <textarea value={taskDraft.penalties_text} onChange={(event) => setTaskDraft({ ...taskDraft, penalties_text: event.target.value })} rows={4} disabled={!canManagePlatform} />
                  </label>
                </div>
              ) : null}
            </div>
            {canManagePlatform ? (
              <div className="stack compact task-action-stack">
                <div className="button-row">
                  <button type="button" onClick={saveTask}>Save task</button>
                  <button type="button" className="secondary" onClick={publishTask} disabled={!taskDraft.id}>Publish task</button>
                  <button type="button" className="ghost-button danger-button task-delete-button" onClick={deleteTask} disabled={!taskDraft.id}>Delete task</button>
                  <button type="button" className="ghost-button task-unpublish-button" onClick={unpublishTask} disabled={!taskDraft.id || selectedTask?.status !== "published"}>Unpublish task</button>
                </div>
                {taskFeedback ? <div className={`status-chip ${taskFeedback.type}`}>{taskFeedback.text}</div> : null}
              </div>
            ) : null}
          </div>
        </SectionCard>
      </div>
    );
  }

  function renderScoringSection() {
    if (!selectedEventId) return <SectionCard title="Scoring" description="Create or select an event first."><p className="hint">Scoring depends on an event and, usually, a selected task.</p></SectionCard>;
    return (
      <div className="section-stack">
        {canManagePlatform ? (
          <div className="tab-row">
            <button type="button" className={scoresPortalTab === "admin" ? "tab-button active" : "tab-button"} onClick={() => setScoresPortalTab("admin")}>Scoring operations</button>
            <button type="button" className={scoresPortalTab === "results" ? "tab-button active" : "tab-button"} onClick={() => setScoresPortalTab("results")}>Results portal</button>
          </div>
        ) : null}
        {canManagePlatform && scoresPortalTab === "admin" ? (
          <SectionCard title="Scoring operations" description="Upload missing IGC files on behalf of pilots, then run scoring manually for the selected task.">
            <div className="stack form-block">
              <label className="stack compact">
                <span>Selected task</span>
                <select value={selectedTaskId ?? ""} onChange={(event) => { const nextId = Number(event.target.value); const nextTask = tasks.find((task) => task.id === nextId); if (nextTask) void loadTask(token, nextId, nextTask); }}>
                  <option value="">Select a task</option>
                  {tasks.map((task) => <option key={task.id} value={task.id}>{task.name} - {task.status}</option>)}
                </select>
              </label>
              <div className="inline-grid">
                <label className="stack compact">
                  <span>Pilot for upload</span>
                  <select value={adminUploadPilotId ?? ""} onChange={(event) => setAdminUploadPilotId(event.target.value ? Number(event.target.value) : null)}>
                    <option value="">Select a pilot</option>
                    {pilots.map((pilot) => (
                      <option key={pilot.id} value={pilot.id}>
                        {pilot.first_name} {pilot.last_name}{pilot.competition_number ? ` - #${pilot.competition_number}` : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="file-input">
                  Upload IGC for pilot
                  <input
                    type="file"
                    accept=".igc"
                    disabled={!selectedTaskId || !adminUploadPilotId}
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file && adminUploadPilotId) void uploadIgc(file, adminUploadPilotId);
                      event.currentTarget.value = "";
                    }}
                  />
                </label>
              </div>
              <label className="file-input">
                Upload multiple IGC files and auto-match pilots
                <input
                  type="file"
                  accept=".igc"
                  multiple
                  disabled={!selectedTaskId}
                  onChange={(event) => {
                    const files = event.target.files;
                    if (files?.length) void uploadIgcBatch(files);
                    event.currentTarget.value = "";
                  }}
                />
              </label>
                {uploadFeedback ? <div className={`status-chip ${uploadFeedback.type}`}>{uploadFeedback.text}</div> : null}
                <p className="hint">Bulk upload matches files to pilots using the IGC pilot header plus the filename against the event roster. Files that cannot be matched confidently are skipped and reported back to you.</p>
                <div className="button-row">
                  <button type="button" onClick={() => void rescoreSelectedTask()}>Run scoring</button>
                  {scoringFeedback ? <div className={`status-chip ${scoringFeedback.type}`}>{scoringFeedback.text}</div> : null}
                </div>
                {uploads.length ? (
                <div className="stack">
                  {uploads.map((upload) => (
                    <div key={upload.id} className="record-card upload-record">
                      <div>
                        <strong>{upload.filename}</strong>
                        <span>{pilotNameById.get(upload.pilot_id) ?? `Pilot ${upload.pilot_id}`} - {upload.sha256.slice(0, 12)}... uploaded {new Date(upload.uploaded_at).toLocaleString()}</span>
                      </div>
                      <button type="button" className="ghost-button danger-button" onClick={() => void deleteUpload(upload)}>Delete</button>
                    </div>
                  ))}
                </div>
              ) : <p className="hint">No IGC uploads have been stored for this task yet.</p>}
            </div>
          </SectionCard>
        ) : null}
        {!canManagePlatform || scoresPortalTab === "results" ? (
        <SectionCard title="Results portal" description="Task results and overall standings are visible to all signed-in users.">
          <div className="stack">
            <div className="tab-row">
              <button type="button" className={scoringTab === "task" ? "tab-button active" : "tab-button"} onClick={() => setScoringTab("task")}>Task results</button>
              <button type="button" className={scoringTab === "overall" ? "tab-button active" : "tab-button"} onClick={() => setScoringTab("overall")}>Overall results</button>
            </div>
            {scoringTab === "task" ? (
              <div className="stack form-block">
                <label className="stack compact">
                  <span>Selected task</span>
                  <select value={selectedTaskId ?? ""} onChange={(event) => { const nextId = Number(event.target.value); const nextTask = tasks.find((task) => task.id === nextId); if (nextTask) void loadTask(token, nextId, nextTask); }}>
                    <option value="">Select a task</option>
                    {tasks.map((task) => <option key={task.id} value={task.id}>{task.name} - {task.status}</option>)}
                  </select>
                </label>
                {taskDefinitionRows.length ? (
                  <div className="results-sheet task-definition-sheet">
                    <div className="results-sheet-header">
                      <h3>Task definition</h3>
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
                        <p>{taskTypeLabel(selectedTask?.task_type ?? taskDraft.task_type)} {taskDistanceMetrics.optimizedDistanceKm ? `- ${taskDistanceMetrics.optimizedDistanceKm.toFixed(1)} km` : ""}</p>
                      </div>
                      <div className="button-row">
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={() => void downloadAllIgcFiles()}
                          disabled={resultsDownloadFeedback?.type === "pending" && resultsDownloadFeedback.all}
                        >
                          {resultsDownloadFeedback?.type === "pending" && resultsDownloadFeedback.all ? "Preparing..." : "Download all IGC files"}
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
                              <th>Total</th>
                              <th>IGC file</th>
                            </tr>
                          </thead>
                          <tbody>
                            {results.map((result) => {
                              const pilot = pilotById.get(result.pilot_id);
                              return (
                                <tr key={result.id}>
                                  <td>{result.rank ?? "-"}</td>
                                <td>
                                  <strong>{result.pilot_name}</strong>
                                  <div className="results-name-meta">{result.status.toUpperCase()}</div>
                                </td>
                                <td>{pilot?.nation ?? "-"}</td>
                                <td>-</td>
                                <td>{formatClockTime(result.started_at, true)}</td>
                                  <td>{formatClockTime(result.goal_at ?? result.ess_at, true)}</td>
                                  <td>{formatElapsedSeconds(result.elapsed_seconds)}</td>
                                  <td>{formatSpeedKmh(result.distance_flown_km, result.elapsed_seconds)}</td>
                                  <td>{result.distance_flown_km.toFixed(1)}</td>
                                  {taskResultsColumns.map((column) => (
                                    <td key={column.key}>{formatResultPoints(gapAwardedPoints(result, column.key))}</td>
                                  ))}
                                  <td className="results-table-total">{result.score_points.toFixed(1)}</td>
                                  <td>
                                    <button
                                      type="button"
                                      className="ghost-button"
                                      disabled={resultsDownloadFeedback?.type === "pending" && resultsDownloadFeedback.uploadId === result.upload_id}
                                      onClick={() => void downloadUploadFile(result.upload_id, uploadById.get(result.upload_id)?.filename ?? `${result.pilot_name}.igc`)}
                                    >
                                      {resultsDownloadFeedback?.type === "pending" && resultsDownloadFeedback.uploadId === result.upload_id ? "Preparing..." : "Download"}
                                    </button>
                                  </td>
                                </tr>
                              );
                          })}
                        </tbody>
                      </table>
                    </div>
                    {taskDraft.points.length ? (
                      <div className="results-task-map">
                        <div className="results-sheet-header">
                          <h3>Task map</h3>
                          <p>Waypoints, cylinders, course line, and checked pilot tracks for the selected task.</p>
                        </div>
                        <div className="results-task-map-layout">
                          <div className="results-task-map-pilot-list">
                            <div className="results-task-map-pilot-header">
                              <strong>Show pilot tracks</strong>
                              <span>{selectedResultUploadIds.length} selected</span>
                            </div>
                            <div className="results-task-map-pilot-items">
                              {results.map((result) => {
                                const isChecked = selectedResultUploadIds.includes(result.upload_id);
                                const pilotTrackColor = resultTrackColorsByUploadId.get(result.upload_id) ?? resultTrackPalette[0];
                                return (
                                  <label key={result.id} className="results-task-map-pilot-item">
                                    <input
                                      type="checkbox"
                                      checked={isChecked}
                                      onChange={(event) => void toggleResultTrack(result.upload_id, event.target.checked)}
                                    />
                                    <span className="results-task-map-pilot-rank">{result.rank ?? "-"}</span>
                                    <span className="results-task-map-pilot-copy">
                                      <strong style={{ color: pilotTrackColor }}>{result.pilot_name}</strong>
                                      <small>{result.status.toUpperCase()} · {result.score_points.toFixed(1)} pts</small>
                                    </span>
                                  </label>
                                );
                              })}
                            </div>
                          </div>
                          <TaskMap
                            turnpoints={resultsTaskMapTurnpoints}
                            airspaces={[]}
                            taskPoints={taskDraft.points}
                            optimizedRoute={taskDistanceMetrics.routeCoordinates}
                            legMetrics={taskDistanceMetrics.legMetrics}
                            totalDistanceKm={taskDistanceMetrics.totalDistanceKm}
                            optimizedDistanceKm={taskDistanceMetrics.optimizedDistanceKm}
                            track={resultsTrackOverlay}
                            editable={false}
                            fitKey={`${selectedTaskId}:${selectedResultUploadIds.join(",")}`}
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
                              <td>{formatDateLabel(task.published_at)}</td>
                              <td>{(taskMetricsById.get(task.id)?.optimizedDistanceKm ?? 0).toFixed(1)}</td>
                              <td>{selectedTaskId === task.id ? taskDayQuality(results) : "-"}</td>
                              <td>{taskTypeLabel(task.task_type)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="results-table-wrap">
                      <table className="results-table">
                        <thead>
                          <tr>
                            <th>#</th>
                            <th>Name</th>
                            <th>Nat</th>
                            <th>Glider</th>
                            {scoredTasks.map((task, index) => <th key={task.id}>{`T ${index + 1}`}</th>)}
                            <th>Total</th>
                          </tr>
                        </thead>
                        <tbody>
                          {pilotSummary.map((summary, index) => {
                            const pilot = pilotById.get(summary.pilot_id);
                            return (
                              <tr key={summary.pilot_id}>
                                <td>{index + 1}</td>
                                <td><strong>{summary.pilot_name}</strong></td>
                                <td>{pilot?.nation ?? "-"}</td>
                                <td>-</td>
                                {scoredTasks.map((task) => <td key={task.id}>{summary.task_scores[String(task.id)] != null ? formatResultPoints(summary.task_scores[String(task.id)]) : "-"}</td>)}
                                <td className="results-table-total">{summary.total_score_points.toFixed(1)}</td>
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
        </SectionCard>
        ) : null}
      </div>
    );
    }

  function renderSettingsSection() {
    return (
      <div className="section-stack">
        <div className="settings-summary-row">
          <span className="role-pill settings-role-pill">Active role: {settingsForm.role}</span>
          <label className="settings-type-control">
            <span>Current type</span>
            <select value={settingsForm.profile_type} onChange={(event) => setSettingsForm((current) => ({ ...current, profile_type: event.target.value as "pilot" | "driver" }))}>
              <option value="pilot">Pilot</option>
              <option value="driver">Driver</option>
            </select>
          </label>
        </div>
        <SectionCard title="Account settings" description="Update the profile details used across the Aervyx portal.">
          <form className="stack form-block" onSubmit={saveAccountSettings}>
            <div className="inline-grid">
              <label className="stack compact">
                <span>Username / email</span>
                <input
                  type="email"
                  value={settingsForm.username ?? ""}
                  onChange={(event) =>
                    setSettingsForm((current) => ({
                      ...current,
                      username: event.target.value,
                      email: event.target.value,
                    }))
                  }
                  placeholder="pilot@example.com"
                  required
                />
              </label>
              <label className="stack compact">
                <span>Display name</span>
                <input value={settingsForm.full_name ?? ""} onChange={(event) => setSettingsForm((current) => ({ ...current, full_name: event.target.value }))} required />
              </label>
            </div>
            <div className="inline-grid">
              <label className="stack compact">
                <span>Nation</span>
                <input value={settingsForm.nation ?? ""} onChange={(event) => setSettingsForm((current) => ({ ...current, nation: event.target.value.toUpperCase() }))} maxLength={3} />
              </label>
              <label className="stack compact">
                <span>Competition number</span>
                <input value={settingsForm.competition_number ?? ""} onChange={(event) => setSettingsForm((current) => ({ ...current, competition_number: event.target.value }))} />
              </label>
            </div>
            <div className="inline-grid">
              <label className="stack compact">
                <span>First name</span>
                <input value={settingsForm.first_name ?? ""} onChange={(event) => setSettingsForm((current) => ({ ...current, first_name: event.target.value }))} />
              </label>
              <label className="stack compact">
                <span>Last name</span>
                <input value={settingsForm.last_name ?? ""} onChange={(event) => setSettingsForm((current) => ({ ...current, last_name: event.target.value }))} />
              </label>
            </div>
            <div className="inline-grid">
              <label className="stack compact">
                <span>CIVL ID</span>
                <input value={settingsForm.civl_id ?? ""} onChange={(event) => setSettingsForm((current) => ({ ...current, civl_id: event.target.value }))} />
              </label>
              <div />
            </div>
            <div className="button-row">
              <button type="submit">Save account settings</button>
            </div>
            {settingsFeedback.profile ? <div className={`status-chip ${settingsFeedback.profile.type}`}>{settingsFeedback.profile.text}</div> : null}
          </form>
        </SectionCard>
        <SectionCard title="Password" description="Change your password securely using your current password first.">
          <form className="stack form-block" onSubmit={savePasswordSettings}>
            <label className="stack compact">
              <span>Current password</span>
              <input type="password" value={settingsPasswordForm.current_password} onChange={(event) => setSettingsPasswordForm((current) => ({ ...current, current_password: event.target.value }))} autoComplete="current-password" required />
            </label>
            <div className="inline-grid">
              <label className="stack compact">
                <span>New password</span>
                <input type="password" value={settingsPasswordForm.new_password} onChange={(event) => setSettingsPasswordForm((current) => ({ ...current, new_password: event.target.value }))} autoComplete="new-password" required />
              </label>
              <label className="stack compact">
                <span>Confirm new password</span>
                <input type="password" value={settingsPasswordForm.confirm_password} onChange={(event) => setSettingsPasswordForm((current) => ({ ...current, confirm_password: event.target.value }))} autoComplete="new-password" required />
              </label>
            </div>
            <div className="button-row">
              <button type="submit">Update password</button>
            </div>
            {settingsFeedback.password ? <div className={`status-chip ${settingsFeedback.password.type}`}>{settingsFeedback.password.text}</div> : null}
          </form>
        </SectionCard>
      </div>
    );
  }

  function renderAdminSection() {
    return (
      <div className="section-stack">
        <SectionCard title="Platform users" description="Admins can manage organizer and pilot accounts for the entire platform here.">
          <div className="stack form-block">
            {adminFeedback ? <div className={`status-chip ${adminFeedback.type}`}>{adminFeedback.text}</div> : null}
            <div className="participant-table-wrap">
              <table className="participant-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Username</th>
                    <th>Role</th>
                    <th>Email</th>
                    <th>Linked pilot</th>
                    <th>Status</th>
                    <th className="participant-table-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {adminUsers.length ? (
                    adminUsers.map((account) => (
                      <tr key={account.id}>
                        <td><strong>{account.full_name}</strong></td>
                        <td>{account.username}</td>
                        <td>
                          <select
                            value={account.role}
                            disabled={account.id === user?.id}
                            onChange={(event) => setAdminUsers((current) => current.map((entry) => entry.id === account.id ? { ...entry, role: event.target.value as AdminUserRecord["role"] } : entry))}
                          >
                            <option value="admin">Admin</option>
                            <option value="organizer">Organizer</option>
                            <option value="pilot">Pilot</option>
                          </select>
                        </td>
                        <td>{account.email ?? "-"}</td>
                        <td>{account.pilot_name ?? "-"}</td>
                        <td>
                          <label className="task-advanced-toggle">
                            <input
                              type="checkbox"
                              checked={account.is_active}
                              disabled={account.id === user?.id}
                              onChange={(event) => setAdminUsers((current) => current.map((entry) => entry.id === account.id ? { ...entry, is_active: event.target.checked } : entry))}
                            />
                            <span>{account.is_active ? "Active" : "Disabled"}</span>
                          </label>
                        </td>
                        <td className="participant-table-actions">
                          <div className="compact-slot-actions">
                            <button type="button" className="ghost-button" onClick={() => void saveAdminUser(account)}>Save</button>
                            <button type="button" className="ghost-button danger-button" disabled={account.id === user?.id} onClick={() => void deleteAdminUser(account)}>Delete</button>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7} className="participant-table-empty">No platform users found.</td>
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

  function renderActiveSection() {
      if (user?.role === "pilot" && activeSection === "events") {
        return renderTasksSection();
      }
      switch (activeSection) {
        case "events":
          return renderEventsSection();
        case "tasks":
          return renderTasksSection();
        case "scoring":
          return renderScoringSection();
        case "live_tracking":
          return <SectionCard title="Live Tracking" description="Live tracking tools will be added here next."><p className="hint">This area is reserved for future live tracking workflows.</p></SectionCard>;
        case "drivers":
          return <SectionCard title="Drivers" description="Driver logistics and tracking tools will be added here next."><p className="hint">This area is reserved for future driver support workflows.</p></SectionCard>;
        case "settings":
          return renderSettingsSection();
        case "admin":
          return isAdmin ? renderAdminSection() : renderSettingsSection();
      }
    }

  if (!user) {
    return null;
  }

  return (
    <main className="shell">
      <div className={sidebarCompact ? "workspace-shell sidebar-compact" : "workspace-shell"}>
          <AppSidebar
            items={sidebarItems}
            activeItem={activeSection}
            onSelect={(id) => setActiveSection(id as SidebarSection)}
            eventName={selectedEvent?.name ?? null}
            compact={sidebarCompact}
            onToggleCompact={() => setSidebarCompact((current) => !current)}
          />
          <section className="content-shell">
            <section className="panel hero content-hero">
              <div>
                <p className="eyebrow">{user.role === "admin" ? "Admin Portal" : user.role === "organizer" ? "Organizer Portal" : "Pilot Portal"}</p>
                <h1>{sidebarItems.find((item) => item.id === activeSection)?.label}</h1>
                <p className="lede">{selectedEvent ? `${selectedEvent.name} - ${selectedEvent.location}` : "Select or create an event to begin."}</p>
              </div>
              <div className="hero-actions">
                <div className="role-pill">{user.role}</div>
                <button className="signout" onClick={signOut}>Sign out</button>
              </div>
            </section>
            {error ? (
              <div className="status-row">
                <div className="status-chip error">{error}</div>
              </div>
            ) : null}
            {message && message !== DEFAULT_MESSAGE ? (
              <div className="status-row">
                <div className="status-chip success">{message}</div>
              </div>
            ) : null}
            {renderActiveSection()}
          </section>
        </div>
    </main>
  );
}
