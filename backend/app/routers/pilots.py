from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_user, require_staff
from app.models import Event, EventPilot, Pilot, User
from app.schemas import PilotResponse, PilotUpsert
from app.services.audit import log_action
from app.services.pilot_identity import (
    apply_pilot_profile,
    ensure_event_membership,
    ensure_pilot_login_identity,
    find_canonical_pilot,
    linked_user_for_pilot,
    normalize_email,
)

router = APIRouter(tags=["pilots"])


def _pilot_payload(session: Session, pilot: Pilot, temp_password: str | None = None) -> PilotResponse:
    user = linked_user_for_pilot(session, pilot)
    return PilotResponse(
        id=pilot.id,
        first_name=pilot.first_name,
        last_name=pilot.last_name,
        email=pilot.email,
        nation=pilot.nation,
        competition_number=pilot.competition_number,
        civl_id=pilot.civl_id,
        portal_username=user.username if user else None,
        is_claimed=user is not None,
        temp_password=temp_password,
    )


@router.get("/api/events/{event_id}/pilots", response_model=list[PilotResponse])
def list_pilots(event_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[PilotResponse]:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    pilots = session.scalars(select(Pilot).join(EventPilot, EventPilot.pilot_id == Pilot.id).where(EventPilot.event_id == event_id).order_by(Pilot.last_name.asc(), Pilot.first_name.asc())).all()
    return [_pilot_payload(session, pilot) for pilot in pilots]


@router.get("/api/pilots", response_model=list[PilotResponse])
def list_people(search: str | None = None, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> list[PilotResponse]:
    query = select(Pilot)
    if search:
        pattern = f"%{search.lower()}%"
        query = query.where(
            or_(
                func.lower(Pilot.first_name).like(pattern),
                func.lower(Pilot.last_name).like(pattern),
                func.lower(func.coalesce(Pilot.email, "")).like(pattern),
                func.lower(func.coalesce(Pilot.competition_number, "")).like(pattern),
            )
        )
    pilots = session.scalars(query.order_by(Pilot.last_name.asc(), Pilot.first_name.asc())).all()
    return [_pilot_payload(session, pilot) for pilot in pilots]


@router.post("/api/events/{event_id}/pilots", response_model=PilotResponse)
def create_pilot(event_id: int, payload: PilotUpsert, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> PilotResponse:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    email = normalize_email(payload.email)
    pilot = find_canonical_pilot(
        session,
        email=email,
        competition_number=payload.competition_number,
        civl_id=payload.civl_id,
    )
    if pilot is None:
        pilot = Pilot(first_name=payload.first_name, last_name=payload.last_name, email=email, nation=payload.nation, competition_number=payload.competition_number, civl_id=payload.civl_id)
    else:
        apply_pilot_profile(
            pilot,
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=email,
            nation=payload.nation,
            competition_number=payload.competition_number,
            civl_id=payload.civl_id,
        )
    session.add(pilot)
    session.flush()
    identity = ensure_pilot_login_identity(session, pilot, payload.username, payload.password)
    ensure_event_membership(session, event_id, identity.pilot.id)
    username = identity.user.username if identity.user else None
    log_action(session, actor_user_id=admin.id, action="pilot.create", entity_type="pilot", entity_id=str(identity.pilot.id), details={"event_id": event_id, "username": username})
    session.commit()
    return _pilot_payload(session, identity.pilot, temp_password=identity.temp_password)


@router.post("/api/events/{event_id}/pilots/{pilot_id}/assign", response_model=PilotResponse)
def assign_existing_pilot(event_id: int, pilot_id: int, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> PilotResponse:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    pilot = session.get(Pilot, pilot_id)
    if pilot is None:
        raise HTTPException(status_code=404, detail="Pilot not found")
    identity = ensure_pilot_login_identity(session, pilot)
    ensure_event_membership(session, event_id, identity.pilot.id)
    log_action(session, actor_user_id=admin.id, action="pilot.assign_existing", entity_type="pilot", entity_id=str(identity.pilot.id), details={"event_id": event_id, "source_pilot_id": pilot_id})
    session.commit()
    return _pilot_payload(session, identity.pilot, temp_password=identity.temp_password)


@router.put("/api/pilots/{pilot_id}", response_model=PilotResponse)
def update_pilot(pilot_id: int, payload: PilotUpsert, actor: User = Depends(get_current_user), session: Session = Depends(get_session)) -> PilotResponse:
    if actor.role not in {"admin", "organizer"}:
        raise HTTPException(status_code=403, detail="Staff role required")
    pilot = session.get(Pilot, pilot_id)
    if pilot is None:
        raise HTTPException(status_code=404, detail="Pilot not found")
    if actor.role != "admin":
        claim = session.scalar(select(User).where(User.pilot_id == pilot.id))
        if claim is not None:
            raise HTTPException(status_code=403, detail="Only admins can edit claimed pilot accounts")
    apply_pilot_profile(
        pilot,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        nation=payload.nation,
        competition_number=payload.competition_number,
        civl_id=payload.civl_id,
    )
    identity = ensure_pilot_login_identity(session, pilot, payload.username, payload.password)
    log_action(session, actor_user_id=actor.id, action="pilot.update", entity_type="pilot", entity_id=str(identity.pilot.id), details={"competition_number": identity.pilot.competition_number})
    session.commit()
    return _pilot_payload(session, identity.pilot, temp_password=identity.temp_password)


@router.delete("/api/events/{event_id}/pilots/{pilot_id}", status_code=204)
def remove_pilot(event_id: int, pilot_id: int, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> Response:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    event_pilot = session.scalar(select(EventPilot).where(EventPilot.event_id == event_id, EventPilot.pilot_id == pilot_id))
    if event_pilot is None:
        raise HTTPException(status_code=404, detail="Pilot is not assigned to this event")
    session.delete(event_pilot)
    log_action(session, actor_user_id=admin.id, action="pilot.remove", entity_type="pilot", entity_id=str(pilot_id), details={"event_id": event_id})
    session.commit()
    return Response(status_code=204)


@router.post("/api/events/{event_id}/pilots/import-csv", response_model=list[PilotResponse])
async def import_pilots(event_id: int, file: UploadFile = File(...), admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> list[PilotResponse]:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    imported: list[PilotResponse] = []
    for row in reader:
        if not row.get("first_name") or not row.get("last_name"):
            continue
        email = normalize_email(row.get("email"))
        pilot = find_canonical_pilot(
            session,
            email=email,
            competition_number=(row.get("competition_number") or "").strip() or None,
            civl_id=(row.get("civl_id") or "").strip() or None,
        )
        if pilot is None:
            pilot = Pilot(
                first_name=row["first_name"].strip(),
                last_name=row["last_name"].strip(),
                email=email,
                nation=(row.get("nation") or "").strip() or None,
                competition_number=(row.get("competition_number") or "").strip() or None,
                civl_id=(row.get("civl_id") or "").strip() or None,
            )
        else:
            apply_pilot_profile(
                pilot,
                first_name=row["first_name"].strip(),
                last_name=row["last_name"].strip(),
                email=email,
                nation=(row.get("nation") or "").strip() or None,
                competition_number=(row.get("competition_number") or "").strip() or None,
                civl_id=(row.get("civl_id") or "").strip() or None,
            )
        session.add(pilot)
        session.flush()
        identity = ensure_pilot_login_identity(session, pilot, (row.get("username") or "").strip() or None, (row.get("password") or "").strip() or None)
        ensure_event_membership(session, event_id, identity.pilot.id)
        imported.append(_pilot_payload(session, identity.pilot, temp_password=identity.temp_password))
    log_action(session, actor_user_id=admin.id, action="pilot.import_csv", entity_type="event", entity_id=str(event_id), details={"filename": file.filename, "count": len(imported)})
    session.commit()
    return imported
