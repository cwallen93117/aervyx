import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.deps import require_admin
from app.models import IntegrationCredential, User
from app.routers.admin_integrations import router
from app.services import faa_airspace, integration_credentials
from app.services.integration_credentials import FaaNotamsCredentials, FAA_NOTAMS_PROVIDER, get_effective_faa_notams_credentials


def _settings(**overrides):
    values = {
        "integration_secret_key": "integration-test-secret",
        "faa_notam_api_enabled": False,
        "faa_notam_api_base_url": "https://api.faa.gov",
        "faa_notam_api_client_id": None,
        "faa_notam_api_client_secret": None,
        "faa_notam_api_client_id_header": "client_id",
        "faa_notam_api_client_secret_header": "client_secret",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _client(monkeypatch, settings=None):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    monkeypatch.setattr(integration_credentials, "get_settings", lambda: settings or _settings())

    test_app = FastAPI()
    test_app.include_router(router)

    def override_session():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    def override_admin() -> User:
        return User(id=1, username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")

    test_app.dependency_overrides[get_session] = override_session
    test_app.dependency_overrides[require_admin] = override_admin
    return TestClient(test_app), factory


def test_faa_credentials_save_does_not_return_or_store_plain_secret(monkeypatch) -> None:
    client, factory = _client(monkeypatch)

    response = client.patch(
        "/api/admin/integrations/faa_notams",
        json={
            "enabled": True,
            "base_url": "https://api.faa.gov",
            "client_id_header": "client_id",
            "client_secret_header": "client_secret",
            "client_id": "visible-client-id",
            "client_secret": "very-secret-value",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["admin_client_id_configured"] is True
    assert payload["admin_client_secret_configured"] is True
    assert "visible-client-id" not in str(payload)
    assert "very-secret-value" not in str(payload)

    with factory() as session:
        row = session.get(IntegrationCredential, FAA_NOTAMS_PROVIDER)
        assert row is not None
        assert row.encrypted_client_id is not None
        assert row.encrypted_client_secret is not None
        assert "visible-client-id" not in row.encrypted_client_id
        assert "very-secret-value" not in row.encrypted_client_secret


def test_faa_credentials_save_requires_encryption_key(monkeypatch) -> None:
    client, _factory = _client(monkeypatch, _settings(integration_secret_key=None))

    response = client.patch(
        "/api/admin/integrations/faa_notams",
        json={
            "enabled": True,
            "base_url": "https://api.faa.gov",
            "client_id_header": "client_id",
            "client_secret_header": "client_secret",
            "client_id": "client-id",
        },
    )

    assert response.status_code == 400
    assert "INTEGRATION_SECRET_KEY" in response.json()["detail"]


def test_effective_faa_credentials_prefers_environment(monkeypatch) -> None:
    _client(monkeypatch, _settings(
        faa_notam_api_enabled=True,
        faa_notam_api_client_id="env-id",
        faa_notam_api_client_secret="env-secret",
        faa_notam_api_base_url="https://external-api.faa.gov/notamapi/v1",
    ))

    credentials = get_effective_faa_notams_credentials()

    assert credentials.source == "environment"
    assert credentials.enabled is True
    assert credentials.base_url == "https://external-api.faa.gov/notamapi/v1"
    assert credentials.client_id == "env-id"
    assert credentials.client_secret == "env-secret"


def test_tfr_notam_timing_enrichment_matches_location(monkeypatch) -> None:
    monkeypatch.setattr(
        faa_airspace,
        "get_effective_faa_notams_credentials",
        lambda _session: FaaNotamsCredentials(
            enabled=True,
            base_url="https://api.faa.gov",
            client_id="client-id",
            client_secret="client-secret",
            client_id_header="client_id",
            client_secret_header="client_secret",
            source="admin",
        ),
    )
    monkeypatch.setattr(faa_airspace, "SessionLocal", lambda: SimpleNamespace(close=lambda: None))

    async def fake_timing_index(_client, _credentials):
        return {
            "loc:SANANGELO:TX": {
                "notam_id": "4/1234",
                "effective_start": datetime(2026, 5, 1, 12, tzinfo=timezone.utc),
                "effective_end": datetime(2026, 5, 1, 18, tzinfo=timezone.utc),
                "notice_time": datetime(2026, 4, 30, 16, tzinfo=timezone.utc),
            }
        }

    monkeypatch.setattr(faa_airspace, "_fetch_notam_timing_index", fake_timing_index)

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[-100.0, 31.0], [-99.0, 31.0], [-100.0, 31.0]]]},
            "properties": {
                "NAME": "SAN ANGELO NATIONAL DEFENSE AIRSPACE TFR",
                "CITY": "SAN ANGELO",
                "STATE": "TX",
                "WKHR_RMK": "BY NOTAM",
            },
        }
    ]

    enriched = asyncio.run(faa_airspace._enrich_tfr_features_with_notam_timing(object(), features))
    normalized = faa_airspace._normalize_tfr(enriched[0])["properties"]

    assert normalized["notamId"] == "4/1234"
    assert normalized["effectiveStart"] == datetime(2026, 5, 1, 12, tzinfo=timezone.utc)
    assert normalized["effectiveEnd"] == datetime(2026, 5, 1, 18, tzinfo=timezone.utc)
    assert normalized["noticeTime"] == datetime(2026, 4, 30, 16, tzinfo=timezone.utc)
