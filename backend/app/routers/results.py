import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_user, require_staff
from app.models import AuditLog, EventPilot, IGCUpload, Pilot, ScorePenalty, ScoreResult, Task, TaskScoringInput, User
from app.schemas import (
    PenaltyAuditEntry,
    PilotSummaryResponse,
    ScorePenaltyEntry,
    ScorePenaltySaveRequest,
    ScoreResultResponse,
    ScoringOperationsResponse,
    ScoringOperationsResultSummary,
    ScoringOperationsRow,
    ScoringUploadOption,
    TaskScoringInputUpdate,
)
from app.services.audit import log_action
from app.services.scoring import build_result_payload, rescore_task

router = APIRouter(tags=["results"])

STATUS_ONLY_VALUES = {"minimum_distance", "did_not_fly", "absent"}


def _upload_source(upload: IGCUpload) -> str:
    normalized = str(upload.metadata_json.get("upload_source") or "manual").strip().lower()
    if normalized == "auto":
        return "bulk"
    return normalized or "manual"


def _penalty_summary(penalties: list[ScorePenalty]) -> str | None:
    if not penalties:
        return None
    parts: list[str] = []
    percentage_values = [penalty for penalty in penalties if penalty.penalty_type == "percentage" and penalty.value]
    fixed_values = [penalty for penalty in penalties if penalty.penalty_type == "fixed" and penalty.value]
    if percentage_values:
        parts.extend([f"-{int(penalty.value) if float(penalty.value).is_integer() else penalty.value:g}%" for penalty in percentage_values])
    if fixed_values:
        parts.extend([f"-{int(penalty.value) if float(penalty.value).is_integer() else penalty.value:g} pts" for penalty in fixed_values])
    return ", ".join(parts) if parts else None


def _row_classification(result: ScoreResult | None, status_override: str | None) -> str:
    if result is not None:
        if result.rank is not None:
            return "ranked"
        if result.status in STATUS_ONLY_VALUES:
            return result.status
    if status_override in STATUS_ONLY_VALUES:
        return status_override
    return "unscored"


def _penalty_audit_entries(session: Session, task_id: int, pilot_id: int) -> list[PenaltyAuditEntry]:
    logs = session.scalars(
        select(AuditLog)
        .where(AuditLog.entity_type == "task_penalty", AuditLog.entity_id == f"{task_id}:{pilot_id}")
        .order_by(AuditLog.created_at.desc())
        .limit(10)
    ).all()
    actor_ids = [log.actor_user_id for log in logs if log.actor_user_id is not None]
    users_by_id = {user.id: user for user in session.scalars(select(User).where(User.id.in_(actor_ids))).all()} if actor_ids else {}
    entries: list[PenaltyAuditEntry] = []
    for log in logs:
        actor = users_by_id.get(log.actor_user_id) if log.actor_user_id is not None else None
        summary = str(log.details_json.get("summary") or log.action)
        entries.append(
            PenaltyAuditEntry(
                actor_name=actor.full_name if actor else "Unknown",
                timestamp=log.created_at,
                summary=summary,
            )
        )
    return entries


def _task_scoring_input(session: Session, task_id: int, pilot_id: int) -> TaskScoringInput:
    entry = session.scalar(select(TaskScoringInput).where(TaskScoringInput.task_id == task_id, TaskScoringInput.pilot_id == pilot_id))
    if entry is None:
        entry = TaskScoringInput(task_id=task_id, pilot_id=pilot_id)
        session.add(entry)
        session.flush()
    return entry


@router.get("/api/tasks/{task_id}/results", response_model=list[ScoreResultResponse])
def get_task_results(task_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[ScoreResultResponse]:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    official_results = session.scalars(
        select(ScoreResult)
        .where(ScoreResult.task_id == task_id, ScoreResult.result_state == "official")
        .order_by(ScoreResult.rank.asc().nullslast(), ScoreResult.score_points.desc())
    ).all()
    results_by_pilot = {result.pilot_id: result for result in official_results}
    pilots = session.execute(
        select(Pilot)
        .join(EventPilot, EventPilot.pilot_id == Pilot.id)
        .where(EventPilot.event_id == task.event_id)
        .order_by(Pilot.last_name.asc(), Pilot.first_name.asc())
    ).scalars().all()
    rows: list[ScoreResultResponse] = []
    for pilot in pilots:
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
            )
        )

    def row_sort_key(row: ScoreResultResponse) -> tuple:
        if row.result_state == "unscored":
            return (1, row.pilot_name.lower())
        return (0, row.rank if row.rank is not None else 10**9, row.pilot_name.lower())

    return sorted(rows, key=row_sort_key)


@router.post("/api/tasks/{task_id}/rescore", response_model=list[ScoreResultResponse])
def rescore(task_id: int, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> list[ScoreResultResponse]:
    if session.get(Task, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    results = rescore_task(session, task_id)
    log_action(session, actor_user_id=admin.id, action="task.rescore", entity_type="task", entity_id=str(task_id), details={"result_count": len(results)})
    session.commit()
    persisted_results = session.scalars(
        select(ScoreResult).where(ScoreResult.task_id == task_id).order_by(ScoreResult.rank.asc().nullslast(), ScoreResult.score_points.desc())
    ).all()
    return [ScoreResultResponse(**build_result_payload(session, result)) for result in persisted_results]


@router.delete("/api/tasks/{task_id}/results")
def delete_task_results(task_id: int, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> dict[str, int | str]:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    existing_count = session.scalar(select(func.count(ScoreResult.id)).where(ScoreResult.task_id == task_id)) or 0
    scoring_input_count = session.scalar(select(func.count(TaskScoringInput.id)).where(TaskScoringInput.task_id == task_id)) or 0
    penalty_count = session.scalar(select(func.count(ScorePenalty.id)).where(ScorePenalty.task_id == task_id)) or 0
    session.execute(delete(ScoreResult).where(ScoreResult.task_id == task_id))
    session.execute(delete(ScorePenalty).where(ScorePenalty.task_id == task_id))
    session.query(TaskScoringInput).where(TaskScoringInput.task_id == task_id).update(
        {
            TaskScoringInput.selected_upload_id: None,
            TaskScoringInput.status_override: None,
        },
        synchronize_session=False,
    )
    log_action(
        session,
        actor_user_id=admin.id,
        action="task.results.delete",
        entity_type="task",
        entity_id=str(task_id),
        details={
            "deleted_count": int(existing_count),
            "cleared_scoring_inputs": int(scoring_input_count),
            "deleted_penalties": int(penalty_count),
        },
    )
    session.commit()
    return {"status": "ok", "deleted_count": int(existing_count)}


@router.get("/api/tasks/{task_id}/scoring-operations", response_model=ScoringOperationsResponse)
def get_scoring_operations(task_id: int, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> ScoringOperationsResponse:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    pilots = session.execute(
        select(Pilot)
        .join(EventPilot, EventPilot.pilot_id == Pilot.id)
        .where(EventPilot.event_id == task.event_id)
        .order_by(Pilot.last_name.asc(), Pilot.first_name.asc())
    ).scalars().all()
    scoring_inputs = session.scalars(select(TaskScoringInput).where(TaskScoringInput.task_id == task_id)).all()
    scoring_input_by_pilot = {entry.pilot_id: entry for entry in scoring_inputs}
    uploads = session.scalars(select(IGCUpload).where(IGCUpload.task_id == task_id).order_by(IGCUpload.uploaded_at.desc())).all()
    uploads_by_pilot: dict[int, list[IGCUpload]] = {}
    for upload in uploads:
        uploads_by_pilot.setdefault(upload.pilot_id, []).append(upload)
    results = session.scalars(select(ScoreResult).where(ScoreResult.task_id == task_id)).all()
    results_by_pilot = {result.pilot_id: result for result in results}
    penalties = session.scalars(
        select(ScorePenalty).where(ScorePenalty.task_id == task_id).order_by(ScorePenalty.pilot_id.asc(), ScorePenalty.position.asc(), ScorePenalty.id.asc())
    ).all()
    penalties_by_pilot: dict[int, list[ScorePenalty]] = {}
    for penalty in penalties:
        penalties_by_pilot.setdefault(penalty.pilot_id, []).append(penalty)

    rows: list[ScoringOperationsRow] = []
    for pilot in pilots:
        entry = scoring_input_by_pilot.get(pilot.id)
        result = results_by_pilot.get(pilot.id)
        pilot_penalties = penalties_by_pilot.get(pilot.id, [])
        rows.append(
            ScoringOperationsRow(
                pilot_id=pilot.id,
                pilot_name=f"{pilot.first_name} {pilot.last_name}".strip(),
                competition_number=pilot.competition_number,
                selected_upload_id=entry.selected_upload_id if entry else None,
                status_override=entry.status_override if entry else None,
                uploads=[
                    ScoringUploadOption(
                        id=upload.id,
                        filename=upload.filename,
                        upload_source=_upload_source(upload),
                        label=f"{upload.filename} — {_upload_source(upload).title()}",
                        uploaded_at=upload.uploaded_at,
                    )
                    for upload in uploads_by_pilot.get(pilot.id, [])
                ],
                result=ScoringOperationsResultSummary(
                    result_id=result.id,
                    upload_id=result.upload_id,
                    status=result.status,
                    rank=result.rank,
                    distance_flown_km=result.distance_flown_km,
                    elapsed_seconds=result.elapsed_seconds,
                    raw_score_points=result.raw_score_points,
                    score_points=result.score_points,
                    result_state=result.result_state,
                ) if result else None,
                penalties=[
                    ScorePenaltyEntry(
                        id=penalty.id,
                        penalty_type=penalty.penalty_type,
                        value=penalty.value,
                        reason=penalty.reason,
                        position=penalty.position,
                        applied_by=None,
                        applied_at=penalty.applied_at,
                    )
                    for penalty in pilot_penalties
                ],
                penalty_summary=_penalty_summary(pilot_penalties),
                penalty_audit=_penalty_audit_entries(session, task_id, pilot.id),
                row_classification=_row_classification(result, entry.status_override if entry else None),
            )
        )

    def row_sort_key(row: ScoringOperationsRow) -> tuple:
        if any(item.result is not None for item in rows):
            classification_order = {
                "ranked": 0,
                "minimum_distance": 1,
                "did_not_fly": 2,
                "absent": 3,
                "unscored": 4,
            }
            return (
                classification_order.get(row.row_classification, 9),
                row.result.rank if row.result and row.result.rank is not None else 10**9,
                row.pilot_name.lower(),
            )
        return (0, row.pilot_name.lower())

    rows.sort(key=row_sort_key)
    return ScoringOperationsResponse(rows=rows)


@router.patch("/api/tasks/{task_id}/scoring-inputs/{pilot_id}")
def update_scoring_input(
    task_id: int,
    pilot_id: int,
    payload: TaskScoringInputUpdate,
    admin: User = Depends(require_staff),
    session: Session = Depends(get_session),
) -> dict[str, str | int | None]:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if session.scalar(select(EventPilot).where(EventPilot.event_id == task.event_id, EventPilot.pilot_id == pilot_id)) is None:
        raise HTTPException(status_code=404, detail="Pilot not found for this event")

    selected_upload_id = payload.selected_upload_id
    status_override = payload.status_override
    if selected_upload_id is not None and status_override:
        raise HTTPException(status_code=400, detail="Select either an upload or a status override, not both")
    if status_override is not None and status_override not in STATUS_ONLY_VALUES:
        raise HTTPException(status_code=400, detail="Invalid status override")
    if selected_upload_id is not None:
        upload = session.get(IGCUpload, selected_upload_id)
        if upload is None or upload.task_id != task_id or upload.pilot_id != pilot_id:
            raise HTTPException(status_code=400, detail="Selected upload does not belong to this pilot and task")

    entry = _task_scoring_input(session, task_id, pilot_id)
    entry.selected_upload_id = selected_upload_id
    entry.status_override = status_override
    entry.updated_by_user_id = admin.id
    log_action(
        session,
        actor_user_id=admin.id,
        action="task.scoring_input.update",
        entity_type="task_scoring_input",
        entity_id=f"{task_id}:{pilot_id}",
        details={"task_id": task_id, "pilot_id": pilot_id, "selected_upload_id": selected_upload_id, "status_override": status_override},
    )
    session.add(entry)
    session.commit()
    return {"status": "ok", "task_id": task_id, "pilot_id": pilot_id, "selected_upload_id": selected_upload_id, "status_override": status_override}


@router.put("/api/tasks/{task_id}/penalties/{pilot_id}")
def save_penalties(
    task_id: int,
    pilot_id: int,
    payload: ScorePenaltySaveRequest,
    admin: User = Depends(require_staff),
    session: Session = Depends(get_session),
) -> dict[str, str | int]:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if session.scalar(select(EventPilot).where(EventPilot.event_id == task.event_id, EventPilot.pilot_id == pilot_id)) is None:
        raise HTTPException(status_code=404, detail="Pilot not found for this event")

    existing_penalties = session.scalars(select(ScorePenalty).where(ScorePenalty.task_id == task_id, ScorePenalty.pilot_id == pilot_id)).all()
    for penalty in existing_penalties:
        session.delete(penalty)
    for index, item in enumerate(payload.penalties):
        session.add(
            ScorePenalty(
                task_id=task_id,
                pilot_id=pilot_id,
                penalty_type=item.penalty_type,
                value=item.value,
                reason=item.reason,
                position=index,
                applied_by_user_id=admin.id,
                updated_by_user_id=admin.id,
            )
        )
    summary = ", ".join(
        [
            f"{item.reason or ('% penalty' if item.penalty_type == 'percentage' else 'Fixed pts')} -{item.value:g}{'%' if item.penalty_type == 'percentage' else ' pts'}"
            for item in payload.penalties
        ]
    ) or "Cleared penalties"
    log_action(
        session,
        actor_user_id=admin.id,
        action="task.penalties.update",
        entity_type="task_penalty",
        entity_id=f"{task_id}:{pilot_id}",
        details={"task_id": task_id, "pilot_id": pilot_id, "summary": summary, "count": len(payload.penalties)},
    )
    session.commit()
    return {"status": "ok", "task_id": task_id, "pilot_id": pilot_id, "penalty_count": len(payload.penalties)}


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


@router.post("/api/tasks/{task_id}/publish-results")
def publish_task_results(task_id: int, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> dict[str, int | str]:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    results = session.scalars(select(ScoreResult).where(ScoreResult.task_id == task_id)).all()
    if not results:
        return {"status": "ok", "published_count": 0}
    published_count = 0
    for result in results:
        if result.result_state != "official":
            result.result_state = "official"
            published_count += 1
    log_action(
        session,
        actor_user_id=admin.id,
        action="task.results.publish",
        entity_type="task",
        entity_id=str(task_id),
        details={"published_count": published_count},
    )
    session.commit()
    return {"status": "ok", "published_count": published_count}


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
        .where(
            Task.event_id == event_id,
            ScoreResult.pilot_id.in_(pilot_ids),
            ScoreResult.result_state == "official",
        )
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
        .where(
            Task.event_id == event_id,
            ScoreResult.pilot_id.in_(pilot_ids),
            ScoreResult.result_state == "official",
        )
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
