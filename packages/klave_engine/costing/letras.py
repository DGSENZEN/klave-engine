"""Cantidades con letra, as a licitación pública requires next to every
precio unitario: "DOSCIENTOS TREINTA Y CUATRO PESOS 56/100 M.N."."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_UNITS = [
    "", "UN", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE", "DIEZ",
    "ONCE", "DOCE", "TRECE", "CATORCE", "QUINCE", "DIECISÉIS", "DIECISIETE", "DIECIOCHO",
    "DIECINUEVE", "VEINTE", "VEINTIÚN", "VEINTIDÓS", "VEINTITRÉS", "VEINTICUATRO",
    "VEINTICINCO", "VEINTISÉIS", "VEINTISIETE", "VEINTIOCHO", "VEINTINUEVE",
]
_TENS = ["", "", "VEINTE", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA",
         "OCHENTA", "NOVENTA"]
_HUNDREDS = ["", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS",
             "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS"]


def _below_thousand(n: int) -> str:
    if n == 0:
        return ""
    if n == 100:
        return "CIEN"
    hundreds, rest = divmod(n, 100)
    words: list[str] = []
    if hundreds:
        words.append(_HUNDREDS[hundreds])
    if rest:
        if rest < 30:
            words.append(_UNITS[rest])
        else:
            tens, units = divmod(rest, 10)
            words.append(_TENS[tens] + (f" Y {_UNITS[units]}" if units else ""))
    return " ".join(words)


def _integer_words(n: int) -> str:
    """0 ≤ n < 10¹² in Spanish (Mexican usage: millones, not billones)."""
    if n == 0:
        return "CERO"
    parts: list[str] = []
    millions, rest = divmod(n, 1_000_000)
    if millions:
        parts.append(
            "UN MILLÓN" if millions == 1 else f"{_integer_words(millions)} MILLONES"
        )
    thousands, units = divmod(rest, 1000)
    if thousands:
        parts.append("MIL" if thousands == 1 else f"{_below_thousand(thousands)} MIL")
    if units:
        parts.append(_below_thousand(units))
    return " ".join(parts)


def pesos_con_letra(amount: float) -> str:
    """'UN MIL DOSCIENTOS TREINTA Y CUATRO PESOS 56/100 M.N.' — the form used
    in catálogos de conceptos for licitación (LOPSRM)."""
    value = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    negative = value < 0
    value = abs(value)
    whole = int(value)
    cents = int((value - whole) * 100)
    words = _integer_words(whole)
    if whole == 1:
        words = "UN"
    # "UN MIL" is the customary form on Mexican tenders for 1 000–1 999.
    if 1000 <= whole < 2000:
        words = "UN " + words
    # "VEINTIÚN" and "UN" agree with "pesos": they stay; "UNO" never appears.
    text = f"{words} PESOS {cents:02d}/100 M.N."
    return f"MENOS {text}" if negative else text
