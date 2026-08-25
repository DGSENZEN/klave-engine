"""Tableros de losa: faces bounded by trabes, typed by pattern and label,
voids subtracted; and the costing split per slab system."""

import ezdxf
from klave_engine.common.ids import IdGenerator
from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.boq import generate_bill_of_quantities
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.models import CostingAssumptions
from klave_engine.detection.slab_panels import SlabPanelConfig, detect_slab_panels
from klave_engine.dxf.parser import DxfParser
from klave_engine.dxf.units import DrawingUnits

from tests.precios import LIBRO


def _beam(msp, x0, y0, x1, y1, width=0.3):
    """A trabe drawn as two parallel lines."""
    if abs(y1 - y0) < 1e-9:
        msp.add_line((x0, y0 - width / 2), (x1, y0 - width / 2), dxfattribs={"layer": "EST-TRABES"})
        msp.add_line((x0, y0 + width / 2), (x1, y0 + width / 2), dxfattribs={"layer": "EST-TRABES"})
    else:
        msp.add_line((x0 - width / 2, y0), (x0 - width / 2, y1), dxfattribs={"layer": "EST-TRABES"})
        msp.add_line((x0 + width / 2, y0), (x0 + width / 2, y1), dxfattribs={"layer": "EST-TRABES"})


def _entities(tmp_path, build):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    build(doc.modelspace())
    path = tmp_path / "panels.dxf"
    doc.saveas(path)
    return DxfParser().parse_file(path).entities


def _build(msp):
    # A 2×2 grid of tableros, 6 m × 5 m each, bounded by double-line trabes;
    # ejes cross the whole thing (and must not split tableros).
    for x in (0.0, 6.0, 12.0):
        _beam(msp, x, 0.0, x, 10.0)
    for y in (0.0, 5.0, 10.0):
        _beam(msp, 0.0, y, 12.0, y)
    for x in (3.0, 9.0):
        msp.add_line((x, -5), (x, 15), dxfattribs={"layer": "EJES"})
    # Bottom-left: reticular pattern + label. Bottom-right: maciza hatch +
    # label. Top-left: vigueta lines + label with H. Top-right: an opening.
    nervada = {"layer": "EST-LOSA NERVADA"}
    for i in range(5):
        msp.add_line((0.5 + i, 0.5), (0.5 + i, 4.5), dxfattribs=nervada)
        msp.add_line((0.5, 0.5 + i * 0.9), (5.5, 0.5 + i * 0.9), dxfattribs=nervada)
    msp.add_text("LOSA RETICULAR ALIGERADA H=30", height=0.15).set_placement((1.0, 2.5))
    hatch = msp.add_hatch(dxfattribs={"layer": "EST-LOSA MACIZA"})
    hatch.paths.add_polyline_path(
        [(6.5, 0.5), (11.5, 0.5), (11.5, 4.5), (6.5, 4.5)], is_closed=True
    )
    msp.add_text("LOSA MACIZA H=20", height=0.15).set_placement((8.0, 2.5))
    vigueta = {"layer": "EST-LOSA VIG Y BOV"}
    for i in range(6):
        msp.add_line((0.5, 5.5 + i * 0.7), (5.5, 5.5 + i * 0.7), dxfattribs=vigueta)
    msp.add_text("LOSA DE VIGUETA Y BOVEDILLA H=20", height=0.15).set_placement((1.0, 7.5))
    # Opening: a crossed box of 2×2 inside the top-right tablero, which is
    # otherwise maciza by label (no pattern) — the box is subtracted.
    msp.add_text("LOSA MACIZA H=12", height=0.15).set_placement((7.0, 9.0))
    msp.add_lwpolyline([(8, 6), (10, 6), (10, 8), (8, 8)], close=True, dxfattribs={"layer": "0"})
    msp.add_line((8, 6), (10, 8), dxfattribs={"layer": "0"})
    msp.add_line((8, 8), (10, 6), dxfattribs={"layer": "0"})
    msp.add_text("VACIO", height=0.1).set_placement((8.8, 7.0))


def test_tableros_typed_by_pattern_and_label_with_voids(tmp_path):
    entities = _entities(tmp_path, _build)
    out = detect_slab_panels(entities, SlabPanelConfig(), IdGenerator("p"))
    panels = {d.properties["family"]: d for d in out.detections}
    assert set(panels) == {"reticular", "maciza", "vigueta_bovedilla"}
    assert len(out.detections) == 4
    # Net tablero = 6×5 minus half a beam width on each side (5.7 × 4.7).
    ret = panels["reticular"]
    assert abs(ret.properties["estimated_area"] - 5.7 * 4.7) < 0.05
    assert ret.properties["thickness_cm"] == 30 and ret.confidence >= 0.9
    assert panels["vigueta_bovedilla"].properties["thickness_cm"] == 20
    macizas = [d for d in out.detections if d.properties["family"] == "maciza"]
    by_h = {d.properties["thickness_cm"]: d for d in macizas}
    assert by_h[20].properties["estimated_area"] > 26
    # The opening was subtracted from the H=12 tablero, not dropped with it.
    assert abs(by_h[12].properties["void_area"] - 4.0) < 0.01
    assert abs(by_h[12].properties["estimated_area"] - (5.7 * 4.7 - 4.0)) < 0.05


def test_slab_systems_split_into_their_own_concepts(tmp_path):
    entities = _entities(tmp_path, _build)
    out = detect_slab_panels(entities, SlabPanelConfig(), IdGenerator("p"))
    assumptions = CostingAssumptions()
    catalog = [c for c in build_default_catalog(assumptions) if c.code in
               {"EST-003", "EST-012", "EST-013", "CIM-007"}]
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    boq = generate_bill_of_quantities(
        "t", out.detections, units, catalog, build_all_apus(catalog, LIBRO), assumptions=assumptions
    )
    lines = {line.concept_code: line for line in boq.lines}
    assert abs(lines["EST-003"].quantity - 5.7 * 4.7) < 0.05  # reticular m²
    assert abs(lines["EST-012"].quantity - 5.7 * 4.7) < 0.05  # vigueta m²
    # maciza m³ = Σ area × H: 26.79 × 0.20 + 22.79 × 0.12
    expected = 5.7 * 4.7 * 0.20 + (5.7 * 4.7 - 4.0) * 0.12
    assert abs(lines["EST-013"].quantity - expected) < 0.02
    assert "CIM-007" not in lines  # no losa de cimentación on this sheet
