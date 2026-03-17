from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FlightComp Platform API"
    app_env: str = "development"
    app_secret_key: str = "change-me"
    database_url: str = f"sqlite:///{(Path(__file__).resolve().parents[2] / 'flightcomp.db').as_posix()}"
    upload_root: str = str(Path(__file__).resolve().parents[2] / "storage" / "uploads")
    access_token_expire_minutes: int = 720
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

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