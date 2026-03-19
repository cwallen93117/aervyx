from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_session
from app.deps import get_current_user
from app.models import EventPilot, IGCUpload, Pilot, Task, TrackPoint, User
from app.schemas import UploadResponse
from app.services.audit import log_action
from app.services.igc import parse_igc
router = APIRouter(tags=["uploads"])


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
    sha256 = hashlib.sha256(content).hexdigest()
    parsed = parse_igc(content)
    settings = get_settings()
    upload_dir = Path(settings.upload_root) / "igc" / sha256
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = upload_dir / (file.filename or "track.igc")
    if not stored_path.exists():
        stored_path.write_bytes(content)
    upload = IGCUpload(event_id=task.event_id, task_id=task.id, pilot_id=effective_pilot_id, uploaded_by_user_id=user.id, filename=file.filename or stored_path.name, sha256=sha256, stored_path=str(stored_path), metadata_json=parsed.metadata)
    session.add(upload)
    session.flush()
    for sequence, fix in enumerate(parsed.fixes, start=1):
        session.add(TrackPoint(upload_id=upload.id, sequence=sequence, recorded_at=fix.recorded_at, latitude=fix.latitude, longitude=fix.longitude, pressure_altitude_m=fix.pressure_altitude_m, gps_altitude_m=fix.gps_altitude_m))
    log_action(session, actor_user_id=user.id, action="igc.upload", entity_type="igc_upload", entity_id=str(upload.id), details={"task_id": task.id, "pilot_id": effective_pilot_id, "sha256": sha256, "fix_count": parsed.metadata.get("fix_count")})
    session.commit()
    return UploadResponse.model_validate(upload)


@router.get("/api/tasks/{task_id}/uploads", response_model=list[UploadResponse])
def list_uploads(task_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[UploadResponse]:
    if session.get(Task, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    query = select(IGCUpload).where(IGCUpload.task_id == task_id).order_by(IGCUpload.uploaded_at.desc())
    if user.role == "pilot":
        query = query.where(IGCUpload.pilot_id == user.pilot_id)
    uploads = session.scalars(query).all()
    return [UploadResponse.model_validate(upload) for upload in uploads]


@router.get("/api/uploads/{upload_id}/track")
def get_track_geojson(upload_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    upload = session.get(IGCUpload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    if user.role == "pilot" and user.pilot_id != upload.pilot_id:
        raise HTTPException(status_code=403, detail="Pilots can only view their own uploads")
    pilot = session.get(Pilot, upload.pilot_id)
    points = session.scalars(select(TrackPoint).where(TrackPoint.upload_id == upload_id).order_by(TrackPoint.sequence)).all()
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"upload_id": upload.id, "pilot_name": f"{pilot.first_name} {pilot.last_name}" if pilot else "Unknown"},
                "geometry": {"type": "LineString", "coordinates": [[point.longitude, point.latitude] for point in points]},
            }
        ],
    }
