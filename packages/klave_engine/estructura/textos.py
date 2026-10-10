"""Dónde está cada texto del plano: el punto donde lo puso el dibujante y lo que ocupa.

La caja que trae el normalizador sale del ``insert`` y de un ancho supuesto; aquí se usa lo que
el dibujo dice de verdad: el punto de alineación de un TEXT alineado, el ancho que el CAD calculó
para los centrados y los alineados a la derecha, y en un MTEXT su punto de inserción, su columna,
la alineación de sus párrafos y cuántos renglones ocupa."""

import math

from klave_engine.dxf.entities import EntityType, NormalizedEntity

# En «alineado» (3) y «ajustado» (5) el código 11 es donde TERMINA la línea base:
# el texto arranca en el ``insert``, así que ése es su ancla.
_HALIGN_CON_FINAL_EN_EL_PUNTO = (3, 5)
# El ancho de un carácter, × el alto, para los textos cuyo ancho no viene en el dibujo (ROMANS en
# Marina mide 0.83–1.03, mediana 0.92; los centrados traen su ancho real).
ANCHO_POR_CARACTER = 0.9
# El paso entre renglones de un MTEXT, × el alto (el interlineado normal de AutoCAD).
PASO_DE_MTEXT = 5.0 / 3.0


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
        cuantos = sum(
            max(1, math.ceil(por_caracter * len(r) / ancho_de_columna)) for r in renglones
        )
        ancho = min(ancho, ancho_de_columna)
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
    total = alto + (cuantos - 1) * PASO_DE_MTEXT * alto
    dy0 = (-total, -total / 2, 0.0)[fila]
    return dx0, dx0 + ancho, dy0, dy0 + total, alto


def caja_de_texto(e: NormalizedEntity, angulo: float) -> tuple[float, float, float, float, float]:
    """La caja del texto respecto a su ancla, en la dirección del renglón (``angulo`` en
    radianes): ``(dx0, dx1, dy0, dy1, alto de un renglón)``."""
    alto = alto_de_texto(e)
    texto = e.text or ""
    if e.entity_type == EntityType.mtext:
        return _caja_de_mtext(e, texto, alto)
    p = e.properties
    halign, valign = p.get("halign") or 0, p.get("valign") or 0
    ancho = _ancho_dibujado(e, angulo) or ANCHO_POR_CARACTER * alto * len(texto.strip())
    dx0 = {1: -ancho / 2, 2: -ancho, 4: -ancho / 2}.get(halign, 0.0)
    if halign == 4:
        dy0 = -alto / 2  # «medio»: centrado en las dos direcciones
    else:
        dy0 = {2: -alto / 2, 3: -alto}.get(valign, 0.0)
    return dx0, dx0 + ancho, dy0, dy0 + alto, alto
