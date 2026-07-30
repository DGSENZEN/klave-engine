"""Project folder ingestion: scan drawing files and build the project manifest."""

import re
from pathlib import Path

from klave_engine.common.errors import ProjectManifestError
from klave_engine.common.ids import short_uuid, slugify
from klave_engine.common.logging import get_logger, log_stage
from klave_engine.ingestion.manifest import (
    ConvertedFile,
    FileType,
    ProcessingStatus,
    ProjectManifest,
    SourceFile,
    load_manifest,
    manifest_path,
    save_manifest,
)

logger = get_logger(__name__)

SHEET_NUMBER_PATTERN = re.compile(r"([A-Z]{1,2}-?\d{2,4})", re.IGNORECASE)

DISCIPLINE_BY_PREFIX = {
    "S": "structural",
    "A": "architectural",
    "M": "mechanical",
    "E": "electrical",
    "P": "plumbing",
    "C": "civil",
}


def infer_sheet_number(filename: str) -> str | None:
    match = SHEET_NUMBER_PATTERN.search(Path(filename).stem)
    return match.group(1).upper() if match else None


def infer_discipline(sheet_number: str | None) -> str | None:
    if not sheet_number:
        return None
    return DISCIPLINE_BY_PREFIX.get(sheet_number[0].upper())


def find_drawing_files(project_root: Path) -> list[Path]:
    """Find DWG/DXF files in the project root and its ``drawings/`` subfolder."""
    candidates: list[Path] = []
    search_dirs = [project_root, project_root / "drawings"]
    for directory in search_dirs:
        if directory.is_dir():
            candidates.extend(
                path
                for path in directory.iterdir()
                if path.is_file() and path.suffix.lower() in {".dwg", ".dxf"}
            )
    return sorted(candidates, key=lambda path: str(path.relative_to(project_root)).casefold())


def _existing_project_id(project_root: Path, processed_dir_name: str) -> str | None:
    """Keep the ID stable when an existing local project is re-ingested."""
    path = manifest_path(project_root, processed_dir_name)
    if not path.exists():
        return None
    try:
        return load_manifest(project_root, processed_dir_name).project_id
    except ProjectManifestError:
        return None


def ingest_project(
    project_root: Path,
    project_name: str | None = None,
    project_id: str | None = None,
    processed_dir_name: str = "processed",
) -> ProjectManifest:
    """Scan a project folder and write its manifest."""
    project_root = project_root.resolve()
    if not project_root.is_dir():
        raise ProjectManifestError(f"Project root does not exist: {project_root}")

    drawing_files = find_drawing_files(project_root)
    project_id = project_id or _existing_project_id(project_root, processed_dir_name)
    if project_id is None:
        stem = slugify(project_root.name)[:40] or "project"
        project_id = f"{stem}_{short_uuid('p')[2:]}"
    manifest = ProjectManifest(
        project_id=project_id,
        project_name=project_name or project_root.name,
        root_path=str(project_root),
        processing_status=ProcessingStatus.ingested,
    )

    for index, path in enumerate(drawing_files, start=1):
        sheet_number = infer_sheet_number(path.name)
        manifest.source_files.append(
            SourceFile(
                file_id=f"{slugify(path.stem)}_{index:03d}",
                path=str(path.relative_to(project_root)),
                file_type=FileType(path.suffix.lower().lstrip(".")),
                sheet_number=sheet_number,
                discipline=infer_discipline(sheet_number),
            )
        )

    # Persisted conversion outputs are part of the manifest, not new source
    # drawings. This avoids parsing a DWG's generated DXF twice on re-ingest.
    for source_file in manifest.source_files:
        if source_file.file_type != FileType.dwg:
            continue
        converted = (
            project_root
            / "converted"
            / source_file.file_id
            / f"{Path(source_file.path).stem}.dxf"
        )
        if converted.is_file():
            manifest.converted_files.append(
                ConvertedFile(
                    source_file_id=source_file.file_id,
                    path=str(converted.relative_to(project_root)),
                )
            )

    if not manifest.source_files:
        manifest.warnings.append("No DWG or DXF files found during ingestion")

    save_manifest(manifest, processed_dir_name)
    log_stage(
        logger,
        "project_ingest_completed",
        project_id=project_id,
        input_path=project_root,
        file_count=len(manifest.source_files),
        warning_count=len(manifest.warnings),
        status=manifest.processing_status.value,
    )
    return manifest
