"""The coverage audit: the engine finding out what it missed.

The vision model counts, per sheet, how many instances of each countable
family are drawn; the rule detectors already counted what they saw. A
disagreement never changes a quantity — it flags the sheet: «en S-02 la IA
cuenta 6 castillos; el motor detectó 4 — revisa esa hoja». Silent recall
failures become review tasks, which is the entire difference between a
wrong presupuesto and an honest one.

Only discrete families are compared (castillos, columnas, trabes, zapatas,
pilotes, escaleras…). Continuous ones (muros, losas) have no natural
instance count and would only produce noise.
"""

from pydantic import BaseModel

from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import Detection

# AI vocabulary → the engine families it should be compared against.
COUNTABLE: dict[str, set[str]] = {
    "castillo": {"castillo"},
    "columna": {"columna"},
    "trabe": {"trabe"},
    "contratrabe": {"contratrabe"},
    "dala": {"dala"},
    "cerramiento": {"cerramiento"},
    "zapata": {"zapata"},
    "pilote": {"pilote"},
    "escalera": {"escalera"},
}


class CoverageFlag(BaseModel):
    frame_code: str
    family: str
    ai_count: int
    engine_count: int
    # faltante: the model sees more than the engine detected (possible recall
    # gap — the important direction). sobrante: the engine detected more than
    # the model counts (usually harmless; the model miscounts dense sheets).
    kind: str  # "faltante" | "sobrante"


def _engine_counts(detections: list[Detection], frame: SheetFrame) -> dict[str, int]:
    counts: dict[str, int] = {}
    for detection in detections:
        if detection.evidence.source and frame.source_file:
            if detection.evidence.source != frame.source_file:
                continue
        box = detection.bbox
        center = ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)
        if not frame.contains(center):
            continue
        counts[detection.family] = counts.get(detection.family, 0) + 1
    return counts


def coverage_flags(
    readings: list[dict],
    detections: list[Detection],
    frames: list[SheetFrame],
) -> list[CoverageFlag]:
    """Compare each reading's conteo with the engine's detections in that
    frame. ``readings`` are stored SheetReading dicts (frame_code + read)."""
    by_code = {frame.code: frame for frame in frames if frame.code}
    flags: list[CoverageFlag] = []
    for reading in readings:
        code = reading.get("frame_code") or ""
        frame = by_code.get(code)
        if frame is None:
            continue
        conteo = (reading.get("read") or {}).get("conteo") or []
        if not conteo:
            continue
        engine = _engine_counts(detections, frame)
        for entry in conteo:
            family = str(entry.get("family", "")).strip().lower()
            engine_families = COUNTABLE.get(family)
            if engine_families is None:
                continue
            try:
                ai_count = int(entry.get("drawn_count", 0))
            except (TypeError, ValueError):
                continue
            engine_count = sum(engine.get(f, 0) for f in engine_families)
            if ai_count == engine_count or (ai_count == 0 and engine_count == 0):
                continue
            flags.append(
                CoverageFlag(
                    frame_code=code,
                    family=family,
                    ai_count=ai_count,
                    engine_count=engine_count,
                    kind="faltante" if ai_count > engine_count else "sobrante",
                )
            )
    # The recall direction first, biggest gaps first.
    flags.sort(key=lambda f: (f.kind != "faltante", -(abs(f.ai_count - f.engine_count))))
    return flags
