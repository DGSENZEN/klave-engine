"""La suite de acabados: el local sabe su piso y su plafón.

El fondo arquitectónico embebido da los locales (rooms); las marcas PI/PL
con su clave dicen qué acabado lleva cada uno. La suite detecta ambos y los
casa: la marca parada dentro del local le estampa su clave, y el área del
local es el m² de ese acabado — leído, no supuesto. Las marcas fuera de
todo local se quedan contadas con aviso.
"""

from __future__ import annotations

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.acabado_marks import detect_acabado_marks
from klave_engine.detection.fixture_detector import detect_fixtures
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.opening_detector import detect_openings
from klave_engine.detection.results import DetectorOutput
from klave_engine.detection.rooms import detect_rooms
from klave_engine.detection.run_detector import detect_runs
from klave_engine.dxf.entities import NormalizedEntity

_CLAVE_PROP = {"piso": "piso_clave", "plafon": "plafon_clave"}
# La marca suele pararse junto al muro del local, no en su centroide:
# estricto primero, cerca después — y de otro marco, jamás.
MARK_TOLERANCE_M = 2.0


def _frame_of(bbox, frames: list[SheetFrame]) -> str | None:
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    for frame in frames:
        if frame.contains((cx, cy)):
            return frame.frame_id
    return None


def _bbox_distance(point: tuple[float, float], bbox) -> float:
    dx = max(bbox[0] - point[0], 0.0, point[0] - bbox[2])
    dy = max(bbox[1] - point[1], 0.0, point[1] - bbox[3])
    return (dx * dx + dy * dy) ** 0.5


def _match_marks_to_rooms(
    marks, rooms, frames: list[SheetFrame], meters_factor: float | None
) -> int:
    """Estampa la clave de cada marca en su local. Regresa las sueltas."""
    tolerance = MARK_TOLERANCE_M / meters_factor if meters_factor else MARK_TOLERANCE_M
    room_frames = {r.detection_id: _frame_of(r.bbox, frames) for r in rooms}
    sueltas = 0
    for mark in marks:
        cx = (mark.bbox[0] + mark.bbox[2]) / 2
        cy = (mark.bbox[1] + mark.bbox[3]) / 2
        mark_frame = _frame_of(mark.bbox, frames)
        best = None
        for room in rooms:
            if room_frames[room.detection_id] != mark_frame:
                continue
            distance = _bbox_distance((cx, cy), room.bbox)
            if distance <= tolerance and (best is None or distance < best[0]):
                best = (distance, room)
        if best is None:
            sueltas += 1
            continue
        local = best[1]
        prop = _CLAVE_PROP[mark.properties["acabado_tipo"]]
        local.properties[prop] = mark.properties["clave"]
        local.evidence.notes.append(
            f"Acabado de {mark.properties['acabado_tipo']}: clave "
            f"{mark.properties['clave']}"
            + (", de la marca parada en el local."
               if best[0] == 0 else f", de la marca a {best[0]:.1f} u. del local.")
        )
    return sueltas


def detect(
    entities: list[NormalizedEntity],
    config,
    ids: IdGenerator,
    meters_factor: float | None,
    frames: list[SheetFrame],
) -> list[DetectorOutput]:
    frame_boxes = [f.bbox for f in frames]
    marks = detect_acabado_marks(entities, ids)
    # Las marcas anclan los locales: Marina no los nombra, pero los marca.
    anchors = [
        ((d.bbox[0] + d.bbox[2]) / 2, (d.bbox[1] + d.bbox[3]) / 2)
        for d in marks.detections
    ]
    rooms = detect_rooms(entities, config.room, ids, frame_boxes, anchor_points=anchors)
    claimed = {
        entity_id for d in marks.detections for entity_id in d.source_entities
    }

    sueltas = _match_marks_to_rooms(
        marks.detections, rooms.detections, frames, meters_factor
    )
    if sueltas:
        marks.warnings.append(
            f"{sueltas} de {len(marks.detections)} marcas de acabado fuera de todo "
            "local: su clave no tiene área a la cual pertenecer."
        )

    fixtures = detect_fixtures(entities, config.fixture, ids, meters_factor)
    fixtures.detections = [
        d for d in fixtures.detections if not set(d.source_entities) & claimed
    ]
    return [
        rooms,
        marks,
        fixtures,
        detect_runs(entities, config.run, ids, meters_factor, frame_boxes),
        detect_openings(entities, [], config.opening, ids, meters_factor),
    ]
