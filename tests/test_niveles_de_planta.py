"""Tarea 15e (R270): cada planta toma el nivel que su plano declara (N.P.T.).

PRUEBA-1 (una hoja, cuatro plantas, sin marcos) escribe bajo el título de cada planta su N.P.T.
(«N.P.T. 0+00», «+3.45», «+6.60», «+7.80») y ninguna planta lo tomaba: todas medían sus castillos
con los 3.00 m supuestos. La leyenda es de la planta a cuyo título está pegada, nunca por el orden.

Qué nivel es: PRUEBA-1 dibuja en PLANTA BAJA y PLANTA ALTA la losa (viguetas, trabes) con los
castillos debajo, y en la AZOTEA castillos y muros sin losa en su planta. Ahí el nivel de una planta
es la losa que dibuja: sus castillos van del nivel de la planta de abajo hasta el suyo (lectura B,
«cada juego está bajo su losa»). Sólo cuando el dibujo lo muestra; si no, no se escoge (Marina:
la duda de la verificación 8 queda como está).
"""

import ezdxf
import pytest
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.views import (
    SheetSegmentation,
    ViewKind,
    ViewRegion,
    nivel_de_leyenda,
    segment_views,
)
from klave_engine.dxf.parser import DxfParser

PLANTAS = [
    ("PLANTA DE CIMENTACIÓN", 0.0, "N.P.T.\t0+00"),
    ("PLANTA BAJA", 40.0, "N.P.T.\t+3.45"),
    ("PLANTA ALTA", 80.0, "N.P.T.\t+6.60"),
    ("AZOTEA", 120.0, "N.P.T.\t+7.80"),
]


def _entities(tmp_path, leyendas, extra=None):
    """Una hoja como PRUEBA-1: cuatro títulos de 1.0 y, debajo de cada uno, su leyenda de nivel
    (``leyendas``: título → textos); más una leyenda esquemática de niveles lejos de todo título."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for i in range(12):
        msp.add_text("nota chica", height=0.2).set_placement((i - 40, -40))
    for titulo, x, _leyenda in PLANTAS:
        msp.add_text(titulo, height=1.0).set_placement((x, 0))
        for j, texto in enumerate(leyendas.get(titulo, [])):
            punto = (x - 1.0, -0.6 - 1.2 * j)
            msp.add_mtext(texto, dxfattribs={"char_height": 1.0, "insert": punto})
    # La leyenda esquemática (A-FLOR-LEVL de PRUEBA-1): niveles sueltos, de ninguna planta.
    for j, n in enumerate(("+0.00", "+3.45", "+9.99")):
        msp.add_mtext(f"N.P.T.\t{n}", dxfattribs={"char_height": 0.2, "insert": (60, -30 + j)})
    if extra:
        extra(msp)
    path = tmp_path / "niveles.dxf"
    doc.saveas(path)
    return DxfParser().parse_file(path).entities


def _det(det_id, tipo, x, y, label="K-1"):
    caja = (x - 0.1, y - 0.1, x + 0.1, y + 0.1)
    return make_detection(det_id, tipo, label, caja, 0.9, [], "m", [])


def _dibujo(losa_en=("PLANTA BAJA", "PLANTA ALTA"), muros_en=("AZOTEA",)):
    """Castillos en las cuatro plantas; losas (``slab_region``) y muros donde se pidan."""
    dets = []
    for titulo, x, _l in PLANTAS:
        clave = titulo.split()[-1][:4].lower()
        dets.append(_det(f"k_{clave}", DetectionType.column_tag, x + 3, 6))
        if titulo in losa_en:
            dets.append(_det(f"losa_{clave}", DetectionType.slab_region, x + 4, 7, "LOSA"))
        if titulo in muros_en:
            dets.append(_det(f"muro_{clave}", DetectionType.wall, x + 5, 6, "W"))
    return dets


def _todas():
    return {t: [leyenda] for t, _x, leyenda in PLANTAS}


def _por_titulo(seg):
    return {v.title: v for v in seg.plan_views()}


def _alturas(seg):
    titulos = {v.view_id: v.title for v in seg.views}
    return {titulos[k]: a for k, a in seg.alturas_de_entrepiso().items()}


@pytest.mark.parametrize(
    ("texto", "nivel"),
    [
        ("N.P.T.\t+3.45", 3.45),
        ("N.P.T. 0+00", 0.0),
        ("N.P.T. ±0.00", 0.0),
        ("N.P.T. %%p0.00", 0.0),
        ("N.P.T. 0.00", 0.0),
        ("NPT -1.20", -1.2),
        ("NIVEL +7,80", 7.8),
        ("PLANTA ALTA", None),
        ("N.P.T.", None),
    ],
)
def test_a_caption_reads_its_level(texto, nivel):
    assert nivel_de_leyenda(texto) == nivel


def test_each_planta_takes_the_caption_under_its_own_title(tmp_path):
    seg = segment_views(_entities(tmp_path, _todas()), _dibujo(), [])
    vistas = _por_titulo(seg)
    assert {t: v.npt_level for t, v in vistas.items()} == {
        "PLANTA DE CIMENTACIÓN": 0.0,
        "PLANTA BAJA": 3.45,
        "PLANTA ALTA": 6.6,
        "AZOTEA": 7.8,
    }
    # La leyenda esquemática, lejos de todo título, no es de ninguna planta.
    assert all(9.99 not in [n for n, _c in v.niveles_leidos] for v in vistas.values())
    assert "«N.P.T. +3.45»" in vistas["PLANTA BAJA"].leyenda_de_nivel


def test_reading_b_when_the_plantas_draw_their_slab_and_the_top_does_not(tmp_path):
    seg = segment_views(_entities(tmp_path, _todas()), _dibujo(), [])
    assert "el nivel es la losa que dibuja la planta" in seg.lectura_de_niveles
    assert "PLANTA BAJA" in seg.lectura_de_niveles and "AZOTEA" in seg.lectura_de_niveles
    alturas = _alturas(seg)
    assert {t: a.altura_m for t, a in alturas.items()} == {
        "PLANTA DE CIMENTACIÓN": 3.45,  # el arranque de los castillos de PLANTA BAJA
        "PLANTA BAJA": 3.45,
        "PLANTA ALTA": 3.15,
        "AZOTEA": 1.2,
    }
    assert alturas["AZOTEA"].sin_losa and not alturas["AZOTEA"].repetida
    assert not alturas["PLANTA ALTA"].sin_losa
    assert (alturas["PLANTA ALTA"].nivel_m, alturas["PLANTA ALTA"].nivel_arriba_m) == (3.45, 6.6)
    assert "+3.45" in alturas["PLANTA ALTA"].texto and "+6.60" in alturas["PLANTA ALTA"].texto
    assert seg.dudas_de_nivel() == []


def test_no_reading_b_when_the_top_planta_draws_a_slab(tmp_path):
    # Con losa en la planta más alta nada dice que su nivel sea el de su losa: no se escoge, y el
    # entrepiso de 1.20 m que resulta (de +6.60 a +7.80) es una duda, no una altura.
    dets = _dibujo(losa_en=("PLANTA BAJA", "PLANTA ALTA", "AZOTEA"))
    seg = segment_views(_entities(tmp_path, _todas()), dets, [])
    assert seg.lectura_de_niveles == ""
    alturas = _alturas(seg)
    assert "PLANTA ALTA" not in alturas
    assert alturas["PLANTA BAJA"].altura_m == 3.15
    assert not any(a.sin_losa for a in alturas.values())
    dudas = seg.dudas_de_nivel()
    assert len(dudas) == 1 and "PLANTA ALTA" in dudas[0] and "1.2 m" in dudas[0]


def test_no_reading_b_when_a_planta_with_castillos_draws_no_slab(tmp_path):
    seg = segment_views(_entities(tmp_path, _todas()), _dibujo(losa_en=("PLANTA BAJA",)), [])
    assert seg.lectura_de_niveles == ""


def test_a_planta_without_caption_has_no_level_and_no_height(tmp_path):
    leyendas = _todas()
    del leyendas["PLANTA ALTA"]
    seg = segment_views(_entities(tmp_path, leyendas), _dibujo(), [])
    vistas = _por_titulo(seg)
    assert vistas["PLANTA ALTA"].npt_level is None and vistas["PLANTA ALTA"].niveles_leidos == []
    alturas = _alturas(seg)
    # Su altura no se inventa (supuesto, verificación 7) y nadie mide a través de ella: la
    # AZOTEA no va de +3.45 a +7.80.
    assert "PLANTA ALTA" not in alturas and "AZOTEA" not in alturas
    assert alturas["PLANTA BAJA"].altura_m == 3.45


def test_two_disagreeing_captions_for_one_planta_are_a_doubt(tmp_path):
    leyendas = _todas()
    leyendas["PLANTA ALTA"] = ["N.P.T.\t+6.60", "N.P.T.\t+6.90"]
    seg = segment_views(_entities(tmp_path, leyendas), _dibujo(), [])
    pa = _por_titulo(seg)["PLANTA ALTA"]
    # Ni la mayor ni la primera: ninguna, y la duda dice las dos.
    assert pa.npt_level is None
    assert sorted(n for n, _c in pa.niveles_leidos) == [6.6, 6.9]
    dudas = seg.dudas_de_nivel()
    assert any("PLANTA ALTA" in d and "+6.60" in d and "+6.90" in d for d in dudas)
    assert "PLANTA ALTA" not in _alturas(seg)


def test_two_agreeing_captions_are_one_level(tmp_path):
    leyendas = _todas()
    leyendas["PLANTA ALTA"] = ["N.P.T.\t+6.60", "NIVEL +6.60"]
    seg = segment_views(_entities(tmp_path, leyendas), _dibujo(), [])
    pa = _por_titulo(seg)["PLANTA ALTA"]
    assert pa.npt_level == 6.6 and pa.niveles_leidos == [(6.6, 2)]


def test_frames_levels_keep_reading_a_when_both_readings_hold():
    # La forma de Marina: cada marco declara su nivel y todas dibujan su losa (también la
    # azotea): no se escoge; las alturas de siempre, la más alta repite la de abajo.
    vistas = [
        ViewRegion(view_id=f"f{i}", title=t, kind=ViewKind.plan, level_key=k, npt_level=n,
                   anchor=(0, 0))
        for i, (t, k, n) in enumerate([
            ("ES-000", "cimentacion", 1.45), ("ES-100", "planta_baja", 4.35),
            ("ES-200", "planta_alta", 7.95), ("ES-400", "azotea", 11.15),
        ])
    ]  # fmt: skip
    seg = SheetSegmentation(views=vistas, assignment={}, is_segmented=True)
    assert seg.story_heights() == {"f0": 2.9, "f1": 3.6, "f2": 3.2, "f3": 3.2}
    assert seg.alturas_de_entrepiso()["f3"].repetida
    assert seg.dudas_de_nivel() == []


def _seg_b(lectura="el nivel es la losa que dibuja la planta: prueba"):
    vistas = [
        ViewRegion(view_id=f"v{i}", title=t, kind=ViewKind.plan, level_key=k, npt_level=n,
                   anchor=(0, 0), detection_ids=[f"x{i}"])
        for i, (t, k, n) in enumerate([
            ("PLANTA DE CIMENTACIÓN", "cimentacion", 0.0), ("PLANTA BAJA", "planta_baja", 3.45),
            ("PLANTA ALTA", "planta_alta", 6.6), ("AZOTEA", "azotea", 7.8),
        ])
    ]  # fmt: skip
    return vistas, lectura


def test_the_budget_measures_castillos_and_walls_from_the_declared_levels():
    from klave_engine.costing.apu import build_all_apus
    from klave_engine.costing.boq import generate_bill_of_quantities
    from klave_engine.costing.catalog import build_default_catalog
    from klave_engine.costing.models import CostingAssumptions
    from klave_engine.detection.taxonomy import classify_family
    from klave_engine.dxf.units import DrawingUnits

    from tests.precios import LIBRO

    def muro(det_id, largo):
        d = make_detection(
            det_id, DetectionType.wall, det_id, (0, 0, largo, 0.15), 0.9, [], "m", [],
            {"estimated_length": largo, "estimated_thickness": 0.15, "wall_kind": "block"},
        )  # fmt: skip
        d.family = classify_family(d).value
        return d

    def castillo(det_id):
        d = make_detection(
            det_id, DetectionType.column_tag, "K-1", (0, 0, 1, 1), 0.9, [], "m", [],
            {"section_cm": "15x15"},
        )  # fmt: skip
        d.family = classify_family(d).value
        return d

    vistas, lectura = _seg_b()
    seg = SheetSegmentation(
        views=vistas, is_segmented=True, lectura_de_niveles=lectura,
        assignment={"w1": "v1", "w2": "v2", "w3": "v3", "c0": "v0", "c1": "v1", "c2": "v2",
                    "c3": "v3"},
    )  # fmt: skip
    a = CostingAssumptions(opening_share_pct=0)
    dets = [muro("w1", 10.0), muro("w2", 20.0), muro("w3", 5.0)]
    dets += [castillo(c) for c in ("c0", "c1", "c2", "c3")]
    catalog = [c for c in build_default_catalog(a) if c.code in {"EST-004", "EST-001", "ACA-001"}]
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    boq = generate_bill_of_quantities(
        "t", dets, units, catalog, build_all_apus(catalog, LIBRO), segmentation=seg, assumptions=a
    )
    lines = {line.concept_code: line for line in boq.lines}
    # PB bajo su losa de +3.45 (3.45 m), PA de +3.45 a +6.60 (3.15 m), los muros de la azotea de
    # +6.60 a +7.80 declarado (1.20 m, no los 0.90 supuestos).
    assert abs(lines["EST-004"].quantity - (10.0 * 3.45 + 20.0 * 3.15 + 5.0 * 1.2)) < 1e-6
    assert any("1.20 m" in n and "declarado" in n for n in lines["EST-004"].assumptions)
    assert abs(lines["ACA-001"].quantity - 2 * (10.0 * 3.45 + 20.0 * 3.15 + 5.0 * 1.2)) < 1e-6
    # Castillos: los de la cimentación son el arranque de los de PLANTA BAJA (no se cuentan dos
    # veces); PB 3.45, PA 3.15, el de la azotea 1.20.
    assert abs(lines["EST-001"].quantity - 0.0225 * (3.45 + 3.15 + 1.2)) < 1e-6
    assert any("losa que dibuja" in n for n in lines["EST-001"].assumptions)


def test_the_castillo_heights_are_notes_that_say_where_they_come_from():
    from klave_engine.estructura.elementos import _altura

    vistas, lectura = _seg_b()
    seg = SheetSegmentation(views=vistas, assignment={}, is_segmented=True,
                            lectura_de_niveles=lectura)  # fmt: skip
    alturas = seg.alturas_de_entrepiso()
    dato = _altura("castillo", alturas["v3"], 3.0)
    assert dato is not None and (dato.valor, dato.fuente) == (1.2, "nota")
    assert "sin losa" in dato.texto and "+6.60" in dato.texto and "+7.80" in dato.texto
    assert "pretil" not in dato.texto  # R273: el dibujo no dice que todo sea pretil
    cim = _altura("castillo", alturas["v0"], 3.0)
    assert cim is not None and (cim.valor, cim.fuente) == (3.45, "nota")
    assert "arranque" in cim.texto


# ------------------------------------------------------- R271: el muro llega bajo su losa


def _detalle_de_losa(msp, cotas=(("15", 0.0, 0.78), ("5", 0.78, 1.04), ("20", 0.0, 1.04))):
    """El detalle de PRUEBA-1 (65B8): «LOSA DE VIGUETA Y BOVEDILLA 12-5» y, junto, la cadena de
    cotas verticales de su peralte, dibujada sin escala (15 + 5 = 20)."""
    x, y = 200.0, 0.0
    msp.add_mtext("LOSA DE VIGUETA Y BOVEDILLA 12-5",
                  dxfattribs={"char_height": 0.2, "insert": (x, y)})  # fmt: skip
    for i, (texto, y0, y1) in enumerate(cotas):
        cota = msp.add_linear_dim(
            base=(x + 4.0 + 0.3 * i, y + 1.0), p1=(x + 4.0, y + 1.0 + y0),
            p2=(x + 4.0, y + 1.0 + y1), angle=90, text=texto,
        )  # fmt: skip
        cota.render()
    # Una cota horizontal (la separación de las viguetas, «63») no es el peralte.
    horizontal = msp.add_linear_dim(base=(x, y + 2.5), p1=(x, y + 2.2), p2=(x + 3.3, y + 2.2),
                                    text="63")  # fmt: skip
    horizontal.render()


def test_the_slab_depth_a_detail_dimensions_is_read(tmp_path):
    seg = segment_views(_entities(tmp_path, _todas(), extra=_detalle_de_losa), _dibujo(), [])
    losa = seg.losa_acotada()
    assert losa is not None and losa.espesor_m == pytest.approx(0.20)
    assert "LOSA DE VIGUETA Y BOVEDILLA 12-5" in losa.texto and "20" in losa.texto


def test_no_slab_depth_without_a_vertical_chain_that_adds_up(tmp_path):
    def sin_cadena(msp):
        _detalle_de_losa(msp, cotas=(("15", 0.0, 0.78), ("5", 0.78, 1.04), ("25", 0.0, 1.04)))

    def una_sola(msp):
        # Una cota vertical sola junto al título puede ser cualquier cosa del detalle (Marina:
        # «LOSA PLANA H=45» junto a una cota de 10): no es el peralte.
        _detalle_de_losa(msp, cotas=(("20", 0.0, 1.04),))

    for extra in (sin_cadena, una_sola, None):
        seg = segment_views(_entities(tmp_path, _todas(), extra=extra), _dibujo(), [])
        assert seg.losa_acotada() is None


def test_slab_details_that_dimension_different_depths_give_none():
    from klave_engine.detection.views import LosaAcotada

    seg = SheetSegmentation(views=[], assignment={}, is_segmented=True, losas_acotadas=[
        LosaAcotada(espesor_m=0.20, texto="a"), LosaAcotada(espesor_m=0.25, texto="b"),
    ])  # fmt: skip
    assert seg.losa_acotada() is None
    iguales = seg.model_copy(update={"losas_acotadas": [LosaAcotada(espesor_m=0.2, texto="a")] * 2})
    assert iguales.losa_acotada() is not None


def _boq_de_muros(losas, leidas=True):
    from klave_engine.costing.apu import build_all_apus
    from klave_engine.costing.boq import generate_bill_of_quantities
    from klave_engine.costing.catalog import build_default_catalog
    from klave_engine.costing.models import CostingAssumptions
    from klave_engine.detection.taxonomy import classify_family
    from klave_engine.dxf.units import DrawingUnits

    from tests.precios import LIBRO

    def muro(det_id, largo):
        d = make_detection(
            det_id, DetectionType.wall, det_id, (0, 0, largo, 0.15), 0.9, [], "m", [],
            {"estimated_length": largo, "estimated_thickness": 0.15, "wall_kind": "block"},
        )  # fmt: skip
        d.family = classify_family(d).value
        return d

    vistas, lectura = _seg_b()
    seg = SheetSegmentation(
        views=vistas, is_segmented=True, lectura_de_niveles=lectura, losas_acotadas=losas,
        losas_leidas=leidas, assignment={"w1": "v1", "w2": "v2", "w3": "v3"},
    )  # fmt: skip
    a = CostingAssumptions(opening_share_pct=0)
    catalog = [c for c in build_default_catalog(a) if c.code in {"EST-004", "ACA-001"}]
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    dets = [muro("w1", 10.0), muro("w2", 20.0), muro("w3", 5.0)]
    boq = generate_bill_of_quantities(
        "t", dets, units, catalog, build_all_apus(catalog, LIBRO), segmentation=seg, assumptions=a
    )
    return {line.concept_code: line for line in boq.lines}


def test_a_block_wall_stops_under_the_slab_the_drawing_dimensions():
    from klave_engine.detection.views import LosaAcotada

    losa = LosaAcotada(espesor_m=0.20, texto="«LOSA DE VIGUETA Y BOVEDILLA 12-5»: 20 = 15 + 5")
    lines = _boq_de_muros([losa])
    # PB 3.45 − 0.20, PA 3.15 − 0.20; los muros de la azotea, sin losa encima, 1.20 enteros.
    esperado = 10.0 * 3.25 + 20.0 * 2.95 + 5.0 * 1.2
    assert lines["EST-004"].quantity == pytest.approx(esperado)
    assert lines["ACA-001"].quantity == pytest.approx(2 * esperado)
    notas = " ".join(lines["EST-004"].assumptions)
    assert "3.25" in notas and "2.95" in notas and "20" in notas
    assert "dala de remate" in notas  # no se descuenta (E2), y se dice
    # M5 (R286): ningún código de ronda en una nota que ve el cliente.
    assert "(E2)" not in notas and "ronda posterior" in notas


def test_without_a_dimensioned_slab_the_wall_keeps_the_storey_height_as_an_assumption():
    lines = _boq_de_muros([])
    assert lines["EST-004"].quantity == pytest.approx(10.0 * 3.45 + 20.0 * 3.15 + 5.0 * 1.2)
    assert any("supuest" in n and "losa" in n for n in lines["EST-004"].assumptions)
    # R286 (I2): dice lo que hizo el motor, nunca que el plano no acota la losa.
    notas = " ".join(lines["EST-004"].assumptions)
    assert "no se leyó un peralte de losa acotado en un detalle" in notas
    assert "el plano no acota" not in notas


def test_wall_line_notes_say_what_the_line_does():
    # R286: ACA no dice «vanos no descontados» junto a su deducción, y la altura promedio de
    # ALB-001 es sólo la de cuando no hay niveles N.P.T. (con niveles, la nota se va).
    from klave_engine.costing.catalog import build_default_catalog
    from klave_engine.costing.models import CostingAssumptions

    conceptos = {c.code: c for c in build_default_catalog(CostingAssumptions())}
    for codigo in ("ACA-001", "ACA-002"):
        notas = " ".join(conceptos[codigo].assumptions)
        assert "vanos no descontados" not in notas and "nota de vanos" in notas
    alb = conceptos["ALB-001"].assumptions
    assert any("Altura promedio de muro" in n and "(si no hay niveles N.P.T.)" in n for n in alb)
    assert not any("(A4)" in n for n in alb)
    lines = _boq_de_muros([])
    assert not any("vanos no descontados" in n for n in lines["ACA-001"].assumptions)


def test_an_old_run_without_slab_reading_does_not_claim_the_drawing_lacks_it():
    # R286 (I2): un views.json de antes de leer las losas no trae el campo; al recalcular, la nota
    # no dice que el plano no las acota: dice que esa lectura no las buscó.
    vieja = SheetSegmentation.model_validate({"views": [], "assignment": {}, "is_segmented": True})
    assert vieja.losas_leidas is False
    notas = " ".join(_boq_de_muros([], leidas=False)["EST-004"].assumptions)
    assert "no buscó el peralte de la losa" in notas and "reprocesa" in notas
    assert "el plano no acota" not in notas and "no se leyó un peralte" not in notas


def test_segmenting_says_it_looked_for_the_slab_depth(tmp_path):
    seg = segment_views(_entities(tmp_path, _todas()), _dibujo(), [])
    assert seg.losas_leidas is True


# ------------------------------------- R272: el arranque de un castillo que sigue arriba


def _ejes(prefijo, x0, y0):
    """Tres ejes verticales y tres horizontales de una planta, desde (x0, y0)."""
    salida = []
    for i, d in enumerate((1.0, 5.0, 9.0)):
        for eje, caja, coord in (
            ("vertical", (x0 + d, y0, x0 + d, y0 + 10), x0 + d),
            ("horizontal", (x0, y0 + d, x0 + 10, y0 + d), y0 + d),
        ):
            salida.append(make_detection(
                f"{prefijo}_{eje[0]}{i}", DetectionType.grid_line, f"{prefijo}{i}", caja, 0.9,
                [], "m", [], {"axis": eje, "coordinate": coord},
            ))  # fmt: skip
    return salida


def _castillo(det_id, x, y):
    d = _det(det_id, DetectionType.column_tag, x, y)
    d.family = "castillo"
    return d


def test_a_cimentacion_castillo_with_no_castillo_above_has_no_noted_height(tmp_path):
    # La rejilla de PLANTA BAJA está corrida (40.5, 0.3) de la de la cimentación. El castillo de
    # (3, 8) sigue en PLANTA BAJA (43.5, 8.3); el de (6, 8) no tiene nada encima (PRUEBA-1: 5DAA,
    # donde PLANTA BAJA dibuja un cerramiento).
    dets = [
        *_ejes("c", 0.0, 5.0), *_ejes("b", 40.5, 5.3),
        _castillo("k_sigue", 3.0, 8.0), _castillo("k_solo", 6.0, 8.0),
        _castillo("k_pb", 43.5, 8.3), _castillo("k_pa", 83.0, 8.0), _castillo("k_az", 123.0, 8.0),
        _det("losa_pb", DetectionType.slab_region, 44.0, 9.0, "LOSA"),
        _det("losa_pa", DetectionType.slab_region, 84.0, 9.0, "LOSA"),
        _det("muro_az", DetectionType.wall, 125.0, 8.0, "W"),
    ]  # fmt: skip
    seg = segment_views(_entities(tmp_path, _todas()), dets, [])
    assert seg.lectura_de_niveles
    assert seg.continuaciones["k_sigue"][0] == "k_pb"
    assert "k_solo" in seg.sin_continuacion and "k_sigue" not in seg.sin_continuacion
    assert "PLANTA BAJA" in seg.sin_continuacion["k_solo"]

    from klave_engine.estructura.elementos import construir_elementos
    from klave_engine.estructura.reglas import reglas_estandar

    els = {
        e.detection_id: e
        for e in construir_elementos(dets, seg, {}, {}, reglas_estandar(), 1.0, 3.0, frames=[])
    }
    sigue, solo = els["k_sigue"].colocacion.altura_m, els["k_solo"].colocacion.altura_m
    assert sigue is not None and (sigue.valor, sigue.fuente) == (3.45, "nota")
    assert solo is not None and (solo.valor, solo.fuente) == (3.0, "supuesto")
    assert "no es el arranque" in solo.texto and "PLANTA BAJA" in solo.texto


# ------------------------------------- R286 (M2): un dibujo en cm se lee como uno en m


def test_a_slab_detail_drawn_in_centimetres_is_read_like_one_in_metres(tmp_path):
    # La cadena 15 + 5 = 20 a 4 m de su título: en un dibujo en cm, 400 unidades. Comparar esas
    # unidades con 6 m (sin el factor) no leería nada.
    from klave_engine.detection.views import _losas_acotadas

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    x, y = 20000.0, 0.0
    msp.add_mtext("LOSA DE VIGUETA Y BOVEDILLA 12-5",
                  dxfattribs={"char_height": 20.0, "insert": (x, y)})  # fmt: skip
    for i, (texto, y0, y1) in enumerate((("15", 0.0, 78.0), ("5", 78.0, 104.0),
                                         ("20", 0.0, 104.0))):  # fmt: skip
        cota = msp.add_linear_dim(
            base=(x + 400.0 + 30.0 * i, y + 100.0), p1=(x + 400.0, y + 100.0 + y0),
            p2=(x + 400.0, y + 100.0 + y1), angle=90, text=texto,
        )  # fmt: skip
        cota.render()
    path = tmp_path / "losa_cm.dxf"
    doc.saveas(path)
    entidades = DxfParser().parse_file(path).entities
    assert _losas_acotadas(entidades, 0.01)[0].espesor_m == pytest.approx(0.20)
    assert _losas_acotadas(entidades, 1.0) == []  # leídas como metros, 4 m serían 400 m


def test_a_castillo_continuation_drawn_in_centimetres_is_read_like_one_in_metres():
    # La planta baja está corrida (40.5, 0.3) m de la cimentación; un castillo sigue a 0.0 m y
    # otro no tiene nada encima. Todo en cm: 100 unidades por metro.
    from klave_engine.detection.views import _continuaciones

    def ejes(prefijo, x0, y0, k):
        salida = []
        for i, d in enumerate((1.0, 5.0, 9.0)):
            for eje, coord in (("vertical", (x0 + d) * k), ("horizontal", (y0 + d) * k)):
                salida.append(make_detection(
                    f"{prefijo}_{eje[0]}{i}", DetectionType.grid_line, f"{prefijo}{i}",
                    (coord, coord, coord, coord), 0.9, [], "m", [],
                    {"axis": eje, "coordinate": coord},
                ))  # fmt: skip
        return salida

    def castillo(det_id, x, y, k):
        d = make_detection(det_id, DetectionType.column_tag, "K-1",
                           ((x - 0.1) * k, (y - 0.1) * k, (x + 0.1) * k, (y + 0.1) * k),
                           0.9, [], "m", [])  # fmt: skip
        d.family = "castillo"
        return d

    vistas = [
        ViewRegion(view_id="c", title="PLANTA DE CIMENTACIÓN", kind=ViewKind.plan,
                   level_key="cimentacion", npt_level=0.0, anchor=(0, 0)),
        ViewRegion(view_id="b", title="PLANTA BAJA", kind=ViewKind.plan,
                   level_key="planta_baja", npt_level=3.45, anchor=(0, 0)),
    ]  # fmt: skip
    for k, factor in ((1.0, 1.0), (100.0, 0.01)):
        dets = [
            *ejes("c", 0.0, 5.0, k), *ejes("b", 40.5, 5.3, k),
            castillo("k_sigue", 3.0, 8.0, k), castillo("k_solo", 6.0, 8.0, k),
            castillo("k_pb", 43.5, 8.3, k),
        ]  # fmt: skip
        asignacion = {d.detection_id: d.detection_id.split("_")[0] for d in dets}
        asignacion |= {"k_sigue": "c", "k_solo": "c", "k_pb": "b"}
        siguen, sin = _continuaciones(vistas, asignacion, dets, [], factor)
        assert siguen == {"k_sigue": ("k_pb", 0.0)}, k
        assert set(sin) == {"k_solo"}, k
        assert "(+40.50, +0.30 m)" in sin["k_solo"] and "3.00 m" in sin["k_solo"], k
