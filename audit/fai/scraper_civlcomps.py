"""Scrape CIVLCOMPS competitions into FsdbCompetition dataclasses.

CIVLCOMPS embeds all data in HTML result pages:
- Event metadata from the results overview page
- Task definitions, scoring params, and pilot results from individual task pages
- IGC download links from the result pages
"""
from __future__ import annotations

import logging
import re

from audit.fsdb_parser import (
    FsdbCompetition, FsdbFormula, FsdbParticipant, FsdbParticipantResult,
    FsdbTask, FsdbTaskScoreParams, FsdbTurnpoint,
)
from audit.fai.event_catalog import FaiEvent
from audit.fai.scraper_common import fetch_page, parse_scoring_params_from_text

log = logging.getLogger(__name__)

CIVLCOMPS_BASE = "https://civlcomps.org"


def scrape_event(event: FaiEvent) -> FsdbCompetition:
    """Scrape a full competition from CIVLCOMPS into FsdbCompetition."""
    slug = event.civl_slug or event.slug
    log.info("Scraping CIVLCOMPS event: %s (%s)", event.name, slug)

    comp = FsdbCompetition(
        name=event.name,
        discipline=event.discipline,
    )

    # 1. Discover task result URLs from the results overview page
    results_url = f"{CIVLCOMPS_BASE}/event/{slug}/results"
    html = fetch_page(results_url)
    task_urls = _discover_task_urls(html, slug)
    log.info("  Found %d task result URLs", len(task_urls))

    if not task_urls:
        log.warning("  No task URLs found for %s", slug)
        return comp

    # 2. Scrape each task result page
    all_pilots: dict[str, FsdbParticipant] = {}  # name → participant

    for task_num, task_url in enumerate(task_urls, 1):
        log.info("  Scraping task %d: %s", task_num, task_url)
        try:
            task_html = fetch_page(task_url)
            task = _parse_task_page(task_html, task_num, task_url, all_pilots)
            comp.tasks.append(task)

            # Set formula from first task
            if task_num == 1:
                comp.formula = task.formula

            # Check for IGC download link
            igc_url = _find_igc_download(task_html, slug)
            if igc_url:
                event.igc_urls[task.fsdb_id] = igc_url

        except Exception as exc:
            log.warning("  Failed to scrape task %d: %s", task_num, exc)

    # Build participant list from all discovered pilots
    comp.participants = list(all_pilots.values())
    log.info("  %d total pilots, %d tasks", len(comp.participants), len(comp.tasks))

    # Extract event metadata from first task page if available
    if comp.tasks:
        _extract_event_metadata(comp, html)

    return comp


def _discover_task_urls(html: str, slug: str) -> list[str]:
    """Find overall task result URLs from the results overview page.

    Filters to only task-level 'Overall' results (not competition-level,
    not Female/Serial/Sport categories).
    """
    # Find all result links with their labels
    # Pattern: <a href="/event/{slug}/results/{hash}">Label</a>
    link_pattern = re.compile(
        rf'<a[^>]+href=["\'](?:https?://civlcomps\.org)?(/event/{re.escape(slug)}/results/([a-f0-9]+))["\'][^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )

    overall_hashes = []
    seen = set()
    for m in link_pattern.finditer(html):
        path = m.group(1)
        hash_val = m.group(2)
        label = re.sub(r'<[^>]+>', '', m.group(3)).strip().lower()

        if hash_val in seen:
            continue
        seen.add(hash_val)

        # Only keep "overall" links
        if label == "overall":
            overall_hashes.append(hash_val)

    # The last "overall" might be competition-level (not task-level).
    # Verify by checking if the page has task_distance.
    # For efficiency, only check the last one if there are 3+.
    urls = [f"{CIVLCOMPS_BASE}/event/{slug}/results/{h}" for h in overall_hashes]

    # Filter to only task-level results (have task_distance in HTML)
    # Competition-level and cumulative results don't have task_distance
    if len(urls) > 8:
        # Many "Overall" links — need to verify each one
        # For efficiency, take every other one (first of each pair = day result)
        task_urls = []
        for i, url in enumerate(urls):
            try:
                html_check = fetch_page(url)
                if "task_distance" in html_check:
                    task_urls.append(url)
            except Exception:
                pass
        urls = task_urls

    elif len(urls) >= 3:
        # Check last URL — if it's a competition result, remove it
        try:
            last_html = fetch_page(urls[-1])
            if "task_distance" not in last_html:
                urls = urls[:-1]
        except Exception:
            pass

    return urls


def _parse_task_page(
    html: str,
    task_num: int,
    task_url: str,
    all_pilots: dict[str, FsdbParticipant],
) -> FsdbTask:
    """Parse a CIVLCOMPS task result page into an FsdbTask."""
    task = FsdbTask(
        fsdb_id=task_num,  # Use sequential IDs
        name=f"Task {task_num}",
    )

    # Extract task name from page title
    title_m = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL)
    if title_m:
        title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
        if title:
            task.name = title.split(" - ")[0].strip() if " - " in title else f"Task {task_num}"

    # Parse scoring parameters
    params = parse_scoring_params_from_text(html)
    if params:
        task.formula = _params_to_formula(params)
        task.score_params = _params_to_score_params(params)

    # Parse turnpoints
    turnpoints = _parse_turnpoints(html)
    if turnpoints:
        task.turnpoints = turnpoints
        # Determine ss/es from turnpoint types
        for i, tp in enumerate(turnpoints):
            tp_type = getattr(tp, '_tp_type', None)
            if tp_type == "start":
                task.ss = i + 1
            elif tp_type == "ess":
                task.es = i + 1
            elif tp_type == "goal" and task.es == 0:
                task.es = i + 1

    # Parse start gates
    gates = _parse_start_gates(html)
    if gates:
        task.start_gates = gates

    # Parse pilot results
    task.participant_results = _parse_pilot_results(html, all_pilots)
    log.info("    %d pilot results", len(task.participant_results))

    return task


def _parse_turnpoints(html: str) -> list[FsdbTurnpoint]:
    """Parse turnpoint definitions from a CIVLCOMPS/Airtribune fs_res table.

    Table format: No, Leg Dist., Id, Radius, Open, Close, Coordinates, Altitude
    The SS/ES markers appear in the first column (e.g. "2 SS", "6 ES").
    """
    turnpoints = []

    # Find fs_res tables and look for the one with turnpoint data
    tables = re.findall(r'<table[^>]*class="fs_res"[^>]*>(.*?)</table>', html, re.DOTALL)

    tp_table = None
    for t in tables:
        if 'Radius' in t or 'radius' in t or 'Coordinates' in t:
            tp_table = t
            break

    if not tp_table:
        return turnpoints

    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tp_table, re.DOTALL)
    ss_idx = 0
    es_idx = 0

    for row in rows[1:]:  # skip header
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        if len(cells) < 4:
            continue

        tp = FsdbTurnpoint()

        # First cell: "1", "2 SS", "6 ES", "7", "8 Goal"
        first = cells[0]
        try:
            num = int(re.match(r'(\d+)', first).group(1))
        except (AttributeError, ValueError):
            continue

        first_lower = first.lower()
        tp_type = "turnpoint"
        if " ss" in first_lower:
            tp_type = "start"
            ss_idx = num
        elif " es" in first_lower:
            tp_type = "ess"
            es_idx = num
        elif "goal" in first_lower:
            tp_type = "goal"
        elif num == 1:
            tp_type = "takeoff"

        tp._tp_type = tp_type  # type: ignore[attr-defined]

        # Name/ID (typically 3rd column)
        if len(cells) > 2:
            tp.code = cells[2].strip()

        # Radius (typically 4th column)
        for c in cells:
            m = re.match(r'^(\d+)\s*m$', c.strip())
            if m:
                tp.radius = float(m.group(1))
                break

        # Coordinates: "Lat: -20.60355 Lon: -41.08582"
        for c in cells:
            coord_m = re.search(r'Lat:\s*(-?[\d.]+)\s*Lon:\s*(-?[\d.]+)', c)
            if coord_m:
                tp.lat = float(coord_m.group(1))
                tp.lon = float(coord_m.group(2))
                break

        # Altitude
        for c in cells:
            alt_m = re.match(r'^(\d+)\s*m$', c.strip())
            if alt_m and float(alt_m.group(1)) != tp.radius:
                tp.altitude = float(alt_m.group(1))

        # Open/Close times
        for c in cells:
            time_m = re.match(r'^(\d{1,2}:\d{2})$', c.strip())
            if time_m:
                if not tp.open_time:
                    tp.open_time = time_m.group(1) + ":00"
                elif not tp.close_time:
                    tp.close_time = time_m.group(1) + ":00"

        turnpoints.append(tp)

    return turnpoints


def _parse_tp_row(cells: list[str]) -> FsdbTurnpoint | None:
    """Parse a single turnpoint row from table cells."""
    # Cells typically: [leg/num, type, name/id, distance, radius, open-close, coords, altitude]
    tp = FsdbTurnpoint()

    # Find the type cell
    type_map = {
        "launch": "takeoff", "takeoff": "takeoff", "to": "takeoff",
        "start": "start", "ss": "start",
        "tp": "turnpoint", "turnpoint": "turnpoint",
        "ess": "ess", "es": "ess", "end": "ess", "energy": "ess",
        "goal": "goal", "finish": "goal",
    }

    tp_type = None
    for cell in cells:
        cell_lower = cell.lower().strip()
        for key, val in type_map.items():
            if key in cell_lower:
                tp_type = val
                break
        if tp_type:
            break

    if tp_type is None:
        return None

    # Store type as internal attribute for ss/es detection
    tp._tp_type = tp_type  # type: ignore[attr-defined]

    # Find name
    for cell in cells:
        if cell and not cell.replace(".", "").replace("-", "").isdigit() and len(cell) < 20:
            if cell.lower() not in type_map:
                tp.code = cell
                break

    # Find coordinates
    for cell in cells:
        coords = re.findall(r'(-?\d+\.\d{3,})', cell)
        if len(coords) >= 2:
            tp.lat = float(coords[0])
            tp.lon = float(coords[1])
            break

    # Find radius
    for cell in cells:
        m = re.match(r'^(\d+)\s*m?$', cell.strip())
        if m:
            tp.radius = float(m.group(1))
            break

    # Find altitude
    for cell in cells:
        m = re.match(r'^(\d+)\s*m?\s*$', cell.strip())
        if m and float(m.group(1)) > 50 and float(m.group(1)) != tp.radius:
            tp.altitude = float(m.group(1))

    return tp


def _parse_start_gates(html: str) -> list[str]:
    """Parse start gate times from the page."""
    gates = []
    # Look for start time or gate patterns
    m = re.search(r'[Ss]tart\s*(?:time|gate)?[:\s]+(\d{1,2}:\d{2}(?::\d{2})?)', html)
    if m:
        gate_time = m.group(1)
        if len(gate_time.split(":")) == 2:
            gate_time += ":00"
        gates.append(gate_time)
    return gates


def _parse_pilot_results(
    html: str,
    all_pilots: dict[str, FsdbParticipant],
) -> list[FsdbParticipantResult]:
    """Parse pilot results from a CIVLCOMPS task result page.

    Uses the same fs_res table format as Airtribune:
    #, Id, Name, [Gender], Nat, Glider, Sponsor, SS, ES, Time, Speed, Distance, Dist.Points, Lead.Points, TimePoints, Total
    """
    results = []

    # Find fs_res tables
    tables = re.findall(r'<table[^>]*class="fs_res"[^>]*>(.*?)</table>', html, re.DOTALL)
    if not tables:
        return results

    # The pilot results table is the largest one
    pilot_table = max(tables, key=lambda t: t.count('<tr'))

    # Detect column order from header row
    header_match = re.search(r'<tr[^>]*>(.*?)</tr>', pilot_table, re.DOTALL)
    if not header_match:
        return results

    header_cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', header_match.group(1), re.DOTALL)
    header_cells = [re.sub(r'<[^>]+>', '', c).strip().lower() for c in header_cells]

    col_map = {}
    for i, h in enumerate(header_cells):
        if h in ('#', 'rank'):
            col_map['rank'] = i
        elif h in ('name',):
            col_map['name'] = i
        elif h in ('id',):
            col_map['pilot_id'] = i
        elif 'dist.point' in h or 'dist point' in h:
            col_map['dist_pts'] = i
        elif 'lead' in h:
            col_map['lead_pts'] = i
        elif 'time' in h and 'point' in h:
            col_map['time_pts'] = i
        elif 'total' in h:
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

        rank_idx = col_map.get('rank', 0)
        try:
            rank = int(cells[rank_idx])
        except (ValueError, IndexError):
            continue

        name_idx = col_map.get('name', 2)
        name = cells[name_idx] if name_idx < len(cells) else ""
        if not name:
            continue

        pilot_id = _get_or_create_pilot(name, all_pilots)

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


def _get_or_create_pilot(name: str, all_pilots: dict[str, FsdbParticipant]) -> int:
    """Get or create a pilot in the shared pilots dict. Returns fsdb_id."""
    key = name.lower().strip()
    if key in all_pilots:
        return all_pilots[key].fsdb_id

    # Assign sequential IDs starting from 1
    new_id = len(all_pilots) + 1
    parts = name.split()
    all_pilots[key] = FsdbParticipant(
        fsdb_id=new_id,
        name=name,
        nation="",
    )
    return new_id


def _find_igc_download(html: str, slug: str) -> str | None:
    """Find the IGC download link on a result page."""
    # CIVLCOMPS pattern: /event/download-file?filename=HASH.zip
    m = re.search(r'/event/download-file\?filename=([a-f0-9]+\.zip)', html)
    if m:
        return f"{CIVLCOMPS_BASE}{m.group(0)}"

    # Also check for direct download links
    m = re.search(r'href=["\']([^"\']*\.zip)["\']', html, re.IGNORECASE)
    if m:
        url = m.group(1)
        if url.startswith("/"):
            url = f"{CIVLCOMPS_BASE}{url}"
        return url

    return None


def _extract_event_metadata(comp: FsdbCompetition, overview_html: str) -> None:
    """Extract event dates and location from the results overview page."""
    # Try to find dates
    date_m = re.search(r'(\d{4}-\d{2}-\d{2})\s*(?:to|[-–])\s*(\d{4}-\d{2}-\d{2})', overview_html)
    if date_m:
        comp.from_date = date_m.group(1)
        comp.to_date = date_m.group(2)

    # Try to find location
    loc_m = re.search(r'(?:location|venue)[:\s]+([^<\n]+)', overview_html, re.IGNORECASE)
    if loc_m:
        comp.location = loc_m.group(1).strip()


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
