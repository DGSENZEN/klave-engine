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
  - los dados D-n (Tarea 15b): los 23 contornos cerrados de EST-DADOS de ES-000 y sus 23
    etiquetas; cada etiqueta es del contorno más cercano a la caja de sus letras (≤ 0.6 m), sin
    otro a menos de 1.25 veces esa distancia, uno por etiqueta (``JUNTA_ESPERADA``); «D-X» E2EC5
    empata (± 0.01 m) entre E2EC4 y 35521, y E2EC4 está dentro de 35521 y es más chico que una
    zapata; ningún contorno de dado queda sin etiqueta;
  - las alturas de los dados en sus cortes (``CORTES_DE_DADO``): el título del corte
    («D-n / CORTE / X-X'») y el de su bloque («DADO D-n»), la cota vertical de su texto y su hoja,
    encima del título, y que mide el cuerpo del dado (dos trazos verticales del dibujo de punta a
    punta de la cota, ± 0.03 m); que cada dado colocado tiene la suya; que los lados verticales de
    las plantas de los dados (``LADOS_DE_PLANTA``) están bajo su título de PLANTA, no de CORTE;
  - CIM-002 = Σ (área del contorno de cada dado colocado × la altura de su corte), contra el gold
    (± 0.1 %, fuente crudo);
  - Tarea 15d (R269, ``variantes_15d``): los tableros macizos que EST-013 cuenta están en su hoja
    de superestructura y TAB50/TAB51 (la variante MACIZA que se fue) en la planta de ES-000, sin
    H=; los 31 muros que EST-004 cuenta están en su hoja con líneas de MUROS1 y el único vano
    leído es el hueco de 1.25 m de la cara sur de W31 (ES-200, caras a 0.20 m). Las áreas, largos
    y clases son del motor (REPRODUCE); con ellas compara las variantes del gold;
  - R259: DC (EST-CADENAS Y DALAS de ES-200) se define en el detalle «D-C» AF02D porque el título
    de su bloque (el texto de una sola palabra de familia más cercano bajo él, en su columna) es
    «DALA» AF011, con su armado («#») en medio.

Qué REPRODUCE (reglas del motor aplicadas a mano sobre esos hechos; no son hechos del plano):
  - criticos_total = 4 × colocaciones (la tarjeta tiene 4 datos críticos por elemento);
  - pilote criticos_del_plano = 3 por pilote (sección, longitudinales, estribos del cuadro; la
    longitud no) y «2E#3 VER CORTE» cuenta como estribo del plano;
  - dado criticos_del_plano = su altura (del corte) + su sección medida en planta salvo donde su
    sección propia está dibujada y no se leyó (un «DADO D-n» fuera de su bloque de corte: R113, la
    medida es supuesto) o su contorno no es un rectángulo (área < 98 % de su caja);
  - la severidad de la verificación 1: sin definición y sin nota de su familia → bloquea; con nota
    → duda (su aviso, el de los muros «sin marca», queda sin cerca: R265);
  - la verificación 2: definida y nunca escrita en una planta (sólo las familias que la lectura lee
    y los dados D-);
  - la partición de la verificación 10 en duda (muros MC-, dados D-, CM-1: marca de elemento de
    concreto o columna escrita sin elemento) y lo que no es duda (nervaduras de EST-LOSA NERVADA,
    placas PL- y conexiones CN-, referencias DET-, letras de corte R1/R1'): esa taxonomía es del
    motor; aquí se aplica por prefijo y capa, a la vista.

Sin diferencias conocidas: la de 10/duda D-C se fue con la Tarea 15b (R259).

Handles fijos que usa (cada uno se imprime con lo que el dibujo tiene en él; si no existe o no
dice lo esperado, sale como diferencia o a la vista): los de ``JUNTA_ESPERADA``,
``CORTES_DE_DADO`` y ``LADOS_DE_PLANTA``, E2EC4 y 35521 (contornos de D-X y de D-4), 25DC7, 25DE4,
C578B y C579B (los contornos de muro que el motor coloca sin marca), 98104 y 98102 («2#3» y «2#4» de
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


# Tarea 15b: la junta de cada etiqueta de EST-DADOS de ES-000 con su contorno (handle de la
# etiqueta → handle del contorno), sacada del listado crudo de distancias y revisada en un render;
# la de D-X (E2EC5) no está: empata entre E2EC4 y 35521.
JUNTA_ESPERADA = {
    "353B8": "353B6", "D6E45": "D6E44", "C8E78": "C8E77", "3552C": "3552F", "3550B": "3550D",
    "25F27": "25F29", "353D5": "2608F", "35522": "35521", "35547": "35542", "EB0C5": "3554C",
    "F08F4": "F08F3", "EB0CB": "3555C", "353BD": "353BC", "353C4": "353C3", "353C9": "353C8",
    "353CE": "353CD", "3551C": "35517", "EB0C9": "35559", "35527": "35526", "EB0C7": "35549",
    "353B0": "35612", "35533": "35532",
}
ALCANCE_DADO = 0.6  # m, de la caja de letras de la etiqueta a su contorno
# Los cortes de los dados (ES-005/006/007): título del corte → (marca, cota de su altura, su texto,
# título del bloque «DADO D-n», hoja). Leídos en el render de cada hoja: la cota vertical junto al
# cuerpo del dado en su corte; el título del bloque nombra la marca con la palabra DADO.
CORTES_DE_DADO = {
    "4274E": ("D-1", "42766", "100", "427C6", "ES-005"),
    "42FFB": ("D-2A", "43016", "100", "42FB2", "ES-005"),
    "429CF": ("D-3", "429EA", "100", "42A36", "ES-005"),
    "43588": ("D-3A", "4357A", "100", "435C1", "ES-005"),
    "4330F": ("D-3B", "43304", "120", "43332", "ES-005"),
    "42DA5": ("D-4", "42DDE", "100", "42DD4", "ES-005"),
    "44C24": ("D-4A", "44C1B", "100", "44C4B", "ES-006"),
    "45A5F": ("D-4B", "45A56", "140", "45A86", "ES-006"),
    "45F4E": ("D-4C", "45F7C", "120", "45F89", "ES-006"),
    "D7449": ("D-5", "D743D", "100", "D7406", "ES-006"),
    "450F9": ("D-5A", "450F0", "120", "45130", "ES-006"),
    "4642D": ("D-5B", "46424", "140", "46464", "ES-006"),
    "E46B8": ("D-1A", "E46D0", "100", "E472E", "ES-007"),
    "E4CB8": ("D-1B", "E4CCF", "120", "E4D08", "ES-007"),
    "E43F7": ("D-1C", "E440E", "100", "E444D", "ES-007"),
}
# Las cotas verticales de las plantas de los dados (sus lados, nunca su altura): D-3B «160»,
# D-4B «170», D-5A «160», D-5B «180», D-1C «115», D-1B «145».
LADOS_DE_PLANTA = {"4334C": "160", "45A14": "170", "450A9": "160", "463DD": "180",
                   "E449A": "115", "E4D59": "145"}


def contornos_de_dado(msp) -> list[dict]:
    """Las polilíneas cerradas de EST-DADOS: handle, caja, centro, lados (cm), área (shoelace)."""
    salida = []
    for e in msp.query("LWPOLYLINE[layer=='EST-DADOS']"):
        if not e.closed:
            continue
        pts = [(p[0], p[1]) for p in e.get_points()]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        area = abs(sum(pts[i][0] * pts[i - 1][1] - pts[i - 1][0] * pts[i][1]
                       for i in range(len(pts)))) / 2
        caja = (min(xs), min(ys), max(xs), max(ys))
        salida.append({"h": e.dxf.handle, "caja": caja, "cx": (caja[0] + caja[2]) / 2,
                       "cy": (caja[1] + caja[3]) / 2, "area": area,
                       "lados": f"{round((caja[2] - caja[0]) * 100)}x"
                                f"{round((caja[3] - caja[1]) * 100)}",
                       # REPRODUCE: un rectángulo a ejes si su área es ≥ 98 % la de su caja
                       # (la regla del motor; 3555C de D-4A va chueco 2e-5, D6E44 de D-1A es un
                       # trapecio: 0.80).
                       "rect": area >= 0.98 * (caja[2] - caja[0]) * (caja[3] - caja[1])})
    return salida


def caja_de_letras(t: dict) -> tuple[float, float, float, float]:
    """La caja de las letras de un texto (ezdxf, aproximada por su fuente)."""
    from ezdxf import bbox

    b = bbox.extents([t["ent"]], fast=True)
    return (b.extmin.x, b.extmin.y, b.extmax.x, b.extmax.y)


def dist_cajas(a, b) -> float:
    dx = max(b[0] - a[2], 0.0, a[0] - b[2])
    dy = max(b[1] - a[3], 0.0, a[1] - b[3])
    return math.hypot(dx, dy)


def _centro(e) -> tuple[float, float]:
    pts = list(e.get_points())
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)


def caja_dentro(a, b, holgura: float = 1e-4) -> bool:
    """Si la caja ``a`` está dentro de ``b`` (con una holgura de dibujo)."""
    return (a[0] >= b[0] - holgura and a[1] >= b[1] - holgura
            and a[2] <= b[2] + holgura and a[3] <= b[3] + holgura)


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


# Tarea 15d (R269): las variantes se reparten sobre lo que el renglón cuenta. Cada elemento: su
# caja (la del motor: el elemento bajo prueba), su clase (espesor H= de la losa; espesor del muro),
# su hoja esperada y su área o largo (lecturas del motor, REPRODUCE: el crudo no las da solas — los
# tableros son celdas entre trabes, no contornos cerrados).
LOSAS_MACIZAS_CONTADAS = {
    "TAB3": (20, "ES-100", (197.351, 50.677, 201.876, 52.952), 9.955),
    "TAB33": (20, "ES-100", (202.026, 50.677, 204.076, 52.952), 4.664),
    "TAB5": (30, "ES-200", (190.551, 8.277, 210.726, 18.277), 34.613),
    "TAB9": (12, "ES-200", (193.076, 8.602, 194.551, 9.777), 1.733),
    "TAB15": (20, "ES-300", (197.276, -20.648, 198.376, -19.398), 1.375),
    "TAB16": (20, "ES-300", (192.776, -22.048, 196.976, -16.948), 21.42),
    "TAB19": (20, "ES-300", (192.776, -26.498, 196.976, -22.348), 17.43),
    "TAB22": (12, "ES-300", (197.051, -26.723, 212.551, -16.723), 27.259),
}
# Los dos tableros macizos de la planta de cimentación (sin H=): la variante EST-013.MACIZA.
LOSAS_MACIZAS_FUERA = {
    "TAB50": (190.851, 87.102, 193.626, 87.902),
    "TAB51": (190.851, 86.152, 193.626, 86.902),
}
MUROS_CONTADOS = {
    # muro: (clase en cm, hoja, caja, largo)
    "W26": (10, "ES-400", (218.608, -49.168, 220.671, -49.108), 2.063),
    "W33": (10, "ES-200", (218.608, 20.832, 220.671, 20.892), 2.063),
    "W37": (10, "ES-100", (218.608, 55.832, 220.671, 55.892), 2.063),
    "W59": (10, "ES-200", (204.426, 12.802, 204.526, 15.752), 1.75),
    "W22": (15, "ES-400", (204.076, -57.198, 205.826, -57.048), 1.75),
    "W23": (15, "ES-400", (205.676, -55.848, 208.426, -55.698), 2.6),
    "W24": (15, "ES-400", (198.376, -54.398, 204.726, -54.248), 5.25),
    "W25": (15, "ES-400", (205.826, -53.948, 208.426, -53.798), 2.6),
    "W57": (15, "ES-400", (203.776, -54.248, 203.926, -52.398), 1.85),
    "W61": (15, "ES-400", (205.676, -55.848, 205.826, -51.948), 1.85),
    "W27": (15, "ES-300", (205.676, -22.648, 210.326, -22.498), 4.5),
    "W29": (15, "ES-300", (206.776, -18.948, 210.526, -18.798), 3.6),
    "W41": (15, "ES-300", (192.576, -24.648, 192.726, -22.048), 2.3),
    "W52": (15, "ES-300", (198.376, -26.498, 198.526, -22.048), 4.05),
    "W54": (15, "ES-300", (201.876, -26.498, 202.026, -22.048), 4.45),
    "W60": (15, "ES-300", (204.576, -26.498, 204.726, -23.848), 2.65),
    "W32": (15, "ES-200", (192.576, 16.052, 196.426, 16.202), 3.55),
    "W42": (15, "ES-200", (192.576, 14.152, 192.726, 16.202), 1.9),
    "W58": (15, "ES-200", (204.076, 12.802, 204.226, 15.752), 1.75),
    "W36": (15, "ES-100", (198.676, 50.602, 201.876, 50.752), 1.6),
    "W46": (15, "ES-100", (194.776, 49.152, 194.926, 51.502), 2.15),
    "W50": (15, "ES-100", (197.276, 49.152, 197.426, 51.502), 2.15),
    "W55": (15, "ES-100", (201.876, 49.152, 202.026, 52.952), 2.2),
    "W48": (20, "ES-400", (196.926, -55.848, 197.126, -51.748), 3.9),
    "W30": (20, "ES-300", (191.976, -16.948, 210.526, -16.748), 4.25),
    "W49": (20, "ES-300", (196.976, -21.098, 197.176, -16.948), 4.05),
    "W31": (20, "ES-200", (193.576, 14.152, 203.126, 14.352), 9.55),
    "W34": (20, "ES-100", (192.576, 49.152, 194.326, 49.352), 1.55),
    "W35": (20, "ES-100", (198.376, 49.152, 200.426, 49.352), 1.9),
    "W43": (20, "ES-100", (192.576, 49.152, 192.776, 51.202), 1.65),
    "W28": (30, "ES-300", (194.576, -22.348, 198.526, -22.048), 3.8),
}
# El único vano que EST-004 leyó (ancho del motor): en W31, ES-200.
VANO_LEIDO = ("W31", 1.25)
# REPRODUCE: altura de entrepiso por hoja (niveles NTC del plano, como los toma el motor) y el
# pretil supuesto de la azotea; altura de vano supuesta.
ALTURA_POR_HOJA = {"ES-100": 3.60, "ES-200": 3.60, "ES-300": 3.20, "ES-400": 0.90}
ALTURA_DE_VANO_M = 2.10


def _segmentos(msp, capa: str):
    for e in msp.query(f"LINE[layer=='{capa}']"):
        yield (e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)
    for e in msp.query(f"LWPOLYLINE[layer=='{capa}']"):
        pts = [(p[0], p[1]) for p in e.get_points()]
        if e.closed:
            pts.append(pts[0])
        yield from zip(pts, pts[1:], strict=False)


def _toca(seg, caja, tol: float = 0.01) -> bool:
    return any(caja[0] - tol <= p[0] <= caja[2] + tol and caja[1] - tol <= p[1] <= caja[3] + tol
               for p in seg)


def variantes_15d(msp, gold: dict, hoja, en_planta) -> None:
    """Tarea 15d (R269). VERIFICA: (EST-013) los tableros macizos contados están en su hoja de
    superestructura y, donde la caja trae un solo «LOSA MACIZA … H=», es el de su clase; TAB50 y
    TAB51 (la variante MACIZA que se fue) están en la planta de ES-000 y sin H=; (EST-004) cada muro
    contado toca líneas de MUROS1 y su caja está en su hoja; el vano leído es el hueco de 1.25 m de
    la cara sur de W31 (MUROS1, caras a 0.20 m) en ES-200. NO verifica (REPRODUCE): áreas, largos y
    clases, lecturas del motor; que TAB50/TAB51 sean maciza; que no haya otro vano."""
    conceptos = gold["money"]["concepts"]
    print("\nTarea 15d — EST-013, tableros macizos:")
    textos_h = []
    for e in msp.query("TEXT MTEXT[layer=='EST-LOSA MACIZA']"):
        if m := re.search(r"H=(\d+)", texto(e)):
            textos_h.append((e.dxf.insert.x, e.dxf.insert.y, int(m.group(1))))
    for tab, (h, hj, c, _area) in LOSAS_MACIZAS_CONTADAS.items():
        cx, cy = (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
        dentro = {v for x, y, v in textos_h if c[0] <= x <= c[2] and c[1] <= y <= c[3]}
        print(f"  {tab}: hoja {hoja(cx, cy)}, H= en su caja {sorted(dentro) or '—'} (clase {h})")
        if hoja(cx, cy) != hj or en_planta(cx, cy) != hj:
            dif(f"{tab} no está en la planta de {hj}")
        if len(dentro) == 1 and dentro != {h}:
            dif(f"{tab}: su caja dice H={dentro}, la clase es {h}")
    achurado = list(_segmentos(msp, "EST-LOSA MACIZA"))
    for tab, c in LOSAS_MACIZAS_FUERA.items():
        cx, cy = (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
        trazos = sum(1 for s in achurado if _toca(s, c, 0.0))
        con_h = [v for x, y, v in textos_h if c[0] <= x <= c[2] and c[1] <= y <= c[3]]
        print(f"  {tab}: en la planta de {en_planta(cx, cy)} (hoja {hoja(cx, cy)}), H= "
              f"{con_h or '—'}; a la vista: {trazos} trazos de EST-LOSA MACIZA con un punto en su "
              "caja (que sea maciza es lectura del motor)")
        if en_planta(cx, cy) != "ES-000" or hoja(cx, cy) != "ES-000" or con_h:
            dif(f"{tab} no es un tablero de la planta de cimentación sin H=")
    calculado = {}
    for h, _hj, _c, area in LOSAS_MACIZAS_CONTADAS.values():
        clave = f"EST-013.MACIZA-{h}"
        calculado[clave] = calculado.get(clave, 0.0) + area * h / 100
    calculado = {k: round(v, 3) for k, v in calculado.items()}
    var = conceptos["EST-013"].get("variants") or {}
    print(f"  variantes (áreas del motor × H): {calculado}; gold {var}")
    if set(var) != set(calculado) or any(abs(var[k] - v) > 0.001 for k, v in calculado.items()):
        dif("las variantes de EST-013")

    print("\nTarea 15d — EST-004, muros contados y el vano leído:")
    muros1 = list(_segmentos(msp, "MUROS1"))
    for muro, (clase, hj, c, _largo) in MUROS_CONTADOS.items():
        cx, cy = (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
        if hoja(cx, cy) != hj or not any(_toca(s, c) for s in muros1):
            dif(f"{muro} ({clase} cm): hoja {hoja(cx, cy)}, se esperaba {hj} con líneas de MUROS1")
    print(f"  {len(MUROS_CONTADOS)} muros contados: cada uno en su hoja, con líneas de MUROS1")
    muro, ancho = VANO_LEIDO
    clase, hj, c, _largo = MUROS_CONTADOS[muro]
    caras: dict[float, list[tuple[float, float]]] = defaultdict(list)
    for a, b in muros1:
        if (abs(a[1] - b[1]) < 1e-3 and c[1] - 0.01 <= a[1] <= c[3] + 0.01
                and all(c[0] - 0.01 <= p[0] <= c[2] + 0.01 for p in (a, b))):
            caras[round(a[1], 3)].append(tuple(sorted((a[0], b[0]))))
    huecos = {}
    for y, tramos in caras.items():
        tramos.sort()
        fin, hs = tramos[0][1], []
        for ini, f in tramos[1:]:
            if ini > fin + 1e-6:
                hs.append((round(fin, 3), round(ini, 3), round(ini - fin, 3)))
            fin = max(fin, f)
        huecos[y] = hs
    print(f"  {muro}: caras de MUROS1 {sorted(caras)}, huecos interiores {huecos}")
    ys = sorted(caras)
    sur = huecos.get(ys[0], []) if ys else []
    if (len(ys) != 2 or abs(ys[1] - ys[0] - clase / 100) > 0.002
            or not any(abs(h[2] - ancho) <= 0.002 for h in sur) or hoja(c[0], c[1]) != hj):
        dif(f"el vano leído de {ancho} m no es el hueco de la cara sur de {muro} "
            f"({clase} cm, {hj})")
    print("  a la vista: el hueco de 1.25 m es el castillo de 0.30 (196.976–197.276) más 0.95 m "
          "bajo el cerramiento CR-2 (EST-CERRAMIENTOS 197.276–198.226); el ancho es el del motor")
    calculado = {}
    for _m, (clase, hj, _c, largo) in MUROS_CONTADOS.items():
        clave = f"EST-004.BLOCK-{clase}"
        calculado[clave] = calculado.get(clave, 0.0) + largo * ALTURA_POR_HOJA[hj]
    clave = f"EST-004.BLOCK-{MUROS_CONTADOS[muro][0]}"
    calculado[clave] -= ancho * ALTURA_DE_VANO_M
    calculado = {k: round(v, 3) for k, v in calculado.items()}
    var = conceptos["EST-004"].get("variants") or {}
    print(f"  variantes (largos del motor × altura de su hoja − vano × 2.10): {calculado}; "
          f"gold {var}")
    if set(var) != set(calculado) or any(abs(var[k] - v) > 0.001 for k, v in calculado.items()):
        dif("las variantes de EST-004")
    if abs(sum(calculado.values()) - conceptos["EST-004"]["quantity"]) > 0.002:
        dif(f"las variantes de EST-004 suman {sum(calculado.values())}, el renglón "
            f"{conceptos['EST-004']['quantity']}")


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
                       "hoja": hoja(x, y), "planta": en_planta(x, y), "bloque": "/" in h,
                       "ent": e})
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
    # Tarea 15b: los dados D-n de ES-000. Cada etiqueta de EST-DADOS es del contorno de EST-DADOS
    # más cercano a su caja de letras; la de D-X queda a la misma distancia de dos (E2EC4 y 35521)
    # y no es de ninguno. Las juntadas son colocaciones de la familia dado (la capa lo dice).
    dados_c = [c for c in contornos_de_dado(msp) if en_planta(c["cx"], c["cy"]) == "ES-000"]
    tags_d = [t for t in textos if t["capa"] == "EST-DADOS" and t["planta"] == "ES-000"]
    print(f"dados: {len(dados_c)} contornos cerrados de EST-DADOS en la planta de ES-000, "
          f"{len(tags_d)} etiquetas en EST-DADOS")
    if len(dados_c) != 23 or len(tags_d) != 23:
        dif(f"dados: {len(dados_c)} contornos y {len(tags_d)} etiquetas, se esperaban 23 y 23")
    junta: dict[str, str] = {}
    for t in sorted(tags_d, key=lambda t: t["t"]):
        caja_t = caja_de_letras(t)
        ds = sorted((dist_cajas(caja_t, c["caja"]), c["h"]) for c in dados_c)
        (d1, c1), (d2, c2) = ds[0], ds[1]
        print(f"  {t['t']:5} {t['h']:6} → {c1} a {d1:.2f} m (el siguiente, {c2}, a {d2:.2f} m)")
        if d1 > ALCANCE_DADO:
            dif(f"{t['t']} {t['h']} a {d1:.2f} m de todo contorno de EST-DADOS")
        if abs(d2 - d1) < 0.01:
            empate = {c1, c2}
            if (t["t"].upper(), t["h"], empate) != ("D-X", "E2EC5", {"E2EC4", "35521"}):
                dif(f"{t['t']} {t['h']} empata entre {sorted(empate)}")
            continue
        if d2 < 1.25 * d1:
            dif(f"{t['t']} {t['h']}: el segundo contorno ({c2}, {d2:.2f}) casi tan cerca")
        junta[t["h"]] = c1
    if junta != JUNTA_ESPERADA:
        dif(f"junta etiqueta→dado: crudo {junta}, esperada {JUNTA_ESPERADA}")
    if len(set(junta.values())) != len(junta):
        dif("dos etiquetas de dado escogen el mismo contorno")
    por_handle = {c["h"]: c for c in dados_c}
    afuera, adentro = por_handle.get("35521"), por_handle.get("E2EC4")
    if afuera is None or adentro is None or not caja_dentro(adentro["caja"], afuera["caja"]):
        dif("E2EC4 (D-X) no está dibujado dentro de 35521 (D-4)")
    else:
        print(f"  E2EC4 ({adentro['lados']}) dentro de 35521 ({afuera['lados']}); su área "
              f"{adentro['area']:.4f} m² es menor que la de una zapata (0.55² = 0.3025): no se "
              "coloca, y su etiqueta D-X queda en duda")
    sin_etiqueta = sorted(set(por_handle) - set(junta.values()) - {"E2EC4"})
    if sin_etiqueta:
        dif(f"dados sin etiqueta: {sin_etiqueta}")
    for t in tags_d:
        if t["h"] in junta:
            etiquetas.append({**t, "familia": "dado", "marca": t["t"].upper(),
                              "contorno": por_handle[junta[t["h"]]]})
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
    # R259: una marca de tipo de dala sin guion («DC», en EST-CADENAS Y DALAS) se define en el
    # detalle que la escribe con guion («D-C» AF02D) sólo si el título de su bloque —el texto más
    # cercano bajo él, en su columna, que es sólo una palabra de familia— dice DALA, con su armado
    # («#») en medio.
    for m in sorted(colocadas - definidas):
        if not re.fullmatch(r"CI|DC|DA\d{1,2}[A-Z]?", m):
            continue
        for t in textos:
            escrito = t["t"].upper().strip()
            if "-" not in escrito or escrito.replace("-", "") != m:
                continue
            bajo = sorted((u for u in textos if u["hoja"] == t["hoja"] and u is not t
                           and abs(u["x"] - t["x"]) <= 0.8 and 0 < t["y"] - u["y"] <= 3.25),
                          key=lambda u: t["y"] - u["y"])
            titulo = next((u for u in bajo if re.fullmatch(
                r"(DALAS?|CADENAS?|DADOS?|ZAPATAS?|TRABES?|CASTILLOS?|COLUMNAS?)",
                u["t"].upper().strip())), None)
            armado_entre = [u for u in bajo if titulo is not None and "#" in u["t"]
                            and u["y"] > titulo["y"]]
            print(f"  {m}: «{t['t']}» {t['h']} ({t['hoja']}), título de su bloque "
                  f"{titulo and (titulo['h'], titulo['t'])}, armado entre "
                  f"{[(u['h'], u['t']) for u in armado_entre]}")
            if titulo is not None and titulo["t"].upper().startswith("DALA") and armado_entre:
                definidas.add(m)
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

    # ---------------------------------------------------------------- dados: alturas
    # Tarea 15b. Cada corte «D-n / CORTE / X-X'» de ES-005/006/007 lleva su altura en una cota
    # vertical junto al cuerpo del dado (``CORTES_DE_DADO``, leídos en el render). Se verifica:
    # el título del corte y el de su bloque («DADO D-n»: la palabra DADO lo dice, R159), la cota
    # (vertical, su texto, su hoja, encima del título) y que mide el cuerpo del dado dibujado en el
    # corte: dos trazos verticales del dibujo (los lados del dado) van de su punto de abajo al de
    # arriba (± 0.03). Su valor es su texto, no lo que mide: los cortes son «SIN ESCALA».
    verticales = []
    for e in msp.query("LINE"):
        a0, b0 = e.dxf.start, e.dxf.end
        if abs(a0.x - b0.x) < 1e-3 and abs(a0.y - b0.y) > 1.0:
            verticales.append((a0.x, min(a0.y, b0.y), max(a0.y, b0.y)))
    for e in msp.query("LWPOLYLINE"):
        pts = list(e.get_points())
        for i in range(len(pts) - (0 if e.closed else 1)):
            p0, p1 = pts[i], pts[(i + 1) % len(pts)]
            if abs(p0[0] - p1[0]) < 1e-3 and abs(p0[1] - p1[1]) > 1.0:
                verticales.append((p0[0], min(p0[1], p1[1]), max(p0[1], p1[1])))
    por_h = {t["h"]: t for t in textos}
    altura_de: dict[str, float] = {}
    for th, (marca, ch, valor, bh, hoja_e) in CORTES_DE_DADO.items():
        t, b = por_h.get(th), por_h.get(bh)
        renglones = [r.strip().upper() for r in (t["t"] if t else "").split("\n") if r.strip()]
        if t is None or renglones[:2] != [marca, "CORTE"] or t["hoja"] != hoja_e:
            dif(f"corte {th}: título {t and t['t']!r} en {t and t['hoja']}")
            continue
        if b is None or " ".join(b["t"].upper().split()) != f"DADO {marca}" or b["hoja"] != hoja_e:
            dif(f"corte {th}: título del bloque {bh} {b and b['t']!r}")
        e = doc.entitydb.get(ch)
        if e is None or e.dxftype() != "DIMENSION" or e.dimtype & 7 != 0:
            dif(f"corte {th}: la cota {ch} no es una cota lineal")
            continue
        p2, p3 = e.dxf.defpoint2, e.dxf.defpoint3
        y0, y1 = sorted((p2.y, p3.y))
        x = min(p2.x, p3.x)
        cuerpo = [v for v in verticales
                  if x - 0.5 <= v[0] <= x + 6.0 and abs(v[1] - y0) <= 0.03
                  and abs(v[2] - y1) <= 0.03]
        ok = (round(float(e.dxf.get("angle") or 0)) % 180 == 90 and e.dxf.text == valor
              and hoja(p2.x, p2.y) == hoja_e and y0 > t["y"] - 0.2 and len(cuerpo) >= 2)
        print(f"  corte {marca:5} {th}: cota {ch} «{e.dxf.text}» (mide {e.get_measurement():.2f}, "
              f"capa {e.dxf.layer}), {len(cuerpo)} lados del cuerpo de {y0:.2f} a {y1:.2f}; "
              f"bloque {bh} «{b and b['t']}»")
        if not ok:
            dif(f"corte {marca} {th}: la cota {ch} no es su altura vertical «{valor}» sobre el "
                "cuerpo del dado")
            continue
        altura_de[marca] = int(valor) / 100
    for ch, valor in LADOS_DE_PLANTA.items():
        e = doc.entitydb.get(ch)
        if e is None or e.dxftype() != "DIMENSION" or e.dxf.text != valor:
            dif(f"lado de planta {ch}: {e and e.dxf.get('text')!r}")
            continue
        p2, p3 = e.dxf.defpoint2, e.dxf.defpoint3
        bajo = [t for t in textos if t["hoja"] == hoja(p2.x, p2.y)
                and re.search(r"\b(PLANTA|CORTE)\b", t["t"].upper())
                and t["y"] < min(p2.y, p3.y)]
        suyo = min(bajo, key=lambda t: math.hypot(t["x"] - p2.x, t["y"] - p2.y), default=None)
        if suyo is None or "PLANTA" not in suyo["t"].upper():
            dif(f"lado de planta {ch}: su título más cercano abajo es {suyo and suyo['t']!r}")
    print(f"  lados de planta (nunca alturas; su título más cercano abajo es una PLANTA): "
          f"{LADOS_DE_PLANTA}")
    colocadas_d = Counter(t["marca"] for t in etiquetas if t["familia"] == "dado")
    sin_corte = sorted(set(colocadas_d) - set(altura_de))
    if sin_corte:
        dif(f"dados colocados sin la altura de su corte: {sin_corte}")
    # CIM-002: el área de cada contorno colocado × la altura de su corte.
    cim_002 = sum(t["contorno"]["area"] * altura_de.get(t["marca"], 0.0)
                  for t in etiquetas if t["familia"] == "dado")
    print(f"  CIM-002 = Σ área × altura de su corte = {cim_002:.4f} m³ "
          f"({ {m: n for m, n in sorted(colocadas_d.items())} })")
    # REPRODUCE (R113, regla del motor): la sección de un dado que tiene su propio dibujo de
    # sección sin leer (un «DADO D-n» fuera de su bloque de corte y fuera de las plantas: las
    # elevaciones de ES-500/501, el corte R1-R1' de ES-007) es la medida en planta como supuesto;
    # las demás, medida en planta si su contorno es un rectángulo. criticos_del_plano de dado = una
    # altura por dado + esas secciones medidas.
    bloques = {bh for _m, _c, _v, bh, _h in CORTES_DE_DADO.values()}
    con_dibujo: set[str] = set()
    for t in textos:
        palabras = re.split(r"[\s/]+", t["t"].upper())
        if "DADO" in palabras and t["h"] not in bloques and t["planta"] is None:
            con_dibujo |= {w for w in palabras if re.fullmatch(r"D-\w{1,3}", w)}
    medidas_d = [t for t in etiquetas if t["familia"] == "dado"
                 and t["marca"] not in con_dibujo and t["contorno"]["rect"]]
    criticos_dado = sum(colocadas_d.values()) + len(medidas_d)
    print(f"  marcas con su dibujo de sección sin leer: {sorted(con_dibujo)}; secciones medidas: "
          f"{sorted(t['marca'] for t in medidas_d)}; criticos_del_plano de dado {criticos_dado}")
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
        if fam == "dado":
            esperado["criticos_del_plano"] = criticos_dado
        for campo, v in campos.items():
            if esperado.get(campo) != v:
                dif(f"{fam}.{campo}: crudo {esperado.get(campo)}, gold {v}")
    leidas = {"castillo", "columna", "trabe", "contratrabe", "dala", "cerramiento", "pilote"}
    if set(por_hoja) - set(est["por_familia"]) - {"zapata", "dado", "muro_concreto"}:
        dif(f"familias con colocaciones fuera del gold: {set(por_hoja) - leidas}")
    # 1/aviso queda sin cerca (R265): su único aviso dice «sin marca» de los muros, y el plano
    # dibuja los suyos en EST-MURO CONCRETO y escribe sus MC-n sobre el achurado; el motor coloca
    # algunos de esos contornos sin juntarles su MC-n (muro_concreto sigue sin cerca). Sólo se
    # imprime a la vista; que ningún dado quede sin su D-n se VERIFICA arriba (22 juntados, el
    # 23.º contorno es D-X, más chico que una zapata) y lo cercan las colocaciones de dado.
    muros_c = sorted(e.dxf.handle for e in msp.query("LWPOLYLINE[layer=='EST-MURO CONCRETO']")
                     if e.closed and en_planta(*_centro(e)))
    print(f"contornos cerrados de EST-MURO CONCRETO en las plantas: {len(muros_c)} "
          "(el motor coloca 25DC7, 25DE4, C578B y C579B, sin marca)")
    for h in ("25DC7", "25DE4", "C578B", "C579B"):
        if h not in muros_c:
            dif(f"el contorno de muro {h} no está en una planta")
    v1_aviso = ["(sin marca)"] if muros_c else []
    crudo_hallazgos = {"1/bloquea": v1_bloquea, "1/duda": v1_duda, "1/aviso": v1_aviso,
                       "2/aviso": v2, "10/duda": v10_duda}
    # Diferencias conocidas, cada una con su razón (el gold las cerca a sabiendas y lo dice en sus
    # notas): la cerca es la del motor de hoy, y se mueve cuando el motor deje de equivocarse.
    conocidas: dict[tuple[str, str], str] = {}
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
    cim2 = gold["money"]["concepts"].get("CIM-002")
    if (cim2 is None or cim2["source"] != "crudo"
            or abs(cim2["quantity"] - cim_002) > 0.001 * cim_002):
        dif(f"CIM-002: crudo {cim_002:.4f}, gold {cim2 and (cim2['quantity'], cim2['source'])}")
    variantes_15d(msp, gold, hoja, en_planta)
    print("\nDIFERENCIAS:", "ninguna" if not diferencias else len(diferencias))
    return 1 if diferencias else 0


if __name__ == "__main__":
    sys.exit(main())
