"""Application configuration via pydantic-settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KLAVE_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    converted_dir_name: str = "converted"
    processed_dir_name: str = "processed"
    reports_dir: Path = Path("reports")

    converter_executable_path: Path | None = None
    overwrite_converted_files: bool = False
    converter_timeout_seconds: int = 120
    max_upload_bytes: int = 100 * 1024 * 1024
    max_concurrent_jobs: int = 2
    max_queued_jobs: int = 8

    log_level: str = "INFO"
    detector_config_path: Path | None = None
    costing_config_path: Path | None = None

    # Drawing units are unknown unless detected or configured.
    assumed_unit: str = "drawing_units"

    # Workspace accounts: a dedicated PostgreSQL instance (docker compose
    # service `users-db`), deliberately separate from the cost-data platform's
    # database. The local compose credentials below are not production secrets.
    users_database_url: str = "postgresql://klave_users:klave@127.0.0.1:5433/klave_users"
    web_origin: str = "http://localhost:3000"
    auth_google_id: str | None = None
    auth_google_secret: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
