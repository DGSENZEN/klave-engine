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

    sueltas = 0
    for mark in marks.detections:
        mx = (mark.bbox[0] + mark.bbox[2]) / 2
        my = (mark.bbox[1] + mark.bbox[3]) / 2
        local = next(
            (r for r in rooms.detections
             if r.bbox[0] <= mx <= r.bbox[2] and r.bbox[1] <= my <= r.bbox[3]),
            None,
        )
        if local is None:
            sueltas += 1
            continue
        prop = _CLAVE_PROP[mark.properties["acabado_tipo"]]
        local.properties[prop] = mark.properties["clave"]
        local.evidence.notes.append(
            f"Acabado de {mark.properties['acabado_tipo']}: clave "
            f"{mark.properties['clave']}, de la marca parada en el local."
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
