"""DWG-to-DXF conversion adapter around an external converter (e.g. ODA File Converter).

The engine never parses DWG directly. This adapter shells out to the configured
converter, captures its output, and returns structured results. Failed
conversions are recorded, never silently swallowed.
"""

import subprocess
import time
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from klave_engine.common.config import Settings
from klave_engine.common.errors import ConversionError
from klave_engine.common.logging import get_logger, log_stage
from klave_engine.conversion.libredwg import convert_dwg_to_dxf, dwg2dxf_available
from klave_engine.ingestion.manifest import (
    ConvertedFile,
    FileType,
    ProcessingStatus,
    ProjectManifest,
)

logger = get_logger(__name__)


class ConversionStatus(StrEnum):
    success = "success"
    failed = "failed"
    skipped_existing = "skipped_existing"
    converter_missing = "converter_missing"


class ConversionResult(BaseModel):
    source_path: str
    output_path: str
    status: ConversionStatus
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    error_message: str | None = None


class DwgToDxfConverter:
    """Adapter around the ODA File Converter CLI.

    ODA converts whole directories:
    ``ODAFileConverter <in_dir> <out_dir> <version> <type> <recurse> <audit> [filter]``
    so each file is converted with a filename filter.
    """

    def __init__(
        self,
        executable: Path | None,
        overwrite: bool = False,
        dxf_version: str = "ACAD2018",
        timeout_seconds: int = 120,
    ) -> None:
        self.executable = executable
        self.overwrite = overwrite
        self.dxf_version = dxf_version
        self.timeout_seconds = timeout_seconds

    def converter_available(self) -> bool:
        return self.executable is not None and Path(self.executable).exists()

    def convert_file(self, source: Path, output_dir: Path) -> ConversionResult:
        if not source.exists():
            raise ConversionError(f"Source DWG does not exist: {source}")

        output_path = output_dir / (source.stem + ".dxf")
        if output_path.exists() and not self.overwrite:
            return ConversionResult(
                source_path=str(source),
                output_path=str(output_path),
                status=ConversionStatus.skipped_existing,
            )

        if not self.converter_available():
            return ConversionResult(
                source_path=str(source),
                output_path=str(output_path),
                status=ConversionStatus.converter_missing,
                error_message=(
                    f"Converter executable not found: {self.executable}. "
                    "Set KLAVE_CONVERTER_EXECUTABLE_PATH."
                ),
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        command = [
            str(self.executable),
            str(source.parent),
            str(output_dir),
            self.dxf_version,
            "DXF",
            "0",  # recurse
            "1",  # audit
            source.name,  # filename filter
        ]
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ConversionResult(
                source_path=str(source),
                output_path=str(output_path),
                status=ConversionStatus.failed,
                duration_seconds=time.monotonic() - started,
                error_message=f"Converter execution failed: {exc}",
            )

        duration = time.monotonic() - started
        succeeded = completed.returncode == 0 and output_path.exists()
        result = ConversionResult(
            source_path=str(source),
            output_path=str(output_path),
            status=ConversionStatus.success if succeeded else ConversionStatus.failed,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            duration_seconds=duration,
            error_message=None
            if succeeded
            else f"Converter exited with code {completed.returncode} "
            f"or produced no output at {output_path}",
        )
        log_stage(
            logger,
            "dwg_conversion_completed",
            input_path=source,
            output_path=output_path,
            status=result.status.value,
            duration_seconds=round(duration, 3),
        )
        return result


def convert_project(manifest: ProjectManifest, settings: Settings) -> list[ConversionResult]:
    """Ensure every DWG source has a DXF, using whatever converter is available.

    Conversion is non-fatal and sheet-aware: a DWG whose sheet already has a DXF
    (a sibling file or a DXF source of the same stem) is skipped, so no sheet is
    converted — or parsed — twice. The genuine "no DXF at all" case is handled by
    the caller checking ``manifest.dxf_paths()``.
    """
    root = manifest.root()
    converted_dir = root / settings.converted_dir_name
    oda = DwgToDxfConverter(
        executable=settings.converter_executable_path,
        overwrite=settings.overwrite_converted_files,
        timeout_seconds=settings.converter_timeout_seconds,
    )
    existing_stems = {
        Path(f.path).stem.lower()
        for f in manifest.source_files
        if f.file_type == FileType.dxf
    } | {Path(c.path).stem.lower() for c in manifest.converted_files}

    results: list[ConversionResult] = []
    for source_file in manifest.source_files:
        if source_file.file_type != FileType.dwg:
            continue
        source = root / source_file.path
        if source.stem.lower() in existing_stems:
            results.append(
                ConversionResult(
                    source_path=str(source),
                    output_path=str(source.with_suffix(".dxf")),
                    status=ConversionStatus.skipped_existing,
                )
            )
            continue

        result = _convert_one(source, converted_dir / source_file.file_id, oda, settings)
        results.append(result)
        if result.status in (ConversionStatus.success, ConversionStatus.skipped_existing):
            manifest.converted_files.append(
                ConvertedFile(
                    source_file_id=source_file.file_id,
                    path=str(Path(result.output_path).relative_to(root)),
                    conversion_status="success",
                )
            )
            existing_stems.add(source.stem.lower())
        else:
            manifest.errors.append(
                f"Conversion failed for {source_file.path}: {result.error_message}"
            )

    if manifest.source_files:
        manifest.processing_status = ProcessingStatus.converted
    return results


def _convert_one(
    source: Path, output_dir: Path, oda: DwgToDxfConverter, settings: Settings
) -> ConversionResult:
    """Convert one DWG with the configured ODA converter, else local LibreDWG."""
    if oda.converter_available():
        return oda.convert_file(source, output_dir)
    if dwg2dxf_available():
        target = output_dir / (source.stem + ".dxf")
        dxf, message = convert_dwg_to_dxf(source, target, settings.converter_timeout_seconds)
        return ConversionResult(
            source_path=str(source),
            output_path=str(target),
            status=ConversionStatus.success if dxf else ConversionStatus.failed,
            stderr="" if dxf else message,
            error_message=None if dxf else message,
        )
    return ConversionResult(
        source_path=str(source),
        output_path=str(output_dir / (source.stem + ".dxf")),
        status=ConversionStatus.converter_missing,
        error_message=(
            "Sin convertidor disponible: configura KLAVE_CONVERTER_EXECUTABLE_PATH "
            "o instala dwg2dxf (LibreDWG)."
        ),
    )
