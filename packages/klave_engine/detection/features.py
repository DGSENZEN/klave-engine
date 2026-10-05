"""Lo que el motor sabía de un elemento, como datos: el insumo del lector que
aprende (spec «el lector que aprende» §3.3).

Cada detector mide área, proporción, repetición, distancia a los ejes, marca
cercana… y lo tira después de decidir con un umbral. Aquí se conserva como un
vector de rasgos: números y fichas de texto (capa, bloque, prefijo de la
marca), nunca coordenadas absolutas — lo que se comparte entre oficinas no
puede reconstruir un plano.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import PurePath

from klave_engine.detection.results import Detection, DetectionType

FEATURES_VERSION = 1
_TOKEN = re.compile(r"[a-z]+")
_PREFIJO = re.compile(r"^([A-Za-z]+)")


def tokens(texto: str) -> list[str]:
    """Fichas de un nombre de capa o bloque: «EST-COL_K» → [est, col, k]."""
    import unicodedata

    plano = unicodedata.normalize("NFKD", texto or "")
    plano = "".join(c for c in plano if not unicodedata.combining(c)).lower()
    return _TOKEN.findall(plano)[:8]


def _hoja(d: Detection) -> str:
    return PurePath(d.evidence.source or "").name


@dataclass
class Contexto:
    """Lo que hace falta saber del resto del plano para describir un elemento."""

    factor: float
    cruces: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    marcas: Counter = field(default_factory=Counter)
    bloques: Counter = field(default_factory=Counter)

    @classmethod
    def de(cls, detections: list[Detection], factor: float | None) -> Contexto:
        ctx = cls(factor=factor or 1.0)
        cruces: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for d in detections:
            hoja = _hoja(d)
            if d.detection_type == DetectionType.grid_intersection:
                x0, y0, x1, y1 = d.bbox
                cruces[hoja].append(((x0 + x1) / 2, (y0 + y1) / 2))
            if d.mark:
                ctx.marcas[(hoja, d.mark)] += 1
            block = (d.properties or {}).get("block_name")
            if block:
                ctx.bloques[(hoja, str(block))] += 1
        ctx.cruces = dict(cruces)
        return ctx

    def distancia_a_eje(self, hoja: str, x: float, y: float) -> float | None:
        puntos = self.cruces.get(hoja)
        if not puntos:
            return None
        return min(math.hypot(px - x, py - y) for px, py in puntos) * self.factor


def _num(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def features(d: Detection, ctx: Contexto) -> dict:
    """El vector de rasgos de una detección, en metros donde hay medida."""
    f = ctx.factor
    x0, y0, x1, y1 = d.bbox
    w, h = abs(x1 - x0) * f, abs(y1 - y0) * f
    props = d.properties or {}
    hoja = _hoja(d)
    out: dict = {
        "tipo": d.detection_type.value,
        "familia": d.family or "",
        "metodo": d.evidence.method or "",
        "ancho_m": round(w, 4),
        "alto_m": round(h, 4),
        "area_bbox_m2": round(w * h, 4),
        "proporcion": round(max(w, h) / min(w, h), 3) if min(w, h) > 0 else None,
        "tiene_marca": bool(d.mark),
        "prefijo_marca": (m.group(1).upper() if (m := _PREFIJO.match(d.mark or "")) else ""),
        "repeticion_marca": ctx.marcas.get((hoja, d.mark), 0) if d.mark else 0,
        "dist_eje_m": None,
        "capa_tokens": tokens(str(props.get("layer") or props.get("span_layer") or "")),
        "bloque_tokens": tokens(str(props.get("block_name") or "")),
        "repeticion_bloque": (
            ctx.bloques.get((hoja, str(props["block_name"])), 0) if props.get("block_name") else 0
        ),
    }
    dist = ctx.distancia_a_eje(hoja, (x0 + x1) / 2, (y0 + y1) / 2)
    if dist is not None:
        out["dist_eje_m"] = round(dist, 3)
    # Medidas que el detector ya calculó, convertidas a metros.
    for key, potencia, nombre in (
        ("section_area_du2", 2, "seccion_m2"), ("estimated_length", 1, "longitud_m"),
        ("estimated_span_length", 1, "claro_m"), ("estimated_area", 2, "area_m2"),
        ("estimated_thickness", 1, "espesor_m"), ("diameter", 1, "diametro_m"),
    ):
        valor = _num(props.get(key))
        if valor is not None:
            out[nombre] = round(valor * f ** potencia, 5)
    if _num(props.get("length_m")) is not None:
        out["longitud_m"] = round(float(props["length_m"]), 4)
    for key in ("section_source", "thickness_source", "wall_kind", "role", "footing_kind"):
        if props.get(key):
            out[key] = str(props[key])
    if "rectangularity" in props:
        out["rectangularidad"] = _num(props.get("rectangularity"))
    if "has_nearby_grid" in props:
        out["eje_cercano"] = bool(props["has_nearby_grid"])
    return out
