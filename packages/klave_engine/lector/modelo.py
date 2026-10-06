"""El modelo, leído sin dependencias: árboles exportados a JSON y sumados en
Python puro. Entrenar necesita scikit-learn (grupo ``lector``); proponer no.

Un nodo numérico manda a la izquierda si el valor es ≤ su umbral; un valor
que falta sigue ``faltante_izq``. La suma de las hojas más la base pasa por
una logística — ese número ordena candidatos y nunca se muestra."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import cache
from pathlib import Path

MODELOS = Path(__file__).parent / "modelos"
ACTIVO = MODELOS / "activo.txt"


@dataclass(frozen=True)
class Modelo:
    version: str
    nombres: tuple[str, ...]
    base: float
    arboles: tuple[tuple[tuple, ...], ...]  # (valor, rasgo, umbral, faltante_izq, izq, der, hoja)
    umbral: float
    max_por_hoja: int

    @classmethod
    def cargar(cls, carpeta: Path) -> Modelo:
        data = json.loads((carpeta / "modelo.json").read_text("utf-8"))
        return cls(
            version=data["version"], nombres=tuple(data["rasgos"]), base=float(data["base"]),
            arboles=tuple(tuple(tuple(n) for n in arbol) for arbol in data["arboles"]),
            umbral=float(data["umbral"]), max_por_hoja=int(data["max_por_hoja"]),
        )

    @staticmethod
    def activo() -> Modelo | None:
        return _activo()

    def puntuar(self, x: list[float | None]) -> float:
        total = self.base
        for arbol in self.arboles:
            i = 0
            while True:
                valor, rasgo, umbral, faltante_izq, izq, der, hoja = arbol[i]
                if hoja:
                    total += valor
                    break
                v = x[rasgo]
                if v is None or math.isnan(v):
                    i = izq if faltante_izq else der
                else:
                    i = izq if v <= umbral else der
        return 1.0 / (1.0 + math.exp(-total))


@cache
def _activo() -> Modelo | None:
    if not ACTIVO.exists():
        return None
    carpeta = MODELOS / ACTIVO.read_text("utf-8").strip()
    return Modelo.cargar(carpeta) if (carpeta / "modelo.json").exists() else None
