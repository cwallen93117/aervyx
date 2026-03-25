import type { MapAirspaceRegion, MapTaskPoint, MapTurnpoint, TrackCollection } from "../TaskMap";

export type SidebarSection = "events" | "tasks" | "scoring" | "live_tracking" | "drivers" | "settings" | "admin";
export type EventTab = "details" | "turnpoints" | "airspace" | "participants" | "scoring";
export type User = { id: number; username: string; full_name: string; role: "admin" | "organizer" | "pilot"; profile_type: "pilot" | "driver"; pilot_id: number | null };
export type AccountSettingsRecord = {
  username: string;
  full_name: string;
  role: "admin" | "organizer" | "pilot";
  profile_type: "pilot" | "driver";
  altitude_unit: "ft" | "m";
  speed_unit: "kph" | "mph";
  distance_unit: "km" | "mi";
  vario_unit: "fpm" | "ms";
  email: string | null;
  first_name: string | null;
  last_name: string | null;
  nation: string | null;
  competition_number: string | null;
  civl_id: string | null;
  access_token?: string | null;
};
export type AdminUserRecord = {
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
export type SiteSettingsRecord = {
  telemetry_vario_smoothing_seconds: number;
  telemetry_altitude_smoothing_seconds: number;
  telemetry_speed_smoothing_seconds: number;
  telemetry_glide_ratio_smoothing_seconds: number;
  updated_at?: string | null;
};
export type EventRecord = {
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
export type PilotRecord = { id: number; first_name: string; last_name: string; email?: string | null; nation?: string | null; competition_number: string | null; civl_id?: string | null; portal_username: string | null; temp_password: string | null };
export type TurnpointRecord = MapTurnpoint & { event_id: number; source_id: number | null; elevation_m: number | null };
export type TurnpointSourceRecord = { id: number; event_id: number; filename: string; file_format: string; sha256: string; enabled: boolean; uploaded_at: string; turnpoint_count: number };
export type TaskPointRecord = MapTaskPoint & { id?: number; turnpoint_id: number | null };
export type TaskRecord = {
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
export type ResultRecord = { id: number; upload_id: number | null; pilot_id: number; pilot_name: string; competition_number?: string | null; status: string; distance_flown_km: number; elapsed_seconds?: number | null; started_at?: string | null; ess_at?: string | null; goal_at?: string | null; raw_score_points?: number; score_points: number; rank: number | null; details_json: Record<string, unknown>; result_state?: string };
export type PilotSummaryRecord = { pilot_id: number; pilot_name: string; competition_number?: string | null; total_score_points: number; tasks_scored: number; best_distance_km: number; task_scores: Record<string, number> };
export type UploadRecord = { id: number; pilot_id: number; filename: string; sha256: string; uploaded_at: string; upload_source?: "manual" | "bulk" | "tracker" | string; metadata_json: Record<string, unknown> };
export type ScoringUploadOptionRecord = { id: number; filename: string; upload_source: "manual" | "bulk" | "tracker" | string; label: string; uploaded_at: string };
export type ScorePenaltyRecord = { id?: number | null; penalty_type: "percentage" | "fixed"; value: number; reason: string; position: number; applied_by?: string | null; applied_at?: string | null };
export type PenaltyAuditRecord = { actor_name: string; timestamp: string; summary: string };
export type ScoringPresetRecord = { id: string; label: string; penalty_type: "percentage" | "fixed"; value: number; reason: string };
export type ScoringOperationsResultRecord = { result_id: number; upload_id: number | null; status: string; rank: number | null; distance_flown_km: number; elapsed_seconds: number | null; raw_score_points: number; score_points: number; result_state?: string };
export type ScoringOperationsRowRecord = {
  pilot_id: number;
  pilot_name: string;
  competition_number?: string | null;
  selected_upload_id: number | null;
  status_override: "minimum_distance" | "did_not_fly" | "absent" | null;
  uploads: ScoringUploadOptionRecord[];
  result: ScoringOperationsResultRecord | null;
  penalties: ScorePenaltyRecord[];
  penalty_summary: string | null;
  penalty_audit: PenaltyAuditRecord[];
  row_classification: "ranked" | "minimum_distance" | "did_not_fly" | "absent" | "unscored" | string;
};
export type ScoringOperationsResponseRecord = { rows: ScoringOperationsRowRecord[] };
export type ScoringInputSelectionRecord = { selected_upload_id: number | null; status_override: "minimum_distance" | "did_not_fly" | "absent" | null };
export type TurnpointUploadResponse = { source_id: number; format: string; imported_count: number; sha256: string; filename: string };
export type BulkUploadItemRecord = { filename: string; matched: boolean; upload_id?: number | null; pilot_id?: number | null; pilot_name?: string | null; message: string };
export type AirspaceSourceRecord = {
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
export type AirspaceUploadResponse = { source_id: number; kind: "airspace" | "restricted_field"; format: string; imported_count: number; sha256: string; filename: string };
export type TaskDraftState = {
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
export type ScoresPortalTab = "admin" | "results";
export type ScoringTab = "task" | "overall";
export type AirspaceCategoryOption = "B" | "C" | "D" | "P" | "Q" | "R" | "TFR" | "OTHER";
export type TaskPointMode = "simple" | "advanced";

export type EventFormState = ReturnType<typeof blankEventForm>;

export function blankEventForm() {
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

export { type MapAirspaceRegion, type MapTurnpoint, type TrackCollection };
