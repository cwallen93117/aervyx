from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_user, require_admin
from app.models import Event, EventPilot, Task, Turnpoint, User
from app.schemas import EventCreate, EventResponse
from app.services.audit import log_action

router = APIRouter(prefix="/api/events", tags=["events"])


def _event_payload(session: Session, event: Event) -> EventResponse:
    pilot_count = session.scalar(select(func.count()).select_from(EventPilot).where(EventPilot.event_id == event.id)) or 0
    task_count = session.scalar(select(func.count()).select_from(Task).where(Task.event_id == event.id)) or 0
    turnpoint_count = session.scalar(select(func.count()).select_from(Turnpoint).where(Turnpoint.event_id == event.id)) or 0
    return EventResponse(
        id=event.id,
        name=event.name,
        location=event.location,
        starts_on=event.starts_on,
        ends_on=event.ends_on,
        timezone=event.timezone,
        created_at=event.created_at,
        pilot_count=pilot_count,
        task_count=task_count,
        turnpoint_count=turnpoint_count,
    )


@router.get("", response_model=list[EventResponse])
def list_events(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[EventResponse]:
    events = session.scalars(select(Event).order_by(Event.starts_on.desc(), Event.name.asc())).all()
    return [_event_payload(session, event) for event in events]


@router.post("", response_model=EventResponse)
def create_event(payload: EventCreate, admin: User = Depends(require_admin), session: Session = Depends(get_session)) -> EventResponse:
    event = Event(**payload.model_dump())
    session.add(event)
    session.flush()
    log_action(session, actor_user_id=admin.id, action="event.create", entity_type="event", entity_id=str(event.id), details=payload.model_dump(mode="json"))
    session.commit()
    session.refresh(event)
    return _event_payload(session, event)


@router.get("/{event_id}", response_model=EventResponse)
def get_event(event_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> EventResponse:
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_payload(session, event)


@router.put("/{event_id}", response_model=EventResponse)
def update_event(event_id: int, payload: EventCreate, admin: User = Depends(require_admin), session: Session = Depends(get_session)) -> EventResponse:
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    for field, value in payload.model_dump().items():
        setattr(event, field, value)
    log_action(session, actor_user_id=admin.id, action="event.update", entity_type="event", entity_id=str(event.id), details=payload.model_dump(mode="json"))
    session.commit()
    session.refresh(event)
    return _event_payload(session, event)