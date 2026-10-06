"""El lector robusto: lo no revisado pesa poco, las decisiones mandan, un
proyecto (o su plano en otro proyecto) se califica con el pliegue que no lo
vio, el conjunto revisado por personas mide y frena la promoción, y un
taller que descarta casi todo pone al lector en pausa."""

import json

import pytest
from klave_engine.costing.catalog_store import CatalogStore
from klave_engine.lector import entrenar, oro
from klave_engine.lector.modelo import Modelo, opaco
from klave_engine.lector.propuestas import clave, estado_del_taller

HOJA = ((1.0, 0, 0, False, 0, 0, True),)  # un árbol de una hoja: +1
MENOS = ((-1.0, 0, 0, False, 0, 0, True),)


def _modelo(**kw):
    base = {"version": "t", "nombres": ("a",) * 6, "base": 0.0, "arboles": (HOJA,),
            "umbral": 0.5, "max_por_hoja": 25}
    return Modelo(**{**base, **kw})


def test_el_pliegue_por_proyecto_y_por_plano():
    m = _modelo(pliegues={opaco("obra-a"): (0.0, (MENOS,))},
                dibujos={opaco("obra-a"): frozenset({"abc123abc123abc1"})})
    x = [None] * 6
    assert m.puntuar(x) > 0.5
    assert m.para("obra-a").puntuar(x) < 0.5  # entrenó con ella
    assert m.para("obra-b", {"abc123abc123abc1" + "f" * 48}).puntuar(x) < 0.5  # su plano
    assert m.para("obra-c", {"0" * 64}).puntuar(x) > 0.5  # nada en común


def _proyecto(tmp_path, nombre="obra"):
    root = tmp_path / nombre
    p = root / "processed"
    p.mkdir(parents=True)
    (p / "project_manifest.json").write_text(json.dumps({"project_id": nombre}))
    (p / "detections.json").write_text("[]")
    (p / "drawing_units.json").write_text(
        json.dumps({"unit": "m", "source": "declared", "confidence": 1.0}))
    f = {"ancho_m": 0.3, "alto_m": 0.3, "proporcion": 1.0, "dist_eje_m": 0.1,
         "repeticion_bloque": 4}
    cands = [{"entity_id": f"e{i}", "hoja": "e.dxf", "bloque": "", "bbox": [i, 0, i + 0.3, 0.3],
              "features": f, "features_version": 1} for i in range(3)]
    (p / "candidates.jsonl").write_text("\n".join(json.dumps(c) for c in cands))
    return root, p, cands, f


def test_pesos_y_decisiones_reemplazan_lo_no_revisado(tmp_path):
    root, p, cands, f = _proyecto(tmp_path)
    (p / "labels.jsonl").write_text(json.dumps({
        "kind": "propuesta", "action": "confirm_proposal", "key": clave(cands[0], 1.0),
        "features": f}) + "\n")
    filas = entrenar.ejemplos(root)
    pesos = sorted((y, w) for _, y, w in filas)
    assert pesos == [(0, 0.3), (0, 0.3), (1, 5.0)]


def test_oro_captura_mide_y_frena_la_promocion(tmp_path):
    root, p, cands, f = _proyecto(tmp_path)
    (p / "labels.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"kind": "propuesta", "action": "reject_proposal", "key": "pr_a", "features": f},
        {"kind": "propuesta", "action": "confirm_proposal", "key": "pr_a", "features": f},
        {"kind": "propuesta", "action": "reject_proposal", "key": "pr_b", "features": f},
    ]))
    path = oro.capturar(root, "prueba", tmp_path / "oro")
    data = json.loads(path.read_text())
    assert data["proyecto"] == opaco("obra") and data["elementos"] == 1  # vale la última
    assert "bbox" not in json.dumps(data) and "obra" not in json.dumps(data)
    sube = oro.evaluar(_modelo(), data)
    assert (sube["precision"], sube["alcance"]) == (0.5, 1.0)
    ok, razones = entrenar.puede_promoverse(
        {}, {}, {"prueba": {"precision": 0.5, "alcance": 0.5}},
        {"prueba": {"precision": 0.5, "alcance": 1.0}})
    assert not ok and "alcance" in razones[0]


def test_pausa_por_taller(tmp_path):
    store = CatalogStore(tmp_path / "c.db")
    for i in range(19):
        store.lector_registrar("t", f"k{i}", "reject_proposal")
    assert not estado_del_taller(store)["pausado"]  # aún no hay 20 decisiones
    store.lector_registrar("t", "k19", "confirm_proposal")
    estado = estado_del_taller(store)
    assert estado["pausado"] and estado["confirmadas"] == 1 and estado["decisiones"] == 20
    store.set_setting("lector_reanudado", {"at": "9999"})
    assert not estado_del_taller(store)["pausado"]


def test_promocion_por_proyecto():
    ok, _ = entrenar.puede_promoverse({"a": {"precision": 0.9}}, {"a": {"precision": 0.905}})
    peor, razones = entrenar.puede_promoverse({"a": {"precision": 0.8}}, {"a": {"precision": 0.9}})
    assert ok and not peor and razones


def test_necesita_dos_proyectos(tmp_path, monkeypatch):
    pytest.importorskip("sklearn")
    monkeypatch.setattr(oro, "ORO", tmp_path / "vacio")
    monkeypatch.setattr(oro, "cargar", lambda destino=None: [])
    root, *_ = _proyecto(tmp_path)
    salida: list[str] = []
    assert entrenar.entrenar([root], salida=salida.append) == 1 and "dos proyectos" in salida[0]
