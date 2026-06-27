from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_user
from app.models import BuddyGroup, BuddyGroupMember, Event, EventCollaborator, EventPilot, Task, User
from app.routers.events import _event_payload
from app.schemas import ChallengeCreate, ChallengeResponse, ChallengeUpdate
from app.services.audit import log_action
from app.services.challenge_defaults import challenge_event_defaults, copy_challenge_default_assets
from app.services.event_access import can_manage_event, require_event_manager
from app.services.pilot_identity import ensure_event_membership

router = APIRouter(prefix="/api/challenges", tags=["challenges"])

CHALLENGE_TYPES = {"open_distance", "race_to_goal_with_gates"}


def _public_slug(session: Session) -> str:
    while True:
        slug = secrets.token_urlsafe(8).replace("_", "-").lower()
        if session.scalar(select(Event.id).where(Event.public_slug == slug)) is None:
            return slug


def _challenge_settings(user: User) -> dict:
    return challenge_event_defaults(user)


def _challenge_type_for_event(session: Session, event_id: int) -> str:
    task_type = session.scalar(
        select(Task.task_type)
        .where(Task.event_id == event_id)
        .order_by(Task.id.asc())
        .limit(1)
    )
    return task_type if task_type in CHALLENGE_TYPES else "open_distance"


def _challenge_payload(session: Session, event: Event) -> ChallengeResponse:
    payload = _event_payload(session, event).model_dump()
    slug = payload.get("public_slug")
    payload["challenge_type"] = _challenge_type_for_event(session, event.id)
    payload["public_url"] = f"/scores?challenge={slug}" if slug else None
    return ChallengeResponse(**payload)


def _load_owned_buddy_group(session: Session, user: User, group_id: int | None) -> BuddyGroup | None:
    if group_id is None:
        return None
    group = session.get(BuddyGroup, group_id)
    if group is None or group.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Buddy group not found")
    return group


def _seed_roster_from_buddy_group(session: Session, event: Event, group: BuddyGroup | None, user: User) -> int:
    pilot_ids: set[int] = set()
    if user.pilot_id is not None:
        pilot_ids.add(user.pilot_id)
    if group is not None:
        pilot_ids.update(
            session.scalars(
                select(BuddyGroupMember.pilot_id).where(BuddyGroupMember.group_id == group.id)
            ).all()
        )
    for pilot_id in sorted(pilot_ids):
        ensure_event_membership(session, event.id, pilot_id)
    return len(pilot_ids)


@router.get("", response_model=list[ChallengeResponse])
def list_challenges(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[ChallengeResponse]:
    if user.role in {"admin", "organizer"}:
        events = session.scalars(
            select(Event)
            .where(Event.event_kind == "challenge")
            .order_by(Event.updated_at.desc(), Event.name.asc())
        ).all()
    else:
        collaborator_event_ids = session.scalars(
            select(EventCollaborator.event_id).where(EventCollaborator.user_id == user.id)
        ).all()
        visible_ids = set(collaborator_event_ids)
        visibility_filters = [Event.owner_user_id == user.id]
        if visible_ids:
            visibility_filters.append(Event.id.in_(visible_ids))
        events = session.scalars(
            select(Event)
            .where(
                Event.event_kind == "challenge",
                or_(*visibility_filters),
            )
            .order_by(Event.updated_at.desc(), Event.name.asc())
        ).all()
    return [_challenge_payload(session, event) for event in events]


@router.post("", response_model=ChallengeResponse, status_code=status.HTTP_201_CREATED)
def create_challenge(payload: ChallengeCreate, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> ChallengeResponse:
    if payload.ends_on < payload.starts_on:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="End date must be on or after start date")
    group = _load_owned_buddy_group(session, user, payload.source_buddy_group_id)
    settings = _challenge_settings(user)
    visibility = payload.visibility if payload.visibility in {"public", "users", "participants", "private"} else "private"
    event = Event(
        **settings,
        name=payload.name.strip()[:160] or "Challenge",
        location=payload.location.strip()[:160],
        starts_on=payload.starts_on,
        ends_on=payload.ends_on,
        timezone=payload.timezone.strip() or "UTC",
        visibility=visibility,
        is_public_tracking=payload.is_public_tracking,
        event_kind="challenge",
        owner_user_id=user.id,
        source_buddy_group_id=group.id if group else None,
        public_slug=_public_slug(session),
        public_listed=payload.public_listed,
    )
    session.add(event)
    session.flush()
    session.add(EventCollaborator(event_id=event.id, user_id=user.id, role="owner"))
    seeded_count = _seed_roster_from_buddy_group(session, event, group, user)
    copy_challenge_default_assets(session, user, event)
    task_type = payload.challenge_type if payload.challenge_type in CHALLENGE_TYPES else "open_distance"
    session.add(
        Task(
            event_id=event.id,
            name=event.name,
            task_date=payload.starts_on,
            task_type=task_type,
            status="draft",
            start_gate_count=event.default_start_gate_count or 1,
            start_gate_interval_seconds=event.default_start_gate_interval_seconds,
        )
    )
    log_action(
        session,
        actor_user_id=user.id,
        action="challenge.create",
        entity_type="event",
        entity_id=str(event.id),
        details={"source_buddy_group_id": event.source_buddy_group_id, "seeded_count": seeded_count, "challenge_type": task_type},
    )
    session.commit()
    session.refresh(event)
    return _challenge_payload(session, event)


@router.get("/{event_id}", response_model=ChallengeResponse)
def get_challenge(event_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> ChallengeResponse:
    event = session.get(Event, event_id)
    if event is None or (event.event_kind or "competition") != "challenge":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found")
    if not can_manage_event(session, user, event):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Challenge access required")
    return _challenge_payload(session, event)


@router.patch("/{event_id}", response_model=ChallengeResponse)
def update_challenge(event_id: int, payload: ChallengeUpdate, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> ChallengeResponse:
    event = require_event_manager(session, user, session.get(Event, event_id))
    if (event.event_kind or "competition") != "challenge":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found")
    if payload.name is not None:
        event.name = payload.name.strip()[:160] or event.name
    if payload.location is not None:
        event.location = payload.location.strip()[:160]
    if payload.starts_on is not None:
        event.starts_on = payload.starts_on
    if payload.ends_on is not None:
        event.ends_on = payload.ends_on
    if event.ends_on < event.starts_on:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="End date must be on or after start date")
    if payload.timezone is not None:
        event.timezone = payload.timezone.strip() or "UTC"
    if payload.visibility is not None:
        if payload.visibility not in {"public", "users", "participants", "private"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid visibility")
        event.visibility = payload.visibility
    if payload.public_listed is not None:
        event.public_listed = payload.public_listed
    if payload.is_public_tracking is not None:
        event.is_public_tracking = payload.is_public_tracking
    log_action(session, actor_user_id=user.id, action="challenge.update", entity_type="event", entity_id=str(event.id), details=payload.model_dump(exclude_unset=True, mode="json"))
    session.commit()
    session.refresh(event)
    return _challenge_payload(session, event)


@router.post("/{event_id}/sync-buddy-roster", response_model=ChallengeResponse)
def sync_buddy_roster(event_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> ChallengeResponse:
    event = require_event_manager(session, user, session.get(Event, event_id))
    if (event.event_kind or "competition") != "challenge":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found")
    group = _load_owned_buddy_group(session, user, event.source_buddy_group_id)
    added_count = _seed_roster_from_buddy_group(session, event, group, user)
    log_action(session, actor_user_id=user.id, action="challenge.roster.sync", entity_type="event", entity_id=str(event.id), details={"source_buddy_group_id": event.source_buddy_group_id, "member_count": added_count})
    session.commit()
    session.refresh(event)
    return _challenge_payload(session, event)
