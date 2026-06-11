"""Project manifest schema: source files, converted files, processing state."""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from klave_engine.common.errors import ProjectManifestError
from klave_engine.common.io import read_json, write_json

MANIFEST_FILENAME = "project_manifest.json"


class FileType(StrEnum):
    dwg = "dwg"
    dxf = "dxf"
    other = "other"


class ProcessingStatus(StrEnum):
    created = "created"
    ingested = "ingested"
    converted = "converted"
    parsed = "parsed"
    processed = "processed"
    failed = "failed"


class SourceFile(BaseModel):
    file_id: str
    path: str  # relative to project root
    file_type: FileType
    sheet_number: str | None = None
    discipline: str | None = None


class ConvertedFile(BaseModel):
    source_file_id: str
    path: str  # relative to project root
    file_type: FileType = FileType.dxf
    conversion_status: str = "success"


class ProjectManifest(BaseModel):
    project_id: str
    project_name: str
    root_path: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_files: list[SourceFile] = Field(default_factory=list)
    converted_files: list[ConvertedFile] = Field(default_factory=list)
    processing_status: ProcessingStatus = ProcessingStatus.created
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    def root(self) -> Path:
        return Path(self.root_path)

    def sheet_numbers(self) -> set[str]:
        return {f.sheet_number for f in self.source_files if f.sheet_number}

    def dxf_paths(self) -> list[Path]:
        """All parseable DXF files: native DXF sources plus successful conversions."""
        root = self.root()
        paths = [root / f.path for f in self.source_files if f.file_type == FileType.dxf]
        paths += [
            root / f.path for f in self.converted_files if f.conversion_status == "success"
        ]
        return paths


def manifest_path(project_root: Path, processed_dir_name: str = "processed") -> Path:
    return project_root / processed_dir_name / MANIFEST_FILENAME


def save_manifest(manifest: ProjectManifest, processed_dir_name: str = "processed") -> Path:
    return write_json(manifest_path(manifest.root(), processed_dir_name), manifest)


def load_manifest(project_root: Path, processed_dir_name: str = "processed") -> ProjectManifest:
    path = manifest_path(project_root, processed_dir_name)
    if not path.exists():
        raise ProjectManifestError(f"No project manifest found at {path}")
    return ProjectManifest.model_validate(read_json(path))
