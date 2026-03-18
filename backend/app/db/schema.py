from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def ensure_runtime_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if "events" not in inspector.get_table_names():
        return

    event_columns = {column["name"] for column in inspector.get_columns("events")}
    statements = {
        "nominal_distance_km": "ALTER TABLE events ADD COLUMN nominal_distance_km FLOAT",
        "nominal_time_hours": "ALTER TABLE events ADD COLUMN nominal_time_hours FLOAT",
        "nominal_launch": "ALTER TABLE events ADD COLUMN nominal_launch FLOAT",
        "minimum_distance_km": "ALTER TABLE events ADD COLUMN minimum_distance_km FLOAT",
        "penalties_json": "ALTER TABLE events ADD COLUMN penalties_json JSON",
    }

    with engine.begin() as connection:
        for column_name, statement in statements.items():
            if column_name not in event_columns:
                connection.execute(text(statement))
