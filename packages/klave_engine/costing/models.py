"""Cost engineering domain models.

The workflow mirrors Mexican cost engineering practice:
catálogo de conceptos → análisis de precios unitarios (APU) → costo directo →
indirectos / financiamiento / utilidad / cargos adicionales → precio de venta →
programa de obra → flujo financiero.

All reference prices are clearly-labeled editable reference data, not market
quotes. Every quantity carries its assumptions and detection provenance.
"""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from klave_engine.detection.results import DetectionType
from klave_engine.dxf.units import DrawingUnits


class ResourceType(StrEnum):
    material = "material"
    labor = "mano_de_obra"
    equipment = "equipo"


class Resource(BaseModel):
    code: str
    description: str
    unit: str
    unit_cost: float
    resource_type: ResourceType
    # When true, unit_cost is a fraction applied to the APU labor subtotal
    # (e.g. herramienta menor = 3% de mano de obra).
    is_labor_percentage: bool = False


class ApuLine(BaseModel):
    resource_code: str
    description: str
    unit: str
    quantity: float
    unit_cost: float
    amount: float
    resource_type: ResourceType


class UnitPriceAnalysis(BaseModel):
    concept_code: str
    concept_description: str
    unit: str
    lines: list[ApuLine]
    breakdown: dict[str, float]  # by resource type
    direct_unit_cost: float
    # Set when the P.U. was adopted from a reference row (catálogo propio or
    # publication) instead of priced from the matrix: "source · clave · vigencia".
    price_source: str | None = None


class QuantityKind(StrEnum):
    COUNT = "count"
    LENGTH = "length"
    AREA = "area"
    VOLUME = "volume"  # area × thickness read from the detection (m³)
    LINEAR_VOLUME = "linear_volume"  # length × section read from the detection (m³)


class ViewScope(StrEnum):
    """How a concept aggregates across the plan views on a segmented sheet.

    Only applied when the sheet is segmented into ≥2 plan views; otherwise the
    flat (count/sum) computation is used unchanged.
    """

    ALL = "all"  # every detection (also the non-segmented fallback)
    FOOTPRINT_ONCE = "footprint_once"  # largest single plan view (e.g. trazo)
    FOUNDATION_ONLY = "foundation_only"  # only the foundation plan (cimentación)
    SUPERSTRUCTURE_SUM = "superstructure_sum"  # sum of non-foundation plans (losa, muros)
    COLUMN_VOLUME = "column_volume"  # max-count plan × measured section × total height


class QuantityRule(BaseModel):
    detection_type: DetectionType
    kind: QuantityKind
    source_property: str | None = None  # detection property holding length/area
    # Only detections whose property value is listed feed the concept; a
    # None in the list matches a detection without that property (e.g. a
    # slab region read by outline, before families existed).
    property_filter: dict[str, list[str | None]] | None = None
    thickness_property: str | None = None  # in cm, for VOLUME rules
    default_thickness_m: float | None = None  # when the sheet declares none
    # LINEAR_VOLUME: section from "section_cm" ("30x80") or a measured marker
    # area (drawing units²) within plausible bounds, else the default.
    section_property: str | None = None
    default_section_m2: float | None = None


class Concept(BaseModel):
    code: str
    description: str
    unit: str  # PZA | M | M2 | M3
    phase: str
    # None marks a manual concept: no detection rule feeds it, so its
    # quantity comes only from documented manual adjustments — never zero
    # invented by the system.
    rule: QuantityRule | None = None
    # Multiplier from the raw measured quantity (count / meters / m²)
    # to the concept unit, e.g. column count × section × height → m³.
    quantity_factor: float = 1.0
    view_scope: ViewScope = ViewScope.ALL
    assumptions: list[str] = Field(default_factory=list)
    # Rendimiento: concept units installed per crew per working day (QPI).
    production_rate_per_day: float
    # Order within a phase for sequencing trades (lower runs first).
    sequence_order: int = 0


class BoqLine(BaseModel):
    concept_code: str
    description: str
    unit: str
    quantity: float
    unit_price: float  # direct unit cost from the APU
    amount: float
    phase: str
    raw_quantity: float
    raw_kind: QuantityKind
    source_detection_count: int
    source_detections: list[str] = Field(default_factory=list)
    confidence: float
    assumptions: list[str] = Field(default_factory=list)
    # Quantity per plan view (view title → quantity in the concept unit) on
    # a segmented sheet; empty on flat sheets and single-view scopes.
    by_view: dict[str, float] = Field(default_factory=dict)


class BillOfQuantities(BaseModel):
    project_id: str
    currency: str = "MXN"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    lines: list[BoqLine] = Field(default_factory=list)
    direct_cost_total: float = 0.0
    totals_by_phase: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class IntegrationLine(BaseModel):
    code: str
    description: str
    base: float
    percentage: float
    amount: float
    accumulated: float


class CostIntegration(BaseModel):
    direct_cost: float
    lines: list[IntegrationLine]
    sale_price: float  # precio de venta (CD+CI+F+U+CA)
    contingency: float
    grand_total: float
    overcost_factor: float  # precio de venta / costo directo


class ScheduleActivity(BaseModel):
    concept_code: str
    description: str
    phase: str
    quantity: float
    unit: str
    rendimiento_per_day: float  # quantitative performance indicator by work type
    crews: int
    duration_days: int
    start_day: int
    end_day: int
    direct_cost: float


class PeriodCashflow(BaseModel):
    period: int
    label: str
    direct_spend: float
    billing: float  # estimación a precio de venta
    advance_amortization: float
    retention: float
    net_cashflow: float
    accumulated_billing: float
    progress_pct: float


class WorkSchedule(BaseModel):
    activities: list[ScheduleActivity]
    total_duration_days: int
    workdays_per_month: int
    phases: list[str]


class OperatingYear(BaseModel):
    year: int
    operation: float
    maintenance: float
    total: float
    accumulated: float


class FinancialPlan(BaseModel):
    currency: str = "MXN"
    advance_payment_pct: float
    retention_pct: float
    advance_payment: float
    total_retention: float
    periods: list[PeriodCashflow]
    operating_projection: list[OperatingYear]
    annual_operating_cost: float


# ---------------------------------------------------------------- config


class CostingAssumptions(BaseModel):
    """Geometric assumptions used to derive volumes from plan detections."""

    column_section_m2: float = 0.09  # 30x30 cm
    column_height_m: float = 3.0
    beam_section_m2: float = 0.1125  # 25x45 cm
    contratrabe_section_m2: float = 0.125  # 25x50 cm
    wall_height_m: float = 2.7
    slab_thickness_m: float = 0.12  # losa maciza without a declared H=
    mat_thickness_m: float = 0.20  # losa de cimentación without a declared H=
    footing_depth_m: float = 0.35
    excavation_depth_m: float = 0.50
    excavation_swell_factor: float = 1.3


class IndirectsConfig(BaseModel):
    field_indirects_pct: float = 8.0
    office_indirects_pct: float = 5.0
    financing_pct: float = 1.5
    profit_pct: float = 10.0  # utilidad
    additional_charges_pct: float = 0.5  # cargos adicionales (e.g. inspección)
    contingency_pct: float = 5.0  # imprevistos


class ScheduleConfig(BaseModel):
    workdays_per_month: int = 24
    # Activities inside a phase follow each other (trades in sequence) with
    # this overlap; phases fast-track onto the previous phase with theirs.
    intra_phase_overlap_pct: float = 50.0
    phase_overlap_pct: float = 15.0
    crews_per_activity: int = 1
    # Multi-level structures cannot be compressed below one cycle per level.
    per_level_cycle_days: int = 15


class FinancialConfig(BaseModel):
    advance_payment_pct: float = 30.0  # anticipo
    retention_pct: float = 5.0  # fondo de garantía
    annual_operation_pct: float = 2.0  # % of sale price per year
    annual_maintenance_pct: float = 1.5
    operating_horizon_years: int = 5


class CostingConfig(BaseModel):
    currency: str = "MXN"
    assumptions: CostingAssumptions = Field(default_factory=CostingAssumptions)
    indirects: IndirectsConfig = Field(default_factory=IndirectsConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    financial: FinancialConfig = Field(default_factory=FinancialConfig)


class CostingOverrides(BaseModel):
    """User edits to costing inputs, persisted per project and applied on
    recompute (and on the next full run). Insumo prices override unit costs by
    resource code.

    ``version`` implements optimistic concurrency for collaboration: a client
    submits the version it edited on top of, and the API rejects the write
    (409) if someone else saved in between — no silent last-write-wins on
    money-bearing parameters."""

    config: CostingConfig = Field(default_factory=CostingConfig)
    insumo_prices: dict[str, float] = Field(default_factory=dict)
    version: int = 0
    updated_by: str | None = None
    updated_at: datetime | None = None


class CostReport(BaseModel):
    project_id: str
    currency: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    drawing_units: DrawingUnits
    boq: BillOfQuantities
    apus: list[UnitPriceAnalysis]
    integration: CostIntegration
    schedule: WorkSchedule
    financial: FinancialPlan
    warnings: list[str] = Field(default_factory=list)
