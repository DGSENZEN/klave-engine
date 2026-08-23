"""Review at scale: every element that feeds the presupuesto as one row —
concept, planta, measure, confidence, the doubts the engine has about it,
and the human's verdict — so an estimator can confirm or exclude hundreds
of elements in minutes instead of one click per bubble in the visor.

A *doubt* is a reason the row deserves a look before the number is trusted:
low confidence, a section or thickness that was assumed rather than read,
a cuadro mark without a section, a tablero without a type. Rows are sorted
doubts-first so the review starts where the money is least certain.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from klave_engine.costing.models import CostReport
from klave_engine.costing.reviews import ProjectReviews, review_key
from klave_engine.detection.results import Detection
from klave_engine.detection.views import SheetSegmentation

LOW_CONFIDENCE = 0.7

MEASURE_PROPERTIES = (
    ("estimated_length", "m"),
    ("estimated_span_length", "m"),
    ("estimated_area", "m²"),
    ("section_cm", "cm"),
    ("thickness_cm", "cm"),
)


class RevisionRow(BaseModel):
    key: str
    detection_id: str
    label: str
    mark: str = ""
    family: str = ""
    family_label: str = ""
    concept_code: str = ""
    concept_unit: str = ""
    view_id: str | None = None
    view_title: str = ""
    sheet: str = ""
    measure: str = ""
    confidence: float
    status: str = ""  # confirmed | excluded | ""
    note: str = ""
    actor: str = ""
    doubts: list[str] = Field(default_factory=list)
    bbox: tuple[float, float, float, float]


class RevisionTable(BaseModel):
    rows: list[RevisionRow]
    concepts: list[dict]  # code, description, unit, count
    views: list[dict]  # view_id, title, count
    total: int
    with_doubts: int
    confirmed: int
    excluded: int


def _measure(detection: Detection) -> str:
    props = detection.properties
    parts: list[str] = []
    for prop, unit in MEASURE_PROPERTIES:
        value = props.get(prop)
        if value is None or value == "":
            continue
        if isinstance(value, (int, float)):
            parts.append(f"{float(value):,.2f} {unit}")
        else:
            parts.append(f"{value} {unit}")
        if len(parts) == 2:
            break
    return " · ".join(parts)


def _doubts(detection: Detection, concept_code: str) -> list[str]:
    props = detection.properties
    doubts: list[str] = []
    if detection.confidence < LOW_CONFIDENCE:
        doubts.append(f"confianza {detection.confidence:.0%}")
    family = detection.family or ""
    if detection.detection_type.value == "column_tag" and not props.get("section_cm"):
        doubts.append("sin sección en cuadro")
    if detection.detection_type.value == "beam_tag" and not props.get("section_cm"):
        doubts.append("sin sección declarada")
    if family == "sin_tipo" or props.get("family") == "sin_tipo":
        doubts.append("tablero sin tipo de losa")
    source = str(props.get("thickness_source") or "")
    if source.startswith("etiqueta cercana"):
        doubts.append("espesor heredado")
    notes = getattr(detection.evidence, "notes", None) or []
    if any("descontar el vacío manualmente" in str(n) for n in notes):
        doubts.append("vacío sin descontar")
    if detection.detection_type.value == "wall" and props.get("estimated_thickness") is None:
        doubts.append("espesor de muro no medido")
    if concept_code == "":
        doubts.append("no entra en ningún concepto")
    return doubts


def build_revision_table(
    report: CostReport,
    detections: list[Detection],
    segmentation: SheetSegmentation | None,
    reviews: ProjectReviews,
) -> RevisionTable:
    concept_of: dict[str, tuple[str, str]] = {}
    for line in report.boq.lines:
        for det_id in line.source_detections:
            concept_of.setdefault(det_id, (line.concept_code, line.unit))
    assignment = segmentation.assignment if segmentation else {}
    titles = {v.view_id: v.title for v in segmentation.views} if segmentation else {}
    rows: list[RevisionRow] = []
    concept_counts: dict[str, int] = {}
    view_counts: dict[str, int] = {}
    for detection in detections:
        code, unit = concept_of.get(detection.detection_id, ("", ""))
        key = review_key(detection)
        review = reviews.detections.get(key)
        # Excluded elements feed no line anymore; they still belong to the
        # concept they would feed, so the reviewer can bring them back.
        if code == "" and review is not None and review.status == "excluded":
            code, unit = "", ""
        view_id = assignment.get(detection.detection_id)
        doubts = _doubts(detection, code) if review is None else []
        if code == "" and review is None:
            continue  # grid lines, intersections, cuadro labels: nothing to review for money
        rows.append(
            RevisionRow(
                key=key,
                detection_id=detection.detection_id,
                label=detection.display_label or detection.label,
                mark=detection.mark,
                family=detection.family,
                family_label=detection.family_label or detection.detection_type.value,
                concept_code=code,
                concept_unit=unit,
                view_id=view_id,
                view_title=titles.get(view_id or "", ""),
                sheet=detection.evidence.source,
                measure=_measure(detection),
                confidence=round(detection.confidence, 3),
                status=review.status if review else "",
                note=review.note if review else "",
                actor=review.actor if review else "",
                doubts=doubts,
                bbox=detection.bbox,
            )
        )
        concept_counts[code] = concept_counts.get(code, 0) + 1
        if view_id:
            view_counts[view_id] = view_counts.get(view_id, 0) + 1
    rows.sort(key=lambda r: (0 if r.doubts else 1, r.concept_code, r.view_title, r.label))
    lines = {line.concept_code: line for line in report.boq.lines}
    concepts = [
        {
            "code": code,
            "description": lines[code].description if code in lines else "Sin concepto",
            "unit": lines[code].unit if code in lines else "",
            "count": count,
        }
        for code, count in sorted(concept_counts.items())
    ]
    views = [
        {"view_id": view_id, "title": titles.get(view_id, view_id), "count": count}
        for view_id, count in sorted(view_counts.items(), key=lambda kv: titles.get(kv[0], ""))
    ]
    return RevisionTable(
        rows=rows,
        concepts=concepts,
        views=views,
        total=len(rows),
        with_doubts=sum(1 for r in rows if r.doubts),
        confirmed=sum(1 for r in rows if r.status == "confirmed"),
        excluded=sum(1 for r in rows if r.status == "excluded"),
    )
