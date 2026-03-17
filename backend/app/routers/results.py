from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_user, require_admin
from app.models import EventPilot, Pilot, ScoreResult, Task, User
from app.schemas import PilotSummaryResponse, ScoreResultResponse
from app.services.audit import log_action
from app.services.scoring import build_result_payload, rescore_task

router = APIRouter(tags=["results"])


@router.get("/api/tasks/{task_id}/results", response_model=list[ScoreResultResponse])
def get_task_results(task_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[ScoreResultResponse]:
    if session.get(Task, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    query = select(ScoreResult).where(ScoreResult.task_id == task_id).order_by(ScoreResult.rank.asc().nullslast(), ScoreResult.score_points.desc())
    if user.role == "pilot":
        query = query.where(ScoreResult.pilot_id == user.pilot_id)
    results = session.scalars(query).all()
    return [ScoreResultResponse(**build_result_payload(session, result)) for result in results]


@router.post("/api/tasks/{task_id}/rescore", response_model=list[ScoreResultResponse])
def rescore(task_id: int, admin: User = Depends(require_admin), session: Session = Depends(get_session)) -> list[ScoreResultResponse]:
    if session.get(Task, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    results = rescore_task(session, task_id)
    log_action(session, actor_user_id=admin.id, action="task.rescore", entity_type="task", entity_id=str(task_id), details={"result_count": len(results)})
    session.commit()
    return [ScoreResultResponse(**build_result_payload(session, result)) for result in results]


@router.get("/api/events/{event_id}/pilot-summary", response_model=list[PilotSummaryResponse])
def pilot_summary(event_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[PilotSummaryResponse]:
    pilot_ids = session.scalars(select(EventPilot.pilot_id).where(EventPilot.event_id == event_id)).all()
    summaries: list[PilotSummaryResponse] = []
    for pilot_id in pilot_ids:
        if user.role == "pilot" and user.pilot_id != pilot_id:
            continue
        pilot = session.get(Pilot, pilot_id)
        aggregates = session.execute(
            select(func.coalesce(func.sum(ScoreResult.score_points), 0), func.count(ScoreResult.id), func.coalesce(func.max(ScoreResult.distance_flown_km), 0))
            .select_from(ScoreResult)
            .join(Task, Task.id == ScoreResult.task_id)
            .where(Task.event_id == event_id, ScoreResult.pilot_id == pilot_id)
        ).one()
        summaries.append(PilotSummaryResponse(pilot_id=pilot_id, pilot_name=f"{pilot.first_name} {pilot.last_name}" if pilot else "Unknown", competition_number=pilot.competition_number if pilot else None, total_score_points=float(aggregates[0] or 0), tasks_scored=int(aggregates[1] or 0), best_distance_km=float(aggregates[2] or 0)))
    return sorted(summaries, key=lambda summary: (-summary.total_score_points, summary.pilot_name))