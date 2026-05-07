from __future__ import annotations

import csv
import io
import re

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db import get_session
from app.deps import get_current_user, require_staff
from app.models import Event, EventPilot, Pilot, User
from app.schemas import PilotResponse, PilotUpsert
from app.services.audit import log_action
from app.services.seeding import DEFAULT_PILOT_PASSWORD

router = APIRouter(tags=["pilots"])


def _slug_username(first_name: str, last_name: str, competition_number: str | None) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", f"{first_name}-{last_name}-{competition_number or 'pilot'}".lower()).strip("-")
    return base or "pilot"


def _email_identity(value: str | None) -> str | None:
    candidate = (value or "").strip().lower()
    return candidate if "@" in candidate else None


def _is_auto_generated_user(user: User) -> bool:
    return "@" not in (user.username or "")


def _linked_user_for_pilot(session: Session, pilot: Pilot) -> User | None:
    linked_users = session.scalars(
        select(User).where(User.pilot_id == pilot.id, User.is_active.is_(True)).order_by(User.id.asc())
    ).all()
    if not linked_users:
        return None
    email = _email_identity(pilot.email)
    if email:
        email_user = next((user for user in linked_users if (user.username or "").strip().lower() == email), None)
        if email_user is not None:
            return email_user
    return linked_users[0]


def _link_matching_email_user(session: Session, pilot: Pilot) -> User | None:
    email = _email_identity(pilot.email)
    if email is None:
        return None
    email_user = session.scalar(
        select(User).where(
            func.lower(User.username) == email,
            User.role == "pilot",
            User.is_active.is_(True),
        )
    )
    if email_user is None:
        return None
    linked_users = session.scalars(
        select(User).where(User.pilot_id == pilot.id, User.is_active.is_(True)).order_by(User.id.asc())
    ).all()
    real_linked_user = next((user for user in linked_users if user.id != email_user.id and not _is_auto_generated_user(user)), None)
    if real_linked_user is not None:
        return None
    for linked_user in linked_users:
        if linked_user.id != email_user.id and _is_auto_generated_user(linked_user):
            linked_user.is_active = False
            linked_user.pilot_id = None
            session.add(linked_user)
    email_user.pilot_id = pilot.id
    session.add(email_user)
    return email_user


def _ensure_portal_user(session: Session, pilot: Pilot, username: str | None, password: str | None) -> tuple[str, str | None]:
    linked_email_user = _link_matching_email_user(session, pilot)
    if linked_email_user is not None:
        return linked_email_user.username, None
    existing = _linked_user_for_pilot(session, pilot)
    generated_password = password or DEFAULT_PILOT_PASSWORD
    username_value = username or _slug_username(pilot.first_name, pilot.last_name, pilot.competition_number)
    if existing is None:
        candidate = username_value
        suffix = 1
        while session.scalar(select(User).where(User.username == candidate)) is not None:
            suffix += 1
            candidate = f"{username_value}-{suffix}"
        session.add(User(username=candidate, full_name=f"{pilot.first_name} {pilot.last_name}", role="pilot", pilot_id=pilot.id, password_hash=hash_password(generated_password)))
        return candidate, generated_password
    return existing.username, None


def _pilot_payload(session: Session, pilot: Pilot, temp_password: str | None = None) -> PilotResponse:
    user = _linked_user_for_pilot(session, pilot)
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
    pilot = Pilot(first_name=payload.first_name, last_name=payload.last_name, email=payload.email, nation=payload.nation, competition_number=payload.competition_number, civl_id=payload.civl_id)
    session.add(pilot)
    session.flush()
    session.add(EventPilot(event_id=event_id, pilot_id=pilot.id))
    username, temp_password = _ensure_portal_user(session, pilot, payload.username, payload.password)
    log_action(session, actor_user_id=admin.id, action="pilot.create", entity_type="pilot", entity_id=str(pilot.id), details={"event_id": event_id, "username": username})
    session.commit()
    return _pilot_payload(session, pilot, temp_password=temp_password)


@router.post("/api/events/{event_id}/pilots/{pilot_id}/assign", response_model=PilotResponse)
def assign_existing_pilot(event_id: int, pilot_id: int, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> PilotResponse:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    pilot = session.get(Pilot, pilot_id)
    if pilot is None:
        raise HTTPException(status_code=404, detail="Pilot not found")
    existing = session.scalar(select(EventPilot).where(EventPilot.event_id == event_id, EventPilot.pilot_id == pilot_id))
    if existing is None:
        session.add(EventPilot(event_id=event_id, pilot_id=pilot_id))
        log_action(session, actor_user_id=admin.id, action="pilot.assign_existing", entity_type="pilot", entity_id=str(pilot_id), details={"event_id": event_id})
    _link_matching_email_user(session, pilot)
    session.commit()
    return _pilot_payload(session, pilot)


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
    for field in ["first_name", "last_name", "email", "nation", "competition_number", "civl_id"]:
        setattr(pilot, field, getattr(payload, field))
    _, temp_password = _ensure_portal_user(session, pilot, payload.username, payload.password)
    log_action(session, actor_user_id=actor.id, action="pilot.update", entity_type="pilot", entity_id=str(pilot.id), details={"competition_number": pilot.competition_number})
    session.commit()
    return _pilot_payload(session, pilot, temp_password=temp_password)


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
        pilot = Pilot(
            first_name=row["first_name"].strip(),
            last_name=row["last_name"].strip(),
            email=(row.get("email") or "").strip() or None,
            nation=(row.get("nation") or "").strip() or None,
            competition_number=(row.get("competition_number") or "").strip() or None,
            civl_id=(row.get("civl_id") or "").strip() or None,
        )
        session.add(pilot)
        session.flush()
        session.add(EventPilot(event_id=event_id, pilot_id=pilot.id))
        _, temp_password = _ensure_portal_user(session, pilot, (row.get("username") or "").strip() or None, (row.get("password") or "").strip() or None)
        imported.append(_pilot_payload(session, pilot, temp_password=temp_password))
    log_action(session, actor_user_id=admin.id, action="pilot.import_csv", entity_type="event", entity_id=str(event_id), details={"filename": file.filename, "count": len(imported)})
    session.commit()
    return imported
