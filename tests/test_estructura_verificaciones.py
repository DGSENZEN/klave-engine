"""Tarea 11: las verificaciones del propio plano — lo que la lectura no sabe, lo que el plano se
contradice y lo que el plano dibuja y la lectura no encontró, agrupado y ordenado por lo que está
en juego. Cada regla tiene aquí un caso sintético que la necesita (ninguna se fija sólo con el
plano de Marina, que no está en el repositorio)."""

import re

import pytest
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.schedules import ElementSpec, ScheduleInventory, SeccionDibujada
from klave_engine.detection.views import SheetSegmentation, ViewKind, ViewRegion
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.estructura.armado import GrupoVarillas, JuegoEstribos, Parrilla, Zona
from klave_engine.estructura.asociacion import Rechazo
from klave_engine.estructura.dato import Dato, elegir
from klave_engine.estructura.definiciones import Definicion
from klave_engine.estructura.elementos import Colocacion, Elemento
from klave_engine.estructura.reglas import FilaVarilla, reglas_estandar
from klave_engine.estructura.verificaciones import (
    CRITICOS,
    Verificacion,
    id_de_verificacion,
    peso,
    verificar,
)
from klave_engine.graph.evidence import EvidencePacket

_N = iter(range(1, 100_000))


# ---------------------------------------------------------------------------------- ayudantes


def _dato(valor, fuente="detalle", hoja="ES-200", texto=None, **kw):
    return Dato(valor=valor, fuente=fuente, hoja=hoja, texto=texto or f"{valor}", **kw)


def _ilegible(texto, hoja="ES-200", fuente="detalle"):
    return Dato(valor=None, fuente=fuente, hoja=hoja, texto=texto, ilegible=True)


def _barras(*grupos):
    return [GrupoVarillas(cantidad=c, numero=n) for c, n in grupos]


def _estribos(texto="E#2@15"):
    if texto == "E#3":
        return [JuegoEstribos(tipo="estribo", cantidad=1, numero="3")]
    if texto == "2E#3 VER CORTE":
        return [JuegoEstribos(tipo="estribo", cantidad=2, numero="3", referencia="VER CORTE")]
    m = re.match(r"E#(\d)@(\d+)", texto)
    assert m is not None
    numero, sep = m.groups()
    return [
        JuegoEstribos(
            tipo="estribo",
            cantidad=1,
            numero=numero,
            zonas=[Zona(tramo="todo", separacion_m=int(sep) / 100)],
        )
    ]


_DEF = object()


def _el(
    marca="K-1",
    familia="castillo",
    definicion="marca",
    hoja="ES-100",
    seccion=_DEF,
    altura=_DEF,
    longitud=_DEF,
    longitudinales=_DEF,
    estribos=_DEF,
    parrillas=None,
    avisos=(),
    dudas=(),
    detection_id=None,
    vista="v_pa",
):
    vigas = familia in ("trabe", "contratrabe", "dala", "cerramiento", "pilote")
    return Elemento(
        element_id=f"el_{next(_N):05d}",
        detection_id=detection_id or f"det_{next(_N):05d}",
        marca=marca,
        familia=familia,
        vista=vista,
        hoja=hoja,
        definicion=definicion,
        seccion_cm=_dato((15, 20)) if seccion is _DEF else seccion,
        altura_m=(None if vigas else _dato(3.0, "nota", "", "entre niveles: 3 m"))
        if altura is _DEF
        else altura,
        longitud_m=(_dato(4.0, "medido", "") if vigas else None) if longitud is _DEF else longitud,
        longitudinales=_dato(_barras((4, "3")), texto="4#3")
        if longitudinales is _DEF
        else longitudinales,
        estribos=_dato(_estribos("E#2@15"), texto="E#2@15") if estribos is _DEF else estribos,
        parrillas=parrillas,
        recubrimiento_m=_dato(0.03, "nota", "", "3 CM EN CASTILLOS"),
        avisos=list(avisos),
        dudas=list(dudas),
        colocacion=Colocacion(),
    )


def _defn(marca="K-1", familia="castillo", hojas=("ES-200",), **campos):
    datos = {"seccion_cm": _dato((15, 20))}
    datos.update(campos)
    return Definicion(marca=marca, familia=familia, hojas=list(hojas), **datos)


def _texto(texto, x=0.0, y=0.0, h=0.1, archivo="a.dxf", handle=None, eid=None):
    ancho = 0.6 * h * len(texto)
    eid = eid or f"ent_{next(_N):05d}"
    return NormalizedEntity(
        entity_id=eid,
        entity_type=EntityType.text,
        source_file=archivo,
        layer="0",
        bbox=(x, y, x + ancho, y + h),
        raw_handle=handle or eid.upper(),
        properties={"height": h},
        evidence=EvidencePacket(source=archivo, method="t"),
        text=texto,
    )


def _det(marca, familia="castillo", x=0.0, y=0.0, entidades=(), vista="v_pa", **props):
    tipo = {
        "castillo": DetectionType.column_tag,
        "pilote": DetectionType.pile,
        "zapata": DetectionType.footing,
        "muro_concreto": DetectionType.wall,
    }.get(familia, DetectionType.beam_tag)
    det = make_detection(
        f"det_{next(_N):05d}",
        tipo,
        marca or familia,
        (x, y, x + 0.3, y + 0.1),
        0.9,
        list(entidades) or [f"ent_{next(_N):05d}"],
        "t",
        [],
        props,
        "a.dxf",
    )
    det.mark = marca
    det.family = familia
    return det


def _seg(
    asignacion=None, vistas=("v_pa",), niveles=None, cimentacion=(), caja=(-100, -100, 100, 100)
):
    niveles = niveles or {}
    regiones = [
        ViewRegion(
            view_id=v,
            title=f"{v.upper()} · PLANTA",
            kind=ViewKind.plan,
            level_key="cimentacion" if v in cimentacion else "planta",
            npt_level=niveles.get(v),
            anchor=(0, 0),
            bbox=caja,
        )
        for v in vistas
    ] + [
        ViewRegion(
            view_id="v_det",
            title="V_DET · DETALLES",
            kind=ViewKind.excluded,
            anchor=(0, 0),
            bbox=(200, 200, 300, 300),
        )
    ]
    return SheetSegmentation(views=regiones, assignment=asignacion or {}, is_segmented=True)


def _run(
    elementos=(),
    defs=None,
    familias=None,
    reglas=None,
    inv=None,
    entities=(),
    detections=(),
    seg=None,
    frames=None,
):
    por_marca = defs if isinstance(defs, dict) else {m: _defn(m) for m in defs or []}
    return verificar(
        por_marca,
        familias or {},
        list(elementos),
        reglas or reglas_estandar(),
        inv or ScheduleInventory(),
        list(entities),
        list(detections),
        seg,
        frames=frames or [],
    )


def _all(v, numero):
    return [x for x in v if x.numero == numero]


def _one(v, numero):
    todos = _all(v, numero)
    assert len(todos) == 1, [x.mensaje for x in todos]
    return todos[0]


def _con(v, numero, texto):
    return [x for x in v if x.numero == numero and texto in x.mensaje]


# ----------------------------------------------------------------- 1: colocada sin definir


def test_1_undefined_mark():
    v = _run(elementos=[_el("K-99", definicion="ninguna")])
    assert _one(v, 1).severidad == "bloquea"
    nota = {
        "castillo": _defn(
            "CASTILLO", seccion_cm=_dato((15, 15), "nota", texto="CASTILLO 15X15 4#3 E#2@20")
        )
    }
    v2 = _run(elementos=[_el("K-99", definicion="familia")], familias=nota)
    assert _one(v2, 1).severidad == "duda" and "nota general" in _one(v2, 1).mensaje
    assert "CASTILLO 15X15 4#3 E#2@20" in _one(v2, 1).mensaje


def test_1_one_finding_per_mark_with_every_placement():
    els = [_el("K-99", definicion="ninguna", hoja=h) for h in ("ES-100", "ES-100", "ES-200")]
    f = _one(_run(elementos=els), 1)
    assert len(f.elementos) == 3 and "3 piezas" in f.mensaje
    assert "ES-100 (2)" in f.mensaje and "ES-200" in f.mensaje and f.hoja == ""


def test_1_unmarked_placements_are_one_aviso_per_family_never_a_block():
    els = [_el("", "zapata", definicion="ninguna", seccion=None, altura=None) for _ in range(3)]
    els.append(_el("", "muro_concreto", definicion="ninguna", seccion=None, altura=None))
    v = _run(elementos=els)
    unos = _all(v, 1)
    assert {x.severidad for x in unos} == {"aviso"} and len(unos) == 2
    zapatas = next(x for x in unos if "zapata" in x.mensaje)
    assert zapatas.mensaje.startswith("3 colocaciones de zapata sin marca")
    assert "sección en 3" in zapatas.mensaje and "parrillas en 3" in zapatas.mensaje
    assert not _all(v, 7)  # their missing values are said in the aviso, not as blocks


def test_1_a_defined_mark_is_not_flagged():
    assert not _all(_run(elementos=[_el("K-1")], defs=["K-1"]), 1)


# ------------------------------------------------------------ 2 y 10: definida, escrita


def _planta_con(*textos, dets=()):
    seg = _seg({d.detection_id: "v_pa" for d in dets})
    frames = [
        SheetFrame(frame_id="v_pa", bbox=(-100, -100, 100, 100), source_file="a.dxf", code="ES-100")
    ]
    return dict(entities=list(textos), detections=list(dets), seg=seg, frames=frames)


def test_2_and_10_defined_but_not_placed():
    v = _run(defs=["K-50"], **_planta_con())
    assert _one(v, 2).severidad == "aviso"
    v2 = _run(defs=["K-50"], **_planta_con(_texto("K-50", 1, 1)))  # written in a planta
    assert _one(v2, 10).severidad == "duda" and not _all(v2, 2)
    assert "K-50" in _one(v2, 10).mensaje and "ES-100" in _one(v2, 10).mensaje


def test_2_skips_definitions_only_the_ai_gives():
    solo_ia = {
        "K-50": Definicion(marca="K-50", familia="castillo", seccion_cm=_dato((15, 15), "ia"))
    }
    assert not _all(_run(defs=solo_ia, **_planta_con()), 2)


def test_10_a_text_a_detection_took_is_a_placement():
    t = _texto("K-50", 1, 1)
    d = _det("K-50", entidades=[t.entity_id], x=1, y=1)
    assert not _all(_run(defs=["K-50"], **_planta_con(t, dets=[d])), 10)


def test_10_a_cuadro_label_is_not_a_placement_text():
    t = _texto("K-50", 1, 1)
    inv = ScheduleInventory(cuadro_mark_entities=[t.entity_id])
    assert not _all(_run(defs=["K-50"], inv=inv, **_planta_con(t)), 10)


def test_10_only_texts_inside_a_structural_planta():
    fuera = _texto("K-50", 250, 250)  # in the detail view
    assert not _all(_run(defs=["K-50"], **_planta_con(fuera)), 10)


def test_10_a_second_label_of_a_placed_element_is_not_recall():
    t = _texto("K-50", 1, 1)
    otra = _texto("K-50", 1.1, 1.3)  # the same element labelled twice
    d = _det("K-50", entidades=[t.entity_id], x=1, y=1)
    assert not _all(_run(defs=["K-50"], **_planta_con(t, otra, dets=[d])), 10)


def test_10_groups_every_text_of_a_mark_and_reads_family_words_and_definition_names():
    textos = [_texto("MC-1", 1 + 3 * i, 1) for i in range(5)] + [_texto("DADO D-4", 30, 1)]
    textos.append(_texto("MC-C", 40, 1))  # not grammar: known because a definition names it
    defs = {"MC-1": _defn("MC-1", "muro_concreto"), "MC-C": _defn("MC-C", "muro_concreto")}
    v = _run(defs=defs, **_planta_con(*textos))
    diez = {x.marcas[0]: x for x in _all(v, 10)}
    assert set(diez) == {"MC-1", "D-4", "MC-C"}
    assert "5 veces" in diez["MC-1"].mensaje and len(diez["MC-1"].textos) == 5
    assert "Tampoco está definida" in diez["D-4"].mensaje


def test_10_a_mark_text_beside_an_unmarked_placement_says_so():
    t = _texto("D-4", 1, 1)
    sin_marca = _det("", "zapata", x=1.0, y=1.15)
    v = _run(defs=["D-4"], **_planta_con(t, dets=[sin_marca]))
    assert "junto a una colocación sin marca (zapata)" in _one(v, 10).mensaje


def test_10_every_pile_text_needs_a_pile():
    v = _run(defs={"P-4": _defn("P-4", "pilote")}, **_planta_con(_texto("P-4", 1, 1)))
    assert "Todo pilote escrito en planta debe tener su pila" in _one(v, 10).mensaje


def test_2_says_when_the_mark_only_appears_as_a_cuadro_label():
    d = _det("K-0", entidades=["ent_k0"], x=1, y=1, role="cuadro")
    v = _run(defs=["K-0"], **_planta_con(dets=[d]))
    assert "sólo aparece como etiqueta de cuadro" in _one(v, 2).mensaje


# ------------------------------------------------------------------- 7: datos críticos


def test_7_critical_missing():
    v = _run(elementos=[_el("P-4", familia="pilote", longitud=None)], defs=["P-4"])
    f = next(x for x in _all(v, 7) if x.campo == "longitud_m")
    assert f.severidad == "bloquea" and "longitud" in f.mensaje
    v2 = _run(elementos=[_el("K-1", estribos=_dato(_estribos("E#3"), texto="E#3"))], defs=["K-1"])
    f2 = _one(v2, 7)  # no spacing; a castillo supuesto exists
    assert f2.severidad == "duda" and "separación" in f2.mensaje


def test_7_no_spacing_without_a_family_supuesto_blocks():
    trabe = _el("T-1", "trabe", estribos=_dato(_estribos("E#3"), texto="E#3"))
    assert _one(_run(elementos=[trabe], defs=["T-1"]), 7).severidad == "bloquea"


def test_7_stirrups_given_by_reference_are_said_as_such():
    p = _el(
        "P-4", "pilote", longitud=_dato(12.0, "nota"), estribos=_dato(_estribos("2E#3 VER CORTE"))
    )
    f = _one(_run(elementos=[p], defs=["P-4"]), 7)
    assert f.severidad == "bloquea" and "remite su separación a «VER CORTE»" in f.mensaje


def test_7_pile_length_quotes_what_the_notes_say():
    nota = _texto("LOS PILOTES SE DESPLANTARAN SEGUN EL ESTUDIO DE MECANICA DE SUELOS", 300, 300)
    p = _el("P-4", "pilote", longitud=None)
    f = next(
        x for x in _run(elementos=[p], defs=["P-4"], entities=[nota]) if x.campo == "longitud_m"
    )
    assert "MECANICA DE SUELOS" in f.mensaje and nota.raw_handle in f.mensaje


def test_7_supuesto_section_is_a_duda_and_says_the_drawn_cotas_near_its_title():
    supuesta = _dato((25, 50), "supuesto", "", "sección supuesta de contratrabe, 25x50 cm")
    el = _el("CTA-11", "contratrabe", seccion=supuesta)
    d = _defn(
        "CTA-11", "contratrabe", seccion_cm=_ilegible("CTA-11 · sección dibujada no encontrada")
    )
    d.avisos = ["las cotas cercanas (70) no se toman (ES-004)"]
    f = _one(_run(elementos=[el], defs={"CTA-11": d}), 7)
    assert f.severidad == "duda" and "25x50" in f.mensaje
    assert "acota 70 cm en ES-004" in f.mensaje and "no coincide" in f.mensaje


def test_7_ilegible_without_supuesto_blocks_and_quotes_the_text():
    el = _el("T3-3", "trabe", longitudinales=_ilegible("«2#8», «3#6»"))
    f = _one(_run(elementos=[el], defs=["T3-3"]), 7)
    assert f.severidad == "bloquea" and "«2#8», «3#6»" in f.mensaje and "por leer" in f.mensaje


def test_7_unread_text_beside_the_section_makes_an_empty_field_por_leer():
    d = _defn("CTA-1", "contratrabe")
    d.sin_leer = {"longitudinales": "«3#8», «4#4»", "estribos": "«E#4»"}
    el = _el("CTA-1", "contratrabe", longitudinales=None, estribos=None)
    f = _one(_run(elementos=[el], defs={"CTA-1": d}), 7)  # both armado fields, one finding
    assert f.campo == "longitudinales,estribos" and f.severidad == "bloquea"
    assert "«3#8», «4#4»" in f.mensaje and "«E#4»" in f.mensaje and "no se leyeron" in f.mensaje


def test_7_one_finding_per_mark_field_and_state_with_all_placements():
    els = [_el("T3-3", "trabe", longitudinales=_ilegible("«2#8»"), hoja=h) for h in ("ES-300",) * 4]
    f = _one(_run(elementos=els, defs=["T3-3"]), 7)
    assert len(f.elementos) == 4 and "4 piezas en ES-300 (4)" in f.mensaje


def test_7_ai_value_is_a_duda():
    el = _el("K-1", seccion=_dato((20, 20), "ia", texto="IA · hoja ES-200"))
    f = _one(_run(elementos=[el], defs=["K-1"]), 7)
    assert f.severidad == "duda" and "lectura IA" in f.mensaje


def test_7_a_value_borrowed_from_another_sheet_is_a_duda():
    dato = elegir(
        [
            _dato(_barras((4, "3")), hoja="ES-200", texto="4#3"),
            _ilegible("CI · 4#3 / E#2@15", "ES-300"),
        ]
    )
    el = _el("CI", "dala", hoja="ES-300", longitudinales=dato)
    f = _one(_run(elementos=[el], defs=["CI"]), 7)
    assert f.severidad == "duda" and "su hoja ES-300 las dibuja y no se pudo leer" in f.mensaje
    assert "lo leído en ES-200" in f.mensaje


def test_7_drawn_section_unread_and_planta_outline_used_is_a_duda():
    medida = _dato(
        {"area_cm2": 2300},
        "medido",
        "",
        "contorno en planta no rectangular: 2300 cm²",
        alternativas=[_ilegible("K-15A · sección dibujada no encontrada")],
    )
    f = _one(_run(elementos=[_el("K-15A", seccion=medida)], defs=["K-15A"]), 7)
    assert f.severidad == "duda" and "medido en planta" in f.mensaje


def test_7_storey_height_supuesto_is_one_finding_per_sheet():
    alto = _dato(3.2, "supuesto", "", "la planta más alta repite la de abajo (3.2 m)")
    els = [_el(m, altura=alto, hoja="ES-400") for m in ("K-1", "K-2", "K-3")]
    f = _one(_run(elementos=els, defs=["K-1", "K-2", "K-3"]), 7)
    assert f.campo == "altura_m" and f.hoja == "ES-400" and len(f.elementos) == 3
    assert "K-1, K-2 y K-3" in f.mensaje


def test_7_single_bar_without_stirrups_is_an_aviso_not_a_block():
    el = _el("K-X", longitudinales=_dato(_barras((1, "4"))), estribos=None)
    assert _one(_run(elementos=[el], defs=["K-X"]), 7).severidad == "aviso"
    el2 = _el("K-2", longitudinales=_dato(_barras((4, "3"))), estribos=None)
    assert _one(_run(elementos=[el2], defs=["K-2"]), 7).severidad == "bloquea"


def test_7_beam_families_carry_their_length():
    assert "longitud_m" in CRITICOS["dala"] and "longitud_m" in CRITICOS["trabe"]
    dala = _el("CI", "dala", longitud=None)
    assert _one(_run(elementos=[dala], defs=["CI"]), 7).campo == "longitud_m"


def test_7_doubtful_placements_group_per_sheet():
    dets = [
        _det("CE-3", "dala", claro_dudoso="claro dudoso: su tramo de punta …") for _ in range(2)
    ]
    dets.append(_det("K-2", marcador_dudoso="marcador dudoso: el marcador tomado …"))
    els = [_el("CE-3", "dala", detection_id=dets[0].detection_id, hoja="ES-200"),
           _el("CE-3", "dala", detection_id=dets[1].detection_id, hoja="ES-200"),
           _el("K-2", detection_id=dets[2].detection_id, hoja="ES-400")]  # fmt: skip
    v = _run(elementos=els, defs=["CE-3", "K-2"], detections=dets)
    claro = _con(v, 7, "claro dudoso")
    assert len(claro) == 1 and len(claro[0].elementos) == 2 and claro[0].hoja == "ES-200"
    assert len(_con(v, 7, "marcador dudoso")) == 1


def test_7_vista_dudosa_from_the_segmentation():
    d = _det("K-1")
    seg = _seg({d.detection_id: "v_pa"})
    seg.vistas_dudosas = {d.detection_id: "vista dudosa: casi igual de cerca de A y de B"}
    v = _run(
        elementos=[_el("K-1", detection_id=d.detection_id)], defs=["K-1"], detections=[d], seg=seg
    )
    assert _con(v, 7, "vista dudosa")[0].severidad == "duda"


def test_7_shared_span_cut_halfway_and_untagged_leg_are_avisos():
    a = _det(
        "T-1", "trabe", claro_compartido="claro compartido: … cortada a medio camino entre ellas"
    )
    b = _det("T-2", "trabe", tramo_sin_etiqueta="tramo sin etiqueta propia: la línea 5AB …")
    c = _det("T-3", "trabe", claro_compartido="claro compartido: … cortada en 1 apoyo(s)")
    els = [_el(d.mark, "trabe", detection_id=d.detection_id) for d in (a, b, c)]
    v = _run(elementos=els, defs=["T-1", "T-2", "T-3"], detections=[a, b, c])
    assert _con(v, 7, "a medio camino")[0].severidad == "aviso"
    assert len(_con(v, 7, "a medio camino")[0].elementos) == 1  # cut at a support: exact
    assert _con(v, 7, "tramo sin etiqueta propia")[0].severidad == "aviso"


def test_7_no_element_duda_is_left_unsaid():
    el = _el("K-1", dudas=["altura de K-1: algo raro que nadie más cubre"])
    assert "algo raro" in _one(_run(elementos=[el], defs=["K-1"]), 7).mensaje


def test_7_wall_variant_not_decided():
    el = _el(
        "CI",
        "dala",
        dudas=["variante de CI: el muro medido (35 cm) no es de ninguna, por confirmar"],
    )
    f = _one(_run(elementos=[el], defs=["CI"]), 7)
    assert "variantes por muro" in f.mensaje and "35 cm" in f.mensaje


# --------------------------------------------------------------- 8: el plano se contradice


def _reglas_marina():
    """Las reglas de una hoja de cimentación: la tabla de varillas da traslape al #8 y la nota
    de esa misma hoja manda soldar del #8 en adelante; en las plantas se suelda del #10."""
    r = reglas_estandar()
    filas = {"6": FilaVarilla(LT1=70.0), "8": FilaVarilla(LT1=115.0), "10": FilaVarilla()}
    copias = [
        Dato(valor=filas, fuente="cuadro", hoja=h, texto="TABLA DE VARILLAS")
        for h in ("ES-000", "ES-100")
    ]
    tabla = elegir(copias)
    assert tabla is not None
    r.tabla_varillas = tabla
    r.soldar_desde_numero = elegir(
        [
            Dato(valor="8", fuente="nota", hoja="ES-000", texto="DEL #8 Y MAYORES SE SOLDARAN"),
            Dato(valor="10", fuente="nota", hoja="ES-100", texto="DEL #10 Y MAYORES SE SOLDARAN"),
        ]
    )
    return r


def _conflicto(marca, a, b):
    return {
        marca: _defn(
            marca,
            seccion_cm=elegir([_dato(a, hoja="ES-200"), _dato(b, hoja="ES-400")]),
        )
    }


def test_8_contradictions():
    v = _run(defs=_conflicto("K-5", (20, 30), (20, 40)), reglas=_reglas_marina())
    msgs = [x.mensaje for x in _all(v, 8)]
    assert any("K-5" in m and "20x30" in m and "20x40" in m for m in msgs)
    assert any("#8" in m and "suelda" in m for m in msgs)


def test_8_rule_difference_across_sheets_is_not_a_contradiction():
    msgs = [x.mensaje for x in _all(_run(reglas=_reglas_marina()), 8)]
    assert not any("#10" in m for m in msgs)  # the plantas weld from #10 and lap only to #8
    assert sum("suelda" in m for m in msgs) == 1


def test_8_two_values_of_a_rule_on_one_sheet_contradict():
    r = reglas_estandar()
    r.traslape_max_numero = elegir(
        [
            Dato(valor="6", fuente="nota", hoja="ES-000", texto="SE TRASLAPARAN HASTA EL #6"),
            Dato(valor="8", fuente="nota", hoja="ES-000", texto="SE TRASLAPARAN HASTA EL #8"),
        ]
    )
    f = _one(_run(reglas=r), 8)
    assert "En ES-000" in f.mensaje and "#6" in f.mensaje and "#8" in f.mensaje


def test_8_a_sheet_with_elements_without_its_own_copy_of_a_disputed_rule():
    f = [
        x
        for x in _all(
            _run(elementos=[_el("K-1", hoja="ES-300")], defs=["K-1"], reglas=_reglas_marina()), 8
        )
    ]
    assert any("ES-300" in x.mensaje and "no trae su propia copia" in x.mensaje for x in f)


def test_8_an_unreadable_copy_or_a_same_value_copy_is_not_a_contradiction():
    ilegible = {
        "K-10": _defn(
            "K-10",
            seccion_cm=elegir([_dato((15, 85), hoja="ES-400"), _ilegible("K-10 · …", "ES-300")]),
        )
    }
    assert ilegible["K-10"].seccion_cm.en_conflicto  # R143 marks it, yet it is no contradiction
    assert not _all(_run(defs=ilegible), 8)
    copias = {
        "K-1": _defn(
            "K-1", seccion_cm=elegir([_dato((15, 20), hoja=h) for h in ("ES-100", "ES-200")])
        )
    }
    assert not _all(_run(defs=copias), 8)


def test_8_variants_are_compared_variant_by_variant():
    v15 = _defn("CI", "dala", seccion_cm=_dato((15, 20)))
    v15.para_muro_cm = 15
    v30 = _defn("CI", "dala", seccion_cm=_dato((30, 20)))
    v30.para_muro_cm = 30
    ci = _defn("CI", "dala", seccion_cm=elegir([_dato((15, 20)), _dato((30, 20), hoja="ES-300")]))
    ci.variantes = [v15, v30]
    assert not _all(_run(defs={"CI": ci}), 8)


def test_8_the_contradiction_says_what_is_at_stake():
    els = [_el("K-5", seccion=_dato((20, 30))) for _ in range(2)]
    f = _one(_run(elementos=els, defs=_conflicto("K-5", (20, 30), (20, 40))), 8)
    assert f.en_juego["concreto_m3"] == pytest.approx(0.20 * 0.10 * 3.0 * 2)


def test_8_a_sheet_code_two_frames_carry():
    frames = [SheetFrame(frame_id=f"f{i}", bbox=(0, 0, 1, 1), code="ES-100") for i in range(2)]
    assert "«ES-100»" in _one(_run(frames=frames), 8).mensaje


def test_8_storeys_counted_two_ways_states_both_readings():
    vistas = ("v0", "v1", "v2")
    seg = _seg(vistas=vistas, niveles={"v0": 1.0, "v1": 4.0, "v2": 7.5}, cimentacion=("v0",))
    els = [
        _el(
            f"K-{i}",
            vista=v,
            hoja=v.upper(),
            altura=_dato(alto, "supuesto" if v == "v2" else "nota", ""),
        )
        for i, (v, alto) in enumerate((("v0", 3.0), ("v1", 3.0), ("v2", 3.0)))
    ]
    f = _con(_run(elementos=els, defs=[e.marca for e in els], seg=seg), 8, "entrepisos")
    assert len(f) == 1 and "(A)" in f[0].mensaje and "(B)" in f[0].mensaje
    assert "Decide cuál vale" in f[0].mensaje and f[0].en_juego["concreto_m3"] > 0
    # no foundation set, or a top planta with its own level above: nothing contradicts
    sin_base = [e for e in els if e.vista != "v0"]
    assert not _con(_run(elementos=sin_base, defs=["K-1", "K-2"], seg=seg), 8, "entrepisos")


# --------------------------------------------------------------------- 11: lo que nadie leyó


def _rech(texto, motivo, marcas, hoja="ES-200", posibles=(), eid=None):
    return Rechazo(
        entidad_id=eid or f"ent_{next(_N):05d}",
        texto=texto,
        hoja=hoja,
        motivo=motivo,
        marcas=list(marcas),
        posibles=list(posibles),
    )


def test_11_orphans_ambiguity_and_cuadro_consistency():
    k7 = _texto("K-7", 1, 1)
    inv = ScheduleInventory(
        rechazos=[_rech("6#4", "ambigua", ["K-1", "K-2"]), _rech("4#3", "sin_dueno", [])],
        cuadro_mark_entities=[k7.entity_id],
    )
    defs = {"K-4": _defn("K-4")}
    defs["K-4"].avisos = ["sin leer: «@1S»"]
    frames = [SheetFrame(frame_id="f", bbox=(-10, -10, 10, 10), source_file="a.dxf", code="ES-200")]
    v = _run(inv=inv, defs=defs, entities=[k7], frames=frames)
    assert len(_all(v, 11)) == 4 and all(x.severidad == "duda" for x in _all(v, 11))


def test_11_rejections_are_grouped_per_sheet_motive_and_kind():
    rechazos = [_rech(t, "sin_dueno", []) for t in ("1@6,8@10", "10@10,1@6", "@20")]
    rechazos += [_rech("4#3", "sin_dueno", []), _rech("2#6", "sin_dueno", [], hoja="ES-300")]
    v = _run(inv=ScheduleInventory(rechazos=rechazos))
    once = _all(v, 11)
    assert len(once) == 3
    dist = _con(v, 11, "distribuciones de estribos")[0]
    assert dist.mensaje.startswith("3 distribuciones") and len(dist.textos) == 3


def test_11_a_stack_owning_label_counted_as_a_placement():
    k1 = _texto("K-1", 1, 1)
    d = _det("K-1", entidades=[k1.entity_id])
    inv = ScheduleInventory(
        cuadro_mark_entities=[k1.entity_id],
        specs=[
            ElementSpec(
                mark="K-1",
                family="castillo",
                source="detalle",
                source_text="K-1",
                confidence=1,
                metodo="pila",
                hoja="",
            )
        ],
    )
    el = _el("K-1", detection_id=d.detection_id)
    assert _con(
        _run(elementos=[el], defs=["K-1"], inv=inv, entities=[k1], detections=[d]),
        11,
        "contadas como colocación",
    )


def test_11_armado_written_beside_or_at_the_corner_of_its_section():
    junto = _texto("E#4", 2.2, 1.0, eid="ent_junto", handle="D085F")  # right of the section
    bajo = _texto("4#3", 1.2, 0.5, eid="ent_bajo", handle="AAAA1")  # under it, a doubted stack
    lejos = _texto("3#8", 9.0, 1.0, eid="ent_lejos", handle="CC583")  # its elevation, far
    inv = ScheduleInventory(
        rechazos=[
            _rech(t.text, "sin_dueno", [], hoja="ES-002", posibles=["CTA-1"], eid=t.entity_id)
            for t in (junto, bajo, lejos)
        ],
        secciones_dibujadas=[
            SeccionDibujada(marca="CTA-1", caja=(1.0, 0.8, 2.0, 2.0), hoja="ES-002", titulo_id="t")
        ],
    )
    f = _con(_run(inv=inv, entities=[junto, bajo, lejos]), 11, "Armado de CTA-1")[0]
    assert "en esquina o junto a la sección" in f.mensaje and "«E#4» D085F" in f.mensaje
    assert "bajo la sección" in f.mensaje and "AAAA1" in f.mensaje and "CC583" not in f.mensaje


def test_11_ai_only_field_beside_unread_drawing_texts_is_a_duda_and_lonely_is_an_aviso():
    titulo = _texto("MURO DE CONCRETO MC-C", 0, 0, h=0.15)
    malla = _texto("#4@15", 0, -0.6, eid="ent_malla", handle="CC0CB")
    frames = [SheetFrame(frame_id="f", bbox=(-10, -10, 10, 10), source_file="a.dxf", code="ES-002")]
    defs = {
        "MC-C": Definicion(
            marca="MC-C",
            familia="muro_concreto",
            parrillas=_dato(
                [Parrilla(numero="4", separacion_m=0.15, lecho="unico", sentidos=None)],
                "ia",
                "ES-002",
                "IA · MC-C",
            ),
        ),
        "CM-1": Definicion(
            marca="CM-1",
            familia="columna",
            seccion_cm=_dato((25.4, 25.4), "ia", "ES-002", "IA · CM-1"),
        ),
    }
    inv = ScheduleInventory(
        rechazos=[_rech("#4@15", "sin_dueno", [], hoja="ES-002", eid=malla.entity_id)]
    )
    v = _run(defs=defs, inv=inv, entities=[titulo, malla], frames=frames)
    ia = {x.marcas[0]: x for x in v if "sólo la lectura IA" in x.mensaje}
    assert ia["MC-C"].severidad == "duda" and "CC0CB" in ia["MC-C"].mensaje
    assert ia["CM-1"].severidad == "aviso"


def test_11_informational_reading_avisos_group_by_kind():
    defs = {m: _defn(m) for m in ("C-1", "C-2")}
    for d in defs.values():
        d.avisos = [
            "familia: el plano no la dice (sólo el prefijo de la marca: columna); se toma la de la "
            "IA: columna"
        ]
    defs["K-4"] = _defn("K-4")
    defs["K-4"].avisos = ["sin leer: «@1S»"]
    v = _run(defs=defs)
    avisos = [x for x in _all(v, 11) if x.severidad == "aviso"]
    assert len(avisos) == 1 and avisos[0].marcas == ["C-1", "C-2"]
    assert _one([x for x in v if x.severidad == "duda"], 11).marcas == ["K-4"]


# ------------------------------------------------------------------------- ids y orden


def test_ids_are_stable():
    assert [x.id for x in _run(elementos=[_el("K-99")])] == [
        x.id for x in _run(elementos=[_el("K-99")])
    ]


def test_ids_do_not_depend_on_counts():
    uno = _run(elementos=[_el("K-99", definicion="ninguna")])
    dos = _run(elementos=[_el("K-99", definicion="ninguna"), _el("K-99", definicion="ninguna")])
    assert _one(uno, 1).id == _one(dos, 1).id
    assert _one(uno, 1).id == id_de_verificacion(1, "K-99", "", "sin definición")


def test_messages_carry_no_rule_codes():
    v = _run(
        elementos=[_el("K-99", definicion="ninguna"), _el("P-4", "pilote", longitud=None)],
        defs=_conflicto("K-5", (20, 30), (20, 40)) | {"P-4": _defn("P-4", "pilote")},
        reglas=_reglas_marina(),
    )
    assert v and not [x.mensaje for x in v if re.search(r"\bR\d{1,3}\b|verificación \d", x.mensaje)]


def test_blocks_come_first_then_by_what_is_at_stake():
    grande = [_el("T-9", "trabe", definicion="ninguna", seccion=_dato((40, 90))) for _ in range(3)]
    chica = [_el("T-8", "trabe", definicion="ninguna", seccion=_dato((15, 20)))]
    duda = _el("K-1", seccion=_dato((60, 60), "ia"))  # more at stake than T-8, yet after it
    v = _run(elementos=[*chica, duda, *grande], defs=["K-1"])
    orden = [(x.severidad, x.marcas[0]) for x in v if x.numero in (1, 7)]
    assert (
        orden.index(("bloquea", "T-9"))
        < orden.index(("bloquea", "T-8"))
        < orden.index(("duda", "K-1"))
    )


def test_peso_is_a_share_of_the_whole_structure():
    v = Verificacion(id="x", numero=7, severidad="duda", mensaje="", en_juego={"concreto_m3": 2.0})
    assert peso(v, {"acero_kg": 100.0, "concreto_m3": 10.0}) == pytest.approx(0.2)
    w = Verificacion(
        id="y", numero=7, severidad="bloquea", mensaje="", en_juego={"volumen_m3": 5.0}
    )
    assert peso(w, {"acero_kg": 100.0, "concreto_m3": 10.0}) == pytest.approx(0.5)


def test_7_an_undefined_mark_is_said_once_not_again_field_by_field():
    v = _run(
        elementos=[_el("T4-3", "trabe", definicion="ninguna", longitudinales=None, estribos=None)]
    )
    assert _one(v, 1).severidad == "bloquea"
    assert not [x for x in _all(v, 7) if x.campo != "longitud_m"]


def test_ids_of_a_whole_mark_do_not_depend_on_its_sheets():
    una = _run(
        elementos=[_el("T3-3", "trabe", longitudinales=_ilegible("«2#8»"), hoja="ES-300")],
        defs=["T3-3"],
    )
    dos = _run(
        elementos=[
            _el("T3-3", "trabe", longitudinales=_ilegible("«2#8»"), hoja="ES-300"),
            _el("T3-3", "trabe", longitudinales=_ilegible("«2#8»"), hoja="ES-400"),
        ],
        defs=["T3-3"],
    )
    assert _one(una, 7).id == _one(dos, 7).id and _one(una, 7).hoja == "ES-300"


def test_11_ai_section_name_counts_its_cut_title_but_only_its_tight_stack():
    corte = _texto("SECCIÓN 1", 0, 0, h=0.1)
    seccion = _texto("30X60", 0, -0.17, h=0.1)
    estribo = _texto("E#3", 0, -0.33, h=0.1, eid="ent_e3", handle="CCEAF")  # its stack
    lejos = _texto("@20", 0, 0.6, h=0.1, eid="ent_e20", handle="CCE17")  # an elevation label above
    frames = [SheetFrame(frame_id="f", bbox=(-10, -10, 10, 10), source_file="a.dxf", code="ES-003")]
    ia = _dato(_estribos("E#3"), "ia", "ES-003", "IA · SECCIÓN 1 30X60 E#3")
    defs = {
        "CTA-5 (SECCIÓN 1)": Definicion(
            marca="CTA-5 (SECCIÓN 1)", familia="contratrabe", estribos=ia
        )
    }
    inv = ScheduleInventory(
        rechazos=[
            _rech(t.text, "sin_dueno", [], hoja="ES-003", eid=t.entity_id) for t in (estribo, lejos)
        ]
    )
    f = [
        x
        for x in _run(defs=defs, inv=inv, entities=[corte, seccion, estribo, lejos], frames=frames)
        if "lectura IA" in x.mensaje
    ]
    assert f[0].severidad == "duda" and "CCEAF" in f[0].mensaje and "CCE17" not in f[0].mensaje


def test_10_a_text_a_detection_took_is_never_recall_wherever_its_box_lies():
    t = _texto("T-5", 1, 1)
    d = _det("T-5", "trabe", entidades=[t.entity_id], x=60, y=60)  # its box is its span, far off
    assert not _all(_run(defs=["T-5"], **_planta_con(t, dets=[d])), 10)


def test_11_a_text_beside_a_section_but_attributed_to_another_mark_is_not_its():
    ajeno = _texto("E#3", 2.2, 1.0, eid="ent_ajeno", handle="BBBB1")
    inv = ScheduleInventory(
        rechazos=[
            _rech("E#3", "sin_dueno", [], hoja="ES-002", posibles=["CTA-2"], eid="ent_ajeno")
        ],
        secciones_dibujadas=[
            SeccionDibujada(marca="CTA-1", caja=(1.0, 0.8, 2.0, 2.0), hoja="ES-002", titulo_id="t")
        ],
    )
    assert not _con(_run(inv=inv, entities=[ajeno]), 11, "Armado de CTA-1")


def test_11_a_family_the_ai_states_against_the_prefix_is_a_duda():
    d = _defn("D-1C", "dado")
    d.avisos = [
        "familia: el plano no la dice (sólo el prefijo de la marca: dala); se toma la de la IA: "
        "dado"
    ]
    assert _one(_run(defs={"D-1C": d}), 11).severidad == "duda"


# ------------------------------------------- el inventario lleva las secciones de los títulos


def _cota(entity_id, p, q, cm):
    horizontal = abs(p[1] - q[1]) < abs(p[0] - q[0])
    x0, x1 = min(p[0], q[0]), max(p[0], q[0])
    y0, y1 = min(p[1], q[1]), max(p[1], q[1])
    bbox = (x0, y0 - 0.18, x1, y1) if horizontal else (x0, y0, x1 + 0.18, y1)
    return NormalizedEntity(
        entity_id=entity_id,
        entity_type=EntityType.dimension,
        source_file="a.dxf",
        layer="COTAS",
        bbox=bbox,
        raw_handle=entity_id,
        properties={
            "display_value": float(cm),
            "dimlfac": 100.0,
            "measurement": cm / 100.0,
            "measured_segment": [p, q],
        },
        evidence=EvidencePacket(source="a.dxf", method="t"),
    )


def _rectangulo(entity_id, x0, y0, x1, y1):
    puntos = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return NormalizedEntity(
        entity_id=entity_id,
        entity_type=EntityType.polyline,
        source_file="a.dxf",
        layer="DETALLES",
        bbox=(x0, y0, x1, y1),
        points=puntos,
        raw_handle=entity_id,
        properties={"closed": True},
        evidence=EvidencePacket(source="a.dxf", method="t"),
    )


def test_the_inventory_carries_each_titles_drawn_section_with_its_box():
    from klave_engine.detection.schedules import build_schedule_inventory
    from klave_engine.detection.text_patterns import TextPatternConfig

    def centrado(eid, texto, x, y, alto):
        ancho = 0.6 * len(texto) * alto
        t = _texto(texto, x - ancho / 2, y - alto / 2, h=alto, eid=eid, handle=eid)
        return t

    ents = [
        centrado("am", "K-5", 0.0, 0.0, 0.13),
        _texto("6#4", -0.2, 0.13, h=0.10, eid="ar0", handle="ar0"),
        _texto("EYG#3@15", -0.2, 0.31, h=0.10, eid="ar1", handle="ar1"),
        _rectangulo("ac", -0.5, 0.9, 0.5, 2.4),
        _cota("ah", (-0.5, 0.9), (0.5, 0.9), 20),
        _cota("av", (0.5, 2.4), (0.5, 0.9), 30),
    ]
    inv = build_schedule_inventory(ents, TextPatternConfig(), unit_to_m=1.0)
    (seccion,) = [s for s in inv.secciones_dibujadas if s.marca == "K-5"]
    assert seccion.caja == pytest.approx((-0.5, 0.9, 0.5, 2.4)) and seccion.titulo_id == "am"


def test_10_structural_detections_outside_every_structural_planta_are_said():
    fuera = _det("K-1", x=500, y=500)
    seg = _seg({})  # the segmentation gave it no view
    v = _run(defs=["K-1"], detections=[fuera], seg=seg)
    f = _con(v, 10, "no se cuentan")
    assert len(f) == 1 and f[0].severidad == "aviso" and "fuera de toda vista" in f[0].mensaje


def test_11_what_the_rules_reading_warns_is_said_once():
    r = reglas_estandar()
    r.avisos = [
        "El recubrimiento de castillo va de 3.0 a 5.0 cm (la nota 4); se toma el mínimo (3.0 cm)."
    ]
    f = _con(_run(reglas=r), 11, "Las reglas del plano")
    assert len(f) == 1 and "se toma el mínimo" in f[0].mensaje
