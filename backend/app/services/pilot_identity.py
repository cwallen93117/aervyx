from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    BuddyGroupMember,
    DriverAssignment,
    EventPilot,
    IGCUpload,
    LivePosition,
    MeshDevice,
    Pilot,
    PilotFlight,
    PilotLanding,
    ScorePenalty,
    ScoreResult,
    SosAlert,
    TaskScoringInput,
    TrackingSession,
    User,
    UserEmail,
)
from app.services.seeding import DEFAULT_PILOT_PASSWORD

logger = logging.getLogger("aervyx.pilot_identity")


@dataclass
class PilotIdentityResult:
    pilot: Pilot
    user: User | None
    temp_password: str | None = None


@dataclass
class PilotMergeResult:
    source_pilot_id: int
    target_pilot_id: int
    moved_counts: dict[str, int] = field(default_factory=dict)
    deleted_conflicts: dict[str, int] = field(default_factory=dict)


def normalize_email(value: str | None) -> str | None:
    candidate = (value or "").strip().lower()
    return candidate if "@" in candidate else None


def normalize_identity_value(value: str | None) -> str | None:
    candidate = (value or "").strip().lower()
    return candidate or None


def is_auto_generated_user(user: User) -> bool:
    return "@" not in (user.username or "")


def linked_user_for_pilot(session: Session, pilot: Pilot) -> User | None:
    linked_users = session.scalars(
        select(User).where(User.pilot_id == pilot.id, User.is_active.is_(True)).order_by(User.id.asc())
    ).all()
    if not linked_users:
        return None
    email = normalize_email(pilot.email)
    if email:
        email_user = next((user for user in linked_users if normalize_email(user.username) == email), None)
        if email_user is not None:
            return email_user
    return linked_users[0]


def find_pilot_user_by_email(session: Session, email: str | None) -> User | None:
    normalized = normalize_email(email)
    if normalized is None:
        return None
    return session.scalar(
        select(User).where(
            func.lower(User.username) == normalized,
            User.role == "pilot",
            User.is_active.is_(True),
        )
    )


def find_user_by_login_email(session: Session, email: str | None, *, role: str | None = None) -> User | None:
    normalized = normalize_email(email)
    if normalized is None:
        return None
    filters = [User.is_active.is_(True)]
    if role is not None:
        filters.append(User.role == role)
    user = session.scalar(select(User).where(func.lower(User.username) == normalized, *filters))
    if user is not None:
        return user
    email_row = session.scalar(select(UserEmail).where(func.lower(UserEmail.email) == normalized))
    if email_row is None:
        return None
    owner = session.get(User, email_row.user_id)
    if owner is None or not owner.is_active:
        return None
    if role is not None and owner.role != role:
        return None
    return owner


def add_user_email_alias(session: Session, user: User, email: str | None) -> UserEmail | None:
    normalized = normalize_email(email)
    if normalized is None or normalize_email(user.username) == normalized:
        return None
    existing = session.scalar(select(UserEmail).where(func.lower(UserEmail.email) == normalized))
    if existing is not None:
        if existing.user_id == user.id:
            return existing
        raise ValueError("Email already belongs to another account")
    row = UserEmail(user_id=user.id, email=normalized)
    session.add(row)
    return row


def merge_user_accounts(session: Session, *, source_user_id: int, target_user_id: int) -> int:
    if source_user_id == target_user_id:
        return 0
    source = session.get(User, source_user_id)
    target = session.get(User, target_user_id)
    if source is None or target is None:
        raise ValueError("Both source and target users must exist before merging")

    changed = 0
    source_mesh_device_id = source.mesh_device_id
    try:
        if add_user_email_alias(session, target, source.username) is not None:
            changed += 1
    except ValueError:
        pass
    for alias in session.scalars(select(UserEmail).where(UserEmail.user_id == source.id)).all():
        try:
            add_user_email_alias(session, target, alias.email)
        except ValueError:
            pass
        session.delete(alias)
        changed += 1

    for model in (LivePosition, TrackingSession):
        rows = session.scalars(select(model).where(model.user_id == source.id)).all()
        for row in rows:
            row.user_id = target.id
            session.add(row)
        changed += len(rows)

    devices = session.scalars(select(MeshDevice).where(MeshDevice.owner_user_id == source.id)).all()
    for device in devices:
        device.owner_user_id = target.id
        session.add(device)
    if devices:
        changed += len(devices)
        if source_mesh_device_id:
            source.mesh_device_id = None
            session.add(source)
            session.flush()
            mesh_holder = session.scalar(
                select(User).where(
                    User.mesh_device_id == source_mesh_device_id,
                    User.id != target.id,
                )
            )
            if not target.mesh_device_id and mesh_holder is None:
                target.mesh_device_id = source_mesh_device_id

    if source.pilot_id and not target.pilot_id:
        target.pilot_id = source.pilot_id
    if not target.full_name and source.full_name:
        target.full_name = source.full_name
    source.is_active = False
    source.pilot_id = None
    source.mesh_device_id = None
    session.add_all([source, target])
    return changed + 1


def _best_pilot_candidate(session: Session, candidates: list[Pilot], preferred: Pilot | None = None) -> Pilot | None:
    unique: dict[int, Pilot] = {pilot.id: pilot for pilot in candidates if pilot is not None}
    if not unique:
        return preferred
    if preferred is not None and preferred.id in unique:
        return preferred
    return max(unique.values(), key=lambda pilot: (_event_membership_count(session, pilot.id), -pilot.id))


def find_canonical_pilot(
    session: Session,
    *,
    email: str | None = None,
    civl_id: str | None = None,
    competition_number: str | None = None,
    preferred: Pilot | None = None,
) -> Pilot | None:
    normalized_email = normalize_email(email)
    if normalized_email is not None:
        email_user = find_pilot_user_by_email(session, normalized_email)
        if email_user is not None and email_user.pilot_id:
            pilot = session.get(Pilot, email_user.pilot_id)
            if pilot is not None:
                return pilot

        email_row = session.scalar(select(UserEmail).where(func.lower(UserEmail.email) == normalized_email))
        if email_row is not None:
            owner = session.get(User, email_row.user_id)
            if owner is not None and owner.pilot_id:
                pilot = session.get(Pilot, owner.pilot_id)
                if pilot is not None:
                    return pilot

        email_candidates = session.scalars(
            select(Pilot).where(func.lower(Pilot.email) == normalized_email).order_by(Pilot.id.asc())
        ).all()
        non_preferred_email_candidates = [pilot for pilot in email_candidates if preferred is None or pilot.id != preferred.id]
        candidate = _best_pilot_candidate(session, non_preferred_email_candidates, None)
        if candidate is not None:
            return candidate

    normalized_civl = normalize_identity_value(civl_id)
    if normalized_civl is not None:
        civl_candidates = session.scalars(
            select(Pilot).where(func.lower(Pilot.civl_id) == normalized_civl).order_by(Pilot.id.asc())
        ).all()
        candidate = _best_pilot_candidate(session, civl_candidates, preferred)
        if candidate is not None:
            return candidate

    normalized_comp = normalize_identity_value(competition_number)
    if normalized_comp is not None:
        comp_candidates = session.scalars(
            select(Pilot).where(func.lower(Pilot.competition_number) == normalized_comp).order_by(Pilot.id.asc())
        ).all()
        candidate = _best_pilot_candidate(session, comp_candidates, preferred)
        if candidate is not None:
            return candidate

    return preferred


def find_canonical_pilot_by_email(session: Session, email: str | None, preferred: Pilot | None = None) -> Pilot | None:
    normalized = normalize_email(email)
    if normalized is None:
        return preferred
    return find_canonical_pilot(session, email=normalized, preferred=preferred)


def merge_pilots(session: Session, *, source_pilot_id: int, target_pilot_id: int) -> PilotMergeResult:
    if source_pilot_id == target_pilot_id:
        return PilotMergeResult(source_pilot_id=source_pilot_id, target_pilot_id=target_pilot_id)

    source = session.get(Pilot, source_pilot_id)
    target = session.get(Pilot, target_pilot_id)
    if source is None or target is None:
        raise ValueError("Both source and target pilots must exist before merging")

    result = PilotMergeResult(source_pilot_id=source_pilot_id, target_pilot_id=target_pilot_id)
    _copy_profile(source=source, target=target)
    session.add(target)

    for user in session.scalars(select(User).where(User.pilot_id == source_pilot_id)).all():
        user.pilot_id = target_pilot_id
        session.add(user)
        result.moved_counts["users"] = result.moved_counts.get("users", 0) + 1

    _move_unique_memberships(
        session,
        model=EventPilot,
        source_pilot_id=source_pilot_id,
        target_pilot_id=target_pilot_id,
        unique_fields=("event_id",),
        result=result,
        key="event_pilots",
    )
    _move_unique_memberships(
        session,
        model=TaskScoringInput,
        source_pilot_id=source_pilot_id,
        target_pilot_id=target_pilot_id,
        unique_fields=("task_id",),
        result=result,
        key="task_scoring_inputs",
    )
    _move_unique_memberships(
        session,
        model=ScoreResult,
        source_pilot_id=source_pilot_id,
        target_pilot_id=target_pilot_id,
        unique_fields=("task_id",),
        result=result,
        key="score_results",
    )
    _move_unique_memberships(
        session,
        model=BuddyGroupMember,
        source_pilot_id=source_pilot_id,
        target_pilot_id=target_pilot_id,
        unique_fields=("group_id",),
        result=result,
        key="buddy_group_members",
    )
    _move_unique_memberships(
        session,
        model=DriverAssignment,
        source_pilot_id=source_pilot_id,
        target_pilot_id=target_pilot_id,
        unique_fields=("task_id", "driver_user_id"),
        result=result,
        key="driver_assignments",
    )

    for model, key in (
        (IGCUpload, "igc_uploads"),
        (PilotFlight, "pilot_flights"),
        (ScorePenalty, "score_penalties"),
        (LivePosition, "live_positions"),
        (TrackingSession, "tracking_sessions"),
        (SosAlert, "sos_alerts"),
        (PilotLanding, "pilot_landings"),
    ):
        rows = session.scalars(select(model).where(model.pilot_id == source_pilot_id)).all()
        for row in rows:
            row.pilot_id = target_pilot_id
            session.add(row)
        if rows:
            result.moved_counts[key] = result.moved_counts.get(key, 0) + len(rows)

    source.email = None
    session.delete(source)
    logger.info(
        "Merged duplicate pilot %s into canonical pilot %s; moved=%s conflicts=%s",
        source_pilot_id,
        target_pilot_id,
        result.moved_counts,
        result.deleted_conflicts,
    )
    return result


def participant_event_ids_for_user(session: Session, user: User) -> set[int]:
    event_ids: set[int] = set()
    if user.pilot_id is not None:
        event_ids.update(session.scalars(select(EventPilot.event_id).where(EventPilot.pilot_id == user.pilot_id)).all())
    emails = {email for email in [normalize_email(user.username)] if email}
    emails.update(session.scalars(select(UserEmail.email).where(UserEmail.user_id == user.id)).all())
    for email in emails:
        event_ids.update(
            session.scalars(
                select(EventPilot.event_id)
                .join(Pilot, Pilot.id == EventPilot.pilot_id)
                .where(func.lower(Pilot.email) == email.lower())
            ).all()
        )
    return event_ids


def apply_pilot_profile(
    pilot: Pilot,
    *,
    first_name: str,
    last_name: str,
    email: str | None,
    nation: str | None,
    competition_number: str | None,
    civl_id: str | None,
) -> None:
    pilot.first_name = first_name
    pilot.last_name = last_name
    pilot.email = normalize_email(email)
    pilot.nation = nation
    pilot.competition_number = competition_number
    pilot.civl_id = civl_id


def ensure_event_membership(session: Session, event_id: int, pilot_id: int) -> EventPilot:
    existing = session.scalar(select(EventPilot).where(EventPilot.event_id == event_id, EventPilot.pilot_id == pilot_id))
    if existing is not None:
        return existing
    membership = EventPilot(event_id=event_id, pilot_id=pilot_id)
    session.add(membership)
    return membership


def ensure_pilot_login_identity(
    session: Session,
    pilot: Pilot,
    username: str | None = None,
    password: str | None = None,
    *,
    create_user: bool = True,
) -> PilotIdentityResult:
    email = normalize_email(pilot.email)
    if email is None:
        return _ensure_portal_identity(session, pilot, username, password, create_user=create_user)

    pilot.email = email
    email_user = find_pilot_user_by_email(session, email)
    canonical = find_canonical_pilot(
        session,
        email=email,
        civl_id=pilot.civl_id,
        competition_number=pilot.competition_number,
        preferred=pilot,
    ) or pilot
    if canonical.id != pilot.id:
        merge_pilots(session, source_pilot_id=pilot.id, target_pilot_id=canonical.id)
        session.flush()

    if email_user is not None:
        email_user.pilot_id = canonical.id
        if not email_user.full_name:
            email_user.full_name = _pilot_full_name(canonical)
        session.add_all([canonical, email_user])
        _retire_auto_users(session, source_pilot_id=canonical.id, except_user_id=email_user.id)
        return PilotIdentityResult(pilot=canonical, user=email_user)

    linked_user = linked_user_for_pilot(session, canonical)
    if linked_user is not None and is_auto_generated_user(linked_user):
        linked_user.username = email
        linked_user.full_name = _pilot_full_name(canonical)
        linked_user.role = "pilot"
        linked_user.profile_type = "pilot"
        linked_user.is_active = True
        if password:
            linked_user.password_hash = hash_password(password)
        elif not linked_user.password_hash:
            linked_user.password_hash = hash_password(DEFAULT_PILOT_PASSWORD)
        session.add_all([canonical, linked_user])
        return PilotIdentityResult(pilot=canonical, user=linked_user)

    if linked_user is not None:
        session.add(canonical)
        return PilotIdentityResult(pilot=canonical, user=linked_user)

    if not create_user:
        session.add(canonical)
        return PilotIdentityResult(pilot=canonical, user=None)

    generated_password = password or DEFAULT_PILOT_PASSWORD
    user = User(
        username=email,
        full_name=_pilot_full_name(canonical),
        role="pilot",
        profile_type="pilot",
        pilot_id=canonical.id,
        password_hash=hash_password(generated_password),
    )
    session.add_all([canonical, user])
    return PilotIdentityResult(pilot=canonical, user=user, temp_password=generated_password)


def repair_user_email_identity(session: Session, user: User) -> PilotIdentityResult | None:
    email = normalize_email(user.username)
    if user.role != "pilot" or email is None:
        return None

    pilot = session.get(Pilot, user.pilot_id) if user.pilot_id else None
    if pilot is None:
        pilot = find_canonical_pilot_by_email(session, email)
        if pilot is None:
            return None
        user.pilot_id = pilot.id
        session.add(user)

    canonical = find_canonical_pilot(
        session,
        email=email,
        civl_id=pilot.civl_id,
        competition_number=pilot.competition_number,
        preferred=pilot,
    )
    if canonical is not None and canonical.id != pilot.id:
        merge_pilots(session, source_pilot_id=pilot.id, target_pilot_id=canonical.id)
        session.flush()
        pilot = canonical
        user.pilot_id = canonical.id
        session.add(user)

    if normalize_email(pilot.email) != email:
        pilot.email = email
    result = ensure_pilot_login_identity(session, pilot, create_user=False)
    backfill_user_subject_pilot_links(session, user)
    return result


def repair_user_email_alias_identity(session: Session, user: User, email: str | None) -> int:
    normalized = normalize_email(email)
    if user.role != "pilot" or normalized is None:
        return 0

    changed = 0
    pilot = session.get(Pilot, user.pilot_id) if user.pilot_id else None
    candidates = session.scalars(
        select(Pilot).where(func.lower(Pilot.email) == normalized).order_by(Pilot.id.asc())
    ).all()
    if pilot is None:
        candidate = _best_pilot_candidate(session, candidates)
        if candidate is not None:
            user.pilot_id = candidate.id
            session.add(user)
            changed += 1
            pilot = candidate

    if pilot is not None:
        for candidate in candidates:
            if candidate.id != pilot.id:
                merge_pilots(session, source_pilot_id=candidate.id, target_pilot_id=pilot.id)
                changed += 1
        pilot.email = normalize_email(user.username) or pilot.email
        session.add(pilot)
        backfill_user_subject_pilot_links(session, user)
    return changed


def backfill_user_subject_pilot_links(session: Session, user: User) -> int:
    profile_type = (user.profile_type or "pilot").strip().lower()
    if user.pilot_id is None or profile_type == "driver":
        return 0

    changed = 0
    for model in (LivePosition, TrackingSession):
        rows = session.scalars(
            select(model).where(
                model.user_id == user.id,
                model.pilot_id.is_(None),
            )
        ).all()
        for row in rows:
            row.pilot_id = user.pilot_id
            session.add(row)
        changed += len(rows)
    return changed


def repair_pilot_email_identities(session: Session) -> int:
    changed = 0
    users = session.scalars(select(User).where(User.role == "pilot", User.is_active.is_(True)).order_by(User.id.asc())).all()
    for user in users:
        before = user.pilot_id
        result = repair_user_email_identity(session, user)
        if result is not None and user.pilot_id != before:
            changed += 1

    pilots = session.scalars(select(Pilot).where(Pilot.email.is_not(None)).order_by(Pilot.id.asc())).all()
    for pilot in pilots:
        email = normalize_email(pilot.email)
        if email and find_pilot_user_by_email(session, email) is not None:
            result = ensure_pilot_login_identity(session, pilot, create_user=False)
            if result.pilot.id != pilot.id:
                changed += 1
    changed += repair_known_messina_identity(session)
    return changed


def repair_known_messina_identity(session: Session) -> int:
    pilots = session.scalars(
        select(Pilot).where(
            func.lower(Pilot.last_name) == "messina",
            func.lower(Pilot.first_name).in_(("jim", "james")),
        ).order_by(Pilot.id.asc())
    ).all()
    users = session.scalars(
        select(User).where(
            User.role == "pilot",
            User.is_active.is_(True),
            func.lower(User.full_name).in_(("jim messina", "james messina")),
        ).order_by(User.id.asc())
    ).all()
    if len(pilots) < 2 and len(users) < 2:
        return 0

    changed = 0
    target_pilot = _select_messina_target_pilot(session, pilots)
    if target_pilot is not None:
        for pilot in list(pilots):
            if pilot.id != target_pilot.id:
                merge_pilots(session, source_pilot_id=pilot.id, target_pilot_id=target_pilot.id)
                changed += 1
        target_pilot.first_name = "Jim"
        target_pilot.last_name = "Messina"
        session.add(target_pilot)
        session.flush()

    if target_pilot is not None:
        users = session.scalars(select(User).where(User.pilot_id == target_pilot.id, User.is_active.is_(True)).order_by(User.id.asc())).all()
    target_user = _select_messina_target_user(users)
    if target_user is not None:
        for user in list(users):
            if user.id != target_user.id:
                changed += merge_user_accounts(session, source_user_id=user.id, target_user_id=target_user.id)
        if target_pilot is not None:
            target_user.pilot_id = target_pilot.id
            target_pilot.email = normalize_email(target_user.username) or target_pilot.email
            session.add(target_pilot)
        target_user.full_name = "Jim Messina"
        session.add(target_user)
    return changed


def _select_messina_target_pilot(session: Session, pilots: list[Pilot]) -> Pilot | None:
    if not pilots:
        return None
    jim = [pilot for pilot in pilots if (pilot.first_name or "").strip().lower() == "jim"]
    pool = jim or pilots
    return max(pool, key=lambda pilot: (_event_membership_count(session, pilot.id), _has_pilot_history(session, pilot.id), -pilot.id))


def _select_messina_target_user(users: list[User]) -> User | None:
    if not users:
        return None
    return max(
        users,
        key=lambda user: (
            normalize_email(user.username) is not None,
            "jim" in (user.username or "").lower() or (user.full_name or "").strip().lower() == "jim messina",
            -user.id,
        ),
    )


def _ensure_portal_identity(
    session: Session,
    pilot: Pilot,
    username: str | None,
    password: str | None,
    *,
    create_user: bool,
) -> PilotIdentityResult:
    existing = linked_user_for_pilot(session, pilot)
    if existing is not None or not create_user:
        return PilotIdentityResult(pilot=pilot, user=existing)

    generated_password = password or DEFAULT_PILOT_PASSWORD
    base_username = username or _slug_username(pilot.first_name, pilot.last_name, pilot.competition_number)
    candidate = base_username
    suffix = 1
    while session.scalar(select(User).where(User.username == candidate)) is not None:
        suffix += 1
        candidate = f"{base_username}-{suffix}"
    user = User(
        username=candidate,
        full_name=_pilot_full_name(pilot),
        role="pilot",
        pilot_id=pilot.id,
        password_hash=hash_password(generated_password),
    )
    session.add(user)
    return PilotIdentityResult(pilot=pilot, user=user, temp_password=generated_password)


def _copy_profile(source: Pilot, target: Pilot) -> None:
    target.first_name = source.first_name or target.first_name
    target.last_name = source.last_name or target.last_name
    target.email = normalize_email(source.email) or target.email
    target.nation = source.nation or target.nation
    target.competition_number = source.competition_number or target.competition_number
    target.civl_id = source.civl_id or target.civl_id


def _move_unique_memberships(
    session: Session,
    *,
    model,
    source_pilot_id: int,
    target_pilot_id: int,
    unique_fields: tuple[str, ...],
    result: PilotMergeResult,
    key: str,
) -> None:
    rows = session.scalars(select(model).where(model.pilot_id == source_pilot_id)).all()
    for row in rows:
        filters = [model.pilot_id == target_pilot_id]
        for field_name in unique_fields:
            filters.append(getattr(model, field_name) == getattr(row, field_name))
        existing = session.scalar(select(model).where(*filters))
        if existing is not None:
            session.delete(row)
            result.deleted_conflicts[key] = result.deleted_conflicts.get(key, 0) + 1
            continue
        row.pilot_id = target_pilot_id
        session.add(row)
        result.moved_counts[key] = result.moved_counts.get(key, 0) + 1


def _retire_auto_users(session: Session, source_pilot_id: int, except_user_id: int | None = None) -> None:
    users = session.scalars(select(User).where(User.pilot_id == source_pilot_id, User.is_active.is_(True))).all()
    for user in users:
        if user.id == except_user_id:
            continue
        if is_auto_generated_user(user):
            user.is_active = False
            user.pilot_id = None
            session.add(user)


def _has_pilot_history(session: Session, pilot_id: int) -> bool:
    history_models = (
        IGCUpload,
        PilotFlight,
        TaskScoringInput,
        ScorePenalty,
        ScoreResult,
        LivePosition,
        TrackingSession,
        SosAlert,
        DriverAssignment,
        PilotLanding,
        BuddyGroupMember,
    )
    for model in history_models:
        if session.scalar(select(model.id).where(model.pilot_id == pilot_id).limit(1)) is not None:
            return True
    return False


def _event_membership_count(session: Session, pilot_id: int) -> int:
    return session.scalar(select(func.count()).select_from(EventPilot).where(EventPilot.pilot_id == pilot_id)) or 0


def _pilot_full_name(pilot: Pilot) -> str:
    return f"{pilot.first_name or ''} {pilot.last_name or ''}".strip() or normalize_email(pilot.email) or "Pilot"


def _slug_username(first_name: str, last_name: str, competition_number: str | None) -> str:
    import re

    base = re.sub(r"[^a-z0-9]+", "-", f"{first_name}-{last_name}-{competition_number or 'pilot'}".lower()).strip("-")
    return base or "pilot"
