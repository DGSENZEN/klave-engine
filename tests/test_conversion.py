"""Conversion adapter: readability probe and failure honesty."""

import ezdxf
from klave_engine.conversion import libredwg


def test_probe_rejects_garbage(tmp_path):
    bad = tmp_path / "bad.dxf"
    bad.write_text("this is not a dxf at all")
    assert libredwg._output_is_readable(bad) is False


def test_probe_accepts_real_dxf(tmp_path):
    path = tmp_path / "ok.dxf"
    doc = ezdxf.new("R2010")
    doc.modelspace().add_line((0, 0), (1, 1))
    doc.saveas(path)
    assert libredwg._output_is_readable(path) is True


def test_dxf_passthrough(tmp_path):
    path = tmp_path / "plano.dxf"
    path.write_text("irrelevant")
    result, message = libredwg.convert_dwg_to_dxf(path)
    assert result == path
    assert "no requiere conversión" in message


def test_missing_converter_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(libredwg.shutil, "which", lambda _name: None)
    result, message = libredwg.convert_dwg_to_dxf(tmp_path / "plano.dwg")
    assert result is None
    assert "no encontrado" in message


def test_most_complete_output_wins_and_minimal_is_last_resort():
    full = {"entities": 5277, "texts": 1036, "blocks": 523, "layouts": 3}
    fewer_blocks = {"entities": 5277, "texts": 1036, "blocks": 2, "layouts": 2}
    best = libredwg.choose_best({"estándar": fewer_blocks, "versión r2000": full})
    assert best == "versión r2000"
    # Ties keep the first declared attempt; nothing to choose from yields None.
    assert libredwg.choose_best({"estándar": full, "versión r2000": dict(full)}) == "estándar"
    assert libredwg.choose_best({}) is None
    assert "-m" in libredwg._LAST_RESORT[1] and all("-m" not in a for _, a in libredwg._CANDIDATES)


def test_completeness_counts_what_matters(tmp_path):
    path = tmp_path / "ok.dxf"
    doc = ezdxf.new("R2010")
    doc.modelspace().add_line((0, 0), (1, 1))
    doc.modelspace().add_text("C-1")
    doc.blocks.new(name="CASTILLO")
    doc.saveas(path)
    assert libredwg.completeness(path) == {"entities": 2, "texts": 1, "blocks": 1, "layouts": 2}
    bad = tmp_path / "bad.dxf"
    bad.write_text("nope")
    assert libredwg.completeness(bad) is None
