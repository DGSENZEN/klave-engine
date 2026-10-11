"""R81: la sección de una etiqueta de cuadro o de detalle sale de SU sección dibujada, no de la cota
más cercana. El contorno cerrado más cercano del lado que la hoja acostumbra (en Marina, encima de
la etiqueta y de su pila), que cubre el centro de la etiqueta y que ninguna otra etiqueta alcanza;
sus cotas son las que tienen sus dos puntos de definición sobre sus aristas."""

import ezdxf
import pytest
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.schedules import (
    ElementSpec,
    _extension_del_texto,
    apply_schedule,
    build_schedule_inventory,
    merge_external_specs,
)
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.dxf.entities import EntityType, EvidencePacket, NormalizedEntity
from klave_engine.dxf.parser import DxfParser
from klave_engine.estructura.definiciones import construir_definiciones, fuente_de_seccion

C = TextPatternConfig()


def _evidencia(entity_id, bbox):
    return EvidencePacket(source="a.dxf", method="t", entity_ids=[entity_id], bbox=bbox,
                          confidence=1.0)  # fmt: skip


def _texto(entity_id, text, x, y, alto=0.13, centrado=True):
    ancho = 0.6 * len(text) * alto
    x0 = x - ancho / 2 if centrado else x
    bbox = (x0, y - alto / 2, x0 + ancho, y + alto / 2)
    return NormalizedEntity(
        entity_id=entity_id, entity_type=EntityType.text, source_file="a.dxf", layer="T",
        bbox=bbox, text=text, properties={"height": alto}, raw_handle=entity_id,
        evidence=_evidencia(entity_id, bbox),
    )  # fmt: skip


def _cota(entity_id, p, q, cm):
    """Una cota con sus dos puntos de definición ``p``, ``q`` y su línea a 0.18 de ellos."""
    horizontal = abs(p[1] - q[1]) < abs(p[0] - q[0])
    x0, x1 = min(p[0], q[0]), max(p[0], q[0])
    y0, y1 = min(p[1], q[1]), max(p[1], q[1])
    bbox = (x0, y0 - 0.18, x1, y1) if horizontal else (x0, y0, x1 + 0.18, y1)
    return NormalizedEntity(
        entity_id=entity_id, entity_type=EntityType.dimension, source_file="a.dxf",
        layer="COTAS", bbox=bbox, raw_handle=entity_id,
        properties={"display_value": float(cm), "dimlfac": 100.0, "measurement": cm / 100.0,
                    "measured_segment": [p, q]},
        evidence=_evidencia(entity_id, bbox),
    )  # fmt: skip


def _poligono(entity_id, puntos, cerrado=True):
    xs, ys = [x for x, _ in puntos], [y for _, y in puntos]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    return NormalizedEntity(
        entity_id=entity_id, entity_type=EntityType.polyline, source_file="a.dxf",
        layer="DETALLES", bbox=bbox, points=list(puntos), raw_handle=entity_id,
        properties={"closed": cerrado}, evidence=_evidencia(entity_id, bbox),
    )  # fmt: skip


def _rectangulo(entity_id, x0, y0, x1, y1):
    return _poligono(entity_id, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def _castillo(n, marca, x, y, renglones, contorno, ancho_cm, peralte_cm):
    """Una etiqueta de cuadro como en Marina: la etiqueta, su pila encima y su sección encima de la
    pila (``contorno``), con su cota horizontal abajo y la vertical a la derecha."""
    x0, y0, x1, y1 = contorno
    ents = [_texto(f"{n}m", marca, x, y)]
    for i, r in enumerate(reversed(renglones)):
        ents.append(_texto(f"{n}r{i}", r, x - 0.2, y + 0.18 * (i + 1), alto=0.10, centrado=False))
    ents.append(_rectangulo(f"{n}c", x0, y0, x1, y1))
    if ancho_cm is not None:
        ents.append(_cota(f"{n}h", (x0, y0), (x1, y0), ancho_cm))
    if peralte_cm is not None:
        ents.append(_cota(f"{n}v", (x1, y1), (x1, y0), peralte_cm))
    return ents


def _cotas(inv, marca, metodo="cotas"):
    return [s for s in inv.specs if s.mark == marca and s.metodo == metodo]


def _ia(marca, family="castillo", **campos):
    return {"mark": marca, "family": family, "source": "ia", "source_text": "IA",
            "confidence": 0.5, **campos}  # fmt: skip


def test_the_label_takes_its_own_section_not_the_next_rows_cota():
    # La geometría de K-5 en Marina (ES-400): su sección (20×30) va encima de su pila, y la cota
    # vertical de la fila de abajo (40, de K-6) queda más cerca del centro de la etiqueta que la
    # suya. El lector viejo tomaba 20×40; la sección de K-5 es la suya: 20×30.
    ents = [
        *_castillo("a", "K-5", 0.0, 0.0, ["6#4", "EYG#3@15"], (-0.5, 0.9, 0.5, 2.4), 20, 30),
        *_castillo("b", "K-6", 0.0, -3.0, ["4#5+2#4", "2E#3@15"], (-0.5, -2.45, 0.5, -0.45),
                   20, 40),
    ]  # fmt: skip
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0)
    (k5,) = _cotas(inv, "K-5")
    (k6,) = _cotas(inv, "K-6")
    assert (k5.section_cm, k6.section_cm) == ((20, 30), (20, 40))
    assert (k5.avisos, k6.avisos, k5.seccion_supuesta) == ([], [], False)
    assert inv.by_mark["K-5"].section_cm == (20, 30)
    defs = construir_definiciones(inv, C)[0]
    assert defs["K-5"].seccion_cm.valor == (20, 30) and defs["K-5"].seccion_cm.fuente == "detalle"
    # Las dos etiquetas son marcas de cuadro (no colocaciones), como antes.
    assert {"am", "bm"} <= set(inv.cuadro_mark_entities)


def test_two_labels_reaching_one_section_lose_it():
    # Dos etiquetas bajo un mismo contorno: de cuál es no lo dice la geometría. Ninguna toma la
    # sección, se rechaza «ambigua» con las dos marcas, y el campo queda reclamado (hay cotas).
    ents = [
        _texto("m1", "K-1", -0.5, 0.0),
        _texto("r1", "4#3", -0.7, 0.18, alto=0.10, centrado=False),
        _texto("m2", "K-2", 0.5, 0.0),
        _texto("r2", "4#4", 0.3, 0.18, alto=0.10, centrado=False),
        _rectangulo("c", -1.0, 0.9, 1.0, 2.4),
        _cota("h", (-1.0, 0.9), (1.0, 0.9), 40),
        _cota("v", (1.0, 2.4), (1.0, 0.9), 30),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0)
    assert not [s for s in inv.specs if s.metodo == "cotas" and s.section_cm is not None]
    ambiguas = sorted((r.entidad_id, r.marcas) for r in inv.rechazos if r.motivo == "ambigua")
    assert ambiguas == [("m1", ["K-1", "K-2"]), ("m2", ["K-2", "K-1"])]
    merge_external_specs(inv, [_ia("K-1", section_cm=(40, 30))], C)
    k1 = construir_definiciones(inv, C)[0]["K-1"].seccion_cm
    assert k1.ilegible and [a.fuente for a in k1.alternativas] == ["ia"]


def test_a_section_that_is_not_a_rectangle_is_never_one():
    # K-15A en Marina: 60 de ancho, 30 + 25 de alto, la parte de arriba de 20. R129: un contorno
    # que no es un rectángulo nunca es sección (ni se toma, ni se reclama por él, ni un rechazo);
    # detiene al título. Lo reclaman sus cotas cercanas, como al lector viejo: la IA no lo llena.
    contorno = [(-1.5, 0.9), (1.5, 0.9), (1.5, 3.65), (0.5, 3.65), (0.5, 2.4), (-1.5, 2.4)]
    ents = [
        _texto("m", "K-15A", 0.0, 0.0),
        _texto("r0", "6#8+6#6", -0.2, 0.36, alto=0.10, centrado=False),
        _texto("r1", "4E#3EXT@10", -0.2, 0.18, alto=0.10, centrado=False),
        _poligono("c", contorno),
        _cota("h", (-1.5, 0.9), (1.5, 0.9), 60),
        _cota("v1", (-1.5, 2.4), (-1.5, 0.9), 30),
        _cota("v2", (1.5, 3.65), (1.5, 2.4), 25),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0)
    (k,) = _cotas(inv, "K-15A")
    assert k.section_cm is None and "seccion" in k.campos_con_texto
    assert k.avisos == [
        "sección: lo más cercano dibujado encima no es una sección: no se toma lo que está más "
        "allá",
        "las cotas cercanas (30, 60) no se toman",
    ]
    assert inv.rechazos == []
    merge_external_specs(inv, [_ia("K-15A", section_cm=(60, 55))], C)
    d = construir_definiciones(inv, C)[0]["K-15A"].seccion_cm
    assert d.ilegible and [a.fuente for a in d.alternativas] == ["ia"]


def test_one_cota_on_a_square_section_is_an_assumed_square():
    # Una sola cota (15) en una sección dibujada cuadrada: se supone cuadrada, y eso es «supuesto»,
    # nunca «detalle». En una que no es cuadrada no se supone nada, pero su sección lleva una cota:
    # la sección es del plano y queda reclamada (R111), la IA no la llena.
    ents = [
        *_castillo("a", "K-1", 0.0, 0.0, ["4#3", "E#2@15"], (-0.375, 0.9, 0.375, 1.65), 15, None),
        *_castillo("b", "K-3", 5.0, 0.0, ["6#3", "E#2@15"], (4.625, 0.9, 5.375, 2.4), 15, None),
    ]  # fmt: skip
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0)
    (k1,) = _cotas(inv, "K-1")
    assert (k1.section_cm, k1.seccion_supuesta) == ((15, 15), True)
    assert "una sola cota (15 cm)" in k1.avisos[0]
    (k3,) = _cotas(inv, "K-3")
    assert k3.section_cm is None and k3.campos_con_texto == ["seccion"]
    assert "sólo su ancho (15 cm) está acotado" in k3.avisos[-1]
    d = construir_definiciones(inv, C)[0]["K-1"].seccion_cm
    assert (d.valor, d.fuente) == ((15, 15), "supuesto")


def test_a_beam_keeps_its_width_by_height():
    # Un detalle de trabe: el título encima de su sección (la hoja acostumbra la sección debajo).
    # 40 de ancho por 20 de peralte, tal cual (R75: una trabe es b×h).
    ents = [
        _texto("m", "T-1", 0.0, 2.9, alto=0.14),
        _rectangulo("c", -1.0, 1.4, 1.0, 2.4),
        _cota("h", (-1.0, 1.4), (1.0, 1.4), 40),
        _cota("v", (-1.0, 2.4), (-1.0, 1.4), 20),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=[(-10, -10, 10, 10)])
    (t1,) = _cotas(inv, "T-1")
    assert t1.section_cm == (40, 20)
    d = construir_definiciones(inv, C)[0]["T-1"]
    assert d.familia == "trabe" and d.seccion_cm.valor == (40, 20)


def test_a_section_drawn_off_its_cotas_is_a_second_reading():
    # K-8 en Marina: cotas 15×60 en un contorno de 0.789 × 2.602 (no está a escala). Se leen las
    # cotas, y la sección como está dibujada queda como otra lectura («geometria»): el desacuerdo
    # se ve, y la definición elige las cotas. La sección dibujada lleva sus décimas (R106).
    ents = _castillo("a", "K-8", 0.0, 0.0, ["8#4", "2E#3@20"], (-0.3945, 0.9, 0.3946, 3.5017),
                     15, 60)  # fmt: skip
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0)
    (k8,) = _cotas(inv, "K-8")
    (dibujada,) = _cotas(inv, "K-8", "geometria")
    assert k8.section_cm == (15, 60) and dibujada.section_cm == (17.9, 59.1)
    assert "no coincide con sus cotas 15x60" in dibujada.avisos[0]
    assert inv.by_mark["K-8"].section_cm == (15, 60)
    d = construir_definiciones(inv, C)[0]["K-8"].seccion_cm
    assert (d.valor, d.fuente, d.en_conflicto) == ((15, 60), "detalle", False)
    assert [(a.valor, a.fuente) for a in d.alternativas] == [((17.9, 59.1), "seccion_dibujada")]


def test_without_its_own_section_no_nearby_cota_is_taken():
    # Antes, la cota más cercana: aquí no hay sección dibujada, sólo cotas sueltas junto al título.
    # No se toman; el campo queda reclamado y la IA no lo llena.
    ents = [
        _texto("m", "CTA-3", 2.0, 20.0, alto=0.12),
        _cota("v", (1.2, 18.8), (1.2, 18.0), 80),
        _cota("h", (1.5, 18.6), (1.8, 18.6), 30),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=[(0, 0, 44, 29.4)])
    (cta,) = _cotas(inv, "CTA-3")
    assert cta.section_cm is None and cta.campos_con_texto == ["seccion"]
    assert cta.avisos == [
        "sección: no se encontró su sección dibujada",
        "las cotas cercanas (30, 80) no se toman",
    ]
    merge_external_specs(inv, [_ia("CTA-3", family="contratrabe", section_cm=(30, 80))], C)
    assert inv.by_mark["CTA-3"].section_cm is None
    d = construir_definiciones(inv, C)[0]["CTA-3"].seccion_cm
    assert d.ilegible and [a.fuente for a in d.alternativas] == ["ia"]


def test_a_chain_of_cotas_gives_the_side():
    # K-7A en Marina: su ancho se acota en cadena, 15 + 55, sobre la arista: 70.
    ents = [
        *_castillo("a", "K-7A", 0.0, 0.0, ["6#5+4#4", "3E#3@20"], (-1.75, 0.9, 1.75, 1.9),
                   None, 20),
        _cota("h1", (-1.75, 0.9), (-1.0, 0.9), 15),
        _cota("h2", (-1.0, 0.9), (1.75, 0.9), 55),
    ]  # fmt: skip
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0)
    (k,) = _cotas(inv, "K-7A")
    assert k.section_cm == (70, 20) and k.avisos == ["ancho 70 = 15 + 55 (cotas en cadena)"]


@pytest.mark.parametrize("supuesta,fuente", [(False, "detalle"), (True, "supuesto")])
def test_an_assumed_side_is_never_a_detail(supuesta, fuente):
    s = ElementSpec(
        mark="K-1", family="castillo", section_cm=(15, 15), source="detalle", metodo="cotas",
        source_text="K-1", confidence=0.5, seccion_supuesta=supuesta,
    )  # fmt: skip
    assert fuente_de_seccion(s) == fuente


def test_a_read_section_beats_an_assumed_one_in_the_by_mark_view():
    # El ancho supuesto de una hoja nunca le gana a la sección leída de otra (mismo rango).
    ents = [
        *_castillo("a", "K-1", 0.0, 0.0, ["4#3", "E#2@15"], (-0.375, 0.9, 0.375, 1.65), 15, None),
        *_castillo("b", "K-1", 5.0, 0.0, ["4#3", "E#2@15"], (4.625, 0.9, 5.375, 2.025), 15, 30),
    ]  # fmt: skip
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0)
    assert sorted(s.section_cm for s in _cotas(inv, "K-1")) == [(15, 15), (15, 30)]
    assert inv.by_mark["K-1"].section_cm == (15, 30)


def test_a_dimension_keeps_its_definition_points(tmp_path):
    # El lector necesita los dos puntos que mide una cota: el normalizador los guarda.
    doc = ezdxf.new("R2010")
    dim = doc.modelspace().add_linear_dim(base=(0, -0.2), p1=(1.0, 2.0), p2=(3.5, 2.0))
    dim.render()
    doc.saveas(tmp_path / "cota.dxf")
    (d,) = [
        e
        for e in DxfParser().parse_file(tmp_path / "cota.dxf").entities
        if e.entity_type == EntityType.dimension
    ]
    assert [tuple(p) for p in d.properties["measured_segment"]] == [(1.0, 2.0), (3.5, 2.0)]
    x0, y0, x1, y1 = d.bbox
    assert x0 <= 1.0 and x1 >= 3.5 and y0 <= -0.2 and y1 >= 2.0


# ------------------------------------------------- Tarea 8b, ronda 1: R106, R111, R112


def _arista(entity_id, p, q):
    """Un trazo suelto (una línea) que acaba un poco antes de sus esquinas: nunca cierra un
    contorno, y no sigue más allá de ellas (R118)."""
    (x0, y0), (x1, y1) = p, q
    dx, dy = (
        (0.01 if x1 > x0 else -0.01 if x1 < x0 else 0),
        (0.01 if y1 > y0 else -0.01 if y1 < y0 else 0),
    )
    return _poligono(entity_id, [(x0 + dx, y0 + dy), (x1 - dx, y1 - dy)], cerrado=False)


def _detalle_sin_contorno(n, marca, x, y, caja, ancho, peralte, aristas=4):
    """Un detalle de trabe como en Marina (ES-101…ES-302): el título encima y su sección debajo,
    dibujada con trazos sueltos (ningún contorno cerrado), con su cota horizontal abajo y la
    vertical a la izquierda, que comparten la esquina de abajo a la izquierda."""
    x0, y0, x1, y1 = caja
    lados = [((x0, y0), (x1, y0)), ((x0, y1), (x1, y1)), ((x0, y0), (x0, y1)), ((x1, y0), (x1, y1))]
    ents = [_texto(f"{n}m", marca, x, y, alto=0.14)]
    ents += [_arista(f"{n}a{i}", p, q) for i, (p, q) in enumerate(lados[:aristas])]
    ents += [_cota(f"{n}h", (x0, y0), (x1, y0), ancho), _cota(f"{n}v", (x0, y1), (x0, y0), peralte)]
    return ents


_DETALLE = [(-10.0, -10.0, 20.0, 10.0)]


def test_a_pair_of_cotas_sharing_a_corner_is_the_section_with_its_decimals():
    # R106 (T2-13 en Marina, ES-202): sin contorno cerrado, el par de cotas que comparte una esquina
    # y cuyas aristas están dibujadas es la sección, con sus decimales (72.5, nunca 72).
    ents = _detalle_sin_contorno("a", "T2-13", 0.0, 2.6, (-1.2, 0.0, 1.2, 2.4), 75, 72.5)
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    (t,) = _cotas(inv, "T2-13")
    assert t.section_cm == (75, 72.5) and t.avisos == []
    assert "par de cotas 75x72.5" in t.source_text
    d = construir_definiciones(inv, C)[0]["T2-13"].seccion_cm
    assert (d.valor, d.fuente) == ((75, 72.5), "detalle")


def test_a_pair_with_two_drawn_edges_is_no_section():
    # R106 (T1-1 en Marina): con sólo dos aristas dibujadas no se sabe si el par es la sección.
    ents = _detalle_sin_contorno("a", "T1-1", 0.0, 1.0, (-0.5, 0.0, 0.5, 0.75), 40, 20, aristas=2)
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert all(s.section_cm is None for s in _cotas(inv, "T1-1"))


def test_a_link_of_a_chain_of_cotas_makes_no_pair():
    # R106: un lado acotado en cadena (5 + 20 + 5) no es de un par (E3): el eslabón de 5 con el
    # peralte no es la sección, aunque el estribo dibuje la cuarta arista.
    ents = _detalle_sin_contorno("a", "T-9", 0.0, 2.2, (-0.6, 0.0, 0.6, 2.0), 30, 50)
    ents = [e for e in ents if e.entity_id != "ah"]
    ents += [
        _cota("h1", (-0.6, 0.0), (-0.4, 0.0), 5),
        _cota("h2", (-0.4, 0.0), (0.4, 0.0), 20),
        _cota("h3", (0.4, 0.0), (0.6, 0.0), 5),
        _arista("estribo", (-0.4, 0.05), (-0.4, 1.95)),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert all(s.section_cm is None for s in _cotas(inv, "T-9"))


def test_two_labels_reaching_one_pair_both_claim_it():
    # R106 con la regla de R81: un rectángulo de par que alcanzan dos etiquetas no es de ninguna;
    # las dos lo reclaman (R111) y se rechazan «ambigua».
    ents = _detalle_sin_contorno("a", "T-1", -0.3, 2.6, (-1.2, 0.0, 1.2, 2.4), 60, 60)
    ents.append(_texto("bm", "T-2", 0.6, 2.6, alto=0.14))
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [s.section_cm for s in _cotas(inv, "T-1")] == [None]
    assert [s.section_cm for s in _cotas(inv, "T-2")] == [None]
    ambiguas = sorted(r.marcas for r in inv.rechazos if r.motivo == "ambigua")
    assert ambiguas == [["T-1", "T-2"], ["T-2", "T-1"]]


def test_a_pair_inside_a_shape_that_is_not_a_rectangle_is_never_its_section():
    # R106 (K-15A): una sección dibujada que no es un rectángulo nunca da el de un par de cotas.
    contorno = [(-1.5, 0.9), (1.5, 0.9), (1.5, 3.65), (0.5, 3.65), (0.5, 2.4), (-1.5, 2.4)]
    ents = [
        _texto("m", "K-15A", 0.0, 0.0),
        _texto("r", "8#6", -0.2, 0.18, alto=0.10, centrado=False),
        _poligono("c", contorno),
        _cota("h", (-1.5, 0.9), (1.5, 0.9), 60),
        _cota("v", (-1.5, 2.4), (-1.5, 0.9), 30),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0)
    assert [s.section_cm for s in _cotas(inv, "K-15A")] == [None]


def test_a_cota_with_decimals_on_an_outline_keeps_them():
    # R106: 72.5 se queda 72.5 (antes, el redondeo del banco lo hacía 72).
    ents = [
        _texto("m", "T-1", 0.0, 2.9, alto=0.14),
        _rectangulo("c", -1.0, 0.0, 1.0, 2.4),
        _cota("h", (-1.0, 0.0), (1.0, 0.0), 30),
        _cota("v", (-1.0, 2.4), (-1.0, 0.0), 72.5),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    (t,) = _cotas(inv, "T-1")
    assert t.section_cm == (30, 72.5)


def test_a_rotated_linear_dimension_measures_along_its_angle():
    # Una cota lineal a 0° mide en x aunque sus puntos estén a distinta altura: es el ancho.
    h = _cota("h", (-1.0, 0.0), (1.0, 0.0), 30)
    h = h.model_copy(
        update={"properties": {**h.properties, "dimtype": 0, "angle": 0.0,
                               "measured_segment": [(-1.0, 2.4), (1.0, 0.0)]}}
    )  # fmt: skip
    ents = [
        _texto("m", "T-1", 0.0, 2.9, alto=0.14),
        _rectangulo("c", -1.0, 0.0, 1.0, 2.4),
        h,
        _cota("v", (-1.0, 2.4), (-1.0, 0.0), 60),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    (t,) = _cotas(inv, "T-1")
    assert t.section_cm == (30, 60)


def test_a_dimension_keeps_its_type_and_angle(tmp_path):
    # R106: el normalizador guarda el tipo de la cota y su ángulo (en qué eje mide).
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_linear_dim(base=(0, -0.2), p1=(1.0, 2.0), p2=(3.5, 2.5), angle=0).render()
    msp.add_linear_dim(base=(-0.3, 0), p1=(0.0, 0.0), p2=(0.5, 2.0), angle=90).render()
    doc.saveas(tmp_path / "cotas.dxf")
    dims = [
        e
        for e in DxfParser().parse_file(tmp_path / "cotas.dxf").entities
        if e.entity_type == EntityType.dimension
    ]
    assert sorted((d.properties["dimtype"], d.properties["angle"]) for d in dims) == [
        (0, 0.0),
        (0, 90.0),
    ]


def test_a_stack_owner_is_a_cotas_candidate_without_armado_near_it():
    # R111 (P-5 en Marina, ES-000): su pila es un renglón ancho cuyo centro queda a más de 0.8 de
    # la etiqueta; antes no era candidata y su 70x70 no se leía.
    ents = [
        _texto("m", "P-5", 0.0, 0.0),
        _texto("r", "4#8 + 12#6 CORRIDAS EN TODA SU ALTURA SIN TRASLAPES", -0.3, 0.18, alto=0.10,
               centrado=False),
        _rectangulo("c", -0.5, 0.9, 0.5, 1.9),
        _cota("h", (-0.5, 0.9), (0.5, 0.9), 70),
        _cota("v", (0.5, 1.9), (0.5, 0.9), 70),
    ]  # fmt: skip
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0)
    (p5,) = _cotas(inv, "P-5")
    assert p5.section_cm == (70, 70)


def test_a_shared_outline_is_claimed_by_every_label_that_reaches_it():
    # R111 (D-3 en Marina): dos etiquetas alcanzan una sección; ninguna la toma y las dos la
    # reclaman aunque no haya cotas «cercanas»: la IA no la llena (antes, D-3: 25x100 de la IA).
    ents = [
        _texto("m1", "D-3", -0.5, 4.3, alto=0.14),
        _texto("m2", "D-4", 0.5, 4.3, alto=0.14),
        _rectangulo("c", -1.0, 0.0, 1.0, 4.0),
        _cota("h", (-1.0, 0.0), (1.0, 0.0), 100),
        _cota("v", (-1.0, 4.0), (-1.0, 0.0), 200),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    for marca in ("D-3", "D-4"):
        (s,) = _cotas(inv, marca)
        assert s.section_cm is None and s.campos_con_texto == ["seccion"]
    merge_external_specs(inv, [_ia("D-3", family="dala", section_cm=(25, 100))], C)
    assert "D-3" not in inv.by_mark or inv.by_mark["D-3"].section_cm is None


def test_a_drawn_section_close_to_its_cotas_corroborates_silently():
    # R112: en un cuadro sin escala, la sección dibujada a 2 cm o 10 % de sus cotas las confirma
    # (antes: otra lectura «geometria», dibujada 21.5x39.2 contra 20x40).
    ents = _castillo("a", "K-1", 0.0, 0.0, ["4#3", "E#2@15"], (-0.43, 0.9, 0.43, 2.472), 20, 40)
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0)
    (k1,) = _cotas(inv, "K-1")
    assert k1.section_cm == (20, 40) and _cotas(inv, "K-1", "geometria") == []


def test_an_assumed_side_is_stamped_supuesto_not_cuadro():
    # R112: una sección con un lado supuesto se estampa «supuesto», nunca «cuadro».
    ents = _castillo("a", "K-1", 0.0, 0.0, ["4#3", "E#2@15"], (-0.375, 0.9, 0.375, 1.65), 15, None)
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0)
    k1 = make_detection("d1", DetectionType.column_tag, "K-1", (0, 0, 1, 1), 0.8, [], "m", [])
    assert apply_schedule([k1], inv, meters_factor=1.0) == 1
    assert (k1.properties["section_cm"], k1.properties["section_source"]) == ("15x15", "supuesto")


def test_a_cota_whose_unit_the_style_does_not_say_is_never_converted():
    # PRUEBA-1 (CR-1): cotas «15» y «20» con dimlfac 40 en un dibujo en metros (1 unidad mostrada =
    # 2.5 cm). Antes se leía 37.5x50; su unidad no se sabe: no se toma, la sección queda
    # reclamada y la IA no la llena.
    def cota(entity_id, p, q, mostrado):
        c = _cota(entity_id, p, q, mostrado)
        props = {**c.properties, "dimlfac": 40.0, "display_text": f"{mostrado:g}"}
        return c.model_copy(update={"properties": props})

    ents = [
        _texto("m", "CR-1", 0.0, 2.0, alto=0.22),
        _rectangulo("c", -0.54, 0.0, 0.54, 1.44),
        cota("h", (-0.54, 0.0), (0.54, 0.0), 15),
        cota("v", (-0.54, 1.44), (-0.54, 0.0), 20),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    (cr,) = _cotas(inv, "CR-1")
    assert cr.section_cm is None and cr.campos_con_texto == ["seccion"]
    assert "cota «15» con un factor de escala que no dice su unidad (1 unidad = 2.5 cm)" in (
        " ".join(cr.avisos)
    )


# ------------------------------------------------- Tarea 8b, ronda 2: R115, R118, R119


def _linea(entity_id, p, q):
    return _poligono(entity_id, [p, q], cerrado=False)


def test_two_touching_sections_never_make_a_phantom_rectangle():
    # R118: A (20x50) y B (20x30) se tocan; la cota de alto de A va en la arista común. El ancho
    # de B con el alto de A no es una sección: la línea de arriba de B la atraviesa. T-2 lee la
    # suya, 20x30 (antes, 20x50).
    ents = [
        _texto("t1", "T-1", 0.4, 2.3, alto=0.14),
        _texto("t2", "T-2", 1.2, 2.3, alto=0.14),
        _linea("a1", (0.0, 0.0), (1.6, 0.0)),
        _linea("a2", (0.0, 0.0), (0.0, 2.0)),
        _linea("a3", (0.0, 2.0), (0.8, 2.0)),
        _linea("a4", (0.8, 0.0), (0.8, 2.0)),
        _linea("a5", (0.8, 1.2), (1.6, 1.2)),
        _linea("a6", (1.6, 0.0), (1.6, 1.2)),
        _cota("ca", (0.0, 2.0), (0.8, 2.0), 20),
        _cota("cav", (0.8, 2.0), (0.8, 0.0), 50),
        _cota("cb", (0.8, 0.0), (1.6, 0.0), 20),
        _cota("cbv", (1.6, 1.2), (1.6, 0.0), 30),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [s.section_cm for s in _cotas(inv, "T-1")] == [(20, 50)]
    assert [s.section_cm for s in _cotas(inv, "T-2")] == [(20, 30)]


def test_slab_lines_running_past_the_corners_make_no_section():
    # R118: una losa (60 de cota, 10 de espesor) cuyas líneas siguen de largo, con una trabe
    # colgada acotada sólo en cadena (5 + 10 + 5): el rectángulo de 60x10 no es la sección de
    # T-1 (antes, 60x10).
    ents = [
        _texto("t1", "T-1", 1.2, 2.4, alto=0.14),
        _linea("l1", (-0.8, 2.0), (3.2, 2.0)),
        _linea("l2", (-0.8, 1.6), (0.8, 1.6)),
        _linea("l3", (1.6, 1.6), (3.2, 1.6)),
        _linea("l4", (0.0, 0.0), (0.0, 2.0)),
        _linea("v1", (0.8, 0.0), (0.8, 1.6)),
        _linea("v2", (1.6, 0.0), (1.6, 1.6)),
        _linea("v3", (0.8, 0.0), (1.6, 0.0)),
        _cota("c60", (0.0, 2.0), (2.4, 2.0), 60),
        _cota("c10", (0.0, 2.0), (0.0, 1.6), 10),
        _cota("h1", (0.8, 0.0), (1.0, 0.0), 5),
        _cota("h2", (1.0, 0.0), (1.4, 0.0), 10),
        _cota("h3", (1.4, 0.0), (1.6, 0.0), 5),
        _cota("v40", (1.6, 1.6), (1.6, 0.0), 40),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert all(s.section_cm is None for s in _cotas(inv, "T-1"))


def _titulo(entity_id, text, x, y, alto=0.14, halign=0):
    """Un título alineado a la izquierda: su ancla (``ancla_texto``) es su ``insert``, la punta
    izquierda de su base; su caja, la que estima el normalizador (siempre desde el ``insert``).
    Con ``halign`` 2, alineado a la derecha en ``x`` (su punto de alineación; el ``insert``
    como lo deja un DXF sin calcular, en el mismo punto)."""
    ancho = 0.6 * len(text) * alto
    bbox = (x, y, x + ancho, y + alto)
    propiedades = {"height": alto, "insert": (x, y)}
    if halign:
        propiedades |= {"halign": halign, "align_point": (x, y)}
    return NormalizedEntity(
        entity_id=entity_id, entity_type=EntityType.text, source_file="a.dxf", layer="T",
        bbox=bbox, text=text, properties=propiedades, raw_handle=entity_id,
        evidence=_evidencia(entity_id, bbox),
    )  # fmt: skip


def _leidas(inv, *marcas):
    return {m: [s.section_cm for s in _cotas(inv, m) if s.section_cm] for m in marcas}


@pytest.mark.parametrize(
    "texto,x,halign,leida",
    [
        # Su ancla dentro de la sección y su texto encima (79 %): es suya.
        ("T-1", 1.0, 0, (20, 50)),
        # T2-8 en Marina (ES-201): alineado a la izquierda, su ancla 1.36 altos antes de la sección
        # (260.966 contra 261.157) y su texto encima de ella (0.145 de 0.336, 43 %): es suya.
        ("T2-8", 0.2 - 0.191, 0, (20, 50)),
        # T3-1 en Marina: su ancla dentro, pero sólo 28 % de su texto encima: menos de un tercio,
        # no es suya (R123).
        ("T-1", 1.13, 0, None),
        # Su texto empieza 0.4 altos después de la sección: no está encima, no es suya (la holgura
        # de media altura de R115 ya no existe).
        ("T-1", 1.256, 0, None),
        # Alineado a la derecha en 1.3, pasada la sección: su texto acaba encima de ella (60 %; la
        # caja del normalizador, desde el insert, no la tocaría): es suya.
        ("T-1", 1.3, 2, (20, 50)),
        # Alineado a la derecha en 0.15, antes de la sección: su texto no la toca (la caja del
        # normalizador sí): no es suya.
        ("T-1", 0.15, 2, None),
    ],
)
def test_ownership_goes_by_the_titles_real_text(texto, x, halign, leida):
    # R120: el dueño de una sección es el título cuyo texto, donde lo pone su alineación, está
    # encima del ancho de la sección; nunca su ancla ni un centro estimado.
    ents = _detalle_sin_contorno("a", texto, 0.0, 0.0, (0.2, 0.0, 1.2, 2.5), 20, 50)
    ents[0] = _titulo("am", texto, x, 2.6, halign=halign)
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert _leidas(inv, texto)[texto] == ([leida] if leida else [])


@pytest.mark.parametrize("contorno", [False, True])
@pytest.mark.parametrize(
    "x_otro,suya",
    [
        # T-1 entero encima de la sección y T-9 en 0.1 de sus 0.252: es de T-1.
        (1.1, True),
        # T-9 encima en 0.22 de 0.252 (87 %) contra el 100 % de T-1: menos del 25 % de margen:
        # de ninguno, reclamada por los dos.
        (0.98, False),
    ],
)
def test_two_titles_over_one_section_the_clearly_larger_overlap_wins(contorno, x_otro, suya):
    # R120: dos títulos encima de una sección (un contorno cerrado o un par de cotas): es del que
    # está más encima por un margen claro (25 %, como R54); si no, de ninguno (ambigua).
    if contorno:
        ents = [
            _rectangulo("c", 0.2, 0.0, 1.2, 2.5),
            _cota("h", (0.2, 0.0), (1.2, 0.0), 20),
            _cota("v", (0.2, 2.5), (0.2, 0.0), 50),
        ]
    else:
        ents = _detalle_sin_contorno("a", "T-1", 0.0, 0.0, (0.2, 0.0, 1.2, 2.5), 20, 50)[1:]
    ents += [_titulo("am", "T-1", 0.4, 2.6), _titulo("bm", "T-9", x_otro, 2.62)]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    ambiguas = sorted(sorted(r.marcas) for r in inv.rechazos if r.motivo == "ambigua")
    if suya:
        assert _leidas(inv, "T-1", "T-9") == {"T-1": [(20, 50)], "T-9": []}
        assert ambiguas == []
    else:
        assert _leidas(inv, "T-1", "T-9") == {"T-1": [], "T-9": []}
        assert ambiguas == [["T-1", "T-9"], ["T-1", "T-9"]]
        for marca in ("T-1", "T-9"):
            assert [s.campos_con_texto for s in _cotas(inv, marca)] == [["seccion"]]


@pytest.mark.parametrize(
    "x_titulo,vecina,leidas",
    [
        # Un título ancho (0.9) encima de dos secciones, de la primera 0.6 y de la otra 0.1: es la
        # primera.
        (0.6, False, {"T-1": [(20, 50)], "T-2": []}),
        # Encima de las dos casi igual (0.35 y 0.35): de ninguna; la reclama.
        (0.85, False, {"T-1": [], "T-2": []}),
        # Igual, pero la segunda tiene su título entero encima: es de su título, y la primera
        # queda del título ancho.
        (0.85, True, {"T-1": [(20, 50)], "T-2": [(30, 60)]}),
    ],
)
def test_a_wide_title_over_two_sections(x_titulo, vecina, leidas):
    # R120: un título encima de dos secciones lado a lado es de la que está más encima por un
    # margen claro; nunca se lleva la de un vecino que tiene su título encima.
    ents = _detalle_sin_contorno("a", "T-1", 0.0, 0.0, (0.2, 0.0, 1.2, 2.5), 20, 50)
    ents[0] = _titulo("am", "T-1", x_titulo, 2.6, alto=0.5)
    ents += _detalle_sin_contorno("b", "T-2", 0.0, 0.0, (1.4, 0.0, 2.4, 2.5), 30, 60)[1:]
    if vecina:
        ents.append(_titulo("bm", "T-2", 1.6, 2.6))
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert _leidas(inv, "T-1", "T-2") == leidas
    if x_titulo == 0.85 and not vecina:
        (t1,) = _cotas(inv, "T-1")
        assert t1.campos_con_texto == ["seccion"]
        assert "su título está sobre dos rectángulos de pares de cotas" in t1.avisos[0]


def _titulo_en_columna(entity_id, text, x, y, alto=0.1):
    """Un MTEXT como los de ES-500 en Marina: insertado arriba a la izquierda, con una columna de
    1.358 y el párrafo centrado en ella («\\pxqc»); su caja del normalizador, desde el insert."""
    ancho = 0.6 * len(text) * alto
    bbox = (x, y, x + ancho, y + alto)
    propiedades = {
        "height": alto,
        "insert": (x, y),
        "attachment_point": 1,
        "column_width": 1.357913709497112,
        "paragraph_align": "c",
    }
    return NormalizedEntity(
        entity_id=entity_id, entity_type=EntityType.mtext, source_file="a.dxf", layer="T",
        bbox=bbox, text=text, properties=propiedades, raw_handle=entity_id,
        evidence=_evidencia(entity_id, bbox),
    )  # fmt: skip


def test_d3_and_cta8_under_a_wall_strip_are_pointed_at_by_their_leaders():
    # R123 + R124 (D-3 y CTA-8 en Marina, ES-500, corridos 204, -105): los dos títulos van
    # centrados en su columna, bajo la misma tira de muro de 1.925 × 0.049; ni ella ni el contorno
    # de 0.300 × 0.049 son secciones (sin cotas y de 0.049 de alto), así que ya no hay ambigua. De
    # cada título sale su flecha dibujada (una polilínea de tres vértices: el apoyo horizontal en
    # el título y el tramo inclinado hacia lo que señala): su sección, que nadie lee, se reclama
    # «señalada por flecha; se lee en E3» y la IA no llena D-3. En la hoja, las secciones van
    # encima de sus títulos (K-1).
    ents = [
        _titulo_en_columna("d3", "DADO\nD-3 ", 0.458, -0.14),
        _titulo_en_columna("c8", "CTA-8 ", 0.469, 0.378),
        _poligono("fd3", [(0.635, 0.049), (0.961, -0.272), (1.282, -0.272)], cerrado=False),
        _poligono("fc8", [(0.477, 0.496), (0.918, 0.247), (1.240, 0.247)], cerrado=False),
        _rectangulo("tira", 0.574, 0.661, 2.499, 0.710),
        _rectangulo("chico", 0.274, 0.161, 0.574, 0.210),
        _texto("k1", "K-1", 5.0, 0.0, alto=0.1),
        _rectangulo("k1c", 4.8, 0.5, 5.2, 1.0),
        _cota("lejos", (8.0, 8.0), (9.0, 8.0), 100),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    for marca in ("D-3", "CTA-8"):
        (s,) = _cotas(inv, marca)
        assert (s.section_cm, s.campos_con_texto) == (None, ["seccion"])
        assert s.avisos == ["sección: señalada por flecha; se lee en E3"]
        assert s.source_text.endswith("señalada por flecha; se lee en E3")
    assert [r for r in inv.rechazos if r.motivo == "ambigua"] == []
    merge_external_specs(inv, [_ia("D-3", family="dala", section_cm=(25, 100))], C)
    assert "D-3" not in inv.by_mark or inv.by_mark["D-3"].section_cm is None


_OCTAGONO = [(0.03, 0.0), (0.105, 0.0), (0.135, 0.03), (0.135, 0.095), (0.105, 0.125),
             (0.03, 0.125), (0.0, 0.095), (0.0, 0.03)]  # fmt: skip


def _caja(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


@pytest.mark.parametrize(
    "puntos,alto,reclama",
    [
        # Su sección dibujada, sin cotas: la reclama.
        (_caja(-1.0, 0.0, 1.0, 2.4), 0.14, True),
        # Una rendija (T2-12 en ES-500: 0.138 × 0.010): no es sección.
        (_caja(-0.069, 0.0, 0.069, 0.010), 0.10, False),
        # Una tira de muro (D-3/CTA-8 en ES-500: 1.925 × 0.049): no es sección.
        (_caja(-0.9625, 0.0, 0.9625, 0.049), 0.10, False),
        # El contorno chico junto a D-3 (0.300 × 0.049): no es sección.
        (_caja(-0.15, 0.0, 0.15, 0.049), 0.14, False),
        # Un octágono (CE-5, T3-11, T3-13 en ES-500: 0.135 × 0.125, ocho esquinas): no es
        # sección, ni un rechazo «sin_lector».
        ([(x - 0.0675, y) for x, y in _OCTAGONO], 0.10, False),
        # Un cuadrito de 0.10 con letras de 0.09 (T4-2 en ES-500): menos de 1.5 altos.
        (_caja(-0.05, 0.0, 0.05, 0.10), 0.09, False),
        # Un rectángulo de 2.0 × 0.22: nueve veces más largo que ancho.
        (_caja(-1.0, 0.0, 1.0, 0.22), 0.14, False),
    ],
)
def test_an_owned_outline_without_cotas_claims_only_if_it_looks_like_a_section(
    puntos, alto, reclama
):
    # R123 (reemplaza a R122): un contorno sin cotas es sección, y se reclama aunque no tenga
    # cotas, sólo si parece una: cuatro esquinas, los dos lados de 1.5 altos del título o más, y
    # no más de 8 veces más largo que ancho. Si no, la IA sí la llena.
    tope = max(y for _x, y in puntos)
    ents = [
        _texto("m", "D-3", 0.0, tope + 0.3, alto=alto),
        _poligono("c", puntos),
        _cota("lejos", (8.0, 8.0), (9.0, 8.0), 100),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    lecturas = _cotas(inv, "D-3")
    assert [(s.section_cm, s.campos_con_texto) for s in lecturas] == (
        [(None, ["seccion"])] if reclama else []
    )
    assert [r.motivo for r in inv.rechazos] == []
    merge_external_specs(inv, [_ia("D-3", family="dala", section_cm=(25, 100))], C)
    de_la_ia = inv.by_mark["D-3"].section_cm if "D-3" in inv.by_mark else None
    assert de_la_ia == (None if reclama else (25, 100))


def test_a_wall_strip_between_the_title_and_a_section_stops_its_reach():
    # R129 (reemplaza el «pasa de largo» de R123): la tira de muro entre el título y la sección
    # dibujada no es sección, pero el título no llega más allá de ella: no toma la de más allá.
    ents = [
        _texto("m", "D-3", 0.0, 0.0, alto=0.1),
        _rectangulo("tira", -1.0, 0.3, 1.0, 0.349),
        _rectangulo("c", -0.5, 0.6, 0.5, 1.6),
        _cota("h", (-0.5, 0.6), (0.5, 0.6), 50),
        _cota("v", (-0.5, 1.6), (-0.5, 0.6), 100),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert _leidas(inv, "D-3") == {"D-3": []}
    (s,) = _cotas(inv, "D-3")
    assert s.avisos[0].startswith("sección: lo más cercano dibujado encima no es una sección")


@pytest.mark.parametrize("x,suya", [(-0.038, False), (-0.1, True)])
def test_a_graze_owns_nothing(x, suya):
    # R123 (D-5 en Marina, ES-006): su título toca la sección dibujada sólo en 15 % de su texto:
    # no es suya, ni la reclama, y la IA la llena; con 40 %, sí.
    ents = [
        _titulo("m", "D-5", x, 0.3),
        _rectangulo("c", -4.0, -4.0, 0.0, 0.0),
        _cota("lejos", (8.0, 8.0), (9.0, 8.0), 100),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [s.campos_con_texto for s in _cotas(inv, "D-5")] == ([["seccion"]] if suya else [])
    merge_external_specs(inv, [_ia("D-5", family="dala", section_cm=(25, 100))], C)
    de_la_ia = inv.by_mark["D-5"].section_cm if "D-5" in inv.by_mark else None
    assert de_la_ia == (None if suya else (25, 100))


def _flecha(entity_id, puntos, lider=False):
    flecha = _poligono(entity_id, puntos, cerrado=False)
    if lider:
        flecha.properties["derived_from"] = "LEADER"
    return flecha


@pytest.mark.parametrize(
    "flecha,senalada",
    [
        # Una flecha dibujada: el apoyo horizontal acaba en el título.
        (_flecha("f", [(-0.6, 0.4), (-0.3, 0.0), (-0.12, 0.0)]), True),
        # Una directriz LEADER (el normalizador la da como polilínea abierta).
        (_flecha("f", [(-0.12, 0.0), (-0.8, 0.5)], lider=True), True),
        # Una línea suelta de dos vértices que acaba en el título no es una flecha dibujada.
        (_flecha("f", [(-0.12, 0.0), (-0.8, 0.5)]), False),
        # Una flecha que acaba lejos del título (a 0.28 de su texto, más de 0.6 altos).
        (_flecha("f", [(-0.7, 0.4), (-0.5, 0.0), (-0.37, 0.0)]), False),
    ],
)
def test_a_title_with_a_leader_and_no_section_read_claims_it(flecha, senalada):
    # R124: un título del que sale una flecha (que empieza o se apoya en él) y cuya sección nadie
    # lee la reclama, ilegible, «señalada por flecha; se lee en E3»: la IA no la llena. A dónde
    # apunta no se lee (E3).
    ents = [
        _texto("m", "D-3", 0.0, 0.0, alto=0.1),
        flecha,
        _cota("lejos", (8.0, 8.0), (9.0, 8.0), 100),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    lecturas = [(s.section_cm, s.campos_con_texto, s.avisos) for s in _cotas(inv, "D-3")]
    aviso = ["sección: señalada por flecha; se lee en E3"]
    assert lecturas == ([(None, ["seccion"], aviso)] if senalada else [])
    merge_external_specs(inv, [_ia("D-3", family="dala", section_cm=(25, 100))], C)
    de_la_ia = inv.by_mark["D-3"].section_cm if "D-3" in inv.by_mark else None
    assert de_la_ia == (None if senalada else (25, 100))


@pytest.mark.parametrize(
    "titulo,familia,senalada",
    [
        # CE-5 en Marina: su familia (dala, por su prefijo) la lee su nota («CADENA DE ENRASE
        # 15x25 …»): la flecha no la reclama y la nota no se borra.
        ("CE-5", "dala", False),
        # D-3 en Marina: su título dice DADO (R130): la nota de las dalas no es suya; se reclama.
        ("DADO\nD-3", "dado", True),
    ],
)
def test_a_leader_claim_never_erases_what_a_family_note_reads(titulo, familia, senalada):
    # R124, R130 (ronda 5): la reclamación «señalada» sólo bloquea a la IA cuando nada del plano
    # lee la marca; la nota de su familia la lee.
    marca = titulo.split()[-1]
    ents = [
        _texto("m", titulo, 0.0, 0.0, alto=0.1),
        _flecha("f", [(-0.6, 0.4), (-0.3, -0.06), (0.4, -0.06)]),
        _texto("n", "DALA 15X25 4#3 E#2@15", 5.0, 5.0, alto=0.1),
        _cota("lejos", (8.0, 8.0), (9.0, 8.0), 100),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [s.section_cm for s in inv.specs if s.mark == "DALA"] == [(15, 25)]
    lecturas = [(s.family, s.avisos) for s in _cotas(inv, marca)]
    aviso = ["sección: señalada por flecha; se lee en E3"]
    assert lecturas == ([(familia, aviso)] if senalada else [])


def test_a_title_with_a_leader_whose_section_is_read_keeps_it():
    # R124: con su sección leída (sus cotas), la flecha no cambia nada; ni la de otro título de la
    # misma marca cuya sección nadie lee ahí (la marca está leída): sin conflicto.
    ents = [
        _texto("m", "D-3", 0.0, 2.7, alto=0.1),
        _flecha("f", [(-0.6, 3.1), (-0.3, 2.7), (-0.15, 2.7)]),
        _rectangulo("c", -0.5, 0.0, 0.5, 2.4),
        _cota("h", (-0.5, 0.0), (0.5, 0.0), 20),
        _cota("v", (-0.5, 2.4), (-0.5, 0.0), 50),
        _texto("m2", "D-3", 6.0, 2.7, alto=0.1),
        _flecha("f2", [(5.4, 3.1), (5.7, 2.7), (5.85, 2.7)]),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [(s.section_cm, s.avisos) for s in _cotas(inv, "D-3")] == [((20, 50), [])]
    d = construir_definiciones(inv, C)[0]["D-3"].seccion_cm
    assert (d.valor, d.en_conflicto) == ((20, 50), False)


@pytest.mark.parametrize("pareja", [False, True])
def test_a_cota_is_never_rounded(pareja):
    # R119: 41.55 es 41.55 (antes, 41.5), en el contorno y en el par de cotas.
    if pareja:
        ents = _detalle_sin_contorno("a", "T-1", 0.0, 2.6, (-1.0, 0.0, 1.0, 2.4), 30, 41.55)
    else:
        ents = [
            _texto("m", "T-1", 0.0, 2.9, alto=0.14),
            _rectangulo("c", -1.0, 0.0, 1.0, 2.4),
            _cota("h", (-1.0, 0.0), (1.0, 0.0), 30),
            _cota("v", (-1.0, 2.4), (-1.0, 0.0), 41.55),
        ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    (t,) = [s for s in _cotas(inv, "T-1") if s.section_cm]
    assert t.section_cm == (30, 41.55)


# ------------------------------------------------- Tarea 8b, ronda 5: R125, R128, R129, R130


def test_a_leader_landing_under_the_whole_title_is_its_leader():
    # R128 (CE-1 en Marina): la flecha llega por la izquierda y su apoyo corre bajo todo el texto
    # (0.10 de alto) y acaba 0.7 altos más allá de él; antes sólo se miraba su punta.
    ents = [
        _titulo("m", "CE-1", 0.0, 0.0, alto=0.1),
        _flecha("f", [(-0.259, 0.317), (-0.009, -0.003), (0.312, -0.003)]),
        _cota("lejos", (8.0, 8.0), (9.0, 8.0), 100),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [s.avisos for s in _cotas(inv, "CE-1")] == [
        ["sección: señalada por flecha; se lee en E3"]
    ]
    merge_external_specs(inv, [_ia("CE-1", family="dala", section_cm=(15, 30))], C)
    assert "CE-1" not in inv.by_mark or inv.by_mark["CE-1"].section_cm is None


@pytest.mark.parametrize(
    "texto,columna,marcas,familia",
    [
        # Títulos de más de 8 letras: nunca fueron etiquetas.
        ("DADO\nD-1A", True, ["D-1A"], "dado"),
        ("DADO D-1B / O D-1C", False, ["D-1B", "D-1C"], "dado"),
        ("PILOTE\nP-3", True, ["P-3"], "pilote"),
        # No es un título (una referencia): ninguna.
        ("VER DETALLE D-1A", False, [], None),
    ],
)
def test_a_long_title_with_a_leader_claims_each_of_its_marks(texto, columna, marcas, familia):
    # R128: para la reclamación de R124, un título es un texto hecho sólo de palabras de familia,
    # marcas y conectores, de cualquier largo; cada marca se reclama, con la familia que su título
    # dice (R130).
    titulo = (
        _titulo_en_columna("m", texto, 0.0, 0.0)
        if columna
        else _titulo("m", texto, 0.0, 0.0, alto=0.1)
    )
    x0, y0, x1, _y1 = _extension_del_texto(titulo)
    ents = [
        titulo,
        _flecha("f", [(x0 - 0.6, y0 + 0.5), (x0 - 0.3, y0 - 0.02), (x1, y0 - 0.02)]),
        _cota("lejos", (8.0, 8.0), (9.0, 8.0), 100),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    senaladas = sorted(
        (s.mark, s.family, s.familia_supuesta)
        for s in inv.specs
        if s.source_text.endswith("señalada por flecha; se lee en E3")
    )
    assert senaladas == [(m, familia, False) for m in marcas]


@pytest.mark.parametrize(
    "otra",
    [
        # Un castillo a escala 1:1 (15×15, letras de 0.14) bajo un contorno de 2.5 × 3.0 acotado
        # 250/300: antes K-1 leía 250x300.
        [
            _rectangulo("grande", -1.25, 0.5, 1.25, 3.5),
            _cota("h", (-1.25, 0.5), (1.25, 0.5), 250),
            _cota("v", (-1.25, 3.5), (-1.25, 0.5), 300),
        ],
        # Más allá de su símbolo, la sección de K-2 (20×40), cuyo título está en otra parte:
        # antes K-1 la tomaba.
        [
            _rectangulo("k2c", -0.5, 0.6, 0.5, 2.6),
            _cota("h", (-0.5, 0.6), (0.5, 0.6), 20),
            _cota("v", (-0.5, 2.6), (-0.5, 0.6), 40),
            _texto("k2", "K-2", 5.0, 0.0, alto=0.14),
        ],
    ],
)
def test_a_title_never_reaches_past_its_own_small_section(otra):
    # R129: su sección propia, chica y sin cotas, no es candidata, pero detiene al título: no
    # llega a lo acotado que está más allá.
    ents = [
        _texto("m", "K-1", 0.0, 0.0, alto=0.14),
        _rectangulo("chico", -0.075, 0.2, 0.075, 0.35),
        *otra,
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert _leidas(inv, "K-1") == {"K-1": []}


def test_a_trapezoid_is_never_owned_nor_sets_the_sheet_convention():
    # R129 (CTA-15 y el dado de D-4 en ES-500, corridos): un trapecio con una cota de 120 en su
    # arista no es sección: CTA-15 no es su dueño (ni un «sin_lector»), y la hoja no voltea su
    # costumbre por él: K-1, con su sección encima, la sigue leyendo.
    trapecio = [(0.0494, -2.298), (0.8494, -2.298), (0.8494, -1.098), (0.0494, -0.888)]
    ents = [
        _texto("m", "CTA-15", 0.62, -0.70, alto=0.1),
        _poligono("t", trapecio),
        _cota("v", (0.8494, -1.098), (0.8494, -2.298), 120),
        _texto("k", "K-1", 5.0, -2.0, alto=0.14),
        _rectangulo("kc", 4.8, -1.7, 5.2, -1.1),
        _cota("kh", (4.8, -1.7), (5.2, -1.7), 20),
        _cota("kv", (5.2, -1.1), (5.2, -1.7), 30),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [s.section_cm for s in _cotas(inv, "CTA-15")] in ([], [None])
    assert [r.motivo for r in inv.rechazos] == []
    assert _leidas(inv, "K-1") == {"K-1": [(20, 30)]}


def test_a_section_one_and_a_half_letters_wide_is_one_despite_float_noise():
    # R129: 0.15 contra 1.5 × 0.10 (CE-1 en Marina, su sección dibujada de 0.150 × 0.300): antes
    # el ruido de coma flotante la dejaba fuera; es sección, se reclama sin cotas.
    ents = [
        _titulo("m", "CE-1", 0.0, 0.0, alto=0.1),
        _rectangulo("c", 0.0, -0.45, 0.15, -0.15),
        _cota("lejos", (8.0, 8.0), (9.0, 8.0), 100),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [(s.section_cm, s.campos_con_texto) for s in _cotas(inv, "CE-1")] == [
        (None, ["seccion"])
    ]


@pytest.mark.parametrize(
    "texto,aviso_de_familia",
    [
        # El título dice DADO (R130): la familia es la del plano.
        ("DADO D-1B / O D-1C", None),
        # Sin palabra de familia, la del prefijo (dala) es supuesta (R125): gana la de la IA.
        (
            "D-1C",
            "familia: el plano no la dice (sólo el prefijo de la marca: dala); se toma la de la "
            "IA: dado",
        ),
    ],
)
def test_a_prefix_guessed_family_never_drops_a_field(texto, aviso_de_familia):
    # R125, R130 (D-1C en Marina, ES-007): su título señalado por una flecha se reclama, y la IA
    # (dado, 55×115, parrillas #4@10) no llena la sección; pero sus parrillas no se tiran por una
    # familia que sólo dice el prefijo: quedan como dato de la IA.
    titulo = _titulo("m", texto, 0.0, 0.0, alto=0.1)
    x0, y0, x1, _y1 = _extension_del_texto(titulo)
    ents = [
        titulo,
        _flecha("f", [(x0 - 0.6, y0 + 0.5), (x0 - 0.3, y0 - 0.02), (x1, y0 - 0.02)]),
        _cota("lejos", (8.0, 8.0), (9.0, 8.0), 100),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    ia = _ia("D-1C", family="dado", section_cm=(55, 115), mesh="#4@10")
    merge_external_specs(inv, [ia], C)
    d = construir_definiciones(inv, C)[0]["D-1C"]
    assert (d.familia, d.seccion_cm.valor, d.seccion_cm.ilegible) == ("dado", None, True)
    assert d.parrillas is not None and d.parrillas.fuente == "ia"
    if aviso_de_familia:
        assert aviso_de_familia in d.avisos
    else:
        assert not any(a.startswith("familia:") for a in d.avisos)


def test_two_texts_on_one_leader_are_one_title():
    # R130 (ES-007 en Marina): «DADO D-1B» sobre el apoyo y «O D-1C» bajo él son un título: D-1C
    # es dado y se reclama; la nota de las dalas no la lee.
    ents = [
        _titulo("a", "DADO D-1B", 0.0, 0.05, alto=0.1),
        _titulo("b", "O D-1C", 0.06, -0.14, alto=0.1),
        _flecha("f", [(-0.6, 0.4), (-0.3, 0.0), (0.55, 0.0)]),
        _texto("n", "DALA 15X25 4#3 E#2@15", 5.0, 5.0, alto=0.1),
        _cota("lejos", (8.0, 8.0), (9.0, 8.0), 100),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    senaladas = sorted(
        (s.mark, s.family)
        for s in inv.specs
        if s.source_text.endswith("señalada por flecha; se lee en E3")
    )
    assert senaladas == [("D-1B", "dado"), ("D-1C", "dado")]
