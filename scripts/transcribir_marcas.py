"""El borrador de una transcripción de marcas, sacado del DXF crudo sin el motor.

Para la revisión a mano (Tarea 16, spec lectura estructural §9): lista cada texto con forma de
marca («K-4», «C-1», «P-5», «D-4B», «CTA-12», «T3-1A», «CI», «DADO D-1», «TRABE TE-A»…) y, para
cada uno, todos los textos a 1.6 m o menos que traen ``#``, ``@``, ``CENTRO``, ``EXT``,
``REFUERZO`` o ``VER CORTE``, con su dx/dy desde la marca, sus alturas, su ruta de bloque y el
código del marco donde caen. No decide de quién es cada texto: eso es la revisión a mano.

Independiente de la asociación del motor: ``load_dxf`` sólo abre el archivo (estricto →
recuperación → saneado); el model space se recorre con ezdxf y los INSERT se expanden aquí con
``virtual_entities()`` hasta profundidad 3. ``frames.json`` de una corrida sólo da el nombre (el
código ES-nnn) del marco que contiene cada texto.

    uv run python -m scripts.transcribir_marcas <dxf> --out <borrador.json> [--frames frames.json]
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from klave_engine.dxf.loader import load_dxf  # sólo para abrir el archivo

ALCANCE_M = 1.6
PROFUNDIDAD = 3
# Una marca: prefijo de letras (con número de tipo, «T3»), guion y número/letra («K-15A», «T3-1A»,
# «CTA-12», «D-X», «MC-A»), las de letra y número sin guion («Z1», «N1») o las de dala sin
# número («CI», «DC»).
_MARCA = r"(?:[A-Z]{1,3}\d{0,2}-[A-Z0-9]{1,4}(?:\.\d)?'?|[A-Z]{1,2}\d{1,2}[A-Z]?|CI|DC)"
# Una etiqueta: la marca sola, o una palabra de familia y la marca («DADO D-1», «TRABE TE-A»).
_FAMILIAS = (
    "CASTILLO", "COLUMNA", "PILOTE", "PILA", "DADO", "ZAPATA", "TRABE", "CONTRATRABE", "DALA",
    "CADENA", "CERRAMIENTO", "MURO", "LOSA", "NERVADURA", "PEDESTAL",
)
ETIQUETA = re.compile(rf"^(?:(?:{'|'.join(_FAMILIAS)})\s+)?({_MARCA})$")
ARMADO = re.compile(r"#|@|CENTRO|EXT|REFUERZO|VER\s+CORTE")


def texto_de(e: Any) -> str:
    if e.dxftype() == "MTEXT":
        return str(e.plain_text()).strip()
    return str(e.dxf.text or "").strip()


def ancla(e: Any) -> tuple[float, float]:
    """El punto con que el texto se alinea: el de inserción si va a la izquierda sobre la base;
    si no, su punto de alineación (TEXT). El MTEXT ya se inserta en su punto de alineación."""
    if e.dxftype() == "TEXT":
        h = int(e.dxf.get("halign", 0) or 0)
        v = int(e.dxf.get("valign", 0) or 0)
        if (h or v) and e.dxf.hasattr("align_point"):
            p = e.dxf.align_point
            return float(p[0]), float(p[1])
    p = e.dxf.insert
    return float(p[0]), float(p[1])


def alineacion(e: Any) -> str:
    if e.dxftype() == "MTEXT":
        return f"mtext:{int(e.dxf.get('attachment_point', 1) or 1)}"
    return f"text:{int(e.dxf.get('halign', 0) or 0)}/{int(e.dxf.get('valign', 0) or 0)}"


def altura(e: Any) -> float:
    if e.dxftype() == "MTEXT":
        return float(e.dxf.get("char_height", 0.0) or 0.0)
    return float(e.dxf.get("height", 0.0) or 0.0)


def textos(msp: Any) -> Iterator[tuple[Any, str]]:
    """Los TEXT/MTEXT (y los ATTRIB) del model space y de los bloques insertados en él, con su
    posición real (``virtual_entities``), hasta profundidad 3. Ruta: handle del INSERT de fuera,
    nombres de bloque y el índice dentro del bloque."""
    for e in msp.query("TEXT MTEXT DIMENSION"):
        yield e, e.dxf.handle

    def explotar(insert: Any, ruta: str, nivel: int) -> Iterator[tuple[Any, str]]:
        ruta = f"{ruta}<{insert.dxf.name}>"
        for a in insert.attribs:
            yield a, f"{ruta}/attrib:{a.dxf.tag}"
        if nivel > PROFUNDIDAD:
            return
        try:
            hijos = list(insert.virtual_entities())
        except Exception as exc:  # un bloque roto no tumba el borrador; se dice
            print(f"aviso: {ruta}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return
        for i, v in enumerate(hijos):
            if v.dxftype() in ("TEXT", "MTEXT", "ATTRIB", "DIMENSION"):
                yield v, f"{ruta}/{i}"
            elif v.dxftype() == "INSERT":
                yield from explotar(v, f"{ruta}/{i}", nivel + 1)

    for ins in msp.query("INSERT"):
        yield from explotar(ins, ins.dxf.handle, 1)


def cota(e: Any) -> dict | None:
    """Una cota (DIMENSION): el texto que muestra (el de su bloque de dibujo, que ya trae la
    sustitución de «<>»), dónde se escribe y si mide en horizontal o en vertical."""
    try:
        partes = list(e.virtual_entities())
    except Exception:
        return None
    textos_cota = [v for v in partes if v.dxftype() in ("MTEXT", "TEXT")]
    if not textos_cota:
        return None
    t = textos_cota[0]
    p1, p2 = e.dxf.get("defpoint2"), e.dxf.get("defpoint3")
    sentido = "?"
    if p1 is not None and p2 is not None:
        angulo = float(e.dxf.get("angle", 0.0) or 0.0) % 180
        if int(e.dxf.get("dimtype", 0)) & 7 == 1:  # alineada: la recta entre sus puntos
            angulo = math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0])) % 180
        sentido = "h" if min(angulo, 180 - angulo) < 10 else "v" if abs(angulo - 90) < 10 else "o"
    x, y = ancla(t)
    return {"texto": texto_de(t), "x": x, "y": y, "altura": altura(t), "sentido": sentido}


def marcos(path: Path | None) -> list[tuple[str, tuple[float, float, float, float]]]:
    if path is None:
        return []
    datos = json.loads(path.read_text())
    lista = datos["frames"] if isinstance(datos, dict) else datos
    return [(str(f.get("code") or f["frame_id"]), tuple(f["bbox"])) for f in lista]


def marco_de(x: float, y: float, lista: list) -> str | None:
    for codigo, (x0, y0, x1, y1) in lista:
        if x0 <= x <= x1 and y0 <= y <= y1:
            return str(codigo)
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dxf", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--alcance", type=float, default=ALCANCE_M, help="radio en m (1.6)")
    ap.add_argument("--frames", type=Path, default=None, help="frames.json (sólo nombres)")
    args = ap.parse_args(argv)

    doc = load_dxf(args.dxf).doc
    lista_marcos = marcos(args.frames)
    todos: list[dict] = []
    cotas: list[dict] = []
    for e, ruta in textos(doc.modelspace()):
        if e.dxftype() == "DIMENSION":
            c = cota(e)
            if c and c["texto"]:
                marco = marco_de(c["x"], c["y"], lista_marcos)
                cotas.append({**c, "x": round(c["x"], 4), "y": round(c["y"], 4), "ruta": ruta,
                              "capa": e.dxf.get("layer", ""), "marco": marco})
            continue
        t = texto_de(e)
        if not t:
            continue
        x, y = ancla(e)
        todos.append({
            "texto": t, "x": round(x, 4), "y": round(y, 4), "altura": round(altura(e), 4),
            "alineacion": alineacion(e), "capa": e.dxf.get("layer", ""), "ruta": ruta,
            "marco": marco_de(x, y, lista_marcos),
        })
    etiquetas = [t for t in todos if ETIQUETA.match(" ".join(t["texto"].upper().split()))]
    armados = [t for t in todos if ARMADO.search(t["texto"].upper())]
    salida = []
    for et in sorted(etiquetas, key=lambda t: (str(t["marco"]), t["texto"], t["x"], t["y"])):
        m = ETIQUETA.match(" ".join(et["texto"].upper().split()))
        assert m is not None
        cerca = []
        for a in armados:
            dx, dy = a["x"] - et["x"], a["y"] - et["y"]
            d = math.hypot(dx, dy)
            if d <= args.alcance:
                cerca.append({
                    "texto": a["texto"], "dx": round(dx, 3), "dy": round(dy, 3),
                    "d": round(d, 3), "altura": a["altura"], "alineacion": a["alineacion"],
                    "capa": a["capa"], "ruta": a["ruta"], "marco": a["marco"],
                })
        cerca.sort(key=lambda c: (-c["dy"], c["dx"]))
        cotas_cerca = []
        for c in cotas:
            dx, dy = c["x"] - et["x"], c["y"] - et["y"]
            if math.hypot(dx, dy) <= args.alcance:
                cotas_cerca.append({
                    "texto": c["texto"], "sentido": c["sentido"], "dx": round(dx, 3),
                    "dy": round(dy, 3), "ruta": c["ruta"], "marco": c["marco"],
                })
        cotas_cerca.sort(key=lambda c: (-c["dy"], c["dx"]))
        salida.append({"marca": m.group(1), **et, "cerca": cerca, "cotas": cotas_cerca})
    cuenta = Counter((s["marca"], s["marco"]) for s in salida)
    args.out.write_text(json.dumps({
        "dxf": str(args.dxf), "alcance_m": args.alcance, "profundidad": PROFUNDIDAD,
        "etiquetas": len(salida), "marcas_por_marco": len(cuenta), "lecturas": salida,
    }, ensure_ascii=False, indent=1))
    con_armado = sum(1 for s in salida if s["cerca"])
    print(f"{len(todos)} textos, {len(cotas)} cotas; {len(salida)} etiquetas de marca en "
          f"{len(cuenta)} (marca, marco); {con_armado} con armado a ≤ {args.alcance} m: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
