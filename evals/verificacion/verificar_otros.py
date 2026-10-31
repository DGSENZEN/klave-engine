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

prueba-1 (Tarea 15c: una etiqueta es de una sola vista). Qué VERIFICA (y compara): sus encabezados
(textos de 0.3 o más que nombran planta, detalle o simbología: las cuatro plantas, dos «ARMADO DE
CASTILLOS» y dos «simbología»), cada uno en el centro de su texto (su ancho medido con la fuente de
su estilo por ezdxf, su anclaje); la extensión dibujada de cada planta, su rejilla (las líneas de
S-GRID que se cruzan, dos o más en cada sentido; la caja de sus líneas), del título de planta que le
queda claramente más cerca entre TODOS los encabezados (el siguiente, al doble o más: el margen se
imprime, también el de los puntos de inserción, que no decide: la cimentación tiene 2.40 por centros
y 1.85 por inserciones, porque «ARMADO DE CASTILLOS» se ancla en su esquina de arriba a la
izquierda; por centros se sostiene mientras ese texto mida 2.92 m o más, y mide 8.27), y que ninguna
caja toque a otra; cada etiqueta de castillo (capa castillos, «K-n»): la planta cuya rejilla la
contiene, o, fuera de toda rejilla, la de la caja claramente más cercana —ninguna en dos, ninguna
sin planta— y cuántas hay en cada planta contra ``por_vista`` y ``por_familia`` del gold, exactas.
Los dos muros que la Tarea 15c cambió de planta: W39, el poniente exterior de PLANTA BAJA (sus
líneas A-WALL en x 50.725–50.905 van de −62.298 a −45.473: 16.825 m), dentro de la rejilla de
PLANTA BAJA; W18, el norte de la AZOTEA (su cara interior A-WALL en y −63.724, 5.22 m), dentro de
la de AZOTEA.

prueba-1, Tarea 15e (R270): cada planta toma el nivel que su plano declara. VERIFICA (y compara):
cada leyenda «N.P.T.» de la hoja, con su handle, su texto y su inserción, y de qué planta es —la
que está justo debajo de su título (a 1 m o menos debajo y de lado); las leyendas esquemáticas de
niveles (A-FLOR-LEVL) y los cajetines (DAT) no son de ninguna—: una por planta, 0+00 / +3.45 /
+6.60 / +7.80. Y la evidencia de que el nivel de cada planta es la losa que dibuja (lectura B):
dentro de su rejilla, PLANTA BAJA y PLANTA ALTA dibujan su losa (E-VIGUETAS) y la AZOTEA dibuja
castillos y muros (A-WALL) sin ninguna línea de losa ni trabe en su planta. Con eso, las alturas
son del nivel de la planta de abajo al suyo: PLANTA BAJA 3.45, PLANTA ALTA 3.15, AZOTEA 1.20 (de
+6.60 a su nivel; R273: el dibujo no dice que todo sea pretil).
R272, VERIFICA: qué castillos y columnas de la cimentación siguen en PLANTA BAJA: la rejilla de
PLANTA BAJA corrida de la de la cimentación (las líneas S-GRID: la diferencia que más ejes junta a
2 cm, +66.12, +2.33), cada marcador de la cimentación (el más cercano a cada etiqueta) contra los
marcadores de la capa castillos de PLANTA BAJA, uno a uno, el par más cercano primero, a 0.30 m o
menos (dos castillos de ancho). 72 de 75 siguen —71 a 3 cm o menos, 5DB1 a 0.20 sobre su mismo
muro— y son el arranque de los de PLANTA BAJA; no siguen 5DAA (K-1: PLANTA BAJA dibuja ahí el
cerramiento CR-2.35) ni los dos C-1 del pórtico de IPR (5DD1, 8849): el motor les da una altura
supuesta con su duda. La cimentación no está en EST-001.
EST-001: la sección de cada castillo es el marcador cerrado más cercano a su etiqueta en la capa
castillos (el cuadro de 15×15, el de 15×30 o el círculo); R273, VERIFICA las tres en que el motor
toma otro (R166, ``R166``: 6355 K-0, su círculo 6315 0.015394 m², el motor el 15×30 62D1 de una K-2,
0.045; 6719 y 9636 K-0, sus cuadros 667C/667A 0.0225, el motor los sombreados 66C8/9635, 0.015299,
cada área medida en crudo) y con ellas la sección del motor por planta, por la altura de su planta,
contra el gold a 0.001 m³. Los conteos, las alturas y cada marcador son crudos; EST-001 no lo es
porque R166 es una lectura del motor que el crudo no da.
R271, VERIFICA: el peralte de la losa que acotan los detalles: «LOSA DE VIGUETA Y BOVEDILLA 12-5»
(65B8), 65C5 «20» = 65C3 «15» + 65C4 «5»; el de doble bovedilla (6617), 6624 = 6622 + 6623: 20 cm.
El muro de block llega bajo su losa: PLANTA BAJA 3.25, PLANTA ALTA 2.95; la AZOTEA, sin losa encima,
1.20. La dala de remate no se descuenta (E2).

Qué REPRODUCE (reglas del motor, no hechos del plano): el nombre de la vista de cada planta en el
motor (``VISTA_DEL_MOTOR``: por el orden de sus títulos); criticos_total = 4 por castillo; con los
largos que el motor leía entonces (``LARGOS_15E``) y las alturas de muro, lo que la Tarea 15e movió
del gold: EST-004 428.630 → 503.696 (antes 2.70 y pretil 0.90 supuestos, reproducido), ACA-001 y
ACA-002 857.260 → 1007.392 (dos caras).

prueba-1, Tarea 15d (R269): las variantes de EST-004 son sólo de los muros que el renglón cuenta.
VERIFICA (y compara) los 34 muros contados en su planta de superestructura, que W5, W31 y W33 (las
variantes BLOCK-19/30/36 que se fueron) no tienen líneas en la superestructura y que cada vano leído
(W40 0.77, W42 0.95, W47 1.03) es un hueco de ese ancho en una cara de su muro.

prueba-1, Tarea 15f (R275): un muro dibujado con su aplanado es un muro. El plano no dibuja la
planta dos veces: dibuja cada muro con dos contornos en la capa A-WALL, el del block y, 15 mm
afuera por cada lado, el del aplanado (las copias exactas del model space y del bloque de Revit,
desfase 0, se cuentan una vez). VERIFICA (y compara): la nota de los muros de block dice un solo
espesor, 15 cm, y la leyenda lo repite; por cada muro contado, sus caras: el núcleo de 0.150 entre
las líneas del aplanado de 0.015 (22 muros) o sólo el contorno de 0.180 = 0.150 + 2 × 0.015 (12),
su largo al eje contra el del motor a 2 mm y sus vanos (los huecos de las dos caras); con eso la
clase de cada muro (15 en los 34, la de la nota) sale del crudo. REPRODUCE EST-004, su variante
BLOCK-15 y ACA-001/ACA-002 (la altura de vano, 2.10, es supuesta: los renglones siguen del motor).
"""

import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

from ezdxf import path as ezpath
from ezdxf.fonts import fonts
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
# Antes de la Tarea 15e (las supuestas de entonces, para reproducir lo que se movió): muros 2.70 m,
# pretil 0.90 m (los castillos, 3.00 m).
ALTURA_DE_MURO_M, ALTURA_DE_PRETIL_M = 2.70, 0.90
# Tarea 15e: la leyenda de nivel de una planta y su valor («N.P.T.\t+3.45», «N.P.T.\t0+00»).
LEYENDA = re.compile(r"N\.?\s*P\.?\s*T\.?\s*(?:(0\+00)|([+-]?\d+\.\d+))", re.I)
# Lo que el renglón de cada planta movió con la Tarea 15e (los valores del gold de antes).
ANTES_15E = {"EST-001": 10.366, "EST-004": 428.630, "ACA-001": 857.260, "ACA-002": 857.260}
# Lo que dejó la Tarea 15e, con los largos y los vanos que el motor leía entonces (antes de la
# Tarea 15f: la unión de los dos contornos de cada muro, el vano de W47 a 1.00 en el aplanado).
DESPUES_15E = {"EST-004": 503.696, "ACA-001": 1007.392, "ACA-002": 1007.392}
LARGOS_15E = {"PLANTA BAJA": 77.764, "PLANTA ALTA": 65.380, "AZOTEA": 53.170}
VANOS_15E_M = 0.77 + 0.95 + 1.00


def _niveles_de_las_plantas(msp, titulos_insercion, rejillas) -> tuple[dict[str, float], int]:
    """Tarea 15e (R270), VERIFICA: cada leyenda de nivel de la hoja, dónde está y de qué planta es.
    Una leyenda es de una planta si está justo debajo de su título (su inserción a 1 m o menos
    debajo de la del título y a 1 m o menos de lado); las demás (las leyendas esquemáticas de
    niveles, los cajetines) no son de ninguna planta. Cada planta, exactamente una. Y la evidencia
    de que el nivel es la losa que dibuja la planta: dentro de su rejilla, PLANTA BAJA y PLANTA ALTA
    dibujan su losa (líneas y textos de E-VIGUETAS, trabes de E-TRABES) y castillos; la AZOTEA,
    castillos y muros (A-WALL) y ninguna línea de losa ni de trabe."""
    malos = 0
    niveles: dict[str, list[tuple[str, str, float]]] = {t: [] for t in titulos_insercion}
    print("  Tarea 15e — leyendas de nivel:")
    for e in msp.query("TEXT MTEXT"):
        m = LEYENDA.search(texto(e))
        if not m:
            continue
        valor = 0.0 if m.group(1) else float(m.group(2))
        p = (e.dxf.insert.x, e.dxf.insert.y)
        suya = [t for t, q in titulos_insercion.items()
                if 0 < q[1] - p[1] <= 1.0 and abs(q[0] - p[0]) <= 1.0]  # fmt: skip
        donde = suya[0] if len(suya) == 1 else "ninguna planta"
        print(f"    {e.dxf.handle} {e.dxf.layer} «{' '.join(texto(e).split())}» en "
              f"({p[0]:.3f}, {p[1]:.3f}) → {donde}")
        if len(suya) == 1:
            niveles[suya[0]].append((e.dxf.handle, texto(e), valor))
    salida = {}
    for t, ls in niveles.items():
        if len({v for _h, _t, v in ls}) != 1 or len(ls) != 1:
            print(f"  ** DIFERENCIA: {t} tiene las leyendas {ls}")
            malos += 1
            continue
        salida[t] = ls[0][2]
    print(f"    nivel de cada planta: {salida}")
    if salida != {"PLANTA DE CIMENTACIÓN": 0.0, "PLANTA BAJA": 3.45, "PLANTA ALTA": 6.6,
                  "AZOTEA": 7.8}:  # fmt: skip
        print("  ** DIFERENCIA en los niveles de las plantas")
        malos += 1
    # La evidencia de la lectura B, por la rejilla de cada planta.
    cuenta: dict[str, Counter] = {t: Counter() for t in rejillas}
    for e in msp:
        if e.dxftype() == "LINE":
            p = _medio(e)
        elif e.dxftype() in ("TEXT", "MTEXT", "INSERT"):
            p = (e.dxf.insert.x, e.dxf.insert.y)
        else:
            continue
        for t, caja in rejillas.items():
            if _dentro(p, caja):
                cuenta[t][e.dxf.layer] += 1
    for t in rejillas:
        c = cuenta[t]
        print(f"    {t}: E-VIGUETAS {c['E-VIGUETAS']}, E-TRABES {c['E-TRABES']}, castillos "
              f"{c['castillos']}, A-WALL {c['A-WALL']}")
    losa = {t: cuenta[t]["E-VIGUETAS"] > 0 for t in rejillas}
    az = cuenta["AZOTEA"]
    if not (losa["PLANTA BAJA"] and losa["PLANTA ALTA"] and not losa["AZOTEA"]
            and az["E-TRABES"] == 0 and az["castillos"] > 0 and az["A-WALL"] > 0):  # fmt: skip
        print("  ** DIFERENCIA: el dibujo no muestra que el nivel sea la losa de su planta")
        malos += 1
    return salida, malos


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


# Los encabezados de la hoja: los textos de 0.3 o más que nombran una planta, un detalle o la
# simbología (en PRUEBA-1: las 4 plantas, 2 «ARMADO DE CASTILLOS» y 2 «simbología»).
ENCABEZADO = re.compile(r"PLANTA|AZOTEA|ARMADO|SIMBOLOG|DETALLE|CORTE|CUADRO|NOTAS|TABLA", re.I)


def _centro_de_texto(doc, e) -> tuple[float, float]:
    """El centro del texto por su propia extensión: su ancho medido con la fuente de su estilo
    (ezdxf, sin el motor; una SHX como «txt» la mide ezdxf con su fuente de reemplazo), su alto, y
    su punto de anclaje (MTEXT: 1–9, arriba/medio/abajo × izquierda/centro/derecha; TEXT:
    izquierda sobre la línea base)."""
    alto = e.dxf.char_height if e.dxftype() == "MTEXT" else e.dxf.height
    estilo = doc.styles.get(e.dxf.get("style", "Standard"))
    archivo = (estilo.dxf.font if estilo is not None else "") or "arial.ttf"
    ancho = fonts.make_font(archivo, cap_height=alto).text_width(texto(e).replace("\t", " "))
    x, y = e.dxf.insert.x, e.dxf.insert.y
    if e.dxftype() == "MTEXT":
        fila, columna = divmod(e.dxf.attachment_point - 1, 3)
        return (x + ancho * (0.5 - columna / 2), y - alto * (0.5 - fila / 2))
    return (x + ancho / 2, y + alto / 2)


def _rejillas(msp, titulos, encabezados) -> tuple[dict[str, tuple], int]:
    """La rejilla de cada planta: las líneas de S-GRID que se cruzan (dos o más en cada sentido),
    la caja de sus líneas, del título de planta que le queda claramente más cerca entre todos los
    encabezados de la hoja (planta, detalle o simbología): el siguiente, al doble o más. Cada
    encabezado está en el centro de su texto; se imprime también el margen por sus puntos de
    inserción, que no deciden."""
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
        cerca = sorted((_a_caja(c, caja), t) for t, c, _i in encabezados)
        por_insercion = sorted((_a_caja(i, caja), t) for t, _c, i in encabezados)
        margen = cerca[1][0] / cerca[0][0] if cerca[0][0] else math.inf
        margen_i = por_insercion[1][0] / por_insercion[0][0] if por_insercion[0][0] else math.inf
        print(f"  rejilla de {len(g)} ejes, caja {tuple(round(c, 2) for c in caja)}: encabezados "
              f"a {[(t, round(d, 2)) for d, t in cerca[:2]]}, margen {margen:.2f} (por inserción "
              f"{margen_i:.2f}: {[(t, round(d, 2)) for d, t in por_insercion[:2]]})")  # fmt: skip
        if margen <= 2 or cerca[0][1] not in titulos or cerca[0][1] in rejillas:
            print("  ** DIFERENCIA: una rejilla sin un título de planta claramente suyo")
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


def _area(pts) -> float:
    return abs(sum(pts[i][0] * pts[i - 1][1] - pts[i - 1][0] * pts[i][1]
                   for i in range(len(pts)))) / 2  # fmt: skip


def _marcadores(msp) -> list[tuple[tuple, float, str]]:
    """Los marcadores cerrados de la capa castillos (cuadros y círculos), con su área y handle."""
    salida = []
    for e in msp:
        if e.dxf.layer != "castillos":
            continue
        if e.dxftype() == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in e.get_points()]
            if len(pts) >= 3 and (e.closed or math.dist(pts[0], pts[-1]) < 1e-6):
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                salida.append(((min(xs), min(ys), max(xs), max(ys)), _area(pts), e.dxf.handle))
        elif e.dxftype() == "CIRCLE":
            c, r = e.dxf.center, e.dxf.radius
            salida.append(((c.x - r, c.y - r, c.x + r, c.y + r), math.pi * r * r, e.dxf.handle))
    return salida


def _area_de_sombreado(e) -> float:
    """El área de un sombreado (su primer contorno, aplanado)."""
    pts = [(v.x, v.y) for v in ezpath.from_hatch_boundary_path(e.paths[0]).flattening(0.001)]
    return _area(pts)


# Tarea 15e (R273): R166, las tres secciones de castillo en que el motor no toma el marcador más
# cercano a la etiqueta (por la mitad de su texto) y el crudo sí. Por etiqueta: su planta, el
# marcador más cercano en crudo y el que toma el motor (handle, tipo). VERIFICA ambos marcadores y
# sus áreas en crudo; con ellos la sección por planta del motor = crudo − el suyo + el del motor.
R166 = {
    "6355": ("PLANTA BAJA", "6315", "62D1"),  # K-0: su círculo; el motor, el 15×30 de una K-2
    "6719": ("PLANTA ALTA", "667C", "66C8"),  # K-0: su cuadro; el motor, el sombreado
    "9636": ("PLANTA ALTA", "667A", "9635"),  # K-0: su cuadro; el motor, el sombreado
}
# Tarea 15e (R272): un castillo (o columna) de la cimentación sigue en PLANTA BAJA si, corrida la
# rejilla (de las líneas S-GRID de las dos), hay uno de PLANTA BAJA a esta distancia o menos.
CONTINUACION_M = 0.30
SIN_CONTINUACION = {"5DAA", "5DD1", "8849"}  # K-1 junto a ZC-1; los dos C-1 del pórtico de IPR
DESPLAZADOS = {"5DB1": 0.20}  # sigue en el marcador de PLANTA BAJA de su mismo muro, a 0.20 m


def _peralte_de_losa(msp) -> tuple[float | None, int]:
    """Tarea 15e (R271), VERIFICA: el peralte que acotan los detalles de losa de la hoja. Cada
    título «LOSA …» y las cotas verticales (DIMENSION) a 6 m o menos de su inserción: la que abarca
    a las demás y las que la llenan, con sus textos (15 + 5 = 20, en centímetros: «ACOTACIONES EN
    CENTIMETROS»). Los dos detalles de PRUEBA-1 (65B8 y 6617) acotan 20 cm."""
    malos = 0
    peraltes = []
    cotas = []
    for d in msp.query("DIMENSION"):
        a, b = d.dxf.defpoint2, d.dxf.defpoint3
        if abs(a.x - b.x) < 1e-6 and abs(a.y - b.y) > 1e-6:
            cotas.append((d.dxf.handle, d.dxf.text, a.x, min(a.y, b.y), max(a.y, b.y)))
    for e in msp.query("TEXT MTEXT"):
        if not re.match(r"^\s*LOSA\b", texto(e), re.I):
            continue
        p = (e.dxf.insert.x, e.dxf.insert.y)
        suyas = [c for c in cotas if math.dist(p, (c[2], (c[3] + c[4]) / 2)) <= 6.0]
        if not suyas:
            print(f"    {e.dxf.handle} «{texto(e)}»: sin cotas verticales")
            continue
        total = max(suyas, key=lambda c: c[4] - c[3])
        partes = [c for c in suyas if c is not total and total[3] - 1e-6 <= c[3]
                  and c[4] <= total[4] + 1e-6]  # fmt: skip
        suma = sum(float(c[1]) for c in partes)
        print(f"    {e.dxf.handle} «{' '.join(texto(e).split())}»: {total[0]} «{total[1]}» = "
              f"{' + '.join(f'{c[0]} «{c[1]}»' for c in partes)}")
        if len(partes) < 2:
            print("      (no es una cadena: no acota el peralte)")
            continue
        if abs(suma - float(total[1])) > 1e-6:
            print("  ** DIFERENCIA: la cadena no suma")
            malos += 1
            continue
        peraltes.append(float(total[1]) / 100)
    if sorted(peraltes) != [0.20, 0.20]:
        print(f"  ** DIFERENCIA: peraltes de losa {peraltes}")
        return None, malos + 1
    return 0.20, malos


def _corrimiento(abajo, arriba) -> tuple[float | None, int]:
    mejor: tuple[int, float] | None = None
    for a in abajo:
        for b in arriba:
            n = sum(1 for x in abajo if any(abs(x + b - a - y) <= 0.02 for y in arriba))
            if n >= 2 and (mejor is None or n > mejor[0]):
                mejor = (n, b - a)
    return (mejor[1], mejor[0]) if mejor else (None, 0)


def _continuacion(msp, rejillas, etiquetas) -> int:
    """Tarea 15e (R272), VERIFICA: cada castillo o columna de la cimentación (su marcador más
    cercano) contra los de PLANTA BAJA, corrida la rejilla: uno a uno, el par más cercano primero,
    a ``CONTINUACION_M`` o menos. Los que no siguen son exactamente ``SIN_CONTINUACION``; los que
    siguen, a 3 cm o menos, salvo ``DESPLAZADOS``."""
    malos = 0
    ejes = {"PLANTA DE CIMENTACIÓN": ([], []), "PLANTA BAJA": ([], [])}
    for e in msp.query("LINE"):
        if e.dxf.layer != "S-GRID":
            continue
        a, b = e.dxf.start, e.dxf.end
        for t, (vert, horiz) in ejes.items():
            if _dentro(_medio(e), rejillas[t]):
                (vert if abs(a.x - b.x) < abs(a.y - b.y) else horiz).append(
                    a.x if abs(a.x - b.x) < abs(a.y - b.y) else a.y
                )
    dx, nx = _corrimiento(*(ejes[t][0] for t in ejes))
    dy, ny = _corrimiento(*(ejes[t][1] for t in ejes))
    print(f"  Tarea 15e — la cimentación sigue en PLANTA BAJA: rejilla corrida ({dx:+.2f}, "
          f"{dy:+.2f}) ({nx} ejes verticales y {ny} horizontales coinciden a 2 cm)")  # fmt: skip
    if dx is None or dy is None:
        return 1
    # Los castillos son sus marcadores: los de las etiquetas de la cimentación (dos etiquetas con
    # el mismo marcador más cercano son ese castillo, una vez) contra todos los marcadores de la
    # capa castillos dentro de la rejilla de PLANTA BAJA.
    de_cim: dict[tuple, list[str]] = {}
    for h, (t, c, _x) in etiquetas.items():
        if t == "PLANTA DE CIMENTACIÓN":
            de_cim.setdefault(c, []).append(h)
    pb = [(((m[0][0] + m[0][2]) / 2, (m[0][1] + m[0][3]) / 2), m[2]) for m in _marcadores(msp)]
    pb = [(q, h) for q, h in pb if _dentro(q, rejillas["PLANTA BAJA"])]
    pares = sorted(
        (math.dist((c[0] + dx, c[1] + dy), q), c, h) for c in de_cim for q, h in pb
    )  # fmt: skip
    por_marcador: dict[tuple, tuple[str, float]] = {}
    usados: set[str] = set()
    for d, c, h in pares:
        if d > CONTINUACION_M:
            break
        if c not in por_marcador and h not in usados:
            por_marcador[c] = (h, d)
            usados.add(h)
    siguen = {h: por_marcador[c] for c, hs in de_cim.items() if c in por_marcador for h in hs}
    cim = [(h, c) for c, hs in de_cim.items() for h in hs]
    pares = [(d, h, j) for d, c, j in pares for h in de_cim[c]]
    sin = {h for h, _c in cim} - set(siguen)
    lejos = {h: round(d, 3) for h, (_k, d) in siguen.items() if d > 0.03}
    for h in sorted(sin):
        cerca = min(d for d, x, _k in pares if x == h)
        print(f"    {h} {etiquetas[h][2]} no sigue: el más cercano de PLANTA BAJA está a "
              f"{cerca:.3f}")  # fmt: skip
    print(f"    {len(siguen)} de {len(cim)} siguen ({len(siguen) - len(lejos)} a 3 cm o menos; "
          f"más lejos: { {h: (siguen[h][0], d) for h, d in lejos.items()} })")  # fmt: skip
    if (
        sin != SIN_CONTINUACION
        or set(lejos) != set(DESPLAZADOS)
        or any(abs(lejos[h] - d) > 0.005 for h, d in DESPLAZADOS.items())
    ):
        print(f"  ** DIFERENCIA: no siguen {sorted(sin)}, desplazados {lejos}")
        malos += 1
    return malos


def prueba_1(gold: dict) -> int:
    """Tarea 15c: PRUEBA-1, cada etiqueta de castillo en una sola planta (ver el docstring)."""
    malos = 0
    path = Path(gold["source"]) / "drawings" / "Plano Prueba 1.dxf"
    print(f"  sha {hashlib.sha256(path.read_bytes()).hexdigest()[:12]}…")
    doc = load_dxf(path).doc
    msp = doc.modelspace()
    encabezados = [
        (texto(e), _centro_de_texto(doc, e), (e.dxf.insert.x, e.dxf.insert.y))
        for e in msp.query("TEXT MTEXT")
        if (e.dxf.char_height if e.dxftype() == "MTEXT" else e.dxf.height) >= 0.3
        and ENCABEZADO.search(texto(e))
    ]
    titulos = {t: c for t, c, _i in encabezados if re.search(r"PLANTA|AZOTEA", t.upper())}
    print("  encabezados (centro de su texto): "
          f"{[(t, tuple(round(v, 2) for v in c)) for t, c, _i in encabezados]}")  # fmt: skip
    otros = sorted(t for t, _c, _i in encabezados if t not in titulos)
    if sorted(titulos) != sorted(VISTA_DEL_MOTOR) or len(encabezados) != len(titulos) + len(otros):
        print(f"  ** DIFERENCIA: los títulos de planta no son {sorted(VISTA_DEL_MOTOR)}")
        return malos + 1
    if otros != ["ARMADO DE CASTILLOS", "ARMADO DE CASTILLOS", "simbología", "simbología"]:
        print(f"  ** DIFERENCIA: los demás encabezados son {otros}")
        malos += 1
    rejillas, m = _rejillas(msp, titulos, encabezados)
    malos += m
    if sorted(rejillas) != sorted(titulos):
        print(f"  ** DIFERENCIA: plantas sin rejilla: {sorted(set(titulos) - set(rejillas))}")
        return malos + 1
    insercion = {t: i for t, _c, i in encabezados if t in titulos}
    niveles, m = _niveles_de_las_plantas(msp, insercion, rejillas)
    malos += m
    if len(niveles) != 4:
        return malos + 1
    # Lectura B: cada planta, del nivel de la de abajo al suyo; la azotea (sin losa en su planta)
    # hasta su nivel.
    orden = ["PLANTA DE CIMENTACIÓN", *SUPERESTRUCTURA]
    altura = {t: round(niveles[t] - niveles[orden[i]], 3) for i, t in enumerate(orden[1:])}
    print(f"    alturas (del nivel de abajo al suyo): {altura}")
    # R271: el muro de block llega bajo su losa: PB y PA, su entrepiso menos el peralte acotado;
    # la azotea no tiene losa encima. La dala de remate no se descuenta (E2).
    print("  Tarea 15e — el peralte de la losa:")
    peralte, m = _peralte_de_losa(msp)
    malos += m
    if peralte is None:
        return malos
    altura_muro = {t: round(h - (peralte if t != "AZOTEA" else 0.0), 3) for t, h in altura.items()}
    print(f"    altura de los muros: {altura_muro}")
    # Cada etiqueta de castillo, en una sola planta; su sección, la de su marcador más cercano.
    marcadores = _marcadores(msp)
    por_planta: Counter = Counter()
    seccion: Counter = Counter()
    etiquetas: dict[str, tuple[str, tuple[float, float], str]] = {}
    marcador_de: dict[str, tuple] = {}
    fuera = 0
    for e in msp.query("TEXT MTEXT"):
        es_columna = re.match(r"^C-?\d$", texto(e).upper()) is not None
        if e.dxf.layer != "castillos" or not (re.match(r"^K-?\d$", texto(e).upper()) or es_columna):
            continue
        p = (e.dxf.insert.x, e.dxf.insert.y)
        dentro = [t for t, caja in rejillas.items() if _dentro(p, caja)]
        if not dentro:
            fuera += 0 if es_columna else 1
            cerca = sorted((_a_caja(p, caja), t) for t, caja in rejillas.items())
            dentro = [cerca[0][1]] if cerca[1][0] > 2 * cerca[0][0] else []
        if len(dentro) != 1:
            print(f"  ** DIFERENCIA: {e.dxf.handle} {texto(e)} en {dentro or 'ninguna planta'}")
            malos += 1
            continue
        m = min(marcadores, key=lambda m, p=p: _a_caja(p, m[0]))
        caja = m[0]
        etiquetas[e.dxf.handle] = (
            dentro[0], ((caja[0] + caja[2]) / 2, (caja[1] + caja[3]) / 2), texto(e)
        )
        marcador_de[e.dxf.handle] = m
        if es_columna:
            continue
        por_planta[dentro[0]] += 1
        seccion[dentro[0]] += m[1]
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
    # Tarea 15e (R272): qué castillos de la cimentación siguen en PLANTA BAJA.
    malos += _continuacion(msp, rejillas, etiquetas)
    # EST-001: sección del marcador × la altura de su planta (de las leyendas), en la
    # superestructura (los de la cimentación que siguen en PLANTA BAJA son su arranque y no se
    # cuentan; los que no siguen tampoco: la cimentación no está en EST-001).
    volumen = {t: round(float(seccion[t]) * altura[t], 4) for t in SUPERESTRUCTURA}
    concepts = (gold.get("money") or {}).get("concepts", {})
    gold_001 = concepts.get("EST-001", {}).get("quantity")
    print(f"  EST-001 crudo {round(sum(volumen.values()), 4)} m³ {volumen} (secciones "
          f"{ {t: round(float(seccion[t]), 6) for t in SUPERESTRUCTURA} } m²)")  # fmt: skip
    # R273: las secciones del motor = las del crudo con las tres de R166 cambiadas (cada marcador,
    # VERIFICADO en crudo); por la altura de cada planta, contra el gold (a 0.001 m³).
    por_handle = {e.dxf.handle: e for e in msp}
    del_motor = {t: float(seccion[t]) for t in SUPERESTRUCTURA}
    for tag, (planta, suyo, motor) in R166.items():
        m = marcador_de.get(tag)
        motor_e = por_handle.get(motor)
        if m is None or m[2] != suyo or etiquetas[tag][0] != planta or motor_e is None:
            print(f"  ** DIFERENCIA R166: {tag} toma {m and m[2]}, se esperaba {suyo} en {planta}")
            malos += 1
            continue
        if motor_e.dxftype() == "HATCH":
            area_motor = _area_de_sombreado(motor_e)
        else:
            area_motor = _area([(p[0], p[1]) for p in motor_e.get_points()])
        print(f"    R166 {tag} ({planta}): crudo {suyo} {m[1]:.6f} m², motor {motor} "
              f"({motor_e.dxftype()}) {area_motor:.6f} m²")
        del_motor[planta] += area_motor - m[1]
    est_001 = sum(del_motor[t] * altura[t] for t in SUPERESTRUCTURA)
    print(f"    secciones del motor {({t: round(v, 6) for t, v in del_motor.items()})} m² × "
          f"{altura} = {round(est_001, 4)} m³; gold {gold_001}")
    if gold_001 is None or abs(est_001 - gold_001) > 0.001:
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
    # Lo que la Tarea 15e movió del gold, con los largos de entonces (los del motor antes de la
    # Tarea 15f, REPRODUCE: LARGOS_15E) a las alturas de las leyendas menos el peralte acotado de
    # la losa (VERIFICA) en vez de 2.70/0.90. Lo de hoy lo compara la Tarea 15f, abajo.
    vanos = VANOS_15E_M * ALTURA_DE_VANO_M
    antes = sum(m * (ALTURA_DE_PRETIL_M if p == "AZOTEA" else ALTURA_DE_MURO_M)
                for p, m in LARGOS_15E.items()) - vanos  # fmt: skip
    despues = sum(m * altura_muro[p] for p, m in LARGOS_15E.items()) - vanos
    print(f"    muros contados por planta (Tarea 15e) {LARGOS_15E} m; vanos {round(vanos, 3)} m²")
    movido = {
        "EST-004": (antes, despues),
        "ACA-001": (2 * antes, 2 * despues),
        "ACA-002": (2 * antes, 2 * despues),
    }
    for code, (de, a) in movido.items():
        print(f"  {code}: {ANTES_15E[code]} (reproducido {round(de, 3)}) → {round(a, 4)} "
              f"(Tarea 15e: {DESPUES_15E[code]})")  # fmt: skip
        if abs(a - DESPUES_15E[code]) > 0.001 or abs(de - ANTES_15E[code]) > 0.001:
            print(f"  ** DIFERENCIA {code}")
            malos += 1
    malos += _variantes_de_muros(msp, lineas, rejillas, concepts, altura_muro)
    malos += _muros_con_aplanado(msp, lineas, concepts, altura_muro)
    return malos


# Tarea 15d (R269): las variantes de EST-004 se reparten sobre los muros que el renglón cuenta.
# Tarea 15f (R275): cada muro está dibujado con dos contornos en la capa A-WALL —el del block y, a
# 15 mm afuera por cada lado, el del aplanado— y la clase de espesor ya no es una lectura del
# motor: es la del núcleo dibujado (o la del contorno menos los dos aplanados), contra la nota.
# Cada muro: su planta, su caja (la del motor: el elemento bajo prueba), lo que se dibujó («nucleo»:
# el block entre las líneas del aplanado; «contorno»: sólo el contorno de 18 cm) y su largo al eje
# (el del motor, que se VERIFICA abajo contra las caras del crudo a 2 mm).
MUROS_CONTADOS = {
    # muro: (planta, caja, dibujo, largo al eje)
    "W11": ("AZOTEA", (90.832, -70.984, 92.812, -70.804), "nucleo", 1.8),
    "W53": ("AZOTEA", (90.832, -70.984, 91.012, -69.004), "nucleo", 1.8),
    "W55": ("AZOTEA", (92.632, -70.984, 92.812, -69.004), "nucleo", 1.89),
    "W7": ("AZOTEA", (88.982, -77.534, 91.532, -77.354), "contorno", 2.385),
    "W8": ("AZOTEA", (91.382, -74.684, 97.982, -74.504), "contorno", 6.435),
    "W15": ("AZOTEA", (94.382, -66.184, 97.982, -66.004), "contorno", 3.42),
    "W17": ("AZOTEA", (94.562, -64.634, 97.072, -64.454), "contorno", 2.42),
    "W18": ("AZOTEA", (88.982, -63.724, 94.562, -63.544), "contorno", 5.4),
    "W52": ("AZOTEA", (88.982, -77.534, 89.162, -63.544), "contorno", 13.81),
    "W54": ("AZOTEA", (91.382, -77.534, 91.562, -74.504), "contorno", 2.85),
    "W56": ("AZOTEA", (94.382, -66.184, 94.562, -63.544), "contorno", 2.46),
    "W57": ("AZOTEA", (97.802, -74.684, 97.982, -66.004), "contorno", 8.5),
    "W21": ("PLANTA BAJA", (51.89, -52.798, 53.84, -52.618), "nucleo", 1.935),
    "W27": ("PLANTA BAJA", (48.227, -45.488, 63.866, -45.308), "nucleo", 14.997),
    "W39": ("PLANTA BAJA", (50.725, -62.298, 50.905, -45.473), "nucleo", 16.81),
    "W40": ("PLANTA BAJA", (51.725, -59.448, 51.905, -48.308), "nucleo", 10.99),
    "W41": ("PLANTA BAJA", (53.175, -59.283, 53.355, -55.133), "nucleo", 4.15),
    "W42": ("PLANTA BAJA", (55.375, -55.748, 55.555, -48.308), "nucleo", 7.425),
    "W43": ("PLANTA BAJA", (56.715, -62.298, 56.895, -60.018), "nucleo", 2.1),
    "W44": ("PLANTA BAJA", (58.245, -62.283, 58.41, -60.033), "nucleo", 2.1),
    "W45": ("PLANTA BAJA", (60.545, -61.398, 60.725, -45.308), "nucleo", 16.0),
    "W20": ("PLANTA ALTA", (78.163, -53.41, 80.563, -53.23), "nucleo", 2.227),
    "W22": ("PLANTA ALTA", (74.028, -52.26, 78.178, -52.08), "nucleo", 4.15),
    "W24": ("PLANTA ALTA", (77.513, -49.91, 79.443, -49.73), "nucleo", 1.758),
    "W25": ("PLANTA ALTA", (80.403, -49.31, 82.698, -49.13), "nucleo", 2.295),
    "W46": ("PLANTA ALTA", (73.863, -58.81, 74.043, -44.82), "nucleo", 13.81),
    "W47": ("PLANTA ALTA", (76.263, -58.81, 76.443, -52.245), "nucleo", 6.475),
    "W48": ("PLANTA ALTA", (77.513, -49.91, 77.693, -44.82), "nucleo", 4.918),
    "W49": ("PLANTA ALTA", (79.263, -48.115, 79.443, -44.82), "nucleo", 3.19),
    "W50": ("PLANTA ALTA", (80.383, -57.745, 80.563, -53.23), "nucleo", 4.433),
    "W51": ("PLANTA ALTA", (82.683, -58.82, 82.863, -44.82), "nucleo", 13.903),
    "W23": ("PLANTA ALTA", (80.173, -52.31, 82.683, -52.13), "contorno", 2.51),
    "W28": ("PLANTA ALTA", (75.193, -45.3, 77.513, -45.12), "contorno", 2.32),
    "W29": ("PLANTA ALTA", (79.443, -45.3, 81.763, -45.12), "contorno", 2.32),
}
# Los que formaban variante sin que el renglón los cuente (BLOCK-36, -30, -19): capa, caja.
MUROS_FUERA = {
    "W31": ("A-WALL", (-14.395, -61.779, -14.215, -50.639)),
    "W33": ("A-WALL", (-10.745, -58.079, -10.565, -50.639)),
    "W5": ("MUROS", (-5.937, -77.616, -2.181, -77.428)),
}
# Los vanos que el renglón leyó (ancho del motor): cada uno es un hueco de las dos caras del
# núcleo de su muro en el crudo (Tarea 15f: el de W47 mide 1.03 en el block, 1.00 en el aplanado,
# que da vuelta al vano).
VANOS_LEIDOS = {"W40": 0.77, "W42": 0.95, "W47": 1.03}
ALTURA_DE_VANO_M = 2.10
# Tarea 15f: una cara es una posición con una línea de 1.5 m o más (el largo mínimo con el que el
# detector junta caras); la línea del aplanado está a 20 mm o menos afuera de su cara y la traslapa
# en 90 % o más del tramo más corto. Dos líneas a 1 mm o menos son la misma cara.
CARA_MINIMA_M, APLANADO_MAXIMO_M, TRASLAPE_MINIMO, MISMA_CARA_M = 1.5, 0.020, 0.9, 0.001
# Lo que puede ser un vano (como el detector): más que 2 espesores y que 0.30, hasta 1.30 m.
VANO_MINIMO_M, VANO_MAXIMO_M = 0.30, 1.30
# La nota que dice el espesor de los muros de block, y la leyenda que lo repite.
ESPESOR_EN_NOTA = re.compile(r"\bEN\s+(\d+(?:\.\d+)?)\s*CMS?\.?\s+DE\s+ESPESOR", re.I)
LEYENDA_DE_MURO = re.compile(r"MURO\s+DE\s+CARGA\s+(\d+)\s*CMS?\b", re.I)


def _en_caja(v, caja, tol=0.003) -> bool:
    return all(caja[0] - tol <= p.x <= caja[2] + tol and caja[1] - tol <= p.y <= caja[3] + tol
               for p in (v.dxf.start, v.dxf.end))  # fmt: skip


def _planta_de(p, rejillas) -> str | None:
    """La planta cuya rejilla contiene el punto; fuera de toda, la claramente más cercana."""
    dentro = [t for t, caja in rejillas.items() if _dentro(p, caja)]
    if len(dentro) == 1:
        return dentro[0]
    cerca = sorted((_a_caja(p, caja), t) for t, caja in rejillas.items())
    return cerca[0][1] if not dentro and cerca[1][0] > 2 * cerca[0][0] else None


def _huecos_interiores(lineas, caja) -> dict[float, list[float]]:
    """Por cara (las líneas paralelas al largo de la caja, por su coordenada), los huecos entre sus
    tramos, sin contar los de las puntas."""
    vertical = (caja[3] - caja[1]) > (caja[2] - caja[0])
    caras: dict[float, list[tuple[float, float]]] = {}
    for v in lineas:
        a, b = v.dxf.start, v.dxf.end
        if vertical and abs(a.x - b.x) < 1e-4 and abs(a.y - b.y) > 1e-4:
            caras.setdefault(round(a.x, 3), []).append(tuple(sorted((a.y, b.y))))
        elif not vertical and abs(a.y - b.y) < 1e-4 and abs(a.x - b.x) > 1e-4:
            caras.setdefault(round(a.y, 3), []).append(tuple(sorted((a.x, b.x))))
    huecos: dict[float, list[float]] = {}
    for cara, tramos in caras.items():
        tramos.sort()
        fin = tramos[0][1]
        for ini, f in tramos[1:]:
            if ini > fin + 1e-6:
                huecos.setdefault(cara, []).append(round(ini - fin, 3))
            fin = max(fin, f)
    return huecos


def _variantes_de_muros(msp, lineas, rejillas, concepts, altura) -> int:
    """Tarea 15d (R269): qué muros cuenta EST-004 y cuáles salieron de su reparto; en qué muros
    están los vanos leídos. Lo que VERIFICA: cada muro contado tiene líneas A-WALL en su caja y
    todas son de su planta de superestructura; los que formaban BLOCK-36/30/19 no tienen ninguna
    línea en la superestructura; cada vano leído es un hueco interior de ese ancho en una cara de
    su muro. Las clases de espesor, los largos y las variantes los VERIFICA la Tarea 15f
    (``_muros_con_aplanado``)."""
    malos = 0
    print("  Tarea 15d — EST-004, muros contados y vanos:")
    for muro, (planta, caja, _dibujo, _largo) in MUROS_CONTADOS.items():
        suyas = [v for v in lineas if _en_caja(v, caja)]
        plantas = {_planta_de(_medio(v), rejillas) for v in suyas}
        if len(suyas) < 2 or plantas != {planta}:
            print(f"  ** DIFERENCIA: {muro} con {len(suyas)} líneas A-WALL en {plantas}, "
                  f"se esperaba {planta}")
            malos += 1
    print(f"    {len(MUROS_CONTADOS)} muros contados: cada uno con sus líneas A-WALL en su planta")
    for muro, (capa, caja) in MUROS_FUERA.items():
        candidatas = lineas if capa == "A-WALL" else msp.query(f"LINE[layer=='{capa}']")
        suyas = [v for v in candidatas if _en_caja(v, caja)]
        plantas = {_planta_de(_medio(v), rejillas) for v in suyas}
        print(f"    {muro}: {len(suyas)} líneas {capa}, de {plantas}")
        if not suyas or plantas & set(SUPERESTRUCTURA):
            print(f"  ** DIFERENCIA: {muro} tiene líneas en la superestructura")
            malos += 1
    for muro, ancho in VANOS_LEIDOS.items():
        caja = MUROS_CONTADOS[muro][1]
        huecos = _huecos_interiores([v for v in lineas if _en_caja(v, caja)], caja)
        todos = sorted({h for hs in huecos.values() for h in hs})
        print(f"    {muro}: vano leído {ancho} m; huecos interiores {todos}")
        if not any(abs(h - ancho) <= 0.002 for h in todos):
            print(f"  ** DIFERENCIA: {muro} no tiene un hueco de {ancho} m")
            malos += 1
    return malos


def _caras_del_muro(lineas, caja) -> list[tuple[float, list[tuple[float, float]], bool]]:
    """Las caras dibujadas en la caja del muro (sin las copias exactas: el model space y el
    bloque de Revit traen la misma línea): por posición a lo ancho, sus tramos a lo largo
    recortados a la caja, y si alguna de sus líneas mide 1.5 m o más."""
    vertical = (caja[3] - caja[1]) > (caja[2] - caja[0])
    a0, a1 = (caja[0], caja[2]) if vertical else (caja[1], caja[3])
    l0, l1 = (caja[1], caja[3]) if vertical else (caja[0], caja[2])
    unicas = set()
    for v in lineas:
        s, e = v.dxf.start, v.dxf.end
        unicas.add(tuple(sorted([(round(s.x, 4), round(s.y, 4)), (round(e.x, 4), round(e.y, 4))])))
    tramos: list[tuple[float, float, float, float]] = []  # (posición, inicio, fin, largo)
    for (x1, y1), (x2, y2) in unicas:
        if vertical and abs(x1 - x2) < 1e-4 and abs(y1 - y2) > 1e-4:
            pos, ini, fin = x1, min(y1, y2), max(y1, y2)
        elif not vertical and abs(y1 - y2) < 1e-4 and abs(x1 - x2) > 1e-4:
            pos, ini, fin = y1, min(x1, x2), max(x1, x2)
        else:
            continue
        if a0 - 0.0005 <= pos <= a1 + 0.0005 and fin > l0 + 1e-4 and ini < l1 - 1e-4:
            tramos.append((pos, max(ini, l0), min(fin, l1), fin - ini))
    tramos.sort()
    grupos: list[list[tuple[float, float, float, float]]] = []
    for t in tramos:
        if grupos and t[0] - grupos[-1][-1][0] <= MISMA_CARA_M:
            grupos[-1].append(t)
        else:
            grupos.append([t])
    caras = []
    for g in grupos:
        juntos: list[tuple[float, float]] = []
        for _p, ini, fin, _l in sorted(g, key=lambda t: t[1]):
            if juntos and ini <= juntos[-1][1]:
                juntos[-1] = (juntos[-1][0], max(juntos[-1][1], fin))
            else:
                juntos.append((ini, fin))
        larga = any(t[3] >= CARA_MINIMA_M - 1e-9 for t in g)
        caras.append((sum(t[0] for t in g) / len(g), juntos, larga))
    return caras


def _cubre(tramos) -> float:
    return sum(f - i for i, f in tramos)


def _es_aplanado(exterior, interior) -> bool:
    if abs(interior[0] - exterior[0]) > APLANADO_MAXIMO_M + 1e-6:
        return False
    cruce = sum(max(0.0, min(fa, fb) - max(ia, ib))
                for ia, fa in exterior[1] for ib, fb in interior[1])  # fmt: skip
    return cruce >= TRASLAPE_MINIMO * min(_cubre(exterior[1]), _cubre(interior[1])) - 1e-9


def _huecos_de(tramos) -> list[tuple[float, float]]:
    return [(a[1], b[0]) for a, b in zip(tramos, tramos[1:], strict=False)]


def _muros_con_aplanado(msp, lineas, concepts, altura) -> int:
    """Tarea 15f (R275), VERIFICA en el crudo: (1) la nota de los muros de block dice un solo
    espesor, 15 cm («… EN 15 CM. DE ESPESOR», dos copias) y la leyenda lo repite («MURO DE CARGA
    15 CMS», dos copias); (2) por cada muro contado, sus caras A-WALL (sin copias exactas): el
    núcleo de 0.150 m (a 1 mm) entre las líneas del aplanado (cada una a 0.015, a 1 mm, afuera de
    su cara, traslapándola en 90 % o más) en los 22 de «nucleo», sólo el contorno de 0.180 en los
    12 de «contorno» (0.180 = 0.150 + 2 × 0.015: el block de la nota con su aplanado); (3) el
    largo al eje de cada uno (la media de lo que corren sus dos caras de block, o de su contorno,
    dentro de su caja) contra el del motor, a 2 mm —cada junta en T una sola vez: el núcleo del
    muro que llega para en el núcleo del que lo recibe—; (4) los vanos: los huecos que tienen las
    dos caras (de 0.30 a 1.30 m) son exactamente los de VANOS_LEIDOS, a 2 mm, y ningún otro muro
    tiene uno. Con eso la clase de cada muro sale del crudo (15 en todos, la de la nota) y
    REPRODUCE: EST-004 = Σ largo × la altura de muro de su planta (Tarea 15e) − los vanos × 2.10
    (la altura de vano es supuesta: el renglón sigue siendo del motor), su variante BLOCK-15 y
    ACA-001/ACA-002 (dos caras), contra el gold a 0.001."""
    malos = 0
    print("  Tarea 15f — muros con su aplanado (R275):")
    textos = [(e.dxf.handle, texto(e)) for e in msp.query("TEXT MTEXT")]
    en_nota = [(h, t, ESPESOR_EN_NOTA.search(t)) for h, t in textos if ESPESOR_EN_NOTA.search(t)]
    leyenda = [(h, t, LEYENDA_DE_MURO.search(t)) for h, t in textos if LEYENDA_DE_MURO.search(t)]
    bloque = [h for h, t in textos if re.search(r"MURO DE BLOQUE DE CONCRETO DE 15 x 20 x 40", t)]
    print(f"    nota: {[(h, t.strip()) for h, t, _m in en_nota]}; pieza {bloque}; leyenda: "
          f"{[(h, t.strip()) for h, t, _m in leyenda]}")  # fmt: skip
    nota_cm = {float(m.group(1)) for _h, _t, m in en_nota}
    if nota_cm != {15.0} or len(en_nota) != 2 or len(bloque) != 2 or len(leyenda) != 2 or {
        m.group(1) for _h, _t, m in leyenda
    } != {"15"}:
        print(f"  ** DIFERENCIA: la nota dice {nota_cm} cm en {len(en_nota)} copias")
        return malos + 1
    nota_m = 0.15
    clases: Counter = Counter()
    cara_por_planta: Counter = Counter()
    vanos_m = 0.0
    aplanados = set()
    for muro, (planta, caja, dibujo, largo) in MUROS_CONTADOS.items():
        caras = [c for c in _caras_del_muro(lineas, caja) if c[2]]
        nucleo = list(caras)
        aplanado = []
        if len(nucleo) >= 3 and _es_aplanado(nucleo[0], nucleo[1]):
            aplanado.append(round(nucleo[1][0] - nucleo[0][0], 4))
            nucleo = nucleo[1:]
        if len(nucleo) >= 3 and _es_aplanado(nucleo[-1], nucleo[-2]):
            aplanado.append(round(nucleo[-1][0] - nucleo[-2][0], 4))
            nucleo = nucleo[:-1]
        visto = "nucleo" if aplanado else "contorno"
        if len(nucleo) != 2:
            posiciones = [round(c[0], 4) for c in caras]
            print(f"  ** DIFERENCIA: {muro} tiene {len(nucleo)} caras: {posiciones}")
            malos += 1
            continue
        a, b = nucleo
        espesor = round(b[0] - a[0], 4)
        eje = ((a[1][-1][1] - a[1][0][0]) + (b[1][-1][1] - b[1][0][0])) / 2
        vanos = []
        for ia, fa in _huecos_de(a[1]):
            for ib, fb in _huecos_de(b[1]):
                ancho = min(fa, fb) - max(ia, ib)
                if max(VANO_MINIMO_M, 2 * espesor) < ancho <= VANO_MAXIMO_M:
                    vanos.append(round(ancho, 3))
        esperado = 0.150 if visto == "nucleo" else 0.180
        aplanados.update(aplanado)
        bien = (
            visto == dibujo
            and abs(espesor - esperado) <= 0.001
            and all(abs(x - 0.015) <= 0.001 for x in aplanado)
            and abs(eje - largo) <= 0.002
            and (vanos == [VANOS_LEIDOS[muro]] if muro in VANOS_LEIDOS else vanos == [])
        )
        if not bien:
            print(f"  ** DIFERENCIA: {muro} {visto} {espesor} (aplanado {aplanado}), eje "
                  f"{round(eje, 3)} (motor {largo}), vanos {vanos}")
            malos += 1
        # La clase: el núcleo dibujado, o el contorno menos sus dos aplanados de 15 mm.
        cm = round((espesor if visto == "nucleo" else espesor - 2 * 0.015) * 100)
        clases[cm] += 1
        cara_por_planta[planta] += largo * altura[planta]
        vanos_m += sum(vanos)
    por_planta = {
        p: round(sum(m[3] for m in MUROS_CONTADOS.values() if m[0] == p), 3)
        for p in SUPERESTRUCTURA
    }
    print(f"    clases del crudo {dict(clases)} (la nota: {nota_m * 100:g}); aplanado "
          f"{sorted(aplanados)}; largos al eje por planta {por_planta}")  # fmt: skip
    if set(clases) != {round(nota_m * 100)} or aplanados != {0.015}:
        print("  ** DIFERENCIA: las clases del crudo no son la de la nota")
        malos += 1
    est_004 = sum(cara_por_planta.values()) - vanos_m * ALTURA_DE_VANO_M
    gold = concepts.get("EST-004", {})
    calculado = {
        "EST-004": est_004,
        "ACA-001": 2 * est_004,
        "ACA-002": 2 * est_004,
    }
    print(f"    EST-004 = Σ largo × altura {altura} − {round(vanos_m, 3)} m × 2.10 = "
          f"{round(est_004, 4)}; variantes del gold {gold.get('variants')}")
    for code, valor in calculado.items():
        q = concepts.get(code, {}).get("quantity")
        print(f"  {code}: reproducido {round(valor, 4)}; gold {q}")
        if q is None or abs(valor - q) > 0.001:
            print(f"  ** DIFERENCIA {code}")
            malos += 1
    variantes = gold.get("variants") or {}
    if set(variantes) != {"EST-004.BLOCK-15"} or abs(
        variantes["EST-004.BLOCK-15"] - est_004
    ) > 0.001:
        print("  ** DIFERENCIA en las variantes de EST-004")
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
