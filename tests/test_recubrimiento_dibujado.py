"""R212: el recubrimiento que la sección dibujada de un cuadro acota en sus esquinas (las cotas en
diagonal de la esquina del contorno a la del estribo) es un dato ``seccion_dibujada`` de la marca,
por hoja, y le gana al rango de la nota («3.0 A 5.0 CM LIBRES EN CASTILLOS»). Lo dudoso (una sola
esquina, valores distintos) no se toma: se dice."""

from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.schedules import build_schedule_inventory
from klave_engine.estructura.dato import Dato
from klave_engine.estructura.definiciones import construir_definiciones
from klave_engine.estructura.reglas import reglas_estandar

from tests.test_estructura_elementos import _construir, _seg, _tag
from tests.test_secciones_de_cotas import C, _castillo, _cota, _cotas


def _diagonal(n, esquina, adentro, cm):
    return _cota(n, esquina, adentro, cm)


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
    return ents


def test_the_cover_drawn_at_the_corners_is_read():
    inv = build_schedule_inventory(_con_recubrimientos("K-12", 0.0, 0.0, [5, 5, 5]), C, 1.0)
    (k,) = _cotas(inv, "K-12")
    assert k.section_cm == (20, 30) and k.recubrimiento_cm == 5
    assert not any("recubrimiento" in a for a in k.avisos)


def test_a_doubtful_drawn_cover_is_said_not_taken():
    una = build_schedule_inventory(_con_recubrimientos("K-1", 0.0, 0.0, [4]), C, 1.0)
    (k,) = _cotas(una, "K-1")
    assert k.recubrimiento_cm is None and any("una sola esquina" in a for a in k.avisos)
    distintas = build_schedule_inventory(_con_recubrimientos("K-1", 0.0, 0.0, [3, 5]), C, 1.0)
    (k,) = _cotas(distintas, "K-1")
    assert k.recubrimiento_cm is None and any("distintos (3, 5)" in a for a in k.avisos)
    # una cota en diagonal que no sale de una esquina no es un recubrimiento
    ents = _castillo("a", "K-1", 0.0, 0.0, ["4#3"], (-0.5, 0.9, 0.5, 2.4), 20, 30)
    ents += [_cota("x1", (-0.2, 1.2), (-0.1, 1.3), 3), _cota("x2", (0.2, 1.2), (0.1, 1.3), 3)]
    (k,) = _cotas(build_schedule_inventory(ents, C, 1.0), "K-1")
    assert k.recubrimiento_cm is None


def test_the_drawn_cover_is_a_dato_of_the_mark_by_sheet_and_beats_the_note():
    inv = build_schedule_inventory(_con_recubrimientos("K-12", 0.0, 0.0, [5, 5]), C, 1.0)
    for s in inv.specs:
        s.hoja = "ES-100"
    otra = build_schedule_inventory(_con_recubrimientos("K-12", 0.0, 0.0, [4, 4], "b"), C, 1.0)
    for s in otra.specs:
        s.hoja = "ES-300"
    inv.specs += otra.specs
    defs = construir_definiciones(inv, C)[0]
    cover = defs["K-12"].recubrimiento_m
    valores = {cover.valor, *(a.valor for a in cover.alternativas)}
    assert cover.fuente == "seccion_dibujada" and valores == {0.05, 0.04}
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
    assert (por_hoja["ES-100"].valor, por_hoja["ES-100"].fuente) == (0.05, "seccion_dibujada")
    assert (por_hoja["ES-300"].valor, por_hoja["ES-300"].fuente) == (0.04, "seccion_dibujada")
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
