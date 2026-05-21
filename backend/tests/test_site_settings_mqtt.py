import os

os.environ.setdefault("APP_SECRET_KEY", "site-settings-mqtt-test-secret-key")

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import User
from app.routers.site_settings import update_site_settings
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
        "mqtt_broker_mode": "private",
        "mqtt_host": "mqtt-staging.aervyx.net",
        "mqtt_port": 8883,
        "mqtt_tls_enabled": True,
        "mqtt_username": "fleet",
        "mqtt_password": "secret",
        "mqtt_topic_prefix": "msh",
    }
    values.update(overrides)
    return SiteSettingsUpdate(**values)


def test_private_mqtt_settings_write_mosquitto_password_file(monkeypatch, tmp_path) -> None:
    password_file = tmp_path / "passwords"
    monkeypatch.setattr(
        "app.routers.site_settings.get_settings",
        lambda: SimpleNamespace(mosquitto_password_file=str(password_file)),
    )
    factory = _session_factory()

    with factory() as session:
        response = update_site_settings(payload=_payload(), _=_admin(), session=session)

    assert response.mqtt_username == "fleet"
    password_lines = password_file.read_text(encoding="utf-8").splitlines()
    assert len(password_lines) == 1
    assert password_lines[0].startswith("fleet:$7$101$")
    assert "secret" not in password_lines[0]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("mqtt_host", None, "Private MQTT mode requires an MQTT host."),
        ("mqtt_username", None, "Private MQTT mode requires an MQTT username and password."),
        ("mqtt_password", None, "Private MQTT mode requires an MQTT username and password."),
    ],
)
def test_private_mqtt_settings_require_broker_credentials(monkeypatch, field: str, value, message: str) -> None:
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
