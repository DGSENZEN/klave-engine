"""La referencia de cada elemento: qué es, en qué hoja y planta, cerca de qué
ejes, y cómo verlo — lo que un supervisor pide en un número generador.

Nada se inventa: los ejes se citan sólo cuando el plano los nombró (una malla
con nombres automáticos «V1, V2» no es la que el supervisor ve), y la planta
sale del marco al que el motor asignó el elemento.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import PurePath
from urllib.parse import quote

from klave_engine.detection.results import Detection, DetectionType
from klave_engine.detection.views import SheetSegmentation

# Radio para citar un eje, en metros: un elemento a más de esto de un eje no
# «está en» ese eje.
EJE_RADIO_M = 1.5


@dataclass(frozen=True)
class Referencia:
    element_id: str
    hoja: str
    planta: str
    ejes: str
    visor: str  # ruta relativa del visor con el elemento encuadrado


def _centro(d: Detection) -> tuple[float, float]:
    x0, y0, x1, y1 = d.bbox
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0


def element_id(detection: Detection, meters_factor: float | None) -> str:
    """Identidad estable del elemento: misma hoja, tipo, marca y posición
    (a 5 cm) dan el mismo id en un reproceso."""
    factor = meters_factor or 1.0
    cx, cy = _centro(detection)
    q = 0.05 / factor if factor > 0 else 0.05
    key = "|".join([
        PurePath(detection.evidence.source or "").name,
        detection.detection_type.value,
        detection.mark or "",
        str(round(cx / q)),
        str(round(cy / q)),
    ])
    return "el_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


@lru_cache(maxsize=4096)
def _hoja(source: str) -> str:
    return PurePath(source).name


def _ejes_con_nombre(grid_lines: list[Detection]) -> list[Detection]:
    """Los ejes que el plano nombra (los automáticos no son referencia)."""
    return [
        g for g in grid_lines
        if (g.properties or {}).get("label_source") != "auto" and g.label
        and (g.properties or {}).get("axis") in ("vertical", "horizontal")
        and (g.properties or {}).get("coordinate") is not None
    ]


def ejes_cercanos(
    detection: Detection, grid_lines: list[Detection], meters_factor: float | None
) -> str:
    """«B / 3» cuando el plano nombra ejes cercanos; vacío si no."""
    factor = meters_factor or 1.0
    radio = EJE_RADIO_M / factor
    cx, cy = _centro(detection)
    source = _hoja(detection.evidence.source or "")
    best: dict[str, tuple[float, str]] = {}
    for g in grid_lines:
        props = g.properties or {}
        if props.get("label_source") == "auto" or not g.label:
            continue
        if _hoja(g.evidence.source or "") != source:
            continue
        axis = props.get("axis")
        coord = props.get("coordinate")
        if axis not in ("vertical", "horizontal") or coord is None:
            continue
        x0, y0, x1, y1 = g.bbox
        if axis == "vertical":
            dist = abs(cx - float(coord))
            inside = y0 - radio <= cy <= y1 + radio
        else:
            dist = abs(cy - float(coord))
            inside = x0 - radio <= cx <= x1 + radio
        if dist <= radio and inside and (axis not in best or dist < best[axis][0]):
            best[axis] = (dist, g.label)
    partes = [best[a][1] for a in ("vertical", "horizontal") if a in best]
    return " / ".join(partes)


def planta(detection: Detection, segmentation: SheetSegmentation | None) -> str:
    if segmentation is None or not segmentation.is_segmented:
        return ""
    view_id = segmentation.assignment.get(detection.detection_id)
    if view_id is None:
        return ""
    view = next((v for v in segmentation.views if v.view_id == view_id), None)
    return view.title if view is not None else ""


def visor_url(project_id: str, detection: Detection) -> str:
    x0, y0, x1, y1 = (round(v, 3) for v in detection.bbox)
    return f"/proyecto/{quote(project_id)}/plano?bbox={x0},{y0},{x1},{y1}"


def referencias(
    project_id: str,
    detections: list[Detection],
    segmentation: SheetSegmentation | None,
    meters_factor: float | None,
) -> dict[str, Referencia]:
    """La referencia de cada detección, por id."""
    # Una sola vez: los ejes nombrados, por hoja (antes se filtraban y se
    # recalculaba el nombre de la hoja por cada par elemento×eje).
    por_hoja: dict[str, list[Detection]] = {}
    for g in _ejes_con_nombre(
        [d for d in detections if d.detection_type == DetectionType.grid_line]
    ):
        por_hoja.setdefault(_hoja(g.evidence.source or ""), []).append(g)
    out: dict[str, Referencia] = {}
    for d in detections:
        out[d.detection_id] = Referencia(
            element_id=element_id(d, meters_factor),
            hoja=PurePath(d.evidence.source or "").stem,
            planta=planta(d, segmentation),
            ejes=ejes_cercanos(d, por_hoja.get(_hoja(d.evidence.source or ""), []),
                               meters_factor),
            visor=visor_url(project_id, d),
        )
    return out
