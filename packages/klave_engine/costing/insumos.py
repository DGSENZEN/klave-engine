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

def default_price_book() -> dict[str, "Resource"]:
    """A fresh, mutable copy of the reference insumos (so edits never leak)."""
    return {code: resource.model_copy(deep=True) for code, resource in RESOURCES.items()}


def apply_price_overrides(
    book: dict[str, "Resource"], overrides: dict[str, float]
) -> dict[str, "Resource"]:
    """Override unit costs by resource code (descriptions/units unchanged)."""
    for code, unit_cost in overrides.items():
        if code in book:
            book[code] = book[code].model_copy(update={"unit_cost": float(unit_cost)})
    return book


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
RESOURCES.update(
    {
        r.code: r
        for r in [
            Resource(
                code="MAT-VIGUETA",
                description="Vigueta pretensada de 13 cm (referencia)",
                unit="M",
                unit_cost=98.0,
                resource_type=ResourceType.material,
            ),
            Resource(
                code="MAT-BOVEDILLA",
                description="Bovedilla de cemento-arena 15×25×56 cm (referencia)",
                unit="PZA",
                unit_cost=24.0,
                resource_type=ResourceType.material,
            ),
        ]
    }
)

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
    # M cadena/dala 15x20: 0.033 m³ of concrete per metre, hand-laid cimbra
    "EST-005": [
        ("MAT-CONC250", 0.033),
        ("MAT-ACERO", 0.0045),
        ("MAT-CIMBRA", 0.42),
        ("MO-CUAD-ALB", 0.035),
        ("MO-CUAD-FIE", 0.020),
        ("MO-CUAD-CARP", 0.030),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M3 muro de concreto armado: two-sided cimbra
    "EST-014": [
        ("MAT-CONC250", 1.05),
        ("MAT-ACERO", 0.090),
        ("MAT-CIMBRA", 10.00),
        ("MO-CUAD-ALB", 0.80),
        ("MO-CUAD-FIE", 0.50),
        ("MO-CUAD-CARP", 0.90),
        ("EQ-VIBRADOR", 0.20),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M3 contratrabe: same matrix as a trabe without obra falsa
    "CIM-008": [
        ("MAT-CONC250", 1.05),
        ("MAT-ACERO", 0.120),
        ("MAT-CIMBRA", 5.00),
        ("MO-CUAD-ALB", 0.70),
        ("MO-CUAD-FIE", 0.55),
        ("MO-CUAD-CARP", 0.50),
        ("EQ-VIBRADOR", 0.20),
        ("EQ-HERRAMIENTA", 1.0),
    ],
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
    # M2 losa de vigueta y bovedilla: 1.45 m de vigueta y 7 bovedillas por
    # m² (separación 70 cm), capa de compresión de 5 cm; la malla va en ACE-005
    "EST-012": [
        ("MAT-VIGUETA", 1.45),
        ("MAT-BOVEDILLA", 7.0),
        ("MAT-CONC250", 0.065),
        ("MO-CUAD-ALB", 0.090),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M3 losa maciza: concreto con desperdicio; acero por detalle, cimbra en EST-011
    "EST-013": [
        ("MAT-CONC250", 1.05),
        ("MO-CUAD-ALB", 0.900),
        ("EQ-VIBRADOR", 0.150),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M3 losa de cimentación: concreto con desperdicio; acero por detalle
    "CIM-007": [
        ("MAT-CONC250", 1.05),
        ("MO-CUAD-ALB", 0.850),
        ("EQ-VIBRADOR", 0.150),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M2 losa reticular aligerada (nervada)
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
