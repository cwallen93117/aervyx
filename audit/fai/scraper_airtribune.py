"""Scrape Airtribune competitions into FsdbCompetition dataclasses.

Uses:
- JSON API for event metadata, tasks, participants
- HTML result pages for scoring formula params, task stats, pilot results
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from audit.fsdb_parser import (
    FsdbCompetition, FsdbFormula, FsdbParticipant, FsdbParticipantResult,
    FsdbTask, FsdbTaskScoreParams, FsdbTurnpoint,
)
from audit.fai.event_catalog import FaiEvent
from audit.fai.scraper_common import fetch_json, fetch_page, parse_scoring_params_from_text

log = logging.getLogger(__name__)

AIRTRIBUNE_API = "https://airtribune.com/api"
AIRTRIBUNE_BASE = "https://airtribune.com"


def scrape_event(event: FaiEvent) -> FsdbCompetition:
    """Scrape a full competition from Airtribune into FsdbCompetition."""
    cid = event.contest_id
    if cid is None:
        raise ValueError(f"No contest_id for Airtribune event {event.name}")

    log.info("Scraping Airtribune contest %d: %s", cid, event.name)

    # 1. Event metadata
    contest_data = fetch_json(f"{AIRTRIBUNE_API}/contest/{cid}")
    comp = FsdbCompetition(
        name=contest_data.get("name", event.name),
        location=_extract_location(contest_data),
        from_date=contest_data.get("start_date", "")[:10],
        to_date=contest_data.get("end_date", "")[:10],
        utc_offset=0,
        discipline=event.discipline,
    )

    # 2. Participants
    participants = fetch_json(f"{AIRTRIBUNE_API}/contest/{cid}/participants")
    for p in participants:
        status = p.get("confirmation_status", "")
        if status not in ("confirmed", ""):
            continue
        comp.participants.append(FsdbParticipant(
            fsdb_id=p["id"],
            name=f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
            civl_id=str(p.get("civl_id", "")) if p.get("civl_id") else "",
            nation=_extract_nation(p),
            glider=f"{p.get('glider_manufacturer', '')} {p.get('glider_model', '')}".strip(),
            female=p.get("gender", "M") == "F",
            contest_number=p.get("contest_number"),
        ))
    log.info("  %d confirmed participants", len(comp.participants))

    # 3. Tasks
    tasks_data = fetch_json(f"{AIRTRIBUNE_API}/contest/{cid}/tasks")
    # 4. Results metadata (for URLs and IGC download links)
    results_meta = fetch_json(f"{AIRTRIBUNE_API}/contest/{cid}/results")
    results_by_task = {}
    igc_by_task = {}
    slug = contest_data.get("url", "").strip("/")
    # Results API returns {"tasks": [...], "user_results": [...], ...}
    results_tasks = results_meta.get("tasks", []) if isinstance(results_meta, dict) else results_meta
    for item in results_tasks:
        # Collect all result URLs from user_results (day-level per-task scores)
        # Prefer user_results (day/) over competition_results (comp/) since day/
        # pages contain per-pilot point breakdowns (dist, lead, time, speed).
        all_result_urls: list[str] = []
        for ur in item.get("user_results", []):
            url = ur.get("url", "") if isinstance(ur, dict) else str(ur)
            if url:
                all_result_urls.append(url)

        # Pick best result URL: prefer "overall", then "open", then any
        for url in all_result_urls:
            m = re.search(r'/task(\d+)/', url)
            if not m:
                continue
            tid = int(m.group(1))
            full_url = f"{AIRTRIBUNE_BASE}{url}" if url.startswith("/") else url
            if tid not in results_by_task or "/overall" in url:
                results_by_task[tid] = full_url
            if "/overall" in url:
                break  # Best possible match

        # IGC tracks URL
        tracks_url = item.get("tracks", "")
        if tracks_url:
            for url in all_result_urls:
                m = re.search(r'/task(\d+)/', url)
                if m:
                    igc_by_task[int(m.group(1))] = tracks_url
                    break

    for i, td in enumerate(tasks_data):
        tid = td["id"]
        task = _build_task(td, i + 1, comp.participants)

        # Store IGC URL for later download
        if tid in igc_by_task:
            event.igc_urls[tid] = igc_by_task[tid]

        # Scrape result page for formula params and pilot results
        result_url = results_by_task.get(tid)
        if result_url is None:
            # Try constructing the URL — day/open has per-pilot point breakdowns
            result_url = f"{AIRTRIBUNE_BASE}/{slug}/results/task{tid}/day/open"

        try:
            _enrich_task_from_results(task, result_url, comp.participants)
        except Exception as exc:
            log.warning("  Failed to scrape results for task %d: %s", tid, exc)

        # Set formula from first task's scraped params (or use defaults)
        if i == 0 and task.formula.id != "GAP2021":
            comp.formula = task.formula

        comp.tasks.append(task)

    log.info("  %d tasks scraped", len(comp.tasks))
    return comp


def _extract_location(data: dict) -> str:
    loc = data.get("location", {})
    if isinstance(loc, dict):
        return f"{loc.get('city', '')}, {loc.get('country', {}).get('name', '')}".strip(", ")
    return str(loc) if loc else ""


def _extract_nation(p: dict) -> str:
    country = p.get("country", {})
    if isinstance(country, dict):
        return country.get("ioc_code", country.get("code", ""))
    return ""


# Airtribune checkpoint type → our point_type mapping
_CHECKPOINT_TYPE_MAP = {
    "to": None,  # takeoff — skip
    "ss": "start",
    "tp": "turnpoint",
    "es": "ess",
    "goal": "goal",
}


def _build_task(td: dict, task_num: int, participants: list[FsdbParticipant]) -> FsdbTask:
    """Build an FsdbTask from Airtribune task JSON."""
    task = FsdbTask(
        fsdb_id=td["id"],
        name=td.get("title", td.get("long_title", f"Task {task_num}")),
    )

    checkpoints = td.get("checkpoints", [])
    ss_idx = 0
    es_idx = 0
    tp_index = 0  # Tracks position excluding takeoff points
    for ci, cp in enumerate(checkpoints):
        cp_type = cp.get("type", "tp")

        # Skip takeoff points — they're not part of the scored route
        if cp_type == "to":
            continue

        tp_index += 1  # 1-based index for FSDB convention
        if cp_type == "ss":
            ss_idx = tp_index
        elif cp_type == "es":
            es_idx = tp_index

        task.turnpoints.append(FsdbTurnpoint(
            code=cp.get("name", f"TP{ci}"),
            lat=cp.get("lat", 0.0),
            lon=cp.get("lon", 0.0),
            altitude=cp.get("altitude", 0.0),
            radius=cp.get("radius", 400.0),
            open_time=cp.get("open_time", cp.get("open", "")),
            close_time=cp.get("close_time", cp.get("close", "")),
        ))

    task.ss = ss_idx if ss_idx else 1
    task.es = es_idx if es_idx else len(task.turnpoints)

    # Start gates from the SS checkpoint open time
    if checkpoints and ss_idx > 0:
        ss_cp = checkpoints[ss_idx - 1]
        if ss_cp.get("open"):
            task.start_gates.append(ss_cp["open"])

    # Also check for start_time in task data (may be separate from checkpoint open)
    start_time = td.get("start_time")
    if start_time and not task.start_gates:
        task.start_gates.append(start_time)

    return task


def _enrich_task_from_results(
    task: FsdbTask,
    result_url: str,
    participants: list[FsdbParticipant],
) -> None:
    """Scrape an Airtribune result page to get formula params, stats, and pilot results."""
    log.info("  Scraping results from %s", result_url)
    html = fetch_page(result_url)
    text = html  # We'll search both HTML and text content

    params = parse_scoring_params_from_text(text)
    if not params:
        log.warning("  No scoring params found in result page")
        return

    # Build formula
    formula = _params_to_formula(params)
    task.formula = formula

    # Build score params
    task.score_params = _params_to_score_params(params)

    # Parse pilot results from the page
    pilot_results = _parse_pilot_results(html, participants)
    task.participant_results = pilot_results
    log.info("  Parsed %d pilot results", len(pilot_results))


def _params_to_formula(params: dict) -> FsdbFormula:
    """Convert scraped params dict to FsdbFormula."""
    def _f(key: str, default: float = 0.0) -> float:
        try:
            return float(params.get(key, default))
        except (ValueError, TypeError):
            return default

    def _b(key: str) -> bool:
        return params.get(key) in ("1", "true", "True")

    return FsdbFormula(
        id=params.get("id", "GAP2023"),
        min_dist=_f("min_dist", 5.0),
        nom_dist=_f("nom_dist", 60.0),
        nom_time=_f("nom_time", 1.5),
        nom_launch=_f("nom_launch", 0.95),
        nom_goal=_f("nom_goal", 0.3),
        score_back_time=int(_f("score_back_time", 5)),
        bonus_gr=_f("bonus_gr", 0.0),
        use_distance_points=_b("use_distance_points") if "use_distance_points" in params else True,
        use_time_points=_b("use_time_points") if "use_time_points" in params else True,
        use_leading_points=_b("use_leading_points") if "use_leading_points" in params else True,
        use_arrival_position_points=_b("use_arrival_position_points"),
        use_arrival_time_points=_b("use_arrival_time_points"),
        use_departure_points=_b("use_departure_points"),
        use_difficulty_for_distance_points=_b("use_difficulty_for_distance_points"),
        use_semi_circle_control_zone_for_goal_line=_b("use_semi_circle_control_zone_for_goal_line") if "use_semi_circle_control_zone_for_goal_line" in params else True,
        use_proportional_leading_weight_if_nobody_in_goal=_b("use_proportional_leading_weight_if_nobody_in_goal"),
        use_constant_leading_weight=_b("use_constant_leading_weight"),
        use_flat_decline_of_timepoints=_b("use_flat_decline_of_timepoints"),
        redistribute_removed_time_points_as_distance_points=_b("redistribute_removed_time_points_as_distance_points"),
        time_points_if_not_in_goal=_f("time_points_if_not_in_goal", 1.0),
        leading_weight_factor=_f("leading_weight", 1.0) if "leading_weight" in params else 1.0,
    )


def _params_to_score_params(params: dict) -> FsdbTaskScoreParams:
    """Convert scraped params dict to FsdbTaskScoreParams."""
    def _f(key: str, default: float = 0.0) -> float:
        try:
            return float(params.get(key, default))
        except (ValueError, TypeError):
            return default

    def _i(key: str, default: int = 0) -> int:
        try:
            return int(float(params.get(key, default)))
        except (ValueError, TypeError):
            return default

    return FsdbTaskScoreParams(
        ss_distance=_f("ss_distance"),
        task_distance=_f("task_distance"),
        day_quality=_f("day_quality"),
        launch_validity=_f("launch_validity"),
        distance_validity=_f("distance_validity"),
        time_validity=_f("time_validity"),
        stop_validity=_f("stop_validity", 1.0),
        available_distance_points=_f("available_points_distance"),
        available_time_points=_f("available_points_time"),
        available_leading_points=_f("available_points_leading"),
        available_arrival_points=_f("available_points_arrival"),
        best_dist=_f("best_dist"),
        goal_ratio=_f("goalratio"),
        no_of_pilots_present=_i("no_of_pilots_present"),
        no_of_pilots_flying=_i("no_of_pilots_flying"),
        no_of_pilots_reaching_goal=_i("no_of_pilots_reaching_goal"),
        no_of_pilots_reaching_es=_i("no_of_pilots_reaching_es"),
        no_of_pilots_in_competition=_i("no_of_pilots_in_competition"),
        distance_weight=_f("distance_weight"),
        time_weight=_f("time_weight"),
    )


def _parse_pilot_results(html: str, participants: list[FsdbParticipant]) -> list[FsdbParticipantResult]:
    """Parse pilot results from an FS-style HTML result page.

    Table format (both CIVLCOMPS and Airtribune):
    #, Id, Name, [Gender], Nat, Glider, Sponsor, SS, ES, Time, Speed, Distance, Dist.Points, Lead.Points, TimePoints, Total
    """
    results = []

    # Build name → fsdb_id lookup (multiple keys per pilot for robust matching)
    name_to_id: dict[str, int] = {}
    for p in participants:
        name_to_id[p.name.lower()] = p.fsdb_id
        parts = p.name.split()
        if len(parts) >= 2:
            name_to_id[f"{parts[0]} {parts[-1]}".lower()] = p.fsdb_id

    # Find the first fs_res table (pilot results)
    tables = re.findall(r'<table[^>]*class="fs_res"[^>]*>(.*?)</table>', html, re.DOTALL)
    if not tables:
        # Some Airtribune pages use plain tables or class="result" tables.
        # Fall back: find any table containing score-related headers.
        all_tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL)
        for t in all_tables:
            t_lower = t.lower()
            if ('totalpoints' in t_lower or 'total' in re.sub(r'<[^>]+>', '', t_lower)) and (
                'dist' in t_lower and 'name' in t_lower
            ):
                tables = [t]
                break
        if not tables:
            # Last resort: look for header rows with Rank/Name embedded in the page
            header_match = re.search(
                r'<tr[^>]*>\s*<th[^>]*>(?:Rank|#)</th>.*?<th[^>]*>Name</th>.*?</tr>',
                html, re.DOTALL | re.IGNORECASE,
            )
            if header_match:
                tables = [html[header_match.start():]]
    if not tables:
        return results

    # The pilot results table is the largest one (most rows)
    pilot_table = max(tables, key=lambda t: t.count('<tr'))

    # Detect column order from header row
    header_match = re.search(r'<tr[^>]*>(.*?)</tr>', pilot_table, re.DOTALL)
    if not header_match:
        return results

    header_cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', header_match.group(1), re.DOTALL)
    header_cells = [re.sub(r'<[^>]+>', '', c).strip().lower() for c in header_cells]

    # Map column names to indices
    col_map = {}
    for i, h in enumerate(header_cells):
        if h in ('#', 'rank'):
            col_map['rank'] = i
        elif h in ('name',):
            col_map['name'] = i
        elif h in ('id',):
            col_map['pilot_id'] = i
        elif 'dist.point' in h or 'dist point' in h or h == 'dst p':
            col_map['dist_pts'] = i
        elif 'lead' in h or h == 'lo p':
            col_map['lead_pts'] = i
        elif ('time' in h and 'point' in h) or h == 'spd p' or h == 'timepoints':
            col_map['time_pts'] = i
        elif h in ('total', 'score', 'totalpoints'):
            col_map['total'] = i
        elif 'distance' in h and 'point' not in h:
            col_map['distance'] = i
        elif 'speed' in h:
            col_map['speed'] = i

    # Parse data rows
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', pilot_table, re.DOTALL)
    for row in rows[1:]:  # skip header
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        if len(cells) < 5:
            continue

        # Get rank
        rank_idx = col_map.get('rank', 0)
        try:
            rank = int(cells[rank_idx])
        except (ValueError, IndexError):
            continue

        # Get name
        name_idx = col_map.get('name', 2)
        name = cells[name_idx] if name_idx < len(cells) else ""
        pilot_id = _match_name_to_pilot(name, name_to_id)
        if pilot_id is None:
            continue

        pr = FsdbParticipantResult(
            fsdb_pilot_id=pilot_id,
            rank=rank,
            present=True,
            had_flight_data=True,
        )

        def _safe_float(idx: int | None) -> float:
            if idx is None or idx >= len(cells):
                return 0.0
            try:
                return float(cells[idx].replace(",", ""))
            except ValueError:
                return 0.0

        pr.points = _safe_float(col_map.get('total'))
        pr.distance_points = _safe_float(col_map.get('dist_pts'))
        pr.leading_points = _safe_float(col_map.get('lead_pts'))
        pr.time_points = _safe_float(col_map.get('time_pts'))
        pr.distance = _safe_float(col_map.get('distance'))

        results.append(pr)

    return results


def _match_name_to_pilot(name: str, name_to_id: dict[str, int]) -> int | None:
    """Match a name string to a participant ID."""
    name_lower = name.lower().strip()
    if name_lower in name_to_id:
        return name_to_id[name_lower]

    # Try partial match — check if any registered name is contained in this name
    for registered_name, pid in name_to_id.items():
        if registered_name in name_lower or name_lower in registered_name:
            return pid

    # Try matching with just first + last name
    parts = name_lower.split()
    if len(parts) >= 2:
        key = f"{parts[0]} {parts[-1]}"
        if key in name_to_id:
            return name_to_id[key]

    return None
