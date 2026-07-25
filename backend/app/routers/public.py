from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import UTC, date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import (
    BuddyGroup,
    BuddyGroupMember,
    AirspaceRegion,
    AirspaceSource,
    DriverAssignment,
    Event,
    EventPilot,
    IGCUpload,
    Pilot,
    ScoreResult,
    SiteSettings,
    Task,
    TaskPoint,
    TrackPoint,
    User,
)
from app.routers.events import _event_payload
from app.routers.site_settings import DEFAULT_AIRSPACE_CATEGORIES, normalize_airspace_categories
from app.routers.tasks import _task_response
from app.schemas import AirspaceRegionResponse, EventResponse, MeetStatsResponse, PilotSummaryResponse, ScoreResultResponse, TaskResponse, TaskResultSummaryResponse
from app.services.replay_tracks import DEFAULT_REPLAY_MAX_POINTS, simplify_replay_points
from app.services.scoring import MEET_STATS_SCOPE_PUBLIC, build_cached_meet_stats_payload, build_result_payload
from app.services.tracking import (
    _current_local_date,
    get_live_positions,
    get_live_positions_for_pilots,
    get_live_positions_for_subjects,
    get_position_history,
    get_position_history_for_pilots,
    get_position_history_for_subjects,
    subscribe,
    subscribe_pilots,
    subscribe_subjects,
    unsubscribe,
    unsubscribe_pilots,
    unsubscribe_subjects,
)

router = APIRouter(prefix="/api/public", tags=["public"])
logger = logging.getLogger("aervyx.public")

DISPLAY_STATUS_ORDER = {"did_not_fly": 1, "absent": 2}


class PublicSiteSettingsResponse(BaseModel):
    max_map_pitch_degrees: int
    public_airspace_categories_json: list[str]


@router.get("/site-settings", response_model=PublicSiteSettingsResponse)
def get_public_site_settings(session: Session = Depends(get_session)) -> PublicSiteSettingsResponse:
    settings = session.get(SiteSettings, 1)
    value = settings.max_map_pitch_degrees if settings is not None else 75
    categories = normalize_airspace_categories(settings.public_airspace_categories_json if settings is not None else None)
    return PublicSiteSettingsResponse(
        max_map_pitch_degrees=max(0, min(90, int(value))),
        public_airspace_categories_json=categories or list(DEFAULT_AIRSPACE_CATEGORIES),
    )


def _task_result_sort_key(row: ScoreResultResponse) -> tuple:
    if row.result_state == "unscored":
        return (3, 0, 10**9, row.pilot_name.lower())
    status_bucket = DISPLAY_STATUS_ORDER.get(row.status)
    if status_bucket is not None:
        return (status_bucket, 0, row.rank if row.rank is not None else 10**9, row.pilot_name.lower())
    return (0, -float(row.score_points or 0), row.rank if row.rank is not None else 10**9, row.pilot_name.lower())


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
    map_task: PublicTaskSummary | None = None
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
    airspaces: list[AirspaceRegionResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Existing public endpoints
# ---------------------------------------------------------------------------

@router.get("/events", response_model=list[EventResponse])
def list_public_events(session: Session = Depends(get_session)) -> list[EventResponse]:
    events = session.scalars(
        select(Event)
        .where(Event.visibility == "public")
        .order_by(Event.starts_on.desc(), Event.ends_on.desc(), Event.name.asc())
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
        .order_by(Task.is_practice.desc(), Task.task_date.is_(None).asc(), Task.task_date.asc(), Task.id.asc())
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
    visible_results = session.scalars(
        select(ScoreResult)
        .where(ScoreResult.task_id == task_id)
        .order_by(ScoreResult.rank.asc().nullslast(), ScoreResult.score_points.desc())
    ).all()
    results_by_pilot = {result.pilot_id: result for result in visible_results}
    pilot_rows = session.execute(
        select(Pilot, EventPilot.pilot_class)
        .join(EventPilot, EventPilot.pilot_id == Pilot.id)
        .where(EventPilot.event_id == task.event_id)
        .order_by(Pilot.last_name.asc(), Pilot.first_name.asc())
    ).all()

    rows: list[ScoreResultResponse] = []
    for pilot, pilot_class in pilot_rows:
        result = results_by_pilot.get(pilot.id)
        if result is not None:
            rows.append(ScoreResultResponse(**build_result_payload(session, result)))
            continue
        rows.append(
            ScoreResultResponse(
                id=-pilot.id,
                task_id=task_id,
                pilot_id=pilot.id,
                upload_id=None,
                pilot_name=f"{pilot.first_name} {pilot.last_name}".strip(),
                competition_number=pilot.competition_number,
                status="unscored",
                rank=None,
                distance_flown_km=0.0,
                started_at=None,
                ess_at=None,
                goal_at=None,
                elapsed_seconds=None,
                raw_score_points=0.0,
                score_points=0.0,
                details_json={},
                result_state="unscored",
                pilot_class=pilot_class,
            )
        )

    return sorted(rows, key=_task_result_sort_key)


@router.get("/uploads/{upload_id}/track")
def get_public_upload_track(
    upload_id: int,
    detail: str = Query(default="replay"),
    max_points: int = Query(default=DEFAULT_REPLAY_MAX_POINTS, ge=2, le=100000),
    session: Session = Depends(get_session),
) -> dict:
    upload = session.get(IGCUpload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    public_result_id = session.scalar(
        select(ScoreResult.id)
        .join(Task, Task.id == ScoreResult.task_id)
        .join(Event, Event.id == Task.event_id)
        .where(
            ScoreResult.upload_id == upload.id,
            ScoreResult.task_id == upload.task_id,
            ScoreResult.pilot_id == upload.pilot_id,
            ScoreResult.result_state.in_(("official", "provisional")),
            Task.status == "published",
            Event.visibility == "public",
        )
        .limit(1)
    )
    if public_result_id is None:
        raise HTTPException(status_code=404, detail="Upload not found")

    pilot = session.get(Pilot, upload.pilot_id)
    pilot_user = session.scalar(select(User).where(User.pilot_id == upload.pilot_id).order_by(User.id.asc()))
    aircraft_icon = (pilot_user.aircraft_icon or "hang_glider").strip().lower() if pilot_user is not None else "hang_glider"
    if aircraft_icon not in {"hang_glider", "paraglider", "sailplane"}:
        aircraft_icon = "hang_glider"
    points = session.scalars(select(TrackPoint).where(TrackPoint.upload_id == upload_id).order_by(TrackPoint.sequence)).all()
    task_points = session.scalars(select(TaskPoint).where(TaskPoint.task_id == upload.task_id).order_by(TaskPoint.position)).all()
    simplified = simplify_replay_points(points, task_points=task_points, max_points=max_points) if detail != "full" else None
    replay_points = simplified.points if simplified is not None else points
    coordinates = [
        [
            point.longitude,
            point.latitude,
            float(point.gps_altitude_m if point.gps_altitude_m is not None else point.pressure_altitude_m if point.pressure_altitude_m is not None else 0),
        ]
        for point in replay_points
    ]
    timestamps = []
    for point in replay_points:
        recorded_at = point.recorded_at if point.recorded_at.tzinfo else point.recorded_at.replace(tzinfo=UTC)
        timestamps.append(recorded_at.astimezone(UTC).isoformat().replace("+00:00", "Z"))
    return {
        "type": "FeatureCollection",
        "metadata": {
            "detail": "full" if detail == "full" else "replay",
            "original_point_count": len(points),
            "returned_point_count": len(replay_points),
            "max_points": max_points,
            "simplified": simplified.simplified if simplified is not None else False,
            "task_aware": simplified.task_aware if simplified is not None else bool(task_points),
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "upload_id": upload.id,
                    "pilot_name": f"{pilot.first_name} {pilot.last_name}" if pilot else "Unknown",
                    "aircraft_icon": aircraft_icon,
                    "timestamps": timestamps,
                    "line_style": "solid",
                    "track_kind": "igc",
                },
                "geometry": {"type": "LineString", "coordinates": coordinates},
            }
        ],
    }


def _gap_day_quality(details_json: dict | None) -> float | None:
    if not isinstance(details_json, dict):
        return None
    gap = details_json.get("gap")
    if not isinstance(gap, dict):
        return None
    validity = gap.get("validity")
    if not isinstance(validity, dict):
        return None
    try:
        value = float(validity.get("overall"))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _gap_task_statistics(details_json: dict | None) -> dict:
    if not isinstance(details_json, dict):
        return {}
    gap = details_json.get("gap")
    if not isinstance(gap, dict):
        return {}
    stats: dict = {}
    task_stats = gap.get("task_stats")
    if isinstance(task_stats, dict):
        stats.update(task_stats)
    available_points = gap.get("available_points")
    if isinstance(available_points, dict):
        for key, value in available_points.items():
            stats[f"available_points_{key}"] = value
    validity = gap.get("validity")
    if isinstance(validity, dict):
        validity_keys = {
            "launch": "launch_validity",
            "distance": "distance_validity",
            "time": "time_validity",
            "stopped": "stop_validity",
            "overall": "day_quality",
        }
        for key, label in validity_keys.items():
            if key in validity:
                stats[label] = validity[key]
    formula = gap.get("formula")
    if isinstance(formula, dict):
        formula_keys = {
            "weightarrival": "arrival_weight",
            "weightstart": "leading_weight",
            "weightspeed": "time_weight",
            "weightdist": "distance_weight",
        }
        for key, label in formula_keys.items():
            if key in formula:
                stats[label] = formula[key]
    leading_coefficients = gap.get("leading_coefficients")
    if isinstance(leading_coefficients, dict) and "minimum" in leading_coefficients:
        stats["smallest_leading_coefficient"] = leading_coefficients["minimum"]
    return stats


@router.get("/events/{event_id}/task-result-summary", response_model=list[TaskResultSummaryResponse])
def public_task_result_summary(event_id: int, session: Session = Depends(get_session)) -> list[TaskResultSummaryResponse]:
    event = session.get(Event, event_id)
    if event is None or event.visibility != "public":
        raise HTTPException(status_code=404, detail="Event not found")
    rows = session.execute(
        select(ScoreResult.task_id, ScoreResult.details_json)
        .join(Task, Task.id == ScoreResult.task_id)
        .where(
            Task.event_id == event_id,
            Task.status == "published",
        )
        .order_by(ScoreResult.task_id.asc(), ScoreResult.rank.asc().nullslast(), ScoreResult.score_points.desc())
    ).all()

    summaries_by_task: dict[int, dict] = {}
    for task_id, details_json in rows:
        task_id_int = int(task_id)
        summary = summaries_by_task.setdefault(task_id_int, {"day_quality": None, "statistics": {}})
        day_quality = _gap_day_quality(details_json)
        if summary["day_quality"] is None and day_quality is not None:
            summary["day_quality"] = day_quality
        if not summary["statistics"]:
            summary["statistics"] = _gap_task_statistics(details_json)

    return [
        TaskResultSummaryResponse(task_id=task_id, day_quality=summary["day_quality"], statistics=summary["statistics"])
        for task_id, summary in sorted(summaries_by_task.items())
    ]


@router.get("/events/{event_id}/meet-stats", response_model=MeetStatsResponse)
def public_meet_stats(event_id: int, session: Session = Depends(get_session)) -> MeetStatsResponse:
    event = session.get(Event, event_id)
    if event is None or event.visibility != "public":
        raise HTTPException(status_code=404, detail="Event not found")
    payload = build_cached_meet_stats_payload(session, event_id, MEET_STATS_SCOPE_PUBLIC, published_tasks_only=True)
    session.commit()
    return MeetStatsResponse(**payload)


@router.get("/events/{event_id}/pilot-summary", response_model=list[PilotSummaryResponse])
def public_pilot_summary(event_id: int, session: Session = Depends(get_session)) -> list[PilotSummaryResponse]:
    event = session.get(Event, event_id)
    if event is None or event.visibility != "public":
        raise HTTPException(status_code=404, detail="Event not found")
    memberships = session.scalars(select(EventPilot).where(EventPilot.event_id == event_id)).all()
    pilot_ids = [membership.pilot_id for membership in memberships]
    pilot_classes = {membership.pilot_id: membership.pilot_class for membership in memberships}
    task_rows = session.execute(select(Task.id, Task.is_practice).where(Task.event_id == event_id, Task.status == "published")).all()
    published_task_ids = [int(task_id) for task_id, _is_practice in task_rows]
    competition_task_ids = [int(task_id) for task_id, is_practice in task_rows if not is_practice]
    summaries: list[PilotSummaryResponse] = []
    for pilot_id in pilot_ids:
        pilot = session.get(Pilot, pilot_id)
        task_scores = {
            int(task_id): float(score_points or 0)
            for task_id, score_points in session.execute(
                select(ScoreResult.task_id, ScoreResult.score_points)
                .where(
                    ScoreResult.task_id.in_(published_task_ids),
                    ScoreResult.pilot_id == pilot_id,
                )
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
            .where(
                ScoreResult.task_id.in_(published_task_ids),
                ScoreResult.task_id.in_(competition_task_ids),
                ScoreResult.pilot_id == pilot_id,
            )
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
                task_result_states={
                    int(task_id): str(result_state or "official")
                    for task_id, result_state in session.execute(
                        select(ScoreResult.task_id, ScoreResult.result_state)
                        .where(
                            ScoreResult.task_id.in_(published_task_ids),
                            ScoreResult.pilot_id == pilot_id,
                        )
                        .order_by(ScoreResult.task_id.asc())
                    ).all()
                },
                task_statuses={
                    int(task_id): str(result_status or "")
                    for task_id, result_status in session.execute(
                        select(ScoreResult.task_id, ScoreResult.status)
                        .where(
                            ScoreResult.task_id.in_(published_task_ids),
                            ScoreResult.pilot_id == pilot_id,
                        )
                        .order_by(ScoreResult.task_id.asc())
                    ).all()
                },
                pilot_class=pilot_classes[pilot_id],
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
        map_task = _select_public_event_map_task(tasks, _current_local_date(event.timezone))
        event_summaries.append(
            PublicEventSummary(
                id=event.id,
                name=event.name,
                location=event.location,
                starts_on=event.starts_on.isoformat(),
                ends_on=event.ends_on.isoformat(),
                timezone=event.timezone,
                map_task=_public_task_summary(map_task) if map_task else None,
                tasks=[_public_task_summary(task) for task in tasks],
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


def _public_task_summary(task: Task) -> PublicTaskSummary:
    return PublicTaskSummary(
        id=task.id,
        name=task.name,
        status=task.status,
        task_date=task.task_date.isoformat() if task.task_date else None,
    )


def _select_public_event_map_task(tasks: list[Task], today: date) -> Task | None:
    if not tasks:
        return None

    def priority(task: Task) -> tuple[int, int, int]:
        if task.status == "active":
            return (0, -(task.task_date or date.min).toordinal(), -task.id)
        if task.task_date == today:
            return (1, 0, -task.id)
        if task.task_date is not None and task.task_date > today:
            return (2, (task.task_date - today).days, task.id)
        if task.task_date is not None:
            return (3, (today - task.task_date).days, -task.id)
        return (4, 0, -task.id)

    return min(tasks, key=priority)


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


def _public_registered_pilot_ids(session: Session, pilot_ids: list[int] | None = None) -> list[int]:
    query = (
        select(User.pilot_id)
        .where(
            User.is_active.is_(True),
            User.profile_type != "stationary_node",
            User.pilot_id.is_not(None),
        )
        .order_by(User.pilot_id.asc())
        .distinct()
    )
    if pilot_ids is not None:
        if not pilot_ids:
            return []
        query = query.where(User.pilot_id.in_(pilot_ids))
    return [pid for pid in session.scalars(query).all() if pid is not None]


def _public_registered_user_ids(session: Session, user_ids: list[int] | None = None) -> list[int]:
    query = (
        select(User.id)
        .where(
            User.is_active.is_(True),
            User.profile_type != "stationary_node",
        )
        .order_by(User.id.asc())
        .distinct()
    )
    if user_ids is not None:
        if not user_ids:
            return []
        query = query.where(User.id.in_(user_ids))
    return list(session.scalars(query).all())


def _public_registered_user_ids_for_pilots(session: Session, pilot_ids: list[int]) -> list[int]:
    if not pilot_ids:
        return []
    return list(
        session.scalars(
            select(User.id)
            .where(
                User.is_active.is_(True),
                User.profile_type != "stationary_node",
                User.pilot_id.in_(pilot_ids),
            )
            .order_by(User.id.asc())
            .distinct()
        ).all()
    )


def _public_event_user_ids(session: Session, event_id: int, pilot_ids: list[int]) -> list[int]:
    pilot_user_ids = set(_public_registered_user_ids_for_pilots(session, pilot_ids))
    driver_user_ids = set(_public_registered_user_ids(session, _public_event_driver_user_ids(event_id, session)))
    return sorted(pilot_user_ids | driver_user_ids)


def _public_registered_live_subject_ids(session: Session) -> tuple[list[int], list[int]]:
    """Return live subject IDs that are safe for anonymous public tracking."""
    return _public_registered_pilot_ids(session), _public_registered_user_ids(session)


def _public_position_payload_allowed(
    payload: dict,
    *,
    pilot_ids: list[int],
    user_ids: list[int],
) -> bool:
    pilot_id = payload.get("pilot_id")
    user_id = payload.get("user_id")
    return (pilot_id is not None and pilot_id in pilot_ids) or (user_id is not None and user_id in user_ids)


def _public_event_driver_user_ids(event_id: int, session: Session) -> list[int]:
    return list(
        session.scalars(
            select(DriverAssignment.driver_user_id)
            .join(Task, Task.id == DriverAssignment.task_id)
            .where(Task.event_id == event_id)
            .order_by(DriverAssignment.driver_user_id.asc())
            .distinct()
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
    pilot_ids = _public_registered_pilot_ids(session, _public_event_pilot_ids(event_id, session))
    user_ids = _public_event_user_ids(session, event_id, pilot_ids)

    queue = subscribe_subjects(pilot_ids, user_ids)

    async def event_stream():
        try:
            snapshot = get_live_positions_for_subjects(session, pilot_ids, user_ids)
            yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"

            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    event_type = message.pop("event", "position") if isinstance(message, dict) else "position"
                    yield f"event: {event_type}\ndata: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            unsubscribe_subjects(pilot_ids, user_ids, queue)

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
    minutes: Annotated[int | None, Query(ge=1, le=24 * 60)] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    session: Session = Depends(get_session),
) -> list[PublicPositionResponse]:
    """Position history for all pilots in a publicly-tracked event."""
    _get_public_event(event_id, session)
    pilot_ids = _public_registered_pilot_ids(session, _public_event_pilot_ids(event_id, session))
    user_ids = _public_event_user_ids(session, event_id, pilot_ids)
    if not pilot_ids and not user_ids:
        return []

    rows = get_position_history_for_subjects(
        session,
        pilot_ids,
        user_ids,
        minutes=minutes,
        limit=limit,
        include_received_app_timestamp_fallback=True,
    )
    return [PublicPositionResponse(**row) for row in rows]


@router.get("/live/task/{task_id}")
async def public_task_live_sse(
    task_id: int,
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """SSE stream of live positions for a publicly-tracked task."""
    task = _get_public_task(task_id, session)
    pilot_ids = _public_registered_pilot_ids(session, _public_event_pilot_ids(task.event_id, session))
    user_ids = _public_event_user_ids(session, task.event_id, pilot_ids)

    queue = subscribe(task_id)

    async def event_stream():
        try:
            snapshot = [
                row
                for row in get_live_positions(session, task_id)
                if _public_position_payload_allowed(row, pilot_ids=pilot_ids, user_ids=user_ids)
            ]
            yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"

            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    if isinstance(message, dict) and not _public_position_payload_allowed(
                        message,
                        pilot_ids=pilot_ids,
                        user_ids=user_ids,
                    ):
                        continue
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
    """Current-day position history for a publicly-tracked task."""
    task = _get_public_task(task_id, session)
    pilot_ids = _public_registered_pilot_ids(session, _public_event_pilot_ids(task.event_id, session))
    user_ids = _public_event_user_ids(session, task.event_id, pilot_ids)
    rows = get_position_history(session, task_id)
    rows = [
        row
        for row in rows
        if _public_position_payload_allowed(row, pilot_ids=pilot_ids, user_ids=user_ids)
    ]
    return [PublicPositionResponse(**row) for row in rows]


@router.get("/live/task/{task_id}/info", response_model=PublicTaskInfoResponse)
def public_task_info(
    task_id: int,
    session: Session = Depends(get_session),
) -> PublicTaskInfoResponse:
    """Task metadata and turnpoints for map rendering."""
    task = _get_public_task(task_id, session)
    event = session.get(Event, task.event_id)

    task_points = session.scalars(
        select(TaskPoint)
        .where(TaskPoint.task_id == task_id)
        .order_by(TaskPoint.position.asc())
    ).all()
    enabled_source_ids = set(session.scalars(
        select(AirspaceSource.id).where(
            AirspaceSource.event_id == task.event_id,
            AirspaceSource.enabled.is_(True),
        )
    ).all())
    visible_classes = set(event.visible_airspace_classes_json or ["B", "C", "D", "P", "Q", "R", "TFR", "OTHER"]) if event else set()
    show_restricted_fields = True if event is None or event.show_restricted_fields is None else event.show_restricted_fields
    airspace_regions = []
    if enabled_source_ids:
        regions = session.scalars(
            select(AirspaceRegion)
            .where(AirspaceRegion.event_id == task.event_id)
            .order_by(AirspaceRegion.is_restricted_field.asc(), AirspaceRegion.name.asc())
        ).all()
        airspace_regions = [
            region
            for region in regions
            if region.source_id in enabled_source_ids
            and (
                show_restricted_fields
                if region.is_restricted_field
                else region.display_category in visible_classes
            )
        ]

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
        airspaces=[AirspaceRegionResponse.model_validate(region) for region in airspace_regions],
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
    pilot_ids = _public_registered_pilot_ids(session, list(pilot_ids))

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
    minutes: Annotated[int | None, Query(ge=1, le=24 * 60)] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    session: Session = Depends(get_session),
) -> list[PublicPositionResponse]:
    """Current-day position history for all pilots in a public buddy group."""
    group = _get_public_buddy_group(group_id, session)

    pilot_ids = session.scalars(
        select(BuddyGroupMember.pilot_id).where(BuddyGroupMember.group_id == group.id)
    ).all()
    pilot_ids = _public_registered_pilot_ids(session, list(pilot_ids))

    if not pilot_ids:
        return []
    rows = get_position_history_for_pilots(session, pilot_ids, minutes=minutes, limit=limit)
    return [PublicPositionResponse(**row) for row in rows]


# ---------------------------------------------------------------------------
# All-users live tracking endpoints
# ---------------------------------------------------------------------------
# These endpoints intentionally back the "All users" option on the public
# Watch Live page.

@router.get("/live/all")
async def public_all_live_sse(session: Session = Depends(get_session)) -> StreamingResponse:
    """SSE stream of live positions for registered public users."""
    pilot_ids, user_ids = _public_registered_live_subject_ids(session)
    queue = subscribe_subjects(pilot_ids, user_ids)

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
            unsubscribe_subjects(pilot_ids, user_ids, queue)

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
    minutes: Annotated[int | None, Query(ge=1, le=24 * 60)] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    session: Session = Depends(get_session),
) -> list[PublicPositionResponse]:
    """Return retained current-day position records for registered public users."""
    pilot_ids, user_ids = _public_registered_live_subject_ids(session)
    rows = get_position_history_for_subjects(
        session,
        pilot_ids,
        user_ids,
        minutes=minutes,
        limit=limit,
        include_received_app_timestamp_fallback=True,
    )
    return [PublicPositionResponse(**row) for row in rows]
