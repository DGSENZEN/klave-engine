"""Un archivo de importación demasiado grande se rechaza con un mensaje que
dice el límite, y una base de oficina exportada a Excel cabe en el límite."""

from klave_engine.common import config as config_module

from apps.api.routes import catalog as catalog_routes


def _client(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    config_module.get_settings.cache_clear()
    return TestClient(create_app())


def test_an_office_base_in_excel_fits():
    # Una base de conceptos con matrices exportada a Excel pasa de 1 MB con
    # facilidad; el tope de antes la rechazaba entera.
    assert catalog_routes.MAX_IMPORT_BYTES >= 10_000_000


def test_too_large_import_says_its_limit(data_dir, monkeypatch):
    monkeypatch.setattr(catalog_routes, "MAX_IMPORT_BYTES", 1_000)
    client = _client(monkeypatch)
    for path in ("/catalog/import-prices", "/catalog/import-matrices"):
        response = client.post(
            path, files={"file": ("base.csv", b"x" * 2_000, "text/csv")}
        )
        assert response.status_code == 413, (path, response.text)
        detail = response.json()["detail"]
        assert detail["error_type"] == "import_too_large" and detail["max_bytes"] == 1_000
        assert "1 KB" in detail["message"] or "0 MB" in detail["message"], detail["message"]
