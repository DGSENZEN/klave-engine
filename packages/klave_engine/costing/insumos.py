"""Reference resource catalog (insumos) and APU templates.

PRECIOS DE REFERENCIA, NO DE MERCADO: these are editable baseline values in
MXN intended to make the workflow runnable end-to-end. Replace them with
project-specific quotations before using any output contractually.
"""

from klave_engine.costing.models import Resource, ResourceType

REFERENCE_PRICE_DISCLAIMER = (
    "Precios de insumos de referencia (MXN); deben sustituirse por "
    "cotizaciones vigentes del proyecto."
)

RESOURCES: dict[str, Resource] = {
    r.code: r
    for r in [
        Resource(
            code="MAT-CONC250",
            description="Concreto premezclado f'c=250 kg/cm²",
            unit="M3",
            unit_cost=2650.0,
            resource_type=ResourceType.material,
        ),
        Resource(
            code="MAT-ACERO",
            description="Acero de refuerzo fy=4200 habilitado y armado",
            unit="TON",
            unit_cost=26500.0,
            resource_type=ResourceType.material,
        ),
        Resource(
            code="MAT-CIMBRA",
            description="Cimbra de contacto en madera (4 usos)",
            unit="M2",
            unit_cost=210.0,
            resource_type=ResourceType.material,
        ),
        Resource(
            code="MAT-PLANTILLA",
            description="Plantilla de concreto f'c=100 kg/cm²",
            unit="M3",
            unit_cost=1450.0,
            resource_type=ResourceType.material,
        ),
        Resource(
            code="MAT-BLOCK",
            description="Block de concreto 15x20x40 incl. desperdicio",
            unit="M2",
            unit_cost=185.0,
            resource_type=ResourceType.material,
        ),
        Resource(
            code="MAT-MORTERO",
            description="Mortero cemento-arena 1:4",
            unit="M3",
            unit_cost=1850.0,
            resource_type=ResourceType.material,
        ),
        Resource(
            code="MO-CUAD-ALB",
            description="Cuadrilla de albañilería (1 oficial + 1 ayudante)",
            unit="JOR",
            unit_cost=1750.0,
            resource_type=ResourceType.labor,
        ),
        Resource(
            code="MO-CUAD-FIE",
            description="Cuadrilla de fierrero (1 oficial + 1 ayudante)",
            unit="JOR",
            unit_cost=1820.0,
            resource_type=ResourceType.labor,
        ),
        Resource(
            code="MO-CUAD-CARP",
            description="Cuadrilla de carpintería de obra negra",
            unit="JOR",
            unit_cost=1780.0,
            resource_type=ResourceType.labor,
        ),
        Resource(
            code="MO-PEON",
            description="Peón",
            unit="JOR",
            unit_cost=620.0,
            resource_type=ResourceType.labor,
        ),
        Resource(
            code="EQ-REVOLVEDORA",
            description="Revolvedora de 1 saco",
            unit="JOR",
            unit_cost=380.0,
            resource_type=ResourceType.equipment,
        ),
        Resource(
            code="EQ-VIBRADOR",
            description="Vibrador para concreto",
            unit="JOR",
            unit_cost=290.0,
            resource_type=ResourceType.equipment,
        ),
        Resource(
            code="EQ-RETRO",
            description="Retroexcavadora 415F",
            unit="HR",
            unit_cost=720.0,
            resource_type=ResourceType.equipment,
        ),
        Resource(
            code="EQ-TOPOGRAFIA",
            description="Equipo de topografía con operador",
            unit="JOR",
            unit_cost=850.0,
            resource_type=ResourceType.equipment,
        ),
        Resource(
            code="EQ-HERRAMIENTA",
            description="Herramienta menor (% de mano de obra)",
            unit="%MO",
            unit_cost=0.03,
            resource_type=ResourceType.equipment,
            is_labor_percentage=True,
        ),
    ]
}

# Quantities of each resource consumed per ONE unit of the concept.
APU_TEMPLATES: dict[str, list[tuple[str, float]]] = {
    # M2 trazo y nivelación
    "PRE-001": [
        ("MO-PEON", 0.020),
        ("EQ-TOPOGRAFIA", 0.005),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M3 excavación estructural
    "CIM-001": [
        ("MO-PEON", 0.180),
        ("EQ-RETRO", 0.090),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M3 concreto en zapatas y dados
    "CIM-002": [
        ("MAT-CONC250", 1.05),
        ("MAT-ACERO", 0.075),
        ("MAT-CIMBRA", 1.20),
        ("MAT-PLANTILLA", 0.080),
        ("MO-CUAD-ALB", 0.45),
        ("MO-CUAD-FIE", 0.35),
        ("EQ-VIBRADOR", 0.12),
        ("EQ-REVOLVEDORA", 0.08),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M3 columnas y castillos
    "EST-001": [
        ("MAT-CONC250", 1.05),
        ("MAT-ACERO", 0.160),
        ("MAT-CIMBRA", 9.00),
        ("MO-CUAD-ALB", 0.90),
        ("MO-CUAD-FIE", 0.70),
        ("MO-CUAD-CARP", 0.80),
        ("EQ-VIBRADOR", 0.25),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M3 trabes y contratrabes
    "EST-002": [
        ("MAT-CONC250", 1.05),
        ("MAT-ACERO", 0.140),
        ("MAT-CIMBRA", 6.50),
        ("MO-CUAD-ALB", 0.75),
        ("MO-CUAD-FIE", 0.60),
        ("MO-CUAD-CARP", 0.65),
        ("EQ-VIBRADOR", 0.20),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M2 losa (sistema nervado / maciza equivalente)
    "EST-003": [
        ("MAT-CONC250", 0.110),
        ("MAT-ACERO", 0.0085),
        ("MAT-CIMBRA", 1.05),
        ("MO-CUAD-ALB", 0.120),
        ("MO-CUAD-CARP", 0.100),
        ("EQ-VIBRADOR", 0.020),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M2 muros
    "EST-004": [
        ("MAT-BLOCK", 1.00),
        ("MAT-MORTERO", 0.020),
        ("MAT-ACERO", 0.0035),
        ("MO-CUAD-ALB", 0.150),
        ("EQ-HERRAMIENTA", 1.0),
    ],
}
