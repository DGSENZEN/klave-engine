"""DWG conversion adapter behavior with a mocked subprocess."""

import subprocess
from pathlib import Path

from klave_engine.conversion.dwg_to_dxf import ConversionStatus, DwgToDxfConverter


def _fake_converter_executable(tmp_path: Path) -> Path:
    executable = tmp_path / "fake_oda"
    executable.write_text("#!/bin/sh\n")
    return executable


def test_converter_missing_reports_structured_error(tmp_path: Path) -> None:
    source = tmp_path / "S-101.dwg"
    source.write_bytes(b"fake dwg")
    converter = DwgToDxfConverter(executable=tmp_path / "does_not_exist")
    result = converter.convert_file(source, tmp_path / "converted")
    assert result.status == ConversionStatus.converter_missing
    assert "KLAVE_CONVERTER_EXECUTABLE_PATH" in (result.error_message or "")


def test_existing_output_is_skipped_without_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "S-101.dwg"
    source.write_bytes(b"fake dwg")
    output_dir = tmp_path / "converted"
    output_dir.mkdir()
    (output_dir / "S-101.dxf").write_text("existing")
    converter = DwgToDxfConverter(executable=_fake_converter_executable(tmp_path))
    result = converter.convert_file(source, output_dir)
    assert result.status == ConversionStatus.skipped_existing
    assert (output_dir / "S-101.dxf").read_text() == "existing"


def test_successful_conversion_with_mocked_subprocess(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "S-101.dwg"
    source.write_bytes(b"fake dwg")
    output_dir = tmp_path / "converted"

    def fake_run(command, **kwargs):
        Path(command[2]).mkdir(parents=True, exist_ok=True)
        (Path(command[2]) / "S-101.dxf").write_text("converted dxf")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    converter = DwgToDxfConverter(executable=_fake_converter_executable(tmp_path))
    result = converter.convert_file(source, output_dir)
    assert result.status == ConversionStatus.success
    assert result.stdout == "ok"


def test_failed_conversion_is_recorded(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "S-101.dwg"
    source.write_bytes(b"fake dwg")

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    converter = DwgToDxfConverter(executable=_fake_converter_executable(tmp_path))
    result = converter.convert_file(source, tmp_path / "converted")
    assert result.status == ConversionStatus.failed
    assert result.error_message is not None
