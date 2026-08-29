"""La suite de cancelería: la pieza con clave manda.

Primero las piezas (el globo de nomenclatura con su clave), luego el trío
de instalaciones — con los vanos del detector genérico filtrados: el mismo
insert no puede ser una pieza y además un vano. La geometría del alzado
acotado (las dimensiones por clave) queda para la siguiente ronda.
"""

from __future__ import annotations

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.cancel_pieces import detect_cancel_pieces
from klave_engine.detection.fixture_detector import detect_fixtures
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.opening_detector import detect_openings
from klave_engine.detection.results import DetectorOutput
from klave_engine.detection.run_detector import detect_runs
from klave_engine.dxf.entities import NormalizedEntity


def detect(
    entities: list[NormalizedEntity],
    config,
    ids: IdGenerator,
    meters_factor: float | None,
    frames: list[SheetFrame],
) -> list[DetectorOutput]:
    pieces = detect_cancel_pieces(entities, ids)
    claimed = {
        entity_id
        for detection in pieces.detections
        for entity_id in detection.source_entities
    }
    openings = detect_openings(entities, [], config.opening, ids, meters_factor)
    openings.detections = [
        d for d in openings.detections
        if not set(d.source_entities) & claimed
    ]
    frame_boxes = [f.bbox for f in frames]
    return [
        pieces,
        detect_fixtures(entities, config.fixture, ids, meters_factor),
        detect_runs(entities, config.run, ids, meters_factor, frame_boxes),
        openings,
    ]
