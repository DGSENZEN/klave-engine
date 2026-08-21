"""Explicit pipeline orchestration.

Each stage has explicit inputs and outputs, writes an inspectable artifact, and
logs a stage event. No magic all-in-one processing: stages can be run
individually (see the CLI) or together via ``run_full_pipeline``.
"""

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from klave_engine.common.config import Settings, get_settings
from klave_engine.common.errors import ConversionError, ProjectManifestError
from klave_engine.common.io import read_json, write_json, write_text
from klave_engine.common.logging import configure_logging, get_logger, log_stage
from klave_engine.conversion.dwg_to_dxf import ConversionResult, convert_project
from klave_engine.costing.catalog_store import get_catalog_store
from klave_engine.costing.insumos import apply_price_overrides
from klave_engine.costing.models import CostingConfig, CostReport
from klave_engine.costing.recompute import load_overrides
from klave_engine.costing.report import (
    boq_to_csv,
    cost_report_to_markdown,
    generate_cost_report,
)
from klave_engine.costing.reviews import filter_excluded, load_reviews
from klave_engine.detection.dimensions import build_dimension_inventory
from klave_engine.detection.results import Detection
from klave_engine.detection.suite import (
    load_detector_config,
    run_detectors,
)
from klave_engine.detection.taxonomy import enrich_detections
from klave_engine.detection.views import segment_views
from klave_engine.dxf.blocks import summarize_blocks
from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.dxf.layers import summarize_layers
from klave_engine.dxf.parser import DxfParser, ParsedDrawing
from klave_engine.dxf.units import DrawingUnits, detect_units
from klave_engine.geometry.spatial_index import SpatialIndex
from klave_engine.graph.builder import DrawingGraph, build_drawing_graph
from klave_engine.ingestion.manifest import (
    ProcessingStatus,
    ProjectManifest,
    save_manifest,
)
from klave_engine.ingestion.project_loader import ingest_project
from klave_engine.risks.report import risk_report_to_markdown
from klave_engine.risks.rules import RiskReport, generate_risk_report
from klave_engine.takeoff.quantities import QuantityReport, generate_quantity_report
from klave_engine.takeoff.report import quantity_report_to_csv, quantity_report_to_markdown

logger = get_logger(__name__)


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
    manifest: ProjectManifest, settings: Settings, output_dir: Path | None = None
) -> list[ConversionResult]:
    """Convert DWG sources to DXF (non-fatal). The real failure — no DXF at all —
    is caught by the caller via ``manifest.dxf_paths()``."""
    results = convert_project(manifest, settings)
    processed = output_dir or _processed_dir(manifest.root(), settings)
    write_json(processed / "conversion_results.json", results)
    save_manifest(manifest, settings.processed_dir_name)
    return results


def parse_drawings(
    manifest: ProjectManifest, settings: Settings, output_dir: Path | None = None
) -> list[ParsedDrawing]:
    parser = DxfParser()
    paths = manifest.dxf_paths()
    drawings = parser.parse_files(
        paths,
        source_files=[str(path.relative_to(manifest.root())) for path in paths],
    )
    entities = [e for d in drawings for e in d.entities]
    warnings = [w for d in drawings for w in d.warnings]
    processed = output_dir or _processed_dir(manifest.root(), settings)
    write_json(processed / "normalized_entities.json", entities)
    write_json(processed / "parse_warnings.json", warnings)
    write_json(processed / "parse_summary.json", _summarize_parse(drawings))
    write_json(processed / "layer_summary.json", summarize_layers(entities))
    write_json(processed / "block_summary.json", summarize_blocks(entities))
    manifest.processing_status = ProcessingStatus.parsed
    save_manifest(manifest, settings.processed_dir_name)
    return drawings


def _summarize_parse(drawings: list[ParsedDrawing]) -> list[dict]:
    """Per-sheet legibility record: what was read, derived, and dropped."""
    summary: list[dict] = []
    for drawing in drawings:
        entities_by_type = Counter(e.entity_type.value for e in drawing.entities)
        derived_by_type = Counter(
            str(e.properties["derived_from"])
            for e in drawing.entities
            if e.properties.get("derived_from")
        )
        dropped_by_type = Counter(
            w.entity_type or "desconocido"
            for w in drawing.warnings
            if w.warning_type == "unsupported_dxf_entity"
        )
        summary.append(
            {
                "source_file": drawing.source_file,
                "entity_count": len(drawing.entities),
                "entities_by_type": dict(entities_by_type.most_common()),
                "from_block_count": sum(
                    1 for e in drawing.entities if e.properties.get("from_block")
                ),
                "derived_by_type": dict(derived_by_type.most_common()),
                "dropped_by_type": dict(dropped_by_type.most_common()),
                "text_count": sum(1 for e in drawing.entities if e.is_textual),
                "recovered": any(
                    w.warning_type == "dxf_recovered" for w in drawing.warnings
                ),
                "warning_count": len(drawing.warnings),
                "insunits": drawing.insunits,
                "layer_count": len(drawing.layers),
                "block_count": len(drawing.blocks),
            }
        )
    return summary


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
    artifact_dir: Path | None = None,
    reports_dir: Path | None = None,
) -> PipelineResult:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    project_root = Path(project_root)
    control_dir = _processed_dir(project_root, settings)
    processed = artifact_dir or control_dir
    reports = reports_dir or _reports_dir(project_root)

    # Capture the previous run's story before this run overwrites anything.
    prev_detections = _previous_artifact(control_dir, "detections.json")
    prev_report = (
        _previous_artifact(control_dir, "cost_report_override.json")
        or _previous_artifact(control_dir, "cost_report.json")
    )
    prev_total = None
    if isinstance(prev_report, dict):
        prev_total = (prev_report.get("integration") or {}).get("grand_total")

    manifest = ingest_project(
        project_root, project_name=project_name, processed_dir_name=settings.processed_dir_name
    )
    if not manifest.source_files:
        manifest.processing_status = ProcessingStatus.failed
        manifest.errors.append("No DWG or DXF source files are available for processing")
        save_manifest(manifest, settings.processed_dir_name)
        raise ProjectManifestError("No DWG or DXF source files are available for processing")
    result = PipelineResult(manifest=manifest)

    convert_drawings(manifest, settings, output_dir=processed)
    if not manifest.dxf_paths():
        manifest.processing_status = ProcessingStatus.failed
        manifest.errors.append("No DXF files are available after conversion")
        save_manifest(manifest, settings.processed_dir_name)
        raise ConversionError("No DXF files are available after conversion")
    drawings = parse_drawings(manifest, settings, output_dir=processed)
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
    detector_outputs = run_detectors(result.entities, index, manifest, detector_config)
    for output in detector_outputs:
        result.warnings.extend(output.warnings)
        result.detections.extend(output.detections)
    enrich_detections(result.detections, units.to_meters())

    graph = build_drawing_graph(manifest.project_id, drawings, result.detections)
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
    catalog_store = get_catalog_store(settings.data_dir)
    overrides = load_overrides(control_dir)
    if overrides is not None:
        costing_config = overrides.config
        price_book = apply_price_overrides(
            catalog_store.load_price_book(), overrides.insumo_prices
        )
    else:
        costing_config = load_costing_config(settings.costing_config_path)
        price_book = catalog_store.load_price_book()
    # Human corrections survive a reprocess: exclusions are keyed by the
    # deterministic display labels and adjustments are concept-level. The
    # detections artifact keeps everything; exclusion is a costing-layer act.
    reviews = load_reviews(control_dir)
    result.cost_report = generate_cost_report(
        manifest.project_id,
        filter_excluded(result.detections, reviews),
        units, costing_config,
        segmentation, dimensions, price_book=price_book,
        apu_templates=catalog_store.load_templates(),
        rendimientos=catalog_store.load_rendimientos(),
        adjustments=reviews.adjustments,
    )
    write_json(processed / "cost_report.json", result.cost_report)
    diff = _run_diff(
        prev_detections,
        prev_total,
        result.detections,
        result.cost_report.integration.grand_total,
    )
    if diff is not None:
        write_json(processed / "run_diff.json", diff)
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


def _previous_artifact(control_dir: Path, name: str):
    """Read an artifact from the currently active run (or the control dir)
    before this pipeline run replaces it."""
    pointer = control_dir / "active_run.json"
    candidates = [control_dir / name]
    if pointer.exists():
        try:
            run_dir = control_dir / str(json.loads(pointer.read_text())["artifact_dir"])
            if run_dir.resolve().is_relative_to(control_dir.resolve()):
                candidates.insert(0, run_dir / name)
        except (KeyError, ValueError, OSError):
            pass
    for path in candidates:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                return None
    return None


def _run_diff(
    prev_detections: list[dict] | None,
    prev_total: float | None,
    new_detections: list[Detection],
    new_total: float,
) -> dict | None:
    """What changed since the last processing: the revision story."""
    if prev_detections is None:
        return None

    def family_of(item: dict) -> str:
        return item.get("family") or item.get("detection_type") or "otro"

    def label_of(item: dict) -> str:
        return item.get("display_label") or item.get("detection_id") or ""

    prev_families: dict[str, int] = {}
    for item in prev_detections:
        prev_families[family_of(item)] = prev_families.get(family_of(item), 0) + 1
    new_items = [d.model_dump(mode="json") for d in new_detections]
    new_families: dict[str, int] = {}
    for item in new_items:
        new_families[family_of(item)] = new_families.get(family_of(item), 0) + 1

    prev_labels = {label_of(item) for item in prev_detections if label_of(item)}
    new_labels = {label_of(item) for item in new_items if label_of(item)}
    return {
        "families": {
            family: {
                "prev": prev_families.get(family, 0),
                "new": new_families.get(family, 0),
            }
            for family in sorted(set(prev_families) | set(new_families))
        },
        "added_labels": sorted(new_labels - prev_labels)[:40],
        "removed_labels": sorted(prev_labels - new_labels)[:40],
        "prev_detection_count": len(prev_detections),
        "new_detection_count": len(new_items),
        "prev_grand_total": prev_total,
        "new_grand_total": new_total,
    }


def load_processed_artifact(project_root: Path, settings: Settings, name: str):
    """Read a processed JSON artifact by filename (e.g. ``detections.json``)."""
    path = _processed_dir(Path(project_root), settings) / name
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
