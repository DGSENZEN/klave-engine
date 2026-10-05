"""Las variantes por API: listar, proponer el mapeo, confirmarlo (queda
etiqueta), olvidarlo — y el presupuesto se recalcula con lo decidido."""

import json

from klave_engine.costing.catalog_store import get_catalog_store
from klave_engine.costing.etiquetas import read_labels
from klave_engine.costing.models import CostingOverrides
from klave_engine.costing.recompute import recompute_and_persist
from klave_engine.detection.results import DetectionType, make_detection


def _project(data_dir):
    pid = "obra-variantes"
    root = data_dir / "projects" / pid
    processed = root / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    (processed / "project_manifest.json").write_text(json.dumps({
        "project_id": pid, "project_name": "Obra", "root_path": str(root), "drawings": [],
    }))
    (data_dir / "projects_registry.json").write_text(json.dumps({pid: str(root)}))
    dets = []
    for i, (sec, arm) in enumerate([("30x40", "8#5"), ("30x40", "8#5"), ("15x15", "4#3")]):
        dets.append(make_detection(
            f"c{i}", DetectionType.column_tag, "EST-COL", (i * 5, 0, i * 5 + 0.4, 0.4), 0.9,
            [f"c{i}"], "tag", [],
            {"section_cm": sec, "spec_rebar": arm, "section_area_du2": 0.0,
             "section_source": "cuadro", "has_nearby_grid": True}, "e.dxf",
        ).model_dump(mode="json"))
    (processed / "detections.json").write_text(json.dumps(dets))
    (processed / "drawing_units.json").write_text(json.dumps(
        {"unit": "m", "source": "declared", "confidence": 1.0}
    ))
    store = get_catalog_store(data_dir)
    store.upsert_insumo("MAT-X", description="X", unit="M3", resource_type="material",
                        unit_cost=100.0)
    store.create_concept(
        code="EMC-30X40", description="Columna de concreto armado f'c=250 kg/cm2 30x40 cm",
        unit="M3", phase="Estructura", production_rate_per_day=2.0,
        components=[("MAT-X", 40.0)],
    )
    recompute_and_persist(processed, processed, root / "reports", pid, CostingOverrides(),
                          catalog_store=store)
    return pid, processed


def test_variants_map_confirm_label_and_forget(data_dir, monkeypatch):
    from fastapi.testclient import TestClient
    from klave_engine.common import config as config_module

    from apps.api.main import create_app

    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    config_module.get_settings.cache_clear()
    pid, processed = _project(data_dir)
    client = TestClient(create_app())

    listed = client.get(f"/projects/{pid}/variantes").json()
    est = next(line for line in listed["lines"] if line["concept_code"] == "EST-001")
    keys = {v["key"] for v in est["variants"]}
    assert keys == {"EST-001.30X40-8N5", "EST-001.15X15-4N3"}
    assert listed["counts"]["sin_mapear"] >= 2

    mapped = client.post(f"/projects/{pid}/variantes/mapear", json={},
                         headers={"X-Actor": "Diego"})
    assert mapped.status_code == 200, mapped.text
    assert mapped.json()["sin_catalogo"] is False

    confirmed = client.put(
        f"/projects/{pid}/variantes/EST-001.30X40-8N5",
        json={"status": "confirmada", "target_kind": "concept", "target_code": "EMC-30X40"},
        headers={"X-Actor": "Diego"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["clave"] == "EMC-30X40" and confirmed.json()["actor"] == "Diego"
    after = client.get(f"/projects/{pid}/variantes").json()
    big = next(v for line in after["lines"] for v in line["variants"]
               if v["key"] == "EST-001.30X40-8N5")
    # Con el precio de la matriz del taller: 40 × $100 = $4,000 por m³.
    assert big["clave"] == "EMC-30X40" and big["unit_price"] == 4000.0
    assert big["mapping"] == "confirmada"

    labels = [lab for lab in read_labels(processed) if lab["kind"] == "mapeo"]
    assert labels[-1]["verdict"]["target_code"] == "EMC-30X40"
    assert labels[-1]["actor"] == "Diego"

    bad = client.put(f"/projects/{pid}/variantes/EST-001.30X40-8N5",
                     json={"status": "confirmada"})
    assert bad.status_code == 422
    assert client.put(f"/projects/{pid}/variantes/NO.EXISTE",
                      json={"status": "sin_equivalente"}).status_code == 404

    review = client.put(f"/projects/{pid}/reviews/detections/c2",
                        json={"status": "excluded"}, headers={"X-Actor": "Diego"})
    assert review.status_code == 200
    det_label = [lab for lab in read_labels(processed) if lab["kind"] == "deteccion"][-1]
    assert det_label["verdict"] == "excluded" and det_label["element"]["type"] == "column_tag"
    assert det_label["element"]["properties"]["section_cm"] == "15x15"

    forgot = client.delete(f"/projects/{pid}/variantes/EST-001.30X40-8N5")
    assert forgot.status_code == 200 and forgot.json()["removed"] is True
