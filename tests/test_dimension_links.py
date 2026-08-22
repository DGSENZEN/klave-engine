"""Cotas find their element: footing sizes, column sections, wall thickness."""

import ezdxf
from klave_engine.detection.dimension_links import link_dimensions
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.dxf.parser import DxfParser


def _entities(tmp_path, build):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    build(doc.modelspace())
    path = tmp_path / "cotas.dxf"
    doc.saveas(path)
    return DxfParser().parse_file(path).entities


def _dim(msp, p1, p2, base, angle=0):
    msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=angle).render()


def test_footing_takes_its_drawn_size(tmp_path):
    def build(msp):
        _dim(msp, (10, 10), (11.08, 10), (10, 9.6))  # width 1.08 below the footing
        _dim(msp, (10, 10), (10, 12.08), (9.6, 10), angle=90)  # length 2.08 beside it
        _dim(msp, (30, 30), (33.3, 30), (30, 29.5))  # a cota elsewhere: not ours

    footing = make_detection(
        "f1", DetectionType.footing, "F1", (10, 10, 11.1, 12.1), 0.8, [], "m", [],
        {"estimated_area": 2.31},
    )
    stats = link_dimensions([footing], _entities(tmp_path, build), meters_factor=1.0)
    assert stats.footings == 1
    props = footing.properties
    assert props["dimensioned_width"] == 1.08 and props["dimensioned_length"] == 2.08
    assert props["estimated_area"] == round(1.08 * 2.08, 6)
    assert props["estimated_area_geometry"] == 2.31 and props["area_source"] == "cota"
    assert any("Acotada en el plano" in note for note in footing.evidence.notes)


def test_column_section_from_perpendicular_cotas_unless_cuadro(tmp_path):
    def build(msp):
        _dim(msp, (5, 5), (5.15, 5), (5, 4.7))
        _dim(msp, (5, 5), (5, 5.3), (4.7, 5), angle=90)

    entities = _entities(tmp_path, build)
    column = make_detection(
        "c1", DetectionType.column_tag, "K-1", (5, 5, 5.15, 5.3), 0.8, [], "m", []
    )
    declared = make_detection(
        "c2", DetectionType.column_tag, "K-2", (5, 5, 5.15, 5.3), 0.8, [], "m", [],
        {"section_area_du2": 0.06, "section_source": "cuadro", "section_cm": "20x30"},
    )
    stats = link_dimensions([column, declared], entities, meters_factor=1.0)
    assert stats.columns == 1
    assert column.properties["section_cm"] == "15x30"
    assert column.properties["section_source"] == "cota"
    assert column.properties["section_area_du2"] == round(0.15 * 0.3, 6)
    assert declared.properties["section_cm"] == "20x30"  # the cuadro stands


def test_wall_thickness_from_crossing_cota_and_unknown_units(tmp_path):
    def build(msp):
        _dim(msp, (3, 0), (3, 0.15), (3.5, 0), angle=90)

    entities = _entities(tmp_path, build)
    wall = make_detection(
        "w1", DetectionType.wall, "W1", (0, 0, 6, 0.16), 0.8, [], "m", [],
        {"estimated_length": 6.0, "estimated_thickness": 0.16},
    )
    assert link_dimensions([wall], entities, meters_factor=None).total == 0
    stats = link_dimensions([wall], entities, meters_factor=1.0)
    assert stats.walls == 1 and wall.properties["estimated_thickness"] == 0.15
    assert wall.properties["thickness_source"] == "cota"
