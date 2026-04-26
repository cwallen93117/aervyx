from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Double, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(20), index=True)
    profile_type: Mapped[str] = mapped_column(String(20), default="pilot")
    altitude_unit: Mapped[str] = mapped_column(String(10), default="ft")
    speed_unit: Mapped[str] = mapped_column(String(10), default="kph")
    distance_unit: Mapped[str] = mapped_column(String(10), default="km")
    vario_unit: Mapped[str] = mapped_column(String(10), default="fpm")
    aircraft_icon: Mapped[str] = mapped_column(String(20), default="hang_glider")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    oauth_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    oauth_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pilot_id: Mapped[int | None] = mapped_column(ForeignKey("pilots.id", ondelete="SET NULL"), nullable=True)
    mesh_device_id: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserEmail(Base):
    __tablename__ = "user_emails"
    __table_args__ = (UniqueConstraint("email", name="uq_user_emails_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MeshDevice(Base):
    __tablename__ = "mesh_devices"
    __table_args__ = (
        UniqueConstraint("device_id", name="uq_mesh_devices_device_id"),
        Index("ix_mesh_devices_owner_user_id", "owner_user_id"),
        Index("ix_mesh_devices_purpose", "purpose"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    device_id: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), default="tracking")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SiteSettings(Base):
    __tablename__ = "site_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    telemetry_vario_smoothing_seconds: Mapped[int] = mapped_column(Integer, default=5)
    telemetry_altitude_smoothing_seconds: Mapped[int] = mapped_column(Integer, default=3)
    telemetry_speed_smoothing_seconds: Mapped[int] = mapped_column(Integer, default=3)
    telemetry_glide_ratio_smoothing_seconds: Mapped[int] = mapped_column(Integer, default=5)
    max_map_pitch_degrees: Mapped[int] = mapped_column(Integer, default=75)
    site_match_radius_m: Mapped[int] = mapped_column(Integer, default=1000)
    # MQTT broker settings
    mqtt_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    mqtt_broker_mode: Mapped[str] = mapped_column(String(20), default="public")
    mqtt_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mqtt_port: Mapped[int] = mapped_column(Integer, default=1883)
    mqtt_topic_prefix: Mapped[str] = mapped_column(String(80), default="msh")
    mqtt_channel_psk: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Meshtastic device profiles (JSON blob)
    mesh_profiles: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MapOverlayConfig(Base):
    __tablename__ = "map_overlay_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    config: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


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
    day_quality_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_points_if_not_in_goal: Mapped[float | None] = mapped_column(Float, nullable=True)
    jump_the_gun_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    jump_the_gun_max_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stopped_glide_bonus: Mapped[float | None] = mapped_column(Float, nullable=True)
    use_1000_points_for_max_day_quality: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    normalize_1000_before_day_quality: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    use_distance_points: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    use_time_points: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    use_leading_points: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    use_arrival_position_points: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    use_arrival_time_points: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    use_departure_points: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    use_difficulty_for_distance_points: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    use_distance_squared_for_lc: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    use_semi_circle_control_zone_for_goal_line: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    use_proportional_leading_weight_if_nobody_in_goal: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    redistribute_removed_time_points_as_distance_points: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    use_best_score_for_ftv_validity: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    use_constant_leading_weight: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    use_pwca2019_for_lc: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    use_flat_decline_of_timepoints: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    scoring_altitude: Mapped[str | None] = mapped_column(String(20), nullable=True)
    final_glide_decelerator: Mapped[str | None] = mapped_column(String(40), nullable=True)
    no_final_glide_decelerator_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    min_time_span_for_valid_task_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    leading_weight_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    turnpoint_radius_tolerance: Mapped[float | None] = mapped_column(Float, nullable=True)
    turnpoint_radius_minimum_absolute_tolerance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    number_of_decimals_task_results: Mapped[int | None] = mapped_column(Integer, nullable=True)
    number_of_decimals_competition_results: Mapped[int | None] = mapped_column(Integer, nullable=True)
    visible_airspace_classes_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    show_restricted_fields: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    penalties_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_public_tracking: Mapped[bool] = mapped_column(Boolean, default=False)
    visibility: Mapped[str] = mapped_column(String(20), default="private")
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


class FlightSite(Base):
    __tablename__ = "flight_sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    city_state: Mapped[str] = mapped_column(String(160), default="")
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    flight_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


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
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
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


class AirspaceSource(Base):
    __tablename__ = "airspace_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_format: Mapped[str] = mapped_column(String(20))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    stored_path: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AirspaceRegion(Base):
    __tablename__ = "airspace_regions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("airspace_sources.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    class_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    type_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    display_category: Mapped[str] = mapped_column(String(40), index=True)
    lower_limit_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    upper_limit_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lower_limit_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    upper_limit_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    geometry_json: Mapped[dict] = mapped_column(JSON, default=dict)
    label_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    label_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_restricted_field: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_event_status", "event_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    task_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
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


class PilotFlight(Base):
    __tablename__ = "pilot_flights"
    __table_args__ = (
        UniqueConstraint("igc_upload_id", name="uq_pilot_flight_igc_upload"),
        Index("ix_pilot_flights_pilot_date", "pilot_id", "flight_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pilot_id: Mapped[int] = mapped_column(ForeignKey("pilots.id", ondelete="CASCADE"), index=True)
    source_kind: Mapped[str] = mapped_column(String(20), index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("flight_sites.id", ondelete="SET NULL"), nullable=True, index=True)
    igc_upload_id: Mapped[int | None] = mapped_column(ForeignKey("igc_uploads.id", ondelete="SET NULL"), nullable=True, index=True)
    flight_date: Mapped[date] = mapped_column(Date, index=True)
    starred: Mapped[bool] = mapped_column(Boolean, default=False)
    site_name: Mapped[str] = mapped_column(String(160), default="")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    highest_altitude_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_climb_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    stored_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PilotFlightTrackPoint(Base):
    __tablename__ = "pilot_flight_track_points"
    __table_args__ = (
        Index("ix_pilot_flight_track_points_flight_seq", "flight_id", "sequence"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flight_id: Mapped[int] = mapped_column(ForeignKey("pilot_flights.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    pressure_altitude_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gps_altitude_m: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TaskScoringInput(Base):
    __tablename__ = "task_scoring_inputs"
    __table_args__ = (
        UniqueConstraint("task_id", "pilot_id", name="uq_task_scoring_input_task_pilot"),
        Index("ix_task_scoring_input_task_pilot", "task_id", "pilot_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    pilot_id: Mapped[int] = mapped_column(ForeignKey("pilots.id", ondelete="CASCADE"), index=True)
    selected_upload_id: Mapped[int | None] = mapped_column(ForeignKey("igc_uploads.id", ondelete="SET NULL"), nullable=True)
    status_override: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ScorePenalty(Base):
    __tablename__ = "score_penalties"
    __table_args__ = (
        Index("ix_score_penalties_task_pilot", "task_id", "pilot_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    pilot_id: Mapped[int] = mapped_column(ForeignKey("pilots.id", ondelete="CASCADE"), index=True)
    penalty_type: Mapped[str] = mapped_column(String(20))
    value: Mapped[float] = mapped_column(Float, default=0)
    reason: Mapped[str] = mapped_column(String(255), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    applied_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TrackPoint(Base):
    __tablename__ = "track_points"
    __table_args__ = (
        Index("ix_track_points_upload_seq", "upload_id", "sequence"),
    )

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
    __table_args__ = (
        UniqueConstraint("task_id", "pilot_id", name="uq_score_task_pilot"),
        Index("ix_score_results_task_pilot", "task_id", "pilot_id"),
        Index("ix_score_results_task_rank", "task_id", "rank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    pilot_id: Mapped[int] = mapped_column(ForeignKey("pilots.id", ondelete="CASCADE"), index=True)
    upload_id: Mapped[int | None] = mapped_column(ForeignKey("igc_uploads.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="uploaded")
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_flown_km: Mapped[float] = mapped_column(Float, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ess_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    goal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    elapsed_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_score_points: Mapped[float] = mapped_column(Float, default=0)
    score_points: Mapped[float] = mapped_column(Float, default=0)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    result_state: Mapped[str] = mapped_column(String(20), default="official", index=True)
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


class BuddyGroup(Base):
    __tablename__ = "buddy_groups"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_buddy_group_user_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    visibility: Mapped[str] = mapped_column(String(20), default="private")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BuddyGroupMember(Base):
    __tablename__ = "buddy_group_members"
    __table_args__ = (UniqueConstraint("group_id", "pilot_id", name="uq_buddy_member_group_pilot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("buddy_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    pilot_id: Mapped[int] = mapped_column(ForeignKey("pilots.id", ondelete="CASCADE"), nullable=False, index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LivePosition(Base):
    __tablename__ = "live_positions"
    __table_args__ = (
        Index("ix_live_positions_task_ts", "task_id", "timestamp"),
        Index("ix_live_positions_task_pilot_ts", "task_id", "pilot_id", "timestamp"),
        Index("ix_live_positions_pilot_ts", "pilot_id", "timestamp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pilot_id: Mapped[int | None] = mapped_column(ForeignKey("pilots.id", ondelete="SET NULL"), nullable=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    lat: Mapped[float] = mapped_column(Double, nullable=False)
    lon: Mapped[float] = mapped_column(Double, nullable=False)
    alt: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    battery_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrackingSession(Base):
    __tablename__ = "tracking_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pilot_id: Mapped[int | None] = mapped_column(ForeignKey("pilots.id", ondelete="SET NULL"), nullable=True, index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    position_count: Mapped[int] = mapped_column(Integer, default=0)


class SosAlert(Base):
    __tablename__ = "sos_alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pilot_id: Mapped[int | None] = mapped_column(ForeignKey("pilots.id", ondelete="SET NULL"), nullable=True, index=True)
    lat: Mapped[float] = mapped_column(Double, nullable=False)
    lon: Mapped[float] = mapped_column(Double, nullable=False)
    alt: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class DriverAssignment(Base):
    __tablename__ = "driver_assignments"
    __table_args__ = (
        UniqueConstraint("task_id", "driver_user_id", "pilot_id", name="uq_driver_assignment"),
        Index("ix_driver_assignments_task_driver", "task_id", "driver_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    driver_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    pilot_id: Mapped[int] = mapped_column(ForeignKey("pilots.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PilotLanding(Base):
    __tablename__ = "pilot_landings"
    __table_args__ = (
        Index("ix_pilot_landings_task_pilot", "task_id", "pilot_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    pilot_id: Mapped[int] = mapped_column(ForeignKey("pilots.id", ondelete="CASCADE"), index=True)
    landed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ready_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lat: Mapped[float] = mapped_column(Double, nullable=False)
    lon: Mapped[float] = mapped_column(Double, nullable=False)
    alt: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="landed")
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    picked_up_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DriverPosition(Base):
    __tablename__ = "driver_positions"
    __table_args__ = (
        Index("ix_driver_positions_user_ts", "driver_user_id", "timestamp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    driver_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    lat: Mapped[float] = mapped_column(Double, nullable=False)
    lon: Mapped[float] = mapped_column(Double, nullable=False)
    heading: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# FAA Airspace cache
# ---------------------------------------------------------------------------

class FaaAirspaceFeature(Base):
    __tablename__ = "faa_airspace_features"
    __table_args__ = (
        Index("ix_faa_airspace_bbox", "min_lon", "min_lat", "max_lon", "max_lat"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    ident: Mapped[str | None] = mapped_column(String(40), nullable=True)
    upper_val: Mapped[float | None] = mapped_column(Float, nullable=True)
    upper_uom: Mapped[str] = mapped_column(String(10), default="FT")
    lower_val: Mapped[float | None] = mapped_column(Float, nullable=True)
    lower_uom: Mapped[str] = mapped_column(String(10), default="FT")
    upper_desc: Mapped[str] = mapped_column(String(100), default="")
    lower_desc: Mapped[str] = mapped_column(String(100), default="")
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(10), nullable=True)
    min_lat: Mapped[float] = mapped_column(Float, nullable=False)
    max_lat: Mapped[float] = mapped_column(Float, nullable=False)
    min_lon: Mapped[float] = mapped_column(Float, nullable=False)
    max_lon: Mapped[float] = mapped_column(Float, nullable=False)
    geometry_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FaaAirspaceMeta(Base):
    __tablename__ = "faa_airspace_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    last_edit_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
