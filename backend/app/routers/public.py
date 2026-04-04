from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Event, EventPilot, Pilot, ScoreResult, Task
from app.routers.events import _event_payload
from app.routers.tasks import _task_response
from app.schemas import EventResponse, PilotSummaryResponse, ScoreResultResponse, TaskResponse
from app.services.scoring import build_result_payload

router = APIRouter(prefix="/api/public", tags=["public"])


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
