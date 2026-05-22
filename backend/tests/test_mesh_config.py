import os

os.environ.setdefault("APP_SECRET_KEY", "mesh-config-test-secret-key")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import SiteSettings, User
from app.routers.tracking import get_mesh_config


def _session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _user() -> User:
    return User(username="pilot", full_name="Pilot", role="user")


def test_mesh_config_returns_cloud_vm_broker_credentials() -> None:
    factory = _session_factory()
    with factory() as session:
        session.add(
            SiteSettings(
                id=1,
                mqtt_broker_mode="cloud_vm",
                mqtt_host="mqtt-staging.aervyx.net",
                mqtt_port=8883,
                mqtt_tls_enabled=True,
                mqtt_username="fleet",
                mqtt_password="secret",
                mqtt_topic_prefix="msh",
                mqtt_channel_psk="AQ==",
            )
        )
        session.commit()

        response = get_mesh_config(user=_user(), session=session)

    assert response.mqtt_host == "mqtt-staging.aervyx.net"
    assert response.mqtt_port == 8883
    assert response.mqtt_tls_enabled is True
    assert response.mqtt_username == "fleet"
    assert response.mqtt_password == "secret"
    assert response.topic_prefix == "msh"
    assert response.channel_psk == "AQ=="


def test_mesh_config_returns_local_mosquitto_radio_credentials() -> None:
    factory = _session_factory()
    with factory() as session:
        session.add(
            SiteSettings(
                id=1,
                mqtt_broker_mode="local_mosquitto",
                mqtt_host="192.168.87.51",
                mqtt_port=1883,
                mqtt_tls_enabled=False,
                mqtt_username="fleet",
                mqtt_password="secret",
                mqtt_topic_prefix="msh",
            )
        )
        session.commit()

        response = get_mesh_config(user=_user(), session=session)

    assert response.mqtt_host == "192.168.87.51"
    assert response.mqtt_port == 1883
    assert response.mqtt_tls_enabled is False
    assert response.mqtt_username == "fleet"
    assert response.mqtt_password == "secret"
    assert response.topic_prefix == "msh"


def test_mesh_config_legacy_public_never_returns_public_credentials() -> None:
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

        response = get_mesh_config(user=_user(), session=session)

    assert response.mqtt_host != "mqtt.meshtastic.org"
    assert response.mqtt_username != "meshdev"
    assert response.mqtt_password != "large4cats"
    assert response.topic_prefix == "msh"
