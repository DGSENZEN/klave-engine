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

    log_level: str = "INFO"
    detector_config_path: Path | None = None
    costing_config_path: Path | None = None

    # Drawing units are unknown unless detected or configured.
    assumed_unit: str = "drawing_units"


@lru_cache
def get_settings() -> Settings:
    return Settings()
