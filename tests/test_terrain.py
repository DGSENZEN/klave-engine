"""Terreno natural from contours, and corte/terraplén against a platform
level the engineer sets — never a guessed one."""

import ezdxf
from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.boq import generate_bill_of_quantities
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.earthwork import cut_fill_volumes
from klave_engine.costing.models import CostingAssumptions
from klave_engine.detection.terrain import TerrainDetectorConfig, detect_terrain
from klave_engine.dxf.parser import DxfParser
from klave_engine.dxf.units import DrawingUnits


def _survey(tmp_path, with_lot=True):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    # A slope rising east: contours are vertical lines x = 0, 10, 20, 30, 40 at
    # levels 100.0 … 102.0 (0.5 m each); elevations on the polylines.
    for i, x in enumerate((0, 10, 20, 30, 40)):
        msp.add_lwpolyline(
            [(x, -5), (x, 25)], dxfattribs={"layer": "TOPO-CURVAS", "elevation": 100.0 + 0.5 * i}
        )
    if with_lot:
        msp.add_lwpolyline(
            [(0, 0), (40, 0), (40, 20), (0, 20)], close=True, dxfattribs={"layer": "LOTE"}
        )
    msp.add_text("101.25", height=0.2, dxfattribs={"layer": "TOPO-PUNTOS"}).set_placement((25, 10))
    path = tmp_path / "topo.dxf"
    doc.saveas(path)
    return DxfParser().parse_file(path).entities


def test_terrain_reads_contour_levels_and_the_lot(tmp_path):
    entities = _survey(tmp_path)
    out = detect_terrain(entities, TerrainDetectorConfig())
    assert len(out.detections) == 1
    terrain = out.detections[0]
    props = terrain.properties
    assert props["contour_count"] == 5 and props["spot_count"] == 1
    assert props["level_min"] == 100.0 and props["level_max"] == 102.0
    assert abs(props["estimated_area"] - 800.0) < 1e-6 and "LOTE" in props["lot_source"]
    assert any(p[2] == 101.25 for p in props["sample_points"])


def test_without_contours_there_is_no_terrain(tmp_path):
    entities = [e for e in _survey(tmp_path) if e.layer != "TOPO-CURVAS"]
    out = detect_terrain(entities, TerrainDetectorConfig())
    assert out.detections == [] and out.warnings and "insuficiente" in out.warnings[0]


def test_cut_and_fill_balance_on_a_plane_at_its_mean_level():
    # Ground z = 100 + x/20 over a 40×20 lot: mean 101. Platform at 101 →
    # corte = terraplén = ∫|z−101| = 2 · (20 · ∫₀²⁰ (x/20) dx) = 2 · 20 · 10 = 400 m³… per side 200.
    pts = [[x, y, 100 + x / 20] for x in range(0, 41, 2) for y in (0, 10, 20)]
    lot = [[0, 0], [40, 0], [40, 20], [0, 20]]
    volumes = cut_fill_volumes(pts, lot, platform_level=101.0)
    assert volumes is not None
    assert abs(volumes.cut_m3 - 200.0) < 12 and abs(volumes.fill_m3 - 200.0) < 12
    assert abs(volumes.area_m2 - 800.0) < 5
    lower = cut_fill_volumes(pts, lot, platform_level=100.0)
    assert lower is not None and lower.fill_m3 < 1.0 and abs(lower.cut_m3 - 800.0) < 30


def test_terracerias_lines_need_a_platform_level(tmp_path):
    entities = _survey(tmp_path)
    terrain = detect_terrain(entities, TerrainDetectorConfig()).detections
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    codes = {"TER-001", "TER-002", "TER-003"}
    # Without a platform level: despalme yes, corte/terraplén no — and a warning.
    a = CostingAssumptions()
    catalog = [c for c in build_default_catalog(a) if c.code in codes]
    boq = generate_bill_of_quantities(
        "t", terrain, units, catalog, build_all_apus(catalog), assumptions=a
    )
    lines = {line.concept_code: line for line in boq.lines}
    assert abs(lines["TER-001"].quantity - 800.0) < 1e-6
    assert "TER-002" not in lines and "TER-003" not in lines
    assert any("nivel de plataforma" in w for w in boq.warnings)
    # With it: corte above, terraplén below.
    a = CostingAssumptions(platform_level_m=101.0)
    catalog = [c for c in build_default_catalog(a) if c.code in codes]
    boq = generate_bill_of_quantities(
        "t", terrain, units, catalog, build_all_apus(catalog), assumptions=a
    )
    lines = {line.concept_code: line for line in boq.lines}
    # Sparse contours (two vertices each) interpolate coarsely: both sides of
    # the platform carry volume, of the same order.
    assert lines["TER-002"].quantity > 100 and lines["TER-003"].quantity > 100
    assert 0.6 < lines["TER-002"].quantity / lines["TER-003"].quantity < 1.6
    assert any("IDW" in n for n in lines["TER-002"].assumptions)
    assert all(line.amount > 0 for line in boq.lines)
