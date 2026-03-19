from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    password: str
    competition_number: str | None = None
    nation: str | None = None
    civl_id: str | None = None


class UserSummary(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    pilot_id: int | None

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserSummary


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
    penalties_json: dict = Field(default_factory=dict)


class EventResponse(EventCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    pilot_count: int = 0
    task_count: int = 0
    turnpoint_count: int = 0


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


class TurnpointSlotResponse(BaseModel):
    slot_number: int
    source_id: int | None = None
    filename: str | None = None
    file_format: str | None = None
    sha256: str | None = None
    uploaded_at: datetime | None = None
    turnpoint_count: int = 0


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
    metadata_json: dict

    model_config = ConfigDict(from_attributes=True)


class ScoreResultResponse(BaseModel):
    id: int
    task_id: int
    pilot_id: int
    upload_id: int
    pilot_name: str
    competition_number: str | None
    status: str
    rank: int | None
    distance_flown_km: float
    started_at: datetime | None
    ess_at: datetime | None
    goal_at: datetime | None
    elapsed_seconds: int | None
    score_points: float
    details_json: dict


class PilotSummaryResponse(BaseModel):
    pilot_id: int
    pilot_name: str
    competition_number: str | None
    total_score_points: float
    tasks_scored: int
    best_distance_km: float
