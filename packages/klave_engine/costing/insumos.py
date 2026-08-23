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

RESOURCES.update(
    {
        r.code: r
        for r in [
            Resource(
                code="EQ-MOTOCONFORMADORA",
                description="Motoconformadora 140 HP, costo horario (referencia SICT)",
                unit="HORA",
                unit_cost=1650.0,
                resource_type=ResourceType.equipment,
            ),
            Resource(
                code="EQ-VIBROCOMPACTADOR",
                description="Vibrocompactador liso 10 t, costo horario (referencia SICT)",
                unit="HORA",
                unit_cost=1100.0,
                resource_type=ResourceType.equipment,
            ),
            Resource(
                code="EQ-CAMION",
                description="Camión volteo 14 m³, costo horario (referencia SICT)",
                unit="HORA",
                unit_cost=780.0,
                resource_type=ResourceType.equipment,
            ),
            Resource(
                code="EQ-PIPA",
                description="Pipa de agua 10 000 L, costo horario (referencia)",
                unit="HORA",
                unit_cost=650.0,
                resource_type=ResourceType.equipment,
            ),
            Resource(
                code="EQ-PERFORADORA",
                description="Perforadora rotatoria para pilotes Ø60–120 cm, costo horario "
                "(referencia SICT)",
                unit="HORA",
                unit_cost=2850.0,
                resource_type=ResourceType.equipment,
            ),
            Resource(
                code="MAT-AGUA",
                description="Agua para obra",
                unit="M3",
                unit_cost=35.0,
                resource_type=ResourceType.material,
            ),
            Resource(
                code="MAT-TEPETATE",
                description="Tepetate de banco puesto en obra (referencia)",
                unit="M3",
                unit_cost=260.0,
                resource_type=ResourceType.material,
            ),
            Resource(
                code="MAT-CONC150",
                description="Concreto hecho en obra f'c=150 kg/cm²",
                unit="M3",
                unit_cost=2100.0,
                resource_type=ResourceType.material,
            ),
            Resource(
                code="MAT-PINTURA",
                description="Pintura vinílica acrílica, cubeta 19 L (referencia)",
                unit="L",
                unit_cost=78.0,
                resource_type=ResourceType.material,
            ),
            Resource(
                code="MAT-SELLADOR",
                description="Sellador vinílico 5×1 (referencia)",
                unit="L",
                unit_cost=32.0,
                resource_type=ResourceType.material,
            ),
            Resource(
                code="MAT-PISO-CER",
                description="Loseta cerámica 60×60 cm tráfico residencial (referencia)",
                unit="M2",
                unit_cost=185.0,
                resource_type=ResourceType.material,
            ),
            Resource(
                code="MAT-ADHESIVO",
                description="Adhesivo para loseta base cemento, saco 20 kg (referencia)",
                unit="KG",
                unit_cost=9.5,
                resource_type=ResourceType.material,
            ),
            Resource(
                code="MAT-YESO",
                description="Yeso para construcción, saco 40 kg (referencia)",
                unit="KG",
                unit_cost=4.2,
                resource_type=ResourceType.material,
            ),
            Resource(
                code="MO-PINTOR",
                description="Pintor (cuadrilla pintor + ayudante, salario real)",
                unit="JOR",
                unit_cost=1180.0,
                resource_type=ResourceType.labor,
            ),
            Resource(
                code="MO-YESERO",
                description="Yesero (cuadrilla yesero + ayudante, salario real)",
                unit="JOR",
                unit_cost=1260.0,
                resource_type=ResourceType.labor,
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
    # M3 concreto en zapatas y dados — solo el concreto y su colado: el
    # acero va en ACE-003, la cimbra en CIM-006 y la plantilla en CIM-003,
    # cada uno con su propia cantidad leída del plano.
    "CIM-002": [
        ("MAT-CONC250", 1.05),
        ("MO-CUAD-ALB", 0.45),
        ("EQ-VIBRADOR", 0.12),
        ("EQ-REVOLVEDORA", 0.08),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M3 columnas y castillos — concreto y colado; acero en ACE-001, cimbra en EST-008
    "EST-001": [
        ("MAT-CONC250", 1.05),
        ("MO-CUAD-ALB", 0.90),
        ("EQ-VIBRADOR", 0.25),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M3 trabes y contratrabes
    # M cadena/dala 15x20: 0.033 m³ of concrete per metre; acero en ACE-002,
    # cimbra en EST-010
    "EST-005": [
        ("MAT-CONC250", 0.033),
        ("MO-CUAD-ALB", 0.035),
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
    # M3 contratrabe — concreto y colado; acero en ACE-004, cimbra en CIM-009
    "CIM-008": [
        ("MAT-CONC250", 1.05),
        ("MO-CUAD-ALB", 0.70),
        ("EQ-VIBRADOR", 0.20),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M3 trabes — concreto y colado; acero en ACE-004, cimbra en EST-009
    "EST-002": [
        ("MAT-CONC250", 1.05),
        ("MO-CUAD-ALB", 0.75),
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
    # M2 plantilla de concreto pobre de 5 cm bajo zapatas
    "CIM-003": [
        ("MAT-CONC150", 0.055),
        ("MO-CUAD-ALB", 0.060),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M pilote colado en sitio Ø60 cm: perforación, armado (≈ 25 kg/m) y
    # concreto (0.283 m³/m + desperdicio por perforación); la longitud viene
    # de las notas, el cuadro o la lectura con IA
    "CIM-011": [
        ("MAT-CONC250", 0.34),
        ("MAT-ACERO", 0.025),
        ("MO-CUAD-ALB", 0.10),
        ("MO-CUAD-FIE", 0.08),
        ("EQ-PERFORADORA", 0.25),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M3 losa de cimentación: concreto con desperdicio; acero por detalle
    "CIM-007": [
        ("MAT-CONC250", 1.05),
        ("MO-CUAD-ALB", 0.850),
        ("EQ-VIBRADOR", 0.150),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M2 losa reticular aligerada (nervada): concreto y el acero de las
    # nervaduras (≈ 6.5 kg/m²); la malla de la capa de compresión va en
    # ACE-005 y la cimbra de contacto en EST-011
    "EST-003": [
        ("MAT-CONC250", 0.110),
        ("MAT-ACERO", 0.0065),
        ("MO-CUAD-ALB", 0.120),
        ("MO-CUAD-FIE", 0.040),
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
    # M2 aplanado fino 1:4, 2 cm, per face (the rule already counts both faces)
    "ACA-001": [
        ("MAT-MORTERO", 0.024),
        ("MO-CUAD-ALB", 0.080),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M2 pintura vinílica dos manos sobre aplanado
    "ACA-002": [
        ("MAT-SELLADOR", 0.10),
        ("MAT-PINTURA", 0.18),
        ("MO-PINTOR", 0.025),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M2 plafón de yeso 1.5 cm
    "ACA-003": [
        ("MAT-YESO", 12.0),
        ("MO-YESERO", 0.055),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M2 pintura en plafones
    "ACA-004": [
        ("MAT-SELLADOR", 0.10),
        ("MAT-PINTURA", 0.20),
        ("MO-PINTOR", 0.030),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M2 loseta cerámica con adhesivo y junteo (5 % desperdicio)
    "PIS-001": [
        ("MAT-PISO-CER", 1.05),
        ("MAT-ADHESIVO", 5.0),
        ("MO-CUAD-ALB", 0.095),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M2 despalme 20 cm con motoconformadora, carga y acarreo libre
    "TER-001": [
        ("EQ-MOTOCONFORMADORA", 0.004),
        ("EQ-RETRO", 0.005),
        ("EQ-CAMION", 0.008),
        ("MO-PEON", 0.006),
    ],
    # M3 corte con retroexcavadora, material B, en banco
    "TER-002": [
        ("EQ-RETRO", 0.028),
        ("MO-PEON", 0.010),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M3 terraplén compactado 90 % Proctor con tepetate de banco
    "TER-003": [
        ("MAT-TEPETATE", 1.25),
        ("MAT-AGUA", 0.12),
        ("EQ-MOTOCONFORMADORA", 0.012),
        ("EQ-VIBROCOMPACTADOR", 0.015),
        ("EQ-PIPA", 0.006),
        ("MO-PEON", 0.020),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    # M2 firme de concreto f'c=150 de 10 cm, pulido
    "PIS-002": [
        ("MAT-CONC150", 0.105),
        ("MO-CUAD-ALB", 0.060),
        ("MO-PEON", 0.040),
        ("EQ-HERRAMIENTA", 1.0),
    ],
}
