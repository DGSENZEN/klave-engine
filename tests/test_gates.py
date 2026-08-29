"""Los candados del tablero: la firma del administrador, asentada."""

import json
from pathlib import Path

from klave_engine.costing.reviews import GateState, ProjectReviews, load_reviews, save_reviews


def test_el_candado_persiste_con_firma(tmp_path):
    control = tmp_path / "processed"
    control.mkdir()
    reviews = load_reviews(control)
    assert reviews.gates == {}
    from datetime import UTC, datetime
    reviews.gates["programa"] = GateState(
        approved_at=datetime.now(UTC), approved_by="Diego"
    )
    save_reviews(control, reviews)

    releido = load_reviews(control)
    assert releido.gates["programa"].approved_by == "Diego"
    assert releido.gates["programa"].approved_at is not None


def test_el_endpoint_abre_y_cierra_el_candado(data_dir, monkeypatch):
    from fastapi.testclient import TestClient

    from klave_engine.common import config as config_module

    from apps.api.main import create_app

    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    config_module.get_settings.cache_clear()

    pid = "obra-gates"
    root = data_dir / "projects" / pid
    (root / "processed").mkdir(parents=True, exist_ok=True)
    (root / "processed" / "project_manifest.json").write_text(json.dumps({
        "project_id": pid, "project_name": "Obra", "root_path": str(root), "drawings": [],
    }))
    (data_dir / "projects_registry.json").write_text(json.dumps({pid: str(root)}))

    client = TestClient(create_app())
    r = client.put(f"/projects/{pid}/gates/programa",
                   json={"approved": True}, headers={"X-Actor": "Diego"})
    assert r.status_code == 200, r.text
    assert r.json()["gates"]["programa"]["approved_by"] == "Diego"

    r2 = client.put(f"/projects/{pid}/gates/programa", json={"approved": False})
    assert r2.status_code == 200 and "programa" not in r2.json()["gates"]

    r3 = client.put(f"/projects/{pid}/gates/nada", json={"approved": True})
    assert r3.status_code == 422


def test_el_tablero_degrada_a_pendiente_sin_artefactos(data_dir, monkeypatch):
    """Sin corrida ni manifest completo, cada nodo dice «pendiente» — nunca 500."""
    from fastapi.testclient import TestClient

    from klave_engine.common import config as config_module

    from apps.api.main import create_app

    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    config_module.get_settings.cache_clear()

    pid = "obra-tablero"
    root = data_dir / "projects" / pid
    (root / "processed").mkdir(parents=True, exist_ok=True)
    (root / "processed" / "project_manifest.json").write_text(json.dumps({
        "project_id": pid, "project_name": "Obra", "root_path": str(root), "drawings": [],
    }))
    (data_dir / "projects_registry.json").write_text(json.dumps({pid: str(root)}))

    client = TestClient(create_app())
    client.put(f"/projects/{pid}/gates/programa",
               json={"approved": True}, headers={"X-Actor": "Diego"})

    r = client.get(f"/projects/{pid}/tablero")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["my_role"] is None  # modo abierto: sin cuentas, sin rol
    assert set(body["nodes"]) == {
        "planos", "revision", "catalogo", "presupuesto", "programa", "contrato",
    }
    assert body["nodes"]["planos"]["estado"] == "pendiente"
    assert body["nodes"]["catalogo"]["estado"] == "pendiente"
    # El candado abierto se refleja; el contrato sigue cerrado y dice qué falta.
    assert body["nodes"]["programa"]["estado"] == "ok"
    assert body["gates"]["programa"]["approved_by"] == "Diego"
    assert body["nodes"]["contrato"]["estado"] == "bloqueado"
    labels = [c["label"] for c in body["nodes"]["contrato"]["chips"]]
    assert any("verificación" in l for l in labels)
    for node in body["nodes"].values():
        for chip in node["chips"]:
            assert chip["tone"] in ("ok", "warn", "bad", "muted")
