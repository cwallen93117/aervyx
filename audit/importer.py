"""Import FSDB competition data into Aervyx via the REST API."""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from audit.api_client import AervyxClient, ApiError
from audit.fsdb_parser import FsdbCompetition, FsdbFormula, FsdbTask, FsdbTurnpoint
from audit.pilot_registry import PilotRegistry

log = logging.getLogger(__name__)


@dataclass
class ImportResult:
    competition_name: str = ""
    event_id: int | None = None
    pilot_map: dict[int, int] = field(default_factory=dict)  # fsdb_id → aervyx_pilot_id
    task_map: dict[int, int] = field(default_factory=dict)  # fsdb_task_id → aervyx_task_id
    upload_summary: dict[int, dict] = field(default_factory=dict)  # task_id → {matched, unmatched, total}
    errors: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------

def _formula_to_event_payload(comp: FsdbCompetition) -> dict:
    """Map FSDB competition + formula to Aervyx EventCreate fields."""
    f = comp.formula
    return {
        "name": comp.name,
        "location": comp.location,
        "starts_on": comp.from_date,
        "ends_on": comp.to_date,
        "timezone": "America/New_York",  # All Highland Challenge comps are US Eastern
        "scoring_formula": f.id,
        "nominal_distance_km": f.nom_dist,
        "nominal_time_hours": f.nom_time,
        "nominal_launch": f.nom_launch,
        "minimum_distance_km": f.min_dist,
        "nominal_goal_percent": f.nom_goal,
        "score_back_time_minutes": f.score_back_time,
        "goal_ss_penalty": 0.0,
        "day_quality_override": f.day_quality_override,
        "time_points_if_not_in_goal": f.time_points_if_not_in_goal,
        "jump_the_gun_factor": f.jump_the_gun_factor,
        "jump_the_gun_max_seconds": f.jump_the_gun_max,
        "stopped_glide_bonus": f.bonus_gr,
        "use_1000_points_for_max_day_quality": f.use_1000_points_for_max_day_quality,
        "normalize_1000_before_day_quality": f.normalize_1000_before_day_quality,
        "use_distance_points": f.use_distance_points,
        "use_time_points": f.use_time_points,
        "use_leading_points": f.use_leading_points,
        "use_arrival_position_points": f.use_arrival_position_points,
        "use_arrival_time_points": f.use_arrival_time_points,
        "use_departure_points": f.use_departure_points,
        "use_difficulty_for_distance_points": f.use_difficulty_for_distance_points,
        "use_distance_squared_for_lc": f.use_distance_squared_for_lc,
        "use_semi_circle_control_zone_for_goal_line": f.use_semi_circle_control_zone_for_goal_line,
        "use_proportional_leading_weight_if_nobody_in_goal": f.use_proportional_leading_weight_if_nobody_in_goal,
        "redistribute_removed_time_points_as_distance_points": f.redistribute_removed_time_points_as_distance_points,
        "use_best_score_for_ftv_validity": f.use_best_score_for_ftv_validity,
        "use_constant_leading_weight": f.use_constant_leading_weight,
        "use_pwca2019_for_lc": f.use_pwca2019_for_lc,
        "use_flat_decline_of_timepoints": f.use_flat_decline_of_timepoints,
        "scoring_altitude": f.scoring_altitude,
        "final_glide_decelerator": f.final_glide_decelerator,
        "no_final_glide_decelerator_reason": f.no_final_glide_decelerator_reason,
        "min_time_span_for_valid_task_minutes": f.min_time_span_for_valid_task,
        "leading_weight_factor": f.leading_weight_factor,
        "turnpoint_radius_tolerance": f.turnpoint_radius_tolerance,
        "turnpoint_radius_minimum_absolute_tolerance_m": f.turnpoint_radius_minimum_absolute_tolerance,
        "number_of_decimals_task_results": f.number_of_decimals_task_results,
        "number_of_decimals_competition_results": f.number_of_decimals_competition_results,
    }


def _determine_task_type(task: FsdbTask) -> str:
    """Infer Aervyx task_type from FSDB task structure."""
    n_gates = len(task.start_gates)
    if n_gates > 1:
        return "race_to_goal_with_gates"
    # single gate or no gates — check if ss != es
    if task.ss != task.es:
        return "race_to_goal"
    return "elapsed_time"


def _extract_time(iso_str: str) -> str | None:
    """Extract HH:MM:SS from an ISO datetime string."""
    if not iso_str:
        return None
    m = re.search(r"(\d{2}:\d{2}:\d{2})", iso_str)
    return m.group(1) if m else None


def _build_task_points(task: FsdbTask) -> list[dict]:
    """Map FSDB turnpoints + ss/es indices to Aervyx TaskPointInput dicts.

    FSDB uses 1-based ss and es indices into the turnpoint list.
    Aervyx expects point_type: start, turnpoint, ess, goal.
    """
    tps = task.turnpoints
    if not tps:
        return []

    ss_idx = task.ss - 1  # Convert to 0-based
    es_idx = task.es - 1
    last_idx = len(tps) - 1

    points: list[dict] = []
    for i, tp in enumerate(tps):
        if i == ss_idx:
            ptype = "start"
        elif i == es_idx and i == last_idx:
            # ESS and goal coincide (common: ESS is the last point = goal)
            ptype = "goal"
        elif i == es_idx:
            ptype = "ess"
        elif i > es_idx:
            ptype = "goal"
        elif ss_idx < i < es_idx:
            ptype = "turnpoint"
        else:
            # Points before ss (e.g. launch point with radius=1)
            # Skip launch/reference points that have tiny radius
            if tp.radius <= 1:
                continue
            ptype = "start"  # Shouldn't normally hit this

        points.append({
            "position": len(points),
            "point_type": ptype,
            "radius_m": tp.radius,
            "name": tp.code,
            "latitude": tp.lat,
            "longitude": tp.lon,
        })

    return points


def _build_task_payload(task: FsdbTask, comp_formula: FsdbFormula) -> dict:
    """Build Aervyx TaskInput payload from FSDB task."""
    task_type = _determine_task_type(task)
    points = _build_task_points(task)

    # Times from first turnpoint or start gate
    tps = task.turnpoints
    start_open = _extract_time(task.start_gates[0]) if task.start_gates else (
        _extract_time(tps[0].open_time) if tps else None
    )
    start_close = _extract_time(tps[0].close_time) if tps else None

    # Task window
    task_start = _extract_time(tps[0].open_time) if tps else None
    task_finish = _extract_time(tps[0].close_time) if tps else None

    # Gate configuration
    gate_count = len(task.start_gates) if task.start_gates else 1
    gate_interval = None
    if len(task.start_gates) >= 2:
        try:
            t1 = datetime.fromisoformat(task.start_gates[0])
            t2 = datetime.fromisoformat(task.start_gates[1])
            gate_interval = int((t2 - t1).total_seconds())
        except (ValueError, TypeError):
            gate_interval = 600  # Default 10 min

    # Use task-level formula if it differs, else comp formula
    f = task.formula

    payload = {
        "name": task.name,
        "status": "draft",
        "task_type": task_type,
        "task_start_time": task_start,
        "task_finish_time": task_finish,
        "start_open_time": start_open,
        "start_close_time": start_close,
        "start_gate_count": gate_count,
        "start_gate_interval_seconds": gate_interval,
        "nominal_distance_km": f.nom_dist,
        "nominal_time_hours": f.nom_time,
        "nominal_launch": f.nom_launch,
        "minimum_distance_km": f.min_dist,
        "penalties_json": {},
        "points": points,
    }
    return payload


# ---------------------------------------------------------------------------
# IGC file discovery
# ---------------------------------------------------------------------------

def _find_igc_folder(task: FsdbTask, comp_folder: Path, task_index: int) -> Path | None:
    """Find the folder containing IGC files for a given task.

    Searches common naming patterns in the competition's tracklogs folder.
    """
    tracklogs_base = None
    for candidate in [
        comp_folder / "4. Tracklogs",
        comp_folder / "Flights",
        comp_folder / "tracklogs",
    ]:
        if candidate.is_dir():
            tracklogs_base = candidate
            break

    if tracklogs_base is None:
        return None

    # Try various naming conventions
    task_num = task_index + 1
    candidates = [
        f"T{task_num}",
        f"Task {task_num}",
        f"Task{task_num}",
        task.name,
    ]

    for sub_name in candidates:
        folder = tracklogs_base / sub_name
        if folder.is_dir():
            return folder

    # Try partial match on any subfolder
    for sub in sorted(tracklogs_base.iterdir()):
        if sub.is_dir():
            name_lower = sub.name.lower()
            if f"t{task_num}" in name_lower or f"task {task_num}" in name_lower or f"task{task_num}" in name_lower:
                return sub
            # Also try matching by day number in folder name
            m = re.search(r"(\d+)", sub.name)
            if m and int(m.group(1)) == task_num:
                return sub

    return None


def _find_igc_folder_2012(task: FsdbTask, comp_folder: Path) -> Path | None:
    """For 2012-era comps, tracklogs are in the FSDB tracklog_folder path.
    But those paths reference the original machine; try to adapt.
    """
    orig = task.tracklog_folder
    if not orig:
        return None

    # Try the original path directly (unlikely to work on different machine)
    orig_path = Path(orig)
    if orig_path.is_dir():
        return orig_path

    # Try extracting the relative part after "Highland Challenge Files"
    lower = orig.replace("\\", "/").lower()
    marker = "highland challenge files/"
    idx = lower.find(marker)
    if idx >= 0:
        relative = orig.replace("\\", "/")[idx + len(marker):]
        from audit.config import HIGHLAND_ROOT
        candidate = HIGHLAND_ROOT / relative
        if candidate.is_dir():
            return candidate

    # Try within the comp_folder Flights directory
    parts = Path(orig).parts
    for i, part in enumerate(parts):
        if "flights" in part.lower() or "tracklogs" in part.lower():
            relative_parts = parts[i:]
            candidate = comp_folder / Path(*relative_parts)
            if candidate.is_dir():
                return candidate

    return None


def _collect_igc_files(folder: Path) -> list[Path]:
    """Collect all .igc files from a folder (non-recursive)."""
    if not folder or not folder.is_dir():
        return []
    return sorted(folder.glob("*.igc"))


# ---------------------------------------------------------------------------
# Main import orchestrator
# ---------------------------------------------------------------------------

def import_competition(
    client: AervyxClient,
    registry: PilotRegistry,
    comp: FsdbCompetition,
    comp_folder: Path,
    dry_run: bool = False,
) -> ImportResult:
    """Import a single competition into Aervyx."""
    result = ImportResult(competition_name=comp.name)

    # Check for existing event with same name
    try:
        existing_events = client.list_events()
        for ev in existing_events:
            if ev["name"] == comp.name:
                result.skipped = True
                result.skip_reason = f"Event '{comp.name}' already exists (id={ev['id']})"
                result.event_id = ev["id"]
                log.warning(result.skip_reason)
                return result
    except Exception as exc:
        result.errors.append(f"Failed to list events: {exc}")
        return result

    if dry_run:
        log.info("[DRY RUN] Would create event: %s", comp.name)
        result.skipped = True
        result.skip_reason = "dry run"
        return result

    # 1. Create event
    log.info("Creating event: %s", comp.name)
    try:
        event_payload = _formula_to_event_payload(comp)
        event_resp = client.create_event(event_payload)
        event_id = event_resp["id"]
        result.event_id = event_id
        log.info("Created event id=%d", event_id)
    except Exception as exc:
        result.errors.append(f"Failed to create event: {exc}")
        return result

    # 2. Register pilots
    log.info("Registering %d pilots", len(comp.participants))
    for p in comp.participants:
        try:
            aervyx_id = registry.find_or_create(p, event_id)
            result.pilot_map[p.fsdb_id] = aervyx_id
        except Exception as exc:
            result.errors.append(f"Failed to register pilot {p.name}: {exc}")

    # 3. Create tasks
    for i, task in enumerate(comp.tasks):
        log.info("Creating task %d/%d: %s", i + 1, len(comp.tasks), task.name)
        try:
            task_payload = _build_task_payload(task, comp.formula)
            task_resp = client.create_task(event_id, task_payload)
            aervyx_task_id = task_resp["id"]
            result.task_map[task.fsdb_id] = aervyx_task_id
            log.info("Created task id=%d", aervyx_task_id)
        except Exception as exc:
            result.errors.append(f"Failed to create task {task.name}: {exc}")
            continue

        # 4. Publish task
        try:
            client.publish_task(aervyx_task_id)
            log.info("Published task id=%d", aervyx_task_id)
        except Exception as exc:
            result.errors.append(f"Failed to publish task {task.name}: {exc}")

        # 5. Upload IGC files
        igc_folder = _find_igc_folder(task, comp_folder, i)
        if igc_folder is None:
            igc_folder = _find_igc_folder_2012(task, comp_folder)

        igc_files = _collect_igc_files(igc_folder) if igc_folder else []
        if not igc_files:
            log.warning("No IGC files found for task %s (searched %s)", task.name, igc_folder)
            result.upload_summary[task.fsdb_id] = {"matched": 0, "unmatched": 0, "total": 0}
            continue

        log.info("Uploading %d IGC files for task %s", len(igc_files), task.name)
        try:
            upload_resp = client.bulk_upload_igc(aervyx_task_id, igc_files)
            matched = sum(1 for u in upload_resp if u.get("matched"))
            unmatched = sum(1 for u in upload_resp if not u.get("matched"))
            result.upload_summary[task.fsdb_id] = {
                "matched": matched,
                "unmatched": unmatched,
                "total": len(upload_resp),
                "details": upload_resp,
            }
            log.info("Uploaded: %d matched, %d unmatched", matched, unmatched)
        except Exception as exc:
            result.errors.append(f"Failed to upload IGC for task {task.name}: {exc}")
            continue

        # 6. Select uploads for scoring and rescore
        try:
            _select_uploads_and_rescore(client, aervyx_task_id, result, task)
        except Exception as exc:
            result.errors.append(f"Failed to score task {task.name}: {exc}")

    return result


def _select_uploads_and_rescore(
    client: AervyxClient,
    task_id: int,
    result: ImportResult,
    fsdb_task: FsdbTask,
) -> None:
    """Select each pilot's upload for scoring, then trigger rescore."""
    # Get scoring operations grid to find uploads
    ops = client.get_scoring_operations(task_id)
    rows = ops.get("rows", [])

    for row in rows:
        pilot_id = row["pilot_id"]
        uploads = row.get("uploads", [])
        if not uploads:
            continue

        # Select the first (most recent) upload
        upload_id = uploads[0]["id"]

        # Check if this pilot is in FSDB results without flight data → mark DNF
        fsdb_pilot_id = None
        for fid, aid in result.pilot_map.items():
            if aid == pilot_id:
                fsdb_pilot_id = fid
                break

        if fsdb_pilot_id is not None:
            # Check if pilot had no flight data in FSDB
            for pr in fsdb_task.participant_results:
                if pr.fsdb_pilot_id == fsdb_pilot_id and not pr.had_flight_data and pr.points == 0:
                    # Pilot was present but didn't fly — but we may still have an upload
                    # so select the upload anyway
                    break

        try:
            client._request(
                "PATCH",
                f"/api/tasks/{task_id}/scoring-inputs/{pilot_id}",
                json={"selected_upload_id": upload_id},
            )
        except Exception as exc:
            log.warning("Failed to select upload for pilot %d: %s", pilot_id, exc)

    # Also mark pilots without uploads who had no flight data as "did_not_fly"
    for row in rows:
        pilot_id = row["pilot_id"]
        uploads = row.get("uploads", [])
        if uploads:
            continue

        # Find FSDB pilot id for this Aervyx pilot
        fsdb_pilot_id = None
        for fid, aid in result.pilot_map.items():
            if aid == pilot_id:
                fsdb_pilot_id = fid
                break

        if fsdb_pilot_id is not None:
            for pr in fsdb_task.participant_results:
                if pr.fsdb_pilot_id == fsdb_pilot_id and not pr.had_flight_data:
                    try:
                        client._request(
                            "PATCH",
                            f"/api/tasks/{task_id}/scoring-inputs/{pilot_id}",
                            json={"status_override": "did_not_fly"},
                        )
                    except Exception:
                        pass
                    break

    # Rescore
    log.info("Rescoring task id=%d", task_id)
    client.rescore_task(task_id)


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def save_import_state(results: list[ImportResult], output_path: Path) -> None:
    """Save import results mapping to JSON for later comparison."""
    state = {
        "competitions": [
            {
                "name": r.competition_name,
                "event_id": r.event_id,
                "pilot_map": {str(k): v for k, v in r.pilot_map.items()},
                "task_map": {str(k): v for k, v in r.task_map.items()},
                "upload_summary": {str(k): {kk: vv for kk, vv in v.items() if kk != "details"} for k, v in r.upload_summary.items()},
                "errors": r.errors,
                "skipped": r.skipped,
                "skip_reason": r.skip_reason,
            }
            for r in results
        ]
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(state, indent=2, default=str))
    log.info("Saved import state to %s", output_path)


def load_import_state(path: Path) -> list[dict]:
    """Load previously saved import state."""
    data = json.loads(path.read_text())
    return data.get("competitions", [])
