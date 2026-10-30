"""Verificación en crudo de la cerca de ``marina-estructural`` en el gold.

Evidencia de los valores cercados (Tarea 15, R260): un guion independiente del motor. ``load_dxf``
sólo abre el archivo (estricto → recuperación → saneado); todo lo demás es ezdxf a mano sobre el
model space y los bloques insertados en él. No importa ningún lector, detector, normalizador ni
verificación del motor. Corre sobre el DXF que el pipeline convierte del DWG del gold (imprime su
sha256; el de la cerca es e72a3d87…) y compara con ``evals/gold/marina-estructural.json``. Sale
con 1 si hay alguna diferencia no explicada.

Desde la raíz del repo (``data/`` son los planos locales):

    uv run python evals/verificacion/verificar_marina.py
    uv run python evals/verificacion/verificar_marina.py <dxf convertido> <gold.json>

Qué VERIFICA (hechos del dibujo; una diferencia con lo esperado sale como «DIFERENCIA»):
  - los 22 marcos (polilíneas de 44×29.33 en ESTRUCTURAL), cada uno con su código ES-nnn;
  - la planta de ES-000…ES-400 = la caja de sus burbujas de eje (INSERT «EJE») ± 0.5 m; ninguna
    etiqueta de las capas de familia de un marco de planta cae fuera de esa caja;
  - qué títulos de cuadro o detalle (una marca con su pila de armado debajo) caen dentro de esa
    caja: deben ser exactamente los cuatro conocidos de ES-200 —CR-1 980E8, CR-2 980FD y CR-3 98117
    (la cabeza del cuadro de cerramientos, dentro sólo por el margen de 0.5 m) y D-C AF02D (el
    detalle de una dala dentro de la caja misma)—; se excluyen de las escrituras de planta;
  - colocaciones por familia y por hoja = etiquetas en la capa de su familia dentro de la planta
    (castillo/columna EST-CASTILLOS K-/C-, trabe EST-TRABES + «TE-A» de EST-CONTRATRABE, contratrabe
    CTA- de EST-CONTRATRABE, dala EST-CADENAS Y DALAS, cerramiento EST-CERRAMIENTOS, pilote
    EST-PILOTES); que no haya dos iguales a < 0.3 m;
  - castillos, columnas y pilotes junto a su contorno: cada etiqueta a ≤ 0.7 m del rectángulo de
    un contorno de su capa (EST-CASTILLOS o COLUMNA; EST-PILOTES) —en el dibujo la etiqueta va al
    lado del contorno, no encima: la más lejana queda a 0.64 m—, y cada pilote con un contorno
    propio (23 etiquetas, 23 contornos, el más cercano de cada una distinto);
  - los contornos de castillo y columna en las plantas: polilíneas de EST-CASTILLOS (rectángulos y
    las dos piezas de 7 vértices de la L de K-15A) y de COLUMNA, y en cuántos cuerpos se juntan los
    que se encimen;
  - definidas: una marca colocada tiene, fuera de las plantas, un texto suyo (sola o en un título,
    también dentro de un bloque) con armado («#») o una cota a ≤ 3 m; las que no lo tienen; y sus
    parecidas sin guion;
  - las notas generales de familia (palabra de la familia + sección «NxM» + «#» en un texto);
  - las marcas escritas solas dentro de una planta que no son etiquetas de familia, por capa;
  - las marcas definidas que no se escriben en ninguna planta;
  - los pilotes de ES-000: contornos y su medida (CIM-010), su cuadro (renglones de armado y
    varillas dibujadas en cada corte) y que su longitud no se escribe (ES-001);
  - los dados D-n: contornos de EST-DADOS, distancia etiqueta–contorno, D-X dentro de D-4, y la
    altura acotada en sus cortes (cotas de COTAS-100 con texto «100»).

Qué REPRODUCE (reglas del motor aplicadas a mano sobre esos hechos; no son hechos del plano):
  - criticos_total = 4 × colocaciones (la tarjeta tiene 4 datos críticos por elemento);
  - pilote criticos_del_plano = 3 por pilote (sección, longitudinales, estribos del cuadro; la
    longitud no) y «2E#3 VER CORTE» cuenta como estribo del plano;
  - la severidad de la verificación 1: sin definición y sin nota de su familia → bloquea; con nota
    → duda;
  - la verificación 2: definida y nunca escrita en una planta (sólo las familias que la lectura lee
    y los dados D-);
  - la partición de la verificación 10 en duda (muros MC-, dados D-, CM-1: marca de elemento de
    concreto o columna escrita sin elemento) y lo que no es duda (nervaduras de EST-LOSA NERVADA,
    placas PL- y conexiones CN-, referencias DET-, letras de corte R1/R1'): esa taxonomía es del
    motor; aquí se aplica por prefijo y capa, a la vista.

Diferencia conocida (la cerca la tiene a sabiendas; R259 la lleva a la Tarea 15b): 10/duda D-C.

Handles fijos que usa (cada uno se imprime con lo que el dibujo tiene en él; si no existe o no
dice lo esperado, sale como diferencia o a la vista): 42766 y 429EA (cotas «100» de los cortes de
D-1 y D-3, ES-005), E2EC4 y 35521 (contornos de D-X y de D-4), 98104 y 98102 («2#3» y «2#4» de
CR-2 en el cuadro de ES-200), D8A3A y D8A4F (nota «CADENA DE ENRASE 15x25 4#3 E#2@15»),
AF02D/AF011/AF025/AF026 (el detalle «D-C» «DALA» «6#3» «E#2@15» de ES-200), AF072 (la etiqueta
«DC» de ES-200), 980E8/980FD/98117 (títulos de cuadro de CR en la caja de ES-200), CF1C5 («D-C» de
ES-500), 30E36 y la cota «DF (VER TABLA DE MECÁNICA DE SUELOS)» de ES-001.
"""

import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from klave_engine.dxf.loader import load_dxf  # sólo para abrir el archivo

PLANTAS = ("ES-000", "ES-100", "ES-200", "ES-300", "ES-400")
MARGEN = 0.5
CAPAS_DE_FAMILIA = {
    "EST-CASTILLOS", "EST-TRABES", "EST-CONTRATRABE", "EST-CADENAS Y DALAS", "EST-CERRAMIENTOS",
    "EST-PILOTES",
}
# Una marca: letras, guion y número/letra («K-15A», «T3-1A», «CTA-12», «D-X»), o las de dala sin
# número («CI», «DC»), o una nervadura («N1», «WI»).
MARCA = re.compile(r"^[A-Z]{1,3}\d{0,2}-[A-Z0-9]{1,3}'?$|^[A-Z]{1,2}\d{1,2}[A-Z]?'?$|^CI$|^DC$")
# Las familias que la lectura lee, más los dados D-, por su prefijo en este dibujo.
DE_FAMILIA_LEIDA = re.compile(r"^(K|C|CTA|CE|CR|DA|D|P|TE|T\d)-[A-Z0-9]{1,3}$|^CI$|^DC$")

diferencias: list[str] = []


def dif(texto: str) -> None:
    diferencias.append(texto)
    print("  ** DIFERENCIA:", texto)


def texto(e) -> str:
    if e.dxftype() == "MTEXT":
        return e.plain_text().strip()
    return (e.dxf.text or "").strip()


def fichas(t: str) -> list[str]:
    """Las fichas de un texto, sin las que nombran un tramo de ejes («EJE D-G»)."""
    todas = [f for f in re.split(r"[\s,;:()«»\"]+", t.upper()) if f]
    return [f for i, f in enumerate(todas) if not (i and todas[i - 1] in ("EJE", "EJES"))]


# Un renglón corto de armado de cuadro («6#3», «E#2@15», «REFUERZO 12#6», «2E#3 VER CORTE»).
RENGLON_DE_ARMADO = re.compile(r"#\d")


def entidades_de_texto(msp):
    """Los TEXT/MTEXT del model space y los de los bloques insertados en él (con su posición
    real, de ``virtual_entities``, recursivo), con el handle del INSERT de fuera."""
    for e in msp.query("TEXT MTEXT"):
        yield e, e.dxf.handle

    def explotar(insert, raiz, nivel=0):
        if nivel > 4:
            return
        for a in insert.attribs:
            yield a, f"{raiz}/attrib"
        try:
            hijos = list(insert.virtual_entities())
        except Exception:
            return
        for i, v in enumerate(hijos):
            if v.dxftype() in ("TEXT", "MTEXT"):
                yield v, f"{raiz}/{i}"
            elif v.dxftype() == "INSERT":
                yield from explotar(v, f"{raiz}/{i}", nivel + 1)

    for ins in msp.query("INSERT"):
        yield from explotar(ins, ins.dxf.handle)


DXF_POR_DEFECTO = Path(
    "data/uploads/marina_lote_04_estructural_d1cd5ec8/converted/"
    "01-02_estructural_l_04_-_26_01_15_001/01-02_estructural_l_04_-_26_01_15.dxf"
)
GOLD_POR_DEFECTO = Path("evals/gold/marina-estructural.json")
# Títulos de cuadro o detalle que caen en la caja de una planta (handle → por qué).
CUADROS_EN_PLANTA = {
    "980E8": "CR-1, cabeza del cuadro de cerramientos de ES-200, dentro sólo por el margen",
    "980FD": "CR-2, cabeza del cuadro de cerramientos de ES-200, dentro sólo por el margen",
    "98117": "CR-3, cabeza del cuadro de cerramientos de ES-200, dentro sólo por el margen",
    "AF02D": "D-C, el detalle de una dala dibujado dentro de la caja de ejes de ES-200",
}
TOLERANCIA_CONTORNO = 0.7  # m, de la etiqueta al rectángulo de su contorno


def main() -> int:
    args = sys.argv[1:]
    dxf = Path(args[0]) if args else DXF_POR_DEFECTO
    gold_path = Path(args[1]) if len(args) > 1 else GOLD_POR_DEFECTO
    gold = json.loads(gold_path.read_text())
    print("DXF", dxf.name, "sha256", hashlib.sha256(dxf.read_bytes()).hexdigest())
    doc = load_dxf(dxf).doc
    msp = doc.modelspace()
    print("$INSUNITS", doc.header.get("$INSUNITS"), "(6 = metros)")

    # ---------------------------------------------------------------- marcos y plantas
    marcos: dict[str, tuple[float, float, float, float]] = {}
    for e in msp.query("LWPOLYLINE[layer=='ESTRUCTURAL']"):
        xs = [p[0] for p in e.get_points()]
        ys = [p[1] for p in e.get_points()]
        if abs(max(xs) - min(xs) - 44.0) < 0.05 and abs(max(ys) - min(ys) - 29.33) < 0.05:
            marcos[e.dxf.handle] = (min(xs), min(ys), max(xs), max(ys))
    codigo: dict[str, str] = {}
    for e in msp.query("TEXT MTEXT[layer=='EST-TEXTOS TITULOS']"):
        t = texto(e)
        if re.fullmatch(r"ES-\d{3}", t):
            x, y = e.dxf.insert.x, e.dxf.insert.y
            for h, m in marcos.items():
                if m[0] <= x <= m[2] and m[1] <= y <= m[3]:
                    codigo[h] = t
    print(f"marcos {len(marcos)}, con código {len(codigo)}: {sorted(codigo.values())}")
    if len(marcos) != 22 or len(codigo) != 22:
        dif("no son 22 marcos con su código")

    def hoja(x: float, y: float) -> str | None:
        for h, m in marcos.items():
            if m[0] <= x <= m[2] and m[1] <= y <= m[3]:
                return codigo.get(h)
        return None

    ejes: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for e in msp.query("INSERT[name=='EJE']"):
        p = e.dxf.insert
        if (h := hoja(p.x, p.y)) is not None:
            ejes[h].append((p.x, p.y))
    caja: dict[str, tuple[float, float, float, float]] = {}
    for h in PLANTAS:
        xs, ys = [p[0] for p in ejes[h]], [p[1] for p in ejes[h]]
        caja[h] = (min(xs) - MARGEN, min(ys) - MARGEN, max(xs) + MARGEN, max(ys) + MARGEN)
        print(f"planta {h}: {len(ejes[h])} burbujas de eje, caja {[round(v, 2) for v in caja[h]]}")

    def en_planta(x: float, y: float) -> str | None:
        for h, c in caja.items():
            if c[0] <= x <= c[2] and c[1] <= y <= c[3]:
                return h
        return None

    textos = []
    for e, h in entidades_de_texto(msp):
        x, y = e.dxf.insert.x, e.dxf.insert.y
        textos.append({"h": h, "capa": e.dxf.layer, "t": texto(e), "x": x, "y": y,
                       "hoja": hoja(x, y), "planta": en_planta(x, y), "bloque": "/" in h})
    en_bloques = [t for t in textos if t["bloque"]]
    print(f"textos: {len(textos)} ({len(en_bloques)} dentro de bloques insertados; de ésos en una "
          f"planta: {sum(1 for t in en_bloques if t['planta'])})")
    armados = [t for t in textos if "#" in t["t"]]
    cotas = []
    for e in msp.query("DIMENSION"):
        p = e.dxf.get("text_midpoint") or e.dxf.defpoint
        cotas.append((p.x, p.y))

    def es_etiqueta_de_cuadro(t: dict) -> bool:
        """Una marca con su pila de armado debajo (un renglón corto con «#» a ≤ 3 m bajo ella y a
        ≤ 1.2 m de su eje) es el título de un cuadro o de un detalle, no una escritura de planta."""
        return any(len(a["t"]) <= 25 and RENGLON_DE_ARMADO.search(a["t"])
                   and abs(a["x"] - t["x"]) <= 1.2 and 0 < t["y"] - a["y"] <= 3.0 for a in armados)

    # ---------------------------------------------------------------- etiquetas de familia
    def familia_de(t: dict) -> str | None:
        m, capa = t["t"].upper(), t["capa"]
        if capa == "EST-CASTILLOS":
            return "castillo" if m.startswith("K-") else "columna" if m.startswith("C-") else "?"
        if capa == "EST-TRABES":
            return "trabe"
        if capa == "EST-CONTRATRABE":
            return "trabe" if m == "TE-A" else "contratrabe" if m.startswith("CTA-") else "?"
        if capa == "EST-CADENAS Y DALAS":
            return "dala"
        if capa == "EST-CERRAMIENTOS":
            return "cerramiento"
        if capa == "EST-PILOTES":
            return "pilote"
        return None

    etiquetas = []
    for t in textos:
        if t["capa"] not in CAPAS_DE_FAMILIA or t["hoja"] not in PLANTAS:
            continue
        fam = familia_de(t)
        if t["planta"] is None:
            dif(f"etiqueta de capa de familia en {t['hoja']} fuera de su planta: {t['h']} "
                f"{t['capa']} {t['t']!r}")
            continue
        if fam == "?" or not MARCA.match(t["t"].upper()):
            dif(f"etiqueta rara en {t['capa']}: {t['h']} {t['t']!r}")
            continue
        etiquetas.append({**t, "familia": fam, "marca": t["t"].upper()})
    fuera_de_marco = [t for t in textos if t["capa"] in CAPAS_DE_FAMILIA and t["hoja"] is None]
    print(f"etiquetas de familia fuera de todo marco: {len(fuera_de_marco)}")
    otras_hojas = Counter(t["hoja"] for t in textos
                          if t["capa"] in CAPAS_DE_FAMILIA and t["hoja"] not in PLANTAS)
    print(f"textos de capas de familia en hojas que no son planta (cortes, detalles): "
          f"{dict(otras_hojas)}")
    por_hoja: dict[str, Counter] = defaultdict(Counter)
    marcas_por_familia: dict[str, Counter] = defaultdict(Counter)
    for t in etiquetas:
        por_hoja[t["familia"]][t["planta"]] += 1
        marcas_por_familia[t["familia"]][t["marca"]] += 1
    # duplicados en su lugar
    for i, a in enumerate(etiquetas):
        for b in etiquetas[i + 1:]:
            if a["marca"] == b["marca"] and math.hypot(a["x"] - b["x"], a["y"] - b["y"]) < 0.3:
                dif(f"etiqueta repetida en su lugar: {a['h']} {b['h']} {a['marca']}")
    for fam in sorted(por_hoja):
        print(f"  {fam}: {sum(por_hoja[fam].values())} {dict(sorted(por_hoja[fam].items()))}")
    te_a = [t for t in textos if "TE-A" in fichas(t["t"]) and t["planta"] is None]
    print(f"«TE-A» fuera de las plantas: {[(t['h'], t['hoja'], t['t']) for t in te_a]}")

    # junto a su contorno: castillos/columnas (EST-CASTILLOS, COLUMNA) y pilotes (EST-PILOTES)
    def contornos(*capas: str) -> list[tuple[float, float, float, float, str, str, int]]:
        salida = []
        for capa in capas:
            for e in msp.query(f"LWPOLYLINE[layer=='{capa}']"):
                pts = list(e.get_points())
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                if len(xs) >= 4 and max(xs) - min(xs) < 3 and max(ys) - min(ys) < 3:
                    c = (min(xs), min(ys), max(xs), max(ys), e.dxf.handle, capa, len(pts))
                    if en_planta((c[0] + c[2]) / 2, (c[1] + c[3]) / 2):
                        salida.append(c)
        return salida

    def distancia(c, x, y) -> float:
        dx = max(c[0] - x, 0.0, x - c[2])
        dy = max(c[1] - y, 0.0, y - c[3])
        return math.hypot(dx, dy)

    de_castillo = contornos("EST-CASTILLOS", "COLUMNA")
    por_capa = Counter((c[5], c[6]) for c in de_castillo)
    # Cuerpos: contornos que se enciman (rectángulos que se cruzan) son el mismo cuerpo.
    grupos: list[set[int]] = []
    for i, a in enumerate(de_castillo):
        juntos = [g for g in grupos if any(
            a[0] < de_castillo[j][2] and de_castillo[j][0] < a[2]
            and a[1] < de_castillo[j][3] and de_castillo[j][1] < a[3] for j in g)]
        nuevo_grupo = {i}.union(*juntos) if juntos else {i}
        grupos = [g for g in grupos if g not in juntos] + [nuevo_grupo]
    def marca_cercana(c) -> str:
        t = min((t for t in etiquetas if t["familia"] in ("castillo", "columna")),
                key=lambda t: distancia(c, t["x"], t["y"]))
        return f"{t['marca']} {t['planta']}"

    encimados = [(marca_cercana(de_castillo[min(g)]),
                  sorted(f"{de_castillo[j][4]}/{de_castillo[j][5]}" for j in g))
                 for g in grupos if len(g) > 1]
    por_tipo = {f"{c} ({v} vértices)": n for (c, v), n in sorted(por_capa.items())}
    print(f"contornos de castillo y columna en las plantas: {len(de_castillo)} {por_tipo}; "
          f"se juntan en {len(grupos)} cuerpos; grupos de más de uno: {encimados}")
    pilotes_c = contornos("EST-PILOTES")
    for fams, cs in ((("castillo", "columna"), de_castillo), (("pilote",), pilotes_c)):
        ds = []
        for t in etiquetas:
            if t["familia"] in fams:
                d = min(distancia(c, t["x"], t["y"]) for c in cs)
                ds.append(d)
                if d > TOLERANCIA_CONTORNO:
                    dif(f"{t['marca']} {t['h']} a {d:.2f} m de todo contorno de su capa")
        print(f"  {'/'.join(fams)}: {len(ds)} etiquetas a ≤ {max(ds):.2f} m de un contorno de su "
              f"capa (tolerancia {TOLERANCIA_CONTORNO} m)")
    suyo = [min(pilotes_c, key=lambda c: distancia(c, t["x"], t["y"]))[4]
            for t in etiquetas if t["familia"] == "pilote"]
    if len(set(suyo)) != len(suyo) or len(suyo) != len(pilotes_c):
        dif(f"pilotes: {len(suyo)} etiquetas, {len(set(suyo))} contornos distintos, "
            f"{len(pilotes_c)} contornos")
    else:
        print(f"  pilotes: cada una de las {len(suyo)} etiquetas tiene su propio contorno")

    # ---------------------------------------------------------------- definiciones
    colocadas = {t["marca"] for t in etiquetas}
    ids_de_etiqueta = {t["h"] for t in etiquetas}

    def ocurrencias(marca: str) -> list[dict]:
        return [t for t in textos if t["h"] not in ids_de_etiqueta and t["planta"] is None
                and marca in fichas(t["t"])]

    def tiene_armado_o_cota(t: dict) -> bool:
        cerca = any(math.hypot(a["x"] - t["x"], a["y"] - t["y"]) <= 3.0 and a["h"] != t["h"]
                    for a in armados)
        return cerca or "#" in t["t"] or any(
            math.hypot(x - t["x"], y - t["y"]) <= 3.0 for x, y in cotas)

    definidas = {m for m in colocadas if any(tiene_armado_o_cota(o) for o in ocurrencias(m))}
    sin_definir = sorted(colocadas - definidas)
    print(f"colocadas {len(colocadas)} marcas; sin definición: {sin_definir}")
    for m in sin_definir:
        llano = m.replace("-", "")
        parecidas = [(t["h"], t["capa"], t["hoja"], t["t"][:40]) for t in textos
                     if t["h"] not in ids_de_etiqueta
                     and any(f.replace("-", "") == llano for f in fichas(t["t"]))]
        print(f"  {m}: textos iguales sin guion fuera de sus etiquetas: {parecidas}")
    con_def = Counter()
    for t in etiquetas:
        if t["marca"] in definidas:
            con_def[t["familia"]] += 1

    # notas generales de familia: palabra + sección NxM + «#» en un mismo texto
    notas = defaultdict(list)
    for t in textos:
        s = t["t"].upper()
        if "#" in s and re.search(r"\d+\s*X\s*\d+", s):
            if "TRABE" in s:
                notas["trabe"].append((t["h"], t["hoja"], t["t"]))
            if "CADENA" in s or "DALA" in s:
                notas["dala"].append((t["h"], t["hoja"], t["t"]))
    print(f"notas de familia: {dict(notas)}")
    fam_de = {t["marca"]: t["familia"] for t in etiquetas}
    v1_bloquea = sorted(m for m in sin_definir if not notas.get(fam_de[m]))
    v1_duda = sorted(m for m in sin_definir if notas.get(fam_de[m]))

    # ---------------------------------------------------------------- escritas en planta
    escritas = defaultdict(list)
    cuadros_en_planta: dict[str, str] = {}
    for t in textos:
        s = t["t"].upper()
        de_losa = t["capa"] == "EST-LOSA NERVADA" and re.fullmatch(r"[A-Z]{2}", s)
        if t["planta"] is None or t["h"] in ids_de_etiqueta or not (MARCA.match(s) or de_losa):
            continue
        if re.fullmatch(r"ES-\d{3}", s):
            continue
        if es_etiqueta_de_cuadro(t):
            cuadros_en_planta[t["h"]] = s
            continue
        escritas[s].append((t["h"], t["capa"], t["planta"]))
    for h, m in sorted(cuadros_en_planta.items()):
        print(f"  título de cuadro o detalle en la caja de una planta: {h} {m} — "
              f"{CUADROS_EN_PLANTA.get(h, 'NO ESPERADO')}")
    if set(cuadros_en_planta) != set(CUADROS_EN_PLANTA):
        dif(f"títulos de cuadro en las plantas: {sorted(cuadros_en_planta)}, se esperaban "
            f"{sorted(CUADROS_EN_PLANTA)}")
    for h in ("980E8", "980FD", "98117"):
        t = next(t for t in textos if t["h"] == h)
        c = caja[t["planta"]]
        if c[0] + MARGEN <= t["x"] <= c[2] - MARGEN and c[1] + MARGEN <= t["y"] <= c[3] - MARGEN:
            dif(f"{h} está dentro de la caja de ejes misma, no sólo del margen")
    clases: dict[str, list[str]] = defaultdict(list)
    for m, donde in sorted(escritas.items()):
        capas = {c for _, c, _ in donde}
        if capas == {"EST-LOSA NERVADA"}:
            clase = "nervadura (EST-LOSA NERVADA)"
        elif m.startswith(("PL-", "CN-")):
            clase = "acero: placa/conexión"
        elif m.startswith("DET-"):
            clase = "referencia a detalle"
        elif m in ("R1", "R1'"):
            clase = "letra de corte"
        elif m.startswith(("MC-", "D-", "CM-")):
            clase = "duda (elemento de concreto/columna escrito sin elemento)"
        else:
            clase = "?"
        clases[clase].append(m)
        if clase.startswith("duda") or clase == "?":
            print(f"  escrita en planta: {m:6} {len(donde)}× capas {sorted(capas)} "
                  f"hojas {sorted({h for _, _, h in donde})} — {clase}")
    for clase, ms in clases.items():
        if not clase.startswith("duda"):
            print(f"  escrita en planta, {clase}: {ms}")
    if clases.get("?"):
        dif(f"marcas escritas en planta sin clase: {clases['?']}")
    v10_duda = sorted(clases.get("duda (elemento de concreto/columna escrito sin elemento)", []))
    de_dados = sorted({m for m, donde in escritas.items()
                       if any(c == "EST-DADOS" for _, c, _ in donde)})
    print(f"  de esas, en EST-DADOS (la junta etiqueta–dado que falta): {len(de_dados)} {de_dados}")
    for h in ("AF02D", "AF011", "AF025", "AF026", "AF072", "CF1C5"):
        t = next((t for t in textos if t["h"] == h), None)
        print(f"  {h}: {t and (t['capa'], t['hoja'], t['planta'], t['t'])}")

    # ---------------------------------------------------------------- verificación 2
    escritas_en_planta = colocadas | set(escritas) | {
        f for t in textos if t["planta"] is not None for f in fichas(t["t"])}
    definiciones = set()
    for t in textos:
        if t["planta"] is not None:
            continue
        for f in fichas(t["t"]):
            if DE_FAMILIA_LEIDA.match(f) and tiene_armado_o_cota(t):
                definiciones.add(f)
    v2 = sorted(definiciones - escritas_en_planta)
    print(f"verificación 2 (definida, nunca escrita en una planta): {v2}")

    # ---------------------------------------------------------------- pilotes
    pilotes = [c for c in contornos("EST-PILOTES") if en_planta((c[0] + c[2]) / 2,
                                                                (c[1] + c[3]) / 2) == "ES-000"]
    medidas = Counter(round((c[2] - c[0]) * 100) for c in pilotes)
    print(f"pilotes: {len(pilotes)} contornos en ES-000, por lado en cm {dict(medidas)}")
    por_marca: dict[str, Counter] = defaultdict(Counter)
    for t in etiquetas:
        if t["familia"] == "pilote":
            c = min(pilotes, key=lambda c: distancia(c, t["x"], t["y"]))
            por_marca[t["marca"]][round((c[2] - c[0]) * 100)] += 1
    print(f"  medida del contorno de cada etiqueta: { {m: dict(v) for m, v in por_marca.items()} }")
    # El cuadro de pilotes de ES-000 (fuera de la caja de ejes): cada título P-n, los renglones de
    # armado a ≤ 1 m de él y las varillas (círculos) de su corte, dibujado encima (≤ 3 m arriba).
    cuadro = [t for t in textos if t["hoja"] == "ES-000" and t["planta"] is None
              and t["t"].upper() in {"P-1", "P-2", "P-3", "P-4", "P-5"}]
    circulos = [(e.dxf.center.x, e.dxf.center.y) for e in
                msp.query("CIRCLE[layer=='EST-ESTRUCTURAL DETALLES']")]
    varillas_del_corte = {}
    for c in sorted(cuadro, key=lambda t: (-round(t["y"]), t["x"])):
        junto = [(a["h"], a["t"].replace("\n", " / ")) for a in armados
                 if math.hypot(a["x"] - c["x"], a["y"] - c["y"]) <= 1.0]
        n = sum(1 for x, y in circulos if abs(x - c["x"]) < 1.5 and 0 < y - c["y"] < 3.0)
        varillas_del_corte[c["t"].upper()] = n
        print(f"  cuadro {c['t']} {c['h']}: renglones a ≤ 1 m {junto}; círculos en su corte {n}")
    print("  (33AF5 «4#8 + 12#6 / 3E#3 VER CORTE» queda a 0.43 m de P-4, pero P-4 ya tiene su "
          "«REFUERZO 12#6» 33AA0 y su corte 12 varillas; el corte de P-5 es el que tiene 16 o más)")
    if varillas_del_corte.get("P-4") != 12 or varillas_del_corte.get("P-5", 0) < 16:
        dif(f"cortes de pilote: P-4 {varillas_del_corte.get('P-4')}, P-5 "
            f"{varillas_del_corte.get('P-5')} círculos")
    for t in textos:
        if t["hoja"] == "ES-001" and "MECÁNICA" in t["t"].upper():
            print(f"  longitud, texto {t['h']} (ES-001): {t['t']!r}")
    for e in msp.query("DIMENSION"):
        p = e.dxf.defpoint
        if "MECÁNICA" in (e.dxf.text or "").upper() or e.dxf.text in ("LP", "DF"):
            print(f"  longitud, cota {e.dxf.handle} ({hoja(p.x, p.y)}): texto {e.dxf.text!r}, "
                  f"medida {e.get_measurement():.2f} (sin escala: el detalle es «pilote tipo»)")

    # ---------------------------------------------------------------- dados
    dados = [c for c in contornos("EST-DADOS") if en_planta((c[0] + c[2]) / 2,
                                                             (c[1] + c[3]) / 2) == "ES-000"]
    tags_d = [t for t in textos if t["capa"] == "EST-DADOS" and t["planta"] == "ES-000"]
    ds = [min(distancia(c, t["x"], t["y"]) for c in dados) for t in tags_d]
    print(f"dados: {len(dados)} contornos en EST-DADOS de ES-000, {len(tags_d)} etiquetas; "
          f"etiqueta→contorno {min(ds):.2f}–{max(ds):.2f} m")
    for h in ("E2EC4", "35521"):
        e = doc.entitydb.get(h)
        print(f"  {h}: {e.dxftype() if e else None} {e.dxf.layer if e else ''} "
              f"{[(round(p[0], 2), round(p[1], 2)) for p in e.get_points()] if e else ''}")
    for h in ("42766", "429EA"):
        e = doc.entitydb.get(h)
        if e is None or e.dxftype() != "DIMENSION":
            dif(f"la cota {h} no está")
            continue
        p = e.dxf.defpoint2
        titulo = min((t for t in textos if t["t"].upper().startswith("DADO ")),
                     key=lambda t: math.hypot(t["x"] - p.x, t["y"] - p.y))
        lejos = math.hypot(titulo["x"] - p.x, titulo["y"] - p.y)
        print(f"  cota {h}: capa {e.dxf.layer}, texto {e.dxf.text!r}, "
              f"medida {e.get_measurement():.2f}, hoja {hoja(p.x, p.y)}, ángulo "
              f"{e.dxf.get('angle')}; título más cercano {titulo['t']!r} {titulo['h']} a "
              f"{lejos:.1f} m")
    for h in ("98104", "98102", "D8A3A", "D8A4F"):
        t = next((t for t in textos if t["h"] == h), None)
        print(f"  {h}: {t and (t['capa'], t['hoja'], t['t'])}")

    # ---------------------------------------------------------------- contra el gold
    est = gold["estructura"]
    print("\n== contra", gold_path)
    for fam, hojas in est["por_hoja"].items():
        if dict(por_hoja[fam]) != hojas:
            dif(f"por_hoja {fam}: crudo {dict(por_hoja[fam])}, gold {hojas}")
    for fam, campos in est["por_familia"].items():
        n = sum(por_hoja[fam].values())
        esperado = {"colocaciones": n, "con_definicion": con_def[fam], "criticos_total": 4 * n}
        if fam == "pilote":
            esperado["criticos_del_plano"] = 3 * n
        for campo, v in campos.items():
            if esperado.get(campo) != v:
                dif(f"{fam}.{campo}: crudo {esperado.get(campo)}, gold {v}")
    leidas = {"castillo", "columna", "trabe", "contratrabe", "dala", "cerramiento", "pilote"}
    if set(por_hoja) - set(est["por_familia"]) - {"zapata", "dado", "muro_concreto"}:
        dif(f"familias con colocaciones fuera del gold: {set(por_hoja) - leidas}")
    crudo_hallazgos = {"1/bloquea": v1_bloquea, "1/duda": v1_duda, "2/aviso": v2,
                       "10/duda": v10_duda}
    # Diferencias conocidas, cada una con su razón (el gold las cerca a sabiendas y lo dice en sus
    # notas): la cerca es la del motor de hoy, y se mueve cuando el motor deje de equivocarse.
    conocidas = {
        ("10/duda", "D-C"): "AF02D «D-C» es el título del detalle de una dala («DALA» AF011, «6#3» "
        "AF025, «E#2@15» AF026) dibujado dentro de la caja de ejes de ES-200; el motor lo toma por "
        "una marca escrita en planta (y el mismo hallazgo dice que la define ahí)",
    }
    for clave, ids in est["hallazgos"].items():
        crudo = crudo_hallazgos.get(clave) or []
        sobran = [m for m in ids if m not in crudo]
        faltan = [m for m in crudo if m not in ids]
        for m in list(sobran):
            if (clave, m) in conocidas:
                print(f"  conocida, {clave} {m}: {conocidas[(clave, m)]}")
                sobran.remove(m)
        if sobran or faltan:
            dif(f"hallazgos {clave}: el gold tiene de más {sobran}, le faltan {faltan}")
        if est["verificaciones"][clave] != len(ids):
            dif(f"verificaciones {clave}: {est['verificaciones'][clave]} ≠ {len(ids)} hallazgos")
    cim = gold["money"]["concepts"]["CIM-010"]
    var = {f"CIM-010.{k}": float(v) for k, v in medidas.items()}
    if cim["quantity"] != len(pilotes) or cim["variants"] != var or cim["source"] != "crudo":
        dif(f"CIM-010: crudo {len(pilotes)} {var}, gold {cim['quantity']} {cim['variants']} "
            f"({cim['source']})")
    print("\nDIFERENCIAS:", "ninguna" if not diferencias else len(diferencias))
    return 1 if diferencias else 0


if __name__ == "__main__":
    sys.exit(main())
