from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


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


class PasswordChangeRequest(BaseModel):
    current_password: str = ""
    new_password: str


class AdminUserResponse(BaseModel):
    id: int
    username: str
    full_name: str
    first_name: str | None = None
    last_name: str | None = None
    role: str
    profile_type: str
    pilot_id: int | None
    email: str | None = None
    pilot_name: str | None = None
    competition_number: str | None = None
    is_active: bool
    created_at: datetime


class AdminUserUpdate(BaseModel):
    role: str
    profile_type: str
    is_active: bool = True


class SiteSettingsResponse(BaseModel):
    telemetry_vario_smoothing_seconds: int = Field(default=5, ge=0, le=30)
    telemetry_altitude_smoothing_seconds: int = Field(default=3, ge=0, le=30)
    telemetry_speed_smoothing_seconds: int = Field(default=3, ge=0, le=30)
    telemetry_glide_ratio_smoothing_seconds: int = Field(default=5, ge=0, le=30)
    max_map_pitch_degrees: int = Field(default=75, ge=0, le=85)
    site_match_radius_m: int = Field(default=1000, ge=1, le=50000)
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SiteSettingsUpdate(BaseModel):
    telemetry_vario_smoothing_seconds: int = Field(default=5, ge=0, le=30)
    telemetry_altitude_smoothing_seconds: int = Field(default=3, ge=0, le=30)
    telemetry_speed_smoothing_seconds: int = Field(default=3, ge=0, le=30)
    telemetry_glide_ratio_smoothing_seconds: int = Field(default=5, ge=0, le=30)
    max_map_pitch_degrees: int = Field(default=75, ge=0, le=85)
    site_match_radius_m: int = Field(default=1000, ge=1, le=50000)


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
    temp_password: str | None = None


class TurnpointResponse(BaseModel):
    id: int
    event_id: int
    source_id: int | None
    code: str | None
    name: str
    latitude: float
    longitude: float
    elevation_m: float | None

    model_config = ConfigDict(from_attributes=True)


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
    enabled: bool


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
    radius_m: float = Field(default=400, gt=0)
    turnpoint_id: int | None = None
    name: str
    latitude: float
    longitude: float


class TaskInput(BaseModel):
    name: str
    task_date: date | None = None
    status: str = "draft"
    task_type: str = "race_to_goal"
    task_start_time: str | None = None
    task_finish_time: str | None = None
    start_open_time: str | None = None
    start_close_time: str | None = None
    start_gate_count: int = Field(default=1, ge=1)
    start_gate_interval_seconds: int | None = Field(default=None, ge=0)
    nominal_distance_km: float = 60
    nominal_time_hours: float = 1.5
    nominal_launch: float = 0.95
    minimum_distance_km: float = 5
    penalties_json: dict = Field(default_factory=dict)
    points: list[TaskPointInput]


class TaskPointResponse(TaskPointInput):
    id: int


class TaskResponse(BaseModel):
    id: int
    event_id: int
    name: str
    task_date: date | None = None
    status: str
    task_type: str
    task_start_time: str | None
    task_finish_time: str | None
    start_open_time: str | None
    start_close_time: str | None
    start_gate_count: int
    start_gate_interval_seconds: int | None
    version: int
    nominal_distance_km: float
    nominal_time_hours: float
    nominal_launch: float
    minimum_distance_km: float
    penalties_json: dict
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
    message: str


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


class PilotSummaryResponse(BaseModel):
    pilot_id: int
    pilot_name: str
    competition_number: str | None
    total_score_points: float
    tasks_scored: int
    best_distance_km: float
    task_scores: dict[int, float] = Field(default_factory=dict)
    task_result_states: dict[int, str] = Field(default_factory=dict)


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
