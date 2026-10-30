"""Verificación en crudo de la cerca estructural de las demás entradas del gold: demo,
torre-reforma-s101 y las cuatro mini (acabados, canceleria, carpinteria, instalaciones).

Evidencia de los valores cercados (Tarea 15, R260): independiente del motor. ``load_dxf`` sólo abre
cada archivo; lo demás es ezdxf a mano sobre el model space y los bloques insertados en él. Por
cada entrada imprime el sha256 de cada DXF, $INSUNITS, sus textos (todos, si son pocos) y lo que
importa, y compara con ``evals/gold/<id>.json``. Sale con 1 si las colocaciones por hoja del crudo
no son las del gold.

Desde la raíz del repo (``data/`` son los planos locales; ``source`` de cada entrada):

    uv run python evals/verificacion/verificar_otros.py              # las seis
    uv run python evals/verificacion/verificar_otros.py demo acabados-mini

Qué VERIFICA (y compara): (demo, torre) las colocaciones por hoja —columna = etiquetas de
S-COL-TAG, trabe = de S-BEAM, zapata = contornos de S-FOOTING—. Qué VERIFICA (y sólo imprime, a la
vista): los textos y contornos de cada DXF, que los contornos de S-FOOTING no tengan texto, que no
haya armado («#», «@»), cuadro, detalle, nota, nivel ni cota en ninguna hoja, y $INSUNITS 0; (minis)
que no haya ninguna marca de las familias que la lectura lee (K-, C-, T, CTA-, CE-, CI, CR-, DA-,
P-, D-, B-, Z-) ni ningún texto con varilla o separación («#», «@»).

Qué REPRODUCE (reglas del motor, no hechos del plano): la marca «C1» del dibujo es «C-1» en el gold
(normalización del motor); criticos_total = 4 por columna y trabe, 3 por zapata (los datos de su
tarjeta); un hallazgo de la verificación 1 por marca sin definir, uno de aviso para todas las
zapatas sin marca, uno de la 7/duda por hoja (la altura supuesta de sus columnas, juntas).
"""

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

from klave_engine.dxf.loader import load_dxf  # sólo para abrir el archivo

LEIDA = re.compile(r"^(K|C|CTA|CE|CR|DA|D|P|TE|T\d?|B|Z)-?\d{1,2}[A-Z]?$|^CI$|^DC$")


def texto(e) -> str:
    if e.dxftype() == "MTEXT":
        return e.plain_text().strip()
    return (e.dxf.text or "").strip()


def textos_de(msp):
    yield from msp.query("TEXT MTEXT")
    for ins in msp.query("INSERT"):
        yield from ins.attribs
        try:
            for v in ins.virtual_entities():
                if v.dxftype() in ("TEXT", "MTEXT"):
                    yield v
        except Exception:
            pass


def una(path: Path) -> dict:
    doc = load_dxf(path).doc
    msp = doc.modelspace()
    ts = [(e.dxf.layer, texto(e)) for e in textos_de(msp)]
    contornos = []
    for e in msp.query("LWPOLYLINE POLYLINE"):
        if e.dxftype() == "LWPOLYLINE":
            pts = list(e.get_points())
        else:
            pts = [v.dxf.location for v in e.vertices]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        contornos.append((e.dxf.layer, round(max(xs) - min(xs), 2), round(max(ys) - min(ys), 2)))
    return {
        "sha": hashlib.sha256(path.read_bytes()).hexdigest()[:12],
        "insunits": doc.header.get("$INSUNITS"),
        "textos": ts,
        "contornos": contornos,
        "cotas": len(msp.query("DIMENSION")),
        "tipos": Counter(e.dxftype() for e in msp),
    }


def main() -> int:
    malos = 0
    ids = sys.argv[1:] or ["demo", "torre-reforma-s101", "acabados-mini", "canceleria-mini",
                           "carpinteria-mini", "instalaciones-mini"]
    for gid in ids:
        gold = json.loads(Path(f"evals/gold/{gid}.json").read_text())
        src = Path(gold["source"]) / "drawings"
        print(f"\n=== {gid} ({src})")
        est = gold.get("estructura") or {}
        marcas_leidas: Counter = Counter()
        armado = []
        por_hoja: dict[str, Counter] = {}
        for path in sorted(src.glob("*.dxf")):
            d = una(path)
            hoja = f"drawings/{path.name}"
            print(f"  {path.name}: sha {d['sha']}… $INSUNITS {d['insunits']}, {len(d['textos'])} "
                  f"textos, {len(d['contornos'])} polilíneas, {d['cotas']} cotas, "
                  f"{dict(d['tipos'].most_common(6))}")
            if len(d["textos"]) <= 15:
                print(f"    textos: {d['textos']}")
                print(f"    polilíneas: {d['contornos']}")
            for capa, t in d["textos"]:
                for f in re.split(r"[\s,;()]+", t.upper()):
                    if LEIDA.match(f):
                        marcas_leidas[(capa, f)] += 1
                        if capa == "S-COL-TAG":
                            por_hoja.setdefault("columna", Counter())[hoja] += 1
                        elif capa == "S-BEAM":
                            por_hoja.setdefault("trabe", Counter())[hoja] += 1
                if "#" in t or "@" in t:
                    armado.append((path.name, capa, t[:80]))
            zapatas = [c for c in d["contornos"] if c[0] == "S-FOOTING"]
            if zapatas:
                por_hoja.setdefault("zapata", Counter())[hoja] += len(zapatas)
        print(f"  marcas de familias leídas: {dict(marcas_leidas)}")
        print(f"  textos con «#» o «@»: {armado}")
        if por_hoja or est.get("por_hoja"):
            crudo = {f: dict(c) for f, c in por_hoja.items()}
            print(f"  colocaciones por hoja, crudo: {crudo}")
            if crudo != est.get("por_hoja", {}):
                print(f"  ** DIFERENCIA por_hoja: gold {est.get('por_hoja')}")
                malos += 1
        elif marcas_leidas or armado:
            print("  ** el gold no cerca colocaciones y el crudo tiene marcas o armado: revisar")
        print(f"  gold: por_familia {est.get('por_familia')}, verificaciones "
              f"{est.get('verificaciones')}, hallazgos {est.get('hallazgos')}, sin_cerca "
              f"{list(est.get('sin_cerca') or {})}")
    return 1 if malos else 0


if __name__ == "__main__":
    sys.exit(main())
