import os

os.environ.setdefault("APP_SECRET_KEY", "site-settings-mqtt-test-secret-key")

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import SiteSettings, User
from app.routers.site_settings import get_site_settings, update_site_settings
from app.schemas import SiteSettingsUpdate


def _session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _admin() -> User:
    return User(username="admin", full_name="Admin", role="admin")


def _payload(**overrides) -> SiteSettingsUpdate:
    values = {
        "mqtt_enabled": True,
        "mqtt_broker_mode": "local_mosquitto",
        "mqtt_host": "mqtt-staging.aervyx.net",
        "mqtt_port": 8883,
        "mqtt_tls_enabled": True,
        "mqtt_username": "fleet",
        "mqtt_password": "secret",
        "mqtt_topic_prefix": "msh",
    }
    values.update(overrides)
    return SiteSettingsUpdate(**values)


def test_local_mosquitto_settings_write_password_file(monkeypatch, tmp_path) -> None:
    password_file = tmp_path / "passwords"
    monkeypatch.setattr(
        "app.routers.site_settings.get_settings",
        lambda: SimpleNamespace(mosquitto_password_file=str(password_file)),
    )
    factory = _session_factory()

    with factory() as session:
        response = update_site_settings(payload=_payload(), _=_admin(), session=session)

    assert response.mqtt_broker_mode == "local_mosquitto"
    assert response.mqtt_username == "fleet"
    password_lines = password_file.read_text(encoding="utf-8").splitlines()
    assert len(password_lines) == 1
    assert password_lines[0].startswith("fleet:$7$101$")
    assert "secret" not in password_lines[0]


def test_cloud_vm_settings_do_not_write_local_password_file(monkeypatch, tmp_path) -> None:
    password_file = tmp_path / "passwords"
    monkeypatch.setattr(
        "app.routers.site_settings.get_settings",
        lambda: SimpleNamespace(mosquitto_password_file=str(password_file)),
    )
    factory = _session_factory()

    with factory() as session:
        response = update_site_settings(payload=_payload(mqtt_broker_mode="cloud_vm"), _=_admin(), session=session)

    assert response.mqtt_broker_mode == "cloud_vm"
    assert response.mqtt_username == "fleet"
    assert not password_file.exists()


def test_legacy_private_settings_map_to_cloud_vm(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.site_settings.get_settings",
        lambda: SimpleNamespace(mosquitto_password_file=None),
    )
    factory = _session_factory()

    with factory() as session:
        response = update_site_settings(payload=_payload(mqtt_broker_mode="private"), _=_admin(), session=session)

    assert response.mqtt_broker_mode == "cloud_vm"


def test_legacy_public_settings_normalize_to_local_mosquitto() -> None:
    factory = _session_factory()

    with factory() as session:
        session.add(
            SiteSettings(
                id=1,
                mqtt_broker_mode="public",
                mqtt_host="mqtt.meshtastic.org",
                mqtt_port=1883,
                mqtt_username="meshdev",
                mqtt_password="large4cats",
                mqtt_topic_prefix="msh",
            )
        )
        session.commit()
        response = get_site_settings(_=_admin(), session=session)

    assert response.mqtt_broker_mode == "local_mosquitto"
    assert response.mqtt_host is None
    assert response.mqtt_username is None
    assert response.mqtt_password is None


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("mqtt_host", None, "MQTT requires an MQTT host."),
        ("mqtt_username", None, "MQTT requires an MQTT username and password."),
        ("mqtt_password", None, "MQTT requires an MQTT username and password."),
    ],
)
def test_mqtt_settings_require_broker_credentials(monkeypatch, field: str, value, message: str) -> None:
    monkeypatch.setattr(
        "app.routers.site_settings.get_settings",
        lambda: SimpleNamespace(mosquitto_password_file=None),
    )
    factory = _session_factory()

    with factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            update_site_settings(payload=_payload(**{field: value}), _=_admin(), session=session)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == message


def test_cloudflare_ddns_settings_encrypt_token_and_do_not_return_it(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.site_settings.get_settings",
        lambda: SimpleNamespace(mosquitto_password_file=None),
    )
    monkeypatch.setattr("app.routers.site_settings.encrypt_secret", lambda value: f"encrypted:{value}")
    factory = _session_factory()

    with factory() as session:
        response = update_site_settings(
            payload=_payload(
                cloudflare_ddns_enabled=True,
                cloudflare_ddns_zone_id="zone123",
                cloudflare_ddns_api_token="cf-token",
                cloudflare_ddns_record_names=["MQTT.AERVYX.NET", "mqtt-staging.aervyx.net"],
                cloudflare_ddns_check_interval_hours=12,
            ),
            _=_admin(),
            session=session,
        )
        row = session.get(SiteSettings, 1)

    assert row is not None
    assert row.cloudflare_ddns_encrypted_api_token == "encrypted:cf-token"
    assert response.cloudflare_ddns_api_token_configured is True
    assert response.cloudflare_ddns_record_names == ["mqtt.aervyx.net", "mqtt-staging.aervyx.net"]
    assert "cloudflare_ddns_api_token" not in response.model_dump()


def test_cloudflare_ddns_requires_token_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.site_settings.get_settings",
        lambda: SimpleNamespace(mosquitto_password_file=None),
    )
    factory = _session_factory()

    with factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            update_site_settings(
                payload=_payload(
                    cloudflare_ddns_enabled=True,
                    cloudflare_ddns_zone_id="zone123",
                    cloudflare_ddns_api_token=None,
                ),
                _=_admin(),
                session=session,
            )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Cloudflare DDNS requires an API token."
