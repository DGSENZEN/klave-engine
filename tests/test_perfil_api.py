"""El perfil por API: revisar en el proyecto enseña al taller, el catálogo lo
muestra con lo que ya actúa, y «Olvidar» lo quita."""

import json

from klave_engine.costing.catalog_store import get_catalog_store
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.taxonomy import enrich_detections


def _project(data_dir):
    pid = "obra-perfil"
    root = data_dir / "projects" / pid
    processed = root / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    (processed / "project_manifest.json").write_text(json.dumps({
        "project_id": pid, "project_name": "Obra", "root_path": str(root), "drawings": [],
    }))
    (data_dir / "projects_registry.json").write_text(json.dumps({pid: str(root)}))
    dets = [make_detection(
        f"k{i}", DetectionType.column_tag, "K-1", (i * 5, 0, i * 5 + 0.15, 0.15), 0.9,
        [f"k{i}"], "tag", [], {"block_name": "CAST15", "layer": "EST-CAST"}, "e.dxf",
    ) for i in range(3)]
    enrich_detections(dets, 1.0)
    (processed / "detections.json").write_text(
        json.dumps([d.model_dump(mode="json") for d in dets])
    )
    return pid


def test_revisar_ensena_al_taller_y_olvidar_lo_quita(data_dir, monkeypatch):
    from fastapi.testclient import TestClient
    from klave_engine.common import config as config_module

    from apps.api.main import create_app

    config_module.get_settings.cache_clear()
    pid = _project(data_dir)
    client = TestClient(create_app())
    keys = [d["display_label"] for d in json.loads(
        (data_dir / "projects" / pid / "processed" / "detections.json").read_text())]
    r = client.put(f"/projects/{pid}/reviews/detections",
                   json={"keys": keys, "status": "confirmed", "recompute": False})
    assert r.status_code == 200, r.text
    perfil = client.get("/catalog/perfil").json()
    bloque = next(e for e in perfil["entradas"] if e["kind"] == "bloque")
    assert (bloque["value"], bloque["a_favor"], bloque["actua"]) == ("CAST15", 3, "agrega")
    assert get_catalog_store(data_dir).load_perfil()
    gone = client.delete(f"/catalog/perfil/{bloque['clave']}")
    assert gone.status_code == 200
    assert all(e["kind"] != "bloque" for e in client.get("/catalog/perfil").json()["entradas"])
    assert client.delete("/catalog/perfil/bloque|nada|x").status_code == 404
