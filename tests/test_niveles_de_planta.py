"""Tarea 15e (R270): cada planta toma el nivel que su plano declara (N.P.T.).

PRUEBA-1 (una hoja, cuatro plantas, sin marcos) escribe bajo el título de cada planta su N.P.T.
(«N.P.T. 0+00», «+3.45», «+6.60», «+7.80») y ninguna planta lo tomaba: todas medían sus castillos
con los 3.00 m supuestos. La leyenda es de la planta a cuyo título está pegada, nunca por el orden.

Qué nivel es: PRUEBA-1 dibuja en PLANTA BAJA y PLANTA ALTA la losa (viguetas, trabes) con los
castillos debajo, y en la AZOTEA castillos y muros sin losa (el pretil). Ahí el nivel de una planta
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
    assert alturas["AZOTEA"].pretil and not alturas["AZOTEA"].repetida
    assert not alturas["PLANTA ALTA"].pretil
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
    assert not any(a.pretil for a in alturas.values())
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
    # PB bajo su losa de +3.45 (3.45 m), PA de +3.45 a +6.60 (3.15 m), el pretil de la azotea de
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
    assert "pretil" in dato.texto and "+6.60" in dato.texto and "+7.80" in dato.texto
    cim = _altura("castillo", alturas["v0"], 3.0)
    assert cim is not None and (cim.valor, cim.fuente) == (3.45, "nota")
    assert "arranque" in cim.texto
