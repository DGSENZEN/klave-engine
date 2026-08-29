"""La suite de albañilería: el tabique con su descuento.

Los muros de una hoja de albañilería son tabique salvo que su capa diga
concreto: se leen con el detector de muros de siempre, estampados
``wall_kind: "tabique"`` para que ALB-001 los cobre en m² con su vano
descontado (A4) — y EST-004, que filtra block/None, no los toque. Los del
fondo arquitectónico embebido cuentan aquí como muros de la disciplina:
esta ES la hoja donde la albañilería se cobra.
"""

from __future__ import annotations

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.fixture_detector import detect_fixtures
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.opening_detector import detect_openings
from klave_engine.detection.results import DetectorOutput, layer_matches
from klave_engine.detection.run_detector import detect_runs
from klave_engine.detection.wall_detector import detect_walls
from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.geometry.spatial_index import SpatialIndex

_CONCRETO = ["CONCRETO", "CONCRETE", "MURO CONC", "PANTALLA"]


def detect(
    entities: list[NormalizedEntity],
    config,
    ids: IdGenerator,
    meters_factor: float | None,
    frames: list[SheetFrame],
) -> list[DetectorOutput]:
    frame_boxes = [f.bbox for f in frames]
    index = SpatialIndex(entities)
    walls = detect_walls(entities, index, config.wall, ids)
    for detection in walls.detections:
        kind = detection.properties.get("wall_kind")
        layer = str(detection.properties.get("layer") or detection.label or "")
        if kind == "concreto" or layer_matches(layer, _CONCRETO):
            continue  # el concreto es de estructura aunque esté en esta hoja
        detection.properties["wall_kind"] = "tabique"
        detection.evidence.notes.append(
            "Muro de la hoja de albañilería: tabique salvo que la capa diga concreto."
        )
    return [
        walls,
        detect_fixtures(entities, config.fixture, ids, meters_factor),
        detect_runs(entities, config.run, ids, meters_factor, frame_boxes),
        detect_openings(entities, walls.detections, config.opening, ids, meters_factor),
    ]
