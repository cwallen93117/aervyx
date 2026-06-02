from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


def default_task_point_direction(point_type: str | None) -> str:
    return "exit" if (point_type or "").lower() == "start" else "enter"


def default_task_point_radius_m(point_type: str | None) -> float:
    point_type = (point_type or "").lower()
    if point_type == "start":
        return 5000.0
    if point_type == "turnpoint":
        return 1000.0
    if point_type == "goal":
        return 400.0
    return 400.0


class GoogleAuthRequest(BaseModel):
    credential: str


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    password: str
    account_role: str = "pilot"
    competition_number: str | None = None
    nation: str | None = None
    civl_id: str | None = None


class UserSummary(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    profile_type: str
    profile_type_updated_at: datetime
    altitude_unit: str = "ft"
    speed_unit: str = "kph"
    distance_unit: str = "km"
    vario_unit: str = "fpm"
    pilot_id: int | None

    model_config = ConfigDict(from_attributes=True)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user: UserSummary


class AccountSettingsResponse(BaseModel):
    username: str
    full_name: str
    role: str
    profile_type: str
    profile_type_updated_at: datetime
    altitude_unit: str = "ft"
    speed_unit: str = "kph"
    distance_unit: str = "km"
    vario_unit: str = "fpm"
    aircraft_icon: str = "hang_glider"
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    nation: str | None = None
    competition_number: str | None = None
    civl_id: str | None = None
    pilot_id: int | None = None
    has_password: bool = False


class AccountSettingsUpdateResponse(AccountSettingsResponse):
    access_token: str | None = None


class AccountSettingsUpdate(BaseModel):
    username: str
    full_name: str
    profile_type: str = "pilot"
    role: str | None = None
    altitude_unit: str = "ft"
    speed_unit: str = "kph"
    distance_unit: str = "km"
    vario_unit: str = "fpm"
    aircraft_icon: str = "hang_glider"
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    nation: str | None = None
    competition_number: str | None = None
    civl_id: str | None = None


class AccountPreferencesUpdate(BaseModel):
    profile_type: str | None = None
    profile_type_updated_at: datetime | None = None
    altitude_unit: str | None = None
    speed_unit: str | None = None
    distance_unit: str | None = None
    vario_unit: str | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str = ""
    new_password: str


class UserEmailResponse(BaseModel):
    id: int
    email: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class UserEmailCreate(BaseModel):
    email: str


class PilotClaimSearchResult(BaseModel):
    pilot_id: int
    first_name: str
    last_name: str
    nation: str | None = None
    competition_number: str | None = None
    civl_id: str | None = None
    can_instant_claim: bool = False


class PilotClaimRequest(BaseModel):
    pilot_id: int
    competition_number: str | None = None
    civl_id: str | None = None


class PilotClaimResponse(BaseModel):
    success: bool
    pilot_id: int
    message: str


class AdminUserResponse(BaseModel):
    id: int
    username: str
    full_name: str
    first_name: str | None = None
    last_name: str | None = None
    role: str
    profile_type: str
    profile_type_updated_at: datetime
    pilot_id: int | None
    email: str | None = None
    pilot_name: str | None = None
    competition_number: str | None = None
    mesh_device_id: str | None = None
    mesh_devices: list[MeshDeviceResponse] = Field(default_factory=list)
    is_active: bool
    created_at: datetime


class AdminUserUpdate(BaseModel):
    role: str
    profile_type: str
    is_active: bool = True


class AdminUserCredentialsUpdate(BaseModel):
    username: str | None = None
    password: str | None = None


class MeshDeviceRegister(BaseModel):
    mesh_device_id: str | None = None


class MeshDeviceCreate(BaseModel):
    device_id: str
    label: str | None = None
    purpose: str = "tracking"


class MeshDeviceUpdate(BaseModel):
    device_id: str | None = None
    label: str | None = None
    purpose: str | None = None


class MeshDeviceResponse(BaseModel):
    id: int
    owner_user_id: int
    owner_name: str | None = None
    device_id: str
    label: str
    purpose: str
    is_pilot_tracker: bool = False
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MapOverlayConfigResponse(BaseModel):
    config: dict
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MapOverlayConfigUpdate(BaseModel):
    config: dict


class SiteSettingsResponse(BaseModel):
    telemetry_vario_smoothing_seconds: int = Field(default=5, ge=0, le=30)
    telemetry_altitude_smoothing_seconds: int = Field(default=3, ge=0, le=30)
    telemetry_speed_smoothing_seconds: int = Field(default=3, ge=0, le=30)
    telemetry_glide_ratio_smoothing_seconds: int = Field(default=5, ge=0, le=30)
    max_map_pitch_degrees: int = Field(default=75, ge=0, le=85)
    site_match_radius_m: int = Field(default=1000, ge=1, le=50000)
    mqtt_enabled: bool = True
    mqtt_broker_mode: str = "local_mosquitto"
    mqtt_host: str | None = None
    mqtt_port: int = 1883
    mqtt_tls_enabled: bool = False
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_topic_prefix: str = "msh"
    mqtt_channel_psk: str | None = None
    cloudflare_ddns_enabled: bool = False
    cloudflare_ddns_zone_id: str | None = None
    cloudflare_ddns_api_token_configured: bool = False
    cloudflare_ddns_record_names: list[str] = Field(default_factory=lambda: ["mqtt.aervyx.net", "mqtt-staging.aervyx.net"])
    cloudflare_ddns_check_interval_hours: int = Field(default=12, ge=1, le=168)
    cloudflare_ddns_last_checked_at: datetime | None = None
    cloudflare_ddns_last_public_ip: str | None = None
    cloudflare_ddns_last_update_result: str | None = None
    cloudflare_ddns_last_error: str | None = None
    mesh_profiles: dict | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SiteSettingsUpdate(BaseModel):
    telemetry_vario_smoothing_seconds: int = Field(default=5, ge=0, le=30)
    telemetry_altitude_smoothing_seconds: int = Field(default=3, ge=0, le=30)
    telemetry_speed_smoothing_seconds: int = Field(default=3, ge=0, le=30)
    telemetry_glide_ratio_smoothing_seconds: int = Field(default=5, ge=0, le=30)
    max_map_pitch_degrees: int = Field(default=75, ge=0, le=85)
    site_match_radius_m: int = Field(default=1000, ge=1, le=50000)
    mqtt_enabled: bool = True
    mqtt_broker_mode: str = "local_mosquitto"
    mqtt_host: str | None = None
    mqtt_port: int = 1883
    mqtt_tls_enabled: bool = False
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_topic_prefix: str = "msh"
    mqtt_channel_psk: str | None = None
    cloudflare_ddns_enabled: bool = False
    cloudflare_ddns_zone_id: str | None = None
    cloudflare_ddns_api_token: str | None = None
    cloudflare_ddns_clear_api_token: bool = False
    cloudflare_ddns_record_names: list[str] = Field(default_factory=lambda: ["mqtt.aervyx.net", "mqtt-staging.aervyx.net"])
    cloudflare_ddns_check_interval_hours: int = Field(default=12, ge=1, le=168)
    mesh_profiles: dict | None = None


class IntegrationCredentialsResponse(BaseModel):
    provider: str
    enabled: bool = False
    base_url: str = "https://api.faa.gov"
    client_id_header: str = "client_id"
    client_secret_header: str = "client_secret"
    client_id_configured: bool = False
    client_secret_configured: bool = False
    admin_client_id_configured: bool = False
    admin_client_secret_configured: bool = False
    credential_source: str = "none"
    env_override: bool = False
    last_tested_at: datetime | None = None
    last_test_status: str | None = None
    last_test_message: str | None = None
    updated_by_user_id: int | None = None
    updated_at: datetime | None = None


class IntegrationCredentialsUpdate(BaseModel):
    enabled: bool = False
    base_url: str = Field(default="https://api.faa.gov", min_length=1, max_length=255)
    client_id_header: str = Field(default="client_id", min_length=1, max_length=80)
    client_secret_header: str = Field(default="client_secret", min_length=1, max_length=80)
    client_id: str | None = None
    client_secret: str | None = None
    clear_credentials: bool = False


class FlightSiteCreate(BaseModel):
    name: str
    city_state: str = ""
    latitude: float
    longitude: float
    is_active: bool = True


class FlightSiteUpdate(BaseModel):
    name: str
    city_state: str = ""
    latitude: float
    longitude: float
    is_active: bool = True


class FlightSiteResponse(BaseModel):
    id: int
    name: str
    city_state: str
    latitude: float
    longitude: float
    is_active: bool
    flight_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FlightSiteRescanResponse(BaseModel):
    scanned_count: int = 0
    matched_count: int = 0
    unmatched_count: int = 0


class FlightSiteScanIgcResponse(BaseModel):
    new_sites_created: int = 0
    flights_matched: int = 0
    total_igc_scanned: int = 0
    sites: list[FlightSiteResponse] = []


class EventCreate(BaseModel):
    name: str
    location: str
    starts_on: date
    ends_on: date
    timezone: str = "UTC"
    scoring_formula: str = "GAP2021"
    nominal_distance_km: float = 60
    nominal_time_hours: float = 1.5
    nominal_launch: float = 0.95
    minimum_distance_km: float = 5
    nominal_goal_percent: float = 0.3
    score_back_time_minutes: int = 15
    goal_ss_penalty: float = 0.0
    day_quality_override: float = 0.0
    time_points_if_not_in_goal: float = 1.0
    jump_the_gun_factor: float = 0.0
    jump_the_gun_max_seconds: int = 0
    default_start_gate_count: int = Field(default=5, ge=1)
    default_start_gate_interval_seconds: int = Field(default=900, ge=0)
    stopped_glide_bonus: float = 0.0
    use_1000_points_for_max_day_quality: bool = False
    normalize_1000_before_day_quality: bool = False
    use_distance_points: bool = True
    use_time_points: bool = True
    use_leading_points: bool = True
    use_arrival_position_points: bool = False
    use_arrival_time_points: bool = False
    use_departure_points: bool = False
    use_difficulty_for_distance_points: bool = True
    use_distance_squared_for_lc: bool = False
    use_semi_circle_control_zone_for_goal_line: bool = True
    use_proportional_leading_weight_if_nobody_in_goal: bool = True
    redistribute_removed_time_points_as_distance_points: bool = False
    use_best_score_for_ftv_validity: bool = True
    use_constant_leading_weight: bool = False
    use_pwca2019_for_lc: bool = False
    use_flat_decline_of_timepoints: bool = False
    scoring_altitude: str = "GPS"
    final_glide_decelerator: str = "none"
    no_final_glide_decelerator_reason: str = ""
    min_time_span_for_valid_task_minutes: int = 60
    leading_weight_factor: float = 1.0
    turnpoint_radius_tolerance: float = 0.0005
    turnpoint_radius_minimum_absolute_tolerance_m: float = 5.0
    number_of_decimals_task_results: int = 2
    number_of_decimals_competition_results: int = 1
    visible_airspace_classes_json: list[str] = Field(default_factory=lambda: ["B", "C", "D", "P", "Q", "R", "TFR", "OTHER"])
    show_restricted_fields: bool = True
    penalties_json: dict = Field(default_factory=dict)
    is_public_tracking: bool = False
    visibility: str = "private"


class EventResponse(EventCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    pilot_count: int = 0
    task_count: int = 0
    turnpoint_count: int = 0
    airspace_count: int = 0
    restricted_field_count: int = 0


class PilotUpsert(BaseModel):
    first_name: str
    last_name: str
    email: str | None = None
    nation: str | None = None
    competition_number: str | None = None
    civl_id: str | None = None
    username: str | None = None
    password: str | None = None


class PilotResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str | None
    nation: str | None
    competition_number: str | None
    civl_id: str | None
    portal_username: str | None = None
    is_claimed: bool = False
    temp_password: str | None = None


class TurnpointResponse(BaseModel):
    id: int
    event_id: int
    source_id: int | None
    code: str | None
    symbol: str | None = None
    name: str
    latitude: float
    longitude: float
    elevation_m: float | None
    extra_json: dict | None = Field(default_factory=dict)
    source_row_index: int | None = None

    model_config = ConfigDict(from_attributes=True)


class TurnpointWrite(BaseModel):
    code: str | None = None
    symbol: str | None = None
    name: str
    latitude: float
    longitude: float
    elevation_m: float | None = None
    extra_json: dict = Field(default_factory=dict)


class TurnpointUploadResponse(BaseModel):
    source_id: int
    format: str
    imported_count: int
    sha256: str
    filename: str


class TurnpointSourceResponse(BaseModel):
    id: int
    event_id: int
    filename: str
    file_format: str
    sha256: str
    enabled: bool = True
    uploaded_at: datetime
    turnpoint_count: int = 0


class TurnpointSourceUpdate(BaseModel):
    enabled: bool | None = None
    filename: str | None = None


class TurnpointSourceSaveAs(BaseModel):
    filename: str


class AirspaceSourceResponse(BaseModel):
    id: int
    event_id: int
    kind: str
    filename: str
    file_format: str
    sha256: str
    enabled: bool = True
    uploaded_at: datetime
    region_count: int = 0


class AirspaceUploadResponse(BaseModel):
    source_id: int
    kind: str
    format: str
    imported_count: int
    sha256: str
    filename: str


class AirspaceSourceUpdate(BaseModel):
    enabled: bool | None = None
    kind: str | None = None


class AirspaceRegionResponse(BaseModel):
    id: int
    event_id: int
    source_id: int
    name: str
    class_code: str | None
    type_code: str | None
    display_category: str
    lower_limit_label: str | None
    upper_limit_label: str | None
    lower_limit_m: float | None
    upper_limit_m: float | None
    geometry_json: dict
    label_latitude: float | None
    label_longitude: float | None
    is_restricted_field: bool

    model_config = ConfigDict(from_attributes=True)


class TaskPointInput(BaseModel):
    position: int
    point_type: str
    direction: str | None = Field(default=None, pattern="^(enter|exit)$")
    radius_m: float | None = None
    turnpoint_id: int | None = None
    name: str
    latitude: float
    longitude: float

    @model_validator(mode="after")
    def apply_default_direction(self) -> "TaskPointInput":
        if self.direction not in {"enter", "exit"}:
            self.direction = default_task_point_direction(self.point_type)
        if self.radius_m is None or self.radius_m <= 0:
            self.radius_m = default_task_point_radius_m(self.point_type)
        return self


class TaskInput(BaseModel):
    name: str
    task_date: date | None = None
    is_practice: bool = False
    status: str = "draft"
    task_type: str = "race_to_goal_with_gates"
    task_start_time: str | None = None
    task_finish_time: str | None = None
    start_open_time: str | None = None
    start_close_time: str | None = None
    start_gate_count: int = Field(default=1, ge=1)
    start_gate_interval_seconds: int | None = Field(default=None, ge=0)
    points: list[TaskPointInput]


class TaskPointResponse(TaskPointInput):
    id: int


class TaskResponse(BaseModel):
    id: int
    event_id: int
    name: str
    task_date: date | None = None
    is_practice: bool = False
    status: str
    task_type: str
    task_start_time: str | None
    task_finish_time: str | None
    start_open_time: str | None
    start_close_time: str | None
    start_gate_count: int
    start_gate_interval_seconds: int | None
    version: int
    published_at: datetime | None
    points: list[TaskPointResponse]


class UploadResponse(BaseModel):
    id: int
    pilot_id: int
    task_id: int
    filename: str
    sha256: str
    uploaded_at: datetime
    upload_source: str = "manual"
    metadata_json: dict

    model_config = ConfigDict(from_attributes=True)


class BulkUploadItemResponse(BaseModel):
    filename: str
    matched: bool
    upload_id: int | None = None
    pilot_id: int | None = None
    pilot_name: str | None = None
    match_confidence: str | None = None
    message: str


class ScorePenaltyCalculationLine(BaseModel):
    kind: str
    label: str
    amount_points: float = 0
    running_score_points: float | None = None
    detail: str | None = None


class ScorePenaltyCalculation(BaseModel):
    raw_score_points: float = 0
    final_score_points: float = 0
    manual_penalty_points: float = 0
    engine_penalty_points: float = 0
    total_display_penalty_points: float = 0
    lines: list[ScorePenaltyCalculationLine] = Field(default_factory=list)


class ScoreResultResponse(BaseModel):
    id: int
    task_id: int
    pilot_id: int
    upload_id: int | None
    pilot_name: str
    competition_number: str | None
    status: str
    rank: int | None
    distance_flown_km: float
    started_at: datetime | None
    ess_at: datetime | None
    goal_at: datetime | None
    elapsed_seconds: int | None
    raw_score_points: float = 0
    score_points: float
    details_json: dict
    result_state: str = "official"
    penalties: list[ScorePenaltyEntry] = Field(default_factory=list)
    penalty_summary: str | None = None
    penalty_calculation: ScorePenaltyCalculation | None = None


class PilotSummaryResponse(BaseModel):
    pilot_id: int
    pilot_name: str
    competition_number: str | None
    total_score_points: float
    tasks_scored: int
    best_distance_km: float
    task_scores: dict[int, float] = Field(default_factory=dict)
    task_result_states: dict[int, str] = Field(default_factory=dict)
    task_statuses: dict[int, str] = Field(default_factory=dict)


class TaskResultSummaryResponse(BaseModel):
    task_id: int
    day_quality: float | None = None
    statistics: dict = Field(default_factory=dict)


class TaskScoringInputUpdate(BaseModel):
    selected_upload_id: int | None = None
    status_override: str | None = None


class ScorePenaltyEntry(BaseModel):
    id: int | None = None
    penalty_type: str = Field(pattern="^(percentage|fixed)$")
    value: float = Field(ge=0)
    reason: str = ""
    position: int = Field(default=0, ge=0)
    applied_by: str | None = None
    applied_at: datetime | None = None


class ScorePenaltySaveEntry(BaseModel):
    penalty_type: str = Field(pattern="^(percentage|fixed)$")
    value: float = Field(ge=0)
    reason: str = ""
    position: int = Field(default=0, ge=0)


class ScorePenaltySaveRequest(BaseModel):
    penalties: list[ScorePenaltySaveEntry] = Field(default_factory=list)


class PenaltyAuditEntry(BaseModel):
    actor_name: str
    timestamp: datetime
    summary: str


class ScoringPresetEntry(BaseModel):
    id: str
    label: str
    penalty_type: str = Field(pattern="^(percentage|fixed)$")
    value: float = Field(ge=0)
    reason: str


class ScoringPresetUpdate(BaseModel):
    presets: list[ScoringPresetEntry] = Field(default_factory=list)


class ScoringUploadOption(BaseModel):
    id: int
    filename: str
    upload_source: str
    label: str
    uploaded_at: datetime
    late_start: bool = False


class ScoringOperationsResultSummary(BaseModel):
    result_id: int
    upload_id: int | None = None
    status: str
    rank: int | None = None
    distance_flown_km: float = 0
    elapsed_seconds: int | None = None
    raw_score_points: float = 0
    score_points: float = 0
    result_state: str = "official"
    penalty_calculation: ScorePenaltyCalculation | None = None


class ScoringOperationsRow(BaseModel):
    pilot_id: int
    pilot_name: str
    competition_number: str | None = None
    selected_upload_id: int | None = None
    status_override: str | None = None
    uploads: list[ScoringUploadOption] = Field(default_factory=list)
    result: ScoringOperationsResultSummary | None = None
    penalties: list[ScorePenaltyEntry] = Field(default_factory=list)
    penalty_summary: str | None = None
    penalty_audit: list[PenaltyAuditEntry] = Field(default_factory=list)
    row_classification: str = "unscored"


class ScoringOperationsResponse(BaseModel):
    rows: list[ScoringOperationsRow] = Field(default_factory=list)


class ScoringLogbookCandidate(BaseModel):
    flight_id: int
    filename: str | None = None
    source_kind: str
    flight_date: date
    created_at: datetime
    event_name: str | None = None
    task_name: str | None = None
    duration_seconds: int | None = None
    highest_altitude_m: float | None = None
    best_climb_mps: float | None = None
    already_linked_upload_id: int | None = None


class ScoringLogbookSelectResponse(BaseModel):
    status: str = "ok"
    task_id: int
    pilot_id: int
    flight_id: int
    selected_upload_id: int


class LogbookFlightCreate(BaseModel):
    flight_date: date
    site_name: str = ""
    duration_seconds: int | None = Field(default=None, ge=0)
    highest_altitude_m: float | None = None
    best_climb_mps: float | None = None
    notes: str | None = None


class LogbookFlightUpdate(BaseModel):
    flight_date: date | None = None
    site_name: str | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    highest_altitude_m: float | None = None
    best_climb_mps: float | None = None
    notes: str | None = None
    starred: bool | None = None


class LogbookFlightStatsResponse(BaseModel):
    duration_seconds: int | None = None
    highest_altitude_m: float | None = None
    best_climb_mps: float | None = None
    launch_time: str | None = None
    landing_time: str | None = None
    launch_altitude_m: float | None = None
    landing_altitude_m: float | None = None
    time_in_thermals_seconds: int = 0
    time_on_glide_seconds: int = 0
    total_track_distance_km: float = 0
    max_ground_speed_kmh: float | None = None


class LogbookFlightSummaryResponse(BaseModel):
    id: int
    source_kind: str
    flight_date: date
    starred: bool = False
    site_id: int | None = None
    site_name: str
    site_city_state: str | None = None
    duration_seconds: int | None = None
    highest_altitude_m: float | None = None
    best_climb_mps: float | None = None
    event_name: str | None = None
    task_name: str | None = None
    filename: str | None = None
    can_download: bool = False
    can_replay: bool = False
    has_statistics: bool = False


class LogbookFlightDetailResponse(LogbookFlightSummaryResponse):
    notes: str | None = None
    stats: LogbookFlightStatsResponse


class LogbookFolderImportItemResponse(BaseModel):
    file_key: str
    sha256: str
    filename: str
    relative_path: str | None = None
    detected_pilot_name: str | None = None
    reason: str
    flight_id: int | None = None


class LogbookFolderImportResponse(BaseModel):
    imported: list[LogbookFolderImportItemResponse] = Field(default_factory=list)
    skipped: list[LogbookFolderImportItemResponse] = Field(default_factory=list)
    review_needed: list[LogbookFolderImportItemResponse] = Field(default_factory=list)


class LogbookBulkDeleteRequest(BaseModel):
    flight_ids: list[int] = Field(default_factory=list)


class LogbookBulkDeleteResponse(BaseModel):
    deleted_ids: list[int] = Field(default_factory=list)
    deleted_count: int = 0
