"""Los candidatos: lo que tiene forma de elemento y ninguna regla tomó.

Las reglas sólo emiten lo que aceptan. La polilínea cerrada que casi era una
columna, el bloque que nadie reconoció, nunca llegaban a Revisión ni a un
registro — así que un modelo no tendría qué clasificar y una persona qué
corregir. Aquí se guardan, sin cambiar ninguna detección: figuras cerradas y
bloques del tamaño de un elemento estructural, en hojas que no son índice,
que ninguna detección cubre. Su veredicto es «no considerado»; el lector que
aprende (F3) los propondrá, nunca los contará solo.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path, PurePath

from klave_engine.detection.features import FEATURES_VERSION, Contexto, tokens
from klave_engine.detection.results import Detection
from klave_engine.dxf.entities import EntityType, NormalizedEntity

CANDIDATES_FILENAME = "candidates.jsonl"
LADO_MIN_M = 0.08
LADO_MAX_M = 3.0
MAX_POR_HOJA = 2000
_TIPOS = {EntityType.polyline, EntityType.insert, EntityType.hatch, EntityType.circle}
_HOJAS_FUERA = {"indice", "portada"}


def _cerrada(e: NormalizedEntity) -> bool:
    if e.entity_type == EntityType.polyline:
        return bool((e.properties or {}).get("closed"))
    return True


def candidatos(
    entities: list[NormalizedEntity],
    detections: list[Detection],
    meters_factor: float | None,
    disciplina_por_hoja: dict[str, str] | None = None,
) -> list[dict]:
    factor = meters_factor or 1.0
    disciplina_por_hoja = disciplina_por_hoja or {}
    cubre: dict[str, list[tuple[float, float, float, float]]] = defaultdict(list)
    margen = 0.05 / factor
    for d in detections:
        x0, y0, x1, y1 = d.bbox
        cubre[PurePath(d.evidence.source or "").name].append(
            (x0 - margen, y0 - margen, x1 + margen, y1 + margen)
        )
    ctx = Contexto.de(detections, factor)
    bloques: dict[tuple[str, str], int] = defaultdict(int)
    for e in entities:
        if e.entity_type == EntityType.insert and e.block_name:
            bloques[(PurePath(e.source_file).name, e.block_name)] += 1
    por_hoja: dict[str, int] = defaultdict(int)
    out: list[dict] = []
    for e in entities:
        if e.entity_type not in _TIPOS or not _cerrada(e):
            continue
        if (e.properties or {}).get("parent_insert"):
            continue  # el hijo de un bloque reventado: el bloque ya cuenta (E2)
        hoja = PurePath(e.source_file).name
        if disciplina_por_hoja.get(hoja, "") in _HOJAS_FUERA:
            continue
        x0, y0, x1, y1 = e.bbox
        w, h = abs(x1 - x0) * factor, abs(y1 - y0) * factor
        if not (LADO_MIN_M <= min(w, h) and max(w, h) <= LADO_MAX_M):
            continue
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if any(a <= cx <= c and b <= cy <= d for a, b, c, d in cubre.get(hoja, ())):
            continue
        if por_hoja[hoja] >= MAX_POR_HOJA:
            continue
        por_hoja[hoja] += 1
        dist = ctx.distancia_a_eje(hoja, cx, cy)
        out.append({
            "entity_id": e.entity_id, "hoja": hoja, "veredicto": "no_considerado",
            "features_version": FEATURES_VERSION,
            "features": {
                "tipo_entidad": e.entity_type.value,
                "ancho_m": round(w, 4), "alto_m": round(h, 4),
                "area_bbox_m2": round(w * h, 4),
                "proporcion": round(max(w, h) / min(w, h), 3) if min(w, h) > 0 else None,
                "capa_tokens": tokens(e.layer),
                "bloque_tokens": tokens(e.block_name or ""),
                "repeticion_bloque": bloques.get((hoja, e.block_name or ""), 0)
                if e.block_name else 0,
                "dist_eje_m": round(dist, 3) if dist is not None else None,
            },
            "bbox": [round(v, 4) for v in e.bbox],
            # Nombre exacto del bloque y de la capa: se quedan en el proyecto
            # (el perfil del taller los aprende); nunca se comparten.
            "bloque": e.block_name or "",
            "capa": e.layer,
        })
    return out


def write_candidates(path_dir: Path, rows: list[dict]) -> Path:
    path = path_dir / CANDIDATES_FILENAME
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path
