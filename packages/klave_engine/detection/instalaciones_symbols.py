"""Qué símbolo es qué, en planos mexicanos de instalaciones.

Un plano de instalaciones no dibuja elementos estructurales: dibuja símbolos
insertados (un W.C., un contacto, un difusor) y trazos sobre capas con nombre
de sistema (agua fría, sanitaria, ducto). Este módulo es la tabla que dice qué
nombre corresponde a qué familia, y es el único lugar donde vive esa
convención — los dos detectores la leen de aquí.

Tres niveles de honestidad, y el orden importa:

1. Lo que la tabla reconoce se vuelve **detección**: un elemento con su caja,
   su confianza, su evidencia y su vista, que cuantifica solo.
2. Lo que no reconoce pero se parece se **propone** como asignación en la
   pantalla de lectura, con la razón escrita.
3. Lo que no cae en ninguna de las dos sigue siendo un **conteo** del
   levantamiento, visible, sin precio y sin desaparecer.

Ningún nivel inventa nada; cambian sólo en cuánto trabajo le ahorran a quien
presupuesta. Un nombre de bloque que nadie reconoció nunca se pierde.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SimboloRegla:
    """Un nombre de bloque que corresponde a una familia de mueble o salida."""

    familia: str
    patron: re.Pattern[str]
    disciplina: str
    # Qué es, en una frase, para la descripción de la detección.
    que_es: str


def _r(patron: str) -> re.Pattern[str]:
    return re.compile(patron, re.I)


# El orden manda: la primera regla que casa gana, así que lo específico va
# antes que lo general (MINGITORIO antes que cualquier cosa con "URIN").
MUEBLES: tuple[SimboloRegla, ...] = (
    # --- Hidráulica y sanitaria: muebles -----------------------------------
    SimboloRegla("wc", _r(r"\bW\.?C\.?\b|INODORO|^TAZA|EXCUSADO|^SANIT[AO]"),
                 "hidrosanitaria", "W.C."),
    SimboloRegla("lavabo", _r(r"LAVABO|^LVB|^LAV\b|OVALIN"),
                 "hidrosanitaria", "lavabo"),
    SimboloRegla("regadera", _r(r"REGADERA|^REG\b|DUCHA"),
                 "hidrosanitaria", "regadera"),
    SimboloRegla("fregadero", _r(r"FREGADERO|^TARJA|^FREG"),
                 "hidrosanitaria", "fregadero o tarja"),
    SimboloRegla("mingitorio", _r(r"MINGITORIO|URINAL|URINARIO"),
                 "hidrosanitaria", "mingitorio"),
    SimboloRegla("tina", _r(r"^TINA|BA[ÑN]ERA|JACUZZI"),
                 "hidrosanitaria", "tina"),
    SimboloRegla("lavadero", _r(r"LAVADERO|LAVADORA|^LVD"),
                 "hidrosanitaria", "lavadero"),
    SimboloRegla("calentador", _r(r"CALENTADOR|BOILER|^CAL\b"),
                 "hidrosanitaria", "calentador"),
    # --- Hidráulica y sanitaria: piezas de red -----------------------------
    SimboloRegla("salida_sanitaria", _r(r"^DESCSAN|^DESC[ _-]?SAN|DESCARGA"),
                 "hidrosanitaria", "salida sanitaria de descarga"),
    SimboloRegla("registro", _r(r"^REG(ISTRO)?[ _-]|^RS[ _-]?\d|POZO[ _-]?VIS"),
                 "hidrosanitaria", "registro sanitario"),
    SimboloRegla("coladera", _r(r"COLADERA|^CDP\b|^C\.?D\.?P\.?\b"),
                 "hidrosanitaria", "coladera"),
    SimboloRegla("bajada", _r(r"SUBIDA[ _-]?BAJADA|^B\.?A\.?[PN]\.?\b|^BAJADA"),
                 "hidrosanitaria", "subida o bajada de la red"),
    SimboloRegla("valvula", _r(r"V[ÁA]LVULA|VALV|LLAVE[ _-]?DE[ _-]?PASO|^PASO$"),
                 "hidrosanitaria", "válvula"),
    SimboloRegla("medidor", _r(r"MEDIDOR|^TOMA[ _-]|HIDR[ÓO]METRO"),
                 "hidrosanitaria", "medidor o toma"),
    # --- Eléctrica ---------------------------------------------------------
    SimboloRegla("contacto", _r(r"CONTACTO|TOMACORR|^C[ _-]?DOBLE|^CTO\b"),
                 "electrica", "contacto"),
    SimboloRegla("apagador", _r(r"APAGADOR|INTERRUPTOR|^SW[ _-]?\d|^APG"),
                 "electrica", "apagador"),
    SimboloRegla("luminaria", _r(r"LUMINARI|L[ÁA]MPARA|^LAMP|^LUZ\b|ARBOTANTE|SPOT"),
                 "electrica", "luminaria o centro de luz"),
    SimboloRegla("tablero", _r(r"TABLERO|CENTRO[ _-]?DE[ _-]?CARGA|^C\.?C\.?\b|^TDC"),
                 "electrica", "tablero o centro de carga"),
    SimboloRegla("salida_especial", _r(r"SALIDA[ _-]?ESP|^SE[ _-]?\d|^S\.?E\.?\b"),
                 "electrica", "salida especial"),
    # --- Aire acondicionado ------------------------------------------------
    SimboloRegla("difusor", _r(r"DIFUSOR|REJILLA|^REJ|^DL\d|CAJA[ _-]?DL|^RI\b|^RR\b|"
                                r"^RE\b|EXTRACT"),
                 "aire", "rejilla o difusor"),
    SimboloRegla("compuerta", _r(r"COMPUERTA|^COMP\d|DAMPER|BYPASS|^BYP\b"),
                 "aire", "compuerta o bypass"),
    SimboloRegla("equipo_aa", _r(r"MINISPLIT|MINI[ _-]?SPLIT|CONDENSADOR|EVAPORADOR|"
                                 r"FAN[ _-]?COIL|^COND\b|^EVAP|MANEJADORA|^UMA\b"),
                 "aire", "equipo de aire acondicionado"),
    # --- Gas ---------------------------------------------------------------
    SimboloRegla("tanque_gas", _r(r"TANQUE[ _-]?(DE[ _-]?)?GAS|^TG\b|ESTACIONARIO"),
                 "gas", "tanque de gas"),
)


@dataclass(frozen=True)
class CorridaRegla:
    """Una capa cuyo trazo es una tubería, un ducto o una canalización."""

    familia: str
    patron: re.Pattern[str]
    disciplina: str
    que_es: str


# Igual que arriba: lo específico primero. «RETORNO» a secas no basta —
# «SEB - Retorno Filtrado» es la filtración de una alberca, no el retorno de
# agua caliente, y un patrón ancho de más convierte una convención de dibujo
# en dinero equivocado.
CORRIDAS: tuple[CorridaRegla, ...] = (
    CorridaRegla("agua_caliente", _r(r"(^|[-_ ])H\s*PIP|AGUA[ _-]?CALIENTE|\bA\.?C\.?\b"),
                 "hidraulica", "tubería de agua caliente"),
    CorridaRegla("retorno", _r(r"(^|[-_ ])R\s*PIP|RETORNO[ _-]*(A\.?C\.?|AGUA|CALIENTE)"),
                 "hidraulica", "retorno de agua caliente"),
    CorridaRegla("agua_fria", _r(r"(^|[-_ ])C\s*PIP|AGUA[ _-]?FRIA|AGUA[ _-]?FRÍA|\bA\.?F\.?\b"),
                 "hidraulica", "tubería de agua fría"),
    CorridaRegla("pluvial", _r(r"PLUVIAL|B\.?A\.?P\.?"), "sanitaria",
                 "bajada de aguas pluviales"),
    CorridaRegla("sanitaria", _r(r"SANITARI|ALBA[ÑN]AL|AGUAS[ _-]?NEGRAS"), "sanitaria",
                 "albañal sanitario"),
    CorridaRegla("gas", _r(r"^GAS([ _-]|$)|TUB.*GAS|\bGAS\b.*TUB"), "gas",
                 "tubería de gas"),
    CorridaRegla("ducto_flexible", _r(r"FLEXIBLE"), "aire", "ducto flexible"),
    CorridaRegla("ducto", _r(r"DUCTO|\bDUCT\b"), "aire", "ducto de lámina"),
    CorridaRegla("refrigerante", _r(r"TUBO[ _-]?CU|COBRE|REFRIGERANT"), "aire",
                 "tubería de refrigerante"),
    CorridaRegla("conduit", _r(r"CONDUIT|CANALIZ|^E[ _-]?TUB"), "electrica",
                 "canalización eléctrica"),
)

# Capas que están en la hoja pero no son de la instalación: el fondo
# arquitectónico sobre el que se dibuja. En una hoja de aire acondicionado
# conviven AireDucto con MUROS2, COLUMNA y PLAFONES, y sin este filtro los
# muros del dibujo de fondo se volverían metros de ducto.
FONDO = re.compile(
    r"^MURO|^COLUMNA|^PLAFON|^ACABADO|^PISO\d|^MUROBAJO|^LOSA|^TRABE|^CIMENT|"
    r"^ARQ|^EJE|^COTA|^TEXTO|^MOBIL|^VEGETA|^ANDADOR|^BANQUET",
    re.I,
)


def familia_de_bloque(block_name: str, layer: str) -> SimboloRegla | None:
    """La familia de un bloque insertado, o None si la tabla no lo reconoce.

    Se busca en el nombre del bloque y, si ahí no dice nada, en el de su capa:
    hay planos donde el bloque se llama ``sms`` y la capa ``CZ - Compuertas``."""
    for regla in MUEBLES:
        if regla.patron.search(block_name or ""):
            return regla
    for regla in MUEBLES:
        if regla.patron.search(layer or ""):
            return regla
    return None


def familia_de_capa(layer: str) -> CorridaRegla | None:
    """La familia de una capa de trazo, o None si no es de instalaciones."""
    if not layer or FONDO.search(layer):
        return None
    for regla in CORRIDAS:
        if regla.patron.search(layer):
            return regla
    return None
