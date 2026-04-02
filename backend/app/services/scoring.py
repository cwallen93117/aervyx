from __future__ import annotations

import math
from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.models import Event, EventPilot, IGCUpload, Pilot, ScorePenalty, ScoreResult, Task, TaskPoint, TaskScoringInput, TrackPoint

STATUS_ORDER = {"goal": 0, "ess": 1, "partial": 2, "minimum_distance": 3, "did_not_fly": 4, "absent": 5, "uploaded": 6}
COMPETITIVE_STATUSES = {"goal", "ess", "partial"}
TIMEZONE_ALIASES = {
    "eastern": "America/New_York",
    "central": "America/Chicago",
    "mountain": "America/Denver",
    "pacific": "America/Los_Angeles",
    "utc": "UTC",
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return 2 * radius_km * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _to_xy_km(latitude: float, longitude: float, reference_latitude: float, reference_longitude: float) -> tuple[float, float]:
    x = (longitude - reference_longitude) * 111.32 * math.cos(math.radians(reference_latitude))
    y = (latitude - reference_latitude) * 110.57
    return x, y


def _project_progress(prev_point: TaskPoint, next_point: TaskPoint, trackpoints: list[TrackPoint]) -> float:
    leg_distance = haversine_km(prev_point.latitude, prev_point.longitude, next_point.latitude, next_point.longitude)
    if leg_distance <= 0:
        return 0.0
    bx, by = _to_xy_km(next_point.latitude, next_point.longitude, prev_point.latitude, prev_point.longitude)
    length_sq = bx * bx + by * by
    if length_sq <= 0:
        return 0.0
    best = 0.0
    for trackpoint in trackpoints:
        px, py = _to_xy_km(trackpoint.latitude, trackpoint.longitude, prev_point.latitude, prev_point.longitude)
        projection = (px * bx + py * by) / length_sq
        best = max(best, min(max(projection, 0.0), 1.0))
    return best * leg_distance


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _isoformat_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _blank_evaluation(status: str) -> dict:
    return {
        "status": status,
        "distance_flown_km": 0.0,
        "started_at": None,
        "ess_at": None,
        "goal_at": None,
        "elapsed_seconds": None,
        "score_points": 0.0,
        "details": {"hits": [], "total_distance_km": 0.0},
    }


def _minimum_distance_evaluation(task: Task, event: Event | None = None) -> dict:
    formula = _build_formula(task, event)
    evaluation = _blank_evaluation("minimum_distance")
    evaluation["distance_flown_km"] = round(formula["mindist_km"], 3)
    evaluation["details"] = {
        "hits": [],
        "total_distance_km": 0.0,
        "status_override": "minimum_distance",
    }
    return evaluation


def _apply_penalties(raw_score: float, penalties: list[ScorePenalty]) -> float:
    score = max(float(raw_score or 0.0), 0.0)
    percentage_penalties = [penalty for penalty in penalties if penalty.penalty_type == "percentage"]
    fixed_penalties = [penalty for penalty in penalties if penalty.penalty_type == "fixed"]
    for penalty in percentage_penalties:
        score -= score * (max(float(penalty.value or 0.0), 0.0) / 100.0)
    for penalty in fixed_penalties:
        score -= max(float(penalty.value or 0.0), 0.0)
    return round(max(score, 0.0), 2)


def _resolve_timezone_name(value: str | None) -> str:
    if not value:
        return "UTC"
    normalized = value.strip()
    return TIMEZONE_ALIASES.get(normalized.lower(), normalized)


def _parse_clock_time(value: str | None) -> time | None:
    if not value:
        return None
    parts = value.split(":")
    if len(parts) < 2:
        return None
    hour = int(parts[0])
    minute = int(parts[1])
    second = int(parts[2]) if len(parts) > 2 else 0
    return time(hour, minute, second)


def _resolve_task_time_utc(value: str | None, trackpoints: list[TrackPoint], timezone_name: str) -> datetime | None:
    clock_time = _parse_clock_time(value)
    if clock_time is None or not trackpoints:
        return None
    try:
        zone = ZoneInfo(_resolve_timezone_name(timezone_name))
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    local_date = trackpoints[0].recorded_at.astimezone(zone).date()
    local_dt = datetime.combine(local_date, clock_time, tzinfo=zone)
    return local_dt.astimezone(trackpoints[0].recorded_at.tzinfo)


def _distance_to_task_point(trackpoint: TrackPoint, point: TaskPoint) -> float:
    return haversine_km(trackpoint.latitude, trackpoint.longitude, point.latitude, point.longitude)


def _find_entry_hit(point: TaskPoint, trackpoints: list[TrackPoint], radius_km: float, cursor: int = 0, earliest_at: datetime | None = None, latest_at: datetime | None = None) -> tuple[int, datetime] | None:
    previous_inside = False
    for idx in range(cursor, len(trackpoints)):
        trackpoint = trackpoints[idx]
        if earliest_at is not None and trackpoint.recorded_at < earliest_at:
            previous_inside = _distance_to_task_point(trackpoint, point) <= radius_km
            continue
        if latest_at is not None and trackpoint.recorded_at > latest_at:
            break
        inside = _distance_to_task_point(trackpoint, point) <= radius_km
        if inside and not previous_inside:
            return idx, trackpoint.recorded_at
        if inside:
            return idx, trackpoint.recorded_at
        previous_inside = inside
    return None


def _find_exit_hit(point: TaskPoint, trackpoints: list[TrackPoint], radius_km: float, cursor: int = 0, earliest_at: datetime | None = None, latest_at: datetime | None = None) -> tuple[int, datetime] | None:
    previous_inside: bool | None = None
    for idx in range(cursor, len(trackpoints)):
        trackpoint = trackpoints[idx]
        inside = _distance_to_task_point(trackpoint, point) <= radius_km
        if earliest_at is not None and trackpoint.recorded_at < earliest_at:
            previous_inside = inside
            continue
        if latest_at is not None and trackpoint.recorded_at > latest_at:
            break
        if previous_inside is None:
            previous_inside = inside
            continue
        if previous_inside and not inside:
            return idx, trackpoint.recorded_at
        previous_inside = inside
    return None


def evaluate_task(task: Task, task_points: list[TaskPoint], trackpoints: list[TrackPoint], event_timezone: str | None = None) -> dict:
    ordered_points = sorted(task_points, key=lambda point: point.position)
    if len(ordered_points) < 2:
        return {"status": "uploaded", "distance_flown_km": 0.0, "details": {"hits": [], "total_distance_km": 0.0}}

    hit_indices: dict[int, int] = {}
    hit_times: dict[int, datetime] = {}
    timezone_name = event_timezone or "UTC"
    start_open_at = _resolve_task_time_utc(task.start_open_time or task.task_start_time, trackpoints, timezone_name)
    start_close_at = _resolve_task_time_utc(task.start_close_time or task.task_finish_time, trackpoints, timezone_name)
    cursor = 0
    for point in ordered_points:
        radius_km = point.radius_m / 1000.0
        if point.point_type == "start":
            hit = _find_exit_hit(point, trackpoints, radius_km, cursor=cursor, earliest_at=start_open_at, latest_at=start_close_at)
        else:
            hit = _find_entry_hit(point, trackpoints, radius_km, cursor=cursor)
        if hit is None:
            continue
        idx, hit_at = hit
        hit_indices[point.id] = idx
        hit_times[point.id] = hit_at
        cursor = idx + 1

    total_distance = 0.0
    progress_distance = 0.0
    for index in range(1, len(ordered_points)):
        previous_point = ordered_points[index - 1]
        current_point = ordered_points[index]
        leg_distance = haversine_km(previous_point.latitude, previous_point.longitude, current_point.latitude, current_point.longitude)
        total_distance += leg_distance
        if current_point.id in hit_indices:
            progress_distance += leg_distance
            continue
        if previous_point.id in hit_indices:
            progress_distance += _project_progress(previous_point, current_point, trackpoints[hit_indices[previous_point.id] + 1 :])
        break

    start_point = next((point for point in ordered_points if point.point_type == "start"), None)
    ess_point = next((point for point in ordered_points if point.point_type == "ESS"), None)
    goal_point = next((point for point in ordered_points if point.point_type == "goal"), None)
    started_at = hit_times.get(start_point.id) if start_point else None
    ess_at = hit_times.get(ess_point.id) if ess_point else None
    goal_at = hit_times.get(goal_point.id) if goal_point else None

    if goal_at is not None:
        status = "goal"
    elif ess_at is not None:
        status = "ess"
    elif progress_distance > 0:
        status = "partial"
    else:
        status = "uploaded"

    elapsed_seconds = None
    if started_at is not None and (goal_at or ess_at) is not None:
        elapsed_seconds = int(((goal_at or ess_at) - started_at).total_seconds())
        if elapsed_seconds < 0:
            elapsed_seconds = None

    return {
        "status": status,
        "distance_flown_km": round(progress_distance, 3),
        "started_at": started_at,
        "ess_at": ess_at,
        "goal_at": goal_at,
        "elapsed_seconds": elapsed_seconds,
        "score_points": 0.0,
        "details": {
            "hits": [
                {
                    "task_point_id": point.id,
                    "name": point.name,
                    "point_type": point.point_type,
                    "hit": point.id in hit_indices,
                    "hit_at": _isoformat_or_none(hit_times.get(point.id)),
                }
                for point in ordered_points
            ],
            "total_distance_km": round(total_distance, 3),
        },
    }


def _build_formula(task: Task, event: Event | None = None) -> dict:
    penalties = task.penalties_json or {}
    nominal_goal = event.nominal_goal_percent if event and event.nominal_goal_percent is not None else penalties.get("nominal_goal", penalties.get("nomgoal", 0.3))
    nominal_goal = float(nominal_goal)
    if nominal_goal > 1:
        nominal_goal /= 100.0
    ss_penalty_source = event.goal_ss_penalty if event and event.goal_ss_penalty is not None else penalties.get("sspenalty", 1.0)
    use_time_points = bool(event.use_time_points) if event and event.use_time_points is not None else True
    use_departure_points = bool(event.use_departure_points) if event and event.use_departure_points is not None else False
    use_leading_points = bool(event.use_leading_points) if event and event.use_leading_points is not None else True
    use_arrival_points = False
    if event is not None:
        if event.use_arrival_position_points is not None or event.use_arrival_time_points is not None:
            use_arrival_points = bool(event.use_arrival_position_points) or bool(event.use_arrival_time_points)

    # Leading weight: default 1/8, scaled by leading_weight_factor from event
    leading_weight_factor = float(event.leading_weight_factor) if event and event.leading_weight_factor is not None else 1.0
    base_leading_weight = float(penalties.get("weightleading", 1.0 / 8.0))

    return {
        # Core nominal parameters
        "mindist_km": max(float(task.minimum_distance_km or (event.minimum_distance_km if event and event.minimum_distance_km is not None else 0) or 0), 0.1),
        "nomdist_km": max(float(task.nominal_distance_km or (event.nominal_distance_km if event and event.nominal_distance_km is not None else 0) or 0), 1.0),
        "nomtime_seconds": max(float(task.nominal_time_hours or (event.nominal_time_hours if event and event.nominal_time_hours is not None else 0) or 0) * 3600.0, 600.0),
        "nomlaunch": _clamp(float(task.nominal_launch or (event.nominal_launch if event and event.nominal_launch is not None else 0.95)), 0.1, 1.0),
        "nomgoal_fraction": _clamp(nominal_goal, 0.05, 1.0),
        # Weight distribution
        "weightdist": penalties.get("weightdist", "post2014"),
        "weightspeed": float(penalties.get("weightspeed", 5.6 / 8.0)),
        "weightstart": float(penalties.get("weightstart", 1.4 / 8.0)),
        "weightarrival": float(penalties.get("weightarrival", 1.0 / 8.0)),
        "weightleading": base_leading_weight * leading_weight_factor,
        "lineardist": _clamp(float(penalties.get("lineardist", 0.5)), 0.0, 1.0),
        # Modes
        "departure_mode": penalties.get("departure_mode", "departure"),
        "arrival_mode": "time" if event and event.use_arrival_time_points else penalties.get("arrival_mode", "position"),
        "speedcalc": penalties.get("speedcalc", "standard"),
        "sspenalty": _clamp(float(ss_penalty_source), 0.0, 1.0),
        "lookahead": max(int(penalties.get("lookahead", 30)), 1),
        # Point type toggles
        "use_distance_points": bool(event.use_distance_points) if event and event.use_distance_points is not None else True,
        "use_time_points": use_time_points,
        "use_departure_points": use_departure_points,
        "use_leading_points": use_leading_points,
        "use_arrival_points": use_arrival_points,
        "use_difficulty_for_distance_points": bool(event.use_difficulty_for_distance_points) if event and event.use_difficulty_for_distance_points is not None else True,
        # Leading coefficient options
        "leading_weight_factor": leading_weight_factor,
        "use_distance_squared_for_lc": bool(event.use_distance_squared_for_lc) if event and event.use_distance_squared_for_lc is not None else False,
        "use_constant_leading_weight": bool(event.use_constant_leading_weight) if event and event.use_constant_leading_weight is not None else False,
        "use_pwca2019_for_lc": bool(event.use_pwca2019_for_lc) if event and event.use_pwca2019_for_lc is not None else False,
        "use_proportional_leading_weight_if_nobody_in_goal": bool(event.use_proportional_leading_weight_if_nobody_in_goal) if event and event.use_proportional_leading_weight_if_nobody_in_goal is not None else True,
        # Day quality and validation
        "day_quality_override": float(event.day_quality_override) if event and event.day_quality_override is not None else 0.0,
        "use_1000_points_for_max_day_quality": bool(event.use_1000_points_for_max_day_quality) if event and event.use_1000_points_for_max_day_quality is not None else False,
        "normalize_1000_before_day_quality": bool(event.normalize_1000_before_day_quality) if event and event.normalize_1000_before_day_quality is not None else False,
        "min_time_span_for_valid_task_minutes": int(event.min_time_span_for_valid_task_minutes) if event and event.min_time_span_for_valid_task_minutes is not None else 60,
        # Time/speed modifiers
        "time_points_if_not_in_goal": float(event.time_points_if_not_in_goal) if event and event.time_points_if_not_in_goal is not None else 1.0,
        "use_flat_decline_of_timepoints": bool(event.use_flat_decline_of_timepoints) if event and event.use_flat_decline_of_timepoints is not None else False,
        "redistribute_removed_time_points_as_distance_points": bool(event.redistribute_removed_time_points_as_distance_points) if event and event.redistribute_removed_time_points_as_distance_points is not None else False,
        # Stopped task / jump-the-gun
        "score_back_time_minutes": int(event.score_back_time_minutes) if event and event.score_back_time_minutes is not None else 15,
        "stopped_glide_bonus": float(event.stopped_glide_bonus) if event and event.stopped_glide_bonus is not None else 0.0,
        "jump_the_gun_factor": float(event.jump_the_gun_factor) if event and event.jump_the_gun_factor is not None else 0.0,
        "jump_the_gun_max_seconds": int(event.jump_the_gun_max_seconds) if event and event.jump_the_gun_max_seconds is not None else 0,
        # Altitude and glide
        "scoring_altitude": str(event.scoring_altitude or "GPS") if event else "GPS",
        "final_glide_decelerator": str(event.final_glide_decelerator or "none") if event else "none",
        # Rounding
        "number_of_decimals_task_results": int(event.number_of_decimals_task_results) if event and event.number_of_decimals_task_results is not None else 2,
        "number_of_decimals_competition_results": int(event.number_of_decimals_competition_results) if event and event.number_of_decimals_competition_results is not None else 1,
        # Turnpoint tolerance
        "turnpoint_radius_tolerance": float(event.turnpoint_radius_tolerance) if event and event.turnpoint_radius_tolerance is not None else 0.0005,
    }


def _day_quality(task_stats: dict, formula: dict) -> dict:
    pilots = max(task_stats["pilots"], 1)
    launched = task_stats["launched"]
    launched_goal = task_stats["goal"]
    x_launch = launched / max(pilots * formula["nomlaunch"], 1e-6)
    if x_launch >= 1:
        launch_validity = 1.0
    else:
        launch_validity = _clamp(0.027 * x_launch + 2.917 * x_launch**2 - 1.944 * x_launch**3)

    nomdist = formula["nomdist_km"]
    mindist = formula["mindist_km"]
    distance_span = max(nomdist - mindist, 0.1)
    average_distance = task_stats["distance_sum_km"] / launched if launched else 0.0
    distance_ratio = max(average_distance - mindist, 0.0) / distance_span
    goal_expectation = max(launched * formula["nomgoal_fraction"], 1.0)
    goal_ratio = launched_goal / goal_expectation
    max_ratio = task_stats["max_distance_km"] / max(nomdist, 0.1)
    distance_validity = _clamp(distance_ratio * 0.6 + _clamp(goal_ratio) * 0.25 + _clamp(max_ratio) * 0.15)

    if task_stats["fastest_time_seconds"] is not None:
        x_time = task_stats["fastest_time_seconds"] / formula["nomtime_seconds"]
    else:
        x_time = task_stats["max_distance_km"] / max(formula["nomdist_km"], 0.1)
    if x_time < 1:
        time_validity = _clamp(-0.271 + 2.912 * x_time - 2.098 * x_time**2 + 0.457 * x_time**3)
    else:
        time_validity = 1.0

    stopped_validity = 1.0
    quality = round(launch_validity * distance_validity * time_validity * stopped_validity, 6)

    # Day quality override: if set to a positive value, use it instead of computed quality
    day_quality_override = formula.get("day_quality_override", 0.0)
    if day_quality_override and day_quality_override > 0:
        quality = _clamp(day_quality_override)

    return {
        "launch": round(launch_validity, 6),
        "distance": round(distance_validity, 6),
        "time": round(time_validity, 6),
        "stopped": stopped_validity,
        "overall": quality,
    }


def _points_weight(task_stats: dict, formula: dict) -> dict:
    quality = task_stats["quality"]
    if task_stats["launched"] <= 0 or quality <= 0:
        return {"distance": 0.0, "speed": 0.0, "departure": 0.0, "leading": 0.0, "arrival": 0.0}

    x = task_stats["goal"] / max(task_stats["launched"], 1)
    if not formula["use_distance_points"]:
        distweight = 0.0
    elif formula["weightdist"] == "post2014":
        distweight = _clamp(0.9 - 1.665 * x + 1.713 * x**2 - 0.587 * x**3, 0.1, 0.9)
    else:
        distweight = 0.838
    speed_bucket = 1.0 - distweight

    # If redistribute_removed_time_points_as_distance_points is on and time/leading/etc
    # are disabled, shift their share to distance
    if formula.get("redistribute_removed_time_points_as_distance_points"):
        any_speed_active = (
            formula["use_time_points"]
            or formula["use_departure_points"]
            or formula.get("use_leading_points", False)
            or formula["use_arrival_points"]
        )
        if not any_speed_active:
            distweight = 1.0
            speed_bucket = 0.0

    active_speed_weights: list[tuple[str, float]] = []
    if formula["use_time_points"]:
        active_speed_weights.append(("speed", formula["weightspeed"]))
    if formula.get("use_leading_points", False):
        active_speed_weights.append(("leading", formula.get("weightleading", 1.0 / 8.0)))
    if formula["use_departure_points"]:
        active_speed_weights.append(("departure", formula["weightstart"]))
    if formula["use_arrival_points"]:
        active_speed_weights.append(("arrival", formula["weightarrival"]))
    if not active_speed_weights:
        active_speed_weights.append(("speed", 1.0))
    normalizer = sum(weight for _, weight in active_speed_weights) or 1.0
    bucket_points = {name: round(1000.0 * quality * speed_bucket * (weight / normalizer), 3) for name, weight in active_speed_weights}
    return {
        "distance": round(1000.0 * quality * distweight, 3),
        "departure": bucket_points.get("departure", 0.0),
        "leading": bucket_points.get("leading", 0.0),
        "arrival": bucket_points.get("arrival", 0.0),
        "speed": bucket_points.get("speed", 0.0),
    }


def _calc_kmdiff(task_stats: dict, evaluations: list[dict], formula: dict) -> list[float]:
    max_distance = task_stats["max_distance_km"]
    if max_distance <= 0:
        return [0.5]

    bucket_count = max(int(math.floor(max_distance * 10)), 1)
    min_bucket = max(0, min(bucket_count, int(math.floor(formula["mindist_km"] * 10))))
    landed_counts = [0] * (bucket_count + 1)
    landed_out_count = 0
    for entry in evaluations:
        evaluation = entry["evaluation"]
        if evaluation["status"] in {"goal", "ess"}:
            continue
        if evaluation["distance_flown_km"] <= 0 and evaluation["started_at"] is None:
            continue
        distance = min(max(evaluation["distance_flown_km"], formula["mindist_km"]), max_distance)
        bucket = min(bucket_count, max(min_bucket, int(math.floor(distance * 10))))
        landed_counts[bucket] += 1
        landed_out_count += 1

    if landed_out_count <= 0:
        return [round(0.5 * (index / bucket_count), 6) for index in range(bucket_count + 1)]

    lookahead = min(bucket_count, max(30, int(round((30.0 * max_distance) / landed_out_count))))
    difficulty = [0.0] * (bucket_count + 1)
    for bucket in range(min_bucket, bucket_count + 1):
        upper = min(bucket_count, bucket + lookahead)
        difficulty[bucket] = float(sum(landed_counts[bucket : upper + 1]))

    sum_of_difficulty = sum(difficulty[min_bucket : bucket_count + 1])
    if sum_of_difficulty <= 0:
        return [round(0.5 * (index / bucket_count), 6) for index in range(bucket_count + 1)]

    running = 0.0
    diffscore = [0.0] * (bucket_count + 1)
    for bucket in range(bucket_count + 1):
        if bucket < min_bucket:
            diffscore[bucket] = 0.0
            continue
        running += difficulty[bucket] / (2.0 * sum_of_difficulty)
        diffscore[bucket] = min(running, 0.5)

    diffscore[bucket_count] = 0.5
    return [round(value, 6) for value in diffscore]


def _pilot_distance_score(evaluation: dict, available_points: dict, task_stats: dict, kmdiff: list[float], formula: dict) -> float:
    if available_points["distance"] <= 0:
        return 0.0
    max_distance = task_stats["max_distance_km"]
    if max_distance <= 0:
        return 0.0
    distance = min(max(evaluation["distance_flown_km"], 0.0), max_distance)
    if formula["use_difficulty_for_distance_points"]:
        linear_fraction = (distance / max_distance) / 2.0
        distance_tenths = distance * 10.0
        lower_bucket = min(len(kmdiff) - 1, max(0, int(math.floor(distance_tenths))))
        upper_bucket = min(len(kmdiff) - 1, lower_bucket + 1)
        interpolation = min(max(distance_tenths - lower_bucket, 0.0), 1.0)
        difficulty_fraction = kmdiff[lower_bucket] + (kmdiff[upper_bucket] - kmdiff[lower_bucket]) * interpolation
        ratio = linear_fraction + difficulty_fraction
    else:
        ratio = distance / max_distance
    return round(available_points["distance"] * _clamp(ratio), 2)


def _pilot_speed_score(evaluation: dict, available_points: dict, task_stats: dict, formula: dict) -> float:
    fastest_time = task_stats["fastest_time_seconds"]
    elapsed_seconds = evaluation["elapsed_seconds"]
    if available_points["speed"] <= 0 or fastest_time is None or elapsed_seconds is None:
        return 0.0
    if evaluation["status"] not in {"ess", "goal"}:
        return 0.0

    time_delta_hours = max((elapsed_seconds - fastest_time) / 3600.0, 0.0)

    if formula.get("use_flat_decline_of_timepoints"):
        # Linear decline: points drop linearly from 1 at fastest to 0 at slowest
        slowest_time = task_stats.get("slowest_time_seconds")
        if slowest_time is not None and slowest_time > fastest_time:
            ratio = 1.0 - (elapsed_seconds - fastest_time) / (slowest_time - fastest_time)
        else:
            ratio = 1.0
    elif formula["speedcalc"] == "extended":
        denominator = math.sqrt(max(fastest_time / 1800.0, 1e-6))
        ratio = 1.0 - (time_delta_hours / denominator) ** (2.0 / 3.0)
    else:
        denominator = math.sqrt(max(fastest_time / 3600.0, 1e-6))
        ratio = 1.0 - (time_delta_hours / denominator) ** (5.0 / 6.0)
    if math.isnan(ratio):
        return 0.0
    score = available_points["speed"] * _clamp(ratio)

    # If pilot reached ESS but not goal, apply time_points_if_not_in_goal factor
    time_factor = formula.get("time_points_if_not_in_goal", 1.0)
    if evaluation["status"] == "ess" and time_factor < 1.0:
        score *= time_factor

    return round(score, 2)


def _pilot_arrival_score(evaluation: dict, available_points: dict, task_stats: dict, arrival_place: int | None, arrival_delta_seconds: float | None, formula: dict) -> float:
    if available_points["arrival"] <= 0 or evaluation["status"] not in {"ess", "goal"}:
        return 0.0

    if formula["arrival_mode"] == "time" and arrival_delta_seconds is not None:
        x = 1.0 - (arrival_delta_seconds / (90.0 * 60.0))
    else:
        ess_count = max(task_stats["ess"], 1)
        if arrival_place is None:
            return 0.0
        x = 1.0 - ((arrival_place - 1) / ess_count)
    x = _clamp(x)
    curve = 0.2 + 0.037 * x + 0.13 * x**2 + 0.633 * x**3
    return round(available_points["arrival"] * curve, 2)


def _pilot_departure_score(evaluation: dict, available_points: dict, speed_points: float, task_stats: dict, formula: dict) -> float:
    first_departure_at = task_stats["first_departure_at"]
    started_at = evaluation["started_at"]
    if available_points["departure"] <= 0 or available_points["speed"] <= 0 or speed_points <= 0:
        return 0.0
    if started_at is None or first_departure_at is None or evaluation["elapsed_seconds"] is None:
        return 0.0
    if formula["departure_mode"] != "departure":
        return 0.0

    x = (started_at - first_departure_at).total_seconds() / max(formula["nomtime_seconds"], 1.0)
    if x >= 0.5:
        return 0.0
    curve = 1.0 - 6.312 * x + 10.932 * x**2 - 2.99 * x**3
    ratio = available_points["departure"] / max(available_points["speed"], 1e-6)
    return round(speed_points * ratio * _clamp(curve), 2)


def _compute_leading_coefficients(
    task_points: list[TaskPoint],
    evaluations: list[dict],
    formula: dict,
) -> dict[int, float]:
    """Compute Leading Coefficient (LC) for each pilot per GAP2021.

    The LC measures how much each pilot contributed to "opening the course".
    At each time step the best (minimum) distance-to-ESS across all flying
    pilots is tracked.  Each pilot accumulates a coefficient proportional to
    how close they were to ESS relative to the task distance.

    Higher LC → pilot was closer to ESS for longer → more leading points.

    Returns mapping of pilot_id → LC value.
    """
    ordered = sorted(task_points, key=lambda p: p.position)
    ess_point = next((p for p in ordered if p.point_type == "ESS"), None)
    if ess_point is None:
        ess_point = next((p for p in ordered if p.point_type == "goal"), None)
    if ess_point is None:
        return {}

    # Total course distance from launch to ESS
    task_distance = 0.0
    for i in range(1, len(ordered)):
        task_distance += haversine_km(
            ordered[i - 1].latitude, ordered[i - 1].longitude,
            ordered[i].latitude, ordered[i].longitude,
        )
        if ordered[i].id == ess_point.id:
            break
    if task_distance <= 0:
        return {}

    use_squared = formula.get("use_distance_squared_for_lc", False)

    # Build per-pilot distance-to-ESS timelines from trackpoints
    pilot_timelines: dict[int, list[tuple[datetime, float]]] = {}
    for entry in evaluations:
        trackpoints = entry.get("_trackpoints")
        if not trackpoints:
            continue
        evaluation = entry["evaluation"]
        if evaluation["started_at"] is None:
            continue
        pilot_id = entry.get("pilot_id")
        if pilot_id is None:
            continue

        timeline: list[tuple[datetime, float]] = []
        started_at = evaluation["started_at"]
        for tp in trackpoints:
            if tp.recorded_at < started_at:
                continue
            dist_to_ess = haversine_km(
                tp.latitude, tp.longitude,
                ess_point.latitude, ess_point.longitude,
            )
            timeline.append((tp.recorded_at, min(dist_to_ess, task_distance)))
        if timeline:
            pilot_timelines[pilot_id] = timeline

    if not pilot_timelines:
        return {}

    # Compute LC for each pilot: integral of (1 - dist_to_ess / task_dist) over time
    # This yields higher values for pilots closer to ESS over more time (leaders).
    coefficients: dict[int, float] = {}
    for pilot_id, timeline in pilot_timelines.items():
        lc = 0.0
        for i in range(1, len(timeline)):
            t_prev, d_prev = timeline[i - 1]
            t_curr, d_curr = timeline[i]
            dt = (t_curr - t_prev).total_seconds()
            if dt <= 0 or dt > 120:  # skip large gaps (> 2 minutes)
                continue

            # Fraction of course covered (0 at start, 1 at ESS)
            frac_prev = max(0.0, 1.0 - d_prev / task_distance)
            frac_curr = max(0.0, 1.0 - d_curr / task_distance)
            avg_frac = (frac_prev + frac_curr) / 2.0

            if use_squared:
                avg_frac = avg_frac ** 2

            lc += avg_frac * dt

        coefficients[pilot_id] = lc

    return coefficients


def _pilot_leading_score(
    pilot_id: int,
    leading_coefficients: dict[int, float],
    available_points: dict,
    formula: dict,
    task_stats: dict,
) -> float:
    """Compute leading points for a single pilot from pre-computed LCs."""
    if available_points.get("leading", 0.0) <= 0:
        return 0.0
    lc = leading_coefficients.get(pilot_id, 0.0)
    if lc <= 0:
        return 0.0

    all_lcs = [v for v in leading_coefficients.values() if v > 0]
    if not all_lcs:
        return 0.0

    lc_max = max(all_lcs)
    if lc_max <= 0:
        return 0.0

    # Ratio: 1.0 for best leader, lower for others
    ratio = lc / lc_max

    # Square-root curve rewards moderate leaders fairly
    score = available_points["leading"] * math.sqrt(_clamp(ratio))

    # If nobody made goal and proportional leading weight is on, scale down
    if task_stats["goal"] == 0 and formula.get("use_proportional_leading_weight_if_nobody_in_goal", True):
        # Scale by the best distance fraction — less leading points if nobody got far
        best_dist = task_stats["max_distance_km"]
        nomdist = formula.get("nomdist_km", 1.0)
        scale = _clamp(best_dist / max(nomdist, 1.0))
        score *= scale

    return round(score, 2)


def _build_task_stats(task: Task, registered_pilot_count: int, evaluations: list[dict], formula: dict) -> dict:
    launched_entries = [entry for entry in evaluations if entry["evaluation"]["distance_flown_km"] > 0 or entry["evaluation"]["started_at"] is not None]
    ess_entries = [entry for entry in evaluations if entry["evaluation"]["status"] in {"ess", "goal"}]
    goal_entries = [entry for entry in evaluations if entry["evaluation"]["status"] == "goal"]
    effective_distances = [
        max(entry["evaluation"]["distance_flown_km"], formula["mindist_km"]) if entry in launched_entries else entry["evaluation"]["distance_flown_km"]
        for entry in evaluations
    ]
    elapsed_candidates = [entry["evaluation"]["elapsed_seconds"] for entry in ess_entries if entry["evaluation"]["elapsed_seconds"] is not None]
    first_departure_at = min(
        (entry["evaluation"]["started_at"] for entry in launched_entries if entry["evaluation"]["started_at"] is not None),
        default=None,
    )
    first_arrival_at = min(
        ((entry["evaluation"]["goal_at"] or entry["evaluation"]["ess_at"]) for entry in ess_entries if (entry["evaluation"]["goal_at"] or entry["evaluation"]["ess_at"]) is not None),
        default=None,
    )
    last_arrival_at = max(
        ((entry["evaluation"]["goal_at"] or entry["evaluation"]["ess_at"]) for entry in ess_entries if (entry["evaluation"]["goal_at"] or entry["evaluation"]["ess_at"]) is not None),
        default=None,
    )
    stats = {
        "pilots": max(registered_pilot_count, len(evaluations)),
        "launched": len(launched_entries),
        "ess": len(ess_entries),
        "goal": len(goal_entries),
        "distance_sum_km": round(sum(effective_distances), 3),
        "max_distance_km": round(max(effective_distances, default=0.0), 3),
        "fastest_time_seconds": min(elapsed_candidates, default=None),
        "slowest_time_seconds": max(elapsed_candidates, default=None),
        "first_departure_at": first_departure_at,
        "first_arrival_at": first_arrival_at,
        "last_arrival_at": last_arrival_at,
    }
    validity = _day_quality(stats, formula)
    stats["launch_validity"] = validity["launch"]
    stats["distance_validity"] = validity["distance"]
    stats["time_validity"] = validity["time"]
    stats["stopped_validity"] = validity["stopped"]
    stats["quality"] = validity["overall"]
    return stats


def _serialize_stats(task_stats: dict) -> dict:
    return {
        "pilots": task_stats["pilots"],
        "launched": task_stats["launched"],
        "ess": task_stats["ess"],
        "goal": task_stats["goal"],
        "distance_sum_km": task_stats["distance_sum_km"],
        "max_distance_km": task_stats["max_distance_km"],
        "fastest_time_seconds": task_stats["fastest_time_seconds"],
        "slowest_time_seconds": task_stats.get("slowest_time_seconds"),
        "first_departure_at": _isoformat_or_none(task_stats["first_departure_at"]),
        "first_arrival_at": _isoformat_or_none(task_stats["first_arrival_at"]),
        "last_arrival_at": _isoformat_or_none(task_stats["last_arrival_at"]),
        "launch_validity": task_stats["launch_validity"],
        "distance_validity": task_stats["distance_validity"],
        "time_validity": task_stats["time_validity"],
        "stopped_validity": task_stats["stopped_validity"],
        "quality": task_stats["quality"],
    }


def _score_evaluations(
    task: Task,
    registered_pilot_count: int,
    evaluations: list[dict],
    penalties_by_pilot: dict[int, list[ScorePenalty]] | Event | None = None,
    event: Event | None = None,
    task_points: list[TaskPoint] | None = None,
) -> list[dict]:
    if event is None and penalties_by_pilot is not None and not isinstance(penalties_by_pilot, dict):
        event = penalties_by_pilot
        penalties_by_pilot = None
    penalties_by_pilot = penalties_by_pilot or {}
    formula = _build_formula(task, event)
    task_stats = _build_task_stats(task, registered_pilot_count, evaluations, formula)
    available_points = _points_weight(task_stats, formula)
    kmdiff = _calc_kmdiff(task_stats, evaluations, formula)

    # Compute leading coefficients from trackpoints when leading points are enabled
    leading_coefficients: dict[int, float] = {}
    if formula.get("use_leading_points", False) and available_points.get("leading", 0.0) > 0 and task_points:
        leading_coefficients = _compute_leading_coefficients(task_points, evaluations, formula)

    arrival_entries = sorted(
        [
            entry
            for entry in evaluations
            if entry["evaluation"]["status"] in {"ess", "goal"} and (entry["evaluation"]["goal_at"] or entry["evaluation"]["ess_at"]) is not None
        ],
        key=lambda entry: entry["evaluation"]["goal_at"] or entry["evaluation"]["ess_at"],
    )
    arrival_places = {
        (entry.get("pilot_id") or (entry.get("upload").pilot_id if entry.get("upload") is not None else None)): index
        for index, entry in enumerate(arrival_entries, start=1)
        if (entry.get("pilot_id") or (entry.get("upload").pilot_id if entry.get("upload") is not None else None)) is not None
    }
    first_arrival_at = task_stats["first_arrival_at"]
    decimals = formula.get("number_of_decimals_task_results", 2)

    scored: list[dict] = []
    for entry in evaluations:
        upload = entry.get("upload")
        pilot_id = entry.get("pilot_id") or (upload.pilot_id if upload is not None else None)
        if pilot_id is None:
            raise KeyError("pilot_id")
        evaluation = entry["evaluation"]
        distance_points = _pilot_distance_score(evaluation, available_points, task_stats, kmdiff, formula)
        speed_points = _pilot_speed_score(evaluation, available_points, task_stats, formula)
        if task_stats["goal"] == 0:
            speed_points = round(speed_points * formula["sspenalty"], 2)
        arrival_at = evaluation["goal_at"] or evaluation["ess_at"]
        arrival_delta_seconds = None
        if arrival_at is not None and first_arrival_at is not None:
            arrival_delta_seconds = max((arrival_at - first_arrival_at).total_seconds(), 0.0)
        arrival_points = _pilot_arrival_score(
            evaluation,
            available_points,
            task_stats,
            arrival_places.get(pilot_id),
            arrival_delta_seconds,
            formula,
        )
        if task_stats["goal"] == 0:
            arrival_points = round(arrival_points * formula["sspenalty"], 2)
        departure_points = _pilot_departure_score(evaluation, available_points, speed_points, task_stats, formula)

        # Leading points
        leading_points = _pilot_leading_score(pilot_id, leading_coefficients, available_points, formula, task_stats)

        raw_points = round(distance_points + speed_points + leading_points + arrival_points + departure_points, decimals)
        pilot_penalties = penalties_by_pilot.get(pilot_id, [])
        final_points = _apply_penalties(raw_points, pilot_penalties)
        final_points = round(final_points, decimals)
        details = dict(evaluation["details"])
        details["gap"] = {
            "formula": formula,
            "validity": {
                "launch": task_stats["launch_validity"],
                "distance": task_stats["distance_validity"],
                "time": task_stats["time_validity"],
                "stopped": task_stats["stopped_validity"],
                "overall": task_stats["quality"],
            },
            "available_points": available_points,
            "task_stats": _serialize_stats(task_stats),
            "awarded_points": {
                "distance": distance_points,
                "speed": speed_points,
                "leading": leading_points,
                "arrival": arrival_points,
                "departure": departure_points,
                "total": raw_points,
                "final": final_points,
            },
        }
        scored.append(
            {
                "task_id": task.id,
                "pilot_id": pilot_id,
                "upload_id": upload.id if upload is not None else None,
                "status": evaluation["status"],
                "distance_flown_km": evaluation["distance_flown_km"],
                "started_at": evaluation["started_at"],
                "ess_at": evaluation["ess_at"],
                "goal_at": evaluation["goal_at"],
                "elapsed_seconds": evaluation["elapsed_seconds"],
                "raw_score_points": raw_points,
                "score_points": final_points,
                "details_json": details,
            }
        )

    scored.sort(
        key=lambda result: (
            0 if result["status"] in COMPETITIVE_STATUSES else 1,
            -(result["raw_score_points"] or 0.0),
            STATUS_ORDER.get(result["status"], 99),
            result["elapsed_seconds"] or 10**9,
            -(result["distance_flown_km"] or 0.0),
        )
    )
    rank = 0
    for result in scored:
        if result["status"] in COMPETITIVE_STATUSES:
            rank += 1
            result["rank"] = rank
        else:
            result["rank"] = None
    return scored


def score_upload(session: Session, upload: IGCUpload) -> ScoreResult:
    rescore_task(session, upload.task_id)
    result = session.scalar(select(ScoreResult).where(ScoreResult.task_id == upload.task_id, ScoreResult.pilot_id == upload.pilot_id))
    if result is None:
        raise ValueError(f"Unable to score upload {upload.id} for task {upload.task_id}.")
    return result


def rescore_task(session: Session, task_id: int) -> list[ScoreResult]:
    task = session.get(Task, task_id)
    if task is None:
        return []
    event = session.get(Event, task.event_id)

    uploads = session.scalars(select(IGCUpload).where(IGCUpload.task_id == task_id).order_by(IGCUpload.uploaded_at)).all()
    uploads_by_id = {upload.id: upload for upload in uploads}
    uploads_by_pilot: dict[int, list[IGCUpload]] = {}
    for upload in reversed(uploads):
        uploads_by_pilot.setdefault(upload.pilot_id, []).append(upload)
    scoring_inputs = session.scalars(select(TaskScoringInput).where(TaskScoringInput.task_id == task_id)).all()
    scoring_input_by_pilot = {entry.pilot_id: entry for entry in scoring_inputs}
    penalties = session.scalars(
        select(ScorePenalty).where(ScorePenalty.task_id == task_id).order_by(ScorePenalty.pilot_id.asc(), ScorePenalty.position.asc(), ScorePenalty.id.asc())
    ).all()
    penalties_by_pilot: dict[int, list[ScorePenalty]] = {}
    for penalty in penalties:
        penalties_by_pilot.setdefault(penalty.pilot_id, []).append(penalty)

    task_points = session.scalars(select(TaskPoint).where(TaskPoint.task_id == task_id).order_by(TaskPoint.position)).all()
    event_pilot_ids = session.scalars(select(EventPilot.pilot_id).where(EventPilot.event_id == task.event_id).order_by(EventPilot.pilot_id.asc())).all()
    registered_pilot_count = len(event_pilot_ids)

    # Batch-load trackpoints only for explicitly selected uploads.
    selected_upload_ids: list[int] = []
    for pilot_id in event_pilot_ids:
        scoring_input = scoring_input_by_pilot.get(pilot_id)
        if (
            scoring_input is not None
            and scoring_input.selected_upload_id is not None
            and scoring_input.selected_upload_id in uploads_by_id
        ):
            selected_upload_ids.append(scoring_input.selected_upload_id)
    upload_ids = list(dict.fromkeys(selected_upload_ids))
    all_trackpoints = session.scalars(
        select(TrackPoint).where(TrackPoint.upload_id.in_(upload_ids)).order_by(TrackPoint.upload_id, TrackPoint.sequence)
    ).all() if upload_ids else []
    trackpoints_by_upload: dict[int, list[TrackPoint]] = {}
    for tp in all_trackpoints:
        trackpoints_by_upload.setdefault(tp.upload_id, []).append(tp)

    evaluations: list[dict] = []
    for pilot_id in event_pilot_ids:
        scoring_input = scoring_input_by_pilot.get(pilot_id)
        effective_upload_id = None
        if scoring_input is not None and scoring_input.selected_upload_id is not None:
            effective_upload_id = scoring_input.selected_upload_id
        if effective_upload_id is not None:
            upload = uploads_by_id.get(effective_upload_id)
            if upload is None or upload.pilot_id != pilot_id:
                continue
            trackpoints = trackpoints_by_upload.get(upload.id, [])
            evaluations.append(
                {
                    "pilot_id": pilot_id,
                    "upload": upload,
                    "evaluation": evaluate_task(task, task_points, trackpoints, event.timezone if event else None),
                    "_trackpoints": trackpoints,  # kept for leading coefficient computation
                }
            )
            continue
        if scoring_input is None:
            continue
        if scoring_input.status_override == "minimum_distance":
            evaluations.append({"pilot_id": pilot_id, "upload": None, "evaluation": _minimum_distance_evaluation(task, event)})
        elif scoring_input.status_override in {"did_not_fly", "absent"}:
            evaluations.append({"pilot_id": pilot_id, "upload": None, "evaluation": _blank_evaluation(scoring_input.status_override)})

    session.execute(text("DELETE FROM score_results WHERE task_id = :task_id"), {"task_id": task_id})
    session.flush()
    session.expire_all()

    scored_payloads = _score_evaluations(task, registered_pilot_count, evaluations, penalties_by_pilot, event, task_points=task_points)
    results: list[ScoreResult] = []
    for payload in scored_payloads:
        payload["result_state"] = "provisional"
        result = ScoreResult(**payload)
        session.add(result)
        results.append(result)
    session.flush()
    return results


def build_result_payload(session: Session, result: ScoreResult) -> dict:
    pilot = session.get(Pilot, result.pilot_id)
    pilot_name = f"{pilot.first_name} {pilot.last_name}" if pilot else "Unknown"
    return {
        "id": result.id,
        "task_id": result.task_id,
        "pilot_id": result.pilot_id,
        "upload_id": result.upload_id,
        "pilot_name": pilot_name,
        "competition_number": pilot.competition_number if pilot else None,
        "status": result.status,
        "rank": result.rank,
        "distance_flown_km": result.distance_flown_km,
        "started_at": result.started_at,
        "ess_at": result.ess_at,
        "goal_at": result.goal_at,
        "elapsed_seconds": result.elapsed_seconds,
        "raw_score_points": result.raw_score_points,
        "score_points": result.score_points,
        "details_json": result.details_json,
        "result_state": result.result_state,
    }
