import json
import math
from datetime import datetime, time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_user, require_staff
from app.models import AuditLog, Event, EventPilot, IGCUpload, Pilot, PilotFlight, PilotFlightTrackPoint, ScorePenalty, ScoreResult, Task, TaskScoringInput, TrackPoint, User
from app.schemas import (
    PenaltyAuditEntry,
    PilotSummaryResponse,
    ScorePenaltyEntry,
    ScorePenaltySaveRequest,
    ScoreResultResponse,
    ScoringOperationsResponse,
    ScoringOperationsResultSummary,
    ScoringOperationsRow,
    ScoringLogbookCandidate,
    ScoringLogbookSelectResponse,
    ScoringUploadOption,
    TaskResultSummaryResponse,
    TaskScoringInputUpdate,
)
from app.services.audit import log_action
from app.services.scoring import build_result_payload, build_task_scoring_audit, repair_fl2026_task1_settings, rescore_task
from app.services.task_uploads import select_upload_for_scoring, store_task_upload

router = APIRouter(tags=["results"])

STATUS_ONLY_VALUES = {"minimum_distance", "did_not_fly", "absent"}


def _is_late_start(task: Task, event_tz: str, first_fix_time: datetime | None) -> bool:
    """Return True if the first fix is after the task's start_close_time."""
    if not task.start_close_time or first_fix_time is None:
        return False
    try:
        parts = task.start_close_time.split(":")
        close_time = dt_time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
    except (ValueError, IndexError):
        return False
    try:
        tz = ZoneInfo(event_tz)
    except Exception:
        tz = ZoneInfo("UTC")
    local_fix = first_fix_time.astimezone(tz).time()
    return local_fix > close_time


def _upload_source(upload: IGCUpload) -> str:
    normalized = str(upload.metadata_json.get("upload_source") or "manual").strip().lower()
    if normalized == "auto":
        return "bulk"
    if normalized == "bulk_review":
        return "review"
    return normalized or "manual"


def _upload_option_label(upload: IGCUpload) -> str:
    source = _upload_source(upload)
    label = f"{upload.filename} — {source.title()}"
    pilot_name = str(upload.metadata_json.get("pilot_name") or "").strip()
    if source == "review":
        label = f"{upload.filename} — Needs review"
        if pilot_name:
            label = f"{label} (IGC: {pilot_name})"
    return label


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


def _effective_selected_upload_id(entry: TaskScoringInput | None) -> int | None:
    if entry is not None and entry.selected_upload_id is not None:
        return entry.selected_upload_id
    return None


def _downloadable_logbook_path(session: Session, flight: PilotFlight) -> Path | None:
    if flight.igc_upload_id is not None:
        upload = session.get(IGCUpload, flight.igc_upload_id)
        if upload is not None:
            candidate = Path(upload.stored_path)
            if candidate.exists():
                return candidate
    if flight.stored_path:
        candidate = Path(flight.stored_path)
        if candidate.exists():
            return candidate
    return None


def _validate_scoring_logbook_context(session: Session, task_id: int, pilot_id: int) -> tuple[Task, Pilot]:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    pilot = session.get(Pilot, pilot_id)
    if pilot is None or session.scalar(select(EventPilot).where(EventPilot.event_id == task.event_id, EventPilot.pilot_id == pilot_id)) is None:
        raise HTTPException(status_code=404, detail="Pilot not found for this event")
    return task, pilot


def _logbook_candidate_payload(session: Session, flight: PilotFlight) -> ScoringLogbookCandidate:
    event = session.get(Event, flight.event_id) if flight.event_id else None
    task = session.get(Task, flight.task_id) if flight.task_id else None
    already_linked_upload_id = None
    if flight.igc_upload_id is not None:
        upload = session.get(IGCUpload, flight.igc_upload_id)
        already_linked_upload_id = upload.id if upload is not None else None
    return ScoringLogbookCandidate(
        flight_id=flight.id,
        filename=flight.filename,
        source_kind=flight.source_kind,
        flight_date=flight.flight_date,
        created_at=flight.created_at,
        event_name=event.name if event else None,
        task_name=task.name if task else None,
        duration_seconds=flight.duration_seconds,
        highest_altitude_m=flight.highest_altitude_m,
        best_climb_mps=flight.best_climb_mps,
        already_linked_upload_id=already_linked_upload_id,
    )


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


@router.get("/api/tasks/{task_id}/results", response_model=list[ScoreResultResponse])
def get_task_results(task_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[ScoreResultResponse]:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    results_query = select(ScoreResult).where(ScoreResult.task_id == task_id)
    if user.role not in {"admin", "organizer"}:
        results_query = results_query.where(ScoreResult.result_state == "official")
    visible_results = session.scalars(
        results_query.order_by(ScoreResult.rank.asc().nullslast(), ScoreResult.score_points.desc())
    ).all()
    results_by_pilot = {result.pilot_id: result for result in visible_results}
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


@router.get("/api/tasks/{task_id}/scoring-audit")
def scoring_audit(task_id: int, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> dict:
    if session.get(Task, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return build_task_scoring_audit(session, task_id)


@router.post("/api/tasks/{task_id}/repair-fl2026-task1")
def repair_fl2026_task1(task_id: int, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> dict:
    if session.get(Task, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    payload = repair_fl2026_task1_settings(session, task_id)
    log_action(session, actor_user_id=admin.id, action="task.repair_fl2026_task1", entity_type="task", entity_id=str(task_id), details={"status": payload.get("status")})
    session.commit()
    return payload


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

    # Preload first fix time per upload for late-start detection
    first_fix_times: dict[int, datetime] = {}
    event = session.get(Event, task.event_id)
    event_tz = event.timezone if event else "UTC"
    if task.start_close_time and uploads:
        upload_ids = [u.id for u in uploads]
        first_fixes = session.execute(
            select(TrackPoint.upload_id, func.min(TrackPoint.recorded_at))
            .where(TrackPoint.upload_id.in_(upload_ids))
            .group_by(TrackPoint.upload_id)
        ).all()
        first_fix_times = {row[0]: row[1] for row in first_fixes}

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
                selected_upload_id=_effective_selected_upload_id(entry),
                status_override=entry.status_override if entry else None,
                uploads=[
                    ScoringUploadOption(
                        id=upload.id,
                        filename=upload.filename,
                        upload_source=_upload_source(upload),
                        label=_upload_option_label(upload),
                        uploaded_at=upload.uploaded_at,
                        late_start=_is_late_start(task, event_tz, first_fix_times.get(upload.id)),
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


@router.get("/api/tasks/{task_id}/pilots/{pilot_id}/logbook-igc-candidates", response_model=list[ScoringLogbookCandidate])
def list_logbook_igc_candidates(
    task_id: int,
    pilot_id: int,
    _admin: User = Depends(require_staff),
    session: Session = Depends(get_session),
) -> list[ScoringLogbookCandidate]:
    task, _pilot = _validate_scoring_logbook_context(session, task_id, pilot_id)
    if task.task_date is None:
        return []
    flights = session.scalars(
        select(PilotFlight)
        .where(
            PilotFlight.pilot_id == pilot_id,
            PilotFlight.flight_date == task.task_date,
            PilotFlight.source_kind.in_(("app_upload", "task_upload")),
        )
        .order_by(PilotFlight.created_at.desc(), PilotFlight.id.desc())
    ).all()
    candidates = [
        flight
        for flight in flights
        if flight.igc_upload_id is not None or _downloadable_logbook_path(session, flight) is not None
    ]
    return [_logbook_candidate_payload(session, flight) for flight in candidates]


@router.post("/api/tasks/{task_id}/pilots/{pilot_id}/logbook-igc-candidates/{flight_id}/select", response_model=ScoringLogbookSelectResponse)
async def select_logbook_igc_candidate(
    task_id: int,
    pilot_id: int,
    flight_id: int,
    admin: User = Depends(require_staff),
    session: Session = Depends(get_session),
) -> ScoringLogbookSelectResponse:
    task, _pilot = _validate_scoring_logbook_context(session, task_id, pilot_id)
    if task.task_date is None:
        raise HTTPException(status_code=400, detail="Task must have a date before logbook files can be matched")
    flight = session.get(PilotFlight, flight_id)
    if flight is None or flight.pilot_id != pilot_id or flight.flight_date != task.task_date:
        raise HTTPException(status_code=404, detail="Logbook flight not found for this pilot and task date")
    if flight.source_kind not in {"app_upload", "task_upload"}:
        raise HTTPException(status_code=400, detail="Only IGC-backed logbook flights can be selected")

    selected_upload: IGCUpload | None = None
    if flight.igc_upload_id is not None:
        linked_upload = session.get(IGCUpload, flight.igc_upload_id)
        if linked_upload is not None and linked_upload.task_id == task.id and linked_upload.pilot_id == pilot_id:
            selected_upload = linked_upload

    if selected_upload is None:
        stored_path = _downloadable_logbook_path(session, flight)
        if stored_path is None:
            raise HTTPException(status_code=400, detail="This logbook flight does not have a downloadable IGC file")
        content = stored_path.read_bytes()
        stored = await store_task_upload(
            session,
            task,
            filename=flight.filename or stored_path.name,
            content=content,
            pilot_id=pilot_id,
            uploaded_by_user_id=admin.id,
            upload_source="logbook",
            auto_select_and_rescore_enabled=False,
        )
        selected_upload = stored.upload
        synced_flight = session.scalar(select(PilotFlight).where(PilotFlight.igc_upload_id == selected_upload.id))
        if flight.igc_upload_id is None and synced_flight is not None and synced_flight.id != flight.id:
            synced_values = {
                "source_kind": "task_upload",
                "event_id": selected_upload.event_id,
                "task_id": selected_upload.task_id,
                "igc_upload_id": selected_upload.id,
                "site_id": synced_flight.site_id,
                "site_name": synced_flight.site_name,
                "filename": synced_flight.filename,
                "sha256": synced_flight.sha256,
                "stored_path": synced_flight.stored_path,
                "metadata_json": synced_flight.metadata_json,
                "duration_seconds": synced_flight.duration_seconds,
                "highest_altitude_m": synced_flight.highest_altitude_m,
                "best_climb_mps": synced_flight.best_climb_mps,
            }
            session.execute(delete(PilotFlightTrackPoint).where(PilotFlightTrackPoint.flight_id == flight.id))
            session.delete(synced_flight)
            session.flush()
            for attr, value in synced_values.items():
                setattr(flight, attr, value)
            session.add(flight)
            session.flush()

    select_upload_for_scoring(session, task, pilot_id, selected_upload, admin.id)
    rescore_task(session, task.id)
    log_action(
        session,
        actor_user_id=admin.id,
        action="task.scoring_input.logbook_select",
        entity_type="task_scoring_input",
        entity_id=f"{task.id}:{pilot_id}",
        details={"task_id": task.id, "pilot_id": pilot_id, "flight_id": flight.id, "selected_upload_id": selected_upload.id},
    )
    session.commit()
    return ScoringLogbookSelectResponse(
        task_id=task.id,
        pilot_id=pilot_id,
        flight_id=flight.id,
        selected_upload_id=selected_upload.id,
    )


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


@router.post("/api/tasks/{task_id}/unpublish-results")
def unpublish_task_results(task_id: int, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> dict[str, int | str]:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    results = session.scalars(select(ScoreResult).where(ScoreResult.task_id == task_id)).all()
    if not results:
        return {"status": "ok", "unpublished_count": 0}
    unpublished_count = 0
    for result in results:
        if result.result_state != "provisional":
            result.result_state = "provisional"
            unpublished_count += 1
    log_action(
        session,
        actor_user_id=admin.id,
        action="task.results.unpublish",
        entity_type="task",
        entity_id=str(task_id),
        details={"unpublished_count": unpublished_count},
    )
    session.commit()
    return {"status": "ok", "unpublished_count": unpublished_count}


@router.get("/api/events/{event_id}/task-result-summary", response_model=list[TaskResultSummaryResponse])
def task_result_summary(event_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[TaskResultSummaryResponse]:
    rows_query = (
        select(ScoreResult.task_id, ScoreResult.details_json)
        .join(Task, Task.id == ScoreResult.task_id)
        .where(Task.event_id == event_id)
        .order_by(ScoreResult.task_id.asc(), ScoreResult.rank.asc().nullslast(), ScoreResult.score_points.desc())
    )
    if user.role not in {"admin", "organizer"}:
        rows_query = rows_query.where(ScoreResult.result_state == "official")

    summaries_by_task: dict[int, float | None] = {}
    for task_id, details_json in session.execute(rows_query).all():
        task_id_int = int(task_id)
        summaries_by_task.setdefault(task_id_int, None)
        day_quality = _gap_day_quality(details_json)
        if summaries_by_task[task_id_int] is None and day_quality is not None:
            summaries_by_task[task_id_int] = day_quality

    return [
        TaskResultSummaryResponse(task_id=task_id, day_quality=day_quality)
        for task_id, day_quality in sorted(summaries_by_task.items())
    ]


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
    score_rows_query = (
        select(ScoreResult.pilot_id, ScoreResult.task_id, ScoreResult.score_points, ScoreResult.result_state, Task.is_practice)
        .join(Task, Task.id == ScoreResult.task_id)
        .where(
            Task.event_id == event_id,
            ScoreResult.pilot_id.in_(pilot_ids),
        )
        .order_by(ScoreResult.task_id.asc())
    )
    if user.role not in {"admin", "organizer"}:
        score_rows_query = score_rows_query.where(ScoreResult.result_state == "official")
    score_rows = session.execute(score_rows_query).all()

    # Batch-load aggregates for all pilots in one query
    agg_rows_query = (
        select(
            ScoreResult.pilot_id,
            func.coalesce(func.sum(ScoreResult.score_points), 0),
            func.count(ScoreResult.id),
            func.coalesce(func.max(ScoreResult.distance_flown_km), 0),
        )
        .join(Task, Task.id == ScoreResult.task_id)
        .where(
            Task.event_id == event_id,
            Task.is_practice.is_(False),
            ScoreResult.pilot_id.in_(pilot_ids),
        )
        .group_by(ScoreResult.pilot_id)
    )
    if user.role not in {"admin", "organizer"}:
        agg_rows_query = agg_rows_query.where(ScoreResult.result_state == "official")
    agg_rows = session.execute(agg_rows_query).all()

    # Build lookup structures
    task_scores_by_pilot: dict[int, dict[int, float]] = {}
    task_states_by_pilot: dict[int, dict[int, str]] = {}
    practice_task_ids: set[int] = set()
    for pid, tid, pts, result_state, is_practice in score_rows:
        if is_practice:
            practice_task_ids.add(int(tid))
        task_scores_by_pilot.setdefault(pid, {})[int(tid)] = float(pts or 0)
        task_states_by_pilot.setdefault(pid, {})[int(tid)] = str(result_state or "official")

    agg_by_pilot: dict[int, tuple] = {row[0]: row[1:] for row in agg_rows}

    # FTV (Fixed Total Validity): when use_best_score_for_ftv_validity is enabled
    # on the event, the overall ranking uses each task's best actual score as the
    # validity ceiling rather than the theoretical 1000 * day_quality.  This means
    # each pilot's per-task score is divided by the task's best actual score to
    # produce a normalised contribution, and the total is capped at the number of
    # tasks (each task can contribute at most 1.0).  The effect is that weaker-day
    # tasks count proportionally less.
    event = session.get(Event, event_id)
    use_ftv = bool(event.use_best_score_for_ftv_validity) if event and event.use_best_score_for_ftv_validity is not None else False

    # Pre-compute per-task best score for FTV normalisation
    task_best_score: dict[int, float] = {}
    if use_ftv:
        for _pid, tid, pts, _state, is_practice in score_rows:
            if is_practice:
                continue
            tid_int = int(tid)
            pts_val = float(pts or 0)
            if pts_val > task_best_score.get(tid_int, 0):
                task_best_score[tid_int] = pts_val

    summaries: list[PilotSummaryResponse] = []
    for pilot_id in pilot_ids:
        pilot = pilots_by_id.get(pilot_id)
        agg = agg_by_pilot.get(pilot_id, (0, 0, 0))
        pilot_task_scores = task_scores_by_pilot.get(pilot_id, {})

        if use_ftv and task_best_score:
            # FTV total: sum of (pilot_score / best_score_for_task) for each task,
            # then multiply by the average best-score to get back into point-space.
            ftv_sum = 0.0
            for tid_str, pts in pilot_task_scores.items():
                if int(tid_str) in practice_task_ids:
                    continue
                best = task_best_score.get(int(tid_str), 0)
                if best > 0:
                    ftv_sum += float(pts) / best
            avg_best = sum(task_best_score.values()) / max(len(task_best_score), 1)
            total_score = round(ftv_sum * avg_best, 2)
        else:
            total_score = float(agg[0] or 0)

        summaries.append(PilotSummaryResponse(
            pilot_id=pilot_id,
            pilot_name=f"{pilot.first_name} {pilot.last_name}" if pilot else "Unknown",
            competition_number=pilot.competition_number if pilot else None,
            total_score_points=total_score,
            tasks_scored=int(agg[1] or 0),
            best_distance_km=float(agg[2] or 0),
            task_scores=pilot_task_scores,
            task_result_states=task_states_by_pilot.get(pilot_id, {}),
        ))
    return sorted(summaries, key=lambda summary: (-summary.total_score_points, summary.pilot_name))
