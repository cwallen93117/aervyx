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
        "cloudflare_ddns_enabled",
        "cloudflare_ddns_zone_id",
        "cloudflare_ddns_encrypted_api_token",
        "cloudflare_ddns_record_names",
        "cloudflare_ddns_check_interval_hours",
        "cloudflare_ddns_last_checked_at",
        "cloudflare_ddns_last_public_ip",
        "cloudflare_ddns_last_update_result",
        "cloudflare_ddns_last_error",
        "mesh_profiles",
    }.issubset(columns)

    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT mqtt_enabled, mqtt_broker_mode, mqtt_port, mqtt_tls_enabled, mqtt_topic_prefix,
                       cloudflare_ddns_enabled, cloudflare_ddns_check_interval_hours
                FROM site_settings
                WHERE id = 1
                """
            )
        ).one()

    assert bool(row.mqtt_enabled) is True
    assert row.mqtt_broker_mode == "local_mosquitto"
    assert row.mqtt_port == 1883
    assert bool(row.mqtt_tls_enabled) is False
    assert row.mqtt_topic_prefix == "msh"
    assert bool(row.cloudflare_ddns_enabled) is False
    assert row.cloudflare_ddns_check_interval_hours == 12


def test_runtime_schema_normalizes_legacy_public_mqtt_values() -> None:
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
                  mqtt_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                  mqtt_broker_mode VARCHAR(20) NOT NULL DEFAULT 'public',
                  mqtt_host VARCHAR(255),
                  mqtt_port INTEGER NOT NULL DEFAULT 1883,
                  mqtt_tls_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                  mqtt_username VARCHAR(255),
                  mqtt_password VARCHAR(255),
                  mqtt_topic_prefix VARCHAR(64) NOT NULL DEFAULT 'msh',
                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO site_settings (
                  id,
                  mqtt_broker_mode,
                  mqtt_host,
                  mqtt_username,
                  mqtt_password
                )
                VALUES (1, 'public', 'mqtt.meshtastic.org', 'meshdev', 'large4cats')
                """
            )
        )

    ensure_runtime_schema(engine)

    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT mqtt_broker_mode, mqtt_host, mqtt_username, mqtt_password
                FROM site_settings
                WHERE id = 1
                """
            )
        ).one()

    assert row.mqtt_broker_mode == "local_mosquitto"
    assert row.mqtt_host is None
    assert row.mqtt_username is None
    assert row.mqtt_password is None
