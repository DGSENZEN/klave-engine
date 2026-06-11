"""DXF parsing on the deterministic demo fixture."""

from pathlib import Path

import ezdxf
import pytest
from klave_engine.common.errors import DxfParseError
from klave_engine.dxf.entities import EntityType
from klave_engine.dxf.parser import DxfParser
from klave_engine.ingestion.project_loader import infer_sheet_number, ingest_project


def test_parse_demo_drawing_counts(demo_drawing) -> None:
    by_type = {}
    for entity in demo_drawing.entities:
        by_type[entity.entity_type] = by_type.get(entity.entity_type, 0) + 1
    assert by_type[EntityType.line] == 7  # 4 grid + 1 beam + 2 wall
    assert by_type[EntityType.circle] == 2
    assert by_type[EntityType.polyline] == 3  # 2 footings + 1 slab
    assert by_type[EntityType.text] == 10


def test_entities_have_handles_and_layers(demo_drawing) -> None:
    for entity in demo_drawing.entities:
        assert entity.raw_handle
        assert entity.layer.startswith("S-")
        assert entity.evidence.method.startswith("ezdxf_")


def test_unsupported_entity_produces_warning_not_crash(tmp_path: Path) -> None:
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_spline([(0, 0), (10, 5), (20, 0)], dxfattribs={"layer": "S-ANNO"})
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "S-GRID"})
    path = tmp_path / "spline.dxf"
    doc.saveas(str(path))

    drawing = DxfParser().parse_file(path)
    assert len(drawing.entities) == 1
    assert any(w.warning_type == "unsupported_dxf_entity" for w in drawing.warnings)
    assert any(w.entity_type == "SPLINE" for w in drawing.warnings)


def test_missing_file_raises_parse_error(tmp_path: Path) -> None:
    with pytest.raises(DxfParseError):
        DxfParser().parse_file(tmp_path / "nope.dxf")


def test_manifest_creation(demo_project_root: Path) -> None:
    manifest = ingest_project(demo_project_root)
    assert manifest.project_id == "demo_project_001"
    assert len(manifest.source_files) == 1
    assert manifest.source_files[0].sheet_number == "S-101"
    assert manifest.source_files[0].discipline == "structural"


def test_sheet_number_inference() -> None:
    assert infer_sheet_number("S-101.dwg") == "S-101"
    assert infer_sheet_number("plan_S201_rev2.dxf") == "S201"
    assert infer_sheet_number("notes.dxf") is None


def test_value_with_embedded_newline_is_recovered(tmp_path: Path) -> None:
    """Regression: LibreDWG writes MTEXT values containing literal newlines,
    which desynchronizes strict DXF tag parsing (found with a real DWG)."""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_text("MARKER_TEXT_VALUE", dxfattribs={"layer": "S-ANNO", "height": 2.5})
    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "S-GRID"})
    path = tmp_path / "broken.dxf"
    doc.saveas(str(path))

    content = path.read_text(encoding="utf-8")
    assert "MARKER_TEXT_VALUE" in content
    path.write_text(
        content.replace("MARKER_TEXT_VALUE", "MARKER_TEXT\nVALUE"), encoding="utf-8"
    )

    drawing = DxfParser().parse_file(path)
    assert any(w.warning_type == "dxf_recovered" for w in drawing.warnings)
    texts = [e for e in drawing.entities if e.text]
    assert any("MARKER_TEXT" in (e.text or "") for e in texts)
    assert len(drawing.entities) == 2
