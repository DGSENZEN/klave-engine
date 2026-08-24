"""Cantidades que se siguen de otras: aplanado sobre muro, pintura sobre
aplanado, impermeabilización sobre azotea.

Una parte grande del presupuesto no se lee del plano ni se propone desde la
historia del taller: **se deduce de lo que ya se midió**. Si hay 420 m² de
muro, hay 840 m² de aplanado (dos caras) y, sobre esos, 840 m² de pintura. El
plano no dibuja el aplanado; el aplanado es una consecuencia del muro.

Eso las distingue de los paramétricos, y la distinción importa:

* un **paramétrico** es una apuesta desde obras anteriores («esta casa suele
  llevar 1.2 salidas eléctricas por m²») y se marca como propuesta;
* una **derivada** es aritmética sobre una cantidad medida, y su confianza es
  la de la cantidad de la que salió, menos nada.

Por eso una derivada entra al presupuesto como línea normal, con su evidencia
diciendo de dónde salió — «420.00 m² de muro (EST-004) × 2 caras» — y no como
sugerencia. Lo que sigue siendo un supuesto es el **factor**, y el factor se
declara en la regla, se imprime en la línea y el taller puede cambiarlo.

Nunca se deriva sobre una cantidad que no se midió: si el muro no se detectó,
no hay aplanado. Inventar la base y luego multiplicarla sería inventar dinero
con más pasos.
"""

from __future__ import annotations

from dataclasses import dataclass

from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    Concept,
    QuantityKind,
    UnitPriceAnalysis,
)


@dataclass(frozen=True)
class Derivada:
    """Un concepto cuya cantidad sale de otros, por un factor declarado."""

    destino: str  # el concepto que se va a crear o completar
    origenes: tuple[str, ...]  # de cuáles sale
    factor: float
    # Por qué ese factor, en el lenguaje del oficio. Se imprime en la línea.
    razon: str
    # Cuando el destino ya trae cantidad propia (leída del plano), no se toca:
    # una lectura real siempre gana sobre una deducción.
    solo_si_falta: bool = True


# Las que se sostienen sin discusión en obra de edificación. El factor vive
# aquí para que se pueda leer, citar y cambiar en un solo lugar.
DERIVADAS: tuple[Derivada, ...] = (
    Derivada(
        destino="ACA-002",
        origenes=("ACA-001",),
        factor=1.0,
        razon="se pinta la superficie aplanada, uno a uno",
    ),
    Derivada(
        destino="ACA-004",
        origenes=("ACA-003",),
        factor=1.0,
        razon="se pinta el plafón aplanado, uno a uno",
    ),
)


def _linea_base(
    boq: BillOfQuantities, codigos: tuple[str, ...], unidad_destino: str
) -> tuple[float, list[str], list[str]]:
    """Suma de las cantidades medidas de las que se deriva, sus claves, y las
    que se descartaron por venir en otra unidad.

    Un factor multiplica un número, no lo convierte: derivar m² de aplanado a
    partir de m³ de concreto daría una cifra con la forma correcta y el valor
    equivocado, que es la peor clase de error porque nadie la nota."""
    total = 0.0
    usados: list[str] = []
    descartados: list[str] = []
    objetivo = unidad_destino.strip().upper().replace("³", "3").replace("²", "2")
    for linea in boq.lines:
        if linea.concept_code not in codigos or linea.quantity <= 0:
            continue
        unidad = linea.unit.strip().upper().replace("³", "3").replace("²", "2")
        if unidad != objetivo:
            descartados.append(f"{linea.concept_code} ({linea.unit})")
            continue
        total += linea.quantity
        usados.append(linea.concept_code)
    return total, usados, descartados


def aplicar_derivadas(
    boq: BillOfQuantities,
    catalog: list[Concept],
    apus: dict[str, UnitPriceAnalysis],
    reglas: tuple[Derivada, ...] = DERIVADAS,
) -> int:
    """Agrega al presupuesto las cantidades que se siguen de otras.

    Devuelve cuántas líneas se derivaron. Una derivada nunca pisa una
    cantidad leída del plano ni una fijada a mano: la lectura manda."""
    conceptos = {c.code: c for c in catalog}
    lineas = {line.concept_code: line for line in boq.lines}
    derivadas = 0

    for regla in reglas:
        concepto = conceptos.get(regla.destino)
        if concepto is None:
            continue
        existente = lineas.get(regla.destino)
        if existente is not None and regla.solo_si_falta and existente.quantity > 0:
            continue  # ya se midió: no se deduce encima
        base, usados, descartados = _linea_base(boq, regla.origenes, concepto.unit)
        if descartados:
            boq.warnings.append(
                f"{regla.destino}: no se derivó de {', '.join(descartados)} porque está "
                f"en otra unidad que {concepto.unit}. Un factor multiplica, no convierte."
            )
        if base <= 0:
            continue  # sin cantidad de origen no hay nada que derivar

        cantidad = round(base * regla.factor, 4)
        apu = apus.get(regla.destino)
        precio = apu.direct_unit_cost if apu else 0.0
        evidencia = (
            f"Cantidad derivada de {', '.join(sorted(set(usados)))}: "
            f"{base:,.2f} {concepto.unit} × {regla.factor:g} "
            f"({regla.razon}). No se leyó del plano."
        )
        if existente is not None:
            existente.quantity = cantidad
            existente.raw_quantity = cantidad
            existente.unit_price = precio
            existente.amount = round(cantidad * precio, 2)
            existente.unpriced = apu is None
            existente.assumptions.append(evidencia)
        else:
            boq.lines.append(
                BoqLine(
                    concept_code=concepto.code,
                    description=concepto.description,
                    unit=concepto.unit,
                    quantity=cantidad,
                    unit_price=precio,
                    amount=round(cantidad * precio, 2) if apu else 0.0,
                    # Cantidad real sin matriz: el importe es desconocido, no
                    # cero, y el presupuesto tiene que decirlo.
                    unpriced=apu is None,
                    phase=concepto.phase,
                    raw_quantity=cantidad,
                    raw_kind=QuantityKind.AREA,
                    source_detection_count=0,
                    source_detections=[],
                    # La confianza es la de la cantidad de la que salió: no se
                    # degrada por derivar, porque la aritmética no se equivoca.
                    confidence=min(
                        (
                            line.confidence
                            for line in boq.lines
                            if line.concept_code in regla.origenes
                        ),
                        default=0.8,
                    ),
                    assumptions=[evidencia],
                )
            )
        derivadas += 1
    return derivadas
