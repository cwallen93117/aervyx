from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_user, require_staff
from app.models import Event, IGCUpload, ScorePenalty, ScoreResult, Task, TaskPoint, TaskScoringInput, TrackPoint, Turnpoint, TurnpointSource, User
from app.schemas import TaskInput, TaskPointResponse, TaskResponse, default_task_point_direction, default_task_point_radius_m
from app.services.audit import log_action

router = APIRouter(tags=["tasks"])


def _normalize_task_type(task_type: str | None) -> str:
    legacy_map = {
        None: "race_to_goal_with_gates",
        "race": "race_to_goal_with_gates",
        "race_to_goal": "race_to_goal_with_gates",
        "speedrun": "elapsed_time",
        "speedrun_interval": "race_to_goal_with_gates",
    }
    return legacy_map.get(task_type, task_type)  # type: ignore[arg-type]


def _uses_independent_start_open(task_type: str | None) -> bool:
    return _normalize_task_type(task_type) == "race_to_goal_with_gates"


def _task_start_open_for_response(task: Task) -> str | None:
    if _uses_independent_start_open(task.task_type):
        return task.start_open_time
    return task.task_start_time or task.start_open_time


def _start_open_for_storage(task_type: str | None, start_open_time: str | None) -> str | None:
    return start_open_time if _uses_independent_start_open(task_type) else None


def _normalize_task_point_direction(direction: str | None, point_type: str) -> str:
    return direction if direction in {"enter", "exit"} else default_task_point_direction(point_type)


def _normalize_task_point_radius(radius_m: float | None, point_type: str) -> float:
    return radius_m if radius_m is not None and radius_m > 0 else default_task_point_radius_m(point_type)


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
    task_type = _normalize_task_type(task.task_type)
    return TaskResponse(
        id=task.id,
        event_id=task.event_id,
        name=task.name,
        task_date=task.task_date,
        is_practice=bool(task.is_practice),
        status=task.status,
        task_type=task_type,
        task_start_time=task.task_start_time,
        task_finish_time=task.task_finish_time,
        start_open_time=_task_start_open_for_response(task),
        start_close_time=task.start_close_time,
        start_gate_count=task.start_gate_count or 1,
        start_gate_interval_seconds=task.start_gate_interval_seconds,
        version=task.version,
        published_at=task.published_at,
        points=[
            TaskPointResponse(
                id=point.id,
                position=point.position,
                point_type=point.point_type,
                direction=_normalize_task_point_direction(point.direction, point.point_type),
                radius_m=point.radius_m,
                turnpoint_id=point.turnpoint_id,
                name=point.name,
                latitude=point.latitude,
                longitude=point.longitude,
            )
            for point in points
        ],
    )


@router.get("/api/events/{event_id}/tasks", response_model=list[TaskResponse])
def list_tasks(event_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[TaskResponse]:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    tasks = session.scalars(
        select(Task)
        .where(Task.event_id == event_id)
        .order_by(Task.is_practice.desc(), Task.task_date.is_(None).asc(), Task.task_date.asc(), Task.id.asc())
    ).all()
    return [_task_response(session, task) for task in tasks]


@router.post("/api/events/{event_id}/tasks", response_model=TaskResponse)
def create_task(event_id: int, payload: TaskInput, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> TaskResponse:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    task_type = _normalize_task_type(payload.task_type)
    task = Task(
        event_id=event_id,
        name=payload.name,
        task_date=payload.task_date,
        is_practice=payload.is_practice,
        status=payload.status,
        task_type=task_type,
        task_start_time=payload.task_start_time,
        task_finish_time=payload.task_finish_time,
        start_open_time=_start_open_for_storage(task_type, payload.start_open_time),
        start_close_time=payload.start_close_time,
        start_gate_count=payload.start_gate_count,
        start_gate_interval_seconds=payload.start_gate_interval_seconds,
    )
    session.add(task)
    session.flush()
    for point in payload.points:
        point_data = point.model_dump()
        point_data["direction"] = _normalize_task_point_direction(point_data.get("direction"), point_data["point_type"])
        point_data["radius_m"] = _normalize_task_point_radius(point_data.get("radius_m"), point_data["point_type"])
        session.add(TaskPoint(task_id=task.id, **point_data))
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
def update_task(task_id: int, payload: TaskInput, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> TaskResponse:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task_type = _normalize_task_type(payload.task_type)
    task.name = payload.name
    task.task_date = payload.task_date
    task.is_practice = payload.is_practice
    task.status = payload.status
    task.task_type = task_type
    task.task_start_time = payload.task_start_time
    task.task_finish_time = payload.task_finish_time
    task.start_open_time = _start_open_for_storage(task_type, payload.start_open_time)
    task.start_close_time = payload.start_close_time
    task.start_gate_count = payload.start_gate_count
    task.start_gate_interval_seconds = payload.start_gate_interval_seconds
    task.version += 1
    session.query(TaskPoint).filter(TaskPoint.task_id == task.id).delete()
    session.flush()
    for point in payload.points:
        point_data = point.model_dump()
        point_data["direction"] = _normalize_task_point_direction(point_data.get("direction"), point_data["point_type"])
        point_data["radius_m"] = _normalize_task_point_radius(point_data.get("radius_m"), point_data["point_type"])
        session.add(TaskPoint(task_id=task.id, **point_data))
    log_action(session, actor_user_id=admin.id, action="task.update", entity_type="task", entity_id=str(task.id), details={"version": task.version, "point_count": len(payload.points)})
    session.commit()
    return _task_response(session, task)


@router.post("/api/tasks/{task_id}/publish", response_model=TaskResponse)
def publish_task(task_id: int, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> TaskResponse:
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
def unpublish_task(task_id: int, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> TaskResponse:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    session.execute(delete(ScoreResult).where(ScoreResult.task_id == task_id))
    session.execute(delete(ScorePenalty).where(ScorePenalty.task_id == task_id))
    session.query(TaskScoringInput).where(TaskScoringInput.task_id == task_id).update(
        {
            TaskScoringInput.selected_upload_id: None,
            TaskScoringInput.status_override: None,
        },
        synchronize_session=False,
    )
    task.status = "draft"
    task.published_at = None
    task.version += 1
    log_action(
        session,
        actor_user_id=admin.id,
        action="task.unpublish",
        entity_type="task",
        entity_id=str(task.id),
        details={"version": task.version, "cleared_scoring": True},
    )
    session.commit()
    return _task_response(session, task)


@router.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> None:
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
