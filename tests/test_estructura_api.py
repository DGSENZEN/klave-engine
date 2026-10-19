"""Tarea 13: la lectura estructural por API — leer el modelo que vale para la corrida activa, sus
elementos por familia, y la decisión de una persona que se guarda, queda como etiqueta y recalcula
(o se quita y el presupuesto queda como si nunca hubiera estado). El router se prueba montado en
su propia app (``main.py`` lo monta aparte); el acceso, con el middleware de siempre."""

import json
import threading
import time
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from klave_engine.common.config import get_settings
from klave_engine.common.io import read_json, write_json
from klave_engine.costing.catalog_store import get_catalog_store
from klave_engine.costing.etiquetas import read_labels
from klave_engine.costing.models import CostingOverrides
from klave_engine.costing.recompute import recompute_and_persist
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.schedules import ElementSpec, ScheduleInventory
from klave_engine.detection.views import SheetSegmentation, ViewKind, ViewRegion
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.estructura.modelo import (
    DECISIONES_FILENAME,
    ESTRUCTURA_DERIVADA_FILENAME,
    ESTRUCTURA_FILENAME,
    Decision,
    construir_estructura,
    escribir_estructura,
    guardar_decision,
)
from klave_engine.evals.fixtures import write_demo_project
from klave_engine.graph.evidence import EvidencePacket
from klave_engine.pipeline import run_full_pipeline

from apps.api.routes import estructura as estructura_routes

# ----------------------------------------------------------------------------------- la obra


def _texto(eid, texto, x, y, h=0.1):
    return NormalizedEntity(
        entity_id=eid,
        entity_type=EntityType.text,
        source_file="a.dxf",
        layer="0",
        bbox=(x, y, x + 0.6 * h * len(texto), y + h),
        raw_handle=eid.upper(),
        properties={"height": h},
        evidence=EvidencePacket(source="a.dxf", method="t"),
        text=texto,
    )


def _spec(marca, familia, seccion, hoja, eid, rebar="4#4", stirrups="E#3@15", **kw):
    return ElementSpec(
        mark=marca,
        family=familia,
        section_cm=seccion,
        rebar=rebar,
        stirrups=stirrups,
        source="cuadro",
        source_text=f"{marca} {seccion[0]}X{seccion[1]} {rebar} {stirrups}",
        confidence=1.0,
        hoja=hoja,
        hoja_llave=f"a.dxf#{hoja}",
        metodo="fila",
        campos_con_texto=["seccion", "longitudinales", "estribos"],
        entidades=[eid],
        **kw,
    )


def _det(det_id, marca, familia, x, y, eid, tipo=DetectionType.column_tag, **props):
    d = make_detection(
        det_id, tipo, marca, (x, y, x + 0.3, y + 0.1), 0.9, [eid], "t", [], props, "a.dxf"
    )
    d.mark, d.family = marca, familia
    return d


_MARCOS = [
    SheetFrame(frame_id="f1", bbox=(0, 0, 100, 100), source_file="a.dxf", code="ES-100"),
    SheetFrame(frame_id="f2", bbox=(200, 0, 300, 100), source_file="a.dxf", code="ES-200"),
    SheetFrame(frame_id="f4", bbox=(400, 0, 500, 100), source_file="a.dxf", code="ES-400"),
]


def _planta(dets):
    """La planta de ES-100 a +0.00 bajo una azotea a +2.90: su entrepiso se lee (2.9 m)."""
    return SheetSegmentation(
        views=[
            ViewRegion(
                view_id="f1",
                title="ES-100 · PLANTA",
                kind=ViewKind.plan,
                level_key="planta",
                npt_level=0.0,
                anchor=(0, 0),
                bbox=(0, 0, 100, 100),
            ),
            ViewRegion(
                view_id="fz",
                title="AZOTEA",
                kind=ViewKind.plan,
                level_key="azotea",
                npt_level=2.9,
                anchor=(0, 0),
                bbox=(600, 0, 700, 100),
            ),
        ],  # fmt: skip
        assignment={d.detection_id: "f1" for d in dets},
        is_segmented=True,
        npt_levels=[0.0, 2.9],
    )


def _lectura():
    """K-5: castillo que el cuadro de ES-200 dice 20x30 y el de ES-400 20x40 (una contradicción),
    colocado dos veces en ES-100. T-1: trabe 25x50 del cuadro, colocada con claros medidos de 4 y
    5 m. CI: dala con variantes por muro (15 y 20 cm), colocada sobre un muro medido de 15 cm (toma
    esa variante) y sobre uno sin medir (toma la definición de la marca)."""
    textos = [
        _texto("t200", "K-5", 210, 10),
        _texto("t400", "K-5", 410, 10),
        _texto("p1", "K-5", 10, 10),
        _texto("p2", "K-5", 30, 10),
        _texto("tt1", "T-1", 220, 30),
        _texto("b1", "T-1", 10, 40),
        _texto("b2", "T-1", 30, 40),
        _texto("tci15", "CI", 230, 50),
        _texto("tci20", "CI", 250, 50),
        _texto("c1", "CI", 10, 70),
        _texto("c2", "CI", 30, 70),
    ]
    dets = [
        _det("d1", "K-5", "castillo", 10, 10, "p1"),
        _det("d2", "K-5", "castillo", 30, 10, "p2"),
        _det("v1", "T-1", "trabe", 10, 40, "b1", DetectionType.beam_tag, estimated_span_length=4.0),
        _det("v2", "T-1", "trabe", 30, 40, "b2", DetectionType.beam_tag, estimated_span_length=5.0),
        _det("ci1", "CI", "dala", 10, 70, "c1", DetectionType.beam_tag, estimated_span_length=3.0,
             muro_espesor=0.15, muro_caras=["W1", "W2"]),
        _det("ci2", "CI", "dala", 30, 70, "c2", DetectionType.beam_tag, estimated_span_length=3.0),
    ]  # fmt: skip
    inv = ScheduleInventory(
        specs=[
            _spec("K-5", "castillo", (20, 30), "ES-200", "t200"),
            _spec("K-5", "castillo", (20, 40), "ES-400", "t400"),
            _spec("T-1", "trabe", (25, 50), "ES-200", "tt1", rebar="3#5", stirrups="E#3@20"),
            _spec("CI", "dala", (15, 20), "ES-200", "tci15", rebar="4#3", stirrups="E#2@15",
                  para_muro_cm=15.0),
            _spec("CI", "dala", (20, 20), "ES-200", "tci20", rebar="4#3", stirrups="E#2@15",
                  para_muro_cm=20.0),
        ]
    )  # fmt: skip
    return textos, dets, inv, _planta(dets)


def _registrar(data_dir, pid):
    root = data_dir / "projects" / pid
    processed = root / get_settings().processed_dir_name
    processed.mkdir(parents=True, exist_ok=True)
    (processed / "project_manifest.json").write_text(
        json.dumps({"project_id": pid, "project_name": "Obra", "root_path": str(root),
                    "drawings": []})
    )  # fmt: skip
    registro = data_dir / "projects_registry.json"
    actual = json.loads(registro.read_text()) if registro.exists() else {}
    registro.write_text(json.dumps({**actual, pid: str(root)}))
    return root, processed


def _obra(data_dir, pid="obra-estructura", *, con_estructura=True, recalcular=True):
    """Una corrida procesada con todo lo que el recálculo y las verificaciones leen; con
    ``recalcular``, ya recalculada una vez (su escenario derivado es el punto de partida)."""
    root, processed = _registrar(data_dir, pid)
    textos, dets, inv, seg = _lectura()
    write_json(processed / "normalized_entities.json", textos)
    write_json(processed / "schedules.json", inv)
    write_json(processed / "detections.json", dets)
    write_json(processed / "views.json", seg)
    write_json(processed / "frames.json", _MARCOS)
    write_json(
        processed / "drawing_units.json", {"unit": "m", "source": "declared", "confidence": 1.0}
    )
    if con_estructura:
        e = construir_estructura(textos, _MARCOS, inv, dets, seg, 1.0, 2.9)
        escribir_estructura(processed, e)
    if recalcular:
        recompute_and_persist(
            processed, processed, root / "reports", pid, CostingOverrides(),
            catalog_store=get_catalog_store(data_dir),
        )  # fmt: skip
    return pid, processed


def _app():
    app = FastAPI()
    app.include_router(estructura_routes.router)
    return app


def _client():
    return TestClient(_app())


def _decidir(client, pid, actor="Diego", **body):
    return client.post(
        f"/projects/{pid}/estructura/decisiones", json=body, headers={"X-Actor": actor}
    )


def _quitar(client, pid, actor="Diego", **params):
    return client.delete(
        f"/projects/{pid}/estructura/decisiones", params=params, headers={"X-Actor": actor}
    )


def _ids(body):
    return {v["id"] for v in body["verificaciones"]}


def _costo(processed):
    report = read_json(processed / "cost_report_override.json")
    return {
        line["concept_code"]: (line["quantity"], line["amount"]) for line in report["boq"]["lines"]
    }


# ------------------------------------------------------------------------- las pruebas del plan


def test_get_estructura_and_decide(data_dir):
    pid, processed = _obra(data_dir)
    client = _client()
    body = client.get(f"/projects/{pid}/estructura").json()
    assert body["disponible"] is True and body["al_dia"] is True
    assert {"resumen", "verificaciones", "reglas", "avisos", "escrituras"} <= set(body)
    contradiccion = next(v for v in body["verificaciones"] if v["numero"] == 8)
    r = _decidir(client, pid, marca="K-5", campo="seccion_cm", valor=[20, 40], nota="hoja PA")
    assert r.status_code == 200, r.text
    nuevo = r.json()
    # the decision answered its finding; every other id stays (Task 11/12: stable ids)
    assert contradiccion["id"] not in _ids(nuevo)
    assert _ids(nuevo) == _ids(body) - {contradiccion["id"]}
    assert nuevo["al_dia"] is True and [d["marca"] for d in nuevo["decisiones"]] == ["K-5"]
    labels = [x for x in read_labels(processed) if x.get("action") == "decide_value"]
    assert len(labels) == 1
    label = labels[0]
    assert label["kind"] == "estructura" and label["marca"] == "K-5"
    assert label["campo"] == "seccion_cm" and label["valor"] == [20, 40]
    assert label["actor"] == "Diego" and label["nota"] == "hoja PA"
    # what was there: the cuadro's reading, in conflict, with its source
    assert label["antes"]["fuente"] == "cuadro"
    assert {tuple(x["valor"]) for x in label["del_plano"]} >= {(20, 30), (20, 40)}


def test_old_run_is_not_an_error(data_dir):
    pid, _ = _obra(data_dir, con_estructura=False, recalcular=False)
    r = _client().get(f"/projects/{pid}/estructura")
    assert r.status_code == 200
    body = r.json()
    assert body["disponible"] is False and body["motivo"] == "anterior"
    assert body["avisos"][0] == estructura_routes.ANTERIOR
    assert body["resumen"] == [] and body["verificaciones"] == [] and body["reglas"] is None


def test_override_needs_a_note(data_dir):
    pid, processed = _obra(data_dir)
    client = _client()
    r = _decidir(client, pid, marca="K-5", campo="seccion_cm", valor=[25, 40], nota="")
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["error_type"] == "nota_requerida"
    assert "20x30" in detail["message"] and "20x40" in detail["message"]
    # a note of blanks is no note
    r = _decidir(client, pid, marca="K-5", campo="seccion_cm", valor=[25, 40], nota="   ")
    assert r.status_code == 422 and r.json()["detail"]["error_type"] == "nota_requerida"
    assert not (processed / DECISIONES_FILENAME).exists()
    assert read_labels(processed) == []


# ---------------------------------------------------------------------------- lo que se lee


def test_the_payload_is_what_the_model_holds(data_dir):
    pid, processed = _obra(data_dir)
    body = _client().get(f"/projects/{pid}/estructura").json()
    derivada = read_json(processed / ESTRUCTURA_DERIVADA_FILENAME)
    assert body["verificaciones"] == derivada["verificaciones"]
    assert body["resumen"] == derivada["resumen"]
    assert body["reglas"] == derivada["reglas"]
    assert body["escrituras"] == derivada["escrituras"]
    assert body["avisos"] == derivada["avisos"]
    assert {x["familia"]: x["colocaciones"] for x in body["familias"]} == {
        "castillo": 2, "dala": 2, "trabe": 2,
    }  # fmt: skip
    assert [c["campo"] for c in body["campos_decidibles"]] == [
        "seccion_cm", "longitud_m", "longitudinales", "estribos", "parrillas",
    ]  # fmt: skip
    # every finding is on one card (R240) and its id is there to answer it
    assert sum(r["bloquea"] + r["duda"] + r["aviso"] for r in body["resumen"]) == len(
        body["verificaciones"]
    )
    assert all(v["id"] for v in body["verificaciones"])


def test_the_elements_of_a_family_with_their_definitions(data_dir):
    pid, _ = _obra(data_dir)
    client = _client()
    body = client.get(f"/projects/{pid}/estructura/elementos", params={"familia": "castillo"})
    assert body.status_code == 200
    body = body.json()
    assert {x["detection_id"] for x in body["elementos"]} == {"d1", "d2"}
    assert set(body["definiciones"]) == {"K-5"}
    k5 = body["definiciones"]["K-5"]
    assert k5["seccion_cm"]["fuente"] == "cuadro" and k5["seccion_cm"]["en_conflicto"] is True
    trabes = client.get(f"/projects/{pid}/estructura/elementos?familia=trabe").json()
    assert {x["colocacion"]["longitud_m"]["valor"] for x in trabes["elementos"]} == {4.0, 5.0}
    # by mark, written another way
    por_marca = client.get(f"/projects/{pid}/estructura/elementos?marca=k5").json()
    assert {x["marca"] for x in por_marca["elementos"]} == {"K-5"}
    # all of them
    todos = client.get(f"/projects/{pid}/estructura/elementos").json()
    assert len(todos["elementos"]) == 6 and set(todos["definiciones"]) == {"K-5", "T-1", "CI"}
    r = client.get(f"/projects/{pid}/estructura/elementos?familia=ventana")
    assert r.status_code == 422 and r.json()["detail"]["error_type"] == "familia_desconocida"


def test_unknown_project_is_404(data_dir):
    client = _client()
    assert client.get("/projects/nadie/estructura").status_code == 404
    assert client.get("/projects/nadie/estructura/elementos").status_code == 404
    r = _decidir(client, "nadie", marca="K-5", campo="seccion_cm", valor=[20, 40], nota="n")
    assert r.status_code == 404
    assert _quitar(client, "nadie", marca="K-5", campo="seccion_cm").status_code == 404


# ------------------------------------------------------------------- las corridas que no lo tienen


def test_a_run_without_estructura_answers_every_endpoint_with_its_aviso(data_dir):
    pid, processed = _obra(data_dir, con_estructura=False, recalcular=False)
    client = _client()
    elementos = client.get(f"/projects/{pid}/estructura/elementos?familia=castillo")
    assert elementos.status_code == 200
    assert elementos.json()["disponible"] is False and elementos.json()["elementos"] == []
    # a decision cannot be checked against a model that does not exist: said, nothing saved
    r = _decidir(client, pid, marca="K-5", campo="seccion_cm", valor=[20, 40], nota="n")
    assert r.status_code == 409 and r.json()["detail"]["message"] == estructura_routes.ANTERIOR
    assert not (processed / DECISIONES_FILENAME).exists()


def test_a_project_not_processed_yet(data_dir):
    _registrar(data_dir, "vacia")
    body = _client().get("/projects/vacia/estructura").json()
    assert body["disponible"] is False and body["motivo"] == "sin_procesar"
    assert body["avisos"] == [estructura_routes.SIN_PROCESAR]


def test_a_partial_estructura_still_reads(data_dir):
    # an estructura.json written before its optional fields (Task 12) is read as it is
    pid, processed = _obra(data_dir, recalcular=False)
    crudo = read_json(processed / ESTRUCTURA_FILENAME)
    for campo in ("resumen", "decisiones", "escrituras", "marcos", "patrones", "base"):
        crudo.pop(campo, None)
    write_json(processed / ESTRUCTURA_FILENAME, crudo)
    body = _client().get(f"/projects/{pid}/estructura").json()
    assert body["disponible"] is True and body["verificaciones"] and body["resumen"] == []


def test_a_corrupt_estructura_is_said_and_a_recompute_rebuilds_it(data_dir):
    pid, processed = _obra(data_dir, recalcular=False)
    (processed / ESTRUCTURA_FILENAME).write_text('{"version": 1, "reglas": "roto"}')
    client = _client()
    r = client.get(f"/projects/{pid}/estructura")
    assert r.status_code == 200
    body = r.json()
    assert body["disponible"] is False and body["motivo"] == "ilegible"
    assert "estructura.json no se pudo leer" in body["avisos"][0]
    torn = processed / ESTRUCTURA_FILENAME
    torn.write_text('{"version": 1, "reg')  # not even JSON
    assert client.get(f"/projects/{pid}/estructura").json()["motivo"] == "ilegible"
    # the recompute rebuilds it from the run's artifacts: then it reads
    recompute_and_persist(
        processed, processed, processed.parent / "reports", pid, CostingOverrides(),
        catalog_store=get_catalog_store(data_dir),
    )  # fmt: skip
    body = client.get(f"/projects/{pid}/estructura").json()
    assert body["disponible"] is True and body["verificaciones"]


def test_an_unreadable_decisions_file_is_said_not_a_500(data_dir):
    pid, processed = _obra(data_dir)
    (processed / DECISIONES_FILENAME).write_text("[{")
    r = _client().get(f"/projects/{pid}/estructura")
    assert r.status_code == 200
    assert any(DECISIONES_FILENAME in a and "no se pudo leer" in a for a in r.json()["avisos"])


def test_a_stale_scenario_is_never_served_as_current(data_dir):
    # a decision saved behind the API's back (and not recomputed): the payload says so
    pid, processed = _obra(data_dir)
    guardar_decision(
        processed,
        Decision(marca="K-5", campo="seccion_cm", valor=[20, 40], nota="n",
                 fecha=datetime(2026, 10, 18, tzinfo=UTC)),
    )  # fmt: skip
    body = _client().get(f"/projects/{pid}/estructura").json()
    assert body["disponible"] is True and body["al_dia"] is False
    assert body["decisiones"] == [] and len(body["decisiones_guardadas"]) == 1
    assert any("las decisiones guardadas cambiaron" in a for a in body["avisos"])


# ------------------------------------------------------------------------------- los rechazos


@pytest.mark.parametrize(
    ("body", "error_type", "en_el_mensaje"),
    [
        # R237: the concrete measures a castillo by its storey
        ({"marca": "K-5", "campo": "longitud_m", "valor": 3.2, "nota": "n"}, "decision_rechazada",
         "la altura de un castillo se decide por entrepiso (pendiente)"),
        # R237: one length for beams whose measured spans differ
        ({"marca": "T-1", "campo": "longitud_m", "valor": 4.5, "nota": "n"}, "decision_rechazada",
         "sus colocaciones miden claros distintos (4 m, 5 m)"),
        # R239: a variant the mark does not have
        ({"marca": "CI", "campo": "seccion_cm", "valor": [30, 20], "nota": "n",
          "para_muro_cm": 30}, "decision_rechazada",
         "CI no tiene una variante para muros de 30 cm"),
        ({"marca": "K-5", "campo": "seccion_cm", "valor": [20, 40], "nota": "n",
          "para_muro_cm": 15}, "decision_rechazada", "la marca no tiene variantes por muro"),
        # values that do not read
        ({"marca": "K-5", "campo": "seccion_cm", "valor": "abc", "nota": "n"},
         "decision_rechazada", "la sección no es b×h en cm"),
        ({"marca": "K-5", "campo": "seccion_cm", "valor": [20, -40], "nota": "n"},
         "decision_rechazada", "la sección no es b×h en cm"),
        ({"marca": "K-5", "campo": "seccion_cm", "valor": None, "nota": "n"},
         "decision_rechazada", "la sección no es b×h en cm"),
        ({"marca": "K-5", "campo": "longitudinales", "valor": "4#5 y algo", "nota": "n"},
         "decision_rechazada", "no se lee entero"),
        ({"marca": "K-5", "campo": "parrillas", "valor": "#4@20", "nota": "n"},
         "decision_rechazada", "la familia castillo no lleva parrillas"),
        ({"marca": "K-5", "campo": "seccion_cm", "valor": [20, 4000], "nota": "n"},
         "decision_rechazada", "fuera de lo que mide un elemento"),
        # a mark the reading does not have
        ({"marca": "K-99", "campo": "seccion_cm", "valor": [20, 40], "nota": "n"},
         "decision_rechazada", "la marca no está en esta lectura"),
        # what is not a decidable field, or not a decision at all
        ({"marca": "K-5", "campo": "color", "valor": "rojo", "nota": "n"}, "campo_desconocido",
         "no es un campo que se decida"),
        ({"marca": "", "campo": "seccion_cm", "valor": [20, 40], "nota": "n"},
         "decision_invalida", "marca"),
        ({"campo": "seccion_cm", "valor": [20, 40]}, "decision_invalida", "marca"),
        ({"marca": "K-5", "campo": "seccion_cm", "valor": [20, 40], "nota": "x" * 301},
         "decision_invalida", "nota"),
        ({"marca": "K-5", "campo": "seccion_cm", "valor": [20, 40], "nota": "n",
          "para_muro_cm": "mucho"}, "muro_invalido", "espesor de su muro"),
        # R244 (Task 13 review): one bound for every value, text or pieces
        ({"marca": "K-5", "campo": "longitudinales", "valor": [{"cantidad": -4, "numero": "4"}],
          "nota": "n"}, "decision_rechazada", "-4 varillas no es un armado"),
        ({"marca": "K-5", "campo": "longitudinales", "valor": [{"cantidad": 0, "numero": "4"}],
          "nota": "n"}, "decision_rechazada", "0 varillas no es un armado"),
        ({"marca": "K-5", "campo": "longitudinales", "valor": [{"cantidad": 4000, "numero": "4"}],
          "nota": "n"}, "decision_rechazada", "4000 varillas no es un armado"),
        ({"marca": "K-5", "campo": "estribos", "valor": "25E#3@15", "nota": "n"},
         "decision_rechazada", "25 piezas por juego de estribo no es un armado"),
        ({"marca": "K-5", "campo": "longitudinales", "valor": [{"cantidad": 4, "numero": "99"}],
          "nota": "n"}, "decision_rechazada", "no hay varilla del #99"),
        ({"marca": "K-5", "campo": "longitudinales", "valor": [{"cantidad": 4, "numero": "abc"}],
          "nota": "n"}, "decision_rechazada", "no hay varilla del #abc"),
        ({"marca": "K-5", "campo": "estribos", "valor": [{"tipo": "estribo", "cantidad": 1,
          "numero": "3", "zonas": [{"tramo": "todo", "separacion_m": 0}]}], "nota": "n"},
         "decision_rechazada", "la separación de los estribos (0 m)"),
        ({"marca": "K-5", "campo": "estribos", "valor": [{"tipo": "estribo", "cantidad": 1,
          "numero": "3", "zonas": [{"tramo": "todo", "separacion_m": -0.2}]}], "nota": "n"},
         "decision_rechazada", "la separación de los estribos (-0.2 m)"),
        ({"marca": "K-5", "campo": "estribos", "valor": [{"tipo": "grapa", "cantidad": 1,
          "numero": "3", "zonas": [{"tramo": "todo", "separacion_m": 0.001}]}], "nota": "n"},
         "decision_rechazada", "la separación de las grapas (0.001 m)"),
        ({"marca": "K-5", "campo": "estribos", "valor": [{"tipo": "estribo", "cantidad": 0,
          "numero": "3", "zonas": []}], "nota": "n"}, "decision_rechazada",
         "0 piezas por juego de estribo"),
        ({"marca": "K-5", "campo": "estribos", "valor": [], "nota": "n"}, "decision_rechazada",
         "una decisión sin estribos no se toma"),
        ({"marca": "K-5", "campo": "seccion_cm", "valor": [1e-9, 1e-9], "nota": "n"},
         "decision_rechazada", "¿en metros? la sección va en cm"),
        ({"marca": "K-5", "campo": "seccion_cm", "valor": [0.2, 0.3], "nota": "n"},
         "decision_rechazada", "¿en metros? la sección va en cm"),
        ({"marca": "K-5", "campo": "seccion_cm", "valor": {"area_cm2": 4}, "nota": "n"},
         "decision_rechazada", "¿en metros? la sección va en cm"),
        ({"marca": "T-1", "campo": "longitud_m", "valor": 0.05, "nota": "n"},
         "decision_rechazada", "¿en centímetros? la longitud va en metros"),
        # R247: a decision no placement takes moves nothing
        ({"marca": "CI", "campo": "seccion_cm", "valor": [20, 25], "nota": "n",
          "para_muro_cm": 20}, "decision_rechazada",
         "ninguna colocación tomó la variante para muros de 20 cm; no se guarda"),
        # R247: a value is a section, a length or an armado, never a document
        ({"marca": "K-5", "campo": "longitudinales", "valor": "4#4 " * 600, "nota": "n"},
         "valor_demasiado_largo", "hasta 2048 caracteres"),
    ],
)  # fmt: skip
def test_a_refusal_is_a_422_with_the_models_aviso_and_saves_nothing(
    data_dir, body, error_type, en_el_mensaje
):
    pid, processed = _obra(data_dir)
    antes = _costo(processed)
    r = _client().post(f"/projects/{pid}/estructura/decisiones", json=body)
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["error_type"] == error_type and en_el_mensaje in detail["message"]
    assert not (processed / DECISIONES_FILENAME).exists() and read_labels(processed) == []
    assert _costo(processed) == antes


def test_the_refusal_is_the_aviso_the_model_gives_when_it_applies(data_dir):
    # the 422 is the model's own aviso: forced into the file, the model says the same words
    pid, processed = _obra(data_dir)
    client = _client()
    r = _decidir(client, pid, marca="T-1", campo="longitud_m", valor=4.5, nota="n")
    mensaje = r.json()["detail"]["message"]
    guardar_decision(
        processed,
        Decision(marca="T-1", campo="longitud_m", valor=4.5, nota="n",
                 fecha=datetime(2026, 10, 18, tzinfo=UTC)),
    )  # fmt: skip
    recompute_and_persist(
        processed, processed, processed.parent / "reports", pid, CostingOverrides(),
        catalog_store=get_catalog_store(data_dir),
    )  # fmt: skip
    assert mensaje in client.get(f"/projects/{pid}/estructura").json()["avisos"]


def test_non_finite_numbers_never_reach_the_model_nor_a_500(data_dir):
    pid, processed = _obra(data_dir)
    client = _client()
    for valor in ("[NaN, 40]", "[20, Infinity]", '{"area_cm2": NaN}'):
        r = client.post(
            f"/projects/{pid}/estructura/decisiones",
            content=f'{{"marca": "K-5", "campo": "seccion_cm", "valor": {valor}, "nota": "n"}}',
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 422, (valor, r.text)
        assert r.json()["detail"]["error_type"] == "decision_rechazada"
    r = client.post(
        f"/projects/{pid}/estructura/decisiones",
        content='{"marca": "CI", "campo": "seccion_cm", "valor": [20, 20], "nota": "n", '
        '"para_muro_cm": NaN}',
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 422 and r.json()["detail"]["error_type"] == "muro_invalido"
    assert not (processed / DECISIONES_FILENAME).exists()


# ---------------------------------------------------------------------- decidir sin nota y quitar


def test_a_value_the_drawing_does_not_give_needs_no_note(data_dir):
    # the demo's C-1 section is Klave's supuesto (no note needed); B-1's span is measured
    root = data_dir / "projects" / "demo"
    write_demo_project(root, declare_units=True)
    run_full_pipeline(root, get_settings())
    pid = read_json(root / get_settings().processed_dir_name / "project_manifest.json")[
        "project_id"
    ]
    _registrar_raiz(data_dir, pid, root)
    client = _client()
    r = _decidir(client, pid, marca="C-1", campo="seccion_cm", valor=[40, 40], nota="")
    assert r.status_code == 200, r.text
    c1 = [
        x for x in client.get(f"/projects/{pid}/estructura/elementos?marca=C-1").json()["elementos"]
    ]
    assert c1 and all(x["seccion_cm"]["fuente"] == "humano" for x in c1)
    # B-1's span is measured on the drawing: overriding it needs a note
    r = _decidir(client, pid, marca="B-1", campo="longitud_m", valor=3.5, nota="")
    assert r.status_code == 422 and r.json()["detail"]["error_type"] == "nota_requerida"
    assert "3 m (medido)" in r.json()["detail"]["message"]
    r = _decidir(client, pid, marca="B-1", campo="longitud_m", valor=3.5, nota="cota de obra")
    assert r.status_code == 200, r.text


def _registrar_raiz(data_dir, pid, root):
    registro = data_dir / "projects_registry.json"
    actual = json.loads(registro.read_text()) if registro.exists() else {}
    registro.write_text(json.dumps({**actual, pid: str(root)}))


def test_undo_leaves_the_payload_and_the_budget_as_before(data_dir):
    # R235 through the API: decide, then remove it — the model and the BOQ are as they were
    pid, processed = _obra(data_dir)
    client = _client()
    antes = client.get(f"/projects/{pid}/estructura").json()
    costo = _costo(processed)
    r = _decidir(client, pid, marca="K-5", campo="seccion_cm", valor=[30, 50], nota="obra")
    assert r.status_code == 200
    assert _costo(processed) != costo  # the decision moved the concrete
    r = _quitar(client, pid, marca="K-5", campo="seccion_cm")
    assert r.status_code == 200, r.text
    despues = r.json()
    assert despues == antes
    assert _costo(processed) == costo
    assert client.get(f"/projects/{pid}/estructura").json() == antes
    acciones = [x["action"] for x in read_labels(processed) if x.get("kind") == "estructura"]
    assert acciones == ["decide_value", "undo_decision"]
    undo = read_labels(processed)[-1]
    assert undo["valor"] is None and undo["antes"]["valor"] == [30, 50]
    # nothing left to remove
    r = _quitar(client, pid, marca="K-5", campo="seccion_cm")
    assert r.status_code == 404 and r.json()["detail"]["error_type"] == "decision_no_encontrada"


def test_undo_names_the_variant_and_the_mark_as_written(data_dir):
    pid, processed = _obra(data_dir)
    client = _client()
    r = _decidir(client, pid, marca="CI", campo="seccion_cm", valor=[15, 25], nota="detalle",
                 para_muro_cm=15)  # fmt: skip
    assert r.status_code == 200, r.text
    assert _quitar(client, pid, marca="CI", campo="seccion_cm").status_code == 404
    r = _quitar(client, pid, marca="ci", campo="seccion_cm", para_muro_cm="15")
    assert r.status_code == 200 and r.json()["decisiones"] == []


def test_a_new_decision_replaces_the_last_one_for_that_mark_and_field(data_dir):
    pid, processed = _obra(data_dir)
    client = _client()
    assert _decidir(client, pid, marca="K-5", campo="seccion_cm", valor=[20, 30],
                    nota="n").status_code == 200  # fmt: skip
    r = _decidir(client, pid, marca="K5", campo="seccion_cm", valor=[20, 40], nota="otra")
    assert r.status_code == 200
    (d,) = r.json()["decisiones"]
    assert d["valor"] == [20, 40] and d["nota"] == "otra"
    assert len(read_json(processed / DECISIONES_FILENAME)) == 1
    label = [x for x in read_labels(processed) if x.get("action") == "decide_value"][-1]
    # what it replaced is the earlier decision
    assert label["antes"]["fuente"] == "humano" and label["antes"]["valor"] == [20, 30]


def test_a_failed_recompute_leaves_nothing_half_done(data_dir, monkeypatch):
    pid, processed = _obra(data_dir)
    client = TestClient(_app(), raise_server_exceptions=False)
    derivada = (processed / ESTRUCTURA_DERIVADA_FILENAME).read_bytes()
    costo = (processed / "cost_report_override.json").read_bytes()
    real = estructura_routes._recompute_after_review

    reportes = processed.parent / "reports"
    otros = {
        x: x.read_bytes()
        for x in (
            reportes / "presupuesto.csv",
            reportes / "resumen_costos.md",
            processed / "costing_overrides.json",
        )
    }
    assert all(otros.values())

    def roto(*a, **k):
        (processed / "cost_report_override.json").write_text("{}")  # half written
        for x in otros:
            x.write_text("a medias")
        raise RuntimeError("catálogo caído")

    monkeypatch.setattr(estructura_routes, "_recompute_after_review", roto)
    r = _decidir(client, pid, marca="K-5", campo="seccion_cm", valor=[20, 40], nota="n")
    assert r.status_code == 500
    assert not (processed / DECISIONES_FILENAME).exists()
    assert (processed / ESTRUCTURA_DERIVADA_FILENAME).read_bytes() == derivada
    assert (processed / "cost_report_override.json").read_bytes() == costo
    assert {x: x.read_bytes() for x in otros} == otros
    assert read_labels(processed) == []
    # with a decision and its label already there, a failed one leaves exactly those
    monkeypatch.setattr(estructura_routes, "_recompute_after_review", real)
    assert _decidir(client, pid, marca="K-5", campo="seccion_cm", valor=[20, 40],
                    nota="n").status_code == 200  # fmt: skip
    decisiones = (processed / DECISIONES_FILENAME).read_bytes()
    derivada = (processed / ESTRUCTURA_DERIVADA_FILENAME).read_bytes()
    costo = (processed / "cost_report_override.json").read_bytes()
    etiquetas = read_labels(processed)
    monkeypatch.setattr(estructura_routes, "_recompute_after_review", roto)
    r = _decidir(client, pid, marca="T-1", campo="estribos", valor="E#3@15", nota="d")
    assert r.status_code == 500
    r = _quitar(client, pid, marca="K-5", campo="seccion_cm")
    assert r.status_code == 500
    assert (processed / DECISIONES_FILENAME).read_bytes() == decisiones
    assert (processed / ESTRUCTURA_DERIVADA_FILENAME).read_bytes() == derivada
    assert (processed / "cost_report_override.json").read_bytes() == costo
    assert read_labels(processed) == etiquetas


def test_the_rollback_saves_the_taller_indices_of_the_restored_budget(data_dir, monkeypatch):
    # the taller's history keeps one row per project that the store cannot give back: the
    # rollback saves again the indices of the budget it restored (R247)
    pid, processed = _obra(data_dir)
    restaurados = []
    monkeypatch.setattr(
        estructura_routes, "apply_taller_history",
        lambda report, store, project_id: restaurados.append((report.boq.direct_cost_total,
                                                              project_id)),
    )  # fmt: skip
    antes = read_json(processed / "cost_report_override.json")["boq"]["direct_cost_total"]

    def roto(*a, **k):
        raise RuntimeError("catálogo caído")

    monkeypatch.setattr(estructura_routes, "_recompute_after_review", roto)
    client = TestClient(_app(), raise_server_exceptions=False)
    r = _decidir(client, pid, marca="K-5", campo="seccion_cm", valor=[30, 50], nota="n")
    assert r.status_code == 500 and restaurados == [(antes, pid)]


def test_an_unreadable_decisions_file_is_a_409_and_is_never_written_over(data_dir):
    # R245: a torn (or non-list) decisions file would lose every decision it holds
    pid, processed = _obra(data_dir)
    client = _client()
    # with no decision in the scenario either, an unreadable file is still not «al día»
    (processed / DECISIONES_FILENAME).write_text("[{")
    assert client.get(f"/projects/{pid}/estructura").json()["al_dia"] is False
    (processed / DECISIONES_FILENAME).unlink()
    assert _decidir(client, pid, marca="T-1", campo="estribos", valor="E#3@15",
                    nota="d").status_code == 200  # fmt: skip
    for roto in ("[{", '{"marca": "T-1"}'):
        (processed / DECISIONES_FILENAME).write_text(roto)
        etiquetas = read_labels(processed)
        body = client.get(f"/projects/{pid}/estructura").json()
        assert body["al_dia"] is False  # the scenario has T-1; the file says nothing readable
        r = _decidir(client, pid, marca="K-5", campo="seccion_cm", valor=[20, 40], nota="PA")
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["error_type"] == "decisiones_ilegibles"
        assert "El archivo de decisiones no se puede leer" in r.json()["detail"]["message"]
        r = _quitar(client, pid, marca="T-1", campo="estribos")
        assert r.status_code == 409 and r.json()["detail"]["error_type"] == "decisiones_ilegibles"
        assert "El archivo de decisiones no se puede leer" in r.json()["detail"]["message"]
        assert (processed / DECISIONES_FILENAME).read_text() == roto
        assert read_labels(processed) == etiquetas


def test_a_recompute_that_does_not_apply_the_decision_is_a_409_with_nothing_saved(data_dir):
    # R246: `_recompute_after_review` says nothing when the run lacks what the costing reads;
    # the route checks the reading it leaves and never answers «saved» for «not applied»
    pid, processed = _obra(data_dir)
    client = _client()
    derivada = (processed / ESTRUCTURA_DERIVADA_FILENAME).read_bytes()
    (processed / "detections.json").unlink()
    r = _decidir(client, pid, marca="K-5", campo="seccion_cm", valor=[20, 40], nota="PA")
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["error_type"] == "recalculo_sin_aplicar"
    assert not (processed / DECISIONES_FILENAME).exists() and read_labels(processed) == []
    assert (processed / ESTRUCTURA_DERIVADA_FILENAME).read_bytes() == derivada
    assert client.get(f"/projects/{pid}/estructura").json()["al_dia"] is True


def test_while_a_recompute_runs_the_decisions_do_not_flicker_away(data_dir, monkeypatch):
    # R247: during the recompute the last scenario is served, marked behind, with its decisions
    pid, processed = _obra(data_dir)
    client = _client()
    assert _decidir(client, pid, marca="K-5", campo="seccion_cm", valor=[20, 40],
                    nota="PA").status_code == 200  # fmt: skip
    real = estructura_routes._recompute_after_review
    vistos = []

    def mirando(*a, **k):
        vistos.append(client.get(f"/projects/{pid}/estructura").json())
        return real(*a, **k)

    monkeypatch.setattr(estructura_routes, "_recompute_after_review", mirando)
    r = _decidir(client, pid, marca="T-1", campo="estribos", valor="E#3@15", nota="d")
    assert r.status_code == 200
    (durante,) = vistos
    assert durante["al_dia"] is False
    assert [d["marca"] for d in durante["decisiones"]] == ["K-5"]
    assert any("las decisiones guardadas cambiaron" in a for a in durante["avisos"])
    assert r.json()["al_dia"] is True
    assert {d["marca"] for d in r.json()["decisiones"]} == {"K-5", "T-1"}


def test_deciding_the_drawings_only_value_needs_no_note(data_dir):
    # R247: T-1's section is 25x50 in its only cuadro; deciding exactly that is no override
    pid, _ = _obra(data_dir)
    client = _client()
    r = _decidir(client, pid, marca="T-1", campo="seccion_cm", valor=[25, 50], nota="")
    assert r.status_code == 200, r.text
    r = _decidir(client, pid, marca="T-1", campo="seccion_cm", valor=[25, 55], nota="")
    assert r.status_code == 422 and r.json()["detail"]["error_type"] == "nota_requerida"
    # K-5's cuadros disagree: picking one of them still needs a note
    r = _decidir(client, pid, marca="K-5", campo="seccion_cm", valor=[20, 30], nota="")
    assert r.status_code == 422 and r.json()["detail"]["error_type"] == "nota_requerida"


def test_the_undo_label_names_the_mark_as_the_decide_label_does(data_dir):
    pid, processed = _obra(data_dir)
    client = _client()
    assert _decidir(client, pid, marca="k5", campo="seccion_cm", valor=[20, 40],
                    nota="PA").status_code == 200  # fmt: skip
    assert _quitar(client, pid, marca="K 5", campo="seccion_cm").status_code == 200
    etiquetas = [x for x in read_labels(processed) if x.get("kind") == "estructura"]
    assert [(x["action"], x["marca"]) for x in etiquetas] == [
        ("decide_value", "K-5"), ("undo_decision", "K-5"),
    ]  # fmt: skip


# ------------------------------------------------------------------- la corrida activa y otra


def _publicar(processed, run_id, nombres):
    """Mueve los artefactos de la corrida a ``runs/<run_id>`` y la publica (como ``jobs.py``)."""
    run = processed / "runs" / run_id
    run.mkdir(parents=True)
    for nombre in nombres:
        if (processed / nombre).exists():
            (processed / nombre).replace(run / nombre)
    write_json(
        processed / "active_run.json",
        {"run_id": run_id, "artifact_dir": f"runs/{run_id}", "reports_dir": f"runs/{run_id}/r"},
    )
    return run


_ARTEFACTOS = (
    "normalized_entities.json", "schedules.json", "detections.json", "views.json", "frames.json",
    "drawing_units.json", ESTRUCTURA_FILENAME,
)  # fmt: skip


def test_the_active_run_is_read_and_a_scenario_of_another_run_is_never_served(data_dir):
    pid, processed = _obra(data_dir, recalcular=False)
    run = _publicar(processed, "r1", _ARTEFACTOS)
    client = _client()
    body = client.get(f"/projects/{pid}/estructura").json()
    assert body["disponible"] is True and body["verificaciones"]
    r = _decidir(client, pid, marca="K-5", campo="seccion_cm", valor=[20, 40], nota="PA")
    assert r.status_code == 200, r.text
    # the decision lives in the control dir; the run stays as it was published
    assert (processed / DECISIONES_FILENAME).exists()
    assert (processed / ESTRUCTURA_DERIVADA_FILENAME).exists()
    assert read_json(run / ESTRUCTURA_FILENAME)["decisiones"] == []
    assert r.json()["al_dia"] is True and r.json()["decisiones"][0]["marca"] == "K-5"
    # a new run is published (its model built without the decision): the old scenario is not
    # its own, so the run's model is served and says it is behind the saved decisions
    textos, dets, inv, seg = _lectura()
    nueva = construir_estructura(textos, _MARCOS, inv, dets[:4], seg, 1.0, 2.9)
    r2 = processed / "runs" / "r2"
    r2.mkdir()
    for nombre in _ARTEFACTOS:
        (r2 / nombre).write_bytes((run / nombre).read_bytes())
    escribir_estructura(r2, nueva)
    write_json(
        processed / "active_run.json",
        {"run_id": "r2", "artifact_dir": "runs/r2", "reports_dir": "runs/r2/r"},
    )
    body = client.get(f"/projects/{pid}/estructura").json()
    assert body["al_dia"] is False and body["decisiones"] == []
    assert body["verificaciones"] == read_json(r2 / ESTRUCTURA_FILENAME)["verificaciones"]
    assert {x["familia"]: x["colocaciones"] for x in body["familias"]}["trabe"] == 2
    assert "dala" not in {x["familia"] for x in body["familias"]}
    # the next decision recomputes over the new run
    r = _decidir(client, pid, marca="T-1", campo="estribos", valor="E#3@15", nota="detalle")
    assert r.status_code == 200 and r.json()["al_dia"] is True
    assert {d["marca"] for d in r.json()["decisiones"]} == {"K-5", "T-1"}


# ------------------------------------------------------------------------------- dos a la vez


def _lento(monkeypatch):
    """El recálculo de siempre, con una pausa y la cuenta de cuántos van a la vez."""
    real = estructura_routes._recompute_after_review
    dentro: list[int] = []
    maximo: list[int] = []
    candado = threading.Lock()

    def lento(*a, **k):
        with candado:
            dentro.append(1)
            maximo.append(len(dentro))
        time.sleep(0.3)
        try:
            return real(*a, **k)
        finally:
            with candado:
                dentro.pop()

    monkeypatch.setattr(estructura_routes, "_recompute_after_review", lento)
    return maximo


def _a_la_vez(*llamadas):
    resultados = {}

    def correr(nombre, llamada):
        resultados[nombre] = llamada()

    hilos = [threading.Thread(target=correr, args=(n, f)) for n, f in llamadas]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    return {n: r.status_code for n, r in resultados.items()}


def test_two_decisions_at_once_are_both_saved_and_recomputed_one_after_the_other(
    data_dir, monkeypatch
):
    pid, processed = _obra(data_dir)
    maximo = _lento(monkeypatch)
    client = _client()
    estados = _a_la_vez(
        ("k5", lambda: _decidir(client, pid, marca="K-5", campo="seccion_cm", valor=[20, 40],
                                nota="PA")),
        ("t1", lambda: _decidir(client, pid, marca="T-1", campo="estribos", valor="E#3@15",
                                nota="detalle")),
    )  # fmt: skip
    assert estados == {"k5": 200, "t1": 200}
    assert max(maximo) == 1  # the recomputes never overlapped
    guardadas = {(d["marca"], d["campo"]) for d in read_json(processed / DECISIONES_FILENAME)}
    assert guardadas == {("K-5", "seccion_cm"), ("T-1", "estribos")}
    final = _client().get(f"/projects/{pid}/estructura").json()
    assert final["al_dia"] is True
    assert {(d["marca"], d["campo"]) for d in final["decisiones"]} == guardadas
    assert len([x for x in read_labels(processed) if x.get("action") == "decide_value"]) == 2


def test_an_undo_and_a_decision_at_once_both_hold(data_dir, monkeypatch):
    pid, processed = _obra(data_dir)
    client = _client()
    assert _decidir(client, pid, marca="K-5", campo="seccion_cm", valor=[20, 40],
                    nota="PA").status_code == 200  # fmt: skip
    maximo = _lento(monkeypatch)
    estados = _a_la_vez(
        ("quitar", lambda: _quitar(client, pid, marca="K-5", campo="seccion_cm")),
        ("t1", lambda: _decidir(client, pid, marca="T-1", campo="estribos", valor="E#3@15",
                                nota="detalle")),
    )  # fmt: skip
    assert estados == {"quitar": 200, "t1": 200}
    assert max(maximo) == 1
    assert [(d["marca"], d["campo"]) for d in read_json(processed / DECISIONES_FILENAME)] == [
        ("T-1", "estribos")
    ]
    final = _client().get(f"/projects/{pid}/estructura").json()
    assert final["al_dia"] is True and [d["marca"] for d in final["decisiones"]] == ["T-1"]


# ------------------------------------------------------------------------------------ el acceso


class _Usuarios:
    """La base de usuarios del middleware, en memoria: Ana es editora del proyecto, Beto lo ve,
    Caro es de otro taller."""

    last_known_has_users = True

    def __init__(self, pid):
        self.pid = pid
        self.usuarios = {
            "ana": {"user_id": "ana", "name": "Ana", "status": "active", "role": "member",
                    "workspace_id": "ws-a"},
            "beto": {"user_id": "beto", "name": "Beto", "status": "active", "role": "member",
                     "workspace_id": "ws-a"},
            "caro": {"user_id": "caro", "name": "Caro", "status": "active", "role": "admin",
                     "workspace_id": "ws-b"},
        }  # fmt: skip
        self.roles = {"ana": "editor", "beto": "viewer"}

    def has_users(self):
        return True

    def get_session_user(self, token):
        return self.usuarios.get(token or "")

    def project_workspace_id(self, project_id):
        return "ws-a"

    def project_role(self, project_id, user_id):
        return self.roles.get(user_id) if project_id == self.pid else None


def test_reading_needs_viewer_and_deciding_needs_editor(data_dir, monkeypatch):
    from apps.api.auth import access, middleware

    pid, processed = _obra(data_dir)
    usuarios = _Usuarios(pid)
    monkeypatch.setattr(middleware, "get_user_store", lambda _url: usuarios)
    monkeypatch.setattr(access, "get_user_store", lambda _url: usuarios)
    app = _app()
    app.add_middleware(middleware.AccessControlMiddleware)
    client = TestClient(app)

    def como(quien):
        client.cookies.clear()
        if quien:
            client.cookies.set(middleware.SESSION_COOKIE, quien)
        return client

    assert como(None).get(f"/projects/{pid}/estructura").status_code == 401
    assert como("beto").get(f"/projects/{pid}/estructura").status_code == 200
    assert como("caro").get(f"/projects/{pid}/estructura").status_code == 403
    body = {"marca": "K-5", "campo": "seccion_cm", "valor": [20, 40], "nota": "PA"}
    r = como("beto").post(f"/projects/{pid}/estructura/decisiones", json=body)
    assert r.status_code == 403 and not (processed / DECISIONES_FILENAME).exists()
    r = como("caro").post(f"/projects/{pid}/estructura/decisiones", json=body)
    assert r.status_code == 403
    r = como("ana").post(
        f"/projects/{pid}/estructura/decisiones", json=body, headers={"X-Actor": "Otra persona"}
    )
    assert r.status_code == 200, r.text
    # the session signs the decision, never the header
    (d,) = read_json(processed / DECISIONES_FILENAME)
    assert d["actor"] == "Ana"
    r = como("beto").delete(
        f"/projects/{pid}/estructura/decisiones", params={"marca": "K-5", "campo": "seccion_cm"}
    )
    assert r.status_code == 403
    r = como("ana").delete(
        f"/projects/{pid}/estructura/decisiones", params={"marca": "K-5", "campo": "seccion_cm"}
    )
    assert r.status_code == 200


def test_the_route_asks_for_the_role_itself(data_dir, monkeypatch):
    # mounted without the middleware but with a signed-in viewer, the route still refuses
    from apps.api.auth import access

    pid, processed = _obra(data_dir)
    usuarios = _Usuarios(pid)
    monkeypatch.setattr(access, "get_user_store", lambda _url: usuarios)
    app = _app()

    @app.middleware("http")
    async def sesion(request, call_next):
        request.state.user = usuarios.usuarios[request.headers["x-quien"]]
        return await call_next(request)

    client = TestClient(app)
    body = {"marca": "K-5", "campo": "seccion_cm", "valor": [20, 40], "nota": "PA"}
    r = client.post(f"/projects/{pid}/estructura/decisiones", json=body,
                    headers={"x-quien": "beto"})  # fmt: skip
    assert r.status_code == 403 and not (processed / DECISIONES_FILENAME).exists()
    r = client.get(f"/projects/{pid}/estructura", headers={"x-quien": "caro"})
    assert r.status_code == 403
    r = client.get(f"/projects/{pid}/estructura/elementos", headers={"x-quien": "caro"})
    assert r.status_code == 403
    r = client.delete(f"/projects/{pid}/estructura/decisiones",
                      params={"marca": "K-5", "campo": "seccion_cm"},
                      headers={"x-quien": "beto"})  # fmt: skip
    assert r.status_code == 403
    r = client.post(f"/projects/{pid}/estructura/decisiones", json=body,
                    headers={"x-quien": "ana"})  # fmt: skip
    assert r.status_code == 200
