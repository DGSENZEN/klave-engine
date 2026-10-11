"""Tarea 9: los elementos — cada colocación de una planta estructural con su definición y sus
reglas, campo por campo y con su fuente; lo que no llega a elemento, con su motivo."""

import pytest
from klave_engine.costing.models import CostingAssumptions
from klave_engine.costing.referencias import element_id
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.views import SheetSegmentation, ViewKind, ViewRegion
from klave_engine.estructura.armado import GrupoVarillas, JuegoEstribos, Zona
from klave_engine.estructura.dato import Dato, elegir
from klave_engine.estructura.definiciones import Definicion
from klave_engine.estructura.elementos import (
    FAMILIAS_ESTRUCTURALES,
    SECCION_SUPUESTA_CM,
    Elemento,
    construir_elementos,
    excluidas,
    resolver,
)
from klave_engine.estructura.reglas import RECUBRIMIENTO_SUPUESTO, reglas_estandar

_TIPO = {
    "castillo": DetectionType.column_tag,
    "columna": DetectionType.column_tag,
    "trabe": DetectionType.beam_tag,
    "contratrabe": DetectionType.beam_tag,
    "dala": DetectionType.beam_tag,
    "cerramiento": DetectionType.beam_tag,
    "zapata": DetectionType.footing,
    "pilote": DetectionType.pile,
    "muro_concreto": DetectionType.wall,
}
_N = iter(range(1, 10_000))


def _tag(marca, familia="castillo", x=0.0, y=0.0, role=None, **props):
    det_id = f"det_{next(_N):06d}"
    if role is not None:
        props["role"] = role
    det = make_detection(
        det_id, _TIPO[familia], marca or familia, (x, y, x + 0.2, y + 0.1), 0.9,
        ["ent_t"], "t", [], props, "a.dxf",
    )  # fmt: skip
    det.mark = marca
    det.family = familia
    return det


def _seg(asignacion, plan=("v_pa",), detalle=("v_det",), niveles=None, otra_hoja=()):
    """Una segmentación con vistas reales: ``niveles`` da el N.P.T. de cada planta, para que
    ``story_heights`` corra como en producción (nunca se parcha)."""
    niveles = niveles or {}
    vistas = [
        ViewRegion(view_id=v, title=f"{v} · PLANTA", kind=ViewKind.plan, level_key="planta",
                   npt_level=niveles.get(v), anchor=(0, 0))
        for v in plan
    ] + [
        ViewRegion(view_id=v, title=f"{v} · DETALLES", kind=ViewKind.excluded, anchor=(0, 0))
        for v in detalle
    ] + [
        ViewRegion(view_id=v, title=f"{v} · PLANTA ALUMINIO", kind=ViewKind.plan,
                   level_key="planta", anchor=(0, 0), structural=False)
        for v in otra_hoja
    ]  # fmt: skip
    return SheetSegmentation(views=vistas, assignment=asignacion, is_segmented=True)


def _seccion(valor, fuente="detalle", hoja="ES-200", **kw):
    return Dato(valor=valor, fuente=fuente, hoja=hoja, texto=f"{valor}", **kw)


def _def(marca, familia="castillo", seccion=(15, 20), **campos):
    datos = {"seccion_cm": _seccion(seccion) if isinstance(seccion, tuple) else seccion}
    datos.update(campos)
    return Definicion(marca=marca, familia=familia, **datos)


def _defs(*marcas, **kw):
    return {m: _def(m, **kw) for m in marcas}


def _nota_dala():
    return Definicion(
        marca="DALA",
        familia="dala",
        seccion_cm=Dato(valor=(15, 25), fuente="nota", hoja="ES-000",
                        texto="CADENA DE ENRASE 15x25 4#3 E#2@15"),
        longitudinales=Dato(valor=[GrupoVarillas(cantidad=4, numero="3")], fuente="nota",
                            hoja="ES-000", texto="CADENA DE ENRASE 15x25 4#3 E#2@15"),
        estribos=Dato(
            valor=[JuegoEstribos(tipo="estribo", cantidad=1, numero="2",
                                 zonas=[Zona(tramo="todo", separacion_m=0.15)])],
            fuente="nota", hoja="ES-000", texto="CADENA DE ENRASE 15x25 4#3 E#2@15",
        ),
    )  # fmt: skip


def _construir(dets, seg=None, por_marca=None, por_familia=None, reglas=None, factor=1.0, **kw):
    return construir_elementos(
        dets, seg, por_marca or {}, por_familia or {}, reglas or reglas_estandar(), factor, 2.7,
        **kw,
    )  # fmt: skip


# ----------------------------------------------------------------------- el plan (brief)


def test_only_structural_plan_placements():
    en_planta, en_detalle, de_cuadro = _tag("K-4"), _tag("K-4"), _tag("K-4", role="cuadro")
    dets = [en_planta, en_detalle, de_cuadro]
    seg = _seg({en_planta.detection_id: "v_pa", en_detalle.detection_id: "v_det",
                de_cuadro.detection_id: "v_pa"})  # fmt: skip
    els = _construir(dets, seg, _defs("K-4"))
    assert len(els) == 1 and els[0].vista == "v_pa"
    assert els[0].detection_id == en_planta.detection_id


def test_join_exact_and_family_fallback_flagged():
    a, b = _tag("K-4"), _tag("K-99")
    seg = _seg({a.detection_id: "v_pa", b.detection_id: "v_pa"})
    familia = Definicion(
        marca="CASTILLO",
        familia="castillo",
        seccion_cm=Dato(valor=(15, 15), fuente="nota", texto="CASTILLO 15X15"),
    )
    els = _construir([a, b], seg, _defs("K-4"), {"castillo": familia})
    by = {e.marca: e for e in els}
    assert by["K-4"].definicion == "marca" and by["K-99"].definicion == "familia"
    assert by["K-99"].seccion_cm.valor == (15, 15) and by["K-99"].seccion_cm.fuente == "nota"
    # El respaldo nunca calla que la marca no está definida (chequeo 1).
    assert any("K-99 no está definida" in a for a in by["K-99"].avisos)
    assert not any("no está definida" in a for a in by["K-4"].avisos)


def test_height_from_levels_else_supuesto():
    k = _tag("K-4")
    seg = _seg({k.detection_id: "v_pa"}, plan=("v_pa", "v_az"),
               niveles={"v_pa": 0.0, "v_az": 2.9})  # fmt: skip
    e = _construir([k], seg, _defs("K-4"))[0]
    assert (e.altura_m.valor, e.altura_m.fuente) == (2.9, "nota")
    e2 = _construir([k], _seg({k.detection_id: "v_pa"}), _defs("K-4"))[0]
    assert (e2.altura_m.valor, e2.altura_m.fuente) == (2.7, "supuesto")


def _reglas_marina():
    reglas = reglas_estandar()
    cubre = dict(reglas.recubrimiento_m)
    cubre["castillo"] = Dato(valor=0.03, fuente="nota", hoja="ES-000",
                             texto="RECUBRIMIENTO LIBRE EN CASTILLOS 3 CM")  # fmt: skip
    return reglas.model_copy(update={"recubrimiento_m": cubre})


def test_cover_by_family_from_rules():
    k = _tag("K-4")
    e = _construir([k], _seg({k.detection_id: "v_pa"}), _defs("K-4"), reglas=_reglas_marina())[0]
    assert (e.recubrimiento_m.valor, e.recubrimiento_m.fuente) == (0.03, "nota")


def test_no_units_no_crash():
    k, t = _tag("K-4"), _tag("T-1", "trabe", estimated_span_length=4.0)
    seg = _seg({k.detection_id: "v_pa", t.detection_id: "v_pa"})
    els = _construir([k, t], seg, _defs("K-4"), factor=None)
    assert len(els) == 2
    viga = next(e for e in els if e.marca == "T-1")
    assert viga.longitud_m is None
    assert any("sin unidades" in a for a in viga.avisos)


# --------------------------------------------------------------------- R70, R71: nada se tira


def test_an_unmarked_placement_is_an_element_never_dropped():
    # R70 (Marina: 38 zapatas —los dados— y 4 muros de concreto sin marca).
    z, m = _tag("", "zapata", rectangularity=1.0), _tag("", "muro_concreto", estimated_length=6.0)
    k = _tag("", "dala", x=3.0, estimated_span_length=4.0)
    seg = _seg({d.detection_id: "v_pa" for d in (z, m, k)})
    els = _construir([z, m, k], seg, {}, {"dala": _nota_dala()})
    assert sorted((e.familia, e.marca, e.definicion) for e in els) == [
        ("dala", "", "familia"), ("muro_concreto", "", "ninguna"), ("zapata", "", "ninguna"),
    ]  # fmt: skip
    for e in els:
        assert any(a.startswith("sin marca") for a in e.avisos)
        assert not any("no está definida" in a for a in e.avisos)
    dala = next(e for e in els if e.familia == "dala")
    assert dala.seccion_cm.valor == (15, 25) and dala.longitudinales.fuente == "nota"
    zapata = next(e for e in els if e.familia == "zapata")
    # El contorno rectangular de la zapata es su medida en planta (0.2 × 0.1 de dibujo, en m).
    assert (zapata.seccion_cm.valor, zapata.seccion_cm.fuente) == ((10.0, 20.0), "medido")
    muro = next(e for e in els if e.familia == "muro_concreto")
    assert (muro.longitud_m.valor, muro.longitud_m.fuente) == (6.0, "medido")
    assert muro.seccion_cm is None and any("sin sección" in a for a in muro.avisos)


def test_every_structural_detection_not_placed_is_excluded_with_its_reason():
    # R71: cada detección de una familia estructural es un elemento o una excluida con su motivo.
    colocada = _tag("K-4")
    cuadro = _tag("K-4", role="cuadro")
    detalle = _tag("T-1", "trabe")
    aluminio = _tag("K-4")
    perdida = _tag("K-4")
    eje = make_detection("det_eje", DetectionType.grid_line, "A", (0, 0, 1, 1), 0.9, [], "t", [])
    eje.family = "eje"
    dets = [colocada, cuadro, detalle, aluminio, perdida, eje]
    seg = _seg(
        {colocada.detection_id: "v_pa", cuadro.detection_id: "v_pa",
         detalle.detection_id: "v_det", aluminio.detection_id: "v_can", "det_eje": "v_pa"},
        otra_hoja=("v_can",),
    )  # fmt: skip
    els = _construir(dets, seg, _defs("K-4"))
    fuera = excluidas(dets, seg)
    assert [e.detection_id for e in els] == [colocada.detection_id]
    assert sorted((x.detection_id, x.motivo) for x in fuera) == sorted([
        (cuadro.detection_id, "cuadro"),
        (detalle.detection_id, "vista_excluida"),
        (aluminio.detection_id, "planta_no_estructural"),
        (perdida.detection_id, "sin_vista"),
    ])  # fmt: skip
    estructurales = [d for d in dets if d.family in FAMILIAS_ESTRUCTURALES]
    assert len(els) + len(fuera) == len(estructurales)
    assert all(x.texto for x in fuera)


def test_without_segmentation_the_whole_drawing_is_one_planta():
    k, c = _tag("K-4"), _tag("K-4", role="cuadro")
    sin_planta = SheetSegmentation(views=[], assignment={}, is_segmented=False)
    for seg in (None, sin_planta):
        els = _construir([k, c], seg, _defs("K-4"))
        assert [(e.detection_id, e.vista) for e in els] == [(k.detection_id, None)]
        assert [x.motivo for x in excluidas([k, c], seg)] == ["cuadro"]


# --------------------------------------------------------------------------- la llave


@pytest.mark.parametrize("escrita", ["K-4", "K4", "k-4", "K 4"])
def test_the_join_is_by_normalised_mark_on_both_sides(escrita):
    k = _tag(escrita)
    (e,) = _construir([k], _seg({k.detection_id: "v_pa"}), _defs("K-4"))
    assert (e.marca, e.definicion) == ("K-4", "marca")


def test_no_prefix_matching():
    # K-15A no es K-15A.1, ni K-1 es K-15A.
    a, b = _tag("K-15A"), _tag("K-1")
    seg = _seg({a.detection_id: "v_pa", b.detection_id: "v_pa"})
    els = _construir([a, b], seg, _defs("K-15A.1", "K-15"))
    assert {e.marca: e.definicion for e in els} == {"K-15A": "ninguna", "K-1": "ninguna"}


def test_the_element_id_is_the_stable_one():
    k = _tag("K-4", x=12.0, y=7.0)
    (e,) = _construir([k], _seg({k.detection_id: "v_pa"}), _defs("K-4"), factor=1.0)
    assert e.element_id == element_id(k, 1.0)


# ---------------------------------------------------------------- R72: cada hoja manda en lo suyo


_MARCOS = [
    SheetFrame(frame_id="f200", bbox=(0, 0, 100, 100), source_file="a.dxf", code="ES-200"),
    SheetFrame(frame_id="f400", bbox=(200, 0, 300, 100), source_file="a.dxf", code="ES-400"),
]


def _seg_marcos(asignacion):
    vistas = [
        ViewRegion(view_id=f.frame_id, title=f"{f.code} · PLANTA", kind=ViewKind.plan,
                   level_key="planta", anchor=(0, 0), bbox=f.bbox)
        for f in _MARCOS
    ]  # fmt: skip
    return SheetSegmentation(views=vistas, assignment=asignacion, is_segmented=True)


def test_each_element_takes_its_own_sheets_reading():
    # Una marca que dos hojas definen distinto: cada colocación toma la de su hoja; la otra queda
    # como alternativa, sin conflicto (el conflicto del plano lo dice la definición).
    seccion = elegir([_seccion((20, 40), hoja="ES-200"), _seccion((20, 30), hoja="ES-400")])
    assert seccion.en_conflicto
    defs = {"K-9": _def("K-9", seccion=seccion)}
    en_200, en_400 = _tag("K-9", x=10, y=10), _tag("K-9", x=210, y=10)
    seg = _seg_marcos({en_200.detection_id: "f200", en_400.detection_id: "f400"})
    els = {e.hoja: e for e in _construir([en_200, en_400], seg, defs, frames=_MARCOS)}
    assert els["ES-200"].seccion_cm.valor == (20, 40)
    assert els["ES-400"].seccion_cm.valor == (20, 30)
    for e in els.values():
        assert not e.seccion_cm.en_conflicto
        assert {tuple(a.valor) for a in e.seccion_cm.alternativas} == {(20, 40), (20, 30)} - {
            tuple(e.seccion_cm.valor)
        }


def test_each_element_takes_its_own_sheets_rules():
    reglas = reglas_estandar()
    cubre = dict(reglas.recubrimiento_m)
    cubre["castillo"] = elegir([
        Dato(valor=0.03, fuente="nota", hoja="ES-200", texto="RECUBRIMIENTO 3 CM"),
        Dato(valor=0.025, fuente="nota", hoja="ES-400", texto="RECUBRIMIENTO 2.5 CM"),
    ])  # fmt: skip
    reglas = reglas.model_copy(update={"recubrimiento_m": cubre})
    en_200, en_400 = _tag("K-9", x=10, y=10), _tag("K-9", x=210, y=10)
    seg = _seg_marcos({en_200.detection_id: "f200", en_400.detection_id: "f400"})
    els = _construir([en_200, en_400], seg, _defs("K-9"), reglas=reglas, frames=_MARCOS)
    assert {e.hoja: e.recubrimiento_m.valor for e in els} == {"ES-200": 0.03, "ES-400": 0.025}


def test_the_sheet_is_the_frames_code_else_the_file():
    k = _tag("K-9", x=210, y=10)
    (e,) = _construir([k], None, _defs("K-9"), frames=_MARCOS)
    assert e.hoja == "ES-400"
    (sin,) = _construir([k], None, _defs("K-9"))
    assert sin.hoja == "a.dxf"


# ------------------------------------------------------------------------- R73: la altura


def test_the_top_planta_repeats_the_one_below_as_supuesto():
    abajo, arriba = _tag("K-4"), _tag("K-4", x=5.0)
    seg = _seg({abajo.detection_id: "v_pb", arriba.detection_id: "v_az"},
               plan=("v_pb", "v_az"), niveles={"v_pb": 1.45, "v_az": 4.35})  # fmt: skip
    els = {e.vista: e for e in _construir([abajo, arriba], seg, _defs("K-4"))}
    pb, az = els["v_pb"].altura_m, els["v_az"].altura_m
    assert (pb.valor, pb.fuente) == (2.9, "nota")
    assert "+1.45" in pb.texto and "+4.35" in pb.texto
    assert (az.valor, az.fuente) == (2.9, "supuesto")
    assert "repite" in az.texto


def test_only_castillos_and_columnas_take_a_storey_height():
    t = _tag("T-1", "trabe", estimated_span_length=4.0)
    seg = _seg({t.detection_id: "v_pa"}, plan=("v_pa", "v_az"), niveles={"v_pa": 0.0, "v_az": 3.0})
    (e,) = _construir([t], seg, _defs("T-1", familia="trabe", seccion=(25, 50)))
    assert e.altura_m is None


# ------------------------------------------------------------------- la longitud de las vigas


def test_a_beam_length_is_its_measured_span():
    t = _tag("T-1", "trabe", estimated_span_length=450.0)
    (e,) = _construir(
        [t], _seg({t.detection_id: "v_pa"}), _defs("T-1", familia="trabe", seccion=(25, 50)),
        factor=0.01,
    )  # fmt: skip
    assert (e.longitud_m.valor, e.longitud_m.fuente) == (4.5, "medido")


def test_a_beam_without_a_span_has_no_length_never_zero():
    t = _tag("T-1", "trabe")
    (e,) = _construir(
        [t], _seg({t.detection_id: "v_pa"}), _defs("T-1", familia="trabe", seccion=(25, 50))
    )
    assert e.longitud_m is None
    assert any(a.startswith("longitud:") for a in e.avisos)


def test_a_doubtful_span_says_so_on_the_element():
    t = _tag("CE-1", "dala", estimated_span_length=14.9,
             claro_dudoso="claro dudoso: 2 líneas igual de cerca de la etiqueta, de largos 9.1, "
                          "14.9; se toma la de 14.9, la de punto medio más cercano")  # fmt: skip
    (e,) = _construir([t], _seg({t.detection_id: "v_pa"}), {}, {"dala": _nota_dala()})
    assert e.longitud_m.valor == 14.9
    assert any(a.startswith("claro dudoso:") for a in e.avisos)


# --------------------------------------------------------- la sección: R113, R134, lo medido


def _ilegible(texto="CE-5 · señalada por flecha; se lee en E3"):
    return Dato(valor=None, fuente="detalle", hoja="ES-500", texto=texto, ilegible=True)


def test_an_unread_drawn_section_falls_back_to_the_family_note_as_supuesto():
    # R134 (CE-5 en Marina): su sección está dibujada y señalada por flecha, nadie la leyó; la
    # nota «CADENA DE ENRASE 15x25» es su respaldo, como supuesto, con aviso y duda; la ilegible
    # queda como alternativa. Nunca el genérico «si el plano no la declara».
    ce5 = _tag("CE-5", "dala", estimated_span_length=4.0)
    defs = {"CE-5": _def("CE-5", familia="dala", seccion=_ilegible())}
    (e,) = _construir([ce5], _seg({ce5.detection_id: "v_pa"}), defs, {"dala": _nota_dala()})
    s = e.seccion_cm
    assert (s.valor, s.fuente) == ((15, 25), "supuesto")
    assert any(a.ilegible for a in s.alternativas)
    assert any("la sección propia está dibujada y no se leyó; se usa la nota de familia" in a
               for a in e.avisos)  # fmt: skip
    assert e.dudas and "CE-5" in e.dudas[0]
    assert not any("no la declara" in a for a in e.avisos)
    # Sin armado propio, el de la nota de la familia, supuesto y dicho.
    assert (e.longitudinales.fuente, e.estribos.fuente) == ("supuesto", "supuesto")
    assert e.longitudinales.valor == _nota_dala().longitudinales.valor


def test_an_unread_drawn_section_without_a_note_takes_the_measure_then_the_default():
    # R113: sin nota de familia, la medida en planta (las cotas junto al castillo) y si no la
    # supuesta: siempre supuesto, «el plano la dibuja; no se leyó», con la ilegible como
    # alternativa.
    medido = _tag("K-7", section_source="cota", section_cm="20x15")
    pelado = _tag("K-7", x=5.0)
    defs = {"K-7": _def("K-7", seccion=_ilegible("K-7 · sección dibujada"))}
    seg = _seg({medido.detection_id: "v_pa", pelado.detection_id: "v_pa"})
    els = {e.detection_id: e for e in _construir([medido, pelado], seg, defs)}
    con, sin = els[medido.detection_id], els[pelado.detection_id]
    assert (con.seccion_cm.valor, con.seccion_cm.fuente) == ((15, 20), "supuesto")
    assert (sin.seccion_cm.valor, sin.seccion_cm.fuente) == (SECCION_SUPUESTA_CM["castillo"],
                                                             "supuesto")  # fmt: skip
    for e in (con, sin):
        assert any(a.startswith("sección: el plano la dibuja; no se leyó") for a in e.avisos)
        assert any(a.ilegible for a in e.seccion_cm.alternativas)
        assert e.dudas


def test_the_measured_section_comes_only_from_cotas_never_an_enclosing_block():
    # R133: la caja de un bloque (marcador_bbox) puede ser la del bloque que contiene al castillo;
    # nunca es su sección medida. La sección que ``apply_schedule`` copió del cuadro tampoco es
    # una medida.
    caja = _tag("K-0", section_source="marcador_bbox", section_area_du2=249.4)
    copia = _tag("K-0", x=5.0, section_source="cuadro", section_cm="25x25")
    cota = _tag("K-0", x=9.0, section_source="cota", section_cm="15x20")
    seg = _seg({d.detection_id: "v_pa" for d in (caja, copia, cota)})
    els = {e.detection_id: e for e in _construir([caja, copia, cota], seg)}
    assert els[caja.detection_id].seccion_cm.fuente == "supuesto"
    assert els[copia.detection_id].seccion_cm.fuente == "supuesto"
    assert (els[cota.detection_id].seccion_cm.valor,
            els[cota.detection_id].seccion_cm.fuente) == ((15, 20), "medido")  # fmt: skip


def test_the_drawings_section_outranks_the_measure_which_stays_an_alternative():
    k = _tag("K-4", section_source="cota", section_cm="20x20")
    (e,) = _construir([k], _seg({k.detection_id: "v_pa"}), _defs("K-4", seccion=(15, 20)))
    assert (e.seccion_cm.valor, e.seccion_cm.fuente) == ((15, 20), "detalle")
    assert [(tuple(a.valor), a.fuente) for a in e.seccion_cm.alternativas] == [((20, 20), "medido")]


def test_a_section_nobody_gives_is_the_familys_default_said_so():
    k = _tag("K-4")
    (e,) = _construir([k], _seg({k.detection_id: "v_pa"}), _defs("K-4", seccion=None))
    assert (e.seccion_cm.valor, e.seccion_cm.fuente) == ((15, 20), "supuesto")
    assert any("no la declara" in a for a in e.avisos)


def test_the_assumed_sections_are_the_costing_assumptions():
    a = CostingAssumptions()
    areas = {
        "castillo": a.castillo_section_m2, "columna": a.column_section_m2,
        "trabe": a.beam_section_m2, "contratrabe": a.contratrabe_section_m2,
        "dala": a.dala_section_m2, "cerramiento": a.dala_section_m2,
    }  # fmt: skip
    for familia, (b, h) in SECCION_SUPUESTA_CM.items():
        assert b * h / 10_000 == pytest.approx(areas[familia])


def test_an_ai_value_never_hides_a_family_fallback_need():
    # La IA de la marca sigue siendo lo que la definición eligió (R80): el elemento no la cambia
    # por la nota de la familia.
    ia = Dato(valor=[GrupoVarillas(cantidad=4, numero="3")], fuente="ia", texto="IA")
    defs = {"CE-1": _def("CE-1", familia="dala", seccion=_ilegible(), longitudinales=ia)}
    ce1 = _tag("CE-1", "dala", estimated_span_length=9.1)
    (e,) = _construir([ce1], _seg({ce1.detection_id: "v_pa"}), defs, {"dala": _nota_dala()})
    assert e.longitudinales.fuente == "ia"
    assert (e.seccion_cm.valor, e.seccion_cm.fuente) == ((15, 25), "supuesto")


# --------------------------------------------------------------------- el recubrimiento


def test_a_family_the_rules_lack_takes_the_standard_cover_as_supuesto():
    reglas = reglas_estandar()
    sin_columna = {f: d for f, d in reglas.recubrimiento_m.items() if f != "columna"}
    reglas = reglas.model_copy(update={"recubrimiento_m": sin_columna})
    c = _tag("C-1", "columna")
    (e,) = _construir([c], _seg({c.detection_id: "v_pa"}), _defs("C-1", familia="columna"),
                      reglas=reglas)  # fmt: skip
    assert (e.recubrimiento_m.valor, e.recubrimiento_m.fuente) == (
        RECUBRIMIENTO_SUPUESTO["columna"], "supuesto",
    )  # fmt: skip


# --------------------------------------------------------------------------- resolver


def test_resolver_rejoins_after_a_decision_and_keeps_the_placement():
    k = _tag("K-4", section_source="cota", section_cm="20x20")
    (e,) = _construir([k], _seg({k.detection_id: "v_pa"}), _defs("K-4"))
    decidida = _def("K-4", seccion=Dato(valor=(20, 30), fuente="humano", texto="Revisión"))
    nuevo = resolver(e, {"K-4": decidida}, {}, reglas_estandar())
    assert isinstance(nuevo, Elemento) and nuevo is not e
    assert (nuevo.seccion_cm.valor, nuevo.seccion_cm.fuente) == ((20, 30), "humano")
    assert nuevo.colocacion == e.colocacion
    assert e.seccion_cm.valor == (15, 20)  # el de antes no cambia
    # Resolver dos veces da lo mismo (los avisos no se acumulan).
    assert resolver(nuevo, {"K-4": decidida}, {}, reglas_estandar()) == nuevo


def _marcos_100_500():
    return [
        SheetFrame(frame_id="f100", bbox=(0, 0, 100, 100), source_file="a.dxf", code="ES-100"),
        SheetFrame(frame_id="f200", bbox=(200, 0, 300, 100), source_file="a.dxf", code="ES-200"),
    ]


def test_a_sheet_never_elects_the_ai_the_definition_blocked():
    # R69 por hoja (CE-1 en Marina): su sección está señalada por flecha en ES-500 (ilegible) y la
    # IA leyó 15x30 en ES-100. La definición no elige la IA; la colocación de ES-100 tampoco,
    # aunque la IA sea lo único que «dice» esa hoja: cae a la nota de la familia (R134) y la IA
    # queda como alternativa.
    seccion = elegir([
        Dato(valor=None, fuente="detalle", hoja="ES-500", ilegible=True,
             texto="CE-1 · señalada por flecha; se lee en E3"),
        Dato(valor=(15, 30), fuente="ia", hoja="ES-100", texto="IA · hoja ES-100"),
    ])  # fmt: skip
    assert seccion.ilegible
    defs = {"CE-1": _def("CE-1", familia="dala", seccion=seccion)}
    ce1 = _tag("CE-1", "dala", x=10, y=10, estimated_span_length=4.0)
    marcos = _marcos_100_500()
    (e,) = _construir([ce1], None, defs, {"dala": _nota_dala()}, frames=marcos)
    assert e.hoja == "ES-100"
    assert (e.seccion_cm.valor, e.seccion_cm.fuente) == ((15, 25), "supuesto")
    assert any(a.fuente == "ia" for a in e.seccion_cm.alternativas)
    # Sin nota de familia: la supuesta, nunca la IA.
    (sin_nota,) = _construir([ce1], None, defs, frames=marcos)
    assert (sin_nota.seccion_cm.valor, sin_nota.seccion_cm.fuente) == ((15, 25), "supuesto")
    assert any(a.fuente == "ia" for a in sin_nota.seccion_cm.alternativas)


def test_a_sheets_unreadable_copy_never_hides_what_another_sheet_read():
    # R76 por hoja: ES-100 leyó 20x30; la copia de ES-200 no se pudo leer. La colocación de
    # ES-200 usa 20x30 y lo dice; la ilegible queda como alternativa.
    seccion = elegir([
        Dato(valor=(20, 30), fuente="detalle", hoja="ES-100", texto="K-9 20X30"),
        Dato(valor=None, fuente="detalle", hoja="ES-200", ilegible=True, texto="K-9 2O×3O"),
    ])  # fmt: skip
    defs = {"K-9": _def("K-9", seccion=seccion)}
    k = _tag("K-9", x=210, y=10)
    (e,) = _construir([k], None, defs, frames=_marcos_100_500())
    assert e.hoja == "ES-200"
    assert (e.seccion_cm.valor, e.seccion_cm.fuente) == ((20, 30), "detalle")
    assert any(a.ilegible for a in e.seccion_cm.alternativas)
    assert any(
        a.startswith("sección: lo que dice la hoja ES-200 no se pudo leer") for a in e.avisos
    )
    assert not e.dudas


def test_one_line_that_is_the_span_of_several_tags_is_said_on_each():
    # Marina: varias etiquetas CE-1 sobre la misma línea de MUROS1 de 14.9 toman cada una el
    # largo entero. La medida no se reparte aquí (es del detector), pero el elemento lo dice.
    a = _tag("CE-1", "dala", x=0.0, estimated_span_length=14.9)
    b = _tag("CE-1", "dala", x=5.0, estimated_span_length=14.9)
    c = _tag("CE-2", "dala", x=9.0, estimated_span_length=3.0)
    a.source_entities = ["ent_a", "ent_linea"]
    b.source_entities = ["ent_b", "ent_linea"]
    c.source_entities = ["ent_c", "ent_otra"]
    seg = _seg({d.detection_id: "v_pa" for d in (a, b, c)})
    els = {e.detection_id: e for e in _construir([a, b, c], seg, {}, {"dala": _nota_dala()})}
    for d in (a, b):
        assert any(x.startswith("claro compartido: la misma línea es el claro de 2 etiquetas")
                   for x in els[d.detection_id].avisos)  # fmt: skip
        assert els[d.detection_id].longitud_m.valor == 14.9
    assert not any(x.startswith("claro compartido") for x in els[c.detection_id].avisos)
