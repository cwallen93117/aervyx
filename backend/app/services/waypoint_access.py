from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Event, EventPilot, Turnpoint, TurnpointSource, User
from app.services.challenge_defaults import CHALLENGE_TEMPLATE_KIND
from app.services.event_access import STAFF_ROLES, can_manage_event
from app.services.pilot_identity import participant_event_ids_for_user


def can_edit_waypoints(session: Session, user: User, event: Event | None) -> bool:
    if event is None:
        return False
    if (event.event_kind or "competition") == CHALLENGE_TEMPLATE_KIND:
        return event.owner_user_id == user.id
    return can_manage_event(session, user, event)


def can_view_waypoints(session: Session, user: User, event: Event | None, participant_event_ids: set[int] | None = None) -> bool:
    if event is None:
        return False
    event_kind = event.event_kind or "competition"
    if can_edit_waypoints(session, user, event):
        return True
    if event_kind == CHALLENGE_TEMPLATE_KIND:
        return False
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


def waypoint_file_records_for_user(session: Session, user: User) -> list[dict]:
    participant_event_ids = participant_event_ids_for_user(session, user)
    turnpoint_counts = (
        select(Turnpoint.source_id.label("source_id"), func.count(Turnpoint.id).label("turnpoint_count"))
        .where(Turnpoint.source_id.is_not(None))
        .group_by(Turnpoint.source_id)
        .subquery()
    )
    rows = session.execute(
        select(TurnpointSource, Event, turnpoint_counts.c.turnpoint_count)
        .join(Event, Event.id == TurnpointSource.event_id)
        .outerjoin(turnpoint_counts, turnpoint_counts.c.source_id == TurnpointSource.id)
        .order_by(TurnpointSource.uploaded_at.desc(), TurnpointSource.id.desc())
    ).all()
    records: list[dict] = []
    for source, event, turnpoint_count in rows:
        if not can_view_waypoints(session, user, event, participant_event_ids):
            continue
        records.append(
            {
                "source_id": source.id,
                "event_id": source.event_id,
                "event_name": event.name,
                "event_kind": event.event_kind or "competition",
                "filename": source.filename,
                "file_format": source.file_format,
                "sha256": source.sha256,
                "enabled": source.enabled,
                "uploaded_at": source.uploaded_at,
                "turnpoint_count": turnpoint_count or 0,
                "can_edit": can_edit_waypoints(session, user, event),
            }
        )
    return records
