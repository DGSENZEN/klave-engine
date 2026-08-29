"""Explicit pipeline orchestration.

Each stage has explicit inputs and outputs, writes an inspectable artifact, and
logs a stage event. No magic all-in-one processing: stages can be run
individually (see the CLI) or together via ``run_full_pipeline``.
"""

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from klave_engine.common.config import Settings, get_settings
from klave_engine.common.errors import ConversionError, ProjectManifestError
from klave_engine.common.ids import IdGenerator
from klave_engine.common.io import read_json, write_json, write_text
from klave_engine.common.logging import configure_logging, get_logger, log_stage
from klave_engine.common.version import engine_stamp
from klave_engine.conversion.dwg_to_dxf import ConversionResult, convert_project
from klave_engine.costing.catalog_store import CatalogStore, get_catalog_store
from klave_engine.costing.hallazgos import promote_detection_warnings
from klave_engine.costing.insumos import apply_price_overrides
from klave_engine.costing.models import CostingConfig, CostReport
from klave_engine.costing.recompute import load_overrides
from klave_engine.costing.report import (
    boq_to_csv,
    cost_report_to_markdown,
    generate_cost_report,
)
from klave_engine.costing.reviews import filter_excluded, load_reviews
from klave_engine.detection.bajadas import stamp_bajada_stacks
from klave_engine.detection.dimension_links import link_dimensions
from klave_engine.detection.dimensions import build_dimension_inventory
from klave_engine.detection.disciplines import route_sheet, vote_content
from klave_engine.detection.frames import SheetFrame, detect_frames
from klave_engine.detection.inventory import build_inventory, reads_as_structure
from klave_engine.detection.prefabs import build_prefab_index
from klave_engine.detection.results import Detection, DetectionType
from klave_engine.detection.schedules import (
    apply_schedule,
    build_schedule_inventory,
    mark_cuadro_detections,
    merge_external_specs,
)
from klave_engine.detection.suite import (
    load_detector_config,
    run_detectors,
)
from klave_engine.detection.taxonomy import enrich_detections
from klave_engine.detection.views import segment_views
from klave_engine.dxf.blocks import summarize_blocks
from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.dxf.harmonize import harmonize_units
from klave_engine.dxf.layers import summarize_layers
from klave_engine.dxf.parser import DxfParser, ParsedDrawing
from klave_engine.dxf.units import UNKNOWN_UNIT, DrawingUnits
from klave_engine.geometry.spatial_index import SpatialIndex
from klave_engine.graph.builder import DrawingGraph, build_drawing_graph
from klave_engine.ingestion.manifest import (
    ProcessingStatus,
    ProjectManifest,
    save_manifest,
)
from klave_engine.ingestion.project_loader import ingest_project
from klave_engine.llm.service import ai_element_specs, load_ai_reads
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
    conversions_path = processed / "conversion_results.json"
    conversions = read_json(conversions_path) if conversions_path.exists() else []
    write_json(processed / "parse_summary.json", _summarize_parse(drawings, conversions))
    write_json(processed / "layer_summary.json", summarize_layers(entities))
    write_json(processed / "block_summary.json", summarize_blocks(entities))
    attdefs: dict[str, list[str]] = {}
    for drawing in drawings:
        for name, tags in drawing.block_attdefs.items():
            merged = attdefs.setdefault(name, [])
            for tag in tags:
                if tag not in merged:
                    merged.append(tag)
    write_json(processed / "prefab_index.json", build_prefab_index(entities, attdefs))
    manifest.processing_status = ProcessingStatus.parsed
    save_manifest(manifest, settings.processed_dir_name)
    return drawings


def _summarize_parse(
    drawings: list[ParsedDrawing], conversions: list[dict] | None = None
) -> list[dict]:
    """Per-sheet legibility record: what was read, derived, and dropped.

    Cada archivo fuente lleva un veredicto de cobertura — ok, parcial o
    ilegible, con sus razones. Un DWG que no convirtió no tiene drawing:
    entra igual, como renglón ilegible, porque el silencio no es cobertura.
    """
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
                "block_attdefs": drawing.block_attdefs,
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
                "layouts": [layout.model_dump() for layout in drawing.layouts],
                "xrefs": [xref.model_dump() for xref in drawing.xrefs],
            }
        )
        reasons: list[str] = []
        if not drawing.entities:
            reasons.append("El archivo convirtió pero no trae entidades legibles.")
        if any(w.warning_type == "dxf_recovered" for w in drawing.warnings):
            reasons.append("Se leyó en modo de recuperación.")
        if any(w.warning_type == "block_explosion_capped" for w in drawing.warnings):
            reasons.append("Bloques con demasiadas entidades: se omitió una parte.")
        if any(w.warning_type == "block_nesting_truncated" for w in drawing.warnings):
            reasons.append("Bloques anidados a más de dos niveles: el fondo no se leyó.")
        if any(w.warning_type == "xref_missing" for w in drawing.warnings):
            reasons.append("Referencias externas ausentes: su geometría no entró.")
        summary[-1]["coverage"] = "parcial" if reasons else "ok"
        summary[-1]["coverage_reasons"] = reasons
    # Un DWG que no convirtió no aparece en drawings: su renglón se agrega
    # aquí, ilegible y con la razón del convertidor.
    for record in conversions or []:
        if record.get("status") != "failed":
            continue
        name = Path(str(record.get("source_path") or "")).name
        summary.append(
            {
                "source_file": name,
                "entity_count": 0,
                "coverage": "ilegible",
                "coverage_reasons": [
                    record.get("error_message") or "La conversión falló sin mensaje."
                ],
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
    catalog_store: CatalogStore | None = None,
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
    # Per-sheet units: each file's unit is read on its own and its geometry
    # scaled into the project's unit before anything measures it.
    units, file_units = harmonize_units(
        [(d.source_file, d.insunits, d.entities) for d in drawings]
    )
    result.entities = [e for d in drawings for e in d.entities]

    index = SpatialIndex(result.entities)
    write_json(processed / "spatial_index_summary.json", index.summary())

    # Twelve sheets in one project: the header unit of the sheets with the
    # most geometry wins (an índice saying inches must not rescale the
    # structural plan), and any disagreement is reported.
    for note in units.notes:
        if "se escaló" in note or "se asume" in note:
            result.warnings.append(note)
    write_json(
        processed / "file_units.json",
        [
            {"source_file": f.source_file, "unit": f.units.unit, "source": f.units.source,
             "confidence": f.units.confidence, "scale": f.scale, "entities": f.entity_count}
            for f in file_units
        ],
    )
    confirmed_unit = load_reviews(control_dir).verification.units_override
    if confirmed_unit:
        units = DrawingUnits(
            unit=confirmed_unit,
            source="confirmed",
            confidence=1.0,
            notes=[f"Unidad confirmada por el ingeniero: {confirmed_unit}"]
            + [f"Detección previa: {units.unit} ({units.source})"],
        )
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

    detector_config = load_detector_config(
        settings.detector_config_path, units, extent=index.extent()
    )
    if units.to_meters() is None:
        result.warnings.append(
            "Unidades del plano no confiables: los umbrales de detección siguen la "
            "extensión del dibujo y el presupuesto queda sin precio hasta confirmar la unidad."
        )
    # Every file is its own drawing space: frames (and, below, detectors)
    # run per file so one sheet's outlines never land inside another's.
    by_file: dict[str, list[NormalizedEntity]] = {}
    for entity in result.entities:
        by_file.setdefault(entity.source_file, []).append(entity)
    frames: list[SheetFrame] = []
    for file_entities in by_file.values():
        found = detect_frames(file_entities)
        for frame in found:
            frame.frame_id = f"frame_{len(frames):02d}"
            frames.append(frame)
    write_json(processed / "frames.json", frames)
    # Levantamiento: symbols and runs per sheet, counted before any price.
    sources_by_id = {src.file_id: src for src in manifest.source_files}
    sheet_names = {
        c.path: Path(sources_by_id[c.source_file_id].path).name
        for c in manifest.converted_files if c.source_file_id in sources_by_id
    }
    sheet_names.update({src.path: Path(src.path).name for src in manifest.source_files})
    inventory = build_inventory(result.entities, units, frames, sheet_names=sheet_names)
    write_json(processed / "inventory.json", inventory)
    # Cada hoja se lee con los detectores que le tocan. Los estructurales sólo
    # en hojas de estructura y arquitectura: en una de instalaciones sus
    # círculos y cajas son salidas y equipos, no zapatas. Los de instalaciones
    # corren en todas, porque un plano arquitectónico también trae contactos y
    # salidas — y ahí el filtro de capa y de bloque es el que decide.
    skipped_sheets = sorted(
        {
            sheet_names.get(source, source) for source in {e.source_file for e in result.entities}
            if not reads_as_structure(sheet_names.get(source, source))
        }
    )
    for sheet in skipped_sheets:
        result.warnings.append(
            f"Hoja «{sheet}» leída como instalaciones: se detectan sus muebles, "
            "salidas y corridas, no elementos estructurales."
        )
    # El nombre propone y el contenido vota: cuando contradicen, se avisa.
    # El reruteo espera a que cada suite tenga su propio gold.
    for source, file_entities in by_file.items():
        label = sheet_names.get(source, source)
        ruta = route_sheet(label)
        voto = vote_content(file_entities)
        if voto is not None and voto[0] != ruta.key:
            result.warnings.append(
                f"La hoja «{label}» se lee como {ruta.key} por su nombre; su "
                f"contenido vota {voto[0]} ({voto[1]} trazos). Revisa el nombre del archivo."
            )
    detector_ids = IdGenerator("det")
    for source, file_entities in by_file.items():
        file_frames = [f for f in frames if f.source_file == source]
        ruta_hoja = route_sheet(sheet_names.get(source, source))
        detector_outputs = run_detectors(
            file_entities, SpatialIndex(file_entities), manifest, detector_config,
            frames=file_frames, ids=detector_ids, units=units,
            structural=ruta_hoja.structural, suite=ruta_hoja,
        )
        for output in detector_outputs:
            result.warnings.extend(output.warnings)
            result.detections.extend(output.detections)
    # Where the sheet draws tableros, a large closed polyline is a notes box
    # or a detail, never a slab: the tablero reading is the authority. Con
    # marcos, la autoridad es por marco — una esquina sin panelizar de otro
    # marco del mismo archivo no pierde su losa. Sin marcos, por archivo.
    def _frame_key(detection) -> tuple[str, str | None]:
        cx = (detection.bbox[0] + detection.bbox[2]) / 2
        cy = (detection.bbox[1] + detection.bbox[3]) / 2
        for frame in frames:
            if frame.source_file == detection.evidence.source and frame.contains((cx, cy)):
                return (detection.evidence.source, frame.frame_id)
        return (detection.evidence.source, None)

    framed_files = {f.source_file for f in frames}
    panel_scopes = {
        _frame_key(d) if d.evidence.source in framed_files else (d.evidence.source, None)
        for d in result.detections
        if d.evidence.method == "slab_panel"
    }
    panel_files_unframed = {src for (src, fid) in panel_scopes if fid is None}
    if panel_scopes:
        def _outline_dropped(d) -> bool:
            if d.evidence.method != "slab_region_from_large_closed_polyline":
                return False
            if d.evidence.source in framed_files:
                return _frame_key(d) in panel_scopes
            return d.evidence.source in panel_files_unframed

        kept = [d for d in result.detections if not _outline_dropped(d)]
        dropped = len(result.detections) - len(kept)
        if dropped:
            result.detections = kept
            log_stage(
                logger, "legacy_slab_outlines_dropped", dropped=dropped,
                files=sorted({src for (src, _fid) in panel_scopes}),
            )
    # What the sheet declares about its marks outranks measured markers and
    # assumptions: stamp sections from cuadros, details, and notes first.
    schedule = build_schedule_inventory(
        result.entities,
        detector_config.text_patterns,
        unit_to_m=units.to_meters(),
        detail_boxes=[f.bbox for f in frames if f.kind == "excluded"],
    )
    ai_reads = load_ai_reads(control_dir)
    if ai_reads.readings:
        merge_external_specs(schedule, ai_element_specs(ai_reads))
        for reading in ai_reads.readings:
            for family, fc in reading.read.concrete_fc.items():
                schedule.concrete_fc.setdefault(family.lower(), int(fc))
    cuadro_tagged = mark_cuadro_detections(result.detections, schedule)
    if cuadro_tagged:
        schedule.notes.append(
            f"{cuadro_tagged} marcas de cuadro dibujado en planta no se cuentan como elementos."
        )
    stamped = apply_schedule(result.detections, schedule, units.to_meters())
    if stamped:
        schedule.notes.append(f"{stamped} detecciones tomaron su sección del plano.")
    # Then the engineer's cotas: footing sizes, wall thickness, and sections
    # for marks no cuadro covered.
    links = link_dimensions(result.detections, result.entities, units.to_meters())
    if links.total:
        schedule.notes.append(
            f"Cotas asociadas a elementos: {links.footings} zapatas, "
            f"{links.columns} columnas/castillos, {links.walls} muros."
        )
    write_json(processed / "schedules.json", schedule)
    enrich_detections(result.detections, units.to_meters())

    graph = build_drawing_graph(manifest.project_id, drawings, result.detections)
    result.graph = graph

    write_json(processed / "drawing_graph.json", graph.to_export(manifest.project_id))
    # detections.json se escribe una sola vez, después del etiquetado de
    # pretiles de azotea: un lector intermedio no debe ver datos sin on_roof.

    result.quantity_report = generate_quantity_report(
        manifest.project_id,
        result.detections,
        assumed_unit=units.unit if units.reliable else UNKNOWN_UNIT,
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

    segmentation = segment_views(result.entities, result.detections, frames)
    write_json(processed / "views.json", segmentation)
    # A wall drawn on the azotea planta is a pretil: knee-high, not a story.
    roof_views = {
        v.view_id for v in segmentation.plan_views() if v.level_key == "azotea"
    }
    if roof_views:
        tagged = 0
        for detection in result.detections:
            if (
                detection.detection_type == DetectionType.wall
                and segmentation.assignment.get(detection.detection_id) in roof_views
            ):
                detection.properties["on_roof"] = True  # a pretil: costed knee-high
                tagged += 1
    # Las bajadas se ligan entre plantas por posición; con niveles N.P.T.
    # declarados, el tiro mide su tramo vertical (SAN-006).
    stamped_stacks = stamp_bajada_stacks(
        result.detections, frames, segmentation, units.to_meters()
    )
    if stamped_stacks:
        log_stage(logger, "bajada_stacks_stamped", stacks=stamped_stacks)
    # Áreas de acabado por clave: lo que el local declara, agregado para que
    # el taller lo mapee. Sin unidad confiable no hay m² (regla A6).
    to_m = units.to_meters()
    acabados_resumen: dict[tuple[str, str], dict] = {}
    sin_acabado = 0
    for detection in result.detections:
        if detection.detection_type != DetectionType.room:
            continue
        props = detection.properties or {}
        tiene = False
        for tipo, prop in (("piso", "piso_clave"), ("plafon", "plafon_clave")):
            clave = props.get(prop)
            if not clave:
                continue
            tiene = True
            area_du2 = float(props.get("estimated_area") or 0.0)
            registro = acabados_resumen.setdefault(
                (tipo, str(clave)),
                {"tipo": tipo, "clave": str(clave), "area_du2": 0.0,
                 "area_m2": 0.0 if to_m else None, "locales": 0},
            )
            registro["area_du2"] = round(registro["area_du2"] + area_du2, 4)
            if to_m:
                registro["area_m2"] = round(
                    (registro["area_m2"] or 0.0) + area_du2 * to_m * to_m, 2
                )
            registro["locales"] += 1
        if not tiene:
            sin_acabado += 1
    if acabados_resumen:
        write_json(
            processed / "acabados.json",
            sorted(acabados_resumen.values(), key=lambda r: (r["tipo"], r["clave"])),
        )
        if sin_acabado:
            result.warnings.append(
                f"{sin_acabado} locales sin clave de acabado: su área no pertenece "
                "a ningún acabado declarado."
            )
    write_json(processed / "detections.json", result.detections)
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
    catalog_store = catalog_store or get_catalog_store(settings.data_dir)
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
        schedule_specs=schedule.model_dump(),
        rendimientos=catalog_store.load_rendimientos(),
        adjustments=reviews.adjustments,
        store_concepts=catalog_store.load_concepts(),
        concept_prices=catalog_store.load_concept_prices(),
        inventory=inventory.model_dump(),
        inventory_mappings=catalog_store.list_inventory_mappings(),
        concept_aliases=catalog_store.load_concept_aliases(),
        parametric_rules=catalog_store.list_parametric_rules(),
        plantillas=catalog_store.list_plantillas(),
        price_vigencias=catalog_store.price_vigencias(),
    )
    # El detector conoce denominadores que el presupuesto no ve; viaja al
    # diagnóstico solo lo que sus reglas saben clasificar.
    result.cost_report.warnings.extend(
        w for w in promote_detection_warnings(result.warnings)
        if w not in result.cost_report.warnings
    )
    write_json(processed / "cost_report.json", result.cost_report)
    write_json(
        processed / "engine.json",
        {**engine_stamp(), "processed_at": datetime.now(UTC).isoformat()},
    )
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
