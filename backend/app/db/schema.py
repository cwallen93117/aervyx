import json

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.services.map_overlay_config import DEFAULT_MAP_OVERLAY_CONFIG


LEGACY_EVENT_COLUMNS = ("event_kind", "owner_user_id", "source_buddy_group_id", "public_slug", "public_listed")


def _remove_challenge_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    event_columns = {column["name"] for column in inspector.get_columns("events")} if "events" in tables else set()
    user_columns = {column["name"] for column in inspector.get_columns("users")} if "users" in tables else set()

    with engine.begin() as connection:
        if "event_kind" in event_columns:
            if {"visibility", "public_listed"}.issubset(event_columns):
                connection.execute(
                    text(
                        "UPDATE events SET visibility = 'participants' "
                        "WHERE event_kind = 'challenge' AND visibility = 'public' AND public_listed = FALSE"
                    )
                )
            connection.execute(text("DELETE FROM events WHERE event_kind = 'challenge_defaults'"))

        connection.execute(text("DROP TABLE IF EXISTS event_collaborators"))
        for index_name in ("ix_events_event_kind", "ix_events_owner_user_id", "ix_events_public_slug"):
            connection.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
        for column_name in LEGACY_EVENT_COLUMNS:
            if column_name in event_columns:
                connection.execute(text(f"ALTER TABLE events DROP COLUMN {column_name}"))
        if "challenge_settings_json" in user_columns:
            connection.execute(text("ALTER TABLE users DROP COLUMN challenge_settings_json"))


def _ensure_turnpoint_library_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "events" not in tables or "turnpoint_sources" not in tables:
        return
    dialect_name = engine.dialect.name
    source_columns = {column["name"] for column in inspector.get_columns("turnpoint_sources")}
    source_event_fk = next(
        (fk for fk in inspector.get_foreign_keys("turnpoint_sources") if fk.get("constrained_columns") == ["event_id"]),
        None,
    )
    turnpoint_event_fk = next(
        (fk for fk in inspector.get_foreign_keys("turnpoints") if fk.get("constrained_columns") == ["event_id"]),
        None,
    ) if "turnpoints" in tables else None
    slot_source_fk = next(
        (fk for fk in inspector.get_foreign_keys("event_turnpoint_slots") if fk.get("constrained_columns") == ["source_id"]),
        None,
    ) if "event_turnpoint_slots" in tables else None
    with engine.begin() as connection:
        if "event_turnpoint_slots" not in tables:
            connection.execute(
                text(
                    """
                    CREATE TABLE event_turnpoint_slots (
                      id INTEGER PRIMARY KEY,
                      event_id INTEGER NOT NULL,
                      slot_number INTEGER NOT NULL,
                      source_id INTEGER NOT NULL,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
                      FOREIGN KEY(source_id) REFERENCES turnpoint_sources(id) ON DELETE CASCADE,
                      CONSTRAINT uq_event_turnpoint_slot UNIQUE (event_id, slot_number),
                      CONSTRAINT uq_event_turnpoint_source UNIQUE (event_id, source_id)
                    )
                    """
                )
            )
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_event_turnpoint_source_idx ON event_turnpoint_slots (event_id, source_id)"))
        insert_prefix = "INSERT OR IGNORE" if dialect_name == "sqlite" else "INSERT"
        insert_suffix = "" if dialect_name == "sqlite" else " ON CONFLICT DO NOTHING"
        enabled_filter = " AND COALESCE(enabled, TRUE) = TRUE" if "enabled" in source_columns else ""
        connection.execute(text(
            f"{insert_prefix} INTO event_turnpoint_slots (event_id, slot_number, source_id) "
            "SELECT event_id, id, id FROM turnpoint_sources WHERE event_id IS NOT NULL"
            f"{enabled_filter}{insert_suffix}"
        ))
        connection.execute(text("DELETE FROM event_turnpoint_slots WHERE source_id IS NULL"))
        if dialect_name == "postgresql":
            connection.execute(text("ALTER TABLE turnpoint_sources ALTER COLUMN event_id DROP NOT NULL"))
            if "turnpoints" in tables:
                connection.execute(text("ALTER TABLE turnpoints ALTER COLUMN event_id DROP NOT NULL"))
            connection.execute(text("ALTER TABLE event_turnpoint_slots ALTER COLUMN source_id SET NOT NULL"))
            preparer = connection.dialect.identifier_preparer
            for table_name, fk in (("turnpoint_sources", source_event_fk), ("turnpoints", turnpoint_event_fk)):
                if not fk or str((fk.get("options") or {}).get("ondelete", "")).upper() == "SET NULL":
                    continue
                constraint_name = fk.get("name") or f"{table_name}_event_id_fkey"
                quoted_table = preparer.quote(table_name)
                quoted_constraint = preparer.quote(constraint_name)
                connection.execute(text(f"ALTER TABLE {quoted_table} DROP CONSTRAINT {quoted_constraint}"))
                connection.execute(
                    text(
                        f"ALTER TABLE {quoted_table} ADD CONSTRAINT {quoted_constraint} "
                        "FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE SET NULL"
                    )
                )
            if slot_source_fk and str((slot_source_fk.get("options") or {}).get("ondelete", "")).upper() != "CASCADE":
                constraint_name = slot_source_fk.get("name") or "event_turnpoint_slots_source_id_fkey"
                quoted_constraint = preparer.quote(constraint_name)
                connection.execute(text(f"ALTER TABLE event_turnpoint_slots DROP CONSTRAINT {quoted_constraint}"))
                connection.execute(
                    text(
                        f"ALTER TABLE event_turnpoint_slots ADD CONSTRAINT {quoted_constraint} "
                        "FOREIGN KEY (source_id) REFERENCES turnpoint_sources(id) ON DELETE CASCADE"
                    )
                )


def ensure_runtime_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    dialect_name = engine.dialect.name

    with engine.begin() as connection:
        if "site_settings" not in table_names:
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
                      mqtt_broker_mode VARCHAR(20) NOT NULL DEFAULT 'local_mosquitto',
                      mqtt_host VARCHAR(255),
                      mqtt_port INTEGER NOT NULL DEFAULT 1883,
                      mqtt_tls_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                      mqtt_username VARCHAR(255),
                      mqtt_password VARCHAR(255),
                      mqtt_topic_prefix VARCHAR(80) NOT NULL DEFAULT 'msh',
                      mqtt_channel_psk VARCHAR(255),
                      cloudflare_ddns_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                      cloudflare_ddns_zone_id VARCHAR(120),
                      cloudflare_ddns_encrypted_api_token TEXT,
                      cloudflare_ddns_record_names JSON,
                      cloudflare_ddns_check_interval_hours INTEGER NOT NULL DEFAULT 12,
                      cloudflare_ddns_last_checked_at TIMESTAMP,
                      cloudflare_ddns_last_public_ip VARCHAR(45),
                      cloudflare_ddns_last_update_result VARCHAR(255),
                      cloudflare_ddns_last_error TEXT,
                      public_airspace_categories_json JSON,
                      mesh_profiles JSON,
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
                      telemetry_vario_smoothing_seconds,
                      telemetry_altitude_smoothing_seconds,
                      telemetry_speed_smoothing_seconds,
                      telemetry_glide_ratio_smoothing_seconds,
                      max_map_pitch_degrees,
                      site_match_radius_m,
                      mqtt_enabled,
                      mqtt_broker_mode,
                      mqtt_port,
                      mqtt_topic_prefix,
                      public_airspace_categories_json
                    ) VALUES (1, 5, 3, 3, 5, 75, 1000, TRUE, 'local_mosquitto', 1883, 'msh', :default_public_airspace_categories)
                    """
                ),
                {"default_public_airspace_categories": json.dumps(["B", "C", "D", "P", "R", "W", "A", "MOA", "TFR"])},
            )
        else:
            site_settings_columns = {column["name"] for column in inspector.get_columns("site_settings")}
            if "telemetry_vario_smoothing_seconds" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN telemetry_vario_smoothing_seconds INTEGER DEFAULT 5"))
            if "telemetry_altitude_smoothing_seconds" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN telemetry_altitude_smoothing_seconds INTEGER DEFAULT 3"))
            if "telemetry_speed_smoothing_seconds" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN telemetry_speed_smoothing_seconds INTEGER DEFAULT 3"))
            if "telemetry_glide_ratio_smoothing_seconds" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN telemetry_glide_ratio_smoothing_seconds INTEGER DEFAULT 5"))
            if "max_map_pitch_degrees" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN max_map_pitch_degrees INTEGER DEFAULT 75"))
            if "site_match_radius_m" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN site_match_radius_m INTEGER DEFAULT 1000"))
            if "mqtt_enabled" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN mqtt_enabled BOOLEAN NOT NULL DEFAULT TRUE"))
            if "mqtt_broker_mode" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN mqtt_broker_mode VARCHAR(20) NOT NULL DEFAULT 'local_mosquitto'"))
            if "mqtt_host" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN mqtt_host VARCHAR(255)"))
            if "mqtt_port" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN mqtt_port INTEGER NOT NULL DEFAULT 1883"))
            if "mqtt_tls_enabled" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN mqtt_tls_enabled BOOLEAN NOT NULL DEFAULT FALSE"))
            if "mqtt_username" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN mqtt_username VARCHAR(255)"))
            if "mqtt_password" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN mqtt_password VARCHAR(255)"))
            if "mqtt_topic_prefix" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN mqtt_topic_prefix VARCHAR(80) NOT NULL DEFAULT 'msh'"))
            if "mqtt_channel_psk" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN mqtt_channel_psk VARCHAR(255)"))
            if "cloudflare_ddns_enabled" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN cloudflare_ddns_enabled BOOLEAN NOT NULL DEFAULT FALSE"))
            if "cloudflare_ddns_zone_id" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN cloudflare_ddns_zone_id VARCHAR(120)"))
            if "cloudflare_ddns_encrypted_api_token" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN cloudflare_ddns_encrypted_api_token TEXT"))
            if "cloudflare_ddns_record_names" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN cloudflare_ddns_record_names JSON"))
            if "cloudflare_ddns_check_interval_hours" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN cloudflare_ddns_check_interval_hours INTEGER NOT NULL DEFAULT 12"))
            if "cloudflare_ddns_last_checked_at" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN cloudflare_ddns_last_checked_at TIMESTAMP"))
            if "cloudflare_ddns_last_public_ip" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN cloudflare_ddns_last_public_ip VARCHAR(45)"))
            if "cloudflare_ddns_last_update_result" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN cloudflare_ddns_last_update_result VARCHAR(255)"))
            if "cloudflare_ddns_last_error" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN cloudflare_ddns_last_error TEXT"))
            if "public_airspace_categories_json" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN public_airspace_categories_json JSON"))
            if "mesh_profiles" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN mesh_profiles JSON"))
            if "updated_at" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
            connection.execute(
                text(
                    """
                    INSERT INTO site_settings (
                      id,
                      telemetry_vario_smoothing_seconds,
                      telemetry_altitude_smoothing_seconds,
                      telemetry_speed_smoothing_seconds,
                      telemetry_glide_ratio_smoothing_seconds,
                      max_map_pitch_degrees,
                      site_match_radius_m,
                      mqtt_enabled,
                      mqtt_broker_mode,
                      mqtt_port,
                      mqtt_topic_prefix
                    )
                    SELECT 1, 5, 3, 3, 5, 75, 1000, TRUE, 'local_mosquitto', 1883, 'msh'
                    WHERE NOT EXISTS (SELECT 1 FROM site_settings WHERE id = 1)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    UPDATE site_settings
                    SET
                      telemetry_vario_smoothing_seconds = COALESCE(telemetry_vario_smoothing_seconds, 5),
                      telemetry_altitude_smoothing_seconds = COALESCE(telemetry_altitude_smoothing_seconds, 3),
                      telemetry_speed_smoothing_seconds = COALESCE(telemetry_speed_smoothing_seconds, 3),
                      telemetry_glide_ratio_smoothing_seconds = COALESCE(telemetry_glide_ratio_smoothing_seconds, 5),
                      max_map_pitch_degrees = COALESCE(max_map_pitch_degrees, 75),
                      site_match_radius_m = COALESCE(site_match_radius_m, 1000),
                      mqtt_enabled = COALESCE(mqtt_enabled, TRUE),
                      mqtt_broker_mode = CASE
                        WHEN mqtt_broker_mode = 'private' THEN 'cloud_vm'
                        WHEN mqtt_broker_mode = 'cloud_vm' THEN 'cloud_vm'
                        ELSE 'local_mosquitto'
                      END,
                      mqtt_port = COALESCE(mqtt_port, 1883),
                      mqtt_tls_enabled = COALESCE(mqtt_tls_enabled, FALSE),
                      mqtt_topic_prefix = COALESCE(mqtt_topic_prefix, 'msh'),
                      mqtt_host = CASE WHEN mqtt_host = 'mqtt.meshtastic.org' THEN NULL ELSE mqtt_host END,
                      mqtt_username = CASE WHEN mqtt_username = 'meshdev' THEN NULL ELSE mqtt_username END,
                      mqtt_password = CASE WHEN mqtt_password = 'large4cats' THEN NULL ELSE mqtt_password END,
                      cloudflare_ddns_enabled = COALESCE(cloudflare_ddns_enabled, FALSE),
                      cloudflare_ddns_check_interval_hours = COALESCE(cloudflare_ddns_check_interval_hours, 12),
                      public_airspace_categories_json = COALESCE(public_airspace_categories_json, :default_public_airspace_categories),
                      updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP)
                    WHERE id = 1
                    """
                ),
                {"default_public_airspace_categories": json.dumps(["B", "C", "D", "P", "R", "W", "A", "MOA", "TFR"])},
            )

        if "integration_credentials" not in table_names:
            connection.execute(
                text(
                    """
                    CREATE TABLE integration_credentials (
                      provider VARCHAR(80) PRIMARY KEY,
                      enabled BOOLEAN NOT NULL DEFAULT FALSE,
                      base_url VARCHAR(255) NOT NULL DEFAULT 'https://api.faa.gov',
                      client_id_header VARCHAR(80) NOT NULL DEFAULT 'client_id',
                      client_secret_header VARCHAR(80) NOT NULL DEFAULT 'client_secret',
                      encrypted_client_id TEXT,
                      encrypted_client_secret TEXT,
                      last_tested_at TIMESTAMP,
                      last_test_status VARCHAR(20),
                      last_test_message TEXT,
                      updated_by_user_id INTEGER,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE SET NULL
                    )
                    """
                )
            )
        else:
            integration_columns = {column["name"] for column in inspector.get_columns("integration_credentials")}
            integration_statements = {
                "enabled": "ALTER TABLE integration_credentials ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT FALSE",
                "base_url": "ALTER TABLE integration_credentials ADD COLUMN base_url VARCHAR(255) NOT NULL DEFAULT 'https://api.faa.gov'",
                "client_id_header": "ALTER TABLE integration_credentials ADD COLUMN client_id_header VARCHAR(80) NOT NULL DEFAULT 'client_id'",
                "client_secret_header": "ALTER TABLE integration_credentials ADD COLUMN client_secret_header VARCHAR(80) NOT NULL DEFAULT 'client_secret'",
                "encrypted_client_id": "ALTER TABLE integration_credentials ADD COLUMN encrypted_client_id TEXT",
                "encrypted_client_secret": "ALTER TABLE integration_credentials ADD COLUMN encrypted_client_secret TEXT",
                "last_tested_at": "ALTER TABLE integration_credentials ADD COLUMN last_tested_at TIMESTAMP",
                "last_test_status": "ALTER TABLE integration_credentials ADD COLUMN last_test_status VARCHAR(20)",
                "last_test_message": "ALTER TABLE integration_credentials ADD COLUMN last_test_message TEXT",
                "updated_by_user_id": "ALTER TABLE integration_credentials ADD COLUMN updated_by_user_id INTEGER",
                "created_at": "ALTER TABLE integration_credentials ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                "updated_at": "ALTER TABLE integration_credentials ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            }
            for column_name, statement in integration_statements.items():
                if column_name not in integration_columns:
                    connection.execute(text(statement))

        if "flight_sites" not in table_names:
            connection.execute(
                text(
                    """
                    CREATE TABLE flight_sites (
                      id INTEGER PRIMARY KEY,
                      name VARCHAR(160) NOT NULL,
                      city_state VARCHAR(160) NOT NULL DEFAULT '',
                      latitude FLOAT NOT NULL,
                      longitude FLOAT NOT NULL,
                      is_active BOOLEAN NOT NULL DEFAULT TRUE,
                      flight_count INTEGER NOT NULL DEFAULT 0,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(text("CREATE INDEX ix_flight_sites_name ON flight_sites (name)"))
        else:
            flight_site_columns = {column["name"] for column in inspector.get_columns("flight_sites")}
            if "flight_count" not in flight_site_columns:
                connection.execute(text("ALTER TABLE flight_sites ADD COLUMN flight_count INTEGER NOT NULL DEFAULT 0"))

        if "task_scoring_inputs" not in table_names:
            connection.execute(
                text(
                    """
                    CREATE TABLE task_scoring_inputs (
                      id INTEGER PRIMARY KEY,
                      task_id INTEGER NOT NULL,
                      pilot_id INTEGER NOT NULL,
                      selected_upload_id INTEGER,
                      status_override VARCHAR(32),
                      updated_by_user_id INTEGER,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE,
                      FOREIGN KEY(pilot_id) REFERENCES pilots (id) ON DELETE CASCADE,
                      FOREIGN KEY(selected_upload_id) REFERENCES igc_uploads (id) ON DELETE SET NULL,
                      FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE SET NULL
                    )
                    """
                )
            )
            connection.execute(text("CREATE UNIQUE INDEX uq_task_scoring_input_task_pilot ON task_scoring_inputs (task_id, pilot_id)"))
            connection.execute(text("CREATE INDEX ix_task_scoring_input_task_pilot ON task_scoring_inputs (task_id, pilot_id)"))

        if "score_penalties" not in table_names:
            connection.execute(
                text(
                    """
                    CREATE TABLE score_penalties (
                      id INTEGER PRIMARY KEY,
                      task_id INTEGER NOT NULL,
                      pilot_id INTEGER NOT NULL,
                      penalty_type VARCHAR(20) NOT NULL,
                      value FLOAT NOT NULL DEFAULT 0,
                      reason VARCHAR(255) DEFAULT '',
                      position INTEGER NOT NULL DEFAULT 0,
                      applied_by_user_id INTEGER,
                      applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      updated_by_user_id INTEGER,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE,
                      FOREIGN KEY(pilot_id) REFERENCES pilots (id) ON DELETE CASCADE,
                      FOREIGN KEY(applied_by_user_id) REFERENCES users (id) ON DELETE SET NULL,
                      FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE SET NULL
                    )
                    """
                )
            )
            connection.execute(text("CREATE INDEX ix_score_penalties_task_pilot ON score_penalties (task_id, pilot_id)"))

        if "map_overlay_config" not in table_names:
            connection.execute(
                text(
                    """
                    CREATE TABLE map_overlay_config (
                      id INTEGER PRIMARY KEY,
                      config TEXT NOT NULL DEFAULT '{}',
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(
                text(
                    "INSERT INTO map_overlay_config (id, config) VALUES (1, :config)"
                ),
                {"config": json.dumps(DEFAULT_MAP_OVERLAY_CONFIG)},
            )
        else:
            map_overlay_columns = {column["name"] for column in inspector.get_columns("map_overlay_config")}
            if "config" not in map_overlay_columns:
                connection.execute(text("ALTER TABLE map_overlay_config ADD COLUMN config TEXT NOT NULL DEFAULT '{}'"))
            if "updated_at" not in map_overlay_columns:
                connection.execute(text("ALTER TABLE map_overlay_config ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
            connection.execute(
                text(
                    """
                    INSERT INTO map_overlay_config (id, config)
                    SELECT 1, :config
                    WHERE NOT EXISTS (SELECT 1 FROM map_overlay_config WHERE id = 1)
                    """
                ),
                {"config": json.dumps(DEFAULT_MAP_OVERLAY_CONFIG)},
            )

    pre_user_columns = {column["name"] for column in inspector.get_columns("users")} if "users" in table_names else set()
    if "users" in table_names:
        with engine.begin() as connection:
            if "mesh_devices" not in table_names:
                id_column = "id INTEGER PRIMARY KEY" if dialect_name == "sqlite" else "id SERIAL PRIMARY KEY"
                connection.execute(
                    text(
                        f"""
                        CREATE TABLE mesh_devices (
                          {id_column},
                          owner_user_id INTEGER NOT NULL,
                          device_id VARCHAR(80) NOT NULL,
                          label VARCHAR(160) NOT NULL,
                          purpose VARCHAR(32) NOT NULL DEFAULT 'tracking',
                          is_active BOOLEAN NOT NULL DEFAULT TRUE,
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          FOREIGN KEY(owner_user_id) REFERENCES users (id) ON DELETE CASCADE,
                          CONSTRAINT uq_mesh_devices_device_id UNIQUE (device_id)
                        )
                        """
                    )
                )
                connection.execute(text("CREATE INDEX ix_mesh_devices_owner_user_id ON mesh_devices (owner_user_id)"))
                connection.execute(text("CREATE INDEX ix_mesh_devices_purpose ON mesh_devices (purpose)"))
                table_names.add("mesh_devices")

            mesh_device_columns = {column["name"] for column in inspector.get_columns("mesh_devices")}
            mesh_device_statements = {
                "label": "ALTER TABLE mesh_devices ADD COLUMN label VARCHAR(160) NOT NULL DEFAULT 'Meshtastic device'",
                "purpose": "ALTER TABLE mesh_devices ADD COLUMN purpose VARCHAR(32) NOT NULL DEFAULT 'tracking'",
                "is_active": "ALTER TABLE mesh_devices ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE",
                "created_at": "ALTER TABLE mesh_devices ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                "updated_at": "ALTER TABLE mesh_devices ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            }
            for column_name, statement in mesh_device_statements.items():
                if column_name not in mesh_device_columns:
                    connection.execute(text(statement))

            existing_mesh_indexes = {idx["name"] for idx in inspector.get_indexes("mesh_devices")}
            if "ix_mesh_devices_owner_user_id" not in existing_mesh_indexes:
                connection.execute(text("CREATE INDEX ix_mesh_devices_owner_user_id ON mesh_devices (owner_user_id)"))
            if "ix_mesh_devices_purpose" not in existing_mesh_indexes:
                connection.execute(text("CREATE INDEX ix_mesh_devices_purpose ON mesh_devices (purpose)"))

            if "mesh_device_id" in pre_user_columns:
                insert_sql = (
                    """
                    INSERT OR IGNORE INTO mesh_devices (owner_user_id, device_id, label, purpose, is_active)
                    SELECT id, mesh_device_id, COALESCE(NULLIF(full_name, ''), username), 'tracking', is_active
                    FROM users
                    WHERE mesh_device_id IS NOT NULL AND mesh_device_id <> ''
                    """
                    if dialect_name == "sqlite"
                    else
                    """
                    INSERT INTO mesh_devices (owner_user_id, device_id, label, purpose, is_active)
                    SELECT id, mesh_device_id, COALESCE(NULLIF(full_name, ''), username), 'tracking', is_active
                    FROM users
                    WHERE mesh_device_id IS NOT NULL AND mesh_device_id <> ''
                    ON CONFLICT (device_id) DO NOTHING
                    """
                )
                connection.execute(text(insert_sql))

            if "mesh_node_statuses" not in table_names:
                id_column = "id INTEGER PRIMARY KEY" if dialect_name == "sqlite" else "id SERIAL PRIMARY KEY"
                connection.execute(
                    text(
                        f"""
                        CREATE TABLE mesh_node_statuses (
                          {id_column},
                          device_id VARCHAR(80) NOT NULL,
                          last_seen_at TIMESTAMP NOT NULL,
                          last_packet_type VARCHAR(40),
                          last_source VARCHAR(32),
                          last_gateway_id VARCHAR(80),
                          last_topic VARCHAR(255),
                          packet_count INTEGER NOT NULL DEFAULT 0,
                          battery_level INTEGER,
                          battery_level_seen_at TIMESTAMP,
                          long_name VARCHAR(160),
                          short_name VARCHAR(40),
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          CONSTRAINT uq_mesh_node_statuses_device_id UNIQUE (device_id)
                        )
                        """
                    )
                )
                connection.execute(text("CREATE INDEX ix_mesh_node_statuses_last_seen_at ON mesh_node_statuses (last_seen_at)"))
                table_names.add("mesh_node_statuses")
            else:
                mesh_node_status_columns = {column["name"] for column in inspector.get_columns("mesh_node_statuses")}
                mesh_node_status_statements = {
                    "last_seen_at": "ALTER TABLE mesh_node_statuses ADD COLUMN last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                    "last_packet_type": "ALTER TABLE mesh_node_statuses ADD COLUMN last_packet_type VARCHAR(40)",
                    "last_source": "ALTER TABLE mesh_node_statuses ADD COLUMN last_source VARCHAR(32)",
                    "last_gateway_id": "ALTER TABLE mesh_node_statuses ADD COLUMN last_gateway_id VARCHAR(80)",
                    "last_topic": "ALTER TABLE mesh_node_statuses ADD COLUMN last_topic VARCHAR(255)",
                    "packet_count": "ALTER TABLE mesh_node_statuses ADD COLUMN packet_count INTEGER NOT NULL DEFAULT 0",
                    "battery_level": "ALTER TABLE mesh_node_statuses ADD COLUMN battery_level INTEGER",
                    "battery_level_seen_at": "ALTER TABLE mesh_node_statuses ADD COLUMN battery_level_seen_at TIMESTAMP",
                    "long_name": "ALTER TABLE mesh_node_statuses ADD COLUMN long_name VARCHAR(160)",
                    "short_name": "ALTER TABLE mesh_node_statuses ADD COLUMN short_name VARCHAR(40)",
                    "created_at": "ALTER TABLE mesh_node_statuses ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                    "updated_at": "ALTER TABLE mesh_node_statuses ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                }
                for column_name, statement in mesh_node_status_statements.items():
                    if column_name not in mesh_node_status_columns:
                        connection.execute(text(statement))
                if "battery_level_seen_at" not in mesh_node_status_columns:
                    connection.execute(
                        text(
                            """
                            UPDATE mesh_node_statuses
                            SET battery_level_seen_at = last_seen_at
                            WHERE battery_level IS NOT NULL
                              AND battery_level_seen_at IS NULL
                            """
                        )
                    )

            existing_mesh_status_indexes = {idx["name"] for idx in inspector.get_indexes("mesh_node_statuses")}
            if "ix_mesh_node_statuses_last_seen_at" not in existing_mesh_status_indexes:
                connection.execute(text("CREATE INDEX ix_mesh_node_statuses_last_seen_at ON mesh_node_statuses (last_seen_at)"))

    if "events" not in table_names:
        return

    if "event_meet_stats_cache" not in table_names:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE event_meet_stats_cache (
                      id INTEGER PRIMARY KEY,
                      event_id INTEGER NOT NULL,
                      scope VARCHAR(40) NOT NULL,
                      payload_json JSON NOT NULL,
                      calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
                      CONSTRAINT uq_event_meet_stats_cache_event_scope UNIQUE (event_id, scope)
                    )
                    """
                )
            )
            connection.execute(text("CREATE INDEX ix_event_meet_stats_cache_event_scope ON event_meet_stats_cache (event_id, scope)"))

    _ensure_turnpoint_library_schema(engine)
    _remove_challenge_schema(engine)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    user_columns = {column["name"] for column in inspector.get_columns("users")} if "users" in table_names else set()
    event_columns = {column["name"] for column in inspector.get_columns("events")}
    task_columns = {column["name"] for column in inspector.get_columns("tasks")} if "tasks" in table_names else set()
    task_point_columns = {column["name"] for column in inspector.get_columns("task_points")} if "task_points" in table_names else set()
    score_result_details = {column["name"]: column for column in inspector.get_columns("score_results")} if "score_results" in table_names else {}
    score_result_columns = set(score_result_details)
    task_scoring_input_columns = {column["name"] for column in inspector.get_columns("task_scoring_inputs")} if "task_scoring_inputs" in table_names else set()
    score_penalty_columns = {column["name"] for column in inspector.get_columns("score_penalties")} if "score_penalties" in table_names else set()
    turnpoint_source_columns = {column["name"] for column in inspector.get_columns("turnpoint_sources")} if "turnpoint_sources" in table_names else set()
    turnpoint_columns = {column["name"] for column in inspector.get_columns("turnpoints")} if "turnpoints" in table_names else set()
    airspace_source_columns = {column["name"] for column in inspector.get_columns("airspace_sources")} if "airspace_sources" in table_names else set()
    pilot_flight_columns = {column["name"] for column in inspector.get_columns("pilot_flights")} if "pilot_flights" in table_names else set()
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
        "default_start_gate_count": "ALTER TABLE events ADD COLUMN default_start_gate_count INTEGER DEFAULT 5",
        "default_start_gate_interval_seconds": "ALTER TABLE events ADD COLUMN default_start_gate_interval_seconds INTEGER DEFAULT 900",
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
        "is_public_tracking": "ALTER TABLE events ADD COLUMN is_public_tracking BOOLEAN DEFAULT FALSE",
        "visibility": "ALTER TABLE events ADD COLUMN visibility VARCHAR(20) NOT NULL DEFAULT 'private'",
    }
    task_statements = {
        "task_type": "ALTER TABLE tasks ADD COLUMN task_type VARCHAR(40) DEFAULT 'race_to_goal_with_gates'",
        "task_date": "ALTER TABLE tasks ADD COLUMN task_date DATE",
        "is_practice": "ALTER TABLE tasks ADD COLUMN is_practice BOOLEAN NOT NULL DEFAULT FALSE",
        "task_start_time": "ALTER TABLE tasks ADD COLUMN task_start_time VARCHAR(8)",
        "task_finish_time": "ALTER TABLE tasks ADD COLUMN task_finish_time VARCHAR(8)",
        "start_open_time": "ALTER TABLE tasks ADD COLUMN start_open_time VARCHAR(8)",
        "start_close_time": "ALTER TABLE tasks ADD COLUMN start_close_time VARCHAR(8)",
        "start_gate_count": "ALTER TABLE tasks ADD COLUMN start_gate_count INTEGER DEFAULT 1",
        "start_gate_interval_seconds": "ALTER TABLE tasks ADD COLUMN start_gate_interval_seconds INTEGER",
    }
    task_point_statements = {
        "direction": "ALTER TABLE task_points ADD COLUMN direction VARCHAR(10) DEFAULT 'enter'",
    }
    score_result_statements = {
        "raw_score_points": "ALTER TABLE score_results ADD COLUMN raw_score_points FLOAT DEFAULT 0",
        "result_state": "ALTER TABLE score_results ADD COLUMN result_state VARCHAR(20) DEFAULT 'official'",
        "scored_at": "ALTER TABLE score_results ADD COLUMN scored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }
    with engine.begin() as connection:
        if "users" in table_names and "oauth_provider" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN oauth_provider VARCHAR(40)"))
        if "users" in table_names and "oauth_id" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN oauth_id VARCHAR(255)"))
        if "users" in table_names:
            # Make password_hash nullable for OAuth-only users
            if dialect_name != "sqlite":
                try:
                    connection.execute(text("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL"))
                except Exception:
                    pass
        if "users" in table_names and "profile_type" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN profile_type VARCHAR(20) DEFAULT 'pilot'"))
            connection.execute(text("UPDATE users SET profile_type = 'pilot' WHERE profile_type IS NULL"))
        if "users" in table_names and "profile_type_updated_at" not in user_columns:
            if dialect_name == "sqlite":
                connection.execute(text("ALTER TABLE users ADD COLUMN profile_type_updated_at TIMESTAMP"))
            else:
                connection.execute(text("ALTER TABLE users ADD COLUMN profile_type_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
            connection.execute(text("UPDATE users SET profile_type_updated_at = CURRENT_TIMESTAMP"))
        if "users" in table_names and "altitude_unit" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN altitude_unit VARCHAR(10) DEFAULT 'ft'"))
        if "users" in table_names and "speed_unit" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN speed_unit VARCHAR(10) DEFAULT 'kph'"))
        if "users" in table_names and "distance_unit" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN distance_unit VARCHAR(10) DEFAULT 'km'"))
        if "users" in table_names and "vario_unit" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN vario_unit VARCHAR(10) DEFAULT 'fpm'"))
        if "users" in table_names and "aircraft_icon" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN aircraft_icon VARCHAR(20) DEFAULT 'hang_glider'"))
        if "users" in table_names and "mesh_device_id" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN mesh_device_id VARCHAR(80)"))
            existing_user_indexes = {idx["name"] for idx in inspector.get_indexes("users")}
            if "uq_users_mesh_device_id" not in existing_user_indexes:
                connection.execute(text("CREATE UNIQUE INDEX uq_users_mesh_device_id ON users (mesh_device_id)"))
        if "users" in table_names:
            connection.execute(text("UPDATE users SET altitude_unit = 'ft' WHERE altitude_unit IS NULL"))
            connection.execute(text("UPDATE users SET speed_unit = 'kph' WHERE speed_unit IS NULL"))
            connection.execute(text("UPDATE users SET distance_unit = 'km' WHERE distance_unit IS NULL"))
            connection.execute(text("UPDATE users SET vario_unit = 'fpm' WHERE vario_unit IS NULL"))
            connection.execute(text("UPDATE users SET aircraft_icon = 'hang_glider' WHERE aircraft_icon IS NULL"))
            connection.execute(text("UPDATE users SET profile_type_updated_at = CURRENT_TIMESTAMP WHERE profile_type_updated_at IS NULL"))
        for column_name, statement in statements.items():
            if column_name not in event_columns:
                connection.execute(text(statement))
        for column_name, statement in task_statements.items():
            if column_name not in task_columns:
                connection.execute(text(statement))
        if "task_points" in table_names:
            for column_name, statement in task_point_statements.items():
                if column_name not in task_point_columns:
                    connection.execute(text(statement))
        for column_name, statement in score_result_statements.items():
            if column_name not in score_result_columns:
                connection.execute(text(statement))
        if "events" in table_names:
            connection.execute(text("UPDATE events SET default_start_gate_count = 5 WHERE default_start_gate_count IS NULL"))
            connection.execute(text("UPDATE events SET default_start_gate_interval_seconds = 900 WHERE default_start_gate_interval_seconds IS NULL"))
        if "tasks" in table_names:
            if "task_type" in task_columns or "task_type" in task_statements:
                connection.execute(
                    text(
                        """
                        UPDATE tasks
                        SET task_type = 'race_to_goal_with_gates'
                        WHERE task_type IS NULL OR task_type IN ('race', 'race_to_goal', 'speedrun_interval')
                        """
                    )
                )
                connection.execute(text("UPDATE tasks SET task_type = 'elapsed_time' WHERE task_type = 'speedrun'"))
        if "task_points" in table_names:
            if "direction" in task_point_columns or "direction" in task_point_statements:
                connection.execute(text("UPDATE task_points SET direction = 'exit' WHERE point_type = 'start' AND (direction IS NULL OR direction NOT IN ('enter', 'exit'))"))
                connection.execute(text("UPDATE task_points SET direction = 'enter' WHERE point_type <> 'start' AND (direction IS NULL OR direction NOT IN ('enter', 'exit'))"))
        if "score_results" in table_names:
            refreshed_score_result_columns = score_result_columns | set(score_result_statements)
            upload_id_column = score_result_details.get("upload_id")
            if upload_id_column and upload_id_column.get("nullable") is False and dialect_name != "sqlite":
                connection.execute(text("ALTER TABLE score_results ALTER COLUMN upload_id DROP NOT NULL"))
            if {"raw_score_points", "score_points"}.issubset(refreshed_score_result_columns):
                connection.execute(text("UPDATE score_results SET raw_score_points = COALESCE(raw_score_points, score_points, 0)"))
            if "result_state" in refreshed_score_result_columns:
                connection.execute(text("UPDATE score_results SET result_state = 'official' WHERE result_state IS NULL"))
            if "scored_at" in refreshed_score_result_columns:
                connection.execute(text("UPDATE score_results SET scored_at = CURRENT_TIMESTAMP WHERE scored_at IS NULL"))
        if "task_scoring_inputs" in table_names:
            if "selected_upload_id" not in task_scoring_input_columns:
                connection.execute(text("ALTER TABLE task_scoring_inputs ADD COLUMN selected_upload_id INTEGER"))
            if "status_override" not in task_scoring_input_columns:
                connection.execute(text("ALTER TABLE task_scoring_inputs ADD COLUMN status_override VARCHAR(32)"))
            if "updated_by_user_id" not in task_scoring_input_columns:
                connection.execute(text("ALTER TABLE task_scoring_inputs ADD COLUMN updated_by_user_id INTEGER"))
            if "updated_at" not in task_scoring_input_columns:
                connection.execute(text("ALTER TABLE task_scoring_inputs ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
        if "score_penalties" in table_names:
            if "updated_by_user_id" not in score_penalty_columns:
                connection.execute(text("ALTER TABLE score_penalties ADD COLUMN updated_by_user_id INTEGER"))
            if "updated_at" not in score_penalty_columns:
                connection.execute(text("ALTER TABLE score_penalties ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
        if "turnpoint_sources" in table_names and "enabled" not in turnpoint_source_columns:
            connection.execute(text("ALTER TABLE turnpoint_sources ADD COLUMN enabled BOOLEAN DEFAULT TRUE"))
        if "turnpoint_sources" in table_names and "schema_json" not in turnpoint_source_columns:
            connection.execute(text("ALTER TABLE turnpoint_sources ADD COLUMN schema_json JSON"))
        if "turnpoint_sources" in table_names:
            connection.execute(text("UPDATE turnpoint_sources SET enabled = TRUE WHERE enabled IS NULL"))
        if "turnpoints" in table_names:
            turnpoint_statements = {
                "symbol": "ALTER TABLE turnpoints ADD COLUMN symbol VARCHAR(40)",
                "extra_json": "ALTER TABLE turnpoints ADD COLUMN extra_json JSON",
                "source_row_index": "ALTER TABLE turnpoints ADD COLUMN source_row_index INTEGER",
            }
            for column_name, statement in turnpoint_statements.items():
                if column_name not in turnpoint_columns:
                    connection.execute(text(statement))
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
        if "pilot_flights" in table_names and "starred" not in pilot_flight_columns:
            connection.execute(text("ALTER TABLE pilot_flights ADD COLUMN starred BOOLEAN DEFAULT FALSE"))
        if "pilot_flights" in table_names and "site_id" not in pilot_flight_columns:
            connection.execute(text("ALTER TABLE pilot_flights ADD COLUMN site_id INTEGER"))
        if "pilot_flights" in table_names:
            connection.execute(text("UPDATE pilot_flights SET starred = FALSE WHERE starred IS NULL"))
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
                      is_restricted_field BOOLEAN DEFAULT FALSE,
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

        if "buddy_groups" not in table_names:
            connection.execute(
                text(
                    """
                    CREATE TABLE buddy_groups (
                      id INTEGER PRIMARY KEY,
                      user_id INTEGER NOT NULL,
                      name VARCHAR(160) NOT NULL,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
                      UNIQUE(user_id, name)
                    )
                    """
                )
            )
            connection.execute(text("CREATE INDEX ix_buddy_groups_user_id ON buddy_groups (user_id)"))
        else:
            bg_cols = {c["name"] for c in inspector.get_columns("buddy_groups")}
            if "is_public" not in bg_cols:
                connection.execute(text("ALTER TABLE buddy_groups ADD COLUMN is_public BOOLEAN DEFAULT FALSE"))
            if "visibility" not in bg_cols:
                connection.execute(text("ALTER TABLE buddy_groups ADD COLUMN visibility VARCHAR(20) NOT NULL DEFAULT 'private'"))

        if "buddy_group_members" not in table_names:
            connection.execute(
                text(
                    """
                    CREATE TABLE buddy_group_members (
                      id INTEGER PRIMARY KEY,
                      group_id INTEGER NOT NULL,
                      pilot_id INTEGER NOT NULL,
                      added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(group_id) REFERENCES buddy_groups (id) ON DELETE CASCADE,
                      FOREIGN KEY(pilot_id) REFERENCES pilots (id) ON DELETE CASCADE,
                      UNIQUE(group_id, pilot_id)
                    )
                    """
                )
            )
            connection.execute(text("CREATE INDEX ix_buddy_group_members_group_id ON buddy_group_members (group_id)"))
            connection.execute(text("CREATE INDEX ix_buddy_group_members_pilot_id ON buddy_group_members (pilot_id)"))

        if "user_emails" not in table_names:
            connection.execute(
                text(
                    """
                    CREATE TABLE user_emails (
                      id INTEGER PRIMARY KEY,
                      user_id INTEGER NOT NULL,
                      email VARCHAR(160) NOT NULL,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
                      UNIQUE(email)
                    )
                    """
                )
            )
            connection.execute(text("CREATE INDEX ix_user_emails_user_id ON user_emails (user_id)"))

        if "site_settings" in table_names:
            site_settings_columns = {col["name"] for col in inspector.get_columns("site_settings")}
            if "live_position_pruning_enabled" not in site_settings_columns:
                connection.execute(text("ALTER TABLE site_settings ADD COLUMN live_position_pruning_enabled BOOLEAN NOT NULL DEFAULT TRUE"))

        # Index for pilot-scoped queries (buddy group tracking)
        if "live_positions" in table_names:
            lp_columns = {col["name"]: col for col in inspector.get_columns("live_positions")}
            if "user_id" not in lp_columns:
                connection.execute(text("ALTER TABLE live_positions ADD COLUMN user_id INTEGER REFERENCES users (id) ON DELETE SET NULL"))
                lp_columns["user_id"] = {"name": "user_id"}
            if "battery_level_seen_at" not in lp_columns:
                connection.execute(text("ALTER TABLE live_positions ADD COLUMN battery_level_seen_at TIMESTAMP"))
                connection.execute(
                    text(
                        """
                        UPDATE live_positions
                        SET battery_level_seen_at = timestamp
                        WHERE battery_level IS NOT NULL
                          AND battery_level_seen_at IS NULL
                        """
                    )
                )
                lp_columns["battery_level_seen_at"] = {"name": "battery_level_seen_at"}
            if "mesh_seq_number" not in lp_columns:
                connection.execute(text("ALTER TABLE live_positions ADD COLUMN mesh_seq_number INTEGER"))
                lp_columns["mesh_seq_number"] = {"name": "mesh_seq_number"}
            existing_indexes = {idx["name"] for idx in inspector.get_indexes("live_positions")}
            if "ix_live_positions_pilot_ts" not in existing_indexes:
                connection.execute(text("CREATE INDEX ix_live_positions_pilot_ts ON live_positions (pilot_id, timestamp)"))
            if "ix_live_positions_user_ts" not in existing_indexes:
                connection.execute(text("CREATE INDEX ix_live_positions_user_ts ON live_positions (user_id, timestamp)"))
            if "ix_live_positions_task_user_ts" not in existing_indexes:
                connection.execute(text("CREATE INDEX ix_live_positions_task_user_ts ON live_positions (task_id, user_id, timestamp)"))

        # Make live_positions.task_id nullable for free-flight recording
        if "live_positions" in table_names and dialect_name != "sqlite":
            lp_columns = {col["name"]: col for col in inspector.get_columns("live_positions")}
            task_id_col = lp_columns.get("task_id")
            if task_id_col and task_id_col.get("nullable") is False:
                connection.execute(text("ALTER TABLE live_positions ALTER COLUMN task_id DROP NOT NULL"))

        # Make tracking_sessions.task_id nullable for free-flight sessions
        if "tracking_sessions" in table_names:
            ts_columns = {col["name"]: col for col in inspector.get_columns("tracking_sessions")}
            if "user_id" not in ts_columns:
                connection.execute(text("ALTER TABLE tracking_sessions ADD COLUMN user_id INTEGER REFERENCES users (id) ON DELETE SET NULL"))
            existing_ts_indexes = {idx["name"] for idx in inspector.get_indexes("tracking_sessions")}
            if "ix_tracking_sessions_user_id" not in existing_ts_indexes:
                connection.execute(text("CREATE INDEX ix_tracking_sessions_user_id ON tracking_sessions (user_id)"))
        if "tracking_sessions" in table_names and dialect_name != "sqlite":
            ts_columns = {col["name"]: col for col in inspector.get_columns("tracking_sessions")}
            ts_task_id_col = ts_columns.get("task_id")
            if ts_task_id_col and ts_task_id_col.get("nullable") is False:
                connection.execute(text("ALTER TABLE tracking_sessions ALTER COLUMN task_id DROP NOT NULL"))

        # -------------------------------------------------------------------
        # SOS alert management columns (0009)
        # -------------------------------------------------------------------
        if "sos_alerts" in table_names:
            sos_columns = {col["name"] for col in inspector.get_columns("sos_alerts")}
            if "status" not in sos_columns:
                connection.execute(text("ALTER TABLE sos_alerts ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'"))
            if "acknowledged_at" not in sos_columns:
                connection.execute(text("ALTER TABLE sos_alerts ADD COLUMN acknowledged_at TIMESTAMP WITH TIME ZONE NULL"))
            if "resolved_at" not in sos_columns:
                connection.execute(text("ALTER TABLE sos_alerts ADD COLUMN resolved_at TIMESTAMP WITH TIME ZONE NULL"))
            if "resolved_by" not in sos_columns:
                connection.execute(text("ALTER TABLE sos_alerts ADD COLUMN resolved_by VARCHAR(100) NULL"))
            if "notes" not in sos_columns:
                connection.execute(text("ALTER TABLE sos_alerts ADD COLUMN notes TEXT NULL"))

        # -------------------------------------------------------------------
        # FAA Airspace cache tables
        # -------------------------------------------------------------------
        if "faa_airspace_features" not in table_names:
            connection.execute(
                text(
                    """
                    CREATE TABLE faa_airspace_features (
                        id SERIAL PRIMARY KEY,
                        source VARCHAR(10) NOT NULL,
                        category VARCHAR(10) NOT NULL,
                        name VARCHAR(200) NOT NULL,
                        ident VARCHAR(40),
                        upper_val FLOAT,
                        upper_uom VARCHAR(10) DEFAULT 'FT',
                        lower_val FLOAT,
                        lower_uom VARCHAR(10) DEFAULT 'FT',
                        upper_desc VARCHAR(100) DEFAULT '',
                        lower_desc VARCHAR(100) DEFAULT '',
                        city VARCHAR(100),
                        state VARCHAR(10),
                        notam_id VARCHAR(80),
                        effective_start TIMESTAMP WITH TIME ZONE,
                        effective_end TIMESTAMP WITH TIME ZONE,
                        notice_time TIMESTAMP WITH TIME ZONE,
                        min_lat FLOAT NOT NULL,
                        max_lat FLOAT NOT NULL,
                        min_lon FLOAT NOT NULL,
                        max_lon FLOAT NOT NULL,
                        geometry_json JSON NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                    """
                )
            )
            connection.execute(text("CREATE INDEX ix_faa_airspace_source ON faa_airspace_features (source)"))
            connection.execute(text("CREATE INDEX ix_faa_airspace_category ON faa_airspace_features (category)"))
            connection.execute(text("CREATE INDEX ix_faa_airspace_bbox ON faa_airspace_features (min_lon, min_lat, max_lon, max_lat)"))
        else:
            faa_airspace_feature_columns = {column["name"] for column in inspector.get_columns("faa_airspace_features")}
            faa_airspace_feature_statements = {
                "notam_id": "ALTER TABLE faa_airspace_features ADD COLUMN notam_id VARCHAR(80)",
                "effective_start": "ALTER TABLE faa_airspace_features ADD COLUMN effective_start TIMESTAMP WITH TIME ZONE",
                "effective_end": "ALTER TABLE faa_airspace_features ADD COLUMN effective_end TIMESTAMP WITH TIME ZONE",
                "notice_time": "ALTER TABLE faa_airspace_features ADD COLUMN notice_time TIMESTAMP WITH TIME ZONE",
            }
            for column_name, statement in faa_airspace_feature_statements.items():
                if column_name not in faa_airspace_feature_columns:
                    connection.execute(text(statement))

        if "faa_airspace_meta" not in table_names:
            connection.execute(
                text(
                    """
                    CREATE TABLE faa_airspace_meta (
                        id SERIAL PRIMARY KEY,
                        source VARCHAR(10) UNIQUE NOT NULL,
                        last_edit_date VARCHAR(40),
                        record_count INTEGER DEFAULT 0,
                        last_fetched_at TIMESTAMP WITH TIME ZONE,
                        last_checked_at TIMESTAMP WITH TIME ZONE
                    )
                    """
                )
            )
        else:
            faa_airspace_meta_columns = {column["name"] for column in inspector.get_columns("faa_airspace_meta")}
            if "last_checked_at" not in faa_airspace_meta_columns:
                connection.execute(text("ALTER TABLE faa_airspace_meta ADD COLUMN last_checked_at TIMESTAMP WITH TIME ZONE"))

        if "users" in table_names:
            connection.execute(text("UPDATE users SET profile_type_updated_at = CURRENT_TIMESTAMP WHERE profile_type_updated_at IS NULL"))
