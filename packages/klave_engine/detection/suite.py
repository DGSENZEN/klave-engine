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
from klave_engine.detection.grid_detector import GridDetectorConfig, detect_grid
from klave_engine.detection.results import DetectorOutput
from klave_engine.detection.slab_detector import SlabDetectorConfig, detect_slabs
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.detection.wall_detector import WallDetectorConfig, detect_walls
from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.dxf.units import DrawingUnits
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
    wall: WallDetectorConfig = Field(default_factory=WallDetectorConfig)
    detail_reference: DetailReferenceDetectorConfig = Field(
        default_factory=DetailReferenceDetectorConfig
    )
    risk: RiskEngineConfig = Field(default_factory=RiskEngineConfig)

    @classmethod
    def preset_for_units(cls, units: DrawingUnits) -> "DetectorSuiteConfig":
        """Detector thresholds scaled to real-world units when they are known.

        The reference preset is defined in meters (validated against a real
        structural sheet) and scaled to the drawing unit; unknown units keep
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
        return config


def load_detector_config(
    path: Path | None, units: DrawingUnits | None = None
) -> DetectorSuiteConfig:
    if path is not None and path.exists():
        return DetectorSuiteConfig.model_validate(read_json(path))
    if units is not None:
        return DetectorSuiteConfig.preset_for_units(units)
    return DetectorSuiteConfig()


def run_detectors(
    entities: list[NormalizedEntity],
    index: SpatialIndex,
    manifest: ProjectManifest,
    config: DetectorSuiteConfig,
) -> list[DetectorOutput]:
    """Run every detector in dependency order (grid → columns → footings …)."""
    ids = IdGenerator("det")
    grid = detect_grid(entities, index, config.grid, config.text_patterns, ids)
    columns = detect_columns(entities, index, grid, config.column, config.text_patterns, ids)
    footings = detect_footings(entities, index, columns, config.footing, ids)
    beams = detect_beams(entities, index, config.beam, config.text_patterns, ids)
    slabs = detect_slabs(entities, config.slab, ids)
    walls = detect_walls(entities, index, config.wall, ids)
    details = detect_detail_references(
        entities, manifest, config.detail_reference, config.text_patterns, ids
    )
    return [grid, columns, footings, beams, slabs, walls, details]
