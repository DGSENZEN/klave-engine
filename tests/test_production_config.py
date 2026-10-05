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
        registration="invite_only",
    )
    _validate_production_config(ok)  # no raise
    with pytest.raises(RuntimeError, match="KLAVE_REGISTRATION"):
        _validate_production_config(ok.model_copy(update={"registration": "open"}))


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



class _Store:
    """Una base de usuarios de mentira: vacía o caída."""

    def __init__(self, has_users=False, down=False, last_known=None):
        self._has, self._down, self.last_known_has_users = has_users, down, last_known

    def has_users(self):
        from apps.api.auth.store import UsersDbUnavailable

        if self._down:
            raise UsersDbUnavailable()
        return self._has


def _client_with(monkeypatch, data_dir, env, store):
    from fastapi.testclient import TestClient
    from klave_engine.common import config as config_module

    import apps.api.auth.middleware as middleware
    from apps.api.main import create_app

    monkeypatch.setenv("KLAVE_ENV", env)
    monkeypatch.setenv("KLAVE_WEB_ORIGIN", "https://app.taller.mx")
    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://u:p@db.internal:5432/u")
    monkeypatch.setenv("KLAVE_REGISTRATION", "invite_only")
    config_module.get_settings.cache_clear()
    monkeypatch.setattr(middleware, "get_user_store", lambda _url: store)
    return TestClient(create_app())


def test_production_without_accounts_opens_nothing(monkeypatch, data_dir):
    client = _client_with(monkeypatch, data_dir, "production", _Store(has_users=False))
    r = client.get("/catalog")
    assert r.status_code == 403 and r.json()["detail"]["error_type"] == "setup_required"
    assert client.get("/health").status_code == 200


def test_production_with_users_db_down_fails_closed_even_after_restart(monkeypatch, data_dir):
    store = _Store(down=True, last_known=None)  # recién reiniciado: no recuerda
    client = _client_with(monkeypatch, data_dir, "production", store)
    assert client.get("/catalog").status_code == 503


def test_dev_keeps_the_local_open_mode(monkeypatch, data_dir):
    client = _client_with(monkeypatch, data_dir, "dev", _Store(has_users=False))
    assert client.get("/catalog").status_code == 200
