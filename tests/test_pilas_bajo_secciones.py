"""Tarea 9c (R147): el armado de un título de detalle se lee de debajo de SU sección dibujada, con
las reglas de la pila (Tarea 6) y sus reglas de reclamo y duda: la sección toma el lugar de la
etiqueta. Lo que se lee es entero y de su marca; lo dudoso no es de nadie; las cajas reclamadas y
las líneas «posible» nunca se leen; las llamadas, lo que va junto a la sección y el alzado se
reportan, nunca se leen; y un campo que el detalle también escribe fuera de la pila no se lee de
ella."""

import random
import tempfile
from pathlib import Path

import pytest
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.schedules import build_schedule_inventory, merge_external_specs
from klave_engine.estructura.asociacion import SeccionDeTitulo, asociar_secciones
from klave_engine.estructura.definiciones import construir_definiciones
from klave_engine.estructura.textos import ancla_texto, caja_de_texto

from tests.test_secciones_de_cotas import (
    _DETALLE,
    C,
    _ce1,
    _cota,
    _flecha,
    _ia,
    _linea,
    _rectangulo,
    _texto,
    _titulo,
)


def _muro(dx=0.0):
    """El muro de block que cuelga bajo la sección de una cadena de enrase (Marina, ES-100)."""
    return [
        _linea(f"m1{dx}", (dx, -1.73), (dx, -2.24)),
        _linea(f"m2{dx}", (dx + 0.854, -1.73), (dx + 0.854, -2.24)),
        _linea(f"m3{dx}", (dx - 0.1, -2.24), (dx + 0.954, -2.24)),
    ]


def _pila_de_ce1(dx=0.0, sufijo=""):
    """«4#3» y «E#2@15» bajo CE-1, donde Marina los escribe (0.71 bajo su sección)."""
    return [
        _texto(f"l1{sufijo}", "4#3", dx + 0.458, -2.468, alto=0.10),
        _texto(f"l2{sufijo}", "E#2@15", dx + 0.458, -2.663, alto=0.10),
    ]


def _cotas(inv, marca, metodo="pila"):
    return [s for s in inv.specs if s.mark == marca and s.metodo == metodo]


def _sin_dueno(inv):
    return {r.texto: r.posibles for r in inv.rechazos if r.motivo == "sin_dueno"}


def test_a_detail_titles_armado_is_read_from_under_its_own_section():
    # R147 (CE-1 de Marina): el título, su sección (15x30) con el muro que cuelga de ella, y bajo
    # todo «4#3» / «E#2@15». Antes nadie los leía (sin dueño) y la IA quedaba bloqueada (R140);
    # ahora son la lectura de CE-1, del detalle, y la IA vuelve a ser sólo una alternativa.
    ents = _ce1() + _muro() + _pila_de_ce1()
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    (pila,) = _cotas(inv, "CE-1")
    assert (pila.source, pila.rebar, pila.stirrups, pila.entidades) == (
        "detalle",
        "4#3",
        "E#2@15",
        ["l1", "l2"],
    )
    assert _sin_dueno(inv) == {}
    merge_external_specs(inv, [_ia("CE-1", family="dala", rebar="4#4", stirrups="E#3@20")], C)
    d = construir_definiciones(inv, C)[0]["CE-1"]
    assert d.longitudinales.fuente == "detalle" and d.estribos.fuente == "detalle"
    assert [a.fuente for a in d.longitudinales.alternativas] == ["ia"]
    assert d.sin_leer == {}


def test_two_details_side_by_side_never_mix_their_stacks():
    # CE-1 y CE-2 de Marina, lado a lado (1.932 entre sus esquinas): cada uno lee la suya.
    ce2 = _ce1(dx=1.932, marca="CE-2")
    for e in ce2:
        e.entity_id = e.raw_handle = e.entity_id + "2"
    ents = (
        _ce1() + _muro() + _pila_de_ce1()
        + ce2 + _muro(1.932)
        + [_texto("k1", "6#3", 1.932 + 0.458, -2.468, alto=0.10),
           _texto("k2", "E#2@15", 1.932 + 0.458, -2.663, alto=0.10)]
    )  # fmt: skip
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    leidas = {s.mark: (s.rebar, s.stirrups) for s in inv.specs if s.metodo == "pila"}
    assert leidas == {"CE-1": ("4#3", "E#2@15"), "CE-2": ("6#3", "E#2@15")}


def _seccion(n, x0, y0, x1, y1, marca, lee=True, sentidos=(-1,), titulo=""):
    return SeccionDeTitulo(
        marca=marca, caja=(x0, y0, x1, y1), archivo="a.dxf", titulo_id=titulo, lee=lee,
        sentidos=sentidos,
    )  # fmt: skip


def _marco(ents):
    return [SheetFrame(frame_id="f0", bbox=(-20, -20, 20, 20), source_file="a.dxf", code="ES-1")]


def test_a_line_two_sections_reach_alike_is_nobodys():
    # Un renglón bajo el hueco entre dos secciones, a la misma distancia de las dos: de cuál es no
    # se sabe; no se lee.
    ents = [_texto("r", "4#3", 1.0, -0.5, alto=0.10)]
    secciones = [
        _seccion(0, 0.0, 0.0, 0.95, 1.0, "T-1"),
        _seccion(1, 1.05, 0.0, 2.0, 1.0, "T-2"),
    ]
    asoc, dudosos = asociar_secciones(ents, _marco(ents), C, secciones, {"r"})
    assert asoc == [] and dudosos == {"r": {"T-1", "T-2"}}


def test_nothing_is_read_on_the_titles_side():
    # El renglón entre el título y su sección (encima de ella) no es su pila: la pila va del lado
    # contrario al título.
    ents = [_texto("r", "4#3", 0.4, 1.2, alto=0.10)]
    asoc, _ = asociar_secciones(ents, _marco(ents), C, [_seccion(0, 0, 0, 0.8, 1.0, "T-1")], {"r"})
    assert asoc == []


def test_claimed_and_free_sections_compete_but_are_never_read():
    # Una sección que sólo se reclama (o que no es de nadie) junto a la del título: su armado no
    # es del título vecino, y de ella no se lee nada.
    ents = [
        _texto("a", "4#3", 0.4, -0.3, alto=0.10),
        _texto("b", "6#4", 1.6, -0.3, alto=0.10),
    ]
    secciones = [
        _seccion(0, 0.0, 0.0, 0.8, 1.0, "T-1"),
        _seccion(1, 1.2, 0.0, 2.0, 1.0, "", lee=False, sentidos=(+1, -1)),
    ]
    asoc, _ = asociar_secciones(ents, _marco(ents), C, secciones, {"a", "b"})
    assert [(a.marca, a.textos) for a in asoc] == [("T-1", ["4#3"])]


def _t_con_alzado(alzado: bool):
    """Un detalle de trabe como T1-2 de Marina (15x45): su título, su sección (cerrada, con sus
    cotas), «E#3@12» bajo ella y una llamada «2#6» con su directriz a la sección; con ``alzado``,
    el alzado a la derecha, a la misma altura, con su distribución de estribos."""
    ents = [
        _titulo("t", "T1-2", 0.1, 1.95, alto=0.14),
        _rectangulo("s", 0.0, 0.0, 0.755, 1.744),
        _cota("h", (0.0, 0.0), (0.755, 0.0), 15),
        _cota("v", (0.0, 1.744), (0.0, 0.0), 45),
        _texto("e", "E#3@12", 0.38, -0.35, alto=0.11),
        _texto("c", "2#6", 1.19, -0.2, alto=0.11),
        _flecha("f", [(1.0, -0.26), (1.35, -0.26), (0.6, 0.15)]),
    ]
    if alzado:
        ents += [
            _linea("z1", (1.8, 0.0), (8.0, 0.0)),
            _linea("z2", (1.8, 1.744), (8.0, 1.744)),
            _texto("z3", "1@6,8@10", 2.3, -0.15, alto=0.10),
            _texto("z4", "@15", 5.0, -0.15, alto=0.10),
        ]
    return ents


@pytest.mark.parametrize("alzado", [False, True])
def test_a_field_the_detail_also_writes_elsewhere_is_never_read_from_the_stack(alzado):
    # R147: «E#3@12» bajo la sección es todo lo que el detalle dice de sus estribos si no hay
    # alzado: se lee. Con el alzado, que escribe la distribución («1@6,8@10», «@15»), la pila es
    # sólo una parte: no se lee, se cita, y el campo queda reclamado (la IA no lo llena). La llamada
    # «2#6» nunca es un renglón de la pila: es de su flecha (E3); sigue bloqueando la IA.
    inv = build_schedule_inventory(_t_con_alzado(alzado), C, unit_to_m=1.0, detail_boxes=_DETALLE)
    (pila,) = _cotas(inv, "T1-2")
    assert pila.entidades == ["e"] and pila.rebar is None
    merge_external_specs(inv, [_ia("T1-2", family="trabe", rebar="4#6", stirrups="E#3@20")], C)
    d = construir_definiciones(inv, C)[0]["T1-2"]
    if alzado:
        assert pila.stirrups is None and pila.campos_con_texto == ["estribos"]
        # R192: dicho como duda, nunca como hecho.
        assert any(a.startswith("estribos: un texto que puede ser de T1-2 fuera de la pila bajo")
                   and a.endswith("no se lee de la pila («E#3@12»)")
                   for a in pila.avisos)  # fmt: skip
        assert d.estribos.ilegible and d.estribos.fuente == "detalle"
    else:
        assert pila.stirrups == "E#3@12"
        assert d.estribos.fuente == "detalle" and d.estribos.valor[0].numero == "3"
    assert _sin_dueno(inv)["2#6"] == ["T1-2"]
    assert d.longitudinales is None and "longitudinales" in d.sin_leer


def test_a_text_at_the_sections_corner_is_never_a_stack_line():
    # CTA-1 de Marina (ES-002): su «E#4» va junto a la esquina de abajo de su sección, metido en
    # su altura: no está bajo ella; no se lee (la separación va en su alzado).
    ents = [
        _titulo("t", "CTA-1", 0.27, 3.29, alto=0.14),
        _rectangulo("s", 0.0, 0.0, 1.325, 3.136),
        _cota("h", (0.0, 0.0), (1.325, 0.0), 35),
        _cota("v", (0.0, 3.136), (0.0, 0.0), 80),
        _texto("e", "E#4", 1.627, -0.028, alto=0.11),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert _cotas(inv, "CTA-1") == []
    assert _sin_dueno(inv) == {"E#4": ["CTA-1"]}


def test_a_claimed_box_is_never_read():
    # R164: una sección que alcanzan dos títulos por igual (R111) es de los dos y de ninguno: su
    # armado bloquea a los dos, nunca se lee.
    ents = [
        _titulo("a", "T-1", 0.1, 0.3, alto=0.14),
        _titulo("b", "T-2", 0.55, 0.3, alto=0.14),
        _rectangulo("s", 0.0, -2.0, 1.0, 0.0),
        _cota("h", (0.0, -2.0), (1.0, -2.0), 30),
        _cota("v", (1.0, -2.0), (1.0, 0.0), 60),
        _texto("r", "3#6", 0.5, -2.35, alto=0.11),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [s for s in inv.specs if s.metodo == "pila"] == []
    assert _sin_dueno(inv) == {"3#6": ["T-1", "T-2"]}


# ------------------------------------------------- las familias de la Tarea 6, con secciones


def _secciones_en_lugar_de_etiquetas(
    ents, de_quien, semilla, grande, titulos=True, lado_al_azar=False
):
    """Cada etiqueta «K-n» de un cuadro al azar se vuelve una sección: su arista del lado de su
    pila donde estaba la de la etiqueta; con ``grande``, 1–2.5 veces su ancho y 0.2–0.9 de alto,
    hacia el lado contrario a su pila. Su título (el mismo texto) va del otro lado de la sección
    (sin ``titulos``, no va). El lado que lee la sección es el de su pila; con ``lado_al_azar``
    (R189), uno al azar, que nunca sale de dónde está su pila: su título va del otro lado."""
    from klave_engine.estructura.textos import caja_de_texto

    def caja(e):
        (ax, ay), (dx0, dx1, dy0, dy1, _a) = ancla_texto(e), caja_de_texto(e, 0.0)
        return ax + dx0, ay + dy0, ax + dx1, ay + dy1

    rnd = random.Random(semilla * 7919 + 17)
    propios: dict[str, set[str]] = {}
    for e in ents:
        if e.is_textual:
            clave = (e.text, round(ancla_texto(e)[0], 3), round(ancla_texto(e)[1], 3))
            if clave in de_quien:
                propios.setdefault(de_quien[clave], set()).add(e.entity_id)
    por_id = {e.entity_id: e for e in ents}
    etiquetas = [e for e in ents if e.is_textual and (e.text or "").startswith("K-")
                 and (e.properties.get("height") or 0) > 0.12]  # fmt: skip
    nuevos = [e for e in ents if e not in etiquetas]
    secciones = []
    for e in etiquetas:
        x0, y0, x1, y1 = caja(e)
        mios = propios.get(e.text or "", set())
        if lado_al_azar:
            lado = rnd.choice((+1, -1))
        elif mios:
            ym = sum((caja(por_id[i])[1] + caja(por_id[i])[3]) / 2 for i in mios) / len(mios)
            lado = +1 if ym > (y0 + y1) / 2 else -1
        else:
            lado = rnd.choice((+1, -1))
        if grande:
            w, h, cx = (x1 - x0) * rnd.uniform(1.0, 2.5), rnd.uniform(0.2, 0.9), (x0 + x1) / 2
            bx = (cx - w / 2, y1 - h, cx + w / 2, y1) if lado > 0 else (cx - w / 2, y0, cx + w / 2,
                                                                         y0 + h)  # fmt: skip
        else:
            bx = (x0, y0, x1, y1)
        secciones.append(
            SeccionDeTitulo(
                marca=e.text or "",
                caja=bx,
                archivo=e.source_file,
                titulo_id=e.entity_id + "_t",
                sentidos=(lado,),
            )
        )
        if not titulos:
            continue
        titulo = e.model_copy(deep=True)
        dy = (bx[1] - 0.05 - (y1 - y0)) - y0 if lado > 0 else (bx[3] + 0.05) - y0
        titulo.properties = {
            k: ((v[0], v[1] + dy) if k in ("insert", "align_point") and v is not None else v)
            for k, v in titulo.properties.items()
        }
        titulo.bbox = (titulo.bbox[0], titulo.bbox[1] + dy, titulo.bbox[2], titulo.bbox[3] + dy)
        titulo.entity_id = titulo.raw_handle = e.entity_id + "_t"
        nuevos.append(titulo)
    return nuevos, secciones, propios


@pytest.mark.parametrize("grande", [False, True])
@pytest.mark.parametrize("mezcla,sin_pila", [(False, False), (True, False), (True, True)])
def test_a_sweep_of_the_reviewers_cuadros_with_sections(mezcla, sin_pila, grande):
    """Las familias del revisor (Tarea 6, R55) con secciones en lugar de etiquetas: ninguna pila
    ajena, ninguna a medias, y se lee algo."""
    from tests.test_estructura_asociacion import _cuadro_del_revisor

    legibles = leidos = 0
    with tempfile.TemporaryDirectory(prefix="t9c_barrida_") as d:
        for semilla in range(120):
            cuadro = _cuadro_del_revisor(Path(d), semilla, mezcla, sin_pila)
            if cuadro is None:
                continue
            ents, de_quien = cuadro
            nuevos, secciones, propios = _secciones_en_lugar_de_etiquetas(
                ents, de_quien, semilla, grande
            )
            libres = {e.entity_id for e in ents if e.is_textual}
            asoc, _ = asociar_secciones(nuevos, _marco(nuevos), C, secciones, libres)
            for a in asoc:
                assert set(a.entidades) == propios.get(a.marca, set()), (semilla, a.marca, a.textos)
            legibles += 1
            leidos += len(asoc)
    assert legibles >= 10 and leidos >= legibles // 2


def _cuadro(d, familia, semilla):
    """Un cuadro de las familias de la Tarea 6 (sus mismos sorteos), o ``None`` si no se lee: dos
    textos que se tocan o, en «borde», un renglón fuera del ensanche de su etiqueta (la salvedad
    a de R58, que la barrida de la Tarea 6 también salta)."""
    import tests.test_estructura_asociacion as ta

    if familia in ("azar", "azar_mezcla"):
        ents, de_quien = ta._cuadro_al_azar(d, semilla, familia == "azar_mezcla")
        return None if ta._se_tocan(ents) else (ents, de_quien)
    if familia == "largo":
        ents, de_quien = ta._cuadro_largo(d, semilla)
    elif familia in ("zigzag", "ambos"):
        ents, de_quien = ta._cuadro_mezclado(d, semilla, familia)
    else:
        ents, de_quien = ta._cuadro_de_lado(d, semilla, familia)
        if ents is not None and familia == "borde" and ta._fuera_del_ensanche(ents, de_quien):
            return None
    return None if ents is None else (ents, de_quien)


def _ni_ajena_ni_a_medias(cuadro, semilla, grande, titulos, al_azar=False):
    ents, de_quien = cuadro
    nuevos, secciones, propios = _secciones_en_lugar_de_etiquetas(
        ents, de_quien, semilla, grande, titulos, al_azar
    )
    libres = {e.entity_id for e in ents if e.is_textual}
    asoc, _ = asociar_secciones(nuevos, _marco(nuevos), C, secciones, libres)
    for a in asoc:
        assert set(a.entidades) == propios.get(a.marca, set()), (semilla, a.marca, a.textos)
    return len(asoc)


# R189: las semillas de las barridas que leían una pila ajena o a medias. Cada una la deja hoy en
# duda al menos una regla; las marcadas, sólo una (en rojo sin ella).
_SEMILLAS = [
    # «zigzag», 814 (en rojo sin el «casi» de la columna entera): la columna de K-2 seguía en dos
    # renglones largos de K-1 que K-3 casi alcanza.
    ("zigzag", 814, False, False, False),
    # «borde», 974 (en rojo sin la competencia del lado del título): K-10 tomaba «8#6 / 12#8+8#6…».
    ("borde", 974, True, True, False),
    # «borde», 3823 (el revisor; en rojo sin la columna contigua): K-3 tomaba de enfrente
    # «12#8+8#6…» saltando «E#4@10», a un lado entre la sección y él.
    ("borde", 3823, True, True, False),
    # «azar_mezcla», 8029, lado al azar (en rojo sin la columna cerrada): la columna de K-3 subía
    # por la pila de K-4 hasta su sección; lo que sigue al último renglón a menos de un hueco entre
    # renglones (la caja de otra sección) la deja en duda.
    ("azar_mezcla", 8029, False, False, True),
    # «borde», 2481; «revisor_sinpila», 4040; «borde», 5551 y 8551; «revisor_sinpila», 7213 (el
    # revisor); «revisor_mezcla», 2776 con el lado al azar: dos reglas o más las dejan en duda.
    ("borde", 2481, False, False, False),
    ("revisor_sinpila", 4040, False, False, False),
    ("borde", 5551, False, True, False),
    ("borde", 8551, False, True, False),
    ("revisor_sinpila", 7213, True, True, False),
    ("revisor_mezcla", 2776, False, False, True),
]


def _cuadro_de(d, familia, semilla):
    if familia.startswith("revisor"):
        from tests.test_estructura_asociacion import _cuadro_del_revisor

        return _cuadro_del_revisor(d, semilla, "mezcla" in familia, "sinpila" in familia)
    return _cuadro(d, familia, semilla)


@pytest.mark.parametrize("familia,semilla,grande,titulos,al_azar", _SEMILLAS)
def test_the_seeds_that_read_a_foreign_or_partial_stack_now_doubt_it(
    familia, semilla, grande, titulos, al_azar
):
    with tempfile.TemporaryDirectory(prefix="t9c_semilla_") as d:
        cuadro = _cuadro_de(Path(d), familia, semilla)
        assert cuadro is not None
        _ni_ajena_ni_a_medias(cuadro, semilla, grande, titulos, al_azar)


def test_a_section_takes_a_stack_only_in_front_of_it():
    # R189 (T3-19 y T4-4 de Marina): «E#3@15» bajo la sección pero a su lado (en su ensanche, sin
    # encimarse con ella): una caja dibujada no se ensancha; no se lee.
    ents = [_texto("r", "E#3@15", 1.2, -0.2, alto=0.10)]
    asoc, _ = asociar_secciones(
        ents, _marco(ents), C, [_seccion(0, 0.0, 0.0, 0.8, 1.0, "T-1")], {"r"}
    )
    assert asoc == []


@pytest.mark.parametrize("titulos", [True, False])
@pytest.mark.parametrize("grande", [False, True])
@pytest.mark.parametrize("familia", ["largo", "azar_mezcla", "zigzag", "ambos", "lado", "borde"])
def test_a_sweep_of_task_6s_other_families_with_sections(familia, grande, titulos):
    """Las demás familias de la Tarea 6 con secciones en lugar de etiquetas (con y sin títulos):
    ninguna pila ajena ni a medias."""
    revisados = 0
    with tempfile.TemporaryDirectory(prefix="t9c_familias_") as d:
        for semilla in range(800, 900):
            cuadro = _cuadro(Path(d), familia, semilla)
            if cuadro is None:
                continue
            _ni_ajena_ni_a_medias(cuadro, semilla, grande, titulos)
            revisados += 1
    assert revisados >= 3


@pytest.mark.parametrize("familia", ["revisor_sinpila", "largo", "lado", "borde"])
def test_a_sweep_with_the_reading_side_at_random(familia):
    """R189: el lado que lee cada sección al azar, nunca de dónde está su pila (su título del
    otro lado): en los cuadros bien planteados, ninguna pila ajena ni a medias."""
    revisados = 0
    with tempfile.TemporaryDirectory(prefix="t9c_azar_") as d:
        for semilla in range(900, 1100):
            cuadro = _cuadro_de(Path(d), familia, semilla)
            if cuadro is None or cuadro[0] is None:
                continue
            ents, de_quien = cuadro
            nuevos, secciones, propios = _secciones_en_lugar_de_etiquetas(
                ents, de_quien, semilla, False, False, True
            )
            if not _bien_planteado(nuevos, secciones, propios):
                continue
            libres = {e.entity_id for e in ents if e.is_textual}
            asoc, _ = asociar_secciones(nuevos, _marco(nuevos), C, secciones, libres)
            for a in asoc:
                assert set(a.entidades) == propios.get(a.marca, set()), (semilla, a.marca)
            revisados += 1
    assert revisados >= 5


def test_a_sweep_of_detail_grids():
    """R189: la rejilla de detalles (``_rejilla_de_detalles``): ninguna pila ajena ni a medias, y
    se lee."""
    cuadros = pilas = 0
    for semilla in range(400):
        leidas = _lee_la_rejilla(semilla)
        if leidas is None:
            continue
        cuadros += 1
        for marca, textos, bien in leidas:
            assert bien, (semilla, marca, textos)
            pilas += 1
    assert cuadros >= 40 and pilas >= cuadros


# ------------------------------------------------- R189: la rejilla de detalles


def _rejilla_de_detalles(semilla):
    """R189: filas y columnas de detalles titulados al alcance de Marina: cada sección de lado
    menor 0.5–2.5, su pila de 1 a 4 renglones debajo (o, uno de cada cuatro, encima) a 0.02–0.9
    de su lado menor, alineada a la izquierda, al centro o a la derecha (±0.3), y las vecinas tan
    cerca que las pilas de unas quedan al alcance de otras. El título va del lado contrario a su
    pila; uno de cada cuatro, del lado equivocado (entre la sección y su pila, o a un lado). La
    sección lee del lado contrario a su título, como en el motor (``_secciones_para_pilas``):
    nunca de dónde está su pila. Devuelve los textos, las secciones y los renglones de cada
    marca; ``None`` si dos textos quedan a menos de 0.02."""
    from tests.test_estructura_asociacion import _CORTOS, _LARGOS, _MEDIOS

    rnd = random.Random(semilla)
    ents, secciones, propios, cajas = [], [], {}, []
    n = 0

    def texto(eid, t, x, y, alto, como):
        # Con el ancho que el motor estima (``caja_de_texto``: 0.9 altos por letra).
        ancho = 0.9 * len(t) * alto
        x0 = {"izq": x, "der": x - ancho, "cen": x - ancho / 2}[como]
        e = _texto(eid, t, x0, y, alto=alto, centrado=False)
        e.bbox = (x0, y - alto / 2, x0 + ancho, y + alto / 2)
        ents.append(e)
        cajas.append(e.bbox)
        return e

    y_fila = 0.0
    for _j in range(rnd.randint(1, 3)):
        x, bajo_de_la_fila = 0.0, y_fila
        for _i in range(rnd.randint(2, 4)):
            n += 1
            marca = f"K-{n}"
            w, h = rnd.uniform(0.5, 2.5), rnd.uniform(0.5, 2.5)
            caja = (x, y_fila - h, x + w, y_fila)
            menor = min(w, h)
            arriba = rnd.random() < 0.25
            hueco = rnd.uniform(0.02, 0.9 * menor)
            como = rnd.choice(("izq", "cen", "der"))
            ax = {"izq": caja[0], "cen": (caja[0] + caja[2]) / 2, "der": caja[2]}[como]
            ax += rnd.uniform(-0.3, 0.3)
            renglones = []
            paso = rnd.uniform(0.17, 0.2)
            for k in range(rnd.randint(1, 4)):
                u = rnd.random()
                t = rnd.choice(_LARGOS if u < 0.3 else _MEDIOS if u < 0.6 else _CORTOS)
                if arriba:
                    yc = caja[3] + hueco + 0.05 + k * paso
                else:
                    yc = caja[1] - hueco - 0.05 - k * paso
                renglones.append(texto(f"{marca}r{k}", t, ax, yc, 0.10, como))
            propios[marca] = {e.entity_id for e in renglones}
            # El título: del lado contrario a su pila, o (uno de cada cuatro) del equivocado.
            lado_titulo = -1 if arriba else +1
            donde = "lado" if rnd.random() < 0.1 else "contrario"
            if rnd.random() < 0.25:
                lado_titulo = -lado_titulo
            cx = (caja[0] + caja[2]) / 2
            if donde == "lado":
                ty = rnd.uniform(caja[1], caja[3])
                titulo = texto(f"{marca}t", marca, caja[2] + 0.1, ty, 0.14, "izq")
            elif lado_titulo > 0:
                titulo = texto(f"{marca}t", marca, cx, caja[3] + 0.05 + 0.07, 0.14, "cen")
            else:
                titulo = texto(f"{marca}t", marca, cx, caja[1] - 0.05 - 0.07, 0.14, "cen")
            ty = (titulo.bbox[1] + titulo.bbox[3]) / 2
            secciones.append(
                SeccionDeTitulo(
                    marca=marca, caja=caja, archivo="a.dxf", titulo_id=titulo.entity_id,
                    sentidos=(-1,) if ty > (caja[1] + caja[3]) / 2 else (+1,),
                )
            )  # fmt: skip
            bajo_de_la_fila = min(bajo_de_la_fila, caja[1], *(e.bbox[1] for e in renglones))
            x = max(caja[2], *(e.bbox[2] for e in renglones)) + rnd.uniform(0.05, 0.6)
        y_fila = bajo_de_la_fila - rnd.uniform(0.05, 0.8)
    if not _bien_planteado(ents, secciones, propios):
        return None
    return ents, secciones, propios


def _caja_del_motor(e):
    (ax, ay), (dx0, dx1, dy0, dy1, _a) = ancla_texto(e), caja_de_texto(e, 0.0)
    return ax + dx0, ay + dy0, ax + dx1, ay + dy1


def _bien_planteado(ents, secciones, propios):
    """R189: si un cuadro con secciones se puede leer, con las cajas de texto que estima el motor:
    ningún texto a menos de 0.02 de otro ni sobre una sección; entre cada sección y el último
    renglón de su pila (en el ancho de las dos) nada de otro detalle; y su pila más cerca de su
    sección que de cualquier otra que la tenga en su columna. Una pila más pegada a la sección de
    otro detalle, o que pasa entre otra sección y la pila de ésta, es de ése para quien lea (como
    la salvedad a de R58 en la Tarea 6): ningún lector sabe que es de la suya."""
    cajas = {e.entity_id: _caja_del_motor(e) for e in ents if e.is_textual}
    lista = list(cajas.values())
    for i, a in enumerate(lista):
        for b in lista[i + 1 :]:
            if (
                a[0] < b[2] + 0.02
                and b[0] < a[2] + 0.02
                and a[1] < b[3] + 0.02
                and b[1] < a[3] + 0.02
            ):
                return False
    for s in secciones:
        x0, y0, x1, y1 = s.caja
        if any(b[0] < x1 and x0 < b[2] and b[1] < y1 and y0 < b[3] for b in lista):
            return False

    def hueco(caja, b):
        return b[1] - caja[3] if b[1] >= caja[3] else caja[1] - b[3] if b[3] <= caja[1] else 0

    for s in secciones:
        suyos = [cajas[i] for i in propios.get(s.marca, ()) if i in cajas]
        if not suyos:
            continue
        x0 = min(s.caja[0], *(b[0] for b in suyos))
        x1 = max(s.caja[2], *(b[2] for b in suyos))
        y0 = min(s.caja[1], *(b[1] for b in suyos))
        y1 = max(s.caja[3], *(b[3] for b in suyos))
        ajenos = [b for i, b in cajas.items() if i not in propios[s.marca] and i != s.titulo_id]
        ajenos += [o.caja for o in secciones if o is not s]
        if any(b[0] < x1 and x0 < b[2] and b[1] < y1 and y0 < b[3] for b in ajenos):
            return False
        propio = min(hueco(s.caja, b) for b in suyos)
        for o in secciones:
            if o is not s and any(
                b[0] < o.caja[2] and o.caja[0] < b[2] and hueco(o.caja, b) <= propio for b in suyos
            ):
                return False
    return True


def _marco_de(ents, secciones):
    xs = [v for e in ents for v in (e.bbox[0], e.bbox[2])] + [
        v for s in secciones for v in (s.caja[0], s.caja[2])
    ]
    ys = [v for e in ents for v in (e.bbox[1], e.bbox[3])] + [
        v for s in secciones for v in (s.caja[1], s.caja[3])
    ]
    return [
        SheetFrame(
            frame_id="f0", bbox=(min(xs) - 5, min(ys) - 5, max(xs) + 5, max(ys) + 5),
            source_file="a.dxf", code="ES-1",
        )
    ]  # fmt: skip


def _lee_la_rejilla(semilla):
    """Las pilas que se leen de una rejilla, y si alguna es ajena o a medias."""
    cuadro = _rejilla_de_detalles(semilla)
    if cuadro is None:
        return None
    ents, secciones, propios = cuadro
    libres = {i for ids in propios.values() for i in ids}
    asoc, _ = asociar_secciones(ents, _marco_de(ents, secciones), C, secciones, libres)
    return [(a.marca, a.textos, set(a.entidades) == propios[a.marca]) for a in asoc]


# ------------------------------------------------- ronda de arreglos 1 (R188–R193)


def _con_otro_archivo(ents):
    """Lo mismo, y un texto de otro archivo del proyecto en cualquier parte (la tubería pasa
    todos los archivos del proyecto al inventario)."""
    otro = _texto("otro", "NOTA", 15.0, 15.0, alto=0.1)
    otro.source_file = "b.dxf"
    return [*ents, otro]


@pytest.mark.parametrize("dos_archivos", [False, True])
def test_a_free_section_competes_in_a_project_of_several_files(dos_archivos):
    # R188 (el revisor, adv2): T-1 tiene su sección; a su lado, una sección acotada que no es de
    # nadie. «4#3» y «E#2@15» van bajo la libre, en la banda ensanchada de T-1. La libre compite
    # siempre, con su archivo (el de sus líneas y cotas): con un archivo más en el proyecto, T-1
    # leía «4#3 / E#2@15», ajeno.
    ents = [
        _titulo("t", "T-1", 0.1, 1.2, alto=0.14),
        _rectangulo("s1", 0.0, 0.0, 0.8, 1.0),
        _cota("h1", (0.0, 0.0), (0.8, 0.0), 20),
        _cota("v1", (0.0, 1.0), (0.0, 0.0), 25),
        _rectangulo("s2", 0.9, 0.0, 1.7, 1.0),
        _cota("h2", (0.9, 0.0), (1.7, 0.0), 20),
        _cota("v2", (1.7, 1.0), (1.7, 0.0), 25),
        _texto("b", "4#3", 1.05, -0.3, alto=0.1),
        _texto("c", "E#2@15", 1.05, -0.45, alto=0.1),
    ]
    if dos_archivos:
        ents = _con_otro_archivo(ents)
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert _cotas(inv, "T-1") == []
    assert _sin_dueno(inv) == {"4#3": ["T-1"], "E#2@15": ["T-1"]}


def _cta_con_alzado_debajo():
    """El revisor (adv3): una sección como la de CTA-1 (35×80, 1.325 × 3.136) con sólo su «E#4»
    en la esquina, y 0.6 debajo el alzado de otra trabe (8.5 × 1.4) con sus etiquetas de varillas
    dentro: «2#8» a 0.18 bajo su línea de arriba."""
    return [
        _titulo("t", "CTA-1", 0.27, 3.29, alto=0.14),
        _rectangulo("s", 0.0, 0.0, 1.325, 3.136),
        _cota("h", (0.0, 0.0), (1.325, 0.0), 35),
        _cota("v", (0.0, 3.136), (0.0, 0.0), 80),
        _texto("e", "E#4", 1.627, -0.028, alto=0.11),
        _linea("z1", (-0.5, -0.6), (8.0, -0.6)),
        _linea("z2", (-0.5, -2.0), (8.0, -2.0)),
        _linea("z3", (-0.5, -0.6), (-0.5, -2.0)),
        _linea("z4", (8.0, -0.6), (8.0, -2.0)),
        _texto("b1", "2#8", 0.66, -0.78, alto=0.11),
        _titulo("t2", "T-9", 8.6, -1.3, alto=0.14),
    ]


def test_a_label_inside_another_drawing_is_never_a_stack_line():
    # R190: «2#8» va dentro del alzado de otra trabe (líneas dibujadas arriba y abajo de él, en la
    # banda de la sección): es de ese dibujo, un obstáculo; CTA-1 nunca lee «2#8» (antes: sus
    # longitudinales 2#8, como detalle).
    inv = build_schedule_inventory(
        _cta_con_alzado_debajo(), C, unit_to_m=1.0, detail_boxes=_DETALLE
    )
    assert _cotas(inv, "CTA-1") == []
    assert "2#8" in _sin_dueno(inv)


def test_a_rotated_text_never_stacks_under_a_section():
    # R147, 0° sólo: «E#2@15» girado 90° bajo la sección de CE-1 no es un renglón de su pila.
    girado = _texto("l2", "E#2@15", 0.458, -2.663, alto=0.10)
    girado.rotation = 90.0
    ents = _ce1() + _muro() + [_texto("l1", "4#3", 0.458, -2.468, alto=0.10), girado]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [p.entidades for p in _cotas(inv, "CE-1")] == [["l1"]]


@pytest.mark.parametrize("motivo,leida", [("sin_dueno", True), ("ambigua", False)])
def test_only_a_line_nobody_reads_or_names_can_stack(motivo, leida):
    # R147: sólo un texto cuyo único rechazo es «sin dueño» puede ser renglón de una pila; uno que
    # la Tarea 6 dejó ambiguo entre dos marcas (u otro rechazo con marcas) estorba, nunca se lee.
    from klave_engine.detection.schedules import _pilas_de_secciones
    from klave_engine.estructura.asociacion import Rechazo, hoja_y_llave

    ents = [_titulo("t", "T-1", 0.4, 1.2, alto=0.14), _texto("r", "4#3", 0.4, -0.3, alto=0.10)]
    marcos = _marco(ents)
    rechazo = Rechazo(entidad_id="r", texto="4#3", hoja="ES-1", motivo=motivo,
                      marcas=[] if motivo == "sin_dueno" else ["K-1", "K-2"])  # fmt: skip
    seccion = _seccion(0, 0.0, 0.0, 0.8, 1.0, "T-1", titulo="t")
    pilas, _ = _pilas_de_secciones(
        ents, marcos, C, [seccion], [], [rechazo], hoja_y_llave(marcos), {}
    )
    assert [p.entidades for p in pilas] == ([["r"]] if leida else [])


def test_a_claimed_box_with_a_single_claimant_is_never_read():
    # R158, R147 (T3-21 de Marina): la sección que T3-21 sólo reclama (sin contorno ni par, el
    # rectángulo de sus cotas) es suya y de nadie más; aun así su «E#3@15» nunca se lee de ella:
    # bloquea, como «posible».
    from tests.test_secciones_de_cotas import _t3_21

    ents = _t3_21() + [_texto("e", "E#3@15", 0.454, -0.387, alto=0.11)]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert _cotas(inv, "T3-21") == []
    assert _sin_dueno(inv) == {"E#3@15": ["T3-21"]}


# R189 con la geometría de Marina (en coordenadas de su hoja, sin el dibujo, que no está en el
# repositorio): las reglas que separan las pilas de detalles en filas.


def _en(eid, texto, x0, y0, x1, y1):
    """Un renglón de Marina con la caja que le estima el motor allá (su factor de ancho la da)."""
    from klave_engine.estructura.textos import ANCHO_POR_CARACTER

    alto = round(y1 - y0, 3)
    e = _texto(eid, texto, x0, (y0 + y1) / 2, alto=alto, centrado=False)
    e.bbox = (x0, y0, x1, y1)
    e.properties = {
        **e.properties,
        "width_factor": (x1 - x0) / (ANCHO_POR_CARACTER * alto * len(texto)),
    }
    return e


def _seccion_de(marca, caja, titulo, **otros):
    return SeccionDeTitulo(marca=marca, caja=caja, archivo="a.dxf", titulo_id=titulo, **otros)


def _marco_grande(ents):
    return [
        SheetFrame(frame_id="f0", bbox=(-1000, -1000, 1000, 1000), source_file="a.dxf", code="E")
    ]


def test_a_title_under_the_stack_above_never_takes_it():
    # ES-300: el título de CE-4 va 0.44 bajo la pila de CE-2 («6#3» / «E#2@15»). El título de una
    # sección no casi alcanza otra pila (la suya es la de su sección): las dos se leen.
    ents = [
        _en("t2", "CE-2", 218.861, -21.176, 219.433, -21.026),
        _en("a", "6#3", 219.0, -24.055, 219.253, -23.955),
        _en("b", "E#2@15", 218.86, -24.25, 219.393, -24.15),
        _en("t4", "CE-4", 218.015, -24.837, 218.593, -24.687),
        _en("c", "4#4", 218.155, -27.934, 218.412, -27.834),
        _en("d", "E#3@16", 218.019, -28.13, 218.548, -28.03),
    ]
    secciones = [
        _seccion_de("CE-2", (218.61, -23.25, 219.58, -21.54), "t2", sentidos=(-1,)),
        _seccion_de("CE-4", (217.77, -27.13, 218.74, -25.2), "t4", sentidos=(-1,)),
    ]
    asoc, _ = asociar_secciones(ents, _marco_grande(ents), C, secciones, {"a", "b", "c", "d"})
    assert sorted((a.marca, a.textos) for a in asoc) == [
        ("CE-2", ["6#3", "E#2@15"]),
        ("CE-4", ["4#4", "E#3@16"]),
    ]


def test_a_section_below_a_stack_takes_it_only_if_clearly_nearer():
    # ES-100: la pila de CE-1 va a 0.71 de su sección y a 0.82 de la de CE-3, bajo ella, con el
    # título de CE-3 en medio. CE-3 compite del lado de su título (puede estar del lado
    # equivocado), pero su título va del lado de la costumbre de la hoja (encima, como el de CE-1):
    # sólo se la quitaría si estuviera claramente más pegada. Las dos se leen.
    ents = [
        _en("t1", "CE-1", 197.691, 38.342, 198.198, 38.492),
        _en("a", "4#3", 197.86, 35.462, 198.113, 35.562),
        _en("b", "E#2@15", 197.72, 35.267, 198.253, 35.367),
        _en("t3", "CE-3", 198.668, 34.808, 199.239, 34.958),
        _en("c", "6#4", 198.828, 31.928, 199.085, 32.028),
        _en("d", "E#3@14", 198.687, 31.733, 199.225, 31.833),
    ]
    secciones = [
        _seccion_de("CE-1", (197.53, 36.27, 198.38, 37.98), "t1", sentidos=(-1,)),
        _seccion_de("CE-3", (198.12, 32.74, 199.83, 34.45), "t3", sentidos=(-1,)),
    ]
    asoc, _ = asociar_secciones(ents, _marco_grande(ents), C, secciones, {"a", "b", "c", "d"})
    assert sorted((a.marca, a.textos) for a in asoc) == [
        ("CE-1", ["4#3", "E#2@15"]),
        ("CE-3", ["6#4", "E#3@14"]),
    ]


def test_a_cuadro_section_never_almost_reaches_a_detail_stack():
    # R195 (ES-300): la sección de K-5, cuya pila ya leyó su etiqueta de cuadro, compite de su lado
    # (hacia arriba) sin leerse; la pila de CE-4 le queda a 1.97, dentro del doble de su alcance.
    # Lo de más allá de su alcance no puede ser suyo: CE-4 lee su pila.
    ents = [
        _en("t4", "CE-4", 218.015, -24.837, 218.593, -24.687),
        _en("c", "4#4", 218.155, -27.934, 218.412, -27.834),
        _en("d", "E#3@16", 218.019, -28.13, 218.548, -28.03),
        _en("k5", "K-5", 217.603, -32.488, 217.981, -32.358),
    ]
    secciones = [
        _seccion_de("CE-4", (217.77, -27.13, 218.74, -25.2), "t4", sentidos=(-1,)),
        _seccion_de("K-5", (217.29, -31.59, 218.3, -30.0), "k5", sentidos=(+1,), lee=False,
                    de_cuadro=True),
    ]  # fmt: skip
    asoc, _ = asociar_secciones(ents, _marco_grande(ents), C, secciones, {"c", "d"})
    assert [(a.marca, a.textos) for a in asoc] == [("CE-4", ["4#4", "E#3@16"])]
