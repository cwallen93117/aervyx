import os

os.environ.setdefault("APP_SECRET_KEY", "runtime-schema-test-secret-key")

from datetime import date

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.db.schema import ensure_runtime_schema
from app.models import Event, EventPilot, EventTurnpointSlot, Pilot, ScoreResult, SiteSettings, Task, Turnpoint, TurnpointSource, User


def test_runtime_schema_backfills_enabled_event_sources_once_and_preserves_library_on_event_delete() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        event = Event(name="Legacy files", location="Ridge", starts_on=date(2026, 1, 1), ends_on=date(2026, 1, 2), timezone="UTC")
        session.add_all([SiteSettings(id=1), event])
        session.flush()
        enabled = TurnpointSource(event_id=event.id, filename="enabled.gpx", file_format="gpx", sha256="a" * 64, stored_path="/tmp/enabled.gpx", enabled=True)
        disabled = TurnpointSource(event_id=event.id, filename="disabled.gpx", file_format="gpx", sha256="b" * 64, stored_path="/tmp/disabled.gpx", enabled=False)
        session.add_all([enabled, disabled])
        session.flush()
        session.add(Turnpoint(event_id=event.id, source_id=enabled.id, name="Kept", latitude=1, longitude=2))
        session.commit()
        event_id, enabled_id, disabled_id = event.id, enabled.id, disabled.id

    ensure_runtime_schema(engine)
    ensure_runtime_schema(engine)

    with Session(engine) as session:
        slots = session.query(EventTurnpointSlot).all()
        assert [(slot.event_id, slot.slot_number, slot.source_id) for slot in slots] == [(event_id, enabled_id, enabled_id)]
        assert session.query(EventTurnpointSlot).filter(EventTurnpointSlot.source_id == disabled_id).count() == 0
        session.delete(session.get(Event, event_id))
        session.commit()
        assert session.get(TurnpointSource, enabled_id) is not None
        assert session.get(TurnpointSource, enabled_id).event_id is None
        point = session.query(Turnpoint).filter(Turnpoint.source_id == enabled_id).one()
        assert point.event_id is None


def test_runtime_schema_converts_events_and_removes_legacy_challenge_storage() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        owner = User(username="owner@example.com", full_name="Owner", role="admin", password_hash="hash")
        pilot = Pilot(first_name="Pilot", last_name="One", email="pilot@example.com")
        ordinary = Event(name="Ordinary", location="Ridge", starts_on=date(2026, 1, 1), ends_on=date(2026, 1, 2), timezone="UTC")
        converted = Event(name="Converted", location="Ridge", starts_on=date(2026, 2, 1), ends_on=date(2026, 2, 2), timezone="UTC", visibility="public")
        hidden = Event(name="Legacy defaults", location="", starts_on=date(2026, 2, 1), ends_on=date(2026, 2, 1), timezone="UTC")
        session.add_all([SiteSettings(id=1), owner, pilot, ordinary, converted, hidden])
        session.flush()
        task = Task(event_id=converted.id, name="Preserved task")
        session.add_all([task, EventPilot(event_id=converted.id, pilot_id=pilot.id)])
        session.flush()
        session.add(ScoreResult(task_id=task.id, pilot_id=pilot.id, score_points=725.5))
        session.commit()
        converted_id, hidden_id = converted.id, hidden.id

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE users ADD COLUMN challenge_settings_json JSON"))
        connection.execute(text("ALTER TABLE events ADD COLUMN event_kind VARCHAR(20) NOT NULL DEFAULT 'competition'"))
        connection.execute(text("ALTER TABLE events ADD COLUMN owner_user_id INTEGER"))
        connection.execute(text("ALTER TABLE events ADD COLUMN source_buddy_group_id INTEGER"))
        connection.execute(text("ALTER TABLE events ADD COLUMN public_slug VARCHAR(80)"))
        connection.execute(text("ALTER TABLE events ADD COLUMN public_listed BOOLEAN NOT NULL DEFAULT TRUE"))
        connection.execute(text("CREATE TABLE event_collaborators (id INTEGER PRIMARY KEY, event_id INTEGER, user_id INTEGER, role VARCHAR(20))"))
        connection.execute(text("UPDATE events SET event_kind = 'challenge', public_listed = FALSE WHERE id = :id"), {"id": converted_id})
        connection.execute(text("UPDATE events SET event_kind = 'challenge_defaults', public_listed = FALSE WHERE id = :id"), {"id": hidden_id})

    ensure_runtime_schema(engine)

    inspector = inspect(engine)
    assert "event_collaborators" not in inspector.get_table_names()
    assert not {"event_kind", "owner_user_id", "source_buddy_group_id", "public_slug", "public_listed"} & {
        column["name"] for column in inspector.get_columns("events")
    }
    assert "challenge_settings_json" not in {column["name"] for column in inspector.get_columns("users")}
    with engine.connect() as connection:
        assert connection.execute(text("SELECT visibility FROM events WHERE id = :id"), {"id": converted_id}).scalar_one() == "participants"
        assert connection.execute(text("SELECT count(*) FROM tasks WHERE event_id = :id"), {"id": converted_id}).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM event_pilots WHERE event_id = :id"), {"id": converted_id}).scalar_one() == 1
        assert connection.execute(text("SELECT score_points FROM score_results WHERE task_id IN (SELECT id FROM tasks WHERE event_id = :id)"), {"id": converted_id}).scalar_one() == 725.5
        assert connection.execute(text("SELECT count(*) FROM events WHERE id = :id"), {"id": hidden_id}).scalar_one() == 0


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
        "public_airspace_categories_json",
        "mesh_profiles",
    }.issubset(columns)

    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT mqtt_enabled, mqtt_broker_mode, mqtt_port, mqtt_tls_enabled, mqtt_topic_prefix,
                       cloudflare_ddns_enabled, cloudflare_ddns_check_interval_hours,
                       public_airspace_categories_json
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
    assert row.public_airspace_categories_json == '["B", "C", "D", "P", "R", "W", "A", "MOA", "TFR"]'


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


def test_runtime_schema_adds_profile_type_timestamp_to_legacy_users() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE users (
                  id INTEGER PRIMARY KEY,
                  username VARCHAR(255),
                  full_name VARCHAR(160),
                  role VARCHAR(20),
                  profile_type VARCHAR(20),
                  mesh_device_id VARCHAR(80),
                  password_hash VARCHAR(255),
                  is_active BOOLEAN
                )
                """
            )
        )
        connection.execute(text("CREATE TABLE events (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE tasks (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE task_points (id INTEGER PRIMARY KEY, point_type VARCHAR(20))"))
        connection.execute(text("CREATE TABLE score_results (id INTEGER PRIMARY KEY, upload_id INTEGER, score_points FLOAT)"))
        connection.execute(
            text(
                """
                CREATE TABLE faa_airspace_features (
                  id INTEGER PRIMARY KEY,
                  source VARCHAR(10),
                  category VARCHAR(10),
                  name VARCHAR(200),
                  min_lat FLOAT,
                  max_lat FLOAT,
                  min_lon FLOAT,
                  max_lon FLOAT,
                  geometry_json JSON
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE faa_airspace_meta (
                  id INTEGER PRIMARY KEY,
                  source VARCHAR(10),
                  last_edit_date VARCHAR(40),
                  record_count INTEGER,
                  last_fetched_at TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO users (
                  username,
                  full_name,
                  role,
                  profile_type,
                  password_hash,
                  is_active
                )
                VALUES (
                  'driver@example.com',
                  'Driver User',
                  'pilot',
                  'driver',
                  'hash',
                  TRUE
                )
                """
            )
        )

    ensure_runtime_schema(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    assert "profile_type_updated_at" in columns
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT profile_type_updated_at
                FROM users
                WHERE username = 'driver@example.com'
                """
            )
        ).one()
    assert row.profile_type_updated_at is not None


def test_runtime_schema_creates_event_meet_stats_cache_table() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE events (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE tasks (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE score_results (id INTEGER PRIMARY KEY, upload_id INTEGER, score_points FLOAT)"))
        connection.execute(
            text(
                """
                CREATE TABLE faa_airspace_features (
                  id INTEGER PRIMARY KEY,
                  source VARCHAR(10),
                  category VARCHAR(10),
                  name VARCHAR(200),
                  min_lat FLOAT,
                  max_lat FLOAT,
                  min_lon FLOAT,
                  max_lon FLOAT,
                  geometry_json JSON
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE faa_airspace_meta (
                  id INTEGER PRIMARY KEY,
                  source VARCHAR(10),
                  last_edit_date VARCHAR(40),
                  record_count INTEGER,
                  last_fetched_at TIMESTAMP
                )
                """
            )
        )

    ensure_runtime_schema(engine)

    inspector = inspect(engine)
    assert "event_meet_stats_cache" in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns("event_meet_stats_cache")}
    assert {"event_id", "scope", "payload_json", "calculated_at", "updated_at"}.issubset(columns)
    indexes = {index["name"] for index in inspector.get_indexes("event_meet_stats_cache")}
    assert "ix_event_meet_stats_cache_event_scope" in indexes
