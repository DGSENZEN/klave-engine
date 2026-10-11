"""R81: la sección de una etiqueta de cuadro o de detalle sale de SU sección dibujada, no de la cota
más cercana. El contorno cerrado más cercano del lado que la hoja acostumbra (en Marina, encima de
la etiqueta y de su pila), que cubre el centro de la etiqueta y que ninguna otra etiqueta alcanza;
sus cotas son las que tienen sus dos puntos de definición sobre sus aristas."""

import ezdxf
import pytest
from klave_engine.detection.schedules import (
    ElementSpec,
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
    # K-15A en Marina: 60 de ancho, 30 + 25 de alto, la parte de arriba de 20. No se toma un
    # rectángulo: un aviso con su caja y su área, un rechazo, y la sección reclamada.
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
    (aviso,) = k.avisos
    assert aviso.startswith("sección no rectangular (6 vértices): caja 3.000 × 2.750 m")
    assert "área 5.7500 m²" in aviso and "cotas en sus aristas: 25, 30, 60" in aviso
    assert [(r.motivo, r.marcas) for r in inv.rechazos] == [("sin_lector", ["K-15A"])]
    merge_external_specs(inv, [_ia("K-15A", section_cm=(60, 55))], C)
    d = construir_definiciones(inv, C)[0]["K-15A"].seccion_cm
    assert d.ilegible and [a.fuente for a in d.alternativas] == ["ia"]


def test_one_cota_on_a_square_section_is_an_assumed_square():
    # Una sola cota (15) en una sección dibujada cuadrada: se supone cuadrada, y eso es «supuesto»,
    # nunca «detalle». En una que no es cuadrada no se supone nada (y sin cota vertical cerca no se
    # reclama: como el lector viejo, que ahí no leía).
    ents = [
        *_castillo("a", "K-1", 0.0, 0.0, ["4#3", "E#2@15"], (-0.375, 0.9, 0.375, 1.65), 15, None),
        *_castillo("b", "K-3", 5.0, 0.0, ["6#3", "E#2@15"], (4.625, 0.9, 5.375, 2.4), 15, None),
    ]  # fmt: skip
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0)
    (k1,) = _cotas(inv, "K-1")
    assert (k1.section_cm, k1.seccion_supuesta) == ((15, 15), True)
    assert "una sola cota (15 cm)" in k1.avisos[0]
    assert _cotas(inv, "K-3") == []
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
    # se ve, y la definición elige las cotas.
    ents = _castillo("a", "K-8", 0.0, 0.0, ["8#4", "2E#3@20"], (-0.3945, 0.9, 0.3946, 3.5017),
                     15, 60)  # fmt: skip
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0)
    (k8,) = _cotas(inv, "K-8")
    (dibujada,) = _cotas(inv, "K-8", "geometria")
    assert k8.section_cm == (15, 60) and dibujada.section_cm == (18, 59)
    assert "no coincide con sus cotas 15x60" in dibujada.avisos[0]
    assert inv.by_mark["K-8"].section_cm == (15, 60)
    d = construir_definiciones(inv, C)[0]["K-8"].seccion_cm
    assert (d.valor, d.fuente, d.en_conflicto) == ((15, 60), "detalle", False)
    assert [(a.valor, a.fuente) for a in d.alternativas] == [((18, 59), "seccion_dibujada")]


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
