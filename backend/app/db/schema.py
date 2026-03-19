from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def ensure_runtime_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if "events" not in inspector.get_table_names():
        return

    event_columns = {column["name"] for column in inspector.get_columns("events")}
    task_columns = {column["name"] for column in inspector.get_columns("tasks")} if "tasks" in inspector.get_table_names() else set()
    turnpoint_source_columns = {column["name"] for column in inspector.get_columns("turnpoint_sources")} if "turnpoint_sources" in inspector.get_table_names() else set()
    airspace_source_columns = {column["name"] for column in inspector.get_columns("airspace_sources")} if "airspace_sources" in inspector.get_table_names() else set()
    statements = {
        "scoring_formula": "ALTER TABLE events ADD COLUMN scoring_formula VARCHAR(40)",
        "nominal_distance_km": "ALTER TABLE events ADD COLUMN nominal_distance_km FLOAT",
        "nominal_time_hours": "ALTER TABLE events ADD COLUMN nominal_time_hours FLOAT",
        "nominal_launch": "ALTER TABLE events ADD COLUMN nominal_launch FLOAT",
        "minimum_distance_km": "ALTER TABLE events ADD COLUMN minimum_distance_km FLOAT",
        "nominal_goal_percent": "ALTER TABLE events ADD COLUMN nominal_goal_percent FLOAT",
        "score_back_time_minutes": "ALTER TABLE events ADD COLUMN score_back_time_minutes INTEGER",
        "goal_ss_penalty": "ALTER TABLE events ADD COLUMN goal_ss_penalty FLOAT",
        "day_quality_override": "ALTER TABLE events ADD COLUMN day_quality_override FLOAT",
        "time_points_if_not_in_goal": "ALTER TABLE events ADD COLUMN time_points_if_not_in_goal FLOAT",
        "jump_the_gun_factor": "ALTER TABLE events ADD COLUMN jump_the_gun_factor FLOAT",
        "jump_the_gun_max_seconds": "ALTER TABLE events ADD COLUMN jump_the_gun_max_seconds INTEGER",
        "stopped_glide_bonus": "ALTER TABLE events ADD COLUMN stopped_glide_bonus FLOAT",
        "use_1000_points_for_max_day_quality": "ALTER TABLE events ADD COLUMN use_1000_points_for_max_day_quality BOOLEAN",
        "normalize_1000_before_day_quality": "ALTER TABLE events ADD COLUMN normalize_1000_before_day_quality BOOLEAN",
        "use_distance_points": "ALTER TABLE events ADD COLUMN use_distance_points BOOLEAN",
        "use_time_points": "ALTER TABLE events ADD COLUMN use_time_points BOOLEAN",
        "use_leading_points": "ALTER TABLE events ADD COLUMN use_leading_points BOOLEAN",
        "use_arrival_position_points": "ALTER TABLE events ADD COLUMN use_arrival_position_points BOOLEAN",
        "use_arrival_time_points": "ALTER TABLE events ADD COLUMN use_arrival_time_points BOOLEAN",
        "use_departure_points": "ALTER TABLE events ADD COLUMN use_departure_points BOOLEAN",
        "use_difficulty_for_distance_points": "ALTER TABLE events ADD COLUMN use_difficulty_for_distance_points BOOLEAN",
        "use_distance_squared_for_lc": "ALTER TABLE events ADD COLUMN use_distance_squared_for_lc BOOLEAN",
        "use_semi_circle_control_zone_for_goal_line": "ALTER TABLE events ADD COLUMN use_semi_circle_control_zone_for_goal_line BOOLEAN",
        "use_proportional_leading_weight_if_nobody_in_goal": "ALTER TABLE events ADD COLUMN use_proportional_leading_weight_if_nobody_in_goal BOOLEAN",
        "redistribute_removed_time_points_as_distance_points": "ALTER TABLE events ADD COLUMN redistribute_removed_time_points_as_distance_points BOOLEAN",
        "use_best_score_for_ftv_validity": "ALTER TABLE events ADD COLUMN use_best_score_for_ftv_validity BOOLEAN",
        "use_constant_leading_weight": "ALTER TABLE events ADD COLUMN use_constant_leading_weight BOOLEAN",
        "use_pwca2019_for_lc": "ALTER TABLE events ADD COLUMN use_pwca2019_for_lc BOOLEAN",
        "use_flat_decline_of_timepoints": "ALTER TABLE events ADD COLUMN use_flat_decline_of_timepoints BOOLEAN",
        "scoring_altitude": "ALTER TABLE events ADD COLUMN scoring_altitude VARCHAR(20)",
        "final_glide_decelerator": "ALTER TABLE events ADD COLUMN final_glide_decelerator VARCHAR(40)",
        "no_final_glide_decelerator_reason": "ALTER TABLE events ADD COLUMN no_final_glide_decelerator_reason TEXT",
        "min_time_span_for_valid_task_minutes": "ALTER TABLE events ADD COLUMN min_time_span_for_valid_task_minutes INTEGER",
        "leading_weight_factor": "ALTER TABLE events ADD COLUMN leading_weight_factor FLOAT",
        "turnpoint_radius_tolerance": "ALTER TABLE events ADD COLUMN turnpoint_radius_tolerance FLOAT",
        "turnpoint_radius_minimum_absolute_tolerance_m": "ALTER TABLE events ADD COLUMN turnpoint_radius_minimum_absolute_tolerance_m FLOAT",
        "number_of_decimals_task_results": "ALTER TABLE events ADD COLUMN number_of_decimals_task_results INTEGER",
        "number_of_decimals_competition_results": "ALTER TABLE events ADD COLUMN number_of_decimals_competition_results INTEGER",
        "visible_airspace_classes_json": "ALTER TABLE events ADD COLUMN visible_airspace_classes_json JSON",
        "show_restricted_fields": "ALTER TABLE events ADD COLUMN show_restricted_fields BOOLEAN",
        "penalties_json": "ALTER TABLE events ADD COLUMN penalties_json JSON",
        "updated_at": "ALTER TABLE events ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }
    task_statements = {
        "task_type": "ALTER TABLE tasks ADD COLUMN task_type VARCHAR(40) DEFAULT 'race'",
        "task_start_time": "ALTER TABLE tasks ADD COLUMN task_start_time VARCHAR(8)",
        "task_finish_time": "ALTER TABLE tasks ADD COLUMN task_finish_time VARCHAR(8)",
        "start_open_time": "ALTER TABLE tasks ADD COLUMN start_open_time VARCHAR(8)",
        "start_close_time": "ALTER TABLE tasks ADD COLUMN start_close_time VARCHAR(8)",
        "start_gate_count": "ALTER TABLE tasks ADD COLUMN start_gate_count INTEGER DEFAULT 1",
        "start_gate_interval_seconds": "ALTER TABLE tasks ADD COLUMN start_gate_interval_seconds INTEGER",
    }

    with engine.begin() as connection:
        for column_name, statement in statements.items():
            if column_name not in event_columns:
                connection.execute(text(statement))
        for column_name, statement in task_statements.items():
            if column_name not in task_columns:
                connection.execute(text(statement))
        table_names = set(inspector.get_table_names())
        if "turnpoint_sources" in table_names and "enabled" not in turnpoint_source_columns:
            connection.execute(text("ALTER TABLE turnpoint_sources ADD COLUMN enabled BOOLEAN DEFAULT TRUE"))
        if "turnpoint_sources" in table_names:
            connection.execute(text("UPDATE turnpoint_sources SET enabled = TRUE WHERE enabled IS NULL"))
        if "airspace_sources" not in table_names:
            connection.execute(
                text(
                    """
                    CREATE TABLE airspace_sources (
                      id INTEGER PRIMARY KEY,
                      event_id INTEGER NOT NULL,
                      kind VARCHAR(30) NOT NULL,
                      filename VARCHAR(255) NOT NULL,
                      content_type VARCHAR(120),
                      file_format VARCHAR(20) NOT NULL,
                      sha256 VARCHAR(64) NOT NULL,
                      stored_path TEXT NOT NULL,
                      enabled BOOLEAN DEFAULT TRUE,
                      uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE
                    )
                    """
                )
            )
            connection.execute(text("CREATE INDEX ix_airspace_sources_event_id ON airspace_sources (event_id)"))
            connection.execute(text("CREATE INDEX ix_airspace_sources_kind ON airspace_sources (kind)"))
            connection.execute(text("CREATE INDEX ix_airspace_sources_sha256 ON airspace_sources (sha256)"))
        elif "enabled" not in airspace_source_columns:
            connection.execute(text("ALTER TABLE airspace_sources ADD COLUMN enabled BOOLEAN DEFAULT TRUE"))
        if "airspace_regions" not in table_names:
            connection.execute(
                text(
                    """
                    CREATE TABLE airspace_regions (
                      id INTEGER PRIMARY KEY,
                      event_id INTEGER NOT NULL,
                      source_id INTEGER NOT NULL,
                      name VARCHAR(255) NOT NULL,
                      class_code VARCHAR(20),
                      type_code VARCHAR(40),
                      display_category VARCHAR(40) NOT NULL,
                      lower_limit_label VARCHAR(80),
                      upper_limit_label VARCHAR(80),
                      lower_limit_m FLOAT,
                      upper_limit_m FLOAT,
                      geometry_json JSON,
                      label_latitude FLOAT,
                      label_longitude FLOAT,
                      is_restricted_field BOOLEAN DEFAULT 0,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE,
                      FOREIGN KEY(source_id) REFERENCES airspace_sources (id) ON DELETE CASCADE
                    )
                    """
                )
            )
            connection.execute(text("CREATE INDEX ix_airspace_regions_event_id ON airspace_regions (event_id)"))
            connection.execute(text("CREATE INDEX ix_airspace_regions_source_id ON airspace_regions (source_id)"))
            connection.execute(text("CREATE INDEX ix_airspace_regions_display_category ON airspace_regions (display_category)"))
