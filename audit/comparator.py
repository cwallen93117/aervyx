"""Compare Aervyx scored results against FSDB original results."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from audit.api_client import AervyxClient
from audit.fsdb_parser import FsdbCompetition, FsdbTask, FsdbParticipantResult, FsdbTaskScoreParams

log = logging.getLogger(__name__)


@dataclass
class PilotComparison:
    pilot_name: str = ""
    fsdb_pilot_id: int = 0
    aervyx_pilot_id: int = 0
    # Ranks
    fsdb_rank: int | None = None
    aervyx_rank: int | None = None
    rank_diff: int | None = None
    # Total points
    fsdb_total: float = 0.0
    aervyx_total: float = 0.0
    total_diff: float = 0.0
    # FSDB total minus leading points (for fair comparison)
    fsdb_total_adj: float = 0.0
    total_diff_adj: float = 0.0
    # Component points
    fsdb_distance_pts: float = 0.0
    aervyx_distance_pts: float = 0.0
    distance_diff: float = 0.0
    fsdb_time_pts: float = 0.0
    aervyx_time_pts: float = 0.0
    time_diff: float = 0.0
    fsdb_leading_pts: float = 0.0
    fsdb_arrival_pts: float = 0.0
    aervyx_arrival_pts: float = 0.0
    fsdb_departure_pts: float = 0.0
    aervyx_departure_pts: float = 0.0
    # Distance
    fsdb_distance_km: float = 0.0
    aervyx_distance_km: float = 0.0
    distance_km_diff: float = 0.0
    # Status
    aervyx_status: str = ""
    match_status: str = "unknown"  # exact, close, mismatch, missing


@dataclass
class TaskComparison:
    task_name: str = ""
    fsdb_task_id: int = 0
    aervyx_task_id: int = 0
    # Validity / quality
    fsdb_day_quality: float = 0.0
    aervyx_day_quality: float | None = None
    fsdb_launch_validity: float = 0.0
    fsdb_distance_validity: float = 0.0
    fsdb_time_validity: float = 0.0
    # Available points
    fsdb_avail_distance: float = 0.0
    fsdb_avail_time: float = 0.0
    fsdb_avail_leading: float = 0.0
    aervyx_avail_distance: float | None = None
    aervyx_avail_time: float | None = None
    # Pilots
    pilots: list[PilotComparison] = field(default_factory=list)
    # Stats
    pilots_matched: int = 0
    pilots_missing: int = 0
    mean_abs_error: float = 0.0
    mean_abs_error_adj: float = 0.0
    max_error: float = 0.0
    max_error_adj: float = 0.0
    rank_swaps: int = 0
    exact_matches: int = 0
    close_matches: int = 0
    mismatches: int = 0


@dataclass
class CompetitionComparison:
    name: str = ""
    event_id: int | None = None
    tasks: list[TaskComparison] = field(default_factory=list)
    total_pilots: int = 0
    total_tasks: int = 0
    overall_mean_abs_error: float = 0.0
    overall_mean_abs_error_adj: float = 0.0
    skipped: bool = False
    skip_reason: str = ""
    errors: list[str] = field(default_factory=list)


def compare_competition(
    client: AervyxClient,
    comp: FsdbCompetition,
    pilot_map: dict[int, int],
    task_map: dict[int, int],
) -> CompetitionComparison:
    """Compare a single competition's results."""
    cc = CompetitionComparison(name=comp.name)
    cc.total_tasks = len(comp.tasks)

    # Build reverse pilot map: aervyx_id → fsdb_id
    reverse_pilot = {v: k for k, v in pilot_map.items()}
    # Build fsdb pilot name lookup
    pilot_names = {p.fsdb_id: p.name for p in comp.participants}
    cc.total_pilots = len(comp.participants)

    for fsdb_task in comp.tasks:
        aervyx_task_id = task_map.get(fsdb_task.fsdb_id)
        if aervyx_task_id is None:
            cc.errors.append(f"Task {fsdb_task.name} not in task_map")
            continue

        tc = _compare_task(
            client, fsdb_task, aervyx_task_id, pilot_map, reverse_pilot, pilot_names
        )
        cc.tasks.append(tc)

    # Overall stats
    all_errors = []
    all_errors_adj = []
    for tc in cc.tasks:
        for pc in tc.pilots:
            if pc.match_status != "missing":
                all_errors.append(abs(pc.total_diff))
                all_errors_adj.append(abs(pc.total_diff_adj))
    if all_errors:
        cc.overall_mean_abs_error = sum(all_errors) / len(all_errors)
        cc.overall_mean_abs_error_adj = sum(all_errors_adj) / len(all_errors_adj)

    return cc


def _compare_task(
    client: AervyxClient,
    fsdb_task: FsdbTask,
    aervyx_task_id: int,
    pilot_map: dict[int, int],
    reverse_pilot: dict[int, int],
    pilot_names: dict[int, str],
) -> TaskComparison:
    tc = TaskComparison(
        task_name=fsdb_task.name,
        fsdb_task_id=fsdb_task.fsdb_id,
        aervyx_task_id=aervyx_task_id,
    )

    # FSDB score params
    sp = fsdb_task.score_params
    if sp:
        tc.fsdb_day_quality = sp.day_quality
        tc.fsdb_launch_validity = sp.launch_validity
        tc.fsdb_distance_validity = sp.distance_validity
        tc.fsdb_time_validity = sp.time_validity
        tc.fsdb_avail_distance = sp.available_distance_points
        tc.fsdb_avail_time = sp.available_time_points
        tc.fsdb_avail_leading = sp.available_leading_points

    # Fetch Aervyx results
    try:
        aervyx_results = client.get_task_results(aervyx_task_id)
    except Exception as exc:
        log.warning("Failed to get results for task %d: %s", aervyx_task_id, exc)
        return tc

    # Index Aervyx results by pilot_id
    aervyx_by_pilot: dict[int, dict] = {}
    for r in aervyx_results:
        aervyx_by_pilot[r["pilot_id"]] = r

    # Extract Aervyx day quality from first result's details
    for r in aervyx_results:
        details = r.get("details_json", {})
        gap = details.get("gap", {})
        validity = gap.get("validity", {})
        if validity:
            tc.aervyx_day_quality = validity.get("overall")
            avail = gap.get("available_points", {})
            tc.aervyx_avail_distance = avail.get("distance")
            tc.aervyx_avail_time = avail.get("speed")
            break

    # Compare per pilot
    for fsdb_pr in fsdb_task.participant_results:
        aervyx_id = pilot_map.get(fsdb_pr.fsdb_pilot_id)
        name = pilot_names.get(fsdb_pr.fsdb_pilot_id, f"Pilot #{fsdb_pr.fsdb_pilot_id}")

        pc = PilotComparison(
            pilot_name=name,
            fsdb_pilot_id=fsdb_pr.fsdb_pilot_id,
            aervyx_pilot_id=aervyx_id or 0,
            fsdb_rank=fsdb_pr.rank,
            fsdb_total=fsdb_pr.points,
            fsdb_total_adj=fsdb_pr.points - fsdb_pr.leading_points,
            fsdb_distance_pts=fsdb_pr.distance_points,
            fsdb_time_pts=fsdb_pr.time_points,
            fsdb_leading_pts=fsdb_pr.leading_points,
            fsdb_arrival_pts=fsdb_pr.arrival_points,
            fsdb_departure_pts=fsdb_pr.departure_points,
            fsdb_distance_km=fsdb_pr.distance,
        )

        if aervyx_id is None or aervyx_id not in aervyx_by_pilot:
            pc.match_status = "missing"
            tc.pilots_missing += 1
            tc.pilots.append(pc)
            continue

        ar = aervyx_by_pilot[aervyx_id]
        details = ar.get("details_json", {})
        gap = details.get("gap", {})
        awarded = gap.get("awarded_points", {})

        pc.aervyx_rank = ar.get("rank")
        pc.aervyx_total = ar.get("score_points", 0.0)
        pc.aervyx_status = ar.get("status", "")
        pc.aervyx_distance_km = ar.get("distance_flown_km", 0.0)
        pc.aervyx_distance_pts = awarded.get("distance", 0.0)
        pc.aervyx_time_pts = awarded.get("speed", 0.0)
        pc.aervyx_arrival_pts = awarded.get("arrival", 0.0)
        pc.aervyx_departure_pts = awarded.get("departure", 0.0)

        # Diffs
        pc.total_diff = pc.aervyx_total - pc.fsdb_total
        pc.total_diff_adj = pc.aervyx_total - pc.fsdb_total_adj
        pc.distance_diff = pc.aervyx_distance_pts - pc.fsdb_distance_pts
        pc.time_diff = pc.aervyx_time_pts - pc.fsdb_time_pts
        pc.distance_km_diff = pc.aervyx_distance_km - pc.fsdb_distance_km

        if pc.fsdb_rank is not None and pc.aervyx_rank is not None:
            pc.rank_diff = pc.aervyx_rank - pc.fsdb_rank

        # Classify
        abs_diff_adj = abs(pc.total_diff_adj)
        if abs_diff_adj <= 0.1:
            pc.match_status = "exact"
        elif abs_diff_adj <= 2.0:
            pc.match_status = "close"
        else:
            pc.match_status = "mismatch"

        tc.pilots_matched += 1
        tc.pilots.append(pc)

    # Sort by FSDB rank
    tc.pilots.sort(key=lambda p: (p.fsdb_rank or 9999, p.pilot_name))

    # Aggregate stats
    matched = [p for p in tc.pilots if p.match_status != "missing"]
    if matched:
        errors = [abs(p.total_diff) for p in matched]
        errors_adj = [abs(p.total_diff_adj) for p in matched]
        tc.mean_abs_error = sum(errors) / len(errors)
        tc.mean_abs_error_adj = sum(errors_adj) / len(errors_adj)
        tc.max_error = max(errors)
        tc.max_error_adj = max(errors_adj)
        tc.rank_swaps = sum(1 for p in matched if p.rank_diff is not None and p.rank_diff != 0)
        tc.exact_matches = sum(1 for p in matched if p.match_status == "exact")
        tc.close_matches = sum(1 for p in matched if p.match_status == "close")
        tc.mismatches = sum(1 for p in matched if p.match_status == "mismatch")

    return tc
