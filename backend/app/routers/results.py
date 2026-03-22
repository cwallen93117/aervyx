from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_user, require_staff
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
    results = session.scalars(query).all()
    return [ScoreResultResponse(**build_result_payload(session, result)) for result in results]


@router.post("/api/tasks/{task_id}/rescore", response_model=list[ScoreResultResponse])
def rescore(task_id: int, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> list[ScoreResultResponse]:
    if session.get(Task, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    results = rescore_task(session, task_id)
    log_action(session, actor_user_id=admin.id, action="task.rescore", entity_type="task", entity_id=str(task_id), details={"result_count": len(results)})
    session.commit()
    return [ScoreResultResponse(**build_result_payload(session, result)) for result in results]


@router.post("/api/results/{result_id}/promote", response_model=ScoreResultResponse)
def promote_result(result_id: int, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> ScoreResultResponse:
    result = session.get(ScoreResult, result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")
    if result.result_state == "official":
        raise HTTPException(status_code=400, detail="Result is already official")
    result.result_state = "official"
    log_action(session, actor_user_id=admin.id, action="result.promote", entity_type="score_result", entity_id=str(result_id), details={"task_id": result.task_id, "pilot_id": result.pilot_id})
    session.commit()
    session.refresh(result)
    return ScoreResultResponse(**build_result_payload(session, result))


@router.get("/api/events/{event_id}/pilot-summary", response_model=list[PilotSummaryResponse])
def pilot_summary(event_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[PilotSummaryResponse]:
    pilot_ids = session.scalars(select(EventPilot.pilot_id).where(EventPilot.event_id == event_id)).all()
    if not pilot_ids:
        return []

    # Batch-load all pilots
    pilots_by_id: dict[int, Pilot] = {
        p.id: p for p in session.scalars(select(Pilot).where(Pilot.id.in_(pilot_ids))).all()
    }

    # Batch-load all per-task scores for these pilots in this event
    score_rows = session.execute(
        select(ScoreResult.pilot_id, ScoreResult.task_id, ScoreResult.score_points)
        .join(Task, Task.id == ScoreResult.task_id)
        .where(Task.event_id == event_id, ScoreResult.pilot_id.in_(pilot_ids))
        .order_by(ScoreResult.task_id.asc())
    ).all()

    # Batch-load aggregates for all pilots in one query
    agg_rows = session.execute(
        select(
            ScoreResult.pilot_id,
            func.coalesce(func.sum(ScoreResult.score_points), 0),
            func.count(ScoreResult.id),
            func.coalesce(func.max(ScoreResult.distance_flown_km), 0),
        )
        .join(Task, Task.id == ScoreResult.task_id)
        .where(Task.event_id == event_id, ScoreResult.pilot_id.in_(pilot_ids))
        .group_by(ScoreResult.pilot_id)
    ).all()

    # Build lookup structures
    task_scores_by_pilot: dict[int, dict[int, float]] = {}
    for pid, tid, pts in score_rows:
        task_scores_by_pilot.setdefault(pid, {})[int(tid)] = float(pts or 0)

    agg_by_pilot: dict[int, tuple] = {row[0]: row[1:] for row in agg_rows}

    summaries: list[PilotSummaryResponse] = []
    for pilot_id in pilot_ids:
        pilot = pilots_by_id.get(pilot_id)
        agg = agg_by_pilot.get(pilot_id, (0, 0, 0))
        summaries.append(PilotSummaryResponse(
            pilot_id=pilot_id,
            pilot_name=f"{pilot.first_name} {pilot.last_name}" if pilot else "Unknown",
            competition_number=pilot.competition_number if pilot else None,
            total_score_points=float(agg[0] or 0),
            tasks_scored=int(agg[1] or 0),
            best_distance_km=float(agg[2] or 0),
            task_scores=task_scores_by_pilot.get(pilot_id, {}),
        ))
    return sorted(summaries, key=lambda summary: (-summary.total_score_points, summary.pilot_name))
