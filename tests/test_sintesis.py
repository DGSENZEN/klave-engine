"""Variantes del plano: el renglón se separa por lo que el plano especifica
de sus elementos y las variantes suman exactamente el renglón."""

import pytest
from klave_engine.costing.boq import generate_bill_of_quantities
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.models import CostingAssumptions
from klave_engine.costing.sintesis import (
    descripcion_variante,
    firma,
    repartir,
    slug,
    variant_key,
)
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.dxf.units import DrawingUnits

UNITS = DrawingUnits(unit="m", source="declared", confidence=1.0)


def _columna(det_id, seccion, armado=None, x=0.0):
    props = {"section_cm": seccion, "section_area_du2": 0.0, "section_source": "cuadro",
             "has_nearby_grid": True}
    if armado:
        props["spec_rebar"] = armado
    return make_detection(
        det_id, DetectionType.column_tag, "EST-COL", (x, 0, x + 0.4, 0.4), 0.9, [det_id],
        "tag", [], props, "e.dxf",
    )


def _muro(det_id, tipo, espesor, largo):
    return make_detection(
        det_id, DetectionType.wall, "MUROS", (0, 0, largo, espesor), 0.9, [det_id], "pair", [],
        {"estimated_length": largo, "estimated_thickness": espesor, "wall_kind": tipo,
         "segment_count": 1, "openings": [], "opening_length": 0},
        "a.dxf",
    )


def test_firma_reads_what_the_drawing_declares_only():
    assert firma(_columna("c1", "40x30", "8#5"), 1.0) == {"seccion": "30x40", "armado": "8#5"}
    assert firma(_columna("c2", ""), 1.0) == {}
    assert firma(_muro("m1", "block", 0.152, 5.0), 1.0) == {"tipo": "block", "espesor_cm": "15"}
    assert slug({"seccion": "30x40", "armado": "8#5"}) == "30X40-8N5"
    assert slug({}) == "GEN"
    assert variant_key("EST-001", {"seccion": "15x15"}) == "EST-001.15X15"
    assert slug({"diametro": '51 mm (2")'}) == "51MM"
    assert slug({"material": "PEAD", "diametro": '19 mm (3/4")'}) == "PEAD-19MM"


def test_descripcion_goes_into_the_identity_before_incluye():
    base = "Columnas de concreto armado f'c=250 kg/cm², incluye cimbra"
    out = descripcion_variante(base, {"seccion": "30x40", "armado": "8#5"})
    assert out.startswith("Columnas de concreto armado f'c=250 kg/cm²")
    assert "de sección 30×40 cm, armado con 8 vars. #5" in out
    assert out.index("sección") < out.index("incluye")
    assert descripcion_variante(base, {}) == base


def test_repartir_sums_exactly():
    parts = repartir(10.0, [1.0, 1.0, 1.0])
    assert sum(parts) == pytest.approx(10.0, abs=1e-9) and len(parts) == 3
    assert repartir(5.0, [0.0, 0.0]) == [2.5, 2.5]


def test_columns_split_by_section_and_sum_to_the_line():
    catalog = [c for c in build_default_catalog(CostingAssumptions()) if c.code == "EST-001"]
    dets = [
        _columna("c1", "30x40", "8#5", 0), _columna("c2", "30x40", "8#5", 5),
        _columna("c3", "15x15", "4#3", 10),
    ]
    boq = generate_bill_of_quantities("p", dets, UNITS, catalog, {}, "MXN")
    line = next(x for x in boq.lines if x.concept_code == "EST-001")
    keys = {v.key: v for v in line.variants}
    assert set(keys) == {"EST-001.30X40-8N5", "EST-001.15X15-4N3"}
    assert sum(v.quantity for v in line.variants) == pytest.approx(line.quantity, abs=1e-9)
    big, small = keys["EST-001.30X40-8N5"], keys["EST-001.15X15-4N3"]
    # 2 columnas de 0.12 m² contra 1 de 0.0225 m²: la grande pesa mucho más.
    assert big.quantity > small.quantity * 5
    assert big.source_detection_count == 2 and small.source_detections == ["c3"]
    assert "30×40" in big.description


def test_uniform_line_gets_one_variant():
    catalog = [c for c in build_default_catalog(CostingAssumptions()) if c.code == "EST-001"]
    dets = [_columna("c1", "30x40", None, 0), _columna("c2", "30x40", None, 5)]
    boq = generate_bill_of_quantities("p", dets, UNITS, catalog, {}, "MXN")
    line = next(x for x in boq.lines if x.concept_code == "EST-001")
    assert len(line.variants) == 1 and line.variants[0].quantity == line.quantity
    assert line.variants[0].key == "EST-001.30X40"
