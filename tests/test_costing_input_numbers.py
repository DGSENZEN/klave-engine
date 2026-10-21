"""Invalid numbers must be rejected before changing a project's money inputs."""

import pytest
from fastapi.testclient import TestClient

from tests.test_variantes_api import _project


@pytest.mark.parametrize("overrides", [
    {"insumo_prices": {"MAT-X": "Infinity"}},
    {"config": {"assumptions": {"wall_height_m": "NaN"}}},
    {"config": {"indirects": {"profit_pct": "Infinity"}}},
    {"config": {"schedule": {"phase_overlap_pct": "NaN"}}},
    {"config": {"financial": {"retention_pct": "Infinity"}}},
    {"config": {"oficina_share_pct": "NaN"}},
    {"config": {"desglose_campo": {"rubros": [{"concepto": "Rent", "importe": "NaN"}]}}},
    {"config": {"financiamiento": {"tasa_anual": "Infinity"}}},
    {"config": {"cargos_adicionales": [{"concepto": "Fee", "pct": "NaN"}]}},
    {"config": {"plantilla_campo": [{"puesto": "Resident", "salario_mensual": "NaN"}]}},
])
def test_recompute_rejects_non_finite_nested_inputs_without_persisting(data_dir, overrides):
    from apps.api.main import create_app

    pid, processed = _project(data_dir)
    before = {path.name: path.read_bytes() for path in processed.iterdir() if path.is_file()}
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(f"/projects/{pid}/recompute", json=overrides)

    assert response.status_code == 422, response.text
    after = {path.name: path.read_bytes() for path in processed.iterdir() if path.is_file()}
    assert after == before


@pytest.mark.parametrize("quantity_field", ["quantity_delta", "quantity_set"])
def test_manual_adjustment_rejects_non_finite_quantity_without_persisting(data_dir, quantity_field):
    from apps.api.main import create_app

    pid, processed = _project(data_dir)
    client = TestClient(create_app(), raise_server_exceptions=False)
    before = {path.name: path.read_bytes() for path in processed.iterdir() if path.is_file()}
    response = client.post(f"/projects/{pid}/reviews/adjustments", json={
        "concept_code": "EST-001", quantity_field: "Infinity", "note": "Field measurement",
    })

    assert response.status_code == 422, response.text
    after = {path.name: path.read_bytes() for path in processed.iterdir() if path.is_file()}
    assert after == before


def test_workspace_defaults_reject_non_finite_configuration(data_dir):
    from apps.api.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)
    before = client.get("/workspace/defaults").json()

    response = client.put("/workspace/defaults", json={
        "config": {"assumptions": {"column_height_m": "NaN"}},
    })

    assert response.status_code == 422, response.text
    assert client.get("/workspace/defaults").json() == before
