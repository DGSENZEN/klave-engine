"""Application configuration via pydantic-settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KLAVE_", env_file=".env", extra="ignore")

    # "dev" (default): localhost origins are welcome. "production": only the
    # configured origins may bring credentials, and startup validates the
    # deployment configuration out loud.
    env: str = "dev"  # dev | production

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

    # Retention: runs (with their reports and croquis) a project keeps after
    # each reprocess; the active run always survives. Versions are never pruned.
    keep_runs: int = 3
    keep_jobs: int = 10

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
    # Hosted deployments: share the session cookie across app/api subdomains
    # (e.g. ".taller.mx"), or go cross-site with SameSite=None (HTTPS only).
    cookie_domain: str | None = None
    cookie_samesite: str = "lax"  # lax | none | strict
    # Explicit override for the session cookie's Secure flag; None derives it
    # from web_origin (https) or SameSite=None.
    cookie_secure: bool | None = None
    # Extra browser origins allowed to call the API with credentials.
    extra_origins: str = ""  # comma-separated
    # Lectura con IA: anthropic | gemini | auto (auto prefers whichever has
    # credentials, Claude first); ai_model overrides the provider's default.
    # Account creation: "open" (anyone founds or asks to join) or
    # "invite_only" (only invitation links create accounts).
    registration: str = "open"

    ai_provider: str = "auto"
    ai_model: str | None = None
    # Tope mensual de gasto estimado en IA por taller, en USD. 0 = sin tope.
    # Es un freno, no un aviso: al llegar, la siguiente llamada se rechaza.
    ai_budget_usd: float = 0.0

    auth_google_id: str | None = None
    auth_google_secret: str | None = None

    # Workspace identity for this deployment: one taller per deploy; more can
    # be created from the CLI (apps.api.auth.cli) and share the server.
    workspace_slug: str = "taller"
    workspace_name: str = "Taller"

    # Transactional mail. "auto" picks Resend when a key is set, SMTP when a
    # host is set, and otherwise the local outbox (data/outbox/*.json) — in
    # which case the UI says no mail is configured and admins hand links over.
    mail_provider: str = "auto"  # auto | resend | smtp | outbox
    mail_from: str = "Klave <no-reply@localhost>"
    resend_api_key: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
