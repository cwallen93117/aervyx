from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import (
    Event,
    EventPilot,
    IGCUpload,
    Pilot,
    ScoreResult,
    Task,
    TaskPoint,
    TaskScoringInput,
    TrackPoint,
)
from app.services.airscore.gap import build_task_totals, calc_kmdiff, points_allocation, points_weight
from app.services.scoring import (
    _blank_evaluation,
    _build_airscore_pilot_result,
    _build_formula,
    _clock_delta,
    _clock_in_timezone,
    _compute_optimized_task_distance,
    _duration_clock,
    _effective_timezone_name,
    _event_task_class,
    _minimum_distance_evaluation,
    _normalized_task_type_for_scoring,
    _number_delta,
    _parse_clock_time,
    _prepare_waypoints_for_distance,
    _resolve_timezone_name,
    _score_evaluations,
    _waypoint_distance_stats,
    evaluate_task,
)


HC2025_TASK1_OFFICIAL_RESULTS = [
    {"comp": "3", "name": "Richard Niehaus", "ss": "14:33:38", "es": "16:41:41", "time": "02:08:03", "distance": 84.09, "distance_points": 365.1, "time_points": 634.9, "total": 1000.0, "status": "goal"},
    {"comp": "1", "name": "Charles Allen", "ss": "14:33:51", "es": "16:46:11", "time": "02:12:20", "distance": 84.09, "distance_points": 365.1, "time_points": 583.6, "total": 948.7, "status": "goal"},
    {"comp": "9", "name": "Jim Messina", "ss": "14:33:45", "es": "16:49:11", "time": "02:15:26", "distance": 84.09, "distance_points": 365.1, "time_points": 554.1, "total": 919.2, "status": "goal"},
    {"comp": "11", "name": "Jeff Chipman", "ss": "14:35:26", "es": "17:00:35", "time": "02:25:09", "distance": 84.09, "distance_points": 365.1, "time_points": 472.3, "total": 837.4, "status": "goal"},
    {"comp": "2", "name": "Mick Howard", "ss": "14:33:33", "es": "17:05:18", "time": "02:31:45", "distance": 84.09, "distance_points": 365.1, "time_points": 421.4, "total": 786.5, "status": "goal"},
    {"comp": "12", "name": "Cory Barnwell", "ss": "14:40:54", "es": "17:21:40", "time": "02:40:46", "distance": 84.09, "distance_points": 365.1, "time_points": 355.6, "total": 720.7, "status": "goal"},
    {"comp": "13", "name": "John Muldoon", "ss": "14:33:49", "es": "17:15:05", "time": "02:41:16", "distance": 84.09, "distance_points": 365.1, "time_points": 352.1, "total": 717.2, "status": "goal"},
    {"comp": "8", "name": "Larry Huffman", "ss": "14:33:27", "es": None, "time": None, "distance": 77.20, "distance_points": 350.1, "time_points": 0.0, "total": 350.1, "status": "partial"},
    {"comp": "6", "name": "Knut R. Ryerson", "ss": "14:34:04", "es": None, "time": None, "distance": 48.41, "distance_points": 245.9, "time_points": 0.0, "total": 245.9, "status": "partial"},
    {"comp": "10", "name": "John Simon", "ss": None, "es": None, "time": None, "distance": 0.0, "distance_points": 0.0, "time_points": 0.0, "total": 0.0, "status": "absent"},
]

HC2025_TASK1_OFFICIAL_PARAMS: dict[str, Any] = {
    "task_type": "elapsed_time",
    "ss_distance": 84.094,
    "task_distance": 84.094,
    "launch_to_ess_distance": 84.094,
    "no_of_pilots_present": 9,
    "no_of_pilots_flying": 9,
    "no_of_pilots_lo": 2,
    "no_of_pilots_reaching_nom_dist": 8,
    "no_of_pilots_reaching_es": 7,
    "no_of_pilots_reaching_goal": 7,
    "sum_flown_distance": 714.27,
    "sum_dist_over_min": 669.27,
    "sum_real_dist_over_min": 669.27,
    "sum_flown_distances": 714.27,
    "best_dist": 84.094,
    "best_time": 2.1342,
    "worst_time": 2.6878,
    "no_of_pilots_in_competition": 10,
    "goalratio": 0.7778,
    "arrival_weight": 0,
    "departure_weight": 0,
    "leading_weight": 0,
    "time_weight": 0.6349,
    "distance_weight": 0.3651,
    "smallest_leading_coefficient": 0,
    "available_points_distance": 365.0713,
    "available_points_time": 634.9287,
    "available_points_departure": 0,
    "available_points_leading": 0,
    "available_points_arrival": 0,
    "time_validity": 1,
    "launch_validity": 1,
    "distance_validity": 1,
    "stop_validity": 1,
    "day_quality": 1,
    "id": "GAP2021",
    "min_dist": 5,
    "nom_dist": 55,
    "nom_time": 1.5,
    "nom_launch": 0.4,
    "nom_goal": 0.2,
    "day_quality_override": 0,
    "bonus_gr": 5,
    "jump_the_gun_factor": 2,
    "jump_the_gun_max": 300,
    "normalize_1000_before_day_quality": 0,
    "time_points_if_not_in_goal": 0.8,
    "use_1000_points_for_max_day_quality": 0,
    "use_arrival_position_points": 0,
    "use_arrival_time_points": 0,
    "use_departure_points": 0,
    "use_difficulty_for_distance_points": 1,
    "use_distance_points": 1,
    "use_distance_squared_for_LC": 1,
    "use_leading_points": 0,
    "use_semi_circle_control_zone_for_goal_line": 1,
    "use_time_points": 1,
    "scoring_altitude": "GPS",
    "final_glide_decelerator": "none",
    "min_time_span_for_valid_task": 45,
    "score_back_time": 15,
    "use_proportional_leading_weight_if_nobody_in_goal": 0,
    "leading_weight_factor": 1,
    "turnpoint_radius_tolerance": 0.005,
    "turnpoint_radius_minimum_absolute_tolerance": 5.0,
    "number_of_decimals_task_results": 1,
    "number_of_decimals_competition_results": 0,
    "redistribute_removed_time_points_as_distance_points": 1,
    "use_best_score_for_ftv_validity": 1,
    "use_constant_leading_weight": 0,
    "use_pwca2019_for_lc": 0,
    "use_flat_decline_of_timepoints": 1,
}


def _normalize_name(value: str | None) -> str:
    return " ".join((value or "").lower().replace(".", "").split())


def _format_number(value: Any, digits: int = 4) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if not isinstance(value, float):
        return value
    rounded = round(float(value), digits)
    if rounded == int(rounded):
        return int(rounded)
    return rounded


def _bool_int(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def _matches(expected: Any, actual: Any) -> bool:
    if expected is None:
        return actual in (None, "")
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            return abs(float(actual) - float(expected)) <= 0.02
        except (TypeError, ValueError):
            return False
    return str(expected).strip().lower() == str(actual).strip().lower()


def _local_clock(value: datetime | str | None, timezone_name: str) -> str | None:
    return _clock_in_timezone(value, timezone_name)


def _stored_param_value(param: str, event: Event, task: Task, task_stats: dict[str, Any]) -> Any:
    penalties = event.penalties_json or {}
    task_penalties = task.penalties_json or {}
    aliases = {
        "use_distance_squared_for_LC": "use_distance_squared_for_lc",
        "jump_the_gun_max": "jump_the_gun_max_seconds",
        "score_back_time": "score_back_time_minutes",
        "turnpoint_radius_minimum_absolute_tolerance": "turnpoint_radius_minimum_absolute_tolerance_m",
    }
    if param == "task_type":
        return task.task_type
    if param in task_stats:
        return task_stats[param]
    if param == "id":
        return event.scoring_formula
    if param == "min_dist":
        return {"event": event.minimum_distance_km, "task": task.minimum_distance_km}
    if param == "nom_dist":
        return {"event": event.nominal_distance_km, "task": task.nominal_distance_km}
    if param == "nom_time":
        return {"event": event.nominal_time_hours, "task": task.nominal_time_hours}
    if param == "nom_launch":
        return {"event": event.nominal_launch, "task": task.nominal_launch}
    if param == "nom_goal":
        return event.nominal_goal_percent
    if param == "score_back_time":
        return event.score_back_time_minutes
    if param == "jump_the_gun_max":
        return event.jump_the_gun_max_seconds
    if param == "bonus_gr":
        return event.stopped_glide_bonus
    if param == "turnpoint_radius_minimum_absolute_tolerance":
        return event.turnpoint_radius_minimum_absolute_tolerance_m
    if param in aliases and hasattr(event, aliases[param]):
        return getattr(event, aliases[param])
    if hasattr(event, param):
        return getattr(event, param)
    return penalties.get(param, task_penalties.get(param))


def _effective_param_value(
    param: str,
    *,
    task: Task,
    event: Event,
    formula: dict[str, Any],
    task_stats: dict[str, Any],
    task_totals: dict[str, Any],
    available_points: dict[str, Any],
) -> Any:
    if param == "task_type":
        return _normalized_task_type_for_scoring(task.task_type)
    if param in task_stats:
        return task_stats[param]
    if param == "id":
        return f"GAP{formula.get('version')}"
    if param == "min_dist":
        return formula["mindist_km"]
    if param == "nom_dist":
        return formula["nomdist_km"]
    if param == "nom_time":
        return round(float(formula["nomtime_seconds"]) / 3600.0, 4)
    if param == "nom_launch":
        return formula["nomlaunch"]
    if param == "nom_goal":
        return formula["nomgoal_fraction"]
    if param == "jump_the_gun_max":
        return formula["jump_the_gun_max_seconds"]
    if param == "score_back_time":
        return formula["score_back_time_minutes"]
    if param == "turnpoint_radius_tolerance":
        return formula["errormargin"]
    if param == "turnpoint_radius_minimum_absolute_tolerance":
        return event.turnpoint_radius_minimum_absolute_tolerance_m
    if param == "number_of_decimals_task_results":
        return formula["number_of_decimals_task_results"]
    if param == "number_of_decimals_competition_results":
        return event.number_of_decimals_competition_results
    if param == "no_of_pilots_in_competition":
        return task_totals.get("pilots")
    if param == "no_of_pilots_present":
        return task_totals.get("pilots") - sum(1 for value in task_totals.get("_pilot_results", []) if value.get("result") == "abs")
    if param == "no_of_pilots_flying":
        return task_totals.get("launched")
    if param == "no_of_pilots_lo":
        return max(int(task_totals.get("launched", 0) or 0) - int(task_totals.get("goal", 0) or 0), 0)
    if param == "no_of_pilots_reaching_nom_dist":
        nomdist = float(formula["nomdist"])
        return sum(1 for value in task_totals.get("_pilot_results", []) if value.get("distance", 0) >= nomdist and value.get("result") not in {"abs", "dnf"})
    if param == "no_of_pilots_reaching_es":
        return task_totals.get("ess")
    if param == "no_of_pilots_reaching_goal":
        return task_totals.get("goal")
    if param in {"sum_flown_distance", "sum_flown_distances"}:
        return round(float(task_totals.get("distance", 0.0) or 0.0) / 1000.0, 3)
    if param in {"sum_dist_over_min", "sum_real_dist_over_min"}:
        mindist = float(formula["mindist"])
        over_min = sum(max(float(value.get("distance", 0.0) or 0.0) - mindist, 0.0) for value in task_totals.get("_pilot_results", []) if value.get("result") not in {"abs", "dnf"})
        return round(over_min / 1000.0, 3)
    if param == "best_dist":
        return round(float(task_totals.get("maxdist", 0.0) or 0.0) / 1000.0, 3)
    if param == "best_time":
        fastest = float(task_totals.get("fastest", 0.0) or 0.0)
        return round(fastest / 3600.0, 4) if fastest else 0
    if param == "worst_time":
        times = [float(value.get("time", 0.0) or 0.0) for value in task_totals.get("_pilot_results", []) if value.get("goal") and value.get("time")]
        return round(max(times) / 3600.0, 4) if times else 0
    if param == "goalratio":
        launched = float(task_totals.get("launched", 0.0) or 0.0)
        return round(float(task_totals.get("goal", 0.0) or 0.0) / launched, 4) if launched else 0
    if param == "distance_weight":
        return round(available_points["distance"] / 1000.0, 4)
    if param == "time_weight":
        return round(available_points["speed"] / 1000.0, 4)
    if param == "leading_weight":
        return round(available_points["leading"] / 1000.0, 4)
    if param == "arrival_weight":
        return round(available_points["arrival"] / 1000.0, 4)
    if param == "departure_weight":
        return 0
    if param == "available_points_distance":
        return available_points["distance"]
    if param == "available_points_time":
        return available_points["speed"]
    if param == "available_points_leading":
        return available_points["leading"]
    if param == "available_points_arrival":
        return available_points["arrival"]
    if param == "available_points_departure":
        return 0
    if param == "smallest_leading_coefficient":
        return task_totals.get("mincoeff")
    if param == "time_validity":
        return task_totals.get("time_validity")
    if param == "launch_validity":
        return task_totals.get("launch_validity")
    if param == "distance_validity":
        return task_totals.get("dist_validity")
    if param == "stop_validity":
        return task_totals.get("stop_validity")
    if param == "day_quality":
        return task_totals.get("quality")
    if param == "use_distance_squared_for_LC":
        return _bool_int(formula.get("use_distance_squared_for_lc"))
    if param.startswith("use_") or param in {"normalize_1000_before_day_quality", "redistribute_removed_time_points_as_distance_points"}:
        key = "use_distance_squared_for_lc" if param == "use_distance_squared_for_LC" else param
        return _bool_int(formula.get(key))
    if param == "time_points_if_not_in_goal":
        return formula["time_points_if_not_in_goal"]
    if param == "leading_weight_factor":
        return formula["leading_weight_factor"]
    if param == "jump_the_gun_factor":
        return formula["jump_the_gun_factor"]
    if param == "scoring_altitude":
        return event.scoring_altitude
    if param == "final_glide_decelerator":
        return event.final_glide_decelerator
    if param == "day_quality_override":
        return event.day_quality_override
    if param == "bonus_gr":
        return formula.get("glidebonus")
    if param == "min_time_span_for_valid_task":
        return (event.penalties_json or {}).get("min_time_span_for_valid_task")
    return formula.get(param)


def _task_formula_override_note(param: str, task: Task, event: Event) -> str | None:
    pairs = {
        "min_dist": ("minimum_distance_km", 5),
        "nom_dist": ("nominal_distance_km", 60),
        "nom_time": ("nominal_time_hours", 1.5),
        "nom_launch": ("nominal_launch", 0.95),
    }
    if param not in pairs:
        return None
    attr, _default = pairs[param]
    task_value = getattr(task, attr, None)
    event_value = getattr(event, attr, None)
    if task_value is not None and event_value is not None and float(task_value) != float(event_value):
        return f"Task {attr} overrides Event Details ({task_value} vs {event_value})."
    return None


def _build_parameter_comparison(
    task: Task,
    event: Event,
    formula: dict[str, Any],
    task_stats: dict[str, Any],
    task_totals: dict[str, Any],
    available_points: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = []
    for param, fs_value in HC2025_TASK1_OFFICIAL_PARAMS.items():
        stored = _stored_param_value(param, event, task, task_stats)
        effective = _effective_param_value(
            param,
            task=task,
            event=event,
            formula=formula,
            task_stats=task_stats,
            task_totals=task_totals,
            available_points=available_points,
        )
        rows.append(
            {
                "param": param,
                "fs_score": fs_value,
                "aervyx_stored": stored,
                "airscore_effective": _format_number(effective),
                "match": _matches(fs_value, effective),
                "note": _task_formula_override_note(param, task, event),
            }
        )
    return rows


def _build_airscore_gap_context(
    task: Task,
    event: Event,
    airscore_waypoints: list[dict],
    formula: dict[str, Any],
    evaluations: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    pilot_results = []
    for entry in evaluations:
        pilot_id = entry.get("pilot_id")
        if pilot_id is None:
            continue
        pilot_results.append(_build_airscore_pilot_result(entry["evaluation"], int(pilot_id)))

    ssdist_m = airscore_waypoints[0].get("_ssdist", 0) if airscore_waypoints else 0.0
    startssdist_m = airscore_waypoints[0].get("_startssdist", 0) if airscore_waypoints else 0.0
    endssdist_m = airscore_waypoints[0].get("_endssdist", 0) if airscore_waypoints else 0.0
    scoring_timezone_name = _resolve_timezone_name(getattr(event, "timezone", None))
    for entry in evaluations:
        tz_from_evaluation = entry.get("evaluation", {}).get("details", {}).get("scoring_timezone")
        if tz_from_evaluation:
            scoring_timezone_name = str(tz_from_evaluation)
            break

    sstart_epoch = 0.0
    sfinish_epoch = 0.0
    for entry in evaluations:
        started_at = entry.get("evaluation", {}).get("started_at")
        if started_at is None:
            continue
        zone = ZoneInfo(_resolve_timezone_name(scoring_timezone_name))
        local_date = started_at.astimezone(zone).date()
        open_time = _parse_clock_time(task.start_open_time)
        finish_time = _parse_clock_time(task.task_finish_time)
        if open_time:
            sstart_epoch = datetime.combine(local_date, open_time, tzinfo=zone).timestamp()
        else:
            sstart_epoch = started_at.timestamp()
        if finish_time:
            sfinish_epoch = datetime.combine(local_date, finish_time, tzinfo=zone).timestamp()
        else:
            sfinish_epoch = sstart_epoch + 86400
        break

    airscore_task = {
        "class": _event_task_class(event),
        "departure": "leadout" if formula.get("use_leading_points") else "departure" if formula.get("use_departure_points") else "off",
        "arrival": "timed" if formula.get("use_arrival_time_points") else "position" if formula.get("use_arrival_position_points") else "off",
        "stopped": 0,
        "sstopped": 0,
        "endssdistance": endssdist_m,
        "startssdistance": startssdist_m,
        "ssdistance": ssdist_m,
        "sstart": sstart_epoch,
        "sfinish": sfinish_epoch,
        "goalalt": 0,
        "launchvalid": 1,
    }
    task_totals = build_task_totals(formula, airscore_task, pilot_results)
    task_totals["_pilot_results"] = pilot_results
    sorted_pilots = sorted(
        pilot_results,
        key=lambda p: (
            99999999 if (p["endSS"] - p["startSS"]) <= 0 else (p["endSS"] - p["startSS"]),
            -p["distance"],
        ),
    )
    first_arrival = task_totals.get("firstarrival", 0)
    place = 0
    last_es = -1
    last_place = -1
    for pilot in sorted_pilots:
        place += 1
        es_time = pilot["endSS"]
        if es_time == last_es:
            pilot["place"] = last_place
        else:
            pilot["place"] = place
            last_es = es_time
            last_place = place
        pilot["timeafter"] = es_time - first_arrival if (es_time > 0 and first_arrival > 0) else 0
    scored_pilots = points_allocation(airscore_task, task_totals, formula, sorted_pilots)
    return airscore_task, task_totals, pilot_results, scored_pilots


def _status_evaluation(task: Task, event: Event, status_override: str | None) -> dict[str, Any] | None:
    if status_override == "minimum_distance":
        return _minimum_distance_evaluation(task, event)
    if status_override in {"did_not_fly", "absent"}:
        return _blank_evaluation(status_override)
    return None


def _build_evaluations(
    session: Session,
    task: Task,
    event: Event,
    task_points: list[TaskPoint],
    airscore_waypoints: list[dict],
    optimized_distance_km: float,
) -> tuple[list[dict[str, Any]], dict[int, TaskScoringInput], dict[int, IGCUpload], dict[int, list[TrackPoint]]]:
    uploads = session.scalars(select(IGCUpload).where(IGCUpload.task_id == task.id).order_by(IGCUpload.uploaded_at)).all()
    uploads_by_id = {upload.id: upload for upload in uploads}
    scoring_inputs = session.scalars(select(TaskScoringInput).where(TaskScoringInput.task_id == task.id)).all()
    scoring_input_by_pilot = {entry.pilot_id: entry for entry in scoring_inputs}
    selected_upload_ids = [
        entry.selected_upload_id
        for entry in scoring_inputs
        if entry.selected_upload_id is not None and entry.selected_upload_id in uploads_by_id
    ]
    trackpoints = (
        session.scalars(
            select(TrackPoint)
            .where(TrackPoint.upload_id.in_(selected_upload_ids))
            .order_by(TrackPoint.upload_id, TrackPoint.sequence)
        ).all()
        if selected_upload_ids
        else []
    )
    trackpoints_by_upload: dict[int, list[TrackPoint]] = {}
    for trackpoint in trackpoints:
        trackpoints_by_upload.setdefault(trackpoint.upload_id, []).append(trackpoint)

    pilot_ids = session.scalars(
        select(EventPilot.pilot_id).where(EventPilot.event_id == task.event_id).order_by(EventPilot.pilot_id.asc())
    ).all()
    evaluations: list[dict[str, Any]] = []
    for pilot_id in pilot_ids:
        scoring_input = scoring_input_by_pilot.get(pilot_id)
        upload = uploads_by_id.get(scoring_input.selected_upload_id) if scoring_input and scoring_input.selected_upload_id else None
        if upload is not None and upload.pilot_id == pilot_id:
            evaluations.append(
                {
                    "pilot_id": pilot_id,
                    "upload": upload,
                    "evaluation": evaluate_task(
                        task,
                        task_points,
                        trackpoints_by_upload.get(upload.id, []),
                        event.timezone,
                        optimized_distance_km,
                        airscore_waypoints=airscore_waypoints,
                        task_class=_event_task_class(event),
                        event=event,
                    ),
                }
            )
            continue
        status_evaluation = _status_evaluation(task, event, scoring_input.status_override if scoring_input else None)
        if status_evaluation is not None:
            evaluations.append({"pilot_id": pilot_id, "upload": None, "evaluation": status_evaluation})
    return evaluations, scoring_input_by_pilot, uploads_by_id, trackpoints_by_upload


def find_hc2025_task1(session: Session, task_id: int | None = None) -> Task | None:
    if task_id is not None:
        return session.get(Task, task_id)
    query = (
        select(Task)
        .join(Event, Task.event_id == Event.id)
        .where(func.lower(Event.name).like("%hc 2025%"))
        .where(Task.task_date == date(2025, 6, 2))
        .order_by(Task.id.desc())
    )
    task = session.scalar(query)
    if task is not None:
        return task
    fallback = (
        select(Task)
        .join(Event, Task.event_id == Event.id)
        .where(func.lower(Event.name).like("%hc%"))
        .where(func.lower(Task.name).like("%task%1%"))
        .order_by(Task.id.desc())
    )
    return session.scalar(fallback)


def build_hc2025_task1_audit(session: Session, task_id: int | None = None) -> dict[str, Any]:
    task = find_hc2025_task1(session, task_id)
    if task is None:
        return {"status": "missing", "message": "Could not find HC 2025 Task 1. Pass --task-id to audit a specific task."}
    event = session.get(Event, task.event_id)
    if event is None:
        return {"status": "missing_event", "task_id": task.id}

    task_points = session.scalars(select(TaskPoint).where(TaskPoint.task_id == task.id).order_by(TaskPoint.position)).all()
    formula = _build_formula(task, event)
    optimized_distance_km, airscore_waypoints = _compute_optimized_task_distance(task_points)
    distance_waypoints, _ = _prepare_waypoints_for_distance(airscore_waypoints, formula)
    task_stats = _waypoint_distance_stats(distance_waypoints or airscore_waypoints, optimized_distance_km)
    evaluations, scoring_input_by_pilot, uploads_by_id, trackpoints_by_upload = _build_evaluations(
        session,
        task,
        event,
        task_points,
        distance_waypoints or airscore_waypoints,
        optimized_distance_km,
    )
    scored_payloads = _score_evaluations(task, len(scoring_input_by_pilot) or len(evaluations), evaluations, {}, event, airscore_waypoints=distance_waypoints or airscore_waypoints)
    scored_by_pilot = {payload["pilot_id"]: payload for payload in scored_payloads}
    airscore_task, task_totals, pilot_results, scored_pilots = _build_airscore_gap_context(
        task,
        event,
        distance_waypoints or airscore_waypoints,
        formula,
        evaluations,
    )
    available_raw = points_weight(airscore_task, task_totals, formula)
    available_points = {
        "distance": round(available_raw[0], 4),
        "speed": round(available_raw[1], 4),
        "leading": round(available_raw[2], 4),
        "arrival": round(available_raw[3], 4),
    }
    parameter_rows = _build_parameter_comparison(task, event, formula, task_stats, task_totals, available_points)

    pilot_ids = session.scalars(select(EventPilot.pilot_id).where(EventPilot.event_id == task.event_id).order_by(EventPilot.pilot_id.asc())).all()
    pilots = {pilot.id: pilot for pilot in session.scalars(select(Pilot).where(Pilot.id.in_(pilot_ids))).all()} if pilot_ids else {}
    stored_results = {result.pilot_id: result for result in session.scalars(select(ScoreResult).where(ScoreResult.task_id == task.id)).all()}
    official_by_comp = {row["comp"]: row for row in HC2025_TASK1_OFFICIAL_RESULTS}
    official_by_name = {_normalize_name(row["name"]): row for row in HC2025_TASK1_OFFICIAL_RESULTS}
    timezone_name = _effective_timezone_name(event.timezone, task_points)

    rows = []
    for pilot_id in pilot_ids:
        pilot = pilots.get(pilot_id)
        pilot_name = f"{pilot.first_name} {pilot.last_name}".strip() if pilot else None
        comp = str(pilot.competition_number or "").strip() if pilot else ""
        official = official_by_comp.get(comp) or official_by_name.get(_normalize_name(pilot_name))
        scoring_input = scoring_input_by_pilot.get(pilot_id)
        upload = uploads_by_id.get(scoring_input.selected_upload_id) if scoring_input and scoring_input.selected_upload_id else None
        stored = stored_results.get(pilot_id)
        effective = scored_by_pilot.get(pilot_id)
        awarded = (effective or {}).get("details_json", {}).get("gap", {}).get("awarded_points", {})
        actual = {
            "status": (effective or {}).get("status"),
            "ss": _local_clock((effective or {}).get("started_at"), timezone_name),
            "es": _local_clock((effective or {}).get("ess_at") or (effective or {}).get("goal_at"), timezone_name),
            "time": _duration_clock((effective or {}).get("elapsed_seconds")),
            "distance": (effective or {}).get("distance_flown_km"),
            "distance_points": awarded.get("distance"),
            "time_points": awarded.get("speed"),
            "total": (effective or {}).get("score_points"),
        }
        diffs: dict[str, Any] = {}
        if official:
            if actual["status"] != official["status"]:
                diffs["status"] = {"fs_score": official["status"], "aervyx": actual["status"]}
            for key in ("ss", "es", "time"):
                delta = _clock_delta(actual.get(key), official.get(key))
                if delta is not None:
                    diffs[key] = {"fs_score": official.get(key), "aervyx": actual.get(key), "delta": delta}
            for key in ("distance", "distance_points", "time_points", "total"):
                delta = _number_delta(actual.get(key), official.get(key))
                if delta is not None:
                    diffs[key] = {"fs_score": official.get(key), "aervyx": actual.get(key), "delta": delta}
        rows.append(
            {
                "pilot_id": pilot_id,
                "competition_number": comp or None,
                "pilot_name": pilot_name,
                "official": official,
                "aervyx_effective": actual,
                "stored_result": {
                    "status": stored.status,
                    "ss": _local_clock(stored.started_at, timezone_name),
                    "es": _local_clock(stored.ess_at or stored.goal_at, timezone_name),
                    "time": _duration_clock(stored.elapsed_seconds),
                    "distance": stored.distance_flown_km,
                    "total": stored.score_points,
                    "awarded_points": stored.details_json.get("gap", {}).get("awarded_points") if stored.details_json else None,
                } if stored else None,
                "selected_upload": {
                    "id": upload.id,
                    "filename": upload.filename,
                    "metadata_pilot_name": (upload.metadata_json or {}).get("pilot_name"),
                    "fix_count": (upload.metadata_json or {}).get("fix_count"),
                    "trackpoint_count": len(trackpoints_by_upload.get(upload.id, [])),
                    "stored_path": upload.stored_path,
                } if upload else None,
                "status_override": scoring_input.status_override if scoring_input else None,
                "differences": diffs,
            }
        )

    knut = _build_knut_investigation(rows, evaluations, pilot_results, scored_pilots, task_totals, formula, available_points, timezone_name)
    return {
        "status": "ok",
        "source": "HC 2025 Task 1 official FS Score table pasted by event admin",
        "task": {
            "id": task.id,
            "name": task.name,
            "task_date": task.task_date.isoformat() if task.task_date else None,
            "task_type": task.task_type,
            "start_open_time": task.start_open_time,
            "start_close_time": task.start_close_time,
            "task_start_time": task.task_start_time,
            "task_finish_time": task.task_finish_time,
        },
        "event": {
            "id": event.id,
            "name": event.name,
            "timezone": event.timezone,
            "effective_timezone": timezone_name,
            "scoring_formula": event.scoring_formula,
        },
        "tracklog_handoff": {
            "input": "track_points table rows generated from IGC B records",
            "time_basis": "UTC-aware recorded_at fixes",
            "coordinate_basis": "raw IGC latitude/longitude fixes converted to AirScore radians",
            "interpolation": "none; verifier selects recorded GPS fixes, so 1-2 second FS Score offsets are expected if FS interpolates cylinder crossings",
        },
        "parameter_comparison": parameter_rows,
        "pilot_comparison": rows,
        "knut_investigation": knut,
    }


def _build_knut_investigation(
    rows: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
    pilot_results: list[dict[str, Any]],
    scored_pilots: list[dict[str, Any]],
    task_totals: dict[str, Any],
    formula: dict[str, Any],
    available_points: dict[str, Any],
    timezone_name: str,
) -> dict[str, Any]:
    knut_row = next((row for row in rows if row.get("competition_number") == "6" or _normalize_name(row.get("pilot_name")) == "knut r ryerson"), None)
    if knut_row is None:
        return {"status": "missing", "message": "Knut was not found in the Aervyx event roster."}
    pilot_id = knut_row["pilot_id"]
    evaluation = next((entry["evaluation"] for entry in evaluations if entry.get("pilot_id") == pilot_id), None)
    pilot_result = next((pilot for pilot in pilot_results if pilot.get("pilot_id") == pilot_id), None)
    scored = next((pilot for pilot in scored_pilots if pilot.get("pilot_id") == pilot_id), None)
    if pilot_result is None or scored is None:
        return {"status": "missing_scoring", "pilot": knut_row}
    kmdiff = calc_kmdiff({}, task_totals, formula)
    bucket = int(float(pilot_result.get("distance", 0.0) or 0.0) / 100.0)
    bucket = min(bucket, len(kmdiff) - 1) if kmdiff else 0
    lineardist = float(formula.get("lineardist", 0.5) or 0.5)
    maxdist = float(task_totals.get("maxdist", 0.0) or 0.0)
    distance_m = float(pilot_result.get("distance", 0.0) or 0.0)
    linear_component = (distance_m / maxdist) * lineardist if maxdist else 0.0
    difficulty_component = (kmdiff[bucket] if kmdiff else 0.0) * (1.0 - lineardist)
    official = knut_row.get("official") or {}
    details = evaluation.get("details", {}) if evaluation else {}
    hits = details.get("hits", [])
    start_hit = next((hit for hit in hits if str(hit.get("point_type", "")).lower() == "start"), None)
    missed = details.get("missed_point")
    return {
        "status": "ok",
        "selected_upload": knut_row.get("selected_upload"),
        "start_fix_used": start_hit.get("track_point") if start_hit else None,
        "start_time_local": _local_clock((knut_row.get("aervyx_effective") or {}).get("ss"), timezone_name),
        "missed_point": missed,
        "scored_distance_km": round(distance_m / 1000.0, 3),
        "fs_distance_km": official.get("distance"),
        "distance_bucket_100m": bucket,
        "available_distance_points": available_points["distance"],
        "lineardist": lineardist,
        "lookahead": task_totals.get("lookahead"),
        "distspread": task_totals.get("distspread"),
        "kmdiff_at_bucket": round(kmdiff[bucket], 6) if kmdiff else None,
        "linear_component": round(linear_component, 6),
        "difficulty_component": round(difficulty_component, 6),
        "aervyx_distance_points": round(float(scored.get("Pdist", 0.0) or 0.0), 3),
        "fs_distance_points": official.get("distance_points"),
        "point_delta": round(float(scored.get("Pdist", 0.0) or 0.0) - float(official.get("distance_points", 0.0) or 0.0), 3),
        "diagnosis": "Knut's distance is near FS Score; any remaining large point delta is in GAP distance-difficulty allocation, not track verification.",
    }


def render_hc2025_task1_audit_markdown(audit: dict[str, Any]) -> str:
    if audit.get("status") != "ok":
        return f"# HC 2025 Task 1 Audit\n\nStatus: {audit.get('status')}\n\n{audit.get('message', '')}\n"
    lines = [
        "# HC 2025 Task 1 Audit",
        "",
        f"Event: {audit['event']['name']} (task {audit['task']['id']})",
        f"Timezone: {audit['event']['timezone']} -> {audit['event']['effective_timezone']}",
        "",
        "## Parameter Comparison",
        "",
        "| Param | FS Score | Aervyx Stored | AirScore Effective | Match | Note |",
        "| --- | ---: | --- | ---: | --- | --- |",
    ]
    for row in audit["parameter_comparison"]:
        lines.append(
            "| {param} | {fs} | {stored} | {effective} | {match} | {note} |".format(
                param=row["param"],
                fs=_markdown_value(row["fs_score"]),
                stored=_markdown_value(row["aervyx_stored"]),
                effective=_markdown_value(row["airscore_effective"]),
                match="yes" if row["match"] else "NO",
                note=row.get("note") or "",
            )
        )
    lines.extend(
        [
            "",
            "## Pilot Comparison",
            "",
            "| # | Pilot | FS SS | Aervyx SS | FS Distance | Aervyx Distance | FS Dist Pts | Aervyx Dist Pts | FS Time Pts | Aervyx Time Pts | FS Total | Aervyx Total | Diffs |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in audit["pilot_comparison"]:
        official = row.get("official") or {}
        actual = row.get("aervyx_effective") or {}
        lines.append(
            "| {comp} | {name} | {fs_ss} | {actual_ss} | {fs_dist} | {actual_dist} | {fs_dp} | {actual_dp} | {fs_tp} | {actual_tp} | {fs_total} | {actual_total} | {diffs} |".format(
                comp=row.get("competition_number") or "",
                name=row.get("pilot_name") or "",
                fs_ss=_markdown_value(official.get("ss")),
                actual_ss=_markdown_value(actual.get("ss")),
                fs_dist=_markdown_value(official.get("distance")),
                actual_dist=_markdown_value(actual.get("distance")),
                fs_dp=_markdown_value(official.get("distance_points")),
                actual_dp=_markdown_value(actual.get("distance_points")),
                fs_tp=_markdown_value(official.get("time_points")),
                actual_tp=_markdown_value(actual.get("time_points")),
                fs_total=_markdown_value(official.get("total")),
                actual_total=_markdown_value(actual.get("total")),
                diffs=", ".join(row.get("differences", {}).keys()) or "",
            )
        )
    knut = audit["knut_investigation"]
    lines.extend(
        [
            "",
            "## Knut Investigation",
            "",
            f"Selected upload: {_markdown_value((knut.get('selected_upload') or {}).get('filename'))}",
            f"IGC metadata pilot: {_markdown_value((knut.get('selected_upload') or {}).get('metadata_pilot_name'))}",
            f"Scored distance: {_markdown_value(knut.get('scored_distance_km'))} km vs FS {_markdown_value(knut.get('fs_distance_km'))} km",
            f"Distance points: {_markdown_value(knut.get('aervyx_distance_points'))} vs FS {_markdown_value(knut.get('fs_distance_points'))} (delta {_markdown_value(knut.get('point_delta'))})",
            f"Bucket: {_markdown_value(knut.get('distance_bucket_100m'))}, lookahead: {_markdown_value(knut.get('lookahead'))}, kmdiff: {_markdown_value(knut.get('kmdiff_at_bucket'))}",
            f"Linear component: {_markdown_value(knut.get('linear_component'))}, difficulty component: {_markdown_value(knut.get('difficulty_component'))}",
            f"Diagnosis: {knut.get('diagnosis')}",
            "",
            "## Tracklog Handoff",
            "",
            f"Input: {audit['tracklog_handoff']['input']}",
            f"Times: {audit['tracklog_handoff']['time_basis']}",
            f"Coordinates: {audit['tracklog_handoff']['coordinate_basis']}",
            f"Interpolation: {audit['tracklog_handoff']['interpolation']}",
        ]
    )
    return "\n".join(lines) + "\n"


def _markdown_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return "`" + json.dumps(value, sort_keys=True) + "`"
    if isinstance(value, float):
        return str(_format_number(value))
    return str(value).replace("|", "\\|")


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the HC 2025 Task 1 FS Score vs Aervyx audit report.")
    parser.add_argument("--task-id", type=int, default=None, help="Aervyx task id. Defaults to auto-detecting HC 2025 Task 1.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args(argv)

    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        try:
            audit = build_hc2025_task1_audit(session, args.task_id)
        except SQLAlchemyError as exc:
            audit = {
                "status": "database_unavailable",
                "message": str(exc),
            }
    finally:
        session.close()
    if args.format == "json":
        print(json.dumps(audit, indent=2, sort_keys=True, default=str))
    else:
        print(render_hc2025_task1_audit_markdown(audit))
    return 0 if audit.get("status") == "ok" else 1
