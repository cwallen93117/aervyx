from pathlib import Path
from shutil import copy2

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_user, require_admin, require_staff
from app.models import AirspaceRegion, AirspaceSource, Event, EventPilot, EventTurnpointSlot, Task, TaskPoint, Turnpoint, User
from app.schemas import EventCreate, EventResponse, ScoringPresetEntry, ScoringPresetUpdate, default_task_point_direction
from app.services.audit import log_action
from app.services.handicap import handicap_config
from app.services.pilot_identity import participant_event_ids_for_user
from app.services.scoring import rescore_scored_event_tasks

router = APIRouter(prefix="/api/events", tags=["events"])
STAFF_ROLES = {"admin", "organizer"}

DEFAULT_SCORING_PRESETS = [
    {"id": "airspace-minor", "label": "Airspace minor -5%", "penalty_type": "percentage", "value": 5, "reason": "Airspace minor"},
    {"id": "airspace-major", "label": "Airspace major -20%", "penalty_type": "percentage", "value": 20, "reason": "Airspace major"},
    {"id": "start-violation", "label": "Start violation -10%", "penalty_type": "percentage", "value": 10, "reason": "Start violation"},
    {"id": "turnpoint-miss", "label": "Turnpoint miss -100%", "penalty_type": "percentage", "value": 100, "reason": "Turnpoint miss"},
    {"id": "late-track-log", "label": "Late track log -50 pts", "penalty_type": "fixed", "value": 50, "reason": "Late track log"},
    {"id": "safety-infraction", "label": "Safety infraction -100 pts", "penalty_type": "fixed", "value": 100, "reason": "Safety infraction"},
]


def _event_scoring_presets(event: Event) -> list[ScoringPresetEntry]:
    penalties_json = event.penalties_json or {}
    raw = penalties_json.get("scoring_operations_presets")
    if not isinstance(raw, list) or not raw:
        raw = DEFAULT_SCORING_PRESETS
    return [ScoringPresetEntry.model_validate(item) for item in raw]


def _event_create_payload(event: Event) -> dict:
    return {field: getattr(event, field) for field in EventCreate.model_fields}


def _normalized_duplicate_task_type(task_type: str | None) -> str:
    if task_type in {None, "race", "race_to_goal", "speedrun_interval"}:
        return "race_to_goal_with_gates"
    if task_type == "speedrun":
        return "elapsed_time"
    return task_type


def _duplicate_name(session: Session, base_name: str) -> str:
    candidate = f"{base_name} Duplicate"
    suffix = 2
    while session.scalar(select(Event.id).where(Event.name == candidate).limit(1)) is not None:
        candidate = f"{base_name} Duplicate {suffix}"
        suffix += 1
    return candidate


def _copy_stored_file(stored_path: str, new_event_id: int, source_id: int) -> str:
    original_path = Path(stored_path)
    if not original_path.exists():
        return stored_path
    duplicate_path = original_path.parent / f"event-{new_event_id}-copy-{source_id}-{original_path.name}"
    if not duplicate_path.exists():
        copy2(original_path, duplicate_path)
    return str(duplicate_path)


def _event_visible_to_user(session: Session, event: Event, user: User, participant_event_ids: set[int] | None = None) -> bool:
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


def _event_payload(session: Session, event: Event) -> EventResponse:
    pilot_count = session.scalar(select(func.count()).select_from(EventPilot).where(EventPilot.event_id == event.id)) or 0
    task_count = session.scalar(select(func.count()).select_from(Task).where(Task.event_id == event.id)) or 0
    turnpoint_count = session.scalar(
        select(func.count())
        .select_from(Turnpoint)
        .join(EventTurnpointSlot, EventTurnpointSlot.source_id == Turnpoint.source_id)
        .where(EventTurnpointSlot.event_id == event.id)
    ) or 0
    airspace_count = session.scalar(select(func.count()).select_from(AirspaceRegion).where(AirspaceRegion.event_id == event.id, AirspaceRegion.is_restricted_field.is_(False))) or 0
    restricted_field_count = session.scalar(select(func.count()).select_from(AirspaceRegion).where(AirspaceRegion.event_id == event.id, AirspaceRegion.is_restricted_field.is_(True))) or 0
    return EventResponse(
        id=event.id,
        name=event.name,
        location=event.location,
        starts_on=event.starts_on,
        ends_on=event.ends_on,
        timezone=event.timezone,
        scoring_formula=event.scoring_formula or "GAP2021",
        nominal_distance_km=event.nominal_distance_km if event.nominal_distance_km is not None else 60,
        nominal_time_hours=event.nominal_time_hours if event.nominal_time_hours is not None else 1.5,
        nominal_launch=event.nominal_launch if event.nominal_launch is not None else 0.95,
        minimum_distance_km=event.minimum_distance_km if event.minimum_distance_km is not None else 5,
        nominal_goal_percent=event.nominal_goal_percent if event.nominal_goal_percent is not None else 0.3,
        score_back_time_minutes=event.score_back_time_minutes if event.score_back_time_minutes is not None else 15,
        goal_ss_penalty=event.goal_ss_penalty if event.goal_ss_penalty is not None else 0,
        day_quality_override=event.day_quality_override if event.day_quality_override is not None else 0,
        time_points_if_not_in_goal=event.time_points_if_not_in_goal if event.time_points_if_not_in_goal is not None else 1,
        jump_the_gun_factor=event.jump_the_gun_factor if event.jump_the_gun_factor is not None else 0,
        jump_the_gun_max_seconds=event.jump_the_gun_max_seconds if event.jump_the_gun_max_seconds is not None else 0,
        default_start_gate_count=event.default_start_gate_count or 5,
        default_start_gate_interval_seconds=event.default_start_gate_interval_seconds if event.default_start_gate_interval_seconds is not None else 900,
        stopped_glide_bonus=event.stopped_glide_bonus if event.stopped_glide_bonus is not None else 0,
        use_1000_points_for_max_day_quality=False if event.use_1000_points_for_max_day_quality is None else event.use_1000_points_for_max_day_quality,
        normalize_1000_before_day_quality=False if event.normalize_1000_before_day_quality is None else event.normalize_1000_before_day_quality,
        use_distance_points=True if event.use_distance_points is None else event.use_distance_points,
        use_time_points=True if event.use_time_points is None else event.use_time_points,
        use_leading_points=True if event.use_leading_points is None else event.use_leading_points,
        use_arrival_position_points=False if event.use_arrival_position_points is None else event.use_arrival_position_points,
        use_arrival_time_points=False if event.use_arrival_time_points is None else event.use_arrival_time_points,
        use_departure_points=False if event.use_departure_points is None else event.use_departure_points,
        use_difficulty_for_distance_points=True if event.use_difficulty_for_distance_points is None else event.use_difficulty_for_distance_points,
        use_distance_squared_for_lc=False if event.use_distance_squared_for_lc is None else event.use_distance_squared_for_lc,
        use_semi_circle_control_zone_for_goal_line=True if event.use_semi_circle_control_zone_for_goal_line is None else event.use_semi_circle_control_zone_for_goal_line,
        use_proportional_leading_weight_if_nobody_in_goal=True if event.use_proportional_leading_weight_if_nobody_in_goal is None else event.use_proportional_leading_weight_if_nobody_in_goal,
        redistribute_removed_time_points_as_distance_points=False if event.redistribute_removed_time_points_as_distance_points is None else event.redistribute_removed_time_points_as_distance_points,
        use_best_score_for_ftv_validity=True if event.use_best_score_for_ftv_validity is None else event.use_best_score_for_ftv_validity,
        use_constant_leading_weight=False if event.use_constant_leading_weight is None else event.use_constant_leading_weight,
        use_pwca2019_for_lc=False if event.use_pwca2019_for_lc is None else event.use_pwca2019_for_lc,
        use_flat_decline_of_timepoints=False if event.use_flat_decline_of_timepoints is None else event.use_flat_decline_of_timepoints,
        scoring_altitude=event.scoring_altitude or "GPS",
        final_glide_decelerator=event.final_glide_decelerator or "none",
        no_final_glide_decelerator_reason=event.no_final_glide_decelerator_reason or "",
        min_time_span_for_valid_task_minutes=event.min_time_span_for_valid_task_minutes if event.min_time_span_for_valid_task_minutes is not None else 60,
        leading_weight_factor=event.leading_weight_factor if event.leading_weight_factor is not None else 1,
        turnpoint_radius_tolerance=event.turnpoint_radius_tolerance if event.turnpoint_radius_tolerance is not None else 0.0005,
        turnpoint_radius_minimum_absolute_tolerance_m=event.turnpoint_radius_minimum_absolute_tolerance_m if event.turnpoint_radius_minimum_absolute_tolerance_m is not None else 5,
        number_of_decimals_task_results=event.number_of_decimals_task_results if event.number_of_decimals_task_results is not None else 2,
        number_of_decimals_competition_results=event.number_of_decimals_competition_results if event.number_of_decimals_competition_results is not None else 1,
        visible_airspace_classes_json=list(event.visible_airspace_classes_json or ["B", "C", "D", "P", "Q", "R", "TFR", "OTHER"]),
        show_restricted_fields=True if event.show_restricted_fields is None else event.show_restricted_fields,
        penalties_json=event.penalties_json or {},
        is_public_tracking=event.is_public_tracking,
        visibility=event.visibility or "private",
        created_at=event.created_at,
        updated_at=event.updated_at,
        pilot_count=pilot_count,
        task_count=task_count,
        turnpoint_count=turnpoint_count,
        airspace_count=airspace_count,
        restricted_field_count=restricted_field_count,
    )


@router.get("", response_model=list[EventResponse])
def list_events(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[EventResponse]:
    # Staff (admin/organizer) can see all events regardless of visibility
    if user.role in STAFF_ROLES:
        events = session.scalars(select(Event).order_by(Event.updated_at.desc(), Event.name.asc())).all()
        return [_event_payload(session, event) for event in events]

    participant_event_ids = participant_event_ids_for_user(session, user)
    events = session.scalars(
        select(Event)
        .where(Event.visibility.in_(["public", "users", "participants"]))
        .order_by(Event.updated_at.desc(), Event.name.asc())
    ).all()
    visible_events = [event for event in events if _event_visible_to_user(session, event, user, participant_event_ids)]

    # Deduplicate and sort by updated_at desc, name asc
    seen: set[int] = set()
    unique_events: list[Event] = []
    for event in sorted(visible_events, key=lambda e: (e.updated_at or e.created_at,), reverse=True):
        if event.id not in seen:
            seen.add(event.id)
            unique_events.append(event)

    return [_event_payload(session, event) for event in unique_events]


@router.post("", response_model=EventResponse)
def create_event(payload: EventCreate, user: User = Depends(require_staff), session: Session = Depends(get_session)) -> EventResponse:
    event = Event(**payload.model_dump())
    session.add(event)
    session.flush()
    log_action(
        session,
        actor_user_id=user.id,
        action="event.create",
        entity_type="event",
        entity_id=str(event.id),
        details=payload.model_dump(mode="json"),
    )
    session.commit()
    session.refresh(event)
    return _event_payload(session, event)


@router.post("/{event_id}/duplicate", response_model=EventResponse)
def duplicate_event(event_id: int, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> EventResponse:
    source_event = session.get(Event, event_id)
    if source_event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    duplicated_event = Event(**_event_create_payload(source_event))
    duplicated_event.name = _duplicate_name(session, source_event.name)
    session.add(duplicated_event)
    session.flush()

    for slot in session.scalars(select(EventTurnpointSlot).where(EventTurnpointSlot.event_id == source_event.id).order_by(EventTurnpointSlot.slot_number)).all():
        session.add(
            EventTurnpointSlot(
                event_id=duplicated_event.id,
                slot_number=slot.slot_number,
                source_id=slot.source_id,
            )
        )

    airspace_source_id_map: dict[int, int] = {}
    for source in session.scalars(select(AirspaceSource).where(AirspaceSource.event_id == source_event.id).order_by(AirspaceSource.id)).all():
        duplicated_source = AirspaceSource(
            event_id=duplicated_event.id,
            kind=source.kind,
            filename=source.filename,
            content_type=source.content_type,
            file_format=source.file_format,
            sha256=source.sha256,
            stored_path=_copy_stored_file(source.stored_path, duplicated_event.id, source.id),
            enabled=source.enabled,
        )
        session.add(duplicated_source)
        session.flush()
        airspace_source_id_map[source.id] = duplicated_source.id

    for region in session.scalars(select(AirspaceRegion).where(AirspaceRegion.event_id == source_event.id).order_by(AirspaceRegion.id)).all():
        session.add(
            AirspaceRegion(
                event_id=duplicated_event.id,
                source_id=airspace_source_id_map[region.source_id],
                name=region.name,
                class_code=region.class_code,
                type_code=region.type_code,
                display_category=region.display_category,
                lower_limit_label=region.lower_limit_label,
                upper_limit_label=region.upper_limit_label,
                lower_limit_m=region.lower_limit_m,
                upper_limit_m=region.upper_limit_m,
                geometry_json=region.geometry_json,
                label_latitude=region.label_latitude,
                label_longitude=region.label_longitude,
                is_restricted_field=region.is_restricted_field,
            )
        )

    for event_pilot in session.scalars(select(EventPilot).where(EventPilot.event_id == source_event.id).order_by(EventPilot.id)).all():
        session.add(EventPilot(event_id=duplicated_event.id, pilot_id=event_pilot.pilot_id, pilot_class=event_pilot.pilot_class))

    task_id_map: dict[int, int] = {}
    for task in session.scalars(select(Task).where(Task.event_id == source_event.id).order_by(Task.id)).all():
        duplicated_task = Task(
            event_id=duplicated_event.id,
            name=task.name,
            status=task.status,
            task_type=_normalized_duplicate_task_type(task.task_type),
            task_start_time=task.task_start_time,
            task_finish_time=task.task_finish_time,
            start_open_time=task.start_open_time,
            start_close_time=task.start_close_time,
            start_gate_count=task.start_gate_count,
            start_gate_interval_seconds=task.start_gate_interval_seconds,
            version=task.version,
            published_at=task.published_at,
        )
        session.add(duplicated_task)
        session.flush()
        task_id_map[task.id] = duplicated_task.id

    for task_point in session.scalars(select(TaskPoint).join(Task, Task.id == TaskPoint.task_id).where(Task.event_id == source_event.id).order_by(TaskPoint.task_id, TaskPoint.position)).all():
        session.add(
            TaskPoint(
                task_id=task_id_map[task_point.task_id],
                position=task_point.position,
                point_type=task_point.point_type,
                direction=task_point.direction if task_point.direction in {"enter", "exit"} else default_task_point_direction(task_point.point_type),
                radius_m=task_point.radius_m,
                turnpoint_id=task_point.turnpoint_id,
                name=task_point.name,
                latitude=task_point.latitude,
                longitude=task_point.longitude,
            )
        )

    log_action(
        session,
        actor_user_id=admin.id,
        action="event.duplicate",
        entity_type="event",
        entity_id=str(duplicated_event.id),
        details={"source_event_id": source_event.id, "source_event_name": source_event.name, "name": duplicated_event.name},
    )
    session.commit()
    session.refresh(duplicated_event)
    return _event_payload(session, duplicated_event)


@router.get("/{event_id}", response_model=EventResponse)
def get_event(event_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> EventResponse:
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if not _event_visible_to_user(session, event, user):
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_payload(session, event)


@router.put("/{event_id}", response_model=EventResponse)
def update_event(event_id: int, payload: EventCreate, user: User = Depends(require_staff), session: Session = Depends(get_session)) -> EventResponse:
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    previous_handicap = handicap_config(event.penalties_json)
    data = payload.model_dump()
    for field, value in data.items():
        setattr(event, field, value)
    rescored_task_count = rescore_scored_event_tasks(session, event_id) if handicap_config(event.penalties_json) != previous_handicap else 0
    log_action(
        session,
        actor_user_id=user.id,
        action="event.update",
        entity_type="event",
        entity_id=str(event.id),
        details={**payload.model_dump(mode="json"), "rescored_task_count": rescored_task_count},
    )
    session.commit()
    session.refresh(event)
    return _event_payload(session, event)


@router.get("/{event_id}/scoring-presets", response_model=list[ScoringPresetEntry])
def get_scoring_presets(event_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[ScoringPresetEntry]:
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_scoring_presets(event)


@router.patch("/{event_id}/scoring-presets", response_model=list[ScoringPresetEntry])
def update_scoring_presets(
    event_id: int,
    payload: ScoringPresetUpdate,
    admin: User = Depends(require_staff),
    session: Session = Depends(get_session),
) -> list[ScoringPresetEntry]:
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    penalties_json = dict(event.penalties_json or {})
    penalties_json["scoring_operations_presets"] = [item.model_dump() for item in payload.presets]
    event.penalties_json = penalties_json
    log_action(
        session,
        actor_user_id=admin.id,
        action="event.scoring_presets.update",
        entity_type="event",
        entity_id=str(event_id),
        details={"preset_count": len(payload.presets)},
    )
    session.commit()
    session.refresh(event)
    return _event_scoring_presets(event)


@router.delete("/{event_id}", status_code=204)
def delete_event(event_id: int, admin: User = Depends(require_admin), session: Session = Depends(get_session)) -> None:
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    event_name = event.name
    session.delete(event)
    log_action(session, actor_user_id=admin.id, action="event.delete", entity_type="event", entity_id=str(event_id), details={"name": event_name})
    session.commit()
