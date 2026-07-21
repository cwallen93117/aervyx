"""
AirScore track verifier.

This module is the Python runtime port of the route-task verification behavior
from Geoff Wong's AirScore ``track_verify_sr.pl``. It consumes AirScore-style
task, waypoint, formula, and flight dictionaries and returns the pilot result
fields expected by the GAP scorer.
"""

from __future__ import annotations

import copy

from . import task as airscore_task
from .route import in_semicircle
from .task import distance_flown, precompute_waypoint_dist
from .track_lib import distance, to_rad_dict


def _coord_time(coord: dict | None) -> float | None:
    if coord is None:
        return None
    value = coord.get("time")
    return float(value) if value is not None else None


def _coord_detail(coord: dict | None) -> dict | None:
    if coord is None:
        return None
    return {
        "track_point_id": coord.get("track_point_id"),
        "sequence": coord.get("sequence"),
        "recorded_at": coord.get("recorded_at"),
        "latitude": coord.get("dlat"),
        "longitude": coord.get("dlong"),
        "pressure_altitude_m": coord.get("pressure_altitude_m"),
        "gps_altitude_m": coord.get("gps_altitude_m"),
        "altitude_m": coord.get("altitude_m"),
    }


def _point_direction(wpt: dict) -> str:
    return "exit" if wpt.get("how") == "exit" else "enter"


def _point_type(wpt: dict) -> str:
    return str(wpt.get("aervyx_point_type") or wpt.get("type") or "turnpoint")


def _required(wpt: dict) -> bool:
    return _point_type(wpt).lower() != "launch"


def _hit_record(wpt: dict) -> dict:
    return {
        "task_point_id": wpt.get("key"),
        "name": wpt.get("name"),
        "point_type": _point_type(wpt),
        "direction": _point_direction(wpt),
        "hit": False,
        "hit_at": None,
        "scored_hit_at": None,
        "track_point": None,
        "ignored_hit": False,
        "ignored_hit_at": None,
        "ignored_track_point": None,
        "required": _required(wpt),
    }


def _inside_radius(coord: dict, wpt: dict, radius_m: float) -> bool:
    return distance(coord, wpt) <= radius_m


def _made_entry(wpt: dict, waypoints: list[dict], wmade: int, coord: dict, awarded: bool = False) -> bool:
    if awarded:
        return True
    dist = distance(coord, wpt)
    radius = float(wpt.get("radius", 0.0) or 0.0)
    margin = float(wpt.get("margin", 0.0) or 0.0)
    if wpt.get("shape") == "line" and wmade > 0:
        return dist < radius + margin and in_semicircle(waypoints, wmade, coord)
    return dist < radius + margin


def _find_entry_hit(
    waypoints: list[dict],
    wmade: int,
    coords: list[dict],
    cursor: int = 0,
    latest_at: float | None = None,
    prefer_latest: bool = False,
    display_previous_outside: bool = False,
) -> tuple[int, float, int | None, float | None] | None:
    wpt = waypoints[wmade]
    radius = float(wpt.get("radius", 0.0) or 0.0)
    margin = float(wpt.get("margin", 0.0) or 0.0)
    entry_radius = radius + margin
    previous_inside = _inside_radius(coords[cursor - 1], wpt, entry_radius) if cursor > 0 and cursor <= len(coords) else False
    previous_outside_idx: int | None = None if previous_inside else cursor - 1 if cursor > 0 and cursor <= len(coords) else None
    candidate: tuple[int, float, int | None, float | None] | None = None
    for idx in range(cursor, len(coords)):
        coord = coords[idx]
        coord_time = _coord_time(coord)
        if coord_time is None:
            continue
        if latest_at is not None and coord_time > latest_at:
            break
        inside = _inside_radius(coord, wpt, entry_radius)
        if inside and not previous_inside and _made_entry(wpt, waypoints, wmade, coord):
            display_idx = previous_outside_idx if display_previous_outside and previous_outside_idx is not None else idx
            display_time = _coord_time(coords[display_idx])
            if display_time is not None:
                candidate = (display_idx, display_time, idx, coord_time)
                if not prefer_latest:
                    return candidate
        if not inside:
            previous_outside_idx = idx
        previous_inside = inside
    return candidate


def _find_exit_hit(
    wpt: dict,
    coords: list[dict],
    cursor: int = 0,
    latest_at: float | None = None,
    prefer_latest: bool = False,
) -> tuple[int, float, int | None, float | None] | None:
    radius = float(wpt.get("radius", 0.0) or 0.0)
    margin = float(wpt.get("margin", 0.0) or 0.0)
    outer_radius = radius + margin
    armed_inside_idx: int | None = None
    last_nominal_inside_idx: int | None = None
    if cursor > 0 and cursor <= len(coords):
        previous = coords[cursor - 1]
        if _inside_radius(previous, wpt, outer_radius):
            armed_inside_idx = cursor - 1
        if _inside_radius(previous, wpt, radius):
            last_nominal_inside_idx = cursor - 1
    candidate: tuple[int, float, int | None, float | None] | None = None
    for idx in range(cursor, len(coords)):
        coord = coords[idx]
        coord_time = _coord_time(coord)
        if coord_time is None:
            continue
        if latest_at is not None and coord_time > latest_at:
            break
        dist = distance(coord, wpt)
        if armed_inside_idx is not None and dist > radius:
            display_idx = last_nominal_inside_idx if last_nominal_inside_idx is not None else armed_inside_idx
            display_time = _coord_time(coords[display_idx])
            if display_time is not None:
                candidate = (display_idx, display_time, idx, coord_time)
                if not prefer_latest:
                    return candidate
            armed_inside_idx = None
            last_nominal_inside_idx = None
        if dist < outer_radius:
            armed_inside_idx = idx
            if dist <= radius:
                last_nominal_inside_idx = idx
        elif dist > outer_radius:
            armed_inside_idx = None
            last_nominal_inside_idx = None
    return candidate


def _find_waypoint_hit(
    waypoints: list[dict],
    wmade: int,
    coords: list[dict],
    cursor: int = 0,
    latest_at: float | None = None,
    prefer_latest: bool = False,
    display_previous_outside: bool = False,
) -> tuple[int, float, int | None, float | None] | None:
    wpt = waypoints[wmade]
    if wpt.get("how") == "exit":
        return _find_exit_hit(wpt, coords, cursor=cursor, latest_at=latest_at, prefer_latest=prefer_latest)
    return _find_entry_hit(
        waypoints,
        wmade,
        coords,
        cursor=cursor,
        latest_at=latest_at,
        prefer_latest=prefer_latest,
        display_previous_outside=display_previous_outside,
    )


def _start_gate_times(task: dict) -> list[float]:
    first_gate = float(task.get("sstart", 0.0) or 0.0)
    if first_gate <= 0:
        return []
    count = max(int(task.get("gate_count", 1) or 1), 1)
    interval = max(float(task.get("interval", 0.0) or 0.0), 0.0)
    return [first_gate + index * interval for index in range(count)]


def _jump_penalty(formula: dict, jump_seconds: int) -> tuple[int, float]:
    max_jump = max(int(formula.get("jump_the_gun_max_seconds", 0) or 0), 0)
    penalty_seconds = min(jump_seconds, max_jump) if max_jump > 0 else jump_seconds
    penalty_points = max(float(formula.get("jump_the_gun_factor", 0.0) or 0.0), 0.0) * penalty_seconds
    return penalty_seconds, penalty_points


def _score_race_start(task: dict, formula: dict, actual_time: float, exit_after_time: float | None) -> tuple[float, dict]:
    gates = _start_gate_times(task)
    if not gates:
        return actual_time, {
            "start_scoring_mode": "race_to_goal_with_gates",
            "start_gate_index": None,
            "start_gate_time": None,
            "jump_the_gun_seconds": 0,
            "jump_the_gun_penalty_seconds": 0,
            "jump_the_gun_penalty_points": 0.0,
        }
    selected_index = 0
    jump_seconds = 0
    if actual_time < gates[0]:
        scored_time = gates[0]
        if exit_after_time is None or exit_after_time < gates[0]:
            jump_seconds = int(gates[0] - actual_time)
    else:
        interval_gate_index = None
        if exit_after_time is not None:
            for index, gate_time in enumerate(gates):
                if actual_time <= gate_time <= exit_after_time:
                    interval_gate_index = index
                    break
        if interval_gate_index is not None:
            selected_index = interval_gate_index
        else:
            for index, gate_time in enumerate(gates):
                if gate_time <= actual_time:
                    selected_index = index
                else:
                    break
        scored_time = gates[selected_index]
    penalty_seconds, penalty_points = _jump_penalty(formula, jump_seconds)
    return scored_time, {
        "start_scoring_mode": "race_to_goal_with_gates",
        "start_gate_index": selected_index + 1,
        "start_gate_time": scored_time,
        "jump_the_gun_seconds": jump_seconds,
        "jump_the_gun_penalty_seconds": penalty_seconds,
        "jump_the_gun_penalty_points": round(penalty_points, 3),
    }


def _score_elapsed_start(task: dict, formula: dict, actual_time: float) -> tuple[float, dict]:
    task_start = float(task.get("sstart", 0.0) or 0.0)
    start_close = task.get("start_close")
    latest = float(start_close) if start_close is not None else None
    scored_time = actual_time
    jump_seconds = 0
    if task_start > 0 and actual_time < task_start:
        scored_time = task_start
        jump_seconds = int(task_start - actual_time)
    elif latest is not None and actual_time > latest:
        scored_time = latest
    penalty_seconds, penalty_points = _jump_penalty(formula, jump_seconds)
    return scored_time, {
        "start_scoring_mode": "elapsed_time",
        "start_gate_index": None,
        "start_gate_time": None,
        "jump_the_gun_seconds": jump_seconds,
        "jump_the_gun_penalty_seconds": penalty_seconds,
        "jump_the_gun_penalty_points": round(penalty_points, 3),
    }


def _score_start(task: dict, formula: dict, actual_time: float, exit_after_time: float | None) -> tuple[float, dict]:
    if task.get("type") == "elapsed":
        return _score_elapsed_start(task, formula, actual_time)
    return _score_race_start(task, formula, actual_time, exit_after_time)


def _cumulative_distance_for_waypoint(waypoint_distances: list[float], wmade: int, total_distance: float) -> float:
    if wmade < 0:
        return 0.0
    if wmade + 1 >= len(waypoint_distances):
        return total_distance
    return max(float(waypoint_distances[wmade + 1] or 0.0), 0.0)


def _leading_target_indices(waypoints: list[dict], hit_indices: dict[int, int], coords: list[dict]) -> list[int]:
    required_indices = [index for index, wpt in enumerate(waypoints) if _required(wpt)]
    if not required_indices:
        return [0] * len(coords)
    pointer = 0
    targets: list[int] = []
    for coord_index, _coord in enumerate(coords):
        while pointer < len(required_indices):
            wpt_index = required_indices[pointer]
            hit_index = hit_indices.get(wpt_index)
            if hit_index is not None and hit_index < coord_index:
                pointer += 1
                continue
            break
        if pointer >= len(required_indices):
            targets.append(required_indices[-1])
        else:
            targets.append(required_indices[pointer])
        while pointer < len(required_indices):
            wpt_index = required_indices[pointer]
            hit_index = hit_indices.get(wpt_index)
            if hit_index is not None and hit_index <= coord_index:
                pointer += 1
                continue
            break
    return targets


def _compute_leading_coeff(
    waypoints: list[dict],
    coords: list[dict],
    startss: float,
    endss: float | None,
    distance_flown_m: float,
    task: dict,
    target_waypoint_indices: list[int],
    actual_start_index: int | None,
) -> tuple[float, float]:
    if not waypoints or len(waypoints) < 2 or not coords or startss <= 0:
        return 0.0, 0.0
    ssdist = float(waypoints[0].get("_ssdist", 0.0) or 0.0)
    endssdist = float(waypoints[0].get("_endssdist", 0.0) or 0.0)
    startssdist = float(waypoints[0].get("_startssdist", endssdist - ssdist if endssdist > 0 and ssdist > 0 else 0.0) or 0.0)
    if ssdist <= 0 or endssdist <= 0:
        return 0.0, 0.0

    task_sstart = float(task.get("sstart", 0.0) or startss)
    task_sfinish = float(task.get("sfinish", 0.0) or (task_sstart + 86400))
    task_class = str(task.get("class") or "HG")
    coeff = 0.0
    leading_area = 0.0
    maxdist = 0.0
    had_previous = False
    ess_epoch = endss if endss is not None and endss > 0 else float("inf")

    for index, coord in enumerate(coords):
        coord_time = _coord_time(coord)
        if coord_time is None:
            continue
        if coord_time > ess_epoch:
            break
        target_index = target_waypoint_indices[index] if index < len(target_waypoint_indices) else int(waypoints[0].get("_spt", 0) or 0)
        try:
            newdist = distance_flown(waypoints, target_index, coord)
        except (IndexError, ZeroDivisionError):
            continue
        if distance_flown_m > 0:
            newdist = min(newdist, distance_flown_m)
        if actual_start_index is not None:
            if index < actual_start_index:
                continue
            if index == actual_start_index:
                coeff = 0.0
                leading_area = 0.0
                maxdist = max(newdist, startssdist)
                had_previous = True
                continue
        if newdist > maxdist:
            if had_previous:
                tasktime = coord_time - task_sstart
                if newdist >= startssdist and tasktime > 0:
                    coeff += tasktime * (newdist - maxdist)
                    last_remaining = endssdist - maxdist
                    remaining = endssdist - newdist
                    if task_class == "HG":
                        leading_area += tasktime * (last_remaining * last_remaining - remaining * remaining)
                    elif ssdist > 0 and remaining >= 0:
                        rising = (1 - 10 ** ((9 * remaining / ssdist) - 9)) ** 5
                        falling = (1 - 10 ** ((-3 * remaining / ssdist))) ** 2
                        leading_area += tasktime * rising * falling * (last_remaining - remaining)
            had_previous = True
            maxdist = newdist

    if (endss is None or endss <= 0) and maxdist > startssdist:
        remaining_ss = endssdist - distance_flown_m
        if remaining_ss > 0:
            ss_delay = max(startss - task_sstart, 0.0)
            task_duration = task_sfinish - task_sstart
            coeff += ssdist * ss_delay + remaining_ss * task_duration
            if task_class == "HG":
                leading_area += task_duration * remaining_ss * remaining_ss
            elif ssdist > 0:
                falling = (1 - 10 ** ((-3 * remaining_ss / ssdist))) ** 2
                leading_area += falling * task_duration * remaining_ss

    if maxdist < startssdist:
        return 0.0, 0.0
    norm = 1800.0 * ssdist
    if norm > 0:
        return coeff / norm, leading_area / norm
    return 0.0, 0.0


def validate_task(flight: dict, task: dict, formula: dict) -> dict:
    """Verify one track against one route task and return AirScore result fields."""
    original_waypoints = task.get("waypoints") or []
    coords = list(flight.get("coords") or [])
    waypoints = copy.deepcopy(original_waypoints)
    if len(waypoints) < 2 or not coords:
        return {
            "result": "lo",
            "goal": 0,
            "distance": 0.0,
            "startSS": 0,
            "endSS": 0,
            "goal_time": 0,
            "time": 0,
            "coeff": 0.0,
            "coeff2": 0.0,
            "penalty": 0.0,
            "status": "uploaded",
            "details": {"hits": [_hit_record(wpt) for wpt in waypoints], "engine": "airscore.verify"},
        }

    spt, ept, gpt, ssdist, startssdist, endssdist, totdist = precompute_waypoint_dist(waypoints, formula)
    waypoint_distances = list(getattr(airscore_task, "_wptdistcache", []))
    for wpt in waypoints:
        wpt["_spt"] = spt
        wpt["_ept"] = ept
        wpt["_gpt"] = gpt
        wpt["_ssdist"] = ssdist
        wpt["_startssdist"] = startssdist
        wpt["_endssdist"] = endssdist
        wpt["_totdist"] = totdist
        wpt["_wptdistances"] = waypoint_distances

    hit_details = [_hit_record(wpt) for wpt in waypoints]
    hit_indices: dict[int, int] = {}
    hit_times: dict[int, float] = {}
    cursor = 0
    missed_index: int | None = None
    last_required_index: int | None = None
    last_required_track_index: int | None = None
    start_exit_after_time: float | None = None
    actual_start_index: int | None = None
    actual_start_time: float | None = None
    startss = 0.0
    start_timing: dict = {
        "actual_start_crossing_at": None,
        "actual_start_exit_after_at": None,
        "scored_start_at": None,
        "start_scoring_mode": "elapsed_time" if task.get("type") == "elapsed" else "race_to_goal_with_gates",
        "start_gate_index": None,
        "start_gate_time": None,
        "jump_the_gun_seconds": 0,
        "jump_the_gun_penalty_seconds": 0,
        "jump_the_gun_penalty_points": 0.0,
    }

    for wmade, wpt in enumerate(waypoints):
        if not _required(wpt):
            optional_hit = _find_waypoint_hit(waypoints, wmade, coords, cursor=cursor)
            if optional_hit is not None:
                idx, hit_time, _inside_idx, _inside_time = optional_hit
                hit_indices[wmade] = idx
                hit_times[wmade] = hit_time
                hit_details[wmade]["hit"] = True
                hit_details[wmade]["hit_at"] = hit_time
                hit_details[wmade]["scored_hit_at"] = hit_time
                hit_details[wmade]["track_point"] = _coord_detail(coords[idx])
                cursor = max(cursor, idx + 1)
            continue

        is_start = wpt.get("type") == "start"
        latest_at = None if is_start and task.get("type") == "elapsed" else float(task.get("sfinish", 0.0) or 0.0) or None
        if is_start:
            # AirScore stops accepting restarts once the next required waypoint is made.
            first_start_hit = _find_waypoint_hit(
                waypoints,
                wmade,
                coords,
                cursor=cursor,
                latest_at=latest_at,
                display_previous_outside=wpt.get("how") == "entry",
            )
            next_required = next((index for index in range(wmade + 1, len(waypoints)) if _required(waypoints[index])), None)
            if first_start_hit is not None and next_required is not None:
                next_cursor = first_start_hit[2] if first_start_hit[2] is not None else first_start_hit[0] + 1
                next_hit = _find_waypoint_hit(waypoints, next_required, coords, cursor=next_cursor, latest_at=latest_at)
                if next_hit is not None:
                    latest_at = min(latest_at, next_hit[1]) if latest_at is not None else next_hit[1]
            hit = _find_waypoint_hit(
                waypoints,
                wmade,
                coords,
                cursor=cursor,
                latest_at=latest_at,
                prefer_latest=True,
                display_previous_outside=wpt.get("how") == "entry",
            )
        else:
            hit = _find_waypoint_hit(waypoints, wmade, coords, cursor=cursor, latest_at=latest_at)
        if hit is None:
            missed_index = wmade
            break
        idx, hit_time, after_idx, after_time = hit
        hit_indices[wmade] = idx
        hit_times[wmade] = hit_time
        hit_details[wmade]["hit"] = True
        hit_details[wmade]["hit_at"] = hit_time
        hit_details[wmade]["scored_hit_at"] = hit_time
        hit_details[wmade]["track_point"] = _coord_detail(coords[idx])
        cursor = idx + 1
        last_required_index = wmade
        last_required_track_index = idx
        if is_start:
            actual_start_index = idx
            actual_start_time = hit_time
            start_exit_after_time = after_time
            startss, start_mode_details = _score_start(task, formula, hit_time, after_time)
            start_timing.update(start_mode_details)
            start_timing["actual_start_crossing_at"] = hit_time
            start_timing["actual_start_exit_after_at"] = start_exit_after_time
            start_timing["scored_start_at"] = startss
            hit_details[wmade]["scored_hit_at"] = startss

    if missed_index is not None:
        ignored_cursor = cursor
        for wmade in range(missed_index + 1, len(waypoints)):
            if not _required(waypoints[wmade]):
                continue
            ignored_hit = _find_waypoint_hit(waypoints, wmade, coords, cursor=ignored_cursor)
            if ignored_hit is None:
                continue
            idx, hit_time, _after_idx, _after_time = ignored_hit
            hit_details[wmade]["ignored_hit"] = True
            hit_details[wmade]["ignored_hit_at"] = hit_time
            hit_details[wmade]["ignored_track_point"] = _coord_detail(coords[idx])
            ignored_cursor = idx + 1

    progress_distance = _cumulative_distance_for_waypoint(waypoint_distances, last_required_index if last_required_index is not None else -1, totdist)
    if missed_index is not None and last_required_index is not None:
        cap = _cumulative_distance_for_waypoint(waypoint_distances, missed_index, totdist)
        search_start = (last_required_track_index + 1) if last_required_track_index is not None else 0
        for coord in coords[search_start:]:
            try:
                flown = distance_flown(waypoints, missed_index, coord)
            except (IndexError, ZeroDivisionError):
                continue
            progress_distance = max(progress_distance, min(flown, cap))

    valid_goal = gpt in hit_indices and missed_index is None
    if valid_goal:
        progress_distance = totdist
    if coords and not valid_goal:
        progress_distance = max(progress_distance, float(formula.get("mindist", 0.0) or 0.0))

    endss = hit_times.get(ept, 0.0) if ept in hit_indices else 0.0
    goal_time = hit_times.get(gpt, 0.0) if gpt in hit_indices and valid_goal else 0.0
    if valid_goal:
        status = "goal"
    elif ept in hit_indices:
        status = "ess"
    elif progress_distance > 0:
        status = "partial"
    else:
        status = "uploaded"

    target_indices = _leading_target_indices(waypoints, hit_indices, coords)
    coeff, coeff2 = _compute_leading_coeff(
        waypoints,
        coords,
        startss,
        endss if endss > 0 else None,
        progress_distance,
        task,
        target_indices,
        actual_start_index,
    )

    elapsed = endss - startss if startss > 0 and endss > 0 else 0
    if elapsed < 0:
        elapsed = 0
    missed_wpt = waypoints[missed_index] if missed_index is not None else None
    return {
        "result": "lo",
        "goal": 1 if valid_goal else 0,
        "distance": progress_distance,
        "startSS": startss if startss > 0 else 0,
        "endSS": endss if startss > 0 and endss > 0 else 0,
        "goal_time": goal_time if valid_goal else 0,
        "time": elapsed,
        "coeff": coeff,
        "coeff2": coeff2,
        "penalty": float(start_timing.get("jump_the_gun_penalty_points", 0.0) or 0.0),
        "status": status,
        "waypoints_made": len(hit_indices),
        "closest": 0,
        "actual_start": actual_start_time,
        "details": {
            "engine": "airscore.verify",
            "engine_source": "track_verify_sr.pl",
            "hits": hit_details,
            "start_timing": start_timing,
            "missed_point": {
                "task_point_id": missed_wpt.get("key"),
                "name": missed_wpt.get("name"),
                "point_type": _point_type(missed_wpt),
            } if missed_wpt is not None else None,
            "airscore_result": {
                "distance": progress_distance,
                "startSS": startss if startss > 0 else 0,
                "endSS": endss if startss > 0 and endss > 0 else 0,
                "goal": 1 if valid_goal else 0,
                "result": "lo",
                "coeff": coeff,
                "coeff2": coeff2,
                "penalty": float(start_timing.get("jump_the_gun_penalty_points", 0.0) or 0.0),
            },
        },
    }


def coord_from_degrees(latitude: float, longitude: float, timestamp: float, **extra) -> dict:
    return to_rad_dict(latitude, longitude, time=timestamp, **extra)
