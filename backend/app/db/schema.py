from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def ensure_runtime_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if "events" not in inspector.get_table_names():
        return

    event_columns = {column["name"] for column in inspector.get_columns("events")}
    task_columns = {column["name"] for column in inspector.get_columns("tasks")} if "tasks" in inspector.get_table_names() else set()
    statements = {
        "scoring_formula": "ALTER TABLE events ADD COLUMN scoring_formula VARCHAR(40)",
        "nominal_distance_km": "ALTER TABLE events ADD COLUMN nominal_distance_km FLOAT",
        "nominal_time_hours": "ALTER TABLE events ADD COLUMN nominal_time_hours FLOAT",
        "nominal_launch": "ALTER TABLE events ADD COLUMN nominal_launch FLOAT",
        "minimum_distance_km": "ALTER TABLE events ADD COLUMN minimum_distance_km FLOAT",
        "nominal_goal_percent": "ALTER TABLE events ADD COLUMN nominal_goal_percent FLOAT",
        "score_back_time_minutes": "ALTER TABLE events ADD COLUMN score_back_time_minutes INTEGER",
        "goal_ss_penalty": "ALTER TABLE events ADD COLUMN goal_ss_penalty FLOAT",
        "jump_the_gun_factor": "ALTER TABLE events ADD COLUMN jump_the_gun_factor FLOAT",
        "jump_the_gun_max_seconds": "ALTER TABLE events ADD COLUMN jump_the_gun_max_seconds INTEGER",
        "stopped_glide_bonus": "ALTER TABLE events ADD COLUMN stopped_glide_bonus FLOAT",
        "use_distance_points": "ALTER TABLE events ADD COLUMN use_distance_points BOOLEAN",
        "use_time_points": "ALTER TABLE events ADD COLUMN use_time_points BOOLEAN",
        "use_leading_points": "ALTER TABLE events ADD COLUMN use_leading_points BOOLEAN",
        "use_arrival_position_points": "ALTER TABLE events ADD COLUMN use_arrival_position_points BOOLEAN",
        "use_arrival_time_points": "ALTER TABLE events ADD COLUMN use_arrival_time_points BOOLEAN",
        "use_departure_points": "ALTER TABLE events ADD COLUMN use_departure_points BOOLEAN",
        "penalties_json": "ALTER TABLE events ADD COLUMN penalties_json JSON",
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
