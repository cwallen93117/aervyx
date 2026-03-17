from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_session
from app.deps import get_current_user, require_admin
from app.models import Event, Turnpoint, TurnpointSource, User
from app.schemas import TurnpointResponse, TurnpointUploadResponse
from app.services.audit import log_action
from app.services.turnpoints import parse_turnpoint_upload

router = APIRouter(tags=["turnpoints"])


@router.get("/api/events/{event_id}/turnpoints", response_model=list[TurnpointResponse])
def list_turnpoints(event_id: int, search: str | None = Query(default=None), user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[TurnpointResponse]:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    query = select(Turnpoint).where(Turnpoint.event_id == event_id)
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Turnpoint.name.ilike(pattern), Turnpoint.code.ilike(pattern)))
    turnpoints = session.scalars(query.order_by(Turnpoint.name.asc())).all()
    return [TurnpointResponse.model_validate(turnpoint) for turnpoint in turnpoints]


@router.post("/api/events/{event_id}/turnpoints/upload", response_model=TurnpointUploadResponse)
async def upload_turnpoints(event_id: int, file: UploadFile = File(...), admin: User = Depends(require_admin), session: Session = Depends(get_session)) -> TurnpointUploadResponse:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    content = await file.read()
    sha256 = hashlib.sha256(content).hexdigest()
    file_format, records = parse_turnpoint_upload(file.filename or "turnpoints.csv", content)
    settings = get_settings()
    upload_dir = Path(settings.upload_root) / "turnpoints" / sha256
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = upload_dir / (file.filename or f"turnpoints.{file_format}")
    if not stored_path.exists():
        stored_path.write_bytes(content)
    source = TurnpointSource(event_id=event_id, filename=file.filename or stored_path.name, content_type=file.content_type, file_format=file_format, sha256=sha256, stored_path=str(stored_path))
    session.add(source)
    session.flush()
    for record in records:
        session.add(Turnpoint(event_id=event_id, source_id=source.id, code=record.code, name=record.name, latitude=record.latitude, longitude=record.longitude, elevation_m=record.elevation_m))
    log_action(session, actor_user_id=admin.id, action="turnpoint.upload", entity_type="turnpoint_source", entity_id=str(source.id), details={"event_id": event_id, "filename": source.filename, "sha256": sha256, "count": len(records)})
    session.commit()
    return TurnpointUploadResponse(source_id=source.id, format=file_format, imported_count=len(records), sha256=sha256, filename=source.filename)