from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import (
    BuddyGroup,
    BuddyGroupMember,
    Event,
    EventPilot,
    Pilot,
    ScoreResult,
    Task,
    TaskPoint,
)
from app.routers.events import _event_payload
from app.routers.tasks import _task_response
from app.schemas import EventResponse, PilotSummaryResponse, ScoreResultResponse, TaskResponse
from app.services.scoring import build_result_payload
from app.services.tracking import (
    get_all_recent_positions,
    get_live_positions,
    get_live_positions_for_pilots,
    get_position_history,
    get_position_history_for_pilots,
    subscribe,
    subscribe_global,
    subscribe_pilots,
    unsubscribe,
    unsubscribe_global,
    unsubscribe_pilots,
)

router = APIRouter(prefix="/api/public", tags=["public"])
logger = logging.getLogger("aervyx.public")


# ---------------------------------------------------------------------------
# Response schemas for live tracking endpoints (local to this router)
# ---------------------------------------------------------------------------

class PublicTaskSummary(BaseModel):
    id: int
    name: str
    status: str
    task_date: str | None


class PublicEventSummary(BaseModel):
    id: int
    name: str
    location: str
    starts_on: str
    ends_on: str
    timezone: str
    tasks: list[PublicTaskSummary]


class PublicBuddyGroupSummary(BaseModel):
    id: int
    name: str
    member_count: int


class PublicLiveSourcesResponse(BaseModel):
    events: list[PublicEventSummary]
    buddy_groups: list[PublicBuddyGroupSummary]


class PublicPositionResponse(BaseModel):
    id: str
    pilot_id: int | None
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
    battery_level: int | None
    aircraft_icon: str = "hang_glider"
    profile_type: str = "pilot"
    position_source: str = "other"


class PublicTurnpointInfo(BaseModel):
    position: int
    name: str
    point_type: str
    radius_m: float
    latitude: float
    longitude: float


class PublicTaskInfoResponse(BaseModel):
    id: int
    name: str
    task_type: str
    task_date: str | None
    turnpoints: list[PublicTurnpointInfo]


# ---------------------------------------------------------------------------
# Existing public endpoints
# ---------------------------------------------------------------------------

@router.get("/events", response_model=list[EventResponse])
def list_public_events(session: Session = Depends(get_session)) -> list[EventResponse]:
    events = session.scalars(
        select(Event).where(Event.visibility == "public").order_by(Event.updated_at.desc(), Event.name.asc())
    ).all()
    return [_event_payload(session, event) for event in events]


@router.get("/events/{event_id}/tasks", response_model=list[TaskResponse])
def list_public_tasks(event_id: int, session: Session = Depends(get_session)) -> list[TaskResponse]:
    event = session.get(Event, event_id)
    if event is None or event.visibility != "public":
        raise HTTPException(status_code=404, detail="Event not found")
    tasks = session.scalars(
        select(Task)
        .where(Task.event_id == event_id, Task.status == "published")
        .order_by(Task.created_at.asc())
    ).all()
    return [_task_response(session, task) for task in tasks]


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_public_task(task_id: int, session: Session = Depends(get_session)) -> TaskResponse:
    task = session.get(Task, task_id)
    if task is None or task.status != "published":
        raise HTTPException(status_code=404, detail="Published task not found")
    event = session.get(Event, task.event_id)
    if event is None or event.visibility != "public":
        raise HTTPException(status_code=404, detail="Published task not found")
    return _task_response(session, task)


@router.get("/tasks/{task_id}/results", response_model=list[ScoreResultResponse])
def get_public_task_results(task_id: int, session: Session = Depends(get_session)) -> list[ScoreResultResponse]:
    task = session.get(Task, task_id)
    if task is None or task.status != "published":
        raise HTTPException(status_code=404, detail="Published task not found")
    event = session.get(Event, task.event_id)
    if event is None or event.visibility != "public":
        raise HTTPException(status_code=404, detail="Published task not found")
    results = session.scalars(
        select(ScoreResult)
        .where(ScoreResult.task_id == task_id)
        .order_by(ScoreResult.rank.asc().nullslast(), ScoreResult.score_points.desc())
    ).all()
    return [ScoreResultResponse(**build_result_payload(session, result)) for result in results]


@router.get("/events/{event_id}/pilot-summary", response_model=list[PilotSummaryResponse])
def public_pilot_summary(event_id: int, session: Session = Depends(get_session)) -> list[PilotSummaryResponse]:
    event = session.get(Event, event_id)
    if event is None or event.visibility != "public":
        raise HTTPException(status_code=404, detail="Event not found")
    pilot_ids = session.scalars(select(EventPilot.pilot_id).where(EventPilot.event_id == event_id)).all()
    published_task_ids = session.scalars(select(Task.id).where(Task.event_id == event_id, Task.status == "published")).all()
    summaries: list[PilotSummaryResponse] = []
    for pilot_id in pilot_ids:
        pilot = session.get(Pilot, pilot_id)
        task_scores = {
            int(task_id): float(score_points or 0)
            for task_id, score_points in session.execute(
                select(ScoreResult.task_id, ScoreResult.score_points)
                .where(ScoreResult.task_id.in_(published_task_ids), ScoreResult.pilot_id == pilot_id)
                .order_by(ScoreResult.task_id.asc())
            ).all()
        }
        aggregates = session.execute(
            select(
                func.coalesce(func.sum(ScoreResult.score_points), 0),
                func.count(ScoreResult.id),
                func.coalesce(func.max(ScoreResult.distance_flown_km), 0),
            )
            .select_from(ScoreResult)
            .where(ScoreResult.task_id.in_(published_task_ids), ScoreResult.pilot_id == pilot_id)
        ).one()
        summaries.append(
            PilotSummaryResponse(
                pilot_id=pilot_id,
                pilot_name=f"{pilot.first_name} {pilot.last_name}" if pilot else "Unknown",
                competition_number=pilot.competition_number if pilot else None,
                total_score_points=float(aggregates[0] or 0),
                tasks_scored=int(aggregates[1] or 0),
                best_distance_km=float(aggregates[2] or 0),
                task_scores=task_scores,
            )
        )
    return sorted(summaries, key=lambda summary: (-summary.total_score_points, summary.pilot_name))


# ---------------------------------------------------------------------------
# Public live tracking endpoints
# ---------------------------------------------------------------------------

@router.get("/live/sources", response_model=PublicLiveSourcesResponse)
def get_public_live_sources(session: Session = Depends(get_session)) -> PublicLiveSourcesResponse:
    """Return all events with public live tracking enabled and public buddy groups."""
    events_with_tracking = session.scalars(
        select(Event).where(Event.is_public_tracking.is_(True)).order_by(Event.starts_on.desc())
    ).all()

    event_summaries: list[PublicEventSummary] = []
    for event in events_with_tracking:
        tasks = session.scalars(
            select(Task)
            .where(
                Task.event_id == event.id,
                Task.status.in_(("published", "active")),
            )
            .order_by(Task.task_date.asc(), Task.id.asc())
        ).all()
        event_summaries.append(
            PublicEventSummary(
                id=event.id,
                name=event.name,
                location=event.location,
                starts_on=event.starts_on.isoformat(),
                ends_on=event.ends_on.isoformat(),
                timezone=event.timezone,
                tasks=[
                    PublicTaskSummary(
                        id=task.id,
                        name=task.name,
                        status=task.status,
                        task_date=task.task_date.isoformat() if task.task_date else None,
                    )
                    for task in tasks
                ],
            )
        )

    # Buddy groups with member counts
    buddy_rows = session.execute(
        select(BuddyGroup, func.count(BuddyGroupMember.id).label("member_count"))
        .outerjoin(BuddyGroupMember, BuddyGroupMember.group_id == BuddyGroup.id)
        .where(BuddyGroup.is_public.is_(True))
        .group_by(BuddyGroup.id)
        .order_by(BuddyGroup.name.asc())
    ).all()

    buddy_summaries = [
        PublicBuddyGroupSummary(
            id=row.BuddyGroup.id,
            name=row.BuddyGroup.name,
            member_count=row.member_count,
        )
        for row in buddy_rows
    ]

    return PublicLiveSourcesResponse(events=event_summaries, buddy_groups=buddy_summaries)


def _get_public_task(task_id: int, session: Session) -> Task:
    """Load a task and verify its event has public tracking enabled. Raises 404 otherwise."""
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    event = session.get(Event, task.event_id)
    if event is None or not event.is_public_tracking:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _get_public_event(event_id: int, session: Session) -> Event:
    """Load an event and verify public tracking is enabled. Raises 404 otherwise."""
    event = session.get(Event, event_id)
    if event is None or not event.is_public_tracking:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


def _public_event_pilot_ids(event_id: int, session: Session) -> list[int]:
    return list(
        session.scalars(
            select(EventPilot.pilot_id)
            .where(EventPilot.event_id == event_id)
            .order_by(EventPilot.pilot_id.asc())
        ).all()
    )


def _get_public_buddy_group(group_id: int, session: Session) -> BuddyGroup:
    """Load a buddy group and verify it is public. Raises 404 otherwise."""
    group = session.get(BuddyGroup, group_id)
    if group is None or not group.is_public:
        raise HTTPException(status_code=404, detail="Buddy group not found")
    return group


@router.get("/live/events/{event_id}")
async def public_event_live_sse(
    event_id: int,
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """SSE stream of live positions for every pilot in a publicly-tracked event."""
    _get_public_event(event_id, session)
    pilot_ids = _public_event_pilot_ids(event_id, session)

    queue = subscribe_pilots(pilot_ids)

    async def event_stream():
        try:
            snapshot = get_live_positions_for_pilots(session, pilot_ids)
            yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"

            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    event_type = message.pop("event", "position") if isinstance(message, dict) else "position"
                    yield f"event: {event_type}\ndata: {json.dumps(message)}\n\n"
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


@router.get("/live/events/{event_id}/positions", response_model=list[PublicPositionResponse])
def public_event_positions(
    event_id: int,
    minutes: int = Query(60),
    limit: int = Query(10000),
    session: Session = Depends(get_session),
) -> list[PublicPositionResponse]:
    """Position history for all pilots in a publicly-tracked event."""
    _get_public_event(event_id, session)
    pilot_ids = _public_event_pilot_ids(event_id, session)
    if not pilot_ids:
        return []

    minutes = max(1, min(minutes, 24 * 60))
    limit = max(1, min(limit, 10000))
    since = datetime.now(UTC) - timedelta(minutes=minutes)
    rows = get_position_history_for_pilots(session, pilot_ids, since=since, limit=limit)
    return [PublicPositionResponse(**row) for row in rows]


@router.get("/live/task/{task_id}")
async def public_task_live_sse(
    task_id: int,
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """SSE stream of live positions for a publicly-tracked task."""
    _get_public_task(task_id, session)

    queue = subscribe(task_id)

    async def event_stream():
        try:
            snapshot = get_live_positions(session, task_id)
            yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"

            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    event_type = message.pop("event", "position") if isinstance(message, dict) else "position"
                    yield f"event: {event_type}\ndata: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
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


@router.get("/live/task/{task_id}/positions", response_model=list[PublicPositionResponse])
def public_task_positions(
    task_id: int,
    session: Session = Depends(get_session),
) -> list[PublicPositionResponse]:
    """Position history for a publicly-tracked task (up to 10 000 records)."""
    _get_public_task(task_id, session)
    rows = get_position_history(session, task_id, limit=10000)
    return [PublicPositionResponse(**row) for row in rows]


@router.get("/live/task/{task_id}/info", response_model=PublicTaskInfoResponse)
def public_task_info(
    task_id: int,
    session: Session = Depends(get_session),
) -> PublicTaskInfoResponse:
    """Task metadata and turnpoints for map rendering."""
    task = _get_public_task(task_id, session)

    task_points = session.scalars(
        select(TaskPoint)
        .where(TaskPoint.task_id == task_id)
        .order_by(TaskPoint.position.asc())
    ).all()

    return PublicTaskInfoResponse(
        id=task.id,
        name=task.name,
        task_type=task.task_type,
        task_date=task.task_date.isoformat() if task.task_date else None,
        turnpoints=[
            PublicTurnpointInfo(
                position=tp.position,
                name=tp.name,
                point_type=tp.point_type,
                radius_m=tp.radius_m,
                latitude=tp.latitude,
                longitude=tp.longitude,
            )
            for tp in task_points
        ],
    )


@router.get("/live/buddies/{group_id}")
async def public_buddy_group_live_sse(
    group_id: int,
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """SSE stream of live positions for a public buddy group."""
    group = _get_public_buddy_group(group_id, session)

    pilot_ids = session.scalars(
        select(BuddyGroupMember.pilot_id).where(BuddyGroupMember.group_id == group.id)
    ).all()
    pilot_ids = list(pilot_ids)

    queue = subscribe_pilots(pilot_ids)

    async def event_stream():
        try:
            snapshot = get_live_positions_for_pilots(session, pilot_ids)
            yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"

            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    event_type = message.pop("event", "position") if isinstance(message, dict) else "position"
                    yield f"event: {event_type}\ndata: {json.dumps(message)}\n\n"
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


@router.get("/live/buddies/{group_id}/positions", response_model=list[PublicPositionResponse])
def public_buddy_group_positions(
    group_id: int,
    minutes: int = Query(60),
    limit: int = Query(10000),
    session: Session = Depends(get_session),
) -> list[PublicPositionResponse]:
    """Position history for all pilots in a public buddy group (up to 10 000 records)."""
    group = _get_public_buddy_group(group_id, session)

    pilot_ids = session.scalars(
        select(BuddyGroupMember.pilot_id).where(BuddyGroupMember.group_id == group.id)
    ).all()
    pilot_ids = list(pilot_ids)

    if not pilot_ids:
        return []
    minutes = max(1, min(minutes, 24 * 60))
    limit = max(1, min(limit, 10000))
    since = datetime.now(UTC) - timedelta(minutes=minutes)
    rows = get_position_history_for_pilots(session, pilot_ids, since=since, limit=limit)
    return [PublicPositionResponse(**row) for row in rows]


# ---------------------------------------------------------------------------
# All-users live tracking endpoints
# ---------------------------------------------------------------------------
# These endpoints intentionally back the "All users" option on the public
# Watch Live page.

@router.get("/live/all")
async def public_all_live_sse() -> StreamingResponse:
    """SSE stream of all live positions from every device."""
    queue = subscribe_global()

    async def event_stream():
        try:
            # Intentionally no snapshot event here — clients should call
            # /api/public/live/all/positions separately to backfill history.
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    event_type = (
                        message.pop("event", "position")
                        if isinstance(message, dict)
                        else "position"
                    )
                    yield f"event: {event_type}\ndata: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            unsubscribe_global(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/live/all/positions", response_model=list[PublicPositionResponse])
def public_all_positions(
    minutes: int = 60,
    limit: int = 10000,
    session: Session = Depends(get_session),
) -> list[PublicPositionResponse]:
    """Return every position record in the last `minutes` minutes across all pilots/tasks."""
    # Clamp inputs to sane ranges
    minutes = max(1, min(minutes, 24 * 60))
    limit = max(1, min(limit, 10000))
    rows = get_all_recent_positions(session, minutes=minutes, limit=limit)
    return [PublicPositionResponse(**row) for row in rows]
