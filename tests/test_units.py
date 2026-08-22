"""Units: the header first, then the cotas the engineer wrote, then extent."""

import ezdxf
from klave_engine.dxf.parser import DxfParser
from klave_engine.dxf.units import detect_units
from klave_engine.geometry.spatial_index import SpatialIndex


def _drawing(tmp_path, build, insunits=0):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = insunits
    build(doc.modelspace())
    path = tmp_path / "u.dxf"
    doc.saveas(path)
    drawing = DxfParser().parse_file(path)
    return drawing, SpatialIndex(drawing.entities).extent(), drawing.insunits


def test_header_wins(tmp_path):
    drawing, extent, insunits = _drawing(tmp_path, lambda msp: msp.add_line((0, 0), (1, 0)), 6)
    units = detect_units(insunits, drawing.entities, extent)
    assert units.unit == "m" and units.source == "dxf_header"


def test_cotas_reveal_centimetres(tmp_path):
    def build(msp):
        # A 250-unit span whose cota reads "2.50": the drawing is in cm.
        for i in range(6):
            y = i * 300
            msp.add_line((0, y), (250, y))
            msp.add_linear_dim(
                base=(0, y - 40), p1=(0, y), p2=(250, y), override={"dimtxt": 10}
            ).render()
            msp.add_text("2.50", height=10).set_placement((100, y - 40))
    drawing, extent, insunits = _drawing(tmp_path, build)
    dims = [e for e in drawing.entities if e.entity_type.value == "dimension"]
    assert dims and dims[0].properties["measurement"] == 250.0
    # ezdxf renders "250" (drawing units) — simulate the engineer's displayed metres.
    for dim in dims:
        dim.properties["display_text"] = "2.50"
        dim.properties["display_value"] = 2.5
    units = detect_units(insunits, drawing.entities, extent)
    assert units.unit == "cm" and units.source == "dimensions" and units.confidence >= 0.85


def test_extent_and_text_heights_vote_without_cotas(tmp_path):
    def build(msp):
        # Torre-like: 10 × 8 m building drawn in cm, text 12 units high.
        msp.add_line((0, 0), (1000, 0))
        msp.add_line((0, 0), (0, 800))
        for i in range(12):
            msp.add_text(f"C-{i}", height=12).set_placement((i * 50, 100))
    drawing, extent, insunits = _drawing(tmp_path, build)
    units = detect_units(insunits, drawing.entities, extent)
    assert units.unit == "cm" and units.source == "heuristics"
    assert units.confidence == 0.75  # extent and text heights agree
    assert "extensión" in units.notes[0]


def test_display_text_is_read_from_override(tmp_path):
    def build(msp):
        msp.add_linear_dim(base=(0, -1), p1=(0, 0), p2=(2.5, 0), text="2.50").render()
    drawing, _extent, _ = _drawing(tmp_path, build, 6)
    dim = next(e for e in drawing.entities if e.entity_type.value == "dimension")
    assert dim.properties["display_text"] == "2.50" and dim.properties["display_value"] == 2.5
    assert dim.properties["dimlfac"] == 1.0
