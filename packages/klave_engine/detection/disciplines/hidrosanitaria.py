"""La suite hidrosanitaria: el primer inquilino del hueco ``detect``.

v1 lee lo que el trío de instalaciones ya leía — muebles, corridas (ahora
por tramo de diámetro) y vanos — pero como suite del registro: el punto de
entrada donde las siguientes rondas agregan lo suyo sin tocar el cableado
general. La liga de bajadas entre niveles corre en el pipeline porque
necesita las vistas segmentadas, que no existen a la hora de detectar.
"""

from __future__ import annotations

from klave_engine.common.ids import IdGenerator
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
    frame_boxes = [f.bbox for f in frames]
    return [
        detect_fixtures(entities, config.fixture, ids, meters_factor),
        detect_runs(entities, config.run, ids, meters_factor, frame_boxes),
        detect_openings(entities, [], config.opening, ids, meters_factor),
    ]
