"""Verificación en crudo de la cerca estructural de las demás entradas del gold: demo,
torre-reforma-s101, las cuatro mini (acabados, canceleria, carpinteria, instalaciones) y prueba-1.

Evidencia de los valores cercados (Tarea 15, R260): independiente del motor. ``load_dxf`` sólo abre
cada archivo; lo demás es ezdxf a mano sobre el model space y los bloques insertados en él. Por
cada entrada imprime el sha256 de cada DXF, $INSUNITS, sus textos (todos, si son pocos) y lo que
importa, y compara con ``evals/gold/<id>.json``. Sale con 1 si las colocaciones por hoja del crudo
no son las del gold, o si una hoja tiene lo que leen la junta de los dados y sus cortes (Tarea 15b).

Desde la raíz del repo (``data/`` son los planos locales; ``source`` de cada entrada):

    uv run python evals/verificacion/verificar_otros.py              # las siete
    uv run python evals/verificacion/verificar_otros.py demo acabados-mini

Qué VERIFICA (y compara): (demo, torre) las colocaciones por hoja —columna = etiquetas de
S-COL-TAG, trabe = de S-BEAM, zapata = contornos de S-FOOTING—. Qué VERIFICA (y sólo imprime, a la
vista): los textos y contornos de cada DXF, que los contornos de S-FOOTING no tengan texto, que no
haya armado («#», «@»), cuadro, detalle, nota, nivel ni cota en ninguna hoja, y $INSUNITS 0; (minis)
que no haya ninguna marca de las familias que la lectura lee (K-, C-, T, CTA-, CE-, CI, CR-, DA-,
P-, D-, B-, Z-) ni ningún texto con varilla o separación («#», «@»). Qué VERIFICA (y compara), en
todas: ninguna capa dice DADO, ningún título de corte nombra una marca y ningún texto es un tipo de
dala escrito con guion (Tarea 15b, R259: lo que esa tarea lee no está aquí).

Qué REPRODUCE (reglas del motor, no hechos del plano): la marca «C1» del dibujo es «C-1» en el gold
(normalización del motor); criticos_total = 4 por columna y trabe, 3 por zapata (los datos de su
tarjeta); un hallazgo de la verificación 1 por marca sin definir, uno de aviso para todas las
zapatas sin marca, uno de la 7/duda por hoja (la altura supuesta de sus columnas, juntas).

prueba-1 (Tarea 15c: una etiqueta es de una sola vista). Qué VERIFICA (y compara): sus cuatro
títulos de planta (textos de 0.5 con PLANTA o AZOTEA); la extensión dibujada de cada planta, su
rejilla (las líneas de S-GRID que se cruzan, dos o más en cada sentido; la caja de sus líneas), de
cada título la que le queda claramente más cerca (la otra, al menos al doble), y que ninguna caja
toque a otra; cada etiqueta de castillo (capa castillos, «K-n»): la planta cuya rejilla la contiene,
o, fuera de toda rejilla, la de la caja claramente más cercana —ninguna en dos, ninguna sin planta—
y cuántas hay en cada planta contra ``por_vista`` y ``por_familia`` del gold, exactas. EST-001: la
sección de cada castillo es el marcador cerrado más cercano a su etiqueta en la capa castillos (el
cuadro de 15×15, el de 15×30 o el círculo), por la altura, en PLANTA BAJA, PLANTA ALTA y AZOTEA,
contra el gold con 0.5 % (lo que difiere: el motor da a dos K-0 sobre el 15×30 de una K-2 ese
marcador —R166— y a dos K-0 sin marcador junto el círculo de su símbolo: −0.046 m³). Los dos muros
que la Tarea 15c cambia de planta: W39, el poniente exterior de PLANTA BAJA (sus líneas A-WALL
en x 50.725–50.905 van de −62.298 a −45.473: 16.825 m), dentro de la rejilla de PLANTA BAJA; W18,
el norte de la AZOTEA (su cara interior A-WALL en y −63.724, 5.22 m), dentro de la de AZOTEA.

Qué REPRODUCE (reglas del motor, no hechos del plano): el nombre de la vista de cada planta en el
motor (``VISTA_DEL_MOTOR``: por el orden de sus títulos); la altura de los castillos, 3.00 m, la
supuesta (las vistas de esta hoja no juntan su N.P.T.); los muros, 2.70 m, y un muro de azotea es
pretil de 0.90 m; criticos_total = 4 por castillo; con ellas, lo que la Tarea 15c movió del gold:
EST-001 9.893 → 10.366 (+7 castillos de 15×15 de PLANTA BAJA × 3.00 m), EST-004 392.598 →
428.630 (+16.825 × 2.70 de W39, −5.22 × 1.80 de W18 al volverse pretil), ACA-001 y ACA-002
785.197 → 857.260 (dos caras).
"""

import hashlib
import json
import math
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
        "capas": sorted({e.dxf.layer for e in msp}),
    }


VISTA_DEL_MOTOR = {
    "PLANTA DE CIMENTACIÓN": "view_00_cimentacion",
    "PLANTA BAJA": "view_01_planta_baja",
    "PLANTA ALTA": "view_02_planta_alta",
    "AZOTEA": "view_03_azotea",
}
SUPERESTRUCTURA = ("PLANTA BAJA", "PLANTA ALTA", "AZOTEA")
ALTURA_DE_CASTILLO_M = 3.00
ALTURA_DE_MURO_M, ALTURA_DE_PRETIL_M = 2.70, 0.90


def _a_caja(p, caja) -> float:
    dx = max(caja[0] - p[0], 0.0, p[0] - caja[2])
    dy = max(caja[1] - p[1], 0.0, p[1] - caja[3])
    return math.hypot(dx, dy)


def _dentro(p, caja) -> bool:
    return caja[0] <= p[0] <= caja[2] and caja[1] <= p[1] <= caja[3]


def _medio(v) -> tuple[float, float]:
    return ((v.dxf.start.x + v.dxf.end.x) / 2, (v.dxf.start.y + v.dxf.end.y) / 2)


def _se_cruzan(a, b) -> bool:
    (x1, y1), (x2, y2) = a
    (x3, y3), (x4, y4) = b
    d = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if abs(d) < 1e-12:
        return False
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / d
    u = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / d
    return 0 <= t <= 1 and 0 <= u <= 1


def _lineas_a_wall(msp):
    """Las líneas A-WALL del model space y de los bloques insertados en él (las de la capa «0»
    de un bloque insertado en A-WALL, en A-WALL)."""
    for e in msp:
        if e.dxftype() == "LINE" and e.dxf.layer == "A-WALL":
            yield e
        elif e.dxftype() == "INSERT":
            try:
                virtuales = list(e.virtual_entities())
            except Exception:
                continue
            for v in virtuales:
                capa = e.dxf.layer if v.dxf.layer == "0" else v.dxf.layer
                if v.dxftype() == "LINE" and capa == "A-WALL":
                    yield v


def _rejillas(msp, titulos) -> tuple[dict[str, tuple], int]:
    """La rejilla de cada planta: las líneas de S-GRID que se cruzan (dos o más en cada sentido),
    la caja de sus líneas, del título que le queda claramente más cerca."""
    malos = 0
    ejes = [((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y))
            for e in msp.query("LINE") if e.dxf.layer == "S-GRID"]  # fmt: skip
    padre = list(range(len(ejes)))

    def raiz(i: int) -> int:
        while padre[i] != i:
            i = padre[i]
        return i

    for i in range(len(ejes)):
        for j in range(i + 1, len(ejes)):
            if _se_cruzan(ejes[i], ejes[j]):
                padre[raiz(j)] = raiz(i)
    grupos: dict[int, list] = {}
    for i, eje in enumerate(ejes):
        grupos.setdefault(raiz(i), []).append(eje)
    rejillas: dict[str, tuple] = {}
    for g in grupos.values():
        horizontales = sum(1 for a, b in g if abs(b[1] - a[1]) < abs(b[0] - a[0]))
        if horizontales < 2 or len(g) - horizontales < 2:
            continue
        xs = [p[0] for a, b in g for p in (a, b)]
        ys = [p[1] for a, b in g for p in (a, b)]
        caja = (min(xs), min(ys), max(xs), max(ys))
        cerca = sorted((_a_caja(p, caja), t) for t, p in titulos.items())
        print(f"  rejilla de {len(g)} ejes, caja {tuple(round(c, 2) for c in caja)}: títulos a "
              f"{[(t, round(d, 2)) for d, t in cerca[:2]]}")  # fmt: skip
        if cerca[1][0] <= 2 * cerca[0][0] or cerca[0][1] in rejillas:
            print("  ** DIFERENCIA: una rejilla sin un título claramente suyo")
            malos += 1
            continue
        rejillas[cerca[0][1]] = caja
    for a in rejillas:
        for b in rejillas:
            ca, cb = rejillas[a], rejillas[b]
            if a < b and ca[0] <= cb[2] and cb[0] <= ca[2] and ca[1] <= cb[3] and cb[1] <= ca[3]:
                print(f"  ** DIFERENCIA: las rejillas de {a} y {b} se tocan")
                malos += 1
    return rejillas, malos


def _marcadores(msp) -> list[tuple[tuple, float]]:
    """Los marcadores cerrados de la capa castillos (cuadros y círculos), con su área."""
    salida = []
    for e in msp:
        if e.dxf.layer != "castillos":
            continue
        if e.dxftype() == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in e.get_points()]
            if len(pts) >= 3 and (e.closed or math.dist(pts[0], pts[-1]) < 1e-6):
                area = abs(sum(pts[i][0] * pts[i - 1][1] - pts[i - 1][0] * pts[i][1]
                               for i in range(len(pts)))) / 2  # fmt: skip
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                salida.append(((min(xs), min(ys), max(xs), max(ys)), area))
        elif e.dxftype() == "CIRCLE":
            c, r = e.dxf.center, e.dxf.radius
            salida.append(((c.x - r, c.y - r, c.x + r, c.y + r), math.pi * r * r))
    return salida


def prueba_1(gold: dict) -> int:
    """Tarea 15c: PRUEBA-1, cada etiqueta de castillo en una sola planta (ver el docstring)."""
    malos = 0
    path = Path(gold["source"]) / "drawings" / "Plano Prueba 1.dxf"
    print(f"  sha {hashlib.sha256(path.read_bytes()).hexdigest()[:12]}…")
    msp = load_dxf(path).doc.modelspace()
    titulos = {
        texto(e): (e.dxf.insert.x, e.dxf.insert.y)
        for e in msp.query("TEXT MTEXT")
        if (e.dxf.char_height if e.dxftype() == "MTEXT" else e.dxf.height) >= 0.45
        and re.search(r"PLANTA|AZOTEA", texto(e).upper())
    }
    donde = {t: tuple(round(c, 2) for c in p) for t, p in titulos.items()}
    print(f"  títulos de planta: {donde}")
    if sorted(titulos) != sorted(VISTA_DEL_MOTOR):
        print(f"  ** DIFERENCIA: los títulos no son {sorted(VISTA_DEL_MOTOR)}")
        return malos + 1
    rejillas, malos = _rejillas(msp, titulos)
    if sorted(rejillas) != sorted(titulos):
        print(f"  ** DIFERENCIA: plantas sin rejilla: {sorted(set(titulos) - set(rejillas))}")
        return malos + 1
    # Cada etiqueta de castillo, en una sola planta; su sección, la de su marcador más cercano.
    marcadores = _marcadores(msp)
    por_planta: Counter = Counter()
    seccion: Counter = Counter()
    fuera = 0
    for e in msp.query("TEXT MTEXT"):
        if e.dxf.layer != "castillos" or not re.match(r"^K-?\d$", texto(e).upper()):
            continue
        p = (e.dxf.insert.x, e.dxf.insert.y)
        dentro = [t for t, caja in rejillas.items() if _dentro(p, caja)]
        if not dentro:
            fuera += 1
            cerca = sorted((_a_caja(p, caja), t) for t, caja in rejillas.items())
            dentro = [cerca[0][1]] if cerca[1][0] > 2 * cerca[0][0] else []
        if len(dentro) != 1:
            print(f"  ** DIFERENCIA: {e.dxf.handle} {texto(e)} en {dentro or 'ninguna planta'}")
            malos += 1
            continue
        por_planta[dentro[0]] += 1
        seccion[dentro[0]] += min(marcadores, key=lambda m, p=p: _a_caja(p, m[0]))[1]
    crudo = {VISTA_DEL_MOTOR[t]: n for t, n in sorted(por_planta.items())}
    est = gold.get("estructura") or {}
    cercado = est.get("por_vista", {}).get("castillo")
    print(f"  castillos por planta, crudo: {dict(por_planta)} ({fuera} fuera de toda rejilla, "
          f"junto a la caja de la suya); gold: {cercado}")
    if crudo != cercado:
        print("  ** DIFERENCIA por_vista")
        malos += 1
    total = sum(por_planta.values())
    tarjeta = est.get("por_familia", {}).get("castillo", {})
    if (total, 4 * total) != (tarjeta.get("colocaciones"), tarjeta.get("criticos_total")):
        print(f"  ** DIFERENCIA: {total} castillos ({4 * total} datos críticos); gold {tarjeta}")
        malos += 1
    if est.get("por_hoja", {}).get("castillo") != {"drawings/Plano Prueba 1.dxf": total}:
        print("  ** DIFERENCIA por_hoja de castillo")
        malos += 1
    # EST-001: sección del marcador × la altura supuesta, en la superestructura.
    volumen = {t: round(float(seccion[t]) * ALTURA_DE_CASTILLO_M, 4) for t in SUPERESTRUCTURA}
    est_001 = sum(volumen.values())
    concepts = (gold.get("money") or {}).get("concepts", {})
    gold_001 = concepts.get("EST-001", {}).get("quantity")
    print(f"  EST-001 crudo {round(est_001, 4)} m³ {volumen}; gold {gold_001} (0.5 %)")
    if gold_001 is None or abs(est_001 - gold_001) > 0.005 * gold_001:
        print("  ** DIFERENCIA EST-001")
        malos += 1
    # Los dos muros que la Tarea 15c cambia de planta.
    lineas = list(_lineas_a_wall(msp))
    w39 = [v for v in lineas
           if 50.70 <= min(v.dxf.start.x, v.dxf.end.x) and max(v.dxf.start.x, v.dxf.end.x) <= 50.93
           and abs(v.dxf.start.y - v.dxf.end.y) > 1.0]  # fmt: skip
    w18 = [v for v in lineas
           if abs(v.dxf.start.y + 63.724) < 0.002 and abs(v.dxf.end.y + 63.724) < 0.002
           and abs(v.dxf.start.x - v.dxf.end.x) > 3.0]  # fmt: skip
    y39 = [y for v in w39 for y in (v.dxf.start.y, v.dxf.end.y)]
    largo_39 = round(max(y39) - min(y39), 3) if y39 else 0.0
    largo_18 = round(max(abs(v.dxf.start.x - v.dxf.end.x) for v in w18), 3) if w18 else 0.0
    en_pb = bool(w39) and all(_dentro(_medio(v), rejillas["PLANTA BAJA"]) for v in w39)
    en_az = bool(w18) and all(_dentro(_medio(v), rejillas["AZOTEA"]) for v in w18)
    print(f"  W39: {len(w39)} líneas A-WALL, {largo_39} m, en la rejilla de PLANTA BAJA {en_pb}; "
          f"W18: cara interior {largo_18} m, en la de AZOTEA {en_az}")
    if (largo_39, largo_18, en_pb, en_az) != (16.825, 5.22, True, True):
        print("  ** DIFERENCIA en los muros que cambian de planta")
        malos += 1
    # Lo que la Tarea 15c movió del gold, de esos hechos y las reglas del motor.
    muros = largo_39 * ALTURA_DE_MURO_M - largo_18 * (ALTURA_DE_MURO_M - ALTURA_DE_PRETIL_M)
    movido = {
        "EST-001": (9.893, 7 * 0.0225 * ALTURA_DE_CASTILLO_M),
        "EST-004": (392.598, muros),
        "ACA-001": (785.197, 2 * muros),
        "ACA-002": (785.197, 2 * muros),
    }
    for code, (antes, delta) in movido.items():
        q = concepts.get(code, {}).get("quantity")
        print(f"  {code}: {antes} + {round(delta, 4)} = {round(antes + delta, 3)}; gold {q}")
        if q is None or abs(antes + delta - q) > 0.001:
            print(f"  ** DIFERENCIA {code}")
            malos += 1
    return malos


def main() -> int:
    malos = 0
    ids = sys.argv[1:] or ["demo", "torre-reforma-s101", "acabados-mini", "canceleria-mini",
                           "carpinteria-mini", "instalaciones-mini", "prueba-1"]
    for gid in ids:
        gold = json.loads(Path(f"evals/gold/{gid}.json").read_text())
        if gid == "prueba-1":
            print(f"\n=== {gid} ({gold['source']})")
            malos += prueba_1(gold)
            continue
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
            # Tarea 15b: lo que la junta de los dados, sus alturas de corte y el detalle de un
            # tipo de dala (R259) leen no está en estas hojas: ninguna capa dice DADO, ningún
            # título de corte nombra una marca («D-1 / CORTE»), ningún texto escribe con guion un
            # tipo de dala («D-C»). Si apareciera, su cerca podría moverse: sale como diferencia.
            dados = [c for c in d["capas"] if re.search(r"(?<![A-Z])DADO", c.upper())]
            cortes = [t for _c, t in d["textos"]
                      if re.match(r"^[A-Z]{1,3}\d{0,2}-[A-Z0-9]{1,3}\b.*\bCORTE\b",
                                  " ".join(t.upper().split()))]
            tipos = [t for _c, t in d["textos"] if t.upper().strip() in ("D-C", "C-I")]
            if dados or cortes or tipos:
                print(f"  ** DIFERENCIA, lo de la Tarea 15b: capas {dados}, cortes {cortes}, "
                      f"tipos de dala con guion {tipos}")
                malos += 1
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
