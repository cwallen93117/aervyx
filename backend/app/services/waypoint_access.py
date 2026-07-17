from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Event, User
from app.services.event_access import STAFF_ROLES, can_manage_event
from app.services.pilot_identity import participant_event_ids_for_user


def can_edit_waypoints(session: Session, user: User, event: Event | None) -> bool:
    if event is None:
        return False
    return can_manage_event(session, user, event)


def can_view_waypoints(session: Session, user: User, event: Event | None, participant_event_ids: set[int] | None = None) -> bool:
    if event is None:
        return False
    if can_edit_waypoints(session, user, event):
        return True
    if user.role in STAFF_ROLES:
        return True
    visibility = event.visibility or "private"
    if visibility in {"public", "users"}:
        return True
    if visibility == "participants":
        if participant_event_ids is None:
            participant_event_ids = participant_event_ids_for_user(session, user)
        return event.id in participant_event_ids
    return False
