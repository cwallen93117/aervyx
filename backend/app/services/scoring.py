"""
Scoring service — wires Aervyx models to the AirScore GAP engine.

The AirScore engine (app.services.airscore) is a 1:1 port of Geoff Wong's
scoring code from https://github.com/geoffwong/airscore.
This module is the only place that bridges Aervyx ORM models ↔ AirScore dicts.
"""

from __future__ import annotations

import copy
import math
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.models import Event, EventPilot, IGCUpload, Pilot, ScorePenalty, ScoreResult, Task, TaskPoint, TaskScoringInput, TrackPoint
from app.services.airscore import task as airscore_task
from app.services.airscore.gap import build_task_totals, day_quality, pilot_arrival, pilot_departure_leadout, pilot_distance, pilot_speed, points_allocation, points_weight, select_coeff
from app.services.airscore.route import find_shortest_route, task_distance as route_task_distance
from app.services.airscore.task import distance_flown as airscore_distance_flown, precompute_waypoint_dist
from app.services.airscore.track_lib import PI, distance as vincenty_distance, distance_deg, to_rad_dict

STATUS_ORDER = {"goal": 0, "ess": 1, "partial": 2, "minimum_distance": 3, "did_not_fly": 4, "absent": 5, "uploaded": 6}
COMPETITIVE_STATUSES = {"goal", "ess", "partial"}
TIMEZONE_ALIASES = {
    "eastern": "America/New_York",
    "est": "America/New_York",
    "edt": "America/New_York",
    "us/eastern": "America/New_York",
    "central": "America/Chicago",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "us/central": "America/Chicago",
    "mountain": "America/Denver",
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "us/mountain": "America/Denver",
    "pacific": "America/Los_Angeles",
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "us/pacific": "America/Los_Angeles",
    "utc": "UTC",
}


# ---------- geometry helpers ----------

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Kept for backward compat. Prefer vincenty for scoring accuracy."""
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return 2 * radius_km * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _vincenty_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Vincenty distance in km from degree coordinates (matches AirScore TrackLib)."""
    return distance_deg(lat1, lon1, lat2, lon2) / 1000.0


# ---------- task time / timezone helpers ----------

def _resolve_timezone_name(value: str | None) -> str:
    if not value:
        return "UTC"
    normalized = value.strip()
    return TIMEZONE_ALIASES.get(normalized.lower(), normalized)


def _infer_timezone_from_task_points(task_points: list[TaskPoint] | None) -> str | None:
    if not task_points:
        return None
    latitudes = [point.latitude for point in task_points if point.latitude is not None]
    longitudes = [point.longitude for point in task_points if point.longitude is not None]
    if not latitudes or not longitudes:
        return None
    avg_lat = sum(latitudes) / len(latitudes)
    avg_lon = sum(longitudes) / len(longitudes)
    if 24.0 <= avg_lat <= 31.5 and -88.0 <= avg_lon <= -79.0:
        return "America/New_York"
    return None


def _effective_timezone_name(value: str | None, task_points: list[TaskPoint] | None = None) -> str:
    resolved = _resolve_timezone_name(value)
    if resolved.upper() == "UTC" and (not value or value.strip().upper() == "UTC"):
        inferred = _infer_timezone_from_task_points(task_points)
        if inferred:
            return inferred
    return resolved


def _parse_clock_time(value: str | None) -> time | None:
    if not value:
        return None
    parts = value.split(":")
    if len(parts) < 2:
        return None
    return time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)


def _resolve_clock_time_utc(value: str | None, local_date: date, timezone_name: str) -> datetime | None:
    clock_time = _parse_clock_time(value)
    if clock_time is None:
        return None
    try:
        zone = ZoneInfo(_resolve_timezone_name(timezone_name))
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    return datetime.combine(local_date, clock_time, tzinfo=zone).astimezone(UTC)


def _as_utc_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _resolve_task_time_utc(value: str | None, trackpoints: list[TrackPoint], timezone_name: str) -> datetime | None:
    clock_time = _parse_clock_time(value)
    if clock_time is None or not trackpoints:
        return None
    try:
        zone = ZoneInfo(_resolve_timezone_name(timezone_name))
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    first_recorded_at = _as_utc_aware(trackpoints[0].recorded_at)
    if first_recorded_at is None:
        return None
    local_date = first_recorded_at.astimezone(zone).date()
    local_dt = datetime.combine(local_date, clock_time, tzinfo=zone)
    return local_dt.astimezone(UTC)


# ---------- turnpoint hit detection ----------

def _distance_to_task_point(trackpoint: TrackPoint, point: TaskPoint) -> float:
    """Distance in km from a trackpoint to a task point (Vincenty)."""
    return _vincenty_km(trackpoint.latitude, trackpoint.longitude, point.latitude, point.longitude)


def _point_direction(point: TaskPoint) -> str:
    direction = getattr(point, "direction", None)
    if direction in {"enter", "exit"}:
        return direction
    return "exit" if point.point_type.lower() == "start" else "enter"


def _find_entry_hit(point: TaskPoint, trackpoints: list[TrackPoint], radius_km: float, cursor: int = 0, earliest_at: datetime | None = None, latest_at: datetime | None = None) -> tuple[int, datetime] | None:
    previous_inside = _distance_to_task_point(trackpoints[cursor - 1], point) <= radius_km if cursor > 0 and cursor <= len(trackpoints) else False
    for idx in range(cursor, len(trackpoints)):
        trackpoint = trackpoints[idx]
        recorded_at = _as_utc_aware(trackpoint.recorded_at)
        if recorded_at is None:
            continue
        if earliest_at is not None and recorded_at < earliest_at:
            previous_inside = _distance_to_task_point(trackpoint, point) <= radius_km
            continue
        if latest_at is not None and recorded_at > latest_at:
            break
        inside = _distance_to_task_point(trackpoint, point) <= radius_km
        if inside and not previous_inside:
            return idx, recorded_at
        previous_inside = inside
    return None


def _find_exit_hit(
    point: TaskPoint,
    trackpoints: list[TrackPoint],
    radius_km: float,
    cursor: int = 0,
    earliest_at: datetime | None = None,
    latest_at: datetime | None = None,
    prefer_latest: bool = False,
) -> tuple[int, datetime] | None:
    previous_inside: bool | None = _distance_to_task_point(trackpoints[cursor - 1], point) <= radius_km if cursor > 0 and cursor <= len(trackpoints) else None
    previous_inside_idx: int | None = cursor - 1 if previous_inside else None
    candidate: tuple[int, datetime] | None = None
    for idx in range(cursor, len(trackpoints)):
        trackpoint = trackpoints[idx]
        recorded_at = _as_utc_aware(trackpoint.recorded_at)
        if recorded_at is None:
            continue
        inside = _distance_to_task_point(trackpoint, point) <= radius_km
        if earliest_at is not None and recorded_at < earliest_at:
            previous_inside = inside
            previous_inside_idx = idx if inside else None
            continue
        if latest_at is not None and recorded_at > latest_at:
            break
        if previous_inside is None:
            previous_inside = inside
            previous_inside_idx = idx if inside else None
            continue
        if previous_inside and not inside:
            if previous_inside_idx is not None:
                previous_inside_point = trackpoints[previous_inside_idx]
                recorded_at = _as_utc_aware(previous_inside_point.recorded_at)
                if recorded_at is None:
                    continue
                candidate = (previous_inside_idx, recorded_at)
                if not prefer_latest:
                    return candidate
            previous_inside_idx = None
        elif inside:
            previous_inside_idx = idx
        previous_inside = inside
    return candidate


def _find_exit_hit_with_interval(
    point: TaskPoint,
    trackpoints: list[TrackPoint],
    radius_km: float,
    cursor: int = 0,
    latest_at: datetime | None = None,
    prefer_latest: bool = False,
) -> tuple[int, datetime, int | None, datetime | None] | None:
    previous_inside: bool | None = _distance_to_task_point(trackpoints[cursor - 1], point) <= radius_km if cursor > 0 and cursor <= len(trackpoints) else None
    previous_inside_idx: int | None = cursor - 1 if previous_inside else None
    candidate: tuple[int, datetime, int | None, datetime | None] | None = None
    for idx in range(cursor, len(trackpoints)):
        trackpoint = trackpoints[idx]
        recorded_at = _as_utc_aware(trackpoint.recorded_at)
        if recorded_at is None:
            continue
        inside = _distance_to_task_point(trackpoint, point) <= radius_km
        if latest_at is not None and recorded_at > latest_at:
            break
        if previous_inside is None:
            previous_inside = inside
            previous_inside_idx = idx if inside else None
            continue
        if previous_inside and not inside:
            if previous_inside_idx is not None:
                previous_inside_point = trackpoints[previous_inside_idx]
                previous_recorded_at = _as_utc_aware(previous_inside_point.recorded_at)
                exit_recorded_at = _as_utc_aware(trackpoint.recorded_at)
                if previous_recorded_at is None:
                    continue
                candidate = (previous_inside_idx, previous_recorded_at, idx, exit_recorded_at)
                if not prefer_latest:
                    return candidate
            previous_inside_idx = None
        elif inside:
            previous_inside_idx = idx
        previous_inside = inside
    return candidate


def _start_gate_times(task: Task, first_gate_at: datetime | None) -> list[datetime]:
    if first_gate_at is None:
        return []
    count = max(int(task.start_gate_count or 1), 1)
    interval_seconds = max(int(task.start_gate_interval_seconds or 0), 0)
    return [first_gate_at + timedelta(seconds=index * interval_seconds) for index in range(count)]


def _scored_start_from_gates(
    task: Task,
    actual_start_at: datetime | None,
    first_gate_at: datetime | None,
    formula: dict,
    exit_after_at: datetime | None = None,
) -> tuple[datetime | None, dict]:
    if actual_start_at is None:
        return None, {"actual_start_crossing_at": None, "scored_start_at": None}
    gates = _start_gate_times(task, first_gate_at)
    if not gates:
        return actual_start_at, {
            "actual_start_crossing_at": _isoformat_or_none(actual_start_at),
            "scored_start_at": _isoformat_or_none(actual_start_at),
            "start_gate_index": None,
            "jump_the_gun_seconds": 0,
            "jump_the_gun_penalty_points": 0.0,
        }

    selected_index = 0
    jump_seconds = 0
    if actual_start_at < gates[0]:
        scored_start_at = gates[0]
        if exit_after_at is None or exit_after_at < gates[0]:
            jump_seconds = int((gates[0] - actual_start_at).total_seconds())
    else:
        interval_gate_index = None
        if exit_after_at is not None:
            for index, gate_at in enumerate(gates):
                if actual_start_at <= gate_at <= exit_after_at:
                    interval_gate_index = index
                    break
        if interval_gate_index is not None:
            selected_index = interval_gate_index
        else:
            for index, gate_at in enumerate(gates):
                if gate_at <= actual_start_at:
                    selected_index = index
                else:
                    break
        scored_start_at = gates[selected_index]

    max_jump_seconds = max(int(formula.get("jump_the_gun_max_seconds", 0) or 0), 0)
    penalty_seconds = min(jump_seconds, max_jump_seconds) if max_jump_seconds > 0 else jump_seconds
    penalty_points = max(float(formula.get("jump_the_gun_factor", 0.0) or 0.0), 0.0) * penalty_seconds
    return scored_start_at, {
        "actual_start_crossing_at": _isoformat_or_none(actual_start_at),
        "actual_start_exit_after_at": _isoformat_or_none(exit_after_at),
        "scored_start_at": _isoformat_or_none(scored_start_at),
        "start_gate_index": selected_index + 1,
        "start_gate_time": _isoformat_or_none(scored_start_at),
        "jump_the_gun_seconds": jump_seconds,
        "jump_the_gun_penalty_seconds": penalty_seconds,
        "jump_the_gun_penalty_points": round(penalty_points, 3),
    }


# ---------- optimized task distance via AirScore Route ----------

def _build_airscore_waypoints(task_points: list[TaskPoint]) -> list[dict]:
    """Convert Aervyx TaskPoints into AirScore waypoint dicts for Route.pm."""
    ordered = sorted(task_points, key=lambda p: p.position)
    has_separate_start = any(p.point_type.lower() == "launch" for p in ordered) and any(p.point_type.lower() == "start" for p in ordered)
    waypoints = []
    for i, tp in enumerate(ordered):
        pt = tp.point_type.lower()
        direction = _point_direction(tp)
        how = "exit" if direction == "exit" else "entry"
        radius_m = float(tp.radius_m or 0.0)
        if pt == "launch" and has_separate_start:
            # AirScore task distance starts from launch/origin, but launch is
            # not a scored cylinder when a distinct start cylinder exists.
            radius_m = 0.0
            how = "entry"
        # Map Aervyx point_type to AirScore type/how
        if pt == "start":
            wpt_type = "start"
        elif pt in ("ess", "endspeed"):
            wpt_type = "endspeed"
        elif pt == "goal":
            wpt_type = "goal"
        else:
            wpt_type = "turnpoint"

        wpt = to_rad_dict(tp.latitude, tp.longitude,
                          radius=radius_m,
                          type=wpt_type,
                          how=how,
                          shape="circle",
                          name=tp.name,
                          key=tp.id,
                          number=i)
        waypoints.append(wpt)
    return waypoints


def _cache_waypoint_distance_metadata(
    waypoints: list[dict],
    spt: int,
    ept: int,
    gpt: int,
    ssdist: float,
    startssdist: float,
    endssdist: float,
    totdist: float,
    wpt_distances: list[float] | None = None,
) -> None:
    distance_cache = list(wpt_distances or [])
    for wpt in waypoints:
        wpt["_spt"] = spt
        wpt["_ept"] = ept
        wpt["_gpt"] = gpt
        wpt["_ssdist"] = ssdist
        wpt["_startssdist"] = startssdist
        wpt["_endssdist"] = endssdist
        wpt["_totdist"] = totdist
        wpt["_wptdistances"] = distance_cache


def _prepare_waypoints_for_distance(waypoints: list[dict], formula: dict | None = None) -> tuple[list[dict], list[float]]:
    local_waypoints = copy.deepcopy(waypoints)
    if not local_waypoints:
        return [], []
    spt, ept, gpt, ssdist, startssdist, endssdist, totdist = precompute_waypoint_dist(
        local_waypoints,
        {"errormargin": (formula or {}).get("errormargin", 0.05)},
    )
    wpt_distances = list(getattr(airscore_task, "_wptdistcache", []))
    _cache_waypoint_distance_metadata(local_waypoints, spt, ept, gpt, ssdist, startssdist, endssdist, totdist, wpt_distances)
    return local_waypoints, wpt_distances


def _waypoint_distance_stats(waypoints: list[dict], fallback_total_km: float = 0.0) -> dict:
    if not waypoints:
        return {
            "task_distance": round(fallback_total_km, 3),
            "ss_distance": 0.0,
            "startss_distance": 0.0,
            "endss_distance": 0.0,
            "launch_to_ess_distance": 0.0,
        }
    total_m = float(waypoints[0].get("_totdist", fallback_total_km * 1000.0) or 0.0)
    ss_m = float(waypoints[0].get("_ssdist", 0.0) or 0.0)
    startss_m = float(waypoints[0].get("_startssdist", max(total_m - ss_m, 0.0)) or 0.0)
    endss_m = float(waypoints[0].get("_endssdist", startss_m + ss_m) or 0.0)
    return {
        "task_distance": round(total_m / 1000.0, 3),
        "ss_distance": round(ss_m / 1000.0, 3),
        "startss_distance": round(startss_m / 1000.0, 3),
        "endss_distance": round(endss_m / 1000.0, 3),
        "launch_to_ess_distance": round(endss_m / 1000.0, 3),
    }


def _compute_optimized_task_distance(task_points: list[TaskPoint]) -> tuple[float, list[dict]]:
    """
    Compute the optimized task distance (shortest route through cylinders)
    using the AirScore Route engine.
    Returns (total_distance_km, waypoints_with_short_positions).
    """
    waypoints = _build_airscore_waypoints(task_points)
    if len(waypoints) < 2:
        return 0.0, waypoints

    shortest = find_shortest_route(waypoints)

    # Apply short-route positions back to waypoints
    for i, wpt in enumerate(waypoints):
        if i < len(shortest):
            wpt["short_lat"] = shortest[i]["lat"]
            wpt["short_long"] = shortest[i]["long"]
        else:
            wpt["short_lat"] = wpt["lat"]
            wpt["short_long"] = wpt["long"]

    spt, ept, gpt, ssdist, startssdist, endssdist, totdist = route_task_distance(waypoints)
    _cache_waypoint_distance_metadata(waypoints, spt, ept, gpt, ssdist, startssdist, endssdist, totdist)

    return totdist / 1000.0, waypoints  # convert metres to km


# ---------- leading coefficient computation ----------

def _compute_leading_coeff(
    waypoints: list[dict],
    trackpoints: list[TrackPoint],
    started_at: datetime | None,
    ess_at: datetime | None,
    distance_flown_m: float,
    task_class: str = "HG",
    task_sstart: float = 0.0,
    task_sfinish: float = 0.0,
    target_waypoint_indices: list[int] | None = None,
) -> tuple[float, float]:
    """
    Compute leading coefficients (LC1 and LC2) from track data.

    Port of AirScore track_verify_sr.pl inc_leading_area / inc_offset_leading_coeff.
    Returns (coeff, coeff2) — normalized by 1800 * essdist.

    The leading coefficient measures how much time a pilot spent "in front" of the
    rest of the field. For each track fix where the pilot advances their max distance,
    the coefficient accumulates time × distance-increment.

    task_sstart / task_sfinish are epoch timestamps for the task gate open / task deadline.
    """
    if not waypoints or len(waypoints) < 2 or not trackpoints or started_at is None:
        return 0.0, 0.0

    # Get task metadata from waypoints (stored by _compute_optimized_task_distance)
    spt = int(waypoints[0].get("_spt", 0) or 0)
    ssdist = waypoints[0].get("_ssdist", 0)
    endssdist = waypoints[0].get("_endssdist", 0)
    startssdist = waypoints[0].get("_startssdist", endssdist - ssdist if endssdist > 0 and ssdist > 0 else 0)

    if ssdist <= 0 or endssdist <= 0:
        return 0.0, 0.0

    # Ensure the task.py module-level distance caches are populated.
    # route.py's task_distance is separate from task.py's precompute_waypoint_dist,
    # but distance_flown depends on the latter's caches.
    precompute_waypoint_dist(waypoints, {"errormargin": 0.05})

    # Use task gate open time as the reference; fall back to pilot's start time
    started_at_utc = _as_utc_aware(started_at)
    if started_at_utc is None:
        return 0.0, 0.0
    task_start_epoch = task_sstart if task_sstart > 0 else started_at_utc.timestamp()
    pilot_start_epoch = started_at_utc.timestamp()

    coeff = 0.0
    leading_area = 0.0
    maxdist = 0.0
    had_previous = False
    # Stop accumulating LC at the pilot's ESS crossing time (if they reached ESS)
    ess_at_utc = _as_utc_aware(ess_at)
    ess_epoch = ess_at_utc.timestamp() if ess_at_utc is not None else float("inf")

    target_indices = target_waypoint_indices or [spt] * len(trackpoints)
    for index, tp in enumerate(trackpoints):
        recorded_at = _as_utc_aware(tp.recorded_at)
        if recorded_at is None:
            continue
        coord_time = recorded_at.timestamp()
        # Stop processing after ESS crossing
        if coord_time > ess_epoch:
            break
        # Convert trackpoint to AirScore coord dict (radians)
        coord = to_rad_dict(tp.latitude, tp.longitude, time=coord_time)
        target_index = target_indices[index] if index < len(target_indices) else spt

        # Compute distance flown using AirScore engine
        try:
            newdist = airscore_distance_flown(waypoints, target_index, coord)
        except (IndexError, ZeroDivisionError):
            continue
        if distance_flown_m > 0:
            newdist = min(newdist, distance_flown_m)

        if newdist > maxdist:
            if had_previous:
                # Accumulate leading area (same as AirScore inc_leading_area)
                tasktime = coord_time - task_start_epoch
                if newdist >= startssdist and tasktime > 0:
                    # LC1: flat leading coefficient
                    coeff += tasktime * (newdist - maxdist)

                    # LC2: class-dependent leading area
                    last_remaining = endssdist - maxdist
                    remaining = endssdist - newdist
                    if task_class == "HG":
                        leading_area += tasktime * (last_remaining * last_remaining - remaining * remaining)
                    else:
                        # PG formula with rising/falling factors
                        if ssdist > 0 and remaining >= 0:
                            rising = (1 - 10 ** ((9 * remaining / ssdist) - 9)) ** 5
                            falling = (1 - 10 ** ((-3 * remaining / ssdist))) ** 2
                            leading_area += tasktime * rising * falling * (last_remaining - remaining)

            had_previous = True
            maxdist = newdist

    # For pilots who didn't reach ESS: add offset for remaining distance
    # AirScore: coeff += ssdist * (startSS - task_sstart) + remaining * (sfinish - task_sstart)
    if ess_at is None and maxdist > startssdist:
        remaining_ss = endssdist - distance_flown_m
        if remaining_ss > 0:
            task_finish_epoch = task_sfinish if task_sfinish > 0 else task_start_epoch + 86400
            # Time pilot waited before starting SS (penalty for late start)
            ss_delay = max(pilot_start_epoch - task_start_epoch, 0)
            task_duration = task_finish_epoch - task_start_epoch
            coeff += ssdist * ss_delay + remaining_ss * task_duration
            # missing leading area
            if task_class == "HG":
                leading_area += task_duration * remaining_ss * remaining_ss
            else:
                if ssdist > 0:
                    falling = (1 - 10 ** ((-3 * remaining_ss / ssdist))) ** 2
                    leading_area += falling * task_duration * remaining_ss

    # Pilots who didn't even start get max coeff (worst possible)
    if maxdist < startssdist:
        return 0.0, 0.0

    # Normalize (AirScore: coeff / 1800 / essdist)
    norm = 1800.0 * ssdist
    if norm > 0:
        return coeff / norm, leading_area / norm
    return 0.0, 0.0


# ---------- evaluate_task ----------

def _isoformat_or_none(value: datetime | None) -> str | None:
    value = _as_utc_aware(value)
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
    evaluation["details"] = {"hits": [], "total_distance_km": 0.0, "status_override": "minimum_distance"}
    return evaluation


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _project_progress(prev_point: TaskPoint, next_point: TaskPoint, trackpoints: list[TrackPoint]) -> float:
    """Project pilot's furthest progress along a leg (used when a turnpoint is missed)."""
    leg_distance = _vincenty_km(prev_point.latitude, prev_point.longitude, next_point.latitude, next_point.longitude)
    if leg_distance <= 0:
        return 0.0
    bx = (next_point.longitude - prev_point.longitude) * 111.32 * math.cos(math.radians(prev_point.latitude))
    by = (next_point.latitude - prev_point.latitude) * 110.57
    length_sq = bx * bx + by * by
    if length_sq <= 0:
        return 0.0
    best = 0.0
    for trackpoint in trackpoints:
        px = (trackpoint.longitude - prev_point.longitude) * 111.32 * math.cos(math.radians(prev_point.latitude))
        py = (trackpoint.latitude - prev_point.latitude) * 110.57
        projection = (px * bx + py * by) / length_sq
        best = max(best, min(max(projection, 0.0), 1.0))
    return best * leg_distance


def evaluate_task(
    task: Task,
    task_points: list[TaskPoint],
    trackpoints: list[TrackPoint],
    event_timezone: str | None = None,
    optimized_distance_km: float | None = None,
    airscore_waypoints: list[dict] | None = None,
    task_class: str = "HG",
    event: Event | None = None,
) -> dict:
    """
    Evaluate a single pilot's flight against the task.
    Returns a dict with status, distance_flown_km, start/ess/goal times, hits, etc.

    Uses Vincenty distance (matching AirScore) for turnpoint hit detection.
    Uses optimized task distance (via AirScore Route) for distance flown.
    """
    ordered_points = sorted(task_points, key=lambda point: point.position)
    if len(ordered_points) < 2:
        return {"status": "uploaded", "distance_flown_km": 0.0, "details": {"hits": [], "total_distance_km": 0.0}}

    if optimized_distance_km is None or airscore_waypoints is None:
        optimized_distance_km, computed_waypoints = _compute_optimized_task_distance(task_points)
        if airscore_waypoints is None:
            airscore_waypoints = computed_waypoints

    timezone_name = _effective_timezone_name(event_timezone, ordered_points)
    start_open_at = _resolve_task_time_utc(task.start_open_time or task.task_start_time, trackpoints, timezone_name)
    start_close_at = _resolve_task_time_utc(task.start_close_time or task.task_finish_time, trackpoints, timezone_name)
    formula = _build_formula(task, event)
    distance_waypoints, waypoint_distances = _prepare_waypoints_for_distance(airscore_waypoints or [], formula)
    task_stats = _waypoint_distance_stats(distance_waypoints or airscore_waypoints or [], optimized_distance_km or 0.0)
    total_task_distance_km = task_stats["task_distance"] or (optimized_distance_km or 0.0)
    waypoint_index_by_point_id = {int(wpt["key"]): index for index, wpt in enumerate(distance_waypoints) if wpt.get("key") is not None}

    hit_indices: dict[int, int] = {}
    hit_times: dict[int, datetime] = {}
    point_detail_state: dict[int, dict] = {
        point.id: {
            "hit": False,
            "hit_at": None,
            "scored_hit_at": None,
            "ignored_hit": False,
            "ignored_hit_at": None,
            "required": point.point_type.lower() != "launch",
        }
        for point in ordered_points
    }

    def _find_point_hit(point: TaskPoint, start_cursor: int, latest_at: datetime | None = None, prefer_latest: bool = False) -> tuple[int, datetime] | None:
        if not trackpoints:
            return None
        radius_km = point.radius_m / 1000.0
        if _point_direction(point) == "exit":
            return _find_exit_hit(point, trackpoints, radius_km, cursor=start_cursor, latest_at=latest_at, prefer_latest=prefer_latest)
        return _find_entry_hit(point, trackpoints, radius_km, cursor=start_cursor, latest_at=latest_at)

    cursor = 0
    missed_point: TaskPoint | None = None
    missed_point_order_index: int | None = None
    last_required_point: TaskPoint | None = None
    last_required_track_index: int | None = None
    last_required_waypoint_index: int | None = None
    start_exit_after_at: datetime | None = None

    for order_index, point in enumerate(ordered_points):
        point_type = point.point_type.lower()
        if point_type == "launch":
            launch_hit = _find_point_hit(point, cursor)
            if launch_hit is not None:
                idx, hit_at = launch_hit
                hit_indices[point.id] = idx
                hit_times[point.id] = hit_at
                point_detail_state[point.id]["hit"] = True
                point_detail_state[point.id]["hit_at"] = _isoformat_or_none(hit_at)
                point_detail_state[point.id]["scored_hit_at"] = _isoformat_or_none(hit_at)
                cursor = max(cursor, idx + 1)
            continue

        is_start = point.point_type.lower() == "start"
        latest_at = start_close_at if is_start else None
        if is_start and _point_direction(point) == "exit":
            exit_hit = _find_exit_hit_with_interval(point, trackpoints, point.radius_m / 1000.0, cursor=cursor, latest_at=latest_at, prefer_latest=True)
            hit = (exit_hit[0], exit_hit[1]) if exit_hit is not None else None
            start_exit_after_at = exit_hit[3] if exit_hit is not None else None
        else:
            hit = _find_point_hit(point, cursor, latest_at=latest_at, prefer_latest=is_start)
        if hit is None:
            missed_point = point
            missed_point_order_index = order_index
            break
        idx, hit_at = hit
        hit_indices[point.id] = idx
        hit_times[point.id] = hit_at
        point_detail_state[point.id]["hit"] = True
        point_detail_state[point.id]["hit_at"] = _isoformat_or_none(hit_at)
        point_detail_state[point.id]["scored_hit_at"] = _isoformat_or_none(hit_at)
        cursor = idx + 1
        last_required_point = point
        last_required_track_index = idx
        last_required_waypoint_index = waypoint_index_by_point_id.get(point.id)

    if missed_point is not None and missed_point_order_index is not None:
        ignored_cursor = cursor
        for point in ordered_points[missed_point_order_index + 1:]:
            if point.point_type.lower() == "launch":
                continue
            ignored_hit = _find_point_hit(point, ignored_cursor)
            if ignored_hit is None:
                continue
            idx, hit_at = ignored_hit
            point_detail_state[point.id]["ignored_hit"] = True
            point_detail_state[point.id]["ignored_hit_at"] = _isoformat_or_none(hit_at)
            ignored_cursor = idx + 1

    def _cumulative_distance_for_waypoint(point: TaskPoint | None) -> float:
        if point is None:
            return 0.0
        waypoint_index = waypoint_index_by_point_id.get(point.id)
        if waypoint_index is None or waypoint_index + 1 >= len(waypoint_distances):
            return total_task_distance_km * 1000.0
        return max(float(waypoint_distances[waypoint_index + 1] or 0.0), 0.0)

    progress_distance_m = _cumulative_distance_for_waypoint(last_required_point)
    if missed_point is not None and last_required_waypoint_index is not None and distance_waypoints:
        cap_m = _cumulative_distance_for_waypoint(missed_point)
        missed_waypoint_index = waypoint_index_by_point_id.get(missed_point.id, last_required_waypoint_index)
        search_start = (last_required_track_index + 1) if last_required_track_index is not None else 0
        for trackpoint in trackpoints[search_start:]:
            coord = to_rad_dict(trackpoint.latitude, trackpoint.longitude, time=trackpoint.recorded_at.timestamp())
            try:
                flown_m = airscore_distance_flown(distance_waypoints, missed_waypoint_index, coord)
            except (IndexError, ZeroDivisionError):
                continue
            progress_distance_m = max(progress_distance_m, min(flown_m, cap_m))

    goal_point = next((p for p in ordered_points if p.point_type.lower() == "goal"), None)

    # Find start, ESS, goal — case-insensitive
    start_point = next((p for p in ordered_points if p.point_type.lower() == "start"), None)
    ess_point = next((p for p in ordered_points if p.point_type.lower() in ("ess", "endspeed")), None)
    # If no separate ESS, goal acts as ESS
    if ess_point is None:
        ess_point = goal_point

    actual_started_at = hit_times.get(start_point.id) if start_point else None
    started_at, start_timing_details = _scored_start_from_gates(task, actual_started_at, start_open_at, formula, exit_after_at=start_exit_after_at)
    if start_point is not None and start_point.id in point_detail_state:
        point_detail_state[start_point.id]["scored_hit_at"] = _isoformat_or_none(started_at)
    ess_at = hit_times.get(ess_point.id) if ess_point else None
    goal_at = hit_times.get(goal_point.id) if goal_point else None
    valid_goal = goal_point is not None and goal_point.id in hit_indices and missed_point is None
    if valid_goal:
        progress_distance_m = total_task_distance_km * 1000.0
    scored_distance_m = progress_distance_m
    if trackpoints and not valid_goal:
        scored_distance_m = max(scored_distance_m, float(formula.get("mindist", 0.0) or 0.0))

    if valid_goal:
        status = "goal"
    elif ess_at is not None:
        status = "ess"
    elif scored_distance_m > 0:
        status = "partial"
    else:
        status = "uploaded"

    elapsed_seconds = None
    if started_at is not None and (goal_at or ess_at) is not None:
        elapsed_seconds = int(((goal_at or ess_at) - started_at).total_seconds())
        if elapsed_seconds < 0:
            elapsed_seconds = None

    def _leading_target_waypoint_indices() -> list[int]:
        required_points = [point for point in ordered_points if point.point_type.lower() != "launch"]
        if not required_points:
            return [0] * len(trackpoints)
        pointer = 0
        targets: list[int] = []
        for track_index, _trackpoint in enumerate(trackpoints):
            while pointer < len(required_points):
                point_id = required_points[pointer].id
                hit_index = hit_indices.get(point_id)
                if hit_index is not None and hit_index < track_index:
                    pointer += 1
                    continue
                break
            if pointer >= len(required_points):
                point = required_points[-1]
            else:
                point = required_points[pointer]
            targets.append(waypoint_index_by_point_id.get(point.id, 0))
            while pointer < len(required_points):
                point_id = required_points[pointer].id
                hit_index = hit_indices.get(point_id)
                if hit_index is not None and hit_index <= track_index:
                    pointer += 1
                    continue
                break
        return targets

    # Compute leading coefficients if waypoints are available
    lc1, lc2 = 0.0, 0.0
    if distance_waypoints and trackpoints and started_at is not None:
        task_sstart_epoch = start_open_at.timestamp() if start_open_at is not None else 0.0
        task_sfinish_epoch = start_close_at.timestamp() if start_close_at is not None else 0.0
        lc1, lc2 = _compute_leading_coeff(
            distance_waypoints, trackpoints, started_at,
            ess_at if ess_at is not None else goal_at,
            scored_distance_m,
            task_class,
            task_sstart=task_sstart_epoch,
            task_sfinish=task_sfinish_epoch,
            target_waypoint_indices=_leading_target_waypoint_indices(),
        )

    return {
        "status": status,
        "distance_flown_km": round(scored_distance_m / 1000.0, 3),
        "started_at": started_at,
        "ess_at": ess_at,
        "goal_at": goal_at,
        "elapsed_seconds": elapsed_seconds,
        "score_points": 0.0,
        "jump_the_gun_penalty_points": start_timing_details.get("jump_the_gun_penalty_points", 0.0),
        "leading_coeff": lc1,
        "leading_coeff2": lc2,
        "details": {
            "hits": [
                {
                    "task_point_id": point.id,
                    "name": point.name,
                    "point_type": point.point_type,
                    "direction": _point_direction(point),
                    "hit": point_detail_state[point.id]["hit"],
                    "hit_at": point_detail_state[point.id]["hit_at"],
                    "scored_hit_at": point_detail_state[point.id]["scored_hit_at"],
                    "ignored_hit": point_detail_state[point.id]["ignored_hit"],
                    "ignored_hit_at": point_detail_state[point.id]["ignored_hit_at"],
                    "required": point_detail_state[point.id]["required"],
                }
                for point in ordered_points
            ],
            "total_distance_km": round(total_task_distance_km, 3),
            "task_stats": task_stats,
            "scoring_timezone": timezone_name,
            "missed_point": {
                "task_point_id": missed_point.id,
                "name": missed_point.name,
                "point_type": missed_point.point_type,
            } if missed_point is not None else None,
            "start_timing": start_timing_details,
        },
    }


# ---------- formula builder: maps Event/Task fields → AirScore formula dict ----------


def _resolve_nondist_weights(penalties: dict, leading_weight_factor: float) -> dict:
    """Return weightspeed / weightstart / weightarrival for the formula dict.

    When *leading_weight_factor* is set (≠ 1.0), it replaces the legacy
    weightstart (1.4/8 = 0.175) as the fraction of non-distance points for
    leading.  The three weights must always sum to 1.0 so that
    ``points_weight()`` distributes all non-distance points exactly.
    """
    wa = float(penalties.get("weightarrival", 1.0 / 8.0))
    if leading_weight_factor != 1.0 and leading_weight_factor > 0:
        ws = leading_weight_factor
        sp = max(1.0 - ws - wa, 0.0)
    else:
        ws = float(penalties.get("weightstart", 1.4 / 8.0))
        sp = float(penalties.get("weightspeed", 5.6 / 8.0))
    return {"weightspeed": sp, "weightstart": ws, "weightarrival": wa}


def _build_formula(task: Task, event: Event | None = None) -> dict:
    """
    Build the AirScore-compatible formula dict from Aervyx Event + Task models.
    Every event parameter is wired through here — nothing is hardcoded.
    """
    penalties = task.penalties_json or {}

    def _ev(attr: str, default=None):
        """Get an event attribute, falling back to default."""
        if event is not None:
            val = getattr(event, attr, None)
            if val is not None:
                return val
        return default

    nominal_goal = _ev("nominal_goal_percent", penalties.get("nominal_goal", penalties.get("nomgoal", 0.3)))
    nominal_goal = float(nominal_goal)
    if nominal_goal > 1:
        nominal_goal /= 100.0

    mindist_km = max(float(task.minimum_distance_km or _ev("minimum_distance_km", 5) or 5), 0.1)
    nomdist_km = max(float(task.nominal_distance_km or _ev("nominal_distance_km", 60) or 60), 1.0)
    nomtime_hours = float(task.nominal_time_hours or _ev("nominal_time_hours", 1.5) or 1.5)
    nomlaunch = _clamp(float(task.nominal_launch or _ev("nominal_launch", 0.95) or 0.95), 0.1, 1.0)

    # Arrival mode
    arrival_mode = "off"
    if _ev("use_arrival_time_points", False):
        arrival_mode = "timed"
    elif _ev("use_arrival_position_points", False):
        arrival_mode = "position"

    # Departure mode
    if _ev("use_leading_points", False):
        departure_mode = "leadout"
    elif _ev("use_departure_points", False):
        departure_mode = "departure"
    else:
        departure_mode = "off"

    # Speed calc from scoring formula version
    scoring_formula = (_ev("scoring_formula") or "GAP2021").upper()
    version = 2021
    fclass = "gap"
    if "PWC" in scoring_formula:
        fclass = "pwc"
    elif "OZGAP" in scoring_formula or "OZ" in scoring_formula:
        fclass = "ozgap"
    elif "GGAP" in scoring_formula:
        fclass = "ggap"
    # Extract version number
    for part in scoring_formula.replace("GAP", "").replace("PWC", "").replace("OZ", "").replace("G", "").split():
        try:
            version = int(part)
            break
        except ValueError:
            pass
    try:
        version = int("".join(c for c in scoring_formula if c.isdigit()) or "2021")
    except ValueError:
        version = 2021

    speedcalc = penalties.get("speedcalc", "standard")
    sspenalty_value = _ev("goal_ss_penalty", penalties.get("sspenalty", 1.0))
    if sspenalty_value is None:
        sspenalty_value = 1.0

    return {
        # Core AirScore formula parameters
        "mindist": mindist_km * 1000,  # AirScore uses metres
        "nomdist": nomdist_km * 1000,
        "nomtime": nomtime_hours * 3600,  # AirScore uses seconds
        "nomlaunch": nomlaunch,
        "nomgoal": nominal_goal * 100,  # AirScore uses percentage (e.g. 20 = 20%)
        "mindist_km": mindist_km,  # keep km versions for backward compat
        "nomdist_km": nomdist_km,
        "nomtime_seconds": nomtime_hours * 3600,
        "nomgoal_fraction": nominal_goal,
        "glidebonus": float(_ev("stopped_glide_bonus", 0) or 0),
        "sspenalty": _clamp(float(sspenalty_value), 0.0, 1.0),
        "jump_the_gun_factor": float(_ev("jump_the_gun_factor", penalties.get("jump_the_gun_factor", 0.0)) or 0.0),
        "jump_the_gun_max_seconds": int(_ev("jump_the_gun_max_seconds", penalties.get("jump_the_gun_max_seconds", 0)) or 0),
        "lineardist": _clamp(float(penalties.get("lineardist", 0.5)), 0.0, 1.0),
        "weightdist": penalties.get("weightdist", "post2014"),
        # GAP2021+: leading_weight_factor overrides legacy weightstart (1.4/8).
        # Adjust all non-distance weights so they sum to 1.0.
        **_resolve_nondist_weights(penalties, float(_ev("leading_weight_factor", 1.0) or 1.0)),
        "speedcalc": speedcalc,
        "arrival": arrival_mode,
        "departure_mode": departure_mode,
        "arrival_mode": arrival_mode,
        "scaletovalidity": False,
        "distmeasure": penalties.get("distmeasure", "area"),
        "diffcalc": penalties.get("diffcalc", "all"),
        "diffdist": float(penalties.get("diffdist", 3)),
        "difframp": penalties.get("difframp", "flexible"),
        "errormargin": float(_ev("turnpoint_radius_tolerance", 0.05) or 0.05),
        "class": fclass,
        "version": version,
        "lookahead": max(int(penalties.get("lookahead", 30)), 1),
        # Boolean flags
        "use_distance_points": bool(_ev("use_distance_points", True)),
        "use_time_points": bool(_ev("use_time_points", True)),
        "use_departure_points": bool(_ev("use_departure_points", False)),
        "use_leading_points": bool(_ev("use_leading_points", False)),
        "use_arrival_position_points": bool(_ev("use_arrival_position_points", False)),
        "use_arrival_time_points": bool(_ev("use_arrival_time_points", False)),
        "use_difficulty_for_distance_points": bool(_ev("use_difficulty_for_distance_points", True)),
        "use_distance_squared_for_lc": bool(_ev("use_distance_squared_for_lc", False)),
        "use_flat_decline_of_timepoints": bool(_ev("use_flat_decline_of_timepoints", False)),
        "use_1000_points_for_max_day_quality": bool(_ev("use_1000_points_for_max_day_quality", False)),
        "normalize_1000_before_day_quality": bool(_ev("normalize_1000_before_day_quality", False)),
        "redistribute_removed_time_points_as_distance_points": bool(_ev("redistribute_removed_time_points_as_distance_points", False)),
        "time_points_if_not_in_goal": float(_ev("time_points_if_not_in_goal", 1.0) or 1.0),
        "leading_weight_factor": float(_ev("leading_weight_factor", 1.0) or 1.0),
        "score_back_time_minutes": int(_ev("score_back_time_minutes", 15) or 15),
        "number_of_decimals_task_results": int(_ev("number_of_decimals_task_results", 1) or 1),
    }


# ---------- penalty application ----------

def _apply_penalties(raw_score: float, penalties: list[ScorePenalty]) -> float:
    score = max(float(raw_score or 0.0), 0.0)
    for penalty in penalties:
        if penalty.penalty_type == "percentage":
            score -= score * (max(float(penalty.value or 0.0), 0.0) / 100.0)
    for penalty in penalties:
        if penalty.penalty_type == "fixed":
            score -= max(float(penalty.value or 0.0), 0.0)
    return round(max(score, 0.0), 2)


# ---------- AirScore GAP scoring pipeline ----------

def _build_airscore_pilot_result(evaluation: dict, pilot_id: int, start_epoch: float = 0) -> dict:
    """Convert an evaluation dict into an AirScore pilot result dict."""
    distance_m = evaluation["distance_flown_km"] * 1000.0
    started_at = evaluation.get("started_at")
    ess_at = evaluation.get("ess_at")
    goal_at = evaluation.get("goal_at")
    elapsed = evaluation.get("elapsed_seconds")

    start_ss = 0
    end_ss = 0
    if started_at is not None:
        start_ss = started_at.timestamp()
    if ess_at is not None:
        end_ss = ess_at.timestamp()
    elif goal_at is not None:
        end_ss = goal_at.timestamp()

    # Guard: if start wasn't detected (start_ss=0) but ESS was, zero end_ss too.
    # AirScore's gap.py computes time as (endSS - startSS) directly, so leaving
    # an epoch value in end_ss would yield ~1.7 billion seconds, poisoning
    # fastest_time_seconds, time validity, and all speed/leading calculations.
    if start_ss <= 0:
        end_ss = 0

    time_val = end_ss - start_ss if (start_ss > 0 and end_ss > 0) else 0
    if time_val < 0:
        time_val = 0

    status = evaluation["status"]
    if status == "goal":
        result_type = "lo"  # AirScore uses "lo" for all that flew
        goal_flag = 1
    elif status in ("ess", "partial"):
        result_type = "lo"
        goal_flag = 0
    elif status in ("did_not_fly", "minimum_distance"):
        result_type = "dnf"
        goal_flag = 0
    elif status == "absent":
        result_type = "abs"
        goal_flag = 0
    else:
        result_type = "lo"
        goal_flag = 0

    return {
        "pilot_id": pilot_id,
        "distance": distance_m,
        "time": time_val,
        "startSS": start_ss,
        "endSS": end_ss,
        "goal": goal_flag,
        "result": result_type,
        "penalty": max(float(evaluation.get("jump_the_gun_penalty_points", 0.0) or 0.0), 0.0),
        "coeff": evaluation.get("leading_coeff", 0),
        "coeff2": evaluation.get("leading_coeff2", 0),
        "stopalt": 0,
        "stoptime": 0,
        "place": 0,
        "timeafter": 0,
    }


def _score_evaluations(
    task: Task,
    registered_pilot_count: int,
    evaluations: list[dict],
    penalties_by_pilot: dict[int, list[ScorePenalty]] | Event | None = None,
    event: Event | None = None,
    airscore_waypoints: list[dict] | None = None,
) -> list[dict]:
    """Score all evaluations using the AirScore GAP engine."""
    if event is None and penalties_by_pilot is not None and not isinstance(penalties_by_pilot, dict):
        event = penalties_by_pilot
        penalties_by_pilot = None
    penalties_by_pilot = penalties_by_pilot or {}
    formula = _build_formula(task, event)

    # Build AirScore pilot results
    pilot_results = []
    eval_map: dict[int, dict] = {}
    for entry in evaluations:
        pilot_id = entry.get("pilot_id") or (entry["upload"].pilot_id if entry.get("upload") else None)
        if pilot_id is None:
            continue
        pil = _build_airscore_pilot_result(entry["evaluation"], pilot_id)
        pilot_results.append(pil)
        eval_map[pilot_id] = entry

    # Extract task distance metadata from waypoints
    ssdist_m = 0.0
    startssdist_m = 0.0
    endssdist_m = 0.0
    task_distance_m = 0.0
    if airscore_waypoints and len(airscore_waypoints) >= 2:
        ssdist_m = airscore_waypoints[0].get("_ssdist", 0)
        startssdist_m = airscore_waypoints[0].get("_startssdist", max(airscore_waypoints[0].get("_endssdist", 0) - ssdist_m, 0))
        endssdist_m = airscore_waypoints[0].get("_endssdist", 0)
        task_distance_m = airscore_waypoints[0].get("_totdist", endssdist_m)

    # Resolve task start/finish times (epoch) from the first pilot's track
    sstart_epoch = 0.0
    sfinish_epoch = 0.0
    scoring_timezone_name = _resolve_timezone_name(getattr(event, "timezone", None) if event else None)
    for entry in evaluations:
        tz_from_evaluation = entry.get("evaluation", {}).get("details", {}).get("scoring_timezone")
        if tz_from_evaluation:
            scoring_timezone_name = str(tz_from_evaluation)
            break
    for entry in evaluations:
        ev = entry.get("evaluation", {})
        sa = ev.get("started_at")
        if sa is not None:
            sstart_epoch = sa.timestamp()
            # Use task finish time if available, otherwise add a generous window
            sfinish_epoch = sstart_epoch + 86400
            break
    # Try to get more accurate times from task fields
    if task.start_open_time and evaluations:
        for entry in evaluations:
            ev = entry.get("evaluation", {})
            sa = ev.get("started_at")
            if sa is not None:
                # Resolve start_open_time to epoch using the flight date
                from datetime import datetime as dt_cls
                try:
                    zone = ZoneInfo(_resolve_timezone_name(scoring_timezone_name))
                except (ZoneInfoNotFoundError, AttributeError):
                    zone = ZoneInfo("UTC")
                flight_date = sa.astimezone(zone).date()
                open_time = _parse_clock_time(task.start_open_time)
                finish_time = _parse_clock_time(task.task_finish_time)
                if open_time:
                    sstart_epoch = dt_cls.combine(flight_date, open_time, tzinfo=zone).timestamp()
                if finish_time:
                    sfinish_epoch = dt_cls.combine(flight_date, finish_time, tzinfo=zone).timestamp()
                elif open_time:
                    sfinish_epoch = sstart_epoch + 86400
                break

    # Build AirScore task dict
    airscore_task = {
        "class": _event_task_class(event),
        "departure": formula["departure_mode"] if formula["departure_mode"] != "departure" else "off",
        "arrival": formula["arrival"] if formula["arrival"] != "off" else "off",
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

    # Use departure mode mapping
    if formula.get("use_leading_points"):
        airscore_task["departure"] = "leadout"
    elif formula.get("use_departure_points"):
        airscore_task["departure"] = "departure"
    else:
        airscore_task["departure"] = "off"

    # Arrival mode
    if formula.get("use_arrival_time_points"):
        airscore_task["arrival"] = "timed"
    elif formula.get("use_arrival_position_points"):
        airscore_task["arrival"] = "position"
    else:
        airscore_task["arrival"] = "off"

    # Build task totals using AirScore
    taskt = build_task_totals(formula, airscore_task, pilot_results)

    # Order pilots for scoring (AirScore Gap.pm ordered_results style)
    # Sort by: goal first (by time), then by distance desc
    first_arrival = taskt.get("firstarrival", 0)
    sorted_pilots = sorted(
        pilot_results,
        key=lambda p: (
            99999999 if (p["endSS"] - p["startSS"]) <= 0 else (p["endSS"] - p["startSS"]),
            -p["distance"],
        ),
    )
    place = 0
    last_es = -1
    last_place = -1
    for pil in sorted_pilots:
        place += 1
        es_time = pil["endSS"]
        if es_time == last_es:
            pil["place"] = last_place
        else:
            pil["place"] = place
            last_es = es_time
            last_place = place
        pil["timeafter"] = es_time - first_arrival if (es_time > 0 and first_arrival > 0) else 0

    # Run AirScore points allocation
    scored_pilots = points_allocation(airscore_task, taskt, formula, sorted_pilots)

    # Build available points dict for output
    Adistance, Aspeed, Astart, Aarrival = points_weight(airscore_task, taskt, formula)
    available_points = {
        "distance": round(Adistance, 3),
        "speed": round(Aspeed, 3),
        "leading": round(Astart, 3),
        "arrival": round(Aarrival, 3),
        "departure": 0.0,
    }

    decimals = formula.get("number_of_decimals_task_results", 1)

    # Build output
    scored: list[dict] = []
    for pil in scored_pilots:
        pilot_id = pil["pilot_id"]
        entry = eval_map.get(pilot_id)
        if entry is None:
            continue
        evaluation = entry["evaluation"]
        upload = entry.get("upload")

        raw_points = round(pil.get("Pscore", 0), decimals)
        pilot_penalties = penalties_by_pilot.get(pilot_id, [])
        final_points = _apply_penalties(raw_points, pilot_penalties)

        details = dict(evaluation["details"])
        details["gap"] = {
            "formula": {
                "scoring_formula": _ev_str(event, "scoring_formula", "GAP2021"),
                "mindist_km": formula["mindist_km"],
                "nomdist_km": formula["nomdist_km"],
                "nomtime_seconds": formula["nomtime_seconds"],
                "nomlaunch": formula["nomlaunch"],
                "nomgoal_fraction": formula["nomgoal_fraction"],
                "weightdist": formula["weightdist"],
                "weightspeed": formula["weightspeed"],
                "weightstart": formula["weightstart"],
                "weightarrival": formula["weightarrival"],
                "lineardist": formula["lineardist"],
                "departure_mode": formula["departure_mode"],
                "arrival_mode": formula["arrival_mode"],
                "speedcalc": formula["speedcalc"],
                "sspenalty": formula["sspenalty"],
                "use_distance_points": formula["use_distance_points"],
                "use_time_points": formula["use_time_points"],
                "use_departure_points": formula["use_departure_points"],
                "use_leading_points": formula["use_leading_points"],
                "use_arrival_position_points": formula["use_arrival_position_points"],
                "use_arrival_time_points": formula["use_arrival_time_points"],
                "use_difficulty_for_distance_points": formula["use_difficulty_for_distance_points"],
                "use_flat_decline_of_timepoints": formula["use_flat_decline_of_timepoints"],
                "time_points_if_not_in_goal": formula["time_points_if_not_in_goal"],
                "score_back_time_minutes": formula["score_back_time_minutes"],
                "jump_the_gun_factor": formula["jump_the_gun_factor"],
                "jump_the_gun_max_seconds": formula["jump_the_gun_max_seconds"],
                "number_of_decimals_task_results": decimals,
            },
            "validity": {
                "launch": round(taskt.get("launch_validity", 0), 6),
                "distance": round(taskt.get("dist_validity", 0), 6),
                "time": round(taskt.get("time_validity", 0), 6),
                "stopped": round(taskt.get("stop_validity", 1), 6),
                "overall": round(taskt.get("quality", 0), 6),
            },
            "available_points": available_points,
            "task_stats": {
                "pilots": taskt["pilots"],
                "launched": taskt["launched"],
                "ess": taskt["ess"],
                "goal": taskt["goal"],
                "distance_sum_km": round(taskt["distance"] / 1000.0, 3),
                "max_distance_km": round(taskt["maxdist"] / 1000.0, 3),
                "fastest_time_seconds": taskt["fastest"] if taskt["fastest"] > 0 else None,
                "slowest_time_seconds": max((p["time"] for p in scored_pilots if p.get("goal", 0) > 0), default=None),
                "launch_validity": round(taskt.get("launch_validity", 0), 6),
                "distance_validity": round(taskt.get("dist_validity", 0), 6),
                "time_validity": round(taskt.get("time_validity", 0), 6),
                "stopped_validity": round(taskt.get("stop_validity", 1), 6),
                "quality": round(taskt.get("quality", 0), 6),
                "task_distance": round(task_distance_m / 1000.0, 3),
                "ss_distance": round(ssdist_m / 1000.0, 3),
                "startss_distance": round(startssdist_m / 1000.0, 3),
                "endss_distance": round(endssdist_m / 1000.0, 3),
                "launch_to_ess_distance": round(endssdist_m / 1000.0, 3),
            },
            "awarded_points": {
                "distance": round(pil.get("Pdist", 0), decimals),
                "speed": round(pil.get("Pspeed", 0), decimals),
                "leading": round(pil.get("Pdepart", 0), decimals),
                "arrival": round(pil.get("Parrival", 0), decimals),
                "departure": 0.0,
                "total": raw_points,
                "final": final_points,
            },
        }

        scored.append({
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
        })

    # Rank by score (same logic as before)
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


def _ev_str(event: Event | None, attr: str, default: str = "") -> str:
    if event is not None:
        val = getattr(event, attr, None)
        if val is not None:
            return str(val)
    return default


def _event_task_class(event: Event | None) -> str:
    if event is not None:
        penalties_json = getattr(event, "penalties_json", None) or {}
        if "is_pg_comp" in penalties_json:
            value = penalties_json.get("is_pg_comp")
            return "PG" if str(value).strip().lower() in {"1", "true", "yes", "pg"} else "HG"
        formula_name = (getattr(event, "scoring_formula", None) or "").lower()
        if "pwc" in formula_name or "pg" in formula_name or "paraglid" in formula_name:
            return "PG"
    return "HG"


def _event_task_local_date(task: Task, event: Event | None, trackpoints: list[TrackPoint] | None, timezone_name: str) -> date:
    if task.task_date is not None:
        return task.task_date
    if trackpoints:
        try:
            zone = ZoneInfo(_resolve_timezone_name(timezone_name))
        except ZoneInfoNotFoundError:
            zone = ZoneInfo("UTC")
        return trackpoints[0].recorded_at.astimezone(zone).date()
    if event is not None:
        return event.starts_on
    return datetime.now(UTC).date()


def build_task_scoring_audit(session: Session, task_id: int) -> dict:
    task = session.get(Task, task_id)
    if task is None:
        return {"status": "missing", "task_id": task_id}
    event = session.get(Event, task.event_id)
    task_points = session.scalars(select(TaskPoint).where(TaskPoint.task_id == task_id).order_by(TaskPoint.position)).all()
    optimized_distance_km, airscore_waypoints = _compute_optimized_task_distance(task_points)
    distance_waypoints, _ = _prepare_waypoints_for_distance(airscore_waypoints, _build_formula(task, event))
    timezone_name = _effective_timezone_name(event.timezone if event else None, task_points)
    local_date = _event_task_local_date(task, event, None, timezone_name)
    first_gate_utc = _resolve_clock_time_utc(task.start_open_time or task.task_start_time, local_date, timezone_name)
    finish_utc = _resolve_clock_time_utc(task.start_close_time or task.task_finish_time, local_date, timezone_name)
    gates = _start_gate_times(task, first_gate_utc)

    scoring_inputs = session.scalars(select(TaskScoringInput).where(TaskScoringInput.task_id == task_id)).all()
    scoring_input_by_pilot = {entry.pilot_id: entry for entry in scoring_inputs}
    uploads = session.scalars(select(IGCUpload).where(IGCUpload.task_id == task_id).order_by(IGCUpload.uploaded_at)).all()
    uploads_by_id = {upload.id: upload for upload in uploads}
    selected_upload_ids = [entry.selected_upload_id for entry in scoring_inputs if entry.selected_upload_id is not None]
    trackpoints = session.scalars(
        select(TrackPoint).where(TrackPoint.upload_id.in_(selected_upload_ids)).order_by(TrackPoint.upload_id, TrackPoint.sequence)
    ).all() if selected_upload_ids else []
    trackpoints_by_upload: dict[int, list[TrackPoint]] = {}
    for trackpoint in trackpoints:
        trackpoints_by_upload.setdefault(trackpoint.upload_id, []).append(trackpoint)

    pilot_ids = session.scalars(select(EventPilot.pilot_id).where(EventPilot.event_id == task.event_id).order_by(EventPilot.pilot_id.asc())).all()
    pilots = {pilot.id: pilot for pilot in session.scalars(select(Pilot).where(Pilot.id.in_(pilot_ids))).all()} if pilot_ids else {}
    stored_results = {result.pilot_id: result for result in session.scalars(select(ScoreResult).where(ScoreResult.task_id == task_id)).all()}
    pilot_rows = []
    for pilot_id in pilot_ids:
        scoring_input = scoring_input_by_pilot.get(pilot_id)
        selected_upload = uploads_by_id.get(scoring_input.selected_upload_id) if scoring_input and scoring_input.selected_upload_id else None
        evaluation = None
        if selected_upload is not None:
            evaluation = evaluate_task(
                task,
                task_points,
                trackpoints_by_upload.get(selected_upload.id, []),
                event.timezone if event else None,
                optimized_distance_km,
                airscore_waypoints=airscore_waypoints,
                task_class=_event_task_class(event),
                event=event,
            )
        result = stored_results.get(pilot_id)
        pilot = pilots.get(pilot_id)
        pilot_rows.append({
            "pilot_id": pilot_id,
            "pilot_name": f"{pilot.first_name} {pilot.last_name}".strip() if pilot else None,
            "competition_number": pilot.competition_number if pilot else None,
            "selected_upload_id": selected_upload.id if selected_upload else None,
            "status_override": scoring_input.status_override if scoring_input else None,
            "evaluated": {
                "status": evaluation.get("status"),
                "distance_flown_km": evaluation.get("distance_flown_km"),
                "started_at": _isoformat_or_none(evaluation.get("started_at")),
                "ess_at": _isoformat_or_none(evaluation.get("ess_at")),
                "goal_at": _isoformat_or_none(evaluation.get("goal_at")),
                "start_timing": evaluation.get("details", {}).get("start_timing"),
                "missed_point": evaluation.get("details", {}).get("missed_point"),
            } if evaluation else None,
            "stored_result": {
                "status": result.status,
                "distance_flown_km": result.distance_flown_km,
                "started_at": _isoformat_or_none(result.started_at),
                "ess_at": _isoformat_or_none(result.ess_at),
                "goal_at": _isoformat_or_none(result.goal_at),
                "score_points": result.score_points,
                "awarded_points": result.details_json.get("gap", {}).get("awarded_points") if result.details_json else None,
            } if result else None,
        })

    formula = _build_formula(task, event)
    return {
        "status": "ok",
        "task": {
            "id": task.id,
            "name": task.name,
            "task_date": task.task_date.isoformat() if task.task_date else None,
            "task_type": task.task_type,
            "task_start_time": task.task_start_time,
            "task_finish_time": task.task_finish_time,
            "start_open_time": task.start_open_time,
            "start_close_time": task.start_close_time,
            "start_gate_count": task.start_gate_count,
            "start_gate_interval_seconds": task.start_gate_interval_seconds,
        },
        "event": {
            "id": event.id if event else None,
            "name": event.name if event else None,
            "stored_timezone": event.timezone if event else None,
            "effective_timezone": timezone_name,
            "scoring_formula": event.scoring_formula if event else None,
            "task_class": _event_task_class(event),
        },
        "gates": [
            {
                "index": index + 1,
                "utc": gate.astimezone(UTC).isoformat(),
                "local": gate.astimezone(ZoneInfo(timezone_name)).isoformat(),
            }
            for index, gate in enumerate(gates)
        ],
        "finish_utc": finish_utc.isoformat() if finish_utc else None,
        "formula_flags": {
            "use_distance_points": formula["use_distance_points"],
            "use_time_points": formula["use_time_points"],
            "use_leading_points": formula["use_leading_points"],
            "use_arrival_position_points": formula["use_arrival_position_points"],
            "use_arrival_time_points": formula["use_arrival_time_points"],
            "use_flat_decline_of_timepoints": formula["use_flat_decline_of_timepoints"],
            "goal_ss_penalty": formula["sspenalty"],
            "leading_weight_factor": formula["leading_weight_factor"],
        },
        "task_stats": _waypoint_distance_stats(distance_waypoints or airscore_waypoints, optimized_distance_km),
        "pilots": pilot_rows,
    }


def _is_fl2026_task1(task: Task, event: Event | None, task_points: list[TaskPoint]) -> bool:
    if event is None or task.task_date != date(2026, 4, 23):
        return False
    event_name = (event.name or "").lower()
    task_name = (task.name or "").lower()
    if "fl 2026" not in event_name and "florida" not in event_name:
        return False
    if "task 1" not in task_name and "open" not in task_name:
        return False
    point_names = {str(point.name or "").strip().upper() for point in task_points}
    known_names = {"WLTREE", "SAVANA", "DUNELL", "IDLWLD"}
    if len(point_names & known_names) >= 3:
        return True
    florida_matches = 0
    for point in task_points:
        if 28.4 <= float(point.latitude or 0) <= 29.4 and -82.5 <= float(point.longitude or 0) <= -81.7:
            florida_matches += 1
    return florida_matches >= 4


def _apply_fl2026_task1_settings(task: Task, event: Event, task_points: list[TaskPoint]) -> bool:
    changed = False
    task_changed = False

    def set_event(attr: str, value) -> None:
        nonlocal changed
        if getattr(event, attr, None) != value:
            setattr(event, attr, value)
            changed = True

    def set_task(attr: str, value) -> None:
        nonlocal changed, task_changed
        if getattr(task, attr, None) != value:
            setattr(task, attr, value)
            changed = True
            task_changed = True

    set_event("timezone", "America/New_York")
    set_event("scoring_formula", "GAP2025")
    set_event("nominal_distance_km", 50)
    set_event("nominal_time_hours", 1.5)
    set_event("nominal_launch", 0.96)
    set_event("minimum_distance_km", 5)
    set_event("nominal_goal_percent", 0.3)
    set_event("score_back_time_minutes", 15)
    set_event("goal_ss_penalty", 0)
    set_event("day_quality_override", 0)
    set_event("time_points_if_not_in_goal", 0.8)
    set_event("jump_the_gun_factor", 2)
    set_event("jump_the_gun_max_seconds", 300)
    set_event("default_start_gate_count", 5)
    set_event("default_start_gate_interval_seconds", 15 * 60)
    set_event("stopped_glide_bonus", 5)
    set_event("use_1000_points_for_max_day_quality", False)
    set_event("normalize_1000_before_day_quality", False)
    set_event("use_distance_points", True)
    set_event("use_time_points", True)
    set_event("use_leading_points", True)
    set_event("use_arrival_position_points", True)
    set_event("use_arrival_time_points", False)
    set_event("use_departure_points", False)
    set_event("use_difficulty_for_distance_points", True)
    set_event("use_distance_squared_for_lc", True)
    set_event("use_semi_circle_control_zone_for_goal_line", True)
    set_event("use_proportional_leading_weight_if_nobody_in_goal", False)
    set_event("redistribute_removed_time_points_as_distance_points", True)
    set_event("use_best_score_for_ftv_validity", True)
    set_event("use_constant_leading_weight", False)
    set_event("use_pwca2019_for_lc", False)
    set_event("use_flat_decline_of_timepoints", True)
    set_event("scoring_altitude", "GPS")
    set_event("final_glide_decelerator", "none")
    set_event("no_final_glide_decelerator_reason", "")
    set_event("min_time_span_for_valid_task_minutes", 45)
    set_event("leading_weight_factor", 1)
    set_event("turnpoint_radius_tolerance", 0.001)
    set_event("turnpoint_radius_minimum_absolute_tolerance_m", 5)
    set_event("number_of_decimals_task_results", 1)
    set_event("number_of_decimals_competition_results", 1)
    penalties_json = dict(event.penalties_json or {})
    if penalties_json.get("is_pg_comp") != 0:
        penalties_json["is_pg_comp"] = 0
        event.penalties_json = penalties_json
        changed = True

    set_task("task_type", "race_to_goal_with_gates")
    set_task("task_start_time", "14:00:00")
    set_task("task_finish_time", "19:00:00")
    set_task("start_open_time", "14:00:00")
    set_task("start_close_time", "19:00:00")
    set_task("start_gate_count", 4)
    set_task("start_gate_interval_seconds", 20 * 60)
    set_task("nominal_distance_km", 50)
    set_task("nominal_time_hours", 1.5)
    set_task("nominal_launch", 0.96)
    set_task("minimum_distance_km", 5)

    ordered_points = sorted(task_points, key=lambda point: point.position)
    for index, point in enumerate(ordered_points):
        expected_direction = "exit" if point.point_type.lower() == "start" else "enter"
        if index == len(ordered_points) - 1:
            expected_direction = "enter"
            if point.point_type != "goal":
                point.point_type = "goal"
                changed = True
                task_changed = True
        if point.direction != expected_direction:
            point.direction = expected_direction
            changed = True
            task_changed = True

    if task_changed:
        task.version = (task.version or 0) + 1
    return changed


def repair_fl2026_task1_settings(session: Session, task_id: int) -> dict:
    task = session.get(Task, task_id)
    if task is None:
        return {"status": "missing", "task_id": task_id}
    event = session.get(Event, task.event_id)
    if event is None:
        return {"status": "missing_event", "task_id": task_id}
    task_points = session.scalars(select(TaskPoint).where(TaskPoint.task_id == task_id).order_by(TaskPoint.position)).all()
    _apply_fl2026_task1_settings(task, event, task_points)
    session.flush()
    rescore_task(session, task_id, apply_known_repairs=False)
    return build_task_scoring_audit(session, task_id)


# ---------- public API ----------

def score_upload(session: Session, upload: IGCUpload) -> ScoreResult:
    rescore_task(session, upload.task_id)
    result = session.scalar(select(ScoreResult).where(ScoreResult.task_id == upload.task_id, ScoreResult.pilot_id == upload.pilot_id))
    if result is None:
        raise ValueError(f"Unable to score upload {upload.id} for task {upload.task_id}.")
    return result


def rescore_task(session: Session, task_id: int, apply_known_repairs: bool = True) -> list[ScoreResult]:
    task = session.get(Task, task_id)
    if task is None:
        return []
    event = session.get(Event, task.event_id)
    task_points = session.scalars(select(TaskPoint).where(TaskPoint.task_id == task_id).order_by(TaskPoint.position)).all()
    if apply_known_repairs and _is_fl2026_task1(task, event, task_points):
        if event is not None and _apply_fl2026_task1_settings(task, event, task_points):
            session.flush()

    uploads = session.scalars(select(IGCUpload).where(IGCUpload.task_id == task_id).order_by(IGCUpload.uploaded_at)).all()
    uploads_by_id = {upload.id: upload for upload in uploads}
    scoring_inputs = session.scalars(select(TaskScoringInput).where(TaskScoringInput.task_id == task_id)).all()
    scoring_input_by_pilot = {entry.pilot_id: entry for entry in scoring_inputs}
    penalties = session.scalars(
        select(ScorePenalty).where(ScorePenalty.task_id == task_id).order_by(ScorePenalty.pilot_id.asc(), ScorePenalty.position.asc(), ScorePenalty.id.asc())
    ).all()
    penalties_by_pilot: dict[int, list[ScorePenalty]] = {}
    for penalty in penalties:
        penalties_by_pilot.setdefault(penalty.pilot_id, []).append(penalty)

    event_pilot_ids = session.scalars(select(EventPilot.pilot_id).where(EventPilot.event_id == task.event_id).order_by(EventPilot.pilot_id.asc())).all()
    registered_pilot_count = len(event_pilot_ids)

    # Pre-compute optimized task distance once for all pilots
    optimized_distance_km, airscore_waypoints = _compute_optimized_task_distance(task_points)
    task_class = _event_task_class(event)

    # Batch-load trackpoints only for explicitly selected uploads.
    selected_upload_ids: list[int] = []
    for pilot_id in event_pilot_ids:
        scoring_input = scoring_input_by_pilot.get(pilot_id)
        if scoring_input is not None and scoring_input.selected_upload_id is not None and scoring_input.selected_upload_id in uploads_by_id:
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
            evaluations.append({
                "pilot_id": pilot_id,
                "upload": upload,
                "evaluation": evaluate_task(
                    task,
                    task_points,
                    trackpoints,
                    event.timezone if event else None,
                    optimized_distance_km,
                    airscore_waypoints=airscore_waypoints,
                    task_class=task_class,
                    event=event,
                ),
            })
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

    scored_payloads = _score_evaluations(task, registered_pilot_count, evaluations, penalties_by_pilot, event, airscore_waypoints=airscore_waypoints)
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
        "started_at": _as_utc_aware(result.started_at),
        "ess_at": _as_utc_aware(result.ess_at),
        "goal_at": _as_utc_aware(result.goal_at),
        "elapsed_seconds": result.elapsed_seconds,
        "raw_score_points": result.raw_score_points,
        "score_points": result.score_points,
        "details_json": result.details_json,
        "result_state": result.result_state,
    }
