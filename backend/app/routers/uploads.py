from __future__ import annotations

import asyncio
import hashlib
import io
import re
import zipfile
from datetime import timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_session
from app.deps import get_current_user
from app.models import EventPilot, IGCUpload, Pilot, ScoreResult, Task, TaskScoringInput, TrackPoint, User
from app.schemas import BulkUploadItemResponse, UploadResponse
from app.services.audit import log_action
from app.services.igc import parse_igc
router = APIRouter(tags=["uploads"])


def _normalized_upload_source(value: str | None) -> str:
    normalized = str(value or "manual").strip().lower()
    if normalized == "auto":
        return "bulk"
    return normalized or "manual"


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    lowered = value.lower()
    lowered = re.sub(r"\.[a-z0-9]+$", "", lowered)
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _pilot_search_terms(pilot: Pilot) -> set[str]:
    terms = {
        _normalize_text(f"{pilot.first_name} {pilot.last_name}"),
        _normalize_text(f"{pilot.last_name} {pilot.first_name}"),
        _normalize_text(pilot.first_name),
        _normalize_text(pilot.last_name),
    }
    if pilot.email:
        email_local = pilot.email.split("@", 1)[0]
        terms.add(_normalize_text(pilot.email))
        terms.add(_normalize_text(email_local))
    if pilot.competition_number:
        terms.add(_normalize_text(pilot.competition_number))
    return {term for term in terms if term}


def _filename_token_hints(filename: str) -> set[str]:
    normalized = _normalize_text(filename)
    tokens = {normalized}
    tokens.update(token for token in normalized.split(" ") if token)
    return tokens


def _score_pilot_match(pilot: Pilot, filename: str, metadata: dict) -> int:
    score = 0
    header_name = _normalize_text(str(metadata.get("pilot_name", "")))
    filename_tokens = _filename_token_hints(filename)
    search_terms = _pilot_search_terms(pilot)

    full_name = _normalize_text(f"{pilot.first_name} {pilot.last_name}")
    reverse_name = _normalize_text(f"{pilot.last_name} {pilot.first_name}")
    if header_name:
        if header_name == full_name or header_name == reverse_name:
            score += 120
        elif all(token in header_name.split(" ") for token in full_name.split(" ") if token):
            score += 100
        elif any(term and term in header_name for term in search_terms):
            score += 70

    if pilot.competition_number:
        comp = _normalize_text(pilot.competition_number)
        if comp and comp in filename_tokens:
            score += 90

    if full_name and full_name in filename_tokens:
        score += 100
    elif reverse_name and reverse_name in filename_tokens:
        score += 90
    else:
        first = _normalize_text(pilot.first_name)
        last = _normalize_text(pilot.last_name)
        if first and any(first in token for token in filename_tokens):
            score += 25
        if last and any(last in token for token in filename_tokens):
            score += 40

    email = _normalize_text(pilot.email)
    if email and any(email in token for token in filename_tokens):
        score += 50

    return score


def _match_pilot_for_upload(session: Session, event_id: int, filename: str, metadata: dict) -> Pilot | None:
    event_pilots = session.scalars(
        select(Pilot)
        .join(EventPilot, EventPilot.pilot_id == Pilot.id)
        .where(EventPilot.event_id == event_id)
    ).all()
    if not event_pilots:
        return None

    ranked: list[tuple[int, Pilot]] = []
    for pilot in event_pilots:
        score = _score_pilot_match(pilot, filename, metadata)
        if score > 0:
            ranked.append((score, pilot))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked:
        return None
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None
    best_score, best_pilot = ranked[0]
    return best_pilot if best_score >= 60 else None


def _manual_filename_with_suffix(session: Session, task_id: int, pilot_id: int, filename: str) -> str:
    existing = {
        str(name)
        for name in session.scalars(
            select(IGCUpload.filename).where(
                IGCUpload.task_id == task_id,
                IGCUpload.pilot_id == pilot_id,
            )
        ).all()
    }
    if filename not in existing:
        return filename
    path = Path(filename)
    base = path.stem
    suffix = path.suffix or ""
    match = re.match(r"^(.*?)(\d+)$", base)
    if match:
        root = match.group(1)
        counter = int(match.group(2))
    else:
        root = base
        counter = 1
    while True:
        counter += 1
        candidate = f"{root}{counter}{suffix}"
        if candidate not in existing:
            return candidate


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


async def _store_upload(
    session: Session,
    task: Task,
    file: UploadFile,
    content: bytes,
    pilot_id: int,
    uploaded_by_user_id: int,
    upload_source: str = "manual",
) -> UploadResponse:
    sha256 = hashlib.sha256(content).hexdigest()
    parsed = parse_igc(content)
    filename = file.filename or "track.igc"
    if upload_source == "manual":
        filename = _manual_filename_with_suffix(session, task.id, pilot_id, filename)
    parsed.metadata["upload_source"] = upload_source
    settings = get_settings()
    upload_dir = Path(settings.upload_root) / "igc" / sha256
    await asyncio.to_thread(upload_dir.mkdir, parents=True, exist_ok=True)
    stored_path = upload_dir / filename
    if not await asyncio.to_thread(stored_path.exists):
        await asyncio.to_thread(stored_path.write_bytes, content)
    upload = IGCUpload(
        event_id=task.event_id,
        task_id=task.id,
        pilot_id=pilot_id,
        uploaded_by_user_id=uploaded_by_user_id,
        filename=filename,
        sha256=sha256,
        stored_path=str(stored_path),
        metadata_json=parsed.metadata,
    )
    session.add(upload)
    session.flush()
    for sequence, fix in enumerate(parsed.fixes, start=1):
        session.add(
            TrackPoint(
                upload_id=upload.id,
                sequence=sequence,
                recorded_at=fix.recorded_at,
                latitude=fix.latitude,
                longitude=fix.longitude,
                pressure_altitude_m=fix.pressure_altitude_m,
                gps_altitude_m=fix.gps_altitude_m,
            )
        )
    log_action(
        session,
        actor_user_id=uploaded_by_user_id,
        action="igc.upload",
        entity_type="igc_upload",
        entity_id=str(upload.id),
        details={"task_id": task.id, "pilot_id": pilot_id, "sha256": sha256, "fix_count": parsed.metadata.get("fix_count"), "upload_source": upload_source},
    )
    return _serialize_upload(upload)


@router.post("/api/tasks/{task_id}/uploads", response_model=UploadResponse)
async def upload_igc(task_id: int, file: UploadFile = File(...), pilot_id: int | None = Form(default=None), user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> UploadResponse:
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
    response = await _store_upload(session, task, file, content, effective_pilot_id, user.id, upload_source="manual")
    session.commit()
    return response


@router.post("/api/tasks/{task_id}/uploads/bulk", response_model=list[BulkUploadItemResponse])
async def bulk_upload_igc(task_id: int, files: list[UploadFile] = File(...), user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[BulkUploadItemResponse]:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can bulk upload IGC files")

    results: list[BulkUploadItemResponse] = []
    for file in files:
        filename = file.filename or "track.igc"
        try:
            content = await file.read()
            parsed = parse_igc(content)
            matched_pilot = _match_pilot_for_upload(session, task.event_id, filename, parsed.metadata)
            if matched_pilot is None:
                results.append(
                    BulkUploadItemResponse(
                        filename=filename,
                        matched=False,
                        message="Could not confidently match this file to a pilot in the event roster.",
                    )
                )
                continue
            upload_response = await _store_upload(session, task, file, content, matched_pilot.id, user.id, upload_source="bulk")
            results.append(
                BulkUploadItemResponse(
                    filename=filename,
                    matched=True,
                    upload_id=upload_response.id,
                    pilot_id=matched_pilot.id,
                    pilot_name=f"{matched_pilot.first_name} {matched_pilot.last_name}".strip(),
                    message="Matched and uploaded successfully.",
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
    session.execute(
        update(TaskScoringInput)
        .where(TaskScoringInput.selected_upload_id == upload_id)
        .values(selected_upload_id=None, status_override=None, updated_by_user_id=user.id)
    )
    session.execute(delete(ScoreResult).where(ScoreResult.upload_id == upload_id))
    session.execute(delete(TrackPoint).where(TrackPoint.upload_id == upload_id))
    session.execute(delete(IGCUpload).where(IGCUpload.id == upload_id))
    log_action(session, actor_user_id=user.id, action="igc.delete", entity_type="igc_upload", entity_id=str(upload_id), details={"task_id": upload.task_id, "pilot_id": upload.pilot_id, "sha256": upload.sha256})
    session.commit()

    if stored_path.exists():
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
    if upload_ids:
        session.execute(
            update(TaskScoringInput)
            .where(TaskScoringInput.task_id == task_id, TaskScoringInput.selected_upload_id.in_(upload_ids))
            .values(selected_upload_id=None, updated_by_user_id=user.id)
        )
        session.execute(delete(ScoreResult).where(ScoreResult.task_id == task_id))
        session.execute(delete(TrackPoint).where(TrackPoint.upload_id.in_(upload_ids)))
        session.execute(delete(IGCUpload).where(IGCUpload.id.in_(upload_ids)))
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
        if stored_path.exists():
            stored_path.unlink()
            try:
                stored_path.parent.rmdir()
            except OSError:
                pass
    return {"status": "deleted", "deleted_count": len(upload_ids)}


@router.get("/api/uploads/{upload_id}/track")
def get_track_geojson(upload_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    upload = session.get(IGCUpload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    pilot = session.get(Pilot, upload.pilot_id)
    points = session.scalars(select(TrackPoint).where(TrackPoint.upload_id == upload_id).order_by(TrackPoint.sequence)).all()
    coordinates = [
        [
            point.longitude,
            point.latitude,
            float(point.gps_altitude_m if point.gps_altitude_m is not None else point.pressure_altitude_m if point.pressure_altitude_m is not None else 0),
        ]
        for point in points
    ]
    timestamps = [
        point.recorded_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if point.recorded_at.tzinfo else point.recorded_at.isoformat()
        for point in points
    ]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "upload_id": upload.id,
                    "pilot_name": f"{pilot.first_name} {pilot.last_name}" if pilot else "Unknown",
                    "timestamps": timestamps,
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
