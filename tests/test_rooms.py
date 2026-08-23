"""Locales from the architectural wall network, and the acabados they feed."""

import ezdxf
from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.boq import generate_bill_of_quantities
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.models import CostingAssumptions
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.rooms import RoomDetectorConfig, detect_rooms
from klave_engine.detection.taxonomy import classify_family
from klave_engine.detection.views import SheetSegmentation, ViewKind, ViewRegion
from klave_engine.dxf.parser import DxfParser
from klave_engine.dxf.units import DrawingUnits


def _double_wall(msp, a, b, t=0.15, layer="A-WALL"):
    """Two parallel lines a wall apart, like an architectural planta."""
    (x0, y0), (x1, y1) = a, b
    if y0 == y1:
        msp.add_line((x0, y0 - t / 2), (x1, y1 - t / 2), dxfattribs={"layer": layer})
        msp.add_line((x0, y0 + t / 2), (x1, y1 + t / 2), dxfattribs={"layer": layer})
    else:
        msp.add_line((x0 - t / 2, y0), (x1 - t / 2, y1), dxfattribs={"layer": layer})
        msp.add_line((x0 + t / 2, y0), (x1 + t / 2, y1), dxfattribs={"layer": layer})


def _plan(tmp_path):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    # A 7×4 m box split into RECÁMARA (4×4) and BAÑO (3×4); a PATIO 3×3 attached east.
    for a, b in [((0, 0), (10, 0)), ((0, 4), (10, 4)), ((0, 0), (0, 4)), ((4, 0), (4, 4)),
                 ((7, 0), (7, 4)), ((10, 0), (10, 4)), ((7, 4), (10, 4))]:
        _double_wall(msp, a, b)
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "S-GRID"})  # an eje: never a wall
    msp.add_text("RECÁMARA", height=0.2).set_placement((1.5, 2))
    msp.add_text("BAÑO", height=0.2).set_placement((5, 2))
    msp.add_text("PATIO", height=0.2).set_placement((8, 2))
    path = tmp_path / "arq.dxf"
    doc.saveas(path)
    return DxfParser().parse_file(path).entities


def test_rooms_are_the_faces_between_walls_named_by_their_text(tmp_path):
    entities = _plan(tmp_path)
    out = detect_rooms(entities, RoomDetectorConfig(min_area=1.5, max_area=400, min_width=0.7))
    rooms = sorted(out.detections, key=lambda d: d.bbox[0])
    assert [d.properties["label"] for d in rooms] == ["RECÁMARA", "BAÑO", "PATIO"]
    assert [d.properties["room_kind"] for d in rooms] == ["interior", "interior", "exterior"]
    # Faces are measured between the walls' inner lines: 3.85 × 3.85 for the recámara.
    assert abs(rooms[0].properties["estimated_area"] - 3.85 * 3.85) < 0.05
    assert abs(rooms[1].properties["estimated_area"] - 2.85 * 3.85) < 0.05
    assert all(d.evidence.method == "room_from_wall_network" for d in rooms)
    assert classify_family(rooms[0]).value == "local"


def _room(det_id, area, kind):
    det = make_detection(
        det_id, DetectionType.room, det_id, (0, 0, 1, 1), 0.85, [], "m", [],
        {"estimated_area": area, "room_kind": kind, "label": kind.upper()},
    )
    det.family = classify_family(det).value
    return det


def _wall(det_id, length):
    det = make_detection(
        det_id, DetectionType.wall, det_id, (0, 0, length, 0.15), 0.9, [], "m", [],
        {"estimated_length": length, "estimated_thickness": 0.15, "wall_kind": "block"},
    )
    det.family = classify_family(det).value
    return det


def test_acabados_follow_rooms_and_both_faces_of_walls():
    a = CostingAssumptions(opening_share_pct=0)  # faces and heights; vanos have their own test
    dets = [
        _room("r1", 16.0, "interior"), _room("r2", 9.0, "exterior"),
        _room("r3", 12.0, "interior"), _room("r4", 5.0, "sin_nombre"),
        _wall("w1", 10.0), _wall("w2", 6.0),
    ]
    views = [
        ViewRegion(view_id="f1", title="A-100 · PLANTA BAJA", kind=ViewKind.plan,
                   level_key="planta_baja", npt_level=0.0, anchor=(0, 0)),
        ViewRegion(view_id="f2", title="A-200 · PLANTA ALTA", kind=ViewKind.plan,
                   level_key="planta_alta", npt_level=2.9, anchor=(0, 0)),
    ]
    seg = SheetSegmentation(
        views=views, is_segmented=True, npt_levels=[0.0, 2.9],
        assignment={"r1": "f1", "r2": "f1", "r3": "f2", "r4": "f2", "w1": "f1", "w2": "f2"},
    )
    codes = {"ACA-001", "ACA-002", "ACA-003", "ACA-004", "PIS-001", "PIS-002", "EST-004"}
    catalog = [c for c in build_default_catalog(a) if c.code in codes]
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    boq = generate_bill_of_quantities(
        "t", dets, units, catalog, build_all_apus(catalog), segmentation=seg, assumptions=a
    )
    lines = {line.concept_code: line for line in boq.lines}
    # Both stories are 2.9 m (the top repeats the one below).
    assert abs(lines["EST-004"].quantity - (10.0 + 6.0) * 2.9) < 1e-6
    assert abs(lines["ACA-001"].quantity - (10.0 + 6.0) * 2.9 * 2) < 1e-6  # two faces
    assert abs(lines["ACA-002"].quantity - lines["ACA-001"].quantity) < 1e-6
    # Plafón, pintura en plafón and piso: named interior locales only — the
    # unnamed face is listed for review and priced by nobody.
    assert abs(lines["ACA-003"].quantity - (16.0 + 12.0)) < 1e-6
    assert abs(lines["PIS-001"].quantity - 28.0) < 1e-6
    assert lines["ACA-003"].by_view == {"A-100 · PLANTA BAJA": 16.0, "A-200 · PLANTA ALTA": 12.0}
    # Firme: the planta baja once, interior and exterior.
    assert abs(lines["PIS-002"].quantity - (16.0 + 9.0)) < 1e-6
    assert all(line.amount > 0 for line in boq.lines)


def test_a_sheet_without_room_names_reads_no_rooms(tmp_path):
    entities = _plan(tmp_path)
    quiet = [e for e in entities if not (e.is_textual and e.text)]
    out = detect_rooms(quiet, RoomDetectorConfig(min_area=1.5, max_area=400, min_width=0.7))
    assert out.detections == [] and any("no nombra" in w for w in out.warnings)


def test_doors_do_not_keep_a_room_from_closing(tmp_path):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    # A 4×4 room whose south wall has a 0.9 m door opening.
    for a, b in [((0, 4), (4, 4)), ((0, 0), (0, 4)), ((4, 0), (4, 4)),
                 ((0, 0), (1.5, 0)), ((2.4, 0), (4, 0))]:
        _double_wall(msp, a, b)
    msp.add_text("COCINA", height=0.2).set_placement((2, 2))
    msp.add_text("PASILLO", height=0.2).set_placement((2, -1))  # a second named local outside
    path = tmp_path / "door.dxf"
    doc.saveas(path)
    entities = DxfParser().parse_file(path).entities
    out = detect_rooms(entities, RoomDetectorConfig(min_area=1.5, max_area=400, min_width=0.7))
    assert len(out.detections) == 1
    assert out.detections[0].properties["label"] == "COCINA"
    assert abs(out.detections[0].properties["estimated_area"] - 3.85 * 3.85) < 0.2
