"""Cuánto cuesta una llamada de IA, y hasta dónde puede gastar un taller.

Dos cosas que conviene decir de frente:

**Las tarifas son declaradas, no consultadas.** Ningún proveedor publica un
precio que se pueda leer desde el programa, y adivinarlo sería inventar
dinero — lo mismo que Klave se prohíbe en los presupuestos. Así que la tabla
de abajo son los valores que el operador declara, con la fecha en que los
declaró, y toda cifra derivada de ella se muestra como **estimación**. Si el
operador no declara la tarifa de un modelo, el costo estimado es cero y la
interfaz dice que no está tarifado, en vez de fingir un número.

**El presupuesto es un freno, no un aviso.** Cuando un taller llega a su tope
mensual, la siguiente llamada se rechaza con un mensaje que explica qué pasó
y cómo subirlo. Un tope que solo advierte no es un tope: la evidencia sobre
avisos ignorados es abundante y ya la aplicamos en los hallazgos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from klave_engine.common.bitacora import uso_del_periodo


@dataclass(frozen=True)
class Tarifa:
    """USD por millón de tokens, como los publican los proveedores."""

    entrada_por_millon: float
    salida_por_millon: float
    declarada: str  # la fecha en que el operador la puso


# Tarifas declaradas por el operador. No son un precio oficial consultado en
# vivo: son lo que quien administra Klave escribió aquí, con su fecha, y por
# eso todo lo que sale de ellas se rotula "estimado".
TARIFAS: dict[str, Tarifa] = {
    # Gemini (Google AI Studio), tarifas de lista declaradas 2026-08.
    "gemini-3.7-flash": Tarifa(0.30, 2.50, "2026-08"),
    "gemini-3.5-flash": Tarifa(0.30, 2.50, "2026-08"),
    "gemini-2.5-pro": Tarifa(1.25, 10.00, "2026-08"),
    # Anthropic, tarifas de lista declaradas 2026-08.
    "claude-opus-5": Tarifa(5.00, 25.00, "2026-08"),
    "claude-sonnet-5": Tarifa(3.00, 15.00, "2026-08"),
    "claude-haiku-4-5-20251001": Tarifa(1.00, 5.00, "2026-08"),
}


def tarifa_de(modelo: str) -> Tarifa | None:
    """La tarifa declarada para ese modelo, o None si nadie la declaró."""
    if modelo in TARIFAS:
        return TARIFAS[modelo]
    # Un modelo con sufijo de fecha o región comparte tarifa con su familia.
    for clave, tarifa in TARIFAS.items():
        if modelo.startswith(clave):
            return tarifa
    return None


def costo_estimado(modelo: str, tokens_entrada: int, tokens_salida: int) -> float:
    """USD estimados, o 0.0 cuando el modelo no está tarifado.

    Cero significa "no sé", no "es gratis", y quien lo muestre debe decirlo."""
    tarifa = tarifa_de(modelo)
    if tarifa is None:
        return 0.0
    return round(
        tokens_entrada / 1_000_000 * tarifa.entrada_por_millon
        + tokens_salida / 1_000_000 * tarifa.salida_por_millon,
        6,
    )


@dataclass
class Consumo:
    """Lo gastado en un periodo, y qué tan cerca está del tope."""

    llamadas: int
    tokens_entrada: int
    tokens_salida: int
    costo_estimado_usd: float
    tope_usd: float | None
    sin_tarifar: int  # llamadas cuyo modelo no tiene tarifa declarada

    @property
    def excedido(self) -> bool:
        return self.tope_usd is not None and self.costo_estimado_usd >= self.tope_usd

    @property
    def porcentaje(self) -> float | None:
        if not self.tope_usd:
            return None
        return round(100.0 * self.costo_estimado_usd / self.tope_usd, 1)


def consumo_del_mes(
    data_dir: Path,
    workspace: str,
    tope_usd: float | None = None,
    hoy: date | None = None,
) -> Consumo:
    """Lo que este taller lleva gastado en el mes en curso."""
    hoy = hoy or datetime.now(UTC).date()
    primero = hoy.replace(day=1)
    filas = uso_del_periodo(data_dir, primero, hoy, workspace=workspace)
    return Consumo(
        llamadas=len(filas),
        tokens_entrada=sum(int(f.get("tokens_entrada") or 0) for f in filas),
        tokens_salida=sum(int(f.get("tokens_salida") or 0) for f in filas),
        costo_estimado_usd=round(
            sum(float(f.get("costo_estimado_usd") or 0.0) for f in filas), 4
        ),
        tope_usd=tope_usd,
        sin_tarifar=sum(
            1 for f in filas if tarifa_de(str(f.get("modelo") or "")) is None
        ),
    )


def estimar_lectura(hojas: int, modelo: str, tokens_por_hoja: int = 1300) -> float:
    """Lo que costaría leer una obra de N hojas, antes de empezar.

    ``tokens_por_hoja`` sale de la media medida en corridas anteriores cuando
    la hay; el valor por defecto es el orden de magnitud de una hoja de 2 600
    px. Se muestra como estimación, nunca como cargo."""
    salida_por_hoja = max(tokens_por_hoja // 3, 200)
    return costo_estimado(modelo, hojas * tokens_por_hoja, hojas * salida_por_hoja)
