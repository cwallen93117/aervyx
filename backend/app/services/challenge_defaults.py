from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from shutil import copy2

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AirspaceRegion, AirspaceSource, Event, Turnpoint, TurnpointSource, User
from app.schemas import EventCreate

CHALLENGE_SCORING_FIELDS = {
    "scoring_formula",
    "nominal_distance_km",
    "nominal_time_hours",
    "nominal_launch",
    "minimum_distance_km",
    "nominal_goal_percent",
    "score_back_time_minutes",
    "goal_ss_penalty",
    "day_quality_override",
    "time_points_if_not_in_goal",
    "jump_the_gun_factor",
    "jump_the_gun_max_seconds",
    "default_start_gate_count",
    "default_start_gate_interval_seconds",
    "stopped_glide_bonus",
    "use_1000_points_for_max_day_quality",
    "normalize_1000_before_day_quality",
    "use_distance_points",
    "use_time_points",
    "use_leading_points",
    "use_arrival_position_points",
    "use_arrival_time_points",
    "use_departure_points",
    "use_difficulty_for_distance_points",
    "use_distance_squared_for_lc",
    "use_semi_circle_control_zone_for_goal_line",
    "use_proportional_leading_weight_if_nobody_in_goal",
    "redistribute_removed_time_points_as_distance_points",
    "use_best_score_for_ftv_validity",
    "use_constant_leading_weight",
    "use_pwca2019_for_lc",
    "use_flat_decline_of_timepoints",
    "scoring_altitude",
    "final_glide_decelerator",
    "no_final_glide_decelerator_reason",
    "min_time_span_for_valid_task_minutes",
    "leading_weight_factor",
    "turnpoint_radius_tolerance",
    "turnpoint_radius_minimum_absolute_tolerance_m",
    "number_of_decimals_task_results",
    "number_of_decimals_competition_results",
    "visible_airspace_classes_json",
    "show_restricted_fields",
    "penalties_json",
}

CHALLENGE_TEMPLATE_KIND = "challenge_defaults"


def challenge_event_defaults(user: User) -> dict:
    defaults = EventCreate(
        name="Challenge",
        location="",
        starts_on=datetime.now(UTC).date(),
        ends_on=datetime.now(UTC).date(),
    ).model_dump()
    settings = dict(user.challenge_settings_json or {})
    return {
        field: settings.get(field, defaults[field])
        for field in CHALLENGE_SCORING_FIELDS
        if field in defaults
    }


def ensure_challenge_defaults_event(session: Session, user: User) -> Event:
    settings = dict(user.challenge_settings_json or {})
    event_id = settings.get("template_event_id")
    event = session.get(Event, event_id) if isinstance(event_id, int) else None
    if event is not None and event.owner_user_id == user.id and event.event_kind == CHALLENGE_TEMPLATE_KIND:
        return event

    event = Event(
        name="Challenge Defaults",
        location="",
        starts_on=datetime.now(UTC).date(),
        ends_on=datetime.now(UTC).date(),
        timezone="UTC",
        visibility="private",
        event_kind=CHALLENGE_TEMPLATE_KIND,
        owner_user_id=user.id,
        public_listed=False,
    )
    session.add(event)
    session.flush()
    settings["template_event_id"] = event.id
    user.challenge_settings_json = settings
    session.add(user)
    return event


def _copy_file(stored_path: str, event_id: int, prefix: str) -> str:
    original = Path(stored_path)
    if not original.exists():
        return stored_path
    target_dir = Path(get_settings().upload_root) / prefix / f"event-{event_id}"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / original.name
    if not target.exists():
        copy2(original, target)
    return str(target)


def _copy_turnpoint_source(session: Session, source: TurnpointSource, event: Event) -> None:
    duplicate = TurnpointSource(
        event_id=event.id,
        filename=source.filename,
        content_type=source.content_type,
        file_format=source.file_format,
        sha256=source.sha256,
        stored_path=_copy_file(source.stored_path, event.id, "turnpoints"),
        schema_json=source.schema_json,
        enabled=True,
    )
    session.add(duplicate)
    session.flush()
    for turnpoint in session.scalars(select(Turnpoint).where(Turnpoint.source_id == source.id).order_by(Turnpoint.source_row_index.asc(), Turnpoint.id.asc())).all():
        session.add(
            Turnpoint(
                event_id=event.id,
                source_id=duplicate.id,
                code=turnpoint.code,
                symbol=turnpoint.symbol,
                name=turnpoint.name,
                latitude=turnpoint.latitude,
                longitude=turnpoint.longitude,
                elevation_m=turnpoint.elevation_m,
                extra_json=turnpoint.extra_json,
                source_row_index=turnpoint.source_row_index,
            )
        )


def _copy_airspace_source(session: Session, source: AirspaceSource, event: Event) -> None:
    duplicate = AirspaceSource(
        event_id=event.id,
        kind=source.kind,
        filename=source.filename,
        content_type=source.content_type,
        file_format=source.file_format,
        sha256=source.sha256,
        stored_path=_copy_file(source.stored_path, event.id, "airspace"),
        enabled=True,
    )
    session.add(duplicate)
    session.flush()
    for region in session.scalars(select(AirspaceRegion).where(AirspaceRegion.source_id == source.id).order_by(AirspaceRegion.id.asc())).all():
        session.add(
            AirspaceRegion(
                event_id=event.id,
                source_id=duplicate.id,
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


def copy_challenge_default_assets(session: Session, user: User, event: Event) -> None:
    settings = dict(user.challenge_settings_json or {})
    source_id = settings.get("turnpoint_source_id")
    source = session.get(TurnpointSource, source_id) if isinstance(source_id, int) else None
    if source is not None:
        _copy_turnpoint_source(session, source, event)

    for key in ("airspace_source_id", "restricted_field_source_id"):
        airspace_source_id = settings.get(key)
        airspace_source = session.get(AirspaceSource, airspace_source_id) if isinstance(airspace_source_id, int) else None
        if airspace_source is not None:
            _copy_airspace_source(session, airspace_source, event)
