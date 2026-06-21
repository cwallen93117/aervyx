from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, EventCollaborator, User

STAFF_ROLES = {"admin", "organizer"}
MANAGE_COLLABORATOR_ROLES = {"owner", "editor"}


def can_manage_event(session: Session, user: User, event: Event | None) -> bool:
    if event is None:
        return False
    if user.role in STAFF_ROLES:
        return True
    if (event.event_kind or "competition") != "challenge":
        return False
    if event.owner_user_id == user.id:
        return True
    collaborator = session.scalar(
        select(EventCollaborator).where(
            EventCollaborator.event_id == event.id,
            EventCollaborator.user_id == user.id,
            EventCollaborator.role.in_(MANAGE_COLLABORATOR_ROLES),
        )
    )
    return collaborator is not None


def require_event_manager(session: Session, user: User, event: Event | None) -> Event:
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if not can_manage_event(session, user, event):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Event management access required")
    return event
