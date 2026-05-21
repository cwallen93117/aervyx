import os

os.environ.setdefault("APP_SECRET_KEY", "runtime-schema-test-secret-key")

from sqlalchemy import create_engine, inspect, text

from app.db.schema import ensure_runtime_schema


def test_runtime_schema_adds_mqtt_site_settings_columns_to_legacy_table() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE site_settings (
                  id INTEGER PRIMARY KEY,
                  telemetry_vario_smoothing_seconds INTEGER NOT NULL DEFAULT 5,
                  telemetry_altitude_smoothing_seconds INTEGER NOT NULL DEFAULT 3,
                  telemetry_speed_smoothing_seconds INTEGER NOT NULL DEFAULT 3,
                  telemetry_glide_ratio_smoothing_seconds INTEGER NOT NULL DEFAULT 5,
                  max_map_pitch_degrees INTEGER NOT NULL DEFAULT 75,
                  site_match_radius_m INTEGER NOT NULL DEFAULT 1000,
                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(text("INSERT INTO site_settings (id) VALUES (1)"))

    ensure_runtime_schema(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("site_settings")}
    assert {
        "mqtt_enabled",
        "mqtt_broker_mode",
        "mqtt_host",
        "mqtt_port",
        "mqtt_tls_enabled",
        "mqtt_username",
        "mqtt_password",
        "mqtt_topic_prefix",
        "mqtt_channel_psk",
        "mesh_profiles",
    }.issubset(columns)

    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT mqtt_enabled, mqtt_broker_mode, mqtt_port, mqtt_tls_enabled, mqtt_topic_prefix
                FROM site_settings
                WHERE id = 1
                """
            )
        ).one()

    assert bool(row.mqtt_enabled) is True
    assert row.mqtt_broker_mode == "public"
    assert row.mqtt_port == 1883
    assert bool(row.mqtt_tls_enabled) is False
    assert row.mqtt_topic_prefix == "msh"
