from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime as dt, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_session
from app.deps import get_current_user
from app.models import Event, EventPilot, IGCUpload, Pilot, PilotFlight, PilotFlightTrackPoint, ScoreResult, Task, TaskPoint, TaskScoringInput, TrackPoint, User
from app.schemas import BulkUploadItemResponse, UploadResponse
from app.services import task_uploads as task_upload_service
from app.services.audit import log_action
from app.services.igc import parse_igc
from app.services.scoring import invalidate_task_meet_stats_cache, rescore_task
from app.services.replay_tracks import DEFAULT_REPLAY_MAX_POINTS, simplify_replay_points
from app.services.task_uploads import (
    is_late_start_upload,
    manual_filename_with_suffix,
    normalized_upload_source,
    select_upload_for_scoring,
    store_task_upload,
)
from app.services.tracking import _publish
router = APIRouter(tags=["uploads"])


@dataclass
class StoredUpload:
    upload: IGCUpload
    created: bool


@dataclass(frozen=True)
class PilotUploadMatch:
    pilot: Pilot | None
    confidence: str
    message: str


def _normalized_upload_source(value: str | None) -> str:
    return normalized_upload_source(value)


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    lowered = value.lower()
    lowered = re.sub(r"\.[a-z0-9]+$", "", lowered)
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _filename_token_hints(filename: str) -> set[str]:
    normalized = _normalize_text(filename)
    tokens = {normalized}
    tokens.update(token for token in normalized.split(" ") if token)
    return tokens


def _ordered_subsequence(tokens: list[str], expected: list[str]) -> bool:
    if not tokens or not expected:
        return False
    cursor = 0
    for token in tokens:
        if token == expected[cursor]:
            cursor += 1
            if cursor == len(expected):
                return True
    return False


def _name_tokens(value: str | None) -> list[str]:
    return [token for token in _normalize_text(value).split(" ") if token and not token.isdigit()]


def _pilot_name_sequences(pilot: Pilot) -> list[list[str]]:
    first = _name_tokens(pilot.first_name)
    last = _name_tokens(pilot.last_name)
    sequences: list[list[str]] = []
    if first and last:
        sequences.append(first + last)
        sequences.append(last + first)
    return sequences


def _tokens_match_pilot_full_name(tokens: list[str], pilot: Pilot) -> bool:
    return any(_ordered_subsequence(tokens, sequence) for sequence in _pilot_name_sequences(pilot))


def _filename_matches_pilot_full_name(filename: str, pilot: Pilot) -> bool:
    return _tokens_match_pilot_full_name(_name_tokens(filename), pilot)


def _metadata_matches_pilot_full_name(metadata: dict, pilot: Pilot) -> bool:
    pilot_name = str(metadata.get("pilot_name") or "")
    return _tokens_match_pilot_full_name(_name_tokens(pilot_name), pilot)


def _filename_matches_comp_number(filename: str, pilot: Pilot) -> bool:
    comp = _normalize_text(pilot.competition_number)
    return bool(comp and comp in _filename_token_hints(filename))


def _single_candidate(candidates: list[Pilot]) -> Pilot | None:
    unique: dict[int, Pilot] = {pilot.id: pilot for pilot in candidates}
    return next(iter(unique.values())) if len(unique) == 1 else None


def _match_pilot_candidate_for_upload(session: Session, event_id: int, filename: str, metadata: dict) -> PilotUploadMatch:
    """Return an exact auto-match or a single review candidate for a bulk IGC.

    Bulk upload selection must be conservative: a partial first/last token score
    is enough to offer a file for review, but never enough to select it for scoring.
    """
    event_pilots = session.scalars(
        select(Pilot)
        .join(EventPilot, EventPilot.pilot_id == Pilot.id)
        .where(EventPilot.event_id == event_id)
    ).all()
    if not event_pilots:
        return PilotUploadMatch(None, "none", "No pilots are registered for this event.")

    header_name = str(metadata.get("pilot_name") or "").strip()
    filename_candidates = [pilot for pilot in event_pilots if _filename_matches_pilot_full_name(filename, pilot)]
    header_candidates = [pilot for pilot in event_pilots if _metadata_matches_pilot_full_name(metadata, pilot)] if header_name else []
    comp_candidates = [pilot for pilot in event_pilots if _filename_matches_comp_number(filename, pilot)]

    filename_candidate = _single_candidate(filename_candidates)
    header_candidate = _single_candidate(header_candidates)
    comp_candidate = _single_candidate(comp_candidates)

    if header_name:
        if filename_candidate is not None and header_candidate is not None and filename_candidate.id == header_candidate.id:
            return PilotUploadMatch(filename_candidate, "auto", "Filename and IGC pilot header both match the same pilot.")
        if comp_candidate is not None and header_candidate is not None and comp_candidate.id == header_candidate.id:
            return PilotUploadMatch(header_candidate, "auto", "Competition number and IGC pilot header both match the same pilot.")
        if filename_candidate is not None:
            return PilotUploadMatch(filename_candidate, "review", "Filename points to one pilot, but the IGC pilot header does not confirm the same full name.")
        if header_candidate is not None:
            return PilotUploadMatch(header_candidate, "review", "IGC pilot header points to one pilot, but the filename does not confirm the same full name.")
        return PilotUploadMatch(None, "none", "Filename and IGC pilot header did not exactly match one event pilot.")

    if filename_candidate is not None:
        return PilotUploadMatch(filename_candidate, "auto", "Filename contains the pilot first and last name.")
    if comp_candidate is not None:
        return PilotUploadMatch(comp_candidate, "review", "Filename contains a unique competition number but no full pilot name.")
    return PilotUploadMatch(None, "none", "Could not confidently match this file to a pilot in the event roster.")


def _match_pilot_for_upload(session: Session, event_id: int, filename: str, metadata: dict) -> Pilot | None:
    match = _match_pilot_candidate_for_upload(session, event_id, filename, metadata)
    return match.pilot if match.confidence == "auto" else None


def _manual_filename_with_suffix(session: Session, task_id: int, pilot_id: int, filename: str) -> str:
    return manual_filename_with_suffix(session, task_id, pilot_id, filename)


def _serialize_upload(upload: IGCUpload) -> UploadResponse:
    return UploadResponse(
        id=upload.id,
        pilot_id=upload.pilot_id,
        task_id=upload.task_id,
        filename=upload.filename,
        sha256=upload.sha256,
        uploaded_at=upload.uploaded_at,
        upload_source=_normalized_upload_source(str(upload.metadata_json.get("upload_source") or "manual")),
        metadata_json=upload.metadata_json,
    )


def _is_late_start_upload(session: Session, task: Task, upload: IGCUpload) -> bool:
    return is_late_start_upload(session, task, upload)


def _select_upload_for_scoring(
    session: Session,
    task: Task,
    pilot_id: int,
    upload: IGCUpload,
    updated_by_user_id: int,
) -> bool:
    return select_upload_for_scoring(session, task, pilot_id, upload, updated_by_user_id)


def _auto_select_and_rescore(
    session: Session, task: Task, pilot_id: int, upload: IGCUpload, uploaded_by_user_id: int,
) -> None:
    """If the task has been scored, auto-select the newest upload and rescore.
    Late-start uploads are NOT auto-selected — they appear in the dropdown but
    the existing selection stays."""
    if _is_late_start_upload(session, task, upload):
        return

    has_scored = (
        session.scalar(
            select(func.count()).select_from(ScoreResult).where(ScoreResult.task_id == task.id)
        )
        or 0
    ) > 0

    changed = _select_upload_for_scoring(session, task, pilot_id, upload, uploaded_by_user_id)
    if changed:
        rescore_task(session, task.id)
        log_action(
            session,
            actor_user_id=uploaded_by_user_id,
            action="task.auto_score",
            entity_type="task",
            entity_id=str(task.id),
            details={"pilot_id": pilot_id, "upload_id": upload.id, "trigger": "new_upload", "previously_scored": has_scored},
        )


async def _store_upload(
    session: Session,
    task: Task,
    file: UploadFile,
    content: bytes,
    pilot_id: int,
    uploaded_by_user_id: int,
    upload_source: str = "manual",
    auto_select_and_rescore: bool = True,
) -> StoredUpload:
    task_upload_service.get_settings = get_settings
    task_upload_service.rescore_task = rescore_task
    task_upload_service._publish = _publish
    stored = await store_task_upload(
        session,
        task,
        filename=file.filename or "track.igc",
        content=content,
        pilot_id=pilot_id,
        uploaded_by_user_id=uploaded_by_user_id,
        upload_source=upload_source,
        auto_select_and_rescore_enabled=auto_select_and_rescore,
    )
    return StoredUpload(upload=stored.upload, created=stored.created)


def _detach_upload_from_logbook(session: Session, upload_id: int) -> list[PilotFlight]:
    flights = session.scalars(select(PilotFlight).where(PilotFlight.igc_upload_id == upload_id)).all()
    if not flights:
        return []
    points = session.scalars(select(TrackPoint).where(TrackPoint.upload_id == upload_id).order_by(TrackPoint.sequence.asc())).all()
    for flight in flights:
        existing_points = session.scalar(select(func.count(PilotFlightTrackPoint.id)).where(PilotFlightTrackPoint.flight_id == flight.id))
        if not existing_points:
            for point in points:
                session.add(
                    PilotFlightTrackPoint(
                        flight_id=flight.id,
                        sequence=point.sequence,
                        recorded_at=point.recorded_at,
                        latitude=point.latitude,
                        longitude=point.longitude,
                        pressure_altitude_m=point.pressure_altitude_m,
                        gps_altitude_m=point.gps_altitude_m,
                    )
                )
        flight.igc_upload_id = None
        session.add(flight)
    session.flush()
    return flights


@router.post("/api/tasks/{task_id}/uploads", response_model=UploadResponse)
async def upload_igc(
    task_id: int,
    file: UploadFile = File(...),
    pilot_id: int | None = Form(default=None),
    upload_source: str = Form(default="manual"),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UploadResponse:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    effective_pilot_id = pilot_id or user.pilot_id
    if effective_pilot_id is None:
        raise HTTPException(status_code=400, detail="Pilot upload requires a pilot assignment")
    if user.role == "pilot" and user.pilot_id != effective_pilot_id:
        raise HTTPException(status_code=403, detail="Pilots can only upload their own IGC files")
    if session.scalar(select(EventPilot).where(EventPilot.event_id == task.event_id, EventPilot.pilot_id == effective_pilot_id)) is None:
        raise HTTPException(status_code=400, detail="Pilot is not registered for this event")
    content = await file.read()
    max_bytes = get_settings().max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {get_settings().max_upload_size_mb} MB.")
    source = _normalized_upload_source(upload_source)
    stored = await _store_upload(session, task, file, content, effective_pilot_id, user.id, upload_source=source)
    session.commit()
    return _serialize_upload(stored.upload)


@router.post("/api/tasks/{task_id}/uploads/bulk", response_model=list[BulkUploadItemResponse])
async def bulk_upload_igc(task_id: int, files: list[UploadFile] = File(...), user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[BulkUploadItemResponse]:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can bulk upload IGC files")

    max_bytes = get_settings().max_upload_size_mb * 1024 * 1024
    results: list[BulkUploadItemResponse] = []
    selection_change_count = 0
    matched_count = 0
    for file in files:
        filename = file.filename or "track.igc"
        try:
            content = await file.read()
            if len(content) > max_bytes:
                results.append(
                    BulkUploadItemResponse(
                        filename=filename,
                        matched=False,
                        message=f"File too large ({len(content) // 1024}KB). Maximum is {get_settings().max_upload_size_mb}MB.",
                    )
                )
                continue
            parsed = parse_igc(content)
            match = _match_pilot_candidate_for_upload(session, task.event_id, filename, parsed.metadata)
            matched_pilot = match.pilot
            if matched_pilot is None:
                results.append(
                    BulkUploadItemResponse(
                        filename=filename,
                        matched=False,
                        match_confidence=match.confidence,
                        message=match.message,
                    )
                )
                continue
            upload_source = "bulk" if match.confidence == "auto" else "bulk_review"
            stored = await _store_upload(
                session,
                task,
                file,
                content,
                matched_pilot.id,
                user.id,
                upload_source=upload_source,
                auto_select_and_rescore=False,
            )
            matched_count += 1
            late_start = _is_late_start_upload(session, task, stored.upload)
            auto_selected = match.confidence == "auto" and not late_start
            if auto_selected and _select_upload_for_scoring(session, task, matched_pilot.id, stored.upload, user.id):
                selection_change_count += 1
            if match.confidence == "auto":
                message = "Matched and uploaded successfully." if stored.created else "Already uploaded; matched existing file."
            else:
                message = "Uploaded for review; not auto-selected for scoring." if stored.created else "Already uploaded for review; not auto-selected for scoring."
            if late_start:
                message = f"{message} Not auto-selected because the first fix is after start close."
            results.append(
                BulkUploadItemResponse(
                    filename=filename,
                    matched=match.confidence == "auto",
                    upload_id=stored.upload.id,
                    pilot_id=matched_pilot.id,
                    pilot_name=f"{matched_pilot.first_name} {matched_pilot.last_name}".strip(),
                    match_confidence=match.confidence,
                    message=message,
                )
            )
        except Exception as exc:
            results.append(
                BulkUploadItemResponse(
                    filename=filename,
                    matched=False,
                    message=str(exc),
                )
            )
    if selection_change_count > 0:
        rescore_task(session, task.id)
        log_action(
            session,
            actor_user_id=user.id,
            action="task.bulk_rescore",
            entity_type="task",
            entity_id=str(task.id),
            details={"matched_count": matched_count, "selected_count": selection_change_count},
        )
    session.commit()
    return results


@router.get("/api/tasks/{task_id}/uploads", response_model=list[UploadResponse])
def list_uploads(task_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[UploadResponse]:
    if session.get(Task, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    query = select(IGCUpload).where(IGCUpload.task_id == task_id).order_by(IGCUpload.uploaded_at.desc())
    if user.role == "pilot":
        query = query.where(IGCUpload.pilot_id == user.pilot_id)
    uploads = session.scalars(query).all()
    return [_serialize_upload(upload) for upload in uploads]


@router.delete("/api/uploads/{upload_id}")
def delete_upload(upload_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    upload = session.get(IGCUpload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    if user.role == "pilot" and user.pilot_id != upload.pilot_id:
        raise HTTPException(status_code=403, detail="Pilots can only delete their own uploads")

    stored_path = Path(upload.stored_path)
    linked_logbook_flights = _detach_upload_from_logbook(session, upload_id)
    preserve_stored_path = any(flight.stored_path == upload.stored_path for flight in linked_logbook_flights)
    session.execute(
        update(TaskScoringInput)
        .where(TaskScoringInput.selected_upload_id == upload_id)
        .values(selected_upload_id=None, status_override=None, updated_by_user_id=user.id)
    )
    session.execute(delete(ScoreResult).where(ScoreResult.upload_id == upload_id))
    session.execute(delete(TrackPoint).where(TrackPoint.upload_id == upload_id))
    session.execute(delete(IGCUpload).where(IGCUpload.id == upload_id))
    invalidate_task_meet_stats_cache(session, upload.task_id)
    log_action(session, actor_user_id=user.id, action="igc.delete", entity_type="igc_upload", entity_id=str(upload_id), details={"task_id": upload.task_id, "pilot_id": upload.pilot_id, "sha256": upload.sha256})
    session.commit()

    if not preserve_stored_path and stored_path.exists():
        stored_path.unlink()
        try:
            stored_path.parent.rmdir()
        except OSError:
            pass

    return {"status": "deleted", "upload_id": upload_id}


@router.delete("/api/tasks/{task_id}/uploads")
def delete_all_uploads_for_task(task_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, int | str]:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if user.role not in {"admin", "organizer"}:
        raise HTTPException(status_code=403, detail="Organizer access required")

    uploads = session.scalars(select(IGCUpload).where(IGCUpload.task_id == task_id)).all()
    upload_ids = [upload.id for upload in uploads]
    stored_paths = [Path(upload.stored_path) for upload in uploads]
    preserved_paths: set[str] = set()
    if upload_ids:
        for upload in uploads:
            linked_logbook_flights = _detach_upload_from_logbook(session, upload.id)
            if any(flight.stored_path == upload.stored_path for flight in linked_logbook_flights):
                preserved_paths.add(upload.stored_path)
        session.execute(
            update(TaskScoringInput)
            .where(TaskScoringInput.task_id == task_id, TaskScoringInput.selected_upload_id.in_(upload_ids))
            .values(selected_upload_id=None, updated_by_user_id=user.id)
        )
        session.execute(delete(ScoreResult).where(ScoreResult.task_id == task_id))
        session.execute(delete(TrackPoint).where(TrackPoint.upload_id.in_(upload_ids)))
        session.execute(delete(IGCUpload).where(IGCUpload.id.in_(upload_ids)))
    invalidate_task_meet_stats_cache(session, task_id)
    log_action(
        session,
        actor_user_id=user.id,
        action="igc.delete_all",
        entity_type="task",
        entity_id=str(task_id),
        details={"upload_count": len(upload_ids)},
    )
    session.commit()

    for stored_path in stored_paths:
        if str(stored_path) in preserved_paths:
            continue
        if stored_path.exists():
            stored_path.unlink()
            try:
                stored_path.parent.rmdir()
            except OSError:
                pass
    return {"status": "deleted", "deleted_count": len(upload_ids)}


@router.get("/api/uploads/{upload_id}/track")
def get_track_geojson(
    upload_id: int,
    detail: str = Query(default="replay"),
    max_points: int = Query(default=DEFAULT_REPLAY_MAX_POINTS, ge=2, le=100000),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    upload = session.get(IGCUpload, upload_id)
    if upload is None:
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
    timestamps = [
        point.recorded_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if point.recorded_at.tzinfo else point.recorded_at.isoformat()
        for point in replay_points
    ]
    metadata = {
        "detail": "full" if detail == "full" else "replay",
        "original_point_count": len(points),
        "returned_point_count": len(replay_points),
        "max_points": max_points,
        "simplified": simplified.simplified if simplified is not None else False,
        "task_aware": simplified.task_aware if simplified is not None else bool(task_points),
    }
    return {
        "type": "FeatureCollection",
        "metadata": metadata,
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


@router.get("/api/uploads/{upload_id}/download")
def download_upload(upload_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> FileResponse:
    upload = session.get(IGCUpload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    stored_path = Path(upload.stored_path)
    if not stored_path.exists():
        raise HTTPException(status_code=404, detail="Stored IGC file not found")
    return FileResponse(path=stored_path, media_type="application/octet-stream", filename=upload.filename)


@router.get("/api/tasks/{task_id}/uploads/download-all")
def download_all_uploads(task_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> StreamingResponse:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    uploads = session.scalars(select(IGCUpload).where(IGCUpload.task_id == task_id).order_by(IGCUpload.uploaded_at.asc())).all()
    if not uploads:
        raise HTTPException(status_code=404, detail="No IGC uploads are available for this task")

    buffer = io.BytesIO()
    used_names: set[str] = set()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for upload in uploads:
            stored_path = Path(upload.stored_path)
            if not stored_path.exists():
                continue
            entry_name = upload.filename
            if entry_name in used_names:
                stem = Path(entry_name).stem
                suffix = Path(entry_name).suffix or ".igc"
                counter = 2
                while f"{stem}-{counter}{suffix}" in used_names:
                    counter += 1
                entry_name = f"{stem}-{counter}{suffix}"
            used_names.add(entry_name)
            archive.writestr(entry_name, stored_path.read_bytes())
    buffer.seek(0)
    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "-", task.name).strip("-") or f"task-{task_id}"
    headers = {"Content-Disposition": f'attachment; filename="{safe_name}-igc-files.zip"'}
    return StreamingResponse(buffer, media_type="application/zip", headers=headers)
