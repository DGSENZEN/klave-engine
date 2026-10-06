"""Las propuestas del lector: lo que ninguna regla tomó y tiene forma de
elemento, punteado en el plano y en Revisión, sin contar hasta que una
persona diga qué es (spec §5, tercera fila).

Cada propuesta lleva su razón en palabras — lo que mide, qué tan cerca está
de un eje, cuántas veces se repite — y nunca el número del modelo. Una
propuesta confirmada o descartada no vuelve a proponerse: su clave depende
de la hoja, del centro a 5 cm y del bloque, así que sobrevive a un reproceso
que renumera las entidades."""

from __future__ import annotations

import hashlib
from collections import defaultdict

from klave_engine.detection.inventory import reads_as_structure
from klave_engine.lector.modelo import Modelo
from klave_engine.lector.rasgos import en_ventana, vector

PROPUESTAS_FILENAME = "propuestas.json"
RESUELTAS = ("confirm_proposal", "reject_proposal")


def clave(cand: dict, factor: float | None) -> str:
    x1, y1, x2, y2 = cand["bbox"]
    paso = 0.05 / (factor or 1.0)  # 5 cm en unidades del dibujo
    cx, cy = round((x1 + x2) / 2 / paso), round((y1 + y2) / 2 / paso)
    raw = f"{cand.get('hoja', '')}|{cx}|{cy}|{cand.get('bloque', '')}"
    return "pr_" + hashlib.sha1(raw.encode()).hexdigest()[:12]


def claves_resueltas(labels: list[dict]) -> set[str]:
    return {str(lab.get("key")) for lab in labels if lab.get("action") in RESUELTAS}


def razon(f: dict) -> str:
    partes = [f"figura de {f['ancho_m']:.2f} × {f['alto_m']:.2f} m"]
    dist = f.get("dist_eje_m")
    if dist is not None and dist <= 0.5:
        partes.append("sobre un cruce de ejes" if dist <= 0.05 else f"a {dist:.2f} m de un eje")
    rep = f.get("repeticion_bloque") or 0
    if rep >= 2:
        partes.append(f"el mismo bloque {rep} veces en la hoja")
    return ", ".join(partes)


def proponer(
    candidates: list[dict], modelo: Modelo, factor: float | None, resueltas: set[str],
    plantas: list[tuple[float, float, float, float]] | None = None,
) -> list[dict]:
    """Las que pasan el umbral en hojas de estructura, las mejores primero, a
    lo más ``max_por_hoja`` por hoja. Sin puntaje en la salida. Si el plano
    trae plantas reconocidas (``plantas``), sólo dentro de ellas: en un
    detalle o en un corte un recuadro de 30 cm no es un elemento más."""
    por_hoja: dict[str, list[tuple[float, dict]]] = defaultdict(list)
    estructura: dict[str, bool] = {}
    for cand in candidates:
        f = cand.get("features") or {}
        hoja = cand.get("hoja", "")
        # Sólo donde corren las reglas estructurales: en una hoja de acabados
        # o de instalaciones un recuadro de 30 cm es otra cosa.
        if hoja not in estructura:
            estructura[hoja] = reads_as_structure(hoja)
        if not estructura[hoja] or not en_ventana(f):
            continue
        if plantas:
            x1, y1, x2, y2 = cand["bbox"]
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            if not any(a <= cx <= c and b <= cy <= d for a, b, c, d in plantas):
                continue
        k = clave(cand, factor)
        if k in resueltas:
            continue
        s = modelo.puntuar(vector(f))
        if s >= modelo.umbral:
            por_hoja[cand.get("hoja", "")].append((s, {
                "key": k, "hoja": cand.get("hoja", ""), "bbox": cand["bbox"],
                "ancho_m": f["ancho_m"], "alto_m": f["alto_m"], "bloque": cand.get("bloque", ""),
                "capa": cand.get("capa", ""), "razon": razon(f), "features": f,
                "features_version": cand.get("features_version"), "modelo": modelo.version,
            }))
    out: list[dict] = []
    for hoja in sorted(por_hoja):
        # Una figura y su achurado (o dos trazos encimados) son el mismo
        # lugar: una sola propuesta, la mejor.
        vistas: set[str] = set()
        filas = []
        for _, p in sorted(por_hoja[hoja], key=lambda t: -t[0]):
            if p["key"] not in vistas:
                vistas.add(p["key"])
                filas.append(p)
        out.extend(filas[: modelo.max_por_hoja])
    return out
