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


def build_catalog_from_store(
    rows: list[dict], assumptions: CostingAssumptions
) -> list[Concept]:
    """Concepts from the workspace database.

    A row with a ``rule_key`` binds to the built-in detection rule of that
    key (rule, quantity factor, view scope, and calibrated assumptions come
    from code); its description, unit, phase, and rendimiento are the user's.
    A row without one is a manual concept: priced by its APU, quantified only
    through documented adjustments.
    """
    specs = {concept.code: concept for concept in build_default_catalog(assumptions)}
    catalog: list[Concept] = []
    for index, row in enumerate(rows):
        base = specs.get(row.get("rule_key") or "")
        if base is not None:
            catalog.append(
                base.model_copy(
                    update={
                        "code": row["code"],
                        "description": row["description"],
                        "unit": row["unit"],
                        "phase": row["phase"],
                        "production_rate_per_day": row["production_rate_per_day"],
                        "sequence_order": int(row.get("sequence_order", index)),
                    }
                )
            )
        else:
            catalog.append(
                Concept(
                    code=row["code"],
                    description=row["description"],
                    unit=row["unit"],
                    phase=row["phase"],
                    rule=None,
                    production_rate_per_day=row["production_rate_per_day"],
                    sequence_order=int(row.get("sequence_order", index)),
                    assumptions=["Cantidad por levantamiento manual documentado"],
                )
            )
    return catalog


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
            code="CIM-007",
            description="Losa de cimentación de concreto armado f'c=250 kg/cm²",
            unit="M3",
            phase="Cimentación",
            rule=QuantityRule(
                detection_type=DetectionType.slab_region,
                kind=QuantityKind.VOLUME,
                source_property="estimated_area",
                property_filter={"family": ["cimentacion"]},
                thickness_property="thickness_cm",
                default_thickness_m=a.mat_thickness_m,
            ),
            quantity_factor=1.0,
            view_scope=ViewScope.FOUNDATION_ONLY,
            assumptions=[
                f"Área de tableros de losa de cimentación × H= del plano (o "
                f"{a.mat_thickness_m:.2f} m si no lo declara)"
            ],
            production_rate_per_day=12.0,
            sequence_order=1,
        ),
        Concept(
            code="CIM-010",
            description="Pilote de concreto colado en sitio (longitud según proyecto)",
            unit="PZA",
            phase="Cimentación",
            rule=QuantityRule(detection_type=DetectionType.pile, kind=QuantityKind.COUNT),
            quantity_factor=1.0,
            view_scope=ViewScope.FOUNDATION_ONLY,
            assumptions=[
                "Pilotes contados por marca en la planta de cimentación; diámetro del círculo, "
                "longitud por notas/detalle. Precio por pieza a adoptar del catálogo."
            ],
            production_rate_per_day=3.0,
            sequence_order=0,
        ),
        Concept(
            code="CIM-008",
            description="Contratrabes de concreto armado f'c=250 kg/cm²",
            unit="M3",
            phase="Cimentación",
            rule=QuantityRule(
                detection_type=DetectionType.beam_tag,
                kind=QuantityKind.LINEAR_VOLUME,
                source_property="estimated_span_length",
                property_filter={"role": [None, "plan"], "family": ["contratrabe"]},
                section_property="section_area_du2",
                default_section_m2=a.contratrabe_section_m2,
            ),
            quantity_factor=1.0,
            view_scope=ViewScope.FOUNDATION_ONLY,
            assumptions=[
                "Claro de cada contratrabe × su sección: la del detalle/cota del plano, "
                f"o {a.contratrabe_section_m2:.3f} m² si el plano no la declara"
            ],
            production_rate_per_day=4.0,
            sequence_order=2,
        ),
        Concept(
            code="EST-001",
            description="Columnas y castillos de concreto armado f'c=250 kg/cm²",
            unit="M3",
            phase="Estructura",
            rule=QuantityRule(
                detection_type=DetectionType.column_tag,
                kind=QuantityKind.COUNT,
                property_filter={"role": [None, "plan"]},
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
            description="Trabes de concreto armado f'c=250 kg/cm²",
            unit="M3",
            phase="Estructura",
            rule=QuantityRule(
                detection_type=DetectionType.beam_tag,
                kind=QuantityKind.LINEAR_VOLUME,
                source_property="estimated_span_length",
                property_filter={"role": [None, "plan"], "family": [None, "trabe"]},
                section_property="section_area_du2",
                default_section_m2=a.beam_section_m2,
            ),
            quantity_factor=1.0,
            view_scope=ViewScope.SUPERSTRUCTURE_SUM,
            assumptions=[
                "Claro de cada trabe × su sección: la del cuadro/detalle/cota del plano, "
                f"o {a.beam_section_m2:.4f} m² si el plano no la declara"
            ],
            production_rate_per_day=4.0,
            sequence_order=1,
        ),
        Concept(
            code="EST-005",
            description="Cadena o dala de concreto armado 15x20 cm",
            unit="M",
            phase="Estructura",
            rule=QuantityRule(
                detection_type=DetectionType.beam_tag,
                kind=QuantityKind.LENGTH,
                source_property="estimated_span_length",
                property_filter={"role": [None, "plan"], "family": ["dala", "cerramiento"]},
            ),
            quantity_factor=1.0,
            view_scope=ViewScope.SUPERSTRUCTURE_SUM,
            assumptions=[
                "Metros de dalas y cerramientos marcados en planta (CE-n, CR-n, DL-n); la "
                "sección declarada en notas (p. ej. «CADENA DE ENRASE 15x25») manda sobre la "
                "matriz, revísala"
            ],
            production_rate_per_day=6.0,
            sequence_order=3,
        ),
        Concept(
            code="EST-014",
            description="Muros de concreto armado f'c=250 kg/cm²",
            unit="M3",
            phase="Estructura",
            rule=QuantityRule(
                detection_type=DetectionType.wall,
                kind=QuantityKind.LINEAR_VOLUME,
                source_property="estimated_length",
                property_filter={"wall_kind": ["concreto"]},
                section_property="estimated_thickness",
                section_height_m=a.wall_height_m,
                default_section_m2=0.20 * a.wall_height_m,
                height_from_levels=True,
            ),
            quantity_factor=1.0,
            view_scope=ViewScope.SUPERSTRUCTURE_SUM,
            assumptions=[
                f"Longitud × espesor medido × altura {a.wall_height_m:.2f} m en muros de la "
                "capa de concreto (MC); espesor supuesto 0.20 m si no se mide"
            ],
            production_rate_per_day=6.0,
            sequence_order=3,
        ),
        Concept(
            code="EST-003",
            description="Losa reticular aligerada (nervada) de concreto armado f'c=250 kg/cm², "
            "incluye casetón",
            unit="M2",
            phase="Estructura",
            rule=QuantityRule(
                detection_type=DetectionType.slab_region,
                kind=QuantityKind.AREA,
                source_property="estimated_area",
                property_filter={"family": [None, "reticular", "sin_tipo", "losa"]},
            ),
            quantity_factor=1.0,
            view_scope=ViewScope.SUPERSTRUCTURE_SUM,
            assumptions=[
                "Área de tableros reticulares (y de losas sin sistema declarado) por nivel"
            ],
            production_rate_per_day=35.0,
            sequence_order=2,
        ),
        Concept(
            code="EST-012",
            description="Losa de vigueta y bovedilla, incluye capa de compresión de 5 cm "
            "f'c=250 kg/cm²",
            unit="M2",
            phase="Estructura",
            rule=QuantityRule(
                detection_type=DetectionType.slab_region,
                kind=QuantityKind.AREA,
                source_property="estimated_area",
                property_filter={"family": ["vigueta_bovedilla"]},
            ),
            quantity_factor=1.0,
            view_scope=ViewScope.SUPERSTRUCTURE_SUM,
            assumptions=["Área de tableros de vigueta y bovedilla por nivel"],
            production_rate_per_day=60.0,
            sequence_order=2,
        ),
        Concept(
            code="EST-013",
            description="Losa maciza de concreto armado f'c=250 kg/cm²",
            unit="M3",
            phase="Estructura",
            rule=QuantityRule(
                detection_type=DetectionType.slab_region,
                kind=QuantityKind.VOLUME,
                source_property="estimated_area",
                property_filter={"family": ["maciza"]},
                thickness_property="thickness_cm",
                default_thickness_m=a.slab_thickness_m,
            ),
            quantity_factor=1.0,
            view_scope=ViewScope.SUPERSTRUCTURE_SUM,
            assumptions=[
                f"Área de tableros macizos × espesor H= del plano (o {a.slab_thickness_m:.2f} m "
                "si no lo declara)"
            ],
            production_rate_per_day=8.0,
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
                property_filter={"wall_kind": [None, "block"]},
                height_from_levels=True,
            ),
            quantity_factor=a.wall_height_m,
            view_scope=ViewScope.SUPERSTRUCTURE_SUM,
            assumptions=[f"Altura promedio de muro {a.wall_height_m:.2f} m"],
            production_rate_per_day=14.0,
            sequence_order=3,
        ),
    ]
