"""API contract tests: full create -> process -> inspect flow over the demo project."""

import pytest
from fastapi.testclient import TestClient
from klave_engine.common.config import Settings
from klave_engine.evals.fixtures import write_demo_project

from apps.api.dependencies import get_settings as api_get_settings
from apps.api.main import create_app


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    data_dir = tmp_path_factory.mktemp("api_data")
    write_demo_project(data_dir / "demo_project_001")
    app = create_app()
    app.dependency_overrides[api_get_settings] = lambda: Settings(data_dir=data_dir)
    return TestClient(app)


@pytest.fixture(scope="module")
def project_id(client: TestClient) -> str:
    root = client.app.dependency_overrides[api_get_settings]().data_dir / "demo_project_001"
    response = client.post(
        "/projects", json={"project_name": "Demo", "root_path": str(root)}
    )
    assert response.status_code == 201, response.text
    project_id = response.json()["project_id"]
    process = client.post(f"/projects/{project_id}/process")
    assert process.status_code == 200, process.text
    return project_id


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_invalid_root_path_is_structured_error(client: TestClient) -> None:
    response = client.post("/projects", json={"project_name": "x", "root_path": "/nope"})
    assert response.status_code == 400
    assert response.json()["detail"]["error_type"] == "invalid_root_path"


def test_unknown_project_is_404(client: TestClient) -> None:
    response = client.get("/projects/does_not_exist")
    assert response.status_code == 404
    assert response.json()["detail"]["error_type"] == "project_not_found"


def test_get_project_manifest(client: TestClient, project_id: str) -> None:
    response = client.get(f"/projects/{project_id}")
    body = response.json()
    assert response.status_code == 200
    assert body["processing_status"] == "processed"
    assert body["source_files"][0]["sheet_number"] == "S-101"


def test_entities_endpoint_filters(client: TestClient, project_id: str) -> None:
    response = client.get(
        f"/projects/{project_id}/entities", params={"layer": "S-GRID", "limit": 5}
    )
    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 8  # 4 grid lines + 4 grid labels
    assert len(body["entities"]) == 5
    assert all(e["layer"] == "S-GRID" for e in body["entities"])


def test_graph_endpoint(client: TestClient, project_id: str) -> None:
    response = client.get(f"/projects/{project_id}/graph", params={"include_elements": False})
    body = response.json()
    assert response.status_code == 200
    assert body["node_count_by_type"]["grid_intersection"] == 4
    assert body["node_count_by_type"]["column_tag"] == 3


def test_detections_endpoint_min_confidence(client: TestClient, project_id: str) -> None:
    everything = client.get(f"/projects/{project_id}/detections").json()
    confident = client.get(
        f"/projects/{project_id}/detections", params={"min_confidence": 0.7}
    ).json()
    assert confident["total"] < everything["total"]
    assert all(d["confidence"] >= 0.7 for d in confident["detections"])


def test_quantities_endpoint(client: TestClient, project_id: str) -> None:
    body = client.get(f"/projects/{project_id}/quantities").json()
    values = {item["name"]: item["value"] for item in body["items"]}
    assert values["column_tag_count"] == 3
    assert values["estimated_slab_area"] == 120000.0
    assert body["assumed_unit"] == "drawing_units"


def test_risks_endpoint(client: TestClient, project_id: str) -> None:
    body = client.get(f"/projects/{project_id}/risks").json()
    risk_types = {f["risk_type"] for f in body["findings"]}
    assert "unresolved_detail_reference" in risk_types


def test_report_endpoint(client: TestClient, project_id: str) -> None:
    body = client.get(f"/projects/{project_id}/report").json()
    assert "# Project Summary" in body["markdown"]
