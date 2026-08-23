"""Heights from the plantas' own levels (NTC/NPT) instead of project-wide
assumptions; slab rebar from the tablero's own label."""

from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.boq import generate_bill_of_quantities
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.models import CostingAssumptions
from klave_engine.costing.steel import slab_rebar_kg_per_m2
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.taxonomy import classify_family
from klave_engine.detection.views import SheetSegmentation, ViewKind, ViewRegion
from klave_engine.dxf.units import DrawingUnits


def _seg():
    views = [
        ViewRegion(view_id="f0", title="ES-000 · CIMENTACIÓN", kind=ViewKind.plan,
                   level_key="cimentacion", npt_level=1.45, anchor=(0, 0)),
        ViewRegion(view_id="f1", title="ES-100 · PLANTA BAJA", kind=ViewKind.plan,
                   level_key="planta_baja", npt_level=4.35, anchor=(0, 0)),
        ViewRegion(view_id="f2", title="ES-200 · PLANTA ALTA", kind=ViewKind.plan,
                   level_key="planta_alta", npt_level=7.95, anchor=(0, 0)),
        ViewRegion(view_id="f3", title="ES-400 · AZOTEA", kind=ViewKind.plan,
                   level_key="azotea", npt_level=11.15, anchor=(0, 0)),
    ]
    return views


def test_story_heights_come_from_consecutive_levels():
    seg = SheetSegmentation(views=_seg(), assignment={}, is_segmented=True,
                            npt_levels=[1.45, 4.35, 7.95, 11.15])
    heights = seg.story_heights()
    assert heights == {"f0": 2.9, "f1": 3.6, "f2": 3.2, "f3": 3.2}  # top repeats the one below


def _wall(det_id, length, kind="block"):
    det = make_detection(
        det_id, DetectionType.wall, det_id, (0, 0, length, 0.15), 0.9, [], "m", [],
        {"estimated_length": length, "estimated_thickness": 0.15, "wall_kind": kind},
    )
    det.family = classify_family(det).value
    return det


def _column(det_id, mark="K-1"):
    det = make_detection(
        det_id, DetectionType.column_tag, mark, (0, 0, 1, 1), 0.9, [], "m", [],
        {"section_cm": "15x20"},
    )
    det.family = classify_family(det).value
    return det


def test_walls_and_columns_use_each_plantas_own_height():
    a = CostingAssumptions()
    dets = [
        _wall("w1", 10.0), _wall("w2", 20.0), _wall("w3", 5.0, "concreto"),
        _column("c0", "K-1"), _column("c1", "K-1"), _column("c2", "K-2"),
    ]
    seg = SheetSegmentation(
        views=_seg(), is_segmented=True, npt_levels=[1.45, 4.35, 7.95, 11.15],
        assignment={"w1": "f1", "w2": "f2", "w3": "f1", "c0": "f0", "c1": "f1", "c2": "f2"},
    )
    catalog = [c for c in build_default_catalog(a) if c.code in {"EST-004", "EST-014", "EST-001"}]
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    boq = generate_bill_of_quantities(
        "t", dets, units, catalog, build_all_apus(catalog), segmentation=seg, assumptions=a
    )
    lines = {line.concept_code: line for line in boq.lines}
    assert abs(lines["EST-004"].quantity - (10.0 * 3.6 + 20.0 * 3.2)) < 1e-6
    assert lines["EST-004"].by_view == {"ES-100 · PLANTA BAJA": 36.0, "ES-200 · PLANTA ALTA": 64.0}
    assert any("NTC/NPT" in n for n in lines["EST-004"].assumptions)
    assert abs(lines["EST-014"].quantity - 5.0 * 0.15 * 3.6) < 1e-6
    # Columns: one per planta above the cimentación, each at its own story height.
    assert abs(lines["EST-001"].quantity - (0.03 * 3.6 + 0.03 * 3.2)) < 1e-6  # 15x20 declared


def test_slab_rebar_from_the_label():
    kg, how = slab_rebar_kg_per_m2("LOSA MACIZA DOBLEMENTE ARMADA H=20 LS #4@20 A/S LI #4@20 A/S")
    # #4 = 0.994 kg/m, every 20 cm = 5 bars/m, both ways, two layers.
    assert abs(kg - 0.994 * 5 * 2 * 2) < 1e-6 and "#4@20 a/s" in how
    kg2, how2 = slab_rebar_kg_per_m2("LOSA MACIZA DOBLEMENTE ARMADA #3@15 A/S")
    assert abs(kg2 - 0.560 * (100 / 15) * 2 * 2) < 1e-2 and "×2 lechos" in how2
    assert slab_rebar_kg_per_m2("LOSA MACIZA H=12") is None
