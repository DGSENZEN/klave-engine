"""La ruta de arquitectura: el fondo que se ve, ancla y jamás cobra.

El plano arquitectónico (o su xref) es el sustrato del proyecto: sus muros
cierran los locales, sus niveles ordenan las plantas, y su geometría dibuja
el contexto en el visor. Pero no es una partida — sus muros ya los cobra la
disciplina a la que pertenecen (albañilería, estructura) en SU hoja. Todo
lo que esta suite detecta sale estampado ``substrate: true``, y el
presupuesto lo ignora por regla general (spec §9).
"""

from __future__ import annotations

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.fixture_detector import detect_fixtures
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.opening_detector import detect_openings
from klave_engine.detection.results import DetectorOutput
from klave_engine.detection.rooms import detect_rooms
from klave_engine.detection.run_detector import detect_runs
from klave_engine.detection.wall_detector import detect_walls
from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.geometry.spatial_index import SpatialIndex


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
    rooms = detect_rooms(entities, config.room, ids, frame_boxes)
    for output in (walls, rooms):
        for detection in output.detections:
            detection.properties["substrate"] = True
            detection.evidence.notes.append(
                "Fondo arquitectónico: geometría de referencia, no partida."
            )
    return [
        walls,
        rooms,
        detect_fixtures(entities, config.fixture, ids, meters_factor),
        detect_runs(entities, config.run, ids, meters_factor, frame_boxes),
        detect_openings(entities, [], config.opening, ids, meters_factor),
    ]
