from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Event, User

STAFF_ROLES = {"admin", "organizer"}


def can_manage_event(session: Session, user: User, event: Event | None) -> bool:
    return event is not None and user.role in STAFF_ROLES


def require_event_manager(session: Session, user: User, event: Event | None) -> Event:
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if not can_manage_event(session, user, event):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Event management access required")
    return event
