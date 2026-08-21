"""Parser coverage: curve flattening, block explosion, and its budgets."""

import ezdxf
import pytest

from klave_engine.dxf import parser as parser_module
from klave_engine.dxf.parser import DxfParser


@pytest.fixture
def dxf_path(tmp_path):
    def _write(build):
        doc = ezdxf.new("R2010")
        build(doc)
        path = tmp_path / "test.dxf"
        doc.saveas(path)
        return path

    return _write


def test_curves_flatten_into_polylines(dxf_path):
    def build(doc):
        msp = doc.modelspace()
        msp.add_spline(fit_points=[(0, 0), (2, 3), (4, 1)])
        msp.add_ellipse((10, 10), major_axis=(3, 0), ratio=0.5)
        msp.add_solid([(20, 20), (21, 20), (20, 21), (21, 21)])

    drawing = DxfParser().parse_file(dxf_path(build))
    derived = {e.properties.get("derived_from") for e in drawing.entities}
    assert derived == {"SPLINE", "ELLIPSE", "SOLID"}
    assert all(e.entity_type.value == "polyline" for e in drawing.entities)
    solid = next(e for e in drawing.entities if e.properties["derived_from"] == "SOLID")
    assert solid.is_closed and len(solid.points) >= 3
    assert not drawing.warnings


def test_block_explosion_reaches_marks_and_adopts_layer(dxf_path):
    def build(doc):
        block = doc.blocks.new(name="CASTILLO")
        block.add_line((0, 0), (1, 1))       # layer "0" → adopts insert layer
        block.add_text("K-7", height=0.2)
        msp = doc.modelspace()
        insert = msp.add_blockref("CASTILLO", (5, 5))
        insert.dxf.layer = "S-COL"

    drawing = DxfParser().parse_file(dxf_path(build))
    exploded = [e for e in drawing.entities if e.properties.get("from_block")]
    assert {e.entity_type.value for e in exploded} == {"line", "text"}
    assert all(e.layer == "S-COL" for e in exploded)
    assert any(e.text == "K-7" for e in exploded)
    assert all(e.block_name == "CASTILLO" for e in exploded)


def test_block_explosion_is_budgeted(dxf_path, monkeypatch):
    monkeypatch.setattr(parser_module, "MAX_CHILDREN_PER_INSERT", 5)

    def build(doc):
        block = doc.blocks.new(name="DENSO")
        for i in range(20):
            block.add_line((i, 0), (i, 1))
        doc.modelspace().add_blockref("DENSO", (0, 0))

    drawing = DxfParser().parse_file(dxf_path(build))
    exploded = [e for e in drawing.entities if e.properties.get("from_block")]
    assert len(exploded) == 5
    assert any(w.warning_type == "block_explosion_capped" for w in drawing.warnings)


def test_unsupported_types_warn_never_silently_drop(dxf_path):
    def build(doc):
        msp = doc.modelspace()
        msp.add_point((0, 0))
        msp.add_line((0, 0), (1, 1))

    drawing = DxfParser().parse_file(dxf_path(build))
    assert len(drawing.entities) == 1
    dropped = [w for w in drawing.warnings if w.warning_type == "unsupported_dxf_entity"]
    assert len(dropped) == 1 and dropped[0].entity_type == "POINT"
