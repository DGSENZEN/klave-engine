"""Concept catalog (catálogo de conceptos) with detection→quantity rules.

Each concept declares which detections feed it and how the raw measured
quantity (count, meters, m²) becomes the concept unit, with the geometric
assumptions made explicit.
"""

from klave_engine.costing.models import (
    Concept,
    CostingAssumptions,
    QuantityKind,
    QuantityRule,
    ViewScope,
)
from klave_engine.detection.results import DetectionType

PHASE_ORDER = ["Preliminares", "Cimentación", "Estructura"]


def build_default_catalog(a: CostingAssumptions) -> list[Concept]:
    footing_volume = a.footing_depth_m
    return [
        Concept(
            code="PRE-001",
            description="Trazo y nivelación del terreno con equipo topográfico",
            unit="M2",
            phase="Preliminares",
            rule=QuantityRule(
                detection_type=DetectionType.slab_region,
                kind=QuantityKind.AREA,
                source_property="estimated_area",
            ),
            quantity_factor=1.0,
            view_scope=ViewScope.FOOTPRINT_ONCE,
            assumptions=["Superficie de trabajo aproximada por el área de losas detectada"],
            production_rate_per_day=200.0,
            sequence_order=0,
        ),
        Concept(
            code="CIM-001",
            description="Excavación estructural para cimentación por medios mecánicos",
            unit="M3",
            phase="Cimentación",
            rule=QuantityRule(
                detection_type=DetectionType.footing,
                kind=QuantityKind.AREA,
                source_property="estimated_area",
            ),
            quantity_factor=a.excavation_depth_m * a.excavation_swell_factor,
            view_scope=ViewScope.FOUNDATION_ONLY,
            assumptions=[
                f"Profundidad de excavación {a.excavation_depth_m:.2f} m",
                f"Factor de abundamiento {a.excavation_swell_factor:.2f}",
            ],
            production_rate_per_day=18.0,
            sequence_order=0,
        ),
        Concept(
            code="CIM-002",
            description=(
                "Concreto f'c=250 kg/cm² en zapatas y dados, incluye acero, "
                "cimbra y plantilla"
            ),
            unit="M3",
            phase="Cimentación",
            rule=QuantityRule(
                detection_type=DetectionType.footing,
                kind=QuantityKind.AREA,
                source_property="estimated_area",
            ),
            quantity_factor=footing_volume,
            view_scope=ViewScope.FOUNDATION_ONLY,
            assumptions=[f"Peralte promedio de zapata/dado {a.footing_depth_m:.2f} m"],
            production_rate_per_day=5.0,
            sequence_order=1,
        ),
        Concept(
            code="EST-001",
            description="Columnas y castillos de concreto armado f'c=250 kg/cm²",
            unit="M3",
            phase="Estructura",
            rule=QuantityRule(
                detection_type=DetectionType.column_tag,
                kind=QuantityKind.COUNT,
            ),
            quantity_factor=a.column_section_m2 * a.column_height_m,
            view_scope=ViewScope.COLUMN_VOLUME,
            assumptions=[
                f"Sección promedio {a.column_section_m2:.3f} m² (si no hay marcador medible)",
                f"Altura de entrepiso {a.column_height_m:.2f} m (si no hay niveles N.P.T.)",
            ],
            production_rate_per_day=3.0,
            sequence_order=0,
        ),
        Concept(
            code="EST-002",
            description="Trabes y contratrabes de concreto armado f'c=250 kg/cm²",
            unit="M3",
            phase="Estructura",
            rule=QuantityRule(
                detection_type=DetectionType.beam_tag,
                kind=QuantityKind.LENGTH,
                source_property="estimated_span_length",
            ),
            quantity_factor=a.beam_section_m2,
            view_scope=ViewScope.SUPERSTRUCTURE_SUM,
            assumptions=[f"Sección promedio de trabe {a.beam_section_m2:.4f} m²"],
            production_rate_per_day=4.0,
            sequence_order=1,
        ),
        Concept(
            code="EST-003",
            description="Losa de concreto armado (sistema nervado o equivalente)",
            unit="M2",
            phase="Estructura",
            rule=QuantityRule(
                detection_type=DetectionType.slab_region,
                kind=QuantityKind.AREA,
                source_property="estimated_area",
            ),
            quantity_factor=1.0,
            view_scope=ViewScope.SUPERSTRUCTURE_SUM,
            assumptions=["Área medida de regiones de losa detectadas (suma por nivel)"],
            production_rate_per_day=35.0,
            sequence_order=2,
        ),
        Concept(
            code="EST-004",
            description="Muros de block/concreto, incluye refuerzo y mortero",
            unit="M2",
            phase="Estructura",
            rule=QuantityRule(
                detection_type=DetectionType.wall,
                kind=QuantityKind.LENGTH,
                source_property="estimated_length",
            ),
            quantity_factor=a.wall_height_m,
            view_scope=ViewScope.SUPERSTRUCTURE_SUM,
            assumptions=[f"Altura promedio de muro {a.wall_height_m:.2f} m"],
            production_rate_per_day=14.0,
            sequence_order=3,
        ),
    ]
