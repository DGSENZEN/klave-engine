"""The DXF loader: converter habits become warnings, never crashes."""

import ezdxf
import pytest
from klave_engine.conversion import libredwg
from klave_engine.dxf.loader import load_dxf, sanitize_dxf_text
from klave_engine.dxf.parser import DxfParser


def _write(tmp_path, name="t.dxf"):
    doc = ezdxf.new("R2010")
    doc.modelspace().add_line((0, 0), (5, 0))
    doc.modelspace().add_text("K-1", height=0.2)
    path = tmp_path / name
    doc.saveas(path)
    return path, doc.modelspace().block_record.dxf.handle


def test_object_records_inside_entities_are_dropped(tmp_path):
    path, owner = _write(tmp_path)
    text = path.read_text(encoding="utf-8")
    # LibreDWG habit: an OBJECT dumped among the entities, owned by model space.
    record = f"  0\nSORTENTSTABLE\n  5\nF0B\n330\n{owner}\n100\nAcDbSortentsTable\n"
    injected = text.replace("  0\nLINE\n", record + "  0\nLINE\n", 1)
    path.write_text(injected, encoding="utf-8")
    cleaned, rejoined, dropped = sanitize_dxf_text(injected)
    assert dropped == 1 and rejoined == 0 and "SORTENTSTABLE" not in cleaned
    assert "AcDbSortentsTable" not in cleaned and cleaned.count("\nLINE\n") == 1
    # Whatever ezdxf makes of the stray object, the chain ends in a usable doc.
    loaded = load_dxf(path)
    assert loaded.doc is not None
    drawing = DxfParser().parse_file(path)
    assert any(e.text == "K-1" for e in drawing.entities)
    assert any(w.warning_type == "non_graphical_in_entities" for w in drawing.warnings)
    assert libredwg._output_is_readable(path) is True
    assert libredwg.completeness(path)["entities"] == 2


def test_embedded_newlines_are_rejoined():
    raw = "  0\nSECTION\n  2\nENTITIES\n  0\nMTEXT\n  1\nPLANTA\nBAJA\n  0\nENDSEC\n  0\nEOF\n"
    text, rejoined, dropped = sanitize_dxf_text(raw)
    assert rejoined == 1 and dropped == 0
    assert "PLANTA\\PBAJA" in text


def test_unreadable_file_raises_with_every_reason(tmp_path):
    bad = tmp_path / "bad.dxf"
    bad.write_bytes(b"\x00\x01 not a dxf")
    with pytest.raises(ValueError) as info:
        load_dxf(bad)
    assert "estricto" in str(info.value) and "saneado" in str(info.value)
