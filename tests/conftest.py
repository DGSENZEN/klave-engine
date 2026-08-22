"""Shared fixtures: isolated data dir, fresh settings, isolated stores."""

import pytest
from klave_engine.common import config as config_module


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Point KLAVE_DATA_DIR at a temp dir and reset cached settings/stores."""
    directory = tmp_path / "data"
    directory.mkdir()
    monkeypatch.setenv("KLAVE_DATA_DIR", str(directory))
    config_module.get_settings.cache_clear()

    import klave_engine.costing.catalog_store as catalog_store_module

    catalog_store_module._STORES.clear()
    yield directory
    config_module.get_settings.cache_clear()
