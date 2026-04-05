"""Import FAI competitions into Aervyx via the REST API.

This is a modified version of audit.importer that:
- Accepts per-event timezone (not hardcoded to America/New_York)
- Takes pre-downloaded IGC file directories instead of searching local paths
- Handles Airtribune/CIVLCOMPS checkpoint type mapping
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from audit.api_client import AervyxClient, ApiError
from audit.fsdb_parser import FsdbCompetition, FsdbFormula, FsdbTask, FsdbTurnpoint
from audit.pilot_registry import PilotRegistry
from audit.importer import (
    ImportResult,
    _determine_task_type,
    _extract_time,
    _build_task_points,
    _collect_igc_files,
    _normalize_name,
    save_import_state,
    load_import_state,
)

log = logging.getLogger(__name__)


def _formula_to_event_payload(comp: FsdbCompetition, timezone: str) -> dict:
    """Map FsdbCompetition + formula to Aervyx EventCreate fields."""
    f = comp.formula
    return {
        "name": comp.name,
        "location": comp.location,
        "starts_on": comp.from_date,
        "ends_on": comp.to_date,
        "timezone": timezone,
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


def _build_task_payload_fai(task: FsdbTask, comp_formula: FsdbFormula) -> dict:
    """Build Aervyx TaskInput payload from an FAI task (web-sourced).

    Handles both FSDB-style and Airtribune-style checkpoint definitions.
    """
    task_type = _determine_task_type(task)
    points = _build_task_points(task)

    tps = task.turnpoints
    start_open = _extract_time(task.start_gates[0]) if task.start_gates else (
        _extract_time(tps[0].open_time) if tps else None
    )
    start_close = _extract_time(tps[0].close_time) if tps else None

    task_start = _extract_time(tps[0].open_time) if tps else None
    task_finish = _extract_time(tps[0].close_time) if tps else None

    gate_count = len(task.start_gates) if task.start_gates else 1
    gate_interval = None
    if len(task.start_gates) >= 2:
        try:
            t1 = datetime.fromisoformat(task.start_gates[0])
            t2 = datetime.fromisoformat(task.start_gates[1])
            gate_interval = int((t2 - t1).total_seconds())
        except (ValueError, TypeError):
            gate_interval = 600

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


def _match_igc_to_pilot_by_name(
    igc_file: Path,
    participants: list,
    pilot_map: dict[int, int],
    at_id_to_pilot: dict[str, int] | None = None,
) -> int | None:
    """Match an IGC file to a pilot ID by name matching in the filename.

    Also supports Airtribune participant ID matching via ``at_id_to_pilot``.
    """
    fname_norm = _normalize_name(igc_file.stem)

    # Try Airtribune participant ID matching first
    # Filenames like "LiveTrack Name.ATID.date..." or "LiveTrack NNN.ATID.date..."
    if at_id_to_pilot:
        parts = igc_file.stem.split(".")
        if len(parts) >= 2:
            at_id = parts[1]
            if at_id in at_id_to_pilot:
                return at_id_to_pilot[at_id]

    # Try contest_number matching for numeric filenames (e.g. "0001.igc" -> contest_number 1)
    stem = igc_file.stem.lstrip("0") or "0"
    if stem.isdigit():
        cn = int(stem)
        for p in participants:
            if p.contest_number is not None and p.contest_number == cn:
                aervyx_id = pilot_map.get(p.fsdb_id)
                if aervyx_id is not None:
                    return aervyx_id

    best_score = 0
    best_pilot_id = None

    for p in participants:
        aervyx_id = pilot_map.get(p.fsdb_id)
        if aervyx_id is None:
            continue

        parts = p.name.split()
        first = parts[0].lower() if parts else ""
        last = parts[-1].lower() if len(parts) > 1 else ""

        score = 0
        if first and first in fname_norm:
            score += 30
        if last and last in fname_norm:
            score += 40
        full = _normalize_name(p.name)
        if full and all(tok in fname_norm for tok in full.split()):
            score += 50

        # CIVL ID in filename
        if p.civl_id:
            if p.civl_id in igc_file.stem:
                score += 60

        if score > best_score:
            best_score = score
            best_pilot_id = aervyx_id

    return best_pilot_id if best_score >= 30 else None


def _build_at_id_to_pilot(
    igc_dirs: dict[int, Path],
    participants: list,
    pilot_map: dict[int, int],
) -> dict[str, int]:
    """Build Airtribune participant ID -> Aervyx pilot ID map.

    Uses IGC files that contain pilot names to cross-reference the AT IDs.
    """
    at_id_to_name: dict[str, str] = {}
    for igc_dir in igc_dirs.values():
        if not igc_dir.exists():
            continue
        for f in igc_dir.glob("*.igc"):
            parts = f.stem.split(".")
            if len(parts) >= 2 and parts[0].startswith("LiveTrack "):
                name_part = parts[0].replace("LiveTrack ", "")
                at_id = parts[1]
                # Only store if name_part looks like a name (not a number)
                if not name_part.isdigit() and len(name_part) > 3:
                    at_id_to_name[at_id] = name_part

    # Map name -> aervyx_id
    name_to_aervyx: dict[str, int] = {}
    for p in participants:
        aervyx_id = pilot_map.get(p.fsdb_id)
        if aervyx_id is not None:
            name_to_aervyx[_normalize_name(p.name)] = aervyx_id

    at_id_to_pilot: dict[str, int] = {}
    for at_id, name in at_id_to_name.items():
        norm = _normalize_name(name)
        if norm in name_to_aervyx:
            at_id_to_pilot[at_id] = name_to_aervyx[norm]

    return at_id_to_pilot


def import_fai_competition(
    client: AervyxClient,
    registry: PilotRegistry,
    comp: FsdbCompetition,
    timezone: str,
    igc_dirs: dict[int, Path],  # fsdb_task_id → directory with IGC files
) -> ImportResult:
    """Import a single FAI competition into Aervyx."""
    result = ImportResult(competition_name=comp.name)

    # Check for existing event
    existing_event = None
    try:
        existing_events = client.list_events()
        for ev in existing_events:
            if ev["name"] == comp.name:
                existing_event = ev
                break
    except Exception as exc:
        result.errors.append(f"Failed to list events: {exc}")
        return result

    if existing_event is not None:
        result.event_id = existing_event["id"]
        log.info("Event '%s' already exists (id=%d) — resuming", comp.name, result.event_id)
        _resume_fai_event(client, registry, comp, result, igc_dirs)
        return result

    # 1. Create event
    log.info("Creating event: %s", comp.name)
    try:
        event_payload = _formula_to_event_payload(comp, timezone)
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

    # Build AT ID -> pilot mapping for Airtribune IGC name matching
    at_id_to_pilot = _build_at_id_to_pilot(igc_dirs, comp.participants, result.pilot_map)
    if at_id_to_pilot:
        log.info("Built AT ID mapping for %d pilots", len(at_id_to_pilot))

    # 3. Create and process tasks
    for i, task in enumerate(comp.tasks):
        log.info("Creating task %d/%d: %s", i + 1, len(comp.tasks), task.name)
        try:
            task_payload = _build_task_payload_fai(task, comp.formula)
            task_resp = client.create_task(event_id, task_payload)
            aervyx_task_id = task_resp["id"]
            result.task_map[task.fsdb_id] = aervyx_task_id
            log.info("Created task id=%d", aervyx_task_id)
        except Exception as exc:
            result.errors.append(f"Failed to create task {task.name}: {exc}")
            continue

        # 4. Publish
        try:
            client.publish_task(aervyx_task_id)
        except Exception as exc:
            result.errors.append(f"Failed to publish task {task.name}: {exc}")

        # 5. Upload IGC files
        igc_dir = igc_dirs.get(task.fsdb_id)
        igc_files = _collect_igc_files(igc_dir) if igc_dir else []
        if not igc_files:
            log.warning("No IGC files for task %s", task.name)
            result.upload_summary[task.fsdb_id] = {"matched": 0, "unmatched": 0, "total": 0}
        else:
            matched, unmatched = _upload_igc_files(
                client, aervyx_task_id, igc_files, comp.participants, result.pilot_map,
                at_id_to_pilot,
            )
            result.upload_summary[task.fsdb_id] = {
                "matched": matched, "unmatched": unmatched, "total": len(igc_files),
            }
            log.info("Uploaded %d/%d IGC files for task %s", matched, len(igc_files), task.name)

        # 6. Select uploads and rescore
        try:
            _select_uploads_and_rescore(client, aervyx_task_id, result, task)
        except Exception as exc:
            result.errors.append(f"Failed to score task {task.name}: {exc}")

    return result


def _resume_fai_event(
    client: AervyxClient,
    registry: PilotRegistry,
    comp: FsdbCompetition,
    result: ImportResult,
    igc_dirs: dict[int, Path],
) -> None:
    """Resume an existing FAI event import."""
    event_id = result.event_id

    # Rebuild pilot map
    event_pilots = client.list_event_pilots(event_id)
    pilot_by_name: dict[str, int] = {}
    pilot_by_civl: dict[str, int] = {}
    for ep in event_pilots:
        name_key = f"{ep.get('first_name', '')} {ep.get('last_name', '')}".strip().lower()
        pilot_by_name[name_key] = ep["id"]
        if ep.get("civl_id"):
            pilot_by_civl[ep["civl_id"]] = ep["id"]

    for p in comp.participants:
        if p.civl_id and p.civl_id in pilot_by_civl:
            result.pilot_map[p.fsdb_id] = pilot_by_civl[p.civl_id]
        elif p.name.lower() in pilot_by_name:
            result.pilot_map[p.fsdb_id] = pilot_by_name[p.name.lower()]
        else:
            try:
                aervyx_id = registry.find_or_create(p, event_id)
                result.pilot_map[p.fsdb_id] = aervyx_id
            except Exception as exc:
                result.errors.append(f"Failed to register pilot {p.name}: {exc}")

    log.info("Rebuilt pilot map: %d/%d", len(result.pilot_map), len(comp.participants))

    # Build AT ID -> pilot mapping
    at_id_to_pilot = _build_at_id_to_pilot(igc_dirs, comp.participants, result.pilot_map)

    # Match existing tasks
    existing_tasks = client.list_tasks(event_id)
    task_by_name: dict[str, dict] = {t["name"]: t for t in existing_tasks}

    for i, task in enumerate(comp.tasks):
        aervyx_task = task_by_name.get(task.name)

        if aervyx_task is None:
            # Task doesn't exist yet — create it
            log.info("Creating missing task %d/%d: %s", i + 1, len(comp.tasks), task.name)
            try:
                task_payload = _build_task_payload_fai(task, comp.formula)
                task_resp = client.create_task(event_id, task_payload)
                aervyx_task_id = task_resp["id"]
                result.task_map[task.fsdb_id] = aervyx_task_id
                log.info("Created task id=%d", aervyx_task_id)
            except Exception as exc:
                result.errors.append(f"Failed to create task {task.name}: {exc}")
                continue

            # Publish
            try:
                client.publish_task(aervyx_task_id)
            except Exception as exc:
                result.errors.append(f"Failed to publish task {task.name}: {exc}")

            # Upload IGC
            igc_dir = igc_dirs.get(task.fsdb_id)
            igc_files = _collect_igc_files(igc_dir) if igc_dir else []
            if igc_files:
                matched, unmatched = _upload_igc_files(
                    client, aervyx_task_id, igc_files, comp.participants, result.pilot_map
                )
                result.upload_summary[task.fsdb_id] = {
                    "matched": matched, "unmatched": unmatched, "total": len(igc_files),
                }
                log.info("Uploaded %d/%d IGC files for task %s", matched, len(igc_files), task.name)
        else:
            aervyx_task_id = aervyx_task["id"]
            result.task_map[task.fsdb_id] = aervyx_task_id

            # Check existing uploads
            existing_uploads = client.list_uploads(aervyx_task_id)
            if existing_uploads:
                log.info("Task %s has %d uploads, skipping", task.name, len(existing_uploads))
            else:
                igc_dir = igc_dirs.get(task.fsdb_id)
                igc_files = _collect_igc_files(igc_dir) if igc_dir else []
                if igc_files:
                    matched, unmatched = _upload_igc_files(
                        client, aervyx_task_id, igc_files, comp.participants, result.pilot_map
                    )
                    result.upload_summary[task.fsdb_id] = {
                        "matched": matched, "unmatched": unmatched, "total": len(igc_files),
                    }

        # Rescore
        try:
            _select_uploads_and_rescore(client, aervyx_task_id, result, task)
        except Exception as exc:
            result.errors.append(f"Failed to score task {task.name}: {exc}")


def _upload_igc_files(
    client: AervyxClient,
    task_id: int,
    igc_files: list[Path],
    participants: list,
    pilot_map: dict[int, int],
    at_id_to_pilot: dict[str, int] | None = None,
) -> tuple[int, int]:
    """Upload IGC files one at a time, matching by pilot name."""
    matched = 0
    unmatched = 0

    for igc_file in igc_files:
        pilot_id = _match_igc_to_pilot_by_name(
            igc_file, participants, pilot_map, at_id_to_pilot
        )
        if pilot_id is None:
            unmatched += 1
            continue

        try:
            client.upload_single_igc(task_id, igc_file, pilot_id)
            matched += 1
        except Exception as exc:
            if "duplicate" in str(exc).lower() or "sha256" in str(exc).lower():
                matched += 1
            else:
                log.warning("Upload failed %s: %s", igc_file.name, exc)
                unmatched += 1

    return matched, unmatched


def _select_uploads_and_rescore(
    client: AervyxClient,
    task_id: int,
    result: ImportResult,
    fsdb_task: FsdbTask,
) -> None:
    """Select uploads for scoring and trigger rescore."""
    ops = client.get_scoring_operations(task_id)
    rows = ops.get("rows", [])

    for row in rows:
        pilot_id = row["pilot_id"]
        uploads = row.get("uploads", [])
        if not uploads:
            continue
        upload_id = uploads[0]["id"]
        try:
            client._request(
                "PATCH",
                f"/api/tasks/{task_id}/scoring-inputs/{pilot_id}",
                json={"selected_upload_id": upload_id},
            )
        except Exception as exc:
            log.warning("Failed to select upload for pilot %d: %s", pilot_id, exc)

    # Mark pilots without uploads as absent
    for row in rows:
        pilot_id = row["pilot_id"]
        uploads = row.get("uploads", [])
        if uploads:
            continue
        # Check if this pilot was marked as not flying in the original results
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
                            json={"status_override": "absent"},
                        )
                    except Exception:
                        pass
                    break

    log.info("Rescoring task id=%d", task_id)
    client.rescore_task(task_id)
