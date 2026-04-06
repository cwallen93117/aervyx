import logging
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_logger = logging.getLogger(__name__)

_INSECURE_DEFAULT_KEY = "change-me"


class Settings(BaseSettings):
    app_name: str = "Aervyx API"
    app_env: str = "development"
    app_secret_key: str = _INSECURE_DEFAULT_KEY
    app_public_url: str = "http://localhost:3000"
    api_public_url: str = "http://localhost:8000"
    database_url: str = f"sqlite:///{(Path(__file__).resolve().parents[2] / 'flightcomp.db').as_posix()}"
    upload_root: str = str(Path(__file__).resolve().parents[2] / "storage" / "uploads")
    apk_root: str = str(Path(__file__).resolve().parents[2] / "storage" / "apks")
    access_token_expire_minutes: int = 1440  # 24 hours
    refresh_token_expire_days: int = 30
    max_upload_size_mb: int = 10
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://10.0.2.2:8000"])
    allowed_hosts: list[str] = Field(
        default_factory=lambda: [
            "localhost",
            "127.0.0.1",
            "10.0.2.2",
            "backend",
            "frontend",
            "192.168.87.56",
            "aervyx.net",
            "api.aervyx.net",
        ]
    )
    google_client_id: str | None = None
    google_client_secret: str | None = None
    mesh_channel_psk: str | None = None
    mqtt_host: str | None = None
    mqtt_port: int = 1883
    mesh_mqtt_topic_prefix: str = "aervyx"
    valhalla_url: str = "http://valhalla:8002"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    Path(settings.upload_root).mkdir(parents=True, exist_ok=True)
    Path(settings.apk_root).mkdir(parents=True, exist_ok=True)

    if settings.app_secret_key == _INSECURE_DEFAULT_KEY:
        if settings.app_env.lower() == "production":
            raise RuntimeError(
                "CRITICAL: APP_SECRET_KEY is still the insecure default 'change-me'. "
                "Set a strong random secret via the APP_SECRET_KEY environment variable "
                "before running in production."
            )
        # Development: generate an ephemeral key so tokens work in dev but
        # invalidate on every restart (safe reminder to set a real key).
        settings.app_secret_key = secrets.token_urlsafe(64)
        _logger.warning(
            "APP_SECRET_KEY not set — using ephemeral random key. "
            "Tokens will not survive restarts. Set APP_SECRET_KEY in .env for persistence."
        )

    return settings
