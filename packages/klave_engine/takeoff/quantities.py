"""Approximate quantity takeoff from detections. Every number carries provenance."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from klave_engine.common.logging import get_logger, log_stage
from klave_engine.detection.results import Detection, DetectionType
from klave_engine.takeoff.units import UNKNOWN_UNIT_ASSUMPTION

logger = get_logger(__name__)

LOW_CONFIDENCE_THRESHOLD = 0.7


class QuantityItem(BaseModel):
    name: str
    value: float
    unit: str
    confidence: float
    source_detections: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class QuantityReport(BaseModel):
    project_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    assumed_unit: str = "drawing_units"
    low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD
    items: list[QuantityItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _of_type(detections: list[Detection], detection_type: DetectionType) -> list[Detection]:
    return [d for d in detections if d.detection_type == detection_type]


def _mean_confidence(detections: list[Detection]) -> float:
    if not detections:
        return 1.0
    return sum(d.confidence for d in detections) / len(detections)


def _count_item(name: str, detections: list[Detection]) -> QuantityItem:
    return QuantityItem(
        name=name,
        value=float(len(detections)),
        unit="count",
        confidence=_mean_confidence(detections),
        source_detections=[d.detection_id for d in detections],
    )


def _sum_item(
    name: str, detections: list[Detection], property_name: str, unit: str
) -> QuantityItem:
    contributing = [d for d in detections if property_name in d.properties]
    missing = [d for d in detections if property_name not in d.properties]
    item = QuantityItem(
        name=name,
        value=round(sum(float(d.properties[property_name]) for d in contributing), 3),
        unit=unit,
        confidence=_mean_confidence(contributing),
        source_detections=[d.detection_id for d in contributing],
        assumptions=[UNKNOWN_UNIT_ASSUMPTION],
    )
    if missing:
        item.warnings.append(
            f"{len(missing)} detection(s) had no '{property_name}' and were excluded"
        )
    return item


def generate_quantity_report(
    project_id: str,
    detections: list[Detection],
    assumed_unit: str = "drawing_units",
    low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
) -> QuantityReport:
    report = QuantityReport(
        project_id=project_id,
        assumed_unit=assumed_unit,
        low_confidence_threshold=low_confidence_threshold,
    )
    length_unit = assumed_unit
    area_unit = f"{assumed_unit}^2"

    columns = _of_type(detections, DetectionType.column_tag)
    footings = _of_type(detections, DetectionType.footing)
    beams = _of_type(detections, DetectionType.beam_tag)
    walls = _of_type(detections, DetectionType.wall)
    slabs = _of_type(detections, DetectionType.slab_region)
    details = _of_type(detections, DetectionType.detail_reference)
    unresolved = [d for d in details if not d.properties.get("resolved", False)]
    low_confidence = [d for d in detections if d.confidence < low_confidence_threshold]

    report.items = [
        _count_item("column_tag_count", columns),
        _count_item("footing_count", footings),
        _count_item("beam_tag_count", beams),
        _sum_item("estimated_beam_length", beams, "estimated_span_length", length_unit),
        _count_item("wall_count", walls),
        _sum_item("estimated_wall_length", walls, "estimated_length", length_unit),
        _count_item("slab_region_count", slabs),
        _sum_item("estimated_slab_area", slabs, "estimated_area", area_unit),
        _count_item("detail_reference_count", details),
        _count_item("unresolved_detail_reference_count", unresolved),
        _count_item("low_confidence_detection_count", low_confidence),
    ]
    if low_confidence:
        report.warnings.append(
            f"{len(low_confidence)} detection(s) below confidence "
            f"{low_confidence_threshold} are included in counts"
        )

    log_stage(
        logger,
        "takeoff_report_generated",
        project_id=project_id,
        item_count=len(report.items),
        warning_count=len(report.warnings),
    )
    return report
