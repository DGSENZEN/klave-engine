"""Synthetic detections from the engineer's levantamiento of missed elements.

A recall failure the engineer catches must not die as a note: an
``OmittedElement`` becomes one ``Detection`` per instance, with confidence
1.0 (a human counted it on the plano), method ``levantamiento_manual`` and
the engineer's note as evidence. Downstream — BoQ, generadores, exports —
treats them like any reading, so the presupuesto shows exactly where a
quantity came from a person instead of the engine.

Measured magnitudes arrive in meters and are stored as drawing-unit
properties (what the quantity rules read), so they are converted with the
project's current unit factor on every recompute; confirming units later
re-derives them, never bakes a stale factor in.
"""

from klave_engine.costing.reviews import OmittedElement
from klave_engine.detection.results import Detection, DetectionType
from klave_engine.detection.taxonomy import FAMILY_INFO, Family
from klave_engine.graph.evidence import EvidencePacket

# The families an engineer can record by hand, and the detection type whose
# quantity rules will consume them. Continuous families carry a measured
# magnitude; count-only families need just the count.
FAMILY_TYPES: dict[str, DetectionType] = {
    "castillo": DetectionType.column_tag,
    "columna": DetectionType.column_tag,
    "trabe": DetectionType.beam_tag,
    "contratrabe": DetectionType.beam_tag,
    "dala": DetectionType.beam_tag,
    "cerramiento": DetectionType.beam_tag,
    "zapata": DetectionType.footing,
    "pilote": DetectionType.pile,
    "muro": DetectionType.wall,
    "muro_concreto": DetectionType.wall,
    "losa": DetectionType.slab_region,
    "escalera": DetectionType.stair,
}
LINEAR_FAMILIES = {"trabe", "contratrabe", "dala", "cerramiento", "muro", "muro_concreto"}
AREA_FAMILIES = {"zapata", "losa", "escalera"}


def _properties(element: OmittedElement, unit_to_m: float) -> dict:
    """Drawing-unit properties the family's quantity rules read. The length
    or area is split evenly across the element's instances so the total is
    what the engineer measured, however many pieces carry it."""
    properties: dict = {"family": element.family}
    if element.section_cm:
        properties["section_cm"] = element.section_cm
    if element.family in LINEAR_FAMILIES and element.length_m:
        per_piece = element.length_m / element.count / unit_to_m
        key = "estimated_length" if element.family.startswith("muro") else "estimated_span_length"
        properties[key] = per_piece
    if element.family in AREA_FAMILIES and element.area_m2:
        properties["estimated_area"] = element.area_m2 / element.count / unit_to_m**2
    if element.family == "muro_concreto":
        properties["wall_kind"] = "concreto"
    if element.family == "losa":
        properties["family"] = "losa"  # matches the generic slab rule filter
    if element.family == "pilote" and element.length_m:
        properties["length_m"] = element.length_m / element.count
    return properties


def synthetic_detections(
    omitted: list[OmittedElement], unit_to_m: float | None
) -> list[Detection]:
    """One detection per recorded instance; unknown families are skipped
    (the API validates them, but reviews files travel between versions)."""
    factor = unit_to_m if unit_to_m else 1.0  # SIN UNIDADES: same posture as the BoQ
    detections: list[Detection] = []
    for element in omitted:
        detection_type = FAMILY_TYPES.get(element.family)
        if detection_type is None:
            continue
        try:
            info = FAMILY_INFO[Family(element.family)]
            family_label = info.label
        except (KeyError, ValueError):
            family_label = element.family
        properties = _properties(element, factor)
        for ordinal in range(1, element.count + 1):
            suffix = f"-{ordinal:02d}" if element.count > 1 else ""
            name = element.mark or family_label
            detections.append(
                Detection(
                    detection_id=f"omitido_{element.element_id}_{ordinal}",
                    detection_type=detection_type,
                    label=element.mark or family_label,
                    bbox=(0.0, 0.0, 0.0, 0.0),
                    source_entities=[],
                    confidence=1.0,
                    evidence=EvidencePacket(
                        source=element.sheet,
                        method="levantamiento_manual",
                        entity_ids=[],
                        bbox=(0.0, 0.0, 0.0, 0.0),
                        confidence=1.0,
                        notes=[
                            "Elemento omitido por el motor, agregado por "
                            + (element.actor or "el ingeniero")
                            + (f": {element.note}" if element.note else ""),
                        ],
                    ),
                    properties=dict(properties),
                    mark=element.mark,
                    family=element.family,
                    family_label=family_label,
                    display_label=f"OM-{name}{suffix}",
                    description=(
                        f"{family_label} {element.mark}".strip()
                        + " · levantamiento manual del ingeniero (omitido por el motor)"
                    ),
                )
            )
    return detections
