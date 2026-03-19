from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_user, require_admin
from app.models import Event, IGCUpload, ScoreResult, Task, TaskPoint, TrackPoint, Turnpoint, TurnpointSource, User
from app.schemas import TaskInput, TaskPointResponse, TaskResponse
from app.services.audit import log_action

router = APIRouter(tags=["tasks"])


def _normalize_task_type(task_type: str | None) -> str:
    legacy_map = {
        None: "race_to_goal",
        "race": "race_to_goal",
        "speedrun": "elapsed_time",
        "speedrun_interval": "race_to_goal_with_gates",
    }
    return legacy_map.get(task_type, task_type)  # type: ignore[arg-type]


def _enabled_turnpoint_source_ids(session: Session, event_id: int) -> set[int]:
    return set(
        session.scalars(
            select(TurnpointSource.id).where(
                TurnpointSource.event_id == event_id,
                TurnpointSource.enabled.is_(True),
            )
        ).all()
    )


def _task_points_for_response(session: Session, task: Task) -> list[TaskPoint]:
    points = session.scalars(select(TaskPoint).where(TaskPoint.task_id == task.id).order_by(TaskPoint.position)).all()
    source_ids = set(session.scalars(select(TurnpointSource.id).where(TurnpointSource.event_id == task.event_id)).all())
    active_source_ids = _enabled_turnpoint_source_ids(session, task.event_id)
    if source_ids and not active_source_ids:
        return [point for point in points if point.turnpoint_id is None]
    if not active_source_ids:
        return points

    turnpoint_source_by_id = {
        turnpoint_id: source_id
        for turnpoint_id, source_id in session.execute(
            select(Turnpoint.id, Turnpoint.source_id).where(Turnpoint.id.in_([point.turnpoint_id for point in points if point.turnpoint_id is not None]))
        ).all()
    }
    return [
        point
        for point in points
        if point.turnpoint_id is None or turnpoint_source_by_id.get(point.turnpoint_id) in active_source_ids
    ]


def _task_response(session: Session, task: Task) -> TaskResponse:
    points = _task_points_for_response(session, task)
    return TaskResponse(
        id=task.id,
        event_id=task.event_id,
        name=task.name,
        status=task.status,
        task_type=_normalize_task_type(task.task_type),
        task_start_time=task.task_start_time,
        task_finish_time=task.task_finish_time,
        start_open_time=task.start_open_time,
        start_close_time=task.start_close_time,
        start_gate_count=task.start_gate_count or 1,
        start_gate_interval_seconds=task.start_gate_interval_seconds,
        version=task.version,
        nominal_distance_km=task.nominal_distance_km,
        nominal_time_hours=task.nominal_time_hours,
        nominal_launch=task.nominal_launch,
        minimum_distance_km=task.minimum_distance_km,
        penalties_json=task.penalties_json,
        published_at=task.published_at,
        points=[TaskPointResponse(id=point.id, position=point.position, point_type=point.point_type, radius_m=point.radius_m, turnpoint_id=point.turnpoint_id, name=point.name, latitude=point.latitude, longitude=point.longitude) for point in points],
    )


@router.get("/api/events/{event_id}/tasks", response_model=list[TaskResponse])
def list_tasks(event_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[TaskResponse]:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    tasks = session.scalars(select(Task).where(Task.event_id == event_id).order_by(Task.created_at.asc())).all()
    return [_task_response(session, task) for task in tasks]


@router.post("/api/events/{event_id}/tasks", response_model=TaskResponse)
def create_task(event_id: int, payload: TaskInput, admin: User = Depends(require_admin), session: Session = Depends(get_session)) -> TaskResponse:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    task = Task(
        event_id=event_id,
        name=payload.name,
        status=payload.status,
        task_type=_normalize_task_type(payload.task_type),
        task_start_time=payload.task_start_time,
        task_finish_time=payload.task_finish_time,
        start_open_time=payload.start_open_time,
        start_close_time=payload.start_close_time,
        start_gate_count=payload.start_gate_count,
        start_gate_interval_seconds=payload.start_gate_interval_seconds,
        nominal_distance_km=payload.nominal_distance_km,
        nominal_time_hours=payload.nominal_time_hours,
        nominal_launch=payload.nominal_launch,
        minimum_distance_km=payload.minimum_distance_km,
        penalties_json=payload.penalties_json,
    )
    session.add(task)
    session.flush()
    for point in payload.points:
        session.add(TaskPoint(task_id=task.id, **point.model_dump()))
    log_action(session, actor_user_id=admin.id, action="task.create", entity_type="task", entity_id=str(task.id), details={"event_id": event_id, "point_count": len(payload.points)})
    session.commit()
    return _task_response(session, task)


@router.get("/api/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> TaskResponse:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_response(session, task)


@router.put("/api/tasks/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, payload: TaskInput, admin: User = Depends(require_admin), session: Session = Depends(get_session)) -> TaskResponse:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task.name = payload.name
    task.status = payload.status
    task.task_type = _normalize_task_type(payload.task_type)
    task.task_start_time = payload.task_start_time
    task.task_finish_time = payload.task_finish_time
    task.start_open_time = payload.start_open_time
    task.start_close_time = payload.start_close_time
    task.start_gate_count = payload.start_gate_count
    task.start_gate_interval_seconds = payload.start_gate_interval_seconds
    task.nominal_distance_km = payload.nominal_distance_km
    task.nominal_time_hours = payload.nominal_time_hours
    task.nominal_launch = payload.nominal_launch
    task.minimum_distance_km = payload.minimum_distance_km
    task.penalties_json = payload.penalties_json
    task.version += 1
    session.query(TaskPoint).filter(TaskPoint.task_id == task.id).delete()
    session.flush()
    for point in payload.points:
        session.add(TaskPoint(task_id=task.id, **point.model_dump()))
    log_action(session, actor_user_id=admin.id, action="task.update", entity_type="task", entity_id=str(task.id), details={"version": task.version, "point_count": len(payload.points)})
    session.commit()
    return _task_response(session, task)


@router.post("/api/tasks/{task_id}/publish", response_model=TaskResponse)
def publish_task(task_id: int, admin: User = Depends(require_admin), session: Session = Depends(get_session)) -> TaskResponse:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "published"
    task.published_at = datetime.now(UTC)
    task.version += 1
    log_action(session, actor_user_id=admin.id, action="task.publish", entity_type="task", entity_id=str(task.id), details={"version": task.version})
    session.commit()
    return _task_response(session, task)


@router.post("/api/tasks/{task_id}/unpublish", response_model=TaskResponse)
def unpublish_task(task_id: int, admin: User = Depends(require_admin), session: Session = Depends(get_session)) -> TaskResponse:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "draft"
    task.published_at = None
    task.version += 1
    log_action(session, actor_user_id=admin.id, action="task.unpublish", entity_type="task", entity_id=str(task.id), details={"version": task.version})
    session.commit()
    return _task_response(session, task)


@router.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, admin: User = Depends(require_admin), session: Session = Depends(get_session)) -> None:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task_name = task.name
    event_id = task.event_id
    upload_ids = session.scalars(select(IGCUpload.id).where(IGCUpload.task_id == task.id)).all()
    if upload_ids:
        session.query(TrackPoint).filter(TrackPoint.upload_id.in_(upload_ids)).delete(synchronize_session=False)
    session.query(ScoreResult).filter(ScoreResult.task_id == task.id).delete(synchronize_session=False)
    session.query(IGCUpload).filter(IGCUpload.task_id == task.id).delete(synchronize_session=False)
    session.query(TaskPoint).filter(TaskPoint.task_id == task.id).delete(synchronize_session=False)
    session.delete(task)
    log_action(
        session,
        actor_user_id=admin.id,
        action="task.delete",
        entity_type="task",
        entity_id=str(task_id),
        details={"name": task_name, "event_id": event_id},
    )
    session.commit()
