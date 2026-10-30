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
castillos y muros (A-WALL) sin ninguna línea de losa ni trabe (su pretil). Con eso, las alturas son
del nivel de la planta de abajo al suyo: PLANTA BAJA 3.45, PLANTA ALTA 3.15, AZOTEA 1.20 (los
castillos de la cimentación son el arranque de los de PLANTA BAJA y no se cuentan en EST-001).
EST-001: la sección de cada castillo es el marcador cerrado más cercano a su etiqueta en la capa
castillos (el cuadro de 15×15, el de 15×30 o el círculo), por la altura de su planta, en PLANTA
BAJA, PLANTA ALTA y AZOTEA, contra el gold con 0.6 %: los conteos y las alturas son crudos, las
secciones del motor no lo son del todo (el motor da a dos K-0 sobre el 15×30 de una K-2 ese
marcador —R166— y a dos K-0 sin marcador junto el círculo de su símbolo: PLANTA BAJA 1.7301 m²
contra 1.7005 crudo, PLANTA ALTA 1.2302 contra 1.2446, AZOTEA 0.4950 igual; a 3.45/3.15/1.20,
10.438 contra 10.381, 0.55 %), así que EST-001 no es crudo.

Qué REPRODUCE (reglas del motor, no hechos del plano): el nombre de la vista de cada planta en el
motor (``VISTA_DEL_MOTOR``: por el orden de sus títulos); criticos_total = 4 por castillo; los
largos de los muros que EST-004 cuenta (``MUROS_CONTADOS``, del motor: tarea 15f) y los vanos
leídos; con ellos y las alturas de las leyendas, lo que la Tarea 15e movió del gold: EST-004
428.630 → 532.325 (antes 2.70 y pretil 0.90 supuestos, reproducido), ACA-001 y ACA-002 857.260 →
1064.650 (dos caras).

prueba-1, Tarea 15d (R269): las variantes de EST-004 son sólo de los muros que el renglón cuenta.
VERIFICA (y compara) los 34 muros contados en su planta de superestructura, que W5, W31 y W33 (las
variantes BLOCK-19/30/36 que se fueron) no tienen líneas en la superestructura, que cada vano leído
(W40 0.77, W42 0.95, W47 1.00) es un hueco de ese ancho en una cara de su muro y que ningún muro de
las clases 17 y 18 tiene un hueco de 0.5 m o más. REPRODUCE los largos y las clases de espesor (del
motor: los 16/17/18 salen de la planta dibujada dos veces a 15 mm, tarea 15f) y con ellos y las
alturas de las leyendas (Tarea 15e) las variantes del gold.
"""

import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

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
    # Lectura B: cada planta, del nivel de la de abajo al suyo; la azotea, su pretil.
    orden = ["PLANTA DE CIMENTACIÓN", *SUPERESTRUCTURA]
    altura = {t: round(niveles[t] - niveles[orden[i]], 3) for i, t in enumerate(orden[1:])}
    print(f"    alturas (del nivel de abajo al suyo): {altura}")
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
    # EST-001: sección del marcador × la altura de su planta (de las leyendas), en la
    # superestructura (los de la cimentación son el arranque de los de PLANTA BAJA).
    volumen = {t: round(float(seccion[t]) * altura[t], 4) for t in SUPERESTRUCTURA}
    est_001 = sum(volumen.values())
    concepts = (gold.get("money") or {}).get("concepts", {})
    gold_001 = concepts.get("EST-001", {}).get("quantity")
    print(f"  EST-001 crudo {round(est_001, 4)} m³ {volumen} (secciones "
          f"{ {t: round(float(seccion[t]), 4) for t in SUPERESTRUCTURA} } m²); gold {gold_001} "
          "(0.6 %)")  # fmt: skip
    if gold_001 is None or abs(est_001 - gold_001) > 0.006 * gold_001:
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
    # Lo que la Tarea 15e movió del gold: los muros que el renglón cuenta (largos del motor,
    # REPRODUCE: MUROS_CONTADOS) a las alturas de las leyendas (VERIFICA) en vez de 2.70/0.90.
    largo = Counter()
    for _clase, planta, _caja, metros in MUROS_CONTADOS.values():
        largo[planta] += metros
    vanos = sum(VANOS_LEIDOS.values()) * ALTURA_DE_VANO_M
    antes = sum(m * (ALTURA_DE_PRETIL_M if p == "AZOTEA" else ALTURA_DE_MURO_M)
                for p, m in largo.items()) - vanos  # fmt: skip
    despues = sum(m * altura[p] for p, m in largo.items()) - vanos
    print(f"    muros contados por planta {dict(largo)} m; vanos {round(vanos, 3)} m²")
    movido = {
        "EST-004": (antes, despues),
        "ACA-001": (2 * antes, 2 * despues),
        "ACA-002": (2 * antes, 2 * despues),
    }
    for code, (de, a) in movido.items():
        q = concepts.get(code, {}).get("quantity")
        print(f"  {code}: {ANTES_15E[code]} (reproducido {round(de, 3)}) → {round(a, 4)}; gold {q}")
        if q is None or abs(a - q) > 0.001 or abs(de - ANTES_15E[code]) > 0.001:
            print(f"  ** DIFERENCIA {code}")
            malos += 1
    malos += _variantes_de_muros(msp, lineas, rejillas, concepts, altura)
    return malos


# Tarea 15d (R269): las variantes de EST-004 se reparten sobre los muros que el renglón cuenta.
# Cada muro: su caja (la del motor: el elemento bajo prueba), su clase de espesor (lectura del
# motor, REPRODUCE: el plano dibuja la planta dos veces desfasada 15 mm y cada copia mide 0.165 m —
# los 16/17/18 salen de juntar caras de copias distintas, tarea 15f), su planta esperada y su largo
# (lectura del motor, REPRODUCE).
MUROS_CONTADOS = {
    # muro: (clase, planta, caja, largo)
    "W11": (16, "AZOTEA", (90.832, -70.984, 92.812, -70.804), 1.98),
    "W53": (16, "AZOTEA", (90.832, -70.984, 91.012, -69.004), 1.98),
    "W55": (16, "AZOTEA", (92.632, -70.984, 92.812, -69.004), 1.98),
    "W21": (16, "PLANTA BAJA", (51.89, -52.798, 53.84, -52.618), 1.95),
    "W39": (16, "PLANTA BAJA", (50.725, -62.298, 50.905, -45.473), 16.825),
    "W40": (16, "PLANTA BAJA", (51.725, -59.448, 51.905, -48.308), 11.14),
    "W41": (16, "PLANTA BAJA", (53.175, -59.283, 53.355, -55.133), 4.15),
    "W42": (16, "PLANTA BAJA", (55.375, -55.748, 55.555, -48.308), 7.44),
    "W43": (16, "PLANTA BAJA", (56.715, -62.298, 56.895, -60.018), 2.28),
    "W44": (16, "PLANTA BAJA", (58.245, -62.283, 58.41, -60.033), 2.25),
    "W45": (16, "PLANTA BAJA", (60.545, -61.398, 60.725, -45.308), 16.09),
    "W20": (16, "PLANTA ALTA", (78.163, -53.41, 80.563, -53.23), 2.4),
    "W22": (16, "PLANTA ALTA", (74.028, -52.26, 78.178, -52.08), 4.15),
    "W24": (16, "PLANTA ALTA", (77.513, -49.91, 79.443, -49.73), 1.93),
    "W25": (16, "PLANTA ALTA", (80.403, -49.31, 82.698, -49.13), 2.295),
    "W47": (16, "PLANTA ALTA", (76.263, -58.81, 76.443, -52.245), 6.565),
    "W48": (16, "PLANTA ALTA", (77.513, -49.91, 77.693, -44.82), 5.09),
    "W49": (16, "PLANTA ALTA", (79.263, -48.115, 79.443, -44.82), 3.295),
    "W50": (16, "PLANTA ALTA", (80.383, -57.745, 80.563, -53.23), 4.515),
    "W51": (16, "PLANTA ALTA", (82.683, -58.82, 82.863, -44.82), 14.0),
    "W27": (17, "PLANTA BAJA", (48.227, -45.488, 63.866, -45.308), 15.639),
    "W46": (17, "PLANTA ALTA", (73.863, -58.81, 74.043, -44.82), 13.99),
    "W23": (18, "PLANTA ALTA", (80.173, -52.31, 82.683, -52.13), 2.51),
    "W28": (18, "PLANTA ALTA", (75.193, -45.3, 77.513, -45.12), 2.32),
    "W29": (18, "PLANTA ALTA", (79.443, -45.3, 81.763, -45.12), 2.32),
    "W7": (18, "AZOTEA", (88.982, -77.534, 91.532, -77.354), 2.22),
    "W8": (18, "AZOTEA", (91.382, -74.684, 97.982, -74.504), 6.6),
    "W15": (18, "AZOTEA", (94.382, -66.184, 97.982, -66.004), 3.24),
    "W17": (18, "AZOTEA", (94.562, -64.634, 97.072, -64.454), 2.33),
    "W18": (18, "AZOTEA", (88.982, -63.724, 94.562, -63.544), 5.22),
    "W52": (18, "AZOTEA", (88.982, -77.534, 89.162, -63.544), 13.99),
    "W54": (18, "AZOTEA", (91.382, -77.534, 91.562, -74.504), 2.67),
    "W56": (18, "AZOTEA", (94.382, -66.184, 94.562, -63.544), 2.28),
    "W57": (18, "AZOTEA", (97.802, -74.684, 97.982, -66.004), 8.68),
}
# Los que formaban variante sin que el renglón los cuente (BLOCK-36, -30, -19): capa, caja.
MUROS_FUERA = {
    "W31": ("A-WALL", (-14.395, -61.779, -14.215, -50.639)),
    "W33": ("A-WALL", (-10.745, -58.079, -10.565, -50.639)),
    "W5": ("MUROS", (-5.937, -77.616, -2.181, -77.428)),
}
# Los vanos que el renglón leyó (ancho del motor): cada uno es un hueco interior de una cara del
# muro en el crudo; ningún muro de las clases 17 y 18 tiene un hueco interior de 0.5 m o más.
VANOS_LEIDOS = {"W40": 0.77, "W42": 0.95, "W47": 1.00}
ALTURA_DE_VANO_M = 2.10


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
    su muro, y ningún muro de las clases 17 y 18 tiene un hueco interior de 0.5 m o más. Lo que NO
    verifica (REPRODUCE): las clases de espesor y los largos, lecturas del motor. Las alturas son
    las de las leyendas de nivel (Tarea 15e, ``altura``: VERIFICA). Con ellas, compara las
    variantes del gold."""
    malos = 0
    print("  Tarea 15d — EST-004, muros contados y vanos:")
    for muro, (clase, planta, caja, _largo) in MUROS_CONTADOS.items():
        suyas = [v for v in lineas if _en_caja(v, caja)]
        plantas = {_planta_de(_medio(v), rejillas) for v in suyas}
        if len(suyas) < 2 or plantas != {planta}:
            print(f"  ** DIFERENCIA: {muro} ({clase}) con {len(suyas)} líneas A-WALL en {plantas}, "
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
    for muro, (clase, _planta, caja, _largo) in MUROS_CONTADOS.items():
        huecos = _huecos_interiores([v for v in lineas if _en_caja(v, caja)], caja)
        todos = sorted({h for hs in huecos.values() for h in hs})
        if muro in VANOS_LEIDOS:
            ok = any(abs(h - VANOS_LEIDOS[muro]) <= 0.002 for h in todos)
            print(f"    {muro}: vano leído {VANOS_LEIDOS[muro]} m; huecos interiores {todos}")
            if not ok:
                print(f"  ** DIFERENCIA: {muro} no tiene un hueco de {VANOS_LEIDOS[muro]} m")
                malos += 1
        elif clase in (17, 18) and any(h >= 0.5 for h in todos):
            print(f"  ** DIFERENCIA: {muro} (clase {clase}) tiene un hueco de {max(todos)} m")
            malos += 1
    # REPRODUCE: las variantes, de los largos del motor × las alturas de las leyendas − los vanos.
    vanos = {16: sum(VANOS_LEIDOS.values()) * ALTURA_DE_VANO_M}
    gold = concepts.get("EST-004", {}).get("variants") or {}
    calculado = {}
    for clase in (16, 17, 18):
        cara = sum(
            largo * altura[planta]
            for c, planta, _caja, largo in MUROS_CONTADOS.values()
            if c == clase
        )
        calculado[f"EST-004.BLOCK-{clase}"] = round(cara - vanos.get(clase, 0.0), 3)
    print(f"    variantes (largos del motor × alturas {altura} − vanos × 2.10): {calculado}; "
          f"gold {gold}")
    if set(gold) != set(calculado) or any(abs(gold[k] - v) > 0.001 for k, v in calculado.items()):
        print("  ** DIFERENCIA en las variantes de EST-004")
        malos += 1
    total = concepts.get("EST-004", {}).get("quantity")
    if total is None or abs(sum(calculado.values()) - total) > 0.002:
        print(f"  ** DIFERENCIA: las variantes suman {sum(calculado.values())}, el renglón {total}")
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
