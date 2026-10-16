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
    mark_cuadro_detections,
    merge_external_specs,
)
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.dxf.entities import EntityType, EvidencePacket, NormalizedEntity
from klave_engine.dxf.parser import DxfParser
from klave_engine.dxf.text_extent import extension_de_texto
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


def test_each_group_of_labels_keeps_its_own_side():
    # R165 (CR-2 en Marina, ES-200): la hoja tiene un cuadro (sus secciones encima de sus
    # etiquetas) y, lejos, el detalle «CERRAMIENTOS» (su sección debajo de su título). Cada grupo de
    # etiquetas cercanas tiene su lado: el cuadro no le quita a CR-2 su «una cota 20».
    ents = []
    for i, x in enumerate((0.0, 3.0, 6.0)):
        contorno = (x - 0.5, 0.9, x + 0.5, 2.4)
        ents += _castillo(f"k{i}", f"K-{i + 1}", x, 0.0, ["4#3", "E#2@15"], contorno, 20, 30)
    ents += [
        _texto("cm", "CR-2", 30.0, 0.0),
        _texto("cr", "4#3", 30.6, 0.0, alto=0.10),
        _rectangulo("cc", 29.6, -1.3, 30.4, -0.5),
        _cota("ch", (29.6, -1.3), (30.4, -1.3), 20),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0)
    assert [s.section_cm for s in _cotas(inv, "K-1")] == [(20, 30)]
    (cr2,) = _cotas(inv, "CR-2")
    assert (cr2.section_cm, cr2.source_text) == ((20, 20), "CR-2 · una cota 20")


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
        # R150: y lo dice: su sección dibujada no es un rectángulo.
        "sección: la dibujada no es un rectángulo",
        "las cotas cercanas (30, 60) no se toman",
    ]
    assert k.seccion_no_rectangular is True
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
    izquierda de su base; su caja, la que da el normalizador (R146: donde la pone su alineación,
    0.9 altos por carácter). Con ``halign`` 2, alineado a la derecha en ``x`` (su punto de
    alineación; el ``insert`` como lo deja un DXF sin calcular, en el mismo punto)."""
    propiedades = {"height": alto, "insert": (x, y)}
    if halign:
        propiedades |= {"halign": halign, "align_point": (x, y)}
    return _con_su_caja(
        NormalizedEntity(
            entity_id=entity_id, entity_type=EntityType.text, source_file="a.dxf", layer="T",
            bbox=(x, y, x, y), text=text, properties=propiedades, raw_handle=entity_id,
            evidence=_evidencia(entity_id, (x, y, x, y)),
        )
    )  # fmt: skip


def _con_su_caja(texto):
    """El texto con la caja que le da el normalizador (R146)."""
    texto.bbox = extension_de_texto(texto)
    return texto


def _leidas(inv, *marcas):
    return {m: [s.section_cm for s in _cotas(inv, m) if s.section_cm] for m in marcas}


@pytest.mark.parametrize(
    "texto,x,halign,leida",
    [
        # Su ancla dentro de la sección y su texto encima (53 %): es suya.
        ("T-1", 1.0, 0, (20, 50)),
        # T2-8 en Marina (ES-201): alineado a la izquierda, su ancla 1.36 altos antes de la sección
        # (260.966 contra 261.157) y su texto encima de ella (0.313 de 0.504, 62 %): es suya.
        ("T2-8", 0.2 - 0.191, 0, (20, 50)),
        # T3-1 en Marina: su ancla dentro, pero sólo 19 % de su texto encima: menos de un tercio,
        # no es suya (R123).
        ("T-1", 1.13, 0, None),
        # Su texto empieza 0.4 altos después de la sección: no está encima, no es suya (la holgura
        # de media altura de R115 ya no existe).
        ("T-1", 1.256, 0, None),
        # Alineado a la derecha en 1.3, pasada la sección: su texto acaba encima de ella (74 %; una
        # caja desde el insert no la tocaría): es suya.
        ("T-1", 1.3, 2, (20, 50)),
        # Alineado a la derecha en 0.15, antes de la sección: su texto no la toca (una caja desde
        # el insert sí): no es suya.
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
        # T-1 entero encima de la sección y T-9 en 0.1 de sus 0.378: es de T-1.
        (1.1, True),
        # T-9 encima en 0.329 de 0.378 (87 %) contra el 100 % de T-1: menos del 25 % de margen:
        # de ninguno, reclamada por los dos.
        (0.871, False),
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
        # Un título ancho (1.35) encima de dos secciones, de la primera 0.9 y de la otra 0.25: es
        # la primera.
        (0.3, False, {"T-1": [(20, 50)], "T-2": []}),
        # Encima de las dos igual (0.575 y 0.575): de ninguna; la reclama.
        (0.625, False, {"T-1": [], "T-2": []}),
        # Igual, pero la segunda tiene su título entero encima: es de su título, y la primera
        # queda del título ancho.
        (0.625, True, {"T-1": [(20, 50)], "T-2": [(30, 60)]}),
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
    if x_titulo == 0.625 and not vecina:
        (t1,) = _cotas(inv, "T-1")
        assert t1.campos_con_texto == ["seccion"]
        assert "su título está sobre dos rectángulos de pares de cotas" in t1.avisos[0]


def _titulo_en_columna(entity_id, text, x, y, alto=0.1):
    """Un MTEXT como los de ES-500 en Marina: insertado arriba a la izquierda, con una columna de
    1.358 y el párrafo centrado en ella («\\pxqc»); su caja, la del normalizador (R146)."""
    propiedades = {
        "height": alto,
        "insert": (x, y),
        "attachment_point": 1,
        "column_width": 1.357913709497112,
        "paragraph_align": "c",
    }
    return _con_su_caja(
        NormalizedEntity(
            entity_id=entity_id, entity_type=EntityType.mtext, source_file="a.dxf", layer="T",
            bbox=(x, y, x, y), text=text, properties=propiedades, raw_handle=entity_id,
            evidence=_evidencia(entity_id, (x, y, x, y)),
        )
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
        # R139: la flecha reclama también el armado (DADO lleva parrillas; la familia de CTA-8 la
        # dice sólo su prefijo, que no exime nada: R155).
        assert (s.section_cm, s.campos_con_texto) == (None, _ARMADO_SENALADO)
        assert s.avisos == ["sección: señalada por flecha; se lee en E3"]
        assert s.source_text.endswith("señalada por flecha; se lee en E3")
    assert [r for r in inv.rechazos if r.motivo == "ambigua"] == []
    merge_external_specs(inv, [_ia("D-3", family="dala", section_cm=(25, 100))], C)
    assert "D-3" not in inv.by_mark or inv.by_mark["D-3"].section_cm is None


# R139: lo que reclama una flecha: la sección y el armado (las parrillas si la familia las lleva
# o si sólo la dice el prefijo de la marca, R155).
_ARMADO_SENALADO = ["seccion", "longitudinales", "estribos", "parrillas"]

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


@pytest.mark.parametrize("x,suya", [(-0.057, False), (-0.151, True)])
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
        # Una directriz LEADER (el normalizador la da como polilínea abierta, de la punta de la
        # flecha a su apoyo): su apoyo acaba en el título.
        (_flecha("f", [(-0.8, 0.5), (-0.12, 0.0)], lider=True), True),
        # R136: la punta de un LEADER en el título es a lo que apunta, nunca su título.
        (_flecha("f", [(-0.12, 0.0), (-0.8, 0.5)], lider=True), False),
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
    # «D-3» sin palabra de familia: sólo el prefijo la dice, y no exime nada (R155).
    assert lecturas == ([(None, _ARMADO_SENALADO, aviso)] if senalada else [])
    merge_external_specs(inv, [_ia("D-3", family="dala", section_cm=(25, 100))], C)
    de_la_ia = inv.by_mark["D-3"].section_cm if "D-3" in inv.by_mark else None
    assert de_la_ia == (None if senalada else (25, 100))


@pytest.mark.parametrize(
    "titulo,nota,familia,senalada",
    [
        # CE-1 en Marina: la nota de su familia («CADENA DE ENRASE 15x25 …») no la nombra: es el
        # respaldo de la familia, no la lee (R132): se reclama y su IA (15x30) no se elige.
        ("CE-1", "DALA 15X25 4#3 E#2@15", "dala", True),
        # Una nota que nombra a la marca sí la lee: la flecha no la reclama ni la borra.
        ("CE-5", "CE-5 15X25 4#3 E#2@15", "dala", False),
        # D-3 en Marina: su título dice DADO (R130); la nota de las dalas no la nombra.
        ("DADO\nD-3", "DALA 15X25 4#3 E#2@15", "dado", True),
    ],
)
def test_only_a_reading_that_names_the_mark_stops_a_leader_claim(titulo, nota, familia, senalada):
    # R124, R132 (ronda 5): la reclamación «señalada» sólo bloquea a la IA cuando ninguna lectura
    # que nombra la marca (nota de la marca, pila, renglón de cuadro, cotas, llamada) da su
    # sección; la nota de la familia nunca cuenta.
    marca = titulo.split()[-1]
    ents = [
        _texto("m", titulo, 0.0, 0.0, alto=0.1),
        _flecha("f", [(-0.6, 0.4), (-0.3, -0.06), (0.4, -0.06)]),
        _texto("n", nota, 5.0, 5.0, alto=0.1),
        _cota("lejos", (8.0, 8.0), (9.0, 8.0), 100),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [s.section_cm for s in inv.specs if s.source == "nota"] == [(15, 25)]
    lecturas = [(s.family, s.avisos) for s in _cotas(inv, marca)]
    aviso = ["sección: señalada por flecha; se lee en E3"]
    assert lecturas == ([(familia, aviso)] if senalada else [])
    merge_external_specs(inv, [_ia(marca, family="dala", section_cm=(15, 30))], C)
    elegida = inv.by_mark[marca].section_cm if marca in inv.by_mark else None
    assert elegida == (None if senalada else (15, 25))


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
    # R125, R130, R155 (D-1C en Marina, ES-007): su título señalado por una flecha se reclama, y
    # la IA (dado, 55×115, parrillas #4@10) no llena la sección ni las parrillas: el detalle al que
    # apunta las dibuja (R139), y una familia que sólo dice el prefijo no exime ningún campo; la
    # IA no se tira: queda como alternativa.
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
    assert d.parrillas is not None
    assert d.parrillas.ilegible and d.parrillas.fuente == "detalle"
    assert any(a.fuente == "ia" for a in d.parrillas.alternativas)
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


# ------------------------------------------------- Tarea 9, paso previo A: R136


def test_a_title_spelled_otherwise_never_outranks_the_note_that_reads_its_mark():
    # R136: «K1» con su flecha y la nota «K-1 20X40 …» son la misma marca (``normalizar_marca``):
    # la nota la lee, así que la flecha no la reclama ni tapa su 20×40 con un ilegible de detalle.
    ents = [
        _titulo("m", "K1", 0.0, 0.0, alto=0.1),
        _flecha("f", [(-0.6, 0.4), (-0.3, -0.02), (0.2, -0.02)]),
        _texto("n", "K-1 20X40 4#3 E#2@15", 5.0, 5.0, alto=0.1),
        _cota("lejos", (8.0, 8.0), (9.0, 8.0), 100),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert not [s for s in inv.specs if s.source_text.endswith("señalada por flecha; se lee en E3")]
    d = construir_definiciones(inv, C)[0]["K-1"].seccion_cm
    assert (d.valor, d.fuente, d.ilegible) == ((20, 40), "nota", False)


@pytest.mark.parametrize("lider", ["LEADER", "MULTILEADER"])
def test_only_the_landing_of_a_leader_attaches_to_a_title(lider):
    # R136: un LEADER o una MULTILEADER va de la punta de su flecha (lo que señala) a su apoyo (su
    # título). La marca suelta «K-7» en la punta no es su título: no se reclama ni toma la familia
    # del título «DADO D-3», que sí está en el apoyo.
    flecha = _flecha("f", [(-1.0, 1.0), (-0.3, -0.02), (0.5, -0.02)])
    flecha.properties["derived_from"] = lider
    ents = [
        _titulo("t", "DADO D-3", 0.0, 0.0, alto=0.1),
        _texto("k", "K-7", -1.0, 1.05, alto=0.1),
        flecha,
        _cota("lejos", (8.0, 8.0), (9.0, 8.0), 100),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    senaladas = sorted(
        (s.mark, s.family)
        for s in inv.specs
        if s.source_text.endswith("señalada por flecha; se lee en E3")
    )
    assert senaladas == [("D-3", "dado")]


# ------------------------------------------------- Tarea 9, ronda 1: R139, R140, R145, M-7


def _grupo_de_cadenas(dx=0.0, armado=True):
    """El grupo «CADENAS DE ENRASE» de Marina (ES-400) dentro de una planta (no hay marco de
    detalle): títulos de 0.15 encima, sus secciones dibujadas debajo con su cota de ancho arriba
    y la de alto a la derecha, el armado tres metros abajo y la nota «SIN ESCALA»."""
    ents = []
    for n, (marca, x, ancho_m, b) in enumerate(
        [("CE-1", 0.0, 0.854, 15), ("CE-2", 2.0, 0.971, 20), ("CE-3", 4.0, 1.709, 30)]
    ):
        x0 = x + dx
        x1 = x0 + ancho_m
        ents += [
            _titulo(f"t{n}", marca, x0 + 0.16, 0.46, alto=0.15),
            _rectangulo(f"s{n}", x0, -1.709, x1, 0.0),
            _cota(f"h{n}", (x0, 0.0), (x1, 0.0), b),
            _cota(f"v{n}", (x1, -1.709), (x1, 0.0), 30),
        ]
        if armado:
            ents += [
                _texto(f"r{n}", ["4#3", "6#3", "6#4"][n], x0 + 0.42, -2.47, alto=0.1),
                _texto(f"e{n}", ["E#2@15", "E#2@15", "E#3@14"][n], x0 + 0.42, -2.67, alto=0.1),
            ]
    ents += [
        _texto("g", "CADENAS DE ENRASE", 2.4, -3.2, alto=0.16),
        _texto("n", "ACOTACIONES EN CMS, SIN ESCALA", 2.4, -3.5, alto=0.1),
    ]
    return ents


def _etiqueta_de_viga(entity_id, marca):
    det = make_detection(
        f"d_{entity_id}", DetectionType.beam_tag, marca, (0, 0, 0.3, 0.15), 0.9, [entity_id],
        "t", [], {"estimated_span_length": 1.708},
    )  # fmt: skip
    return det


def test_a_label_owning_a_dimensioned_section_inside_a_planta_is_a_detail_title():
    # R145 (C-1): las 22 cadenas y cerramientos de Marina dibujados dentro de las plantas
    # ES-100…ES-400 no son colocaciones: cada título es dueño de su sección acotada; es una
    # definición (role=cuadro, «título de detalle») y su sección se lee: 15x30, 20x30, 30x30.
    ents = _grupo_de_cadenas()
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=[])
    leidas = {s.mark: s.section_cm for s in inv.specs if s.metodo == "cotas"}
    assert leidas == {"CE-1": (15, 30), "CE-2": (20, 30), "CE-3": (30, 30)}
    assert sorted(inv.titulos_de_detalle) == ["t0", "t1", "t2"]
    assert {"t0", "t1", "t2"} <= set(inv.cuadro_mark_entities)
    dets = [_etiqueta_de_viga(t, m) for t, m in (("t0", "CE-1"), ("t1", "CE-2"), ("t2", "CE-3"))]
    assert mark_cuadro_detections(dets, inv) == 3
    assert all(d.properties["role"] == "cuadro" for d in dets)
    assert all(d.properties["titulo_de_detalle"] is True for d in dets)


def test_a_plan_tag_beside_its_marker_and_a_grid_cota_stays_a_placement():
    # R145, el pin: una etiqueta de castillo en planta junto a su marcador (sin cotas) y cerca
    # de la cadena de cotas de los ejes nunca es un título.
    ents = [
        _titulo("k", "K-1", 0.0, 0.25, alto=0.1),
        _rectangulo("m", 0.0, 0.4, 0.15, 0.6),
        _cota("c1", (-3.0, -0.4), (0.0, -0.4), 300),
        _cota("c2", (0.0, -0.4), (3.0, -0.4), 300),
        _cota("lejos", (8.0, 8.0), (9.0, 8.0), 100),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=[])
    assert inv.titulos_de_detalle == [] and "k" not in inv.cuadro_mark_entities
    assert [s for s in inv.specs if s.mark == "K-1"] == []
    det = make_detection("dk", DetectionType.column_tag, "K-1", (0, 0, 1, 1), 0.9, ["k"], "t", [])
    mark_cuadro_detections([det], inv)
    assert "role" not in det.properties


def test_the_unowned_armado_under_a_titles_section_blocks_its_ai():
    # R140: el armado escrito bajo la sección de cada título («4#3», «E#2@15»), que nadie lee,
    # puede ser de ese título: bloquea la IA de su marca en esos campos (la sección ya es suya).
    ents = _grupo_de_cadenas()
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=[])
    posibles = {r.texto: r.posibles for r in inv.rechazos if r.motivo == "sin_dueno"}
    assert posibles["4#3"] == ["CE-1"] and posibles["E#3@14"] == ["CE-3"]
    ia = _ia("CE-1", family="dala", section_cm=(15, 30), rebar="4#3", stirrups="E#2@15")
    merge_external_specs(inv, [ia], C)
    d = construir_definiciones(inv, C)[0]["CE-1"]
    assert d.longitudinales is None and d.estribos is None
    assert set(d.sin_leer) == {"longitudinales", "estribos"}
    assert (d.seccion_cm.valor, d.seccion_cm.fuente) == ((15, 30), "detalle")


def test_the_unowned_armado_beside_a_detail_section_blocks_the_ai():
    # R140 (CTA-1 en Marina, ES-002): la IA leyó 8#4 / E#4; el detalle escribe «4#4» y «E#4»
    # junto a la sección (35x80 por su par de cotas) y nadie los leyó: la IA no se toma.
    ents = _detalle_sin_contorno("a", "CTA-1", 0.6, 3.5, (0.0, 0.0, 1.325, 3.136), 35, 80)
    ents += [
        _texto("r", "4#4", 1.55, 1.4, alto=0.11, centrado=False),
        _texto("e", "E#4", 1.55, 0.03, alto=0.11, centrado=False),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [s.section_cm for s in _cotas(inv, "CTA-1")] == [(35, 80)]
    merge_external_specs(inv, [_ia("CTA-1", family="contratrabe", rebar="8#4", stirrups="E#4")], C)
    d = construir_definiciones(inv, C)[0]["CTA-1"]
    assert d.longitudinales is None and d.estribos is None
    assert set(d.sin_leer) == {"longitudinales", "estribos"}


def test_a_leader_claim_covers_the_armado_too():
    # R139 (CE-1 en Marina, ES-500/ES-501): la sección a la que apunta la flecha dibuja también
    # sus varillas y su estribo: la IA no llena ni la sección ni el armado.
    ents = [
        _titulo("m", "CE-1", 0.0, 0.0, alto=0.1),
        _flecha("f", [(-0.259, 0.317), (-0.009, -0.003), (0.312, -0.003)]),
        _cota("lejos", (8.0, 8.0), (9.0, 8.0), 100),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    (claim,) = _cotas(inv, "CE-1")
    assert claim.campos_con_texto == _ARMADO_SENALADO
    ia = _ia("CE-1", family="dala", section_cm=(15, 30), rebar="4#3", stirrups="E#2@15")
    merge_external_specs(inv, [ia], C)
    d = construir_definiciones(inv, C)[0]["CE-1"]
    for campo in ("seccion_cm", "longitudinales", "estribos"):
        dato = getattr(d, campo)
        assert dato.ilegible and dato.fuente == "detalle", campo
        assert any(a.fuente == "ia" for a in dato.alternativas), campo
    assert "m" in inv.titulos_de_detalle


def test_a_leader_never_closes_a_section_outline():
    # M-7: tres trazos y una directriz LEADER encima del cuarto lado no son un contorno cerrado:
    # el título no es dueño de nada ahí y no reclama una sección.
    lider = _flecha("l", [(1.0, 1.0), (0.0, 1.0)], lider=True)
    ents = [
        _texto("m", "T-1", 0.5, 1.2, alto=0.1),
        _linea("a", (0.0, 1.0), (0.0, 0.0)),
        _linea("b", (0.0, 0.0), (1.0, 0.0)),
        _linea("c", (1.0, 0.0), (1.0, 1.0)),
        lider,
        _cota("lejos", (8.0, 8.0), (9.0, 8.0), 100),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert _cotas(inv, "T-1") == []


def test_the_unowned_armado_under_a_titles_section_is_said_even_without_ai():
    # R140 (CE-5 en Marina: sin lectura IA): su armado está escrito bajo su sección y nadie lo
    # leyó; la definición lo dice, para que el elemento no diga «la marca no lo dice».
    inv = build_schedule_inventory(_grupo_de_cadenas(), C, unit_to_m=1.0, detail_boxes=[])
    d = construir_definiciones(inv, C)[0]["CE-3"]
    assert d.longitudinales is None and d.estribos is None
    assert d.sin_leer == {"longitudinales": "«6#4»", "estribos": "«E#3@14»"}


# ------------------------------------------------- Tarea 9, ronda 2: R149, R150


def _cota_lineal(entity_id, p, q, cm, angulo):
    """Una cota lineal (dimtype 0) que mide sobre ``angulo`` aunque sus puntos no estén uno sobre
    otro: la del alto de CE-1, de la esquina de la sección a la losa junto a ella."""
    cota = _cota(entity_id, p, q, cm)
    cota.properties |= {"dimtype": 0, "angle": angulo}
    return cota


def _ce1(dx=0.0, arriba_hasta=1.214, marca="CE-1"):
    """CE-1 (15x30) como en Marina: arriba la línea sigue hasta la losa (``arriba_hasta``), el
    lado derecho sólo abajo, y su «30» va de su esquina de abajo a la losa (punto lejano)."""
    return [
        _titulo("ta", marca, dx + 0.16, 0.46, alto=0.15),
        _linea("a1", (dx, 0.0), (dx + arriba_hasta, 0.0)),
        _linea("a2", (dx, -1.709), (dx, 0.0)),
        _linea("a3", (dx, -1.709), (dx + 0.854, -1.709)),
        _linea("a4", (dx + 0.854, -1.709), (dx + 0.854, -1.424)),
        _cota("ah", (dx, 0.0), (dx + 0.854, 0.0), 15),
        _cota_lineal("av", (dx + 0.854, -1.709), (dx + 1.214, 0.0), 30, 90.0),
    ]


def test_the_projected_corner_keeps_ce1():
    # R149, el pin: CE-1 se sigue leyendo 15x30 (su arista de arriba llega al punto lejano, su
    # «30» no es una suma, nada atraviesa su lado).
    inv = build_schedule_inventory(_ce1(), C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [s.section_cm for s in _cotas(inv, "CE-1")] == [(15, 30)]


def test_a_section_beside_the_far_point_never_borrows_the_depth():
    # R149 (a): B (20 de ancho, 25 de alto, sin línea arriba) está al pie del «30» de CE-1; la
    # esquina que ese «30» proyecta al pie de B no tiene arista dibujada hasta el punto lejano
    # (entre CE-1 y B no hay línea): B no lee 20x30.
    ents = _ce1() + [
        _titulo("tb", "CE-2", 1.4, 0.46, alto=0.15),
        _linea("b1", (1.214, -1.709), (2.354, -1.709)),
        _linea("b2", (1.214, -1.709), (1.214, -0.284)),
        _linea("b3", (2.354, -1.709), (2.354, -0.284)),
        _cota("bh", (1.214, -1.709), (2.354, -1.709), 20),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert (20, 30) not in [s.section_cm for s in _cotas(inv, "CE-2")]
    assert [s.section_cm for s in _cotas(inv, "CE-1")] == [(15, 30)]


@pytest.mark.parametrize("piezas", [(33, 20), (48, 5), (30, 18, 5)])
def test_an_overall_cota_is_never_a_sections_depth(piezas):
    # R149 (b), R153 (ES-203 «DET.MB» en Marina): el «53» de conjunto es «33» del muro más «20» de
    # la dala de remate; con el «35» de ancho no hacen una sección de 35x53. Toda cota de 1 cm o
    # más es una pieza (R153): «48» + «5» y «30» + «18» + «5» también. El título es de un
    # cerramiento, que sí puede acotarse a una esquina proyectada: sólo la suma la rechaza.
    ents = [
        _titulo("t", "CR-1", 0.1, 0.8, alto=0.12),
        _linea("l1", (0.0, 0.53), (0.6, 0.53)),
        _linea("l2", (0.0, 0.0), (0.0, 0.53)),
        _linea("l3", (0.0, 0.0), (0.35, 0.0)),
        _linea("l4", (0.35, 0.0), (0.35, 0.53)),
        _cota("h", (0.0, 0.53), (0.35, 0.53), 35),
        _cota_lineal("v", (0.35, 0.0), (0.6, 0.53), 53, 90.0),
    ]
    y = 0.0
    for n, cm in enumerate(piezas):
        ents.append(_cota(f"v{n}", (0.9, y), (0.9, y + cm / 100), cm))
        y += cm / 100
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert (35, 53) not in [s.section_cm for s in _cotas(inv, "CR-1")]


def test_without_the_chain_the_cerramiento_reads_its_projected_corner():
    # R153, el pin del anterior: sin la cadena de cotas al lado, el mismo dibujo es una sección
    # de 35x53 de un cerramiento.
    ents = [
        _titulo("t", "CR-1", 0.1, 0.8, alto=0.12),
        _linea("l1", (0.0, 0.53), (0.6, 0.53)),
        _linea("l2", (0.0, 0.0), (0.0, 0.53)),
        _linea("l3", (0.0, 0.0), (0.35, 0.0)),
        _linea("l4", (0.35, 0.0), (0.35, 0.53)),
        _cota("h", (0.0, 0.53), (0.35, 0.53), 35),
        _cota_lineal("v", (0.35, 0.0), (0.6, 0.53), 53, 90.0),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [s.section_cm for s in _cotas(inv, "CR-1")] == [(35, 53)]


@pytest.mark.parametrize("marca", ["T-1", "CE-6"])
def test_a_beam_under_a_slab_never_takes_the_slab_in_its_depth(marca):
    # R149 (c): la trabe (20 de ancho) cuelga de la losa; el «50» va de su esquina de abajo a la
    # cara de arriba de la losa, más allá de la trabe, y la cara de abajo de la losa (dibujada
    # desde dentro de la trabe hacia la derecha: no la cruza de lado a lado, R118 no la ve)
    # atraviesa el lado de la trabe: no es una sección de 20x50, aunque el «40» esté dibujado.
    # Con el título de una cadena (CE-6), que sí puede acotarse así (R153), la rechaza (c).
    ents = [
        _titulo("t", marca, 0.0, 0.25, alto=0.1),
        _linea("losa_arriba", (-1.0, 0.0), (1.2, 0.0)),
        _linea("losa_abajo", (0.1, -0.1), (1.2, -0.1)),
        _linea("t1", (0.0, -0.5), (0.2, -0.5)),
        _linea("t2", (0.0, -0.5), (0.0, -0.1)),
        _linea("t3", (0.2, -0.5), (0.2, -0.1)),
        _cota("h", (0.0, 0.0), (0.2, 0.0), 20),
        _cota_lineal("v", (0.2, -0.5), (0.5, 0.0), 50, 90.0),
        _cota("v40", (-0.3, -0.5), (-0.3, -0.1), 40),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert (20, 50) not in [s.section_cm for s in _cotas(inv, marca)]


def test_unowned_armado_beyond_its_sections_group_stays_unowned():
    # R150 (las «CADENAS INTERMEDIAS» de ES-200 en Marina, junto al cuadro de castillos): el
    # armado de otro detalle, con su encabezado entre él y la sección dueña, o a más de tres altos
    # de ella, no es de esa marca: queda sin dueño, sin «posible».
    ents = _grupo_de_cadenas() + [
        _texto("lejos", "4#5", 0.5, -7.5, alto=0.1),
        _texto("ci", "CADENAS INTERMEDIAS", 7.3, -0.8, alto=0.16),
        _texto("tras", "8#4", 8.9, -0.8, alto=0.1),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=[])
    posibles = {r.texto: r.posibles for r in inv.rechazos if r.motivo == "sin_dueno"}
    assert posibles["4#5"] == [] and posibles["8#4"] == []
    assert posibles["4#3"] == ["CE-1"] and posibles["6#4"] == ["CE-3"]


def test_a_plan_castillo_whose_marker_carries_a_cota_is_no_detail_title():
    # R150 (R145 latente): una etiqueta de castillo en planta, del alto de las demás, en su capa,
    # sobre su marcador acotado y sin encabezado de detalle cerca: sigue siendo una colocación.
    ents = [
        _titulo("k", "K-1", 0.0, 0.25, alto=0.1),
        _titulo("k2", "K-2", 6.0, 0.25, alto=0.1),
        _titulo("k3", "K-3", 9.0, 0.25, alto=0.1),
        _rectangulo("m", 0.0, -0.4, 0.2, 0.0),
        _cota("h", (0.0, 0.0), (0.2, 0.0), 20),
        _cota("v", (0.2, 0.0), (0.2, -0.4), 40),
    ]
    for e in ents:
        e.layer = "EST-CASTILLOS"
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=[])
    assert inv.titulos_de_detalle == [] and "k" not in inv.cuadro_mark_entities


def test_a_non_rectangular_drawn_section_is_said_in_the_definition():
    # R150 (K-15A en Marina): lo más cercano dibujado sobre su título es su sección en L, que no
    # es un rectángulo: la definición lo dice (para usar el área de su contorno en planta, R142).
    ele = [(0.0, 0.5), (0.6, 0.5), (0.6, 0.9), (0.3, 0.9), (0.3, 1.7), (0.0, 1.7)]
    ents = [
        _titulo("m", "K-15A", 0.05, 0.25, alto=0.1),
        _poligono("l", ele),
        _cota("h", (0.0, 0.5), (0.6, 0.5), 60),
        _cota("v", (0.0, 1.7), (0.0, 0.5), 30),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert all(s.seccion_no_rectangular for s in _cotas(inv, "K-15A"))
    assert construir_definiciones(inv, C)[0]["K-15A"].seccion_no_rectangular


@pytest.mark.parametrize("abierta", [False, True])
def test_armado_under_a_section_nobody_owns_is_that_sections(abierta):
    # R150 (las «CI» de ES-200 en Marina, su armado debajo): aunque la sección de CE-3 esté al lado
    # y al alcance, el armado de la sección de la CI es de ella, nunca de CE-3. R154: también
    # dibujada abierta, con un par de cotas que comparten su esquina (R106). R152: la «CI» es la
    # marca de su tipo (antes, sin marca, su armado quedaba sin dueño).
    seccion = (
        [
            _linea("ci1", (6.6, -1.2), (7.4, -1.2)),
            _linea("ci2", (6.6, -1.2), (6.6, 0.0)),
            _linea("ci3", (7.4, -1.2), (7.4, 0.0)),
            _cota("cih", (6.6, -1.2), (7.4, -1.2), 30),
        ]
        if abierta
        else [_rectangulo("cis", 6.6, -1.2, 7.4, 0.0), _cota("cih", (6.6, 0.0), (7.4, 0.0), 30)]
    )
    ents = (
        _grupo_de_cadenas(armado=False)
        + seccion
        + [
            _texto("ci", "CI", 7.0, 0.3, alto=0.13),
            _cota("civ", (7.4, -1.2), (7.4, 0.0), 20),
            _texto("cir", "6#3", 7.0, -1.45, alto=0.1),
        ]
    )
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=[])
    posibles = {r.texto: r.posibles for r in inv.rechazos if r.motivo == "sin_dueno"}
    assert posibles["6#3"] == ["CI"]


# ------------------------------------------------- Tarea 9, ronda 3: R153, R154, R155, R156


def test_a_shared_base_line_never_lends_the_depth_to_the_section_beside():
    # R153 (a): una línea de base común bajo CE-1 y B. La esquina que el «30» de CE-1 proyecta al
    # pie de B tiene dibujada su arista hasta el punto lejano (la base común), pero el otro punto
    # de la cota (1.214, 0) no está en el lado dibujado de B, que acaba en −0.284: B lee su propio
    # «25», nunca 20x30.
    ents = _ce1() + [
        _titulo("tb", "CE-2", 1.4, 0.46, alto=0.15),
        _linea("base", (0.854, -1.709), (2.354, -1.709)),
        _linea("b2", (1.214, -1.709), (1.214, -0.284)),
        _linea("b3", (2.354, -1.709), (2.354, -0.284)),
        _cota("bh", (1.214, -1.709), (2.354, -1.709), 20),
        _cota("bv", (2.354, -1.709), (2.354, -0.284), 25),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [s.section_cm for s in _cotas(inv, "CE-2")] == [(20, 25)]


@pytest.mark.parametrize("marca,lee", [("CE-1", True), ("CR-1", True), ("T-1", False),
                                       ("CTA-1", False)])  # fmt: skip
def test_only_a_cadena_or_a_cerramiento_reads_a_projected_corner(marca, lee):
    # R153: la esquina proyectada (el «30» de CE-1, de su esquina a la losa junto a ella) es el
    # dibujo de una cadena o un cerramiento. Una trabe o una contratrabe dibujada igual (la cara
    # de abajo de la losa sólo llega a su lado) necesita una esquina real (R106): su sección queda
    # reclamada, sin valor, y nada la llena (ni el 20x50 de la losa con la trabe).
    inv = build_schedule_inventory(_ce1(marca=marca), C, unit_to_m=1.0, detail_boxes=_DETALLE)
    (s,) = _cotas(inv, marca)
    if lee:
        assert s.section_cm == (15, 30)
    else:
        assert s.section_cm is None and s.campos_con_texto == ["seccion"]
        assert any("esquina proyectada" in a for a in s.avisos)
        merge_external_specs(inv, [_ia(marca, family="trabe", section_cm=(15, 30))], C)
        d = construir_definiciones(inv, C)[0][marca]
        assert (d.seccion_cm.valor, d.seccion_cm.ilegible) == (None, True)


def test_armado_under_the_title_under_its_section_blocks_the_ai():
    # R154: la sección arriba, su título debajo y el armado bajo el título (una cadena dibujada
    # así): su propio título no está «entre» el armado y su sección; la IA (4#8, E#4@30) no se
    # toma.
    ents = [
        _rectangulo("s", 0.0, 0.0, 1.709, 1.709),
        _cota("h", (0.0, 1.709), (1.709, 1.709), 30),
        _cota("v", (1.709, 0.0), (1.709, 1.709), 30),
        _titulo("t", "CE-3", 0.6, -0.35, alto=0.15),
        _texto("r", "6#4", 0.85, -0.75, alto=0.1),
        _texto("e", "E#3@14", 0.85, -0.95, alto=0.1),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [s.section_cm for s in _cotas(inv, "CE-3")] == [(30, 30)]
    posibles = {r.texto: r.posibles for r in inv.rechazos if r.motivo == "sin_dueno"}
    assert posibles == {"6#4": ["CE-3"], "E#3@14": ["CE-3"]}
    merge_external_specs(inv, [_ia("CE-3", family="dala", rebar="4#8", stirrups="E#4@30")], C)
    d = construir_definiciones(inv, C)[0]["CE-3"]
    assert d.longitudinales is None and d.estribos is None
    assert set(d.sin_leer) == {"longitudinales", "estribos"}


def test_armado_across_a_corner_of_its_section_blocks_the_ai():
    # R154 (T4-4 en Marina, ES-400): «2#6» junto a la esquina de arriba a la derecha de su
    # sección, ni encima ni al lado de ella: es de su grupo (a tres altos, nada entre ellos).
    ents = [
        _titulo("t", "T4-4", 0.031, 0.158, alto=0.14),
        _rectangulo("s", 0.0, -3.3, 0.6, 0.0),
        _cota("h", (0.0, -3.3), (0.6, -3.3), 15),
        _cota("v", (0.6, -3.3), (0.6, 0.0), 82.5),
        _texto("r", "2#6", 0.882, 0.223, alto=0.11),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [s.section_cm for s in _cotas(inv, "T4-4")] == [(15, 82.5)]
    posibles = {r.texto: r.posibles for r in inv.rechazos if r.motivo == "sin_dueno"}
    assert posibles == {"2#6": ["T4-4"]}
    merge_external_specs(inv, [_ia("T4-4", family="trabe", rebar="3#5")], C)
    d = construir_definiciones(inv, C)[0]["T4-4"]
    assert d.longitudinales is None and "longitudinales" in d.sin_leer


def test_a_leader_from_armado_into_a_section_gives_it_to_that_title_whatever_the_distance():
    # R154 (T4-4 y T1-2 en Marina: «2#6» y la V que va de él a dos varillas de la sección): un
    # texto de armado con una directriz dibujada que acaba dentro de una sección con dueño es de
    # ese título, a cualquier distancia (aquí, más allá de tres altos). La que acaba dentro de la
    # sección acotada de una «CI» (marca de su tipo desde R152) es de ella, aunque CE-3 esté al
    # lado.
    ents = _grupo_de_cadenas(armado=False) + [
        _texto("lejos", "2#6", 0.5, -7.5, alto=0.1),
        _poligono("v", [(0.2, -1.5), (0.40, -7.44), (0.65, -1.5)], cerrado=False),
        _texto("ci", "CI", 7.0, 0.3, alto=0.13),
        _rectangulo("cis", 6.6, -1.2, 7.4, 0.0),
        _cota("cih", (6.6, 0.0), (7.4, 0.0), 30),
        _cota("civ", (7.4, -1.2), (7.4, 0.0), 20),
        _texto("junto", "3#5", 5.0, -2.3, alto=0.1),
        _poligono("w", [(6.8, -0.6), (5.11, -2.26), (7.2, -0.6)], cerrado=False),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=[])
    posibles = {r.texto: r.posibles for r in inv.rechazos if r.motivo == "sin_dueno"}
    assert posibles == {"2#6": ["CE-1"], "3#5": ["CI"]}


@pytest.mark.parametrize(
    "titulo,familia_de_la_ia,reclamada",
    [
        # Sólo el prefijo dice contratrabe: no exime nada; las parrillas se reclaman (R155).
        ("CTA-8", None, True),
        # La IA dice contratrabe: la familia final es de viga, dicha: sin parrillas.
        ("CTA-8", "contratrabe", False),
        # El título la dice (R130): sin parrillas.
        ("CONTRATRABE CTA-8", None, False),
    ],
)
def test_only_a_stated_beam_family_exempts_a_leaders_parrillas(titulo, familia_de_la_ia, reclamada):
    # R155: la exención de parrillas de una familia de viga usa la familia FINAL de la
    # definición; una que sólo dice el prefijo nunca exime un campo.
    t = _titulo("m", titulo, 0.0, 0.0, alto=0.1)
    x0, y0, x1, _y1 = _extension_del_texto(t)
    ents = [
        t,
        _flecha("f", [(x0 - 0.6, y0 + 0.5), (x0 - 0.3, y0 - 0.02), (x1, y0 - 0.02)]),
        _cota("lejos", (8.0, 8.0), (9.0, 8.0), 100),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    if familia_de_la_ia:
        merge_external_specs(inv, [_ia("CTA-8", family=familia_de_la_ia, section_cm=(30, 70))], C)
    d = construir_definiciones(inv, C)[0]["CTA-8"]
    if reclamada:
        assert d.parrillas is not None and d.parrillas.ilegible
        assert d.parrillas.fuente == "detalle"
    else:
        assert d.parrillas is None


def test_a_title_with_a_leader_never_takes_the_shape_of_the_outline_under_it():
    # R156 (CTA-15 en Marina, ES-500): bajo el título está el trapecio del dado D-4, y su flecha
    # apunta a su sección (dentro de él): el trapecio no es su sección, no dice que la suya no sea
    # un rectángulo.
    trapecio = [(0.049, -1.698), (0.849, -1.698), (0.849, -0.498), (0.049, -0.288)]
    ents = [
        _texto("m", "CTA-15", 0.334, -0.003, alto=0.1),
        _poligono("t", trapecio),
        _cota("v", (0.849, -0.498), (0.849, -1.698), 120),
        _flecha("f", [(0.25, -0.671), (0.45, -0.073), (0.60, -0.073)]),
        _texto("d", "DADO\nD-4", 0.636, -1.518, alto=0.1),
        # Una cota de ancho cerca, como el «120» de Marina: la sección se reclama (R123).
        _cota("w", (0.2, -2.2), (0.5, -2.2), 30),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert _cotas(inv, "CTA-15")
    assert not any(s.seccion_no_rectangular for s in _cotas(inv, "CTA-15"))
    assert not any(a == "sección: la dibujada no es un rectángulo" for s in inv.specs
                   for a in s.avisos)  # fmt: skip
    assert not construir_definiciones(inv, C)[0]["CTA-15"].seccion_no_rectangular


def test_another_titles_non_rectangular_outline_says_nothing_of_this_one():
    # R156: de dos títulos bajo la misma L, es de K-15A (que se le encima entera); K-15B, que se le
    # encima menos, no toma su forma.
    ele = [(0.0, 0.5), (0.6, 0.5), (0.6, 0.9), (0.3, 0.9), (0.3, 1.7), (0.0, 1.7)]
    ents = [
        _titulo("a", "K-15A", 0.05, 0.25, alto=0.1),
        _titulo("b", "K-15B", 0.45, 0.25, alto=0.1),
        _poligono("l", ele),
        _cota("h", (0.0, 0.5), (0.6, 0.5), 60),
        _cota("v", (0.0, 1.7), (0.0, 0.5), 30),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert all(s.seccion_no_rectangular for s in _cotas(inv, "K-15A"))
    assert not any(s.seccion_no_rectangular for s in _cotas(inv, "K-15B"))


# ------------------------------------------------- Tarea 9, ronda 4: R157, R158, R159


def test_a_projected_rectangle_two_titles_reach_is_claimed_by_both():
    # R157: de quién es el rectángulo se decide entre TODOS los títulos; CE-1 y T-1 se le encima
    # igual: los dos lo reclaman (R111), ninguno lo lee.
    ents = [e for e in _ce1() if e.entity_id != "ta"] + [
        _titulo("a", "CE-1", 0.05, 0.46, alto=0.15),
        _titulo("b", "T-1", 0.5, 0.46, alto=0.15),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    for marca in ("CE-1", "T-1"):
        (s,) = _cotas(inv, marca)
        assert s.section_cm is None, marca
        assert any("lo alcanza también" in a for a in s.avisos), marca


@pytest.mark.parametrize(
    "marca,encabezado,lee",
    [
        ("D-1", None, False),  # D-: dala o dado (R159), sola nunca
        ("D-1", "CADENAS DE ENRASE", True),  # el encabezado de su grupo la dice
        ("DALA D-1", None, True),  # la palabra de su título la dice
        ("CE-1", None, True),  # un prefijo sin duda
    ],
)
def test_a_projected_corner_needs_the_cadena_stated(marca, encabezado, lee):
    # R159: la esquina proyectada sólo la lee una cadena o un cerramiento DICHOS.
    ents = _ce1(marca=marca)
    if encabezado:
        ents.append(_texto("g", encabezado, 0.6, -2.6, alto=0.16))
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    leida = marca.split()[-1]
    (s,) = _cotas(inv, leida)
    if lee:
        assert s.section_cm == (15, 30)
    else:
        assert s.section_cm is None
        assert any("esquina proyectada" in a for a in s.avisos)


def _t3_21():
    """T3-21 de Marina (ES-302), con el origen en la esquina de abajo a la izquierda de su
    sección: la losa llega a sus dos lados (sus lados sólo dibujados en parte), la cota de ancho va
    de un punto de su lado izquierdo a su esquina de abajo, la de alto por su lado izquierdo: no hay
    par (R106) ni contorno; el título reclama su sección («las cotas cercanas … no se toman»)."""
    ancho = _cota_lineal("h", (0.0, 0.8), (0.976, 0.0), 20, 0.0)
    ancho.bbox = (-0.05, -0.3, 1.026, 0.05)  # su línea de cota va bajo la sección
    return [
        _titulo("t", "T3-21", -0.017, 2.171, alto=0.14),
        _linea("arriba", (0.0, 2.0), (1.246, 2.0)),
        _linea("der", (0.976, 0.0), (0.976, 1.2)),
        _linea("izq", (0.0, 0.8), (0.0, 2.0)),
        _linea("abajo", (0.0, 0.0), (0.976, 0.0)),
        _linea("losa_der", (0.976, 1.2), (1.246, 1.2)),
        _linea("losa_izq", (-0.27, 0.8), (0.0, 0.8)),
        _linea("abajo_izq", (-0.27, 0.0), (0.0, 0.0)),
        ancho,
        _cota("v", (0.0, 2.0), (0.0, 0.0), 50),
    ]


def test_armado_of_a_beam_where_a_slab_meets_it_blocks_its_ai():
    # R158 (T3-21 en Marina): su sección queda reclamada sin contorno ni par; el rectángulo que
    # sus cotas abarcan es su sección reclamada: su «2#6», con su V hacia dos varillas, y el
    # «E#3@15» bajo ella son suyos y bloquean la IA de su armado.
    ents = _t3_21() + [
        _texto("r", "2#6", 1.255, 2.333, alto=0.11),
        _flecha("f", [(0.854, 1.876), (1.195, 2.254), (0.122, 1.876)]),
        _texto("e", "E#3@15", 0.454, -0.387, alto=0.11),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    (s,) = _cotas(inv, "T3-21")
    assert s.section_cm is None
    posibles = {r.texto: r.posibles for r in inv.rechazos if r.motivo == "sin_dueno"}
    assert posibles == {"2#6": ["T3-21"], "E#3@15": ["T3-21"]}
    merge_external_specs(inv, [_ia("T3-21", family="trabe", rebar="3#6", stirrups="E#3@20")], C)
    d = construir_definiciones(inv, C)[0]["T3-21"]
    assert d.longitudinales is None and d.estribos is None
    assert set(d.sin_leer) == {"longitudinales", "estribos"}


def test_a_section_two_titles_claim_gives_its_armado_to_both():
    # R158 (R111): una sección dibujada que alcanzan dos títulos por igual la reclaman los dos;
    # el armado bajo ella puede ser de cualquiera: bloquea a los dos.
    ents = [
        _titulo("a", "T-1", 0.1, 0.3, alto=0.14),
        _titulo("b", "T-2", 0.55, 0.3, alto=0.14),
        _rectangulo("s", 0.0, -2.0, 1.0, 0.0),
        _cota("h", (0.0, -2.0), (1.0, -2.0), 30),
        _cota("v", (1.0, -2.0), (1.0, 0.0), 60),
        _texto("r", "3#6", 0.5, -2.35, alto=0.11),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [s.section_cm for s in _cotas(inv, "T-1")] == [None]
    posibles = {r.texto: r.posibles for r in inv.rechazos if r.motivo == "sin_dueno"}
    assert posibles == {"3#6": ["T-1", "T-2"]}


def _t2_10():
    """T2-10 de Marina (ES-201), con el origen en la esquina de abajo a la izquierda de su sección
    (1.057 × 1.754, acotada 30x40) y su alzado a la derecha, a la misma altura."""
    return [
        _titulo("t", "T2-10", 0.131, 2.082, alto=0.14),
        _rectangulo("s", 0.0, 0.0, 1.057, 1.754),
        _cota("h", (0.0, 0.0), (1.057, 0.0), 30),
        _cota("v", (0.0, 1.754), (0.0, 0.0), 40),
        _linea("alzado_arriba", (1.756, 1.781), (7.735, 1.781)),
        _linea("alzado_abajo", (1.756, 0.004), (7.735, 0.004)),
        _linea("alzado_apoyo", (1.756, 0.004), (1.756, 1.781)),
    ]


def test_armado_on_a_beams_elevation_beside_its_section_blocks_its_ai():
    # R158, R150 (T2-10 en Marina): «3#4», «2#6» y «@18» van en su alzado, a 3.5 de su sección
    # (más que su lado mayor, menos que tres altos, en su banda de altura): son de su grupo. Un
    # texto a la misma distancia fuera de su banda y de su columna, no.
    ents = _t2_10() + [
        _texto("a", "3#4", 4.671, 1.577, alto=0.1),
        _texto("b", "2#6", 4.698, 0.21, alto=0.1),
        _texto("c", "@18", 4.651, -0.099, alto=0.1),
        _texto("d", "4#5", 4.0, 4.6, alto=0.1),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    posibles = {r.texto: r.posibles for r in inv.rechazos if r.motivo == "sin_dueno"}
    assert posibles == {"3#4": ["T2-10"], "2#6": ["T2-10"], "@18": ["T2-10"], "4#5": []}
    merge_external_specs(inv, [_ia("T2-10", family="trabe", rebar="3#6")], C)
    d = construir_definiciones(inv, C)[0]["T2-10"]
    assert d.longitudinales is None and "longitudinales" in d.sin_leer


def test_armado_on_a_sloped_elevation_outline_is_its_beams():
    # R158 (TE-A en Marina, ES-007: una trabe en rampa): su alzado es un paralelogramo cerrado que
    # empieza junto a su sección y sube; el «2#6+1#4» escrito en él, a más de 6 de la sección, es
    # suyo.
    ents = [
        _titulo("t", "TE-A", 0.111, 1.759, alto=0.14),
        _rectangulo("s", 0.0, 0.0, 0.8, 1.6),
        _cota("h", (0.0, 0.0), (0.8, 0.0), 20),
        _cota("v", (0.0, 1.6), (0.0, 0.0), 40),
        _poligono("alzado", [(1.529, 0.117), (1.529, 1.6), (12.882, 5.571), (12.882, 4.088)]),
        _texto("r", "2#6+1#4", 7.107, 3.204, alto=0.1),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    posibles = {r.texto: r.posibles for r in inv.rechazos if r.motivo == "sin_dueno"}
    assert posibles == {"2#6+1#4": ["TE-A"]}


# ------------------------------------------------- Tarea 9, ronda 5: R161, R162, R163


@pytest.mark.parametrize("abajo,suyo", [(1.2, True), (1.5, False)])
def test_the_column_reach_stops_at_1_3_section_heights(abajo, suyo):
    # R161: bajo su sección (su columna), el armado llega a 1.3 de sus altos, ya no a tres: lo
    # que va más abajo es de otro alzado (A9852 «2#8+2#6» de T2-6A en Marina, que caía en T2-9).
    alto = 1.754
    ents = _t2_10() + [_texto("r", "2#8+2#6", 0.5, -abajo * alto - 0.05, alto=0.1)]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    posibles = {r.texto: r.posibles for r in inv.rechazos if r.motivo == "sin_dueno"}
    assert posibles["2#8+2#6"] == (["T2-10"] if suyo else [])


@pytest.mark.parametrize(
    "textos",
    [
        # El encabezado de un grupo vecino (o el de abajo), a más de 1.5 altos de la sección.
        [("CADENAS DE ENRASE", 0.6, -5.3)],
        [("CADENAS INTERMEDIAS", 0.4, -5.6)],
        # Una nota que nombra la cadena en medio.
        [("2 VARILLAS #5 ANCLADA AL MURO O CADENA", 0.9, -2.6)],
        # El subtítulo de un detalle (T2-10 en Marina).
        [("(A NIVEL DE CERRAMIENTO)", 0.9, -2.4)],
        # Un renglón de las notas generales.
        [("1.- LAS CADENAS Y CASTILLOS SERAN DE F'C=150", 1.6, -2.4)],
        # El encabezado más cercano es de dados; el de cadenas va más lejos.
        [("DADOS", 0.4, -2.2), ("CADENAS DE ENRASE", 0.6, -3.1)],
    ],
)
def test_only_the_nearest_heading_opening_its_text_states_a_cadena(textos):
    # R162: una «D-1» sobre el dibujo de CE-1 lee la esquina proyectada sólo si el encabezado de
    # grupo MÁS CERCANO a su sección abre su texto con «CADENAS»/«CERRAMIENTOS» y está en su
    # grupo: ni notas, ni subtítulos, ni el grupo de al lado.
    ents = _ce1(marca="D-1") + [
        _texto(f"g{n}", texto, x, y, alto=0.16) for n, (texto, x, y) in enumerate(textos)
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    (s,) = _cotas(inv, "D-1")
    assert s.section_cm is None
    assert any("esquina proyectada" in a for a in s.avisos)


def _t3_8():
    """T3-8 de Marina (ES-301), con el origen en (251.173, −25.881): a la izquierda de su sección
    el escalón de la losa nervada (A9009) con su «60» horizontal (A9033) y su «30» (A9032), y el
    «60» girado de esquina a esquina (E266C); su sección (su «20» de ancho, A90B7) a la derecha,
    de la losa (A9087) al fondo, que corre bajo los tres (A9074). Su título va sobre el escalón y
    acaba a 0.05 de su sección."""
    return [
        _titulo("t", "T3-8", 1.799, 2.606, alto=0.14),
        _poligono("escalon", [(0.0, 0.0), (0.0, 1.237), (2.357, 1.237), (2.357, 2.52)], False),
        _linea("fondo", (0.0, 0.0), (4.426, 0.0)),
        _cota("h60", (0.0, 1.237), (2.357, 1.237), 60),
        _cota("v30", (0.0, 0.0), (0.0, 1.237), 30),
        _cota_lineal("v60", (0.0, 0.0), (2.357, 2.243), 60, 90.0),
        _poligono("t38", [(3.141, 2.52), (3.141, 0.786), (4.426, 0.786)], False),
        _cota_lineal("b20", (2.357, 1.237), (3.141, 0.786), 20, 0.0),
    ]


@pytest.mark.parametrize("x,suya", [(0.8, True), (0.85, False)])
def test_a_title_over_a_quarter_of_its_claimed_box_gives_it_its_armado(x, suya):
    # R165 (T3-1 en Marina, ES-301): el rectángulo que reclaman sus cotas sólo atribuye armado,
    # nunca una lectura: basta un cuarto de su texto real encima (28 % de 0.63); un quinto no.
    ents = _t3_21()
    ents[0] = _titulo("t", "T3-21", x, 2.171, alto=0.14)
    ents.append(_texto("e", "E#3@15", 0.454, -0.387, alto=0.11))
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [s.section_cm for s in _cotas(inv, "T3-21")] == [None]
    posibles = {r.texto: r.posibles for r in inv.rechazos if r.motivo == "sin_dueno"}
    assert posibles == {"E#3@15": ["T3-21"] if suya else []}


def test_a_claimed_box_is_the_titles_own_drawn_section():
    # R164 (T3-8 en Marina): el escalón de la losa («60» × «30», sus cotas sí se encuentran en una
    # esquina) no es la sección de T3-8 aunque su título vaya encima: el título acaba a 0.05 de la
    # junta con su propia sección («20» × «60»). En la junta de dos piezas acotadas, de cuál es no
    # se sabe: no reclama ninguna. El escalón es una pieza acotada que no es de nadie: lo que va
    # escrito en él es suyo (sin dueño), nunca del título más cercano. Y el rectángulo de los dos
    # «60» (uno a media altura, otro girado) tiene una esquina sin dibujar: no es un rectángulo.
    ents = _t3_8() + [
        _texto("r", "4#4", 1.0, 0.6, alto=0.11),
        _texto("e", "2E#3@15", -0.6, 0.25, alto=0.1),
        _flecha("fe", [(-0.3, 0.25), (0.15, 0.6)]),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [s.section_cm for s in _cotas(inv, "T3-8")] == [None]
    posibles = {r.texto: r.posibles for r in inv.rechazos if r.motivo == "sin_dueno"}
    assert posibles == {"4#4": [], "2E#3@15": []}


def _t2_7():
    """T2-7 de Marina (ES-201), con el origen en (236.626, 3.485): una sección compuesta — su
    cuerpo de 50 × 72.5 (capa de detalles: A9A9A, A9A9B, A9A9C, A9AA1) y, a su izquierda y abajo,
    el ala de 60 × 30 (capa 0: A9C9B, A9C9C, A9C9D). Sus cotas no se encuentran en una esquina:
    el «50» (A9A9D) va del pie del lado izquierdo del cuerpo a la esquina de abajo a la derecha, y
    el «42.5» (AFD22) de la esquina del ala a la de arriba del cuerpo; sus cajas, las de Marina
    (la del «50» es apenas más alta que ancha)."""
    h50 = _cota_lineal("h50", (2.001, 1.068), (3.734, 0.0), 50, 180.0)
    h50.bbox = (1.951, -0.769, 3.784, 1.068)
    v42 = _cota_lineal("v42", (0.0, 1.068), (2.001, 2.485), 42.5, 90.0)
    v42.bbox = (-0.295, 1.018, 2.001, 2.535)
    return [
        _titulo("t", "T2-7", 2.537, 2.624, alto=0.14),
        _linea("arriba", (3.734, 2.485), (2.001, 2.485)),
        _linea("der", (3.734, 2.282), (3.734, 0.0)),
        _linea("izq", (2.001, 1.068), (2.001, 2.485)),
        _linea("abajo", (2.001, 0.0), (3.734, 0.0)),
        _linea("ala_abajo", (2.001, 0.0), (0.0, 0.0)),
        _linea("ala_arriba", (2.001, 1.068), (0.0, 1.068)),
        _linea("ala_izq", (0.0, 0.0), (0.0, 1.068)),
        _linea("losa", (4.004, 2.485), (3.734, 2.485)),
        h50,
        v42,
        _cota_lineal("h60", (0.0, 0.0), (2.001, -0.567), 60, 180.0),
        _cota("v30", (0.0, 0.0), (0.0, 1.068), 30),
        _cota("v72", (-0.295, 0.0), (-0.295, 2.485), 72.5),
        _cota("h110", (0.0, -0.769), (3.734, -0.769), 110),
    ]


def test_a_composite_sections_own_box_is_claimed():
    # R164 (T2-7 en Marina): sus cotas «50» y «42.5» no se encuentran en una esquina, pero el
    # rectángulo que abarcan está dibujado (sus cuatro esquinas sobre sus líneas): es su sección,
    # reclamada (nunca leída). Su «2#6», con su flecha al cuerpo, y lo de su alzado («2#8»,
    # «1@6,8@15») son suyos: bloquean su IA.
    ents = _t2_7() + [
        _texto("r", "2#6", 1.722, 1.395, alto=0.1),
        _flecha("f", [(2.116, 0.921), (1.781, 1.317), (3.6, 0.921)]),
        _texto("a", "2#8", 5.771, 2.211, alto=0.1),
        _texto("e", "1@6,8@15", 5.106, -0.109, alto=0.1),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [s.section_cm for s in _cotas(inv, "T2-7")] == [None]
    posibles = {r.texto: r.posibles for r in inv.rechazos if r.motivo == "sin_dueno"}
    assert posibles == {"2#6": ["T2-7"], "2#8": ["T2-7"], "1@6,8@15": ["T2-7"]}
    merge_external_specs(inv, [_ia("T2-7", family="trabe", rebar="4#8", stirrups="E#4@15")], C)
    d = construir_definiciones(inv, C)[0]["T2-7"]
    assert d.longitudinales is None and d.estribos is None
    assert {"longitudinales", "estribos"} <= set(d.sin_leer)


def test_a_notes_panel_beside_a_section_is_no_elevation():
    # R163: el marco de las notas generales de una hoja (un rectángulo cerrado de 5.68 × 29 que
    # empieza junto a una sección) no es el alzado de esa sección: lo que va escrito en él no es
    # suyo. El alzado en rampa de TE-A (su test) lo sigue siendo.
    ents = [
        _titulo("t", "TE-A", 0.111, 1.759, alto=0.14),
        _rectangulo("s", 0.0, 0.0, 0.8, 1.6),
        _cota("h", (0.0, 0.0), (0.8, 0.0), 20),
        _cota("v", (0.0, 1.6), (0.0, 0.0), 40),
        _rectangulo("notas", 1.0, -14.0, 6.68, 15.0),
        _texto("r", "2#6", 4.0, 8.0, alto=0.1),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    posibles = {r.texto: r.posibles for r in inv.rechazos if r.motivo == "sin_dueno"}
    assert posibles == {"2#6": []}


def _cr1(*notas):
    """CR-1 de Marina (ES-200), con el origen en la esquina de abajo a la izquierda de su sección
    (0.854 × 1.139, dibujada sin escala): su ancho «15» con dimlfac 100 (centímetros, fijos por su
    estilo) y su alto «20» con dimlfac 1 (el estilo no dice su unidad); ``notas`` son las notas de
    unidad de su grupo, como (texto, x, y)."""
    alto = _cota("v", (0.0, 1.139), (0.0, 0.0), 20)
    alto.properties |= {"dimlfac": 1.0, "display_value": 20.0, "measurement": 1.139}
    return [
        _titulo("t", "CR-1", 0.25, 1.341, alto=0.13),
        _rectangulo("s", 0.0, 0.0, 0.854, 1.139),
        _cota("h", (0.0, 0.0), (0.854, 0.0), 15),
        alto,
        *(_texto(f"n{i}", t, x, y, alto=0.1) for i, (t, x, y) in enumerate(notas)),
    ]


_EN_CMS = "ACOTACIONES EN CMS, SIN ESCALA"


@pytest.mark.parametrize(
    "notas,leida,aviso",
    [
        # Su grupo dice «EN CMS»: el «20» de dimlfac 1 es 20 cm (R151).
        ([(_EN_CMS, 0.976, -1.554)], (15, 20), None),
        # En la fila de notas bajo su título, la suya y, al lado, la «EN MMS» del grupo vecino
        # (ES-200: CERRAMIENTOS y COLUMNAS METÁLICAS): la que tiene debajo.
        ([(_EN_CMS, 0.976, -1.554), ("ACOTACIONES EN MMS, SIN ESCALA", -2.6, -1.554)], (15, 20),
         None),
        # Una nota más arriba que su título (la de otro grupo encima) no es la suya.
        ([("ACOTACIONES EN MMS, SIN ESCALA", 0.476, 2.5)], None,
         "peralte 2000 cm fuera de rango: no se toma"),
        # Sin nota, el estilo manda: 20 m, fuera de rango (como antes).
        ([], None, "peralte 2000 cm fuera de rango: no se toma"),
        # Una nota a más de 60 de sus alturas bajo el título no es de su grupo.
        ([(_EN_CMS, 0.976, -5.0)], None, "peralte 2000 cm fuera de rango: no se toma"),
        # «EN MMS»: 20 mm, fuera de rango; el «15» de dimlfac 100 sigue en centímetros.
        ([("ACOTACIONES EN MMS, SIN ESCALA", 0.976, -1.554)], None,
         "peralte 2 cm fuera de rango: no se toma"),
        # Dos notas que no coinciden, las dos bajo su título en la misma fila: no se sabe cuál es
        # la de su grupo; la cota no se toma y la sección se reclama.
        ([(_EN_CMS, 0.976, -1.554), ("ACOTACIONES EN MMS, SIN ESCALA", -0.2, -1.554)], None,
         "cota «20»: las notas de unidad de su grupo no coinciden (cm, mm): no se toma"),
    ],
)  # fmt: skip
def test_a_unit_note_declares_the_unit_of_its_own_groups_cotas(notas, leida, aviso):
    # R151: «ACOTACIONES EN CMS/MMS/METROS» vale sólo para las cotas de su grupo y sólo donde el
    # dimlfac no fija la unidad (el alto «20» de los CR de Marina, dimlfac 1 en un plano en metros).
    inv = build_schedule_inventory(_cr1(*notas), C, unit_to_m=1.0, detail_boxes=_DETALLE)
    (s,) = _cotas(inv, "CR-1")
    assert s.section_cm == leida
    if aviso is not None:
        assert any(aviso in a for a in s.avisos), s.avisos
        assert "seccion" in s.campos_con_texto  # reclamada: nada la llena de otro lado


# ------------------------------------------------- Tarea 9b, ronda de arreglos 1: R174


def _cota_suelta(entity_id, p, q, numero):
    """Una cota de dimlfac 1 (su estilo no dice la unidad de su número)."""
    cota = _cota(entity_id, p, q, numero)
    cota.properties |= {"dimlfac": 1.0, "display_value": float(numero)}
    return cota


def _unidades(ents):
    from klave_engine.detection.schedules import _con_unidad_declarada

    dims = [e for e in ents if e.entity_type == EntityType.dimension]
    salida = _con_unidad_declarada(dims, ents, 1.0, C)
    unidad = {d.entity_id: d.properties.get("unidad_declarada") for d in salida}
    conflicto = {d.entity_id: d.properties.get("unidades_en_conflicto") for d in salida}
    return {k: unidad[k] or conflicto[k] for k in unidad}


def test_a_cotas_group_is_its_nearest_heading_of_any_kind():
    # R174 (Marina ES-200): las cotas «254» y «12.7» de CM-1 (que no es una marca) están bajo
    # «COLUMNAS METÁLICAS» / «ACOTACIONES EN MMS»; su título de marca más cercano es CR-1, cuya
    # nota dice «EN CMS». Su grupo es el encabezado más cercano: milímetros. La cota de CR-1
    # sigue con la nota de su grupo, centímetros.
    ents = [
        _titulo("cr1", "CR-1", 197.81, 4.95, alto=0.13),
        _texto("cm", "COLUMNAS METÁLICAS", 195.235, 2.605, alto=0.15),
        _texto("mms", "ACOTACIONES EN MMS, SIN ESCALA", 195.235, 2.24, alto=0.1),
        _texto("cerr", "CERRAMIENTOS", 199.95, 2.54, alto=0.16),
        _texto("cms", "ACOTACIONES EN CMS, SIN ESCALA", 199.955, 2.17, alto=0.1),
        _cota_suelta("254", (195.789, 4.734), (194.522, 4.734), 254),
        _cota_suelta("12.7", (194.584, 4.072), (194.522, 4.072), 12.7),
        _cota_suelta("cr", (197.8, 3.4), (197.8, 4.54), 20),
    ]
    assert _unidades(ents) == {"254": 0.001, "12.7": 0.001, "cr": 0.01}


def test_a_general_note_never_scopes_a_details_cotas():
    # R174 (PRUEBA-1): las cotas del detalle de T-8 tomaban «1.- ACOTACIONES Y NIVELES EN METROS,
    # EXCEPTO INDICADOS», la primera de las NOTAS GENERALES junto a PLANTA BAJA, 5 m abajo: una
    # nota general (numerada) no es la de ningún grupo de detalle.
    nota = "1.- ACOTACIONES Y NIVELES EN METROS, EXCEPTO INDICADOS"
    ents = [
        _titulo("t8", "T-8", 68.07, -62.97, alto=0.39),
        _cota_suelta("40", (67.33, -61.31), (67.33, -60.11), 40),
        _texto("ng", "NOTAS  GENERALES", 68.78, -67.33, alto=0.3),
        _texto("n1", nota, 67.2, -67.885, alto=0.11),
    ]
    assert _unidades(ents) == {"40": None}
    # Escrita como la nota de un grupo, bajo su encabezado, sí lo es (R151).
    ents[3] = _texto("n1", "ACOTACIONES EN METROS", 67.2, -67.885, alto=0.11)
    assert _unidades(ents) == {"40": 1.0}


def test_a_titles_note_is_never_across_another_groups_heading():
    # R174: entre el título y la fila de notas que encuentra (la de DADOS), el encabezado largo de
    # otro grupo sobre la columna del título (su nota, bajo su otra punta, lejos de lado): la nota
    # de DADOS no es la del grupo del título.
    ents = [
        _titulo("t", "T-1", 0.0, 5.0, alto=0.1),
        _cota_suelta("c", (0.0, 4.5), (0.6, 4.5), 30),
        _texto("otro", "CONEXIÓN COLUMNA CM-1 CON TRABE METÁLICA", 4.0, 3.0, alto=0.4),
        _texto("su_nota", "ACOTACIONES EN MMS, SIN ESCALA", 8.4, 2.6, alto=0.1),
        _texto("dados", "DADOS", 0.3, 0.87, alto=0.15),
        _texto("cms", "ACOTACIONES EN CMS, SIN ESCALA", 0.3, 0.5, alto=0.1),
    ]
    assert _unidades(ents) == {"c": None}
    # Sin ese encabezado, la de DADOS es la de su grupo (R151).
    assert _unidades([e for e in ents if e.entity_id != "otro"]) == {"c": 0.01}


# ------------------------------------------------- Tarea 9c: R168, variantes por muro


def _ci(dx, ancho_cm, muros, n):
    """Un detalle «CI» de Marina (ES-200): el título, su subtítulo «(PARA MUROS DE nCM)» debajo y
    su sección (ancho × 20, sin escala: 0.854 de ancho por cada 15 cm) bajo ellos."""
    ancho = 0.854 * ancho_cm / 15
    ents = [
        _titulo(f"t{n}", "CI", dx + 0.33, 1.466, alto=0.13),
        _rectangulo(f"s{n}", dx, 0.0, dx + ancho, 1.139),
        _cota(f"h{n}", (dx, 0.0), (dx + ancho, 0.0), ancho_cm),
        _cota(f"v{n}", (dx, 1.139), (dx, 0.0), 20),
    ]
    if muros is not None:
        ents.append(_texto(f"m{n}", muros, dx + 0.43, 1.325, alto=0.1))
    return ents


def test_a_detail_title_declaring_its_wall_is_a_variant_of_its_mark():
    # R168: los títulos «CI» de Marina llevan debajo «(PARA MUROS DE 15CM)», «(… 20CM)» y
    # «(… 30CM)»: cada lectura es la variante de ese muro, y la definición de CI las guarda.
    ents = [
        *_ci(0.0, 15, "(PARA MUROS DE 15CM)", 1),
        *_ci(3.0, 20, "(PARA MUROS DE 20CM)", 2),
        *_ci(6.0, 30, "(PARA MUROS DE 30CM)", 3),
    ]
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    leidas = sorted((s.section_cm, s.para_muro_cm) for s in _cotas(inv, "CI"))
    assert leidas == [((15, 20), 15.0), ((20, 20), 20.0), ((30, 20), 30.0)]
    d = construir_definiciones(inv, C)[0]["CI"]
    assert d.seccion_cm.en_conflicto
    assert [(v.para_muro_cm, v.seccion_cm.valor) for v in d.variantes] == [
        (15.0, (15, 20)),
        (20.0, (20, 20)),
        (30.0, (30, 20)),
    ]
    assert not any(v.seccion_cm.en_conflicto for v in d.variantes)


@pytest.mark.parametrize(
    "muros", [None, "CADENAS INTERMEDIAS (PARA MUROS DE 15/20/30 CM)", "(PARA MUROS DE 15CM)"]
)
def test_only_a_titles_own_subtitle_makes_a_variant(muros):
    # R168: sin subtítulo, con el encabezado de todo el grupo («15/20/30»), o con el subtítulo de
    # otro título (aquí lejos, bajo la sección): no es una variante.
    ents = _ci(0.0, 15, None, 1)
    if muros is not None:
        ents.append(_texto("m", muros, 0.43, -1.0, alto=0.1))
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0, detail_boxes=_DETALLE)
    assert [s.para_muro_cm for s in _cotas(inv, "CI")] == [None]
    assert construir_definiciones(inv, C)[0]["CI"].variantes == []
