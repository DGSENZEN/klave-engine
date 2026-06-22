"""Entity normalization details: bboxes, closed flags, text, hatches."""

from pathlib import Path

import ezdxf
import pytest
from klave_engine.dxf.entities import EntityType
from klave_engine.dxf.parser import DxfParser


def test_circle_bbox_is_exact(demo_entities) -> None:
    circles = [e for e in demo_entities if e.entity_type == EntityType.circle]
    circle = next(c for c in circles if c.properties["center"] == (200.0, 600.0))
    assert circle.bbox == (192.0, 592.0, 208.0, 608.0)


def test_closed_polyline_flag(demo_entities) -> None:
    polylines = [e for e in demo_entities if e.entity_type == EntityType.polyline]
    assert all(p.is_closed for p in polylines)
    assert all(p.points and len(p.points) >= 3 for p in polylines)


def test_text_normalization_preserves_content(demo_entities) -> None:
    texts = {e.text for e in demo_entities if e.entity_type == EntityType.text}
    assert {"C1", "C2", "B1", "5/S-501", "2/S-101", "A", "B", "1", "2"} <= texts


def test_text_bbox_is_conservative_approximation(demo_entities) -> None:
    c1 = next(e for e in demo_entities if e.text == "C1" and e.bbox[0] == 210.0)
    assert c1.bbox[2] > c1.bbox[0] and c1.bbox[3] > c1.bbox[1]
    assert any("approximated" in note for note in c1.evidence.notes)


def test_hatch_normalization(tmp_path: Path) -> None:
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    hatch = msp.add_hatch(color=7, dxfattribs={"layer": "S-SLAB"})
    hatch.paths.add_polyline_path(
        [(0, 0), (100, 0), (100, 50), (0, 50)], is_closed=True
    )
    path = tmp_path / "hatch.dxf"
    doc.saveas(str(path))

    drawing = DxfParser().parse_file(path)
    hatches = [e for e in drawing.entities if e.entity_type == EntityType.hatch]
    assert len(hatches) == 1
    assert hatches[0].bbox == (0.0, 0.0, 100.0, 50.0)
    assert hatches[0].is_closed


def test_insert_with_missing_block_definition_falls_back(tmp_path: Path) -> None:
    """Regression: an INSERT referencing a missing block definition must not
    crash bbox computation; it falls back to the insertion point.
    (Found on a real azotea sheet whose INSERT referenced block '*X'.)"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    # Reference a block name that has no BLOCK definition in the document.
    msp.add_blockref("DOES_NOT_EXIST", (12.0, 34.0), dxfattribs={"layer": "S-ANNO"})
    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "S-GRID"})
    path = tmp_path / "ghost_block.dxf"
    doc.saveas(str(path))

    drawing = DxfParser().parse_file(path)
    inserts = [e for e in drawing.entities if e.entity_type == EntityType.insert]
    assert len(inserts) == 1
    # bbox degenerates to the insertion point rather than raising.
    assert inserts[0].bbox == (12.0, 34.0, 12.0, 34.0)
    assert any("insertion point" in note for note in inserts[0].evidence.notes)


def test_dimension_entity_is_parsed_with_measurement(tmp_path: Path) -> None:
    """DIMENSION entities carry the engineer's measured value (highest-authority
    source); they must be extracted, not skipped (209 were dropped on a real file)."""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_linear_dim(base=(0, 5), p1=(0, 0), p2=(3, 0)).render()
    msp.add_line((0, 0), (3, 0), dxfattribs={"layer": "S-GRID"})
    path = tmp_path / "dim.dxf"
    doc.saveas(str(path))

    drawing = DxfParser().parse_file(path)
    dims = [e for e in drawing.entities if e.entity_type == EntityType.dimension]
    assert len(dims) == 1
    assert dims[0].properties["measurement"] == pytest.approx(3.0, abs=0.01)
