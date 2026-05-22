import os
from datetime import UTC, datetime

os.environ.setdefault("APP_SECRET_KEY", "cloudflare-ddns-test-secret-key")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import SiteSettings
from app.services.cloudflare_ddns import run_cloudflare_ddns_check

pytestmark = pytest.mark.asyncio


class _FakeResponse:
    def __init__(self, status_code: int = 200, *, text: str = "", data: dict | None = None) -> None:
        self.status_code = status_code
        self.text = text
        self._data = data if data is not None else {}

    def json(self) -> dict:
        return self._data


class _FakeCloudflareClient:
    def __init__(self, *, public_ip: str = "74.103.142.23", records: dict[str, dict] | None = None, public_status: int = 200) -> None:
        self.public_ip = public_ip
        self.public_status = public_status
        self.records = records or {}
        self.patches: list[dict] = []
        self.get_headers: list[dict] = []

    async def get(self, url: str, **kwargs):
        if "api.ipify.org" in url:
            return _FakeResponse(self.public_status, text=self.public_ip)
        self.get_headers.append(kwargs.get("headers") or {})
        params = kwargs.get("params") or {}
        name = params.get("name")
        record = self.records.get(name)
        return _FakeResponse(
            200,
            data={
                "success": True,
                "result": [record] if record else [],
            },
        )

    async def patch(self, url: str, **kwargs):
        payload = kwargs.get("json") or {}
        self.patches.append({"url": url, "headers": kwargs.get("headers") or {}, "json": payload})
        return _FakeResponse(200, data={"success": True, "result": payload})


def _session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _record(record_id: str, name: str, content: str, proxied: bool = False) -> dict:
    return {
        "id": record_id,
        "type": "A",
        "name": name,
        "content": content,
        "proxied": proxied,
    }


def _settings(**overrides) -> SiteSettings:
    values = {
        "id": 1,
        "cloudflare_ddns_enabled": True,
        "cloudflare_ddns_zone_id": "zone123",
        "cloudflare_ddns_encrypted_api_token": "encrypted-token",
        "cloudflare_ddns_record_names": ["mqtt.aervyx.net", "mqtt-staging.aervyx.net"],
        "cloudflare_ddns_check_interval_hours": 12,
    }
    values.update(overrides)
    return SiteSettings(**values)


async def test_cloudflare_ddns_noops_when_records_match(monkeypatch) -> None:
    monkeypatch.setattr("app.services.cloudflare_ddns.decrypt_secret", lambda value: "cf-token")
    factory = _session_factory()
    client = _FakeCloudflareClient(
        records={
            "mqtt.aervyx.net": _record("one", "mqtt.aervyx.net", "74.103.142.23"),
            "mqtt-staging.aervyx.net": _record("two", "mqtt-staging.aervyx.net", "74.103.142.23"),
        }
    )

    with factory() as session:
        session.add(_settings())
        session.commit()

        result = await run_cloudflare_ddns_check(session, client=client, now=datetime(2026, 5, 22, tzinfo=UTC))

    assert client.patches == []
    assert result.cloudflare_ddns_last_public_ip == "74.103.142.23"
    assert result.cloudflare_ddns_last_update_result == "Already current: 2 record(s)"
    assert result.cloudflare_ddns_last_error is None


async def test_cloudflare_ddns_updates_changed_records_and_forces_dns_only(monkeypatch) -> None:
    monkeypatch.setattr("app.services.cloudflare_ddns.decrypt_secret", lambda value: "cf-token")
    factory = _session_factory()
    client = _FakeCloudflareClient(
        records={
            "mqtt.aervyx.net": _record("one", "mqtt.aervyx.net", "203.0.113.10"),
            "mqtt-staging.aervyx.net": _record("two", "mqtt-staging.aervyx.net", "74.103.142.23", proxied=True),
        }
    )

    with factory() as session:
        session.add(_settings())
        session.commit()

        result = await run_cloudflare_ddns_check(session, client=client, now=datetime(2026, 5, 22, tzinfo=UTC))

    assert len(client.patches) == 2
    assert {patch["json"]["name"] for patch in client.patches} == {"mqtt.aervyx.net", "mqtt-staging.aervyx.net"}
    assert all(patch["json"]["content"] == "74.103.142.23" for patch in client.patches)
    assert all(patch["json"]["proxied"] is False for patch in client.patches)
    assert all(patch["json"]["ttl"] == 1 for patch in client.patches)
    assert client.patches[0]["headers"]["Authorization"] == "Bearer cf-token"
    assert result.cloudflare_ddns_last_update_result == "Updated 2 record(s) to 74.103.142.23"
    assert result.cloudflare_ddns_last_error is None


async def test_cloudflare_ddns_records_public_ip_failure_without_crashing(monkeypatch) -> None:
    monkeypatch.setattr("app.services.cloudflare_ddns.decrypt_secret", lambda value: "cf-token")
    factory = _session_factory()
    client = _FakeCloudflareClient(public_status=500)

    with factory() as session:
        session.add(_settings())
        session.commit()

        result = await run_cloudflare_ddns_check(session, client=client, now=datetime(2026, 5, 22, tzinfo=UTC))

    assert client.patches == []
    assert result.cloudflare_ddns_last_update_result == "Updated 0, unchanged 0, failed 1"
    assert "Public IP lookup returned HTTP 500" in (result.cloudflare_ddns_last_error or "")
