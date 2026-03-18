from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str
    password: str


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
    nominal_distance_km: float = 60
    nominal_time_hours: float = 1.5
    nominal_launch: float = 0.95
    minimum_distance_km: float = 5
    penalties_json: dict = Field(default_factory=dict)


class EventResponse(EventCreate):
    id: int
    created_at: datetime
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
