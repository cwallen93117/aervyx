from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Aervyx API"
    app_env: str = "development"
    app_secret_key: str = "change-me"
    app_public_url: str = "http://localhost:3000"
    api_public_url: str = "http://localhost:8000"
    database_url: str = f"sqlite:///{(Path(__file__).resolve().parents[2] / 'flightcomp.db').as_posix()}"
    upload_root: str = str(Path(__file__).resolve().parents[2] / "storage" / "uploads")
    access_token_expire_minutes: int = 720
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
    mesh_channel_psk: str | None = None
    mqtt_host: str | None = None
    mqtt_port: int = 1883
    mesh_mqtt_topic_prefix: str = "aervyx"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    Path(settings.upload_root).mkdir(parents=True, exist_ok=True)
    return settings
