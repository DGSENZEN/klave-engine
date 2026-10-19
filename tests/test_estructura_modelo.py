"""Tarea 12: el modelo estructural en el pipeline y en el recálculo — ``estructura.json``, las
decisiones humanas que sobreviven a la reprocesada, la tarjeta por familia con lo que está en
juego, y lo que el modelo escribe en las detecciones que el presupuesto lee. Los casos son
sintéticos: el conflicto de K-5 (20x30 / 20x40) ya no es un hecho de Marina (spec §2, bb4c68c);
aquí es un ejemplo."""

import json
import typing
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from klave_engine.common.config import get_settings
from klave_engine.common.io import read_json, write_json
from klave_engine.costing.models import BillOfQuantities, BoqLine, CostingOverrides, QuantityKind
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.schedules import ElementSpec, ScheduleInventory
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.detection.views import SheetSegmentation, ViewKind, ViewRegion
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.estructura.dato import Dato
from klave_engine.estructura.elementos import Colocacion, Elemento
from klave_engine.estructura.modelo import (
    DECISIONES_FILENAME,
    ESTRUCTURA_DERIVADA_FILENAME,
    ESTRUCTURA_FILENAME,
    Decision,
    Estructura,
    ResumenFamilia,
    aplicar_decisiones,
    cargar_decisiones,
    construir_estructura,
    diferencias_con_el_concreto,
    escribir_en_detecciones,
    guardar_decision,
    leer_decisiones,
    leer_estructura,
    leer_estructura_vigente,
    resumir,
)
from klave_engine.evals.fixtures import write_demo_project
from klave_engine.graph.evidence import EvidencePacket
from klave_engine.pipeline import run_full_pipeline

_FECHA = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


def _now():
    return _FECHA


# ---------------------------------------------------------------------------------- ayudantes


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


def _spec(marca, seccion, hoja, eid, rebar="4#4", stirrups="E#3@15", **kw):
    return ElementSpec(
        mark=marca,
        family="castillo",
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


def _castillo(det_id, marca, x, y, eid, **props):
    d = make_detection(
        det_id, DetectionType.column_tag, marca, (x, y, x + 0.3, y + 0.1), 0.9, [eid], "t", [],
        props, "a.dxf",
    )  # fmt: skip
    d.mark, d.family = marca, "castillo"
    return d


def _planta(detecciones):
    vistas = [
        ViewRegion(
            view_id="f1",
            title="ES-100 · PLANTA",
            kind=ViewKind.plan,
            level_key="planta",
            anchor=(0, 0),
            bbox=(0, 0, 100, 100),
        )
    ]
    return SheetSegmentation(
        views=vistas, assignment={d.detection_id: "f1" for d in detecciones}, is_segmented=True
    )


_MARCOS = [
    SheetFrame(frame_id="f1", bbox=(0, 0, 100, 100), source_file="a.dxf", code="ES-100"),
    SheetFrame(frame_id="f2", bbox=(200, 0, 300, 100), source_file="a.dxf", code="ES-200"),
    SheetFrame(frame_id="f4", bbox=(400, 0, 500, 100), source_file="a.dxf", code="ES-400"),
]


def _estructura_k5_conflict(con_k9=False):
    """K-5 dicho 20x30 en el cuadro de ES-200 y 20x40 en el de ES-400; dos K-5 colocados en la
    planta de ES-100, sin niveles (altura supuesta 2.9 m). ``con_k9``: además un K-9 colocado que
    el plano no define (su verificación 1 es otro hallazgo, que una decisión de K-5 no toca)."""
    textos = [
        _texto("t200", "K-5", 210, 10),
        _texto("t400", "K-5", 410, 10),
        _texto("p1", "K-5", 10, 10),
        _texto("p2", "K-5", 30, 10),
    ]
    dets = [_castillo("d1", "K-5", 10, 10, "p1"), _castillo("d2", "K-5", 30, 10, "p2")]
    if con_k9:
        textos.append(_texto("p9", "K-9", 50, 10))
        dets.append(_castillo("d9", "K-9", 50, 10, "p9"))
    inv = ScheduleInventory(
        specs=[_spec("K-5", (20, 30), "ES-200", "t200"), _spec("K-5", (20, 40), "ES-400", "t400")]
    )
    return construir_estructura(textos, _MARCOS, inv, dets, _planta(dets), 1.0, 2.9)


def _linea(code, ids, unit="M3", price=0.0, unpriced=False):
    return BoqLine(
        concept_code=code, description=code, unit=unit, quantity=1.0, unit_price=price,
        amount=price, phase="Estructura", raw_quantity=1.0, raw_kind=QuantityKind.COUNT,
        source_detection_count=len(ids), source_detections=list(ids), confidence=0.9,
        unpriced=unpriced,
    )  # fmt: skip


def _report_with_est001_price(pu, acero=None):
    lineas = [_linea("EST-001", ["d1", "d2"], price=pu)]
    if acero is not None:
        lineas.append(_linea("ACE-001", ["d1", "d2"], unit="KG", price=acero))
    return SimpleNamespace(boq=BillOfQuantities(project_id="p", lines=lineas))


def _k5(e):
    return next(x for x in e.definiciones if x.marca == "K-5")


def _ocho_de(e, marca):
    return [v for v in e.verificaciones if v.numero == 8 and marca in v.marcas]


# ----------------------------------------------------------------- el plan (pruebas del brief)


def test_pipeline_writes_estructura_on_demo(tmp_path, data_dir):
    root = tmp_path / "demo"
    write_demo_project(root)
    run_full_pipeline(root, get_settings())
    e = leer_estructura(root / get_settings().processed_dir_name)
    assert e is not None and e.reglas.tabla_varillas.fuente == "supuesto"
    assert isinstance(e.resumen, list) and e.elementos
    # the steel of that run came from the model (R6), not from the specs path
    report = read_json(root / get_settings().processed_dir_name / "cost_report.json")
    assert any(
        w.startswith("Acero por leer — castillos y columnas: ") for w in report["boq"]["warnings"]
    )


def test_decision_applies_and_survives():
    e = _estructura_k5_conflict()
    assert _k5(e).seccion_cm.en_conflicto and _ocho_de(e, "K-5")  # the drawing contradicts itself
    d = Decision(
        marca="K-5", campo="seccion_cm", valor=[20, 40], nota="hoja de PA", actor="Diego",
        fecha=_now(),
    )  # fmt: skip
    out = aplicar_decisiones(e, [d])
    k5 = _k5(out).seccion_cm
    assert k5.fuente == "humano" and tuple(k5.valor) == (20, 40) and not k5.en_conflicto
    assert not _ocho_de(out, "K-5")
    # every placement takes it, whatever its sheet says (R141: per-sheet never displaces humano)
    assert {tuple(x.seccion_cm.valor) for x in out.elementos} == {(20, 40)}
    assert all(x.seccion_cm.fuente == "humano" for x in out.elementos)
    # what the drawing said stays as its alternative, intact
    assert k5.alternativas[0] == _k5(e).seccion_cm


def test_decision_for_a_vanished_mark_is_a_warning():
    out = aplicar_decisiones(
        _estructura_k5_conflict(),
        [Decision(marca="K-77", campo="estribos", valor=[], fecha=_now())],
    )
    assert any("K-77" in a and "ya no está" in a for a in out.avisos)
    assert out.decisiones[0].marca == "K-77"  # kept, never dropped


def test_resumen_counts_and_money():
    r = resumir(_estructura_k5_conflict(), _report_with_est001_price(4000.0))
    cas = next(x for x in r if x.familia == "castillo")
    assert cas.colocaciones == 2 and cas.con_definicion == 2 and cas.duda >= 1
    assert cas.en_juego_mxn == pytest.approx(
        0.20 * 0.10 * 2.9 * 2 * 4000.0
    )  # Δ area × h × 2 × P.U.


def test_recompute_without_estructura_still_works(tmp_path, data_dir):
    root = tmp_path / "demo"
    write_demo_project(root)
    settings = get_settings()
    run_full_pipeline(root, settings)
    for p in (root / settings.processed_dir_name).rglob(ESTRUCTURA_FILENAME):
        p.unlink()  # now it looks like an old run
    report = _recompute(root)
    assert report.boq.lines and not any(
        "estructura" in w.lower() and "error" in w.lower() for w in report.boq.warnings
    )
    assert not (root / settings.processed_dir_name / ESTRUCTURA_DERIVADA_FILENAME).exists()


def test_instalaciones_only_is_empty_not_a_crash():
    e = construir_estructura([], [], ScheduleInventory(), [], None, None, 2.7)
    assert e.elementos == [] and e.resumen == [] and e.verificaciones == []
    assert resumir(e, _report_with_est001_price(1.0)) == []


# --------------------------------------------------------------------- R6: los nombres de campo


def test_the_steel_stage_reads_reglas_and_elementos_by_those_names():
    # R6: compute_steel reads estructura["reglas"] and estructura["elementos"]; renaming either
    # silently turns the model path off.
    assert {"reglas", "elementos"} <= set(Estructura.model_fields)
    from klave_engine.costing.steel import compute_steel

    e = _estructura_k5_conflict()
    boq = BillOfQuantities(project_id="p", lines=[_linea("EST-001", ["d1", "d2"])])
    dets = e._contexto.detections
    for estructura in (e.model_dump(mode="json"), e.para_el_costo()):
        acero = compute_steel(boq, dets, None, None, 1.0, 3.0, estructura=estructura)
        notas = acero.lines[0].notes
        assert not any("método sin modelo estructural" in n for n in notas)
        assert any(n.startswith("K-5: 2 pzas ×") for n in notas)
    assert set(e.para_el_costo()) == {"reglas", "elementos"}


# ---------------------------------------------------------------------------- las decisiones


def test_a_decision_answers_its_finding_and_leaves_every_other_id_alone():
    e = _estructura_k5_conflict(con_k9=True)
    antes = {v.id for v in e.verificaciones}
    contestada = {v.id for v in _ocho_de(e, "K-5")}
    assert contestada and any(v.numero == 1 and "K-9" in v.marcas for v in e.verificaciones)
    out = aplicar_decisiones(
        e, [Decision(marca="K5", campo="seccion_cm", valor="20x40", fecha=_now())]
    )  # a mark written another way is the same mark
    assert {v.id for v in out.verificaciones} == antes - contestada


def test_building_with_decisions_is_applying_them_after():
    sin = _estructura_k5_conflict(con_k9=True)
    ctx = sin._contexto
    ds = [
        Decision(marca="K-5", campo="seccion_cm", valor=[20, 40], fecha=_now()),
        Decision(marca="K-9", campo="longitudinales", valor="4#4", fecha=_now()),
        Decision(marca="K-77", campo="estribos", valor=[], fecha=_now()),
    ]
    con = construir_estructura(
        ctx.entities, _MARCOS, ctx.inv, ctx.detections, ctx.segmentation, 1.0, 2.9, decisiones=ds
    )
    despues = aplicar_decisiones(sin, ds)
    for campo in ("definiciones", "elementos", "verificaciones", "decisiones", "avisos"):
        assert getattr(con, campo) == getattr(despues, campo), campo


def test_decisions_are_idempotent_and_reversible():
    e = _estructura_k5_conflict()
    d = Decision(marca="K-5", campo="seccion_cm", valor=[20, 40], fecha=_now())
    una = aplicar_decisiones(e, [d])
    dos = aplicar_decisiones(una, [d])
    assert dos.definiciones == una.definiciones and dos.elementos == una.elementos
    assert [v.id for v in dos.verificaciones] == [v.id for v in una.verificaciones]
    # taking the decision back leaves the drawing as the reading reads it
    sin = aplicar_decisiones(una, [])
    assert sin.definiciones == e.definiciones and sin.elementos == e.elementos
    assert sin.verificaciones == e.verificaciones and sin.decisiones == []


def test_the_latest_decision_per_mark_and_field_wins():
    e = _estructura_k5_conflict()
    vieja = Decision(marca="K-5", campo="seccion_cm", valor=[20, 30], fecha=_FECHA)
    nueva = Decision(marca="K-5", campo="seccion_cm", valor=[20, 40], fecha=_FECHA.replace(hour=13))
    for orden in ([vieja, nueva], [nueva, vieja]):
        assert tuple(_k5(aplicar_decisiones(e, orden)).seccion_cm.valor) == (20, 40)


def test_an_armado_decision_reaches_the_steel():
    e = _estructura_k5_conflict()
    out = aplicar_decisiones(
        e, [Decision(marca="K-5", campo="longitudinales", valor="4#6", fecha=_now())]
    )
    grupos = {(g["cantidad"], g["numero"]) for x in out.elementos for g in x.longitudinales.valor}
    assert grupos == {(4, "6")}
    from klave_engine.estructura.acero import acero_elemento

    kg = acero_elemento(out.elementos[0], out.reglas, 0.4).kg_por_numero
    assert "6" in kg and "4" not in kg


def test_a_decision_on_an_undefined_mark_goes_to_its_placements_and_check_1_stays():
    e = _estructura_k5_conflict(con_k9=True)
    out = aplicar_decisiones(
        e, [Decision(marca="K-9", campo="seccion_cm", valor=[15, 15], fecha=_now())]
    )
    k9 = next(x for x in out.elementos if x.marca == "K-9")
    assert k9.seccion_cm.fuente == "humano" and tuple(k9.seccion_cm.valor) == (15, 15)
    assert not any(
        d.marca == "K-9" for d in out.definiciones
    )  # the drawing still doesn't define it
    assert any(v.numero == 1 and "K-9" in v.marcas for v in out.verificaciones)


def test_a_decision_reaches_every_variant_of_its_mark():
    from klave_engine.estructura.definiciones import Definicion

    e = _estructura_k5_conflict()
    k5 = _k5(e)
    variante = k5.model_copy(deep=True, update={"para_muro_cm": 15.0, "variantes": []})
    e.definiciones = [
        k5.model_copy(update={"variantes": [variante]}) if isinstance(k5, Definicion) else k5
    ]
    out = aplicar_decisiones(
        e, [Decision(marca="K-5", campo="seccion_cm", valor=[20, 40], fecha=_now())]
    )
    assert _k5(out).variantes[0].seccion_cm.fuente == "humano"


@pytest.mark.parametrize(
    "campo,valor,motivo",
    [
        ("seccion_cm", [20], "b×h"),
        ("seccion_cm", [20, -1], "b×h"),
        ("longitud_m", "mucho", "longitud"),
        ("longitudinales", "4#4 VER CROQUIS RARO", "no se lee entero"),
        ("longitudinales", [], "sin varillas"),
        ("parrillas", "LS #4@20 A/S", "no lleva parrillas"),
    ],
)
def test_an_unusable_decision_value_is_an_aviso_never_an_error(campo, valor, motivo):
    out = aplicar_decisiones(
        _estructura_k5_conflict(), [Decision(marca="K-5", campo=campo, valor=valor, fecha=_now())]
    )
    assert any("K-5" in a and motivo in a and "no se aplica" in a for a in out.avisos), out.avisos
    assert _k5(out).seccion_cm.fuente != "humano"


def test_without_the_drawing_texts_the_checks_are_kept_and_it_is_said():
    e = Estructura.model_validate(_estructura_k5_conflict().model_dump(mode="json"))
    out = aplicar_decisiones(
        e, [Decision(marca="K-5", campo="seccion_cm", valor=[20, 40], fecha=_now())]
    )
    assert _k5(out).seccion_cm.fuente == "humano"
    assert out.verificaciones == e.verificaciones
    assert any("no se volvieron a correr" in a for a in out.avisos)
    # the stale contradiction stays listed, but a decided value is not at stake any more
    assert _ocho_de(out, "K-5")
    cas = resumir(out, _report_with_est001_price(4000.0))[0]
    assert cas.en_juego_cantidad == {} and cas.en_juego_mxn == 0.0


def test_saved_decisions_replace_per_mark_and_field_and_bad_entries_are_said(tmp_path):
    guardar_decision(
        tmp_path, Decision(marca="K-5", campo="seccion_cm", valor=[20, 30], fecha=_FECHA)
    )
    guardar_decision(
        tmp_path, Decision(marca="K5", campo="seccion_cm", valor=[20, 40], fecha=_FECHA)
    )
    guardar_decision(
        tmp_path, Decision(marca="K-5", campo="estribos", valor="E#3@15", fecha=_FECHA)
    )
    leidas = cargar_decisiones(tmp_path)
    assert [(d.marca, d.campo, d.valor) for d in leidas] == [
        ("K5", "seccion_cm", [20, 40]),
        ("K-5", "estribos", "E#3@15"),
    ]
    crudas = read_json(tmp_path / DECISIONES_FILENAME)
    write_json(tmp_path / DECISIONES_FILENAME, [*crudas, {"marca": "K-1"}])
    decisiones, avisos = leer_decisiones(tmp_path)
    assert len(decisiones) == 2 and len(avisos) == 1 and "no se aplica" in avisos[0]
    (tmp_path / DECISIONES_FILENAME).write_text("{no es json")
    assert leer_decisiones(tmp_path)[0] == [] and leer_decisiones(tmp_path)[1]
    assert cargar_decisiones(tmp_path / "otra") == []


# ------------------------------------------------------------------------------ la tarjeta


def test_resumen_without_steel_price_keeps_the_kilos_as_quantity():
    r = resumir(_estructura_k5_conflict(), _report_with_est001_price(4000.0))
    cas = next(x for x in r if x.familia == "castillo")
    assert cas.en_juego_cantidad["concreto_m3"] == pytest.approx(0.20 * 0.10 * 2.9 * 2)
    assert cas.en_juego_cantidad["acero_kg"] > 0
    assert cas.en_juego_sin_precio == {"acero_kg": cas.en_juego_cantidad["acero_kg"]}
    # priced steel joins the money; nothing priced at all is None, not zero
    con_acero = next(
        x
        for x in resumir(_estructura_k5_conflict(), _report_with_est001_price(4000.0, acero=30.0))
        if x.familia == "castillo"
    )
    assert con_acero.en_juego_mxn == pytest.approx(
        cas.en_juego_mxn + cas.en_juego_cantidad["acero_kg"] * 30.0
    )
    sin_precio = resumir(_estructura_k5_conflict(), _report_with_est001_price(0.0))
    sin_precio_line = SimpleNamespace(
        boq=BillOfQuantities(
            project_id="p", lines=[_linea("EST-001", ["d1", "d2"], price=9.0, unpriced=True)]
        )
    )
    assert next(x for x in resumir(_estructura_k5_conflict(), sin_precio_line)).en_juego_mxn is None
    assert sin_precio[0].en_juego_mxn == 0.0  # priced at zero is zero


def test_resumen_counts_critical_values_from_the_drawing_and_decided_ones_apart():
    e = _estructura_k5_conflict()
    cas = resumir(e, _report_with_est001_price(1.0))[0]
    # 2 castillos × (sección, altura, longitudinales, estribos); the height is supuesto
    assert cas.criticos_total == 8 and cas.criticos_del_plano == 6 and cas.criticos_humanos == 0
    out = aplicar_decisiones(
        e, [Decision(marca="K-5", campo="seccion_cm", valor=[20, 40], fecha=_now())]
    )
    decidida = resumir(out, _report_with_est001_price(1.0))[0]
    assert decidida.criticos_del_plano == 4 and decidida.criticos_humanos == 2
    assert decidida.en_juego_mxn == 0.0 and decidida.en_juego_cantidad == {}  # nothing at stake


def test_resumen_has_one_card_per_family_and_says_apart_what_it_cannot_split():
    from klave_engine.estructura.armado import GrupoVarillas, JuegoEstribos, Zona
    from klave_engine.estructura.reglas import reglas_estandar
    from klave_engine.estructura.verificaciones import Verificacion

    cas = _el(
        "castillo", [20, 20], detection_id="d1",
        altura_m=Dato(valor=3.0, fuente="nota", texto="3 m"),
        longitudinales=Dato(valor=[GrupoVarillas(cantidad=4, numero="3")], fuente="cuadro"),
        estribos=Dato(
            valor=[JuegoEstribos(tipo="estribo", cantidad=1, numero="2",
                                 zonas=[Zona(tramo="todo", separacion_m=0.15)])],
            fuente="cuadro",
        ),
        recubrimiento_m=Dato(valor=0.03, fuente="nota", texto="3 CM"),
    )  # fmt: skip
    col = _el("columna", [30, 30], detection_id="d2", marca="C-1")
    entrepisos = Verificacion(
        id="e1", numero=8, severidad="duda", mensaje="entrepisos", campo="altura_m",
        elementos=[cas.element_id, col.element_id],
        en_juego={"acero_kg": 1666.75, "concreto_m3": 4.32, "piezas": 2.0},
    )  # fmt: skip
    cada_hoja = Verificacion(
        id="r1", numero=8, severidad="aviso", mensaje="cada hoja usa la suya",
        campo="recubrimiento_m", marcas=["K-1"], elementos=[cas.element_id],
        datos=[Dato(valor=0.04, fuente="seccion_dibujada", hoja="ES-100"),
               Dato(valor=0.03, fuente="seccion_dibujada", hoja="ES-400")],
        en_juego={"acero_kg": 5.0},
    )  # fmt: skip
    e = Estructura(
        reglas=reglas_estandar(), elementos=[cas, col], verificaciones=[entrepisos, cada_hoja]
    )
    r = resumir(e, _report_with_est001_price(4000.0))
    assert [x.familia for x in r] == ["castillo", "columna"]  # each once, in the plan's order
    for x in r:
        assert x.en_juego_aparte == {"e1": {"acero_kg": 1666.75, "concreto_m3": 4.32}}
        assert x.en_juego_cantidad == {} and x.en_juego_mxn == 0.0  # never split by eye
    assert r[0].duda == 1 and r[0].aviso == 1 and r[1].aviso == 0


def test_a_decision_that_there_are_no_stirrups_is_weighed_as_such():
    from klave_engine.estructura.acero import acero_elemento

    e = _estructura_k5_conflict()
    out = aplicar_decisiones(e, [Decision(marca="K-5", campo="estribos", valor=[], fecha=_now())])
    acero = acero_elemento(out.elementos[0], out.reglas, 0.4)
    assert acero.sin_estribos_declarados and not acero.por_leer
    assert "3" not in acero.kg_por_numero  # the E#3 the drawing wrote is not weighed


def test_a_decided_value_is_not_said_to_come_from_another_sheet():
    # K-5's own sheet (ES-100) has its text unread; the element says it uses what ES-200 read —
    # once decided, it uses the decision and says nothing of the sheets.
    from klave_engine.estructura.dato import elegir
    from klave_engine.estructura.definiciones import Definicion
    from klave_engine.estructura.elementos import resolver
    from klave_engine.estructura.reglas import reglas_estandar

    seccion = elegir(
        [
            Dato(valor=[20, 30], fuente="cuadro", hoja="ES-200", texto="K-5 20X30"),
            Dato(valor=None, fuente="cuadro", hoja="ES-100", texto="K-5 2OX3O", ilegible=True),
        ]
    )
    k5 = Definicion(marca="K-5", familia="castillo", seccion_cm=seccion, hojas=["ES-100"])
    base = resolver(
        _el("castillo", None, marca="K-5"), {"K-5": k5}, {}, reglas_estandar(), frames=[]
    )
    assert any("se usa lo que se leyó en ES-200" in a for a in base.avisos)
    e = Estructura(reglas=reglas_estandar(), definiciones=[k5], elementos=[base])
    out = aplicar_decisiones(
        e, [Decision(marca="K-5", campo="seccion_cm", valor=[20, 40], fecha=_now())]
    )
    assert out.elementos[0].seccion_cm.fuente == "humano"
    assert not any("se usa lo que se leyó" in a for a in out.elementos[0].avisos)


def test_resumen_counts_only_placements_joined_to_their_own_marks_definition():
    from klave_engine.estructura.reglas import reglas_estandar

    tres = [
        _el("castillo", [15, 20], detection_id=f"d{i}").model_copy(update={"definicion": d})
        for i, d in enumerate(("marca", "familia", "ninguna"))
    ]
    r = resumir(Estructura(reglas=reglas_estandar(), elementos=tres), None)
    assert r[0].colocaciones == 3 and r[0].con_definicion == 1  # a family note is not its mark
    cas = next(
        x
        for x in resumir(_estructura_k5_conflict(con_k9=True), _report_with_est001_price(1.0))
        if x.familia == "castillo"
    )
    assert cas.colocaciones == 3 and cas.con_definicion == 2  # K-9 is not defined


def test_a_value_two_findings_put_in_doubt_is_at_stake_once():
    from klave_engine.estructura.dato import elegir
    from klave_engine.estructura.definiciones import Definicion
    from klave_engine.estructura.reglas import reglas_estandar
    from klave_engine.estructura.verificaciones import Verificacion

    dos_cortes = elegir(
        [
            Dato(valor=[30, 80], fuente="cuadro", hoja="ES-004", texto="SECCIÓN 1 30X80"),
            Dato(valor=[30, 60], fuente="cuadro", hoja="ES-004", texto="SECCIÓN 2 30X60"),
        ]
    )
    cta = Definicion(marca="CTA-3", familia="contratrabe", seccion_cm=dos_cortes)
    el = _el(
        "contratrabe", [30, 80], marca="CTA-3", detection_id="d1",
        longitud_m=Dato(valor=5.0, fuente="medido", texto="5 m"),
    )  # fmt: skip
    siete = Verificacion(
        id="v7", numero=7, severidad="duda", mensaje="dos cortes", campo="seccion_cm",
        marcas=["CTA-3"], elementos=[el.element_id],
    )  # fmt: skip
    ocho = Verificacion(
        id="v8", numero=8, severidad="duda", mensaje="se contradice", campo="seccion_cm",
        marcas=["CTA-3"], elementos=[el.element_id],
        datos=[Dato(valor=[30, 80], fuente="cuadro"), Dato(valor=[30, 60], fuente="cuadro")],
    )  # fmt: skip
    e = Estructura(
        reglas=reglas_estandar(), definiciones=[cta], elementos=[el], verificaciones=[siete, ocho]
    )
    reporte = SimpleNamespace(
        boq=BillOfQuantities(project_id="p", lines=[_linea("CIM-008", ["d1"], price=100.0)])
    )
    r = resumir(e, reporte)[0]
    assert r.en_juego_cantidad == {"concreto_m3": pytest.approx(0.3 * 0.2 * 5.0)}
    assert r.en_juego_mxn == pytest.approx(0.3 * 0.2 * 5.0 * 100.0)
    # the two drawn cuts alone (R225, check 7) already put it at stake
    solo = resumir(e.model_copy(update={"verificaciones": [siete]}), reporte)[0]
    assert solo.en_juego_cantidad == r.en_juego_cantidad


def test_a_new_assumed_height_reaches_the_elements_that_have_no_levels():
    e = _estructura_k5_conflict()
    assert {x.altura_m.valor for x in e.elementos} == {2.9}
    out = aplicar_decisiones(e, [], altura_supuesta_m=3.2)
    assert {x.altura_m.valor for x in out.elementos} == {3.2}
    assert all(x.altura_m.fuente == "supuesto" for x in out.elementos)
    assert out.altura_supuesta_m == 3.2


def test_the_pipeline_model_uses_the_projects_assumed_height(tmp_path):
    # PRUEBA-1's shape: levels that do not pair into storeys, three plantas → 7.8 / 3 = 2.6 m (the
    # height the old steel path used), never the 3.0 m default.
    from klave_engine.costing.models import CostingConfig
    from klave_engine.dxf.units import DrawingUnits
    from klave_engine.ingestion.manifest import ProjectManifest
    from klave_engine.pipeline import PipelineResult, _modelo_estructural

    dets = [_castillo("d1", "K-1", 10, 10, "p1")]
    vistas = [
        ViewRegion(view_id=v, title=v, kind=ViewKind.plan, level_key=k, anchor=(0, 0),
                   bbox=(0, 0, 100, 100) if v == "pb" else (1000, 1000, 1001, 1001))
        for v, k in (("pb", "planta_baja"), ("pa", "planta_alta"), ("az", "azotea"))
    ]  # fmt: skip
    seg = SheetSegmentation(
        views=vistas, assignment={"d1": "pb"}, is_segmented=True, npt_levels=[0.0, 3.45, 6.6, 7.8]
    )
    result = PipelineResult(
        manifest=ProjectManifest(project_id="p", project_name="p", root_path=str(tmp_path)),
        entities=[_texto("p1", "K-1", 10, 10)],
        detections=dets,
    )
    unidades = DrawingUnits(unit="m", source="declared", confidence=1.0)
    e = _modelo_estructural(
        result, [], ScheduleInventory(), seg, unidades, CostingConfig(), tmp_path,
        TextPatternConfig(),
    )  # fmt: skip
    assert e is not None and e.altura_supuesta_m == pytest.approx(2.6)
    assert e.elementos[0].altura_m.valor == pytest.approx(2.6)


def test_a_vanished_decision_is_said_in_the_run_and_its_budget(tmp_path, data_dir):
    root, control = _demo(tmp_path)
    guardar_decision(control, Decision(marca="K-77", campo="estribos", valor=[], fecha=_FECHA))
    result = run_full_pipeline(root, get_settings())
    assert any("K-77" in w for w in result.cost_report.warnings)
    assert any("K-77" in w for w in result.warnings)
    assert any("K-77" in w for w in _recompute(root).warnings)


def test_a_scenario_of_another_run_is_never_taken(tmp_path):
    from klave_engine.estructura.modelo import escribir_estructura, escribir_estructura_derivada
    from klave_engine.estructura.reglas import reglas_estandar

    corrida, control = tmp_path / "run", tmp_path / "control"
    escribir_estructura(corrida, Estructura(reglas=reglas_estandar(), avisos=["la corrida"]))
    escribir_estructura_derivada(
        control, corrida, Estructura(reglas=reglas_estandar(), avisos=["el escenario"])
    )
    assert leer_estructura_vigente(control, corrida).avisos == ["el escenario"]
    escribir_estructura(corrida, Estructura(reglas=reglas_estandar(), avisos=["otra corrida"]))
    assert leer_estructura_vigente(control, corrida).avisos == ["otra corrida"]


def test_resumen_fields_are_the_plans():
    assert {
        "familia", "colocaciones", "con_definicion", "criticos_total", "criticos_del_plano",
        "bloquea", "duda", "aviso", "en_juego_mxn", "en_juego_cantidad",
    } <= set(ResumenFamilia.model_fields)  # fmt: skip


# ----------------------------------------------------------------- la escritura de vuelta


def _el(familia, seccion, fuente="detalle", detection_id="d1", marca="K-1", **kw):
    valor = seccion
    return Elemento(
        element_id=f"el_{detection_id}",
        detection_id=detection_id,
        marca=marca,
        familia=familia,
        hoja="ES-100",
        definicion="marca",
        seccion_cm=Dato(valor=valor, fuente=fuente, texto=f"{marca} {seccion}")
        if seccion is not None
        else None,
        colocacion=Colocacion(),
        **kw,
    )


def _det(familia="castillo", det_id="d1", tipo=DetectionType.column_tag, **props):
    d = make_detection(det_id, tipo, "K-1", (0, 0, 1, 1), 0.9, [], "t", [], props, "a.dxf")
    d.mark, d.family = "K-1", familia
    return d


def test_a_drawing_section_replaces_a_marker_and_keeps_what_was_there():
    det = _det(section_area_du2=0.0225, section_source="marcador_poligonal")
    salida, escritas = escribir_en_detecciones([det], [_el("castillo", [20, 55])], 1.0)
    p = salida[0].properties
    assert p["section_cm"] == "20x55" and p["section_area_du2"] == pytest.approx(0.11)
    assert p["section_source"] == "detalle"
    assert p["seccion_previa"] == {
        "section_cm": None, "section_area_du2": 0.0225, "section_source": "marcador_poligonal"
    }  # fmt: skip
    assert escritas[0].antes == "225 cm²" and escritas[0].despues == "20x55"
    assert det.properties == {"section_area_du2": 0.0225, "section_source": "marcador_poligonal"}
    # idempotent: a second pass writes nothing and the first previa stays
    otra, nada = escribir_en_detecciones(salida, [_el("castillo", [20, 55])], 1.0)
    assert nada == [] and otra[0] is salida[0]
    humano = _el("castillo", [25, 55], fuente="humano")
    tercera, una = escribir_en_detecciones(salida, [humano], 1.0)
    assert len(una) == 1 and tercera[0].properties["seccion_previa"] == p["seccion_previa"]
    assert tercera[0].properties["section_source"] == "humano"


def test_side_order_is_the_same_section_for_a_castillo_but_not_for_a_beam():
    cas = _det(section_cm="40x30", section_source="cuadro", spec_source="detalle")
    assert escribir_en_detecciones([cas], [_el("castillo", [30, 40])], 1.0)[1] == []
    viga = _det("trabe", tipo=DetectionType.beam_tag, section_cm="80x30", section_source="cuadro")
    salida, escritas = escribir_en_detecciones([viga], [_el("trabe", [30, 80])], 1.0)
    assert salida[0].properties["section_cm"] == "30x80" and len(escritas) == 1


def test_a_supuesto_never_covers_a_measure_nor_fills_an_empty_detection():
    marcador = _det(section_area_du2=0.0225, section_source="marcador_poligonal")
    vacia = _det(det_id="d2")
    elementos = [
        _el("castillo", [15, 20], fuente="supuesto"),
        _el("castillo", [15, 20], fuente="supuesto", detection_id="d2"),
    ]
    salida, escritas = escribir_en_detecciones([marcador, vacia], elementos, 1.0)
    assert escritas == [] and salida[0] is marcador and salida[1] is vacia


def _supuestos(castillo=0.03):
    from klave_engine.costing.models import CostingAssumptions

    return CostingAssumptions(castillo_section_m2=castillo)


def test_where_concrete_and_steel_do_not_measure_the_same_it_is_said():
    marcador = _det(section_area_du2=0.0225, section_source="marcador_poligonal")
    vacia = _det(det_id="d2")
    lejos = _det(det_id="d3", section_area_du2=0.05, section_source="marcador_poligonal")
    fuera_de_rango = _det(det_id="d4", section_area_du2=0.64, section_source="marcador_poligonal")
    elementos = [
        _el("castillo", [15, 20], fuente="supuesto"),
        _el("castillo", [15, 20], fuente="supuesto", detection_id="d2"),
        _el("castillo", [15, 20], fuente="supuesto", detection_id="d3"),
        _el("castillo", [15, 20], fuente="supuesto", detection_id="d4"),
    ]
    dets = [marcador, vacia, lejos, fuera_de_rango]
    avisos = diferencias_con_el_concreto(dets, elementos, 1.0, _supuestos(), None, {"d1", "d2"})
    # one per mark; the empty detection is measured with the budget's 15x20 (the same); d3 is
    # not in a concrete line (the cimentación planta, say): nothing to compare
    assert len(avisos) == 1 and "225 cm² de la detección" in avisos[0], avisos
    assert "15x20 (supuesto)" in avisos[0] and "1 pza" in avisos[0]
    otra = diferencias_con_el_concreto(dets, elementos, 1.0, _supuestos(0.0225), None, {"d2"})
    assert "la supuesta del presupuesto (225 cm²)" in otra[0]
    # a marker out of range is not what the concrete takes: it takes its assumed section
    fuera = diferencias_con_el_concreto(dets, elementos, 1.0, _supuestos(0.04), None, {"d4"})
    assert "la supuesta del presupuesto (400 cm²), porque 6400 cm²" in fuera[0]


def test_a_value_the_cuadro_stamped_and_the_model_did_not_take_is_corrected_honestly():
    # apply_schedule stamped an AI section as «cuadro»; the model blocked it and supposes 15x20
    ia = _det(section_cm="25x25", section_source="cuadro", spec_source="ia")
    salida, escritas = escribir_en_detecciones([ia], [_el("castillo", [15, 20], "supuesto")], 1.0)
    p = salida[0].properties
    assert p["section_cm"] == "15x20" and p["section_source"] == "supuesto"
    assert escritas[0].fuente_antes == "cuadro"
    # the same value, but the cuadro label overclaims: only the label is fixed
    misma = _det(section_cm="15x20", section_source="cuadro", spec_source="ia")
    salida, escritas = escribir_en_detecciones([misma], [_el("castillo", [15, 20], "ia")], 1.0)
    assert salida[0].properties["section_source"] == "ia" and escritas[0].campo == "fuente"
    assert salida[0].properties["section_cm"] == "15x20"


def test_a_non_rectangular_section_writes_its_area_and_drops_the_rectangle():
    det = _det(section_cm="40x45", section_source="cuadro", spec_source="detalle")
    salida, escritas = escribir_en_detecciones(
        [det], [_el("castillo", {"area_cm2": 2300.0}, fuente="medido")], 1.0
    )
    p = salida[0].properties
    assert "section_cm" not in p and p["section_area_du2"] == pytest.approx(0.23)
    assert p["seccion_previa"]["section_cm"] == "40x45" and escritas[0].despues == "2300 cm²"


def test_a_declared_span_and_a_pile_length_are_written():
    viga = _det("trabe", tipo=DetectionType.beam_tag, estimated_span_length=4.0)
    declarada = _el(
        "trabe",
        [25, 50],
        longitud_m=Dato(valor=4.6, fuente="cuadro", texto="L=4.60"),
    )
    medida = _el("trabe", [25, 50], longitud_m=Dato(valor=4.0, fuente="medido", texto="4 m"))
    salida, escritas = escribir_en_detecciones([viga], [declarada], 1.0)
    assert salida[0].properties["estimated_span_length"] == pytest.approx(4.6)
    assert salida[0].properties["claro_previo"] == {"estimated_span_length": 4.0}
    assert [w.campo for w in escritas] == ["seccion", "claro"]
    otra_medida = _el("trabe", [25, 50], longitud_m=Dato(valor=4.3, fuente="medido", texto="m"))
    assert "claro" not in {w.campo for w in escribir_en_detecciones([viga], [otra_medida], 1.0)[1]}
    assert escribir_en_detecciones([viga], [medida], 1.0)[0][0].properties[
        "estimated_span_length"
    ] == pytest.approx(4.0)
    pila = _det("pilote", tipo=DetectionType.pile)
    largo = _el("pilote", None, longitud_m=Dato(valor=18.0, fuente="humano", texto="decisión"))
    salida, escritas = escribir_en_detecciones([pila], [largo], 1.0)
    assert salida[0].properties["longitud_m"] == 18.0 and escritas[0].campo == "claro"
    supuesta = _el("pilote", None, longitud_m=Dato(valor=12.0, fuente="supuesto", texto="?"))
    assert escribir_en_detecciones([pila], [supuesta], 1.0)[1] == []


def test_apply_piles_takes_the_models_length_first():
    from klave_engine.costing.piles import apply_piles

    pila = make_detection("p1", DetectionType.pile, "P-4", (0, 0, 1, 1), 0.9, [], "t", [],
                          {"longitud_m": 18.0})  # fmt: skip
    boq = BillOfQuantities(project_id="p", lines=[_linea("CIM-010", ["p1"], unit="PZA")])
    specs = {"by_mark": {"P-4": {"length_m": 12.0}}}
    from klave_engine.costing.catalog import build_default_catalog
    from klave_engine.costing.models import CostingAssumptions

    apply_piles(boq, build_default_catalog(CostingAssumptions()), {}, [pila], specs)
    metros = next(x for x in boq.lines if x.concept_code == "CIM-011")
    assert metros.quantity == 18.0


def test_a_height_the_concrete_does_not_use_is_said():
    seg = SheetSegmentation(
        views=[
            ViewRegion(
                view_id=v,
                title=v,
                kind=ViewKind.plan,
                level_key="planta",
                npt_level=n,
                anchor=(0, 0),
                bbox=(0, 0, 1, 1),
            )
            for v, n in (("pb", 0.0), ("pa", 2.9))
        ],  # fmt: skip
        assignment={"d1": "pb"},
        is_segmented=True,
        npt_levels=[0.0, 2.9],
    )
    e = _el("castillo", [20, 20], altura_m=Dato(valor=3.2, fuente="humano", texto="decisión"))
    det = _det(section_cm="20x20", section_source="cuadro", spec_source="cuadro")
    avisos = diferencias_con_el_concreto([det], [e], 1.0, _supuestos(), seg, {"d1"})
    assert len(avisos) == 1 and "toma 2.9 m" in avisos[0] and "3.2 m (humano)" in avisos[0]
    igual = e.model_copy(update={"altura_m": Dato(valor=2.9, fuente="nota", texto="niveles")})
    assert diferencias_con_el_concreto([det], [igual], 1.0, _supuestos(), seg, {"d1"}) == []


def test_without_reliable_units_nothing_is_written():
    det = _det(section_area_du2=0.0225, section_source="marcador_poligonal")
    salida, escritas = escribir_en_detecciones([det], [_el("castillo", [20, 55])], None)
    assert salida == [det] and escritas == []


# --------------------------------------------------------------- pipeline, recálculo y gold


def _recompute(root, overrides=None):
    from klave_engine.costing.catalog_store import get_catalog_store
    from klave_engine.costing.recompute import recompute_and_persist
    from klave_engine.ingestion.manifest import load_manifest

    settings = get_settings()
    control = root / settings.processed_dir_name
    pid = load_manifest(root, settings.processed_dir_name).project_id
    return recompute_and_persist(
        control, control, root / "reports", pid, overrides or CostingOverrides(),
        catalog_store=get_catalog_store(settings.data_dir),
    )  # fmt: skip


def _demo(tmp_path):
    root = tmp_path / "demo"
    write_demo_project(root, declare_units=True)
    return root, root / get_settings().processed_dir_name


def _c1_volume(report):
    line = next(x for x in report.boq.lines if x.concept_code == "EST-001")
    return line.quantity


def test_a_decision_survives_a_reprocess_and_moves_the_concrete(tmp_path, data_dir):
    root, control = _demo(tmp_path)
    antes = _c1_volume(run_full_pipeline(root, get_settings()).cost_report)
    guardar_decision(
        control, Decision(marca="C-1", campo="seccion_cm", valor=[70, 70], fecha=_FECHA)
    )
    # the recompute applies it now…
    recalculado = _recompute(root)
    derivada = leer_estructura_vigente(control, control)
    assert derivada is not None and derivada.decisiones[0].marca == "C-1"
    c1 = [x for x in derivada.elementos if x.marca == "C-1"]
    assert c1 and all(x.seccion_cm.fuente == "humano" for x in c1)
    assert _c1_volume(recalculado) > antes
    # …and a reprocess keeps it
    result = run_full_pipeline(root, get_settings())
    e = leer_estructura(control)
    assert all(x.seccion_cm.fuente == "humano" for x in e.elementos if x.marca == "C-1")
    assert _c1_volume(result.cost_report) == pytest.approx(_c1_volume(recalculado))
    assert any(
        n.startswith("Secciones del modelo estructural escritas") and "→ 70x70 (humano)" in n
        for n in result.cost_report.boq.assumptions
    )
    ids = {x.detection_id for x in e.elementos if x.marca == "C-1"}
    escritas = [d for d in result.detections if d.detection_id in ids]
    assert escritas and all(d.properties["section_source"] == "humano" for d in escritas)
    # a stale scenario of another run is never taken
    assert leer_estructura_vigente(control, control).base in ("", e.base)


def test_a_price_recompute_does_not_rebuild_the_model(tmp_path, data_dir, monkeypatch):
    root, control = _demo(tmp_path)
    # a decision the run already applied is no change either (it survives the JSON round trip)
    guardar_decision(
        control, Decision(marca="C-1", campo="seccion_cm", valor=[70, 70], nota="n", fecha=_FECHA)
    )
    run_full_pipeline(root, get_settings())
    import klave_engine.estructura.modelo as modelo

    def no(*a, **k):
        raise AssertionError("rebuilt")

    monkeypatch.setattr(modelo, "aplicar_decisiones", no)
    monkeypatch.setattr(modelo, "construir_estructura", no)
    _recompute(root)
    assert (control / ESTRUCTURA_DERIVADA_FILENAME).exists()
    monkeypatch.undo()
    # a new decision is applied once; the next price recompute reuses that scenario
    guardar_decision(
        control, Decision(marca="C-1", campo="seccion_cm", valor=[80, 80], fecha=_FECHA)
    )
    _recompute(root)
    monkeypatch.setattr(modelo, "aplicar_decisiones", no)
    monkeypatch.setattr(modelo, "construir_estructura", no)
    report = _recompute(root)
    vigente = leer_estructura_vigente(control, control)
    assert {tuple(x.seccion_cm.valor) for x in vigente.elementos if x.marca == "C-1"} == {(80, 80)}
    assert report.boq.lines


def test_recompute_with_an_estructura_written_before_its_optional_fields(tmp_path, data_dir):
    root, control = _demo(tmp_path)
    completo = run_full_pipeline(root, get_settings()).cost_report
    crudo = read_json(control / ESTRUCTURA_FILENAME)
    # the plan's own lists stay (a model always had them); every optional field inside them, and
    # every field this task added, goes
    viejo = _quitar_opcionales(
        Estructura, crudo, conservar={"definiciones", "por_familia", "elementos", "verificaciones"}
    )
    assert {"resumen", "decisiones", "marcos", "patrones", "altura_supuesta_m"}.isdisjoint(viejo)
    assert (
        "colocacion" not in viejo["elementos"][0] and "recubrimiento_m" not in viejo["elementos"][0]
    )
    write_json(control / ESTRUCTURA_FILENAME, viejo)
    assert leer_estructura(control) is not None
    report = _recompute(root)
    assert report.boq.lines and _c1_volume(report) == pytest.approx(_c1_volume(completo))
    assert leer_estructura_vigente(control, control).resumen  # rewritten with today's fields


def test_an_unreadable_estructura_is_rebuilt_from_the_run_and_said(tmp_path, data_dir):
    root, control = _demo(tmp_path)
    completo = run_full_pipeline(root, get_settings()).cost_report
    (control / ESTRUCTURA_FILENAME).write_text(json.dumps({"version": 1, "reglas": "roto"}))
    report = _recompute(root)
    assert any("se rehízo" in w for w in report.warnings)
    assert _c1_volume(report) == pytest.approx(_c1_volume(completo))


def test_a_broken_model_never_fails_the_run(tmp_path, data_dir, monkeypatch):
    import klave_engine.pipeline as pipeline

    def roto(*a, **k):
        raise RuntimeError("detalle roto")

    monkeypatch.setattr(pipeline, "construir_estructura", roto)
    root, control = _demo(tmp_path)
    result = run_full_pipeline(root, get_settings())
    assert result.cost_report is not None and not (control / ESTRUCTURA_FILENAME).exists()
    assert any("lectura estructural no se pudo construir" in w for w in result.warnings)


def test_an_excluded_detection_is_no_element_of_the_budget():
    from klave_engine.costing.models import CostingConfig
    from klave_engine.costing.report import generate_cost_report
    from klave_engine.dxf.units import DrawingUnits

    e = _estructura_k5_conflict()
    d1 = next(d for d in e._contexto.detections if d.detection_id == "d1")
    unidades = DrawingUnits(unit="m", source="declared", confidence=1.0)
    report = generate_cost_report(
        "p", [d1], unidades, CostingConfig(), _planta([d1]), None,
        estructura=e.model_dump(mode="json"),
    )  # fmt: skip
    # d2 was excluded in Revisión: its element is neither weighed nor «outside the budget»
    assert not any(w.startswith("Acero fuera del presupuesto") for w in report.boq.warnings)
    assert any(w.startswith("Acero calculado (") for w in report.boq.warnings)  # d1 is


def test_the_gold_money_uses_the_runs_model(tmp_path, data_dir, monkeypatch):
    from klave_engine.costing import report as report_module
    from klave_engine.evals.gold import _engine_money

    root, control = _demo(tmp_path)
    detections = run_full_pipeline(root, get_settings()).detections
    vistos = []
    original = report_module.compute_steel

    def espia(*a, **k):
        vistos.append(k.get("estructura"))
        return original(*a, **k)

    monkeypatch.setattr(report_module, "compute_steel", espia)
    _engine_money(root, get_settings(), detections)
    assert vistos and vistos[0] is not None and vistos[0]["elementos"]


def test_the_model_uses_the_same_assumed_height_as_the_old_steel_path():
    from klave_engine.costing.steel import altura_supuesta_m

    seg = SheetSegmentation(
        views=[
            ViewRegion(
                view_id=v,
                title=v,
                kind=ViewKind.plan,
                level_key=k,
                anchor=(0, 0),
                bbox=(0, 0, 1, 1),
            )
            for v, k in (
                ("c", "cimentacion"),
                ("pb", "planta_baja"),
                ("pa", "planta_alta"),
                ("az", "azotea"),
            )
        ],  # fmt: skip
        assignment={},
        is_segmented=True,
        npt_levels=[0.0, 3.45, 6.6, 7.8],
    )
    assert altura_supuesta_m(seg, 3.0) == pytest.approx(2.6)  # PRUEBA-1: 7.8 m / 3 plantas
    assert altura_supuesta_m(None, 3.0) == 3.0


# ------------------------------------------------------------------------------- utilidades


def _quitar_opcionales(modelo, datos, conservar=frozenset()):
    """``datos`` (el volcado de ``modelo``) sin ningún campo opcional, en cualquier nivel (salvo
    los de ``conservar`` en este nivel): como lo habría escrito un motor anterior a esos campos."""
    if not isinstance(datos, dict):
        return datos
    salida = {}
    for nombre, campo in modelo.model_fields.items():
        if nombre not in datos or (not campo.is_required() and nombre not in conservar):
            continue
        salida[nombre] = _quitar_en(campo.annotation, datos[nombre])
    return salida


def _quitar_en(anotacion, valor):
    from pydantic import BaseModel

    modelos = [t for t in _tipos(anotacion) if isinstance(t, type) and issubclass(t, BaseModel)]
    if not modelos:
        return valor
    m = modelos[0]
    if m is Dato:
        return valor  # a Dato is the same since Tarea 2: its value is never optional
    if isinstance(valor, list):
        return [_quitar_opcionales(m, v) for v in valor]
    if isinstance(valor, dict) and not set(valor) & set(m.model_fields):
        return {k: _quitar_opcionales(m, v) for k, v in valor.items()}
    return _quitar_opcionales(m, valor)


def _tipos(anotacion):
    yield anotacion
    for arg in typing.get_args(anotacion):
        yield from _tipos(arg)
