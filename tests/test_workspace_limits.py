from fastapi.testclient import TestClient
from klave_engine.common.config import get_settings


def test_overview_reports_configured_limits(data_dir, monkeypatch):
    from apps.api.main import create_app

    monkeypatch.setenv("KLAVE_MAX_UPLOAD_BYTES", "123456")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.get("/workspace/overview")
    assert response.status_code == 200
    assert response.json()["upload_limits"] == {"max_files": 40, "max_file_bytes": 123456}
