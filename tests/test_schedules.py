"""Sheet-declared specifications: tables, details, notes, and their authority."""

import ezdxf
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.schedules import apply_schedule, build_schedule_inventory
from klave_engine.dxf.parser import DxfParser


def _entities(tmp_path, build):
    doc = ezdxf.new("R2010")
    build(doc.modelspace())
    path = tmp_path / "specs.dxf"
    doc.saveas(path)
    return DxfParser().parse_file(path).entities


def test_table_rows_become_specs_by_mark(tmp_path):
    def build(msp):
        header = ["MARCA", "SECCION", "ARMADO", "ESTRIBOS"]
        for col, title in enumerate(header):
            msp.add_text(title, height=0.25).set_placement((col * 3, 10))
        rows = [["K-1", "15x20", "4#3", "E#2@20"], ["K-2", "20 x 30", "6 VAR #4", "E#3@15"]]
        for r, row in enumerate(rows):
            for col, value in enumerate(row):
                msp.add_text(value, height=0.25).set_placement((col * 3, 9.5 - r * 0.5))
        msp.add_text("NOTAS GENERALES", height=0.25).set_placement((0, 2))  # far: ends the table

    inventory = build_schedule_inventory(_entities(tmp_path, build))
    assert inventory.tables_found == 1
    k1, k2 = inventory.by_mark["K-1"], inventory.by_mark["K-2"]
    assert (k1.section_cm, k1.rebar, k1.stirrups, k1.source) == ((15, 20), "4#3", "#2@20", "cuadro")
    assert (k2.section_cm, k2.rebar, k2.stirrups) == ((20, 30), "6#4", "#3@15")
    assert k1.family == "castillo"


def test_detail_annotation_and_family_note(tmp_path):
    def build(msp):
        msp.add_text("C-1", height=0.3).set_placement((0, 0))
        msp.add_text("30x40  8#5  E#3@15", height=0.2).set_placement((1.0, -0.4))
        msp.add_text("ARMEX 15X30", height=0.2).set_placement((40, 40))  # a general note
        msp.add_text("DALA 15x30 4#3,E#2@20", height=0.2).set_placement((40, 38))

    inventory = build_schedule_inventory(_entities(tmp_path, build))
    c1 = inventory.by_mark["C-1"]
    assert c1.source == "detalle" and c1.section_cm == (30, 40)
    assert c1.rebar == "8#5" and c1.stirrups == "#3@15"
    assert inventory.by_family["castillo"].section_cm == (15, 30)
    assert inventory.by_family["dala"].rebar == "4#3"
    assert "K-1" not in inventory.by_mark


def test_apply_stamps_sections_by_authority(tmp_path):
    def build(msp):
        msp.add_text("K-1 15x20 4#3 E#2@20", height=0.2).set_placement((0, 0))
        msp.add_text("ARMEX 15X30", height=0.2).set_placement((10, 10))

    inventory = build_schedule_inventory(_entities(tmp_path, build))
    k1 = make_detection("d1", DetectionType.column_tag, "K-1", (0, 0, 1, 1), 0.8, [], "m", [])
    k1.properties["section_area_du2"] = 0.5  # a measured marker the sheet overrules
    k1.properties["section_source"] = "marcador_poligonal"
    k7 = make_detection("d2", DetectionType.column_tag, "K-7", (0, 0, 1, 1), 0.8, [], "m", [])
    c9 = make_detection("d3", DetectionType.column_tag, "C-9", (0, 0, 1, 1), 0.8, [], "m", [])
    assert apply_schedule([k1, k7, c9], inventory, meters_factor=1.0) == 2
    assert k1.properties["section_cm"] == "15x20" and k1.properties["section_area_du2"] == 0.03
    assert k1.properties["section_marker_du2"] == 0.5  # kept as evidence, not used
    assert k7.properties["section_cm"] == "15x30"  # family-level note covers K-*
    assert "section_cm" not in c9.properties  # no spec for columnas: assumptions apply
    assert apply_schedule([k1], inventory, meters_factor=None) == 0
