"""R212, R218: el recubrimiento que la sección dibujada de un cuadro acota en sus esquinas (las
cotas de la esquina del contorno a la esquina de un estribo dibujado) es un dato
``seccion_dibujada`` de la marca, por hoja, y le gana al rango de la nota («3.0 A 5.0 CM LIBRES EN
CASTILLOS»). Lo dudoso (una sola esquina, valores distintos) y lo que no es un recubrimiento (a un
centro de varilla, una separación de varillas, fuera del rango de la nota) no se toma: se dice."""

from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.schedules import build_schedule_inventory
from klave_engine.estructura.dato import Dato
from klave_engine.estructura.definiciones import construir_definiciones
from klave_engine.estructura.reglas import reglas_estandar

from tests.test_estructura_elementos import _construir, _seg, _tag
from tests.test_secciones_de_cotas import C, _castillo, _cota, _cotas, _poligono


def _diagonal(n, esquina, adentro, cm):
    return _cota(n, esquina, adentro, cm)


def _estribo_en(n, punto, hacia):
    """La esquina de un estribo dibujado en ``punto``: dos trazos abiertos hacia adentro."""
    (px, py), (sx, sy) = punto, hacia
    return _poligono(n, [(px + 0.2 * sx, py), (px, py), (px, py + 0.2 * sy)], cerrado=False)


def _con_recubrimientos(marca, x, y, cms, hoja_n="a"):
    """Un castillo de cuadro (sección 20×30 encima de su pila) con una cota de recubrimiento en
    diagonal por cada valor de ``cms``, cada una en una esquina."""
    x0, y0, x1, y1 = (x - 0.5, y + 0.9, x + 0.5, y + 2.4)
    ents = _castillo(hoja_n, marca, x, y, ["6#4", "EYG#3@15"], (x0, y0, x1, y1), 20, 30)
    esquinas = [((x0, y0), (x0 + 0.1, y0 + 0.1)), ((x1, y1), (x1 - 0.1, y1 - 0.1)),
                ((x0, y1), (x0 + 0.1, y1 - 0.1)), ((x1, y0), (x1 - 0.1, y0 + 0.1))]  # fmt: skip
    for i, cm in enumerate(cms):
        esquina, adentro = esquinas[i]
        ents.append(_diagonal(f"{hoja_n}r{i}d", esquina, adentro, cm))
        hacia = (1 if adentro[0] > esquina[0] else -1, 1 if adentro[1] > esquina[1] else -1)
        ents.append(_estribo_en(f"{hoja_n}r{i}e", adentro, hacia))
    return ents


def test_the_cover_drawn_at_the_corners_is_read():
    inv = build_schedule_inventory(_con_recubrimientos("K-12", 0.0, 0.0, [4, 4, 4]), C, 1.0)
    (k,) = _cotas(inv, "K-12")
    assert k.section_cm == (20, 30) and k.recubrimiento_cm == 4
    assert not any("recubrimiento" in a for a in k.avisos)


def test_a_doubtful_drawn_cover_is_said_not_taken():
    una = build_schedule_inventory(_con_recubrimientos("K-1", 0.0, 0.0, [4]), C, 1.0)
    (k,) = _cotas(una, "K-1")
    assert k.recubrimiento_cm is None and any("una sola esquina" in a for a in k.avisos)
    assert k.recubrimiento_sin_tomar == "acota 4 cm en una sola esquina leída"
    distintas = build_schedule_inventory(_con_recubrimientos("K-1", 0.0, 0.0, [3, 4]), C, 1.0)
    (k,) = _cotas(distintas, "K-1")
    assert k.recubrimiento_cm is None and any("distintos (3, 4)" in a for a in k.avisos)
    # una cota en diagonal que no sale de una esquina no es un recubrimiento
    ents = _castillo("a", "K-1", 0.0, 0.0, ["4#3"], (-0.5, 0.9, 0.5, 2.4), 20, 30)
    ents += [_cota("x1", (-0.2, 1.2), (-0.1, 1.3), 3), _cota("x2", (0.2, 1.2), (0.1, 1.3), 3)]
    (k,) = _cotas(build_schedule_inventory(ents, C, 1.0), "K-1")
    assert k.recubrimiento_cm is None


def test_the_drawn_cover_is_a_dato_of_the_mark_by_sheet_and_beats_the_note():
    inv = build_schedule_inventory(_con_recubrimientos("K-12", 0.0, 0.0, [4, 4]), C, 1.0)
    for s in inv.specs:
        s.hoja = "ES-100"
    otra = build_schedule_inventory(_con_recubrimientos("K-12", 0.0, 0.0, [3, 3], "b"), C, 1.0)
    for s in otra.specs:
        s.hoja = "ES-300"
    inv.specs += otra.specs
    defs = construir_definiciones(inv, C)[0]
    cover = defs["K-12"].recubrimiento_m
    valores = {cover.valor, *(a.valor for a in cover.alternativas)}
    assert cover.fuente == "seccion_dibujada" and valores == {0.04, 0.03}
    reglas = reglas_estandar()
    cubre = dict(reglas.recubrimiento_m)
    cubre["castillo"] = Dato(valor=0.03, fuente="nota", hoja="ES-100",
                             texto="3.0 A 5.0 CM LIBRES EN CASTILLOS")  # fmt: skip
    reglas = reglas.model_copy(update={"recubrimiento_m": cubre})
    a, b = _tag("K-12"), _tag("K-12")
    seg = _seg({a.detection_id: "v_100", b.detection_id: "v_300"}, plan=("v_100", "v_300"))
    marcos = [
        SheetFrame(frame_id=v, code=c, bbox=(0, 0, 1, 1), title=c)
        for v, c in (("v_100", "ES-100"), ("v_300", "ES-300"))
    ]
    por_hoja = {
        e.hoja: e.recubrimiento_m
        for e in _construir([a, b], seg, defs, {}, reglas=reglas, frames=marcos)
    }
    assert (por_hoja["ES-100"].valor, por_hoja["ES-100"].fuente) == (0.04, "seccion_dibujada")
    assert (por_hoja["ES-300"].valor, por_hoja["ES-300"].fuente) == (0.03, "seccion_dibujada")
    # la nota queda como alternativa: nada se pierde
    assert any(x.fuente == "nota" for x in por_hoja["ES-100"].alternativas)


def test_marina_measures_each_corner_along_x_and_along_y():
    # En Marina cada esquina lleva dos cotas lineales (ángulo 0 y 90) de la esquina del contorno a
    # la del estribo, dibujadas en diagonal: las dos son el recubrimiento.
    x0, y0, x1, y1 = (-0.5, 0.9, 0.5, 2.4)
    ents = _castillo("a", "K-4", 0.0, 0.0, ["6#4", "EYG#3@15"], (x0, y0, x1, y1), 15, 30)
    for i, (esquina, adentro) in enumerate(
        [((x0, y1), (x0 + 0.158, y1 - 0.118)), ((x1, y0), (x1 - 0.158, y0 + 0.118))]
    ):
        for j, angulo in enumerate((0.0, 90.0)):
            cota = _cota(f"c{i}{j}", esquina, adentro, 3)
            cota.properties.update({"dimtype": 0, "angle": angulo})
            ents.append(cota)
        hacia = (1 if adentro[0] > esquina[0] else -1, 1 if adentro[1] > esquina[1] else -1)
        ents.append(_estribo_en(f"e{i}", adentro, hacia))
    (k,) = _cotas(build_schedule_inventory(ents, C, 1.0), "K-4")
    assert k.section_cm == (15, 30) and k.recubrimiento_cm == 3


def test_a_drawn_cover_is_only_its_own_sheets():
    # K-10 en Marina: ES-400 acota 3 cm y en ES-300 su sección no se encontró (el plano dibuja
    # 4): la colocación de ES-300 no toma el 3 de otra hoja como dibujado; toma la regla, y se dice.
    inv = build_schedule_inventory(_con_recubrimientos("K-10", 0.0, 0.0, [3, 3]), C, 1.0)
    for s in inv.specs:
        s.hoja = "ES-400"
    defs = construir_definiciones(inv, C)[0]
    reglas = reglas_estandar()
    cubre = dict(reglas.recubrimiento_m)
    cubre["castillo"] = Dato(valor=0.03, fuente="nota", hoja="ES-300",
                             texto="3.0 A 5.0 CM LIBRES EN CASTILLOS")  # fmt: skip
    reglas = reglas.model_copy(update={"recubrimiento_m": cubre})
    a = _tag("K-10")
    seg = _seg({a.detection_id: "v_300"}, plan=("v_300",))
    marcos = [SheetFrame(frame_id="v_300", code="ES-300", bbox=(0, 0, 1, 1), title="ES-300")]
    (e,) = _construir([a], seg, defs, {}, reglas=reglas, frames=marcos)
    assert e.recubrimiento_m.fuente == "nota"
    assert any("recubrimiento" in x and "ES-400" in x for x in e.avisos)


def test_a_cota_from_a_corner_that_runs_outside_is_not_its_cover():
    # La cota de recubrimiento de la sección vecina que parte de una esquina compartida corre
    # hacia afuera de ésta: no es su recubrimiento.
    x0, y0, x1, y1 = (-0.5, 0.9, 0.5, 2.4)
    ents = _castillo("a", "K-1", 0.0, 0.0, ["4#3"], (x0, y0, x1, y1), 20, 30)
    ents += [
        _cota("f1", (x1, y1), (x1 + 0.1, y1 - 0.1), 3),
        _cota("f2", (x1, y0), (x1 + 0.1, y0 + 0.1), 3),
    ]
    (k,) = _cotas(build_schedule_inventory(ents, C, 1.0), "K-1")
    assert k.recubrimiento_cm is None


# -------------------------------------------------------------- R218: lo que no es recubrimiento


def _seccion_con(cotas, estribos=True, ancho=20, peralte=30):
    """Una sección (1.0 × 1.5 unidades, ``ancho``×``peralte`` cm) con ``cotas``: (esquina,
    adentro, cm); con la esquina de un estribo dibujada en cada ``adentro`` si ``estribos``."""
    x0, y0, x1, y1 = (-0.5, 0.9, 0.5, 2.4)
    ents = _castillo("a", "K-1", 0.0, 0.0, ["4#3"], (x0, y0, x1, y1), ancho, peralte)
    for i, (esquina, adentro, cm) in enumerate(cotas):
        ents.append(_diagonal(f"q{i}", esquina, adentro, cm))
        if estribos:
            hacia = (1 if adentro[0] > esquina[0] else -1, 1 if adentro[1] > esquina[1] else -1)
            ents.append(_estribo_en(f"s{i}", adentro, hacia))
    (k,) = _cotas(build_schedule_inventory(ents, C, 1.0), "K-1")
    return k


def test_a_cota_to_a_bar_centre_is_not_a_cover():
    # El «7» del revisor: de la esquina al centro de una varilla (un círculo, ningún trazo).
    k = _seccion_con([((-0.5, 0.9), (-0.38, 1.02), 7), ((0.5, 2.4), (0.38, 2.28), 7)],
                     estribos=False)  # fmt: skip
    assert k.recubrimiento_cm is None
    assert any("no es la esquina de un estribo" in a for a in k.avisos)
    assert "no es un estribo" in k.recubrimiento_sin_tomar


def test_a_bar_spacing_from_a_corner_is_not_a_cover():
    # El «10» del revisor: separación de varillas que sale de las esquinas (razón 0.5).
    k = _seccion_con([((-0.5, 0.9), (-0.4, 1.1), 10), ((0.5, 2.4), (0.4, 2.2), 10)])
    assert k.recubrimiento_cm is None
    assert any("un cuarto o más de su lado menor (20 cm)" in a for a in k.avisos)


def test_each_guard_of_the_cover_reader_holds_alone():
    # sin la esquina de un estribo dibujado
    k = _seccion_con([((-0.5, 0.9), (-0.4, 1.0), 3), ((0.5, 2.4), (0.4, 2.3), 3)], estribos=False)
    assert k.recubrimiento_cm is None
    # un cuarto del lado menor (20/4 = 5) no es un recubrimiento
    k = _seccion_con([((-0.5, 0.9), (-0.4, 1.0), 5), ((0.5, 2.4), (0.4, 2.3), 5)])
    assert k.recubrimiento_cm is None
    # una cota que corre casi de lado (razón 3) no va de esquina a esquina de estribo
    k = _seccion_con([((-0.5, 0.9), (-0.2, 1.0), 3), ((0.5, 2.4), (0.2, 2.3), 3)])
    assert k.recubrimiento_cm is None
    # una que llega más allá de la mitad de la sección tampoco
    k = _seccion_con([((-0.5, 0.9), (0.1, 1.5), 3), ((0.5, 2.4), (-0.1, 1.8), 3)])
    assert k.recubrimiento_cm is None
    # y con todo en regla, sí
    k = _seccion_con([((-0.5, 0.9), (-0.4, 1.0), 3), ((0.5, 2.4), (0.4, 2.3), 3)])
    assert k.recubrimiento_cm == 3


def test_a_drawn_cover_outside_the_notes_range_is_not_taken():
    # Una sección de 40×60 acota 7 cm (menos de un cuarto de 40) y la nota dice «3.0 A 5.0 CM»:
    # no se toma; se dice, y queda el de la nota.
    k = _seccion_con([((-0.5, 0.9), (-0.4, 1.0), 7), ((0.5, 2.4), (0.4, 2.3), 7)],
                     ancho=40, peralte=60)  # fmt: skip
    assert k.recubrimiento_cm == 7
    inv = build_schedule_inventory(
        _con_recubrimientos("K-1", 0.0, 0.0, []), C, 1.0
    )  # una definición cualquiera de K-1 a la que se le pone esa lectura
    (spec,) = _cotas(inv, "K-1")
    spec.recubrimiento_cm, spec.hoja = 7.0, "ES-100"
    defs = construir_definiciones(inv, C)[0]
    reglas = reglas_estandar()
    cubre = dict(reglas.recubrimiento_m)
    cubre["castillo"] = Dato(valor=0.03, fuente="nota", hoja="ES-100",
                             texto="3.0 A 5.0 CM LIBRES EN CASTILLOS")  # fmt: skip
    reglas = reglas.model_copy(update={"recubrimiento_m": cubre})
    a = _tag("K-1")
    marcos = [SheetFrame(frame_id="v_100", code="ES-100", bbox=(0, 0, 1, 1), title="ES-100")]
    (e,) = _construir([a], _seg({a.detection_id: "v_100"}, plan=("v_100",)), defs, {},
                      reglas=reglas, frames=marcos)  # fmt: skip
    assert (e.recubrimiento_m.valor, e.recubrimiento_m.fuente) == (0.03, "nota")
    assert any("recubrimiento acotado 7 cm fuera de lo que dice la nota" in x for x in e.avisos)


def test_what_the_drawing_dimensions_without_being_taken_reaches_the_element():
    # R216 (K-12 en Marina): una sola esquina leída; la colocación lo dice con su valor.
    inv = build_schedule_inventory(_con_recubrimientos("K-12", 0.0, 0.0, [4]), C, 1.0)
    for s in inv.specs:
        s.hoja = "ES-300"
    defs = construir_definiciones(inv, C)[0]
    a = _tag("K-12")
    marcos = [SheetFrame(frame_id="v_300", code="ES-300", bbox=(0, 0, 1, 1), title="ES-300")]
    (e,) = _construir([a], _seg({a.detection_id: "v_300"}, plan=("v_300",)), defs, {},
                      frames=marcos)  # fmt: skip
    assert any(
        "la sección dibujada de la hoja ES-300 no se leyó (acota 4 cm en una sola esquina leída)"
        in x
        for x in e.avisos
    )
