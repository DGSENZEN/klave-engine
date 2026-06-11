"""Shared fixtures: a deterministic demo project, parsed entities, and indexes."""

from pathlib import Path

import pytest
from klave_engine.dxf.parser import DxfParser, ParsedDrawing
from klave_engine.evals.fixtures import write_demo_project
from klave_engine.geometry.spatial_index import SpatialIndex
from klave_engine.ingestion.manifest import ProjectManifest
from klave_engine.ingestion.project_loader import ingest_project


@pytest.fixture(scope="session")
def demo_project_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("demo") / "demo_project_001"
    write_demo_project(root)
    return root


@pytest.fixture(scope="session")
def demo_manifest(demo_project_root: Path) -> ProjectManifest:
    return ingest_project(demo_project_root)


@pytest.fixture(scope="session")
def demo_drawing(demo_project_root: Path) -> ParsedDrawing:
    return DxfParser().parse_file(demo_project_root / "drawings" / "S-101.dxf")


@pytest.fixture(scope="session")
def demo_entities(demo_drawing: ParsedDrawing):
    return demo_drawing.entities


@pytest.fixture(scope="session")
def demo_index(demo_entities) -> SpatialIndex:
    return SpatialIndex(demo_entities)
