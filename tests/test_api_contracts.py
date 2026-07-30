"""API contract tests: full create -> process -> inspect flow over the demo project."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from klave_engine.common.config import Settings
from klave_engine.evals.fixtures import write_demo_project

from apps.api.dependencies import get_settings as api_get_settings
from apps.api.main import create_app


def _wait_for_processing(client: TestClient, project_id: str) -> dict:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = client.get(f"/projects/{project_id}/status")
        assert response.status_code == 200, response.text
        status = response.json()
        if status["state"] == "processed":
            return status
        if status["state"] == "failed":
            pytest.fail(status.get("error") or "processing failed")
        time.sleep(0.02)
    pytest.fail("processing did not finish within 10 seconds")


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
    assert process.status_code == 202, process.text
    _wait_for_processing(client, project_id)
    return project_id


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_invalid_root_path_is_structured_error(client: TestClient) -> None:
    response = client.post("/projects", json={"project_name": "x", "root_path": "/nope"})
    assert response.status_code == 400
    assert response.json()["detail"]["error_type"] == "invalid_root_path"


def test_external_project_root_is_rejected(client: TestClient, tmp_path: Path) -> None:
    response = client.post(
        "/projects", json={"project_name": "x", "root_path": str(tmp_path)}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error_type"] == "unmanaged_project_root"


def test_upload_rejects_path_like_filename(client: TestClient) -> None:
    response = client.post(
        "/projects/upload",
        files={"file": ("../escape.dxf", b"0\nSECTION\n2\nHEADER\n0\nEOF\n")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error_type"] == "invalid_filename"


def test_upload_rejects_content_type_spoofing(client: TestClient) -> None:
    response = client.post(
        "/projects/upload", files={"file": ("plano.dxf", b"not a drawing")}
    )
    assert response.status_code == 422
    assert response.json()["detail"]["error_type"] == "invalid_file_signature"


def test_upload_accepts_uppercase_dxf_extension(client: TestClient) -> None:
    data_dir = client.app.dependency_overrides[api_get_settings]().data_dir
    drawing = data_dir / "demo_project_001" / "drawings" / "S-101.dxf"
    response = client.post(
        "/projects/upload", files={"file": ("S-101.DXF", drawing.read_bytes())}
    )

    assert response.status_code == 202, response.text
    _wait_for_processing(client, response.json()["project_id"])
    project = client.get(f"/projects/{response.json()['project_id']}").json()
    assert project["processing_status"] == "processed"
    assert project["source_files"][0]["path"] == "drawings/source.dxf"


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
        f"/projects/{project_id}/detections", params={"min_confidence": 0.9}
    ).json()
    assert confident["total"] < everything["total"]
    assert all(d["confidence"] >= 0.9 for d in confident["detections"])


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


def test_recompute_publishes_derived_cost_without_mutating_run(
    client: TestClient, project_id: str
) -> None:
    before = client.get(f"/projects/{project_id}/costs").json()
    response = client.post(
        f"/projects/{project_id}/recompute",
        json={"insumo_prices": {"MAT-CONC250": 5300.0}},
    )

    assert response.status_code == 200, response.text
    after = client.get(f"/projects/{project_id}/costs").json()
    assert after["boq"]["direct_cost_total"] > before["boq"]["direct_cost_total"]
    root = client.app.dependency_overrides[api_get_settings]().data_dir / "demo_project_001"
    control = root / "processed"
    assert (control / "cost_report_override.json").exists()
    assert not (control / "cost_report.json").exists()
