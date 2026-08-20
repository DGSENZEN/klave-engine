"""Recompute the cost report from persisted detection artifacts.

Detection, segmentation and dimension parsing are the expensive stages; once a
project is processed their results are on disk. Editing a parameter or an
insumo price only needs the costing stage, so this module reloads those
artifacts and rebuilds the cost report in well under a second — no re-detection.

User edits are persisted as ``costing_overrides.json`` so they survive reloads
and are reapplied on the next full pipeline run.
"""

from pathlib import Path

from klave_engine.common.config import get_settings
from klave_engine.common.errors import ReportGenerationError
from klave_engine.common.io import read_json, write_json, write_text
from klave_engine.common.logging import get_logger, log_stage
from klave_engine.costing.catalog_store import get_catalog_store
from klave_engine.costing.insumos import apply_price_overrides
from klave_engine.costing.models import CostingOverrides, CostReport
from klave_engine.costing.report import (
    boq_to_csv,
    cost_report_to_markdown,
    generate_cost_report,
)
from klave_engine.costing.reviews import ProjectReviews, filter_excluded, load_reviews
from klave_engine.detection.dimensions import DimensionInventory
from klave_engine.detection.results import Detection
from klave_engine.detection.views import SheetSegmentation
from klave_engine.dxf.units import DrawingUnits

logger = get_logger(__name__)

OVERRIDES_FILENAME = "costing_overrides.json"
COST_REPORT_OVERRIDE_FILENAME = "cost_report_override.json"


class CostingInputs:
    """The persisted, detection-stage outputs that costing consumes."""

    def __init__(
        self,
        project_id: str,
        detections: list[Detection],
        units: DrawingUnits,
        segmentation: SheetSegmentation | None,
        dimensions: DimensionInventory | None,
    ) -> None:
        self.project_id = project_id
        self.detections = detections
        self.units = units
        self.segmentation = segmentation
        self.dimensions = dimensions


def load_costing_inputs(processed_dir: Path, project_id: str) -> CostingInputs:
    detections_path = processed_dir / "detections.json"
    if not detections_path.exists():
        raise ReportGenerationError(
            "No hay detecciones; procesa el proyecto antes de recalcular costos."
        )
    detections = [Detection.model_validate(d) for d in read_json(detections_path)]
    units = DrawingUnits.model_validate(read_json(processed_dir / "drawing_units.json"))
    seg_path = processed_dir / "views.json"
    segmentation = (
        SheetSegmentation.model_validate(read_json(seg_path)) if seg_path.exists() else None
    )
    dims_path = processed_dir / "dimensions.json"
    dimensions = (
        DimensionInventory.model_validate(read_json(dims_path)) if dims_path.exists() else None
    )
    return CostingInputs(project_id, detections, units, segmentation, dimensions)


def load_overrides(processed_dir: Path) -> CostingOverrides | None:
    path = processed_dir / OVERRIDES_FILENAME
    if not path.exists():
        return None
    return CostingOverrides.model_validate(read_json(path))


def save_overrides(processed_dir: Path, overrides: CostingOverrides) -> None:
    write_json(processed_dir / OVERRIDES_FILENAME, overrides)


def build_cost_report(
    inputs: CostingInputs,
    overrides: CostingOverrides,
    reviews: ProjectReviews | None = None,
) -> CostReport:
    """Costing from persisted inputs: workspace catalog, project overrides,
    and human corrections (excluded detections + manual adjustments)."""
    store = get_catalog_store(get_settings().data_dir)
    price_book = apply_price_overrides(store.load_price_book(), overrides.insumo_prices)
    detections = (
        filter_excluded(inputs.detections, reviews) if reviews else inputs.detections
    )
    return generate_cost_report(
        inputs.project_id,
        detections,
        inputs.units,
        overrides.config,
        inputs.segmentation,
        inputs.dimensions,
        price_book=price_book,
        apu_templates=store.load_templates(),
        rendimientos=store.load_rendimientos(),
        adjustments=reviews.adjustments if reviews else None,
    )


def recompute_and_persist(
    input_dir: Path,
    control_dir: Path,
    reports_dir: Path,
    project_id: str,
    overrides: CostingOverrides,
) -> CostReport:
    """Recompute costs from an immutable run and persist a derived scenario."""
    inputs = load_costing_inputs(input_dir, project_id)
    report = build_cost_report(inputs, overrides, reviews=load_reviews(control_dir))

    write_json(control_dir / COST_REPORT_OVERRIDE_FILENAME, report)
    save_overrides(control_dir, overrides)
    boq_to_csv(report, reports_dir / "presupuesto.csv")
    write_text(reports_dir / "resumen_costos.md", cost_report_to_markdown(report))

    log_stage(
        logger,
        "cost_recomputed",
        project_id=project_id,
        direct_cost=report.boq.direct_cost_total,
        grand_total=report.integration.grand_total,
        price_overrides=len(overrides.insumo_prices),
    )
    return report
