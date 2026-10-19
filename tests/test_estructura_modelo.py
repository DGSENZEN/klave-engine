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
    notas_de_escritura,
    resumir,
)
from klave_engine.estructura.modelo import NOMBRE_DEL_CAMPO as _NOMBRE
from klave_engine.estructura.verificaciones import id_de_verificacion
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


def _planta(detecciones, niveles=False):
    """La planta de ES-100; con ``niveles``, declarada a +0.00 bajo otra a +2.90 (su entrepiso
    se lee: 2.9 m, ``nota``); sin ellos, su altura es la supuesta."""
    vistas = [
        ViewRegion(
            view_id="f1",
            title="ES-100 · PLANTA",
            kind=ViewKind.plan,
            level_key="planta",
            npt_level=0.0 if niveles else None,
            anchor=(0, 0),
            bbox=(0, 0, 100, 100),
        )
    ]
    if niveles:
        vistas.append(
            ViewRegion(
                view_id="fz",
                title="AZOTEA",
                kind=ViewKind.plan,
                level_key="azotea",
                npt_level=2.9,
                anchor=(0, 0),
                bbox=(600, 0, 700, 100),
            )  # fmt: skip
        )
    return SheetSegmentation(
        views=vistas,
        assignment={d.detection_id: "f1" for d in detecciones},
        is_segmented=True,
        npt_levels=[0.0, 2.9] if niveles else [],
    )


_MARCOS = [
    SheetFrame(frame_id="f1", bbox=(0, 0, 100, 100), source_file="a.dxf", code="ES-100"),
    SheetFrame(frame_id="f2", bbox=(200, 0, 300, 100), source_file="a.dxf", code="ES-200"),
    SheetFrame(frame_id="f4", bbox=(400, 0, 500, 100), source_file="a.dxf", code="ES-400"),
]


def _estructura_k5_conflict(con_k9=False, niveles=False):
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
    return construir_estructura(textos, _MARCOS, inv, dets, _planta(dets, niveles), 1.0, 2.9)


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
    # with its storey declared, the only open doubt of K-5 is the contradiction, which has a figure
    r = resumir(_estructura_k5_conflict(niveles=True), _report_with_est001_price(4000.0))
    cas = next(x for x in r if x.familia == "castillo")
    assert cas.en_juego_desconocido == 0
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


def _con_variantes():
    """K-5 con dos variantes por muro (15 y 20 cm): d1 resolvió la de 15 cm; d2 no (su muro no
    se midió), así que toma la definición de la marca con sus variantes juntas."""
    from klave_engine.estructura.elementos import resolver_todos

    e = _estructura_k5_conflict()
    k5 = _k5(e)
    v15 = k5.model_copy(
        deep=True,
        update={"para_muro_cm": 15.0, "variantes": [],
                "seccion_cm": Dato(valor=[15, 20], fuente="detalle", hoja="ES-200")},
    )  # fmt: skip
    v20 = k5.model_copy(
        deep=True,
        update={"para_muro_cm": 20.0, "variantes": [],
                "seccion_cm": Dato(valor=[20, 20], fuente="detalle", hoja="ES-200")},
    )  # fmt: skip
    e.definiciones = [k5.model_copy(update={"variantes": [v15, v20]})]
    medido = Dato(valor=15.0, fuente="medido", texto="el muro bajo la etiqueta: 15 cm")
    e.elementos = [
        x.model_copy(update={"colocacion": x.colocacion.model_copy(update={"muro_cm": medido})})
        if x.detection_id == "d1"
        else x
        for x in e.elementos
    ]
    e.elementos = resolver_todos(e.elementos, {"K-5": e.definiciones[0]}, {}, e.reglas, frames=[])
    return e


def test_a_decision_on_a_mark_with_variants_takes_only_the_unresolved_placements():
    # R239: d1 keeps its wall's variant; only d2 (its variant unknown) takes the mark's decision.
    e = _con_variantes()
    por_id = {x.detection_id: x for x in e.elementos}
    assert tuple(por_id["d1"].seccion_cm.valor) == (15, 20)
    out = aplicar_decisiones(
        e, [Decision(marca="K-5", campo="seccion_cm", valor=[25, 20], fecha=_now())]
    )
    por_id = {x.detection_id: x for x in out.elementos}
    assert tuple(por_id["d1"].seccion_cm.valor) == (15, 20)
    assert por_id["d1"].seccion_cm.fuente == "detalle"
    assert por_id["d2"].seccion_cm.fuente == "humano"
    assert all(v.seccion_cm.fuente != "humano" for v in _k5(out).variantes)
    aviso = next(a for a in out.avisos if a.startswith("Decisión sobre K-5 (sección"))
    assert "la toman 1 pza de 2" in aviso and "conservan la de su muro" in aviso
    # a decision that names the variant takes exactly that variant
    out = aplicar_decisiones(
        e,
        [Decision(marca="K-5", campo="seccion_cm", valor=[15, 25], para_muro_cm=15, fecha=_now())],
    )
    por_id = {x.detection_id: x for x in out.elementos}
    assert tuple(por_id["d1"].seccion_cm.valor) == (15, 25)
    assert por_id["d2"].seccion_cm.fuente != "humano"
    assert _k5(out).variantes[0].seccion_cm.fuente == "humano"
    sin = aplicar_decisiones(
        e,
        [Decision(marca="K-5", campo="seccion_cm", valor=[15, 25], para_muro_cm=30, fecha=_now())],
    )
    assert any("no tiene una variante para muros de 30 cm" in a for a in sin.avisos)


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
    e = Estructura.model_validate(_estructura_k5_conflict(niveles=True).model_dump(mode="json"))
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
    r = resumir(_estructura_k5_conflict(niveles=True), _report_with_est001_price(4000.0))
    cas = next(x for x in r if x.familia == "castillo")
    assert cas.en_juego_cantidad["concreto_m3"] == pytest.approx(0.20 * 0.10 * 2.9 * 2)
    assert cas.en_juego_cantidad["acero_kg"] > 0
    assert cas.en_juego_sin_precio == {"acero_kg": cas.en_juego_cantidad["acero_kg"]}
    # priced steel joins the money; nothing priced at all is None, not zero
    con_acero = next(
        x
        for x in resumir(
            _estructura_k5_conflict(niveles=True), _report_with_est001_price(4000.0, acero=30.0)
        )
        if x.familia == "castillo"
    )
    assert con_acero.en_juego_mxn == pytest.approx(
        cas.en_juego_mxn + cas.en_juego_cantidad["acero_kg"] * 30.0
    )
    sin_precio = resumir(_estructura_k5_conflict(niveles=True), _report_with_est001_price(0.0))
    sin_precio_line = SimpleNamespace(
        boq=BillOfQuantities(
            project_id="p", lines=[_linea("EST-001", ["d1", "d2"], price=9.0, unpriced=True)]
        )
    )
    nada = next(x for x in resumir(_estructura_k5_conflict(niveles=True), sin_precio_line))
    assert nada.en_juego_mxn is None and nada.en_juego_sin_precio["concreto_m3"] > 0
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
    # the contradiction is answered; the supposed height is still open and has no figure: never $0
    assert decidida.en_juego_cantidad == {} and decidida.en_juego_desconocido == 1
    assert decidida.en_juego_mxn is None
    nivelada = aplicar_decisiones(
        _estructura_k5_conflict(niveles=True),
        [Decision(marca="K-5", campo="seccion_cm", valor=[20, 40], fecha=_now())],
    )
    nada = resumir(nivelada, _report_with_est001_price(1.0))[0]
    assert nada.duda == 0 and nada.en_juego_mxn == 0.0  # nothing open: nothing at stake


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
        # never split by eye, and while it is open the card gives no money (never $0)
        assert x.en_juego_cantidad == {}
    assert r[0].en_juego_mxn is None and r[1].en_juego_mxn == 0.0  # the finding is on one card
    assert r[0].duda == 1 and r[0].aviso == 1 and r[1].duda == 0 and r[1].aviso == 0


def test_a_decision_without_pieces_is_refused():
    # R244 (Task 13 review): «no stirrups» is no armado a person decides — an empty list was taken
    # as such (Task 12) and dropped the stirrups' steel without a figure; now it is refused, as an
    # empty «longitudinales» always was, and the drawing's E#3 is still weighed.
    from klave_engine.estructura.acero import acero_elemento

    e = _estructura_k5_conflict()
    for campo in ("estribos", "longitudinales"):
        out = aplicar_decisiones(e, [Decision(marca="K-5", campo=campo, valor=[], fecha=_now())])
        assert any(
            a.startswith(f"Decisión sobre K-5 ({_NOMBRE[campo]})") and "no se aplica" in a
            for a in out.avisos
        ), out.avisos
    acero = acero_elemento(out.elementos[0], out.reglas, 0.4)
    assert "3" in acero.kg_por_numero


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


def test_the_known_money_is_never_hidden_by_a_finding_without_a_figure():
    # Task 12 carried minor: an open doubt with no figure makes the card's money None (never $0),
    # but the priced part of what is at stake is still said, and the cards rank by it.
    from klave_engine.estructura.verificaciones import Verificacion

    e = _estructura_k5_conflict()  # its storey is assumed: a doubt with no figure
    cas = next(x for x in resumir(e, _report_with_est001_price(4000.0)) if x.familia == "castillo")
    assert cas.en_juego_desconocido >= 1 and cas.en_juego_mxn is None
    assert cas.en_juego_mxn_conocido == pytest.approx(0.20 * 0.10 * 2.9 * 2 * 4000.0)
    sin_nada = resumir(_estructura_k5_conflict(niveles=True), _report_with_est001_price(0.0))
    assert sin_nada[0].en_juego_mxn == 0.0 and sin_nada[0].en_juego_mxn_conocido == 0.0
    # d1 a columna whose concrete is priced and that has an open doubt without a figure; d2 a
    # castillo whose line has no price: the same Δ each, so only the known money orders them
    e = _estructura_k5_conflict()
    e.elementos = [
        x.model_copy(update={"familia": "columna"}) if x.detection_id == "d1" else x
        for x in e.elementos
    ]
    d1 = next(x.element_id for x in e.elementos if x.detection_id == "d1")
    e.verificaciones = [
        *e.verificaciones,
        Verificacion(
            id="c", numero=7, severidad="duda", mensaje="C", marcas=["K-5"], elementos=[d1]
        ),
    ]
    report = SimpleNamespace(
        boq=BillOfQuantities(
            project_id="p",
            lines=[
                _linea("EST-001", ["d1"], price=4000.0),
                _linea("EST-002", ["d2"], price=0.0, unpriced=True),
            ],
        )
    )
    r = resumir(e, report)
    col, cas = r[0], r[1]
    assert (col.familia, cas.familia) == ("columna", "castillo")
    assert col.en_juego_mxn is None and col.en_juego_mxn_conocido == pytest.approx(
        0.20 * 0.10 * 2.9 * 4000.0
    )
    assert cas.en_juego_cantidad["concreto_m3"] == pytest.approx(
        col.en_juego_cantidad["concreto_m3"]
    )


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
        "section_cm": None, "section_area_du2": 0.0225, "section_source": "marcador_poligonal",
        "section_perimetro_du": None, "spec_rebar": None, "spec_stirrups": None,
    }  # fmt: skip
    assert escritas[0].antes == "225 cm²" and escritas[0].despues == "20x55"
    assert det.properties == {"section_area_du2": 0.0225, "section_source": "marcador_poligonal"}
    # R235, a pure function of (the detector's detection, the model): on an already written
    # detection (an old run saved it) it gives the same result, its first previa intact…
    otra, _ = escribir_en_detecciones(salida, [_el("castillo", [20, 55])], 1.0)
    assert otra[0].properties == p and otra[0].evidence.notes == salida[0].evidence.notes
    humano = _el("castillo", [25, 55], fuente="humano")
    tercera, una = escribir_en_detecciones(salida, [humano], 1.0)
    assert len(una) == 1 and tercera[0].properties["seccion_previa"] == p["seccion_previa"]
    assert tercera[0].properties["section_source"] == "humano"
    # …and a model without the decision restores what the detector read, exactly
    vuelta, nada = escribir_en_detecciones(tercera, [_el("castillo", [15, 20], "supuesto")], 1.0)
    assert nada == [] and vuelta[0].properties == det.properties
    assert vuelta[0].evidence.notes == det.evidence.notes


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
    assert salida[0].properties["longitud_m"] == 18.0
    # a pile's length is no beam's span: its write says so (Task 12 carried minor)
    assert [(w.campo, w.despues) for w in escritas] == [("longitud_m", "18 m")]
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
        n.startswith("Secciones y armados del modelo estructural escritos")
        and "→ 70x70 (humano)" in n
        for n in result.cost_report.boq.assumptions
    )
    # R235: detections.json keeps what the detector read; the decision lives only in the costing
    ids = {x.detection_id for x in e.elementos if x.marca == "C-1"}
    guardadas = [d for d in read_json(control / "detections.json") if d["detection_id"] in ids]
    assert guardadas and all(
        d["properties"].get("section_source") != "humano"
        and "seccion_previa" not in d["properties"]
        for d in guardadas
    )
    assert {w.detection_id for w in e.escrituras} >= ids
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


# ------------------------------------------------------------- ronda de arreglos 1 (R235–R242)


def test_a_removed_decision_leaves_the_concrete_as_if_it_never_was(tmp_path, data_dir):
    # R235: the decision lives in the costing, never in detections.json.
    root, control = _demo(tmp_path)
    limpio = _c1_volume(run_full_pipeline(root, get_settings()).cost_report)
    guardar_decision(
        control, Decision(marca="C-1", campo="seccion_cm", valor=[70, 70], fecha=_FECHA)
    )
    con = _c1_volume(run_full_pipeline(root, get_settings()).cost_report)
    assert con > limpio
    (control / DECISIONES_FILENAME).unlink()
    assert _c1_volume(_recompute(root)) == pytest.approx(limpio)
    assert _c1_volume(run_full_pipeline(root, get_settings()).cost_report) == pytest.approx(limpio)


def test_an_old_run_that_saved_a_decision_on_its_detections_is_restored():
    # A detections.json written by the first Task 12 commit carries the humano section and pile
    # length; costing without the decision measures what the detector read.
    from klave_engine.costing.models import CostingConfig
    from klave_engine.costing.report import generate_cost_report
    from klave_engine.dxf.units import DrawingUnits

    escrita = _det(
        section_cm="70x70", section_area_du2=0.49, section_source="humano",
        seccion_previa={"section_cm": None, "section_area_du2": 0.0225,
                        "section_source": "marcador_poligonal"},
        seccion_del_modelo="decisión",
    )  # fmt: skip
    escrita.evidence.notes.append("Sección 70x70 del modelo estructural (humano: «decisión»)")
    limpia = _det(section_area_du2=0.0225, section_source="marcador_poligonal")
    salida, nada = escribir_en_detecciones([escrita], [_el("castillo", [15, 20], "supuesto")], 1.0)
    assert nada == [] and salida[0].properties == limpia.properties
    assert salida[0].evidence.notes == limpia.evidence.notes
    pila = make_detection(
        "p1", DetectionType.pile, "P-4", (0, 0, 1, 1), 0.9, [], "t", [],
        {"longitud_m": 18.0, "longitud_fuente": "humano", "longitud_previa": {"longitud_m": None}},
    )  # fmt: skip
    pila.mark, pila.family = "P-4", "pilote"
    sin = _el("pilote", None, detection_id="p1", marca="P-4",
              longitud_m=Dato(valor=12.0, fuente="supuesto", texto="?"))  # fmt: skip
    unidades = DrawingUnits(unit="m", source="declared", confidence=1.0)
    from klave_engine.estructura.reglas import reglas_estandar

    def metros(det, elementos):
        r = generate_cost_report(
            "p", [det], unidades, CostingConfig(), None, None,
            schedule_specs={"by_mark": {"P-4": {"length_m": 10.0}}},
            estructura={"reglas": reglas_estandar(), "elementos": elementos},
        )  # fmt: skip
        return next(x.quantity for x in r.boq.lines if x.concept_code == "CIM-011")

    assert metros(pila, [sin]) == 10.0  # the specs' length, as if the decision never was
    decidida = sin.model_copy(update={"longitud_m": Dato(valor=18.0, fuente="humano", texto="d")})
    assert metros(pila, [decidida]) == 18.0


def test_a_variants_section_goes_with_its_own_armado():
    # R236: the 30 cm wall's variant writes 30x20 AND its 6#3 / E#2@15, never 30x20 with 4#3.
    from klave_engine.costing.sintesis import firma
    from klave_engine.estructura.armado import GrupoVarillas, JuegoEstribos, Zona

    det = _det(
        "dala", tipo=DetectionType.beam_tag, section_cm="15x20", section_source="cuadro",
        spec_source="detalle", spec_rebar="4#3", spec_stirrups="E#2@15",
    )  # fmt: skip
    e = _el(
        "dala", [30, 20], marca="CI",
        longitudinales=Dato(valor=[GrupoVarillas(cantidad=6, numero="3")], fuente="detalle"),
        estribos=Dato(
            valor=[JuegoEstribos(tipo="estribo", cantidad=1, numero="2",
                                 zonas=[Zona(tramo="todo", separacion_m=0.15)])],
            fuente="detalle",
        ),
        avisos=["variante: CI «para muros de 30 cm»: el muro bajo la etiqueta: 30 cm"],
    )  # fmt: skip
    salida, escritas = escribir_en_detecciones([det], [e], 1.0)
    p = salida[0].properties
    assert (
        p["section_cm"] == "30x20" and p["spec_rebar"] == "6#3" and p["spec_stirrups"] == "E#2@15"
    )
    # one previa for both writes: what the detector had, never the section just written
    assert (
        p["seccion_previa"]["spec_rebar"] == "4#3" and p["seccion_previa"]["section_cm"] == "15x20"
    )
    assert {w.campo for w in escritas} == {"seccion", "armado"}
    assert firma(salida[0], 1.0) == {"seccion": "20x30", "armado": "6#3"}
    # the same section as the detection's, but its variant's armado differs: the armado is written
    igual = det.model_copy(update={"properties": {**det.properties, "section_cm": "30x20"}})
    otra, escritas = escribir_en_detecciones([igual], [e], 1.0)
    assert otra[0].properties["spec_rebar"] == "6#3" and [w.campo for w in escritas] == ["armado"]
    # the budget's note says the armado rewrite too (Task 12 carried minor), and an armado-only
    # write never says a section «→» to itself
    assert notas_de_escritura(salida) == [
        "Secciones y armados del modelo estructural escritos en las detecciones (la definición de "
        "cada marca en su hoja, con su fuente; lo que había queda en la detección): K-1 (1): "
        "15x20 (cuadro) → 30x20 (detalle), armado 4#3 E#2@15 → 6#3 E#2@15 (detalle)"
    ]
    (nota,) = notas_de_escritura(otra)
    assert nota.endswith(": K-1 (1): armado 4#3 E#2@15 → 6#3 E#2@15 (detalle)")
    # a section-only write says no armado
    sola = _el("castillo", [20, 20], marca="K-1")
    marcador = _det("castillo", section_cm="15x20", section_source="cuadro", spec_source="cuadro")
    (nota,) = notas_de_escritura(escribir_en_detecciones([marcador], [sola], 1.0)[0])
    assert nota.endswith(": K-1 (1): 15x20 (cuadro) → 20x20 (detalle)")


def test_a_height_decision_on_a_castillo_waits_for_its_storey():
    # R237: concrete measures a castillo by its storey; a human height would move only the steel.
    out = aplicar_decisiones(
        _estructura_k5_conflict(),
        [Decision(marca="K-5", campo="longitud_m", valor=3.2, fecha=_now())],
    )
    assert any("se decide por entrepiso (pendiente)" in a for a in out.avisos)
    assert all(x.altura_m.fuente != "humano" for x in out.elementos)


def test_a_beam_length_decision_needs_one_measured_span():
    from klave_engine.estructura.definiciones import Definicion
    from klave_engine.estructura.reglas import reglas_estandar

    def viga(i, claro):
        x = _el("trabe", [25, 50], marca="T-1", detection_id=f"t{i}")
        medido = Dato(valor=claro, fuente="medido", texto=f"{claro} m")
        return x.model_copy(update={"colocacion": Colocacion(longitud_m=medido)})

    t1 = Definicion(marca="T-1", familia="trabe", seccion_cm=Dato(valor=[25, 50], fuente="cuadro"))
    d = Decision(marca="T-1", campo="longitud_m", valor=5.0, fecha=_now())
    distintas = Estructura(
        reglas=reglas_estandar(), definiciones=[t1], elementos=[viga(1, 4.0), viga(2, 6.0)]
    )
    out = aplicar_decisiones(distintas, [d])
    assert any("miden claros distintos (4 m, 6 m)" in a for a in out.avisos)
    iguales = distintas.model_copy(update={"elementos": [viga(1, 4.0), viga(2, 4.0)]})
    out = aplicar_decisiones(iguales, [d])
    assert {x.longitud_m.fuente for x in out.elementos} == {"humano"}


def test_naive_and_aware_decision_dates_are_both_utc(tmp_path):
    # R238: a decisions file mixing «…T12:00:00» and «…Z» used to crash the recompute.
    write_json(
        tmp_path / DECISIONES_FILENAME,
        [
            {"marca": "K-5", "campo": "seccion_cm", "valor": v, "fecha": f}
            for v, f in (([20, 30], "2026-10-18T12:00:00"), ([20, 40], "2026-10-18T13:00:00Z"))
        ],
    )
    decisiones = cargar_decisiones(tmp_path)
    assert all(d.fecha.tzinfo is not None for d in decisiones)
    out = aplicar_decisiones(_estructura_k5_conflict(), decisiones)
    assert tuple(_k5(out).seccion_cm.valor) == (20, 40)  # 13:00 UTC is the latest


def test_every_finding_is_on_exactly_one_card():
    # R240: the card totals are the findings; what is no family's goes to «general».
    from klave_engine.estructura.reglas import reglas_estandar
    from klave_engine.estructura.verificaciones import Verificacion

    e = _estructura_k5_conflict(con_k9=True)
    extra = [
        Verificacion(id="z", numero=10, severidad="duda", mensaje="ZC-1 escrita", marcas=["ZC-1"]),
        Verificacion(id="g", numero=8, severidad="duda", mensaje="tabla contra nota"),
        Verificacion(id="m", numero=2, severidad="aviso", mensaje="D-9", marcas=["XYZ-9"]),
    ]
    e = e.model_copy(update={"verificaciones": [*e.verificaciones, *extra]})
    r = resumir(e, _report_with_est001_price(1.0))
    assert sum(x.bloquea + x.duda + x.aviso for x in r) == len(e.verificaciones)
    por = {x.familia: x for x in r}
    assert por["zapata"].duda == 1  # by its mark's prefix
    assert por["general"].duda == 1 and por["general"].aviso == 1
    assert por["general"].en_juego_mxn is None and por["general"].en_juego_desconocido == 1
    assert Estructura(reglas=reglas_estandar()).resumen == []


def test_cards_rank_by_money_then_known_quantity_and_state_out_of_budget_apart():
    e = _estructura_k5_conflict(niveles=True)
    solo_d1 = SimpleNamespace(
        boq=BillOfQuantities(project_id="p", lines=[_linea("EST-001", ["d1"], price=4000.0)])
    )
    cas = next(x for x in resumir(e, solo_d1) if x.familia == "castillo")
    # d2 is no line's: its Δ is said apart, never summed into what is at stake in the budget
    assert cas.en_juego_cantidad["concreto_m3"] == pytest.approx(0.02 * 2.9)
    assert cas.en_juego_fuera_del_presupuesto["concreto_m3"] == pytest.approx(0.02 * 2.9)
    assert cas.en_juego_mxn == pytest.approx(0.02 * 2.9 * 4000.0)
    from klave_engine.estructura.verificaciones import Verificacion

    e = e.model_copy(
        update={
            "verificaciones": [
                *e.verificaciones,
                Verificacion(id="t", numero=7, severidad="duda", mensaje="T-1", marcas=["T-1"]),
            ]
        }
    )
    assert [x.familia for x in resumir(e, _report_with_est001_price(4000.0))][:2] == [
        "castillo",
        "trabe",
    ]


def test_a_reading_aviso_on_a_decided_field_is_never_a_new_doubt():
    # R241: K-5's reading says its drawn section does not match its cotas (a duda of its own);
    # once a person decides the section, that is an aviso naming who decided, never a new duda.
    sin = _estructura_k5_conflict(niveles=True)
    ctx = sin._contexto
    aviso = "sección dibujada 17.8x84.4 cm a la escala de sus cotas: no coincide con 15x85"

    def con_aviso(decisiones):
        e = construir_estructura(
            ctx.entities, _MARCOS, ctx.inv, ctx.detections, ctx.segmentation, 1.0, 2.9
        )
        _k5(e).avisos.append(aviso)
        e.decisiones = [Decision(marca="X", campo="estribos", valor=[], fecha=_now())]
        return aplicar_decisiones(e, decisiones)  # re-runs the checks with the aviso

    antes = [v for v in con_aviso([]).verificaciones if v.numero == 11 and "K-5" in v.marcas]
    assert [v.severidad for v in antes] == ["duda"]
    d = Decision(marca="K-5", campo="seccion_cm", valor=[15, 85], actor="Diego", fecha=_now())
    once = [v for v in con_aviso([d]).verificaciones if v.numero == 11 and "K-5" in v.marcas]
    assert [v.severidad for v in once] == ["aviso"]
    assert "decidido por Diego" in once[0].mensaje and "17.8x84.4" in once[0].mensaje


def test_a_decided_aviso_on_a_mark_with_variants_says_who_took_it_and_folds_only_its_part():
    # Task 12 carried minor (R241 on variant marks): a mark-level decision reaches only the
    # placements whose variant is unresolved, so it folds only the mark's own reading avisos and
    # says how many placements took it; the 15 cm variant's own aviso stays in doubt (folded into
    # the mark's check-7 finding, R228) until a decision names that variant.
    e = _con_variantes()
    k5 = _k5(e)
    de_la_marca = "sección dibujada 21.0x31.0 cm a la escala de sus cotas: no coincide con 20x30"
    de_la_15 = "sección dibujada 14.1x22.4 cm a la escala de sus cotas: no coincide con 15x20"
    k5.avisos += [de_la_marca, de_la_15]
    k5.variantes[0].avisos.append(de_la_15)
    e.decisiones = [Decision(marca="X", campo="estribos", valor=[], fecha=_now())]

    def hallazgos(decisiones):
        out = aplicar_decisiones(e, decisiones)
        suyos = [v for v in out.verificaciones if "K-5" in v.marcas]
        dudas = " ".join(v.mensaje for v in suyos if v.severidad != "aviso")
        decididos = [v for v in suyos if v.numero == 11 and v.severidad == "aviso"]
        return dudas, decididos

    dudas, decididos = hallazgos([])
    assert de_la_marca in dudas and de_la_15 in dudas and decididos == []
    marca = Decision(marca="K-5", campo="seccion_cm", valor=[25, 20], actor="R", fecha=_now())
    dudas, (aviso,) = hallazgos([marca])
    assert de_la_15 in dudas and de_la_marca not in dudas
    assert aviso.mensaje.startswith("K-5: la sección es 20x25 cm, decidido por R")
    assert "lo toman 1 de 2 colocaciones" in aviso.mensaje
    assert de_la_marca in aviso.mensaje and de_la_15 not in aviso.mensaje
    # the mark-level aviso keeps the id it had before this rule (its clave is unchanged)
    assert aviso.id == id_de_verificacion(11, "K-5", "", "avisos de lectura: decidido: seccion_cm")
    quince = Decision(
        marca="K-5", campo="seccion_cm", valor=[15, 25], para_muro_cm=15, actor="R", fecha=_now()
    )
    dudas, (aviso,) = hallazgos([quince])
    assert de_la_marca in dudas and de_la_15 not in dudas
    assert aviso.mensaje.startswith("K-5 (para muros de 15 cm): la sección es 15x25 cm")
    assert "lo toman 1 de 2 colocaciones" in aviso.mensaje and de_la_15 in aviso.mensaje
    # both decided: neither reading is in doubt any more; one aviso per part, distinct ids
    dudas, ambos = hallazgos([marca, quince])
    assert de_la_marca not in dudas and de_la_15 not in dudas
    assert len(ambos) == 2 and len({x.id for x in ambos}) == 2
    # each part counts its own placements: d2 took the mark's, d1 its variant's
    assert all("lo toman 1 de 2 colocaciones" in x.mensaje for x in ambos)
    # without variants nothing changes: every placement takes it and no count is said
    sin_variantes = _estructura_k5_conflict(niveles=True)
    _k5(sin_variantes).avisos.append(de_la_marca)
    sin_variantes.decisiones = [Decision(marca="X", campo="estribos", valor=[], fecha=_now())]
    out = aplicar_decisiones(sin_variantes, [marca])
    (aviso,) = [x for x in out.verificaciones if x.numero == 11 and "K-5" in x.marcas]
    assert aviso.severidad == "aviso" and "lo toman" not in aviso.mensaje


def test_a_reading_two_decided_variants_share_folds_with_each_variants_count():
    # R247 (Task 13 review, minor 9): an aviso both variants' readings say folds only once both
    # are decided, and the aviso gives each variant its value and its own count
    e = _con_variantes()
    k5 = _k5(e)
    comun = "estribos: un texto que puede ser de K-5 fuera de la pila bajo su sección («E#3@15»)"
    k5.avisos.append(comun)
    for v in k5.variantes:
        v.avisos.append(comun)
    e.decisiones = [Decision(marca="X", campo="estribos", valor=[], fecha=_now())]
    d15 = Decision(marca="K-5", campo="estribos", valor="E#3@10", para_muro_cm=15, actor="R",
                   fecha=_now())  # fmt: skip
    d20 = Decision(marca="K-5", campo="estribos", valor="E#3@20", para_muro_cm=20, actor="R",
                   fecha=_now())  # fmt: skip

    def decididos(ds):
        out = aplicar_decisiones(e, ds)
        suyos = [v for v in out.verificaciones if "K-5" in v.marcas]
        dudas = " ".join(v.mensaje for v in suyos if v.severidad != "aviso")
        return dudas, [v for v in suyos if v.numero == 11 and v.severidad == "aviso"]

    dudas, avisos = decididos([d15])
    assert comun in dudas and avisos == []  # the 20 cm variant has not been decided
    dudas, (aviso,) = decididos([d15, d20])
    assert comun not in dudas
    assert "K-5 (para muros de 15 cm):" in aviso.mensaje and "lo toman 1 de 2 colocaciones" in (
        aviso.mensaje
    )
    assert "K-5 (para muros de 20 cm):" in aviso.mensaje and "lo toman 0 de 2 colocaciones" in (
        aviso.mensaje
    )
    assert aviso.id == id_de_verificacion(
        11, "K-5", "", "avisos de lectura: decidido: estribos: muro 15: muro 20"
    )


def test_formwork_of_a_non_rectangular_section_is_its_contour():
    # R242: K-15A's L (2,300 cm², perimeter 2.30 m) is formed over its contour, not √area.
    from klave_engine.costing.formwork import _section_m

    det = _det(section_area_du2=0.0225, section_source="marcador_poligonal")
    e = _el("castillo", {"area_cm2": 2300.0, "perimetro_cm": 230.0}, fuente="medido")
    (escrita,), _ = escribir_en_detecciones([det], [e], 1.0)
    (a, b), origen = _section_m(escrita.properties, None, "K-15A", "castillo", (0.15, 0.2), 1.0)
    assert origen == "contorno" and 2 * (a + b) == pytest.approx(2.30)
    sin = _el("castillo", {"area_cm2": 2300.0}, fuente="medido")
    (escrita,), _ = escribir_en_detecciones([det], [sin], 1.0)
    assert "section_perimetro_du" not in escrita.properties
    assert _section_m(escrita.properties, None, "K-15A", "castillo", (0.15, 0.2), 1.0)[1] == (
        "área sin contorno"
    )


def test_a_saved_decision_leaves_the_scenario_marked_stale_until_the_recompute(tmp_path, data_dir):
    # R247 (Task 13 review): saving no longer deletes the recompute's scenario — while the
    # recompute runs, the last scenario (the one the derived budget is) is served, saying it is
    # behind, so its decisions never flicker away; a recompute makes it current again.
    root, control = _demo(tmp_path)
    run_full_pipeline(root, get_settings())
    _recompute(root)
    assert (control / ESTRUCTURA_DERIVADA_FILENAME).exists()
    guardar_decision(
        control, Decision(marca="C-1", campo="seccion_cm", valor=[70, 70], fecha=_FECHA)
    )
    assert (control / ESTRUCTURA_DERIVADA_FILENAME).exists()
    vigente = leer_estructura_vigente(control, control)
    assert any("cambiaron desde este modelo" in a for a in vigente.avisos)
    assert vigente.decisiones == [] and vigente.base  # the scenario, behind
    _recompute(root)
    vigente = leer_estructura_vigente(control, control)
    assert not any("cambiaron desde este modelo" in a for a in vigente.avisos)
    ids = {x.detection_id for x in vigente.elementos if x.marca == "C-1"}
    assert ids <= {w.detection_id for w in vigente.escrituras}  # the recompute's own writes
    # removed by hand: the scenario that was costed (with C-1 decided) is still what the derived
    # budget is, and it says it is behind the saved decisions
    (control / DECISIONES_FILENAME).unlink()
    vigente = leer_estructura_vigente(control, control)
    assert any(x.seccion_cm.fuente == "humano" for x in vigente.elementos)
    assert any("cambiaron desde este modelo" in a for a in vigente.avisos)
    _recompute(root)
    vigente = leer_estructura_vigente(control, control)
    assert not any(x.seccion_cm.fuente == "humano" for x in vigente.elementos)
    assert not any("cambiaron desde este modelo" in a for a in vigente.avisos)


def test_an_unreadable_decisions_file_is_never_written_over(tmp_path):
    # R245: a torn or non-list decisions file would lose every decision it holds if a save or an
    # undo wrote over it; both refuse, and the file stays byte for byte
    from klave_engine.estructura.modelo import (
        DecisionesIlegibles,
        problema_de_decisiones,
        quitar_decision,
    )

    d = Decision(marca="K-5", campo="seccion_cm", valor=[20, 40], fecha=_FECHA)
    assert problema_de_decisiones(tmp_path) is None
    for roto in ("[{", '{"marca": "K-5"}'):
        (tmp_path / DECISIONES_FILENAME).write_text(roto)
        assert problema_de_decisiones(tmp_path)
        with pytest.raises(DecisionesIlegibles):
            guardar_decision(tmp_path, d)
        with pytest.raises(DecisionesIlegibles):
            quitar_decision(tmp_path, "K-5", "seccion_cm")
        assert (tmp_path / DECISIONES_FILENAME).read_text() == roto
    # one unreadable entry is no unreadable file: it is kept and the rest is read
    write_json(tmp_path / DECISIONES_FILENAME, [{"marca": "K-1"}])
    assert problema_de_decisiones(tmp_path) is None
    guardar_decision(tmp_path, d)
    assert read_json(tmp_path / DECISIONES_FILENAME)[0] == {"marca": "K-1"}


def test_decisions_key_on_the_normalized_mark():
    from klave_engine.estructura.modelo import _vigentes

    ds = [
        Decision(marca="K5", campo="seccion_cm", valor=[20, 30], fecha=_FECHA),
        Decision(marca="K-5", campo="seccion_cm", valor=[20, 40], fecha=_FECHA.replace(hour=13)),
    ]
    assert [d.valor for d in _vigentes(ds, TextPatternConfig())] == [[20, 40]]


def test_an_assumed_side_the_cuadro_stamped_is_corrected_too():
    # apply_schedule stamps a section with an assumed side as «supuesto»: the model may correct it.
    det = _det(section_cm="15x30", section_source="supuesto", spec_source="cuadro")
    salida, escritas = escribir_en_detecciones([det], [_el("castillo", [15, 20], "supuesto")], 1.0)
    assert salida[0].properties["section_cm"] == "15x20" and escritas


def test_a_pile_length_written_twice_keeps_what_the_detector_had():
    pila = make_detection("p1", DetectionType.pile, "P-4", (0, 0, 1, 1), 0.9, [], "t", [], {})
    pila.mark, pila.family = "P-4", "pilote"
    largo = _el("pilote", None, detection_id="p1", marca="P-4",
                longitud_m=Dato(valor=18.0, fuente="humano", texto="d"))  # fmt: skip
    (una,), _ = escribir_en_detecciones([pila], [largo], 1.0)
    otro = largo.model_copy(update={"longitud_m": Dato(valor=20.0, fuente="humano", texto="d")})
    (dos,), _ = escribir_en_detecciones([una], [otro], 1.0)
    assert dos.properties["longitud_m"] == 20.0
    assert dos.properties["longitud_previa"] == {"longitud_m": None}


def test_a_non_rectangular_placement_carries_its_contours_perimeter():
    # R142 + R242: the element's measured L section keeps its contour's perimeter (cm).
    from klave_engine.estructura.elementos import _contorno_no_rectangular

    det = _det(
        contorno_area_du2=0.23, contorno_rectangular=False, contorno_capa="EST-CASTILLOS",
        contorno_perimetro_du=2.30,
    )  # fmt: skip
    dato = _contorno_no_rectangular(det, "castillo", 1.0)
    assert dato is not None and dato.valor == {"area_cm2": 2300.0, "perimetro_cm": 230.0}


# ------------------------------------------------- Tarea 13: revisar una decisión y quitarla


def _como(e, familia):
    """K-5 vuelta otra familia (definición y colocaciones)."""
    e.definiciones = [d.model_copy(update={"familia": familia}) for d in e.definiciones]
    e.elementos = [x.model_copy(update={"familia": familia}) for x in e.elementos]
    return e


def _como_zapata(e):
    """Una zapata: una familia que no lee estribos ni longitud."""
    return _como(e, "zapata")


@pytest.mark.parametrize(
    ("hacer", "decision", "motivo"),
    [
        (lambda: _estructura_k5_conflict(niveles=True), dict(marca="K-5", campo="longitud_m",
         valor=3.2), "la altura de un castillo se decide por entrepiso (pendiente)"),
        (lambda: _como(_estructura_k5_conflict(niveles=True), "columna"), dict(marca="K-5",
         campo="longitud_m", valor=3.2), "la altura de una columna se decide por entrepiso"),
        (lambda: _estructura_k5_conflict(niveles=True), dict(marca="K-5", campo="seccion_cm",
         valor=[20]), "la sección no es b×h en cm"),
        (lambda: _estructura_k5_conflict(niveles=True), dict(marca="K-5", campo="seccion_cm",
         valor=["nan", 40]), "la sección no es b×h en cm"),
        (lambda: _estructura_k5_conflict(niveles=True), dict(marca="K-5", campo="longitud_m",
         valor="inf"), "la longitud no es un número positivo de metros"),
        (lambda: _estructura_k5_conflict(niveles=True), dict(marca="K-5", campo="longitud_m",
         valor=500), "la longitud 500 m está fuera de lo que mide un elemento"),
        (lambda: _estructura_k5_conflict(niveles=True), dict(marca="K-5", campo="seccion_cm",
         valor=[float("nan"), 40]), "un número que no es finito"),
        (lambda: _estructura_k5_conflict(niveles=True), dict(marca="K-5", campo="seccion_cm",
         valor={"area_cm2": float("inf")}), "un número que no es finito"),
        (lambda: _estructura_k5_conflict(niveles=True), dict(marca="K-5", campo="seccion_cm",
         valor=[20, 4000]), "fuera de lo que mide un elemento"),
        (lambda: _estructura_k5_conflict(niveles=True), dict(marca="K-5", campo="seccion_cm",
         valor={"area_cm2": 5e6}), "fuera de lo que mide un elemento"),
        (lambda: _estructura_k5_conflict(niveles=True), dict(marca="K-5", campo="seccion_cm",
         valor=[20, 40], para_muro_cm=15), "la marca no tiene variantes por muro"),
        (_con_variantes, dict(marca="K-5", campo="seccion_cm", valor=[20, 40], para_muro_cm=30),
         "K-5 no tiene una variante para muros de 30 cm"),
        (lambda: _como_zapata(_estructura_k5_conflict(niveles=True)), dict(marca="K-5",
         campo="estribos", valor="E#3@15"), "el modelo no lee los estribos de una zapata"),
        (lambda: _como_zapata(_estructura_k5_conflict(niveles=True)), dict(marca="K-5",
         campo="longitud_m", valor=2.0), "el modelo no lee la longitud de una zapata"),
        # R244: a parrilla's spacing and bar, as text or as pieces, through the same bound
        (lambda: _como_zapata(_estructura_k5_conflict(niveles=True)), dict(marca="K-5",
         campo="parrillas", valor=[{"numero": "4", "separacion_m": 0, "lecho": "inf",
         "sentidos": "ambos"}]), "una parrilla sin separación no es un armado"),
        (lambda: _como_zapata(_estructura_k5_conflict(niveles=True)), dict(marca="K-5",
         campo="parrillas", valor=[{"numero": "4", "separacion_m": 0.01, "lecho": "inf",
         "sentidos": "ambos"}]), "la separación de la parrilla (0.01 m)"),
        (lambda: _como_zapata(_estructura_k5_conflict(niveles=True)), dict(marca="K-5",
         campo="parrillas", valor=[{"numero": "9", "separacion_m": 0.2, "lecho": "inf",
         "sentidos": "ambos"}]), "no hay varilla del #9"),
        (lambda: _como_zapata(_estructura_k5_conflict(niveles=True)), dict(marca="K-5",
         campo="parrillas", valor=[]), "una decisión sin parrillas no se toma"),
        (lambda: _estructura_k5_conflict(niveles=True), dict(marca="K-5", campo="estribos",
         valor=[{"tipo": "estribo", "cantidad": 1, "numero": "3", "zonas": [{"tramo": "extremos",
         "separacion_m": 0.1, "longitud_m": 0}]}]), "no es un tramo de elemento"),
        (lambda: _estructura_k5_conflict(niveles=True), dict(marca="K-5", campo="estribos",
         valor=[{"tipo": "estribo", "cantidad": 1, "numero": "3", "zonas": [{"tramo": "todo",
         "separacion_m": 3.0}]}]), "la separación de los estribos (3 m)"),
    ],
)  # fmt: skip
def test_a_refusal_before_saving_is_the_aviso_the_model_gives_when_applying(
    hacer, decision, motivo
):
    from klave_engine.estructura.modelo import revisar_decision

    e = hacer()
    d = Decision(**decision, fecha=_now())
    r = revisar_decision(e, d)
    assert r.rechazo is not None and motivo in r.rechazo and r.rechazo.endswith("; no se aplica")
    # the same words the model writes when the decision is in the file
    assert r.rechazo in aplicar_decisiones(e, [d]).avisos


def test_a_mark_the_reading_does_not_have_is_refused_before_it_is_saved():
    from klave_engine.estructura.modelo import revisar_decision

    e = _estructura_k5_conflict(niveles=True)
    d = Decision(marca="K-99", campo="seccion_cm", valor=[20, 40], actor="Ana", fecha=_now())
    r = revisar_decision(e, d)
    assert r.rechazo == (
        "Decisión sobre K-99 (sección, Ana): la marca no está en esta lectura (ni definida ni "
        "colocada); no se guarda"
    )
    # once saved (an older reading had it), it is kept and said, never applied
    assert any(
        a.startswith("Decisión sobre K-99 (sección, Ana): la marca ya no está")
        and a.endswith("se conserva y no se aplica")
        for a in aplicar_decisiones(e, [d]).avisos
    )


def test_what_a_decision_replaces_and_whether_it_needs_a_note():
    from klave_engine.estructura.modelo import revisar_decision

    e = _estructura_k5_conflict(niveles=True)
    d = Decision(marca="K5", campo="seccion_cm", valor="20x45", fecha=_now())
    r = revisar_decision(e, d)
    assert r.rechazo is None and r.marca == "K-5" and r.valor == [20, 45]
    assert r.antes is not None and r.antes.fuente == "cuadro" and r.antes.en_conflicto
    assert {(tuple(x.valor), x.fuente, x.hoja) for x in r.del_plano} == {
        ((20, 30), "cuadro", "ES-200"),
        ((20, 40), "cuadro", "ES-400"),
    }
    assert all(not x.alternativas for x in r.del_plano)
    assert "20x30 cm (cuadro, ES-200)" in r.nota_requerida
    assert "20x40 cm (cuadro, ES-400)" in r.nota_requerida
    # under an earlier decision the drawing still says what it says
    decidida = aplicar_decisiones(
        e, [Decision(marca="K-5", campo="seccion_cm", valor=[20, 40], nota="PA", fecha=_now())]
    )
    r = revisar_decision(decidida, d)
    assert r.antes.fuente == "humano" and r.antes.valor == [20, 40]
    assert {tuple(x.valor) for x in r.del_plano} >= {(20, 30), (20, 40)}
    # what Klave supposed is no drawing value: no note
    d9 = Decision(marca="K-9", campo="seccion_cm", valor=[20, 20], fecha=_now())
    r9 = revisar_decision(_estructura_k5_conflict(con_k9=True, niveles=True), d9)
    assert r9.rechazo is None and r9.del_plano == [] and r9.nota_requerida is None


def test_an_unread_text_is_not_a_drawing_value_to_override():
    from klave_engine.estructura.modelo import revisar_decision

    e = _estructura_k5_conflict(niveles=True)
    k5 = _k5(e)
    sin_leer = Dato(fuente="detalle", ilegible=True, texto="sección dibujada no encontrada")
    k5.seccion_cm = Dato(valor=[20, 20], fuente="supuesto", texto="s", alternativas=[sin_leer])
    e.elementos = [x.model_copy(update={"seccion_cm": k5.seccion_cm}) for x in e.elementos]
    r = revisar_decision(e, Decision(marca="K-5", campo="seccion_cm", valor=[20, 40], fecha=_now()))
    assert r.rechazo is None and r.del_plano == [] and r.nota_requerida is None
    # a readable one deep in the alternatives is
    leido = Dato(valor=[20, 30], fuente="seccion_dibujada", hoja="ES-200", texto="d")
    k5.seccion_cm = k5.seccion_cm.model_copy(
        update={"alternativas": [sin_leer.model_copy(update={"alternativas": [leido]})]}
    )
    r = revisar_decision(e, Decision(marca="K-5", campo="seccion_cm", valor=[20, 40], fecha=_now()))
    assert [tuple(x.valor) for x in r.del_plano] == [(20, 30)]
    # the source in words, as the office says it
    assert "el plano dice 20x30 cm (sección dibujada, ES-200)." in r.nota_requerida


def test_a_variant_decision_replaces_only_that_variant_and_its_placements():
    from klave_engine.estructura.modelo import revisar_decision

    e = _con_variantes()
    quince = Decision(marca="K-5", campo="seccion_cm", valor=[15, 25], para_muro_cm=15,
                      fecha=_now())  # fmt: skip
    r = revisar_decision(e, quince)
    assert r.antes.valor == [15, 20] and {tuple(x.valor) for x in r.del_plano} == {(15, 20)}
    marca = Decision(marca="K-5", campo="seccion_cm", valor=[25, 25], fecha=_now())
    r = revisar_decision(e, marca)
    # the mark's part: its merged definition and d2 (unresolved); d1 keeps its 15 cm variant, so
    # its 15x20 is not what this decision replaces
    assert r.antes == _k5(e).seccion_cm
    assert {tuple(x.valor) for x in r.del_plano} == {(20, 30), (20, 40)}


def test_undo_removes_a_decision_as_it_was_written_and_keeps_what_does_not_read(tmp_path):
    from klave_engine.estructura.modelo import quitar_decision

    guardar_decision(tmp_path, Decision(marca="K-5", campo="seccion_cm", valor=[20, 40],
                                        fecha=_FECHA))  # fmt: skip
    guardar_decision(tmp_path, Decision(marca="CI", campo="seccion_cm", valor=[15, 25],
                                        para_muro_cm=15, fecha=_FECHA))  # fmt: skip
    guardar_decision(tmp_path, Decision(marca="CI", campo="seccion_cm", valor=[25, 25],
                                        fecha=_FECHA))  # fmt: skip
    write_json(tmp_path / DECISIONES_FILENAME,
               [*read_json(tmp_path / DECISIONES_FILENAME), {"marca": "K-5"}])  # fmt: skip
    (tmp_path / ESTRUCTURA_DERIVADA_FILENAME).write_text("{}")
    assert quitar_decision(tmp_path, "K-5", "estribos") == []
    (quitada,) = quitar_decision(tmp_path, "k5", "seccion_cm")
    assert quitada.valor == [20, 40]
    # R247: the scenario stays (it says it is behind) until the recompute makes it again
    assert (tmp_path / ESTRUCTURA_DERIVADA_FILENAME).read_text() == "{}"
    # the variant's decision and the mark's are different keys
    (quitada,) = quitar_decision(tmp_path, "CI", "seccion_cm", 15.0)
    assert quitada.para_muro_cm == 15.0
    restantes = read_json(tmp_path / DECISIONES_FILENAME)
    assert [(c.get("marca"), c.get("para_muro_cm")) for c in restantes] == [
        ("CI", None), ("K-5", None),
    ]  # fmt: skip
    assert restantes[1] == {"marca": "K-5"}  # the unreadable entry is kept as it was
    # a mark the project's own tags write another way («MX1» is MX-1 for this project)
    proyecto = TextPatternConfig(column_tag=[r"^MX\d$"], beam_tag=[])
    guardar_decision(tmp_path, Decision(marca="MX1", campo="estribos", valor="E#3@15",
                                        fecha=_FECHA))  # fmt: skip
    assert quitar_decision(tmp_path, "MX-1", "estribos") == []
    (quitada,) = quitar_decision(tmp_path, "MX-1", "estribos", config=proyecto)
    assert quitada.marca == "MX1"
    # and the other way: saved as MX-1, asked for as the project writes it
    guardar_decision(tmp_path, Decision(marca="MX-1", campo="estribos", valor="E#3@15",
                                        fecha=_FECHA))  # fmt: skip
    assert quitar_decision(tmp_path, "MX1", "estribos") == []
    (quitada,) = quitar_decision(tmp_path, "MX1", "estribos", config=proyecto)
    assert quitada.marca == "MX-1"
    assert quitar_decision(tmp_path / "otra", "CI", "seccion_cm") == []


def test_the_current_decisions_are_one_per_mark_field_and_variant():
    from klave_engine.estructura.modelo import decisiones_vigentes

    a = Decision(marca="K-5", campo="seccion_cm", valor=[20, 30], fecha=_FECHA)
    b = Decision(marca="K5", campo="seccion_cm", valor=[20, 40],
                 fecha=_FECHA.replace(hour=13))  # fmt: skip
    c = Decision(marca="K-5", campo="seccion_cm", valor=[15, 20], para_muro_cm=15, fecha=_FECHA)
    assert decisiones_vigentes([a, b, c], TextPatternConfig()) == [b, c]
