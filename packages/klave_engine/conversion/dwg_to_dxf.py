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

from klave_engine.common.errors import ConversionError
from klave_engine.common.logging import get_logger, log_stage
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


def convert_project(
    manifest: ProjectManifest,
    converter: DwgToDxfConverter,
    converted_dir_name: str = "converted",
) -> list[ConversionResult]:
    """Convert all DWG source files in a project and update the manifest in memory."""
    root = manifest.root()
    output_dir = root / converted_dir_name
    results: list[ConversionResult] = []
    already_converted = {c.source_file_id for c in manifest.converted_files}

    for source_file in manifest.source_files:
        if source_file.file_type != FileType.dwg:
            continue
        result = converter.convert_file(root / source_file.path, output_dir)
        results.append(result)
        if result.status in (ConversionStatus.success, ConversionStatus.skipped_existing):
            if source_file.file_id not in already_converted:
                manifest.converted_files.append(
                    ConvertedFile(
                        source_file_id=source_file.file_id,
                        path=str(Path(result.output_path).relative_to(root)),
                        conversion_status="success",
                    )
                )
        else:
            manifest.errors.append(
                f"Conversion failed for {source_file.path}: {result.error_message}"
            )

    if any(r.status == ConversionStatus.failed for r in results):
        manifest.processing_status = ProcessingStatus.failed
    elif manifest.source_files:
        manifest.processing_status = ProcessingStatus.converted
    return results
