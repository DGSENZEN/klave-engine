"""Shared fixtures: isolated data dir, fresh settings, isolated stores."""

import pytest
from klave_engine.common import config as config_module


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Point KLAVE_DATA_DIR at a temp dir and reset cached settings/stores."""
    directory = tmp_path / "data"
    directory.mkdir()
    monkeypatch.setenv("KLAVE_DATA_DIR", str(directory))
    # Ninguna prueba toca la base de usuarios de quien corre la suite: con una
    # cuenta creada en desarrollo, la API pasa a modo protegido y las pruebas
    # de endpoints fallaban con 401 según la máquina. La que necesite usuarios
    # pone su propia URL después de esto.
    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    config_module.get_settings.cache_clear()

    import klave_engine.costing.catalog_store as catalog_store_module

    catalog_store_module._STORES.clear()
    yield directory
    config_module.get_settings.cache_clear()
