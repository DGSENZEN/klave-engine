"""Explicit pipeline orchestration.

Each stage has explicit inputs and outputs, writes an inspectable artifact, and
logs a stage event. No magic all-in-one processing: stages can be run
individually (see the CLI) or together via ``run_full_pipeline``.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

from klave_engine.common.config import Settings, get_settings
from klave_engine.common.ids import IdGenerator
from klave_engine.common.io import read_json, write_json, write_text
from klave_engine.common.logging import configure_logging, get_logger, log_stage
from klave_engine.conversion.dwg_to_dxf import (
    ConversionResult,
    DwgToDxfConverter,
    convert_project,
)
from klave_engine.costing.insumos import apply_price_overrides, default_price_book
from klave_engine.costing.models import CostingConfig, CostReport
from klave_engine.costing.recompute import load_overrides
from klave_engine.costing.report import (
    boq_to_csv,
    cost_report_to_markdown,
    generate_cost_report,
)
from klave_engine.detection.beam_detector import BeamDetectorConfig, detect_beams
from klave_engine.detection.column_detector import ColumnDetectorConfig, detect_columns
from klave_engine.detection.detail_reference_detector import (
    DetailReferenceDetectorConfig,
    detect_detail_references,
)
from klave_engine.detection.dimensions import build_dimension_inventory
from klave_engine.detection.footing_detector import FootingDetectorConfig, detect_footings
from klave_engine.detection.grid_detector import GridDetectorConfig, detect_grid
from klave_engine.detection.results import Detection, DetectorOutput
from klave_engine.detection.slab_detector import SlabDetectorConfig, detect_slabs
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.detection.views import segment_views
from klave_engine.detection.wall_detector import WallDetectorConfig, detect_walls
from klave_engine.dxf.blocks import summarize_blocks
from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.dxf.layers import summarize_layers
from klave_engine.dxf.parser import DxfParser, ParsedDrawing
from klave_engine.dxf.units import DrawingUnits, detect_units
from klave_engine.geometry.spatial_index import SpatialIndex
from klave_engine.graph.builder import DrawingGraph, DrawingGraphBuilder
from klave_engine.ingestion.manifest import (
    ProcessingStatus,
    ProjectManifest,
    save_manifest,
)
from klave_engine.ingestion.project_loader import ingest_project
from klave_engine.risks.report import risk_report_to_markdown
from klave_engine.risks.rules import RiskEngineConfig, RiskReport, generate_risk_report
from klave_engine.takeoff.quantities import QuantityReport, generate_quantity_report
from klave_engine.takeoff.report import quantity_report_to_csv, quantity_report_to_markdown

logger = get_logger(__name__)


class DetectorSuiteConfig(BaseModel):
    """Aggregate configuration for all detectors; overridable from a JSON file."""

    text_patterns: TextPatternConfig = Field(default_factory=TextPatternConfig)
    grid: GridDetectorConfig = Field(default_factory=GridDetectorConfig)
    column: ColumnDetectorConfig = Field(default_factory=ColumnDetectorConfig)
    footing: FootingDetectorConfig = Field(default_factory=FootingDetectorConfig)
    beam: BeamDetectorConfig = Field(default_factory=BeamDetectorConfig)
    slab: SlabDetectorConfig = Field(default_factory=SlabDetectorConfig)
    wall: WallDetectorConfig = Field(default_factory=WallDetectorConfig)
    detail_reference: DetailReferenceDetectorConfig = Field(
        default_factory=DetailReferenceDetectorConfig
    )
    risk: RiskEngineConfig = Field(default_factory=RiskEngineConfig)
    graph_near_radius: float = 25.0

    @classmethod
    def preset_for_units(cls, units: DrawingUnits) -> "DetectorSuiteConfig":
        """Detector thresholds scaled to real-world units when they are known.

        The reference preset is defined in meters (validated against a real
        structural sheet) and scaled to the drawing unit. Unknown units keep
        the generic defaults.
        """
        factor = units.to_meters()
        if factor is None:
            return cls()

        def m(value_in_meters: float) -> float:
            return value_in_meters / factor

        config = cls()
        config.grid.min_relative_length = 0.04
        config.grid.label_search_radius_factor = 0.01
        config.column.grid_search_radius = m(1.5)
        config.column.geometry_search_radius = m(0.6)
        config.column.max_marker_area = m(1.0) * m(1.0)
        config.footing.min_area = m(0.55) * m(0.55)
        config.footing.max_area = m(5.5) * m(5.5)
        config.footing.column_search_radius = m(2.0)
        config.beam.line_search_radius = m(1.0)
        config.beam.min_beam_length = m(1.5)
        config.slab.min_area = m(4.0) * m(4.0)
        config.wall.min_length = m(1.5)
        config.wall.max_thickness = m(0.45)
        config.risk.duplicate_column_distance = m(10.0)
        config.graph_near_radius = m(0.5)
        return config


def load_detector_config(path: Path | None, units: DrawingUnits | None = None
                         ) -> DetectorSuiteConfig:
    if path is not None and path.exists():
        return DetectorSuiteConfig.model_validate(read_json(path))
    if units is not None:
        return DetectorSuiteConfig.preset_for_units(units)
    return DetectorSuiteConfig()


@dataclass
class PipelineResult:
    manifest: ProjectManifest
    entities: list[NormalizedEntity] = field(default_factory=list)
    detections: list[Detection] = field(default_factory=list)
    graph: DrawingGraph | None = None
    units: DrawingUnits | None = None
    quantity_report: QuantityReport | None = None
    risk_report: RiskReport | None = None
    cost_report: CostReport | None = None
    warnings: list[str] = field(default_factory=list)


def load_costing_config(path: Path | None) -> CostingConfig:
    if path is None or not path.exists():
        return CostingConfig()
    return CostingConfig.model_validate(read_json(path))


def _processed_dir(project_root: Path, settings: Settings) -> Path:
    return project_root / settings.processed_dir_name


def _reports_dir(project_root: Path) -> Path:
    return project_root / "reports"


def convert_drawings(
    manifest: ProjectManifest, settings: Settings
) -> list[ConversionResult]:
    converter = DwgToDxfConverter(
        executable=settings.converter_executable_path,
        overwrite=settings.overwrite_converted_files,
        timeout_seconds=settings.converter_timeout_seconds,
    )
    results = convert_project(manifest, converter, settings.converted_dir_name)
    write_json(
        _processed_dir(manifest.root(), settings) / "conversion_results.json", results
    )
    save_manifest(manifest, settings.processed_dir_name)
    return results


def parse_drawings(
    manifest: ProjectManifest, settings: Settings
) -> list[ParsedDrawing]:
    parser = DxfParser()
    drawings = parser.parse_files(manifest.dxf_paths())
    entities = [e for d in drawings for e in d.entities]
    warnings = [w for d in drawings for w in d.warnings]
    processed = _processed_dir(manifest.root(), settings)
    write_json(processed / "normalized_entities.json", entities)
    write_json(processed / "parse_warnings.json", warnings)
    write_json(processed / "layer_summary.json", summarize_layers(entities))
    write_json(processed / "block_summary.json", summarize_blocks(entities))
    manifest.processing_status = ProcessingStatus.parsed
    save_manifest(manifest, settings.processed_dir_name)
    return drawings


def run_detectors(
    entities: list[NormalizedEntity],
    index: SpatialIndex,
    manifest: ProjectManifest,
    config: DetectorSuiteConfig,
) -> list[DetectorOutput]:
    detection_ids = IdGenerator("det")
    edge_ids = IdGenerator("dedge")
    grid = detect_grid(
        entities, index, config.grid, config.text_patterns, detection_ids, edge_ids
    )
    columns = detect_columns(
        entities, index, grid, config.column, config.text_patterns, detection_ids, edge_ids
    )
    footings = detect_footings(
        entities, index, columns, config.footing, detection_ids, edge_ids
    )
    beams = detect_beams(
        entities, index, config.beam, config.text_patterns, detection_ids, edge_ids
    )
    slabs = detect_slabs(entities, config.slab, detection_ids, edge_ids)
    walls = detect_walls(entities, index, config.wall, detection_ids, edge_ids)
    details = detect_detail_references(
        entities, manifest, config.detail_reference, config.text_patterns, detection_ids
    )
    return [grid, columns, footings, beams, slabs, walls, details]


def _write_summary_markdown(
    manifest: ProjectManifest,
    entities: list[NormalizedEntity],
    graph: DrawingGraph,
    detections: list[Detection],
    quantity_report: QuantityReport,
    risk_report: RiskReport,
    path: Path,
) -> None:
    export = graph.to_export(manifest.project_id)
    lines = [
        f"# Project Summary: {manifest.project_name}",
        "",
        f"- Project ID: `{manifest.project_id}`",
        f"- Source files: {len(manifest.source_files)}",
        f"- Normalized entities: {len(entities)}",
        f"- Graph nodes: {len(export.nodes)}, edges: {len(export.edges)}",
        f"- Detections: {len(detections)}",
        "",
        quantity_report_to_markdown(quantity_report),
        risk_report_to_markdown(risk_report),
    ]
    write_text(path, "\n".join(lines))


def run_full_pipeline(
    project_root: Path,
    settings: Settings | None = None,
    project_name: str | None = None,
) -> PipelineResult:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    project_root = Path(project_root)
    processed = _processed_dir(project_root, settings)
    reports = _reports_dir(project_root)

    manifest = ingest_project(
        project_root, project_name=project_name, processed_dir_name=settings.processed_dir_name
    )
    result = PipelineResult(manifest=manifest)

    convert_drawings(manifest, settings)
    drawings = parse_drawings(manifest, settings)
    result.entities = [e for d in drawings for e in d.entities]

    index = SpatialIndex(result.entities)
    write_json(processed / "spatial_index_summary.json", index.summary())

    insunits = next((d.insunits for d in drawings if d.insunits), None)
    units = detect_units(insunits, result.entities)
    result.units = units
    write_json(processed / "drawing_units.json", units)
    log_stage(
        logger,
        "drawing_units_detected",
        project_id=manifest.project_id,
        unit=units.unit,
        source=units.source,
        confidence=units.confidence,
    )

    detector_config = load_detector_config(settings.detector_config_path, units)
    builder = DrawingGraphBuilder(
        manifest.project_id, near_radius=detector_config.graph_near_radius
    )
    graph = builder.build(drawings, index)

    detector_outputs = run_detectors(result.entities, index, manifest, detector_config)
    for output in detector_outputs:
        result.warnings.extend(output.warnings)
        result.detections.extend(output.detections)
        merge_warnings = builder.merge_detector_output(graph, output.nodes, output.edges)
        result.warnings.extend(merge_warnings)
    result.graph = graph

    write_json(processed / "drawing_graph.json", graph.to_export(manifest.project_id))
    write_json(processed / "detections.json", result.detections)

    result.quantity_report = generate_quantity_report(
        manifest.project_id, result.detections, assumed_unit=units.unit
    )
    write_json(processed / "quantity_report.json", result.quantity_report)

    result.risk_report = generate_risk_report(
        manifest.project_id,
        manifest,
        result.entities,
        result.detections,
        result.quantity_report,
        detector_config.risk,
    )
    write_json(processed / "risk_report.json", result.risk_report)

    segmentation = segment_views(result.entities, result.detections)
    write_json(processed / "views.json", segmentation)
    log_stage(
        logger,
        "views_segmented",
        project_id=manifest.project_id,
        segmented=segmentation.is_segmented,
        plan_views=len(segmentation.plan_views()),
        npt_levels=segmentation.npt_levels,
    )

    dimensions = build_dimension_inventory(result.entities, units.to_meters() or 1.0)
    write_json(processed / "dimensions.json", dimensions)
    log_stage(
        logger,
        "dimensions_parsed",
        project_id=manifest.project_id,
        dimension_count=dimensions.dimension_count,
        typical_section_cm=dimensions.typical_section_cm,
        typical_wall_cm=dimensions.typical_wall_thickness_cm,
        vigueta=dimensions.vigueta_system,
    )

    # Reapply any user costing edits so they survive a full reprocess.
    overrides = load_overrides(processed)
    if overrides is not None:
        costing_config = overrides.config
        price_book = apply_price_overrides(default_price_book(), overrides.insumo_prices)
    else:
        costing_config = load_costing_config(settings.costing_config_path)
        price_book = None
    result.cost_report = generate_cost_report(
        manifest.project_id, result.detections, units, costing_config,
        segmentation, dimensions, price_book=price_book,
    )
    write_json(processed / "cost_report.json", result.cost_report)
    boq_to_csv(result.cost_report, reports / "presupuesto.csv")
    write_text(
        reports / "resumen_costos.md", cost_report_to_markdown(result.cost_report)
    )

    quantity_report_to_csv(result.quantity_report, reports / "quantity_report.csv")
    write_text(reports / "risk_report.md", risk_report_to_markdown(result.risk_report))
    _write_summary_markdown(
        manifest,
        result.entities,
        graph,
        result.detections,
        result.quantity_report,
        result.risk_report,
        reports / "summary.md",
    )

    manifest.warnings.extend(result.warnings)
    manifest.processing_status = ProcessingStatus.processed
    save_manifest(manifest, settings.processed_dir_name)

    log_stage(
        logger,
        "pipeline_completed",
        project_id=manifest.project_id,
        entity_count=len(result.entities),
        detection_count=len(result.detections),
        risk_count=len(result.risk_report.findings),
        status=manifest.processing_status.value,
    )
    return result


def load_processed_artifact(project_root: Path, settings: Settings, name: str):
    """Read a processed JSON artifact by filename (e.g. ``detections.json``)."""
    path = _processed_dir(Path(project_root), settings) / name
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
