"""Las bajadas ligadas entre niveles: un tiro vertical, no N símbolos.

El símbolo de subida-bajada se dibuja en cada planta donde la tubería
cambia de nivel — el mismo tiro aparece una vez por nivel, en la misma
posición del edificio. Ligarlos por su posición relativa al marco convierte
N símbolos en una columna con niveles, y cuando las plantas declaran su
N.P.T., en los metros del tramo vertical — los metros que la corrida en
planta nunca dibuja y que antes no cobraba nadie.

Nada se inventa: sin niveles declarados el tiro se liga igual (la posición
lo dice) pero no declara metros, y el diagnóstico dice por qué.
"""

from __future__ import annotations

import math
from pathlib import Path

from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import Detection, DetectionType
from klave_engine.detection.views import SheetSegmentation

# Dos símbolos a menos de esto (en metros) en plantas distintas son el
# mismo tiro: los planos repiten la posición con precisión de dibujo.
STACK_TOLERANCE_M = 0.5


def _frame_of(detection: Detection, frames: list[SheetFrame]) -> SheetFrame | None:
    cx = (detection.bbox[0] + detection.bbox[2]) / 2
    cy = (detection.bbox[1] + detection.bbox[3]) / 2
    source = detection.evidence.source
    for frame in frames:
        if frame.source_file != source and Path(frame.source_file).name != Path(source).name:
            continue
        if frame.contains((cx, cy)):
            return frame
    return None


def stamp_bajada_stacks(
    detections: list[Detection],
    frames: list[SheetFrame],
    segmentation: SheetSegmentation | None,
    meters_factor: float | None,
) -> int:
    """Liga las bajadas entre plantas y estampa el tiro. Regresa cuántos
    tiros (de ≥2 niveles) se ligaron."""
    if meters_factor is None or not frames:
        return 0
    tolerance = STACK_TOLERANCE_M / meters_factor
    npt_by_frame: dict[str, float] = {
        v.view_id: v.npt_level
        for v in (segmentation.views if segmentation else [])
        if v.npt_level is not None
    }

    bajadas: list[tuple[Detection, SheetFrame, tuple[float, float]]] = []
    for detection in detections:
        if detection.detection_type != DetectionType.fixture:
            continue
        if (detection.properties or {}).get("fixture_family") != "bajada":
            continue
        frame = _frame_of(detection, frames)
        if frame is None:
            continue
        cx = (detection.bbox[0] + detection.bbox[2]) / 2
        cy = (detection.bbox[1] + detection.bbox[3]) / 2
        bajadas.append((detection, frame, (cx - frame.bbox[0], cy - frame.bbox[1])))

    stacks = 0
    used: set[str] = set()
    for seed, seed_frame, seed_pos in bajadas:
        if seed.detection_id in used:
            continue
        members = [(seed, seed_frame)]
        taken_frames = {seed_frame.frame_id}
        for other, frame, pos in bajadas:
            if other.detection_id in used or other.detection_id == seed.detection_id:
                continue
            if frame.frame_id in taken_frames or frame.source_file != seed_frame.source_file:
                continue
            if math.dist(seed_pos, pos) <= tolerance:
                members.append((other, frame))
                taken_frames.add(frame.frame_id)
        if len(members) < 2:
            continue
        stacks += 1
        stack_id = f"bajada-{Path(seed_frame.source_file).stem[:24]}-{stacks:02d}"
        for detection, _frame in members:
            used.add(detection.detection_id)
            detection.properties["stack_id"] = stack_id
            detection.properties["stack_levels"] = len(members)
        levels = sorted(
            npt_by_frame[frame.frame_id]
            for _det, frame in members
            if frame.frame_id in npt_by_frame
        )
        if len(levels) >= 2 and levels[-1] > levels[0]:
            vertical_m = round(levels[-1] - levels[0], 2)
            representative = min(
                members,
                key=lambda m: npt_by_frame.get(m[1].frame_id, float("inf")),
            )[0]
            # El tramo vive en UNA representante: un tiro es una columna.
            representative.properties["vertical_length_m"] = vertical_m
            representative.properties["vertical_length_du"] = round(
                vertical_m / meters_factor, 4
            )
            representative.evidence.notes.append(
                f"Tiro vertical de {vertical_m:.2f} m: {len(members)} niveles ligados "
                "por posición, medido de los N.P.T. declarados."
            )
    return stacks
