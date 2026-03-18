from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(20), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    pilot_id: Mapped[int | None] = mapped_column(ForeignKey("pilots.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    location: Mapped[str] = mapped_column(String(160))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    scoring_formula: Mapped[str | None] = mapped_column(String(40), nullable=True)
    nominal_distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    nominal_time_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    nominal_launch: Mapped[float | None] = mapped_column(Float, nullable=True)
    minimum_distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    nominal_goal_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_back_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goal_ss_penalty: Mapped[float | None] = mapped_column(Float, nullable=True)
    jump_the_gun_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    jump_the_gun_max_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stopped_glide_bonus: Mapped[float | None] = mapped_column(Float, nullable=True)
    use_distance_points: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    use_time_points: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    use_leading_points: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    use_arrival_position_points: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    use_arrival_time_points: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    use_departure_points: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    penalties_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Pilot(Base):
    __tablename__ = "pilots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    nation: Mapped[str | None] = mapped_column(String(3), nullable=True)
    competition_number: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    civl_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EventPilot(Base):
    __tablename__ = "event_pilots"
    __table_args__ = (UniqueConstraint("event_id", "pilot_id", name="uq_event_pilot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    pilot_id: Mapped[int] = mapped_column(ForeignKey("pilots.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TurnpointSource(Base):
    __tablename__ = "turnpoint_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_format: Mapped[str] = mapped_column(String(20))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    stored_path: Mapped[str] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EventTurnpointSlot(Base):
    __tablename__ = "event_turnpoint_slots"
    __table_args__ = (UniqueConstraint("event_id", "slot_number", name="uq_event_turnpoint_slot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    slot_number: Mapped[int] = mapped_column(Integer)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("turnpoint_sources.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Turnpoint(Base):
    __tablename__ = "turnpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("turnpoint_sources.id", ondelete="SET NULL"), nullable=True)
    code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    elevation_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    task_type: Mapped[str] = mapped_column(String(40), default="race_to_goal")
    task_start_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    task_finish_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    start_open_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    start_close_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    start_gate_count: Mapped[int] = mapped_column(Integer, default=1)
    start_gate_interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    nominal_distance_km: Mapped[float] = mapped_column(Float, default=60)
    nominal_time_hours: Mapped[float] = mapped_column(Float, default=1.5)
    nominal_launch: Mapped[float] = mapped_column(Float, default=0.95)
    minimum_distance_km: Mapped[float] = mapped_column(Float, default=5)
    penalties_json: Mapped[dict] = mapped_column(JSON, default=dict)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TaskPoint(Base):
    __tablename__ = "task_points"
    __table_args__ = (UniqueConstraint("task_id", "position", name="uq_task_point_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    point_type: Mapped[str] = mapped_column(String(20))
    radius_m: Mapped[float] = mapped_column(Float, default=400)
    turnpoint_id: Mapped[int | None] = mapped_column(ForeignKey("turnpoints.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)


class IGCUpload(Base):
    __tablename__ = "igc_uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    pilot_id: Mapped[int] = mapped_column(ForeignKey("pilots.id", ondelete="CASCADE"), index=True)
    uploaded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    stored_path: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrackPoint(Base):
    __tablename__ = "track_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("igc_uploads.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    pressure_altitude_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gps_altitude_m: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ScoreResult(Base):
    __tablename__ = "score_results"
    __table_args__ = (UniqueConstraint("task_id", "pilot_id", name="uq_score_task_pilot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    pilot_id: Mapped[int] = mapped_column(ForeignKey("pilots.id", ondelete="CASCADE"), index=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("igc_uploads.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="uploaded")
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_flown_km: Mapped[float] = mapped_column(Float, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ess_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    goal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    elapsed_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_points: Mapped[float] = mapped_column(Float, default=0)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(80), index=True)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
