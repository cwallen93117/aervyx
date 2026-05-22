from __future__ import annotations

import asyncio
import ipaddress
import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import SiteSettings
from app.services.integration_credentials import IntegrationSecretError, decrypt_secret

logger = logging.getLogger(__name__)

DEFAULT_CLOUDFLARE_DDNS_RECORD_NAMES = ["mqtt.aervyx.net", "mqtt-staging.aervyx.net"]
CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"
PUBLIC_IP_URL = "https://api.ipify.org"
DEFAULT_CHECK_INTERVAL_HOURS = 12
MIN_CHECK_INTERVAL_HOURS = 1
MAX_CHECK_INTERVAL_HOURS = 168


def normalize_cloudflare_record_names(value: Any) -> list[str]:
    if value is None:
        return list(DEFAULT_CLOUDFLARE_DDNS_RECORD_NAMES)
    if isinstance(value, str):
        raw_names = value.replace(",", "\n").splitlines()
    elif isinstance(value, list):
        raw_names = [str(item) for item in value]
    else:
        raw_names = []

    names: list[str] = []
    seen: set[str] = set()
    for raw_name in raw_names:
        name = raw_name.strip().rstrip(".").lower()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names or list(DEFAULT_CLOUDFLARE_DDNS_RECORD_NAMES)


def normalize_check_interval_hours(value: int | None) -> int:
    if value is None:
        return DEFAULT_CHECK_INTERVAL_HOURS
    return max(MIN_CHECK_INTERVAL_HOURS, min(MAX_CHECK_INTERVAL_HOURS, int(value)))


def normalize_cloudflare_ddns_settings(settings: SiteSettings) -> bool:
    changed = False
    record_names = normalize_cloudflare_record_names(settings.cloudflare_ddns_record_names)
    if settings.cloudflare_ddns_record_names != record_names:
        settings.cloudflare_ddns_record_names = record_names
        changed = True
    interval_hours = normalize_check_interval_hours(settings.cloudflare_ddns_check_interval_hours)
    if settings.cloudflare_ddns_check_interval_hours != interval_hours:
        settings.cloudflare_ddns_check_interval_hours = interval_hours
        changed = True
    return changed


def cloudflare_ddns_interval_seconds(settings: SiteSettings | None) -> int:
    if settings is None:
        return DEFAULT_CHECK_INTERVAL_HOURS * 3600
    return normalize_check_interval_hours(settings.cloudflare_ddns_check_interval_hours) * 3600


def _mark_check_result(
    settings: SiteSettings,
    *,
    checked_at: datetime,
    public_ip: str | None = None,
    result: str,
    error: str | None = None,
) -> None:
    settings.cloudflare_ddns_last_checked_at = checked_at
    if public_ip:
        settings.cloudflare_ddns_last_public_ip = public_ip
    settings.cloudflare_ddns_last_update_result = result[:255]
    settings.cloudflare_ddns_last_error = error


async def _fetch_public_ipv4(client: Any) -> str:
    response = await client.get(PUBLIC_IP_URL, timeout=15)
    if response.status_code >= 400:
        raise RuntimeError(f"Public IP lookup returned HTTP {response.status_code}.")
    candidate = response.text.strip()
    try:
        ip = ipaddress.ip_address(candidate)
    except ValueError as exc:
        raise RuntimeError(f"Public IP lookup returned an invalid IP address: {candidate!r}.") from exc
    if ip.version != 4:
        raise RuntimeError(f"Public IP lookup returned IPv6 ({candidate}); Cloudflare MQTT records are A records.")
    return str(ip)


def _cloudflare_headers(api_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }


def _cloudflare_error_message(data: dict[str, Any]) -> str:
    errors = data.get("errors")
    if isinstance(errors, list) and errors:
        messages = []
        for error in errors:
            if isinstance(error, dict):
                messages.append(str(error.get("message") or error))
            else:
                messages.append(str(error))
        return "; ".join(messages)
    return "Cloudflare API request failed."


async def _cloudflare_get_json(client: Any, url: str, *, api_token: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    response = await client.get(url, headers=_cloudflare_headers(api_token), params=params, timeout=20)
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Cloudflare returned invalid JSON for {url}.") from exc
    if response.status_code >= 400 or data.get("success") is False:
        raise RuntimeError(_cloudflare_error_message(data))
    return data


async def _cloudflare_patch_json(client: Any, url: str, *, api_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = await client.patch(url, headers=_cloudflare_headers(api_token), json=payload, timeout=20)
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Cloudflare returned invalid JSON for {url}.") from exc
    if response.status_code >= 400 or data.get("success") is False:
        raise RuntimeError(_cloudflare_error_message(data))
    return data


async def _find_cloudflare_a_record(client: Any, *, zone_id: str, api_token: str, record_name: str) -> dict[str, Any]:
    data = await _cloudflare_get_json(
        client,
        f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/dns_records",
        api_token=api_token,
        params={"type": "A", "name": record_name},
    )
    result = data.get("result")
    if not isinstance(result, list) or not result:
        raise RuntimeError(f"Cloudflare A record not found: {record_name}.")
    return result[0]


async def _patch_cloudflare_a_record(
    client: Any,
    *,
    zone_id: str,
    api_token: str,
    record_id: str,
    record_name: str,
    public_ip: str,
) -> None:
    await _cloudflare_patch_json(
        client,
        f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/dns_records/{record_id}",
        api_token=api_token,
        payload={
            "type": "A",
            "name": record_name,
            "content": public_ip,
            "ttl": 1,
            "proxied": False,
        },
    )


async def run_cloudflare_ddns_check(session: Session, *, client: Any | None = None, now: datetime | None = None) -> SiteSettings:
    """Run one Cloudflare DDNS check and persist the result on site_settings."""
    settings = session.get(SiteSettings, 1)
    if settings is None:
        settings = SiteSettings(id=1)
        session.add(settings)
        session.flush()

    normalize_cloudflare_ddns_settings(settings)
    checked_at = now or datetime.now(UTC)

    if not settings.cloudflare_ddns_enabled:
        _mark_check_result(settings, checked_at=checked_at, result="Disabled")
        session.add(settings)
        session.commit()
        session.refresh(settings)
        return settings

    zone_id = (settings.cloudflare_ddns_zone_id or "").strip()
    if not zone_id:
        _mark_check_result(settings, checked_at=checked_at, result="Configuration error", error="Cloudflare zone ID is required.")
        session.add(settings)
        session.commit()
        session.refresh(settings)
        return settings

    try:
        api_token = decrypt_secret(settings.cloudflare_ddns_encrypted_api_token)
    except IntegrationSecretError as exc:
        _mark_check_result(settings, checked_at=checked_at, result="Configuration error", error=str(exc))
        session.add(settings)
        session.commit()
        session.refresh(settings)
        return settings

    if not api_token:
        _mark_check_result(settings, checked_at=checked_at, result="Configuration error", error="Cloudflare API token is required.")
        session.add(settings)
        session.commit()
        session.refresh(settings)
        return settings

    created_client = client is None
    if created_client:
        client = httpx.AsyncClient(follow_redirects=True)

    public_ip: str | None = None
    updated = 0
    unchanged = 0
    errors: list[str] = []
    try:
        public_ip = await _fetch_public_ipv4(client)
        for record_name in normalize_cloudflare_record_names(settings.cloudflare_ddns_record_names):
            try:
                record = await _find_cloudflare_a_record(client, zone_id=zone_id, api_token=api_token, record_name=record_name)
                record_id = str(record.get("id") or "")
                if not record_id:
                    raise RuntimeError(f"Cloudflare A record has no record ID: {record_name}.")
                if record.get("content") == public_ip and record.get("proxied") is False:
                    unchanged += 1
                    continue
                await _patch_cloudflare_a_record(
                    client,
                    zone_id=zone_id,
                    api_token=api_token,
                    record_id=record_id,
                    record_name=record_name,
                    public_ip=public_ip,
                )
                updated += 1
            except Exception as exc:
                errors.append(f"{record_name}: {exc}")
    except Exception as exc:
        errors.append(str(exc))
    finally:
        if created_client:
            await client.aclose()

    if errors:
        result = f"Updated {updated}, unchanged {unchanged}, failed {len(errors)}"
        _mark_check_result(settings, checked_at=checked_at, public_ip=public_ip, result=result, error="; ".join(errors))
    elif updated:
        _mark_check_result(settings, checked_at=checked_at, public_ip=public_ip, result=f"Updated {updated} record(s) to {public_ip}")
    else:
        _mark_check_result(settings, checked_at=checked_at, public_ip=public_ip, result=f"Already current: {unchanged} record(s)")

    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


async def _cloudflare_ddns_loop() -> None:
    await asyncio.sleep(60)
    while True:
        interval_seconds = DEFAULT_CHECK_INTERVAL_HOURS * 3600
        session = SessionLocal()
        try:
            settings = await run_cloudflare_ddns_check(session)
            interval_seconds = cloudflare_ddns_interval_seconds(settings)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Cloudflare DDNS sync failed unexpectedly", exc_info=True)
        finally:
            session.close()
        await asyncio.sleep(interval_seconds)


async def start_cloudflare_ddns_sync() -> asyncio.Task[None]:
    task = asyncio.create_task(_cloudflare_ddns_loop(), name="cloudflare-ddns-sync")
    logger.info("Cloudflare DDNS sync background task started")
    return task
