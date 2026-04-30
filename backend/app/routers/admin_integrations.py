from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import require_admin
from app.models import IntegrationCredential, User
from app.schemas import IntegrationCredentialsResponse, IntegrationCredentialsUpdate
from app.services.integration_credentials import (
    DEFAULT_CLIENT_ID_HEADER,
    DEFAULT_CLIENT_SECRET_HEADER,
    DEFAULT_FAA_NOTAM_BASE_URL,
    FAA_NOTAMS_PROVIDER,
    IntegrationSecretError,
    admin_credentials_configured,
    build_faa_notams_probe_url,
    encrypt_secret,
    env_credentials_configured,
    env_has_faa_override,
    get_effective_faa_notams_credentials,
    get_or_create_credentials_row,
    normalize_base_url,
    normalize_provider,
)

router = APIRouter(prefix="/api/admin/integrations", tags=["admin-integrations"])


def _row_or_default(row: IntegrationCredential | None) -> dict[str, object]:
    return {
        "base_url": row.base_url if row else DEFAULT_FAA_NOTAM_BASE_URL,
        "client_id_header": row.client_id_header if row else DEFAULT_CLIENT_ID_HEADER,
        "client_secret_header": row.client_secret_header if row else DEFAULT_CLIENT_SECRET_HEADER,
        "last_tested_at": row.last_tested_at if row else None,
        "last_test_status": row.last_test_status if row else None,
        "last_test_message": row.last_test_message if row else None,
        "updated_by_user_id": row.updated_by_user_id if row else None,
        "updated_at": row.updated_at if row else None,
    }


def _response(session: Session, provider: str = FAA_NOTAMS_PROVIDER) -> IntegrationCredentialsResponse:
    provider = normalize_provider(provider)
    row = session.get(IntegrationCredential, provider)
    admin_id_configured, admin_secret_configured = admin_credentials_configured(row)
    env_id_configured, env_secret_configured = env_credentials_configured()
    effective = get_effective_faa_notams_credentials(session)
    env_override = env_has_faa_override()
    defaults = _row_or_default(row)
    return IntegrationCredentialsResponse(
        provider=provider,
        enabled=effective.enabled,
        base_url=effective.base_url if env_override else str(defaults["base_url"]),
        client_id_header=effective.client_id_header if env_override else str(defaults["client_id_header"]),
        client_secret_header=effective.client_secret_header if env_override else str(defaults["client_secret_header"]),
        client_id_configured=env_id_configured or admin_id_configured,
        client_secret_configured=env_secret_configured or admin_secret_configured,
        admin_client_id_configured=admin_id_configured,
        admin_client_secret_configured=admin_secret_configured,
        credential_source=effective.source,
        env_override=env_override,
        last_tested_at=defaults["last_tested_at"],
        last_test_status=defaults["last_test_status"],
        last_test_message=defaults["last_test_message"],
        updated_by_user_id=defaults["updated_by_user_id"],
        updated_at=defaults["updated_at"],
    )


def _trim_header_name(value: str, fallback: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        return fallback
    return trimmed


@router.get("", response_model=list[IntegrationCredentialsResponse])
def list_integrations(
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[IntegrationCredentialsResponse]:
    return [_response(session, FAA_NOTAMS_PROVIDER)]


@router.get("/{provider}", response_model=IntegrationCredentialsResponse)
def get_integration(
    provider: str,
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> IntegrationCredentialsResponse:
    try:
        return _response(session, provider)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/{provider}", response_model=IntegrationCredentialsResponse)
def update_integration(
    provider: str,
    payload: IntegrationCredentialsUpdate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> IntegrationCredentialsResponse:
    try:
        provider = normalize_provider(provider)
        base_url = normalize_base_url(payload.base_url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    row = get_or_create_credentials_row(session, provider)
    row.enabled = payload.enabled
    row.base_url = base_url
    row.client_id_header = _trim_header_name(payload.client_id_header, DEFAULT_CLIENT_ID_HEADER)
    row.client_secret_header = _trim_header_name(payload.client_secret_header, DEFAULT_CLIENT_SECRET_HEADER)
    row.updated_by_user_id = admin.id

    if payload.clear_credentials:
        row.encrypted_client_id = None
        row.encrypted_client_secret = None
    else:
        client_id = (payload.client_id or "").strip()
        client_secret = (payload.client_secret or "").strip()
        try:
            if client_id:
                row.encrypted_client_id = encrypt_secret(client_id)
            if client_secret:
                row.encrypted_client_secret = encrypt_secret(client_secret)
        except IntegrationSecretError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    session.add(row)
    session.commit()
    session.refresh(row)
    return _response(session, provider)


async def _probe_faa_connection(session: Session) -> tuple[str, str]:
    credentials = get_effective_faa_notams_credentials(session)
    if not credentials.enabled:
        return "error", "FAA NOTAMS API is disabled."
    if not credentials.configured:
        return "error", "Client ID and client secret are required."

    probe_url = build_faa_notams_probe_url(credentials.base_url)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            response = await client.get(probe_url, headers=credentials.auth_headers())
    except httpx.HTTPError as exc:
        return "error", f"Could not reach FAA NOTAMS API: {exc}"

    if response.status_code in {401, 403}:
        return "error", f"FAA rejected the configured credentials ({response.status_code})."
    if response.status_code >= 500:
        return "error", f"FAA NOTAMS API returned {response.status_code}."
    return "success", f"FAA NOTAMS API reachable ({response.status_code})."


@router.post("/{provider}/test", response_model=IntegrationCredentialsResponse)
async def test_integration(
    provider: str,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> IntegrationCredentialsResponse:
    try:
        provider = normalize_provider(provider)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    row = get_or_create_credentials_row(session, provider)
    test_status, message = await _probe_faa_connection(session)
    row.last_tested_at = datetime.now(timezone.utc)
    row.last_test_status = test_status
    row.last_test_message = message
    row.updated_by_user_id = admin.id
    session.add(row)
    session.commit()
    session.refresh(row)
    return _response(session, provider)
