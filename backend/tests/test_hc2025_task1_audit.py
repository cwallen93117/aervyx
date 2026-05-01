from datetime import date

from app.models import Event, Task
from app.services.hc2025_task1_audit import (
    _build_parameter_comparison,
    render_hc2025_task1_audit_markdown,
)
from app.services.scoring import _build_formula


def _event() -> Event:
    return Event(
        id=1,
        name="HC 2025",
        location="Maryland",
        starts_on=date(2025, 5, 30),
        ends_on=date(2025, 6, 7),
        timezone="America/New_York",
        scoring_formula="GAP2021",
        nominal_distance_km=55,
        nominal_time_hours=1.5,
        nominal_launch=0.4,
        minimum_distance_km=5,
        nominal_goal_percent=0.2,
        jump_the_gun_factor=2,
        jump_the_gun_max_seconds=300,
        use_arrival_position_points=False,
        use_arrival_time_points=False,
        use_departure_points=False,
        use_difficulty_for_distance_points=True,
        use_distance_points=True,
        use_distance_squared_for_lc=True,
        use_leading_points=False,
        use_time_points=True,
        use_flat_decline_of_timepoints=True,
        redistribute_removed_time_points_as_distance_points=True,
        turnpoint_radius_tolerance=0.005,
        turnpoint_radius_minimum_absolute_tolerance_m=5,
        number_of_decimals_task_results=1,
        number_of_decimals_competition_results=0,
        leading_weight_factor=1,
        time_points_if_not_in_goal=0.8,
        penalties_json={"min_time_span_for_valid_task": 45},
    )


def _task() -> Task:
    return Task(
        id=10,
        event_id=1,
        name="Task 1",
        task_date=date(2025, 6, 2),
        task_type="elapsed_time",
        nominal_distance_km=60,
        nominal_time_hours=1.5,
        nominal_launch=0.95,
        minimum_distance_km=5,
    )


def test_hc2025_parameter_comparison_flags_task_overrides() -> None:
    event = _event()
    task = _task()
    formula = _build_formula(task, event)
    task_stats = {"task_distance": 84.094, "ss_distance": 84.094, "launch_to_ess_distance": 84.094}
    task_totals = {
        "pilots": 9,
        "launched": 9,
        "goal": 7,
        "ess": 7,
        "distance": 714270,
        "maxdist": 84094,
        "fastest": 7683,
        "mincoeff": 0,
        "time_validity": 1,
        "launch_validity": 1,
        "dist_validity": 1,
        "stop_validity": 1,
        "quality": 1,
        "_pilot_results": [],
    }
    available_points = {"distance": 365.0713, "speed": 634.9287, "leading": 0, "arrival": 0}

    rows = _build_parameter_comparison(task, event, formula, task_stats, task_totals, available_points)
    by_param = {row["param"]: row for row in rows}

    assert by_param["nom_dist"]["fs_score"] == 55
    assert by_param["nom_dist"]["airscore_effective"] == 60
    assert by_param["nom_dist"]["match"] is False
    assert "overrides Event Details" in by_param["nom_dist"]["note"]
    assert by_param["use_distance_squared_for_LC"]["match"] is True


def test_hc2025_markdown_report_includes_knut_diagnostics() -> None:
    audit = {
        "status": "ok",
        "event": {"name": "HC 2025", "timezone": "America/New_York", "effective_timezone": "America/New_York"},
        "task": {"id": 10},
        "parameter_comparison": [
            {"param": "nom_dist", "fs_score": 55, "aervyx_stored": {"event": 55, "task": 60}, "airscore_effective": 60, "match": False, "note": "Task nominal_distance_km overrides Event Details."}
        ],
        "pilot_comparison": [
            {
                "competition_number": "6",
                "pilot_name": "Knut R. Ryerson",
                "official": {"ss": "14:34:04", "distance": 48.41, "distance_points": 245.9, "time_points": 0, "total": 245.9},
                "aervyx_effective": {"ss": "14:34:06", "distance": 48.458, "distance_points": 287.7, "time_points": 0, "total": 287.7},
                "differences": {"distance_points": {"delta": 41.8}},
            }
        ],
        "knut_investigation": {
            "selected_upload": {"filename": "Knut_Ryerson.igc", "metadata_pilot_name": "Knut R. Ryerson"},
            "scored_distance_km": 48.458,
            "fs_distance_km": 48.41,
            "aervyx_distance_points": 287.7,
            "fs_distance_points": 245.9,
            "point_delta": 41.8,
            "distance_bucket_100m": 484,
            "lookahead": 1158,
            "kmdiff_at_bucket": 1,
            "linear_component": 0.288,
            "difficulty_component": 0.5,
            "diagnosis": "distance-difficulty allocation",
        },
        "tracklog_handoff": {
            "input": "track_points table rows generated from IGC B records",
            "time_basis": "UTC-aware recorded_at fixes",
            "coordinate_basis": "raw IGC latitude/longitude fixes converted to AirScore radians",
            "interpolation": "none",
        },
    }

    markdown = render_hc2025_task1_audit_markdown(audit)

    assert "## Knut Investigation" in markdown
    assert "Knut_Ryerson.igc" in markdown
    assert "Interpolation: none" in markdown
