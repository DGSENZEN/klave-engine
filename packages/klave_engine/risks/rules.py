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


MIN_GRID_LINES = 4
MAX_INDIVIDUAL_GRID_FINDINGS = 20


def _sheet_name(source: str) -> str:
    """The file a person recognises, not the converted path."""
    name = source.replace("\\", "/").rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0] if "." in name else name


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
                    f"La referencia de detalle {detail.label} está en "
                    f"{detail.evidence.source}, pero la hoja {sheet} no forma "
                    "parte del proyecto."
                ),
                source_entities=detail.source_entities,
                related_detections=[detail.detection_id],
                bbox=detail.bbox,
                evidence=evidence_for("detail_reference_manifest_lookup", detail),
                recommended_human_action=(
                    f"Confirma si la hoja {sheet} existe y agrégala al proyecto, "
                    "o corrige la referencia."
                ),
            )
        )

    # Rule: column tag with no nearby grid intersection. A sheet whose grid
    # was barely read (fewer than MIN_GRID_LINES axes in that file) would
    # flag every column: then the grid is the doubt, not the columns — and
    # past MAX_INDIVIDUAL_GRID_FINDINGS the repeats collapse into one.
    grid_by_file: dict[str, int] = {}
    for line in by_type[DetectionType.grid_line]:
        grid_by_file[line.evidence.source] = grid_by_file.get(line.evidence.source, 0) + 1
    without_grid = [
        c for c in by_type[DetectionType.column_tag]
        if not c.properties.get("has_nearby_grid", False)
        and c.properties.get("role") != "cuadro"
        and grid_by_file.get(c.evidence.source, 0) >= MIN_GRID_LINES
    ]
    poor_grid_files = {
        c.evidence.source for c in by_type[DetectionType.column_tag]
        if grid_by_file.get(c.evidence.source, 0) < MIN_GRID_LINES
    }
    for source in sorted(poor_grid_files):
        findings.append(
            RiskFinding(
                risk_id=ids.next(),
                risk_type="sparse_grid",
                severity=Severity.low,
                message=(
                    f"En {_sheet_name(source)} se leyeron {grid_by_file.get(source, 0)} ejes; "
                    "la comprobación columna–eje no aplica hasta que la malla se lea completa."
                ),
                source_entities=[],
                related_detections=[],
                bbox=None,
                evidence=evidence_for("grid_coverage_check"),
                recommended_human_action=(
                    "Revisa que los ejes estén en una capa de ejes (EJE/GRID/AXIS) con sus "
                    "burbujas; si lo están, confirma las intersecciones en el visor."
                ),
            )
        )
    if len(without_grid) > MAX_INDIVIDUAL_GRID_FINDINGS:
        findings.append(
            RiskFinding(
                risk_id=ids.next(),
                risk_type="column_tag_without_grid",
                severity=Severity.medium,
                message=(
                    f"{len(without_grid)} columnas o castillos no tienen una intersección de "
                    f"ejes cerca (p. ej. {', '.join(c.label for c in without_grid[:6])})."
                ),
                source_entities=[],
                related_detections=[c.detection_id for c in without_grid[:200]],
                bbox=None,
                evidence=evidence_for("column_grid_proximity_check"),
                recommended_human_action=(
                    "Recorre estas columnas en el visor contra los ejes estructurales; si la "
                    "malla está completa, varias pueden ser etiquetas de detalle."
                ),
            )
        )
        without_grid = []
    for column in without_grid:
        findings.append(
            RiskFinding(
                risk_id=ids.next(),
                risk_type="column_tag_without_grid",
                severity=Severity.medium,
                message=(
                    f"La columna {column.label} en {_sheet_name(column.evidence.source)} no "
                    "tiene una intersección de ejes dentro del radio de búsqueda."
                ),
                source_entities=column.source_entities,
                related_detections=[column.detection_id],
                bbox=column.bbox,
                evidence=evidence_for("column_grid_proximity_check", column),
                recommended_human_action=(
                    f"Verifica la posición de la columna {column.label} contra los "
                    "ejes estructurales."
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
                    f"La zapata {footing.label} en {footing.evidence.source} no tiene "
                    "una columna etiquetada dentro del radio de búsqueda."
                ),
                source_entities=footing.source_entities,
                related_detections=[footing.detection_id],
                bbox=footing.bbox,
                evidence=evidence_for("footing_column_proximity_check", footing),
                recommended_human_action=(
                    f"Revisa si la zapata {footing.label} soporta una columna sin "
                    "etiqueta."
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
                        f"La etiqueta de columna {label} aparece {len(group)} veces, "
                        f"con separaciones de hasta {max_distance:.0f} unidades de "
                        "dibujo."
                    ),
                    source_entities=[e for d in group for e in d.source_entities],
                    related_detections=[d.detection_id for d in group],
                    bbox=group[0].bbox,
                    evidence=evidence_for("duplicate_column_tag_check", group[0]),
                    recommended_human_action=(
                        f"Confirma si {label} se repite a propósito o está mal "
                        "etiquetada."
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
                    f"La detección {detection.label} ({detection.detection_type.value}) "
                    f"tiene confianza {detection.confidence:.2f}, por debajo de "
                    f"{config.low_confidence_threshold}, pero forma parte de la "
                    "cuantificación."
                ),
                source_entities=detection.source_entities,
                related_detections=[detection.detection_id],
                bbox=detection.bbox,
                evidence=evidence_for("low_confidence_takeoff_check", detection),
                recommended_human_action=(
                    f"Verifica manualmente {detection.label} en el visor y confírmala "
                    "o exclúyela."
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
                    "No se pudieron determinar las unidades del plano; longitudes y "
                    "áreas se reportan en unidades de dibujo."
                ),
                evidence=evidence_for("drawing_unit_check"),
                recommended_human_action=(
                    "Confirma la escala y unidad del plano y configúralas para la "
                    "cuantificación."
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
                        f"{unknown_count} de {len(entities)} entidades ({ratio:.0%}) "
                        "están en capas sin una nomenclatura reconocible."
                    ),
                    evidence=evidence_for("unknown_layer_ratio_check"),
                    recommended_human_action=(
                        "Revisa la convención de nombres de capas de este juego de "
                        "planos."
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
                    f"El proyecto tiene {len(manifest.source_files)} archivo(s) fuente "
                    "pero la lectura no produjo ninguna entidad."
                ),
                evidence=evidence_for("empty_drawing_check"),
                recommended_human_action=(
                    "Revisa la Lectura del Plano: estado de conversión y avisos de "
                    "lectura de este proyecto."
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
