"""Detail reference detection (e.g. ``5/S-301``) and resolution against the manifest."""

from pydantic import BaseModel

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.results import (
    DetectionType,
    DetectorOutput,
    make_detection,
)
from klave_engine.detection.text_patterns import TextPatternConfig, match_category
from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.ingestion.manifest import ProjectManifest


class DetailReferenceDetectorConfig(BaseModel):
    base_confidence: float = 0.85


def _normalize_sheet(sheet: str) -> str:
    return sheet.upper().replace("-", "")


def detect_detail_references(
    entities: list[NormalizedEntity],
    manifest: ProjectManifest,
    config: DetailReferenceDetectorConfig | None = None,
    text_config: TextPatternConfig | None = None,
    detection_ids: IdGenerator | None = None,
) -> DetectorOutput:
    config = config or DetailReferenceDetectorConfig()
    text_config = text_config or TextPatternConfig()
    detection_ids = detection_ids or IdGenerator("det")
    output = DetectorOutput(detector_name="detail_reference_detector")

    known_sheets = {_normalize_sheet(s): s for s in manifest.sheet_numbers()}

    for entity in entities:
        if not entity.is_textual or not entity.text:
            continue
        match = match_category(entity.text, text_config, "detail_reference")
        if match is None:
            continue
        target_sheet = match.groups.get("sheet", "").upper()
        target_detail = match.groups.get("detail", "")
        resolved = _normalize_sheet(target_sheet) in known_sheets

        notes = [f"Text '{entity.text.strip()}' matched detail reference pattern"]
        if resolved:
            notes.append(f"Sheet {target_sheet} found in project manifest")
        else:
            notes.append(f"Sheet {target_sheet} NOT found in project manifest")
        output.detections.append(
            make_detection(
                detection_ids.next(),
                DetectionType.detail_reference,
                entity.text.strip(),
                entity.bbox,
                config.base_confidence,
                [entity.entity_id],
                "detail_reference_regex_manifest_lookup",
                notes,
                {
                    "target_sheet": target_sheet,
                    "target_detail": target_detail,
                    "resolved": resolved,
                },
                entity.source_file,
            )
        )
    return output
