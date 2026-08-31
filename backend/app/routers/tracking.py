from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_session
from app.deps import get_current_user, require_admin
from app.models import Event, EventPilot, IGCUpload, LivePosition, MeshDevice, MeshNodeStatus, Pilot, SiteSettings, SosAlert, Task, TaskPoint, TaskScoringInput, TrackPoint, User
from app.services.mesh_ids import normalize_mesh_device_id, resolve_mesh_device_display_names
from app.services.mqtt_config import clear_legacy_public_mqtt_values, normalize_mqtt_broker_mode
from app.services.tracking import (
    _iso_or_none,
    _payloads_for_positions,
    get_all_active_positions,
    get_live_positions,
    get_live_positions_for_pilots,
    get_position_history,
    get_position_history_for_pilots,
    mesh_purpose_to_profile_type,
    normalize_position_source,
    resolve_active_task_id,
    resolve_active_task_id_for_user,
    resolve_mesh_device_assignment,
    resolve_tracking_timezone_name,
    store_position,
    subject_key_for_position,
    subscribe,
    subscribe_pilots,
    unsubscribe,
    unsubscribe_pilots,
)

router = APIRouter(tags=["tracking"])

MESH_STATUS_LIVE_SECONDS = 10 * 60
MESH_STATUS_STALE_SECONDS = 6 * 60 * 60
MESH_GATEWAY_METADATA_TOLERANCE_SECONDS = 5 * 60
MESH_POSITION_SOURCES = {"mesh_relay", "mqtt_gateway"}
MISSING_MESH_DEVICE_ID_SENTINELS = {"unknown", "!unknown", "null", "none", "undefined"}


def _timestamp_value(value: datetime | None) -> float:
    if value is None:
        return 0
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


def _status_gateway_id_for_latest(
    node_status: MeshNodeStatus | None,
    *,
    latest_position_is_newer: bool,
    latest_position_ts: datetime | None,
    source: str | None,
    packet_type: str | None,
) -> str | None:
    if node_status is None or node_status.last_gateway_id is None:
        return None
    if not latest_position_is_newer:
        return node_status.last_gateway_id
    if latest_position_ts is None or node_status.last_seen_at is None:
        return None
    if source is not None and node_status.last_source is not None and source != node_status.last_source:
        return None
    if packet_type is not None and node_status.last_packet_type is not None and packet_type != node_status.last_packet_type:
        return None
    if (
        abs(_timestamp_value(latest_position_ts) - _timestamp_value(node_status.last_seen_at))
        <= MESH_GATEWAY_METADATA_TOLERANCE_SECONDS
    ):
        return node_status.last_gateway_id
    return None


def mesh_status_for_seen_at(now: datetime, value: datetime | None) -> str:
    if value is None:
        return "never_seen"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    age = (now - value).total_seconds()
    if age < MESH_STATUS_LIVE_SECONDS:
        return "live"
    if age < MESH_STATUS_STALE_SECONDS:
        return "stale"
    return "offline"
logger = logging.getLogger("aervyx.tracking")


def _upsert_mesh_position_status(
    session: Session,
    *,
    device_id: str | None,
    seen_at: datetime,
    source: str,
    gateway_id: str | None,
    battery_level: int | None = None,
) -> MeshNodeStatus | None:
    normalized_device_id = normalize_mesh_device_id(device_id)
    if normalized_device_id is None:
        return None
    normalized_gateway_id = normalize_mesh_device_id(gateway_id)
    status_row = session.scalar(
        select(MeshNodeStatus).where(MeshNodeStatus.device_id == normalized_device_id)
    )
    if status_row is None:
        status_row = MeshNodeStatus(
            device_id=normalized_device_id,
            last_seen_at=seen_at,
            packet_count=0,
        )
        session.add(status_row)
    status_row.last_seen_at = seen_at
    status_row.last_packet_type = "POSITION_APP"
    status_row.last_source = source
    status_row.last_gateway_id = normalized_gateway_id
    status_row.last_topic = "api:/api/track/position" if source == "mesh_relay" else status_row.last_topic
    status_row.packet_count = (status_row.packet_count or 0) + 1
    if battery_level is not None:
        status_row.battery_level = battery_level
        status_row.battery_level_seen_at = seen_at
    return status_row


def _normalize_required_mesh_position_device_id(device_id: str | None) -> str:
    normalized = normalize_mesh_device_id(device_id)
    if (
        normalized is None
        or normalized in MISSING_MESH_DEVICE_ID_SENTINELS
        or not normalized.replace("!", "").strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="device_id is required for mesh positions",
        )
    return normalized


# ---------------------------------------------------------------------------
# Request / response schemas (local to this router)
# ---------------------------------------------------------------------------

class PositionPayload(BaseModel):
    task_id: int | None = None
    lat: float
    lon: float
    alt: float | None = None
    speed: float | None = None
    heading: float | None = None
    accuracy: float | None = None
    timestamp: datetime | None = None
    source: str | None = None
    device_id: str | None = None
    mesh_seq_number: int | None = None
    battery_level: int | None = None
    battery_level_seen_at: datetime | None = None


class MeshRadioTelemetryPayload(BaseModel):
    device_id: str
    battery_level: int
    battery_level_seen_at: datetime


class MeshRadioTelemetryResponse(BaseModel):
    device_id: str
    battery_level: int
    battery_level_seen_at: str


class PositionResponse(BaseModel):
    id: str
    subject_key: str
    pilot_id: int | None
    user_id: int | None = None
    pilot_name: str | None = None
    task_id: int | None
    lat: float
    lon: float
    alt: float | None
    speed: float | None
    heading: float | None
    accuracy: float | None
    timestamp: str
    source: str | None
    device_id: str | None
    mesh_seq_number: int | None = None
    battery_level: int | None
    aircraft_icon: str = "hang_glider"
    profile_type: str = "pilot"
    position_source: str = "other"
    received_at: str | None = None


class MeshConfigResponse(BaseModel):
    channel_psk: str | None = None
    mqtt_host: str | None = None
    mqtt_port: int = 1883
    mqtt_tls_enabled: bool = False
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    topic_prefix: str = "aervyx"


class ActivePilotResponse(BaseModel):
    subject_key: str
    pilot_id: int | None = None
    user_id: int | None = None
    pilot_name: str | None = None
    task_id: int | None = None
    lat: float
    lon: float
    alt: float | None = None
    speed: float | None = None
    heading: float | None = None
    accuracy: float | None = None
    timestamp: str
    source: str | None = None
    battery_level: int | None = None
    aircraft_icon: str = "hang_glider"
    profile_type: str = "pilot"
    position_source: str = "other"


class MeshNodeResponse(BaseModel):
    device_id: str
    pilot_id: int | None = None
    pilot_name: str | None = None
    profile_type: str | None = None
    device_label: str | None = None
    device_purpose: str | None = None
    registered_owner_user_id: int | None = None
    registered_owner_name: str | None = None
    lat: float | None = None
    lon: float | None = None
    alt: float | None = None
    speed: float | None = None
    heading: float | None = None
    battery_level: int | None = None
    battery_level_seen_at: str | None = None
    timestamp: str
    source: str | None = None
    position_source: str = "other"
    mesh_status: str = "never_seen"
    last_packet_type: str | None = None
    last_gateway_id: str | None = None
    last_gateway_display_name: str | None = None
    last_topic: str | None = None
    packet_count: int = 0


class SosPayload(BaseModel):
    lat: float
    lon: float
    alt: float | None = None
    message: str | None = None
    timestamp: datetime | None = None


class SosResponse(BaseModel):
    id: str
    pilot_id: int | None
    lat: float
    lon: float
    alt: float | None
    message: str | None
    timestamp: str


class DriverSosAlertResponse(BaseModel):
    id: str
    pilot_id: int | None
    pilot_name: str | None
    lat: float
    lon: float
    alt: float | None
    message: str | None
    timestamp: str
    status: str


class ActiveTaskTurnpoint(BaseModel):
    id: str
    name: str
    type: str
    point_type: str
    lat: float
    lon: float
    radius: float
    radius_meters: float


class ActiveTaskResponse(BaseModel):
    task_id: int
    event_id: int
    task_name: str
    visible_airspace_classes: list[str]
    show_restricted_fields: bool
    turnpoints: list[ActiveTaskTurnpoint]


class FlightDetectionThresholds(BaseModel):
    altitude_gain_m: float
    speed_threshold_ms: float


class FlightDetectionConfigResponse(BaseModel):
    paraglider: FlightDetectionThresholds
    hang_glider: FlightDetectionThresholds
    glider: FlightDetectionThresholds
    landing_speed_ms: float
    landing_altitude_tolerance_m: float
    landing_confirm_seconds: int
    landing_countdown_seconds: int


class AssignedPilotResponse(BaseModel):
    pilot_id: int
    first_name: str
    last_name: str


class LiveBacktestPilotSummary(BaseModel):
    id: int
    pilot_name: str
    competition_number: str | None = None
    point_count: int = 0


class LiveBacktestTaskSummary(BaseModel):
    id: int
    event_id: int
    name: str
    status: str
    task_date: str | None = None
    pilots: list[LiveBacktestPilotSummary]


class LiveBacktestEventSummary(BaseModel):
    id: int
    name: str
    location: str
    starts_on: str
    ends_on: str
    timezone: str
    tasks: list[LiveBacktestTaskSummary]


class LiveBacktestSourcesResponse(BaseModel):
    events: list[LiveBacktestEventSummary]


class LiveBacktestTaskPointResponse(BaseModel):
    position: int
    name: str
    point_type: str
    radius_m: float
    latitude: float
    longitude: float


class LiveBacktestPositionResponse(PositionResponse):
    created_at: str | None = None
    battery_level_seen_at: str | None = None
    raw_metadata: dict[str, str | None] = Field(default_factory=dict)


class LiveBacktestTrackResponse(BaseModel):
    event: LiveBacktestEventSummary
    task: LiveBacktestTaskSummary
    pilot: LiveBacktestPilotSummary
    task_points: list[LiveBacktestTaskPointResponse]
    raw_points: list[LiveBacktestPositionResponse]


class RawPositionHistoryPoint(BaseModel):
    id: str
    timestamp: str
    alt: float | None
    lat: float
    lon: float
    source: str | None
    device_id: str | None
    point_type: str
    path: str
    vario_mps: float | None


class RawPositionHistoryResponse(BaseModel):
    points: list[RawPositionHistoryPoint]
    next_cursor: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _pilot_display_name(pilot: Pilot) -> str:
    return f"{pilot.first_name or ''} {pilot.last_name or ''}".strip() or f"Pilot {pilot.id}"


def _live_backtest_user_ids_for_pilot(session: Session, pilot_id: int) -> list[int]:
    return list(
        session.scalars(
            select(User.id)
            .where(User.pilot_id == pilot_id, User.is_active.is_(True))
            .order_by(User.id.asc())
        ).all()
    )


def _raw_position_history_cursor(value: str | None) -> tuple[datetime, uuid.UUID] | None:
    if not value:
        return None
    try:
        timestamp_text, row_id = value.split("|", maxsplit=1)
        timestamp = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return timestamp.astimezone(UTC), uuid.UUID(row_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid history cursor")


def _raw_position_history_timestamp(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _raw_position_path(source: str | None) -> tuple[str, str]:
    if source == "app":
        return "app", "App"
    if source == "mesh_relay":
        return "mesh", "Mesh relay"
    if source == "mqtt_gateway":
        return "mesh", "MQTT gateway"
    return "mesh" if source in MESH_POSITION_SOURCES else "app", source or "App"


def _raw_position_vario_mps(previous: LivePosition | None, current: LivePosition) -> float | None:
    if previous is None or previous.alt is None or current.alt is None:
        return None
    elapsed = (current.timestamp - previous.timestamp).total_seconds()
    if elapsed <= 0:
        return None
    return (current.alt - previous.alt) / elapsed


def _live_backtest_task_day_window_utc(task: Task, event: Event) -> tuple[datetime, datetime] | None:
    if task.task_date is None:
        return None
    zone = ZoneInfo(resolve_tracking_timezone_name(event.timezone))
    local_start = datetime.combine(task.task_date, time.min, tzinfo=zone)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(UTC), local_end.astimezone(UTC)


def _live_backtest_task_scope_clause(task: Task, event: Event):
    conditions = [LivePosition.task_id == task.id]
    task_day_window = _live_backtest_task_day_window_utc(task, event)
    if task_day_window is not None:
        start_utc, end_utc = task_day_window
        conditions.append(
            and_(
                LivePosition.task_id.is_(None),
                LivePosition.timestamp >= start_utc,
                LivePosition.timestamp < end_utc,
            )
        )
    return or_(*conditions)


def _live_backtest_pilot_summaries(session: Session, task: Task, event: Event) -> list[LiveBacktestPilotSummary]:
    task_scope = _live_backtest_task_scope_clause(task, event)
    point_counts = {
        int(pilot_id): int(count)
        for pilot_id, count in session.execute(
            select(LivePosition.pilot_id, func.count(LivePosition.id))
            .where(task_scope, LivePosition.pilot_id.is_not(None))
            .group_by(LivePosition.pilot_id)
        ).all()
        if pilot_id is not None
    }
    pilot_ids = set(point_counts)
    event_pilot_ids = set(session.scalars(select(EventPilot.pilot_id).where(EventPilot.event_id == event.id)).all())
    pilot_ids.update(event_pilot_ids)
    if event_pilot_ids:
        linked_users = session.execute(
            select(User.id, User.pilot_id).where(
                User.pilot_id.in_(sorted(event_pilot_ids)),
                User.is_active.is_(True),
            )
        ).all()
        pilot_id_by_user_id = {int(user_id): int(user_pilot_id) for user_id, user_pilot_id in linked_users if user_pilot_id is not None}
        if pilot_id_by_user_id:
            user_counts = session.execute(
                select(LivePosition.user_id, func.count(LivePosition.id))
                .where(
                    task_scope,
                    LivePosition.pilot_id.is_(None),
                    LivePosition.user_id.in_(sorted(pilot_id_by_user_id)),
                )
                .group_by(LivePosition.user_id)
            ).all()
            for user_id, count in user_counts:
                mapped_pilot_id = pilot_id_by_user_id.get(int(user_id))
                if mapped_pilot_id is not None:
                    point_counts[mapped_pilot_id] = point_counts.get(mapped_pilot_id, 0) + int(count)
                    pilot_ids.add(mapped_pilot_id)
    if not pilot_ids:
        return []
    pilots = session.scalars(
        select(Pilot)
        .where(Pilot.id.in_(sorted(pilot_ids)))
        .order_by(Pilot.last_name.asc(), Pilot.first_name.asc(), Pilot.id.asc())
    ).all()
    return [
        LiveBacktestPilotSummary(
            id=pilot.id,
            pilot_name=_pilot_display_name(pilot),
            competition_number=pilot.competition_number,
            point_count=point_counts.get(pilot.id, 0),
        )
        for pilot in pilots
    ]


def _live_backtest_task_summary(session: Session, task: Task) -> LiveBacktestTaskSummary:
    event = session.get(Event, task.event_id)
    if event is None:
        pilots: list[LiveBacktestPilotSummary] = []
    else:
        pilots = _live_backtest_pilot_summaries(session, task, event)
    return LiveBacktestTaskSummary(
        id=task.id,
        event_id=task.event_id,
        name=task.name,
        status=task.status,
        task_date=task.task_date.isoformat() if task.task_date else None,
        pilots=pilots,
    )


def _live_backtest_event_summary(session: Session, event: Event) -> LiveBacktestEventSummary:
    tasks = session.scalars(
        select(Task)
        .where(Task.event_id == event.id)
        .order_by(Task.task_date.is_(None).asc(), Task.task_date.asc(), Task.id.asc())
    ).all()
    return LiveBacktestEventSummary(
        id=event.id,
        name=event.name,
        location=event.location,
        starts_on=event.starts_on.isoformat(),
        ends_on=event.ends_on.isoformat(),
        timezone=event.timezone,
        tasks=[_live_backtest_task_summary(session, task) for task in tasks],
    )


@router.get("/api/admin/live-backtest/sources", response_model=LiveBacktestSourcesResponse)
def admin_live_backtest_sources(
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> LiveBacktestSourcesResponse:
    events = session.scalars(
        select(Event).order_by(Event.starts_on.desc(), Event.ends_on.desc(), Event.name.asc())
    ).all()
    return LiveBacktestSourcesResponse(events=[_live_backtest_event_summary(session, event) for event in events])


@router.get("/api/admin/live-backtest/track", response_model=LiveBacktestTrackResponse)
def admin_live_backtest_track(
    task_id: int = Query(..., ge=1),
    pilot_id: int = Query(..., ge=1),
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> LiveBacktestTrackResponse:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    event = session.get(Event, task.event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    pilot = session.get(Pilot, pilot_id)
    if pilot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pilot not found")

    user_ids = _live_backtest_user_ids_for_pilot(session, pilot_id)
    subject_conditions = [LivePosition.pilot_id == pilot_id]
    if user_ids:
        subject_conditions.append(
            (LivePosition.pilot_id.is_(None)) & (LivePosition.user_id.in_(user_ids))
        )
    rows = session.scalars(
        select(LivePosition)
        .where(_live_backtest_task_scope_clause(task, event), or_(*subject_conditions))
        .order_by(LivePosition.timestamp.asc(), LivePosition.created_at.asc(), LivePosition.id.asc())
    ).all()
    payloads = _payloads_for_positions(session, rows)
    raw_points = [
        LiveBacktestPositionResponse(
            **payload,
            created_at=_iso_or_none(row.created_at),
            battery_level_seen_at=_iso_or_none(row.battery_level_seen_at),
            raw_metadata={
                "created_at": _iso_or_none(row.created_at),
                "battery_level_seen_at": _iso_or_none(row.battery_level_seen_at),
                "live_position_id": str(row.id),
            },
        )
        for row, payload in zip(rows, payloads, strict=True)
    ]
    task_points = session.scalars(
        select(TaskPoint).where(TaskPoint.task_id == task_id).order_by(TaskPoint.position.asc())
    ).all()

    task_summary = _live_backtest_task_summary(session, task)
    pilot_summary = next(
        (candidate for candidate in task_summary.pilots if candidate.id == pilot.id),
        LiveBacktestPilotSummary(
            id=pilot.id,
            pilot_name=_pilot_display_name(pilot),
            competition_number=pilot.competition_number,
            point_count=len(raw_points),
        ),
    )
    return LiveBacktestTrackResponse(
        event=_live_backtest_event_summary(session, event),
        task=task_summary,
        pilot=pilot_summary,
        task_points=[
            LiveBacktestTaskPointResponse(
                position=point.position,
                name=point.name,
                point_type=point.point_type,
                radius_m=point.radius_m,
                latitude=point.latitude,
                longitude=point.longitude,
            )
            for point in task_points
        ],
        raw_points=raw_points,
    )


@router.get("/api/admin/live-history/{pilot_id}", response_model=RawPositionHistoryResponse)
def admin_raw_position_history(
    pilot_id: int,
    limit: int = Query(default=500, ge=1, le=2000),
    cursor: str | None = Query(default=None),
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> RawPositionHistoryResponse:
    if session.get(Pilot, pilot_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pilot not found")

    # Include app rows created before a user account was deactivated as well as
    # direct pilot and mesh-assigned rows. This audit endpoint intentionally
    # does not apply live-map retention visibility filters.
    user_ids = list(session.scalars(select(User.id).where(User.pilot_id == pilot_id)).all())
    subject_clause = LivePosition.pilot_id == pilot_id
    if user_ids:
        subject_clause = or_(subject_clause, LivePosition.user_id.in_(user_ids))

    query = select(LivePosition).where(subject_clause)
    parsed_cursor = _raw_position_history_cursor(cursor)
    if parsed_cursor is not None:
        timestamp, row_id = parsed_cursor
        query = query.where(
            or_(
                LivePosition.timestamp < timestamp,
                and_(LivePosition.timestamp == timestamp, LivePosition.id < row_id),
            )
        )

    rows = session.scalars(
        query.order_by(LivePosition.timestamp.desc(), LivePosition.id.desc()).limit(limit + 1)
    ).all()
    page_rows = rows[:limit]
    previous_row: LivePosition | None = None
    if page_rows:
        oldest = page_rows[-1]
        previous_row = session.scalar(
            select(LivePosition)
            .where(
                subject_clause,
                or_(
                    LivePosition.timestamp < oldest.timestamp,
                    and_(LivePosition.timestamp == oldest.timestamp, LivePosition.id < oldest.id),
                ),
            )
            .order_by(LivePosition.timestamp.desc(), LivePosition.id.desc())
            .limit(1)
        )

    chronological_rows = list(reversed(page_rows))
    vario_by_id: dict[uuid.UUID, float | None] = {}
    for row in chronological_rows:
        vario_by_id[row.id] = _raw_position_vario_mps(previous_row, row)
        previous_row = row

    points = []
    for row in page_rows:
        point_type, path = _raw_position_path(row.source)
        points.append(
            RawPositionHistoryPoint(
                id=str(row.id),
                timestamp=row.timestamp.isoformat(),
                alt=row.alt,
                lat=row.lat,
                lon=row.lon,
                source=row.source,
                device_id=row.device_id,
                point_type=point_type,
                path=path,
                vario_mps=vario_by_id[row.id],
            )
        )

    next_cursor = None
    if len(rows) > limit and page_rows:
        tail = page_rows[-1]
        next_cursor = f"{_raw_position_history_timestamp(tail.timestamp).isoformat()}|{tail.id}"
    return RawPositionHistoryResponse(points=points, next_cursor=next_cursor)

@router.post("/api/track/position", response_model=PositionResponse, status_code=status.HTTP_201_CREATED)
def post_position(
    payload: PositionPayload,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> PositionResponse:
    if payload.task_id is not None:
        task = session.get(Task, payload.task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    source = (payload.source or "app").strip().lower() or "app"
    payload_device_id = payload.device_id
    if source in MESH_POSITION_SOURCES:
        payload_device_id = _normalize_required_mesh_position_device_id(payload.device_id)
    elif source == "app":
        payload_device_id = None

    user_id: int | None = user.id
    pilot_id = None if (user.profile_type or "pilot").strip().lower() == "driver" else user.pilot_id
    task_id = payload.task_id
    response_profile_type = user.profile_type or "pilot"
    response_aircraft_icon = user.aircraft_icon or "hang_glider"
    response_pilot_name: str | None = user.full_name
    if source in MESH_POSITION_SOURCES:
        mesh_user, mesh_device = resolve_mesh_device_assignment(session, payload_device_id)
        mesh_profile_type = mesh_purpose_to_profile_type(mesh_device.purpose) if mesh_device is not None else None
        user_id = mesh_user.id if mesh_user is not None else None
        pilot_id = (
            mesh_user.pilot_id
            if mesh_user is not None
            and (mesh_user.profile_type or "pilot").strip().lower() != "driver"
            and mesh_profile_type != "driver"
            else None
        )
        if mesh_user is not None and mesh_profile_type == "driver":
            response_profile_type = "driver"
            response_aircraft_icon = mesh_user.aircraft_icon or "hang_glider"
            response_pilot_name = mesh_device.label if mesh_device is not None else mesh_user.full_name
        elif mesh_user is not None:
            response_profile_type = mesh_user.profile_type or "pilot"
            response_aircraft_icon = mesh_user.aircraft_icon or "hang_glider"
            response_pilot_name = mesh_user.full_name
        elif mesh_device is not None:
            response_profile_type = mesh_profile_type or "pilot"
            response_pilot_name = mesh_device.label
        if task_id is None:
            if mesh_user is not None:
                task_id = resolve_active_task_id_for_user(session, mesh_user)
            elif pilot_id is not None:
                task_id = resolve_active_task_id(session, pilot_id)
    elif task_id is None:
        task_id = resolve_active_task_id_for_user(session, user)

    pos = store_position(
        session,
        task_id=task_id,
        lat=payload.lat,
        lon=payload.lon,
        alt=payload.alt,
        speed=payload.speed,
        heading=payload.heading,
        accuracy=payload.accuracy,
        timestamp=payload.timestamp,
        source=source,
        device_id=payload_device_id,
        mesh_seq_number=payload.mesh_seq_number,
        battery_level=payload.battery_level,
        battery_level_seen_at=payload.battery_level_seen_at,
        pilot_id=pilot_id,
        user_id=user_id,
    )
    if source in MESH_POSITION_SOURCES:
        gateway_id = user.mesh_device_id if source == "mesh_relay" else payload.device_id
        _upsert_mesh_position_status(
            session,
            device_id=payload_device_id,
            seen_at=pos.timestamp,
            source=source,
            gateway_id=gateway_id,
            battery_level=payload.battery_level,
        )
        if gateway_id and normalize_mesh_device_id(gateway_id) != normalize_mesh_device_id(payload_device_id):
            _upsert_mesh_position_status(
                session,
                device_id=gateway_id,
                seen_at=pos.timestamp,
                source=source,
                gateway_id=gateway_id,
            )
    session.commit()

    return PositionResponse(
        id=str(pos.id),
        subject_key=subject_key_for_position(pos, profile_type=response_profile_type),
        pilot_id=pos.pilot_id,
        user_id=pos.user_id,
        pilot_name=response_pilot_name,
        task_id=pos.task_id,
        lat=pos.lat,
        lon=pos.lon,
        alt=pos.alt,
        speed=pos.speed,
        heading=pos.heading,
        accuracy=pos.accuracy,
        timestamp=pos.timestamp.isoformat(),
        source=pos.source,
        device_id=pos.device_id,
        mesh_seq_number=pos.mesh_seq_number,
        battery_level=pos.battery_level,
        aircraft_icon=response_aircraft_icon,
        profile_type=response_profile_type,
        position_source=normalize_position_source(pos.source),
        received_at=pos.created_at.isoformat() if pos.created_at else None,
    )


@router.post(
    "/api/track/mesh-radio/telemetry",
    response_model=MeshRadioTelemetryResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_mesh_radio_telemetry(
    payload: MeshRadioTelemetryPayload,
    _user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MeshRadioTelemetryResponse:
    normalized_device_id = _normalize_required_mesh_position_device_id(payload.device_id)
    if payload.battery_level < 0 or payload.battery_level > 101:
        raise HTTPException(
            status_code=422,
            detail="battery_level must be between 0 and 101",
        )

    seen_at = payload.battery_level_seen_at
    if seen_at.tzinfo is None:
        seen_at = seen_at.replace(tzinfo=UTC)
    else:
        seen_at = seen_at.astimezone(UTC)

    status_row = session.scalar(
        select(MeshNodeStatus).where(MeshNodeStatus.device_id == normalized_device_id)
    )
    if status_row is None:
        status_row = MeshNodeStatus(
            device_id=normalized_device_id,
            last_seen_at=seen_at,
            packet_count=0,
        )
        session.add(status_row)

    existing_battery_seen_at = status_row.battery_level_seen_at
    if existing_battery_seen_at is not None:
        if existing_battery_seen_at.tzinfo is None:
            existing_battery_seen_at = existing_battery_seen_at.replace(tzinfo=UTC)
        else:
            existing_battery_seen_at = existing_battery_seen_at.astimezone(UTC)
        if existing_battery_seen_at > seen_at:
            return MeshRadioTelemetryResponse(
                device_id=normalized_device_id,
                battery_level=status_row.battery_level,
                battery_level_seen_at=existing_battery_seen_at.isoformat(),
            )

    status_row.last_seen_at = seen_at
    status_row.last_packet_type = "TELEMETRY_APP"
    status_row.last_source = "app_ble"
    status_row.last_topic = "api:/api/track/mesh-radio/telemetry"
    status_row.packet_count = (status_row.packet_count or 0) + 1
    status_row.battery_level = payload.battery_level
    status_row.battery_level_seen_at = seen_at
    session.commit()

    return MeshRadioTelemetryResponse(
        device_id=normalized_device_id,
        battery_level=status_row.battery_level,
        battery_level_seen_at=seen_at.isoformat(),
    )


@router.get("/api/track/live/{task_id}")
async def live_positions_sse(
    task_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    queue = subscribe(task_id)

    async def event_stream():
        try:
            # Send initial snapshot as first event
            snapshot = get_live_positions(session, task_id)
            yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"

            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    event_type = message.pop("event", "position") if isinstance(message, dict) else "position"
                    yield f"event: {event_type}\ndata: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    # Send keep-alive comment to prevent connection timeout
                    yield ": keepalive\n\n"
        finally:
            unsubscribe(task_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/track/positions/{task_id}", response_model=list[PositionResponse])
def get_positions(
    task_id: int,
    pilot_id: int | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: Annotated[int | None, Query(ge=1)] = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[PositionResponse]:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    rows = get_position_history(session, task_id, pilot_id=pilot_id, since=since, limit=limit)
    return [PositionResponse(**row) for row in rows]


@router.get("/api/track/active-pilots", response_model=list[ActivePilotResponse])
def get_active_pilots_endpoint(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ActivePilotResponse]:
    """Return latest position for all pilots with recent activity (any task or free-flight)."""
    rows = get_all_active_positions(session)
    return [ActivePilotResponse(**row) for row in rows]


@router.get("/api/track/live/pilots")
async def live_positions_pilots_sse(
    ids: str = Query(..., description="Comma-separated pilot IDs"),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """SSE stream for a set of pilot IDs (buddy group tracking)."""
    pilot_ids = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    if not pilot_ids:
        raise HTTPException(status_code=422, detail="At least one pilot ID is required")

    queue = subscribe_pilots(pilot_ids)

    async def event_stream():
        try:
            snapshot = get_live_positions_for_pilots(session, pilot_ids)
            yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"event: position\ndata: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            unsubscribe_pilots(pilot_ids, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/track/positions/pilots", response_model=list[PositionResponse])
def get_positions_for_pilots(
    ids: str = Query(..., description="Comma-separated pilot IDs"),
    since: datetime | None = Query(default=None),
    limit: Annotated[int | None, Query(ge=1)] = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[PositionResponse]:
    """Position history for a set of pilots (all tasks + free-flight)."""
    pilot_ids = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    if not pilot_ids:
        raise HTTPException(status_code=422, detail="At least one pilot ID is required")
    rows = get_position_history_for_pilots(session, pilot_ids, since=since, limit=limit)
    return [PositionResponse(**row) for row in rows]


@router.get("/api/track/igc/{task_id}/{pilot_id}")
def get_igc_track(
    task_id: int,
    pilot_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Return IGC track as GeoJSON for a task/pilot if an upload exists."""
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Prefer selected upload from scoring inputs
    scoring_input = session.scalar(
        select(TaskScoringInput).where(
            TaskScoringInput.task_id == task_id,
            TaskScoringInput.pilot_id == pilot_id,
        )
    )
    upload_id = scoring_input.selected_upload_id if scoring_input and scoring_input.selected_upload_id else None

    if upload_id:
        upload = session.get(IGCUpload, upload_id)
    else:
        upload = session.scalar(
            select(IGCUpload).where(
                IGCUpload.task_id == task_id,
                IGCUpload.pilot_id == pilot_id,
            ).order_by(IGCUpload.uploaded_at.desc()).limit(1)
        )

    if not upload:
        raise HTTPException(status_code=404, detail="No IGC upload found")

    points = session.scalars(
        select(TrackPoint).where(TrackPoint.upload_id == upload.id).order_by(TrackPoint.sequence.asc())
    ).all()

    if not points:
        raise HTTPException(status_code=404, detail="No track points in upload")

    coordinates = []
    timestamps = []
    for point in points:
        alt = point.pressure_altitude_m if point.pressure_altitude_m is not None else (point.gps_altitude_m or 0)
        coordinates.append([point.longitude, point.latitude, alt])
        timestamps.append(point.recorded_at.isoformat() if point.recorded_at else "")

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "pilot_id": pilot_id,
                    "upload_id": upload.id,
                    "filename": upload.filename,
                    "timestamps": timestamps,
                    "line_style": "solid",
                    "track_kind": "igc",
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates,
                },
            }
        ],
    }


@router.get("/api/config/mesh", response_model=MeshConfigResponse)
def get_mesh_config(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MeshConfigResponse:
    site = session.get(SiteSettings, 1)
    if site is None:
        # Fall back to env-based config if site_settings row doesn't exist yet
        settings = get_settings()
        return MeshConfigResponse(
            channel_psk=getattr(settings, "mesh_channel_psk", None),
            mqtt_host=getattr(settings, "mqtt_host", None),
            mqtt_port=getattr(settings, "mqtt_port", 1883),
            mqtt_tls_enabled=getattr(settings, "mqtt_tls_enabled", False),
            mqtt_username=getattr(settings, "mqtt_username", None),
            mqtt_password=getattr(settings, "mqtt_password", None),
            topic_prefix=getattr(settings, "mesh_mqtt_topic_prefix", "aervyx"),
        )
    broker_mode = normalize_mqtt_broker_mode(site.mqtt_broker_mode)
    changed = site.mqtt_broker_mode != broker_mode
    site.mqtt_broker_mode = broker_mode
    changed = clear_legacy_public_mqtt_values(site) or changed
    if changed:
        session.add(site)
        session.commit()
        session.refresh(site)
    return MeshConfigResponse(
        channel_psk=site.mqtt_channel_psk,
        mqtt_host=site.mqtt_host,
        mqtt_port=site.mqtt_port,
        mqtt_tls_enabled=site.mqtt_tls_enabled,
        mqtt_username=site.mqtt_username,
        mqtt_password=site.mqtt_password,
        topic_prefix=site.mqtt_topic_prefix,
    )


class MeshProfilesResponse(BaseModel):
    profiles: dict
    updated_at: str | None = None


@router.get("/api/config/mesh-profiles", response_model=MeshProfilesResponse)
def get_mesh_profiles(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MeshProfilesResponse:
    from app.routers.site_settings import DEFAULT_MESH_PROFILES
    site = session.get(SiteSettings, 1)
    profiles = site.mesh_profiles if site and site.mesh_profiles else DEFAULT_MESH_PROFILES
    updated = site.updated_at.isoformat() if site and site.updated_at else None
    return MeshProfilesResponse(profiles=profiles, updated_at=updated)


@router.get("/api/track/active-task", response_model=ActiveTaskResponse | None)
def get_active_task(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ActiveTaskResponse | None:
    """Return the user's currently active competition task with turnpoints, or null."""
    task_id = resolve_active_task_id_for_user(session, user)
    if task_id is None:
        return None

    task = session.get(Task, task_id)
    if task is None:
        return None
    event = session.get(Event, task.event_id)

    points = session.scalars(
        select(TaskPoint)
        .where(TaskPoint.task_id == task.id)
        .order_by(TaskPoint.position.asc())
    ).all()

    return ActiveTaskResponse(
        task_id=task.id,
        event_id=task.event_id,
        task_name=task.name,
        visible_airspace_classes=(
            list(event.visible_airspace_classes_json or ["B", "C", "D", "P", "Q", "R", "TFR", "OTHER"])
            if event is not None
            else ["B", "C", "D", "P", "Q", "R", "TFR", "OTHER"]
        ),
        show_restricted_fields=True
        if event is None or event.show_restricted_fields is None
        else event.show_restricted_fields,
        turnpoints=[
            ActiveTaskTurnpoint(
                id=str(tp.id),
                name=tp.name,
                type=tp.point_type,
                point_type=tp.point_type,
                lat=tp.latitude,
                lon=tp.longitude,
                radius=tp.radius_m,
                radius_meters=tp.radius_m,
            )
            for tp in points
        ],
    )


@router.post("/api/sos", response_model=SosResponse, status_code=status.HTTP_201_CREATED)
def post_sos(
    payload: SosPayload,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SosResponse:
    """Record an SOS alert from a pilot."""
    ts = payload.timestamp or datetime.now(UTC)
    alert = SosAlert(
        id=uuid.uuid4(),
        pilot_id=user.pilot_id,
        lat=payload.lat,
        lon=payload.lon,
        alt=payload.alt,
        message=payload.message,
        timestamp=ts,
    )
    session.add(alert)
    session.commit()
    logger.warning(
        "SOS alert from user %s (pilot_id=%s) at %.6f, %.6f: %s",
        user.username, user.pilot_id, payload.lat, payload.lon, payload.message,
    )
    return SosResponse(
        id=str(alert.id),
        pilot_id=alert.pilot_id,
        lat=alert.lat,
        lon=alert.lon,
        alt=alert.alt,
        message=alert.message,
        timestamp=ts.isoformat(),
    )


@router.get("/api/driver/sos", response_model=list[DriverSosAlertResponse])
def list_driver_sos_alerts(
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[DriverSosAlertResponse]:
    """Return active SOS alerts for driver mobile clients."""
    profile_type = (user.profile_type or "pilot").strip().lower()
    if user.role != "admin" and profile_type != "driver":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Driver access required",
        )

    rows = session.execute(
        select(SosAlert, Pilot.first_name, Pilot.last_name)
        .outerjoin(Pilot, SosAlert.pilot_id == Pilot.id)
        .where(SosAlert.status == "active")
        .order_by(SosAlert.timestamp.desc())
        .limit(limit)
    ).all()

    alerts: list[DriverSosAlertResponse] = []
    for alert, first_name, last_name in rows:
        pilot_name = None
        if first_name is not None or last_name is not None:
            pilot_name = f"{first_name or ''} {last_name or ''}".strip() or None
        timestamp = alert.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        alerts.append(
            DriverSosAlertResponse(
                id=str(alert.id),
                pilot_id=alert.pilot_id,
                pilot_name=pilot_name,
                lat=alert.lat,
                lon=alert.lon,
                alt=alert.alt,
                message=alert.message,
                timestamp=timestamp.isoformat(),
                status=alert.status,
            )
        )
    return alerts


@router.get("/api/config/flight-detection", response_model=FlightDetectionConfigResponse)
def get_flight_detection_config(
    user: User = Depends(get_current_user),
) -> FlightDetectionConfigResponse:
    """Return flight detection thresholds. Hardcoded defaults for now."""
    return FlightDetectionConfigResponse(
        paraglider=FlightDetectionThresholds(altitude_gain_m=10, speed_threshold_ms=2.2),
        hang_glider=FlightDetectionThresholds(altitude_gain_m=10, speed_threshold_ms=3.6),
        glider=FlightDetectionThresholds(altitude_gain_m=15, speed_threshold_ms=6.7),
        landing_speed_ms=4.47,
        landing_altitude_tolerance_m=30.5,
        landing_confirm_seconds=15,
        landing_countdown_seconds=15,
    )


@router.get("/api/driver/assigned-pilots/{task_id}", response_model=list[AssignedPilotResponse])
def get_assigned_pilots(
    task_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[AssignedPilotResponse]:
    """Return pilots assigned to this driver for a task.

    Uses DriverAssignment table if assignments exist, otherwise falls back
    to all event pilots for backward compatibility.
    """
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    from app.models import DriverAssignment, Pilot, PilotLanding

    # Try explicit driver assignments first
    assigned_ids = session.scalars(
        select(DriverAssignment.pilot_id).where(
            DriverAssignment.task_id == task_id,
            DriverAssignment.driver_user_id == user.id,
        )
    ).all()

    if assigned_ids:
        rows = session.execute(
            select(Pilot)
            .where(Pilot.id.in_(assigned_ids))
            .order_by(Pilot.last_name.asc(), Pilot.first_name.asc())
        ).scalars().all()
    else:
        # Fallback: all event pilots
        rows = session.execute(
            select(Pilot)
            .join(EventPilot, EventPilot.pilot_id == Pilot.id)
            .where(EventPilot.event_id == task.event_id)
            .order_by(Pilot.last_name.asc(), Pilot.first_name.asc())
        ).scalars().all()

    return [
        AssignedPilotResponse(
            pilot_id=p.id,
            first_name=p.first_name,
            last_name=p.last_name,
        )
        for p in rows
    ]


# ---------------------------------------------------------------------------
# Stationary Meshtastic node registration (admin only)
# ---------------------------------------------------------------------------

class StationaryNodeCreate(BaseModel):
    mesh_device_id: str
    display_name: str


class StationaryNodeResponse(BaseModel):
    user_id: int
    mesh_device_id: str
    display_name: str
    profile_type: str


@router.post(
    "/api/admin/stationary-nodes",
    response_model=StationaryNodeResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_stationary_node(
    payload: StationaryNodeCreate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> StationaryNodeResponse:
    """Register (or re-register) a stationary Meshtastic relay as a User row.

    The node-type is never transmitted over the mesh; the backend identifies
    the relay by joining ``LivePosition.device_id`` against ``users.mesh_device_id``
    at query time. This endpoint exists so the mobile Meshtastic setup flow can
    record the device ID → stationary_node mapping once, during pairing.
    """
    mesh_device_id = (payload.mesh_device_id or "").strip()
    display_name = (payload.display_name or "").strip()
    if not mesh_device_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mesh_device_id is required")
    if not display_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="display_name is required")

    existing = session.scalar(select(User).where(User.mesh_device_id == mesh_device_id))
    if existing is not None:
        existing.full_name = display_name
        existing.profile_type = "stationary_node"
        existing.is_active = True
        session.add(existing)
        session.commit()
        from app.services.mqtt_subscriber import request_mqtt_reconnect
        request_mqtt_reconnect()
        session.refresh(existing)
        return StationaryNodeResponse(
            user_id=existing.id,
            mesh_device_id=mesh_device_id,
            display_name=existing.full_name,
            profile_type=existing.profile_type,
        )

    # Generate a synthetic username so there's no login conflict with pilots/drivers.
    synthetic_username = f"mesh-node-{mesh_device_id}"[:80]
    collision = session.scalar(select(User).where(User.username == synthetic_username))
    if collision is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with that synthetic username already exists")

    node = User(
        username=synthetic_username,
        full_name=display_name,
        role="pilot",  # non-admin role; stationary nodes do not need elevated access
        profile_type="stationary_node",
        mesh_device_id=mesh_device_id,
        is_active=True,
    )
    session.add(node)
    session.commit()
    from app.services.mqtt_subscriber import request_mqtt_reconnect
    request_mqtt_reconnect()
    session.refresh(node)
    return StationaryNodeResponse(
        user_id=node.id,
        mesh_device_id=mesh_device_id,
        display_name=node.full_name,
        profile_type=node.profile_type,
    )


@router.get("/api/admin/mesh-nodes", response_model=list[MeshNodeResponse])
def get_mesh_nodes(
    minutes: int = Query(default=60, ge=1, le=1440),
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[MeshNodeResponse]:
    """Return the latest position for every device_id that reported a position recently.

    Unlike the active-pilots endpoint this query is keyed on device_id rather
    than pilot_id, so bare mesh nodes (relays, stationary nodes, unregistered
    handsets) that never linked to a pilot account still appear on the map.
    """
    from datetime import timedelta

    from sqlalchemy import func as sa_func

    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=minutes)

    # Window function: rank rows per device_id by descending timestamp so we
    # can pick only the most-recent position for each device in one query.
    row_num = sa_func.row_number().over(
        partition_by=LivePosition.device_id,
        order_by=LivePosition.timestamp.desc(),
    ).label("rn")

    subq = (
        select(LivePosition, row_num)
        .where(
            LivePosition.device_id.isnot(None),
            LivePosition.device_id != "",
            LivePosition.device_id != "!",
            sa_func.lower(LivePosition.device_id).notin_(sorted(MISSING_MESH_DEVICE_ID_SENTINELS)),
            LivePosition.source.in_(sorted(MESH_POSITION_SOURCES)),
            LivePosition.timestamp >= cutoff,
        )
        .subquery()
    )

    rows = session.execute(select(subq).where(subq.c.rn == 1)).all()
    position_by_device = {r.device_id: r for r in rows if r.device_id}
    status_rows = session.scalars(
        select(MeshNodeStatus).where(
            MeshNodeStatus.last_seen_at >= cutoff,
            MeshNodeStatus.device_id != "",
            MeshNodeStatus.device_id != "!",
            sa_func.lower(MeshNodeStatus.device_id).notin_(sorted(MISSING_MESH_DEVICE_ID_SENTINELS)),
        )
    ).all()
    status_by_device = {status.device_id: status for status in status_rows}
    gateway_display_names = resolve_mesh_device_display_names(
        session,
        {status.last_gateway_id for status in status_rows},
    )
    all_device_ids = sorted(set(position_by_device) | set(status_by_device))

    if not all_device_ids:
        return []

    # Resolve pilot names / profile types via pilot_id when available.
    pilot_ids = [r.pilot_id for r in position_by_device.values() if r.pilot_id is not None]
    users_by_pilot: dict[int, User] = {}
    if pilot_ids:
        for u in session.scalars(select(User).where(User.pilot_id.in_(pilot_ids))).all():
            if u.pilot_id is not None:
                users_by_pilot[u.pilot_id] = u

    # Fall back to device_id → User lookup for positions with no pilot_id.
    unlinked_device_ids = [
        device_id
        for device_id in all_device_ids
        if position_by_device.get(device_id) is None or position_by_device[device_id].pilot_id is None
    ]
    users_by_device: dict[str, User] = {}
    if unlinked_device_ids:
        for u in session.scalars(select(User).where(User.mesh_device_id.in_(unlinked_device_ids))).all():
            if u.mesh_device_id:
                users_by_device[u.mesh_device_id] = u

    devices_by_id: dict[str, MeshDevice] = {}
    owners_by_id: dict[int, User] = {}
    if all_device_ids:
        devices = session.scalars(select(MeshDevice).where(MeshDevice.device_id.in_(all_device_ids))).all()
        devices_by_id = {device.device_id: device for device in devices}
        owner_ids = {device.owner_user_id for device in devices}
        if owner_ids:
            owners_by_id = {
                owner.id: owner
                for owner in session.scalars(select(User).where(User.id.in_(owner_ids))).all()
            }

    # For devices whose latest position has alt=NULL, look up the most recent
    # position that DID have altitude (backfill from older rows).
    devices_missing_alt = [r.device_id for r in position_by_device.values() if r.alt is None and r.device_id]
    alt_backfill: dict[str, float] = {}
    if devices_missing_alt:
        alt_subq = (
            select(
                LivePosition.device_id,
                LivePosition.alt,
                sa_func.row_number().over(
                    partition_by=LivePosition.device_id,
                    order_by=LivePosition.timestamp.desc(),
                ).label("rn"),
            )
            .where(
                LivePosition.device_id.in_(devices_missing_alt),
                LivePosition.alt.isnot(None),
                LivePosition.timestamp >= cutoff,
            )
            .subquery()
        )
        alt_rows = session.execute(
            select(alt_subq.c.device_id, alt_subq.c.alt).where(alt_subq.c.rn == 1)
        ).all()
        alt_backfill = {r.device_id: r.alt for r in alt_rows}

    # Similarly backfill battery from recent positions for devices with NULL battery
    devices_missing_bat = [r.device_id for r in position_by_device.values() if r.battery_level is None and r.device_id]
    bat_backfill: dict[str, tuple[int, datetime | None]] = {}
    if devices_missing_bat:
        bat_subq = (
            select(
                LivePosition.device_id,
                LivePosition.battery_level,
                LivePosition.timestamp,
                sa_func.row_number().over(
                    partition_by=LivePosition.device_id,
                    order_by=LivePosition.timestamp.desc(),
                ).label("rn"),
            )
            .where(
                LivePosition.device_id.in_(devices_missing_bat),
                LivePosition.battery_level.isnot(None),
                LivePosition.timestamp >= cutoff,
            )
            .subquery()
        )
        bat_rows = session.execute(
            select(bat_subq.c.device_id, bat_subq.c.battery_level, bat_subq.c.timestamp).where(bat_subq.c.rn == 1)
        ).all()
        bat_backfill = {r.device_id: (r.battery_level, r.timestamp) for r in bat_rows}

    def _ts_value(value: datetime | None) -> float:
        if value is None:
            return 0
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.timestamp()

    results: list[MeshNodeResponse] = []
    for device_id in sorted(
        all_device_ids,
        key=lambda item: max(
            _ts_value(status_by_device[item].last_seen_at) if item in status_by_device else 0,
            _ts_value(position_by_device[item].timestamp) if item in position_by_device else 0,
        ),
        reverse=True,
    ):
        row = position_by_device.get(device_id)
        node_status = status_by_device.get(device_id)
        device = devices_by_id.get(device_id)
        owner = owners_by_id.get(device.owner_user_id) if device is not None else None
        u = (
            users_by_pilot.get(row.pilot_id)
            if row is not None and row.pilot_id is not None
            else (owner or users_by_device.get(device_id))
        )
        profile_type = (
            u.profile_type
            if row is not None and row.pilot_id is not None and u is not None
            else mesh_purpose_to_profile_type(device.purpose) if device is not None
            else u.profile_type if u is not None else None
        )
        alt = row.alt if row is not None and row.alt is not None else alt_backfill.get(device_id)
        battery = (
            node_status.battery_level
            if node_status is not None and node_status.battery_level is not None
            else row.battery_level if row is not None and row.battery_level is not None
            else bat_backfill.get(device_id, (None, None))[0]
        )
        battery_seen_at = (
            node_status.battery_level_seen_at or node_status.last_seen_at
            if node_status is not None and node_status.battery_level is not None
            else row.timestamp if row is not None and row.battery_level is not None
            else bat_backfill.get(device_id, (None, None))[1]
        )
        latest_ts = node_status.last_seen_at if node_status is not None else None
        latest_position_is_newer = False
        if row is not None and _ts_value(row.timestamp) > _ts_value(latest_ts):
            latest_ts = row.timestamp
            latest_position_is_newer = True
        mesh_status = mesh_status_for_seen_at(now, latest_ts)
        source = (
            row.source
            if latest_position_is_newer and row is not None and row.source is not None
            else node_status.last_source if node_status is not None and node_status.last_source
            else row.source if row is not None else None
        )
        last_packet_type = (
            "POSITION_APP"
            if latest_position_is_newer and row is not None
            else node_status.last_packet_type if node_status is not None
            else "POSITION_APP" if row is not None
            else None
        )
        last_gateway_id = _status_gateway_id_for_latest(
            node_status,
            latest_position_is_newer=latest_position_is_newer,
            latest_position_ts=row.timestamp if row is not None else None,
            source=source,
            packet_type=last_packet_type,
        )
        results.append(
            MeshNodeResponse(
                device_id=device_id,
                pilot_id=row.pilot_id if row is not None else (u.pilot_id if u else None),
                pilot_name=u.full_name if u else None,
                profile_type=profile_type,
                device_label=device.label if device else None,
                device_purpose=device.purpose if device else None,
                registered_owner_user_id=owner.id if owner else (u.id if u and (row is None or row.pilot_id is None) else None),
                registered_owner_name=owner.full_name if owner else (u.full_name if u and (row is None or row.pilot_id is None) else None),
                lat=row.lat if row is not None else None,
                lon=row.lon if row is not None else None,
                alt=alt,
                speed=row.speed if row is not None else None,
                heading=row.heading if row is not None else None,
                battery_level=battery,
                battery_level_seen_at=battery_seen_at.isoformat() if battery_seen_at else None,
                timestamp=latest_ts.isoformat() if latest_ts else now.isoformat(),
                source=source,
                position_source=normalize_position_source(row.source if row is not None else None),
                mesh_status=mesh_status,
                last_packet_type=last_packet_type,
                last_gateway_id=last_gateway_id,
                last_gateway_display_name=(
                    gateway_display_names.get(last_gateway_id)
                    if last_gateway_id is not None
                    else None
                ),
                last_topic=node_status.last_topic if node_status is not None else None,
                packet_count=node_status.packet_count if node_status is not None else (1 if row is not None else 0),
            )
        )

    return results
