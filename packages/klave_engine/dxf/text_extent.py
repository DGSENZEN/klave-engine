"""Dónde está cada texto del plano: el punto donde lo puso el dibujante y lo que ocupa (R146).

El normalizador da a cada TEXT y MTEXT su extensión real con este modelo, y los lectores
(asociación de pilas, dueños de secciones, detectores) usan el mismo: el punto de alineación de un
TEXT alineado, el ancho que el CAD calculó para los centrados y los alineados a la derecha, el
factor de ancho, la inclinación y el espejo del texto; en un MTEXT su punto de inserción, su
columna, la alineación de sus párrafos y cuántos renglones ocupa; y en los dos, su giro.

El ancho de un texto cuyo ancho el CAD no guardó se estima por carácter: no se usa la medida de
ezdxf, que depende de las fuentes instaladas en la máquina (sin las SHX del dibujo cae a otra fuente
y mide ROMANS un 11–18 % más angosto que el CAD) y haría que dos máquinas leyeran distinto."""

import math
import re

from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import BBox, Point

# En «alineado» (3) y «ajustado» (5) el código 11 es donde TERMINA la línea base:
# el texto arranca en el ``insert``, así que ése es su ancla.
_HALIGN_CON_FINAL_EN_EL_PUNTO = (3, 5)
# El ancho de un carácter, × el alto, para los textos cuyo ancho no viene en el dibujo (ROMANS en
# Marina mide 0.83–1.03, mediana 0.92; los centrados traen su ancho real).
ANCHO_POR_CARACTER = 0.9
# El paso entre renglones de un MTEXT, × el alto (el interlineado normal de AutoCAD).
PASO_DE_MTEXT = 5.0 / 3.0
# Los códigos de control de un TEXT: «%%C» (Ø), «%%D» (°), «%%P» (±) y «%%nnn» se dibujan como un
# carácter; «%%U» y «%%O» (subrayado, sobrerrayado) no ocupan nada.
_UN_CARACTER = re.compile(r"%%(?:[CDPcdp]|\d{3})")
_SIN_ANCHO = re.compile(r"%%[UOuo]")


def ancla_texto(e: NormalizedEntity) -> tuple[float, float]:
    """El punto donde el dibujante puso el texto, no la esquina de su caja.

    Un TEXT con alineación distinta de «izquierda-base» se coloca por su punto
    de alineación (código 11): el ``insert`` de esos textos queda en otro lado.
    Excepto «alineado» y «ajustado», donde el código 11 es el final de la línea
    base y el ancla sigue siendo el ``insert``. Si no hay alineación, el ancla
    es el ``insert``; sin él, la esquina inferior izquierda de la caja."""
    propiedades = e.properties
    halign = propiedades.get("halign", 0)
    if (
        e.entity_type == EntityType.text
        and halign not in _HALIGN_CON_FINAL_EN_EL_PUNTO
        and (halign != 0 or propiedades.get("valign", 0) != 0)
    ):
        punto = propiedades.get("align_point")
        if punto is not None:
            return (float(punto[0]), float(punto[1]))
    insercion = propiedades.get("insert")
    if insercion is not None:
        return (float(insercion[0]), float(insercion[1]))
    return (e.bbox[0], e.bbox[1])


def alto_de_texto(e: NormalizedEntity) -> float:
    """El alto de un renglón del texto (el de su caja si no lo trae)."""
    alto = e.properties.get("height")
    if not isinstance(alto, int | float) or alto <= 0:
        alto = e.bbox[3] - e.bbox[1]
    return float(alto) if alto > 0 else 1e-6


def caracteres(texto: str) -> int:
    """Cuántos caracteres dibuja un renglón: los códigos de control cuentan lo que dibujan."""
    return len(_SIN_ANCHO.sub("", _UN_CARACTER.sub("X", texto.strip())))


def _ancho_dibujado(e: NormalizedEntity, angulo: float) -> float | None:
    """El ancho de un TEXT alineado tal como lo calculó el CAD: la distancia, a lo largo del
    renglón, de su ``insert`` (inicio de la línea base) a su punto de alineación."""
    p = e.properties
    halign = p.get("halign") or 0
    insercion, punto = p.get("insert"), p.get("align_point")
    if e.entity_type != EntityType.text or not halign or insercion is None or punto is None:
        return None
    avance = (float(punto[0]) - float(insercion[0])) * math.cos(angulo) + (
        float(punto[1]) - float(insercion[1])
    ) * math.sin(angulo)
    if p.get("mirror_x"):
        avance = -avance  # al revés: el renglón corre hacia atrás desde su inicio
    if avance <= 1e-9:
        return None  # sin el insert calculado (p. ej. un DXF de ezdxf): no se sabe
    return 2.0 * avance if halign in (1, 4) else avance


def _caja_de_mtext(
    e: NormalizedEntity, texto: str, alto: float
) -> tuple[float, float, float, float, float]:
    """La caja de un MTEXT: su punto de inserción es una esquina, un lado o el centro de la
    caja (``attachment_point``); con columna (``column_width``), los párrafos van a la
    izquierda, al centro o a la derecha de ella (``paragraph_align``; si no la dice, según el
    punto de inserción) y los renglones largos se parten."""
    p = e.properties
    punto = int(p.get("attachment_point") or 1)
    punto = punto if 1 <= punto <= 9 else 1
    columna, fila = (punto - 1) % 3, (punto - 1) // 3
    renglones = [r.strip() for r in texto.split("\n")] or [""]
    por_caracter = ANCHO_POR_CARACTER * alto
    ancho = por_caracter * max(len(r) for r in renglones)
    cuantos = len(renglones)
    ancho_de_columna = float(p.get("column_width") or 0.0)
    if ancho_de_columna > 0:
        # Los párrafos se parten entre palabras, como en el CAD: una palabra más larga que la
        # columna no se corta, se sale de ella.
        partidos = [
            r for renglon in renglones for r in _partir(renglon, por_caracter, ancho_de_columna)
        ]
        cuantos = len(partidos)
        ancho = por_caracter * max(len(r) for r in partidos)
        inicio = (0.0, -ancho_de_columna / 2, -ancho_de_columna)[columna]
        alineacion = p.get("paragraph_align") or "lcr"[columna]
        if alineacion == "c":
            dx0 = inicio + (ancho_de_columna - ancho) / 2
        elif alineacion == "r":
            dx0 = inicio + ancho_de_columna - ancho
        elif alineacion in ("j", "d"):
            dx0, ancho = inicio, ancho_de_columna  # justificado: ocupa la columna
        else:
            dx0 = inicio
    else:
        dx0 = (0.0, -ancho / 2, -ancho)[columna]
    interlineado = float(p.get("line_spacing") or 1.0)
    total = alto + (cuantos - 1) * PASO_DE_MTEXT * interlineado * alto
    dy0 = (-total, -total / 2, 0.0)[fila]
    return dx0, dx0 + ancho, dy0, dy0 + total, alto


def _partir(renglon: str, por_caracter: float, ancho_de_columna: float) -> list[str]:
    """Un párrafo partido en los renglones que caben en la columna, palabra por palabra."""
    salida: list[str] = []
    actual = ""
    for palabra in renglon.split():
        tentativo = f"{actual} {palabra}" if actual else palabra
        if actual and por_caracter * len(tentativo) > ancho_de_columna:
            salida.append(actual)
            actual = palabra
        else:
            actual = tentativo
    salida.append(actual)
    return salida


def caja_de_texto(e: NormalizedEntity, angulo: float) -> tuple[float, float, float, float, float]:
    """La caja del texto respecto a su ancla, en la dirección del renglón (``angulo`` en
    radianes): ``(dx0, dx1, dy0, dy1, alto de un renglón)``."""
    alto = alto_de_texto(e)
    texto = e.text or ""
    if e.entity_type == EntityType.mtext:
        return _caja_de_mtext(e, texto, alto)
    p = e.properties
    halign, valign = p.get("halign") or 0, p.get("valign") or 0
    factor = float(p.get("width_factor") or 1.0)
    ancho = _ancho_dibujado(e, angulo) or ANCHO_POR_CARACTER * alto * caracteres(texto) * factor
    dx0 = {1: -ancho / 2, 2: -ancho, 4: -ancho / 2}.get(halign, 0.0)
    if halign == 4:
        dy0 = -alto / 2  # «medio»: centrado en las dos direcciones
    else:
        dy0 = {2: -alto / 2, 3: -alto}.get(valign, 0.0)
    dx1, dy1 = dx0 + ancho, dy0 + alto
    inclinacion = float(p.get("oblique") or 0.0)
    if inclinacion:
        # Las letras inclinadas corren su parte de arriba hacia un lado.
        corrimiento = alto * math.tan(math.radians((inclinacion + 180.0) % 360.0 - 180.0))
        dx0, dx1 = min(dx0, dx0 + corrimiento), max(dx1, dx1 + corrimiento)
    if p.get("mirror_x"):
        dx0, dx1 = -dx1, -dx0  # al revés: el renglón corre hacia atrás desde su ancla
    if p.get("mirror_y"):
        dy0, dy1 = -dy1, -dy0  # de cabeza: cuelga bajo su línea base
    return dx0, dx1, dy0, dy1, alto


def esquinas_de_texto(e: NormalizedEntity) -> list[Point]:
    """Las cuatro esquinas del rectángulo que ocupa el texto, girado con él. Un texto sin punto
    de inserción (armado a mano, sin el normalizador) ocupa su caja."""
    if e.properties.get("insert") is None:
        x0, y0, x1, y1 = e.bbox
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    ax, ay = ancla_texto(e)
    giro = math.radians(e.rotation or 0.0)
    dx0, dx1, dy0, dy1, _alto = caja_de_texto(e, giro)
    c, s = math.cos(giro), math.sin(giro)
    return [
        (ax + u * c - v * s, ay + u * s + v * c)
        for u, v in ((dx0, dy0), (dx1, dy0), (dx1, dy1), (dx0, dy1))
    ]


def extension_de_texto(e: NormalizedEntity) -> BBox:
    """La caja alineada a los ejes que encierra el texto tal como está dibujado."""
    esquinas = esquinas_de_texto(e)
    xs, ys = [q[0] for q in esquinas], [q[1] for q in esquinas]
    return (min(xs), min(ys), max(xs), max(ys))
