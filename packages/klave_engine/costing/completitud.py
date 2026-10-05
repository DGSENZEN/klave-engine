"""Esperado y ausente: lo que una partida trae consigo y el presupuesto no tiene.

La omisión que hace perder una licitación no es una cantidad mal medida: es
una partida que nadie escribió. 1,983 m² de muro y ningún aplanado; zapatas
y ninguna plantilla; columnas de concreto armado y ningún renglón de acero.
Aquí se revisa con una tabla curada (``implicaciones.json``) y se dice con su
evidencia. Nada se agrega solo: lo que falta puede estar incluido en otro
precio, y eso lo decide una persona.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

from pydantic import BaseModel

from klave_engine.costing.matching import normalize
from klave_engine.costing.models import BillOfQuantities


class Ausente(BaseModel):
    id: str
    partida: str
    porque: str
    evidencia: str
    buscar: str  # con qué palabra buscarla en tu catálogo


@lru_cache(maxsize=1)
def reglas() -> list[dict]:
    raw = json.loads(
        resources.files("klave_engine.costing").joinpath("implicaciones.json").read_text(
            encoding="utf-8"
        )
    )
    return list(raw["reglas"])


def _textos(line) -> list[str]:
    return [normalize(line.description)] + [
        normalize(t) for v in line.variants for t in (v.mapped_description, v.description) if t
    ]


def esperado_y_ausente(boq: BillOfQuantities, plantas: int = 1) -> list[Ausente]:
    activos = {line.concept_code: line for line in boq.lines if line.quantity > 0}
    textos = [t for line in activos.values() for t in _textos(line)]
    out: list[Ausente] = []
    for regla in reglas():
        esperado = any(c in activos for c in regla.get("espera", [])) or any(
            code.startswith(p) for code in activos for p in regla.get("espera_prefijo", [])
        )
        if esperado:
            continue
        palabras = [normalize(p) for p in regla.get("palabras", [])]
        incluido = [normalize(p) for p in regla.get("incluido", [])]
        if "si_plantas" in regla:
            if plantas < int(regla["si_plantas"]):
                continue
            if any(p in t for t in textos for p in palabras):
                continue
            evidencia = f"el plano trae {plantas} plantas"
        else:
            disparadores = [activos[c] for c in regla["si"] if c in activos]
            if not disparadores:
                continue
            if regla.get("por_renglon"):
                # Cada renglón tiene que traerlo él mismo: el acero de una losa
                # no arma las columnas.
                faltan = [
                    ln for ln in disparadores
                    if not any(p in t for t in _textos(ln) for p in incluido + palabras)
                ]
            else:
                if any(p in t for t in textos for p in palabras):
                    continue
                faltan = [
                    ln for ln in disparadores
                    if not any(p in t for t in _textos(ln) for p in incluido)
                ]
            if not faltan:
                continue
            principal = max(faltan, key=lambda ln: ln.quantity)
            evidencia = (
                f"el plano trae {principal.quantity:,.2f} {principal.unit} de "
                f"«{principal.description[:60]}»"
            )
            if len(faltan) > 1:
                evidencia += f" y {len(faltan) - 1} renglón(es) más"
        out.append(Ausente(
            id=regla["id"], partida=regla["partida"], porque=regla["porque"],
            evidencia=evidencia, buscar=regla.get("palabras", [regla["partida"]])[0],
        ))
    return out
