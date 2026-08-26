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
from typing import Literal

from pydantic import BaseModel, Field

from klave_engine.costing.plantilla import CargoCampo
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
    # Terracerías: the terrain's sampled ground against the platform level
    # the engineer sets (m³ of corte / terraplén over the lot polygon).
    EARTHWORK_CUT = "earthwork_cut"
    EARTHWORK_FILL = "earthwork_fill"


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
    # LINEAR_VOLUME for walls: section = thickness (section_property) × this height.
    section_height_m: float | None = None
    # The height in quantity_factor / section_height_m is an assumption; when
    # the plantas declare their levels (NPT/NTC), use each planta's own story
    # height instead.
    height_from_levels: bool = False
    # Faces of a wall the concept covers (aplanado and pintura: both sides).
    # Applied with the story height; for assumed heights fold it into
    # quantity_factor as well.
    sides: float = 1.0
    # Wall faces lose their doors and windows: measured from the openings the
    # wall detector bridged when there are any, else the assumed share.
    opening_deduction: bool = False
    # A wall on the azotea planta is a pretil: costed at parapet_height_m.
    roof_walls_are_parapets: bool = False


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
    # The taller's own clave for this concept (alias), shown on every
    # deliverable so OPUS/Neodata and the client see their vocabulary.
    taller_clave: str = ""


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
    # What the engine read before any manual adjustment; None when the line
    # carries the engine's own figure. A presupuesto never hides an edit.
    engine_quantity: float | None = None
    # The taller's clave when the concept has an alias ("" otherwise).
    taller_clave: str = ""
    # True when the quantity is a parametric proposal from the taller's
    # history (per m², per planta, per local), not a reading of the plan.
    parametric: bool = False
    # True when the concept has no matrix nor adopted P.U.: the quantity is
    # real, the amount is not zero — it is unknown, and the presupuesto says so.
    unpriced: bool = False


class BillOfQuantities(BaseModel):
    project_id: str
    currency: str = "MXN"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    lines: list[BoqLine] = Field(default_factory=list)
    direct_cost_total: float = 0.0
    totals_by_phase: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    # False when the drawing's unit is not reliable: quantities are in
    # drawing units, every line is unpriced and the total is not a price.
    units_reliable: bool = True


class MoneyBasis(BaseModel):
    """What the engine read about the drawing's scale, frozen with the run.

    Stable for the life of a run: re-reading the plan is what changes it, and
    that always produces a new run.
    """

    units_reliable: bool = True
    unit: str = ""
    source: str = ""
    confidence: float = 0.0
    # Why, in the words the screens already use.
    reasons: list[str] = Field(default_factory=list)
    # Share of the direct cost by confidence band, in percent. Money-weighted
    # on purpose: a simple average lets a hundred safe screws hide one
    # doubtful beam.
    confidence_bands: dict[str, float] = Field(default_factory=dict)


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


# Which derived concept serves which pour, and as what. Task 8's hard edges
# read the same map: one statement of "EST-008 is the formwork for EST-001",
# used both to order it before the pour and to make the pour wait for it.
# You form, you reinforce, you pour — so cimbra takes parent - 2 and acero
# parent - 1, in the gap of nine the catalog already leaves before each parent.
DERIVADO_DE: dict[str, tuple[str, str]] = {
    "EST-008": ("EST-001", "cimbra"),
    "EST-009": ("EST-002", "cimbra"),
    "EST-010": ("EST-005", "cimbra"),
    "EST-011": ("EST-013", "cimbra"),
    "CIM-006": ("CIM-002", "cimbra"),
    "CIM-009": ("CIM-008", "cimbra"),
    "ACE-001": ("EST-001", "acero"),
    "ACE-002": ("EST-005", "acero"),
    "ACE-003": ("CIM-002", "acero"),
    "ACE-004": ("EST-002", "acero"),
    "ACE-005": ("EST-012", "acero"),
    "ACE-006": ("EST-013", "acero"),
}

_OFFSET_POR_TIPO = {"cimbra": -2, "acero": -1}


class ScheduleLink(BaseModel):
    """One precedence relation, as RLOPSRM art. 224 requires the network to
    state it: which activity comes before, of what kind, with what lag."""

    predecessor: str  # concept_code of the activity that comes before
    kind: Literal["FS", "SS"] = "SS"  # fin-a-inicio | inicio-a-inicio
    lag_days: int = 0


class ScheduleActivity(BaseModel):
    concept_code: str
    description: str
    phase: str
    quantity: float
    unit: str
    rendimiento_per_day: float  # quantitative performance indicator by work type
    # Where that rendimiento came from: "matriz" (derived from the APU's own
    # crew-days, so the programa and the money cannot disagree) or "catálogo"
    # (the concept's stored rate, used when the matrix has no crew line).
    rendimiento_source: str = "catálogo"
    crews: int
    duration_days: int
    start_day: int
    end_day: int
    # The network, per art. 224: precedences, the late dates they imply, and
    # the float that falls out of them.
    predecessors: list[ScheduleLink] = Field(default_factory=list)
    late_start_day: int = 0
    late_finish_day: int = 0
    total_float_days: int = 0
    free_float_days: int = 0
    critical: bool = False
    # Calendar dates when the obra has a start date (ISO), else None.
    start_date: str | None = None
    end_date: str | None = None
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
    # The obra's start and end on the calendar when a start date is set.
    start_date: str | None = None
    end_date: str | None = None
    # Días naturales corridos, which is the unit the contract speaks (LOPSRM
    # art. 31 fr. V): the working days above run on a six-day site week, so
    # reporting them as the contractual plazo understates it by about a fifth.
    calendar_days: int = 0

    @property
    def critical_path(self) -> list[str]:
        return [a.concept_code for a in self.activities if a.critical]


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
    castillo_section_m2: float = 0.03  # 15x20 cm (K marks without a cuadro)
    column_height_m: float = 3.0
    beam_section_m2: float = 0.1125  # 25x45 cm
    contratrabe_section_m2: float = 0.125  # 25x50 cm
    dala_section_m2: float = 0.0375  # 15x25 cm (cadena de enrase / cerramiento)
    wall_height_m: float = 2.7
    # Vanos: share of a wall face that is door and window when the plano
    # gives no measured openings (vivienda: 15–25 %); 0 disables the deduction.
    opening_share_pct: float = 18.0
    # Height of a measured opening (a door; windows sit within it) used with
    # the widths the wall detector reads.
    opening_height_m: float = 2.1
    # Pretil: the height of a wall drawn on the azotea planta.
    parapet_height_m: float = 0.9
    slab_thickness_m: float = 0.12  # losa maciza without a declared H=
    mat_thickness_m: float = 0.20  # losa de cimentación without a declared H=
    footing_depth_m: float = 0.35
    excavation_depth_m: float = 0.50
    # Terracerías: the platform (desplante) level in the survey's datum. None
    # until the engineer sets it — corte/terraplén are never computed against
    # a guessed level.
    platform_level_m: float | None = None
    despalme_thickness_m: float = 0.20
    # Área construida for paramétricos; None = read from the plan's slabs.
    area_construida_m2: float | None = None
    excavation_swell_factor: float = 1.3


class IndirectsConfig(BaseModel):
    field_indirects_pct: float = 8.0
    office_indirects_pct: float = 5.0
    financing_pct: float = 1.5
    profit_pct: float = 10.0  # utilidad
    additional_charges_pct: float = 0.5  # cargos adicionales (e.g. inspección)
    contingency_pct: float = 5.0  # imprevistos


class ScheduleConfig(BaseModel):
    # Obra start date (ISO, "2026-09-01"); None keeps the programa in
    # relative working days. Calendar dates skip Sundays (6-day site week).
    start_date: str | None = None
    workdays_per_month: int = 24
    # Activities inside a phase follow each other (trades in sequence) with
    # this overlap; phases fast-track onto the previous phase with theirs.
    intra_phase_overlap_pct: float = 50.0
    phase_overlap_pct: float = 15.0
    crews_per_activity: int = 1
    # Frentes de trabajo: cuántas partes de la obra avanzan a la vez con
    # cuadrillas propias. Es el otro modo de acortar el plazo, y el que un
    # residente usa de verdad — dos frentes no hacen a la cuadrilla más
    # rápida, ponen dos cuadrillas donde había una.
    frentes: int = 1
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
    # Personal técnico, administrativo y de servicio de campo: el único de los
    # cinco programas del art. 45-A que no sale del presupuesto, porque es
    # costo indirecto y no vive en ninguna matriz. Vacío = programa vacío, y
    # el programa lo dice en vez de fingir que no hacía falta.
    plantilla_campo: list[CargoCampo] = Field(default_factory=list)
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
    # Sanity ratios and partida shares vs the taller's plantilla (indicadores.py).
    indicators: dict = Field(default_factory=dict)
    # La plantilla de campo con la que se armó el programa de personal, y el
    # importe de indirectos de campo contra el que tiene que cuadrar. Viajan
    # con el reporte para que el Excel se genere de lo guardado y no de la
    # configuración de hoy.
    plantilla_campo: list[CargoCampo] = Field(default_factory=list)
    indirectos_campo: float = 0.0
    # What the engine read about the drawing's scale, frozen with this run.
    # Joined with the reviews' sign-off by costing.presentation at read time;
    # None on runs written before the verdict existed, which resolve to
    # "blocked" rather than being trusted.
    money_basis: MoneyBasis | None = None
