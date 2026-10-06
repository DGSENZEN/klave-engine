"""El perfil del taller: tres confirmaciones de un bloque y ninguna en contra
lo vuelven regla de esta oficina (sólo para lo que se cuenta por pieza); lo
que la oficina excluye nunca se quita, entra con una duda."""

from klave_engine.costing.catalog_store import CatalogStore
from klave_engine.costing.perfil import aplicar_perfil, aprender, firmes
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.taxonomy import enrich_detections


def _rec(action, tipo="column_tag", bloque="CAST15", capa="EST-CAST", family="castillo",
         verdict=None):
    return {"kind": "deteccion", "action": action, "verdict": verdict or action,
            "element": {"type": tipo, "family": family,
                        "properties": {"block_name": bloque, "layer": capa}}}


def _cand(eid, bloque="CAST15", hoja="e.dxf", x=5.0):
    return {"entity_id": eid, "hoja": hoja, "bloque": bloque, "capa": "EST-CAST",
            "bbox": [x, 5.0, x + 0.15, 5.15]}


def test_tres_confirmaciones_vuelven_firme_un_bloque(tmp_path):
    store = CatalogStore(tmp_path / "c.db")
    aprender(store, [_rec("confirmed")] * 2, [])
    assert firmes(store.load_perfil())[0] == []
    aprender(store, [_rec("confirmed")], [])
    positivas, _ = firmes(store.load_perfil())
    assert [(p["value"], p["family"]) for p in positivas] == [("CAST15", "castillo")]
    # Una sola exclusión en contra le quita lo firme.
    aprender(store, [_rec("excluded")], [])
    assert firmes(store.load_perfil())[0] == []


def test_reasignar_y_agregar_omitido_ensenan_el_bloque(tmp_path):
    store = CatalogStore(tmp_path / "c.db")
    reasignar = _rec("reassign", tipo="footing", bloque="PIL60", family="zapata",
                     verdict="pilote")
    omitido = {"kind": "omitido", "action": "add_missed", "verdict": "pilote",
               "bbox": [0, 4, 1, 6]}
    aprender(store, [reasignar, omitido, omitido], [_cand("p", "PIL60", x=0.4)])
    perfil = {(p["value"], p["detection_type"]): p for p in store.load_perfil()}
    assert perfil[("PIL60", "pile")]["a_favor"] == 3
    assert perfil[("PIL60", "footing")]["en_contra"] == 1


def test_aplicar_agrega_lo_firme_y_duda_de_lo_que_se_excluye(tmp_path):
    store = CatalogStore(tmp_path / "c.db")
    aprender(store, [_rec("confirmed")] * 3, [])
    aprender(store, [_rec("excluded", tipo="wall", bloque="", capa="A-MURO-FALSO",
                          family="muro")] * 3, [])
    muro = make_detection("m", DetectionType.wall, "", (0, 0, 4, 0.15), 0.9, ["m"], "muro",
                          [], {"layer": "A-MURO-FALSO"}, "/p/e.dxf")
    dets, agregadas, dudas = aplicar_perfil([muro], [_cand("k1"), _cand("otro", "X")],
                                            store.load_perfil())
    assert (agregadas, dudas) == (1, 1)
    enrich_detections(dets, 1.0)
    nueva = next(d for d in dets if d.evidence.method == "perfil_del_taller")
    assert nueva.family == "castillo" and nueva.evidence.source == "/p/e.dxf"
    assert "excluyó 3" in next(d for d in dets if d.detection_id == "m").properties["perfil_duda"]


def test_bloque_firme_de_familia_lineal_no_actua(tmp_path):
    store = CatalogStore(tmp_path / "c.db")
    aprender(store, [_rec("confirmed", tipo="beam_tag", bloque="TR", family="trabe")] * 5, [])
    assert firmes(store.load_perfil())[0] == []


def test_olvidar(tmp_path):
    store = CatalogStore(tmp_path / "c.db")
    aprender(store, [_rec("confirmed")], [])
    clave = store.load_perfil()[0]["clave"]
    assert store.delete_perfil(clave) and store.load_perfil()[0]["value"] == "EST-CAST"
