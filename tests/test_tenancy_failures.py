"""User-database outages must not switch protected projects to shared prices."""

import sqlite3
from contextlib import closing

import pytest
from klave_engine.common.config import Settings
from klave_engine.costing.catalog_store import get_catalog_store

from apps.api import tenancy
from apps.api.auth.store import UsersDbUnavailable


class UnavailableUsers:
    """Mirror UserStore's has_users signal and per-operation connection failures."""

    def __init__(self, failure_at, last_known_has_users=None, has_users=True):
        self.failure_at = failure_at
        self.last_known_has_users = last_known_has_users
        self.protected = has_users

    def has_users(self):
        if self.failure_at == "has_users":
            raise UsersDbUnavailable()
        self.last_known_has_users = self.protected
        return self.protected

    def default_workspace(self):
        if self.failure_at == "workspace":
            raise UsersDbUnavailable()
        return {"workspace_id": "ws-default"}

    def project_workspace_id(self, _project_id):
        if self.failure_at == "workspace":
            raise UsersDbUnavailable()
        return "ws-default"


@pytest.mark.parametrize("failure_at", ["has_users", "workspace"])
@pytest.mark.parametrize(
    ("environment", "last_known"), [("production", None), ("dev", True)]
)
def test_protected_project_lookup_outage_cannot_open_shared_catalog(
    data_dir, monkeypatch, failure_at, environment, last_known
):
    settings = Settings(data_dir=data_dir, env=environment)
    users = UnavailableUsers(failure_at, last_known_has_users=last_known)
    monkeypatch.setattr(tenancy, "get_user_store", lambda _url: users)

    with pytest.raises(UsersDbUnavailable):
        tenancy.store_for_project(settings, "project-a")

    assert not (data_dir / "catalog.db").exists()
    assert not (data_dir / "catalogs").exists()


@pytest.mark.parametrize("consumer", [tenancy.workspace_store, tenancy.defaults_scope])
@pytest.mark.parametrize("failure_at", ["has_users", "workspace"])
def test_default_workspace_lookup_outage_cannot_skip_legacy_adoption(
    data_dir, monkeypatch, consumer, failure_at
):
    settings = Settings(data_dir=data_dir)
    users = UnavailableUsers(failure_at, last_known_has_users=True)
    monkeypatch.setattr(tenancy, "get_user_store", lambda _url: users)

    with pytest.raises(UsersDbUnavailable):
        consumer(settings, "ws-default")

    assert not (data_dir / "catalogs").exists()


def test_lookup_failure_after_has_users_is_not_development_open_mode(data_dir, monkeypatch):
    settings = Settings(data_dir=data_dir, env="dev")
    users = UnavailableUsers("workspace")
    monkeypatch.setattr(tenancy, "get_user_store", lambda _url: users)

    with pytest.raises(UsersDbUnavailable):
        tenancy.store_for_project(settings, "project-a")

    assert not (data_dir / "catalog.db").exists()


@pytest.mark.parametrize("last_known", [None, False])
def test_never_protected_development_can_use_legacy_when_users_database_is_down(
    data_dir, monkeypatch, last_known
):
    settings = Settings(data_dir=data_dir, env="dev")
    users = UnavailableUsers("has_users", last_known_has_users=last_known)
    monkeypatch.setattr(tenancy, "get_user_store", lambda _url: users)

    catalog = tenancy.store_for_project(settings, "local-project")

    assert catalog.workspace_id is None
    assert catalog.db_path == data_dir / "catalog.db"
    assert tenancy.default_workspace_id(settings) is None


def test_default_workspace_adopts_committed_prices_from_live_legacy_wal(data_dir, monkeypatch):
    settings = Settings(data_dir=data_dir)
    legacy = get_catalog_store(data_dir)
    monkeypatch.setattr(tenancy, "default_workspace_id", lambda _settings: "ws-default")

    # Keep a live connection so committed changes remain in WAL rather than
    # being checkpointed when CatalogStore closes its per-operation connection.
    with closing(sqlite3.connect(legacy.db_path)) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA wal_autocheckpoint = 0")
        connection.execute("UPDATE insumos SET unit_cost = 876.0 WHERE code = 'MAT-BLOCK'")
        connection.commit()

        adopted = tenancy.workspace_store(settings, "ws-default")

        assert adopted.load_price_book()["MAT-BLOCK"].unit_cost == 876.0
