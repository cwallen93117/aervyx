from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_session
from app.deps import get_current_user
from app.models import Event, EventPilot, SosAlert, Task, TaskPoint, User
from app.services.tracking import (
    get_live_positions,
    get_live_positions_for_pilots,
    get_position_history,
    get_position_history_for_pilots,
    store_position,
    subscribe,
    subscribe_pilots,
    unsubscribe,
    unsubscribe_pilots,
)

router = APIRouter(tags=["tracking"])
logger = logging.getLogger("aervyx.tracking")


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
    battery_level: int | None = None


class PositionResponse(BaseModel):
    id: str
    pilot_id: int | None
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
    battery_level: int | None
    aircraft_icon: str = "hang_glider"


class MeshConfigResponse(BaseModel):
    channel_psk: str | None = None
    mqtt_host: str | None = None
    mqtt_port: int = 1883
    topic_prefix: str = "aervyx"


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


class ActiveTaskTurnpoint(BaseModel):
    id: int
    name: str
    point_type: str
    lat: float
    lon: float
    radius_meters: float


class ActiveTaskResponse(BaseModel):
    task_id: int
    task_name: str
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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

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

    pos = store_position(
        session,
        task_id=payload.task_id,
        lat=payload.lat,
        lon=payload.lon,
        alt=payload.alt,
        speed=payload.speed,
        heading=payload.heading,
        accuracy=payload.accuracy,
        timestamp=payload.timestamp,
        source=payload.source or "app",
        device_id=payload.device_id,
        battery_level=payload.battery_level,
        pilot_id=user.pilot_id,
    )
    session.commit()

    return PositionResponse(
        id=str(pos.id),
        pilot_id=pos.pilot_id,
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
        battery_level=pos.battery_level,
        aircraft_icon=(user.aircraft_icon or "hang_glider"),
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
                    yield f"event: position\ndata: {json.dumps(message)}\n\n"
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
    limit: int = Query(default=5000, le=10000),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[PositionResponse]:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    rows = get_position_history(session, task_id, pilot_id=pilot_id, since=since, limit=limit)
    return [PositionResponse(**row) for row in rows]


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
    limit: int = Query(default=10000, le=50000),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[PositionResponse]:
    """Position history for a set of pilots (all tasks + free-flight)."""
    pilot_ids = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    if not pilot_ids:
        raise HTTPException(status_code=422, detail="At least one pilot ID is required")
    rows = get_position_history_for_pilots(session, pilot_ids, since=since, limit=limit)
    return [PositionResponse(**row) for row in rows]


@router.get("/api/config/mesh", response_model=MeshConfigResponse)
def get_mesh_config(user: User = Depends(get_current_user)) -> MeshConfigResponse:
    settings = get_settings()
    return MeshConfigResponse(
        channel_psk=getattr(settings, "mesh_channel_psk", None),
        mqtt_host=getattr(settings, "mqtt_host", None),
        mqtt_port=getattr(settings, "mqtt_port", 1883),
        topic_prefix=getattr(settings, "mesh_mqtt_topic_prefix", "aervyx"),
    )


@router.get("/api/track/active-task", response_model=ActiveTaskResponse | None)
def get_active_task(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ActiveTaskResponse | None:
    """Return the user's currently active competition task with turnpoints, or null."""
    if user.pilot_id is None:
        return None

    # Find an active task in an event the pilot is registered for
    row = session.execute(
        select(Task)
        .join(Event, Task.event_id == Event.id)
        .join(EventPilot, EventPilot.event_id == Event.id)
        .where(
            EventPilot.pilot_id == user.pilot_id,
            Task.status == "active",
        )
        .order_by(Task.id.desc())
        .limit(1)
    ).scalar_one_or_none()

    if row is None:
        return None

    task: Task = row
    points = session.scalars(
        select(TaskPoint)
        .where(TaskPoint.task_id == task.id)
        .order_by(TaskPoint.position.asc())
    ).all()

    return ActiveTaskResponse(
        task_id=task.id,
        task_name=task.name,
        turnpoints=[
            ActiveTaskTurnpoint(
                id=tp.id,
                name=tp.name,
                point_type=tp.point_type,
                lat=tp.latitude,
                lon=tp.longitude,
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
    """Return pilots in a task. First pass returns all event pilots for the task."""
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    from app.models import Pilot
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
