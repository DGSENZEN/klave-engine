"""KLAVE_ENV=production shuts the developer conveniences and refuses to boot
half-configured."""

import pytest
from klave_engine.common.config import Settings

from apps.api.main import _validate_production_config


def test_production_validation_names_each_problem():
    with pytest.raises(RuntimeError) as excinfo:
        _validate_production_config(Settings(env="production"))
    message = str(excinfo.value)
    assert "localhost" in message and "KLAVE_USERS_DATABASE_URL" in message

    ok = Settings(
        env="production",
        web_origin="https://app.taller.mx",
        users_database_url="postgresql://klave_users:s3cret@db.internal:5432/klave_users",
    )
    _validate_production_config(ok)  # no raise


def test_localhost_origins_are_dev_only(monkeypatch, data_dir):
    from klave_engine.common import config as config_module

    from apps.api.auth.middleware import origin_allowed

    monkeypatch.setenv("KLAVE_ENV", "dev")
    config_module.get_settings.cache_clear()
    assert origin_allowed("http://localhost:5173")
    monkeypatch.setenv("KLAVE_ENV", "production")
    monkeypatch.setenv("KLAVE_WEB_ORIGIN", "https://app.taller.mx")
    config_module.get_settings.cache_clear()
    assert not origin_allowed("http://localhost:5173")
    assert origin_allowed("https://app.taller.mx")
    config_module.get_settings.cache_clear()
