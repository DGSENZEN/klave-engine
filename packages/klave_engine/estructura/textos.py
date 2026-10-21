"""Dónde está cada texto del plano: el punto donde lo puso el dibujante y lo que ocupa.

El modelo vive en ``klave_engine.dxf.text_extent`` (R146): el normalizador da con él la caja de
cada texto, y aquí se usa el mismo, para que la asociación y los detectores lean el texto en el
mismo lugar."""

from klave_engine.dxf.text_extent import (
    ANCHO_POR_CARACTER,
    PASO_DE_MTEXT,
    alto_de_texto,
    ancla_texto,
    caja_de_texto,
    esquinas_de_texto,
    extension_de_texto,
)

__all__ = [
    "ANCHO_POR_CARACTER",
    "PASO_DE_MTEXT",
    "alto_de_texto",
    "ancla_texto",
    "caja_de_texto",
    "esquinas_de_texto",
    "extension_de_texto",
]
