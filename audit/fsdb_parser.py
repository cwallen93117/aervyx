"""Parse FS scoring database (.fsdb) XML files into structured dataclasses."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FsdbFormula:
    id: str = "GAP2021"
    min_dist: float = 5.0
    nom_dist: float = 60.0
    nom_time: float = 1.5
    nom_launch: float = 0.95
    nom_goal: float = 0.3
    day_quality_override: float = 0.0
    bonus_gr: float = 0.0
    jump_the_gun_factor: float = 0.0
    jump_the_gun_max: int = 0
    normalize_1000_before_day_quality: bool = False
    time_points_if_not_in_goal: float = 1.0
    use_1000_points_for_max_day_quality: bool = False
    use_arrival_position_points: bool = False
    use_arrival_time_points: bool = False
    use_departure_points: bool = False
    use_difficulty_for_distance_points: bool = True
    use_distance_points: bool = True
    use_distance_squared_for_lc: bool = False
    use_leading_points: bool = True
    use_semi_circle_control_zone_for_goal_line: bool = True
    use_time_points: bool = True
    scoring_altitude: str = "GPS"
    final_glide_decelerator: str = "none"
    no_final_glide_decelerator_reason: str = ""
    min_time_span_for_valid_task: int = 60
    score_back_time: int = 15
    use_proportional_leading_weight_if_nobody_in_goal: bool = True
    leading_weight_factor: float = 1.0
    turnpoint_radius_tolerance: float = 0.0005
    turnpoint_radius_minimum_absolute_tolerance: float = 5.0
    number_of_decimals_task_results: int = 2
    number_of_decimals_competition_results: int = 1
    redistribute_removed_time_points_as_distance_points: bool = False
    use_best_score_for_ftv_validity: bool = True
    use_constant_leading_weight: bool = False
    use_pwca2019_for_lc: bool = False
    use_flat_decline_of_timepoints: bool = False
    # GAP2011-era extras
    no_pilots_in_goal_factor: float = 1.0
    task_stopped_factor: float = 1.0
    time_validity_based_on_pilot_with_speed_rank: int = 1


@dataclass
class FsdbParticipant:
    fsdb_id: int = 0
    name: str = ""
    civl_id: str = ""
    nation: str = ""
    glider: str = ""
    female: bool = False


@dataclass
class FsdbTurnpoint:
    code: str = ""
    lat: float = 0.0
    lon: float = 0.0
    altitude: float = 0.0
    radius: float = 400.0
    open_time: str = ""
    close_time: str = ""


@dataclass
class FsdbParticipantResult:
    fsdb_pilot_id: int = 0
    rank: int | None = None
    points: float = 0.0
    distance: float = 0.0
    distance_points: float = 0.0
    linear_distance_points: float = 0.0
    difficulty_distance_points: float = 0.0
    time_points: float = 0.0
    arrival_points: float = 0.0
    departure_points: float = 0.0
    leading_points: float = 0.0
    penalty: float = 0.0
    penalty_points: float = 0.0
    penalty_reason: str = ""
    ss_time: str = ""
    tracklog_filename: str = ""
    started_ss: str = ""
    finished_ss: str = ""
    real_distance: float = 0.0
    got_time_but_not_goal_penalty: bool = False
    # Whether the pilot had any flight data at all
    had_flight_data: bool = False
    # Whether pilot was listed as present (had a participant entry in task)
    present: bool = True


@dataclass
class FsdbTaskScoreParams:
    ss_distance: float = 0.0
    task_distance: float = 0.0
    day_quality: float = 0.0
    launch_validity: float = 0.0
    distance_validity: float = 0.0
    time_validity: float = 0.0
    stop_validity: float = 1.0
    available_distance_points: float = 0.0
    available_time_points: float = 0.0
    available_leading_points: float = 0.0
    available_arrival_points: float = 0.0
    available_departure_points: float = 0.0
    best_dist: float = 0.0
    best_time: float = 0.0
    goal_ratio: float = 0.0
    no_of_pilots_present: int = 0
    no_of_pilots_flying: int = 0
    no_of_pilots_reaching_goal: int = 0
    no_of_pilots_reaching_es: int = 0
    no_of_pilots_in_competition: int = 0
    distance_weight: float = 0.0
    time_weight: float = 0.0


@dataclass
class FsdbTask:
    fsdb_id: int = 0
    name: str = ""
    tracklog_folder: str = ""
    formula: FsdbFormula = field(default_factory=FsdbFormula)
    ss: int = 1
    es: int = 2
    goal_type: str = "CIRCLE"
    ground_start: bool = False
    turnpoints: list[FsdbTurnpoint] = field(default_factory=list)
    start_gates: list[str] = field(default_factory=list)
    task_state: str = "REGULAR"
    score_back_time: int = 0
    participant_results: list[FsdbParticipantResult] = field(default_factory=list)
    score_params: FsdbTaskScoreParams | None = None


@dataclass
class FsdbCompetition:
    name: str = ""
    location: str = ""
    from_date: str = ""
    to_date: str = ""
    utc_offset: int = 0
    discipline: str = "hg"
    formula: FsdbFormula = field(default_factory=FsdbFormula)
    participants: list[FsdbParticipant] = field(default_factory=list)
    tasks: list[FsdbTask] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _bool(val: str | None) -> bool:
    return str(val).strip() in ("1", "true", "True")


def _float(val: str | None, default: float = 0.0) -> float:
    try:
        return float(val) if val else default
    except (ValueError, TypeError):
        return default


def _int(val: str | None, default: int = 0) -> int:
    try:
        return int(float(val)) if val else default
    except (ValueError, TypeError):
        return default


def _parse_formula(elem: ET.Element) -> FsdbFormula:
    g = elem.get
    return FsdbFormula(
        id=g("id", "GAP2021"),
        min_dist=_float(g("min_dist"), 5.0),
        nom_dist=_float(g("nom_dist"), 60.0),
        nom_time=_float(g("nom_time"), 1.5),
        nom_launch=_float(g("nom_launch"), 0.95),
        nom_goal=_float(g("nom_goal"), 0.3),
        day_quality_override=_float(g("day_quality_override", g("day_quality")), 0.0),
        bonus_gr=_float(g("bonus_gr"), 0.0),
        jump_the_gun_factor=_float(g("jump_the_gun_factor"), 0.0),
        jump_the_gun_max=_int(g("jump_the_gun_max"), 0),
        normalize_1000_before_day_quality=_bool(g("normalize_1000_before_day_quality")),
        time_points_if_not_in_goal=_float(g("time_points_if_not_in_goal"), 1.0),
        use_1000_points_for_max_day_quality=_bool(g("use_1000_points_for_max_day_quality")),
        use_arrival_position_points=_bool(g("use_arrival_position_points")),
        use_arrival_time_points=_bool(g("use_arrival_time_points")),
        use_departure_points=_bool(g("use_departure_points")),
        use_difficulty_for_distance_points=_bool(g("use_difficulty_for_distance_points")),
        use_distance_points=_bool(g("use_distance_points")),
        use_distance_squared_for_lc=_bool(g("use_distance_squared_for_LC")),
        use_leading_points=_bool(g("use_leading_points")),
        use_semi_circle_control_zone_for_goal_line=_bool(g("use_semi_circle_control_zone_for_goal_line")),
        use_time_points=_bool(g("use_time_points")),
        scoring_altitude=g("scoring_altitude", "GPS"),
        final_glide_decelerator=g("final_glide_decelerator", "none"),
        no_final_glide_decelerator_reason=g("no_final_glide_decelerator_reason", ""),
        min_time_span_for_valid_task=_int(g("min_time_span_for_valid_task"), 60),
        score_back_time=_int(g("score_back_time"), 15),
        use_proportional_leading_weight_if_nobody_in_goal=_bool(g("use_proportional_leading_weight_if_nobody_in_goal")),
        leading_weight_factor=_float(g("leading_weight_factor"), 1.0),
        turnpoint_radius_tolerance=_float(g("turnpoint_radius_tolerance"), 0.0005),
        turnpoint_radius_minimum_absolute_tolerance=_float(g("turnpoint_radius_minimum_absolute_tolerance"), 5.0),
        number_of_decimals_task_results=_int(g("number_of_decimals_task_results"), 2),
        number_of_decimals_competition_results=_int(g("number_of_decimals_competition_results"), 1),
        redistribute_removed_time_points_as_distance_points=_bool(g("redistribute_removed_time_points_as_distance_points")),
        use_best_score_for_ftv_validity=_bool(g("use_best_score_for_ftv_validity")),
        use_constant_leading_weight=_bool(g("use_constant_leading_weight")),
        use_pwca2019_for_lc=_bool(g("use_pwca2019_for_lc")),
        use_flat_decline_of_timepoints=_bool(g("use_flat_decline_of_timepoints")),
        no_pilots_in_goal_factor=_float(g("no_pilots_in_goal_factor"), 1.0),
        task_stopped_factor=_float(g("task_stopped_factor"), 1.0),
        time_validity_based_on_pilot_with_speed_rank=_int(g("time_validity_based_on_pilot_with_speed_rank"), 1),
    )


def _parse_participant(elem: ET.Element) -> FsdbParticipant:
    g = elem.get
    return FsdbParticipant(
        fsdb_id=_int(g("id")),
        name=g("name", ""),
        civl_id=g("CIVLID", ""),
        nation=g("nat_code_3166_a3", ""),
        glider=g("glider", ""),
        female=_bool(g("female")),
    )


def _parse_task_participant(elem: ET.Element, comp_participants: dict[int, FsdbParticipant]) -> FsdbParticipantResult:
    pid = _int(elem.get("id"))
    result = FsdbParticipantResult(fsdb_pilot_id=pid, present=True)

    flight_elem = elem.find("FsFlightData")
    result_elem = elem.find("FsResult")

    if flight_elem is not None:
        fg = flight_elem.get
        result.tracklog_filename = fg("tracklog_filename", "")
        result.had_flight_data = bool(
            _float(fg("distance")) > 0 or result.tracklog_filename
        )

    if result_elem is not None:
        rg = result_elem.get
        rank_val = rg("rank")
        result.rank = _int(rank_val) if rank_val else None
        result.points = _float(rg("points"))
        result.distance = _float(rg("distance"))
        result.distance_points = _float(rg("distance_points"))
        result.linear_distance_points = _float(rg("linear_distance_points"))
        result.difficulty_distance_points = _float(rg("difficulty_distance_points"))
        result.time_points = _float(rg("time_points"))
        result.arrival_points = _float(rg("arrival_points"))
        result.departure_points = _float(rg("departure_points"))
        result.leading_points = _float(rg("leading_points"))
        result.penalty = _float(rg("penalty"))
        result.penalty_points = _float(rg("penalty_points"))
        result.penalty_reason = rg("penalty_reason", "")
        result.ss_time = rg("ss_time", "")
        result.started_ss = rg("started_ss", "")
        result.finished_ss = rg("finished_ss", "")
        result.real_distance = _float(rg("real_distance"))
        result.got_time_but_not_goal_penalty = rg("got_time_but_not_goal_penalty", "False") == "True"

    return result


def _parse_score_params(elem: ET.Element) -> FsdbTaskScoreParams:
    g = elem.get
    return FsdbTaskScoreParams(
        ss_distance=_float(g("ss_distance")),
        task_distance=_float(g("task_distance")),
        day_quality=_float(g("day_quality")),
        launch_validity=_float(g("launch_validity")),
        distance_validity=_float(g("distance_validity")),
        time_validity=_float(g("time_validity")),
        stop_validity=_float(g("stop_validity"), 1.0),
        available_distance_points=_float(g("available_points_distance")),
        available_time_points=_float(g("available_points_time")),
        available_leading_points=_float(g("available_points_leading")),
        available_arrival_points=_float(g("available_points_arrival")),
        available_departure_points=_float(g("available_points_departure")),
        best_dist=_float(g("best_dist")),
        best_time=_float(g("best_time")),
        goal_ratio=_float(g("goalratio")),
        no_of_pilots_present=_int(g("no_of_pilots_present")),
        no_of_pilots_flying=_int(g("no_of_pilots_flying")),
        no_of_pilots_reaching_goal=_int(g("no_of_pilots_reaching_goal")),
        no_of_pilots_reaching_es=_int(g("no_of_pilots_reaching_es")),
        no_of_pilots_in_competition=_int(g("no_of_pilots_in_competition")),
        distance_weight=_float(g("distance_weight")),
        time_weight=_float(g("time_weight")),
    )


def _parse_task(elem: ET.Element, comp_participants: dict[int, FsdbParticipant]) -> FsdbTask:
    task = FsdbTask(
        fsdb_id=_int(elem.get("id")),
        name=elem.get("name", ""),
        tracklog_folder=elem.get("tracklog_folder", ""),
    )

    # Task-level formula
    formula_elem = elem.find("FsScoreFormula")
    if formula_elem is not None:
        task.formula = _parse_formula(formula_elem)

    # Task definition (turnpoints, gates, ss/es)
    defn = elem.find("FsTaskDefinition")
    if defn is not None:
        task.ss = _int(defn.get("ss"), 1)
        task.es = _int(defn.get("es"), 2)
        task.goal_type = defn.get("goal", "CIRCLE")
        task.ground_start = _bool(defn.get("groundstart"))

        for tp_elem in defn.findall("FsTurnpoint"):
            task.turnpoints.append(FsdbTurnpoint(
                code=tp_elem.get("id", ""),
                lat=_float(tp_elem.get("lat")),
                lon=_float(tp_elem.get("lon")),
                altitude=_float(tp_elem.get("altitude")),
                radius=_float(tp_elem.get("radius"), 400.0),
                open_time=tp_elem.get("open", ""),
                close_time=tp_elem.get("close", ""),
            ))

        for gate_elem in defn.findall("FsStartGate"):
            task.start_gates.append(gate_elem.get("open", ""))

    # Task state
    state_elem = elem.find("FsTaskState")
    if state_elem is not None:
        task.task_state = state_elem.get("task_state", "REGULAR")
        task.score_back_time = _int(state_elem.get("score_back_time"))

    # Participant results
    parts_elem = elem.find("FsParticipants")
    if parts_elem is not None:
        for p_elem in parts_elem.findall("FsParticipant"):
            task.participant_results.append(
                _parse_task_participant(p_elem, comp_participants)
            )

    # Score params
    sp_elem = elem.find("FsTaskScoreParams")
    if sp_elem is not None:
        task.score_params = _parse_score_params(sp_elem)

    return task


# ---------------------------------------------------------------------------
# Main parsing entry point
# ---------------------------------------------------------------------------

def parse_fsdb(filepath: Path) -> FsdbCompetition:
    """Parse an FSDB file and return a structured FsdbCompetition."""
    tree = ET.parse(filepath)
    root = tree.getroot()

    comp_elem = root.find("FsCompetition")
    if comp_elem is None:
        raise ValueError(f"No FsCompetition element found in {filepath}")

    comp = FsdbCompetition(
        name=comp_elem.get("name", ""),
        location=comp_elem.get("location", ""),
        from_date=comp_elem.get("from", ""),
        to_date=comp_elem.get("to", ""),
        utc_offset=_int(comp_elem.get("utc_offset"), 0),
        discipline=comp_elem.get("discipline", "hg"),
    )

    # Competition-level formula
    formula_elem = comp_elem.find("FsScoreFormula")
    if formula_elem is not None:
        comp.formula = _parse_formula(formula_elem)

    # Participants
    comp_participants: dict[int, FsdbParticipant] = {}
    parts_elem = comp_elem.find("FsParticipants")
    if parts_elem is not None:
        for p_elem in parts_elem.findall("FsParticipant"):
            p = _parse_participant(p_elem)
            comp.participants.append(p)
            comp_participants[p.fsdb_id] = p

    # Tasks
    tasks_elem = comp_elem.find("FsTasks")
    if tasks_elem is not None:
        for t_elem in tasks_elem.findall("FsTask"):
            task = _parse_task(t_elem, comp_participants)
            # Skip cancelled tasks
            if task.task_state == "CANCELLED":
                continue
            comp.tasks.append(task)

    return comp


# ---------------------------------------------------------------------------
# Competition discovery
# ---------------------------------------------------------------------------

def discover_competitions(root: Path) -> list[tuple[Path, str]]:
    """Find FSDB files under root, returning (fsdb_path, folder_name) pairs.

    For folders with multiple FSDB files that represent the SAME competition,
    prefer ones with "New Version" or "new scoring software" in the name.
    If a folder has multiple FSDB files representing DIFFERENT competitions
    (e.g. "Open 2012.fsdb" and "Sport 2012.fsdb"), return all of them.

    Deduplicates by parsing competition names to avoid importing the same
    comp twice when files are copied across year folders.
    """
    # Group FSDB files by parent directory
    by_dir: dict[Path, list[Path]] = {}
    for fsdb in root.rglob("*.fsdb"):
        # Skip files inside 'old' directories
        parts_lower = [p.lower() for p in fsdb.parts]
        if "old" in parts_lower:
            continue
        parent = fsdb.parent
        by_dir.setdefault(parent, []).append(fsdb)

    all_candidates: list[tuple[Path, str]] = []
    for parent_dir, files in sorted(by_dir.items()):
        # Walk up to find the competition year folder
        folder_name = parent_dir.name
        for ancestor in parent_dir.parents:
            if ancestor == root:
                break
            folder_name = ancestor.name

        if len(files) == 1:
            all_candidates.append((files[0], folder_name))
        else:
            # Group files by base competition name (strip "New Version" etc.)
            groups: dict[str, list[Path]] = {}
            for f in files:
                base = f.stem.lower()
                for suffix in ["(new version)", "(new scoring software)", " revised", " old software"]:
                    base = base.replace(suffix, "")
                # Normalize: remove extra spaces, standardize "hcYYYY" to "hc YYYY"
                base = base.strip()
                base = re.sub(r"hc\s*(\d{4})", r"hc \1", base)
                base = re.sub(r"\s+", " ", base).strip()
                groups.setdefault(base, []).append(f)

            for base_name, group_files in groups.items():
                if len(group_files) == 1:
                    all_candidates.append((group_files[0], folder_name))
                else:
                    # Multiple versions of same comp — prefer "New Version"
                    preferred = [
                        f for f in group_files
                        if "new version" in f.stem.lower()
                    ]
                    if preferred:
                        chosen = max(preferred, key=lambda f: f.stat().st_mtime)
                    else:
                        # Skip "new scoring software" variants if a regular version exists
                        regular = [f for f in group_files if "new scoring" not in f.stem.lower()]
                        chosen = max(regular or group_files, key=lambda f: f.stat().st_mtime)
                    all_candidates.append((chosen, folder_name))

    # Deduplicate by competition name (parse each file to check)
    seen_names: dict[str, tuple[Path, str]] = {}
    results: list[tuple[Path, str]] = []
    for fsdb_path, folder_name in all_candidates:
        try:
            tree = ET.parse(fsdb_path)
            comp_elem = tree.getroot().find("FsCompetition")
            comp_name = comp_elem.get("name", fsdb_path.stem) if comp_elem is not None else fsdb_path.stem
        except Exception:
            comp_name = fsdb_path.stem

        if comp_name in seen_names:
            # Keep the one from the folder whose name matches the comp year better
            existing_path, existing_folder = seen_names[comp_name]
            # Extract year from comp name
            import re as _re
            year_match = _re.search(r"20\d{2}", comp_name)
            if year_match:
                comp_year = year_match.group()
                if comp_year in folder_name and comp_year not in existing_folder:
                    # Current one is a better match
                    seen_names[comp_name] = (fsdb_path, folder_name)
            continue

        seen_names[comp_name] = (fsdb_path, folder_name)

    results = list(seen_names.values())
    return sorted(results, key=lambda x: x[0].name)
