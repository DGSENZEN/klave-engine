"""Qué disciplina es cada hoja, por su nombre y por su vocabulario.

El nombre propone (llega slugificado y sin ñ: «albañilería» es "alba iler
a"), el contenido vota (capas y bloques contra estos vocabularios), y una
hoja que nadie reclama se lee como estructura — la regla de siempre. El
orden de la tupla manda: el primer patrón que casa gana, así que lo
específico va antes que lo general.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass


def _r(patron: str) -> re.Pattern[str]:
    return re.compile(patron, re.I)


@dataclass(frozen=True)
class DisciplineSuite:
    key: str
    name_hint: re.Pattern[str]
    layer_hints: tuple[str, ...] = ()
    block_hints: tuple[str, ...] = ()
    structural: bool = False
    # Las suites reales (hidrosanitaria en adelante) llenan este hueco con
    # sus detectores; mientras es None, suite.py conserva su cableado.
    detect: Callable[..., list] | None = None


SUITES: tuple[DisciplineSuite, ...] = (
    DisciplineSuite("hidraulica", _r(r"HIDR|AGUA|HPIP|CPIP|H\.?F\.?|H\.?C\.?"),
                    layer_hints=("HIDR", "HPIP", "CPIP", "RPIP")),
    DisciplineSuite("sanitaria", _r(r"SANIT|PLUV|DREN|ALBA[ÑN]AL"),
                    layer_hints=("SANITARIA", "PLUV")),
    DisciplineSuite("electrica", _r(r"ELEC|LUMIN|LAMP|CONTACT|APAG|TABLERO")),
    DisciplineSuite("gas", _r(r"\bGAS\b|PEAD"), layer_hints=("GAS",)),
    DisciplineSuite("aire", _r(r"AIRE|\bAA\b|DUCTO|CLIMA|HVAC|MINISPLIT|COND"),
                    block_hints=("COND", "COMPUERTA")),
    DisciplineSuite("cctv", _r(r"CCTV|CAMARA|CÁMARA|SEGURIDAD|SENSOR|ALARMA")),
    DisciplineSuite("canceleria", _r(r"CANCEL|VENTANA|PUERTA|ALUM|HERRER"),
                    block_hints=("CANC", "PTALOUVER")),
    DisciplineSuite("acabados", _r(r"ACABAD|\bPISOS?\b|PLAFON|PINTURA|AZULEJO|LAMBR"),
                    block_hints=("QRF", "CAMBIO-ACABADOS")),
    DisciplineSuite("carpinteria", _r(r"CARPINT|MADERA|CLOSET|COCINA")),
    # La subida slugifica y pierde la ñ: «albañilería» llega como "alba iler a".
    DisciplineSuite("albanileria", _r(r"ALBA[ÑN]ILER|ALBA\W?ILER")),
    DisciplineSuite("indice", _r(r"\bINDICE\b|ÍNDICE|PORTADA|CAR[ÁA]TULA")),
    # El fondo arquitectónico: sustrato que ancla, nunca partida (§9).
    DisciplineSuite("arquitectura", _r(r"\bXREF\b|\bARQ\b|ARQUITEC")),
    DisciplineSuite("estructural", _r(r"EST|TRABE|LOSA|ZAPATA|CASTILL|COLUMN|CIMENT"),
                    layer_hints=("EST", "EJES", "TRABE", "ZAPATA"), structural=True),
)
