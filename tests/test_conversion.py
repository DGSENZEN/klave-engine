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
