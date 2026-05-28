import type { MapAirspaceRegion, MapTaskPoint, MapTurnpoint, TrackCollection } from "../TaskMap";

export type SidebarSection = "events" | "tasks" | "scoring" | "live_tracking" | "drivers" | "logbook" | "weather" | "airspace" | "sos" | "settings" | "admin";
export type EventTab = "details" | "turnpoints" | "airspace" | "participants" | "scoring";
export type User = { id: number; username: string; full_name: string; role: "admin" | "organizer" | "pilot"; profile_type: "pilot" | "driver"; profile_type_updated_at: string; pilot_id: number | null };
export type AircraftIconType = "hang_glider" | "paraglider" | "sailplane";
export type AccountSettingsRecord = {
  username: string;
  full_name: string;
  role: "admin" | "organizer" | "pilot";
  profile_type: "pilot" | "driver";
  profile_type_updated_at: string;
  altitude_unit: "ft" | "m";
  speed_unit: "kph" | "mph";
  distance_unit: "km" | "mi";
  vario_unit: "fpm" | "ms";
  aircraft_icon: AircraftIconType;
  email: string | null;
  first_name: string | null;
  last_name: string | null;
  nation: string | null;
  competition_number: string | null;
  civl_id: string | null;
  pilot_id: number | null;
  has_password?: boolean;
  access_token?: string | null;
};
export type AdminUserRecord = {
  id: number;
  username: string;
  full_name: string;
  first_name: string | null;
  last_name: string | null;
  role: "admin" | "organizer" | "pilot";
  profile_type: "pilot" | "driver";
  profile_type_updated_at: string;
  pilot_id: number | null;
  email: string | null;
  pilot_name: string | null;
  competition_number: string | null;
  mesh_device_id: string | null;
  mesh_devices: MeshDeviceRecord[];
  is_active: boolean;
  created_at: string;
};
export type MeshDevicePurpose = "tracking" | "base_station" | "driver_wifi" | "driver_mesh" | "relay";
export type MeshDeviceRecord = {
  id: number;
  owner_user_id: number;
  owner_name: string | null;
  device_id: string;
  label: string;
  purpose: MeshDevicePurpose;
  is_pilot_tracker: boolean;
  created_at: string;
  updated_at: string | null;
};
export type AdminSiteRecord = {
  id: number;
  name: string;
  city_state: string;
  latitude: number;
  longitude: number;
  is_active: boolean;
  flight_count: number;
  created_at: string;
  updated_at: string;
};
export type AdminSiteRescanResultRecord = {
  scanned_count: number;
  matched_count: number;
  unmatched_count: number;
};
export type AdminSiteScanIgcResultRecord = {
  new_sites_created: number;
  flights_matched: number;
  total_igc_scanned: number;
  sites: AdminSiteRecord[];
};
export type MapOverlayContextConfig = Record<string, boolean>;
export type MapOverlayConfigShape = {
  schema_version?: number;
  groups?: Record<string, MapOverlayContextConfig>;
  task_builder?: MapOverlayContextConfig;
  scoring?: MapOverlayContextConfig;
  logbook_replay?: MapOverlayContextConfig;
  dashboard_live?: MapOverlayContextConfig;
  public_live?: MapOverlayContextConfig;
  airspace_explorer?: MapOverlayContextConfig;
  soaring_forecast?: MapOverlayContextConfig;
  admin_site_preview?: MapOverlayContextConfig;
};
export type MapOverlayConfigRecord = {
  config: MapOverlayConfigShape;
  updated_at?: string | null;
};
export type MqttBrokerMode = "local_mosquitto" | "cloud_vm";
export type SiteSettingsRecord = {
  telemetry_vario_smoothing_seconds: number;
  telemetry_altitude_smoothing_seconds: number;
  telemetry_speed_smoothing_seconds: number;
  telemetry_glide_ratio_smoothing_seconds: number;
  max_map_pitch_degrees: number;
  site_match_radius_m: number;
  mqtt_enabled: boolean;
  mqtt_broker_mode: MqttBrokerMode;
  mqtt_host: string | null;
  mqtt_port: number;
  mqtt_tls_enabled: boolean;
  mqtt_username: string | null;
  mqtt_password: string | null;
  mqtt_topic_prefix: string;
  mqtt_channel_psk: string | null;
  cloudflare_ddns_enabled: boolean;
  cloudflare_ddns_zone_id: string | null;
  cloudflare_ddns_api_token_configured: boolean;
  cloudflare_ddns_api_token?: string | null;
  cloudflare_ddns_clear_api_token?: boolean;
  cloudflare_ddns_record_names: string[];
  cloudflare_ddns_check_interval_hours: number;
  cloudflare_ddns_last_checked_at: string | null;
  cloudflare_ddns_last_public_ip: string | null;
  cloudflare_ddns_last_update_result: string | null;
  cloudflare_ddns_last_error: string | null;
  mesh_profiles: Record<string, Record<string, unknown>> | null;
  updated_at?: string | null;
};
export type LogbookFlightStatsRecord = {
  duration_seconds: number | null;
  highest_altitude_m: number | null;
  best_climb_mps: number | null;
  launch_time: string | null;
  landing_time: string | null;
  launch_altitude_m: number | null;
  landing_altitude_m: number | null;
  time_in_thermals_seconds: number;
  time_on_glide_seconds: number;
  total_track_distance_km: number;
  max_ground_speed_kmh: number | null;
};
export type LogbookFlightSummaryRecord = {
  id: number;
  source_kind: "task_upload" | "app_upload" | "manual" | string;
  flight_date: string;
  starred: boolean;
  site_id?: number | null;
  site_name: string;
  site_city_state?: string | null;
  duration_seconds: number | null;
  highest_altitude_m: number | null;
  best_climb_mps: number | null;
  event_name: string | null;
  task_name: string | null;
  filename: string | null;
  can_download: boolean;
  can_replay: boolean;
  has_statistics: boolean;
};
export type LogbookFlightDetailRecord = LogbookFlightSummaryRecord & {
  notes: string | null;
  stats: LogbookFlightStatsRecord;
};
export type LogbookFolderImportItemRecord = {
  file_key: string;
  sha256: string;
  filename: string;
  relative_path: string | null;
  detected_pilot_name: string | null;
  reason: string;
  flight_id: number | null;
};
export type LogbookFolderImportResultRecord = {
  imported: LogbookFolderImportItemRecord[];
  skipped: LogbookFolderImportItemRecord[];
  review_needed: LogbookFolderImportItemRecord[];
};
export type LogbookBulkDeleteResponseRecord = {
  deleted_ids: number[];
  deleted_count: number;
};
export type LogbookFlightFormRecord = {
  flight_date: string;
  site_name: string;
  duration_seconds: string;
  highest_altitude_m: string;
  best_climb_mps: string;
  notes: string;
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
  default_start_gate_count: number;
  default_start_gate_interval_seconds: number;
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
  is_public_tracking: boolean;
  visibility: "public" | "users" | "participants" | "private";
  updated_at: string;
  pilot_count: number;
  task_count: number;
  turnpoint_count: number;
  airspace_count: number;
  restricted_field_count: number;
};
export type PilotRecord = { id: number; first_name: string; last_name: string; email?: string | null; nation?: string | null; competition_number: string | null; civl_id?: string | null; portal_username: string | null; is_claimed?: boolean; temp_password: string | null };
export type TurnpointRecord = MapTurnpoint & { event_id: number; source_id: number | null; elevation_m: number | null };
export type TurnpointSourceRecord = { id: number; event_id: number; filename: string; file_format: string; sha256: string; enabled: boolean; uploaded_at: string; turnpoint_count: number };
export type TaskPointDirection = "enter" | "exit";
export type TaskPointRecord = MapTaskPoint & { id?: number; turnpoint_id: number | null; direction: TaskPointDirection };
export type TaskRecord = {
  id: number;
  event_id: number;
  name: string;
  task_date: string | null;
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
export type PilotSummaryRecord = { pilot_id: number; pilot_name: string; competition_number?: string | null; total_score_points: number; tasks_scored: number; best_distance_km: number; task_scores: Record<string, number>; task_result_states: Record<string, string> };
export type TaskResultSummaryRecord = { task_id: number; day_quality: number | null };
export type UploadRecord = { id: number; pilot_id: number; filename: string; sha256: string; uploaded_at: string; upload_source?: "manual" | "bulk" | "tracker" | string; metadata_json: Record<string, unknown> };
export type ScoringUploadOptionRecord = { id: number; filename: string; upload_source: "manual" | "bulk" | "tracker" | "app" | string; label: string; uploaded_at: string; late_start?: boolean };
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
export type BulkUploadItemRecord = { filename: string; matched: boolean; upload_id?: number | null; pilot_id?: number | null; pilot_name?: string | null; match_confidence?: string | null; message: string };
export type AirspaceSourceKind = "" | "airspace" | "restricted_field";
export type AirspaceSourceRecord = {
  id: number;
  event_id: number;
  kind: AirspaceSourceKind;
  filename: string;
  file_format: string;
  sha256: string;
  uploaded_at: string;
  region_count: number;
  enabled?: boolean;
};
export type AirspaceUploadResponse = { source_id: number; kind: AirspaceSourceKind; format: string; imported_count: number; sha256: string; filename: string };
export type TaskDraftState = {
  id: number | null;
  name: string;
  task_date: string;
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
    default_start_gate_count: 5,
    default_start_gate_interval_seconds: 900,
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
    is_public_tracking: false,
    visibility: "private" as "public" | "users" | "participants" | "private",
  };
}

export type DebugActiveSession = {
  pilot_id: number | null;
  user_id: number | null;
  pilot_name: string;
  profile_type: string | null;
  task_id: number | null;
  task_name: string | null;
  device_id: string | null;
  source: string | null;
  battery_level: number | null;
  battery_level_seen_at: string | null;
  position_count: number;
  positions_last_60s: number;
  started_at: string | null;
  last_seen_at: string | null;
  last_position: { lat: number; lon: number; alt: number | null; speed: number | null } | null;
  is_online: boolean;
  has_mesh: boolean;
};

export type DebugMeshDevice = {
  owner_user_id: number;
  owner_name: string | null;
  owner_pilot_id: number | null;
  device_id: string;
  label: string;
  purpose: MeshDevicePurpose | string;
  is_connected: boolean;
  mesh_status: "live" | "stale" | "offline" | "never_seen";
  last_seen_at: string | null;
  last_packet_type: string | null;
  last_gateway_id: string | null;
  last_gateway_display_name: string | null;
  last_topic: string | null;
  packet_count: number;
  long_name: string | null;
  short_name: string | null;
  battery_level: number | null;
  battery_level_seen_at: string | null;
  source: string | null;
  last_position: { lat: number; lon: number; alt: number | null; speed: number | null; heading: number | null } | null;
};

export type DebugSosAlert = {
  pilot_id: number;
  pilot_name: string;
  lat: number;
  lon: number;
  alt: number | null;
  message: string;
  timestamp: string;
};

export type DebugStatusResponse = {
  mqtt_connected: boolean;
  mqtt_last_message_at: string | null;
  sse_subscriber_count: number;
  sse_subscribers_by_task: Record<string, number>;
  active_sessions: DebugActiveSession[];
  registered_mesh_devices: DebugMeshDevice[];
  recent_sos_alerts: DebugSosAlert[];
  position_stats: {
    last_hour_total: number;
    last_hour_cellular: number;
    last_hour_mesh: number;
  };
};

export type BuddyGroupMember = {
  pilot_id: number;
  first_name: string;
  last_name: string;
  nation: string | null;
  competition_number: string | null;
};
export type BuddyGroup = {
  id: number;
  name: string;
  visibility: "public" | "users" | "buddies" | "private";
  members: BuddyGroupMember[];
  created_at: string;
};
export type PilotSearchResult = {
  pilot_id: number;
  first_name: string;
  last_name: string;
  nation: string | null;
  competition_number: string | null;
  email: string | null;
};

export type UserEmailRecord = {
  id: number;
  email: string;
  created_at: string;
};
export type PilotClaimSearchResultRecord = {
  pilot_id: number;
  first_name: string;
  last_name: string;
  nation: string | null;
  competition_number: string | null;
  civl_id: string | null;
  can_instant_claim: boolean;
};
export type PilotClaimResponseRecord = {
  success: boolean;
  pilot_id: number;
  message: string;
};

export { type MapAirspaceRegion, type MapTurnpoint, type TrackCollection };
