"""Las propuestas del lector: sólo lo que pasa el umbral y cabe en la
ventana, a lo más N por hoja, con su razón en palabras y sin puntaje; lo que
una persona resolvió no vuelve; confirmar entra como elemento omitido con la
medida del recuadro."""

import json

from klave_engine.costing.etiquetas import read_labels
from klave_engine.costing.reviews import load_reviews
from klave_engine.lector.modelo import Modelo
from klave_engine.lector.propuestas import clave, proponer

# Un árbol: ancho ≤ 0.5 m → +4 (elemento), si no → -4.
MODELO = Modelo(version="t", nombres=("a",) * 6, base=0.0,
                arboles=(((0.0, 0, 0.5, True, 1, 2, False), (4.0, 0, 0, False, 0, 0, True),
                          (-4.0, 0, 0, False, 0, 0, True)),),
                umbral=0.5, max_por_hoja=2)


def _cand(i, ancho, hoja="e.dxf", bloque="B"):
    return {"entity_id": f"e{i}", "hoja": hoja, "bloque": bloque, "capa": "X",
            "bbox": [i * 10.0, 0.0, i * 10.0 + ancho, ancho],
            "features": {"ancho_m": ancho, "alto_m": ancho, "proporcion": 1.0,
                         "dist_eje_m": 0.02, "repeticion_bloque": 7}}


def test_umbral_ventana_tope_y_razon():
    cands = [_cand(0, 0.3), _cand(1, 0.4), _cand(2, 0.45), _cand(3, 1.2), _cand(4, 0.05)]
    out = proponer(cands, MODELO, 1.0, set())
    assert len(out) == 2  # tope por hoja; 1.2 m no pasa, 0.05 m está fuera de la ventana
    assert "sobre un cruce de ejes" in out[0]["razon"] and "7 veces" in out[0]["razon"]
    assert all("score" not in p and "probabilidad" not in json.dumps(p) for p in out)
    assert proponer([_cand(0, 0.3, hoja="10-10_acabados_l_04.dxf")], MODELO, 1.0, set()) == []
    # Con plantas reconocidas, sólo lo que cae dentro de una.
    dentro = proponer(cands, MODELO, 1.0, set(), [(-1.0, -1.0, 5.0, 5.0)])
    assert [p["key"] for p in dentro] == [clave(cands[0], 1.0)]
    # Una figura y su achurado encimados: una sola propuesta.
    doble = [_cand(0, 0.3), {**_cand(0, 0.3), "entity_id": "achurado"}]
    assert len(proponer(doble, MODELO, 1.0, set())) == 1
    resuelta = clave(cands[0], 1.0)
    assert resuelta not in {p["key"] for p in proponer(cands, MODELO, 1.0, {resuelta})}


def test_la_clave_sobrevive_a_renumerar():
    a, b = _cand(0, 0.3), _cand(0, 0.3)
    b["entity_id"] = "otro"
    assert clave(a, 1.0) == clave(b, 1.0)


def _project(data_dir):
    pid = "obra-propuestas"
    root = data_dir / "projects" / pid
    processed = root / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    (processed / "project_manifest.json").write_text(json.dumps({
        "project_id": pid, "project_name": "Obra", "root_path": str(root), "drawings": [],
    }))
    (data_dir / "projects_registry.json").write_text(json.dumps({pid: str(root)}))
    (processed / "detections.json").write_text("[]")
    (processed / "drawing_units.json").write_text(
        json.dumps({"unit": "m", "source": "declared", "confidence": 1.0}))
    props = proponer([_cand(0, 0.3, hoja="E-01.dxf", bloque="K15"), _cand(1, 0.4)],
                     MODELO, 1.0, set())
    (processed / "propuestas.json").write_text(json.dumps(props))
    return pid, processed, props


def test_confirmar_y_descartar(data_dir, monkeypatch):
    from fastapi.testclient import TestClient
    from klave_engine.common import config as config_module

    from apps.api.main import create_app

    config_module.get_settings.cache_clear()
    pid, processed, props = _project(data_dir)
    client = TestClient(create_app())
    listed = client.get(f"/projects/{pid}/propuestas").json()
    assert len(listed["propuestas"]) == 2 and "features" not in listed["propuestas"][0]
    k0, k1 = props[0]["key"], props[1]["key"]
    malo = client.post(f"/projects/{pid}/propuestas/{k0}/confirmar", json={"family": "trabe"})
    assert malo.status_code == 422 and "Lo que Klave no vio" in malo.json()["detail"]["message"]
    ok = client.post(f"/projects/{pid}/propuestas/{k0}/confirmar", json={"family": "castillo"},
                     headers={"X-Actor": "Diego"})
    assert ok.status_code == 200, ok.text
    om = load_reviews(processed).omitted[-1]
    assert (om.family, om.section_cm, om.sheet, om.count) == ("castillo", "30x30", "E-01", 1)
    assert om.bbox == props[0]["bbox"] and "recuadro" in om.note
    assert client.post(f"/projects/{pid}/propuestas/{k1}/descartar").status_code == 200
    assert client.get(f"/projects/{pid}/propuestas").json()["propuestas"] == []
    acciones = [lab["action"] for lab in read_labels(processed) if lab.get("kind") == "propuesta"]
    assert acciones == ["confirm_proposal", "reject_proposal"]
    assert client.post(f"/projects/{pid}/propuestas/{k1}/descartar").status_code == 404
