from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_session
from app.deps import get_current_user
from app.models import Task, User
from app.services.tracking import (
    get_live_positions,
    get_position_history,
    store_position,
    subscribe,
    unsubscribe,
)

router = APIRouter(tags=["tracking"])


# ---------------------------------------------------------------------------
# Request / response schemas (local to this router)
# ---------------------------------------------------------------------------

class PositionPayload(BaseModel):
    task_id: int
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
    task_id: int
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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/track/position", response_model=PositionResponse, status_code=status.HTTP_201_CREATED)
def post_position(
    payload: PositionPayload,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> PositionResponse:
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


@router.get("/api/config/mesh", response_model=MeshConfigResponse)
def get_mesh_config(user: User = Depends(get_current_user)) -> MeshConfigResponse:
    settings = get_settings()
    return MeshConfigResponse(
        channel_psk=getattr(settings, "mesh_channel_psk", None),
        mqtt_host=getattr(settings, "mqtt_host", None),
        mqtt_port=getattr(settings, "mqtt_port", 1883),
        topic_prefix=getattr(settings, "mesh_mqtt_topic_prefix", "aervyx"),
    )
