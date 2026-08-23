"""Detector suite: aggregate config, unit-scaled presets, and the run step.

Keeps all detector wiring in the detection layer so ``pipeline`` stays pure
orchestration.
"""

from pathlib import Path

from pydantic import BaseModel, Field

from klave_engine.common.ids import IdGenerator
from klave_engine.common.io import read_json
from klave_engine.detection.beam_detector import BeamDetectorConfig, detect_beams
from klave_engine.detection.column_detector import ColumnDetectorConfig, detect_columns
from klave_engine.detection.detail_reference_detector import (
    DetailReferenceDetectorConfig,
    detect_detail_references,
)
from klave_engine.detection.footing_detector import FootingDetectorConfig, detect_footings
from klave_engine.detection.frames import SheetFrame, frame_boxes
from klave_engine.detection.grid_detector import GridDetectorConfig, detect_grid
from klave_engine.detection.pile_detector import PileDetectorConfig, detect_piles
from klave_engine.detection.results import DetectorOutput
from klave_engine.detection.rooms import RoomDetectorConfig, detect_rooms
from klave_engine.detection.slab_detector import SlabDetectorConfig, detect_slabs
from klave_engine.detection.slab_panels import SlabPanelConfig, detect_slab_panels
from klave_engine.detection.terrain import TerrainDetectorConfig, detect_terrain
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.detection.wall_detector import WallDetectorConfig, detect_walls
from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.dxf.units import METERS_FACTOR, DrawingUnits, vote_from_extent
from klave_engine.geometry.bbox import BBox
from klave_engine.geometry.spatial_index import SpatialIndex
from klave_engine.ingestion.manifest import ProjectManifest
from klave_engine.risks.rules import RiskEngineConfig


class DetectorSuiteConfig(BaseModel):
    """Aggregate configuration for all detectors; overridable from a JSON file."""

    text_patterns: TextPatternConfig = Field(default_factory=TextPatternConfig)
    grid: GridDetectorConfig = Field(default_factory=GridDetectorConfig)
    column: ColumnDetectorConfig = Field(default_factory=ColumnDetectorConfig)
    footing: FootingDetectorConfig = Field(default_factory=FootingDetectorConfig)
    beam: BeamDetectorConfig = Field(default_factory=BeamDetectorConfig)
    slab: SlabDetectorConfig = Field(default_factory=SlabDetectorConfig)
    slab_panel: SlabPanelConfig = Field(default_factory=SlabPanelConfig)
    pile: PileDetectorConfig = Field(default_factory=PileDetectorConfig)
    wall: WallDetectorConfig = Field(default_factory=WallDetectorConfig)
    room: RoomDetectorConfig = Field(default_factory=RoomDetectorConfig)
    terrain: TerrainDetectorConfig = Field(default_factory=TerrainDetectorConfig)
    detail_reference: DetailReferenceDetectorConfig = Field(
        default_factory=DetailReferenceDetectorConfig
    )
    risk: RiskEngineConfig = Field(default_factory=RiskEngineConfig)

    @classmethod
    def preset_for_units(
        cls, units: DrawingUnits, extent: BBox | None = None
    ) -> "DetectorSuiteConfig":
        """Detector thresholds scaled to real-world units when they are known.

        The reference preset is defined in meters (validated against a real
        structural sheet) and scaled to the drawing unit. When the unit is
        not reliable, the model's extent still says what it most likely is
        (a building is tens of metres across) and the thresholds follow that
        guess — the money never does; it waits for a confirmed unit.
        """
        factor = units.to_meters()
        if factor is None and extent is not None:
            guess = vote_from_extent(extent)
            if guess is not None:
                factor = METERS_FACTOR.get(guess[0])
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
        config.footing.strip_max_width = m(1.5)
        config.footing.mark_search_radius = m(1.2)
        config.beam.line_search_radius = m(1.0)
        config.beam.min_beam_length = m(1.5)
        config.beam.max_beam_length = m(15.0)
        # A 3×3 m panel is a real slab (a small room); cuadros and notes
        # are kept out by the avoid layers and the frame-share guard.
        config.slab.min_area = m(3.0) * m(3.0)
        config.slab_panel.min_area = m(1.0) * m(1.0)
        config.slab_panel.max_area = m(20.0) * m(20.0)
        config.slab_panel.min_width = m(0.6)
        config.slab_panel.edge_tolerance = m(0.03)
        config.slab_panel.label_search_radius = m(30.0)
        config.slab_panel.family_inherit_radius = m(6.0)
        config.slab_panel.pattern_outline_min_area = m(2.0) * m(2.0)
        config.pile.circle_search_radius = m(1.5)
        config.pile.min_diameter = m(0.2)
        config.pile.max_diameter = m(2.5)
        config.wall.min_length = m(1.5)
        config.wall.max_thickness = m(0.45)
        config.wall.min_thickness = m(0.05)
        config.wall.merge_gap = m(0.30)
        config.wall.opening_gap_max = m(1.30)
        config.room.min_area = m(1.0) * m(1.5)
        config.room.max_area = m(20.0) * m(20.0)
        config.room.min_width = m(0.7)
        config.room.unnamed_note_area = m(2.0) * m(2.0)
        config.room.label_max_height = m(0.6)
        config.room.max_opening = m(1.3)
        config.room.max_thickness = m(0.45)
        config.terrain.label_search_radius = m(1.0)
        config.risk.duplicate_column_distance = m(10.0)
        return config


def load_detector_config(
    path: Path | None, units: DrawingUnits | None = None, extent: BBox | None = None
) -> DetectorSuiteConfig:
    if path is not None and path.exists():
        return DetectorSuiteConfig.model_validate(read_json(path))
    if units is not None:
        return DetectorSuiteConfig.preset_for_units(units, extent)
    return DetectorSuiteConfig()


def run_detectors(
    entities: list[NormalizedEntity],
    index: SpatialIndex,
    manifest: ProjectManifest,
    config: DetectorSuiteConfig,
    frames: list[SheetFrame] | None = None,
    ids: IdGenerator | None = None,
) -> list[DetectorOutput]:
    """Run every detector in dependency order (grid → columns → footings …)."""
    ids = ids or IdGenerator("det")
    grid = detect_grid(entities, index, config.grid, config.text_patterns, ids)
    columns = detect_columns(entities, index, grid, config.column, config.text_patterns, ids)
    footings = detect_footings(entities, index, columns, config.footing, ids)
    beams = detect_beams(entities, index, config.beam, config.text_patterns, ids)
    slabs = detect_slabs(entities, config.slab, ids, frame_boxes(frames or []))
    panels = detect_slab_panels(entities, config.slab_panel, ids, frame_boxes(frames or []))
    if panels.detections:
        _prefer_panels(slabs, panels)
    walls = detect_walls(entities, index, config.wall, ids)
    piles = detect_piles(entities, index, config.pile, ids)
    rooms = detect_rooms(entities, config.room, ids, frame_boxes(frames or []))
    terrain = detect_terrain(entities, config.terrain, ids)
    details = detect_detail_references(
        entities, manifest, config.detail_reference, config.text_patterns, ids
    )
    return [
        grid, columns, footings, beams, slabs, panels, walls, piles, rooms, terrain, details,
    ]


def _prefer_panels(slabs: DetectorOutput, panels: DetectorOutput) -> None:
    """Where tableros were read from the beam network, the outline-based
    guesses that overlap them (terrain hatches, wall outlines, the building
    outline itself) are dropped; elsewhere they stay as the fallback."""
    boxes = [p.bbox for p in panels.detections]

    def overlaps(bbox: tuple[float, float, float, float]) -> bool:
        return any(
            bbox[0] < b[2] and b[0] < bbox[2] and bbox[1] < b[3] and b[1] < bbox[3]
            for b in boxes
        )

    kept = [d for d in slabs.detections if not overlaps(d.bbox)]
    dropped = len(slabs.detections) - len(kept)
    slabs.detections = kept
    if dropped:
        slabs.warnings.append(
            f"{dropped} regiones de losa por contorno se descartaron: los tableros "
            "acotados por trabes las reemplazan."
        )
