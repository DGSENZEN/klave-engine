"""El modelo, leído sin dependencias: árboles exportados a JSON y sumados en
Python puro. Entrenar necesita scikit-learn (grupo ``lector``); proponer no.

Un nodo numérico manda a la izquierda si el valor es ≤ su umbral; un valor
que falta sigue ``faltante_izq``. La suma de las hojas más la base pasa por
una logística — ese número ordena candidatos y nunca se muestra.

Un proyecto con el que se entrenó se califica con el pliegue que lo dejó
fuera: el modelo completo ya vio sus figuras sin revisar como «no es» y
callaría justo ahí."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from functools import cache
from pathlib import Path

MODELOS = Path(__file__).parent / "modelos"
ACTIVO = MODELOS / "activo.txt"

# Cada nodo: (valor, rasgo, umbral, faltante_izq, izq, der, hoja).
Arboles = tuple[tuple[tuple, ...], ...]


def opaco(project_id: str) -> str:
    """El nombre de un proyecto en un modelo: un hash, nunca el nombre."""
    return hashlib.sha1(project_id.encode()).hexdigest()[:10]


def _arboles(data: dict) -> tuple[float, Arboles]:
    return float(data["base"]), tuple(tuple(tuple(n) for n in a) for a in data["arboles"])


@dataclass(frozen=True)
class Modelo:
    version: str
    nombres: tuple[str, ...]
    base: float
    arboles: Arboles
    umbral: float
    max_por_hoja: int
    features_version: int = 1
    pliegues: dict[str, tuple[float, Arboles]] = field(default_factory=dict)
    # Los planos (sha256 recortado) con que entrenó cada pliegue: el mismo
    # plano subido a otro proyecto también se califica con el que no lo vio.
    dibujos: dict[str, frozenset[str]] = field(default_factory=dict)

    @classmethod
    def cargar(cls, carpeta: Path) -> Modelo:
        data = json.loads((carpeta / "modelo.json").read_text("utf-8"))
        base, arboles = _arboles(data.get("completo") or data)
        return cls(
            version=data["version"], nombres=tuple(data["rasgos"]), base=base, arboles=arboles,
            umbral=float(data["umbral"]), max_por_hoja=int(data["max_por_hoja"]),
            features_version=int(data.get("features_version", 1)),
            pliegues={k: _arboles(v) for k, v in (data.get("pliegues") or {}).items()},
            dibujos={k: frozenset(v) for k, v in (data.get("dibujos") or {}).items()},
        )

    @staticmethod
    def activo() -> Modelo | None:
        return _activo()

    def para(self, project_id: str, dibujos: set[str] | None = None) -> Modelo:
        """El modelo que califica este proyecto: el pliegue que lo dejó fuera
        si entrenó con él, o el que dejó fuera más de sus planos."""
        clave = opaco(project_id)
        if clave not in self.pliegues and dibujos:
            mios = {d[:16] for d in dibujos}
            traslape = {k: len(mios & v) for k, v in self.dibujos.items() if k in self.pliegues}
            mejor = max(traslape, key=lambda k: traslape[k], default=None)
            if mejor is not None and traslape[mejor] > 0:
                clave = mejor
        pliegue = self.pliegues.get(clave)
        if pliegue is None:
            return self
        return replace(self, base=pliegue[0], arboles=pliegue[1], pliegues={}, dibujos={})

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
