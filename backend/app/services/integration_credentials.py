from __future__ import annotations

import base64
import hashlib
import logging
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import IntegrationCredential

logger = logging.getLogger(__name__)

FAA_NOTAMS_PROVIDER = "faa_notams"
DEFAULT_FAA_NOTAM_BASE_URL = "https://api.faa.gov"
DEFAULT_CLIENT_ID_HEADER = "client_id"
DEFAULT_CLIENT_SECRET_HEADER = "client_secret"
SUPPORTED_PROVIDERS = {FAA_NOTAMS_PROVIDER}


class IntegrationSecretError(RuntimeError):
    pass


@dataclass(frozen=True)
class FaaNotamsCredentials:
    enabled: bool
    base_url: str
    client_id: str | None
    client_secret: str | None
    client_id_header: str
    client_secret_header: str
    source: str

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def auth_headers(self) -> dict[str, str]:
        if not self.configured:
            return {}
        return {
            self.client_id_header: self.client_id or "",
            self.client_secret_header: self.client_secret or "",
        }


def normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported integration provider: {provider}")
    return normalized


def normalize_base_url(value: str | None) -> str:
    base_url = (value or DEFAULT_FAA_NOTAM_BASE_URL).strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("FAA API base URL must be a valid http(s) URL.")
    return base_url


def build_faa_notams_probe_url(base_url: str) -> str:
    parsed = urlparse(normalize_base_url(base_url))
    path = parsed.path.rstrip("/")
    if "notamapi" in path.lower():
        return normalize_base_url(base_url)
    return urljoin(normalize_base_url(base_url) + "/", "notamapi/v1/")


def build_faa_notams_query_url(base_url: str) -> str:
    probe_url = build_faa_notams_probe_url(base_url)
    path = urlparse(probe_url).path.rstrip("/").lower()
    if path.endswith("/notams"):
        return probe_url
    return urljoin(probe_url.rstrip("/") + "/", "notams")


def get_or_create_credentials_row(session: Session, provider: str = FAA_NOTAMS_PROVIDER) -> IntegrationCredential:
    provider = normalize_provider(provider)
    row = session.get(IntegrationCredential, provider)
    if row is None:
        row = IntegrationCredential(
            provider=provider,
            enabled=False,
            base_url=DEFAULT_FAA_NOTAM_BASE_URL,
            client_id_header=DEFAULT_CLIENT_ID_HEADER,
            client_secret_header=DEFAULT_CLIENT_SECRET_HEADER,
        )
        session.add(row)
        session.flush()
    return row


def get_credentials_row(session: Session, provider: str = FAA_NOTAMS_PROVIDER) -> IntegrationCredential | None:
    return session.get(IntegrationCredential, normalize_provider(provider))


def _settings_fernet() -> Fernet | None:
    raw_key = (get_settings().integration_secret_key or "").strip()
    if not raw_key:
        return None
    key_bytes = raw_key.encode("utf-8")
    try:
        return Fernet(key_bytes)
    except ValueError:
        derived = base64.urlsafe_b64encode(hashlib.sha256(key_bytes).digest())
        return Fernet(derived)


def encrypt_secret(value: str) -> str:
    fernet = _settings_fernet()
    if fernet is None:
        raise IntegrationSecretError("INTEGRATION_SECRET_KEY is required to save API credentials.")
    return fernet.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    fernet = _settings_fernet()
    if fernet is None:
        raise IntegrationSecretError("INTEGRATION_SECRET_KEY is required to read saved API credentials.")
    try:
        return fernet.decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise IntegrationSecretError("Saved integration credentials could not be decrypted.") from exc


def admin_credentials_configured(row: IntegrationCredential | None) -> tuple[bool, bool]:
    if row is None:
        return False, False
    return bool(row.encrypted_client_id), bool(row.encrypted_client_secret)


def env_credentials_configured() -> tuple[bool, bool]:
    settings = get_settings()
    return bool(settings.faa_notam_api_client_id), bool(settings.faa_notam_api_client_secret)


def env_has_faa_override() -> bool:
    settings = get_settings()
    return bool(
        settings.faa_notam_api_enabled
        or settings.faa_notam_api_client_id
        or settings.faa_notam_api_client_secret
    )


def get_effective_faa_notams_credentials(session: Session | None = None) -> FaaNotamsCredentials:
    settings = get_settings()
    if settings.faa_notam_api_client_id or settings.faa_notam_api_client_secret or settings.faa_notam_api_enabled:
        return FaaNotamsCredentials(
            enabled=settings.faa_notam_api_enabled,
            base_url=normalize_base_url(settings.faa_notam_api_base_url),
            client_id=settings.faa_notam_api_client_id,
            client_secret=settings.faa_notam_api_client_secret,
            client_id_header=(settings.faa_notam_api_client_id_header or DEFAULT_CLIENT_ID_HEADER).strip(),
            client_secret_header=(settings.faa_notam_api_client_secret_header or DEFAULT_CLIENT_SECRET_HEADER).strip(),
            source="environment",
        )

    if session is None:
        return FaaNotamsCredentials(
            enabled=False,
            base_url=DEFAULT_FAA_NOTAM_BASE_URL,
            client_id=None,
            client_secret=None,
            client_id_header=DEFAULT_CLIENT_ID_HEADER,
            client_secret_header=DEFAULT_CLIENT_SECRET_HEADER,
            source="none",
        )

    row = get_credentials_row(session)
    if row is None:
        return FaaNotamsCredentials(
            enabled=False,
            base_url=DEFAULT_FAA_NOTAM_BASE_URL,
            client_id=None,
            client_secret=None,
            client_id_header=DEFAULT_CLIENT_ID_HEADER,
            client_secret_header=DEFAULT_CLIENT_SECRET_HEADER,
            source="none",
        )

    try:
        client_id = decrypt_secret(row.encrypted_client_id)
        client_secret = decrypt_secret(row.encrypted_client_secret)
    except IntegrationSecretError:
        logger.warning("FAA NOTAMS credentials are saved but cannot be decrypted.", exc_info=True)
        client_id = None
        client_secret = None

    return FaaNotamsCredentials(
        enabled=bool(row.enabled),
        base_url=normalize_base_url(row.base_url),
        client_id=client_id,
        client_secret=client_secret,
        client_id_header=(row.client_id_header or DEFAULT_CLIENT_ID_HEADER).strip(),
        client_secret_header=(row.client_secret_header or DEFAULT_CLIENT_SECRET_HEADER).strip(),
        source="admin" if client_id or client_secret else "none",
    )
