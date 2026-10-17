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
from klave_engine.estructura.textos import ancla_texto

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
        assert any(a.startswith("estribos: no se lee de la pila bajo su sección («E#3@12»)")
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


def _secciones_en_lugar_de_etiquetas(ents, de_quien, semilla, grande, titulos=True):
    """Cada etiqueta «K-n» de un cuadro al azar se vuelve una sección: su arista del lado de su
    pila donde estaba la de la etiqueta; con ``grande``, 1–2.5 veces su ancho y 0.2–0.9 de alto,
    hacia el lado contrario a su pila. Su título (el mismo texto) va del otro lado de la sección
    (sin ``titulos``, no va)."""
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
        if mios:
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


def _ni_ajena_ni_a_medias(cuadro, semilla, grande, titulos):
    ents, de_quien = cuadro
    nuevos, secciones, propios = _secciones_en_lugar_de_etiquetas(
        ents, de_quien, semilla, grande, titulos
    )
    libres = {e.entity_id for e in ents if e.is_textual}
    asoc, _ = asociar_secciones(nuevos, _marco(nuevos), C, secciones, libres)
    for a in asoc:
        assert set(a.entidades) == propios.get(a.marca, set()), (semilla, a.marca, a.textos)
    return len(asoc)


def test_a_long_line_under_the_next_section_puts_the_stack_in_doubt():
    # Barrida «zigzag», semilla 814, con las secciones del tamaño de las etiquetas y sin títulos:
    # la columna de K-2 («2E#3EXT@10», «4#3») seguía en dos renglones largos de K-1 que pasan
    # también bajo la sección de K-3, que lee hacia el mismo lado y está igual de cerca. K-2 los
    # tomaba (ajenos). Un renglón que está en la columna de otra sección no más lejos de ella deja
    # la pila en duda: no se lee.
    with tempfile.TemporaryDirectory(prefix="t9c_814_") as d:
        cuadro = _cuadro(Path(d), "zigzag", 814)
        assert cuadro is not None
        _ni_ajena_ni_a_medias(cuadro, 814, grande=False, titulos=False)


def test_a_neighbours_column_never_takes_a_stack_just_beyond_its_sections_reach():
    # Barrida «borde», semilla 2481, con secciones del tamaño de las etiquetas y sin títulos: la
    # pila de K-1 empieza apenas fuera del alcance de su sección (0.139 > 0.13) y su último
    # renglón, largo, sigue la columna de K-4, que bajaba hasta él y lo tomaba (ajeno). La pila
    # que una sección casi alcanza le queda enfrente entera (y su columna más allá del corte):
    # la de K-4, que sigue en ella, queda en duda.
    with tempfile.TemporaryDirectory(prefix="t9c_2481_") as d:
        cuadro = _cuadro(Path(d), "borde", 2481)
        assert cuadro is not None
        _ni_ajena_ni_a_medias(cuadro, 2481, grande=False, titulos=False)


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
