"""Lo que el plano no dio: la lista que viaja con cada juego de generadores.

Un presupuesto puede quedar incompleto sin que nadie lo note: un elemento que
el motor vio pero ninguna regla cuantificó, un renglón sin precio, una hoja
de la que no se leyó nada. Aquí se dice, con nombre y cuenta, para que lo que
falta se capture a mano a sabiendas y no se olvide en silencio.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import PurePath

from pydantic import BaseModel, Field

from klave_engine.costing.models import CostReport
from klave_engine.costing.reviews import ProjectReviews
from klave_engine.detection.results import Detection, DetectionType

# Lo que el motor lee para ubicar o descontar, no para cobrar.
_CONTEXTO = {
    DetectionType.grid_line, DetectionType.grid_intersection, DetectionType.opening,
}
_SIN_LECTURA_OK = {"indice", "portada", ""}


class Vistos(BaseModel):
    familia: str
    cantidad: int
    marcas: list[str] = Field(default_factory=list)


class SinPrecio(BaseModel):
    clave: str
    descripcion: str
    cantidad: float
    unidad: str


class HojaSinLectura(BaseModel):
    hoja: str
    disciplina: str


class Captura(BaseModel):
    vistos_sin_cantidad: list[Vistos] = Field(default_factory=list)
    sin_precio: list[SinPrecio] = Field(default_factory=list)
    hojas_sin_lectura: list[HojaSinLectura] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            sum(v.cantidad for v in self.vistos_sin_cantidad)
            + len(self.sin_precio) + len(self.hojas_sin_lectura)
        )


def lo_que_el_plano_no_dio(
    report: CostReport,
    detections: list[Detection],
    reviews: ProjectReviews | None = None,
    inventory: dict | None = None,
) -> Captura:
    excluded = {
        key for key, review in (reviews.detections if reviews else {}).items()
        if review.status == "excluded"
    }
    consumed: set[str] = set()
    for line in report.boq.lines:
        consumed.update(line.source_detections)
        for variant in line.variants:
            consumed.update(variant.source_detections)

    vistos: dict[str, list[Detection]] = defaultdict(list)
    for d in detections:
        if d.detection_type in _CONTEXTO or (d.properties or {}).get("role") == "cuadro":
            continue
        if (d.properties or {}).get("substrate"):
            continue
        if d.detection_id in consumed:
            continue
        if (d.display_label or d.detection_id) in excluded or d.detection_id in excluded:
            continue
        vistos[d.family_label or d.detection_type.value].append(d)

    out = Captura()
    for familia, dets in sorted(vistos.items(), key=lambda kv: -len(kv[1])):
        marcas = sorted({d.mark for d in dets if d.mark})[:8]
        out.vistos_sin_cantidad.append(Vistos(familia=familia, cantidad=len(dets), marcas=marcas))
    for line in report.boq.lines:
        if line.unpriced:
            out.sin_precio.append(SinPrecio(
                clave=line.taller_clave or "", descripcion=line.description,
                cantidad=round(line.quantity, 3), unidad=line.unit,
            ))
    leidas = {PurePath(d.evidence.source or "").name for d in detections}
    for sheet in (inventory or {}).get("sheets") or []:
        disciplina = str(sheet.get("discipline") or "")
        if disciplina in _SIN_LECTURA_OK:
            continue
        if PurePath(str(sheet.get("sheet") or "")).name not in leidas:
            out.hojas_sin_lectura.append(HojaSinLectura(
                hoja=str(sheet.get("label") or sheet.get("sheet") or ""), disciplina=disciplina,
            ))
    return out
