from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_session
from app.deps import get_current_user, require_admin
from app.models import Event, EventTurnpointSlot, Turnpoint, TurnpointSource, User
from app.schemas import TurnpointResponse, TurnpointSlotResponse, TurnpointUploadResponse
from app.services.audit import log_action
from app.services.turnpoints import parse_turnpoint_upload

router = APIRouter(tags=["turnpoints"])


def _validate_slot_number(slot_number: int) -> int:
    if slot_number not in {1, 2, 3}:
        raise HTTPException(status_code=400, detail="Turnpoint slot must be 1, 2, or 3.")
    return slot_number


def _slot_payload(session: Session, event_id: int, slot_number: int) -> TurnpointSlotResponse:
    slot = session.scalar(select(EventTurnpointSlot).where(EventTurnpointSlot.event_id == event_id, EventTurnpointSlot.slot_number == slot_number))
    if slot is None or slot.source_id is None:
        return TurnpointSlotResponse(slot_number=slot_number, turnpoint_count=0)
    source = session.get(TurnpointSource, slot.source_id)
    if source is None:
        return TurnpointSlotResponse(slot_number=slot_number, turnpoint_count=0)
    turnpoint_count = session.scalar(select(func.count()).select_from(Turnpoint).where(Turnpoint.source_id == source.id)) or 0
    return TurnpointSlotResponse(
        slot_number=slot_number,
        source_id=source.id,
        filename=source.filename,
        file_format=source.file_format,
        sha256=source.sha256,
        uploaded_at=source.uploaded_at,
        turnpoint_count=turnpoint_count,
    )


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


@router.get("/api/events/{event_id}/turnpoint-slots", response_model=list[TurnpointSlotResponse])
def list_turnpoint_slots(event_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[TurnpointSlotResponse]:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return [_slot_payload(session, event_id, slot_number) for slot_number in (1, 2, 3)]


@router.post("/api/events/{event_id}/turnpoints/upload", response_model=TurnpointUploadResponse)
async def upload_turnpoints(event_id: int, slot_number: int = Query(...), file: UploadFile = File(...), admin: User = Depends(require_admin), session: Session = Depends(get_session)) -> TurnpointUploadResponse:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    slot_number = _validate_slot_number(slot_number)
    content = await file.read()
    sha256 = hashlib.sha256(content).hexdigest()
    file_format, records = parse_turnpoint_upload(file.filename or "turnpoints.csv", content)
    settings = get_settings()
    upload_dir = Path(settings.upload_root) / "turnpoints" / sha256
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = upload_dir / (file.filename or f"turnpoints.{file_format}")
    if not stored_path.exists():
        stored_path.write_bytes(content)
    slot = session.scalar(select(EventTurnpointSlot).where(EventTurnpointSlot.event_id == event_id, EventTurnpointSlot.slot_number == slot_number))
    previous_source_id = slot.source_id if slot else None
    if previous_source_id is not None:
        session.query(Turnpoint).filter(Turnpoint.source_id == previous_source_id).delete()
        previous_source = session.get(TurnpointSource, previous_source_id)
        if previous_source is not None:
            session.delete(previous_source)
        session.flush()
    source = TurnpointSource(event_id=event_id, filename=file.filename or stored_path.name, content_type=file.content_type, file_format=file_format, sha256=sha256, stored_path=str(stored_path))
    session.add(source)
    session.flush()
    if slot is None:
        slot = EventTurnpointSlot(event_id=event_id, slot_number=slot_number, source_id=source.id)
        session.add(slot)
    else:
        slot.source_id = source.id
    for record in records:
        session.add(Turnpoint(event_id=event_id, source_id=source.id, code=record.code, name=record.name, latitude=record.latitude, longitude=record.longitude, elevation_m=record.elevation_m))
    log_action(session, actor_user_id=admin.id, action="turnpoint.upload", entity_type="turnpoint_source", entity_id=str(source.id), details={"event_id": event_id, "slot_number": slot_number, "filename": source.filename, "sha256": sha256, "count": len(records), "replaced_source_id": previous_source_id})
    session.commit()
    return TurnpointUploadResponse(source_id=source.id, format=file_format, imported_count=len(records), sha256=sha256, filename=source.filename)
