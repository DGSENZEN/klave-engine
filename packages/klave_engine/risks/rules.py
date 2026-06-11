"""Deterministic risk rules over detections, entities, and the manifest.

Every finding names its sources and recommends a human action. Messages are
specific, never vague.
"""

from collections import Counter, defaultdict
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from klave_engine.common.ids import IdGenerator
from klave_engine.common.logging import get_logger, log_stage
from klave_engine.detection.results import Detection, DetectionType
from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.geometry.bbox import BBox, bbox_distance
from klave_engine.graph.evidence import EvidencePacket
from klave_engine.ingestion.manifest import ProjectManifest
from klave_engine.takeoff.quantities import QuantityReport

logger = get_logger(__name__)

KNOWN_LAYER_HINTS = [
    # English
    "GRID", "COL", "BEAM", "WALL", "SLAB", "FOOT", "FOUND", "FDN",
    "TEXT", "ANNO", "DIM", "0",
    # Spanish (Mexican structural conventions)
    "EJE", "TRABE", "LOSA", "MURO", "CASTILLO", "ZAPATA", "CIM", "DADO",
    "PILOT", "ACERO", "ARMADO", "COTA", "EST", "CADENA", "DALA", "TEXTO",
]


class Severity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class RiskFinding(BaseModel):
    risk_id: str
    risk_type: str
    severity: Severity
    message: str
    source_entities: list[str] = Field(default_factory=list)
    related_detections: list[str] = Field(default_factory=list)
    bbox: BBox | None = None
    evidence: EvidencePacket
    recommended_human_action: str


class RiskReport(BaseModel):
    project_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    findings: list[RiskFinding] = Field(default_factory=list)
    counts_by_severity: dict[str, int] = Field(default_factory=dict)


class RiskEngineConfig(BaseModel):
    duplicate_column_distance: float = 100.0
    low_confidence_threshold: float = 0.7
    unknown_layer_ratio_threshold: float = 0.5
    unknown_layer_min_entities: int = 20


def generate_risk_report(
    project_id: str,
    manifest: ProjectManifest,
    entities: list[NormalizedEntity],
    detections: list[Detection],
    quantity_report: QuantityReport | None = None,
    config: RiskEngineConfig | None = None,
) -> RiskReport:
    config = config or RiskEngineConfig()
    ids = IdGenerator("risk")
    findings: list[RiskFinding] = []

    def evidence_for(method: str, detection: Detection | None = None) -> EvidencePacket:
        return EvidencePacket(
            source=detection.evidence.source if detection else project_id,
            method=method,
            entity_ids=detection.source_entities if detection else [],
            bbox=detection.bbox if detection else None,
        )

    by_type: dict[DetectionType, list[Detection]] = defaultdict(list)
    for detection in detections:
        by_type[detection.detection_type].append(detection)

    # Rule: detail reference points to a missing sheet.
    for detail in by_type[DetectionType.detail_reference]:
        if detail.properties.get("resolved", False):
            continue
        sheet = detail.properties.get("target_sheet", "?")
        findings.append(
            RiskFinding(
                risk_id=ids.next(),
                risk_type="unresolved_detail_reference",
                severity=Severity.high,
                message=(
                    f"Detail reference {detail.label} was found on "
                    f"{detail.evidence.source}, but sheet {sheet} is not present "
                    "in the project manifest."
                ),
                source_entities=detail.source_entities,
                related_detections=[detail.detection_id],
                bbox=detail.bbox,
                evidence=evidence_for("detail_reference_manifest_lookup", detail),
                recommended_human_action=(
                    f"Confirm whether sheet {sheet} exists and add it to the project, "
                    "or correct the reference."
                ),
            )
        )

    # Rule: column tag with no nearby grid intersection.
    for column in by_type[DetectionType.column_tag]:
        if column.properties.get("has_nearby_grid", False):
            continue
        findings.append(
            RiskFinding(
                risk_id=ids.next(),
                risk_type="column_tag_without_grid",
                severity=Severity.medium,
                message=(
                    f"Column tag {column.label} on {column.evidence.source} has no "
                    "grid intersection within the search radius."
                ),
                source_entities=column.source_entities,
                related_detections=[column.detection_id],
                bbox=column.bbox,
                evidence=evidence_for("column_grid_proximity_check", column),
                recommended_human_action=(
                    f"Verify the placement of column {column.label} against the "
                    "structural grid."
                ),
            )
        )

    # Rule: footing with no nearby column tag.
    for footing in by_type[DetectionType.footing]:
        if footing.properties.get("nearby_column_tag"):
            continue
        findings.append(
            RiskFinding(
                risk_id=ids.next(),
                risk_type="footing_without_column",
                severity=Severity.medium,
                message=(
                    f"Footing {footing.label} on {footing.evidence.source} has no "
                    "column tag within the search radius."
                ),
                source_entities=footing.source_entities,
                related_detections=[footing.detection_id],
                bbox=footing.bbox,
                evidence=evidence_for("footing_column_proximity_check", footing),
                recommended_human_action=(
                    f"Check whether footing {footing.label} supports an untagged column."
                ),
            )
        )

    # Rule: duplicate column tag labels in distant locations.
    columns_by_label: dict[str, list[Detection]] = defaultdict(list)
    for column in by_type[DetectionType.column_tag]:
        columns_by_label[column.label].append(column)
    for label, group in sorted(columns_by_label.items()):
        if len(group) < 2:
            continue
        max_distance = max(
            bbox_distance(a.bbox, b.bbox)
            for i, a in enumerate(group)
            for b in group[i + 1 :]
        )
        if max_distance > config.duplicate_column_distance:
            findings.append(
                RiskFinding(
                    risk_id=ids.next(),
                    risk_type="duplicate_column_tag",
                    severity=Severity.medium,
                    message=(
                        f"Column tag {label} appears {len(group)} times, "
                        f"up to {max_distance:.0f} drawing units apart."
                    ),
                    source_entities=[e for d in group for e in d.source_entities],
                    related_detections=[d.detection_id for d in group],
                    bbox=group[0].bbox,
                    evidence=evidence_for("duplicate_column_tag_check", group[0]),
                    recommended_human_action=(
                        f"Confirm whether {label} is intentionally repeated or mislabeled."
                    ),
                )
            )

    # Rule: low-confidence detections included in takeoff.
    low_confidence = [
        d for d in detections if d.confidence < config.low_confidence_threshold
    ]
    for detection in low_confidence:
        findings.append(
            RiskFinding(
                risk_id=ids.next(),
                risk_type="low_confidence_detection_in_takeoff",
                severity=Severity.low,
                message=(
                    f"{detection.detection_type.value} detection {detection.label} has "
                    f"confidence {detection.confidence:.2f}, below "
                    f"{config.low_confidence_threshold}, but is included in the takeoff."
                ),
                source_entities=detection.source_entities,
                related_detections=[detection.detection_id],
                bbox=detection.bbox,
                evidence=evidence_for("low_confidence_takeoff_check", detection),
                recommended_human_action=(
                    f"Manually verify {detection.detection_type.value} {detection.label}."
                ),
            )
        )

    # Rule: missing or unknown drawing units.
    if quantity_report is None or quantity_report.assumed_unit == "drawing_units":
        findings.append(
            RiskFinding(
                risk_id=ids.next(),
                risk_type="unknown_drawing_units",
                severity=Severity.low,
                message=(
                    "Drawing units are unknown; all lengths and areas are reported "
                    "in raw drawing units."
                ),
                evidence=evidence_for("drawing_unit_check"),
                recommended_human_action=(
                    "Confirm the drawing scale and unit, then configure it for takeoff."
                ),
            )
        )

    # Rule: too many entities on unknown layers.
    if entities:
        layer_counts = Counter(e.layer for e in entities)
        unknown_count = sum(
            count
            for layer, count in layer_counts.items()
            if not any(hint in layer.upper() for hint in KNOWN_LAYER_HINTS)
        )
        ratio = unknown_count / len(entities)
        if (
            unknown_count >= config.unknown_layer_min_entities
            and ratio > config.unknown_layer_ratio_threshold
        ):
            findings.append(
                RiskFinding(
                    risk_id=ids.next(),
                    risk_type="unknown_layer_entities",
                    severity=Severity.low,
                    message=(
                        f"{unknown_count} of {len(entities)} entities "
                        f"({ratio:.0%}) sit on layers with no recognizable naming."
                    ),
                    evidence=evidence_for("unknown_layer_ratio_check"),
                    recommended_human_action=(
                        "Review the layer naming convention used in this drawing set."
                    ),
                )
            )

    # Rule: empty drawing after parsing.
    if manifest.source_files and not entities:
        findings.append(
            RiskFinding(
                risk_id=ids.next(),
                risk_type="empty_drawing_after_parsing",
                severity=Severity.high,
                message=(
                    f"Project {project_id} has {len(manifest.source_files)} source "
                    "file(s) but produced zero normalized entities after parsing."
                ),
                evidence=evidence_for("empty_drawing_check"),
                recommended_human_action=(
                    "Check conversion logs and DXF parse warnings for this project."
                ),
            )
        )

    report = RiskReport(
        project_id=project_id,
        findings=findings,
        counts_by_severity=dict(
            sorted(Counter(f.severity.value for f in findings).items())
        ),
    )
    log_stage(
        logger,
        "risk_report_generated",
        project_id=project_id,
        finding_count=len(findings),
        counts=report.counts_by_severity,
    )
    return report
