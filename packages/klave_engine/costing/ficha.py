"""La ficha técnica de un concepto: sus características, extraídas del texto.

Un concepto de catálogo trae sus datos duros enterrados en la descripción —
«f'c= 300 kg/cm2, t.m.a. de 20 mm, fraguado de 14 días, revenimiento 14,
clase 1, bombeable» — y quien cotiza los lee de un vistazo en OPUS porque
OPUS los enseña como campos. Aquí se extraen con las mismas reglas del
oficio que usa el matcher: nada se inventa; lo que el texto no dice, la
ficha no lo trae.
"""

from __future__ import annotations

import re
import unicodedata

_FC = re.compile(r"f['’´]?c\s*=?\s*(\d{2,3})\s*(?:kg\s*/\s*cm2?)?", re.IGNORECASE)
_FY = re.compile(r"fy\s*=?\s*(\d{3,4})\s*(?:kg\s*/\s*cm2?)?", re.IGNORECASE)
_TMA = re.compile(r"t\.?\s*m\.?\s*a\.?\s*(?:de\s*)?(\d{1,2})\s*mm", re.IGNORECASE)
_REVENIMIENTO = re.compile(r"revenimiento\s*(?:de\s*)?(\d{1,2})", re.IGNORECASE)
_FRAGUADO_DIAS = re.compile(r"fraguado\s*(?:de\s*)?(\d{1,2})\s*dias?", re.IGNORECASE)
_FRAGUADO_TIPO = re.compile(r"fraguado\s+(normal|rapido)", re.IGNORECASE)
_CLASE = re.compile(r"\bclase\s*([12])\b", re.IGNORECASE)
_VARILLA = re.compile(r"(?:del?\s+)?no\.?\s*(\d{1,2})\s*\(([^)]{1,8})\)", re.IGNORECASE)
_VARILLA_GATO = re.compile(r"#\s*(\d{1,2})\b")
_ESPESOR = re.compile(
    r"(?:espesor\s*(?:de\s*)?(\d{1,3}(?:[.,]\d)?)\s*cm|(\d{1,3}(?:[.,]\d)?)\s*cm\s*de\s*espesor)",
    re.IGNORECASE,
)
_PROPORCION = re.compile(r"\b1\s*:\s*(\d{1,2})\b")
_ACABADO = re.compile(r"acabado\s+(comun|aparente)", re.IGNORECASE)

# Los elementos donde el concepto se aplica, en el orden en que el texto los
# nombra. «losas macizas y reticulares» son dos, y la frase entre paréntesis
# de una superestructura los trae todos.
_ELEMENTOS = [
    "columnas de cimentacion",
    "losas macizas",
    "losas reticulares",
    "contratrabes",
    "columnas",
    "trabes",
    "losas",
    "muros",
    "zapatas",
    "castillos",
    "cadenas",
    "dalas",
    "pretiles",
    "faldones",
    "pilotes",
    "firmes",
    "entrepiso",
    "azotea",
    "cimentacion",
    "superestructura",
    "subestructura",
]


def _plano(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in plain if not unicodedata.combining(c)).lower()


def extraer_ficha(descripcion: str) -> list[dict]:
    """Las características del concepto como pares campo·valor, en orden fijo."""
    text = descripcion or ""
    low = _plano(text)
    ficha: list[dict] = []

    def add(campo: str, valor: str) -> None:
        if valor and not any(f["campo"] == campo for f in ficha):
            ficha.append({"campo": campo, "valor": valor})

    m = _FC.search(low)
    if m:
        add("f'c", f"{m.group(1)} kg/cm²")
    m = _FY.search(low)
    if m:
        add("fy", f"{m.group(1)} kg/cm²")
    m = _VARILLA.search(low)
    if m:
        add("Varilla", f"n.º {m.group(1)} ({m.group(2).strip()})")
    elif (m := _VARILLA_GATO.search(text)) is not None:
        add("Varilla", f"n.º {m.group(1)}")
    m = _TMA.search(low)
    if m:
        add("T.M.A.", f"{m.group(1)} mm")
    m = _REVENIMIENTO.search(low)
    if m:
        add("Revenimiento", m.group(1))
    m = _FRAGUADO_DIAS.search(low)
    if m:
        add("Fraguado", f"{m.group(1)} días")
    elif (m := _FRAGUADO_TIPO.search(low)) is not None:
        add("Fraguado", m.group(1).replace("rapido", "rápido"))
    m = _CLASE.search(low)
    if m:
        add("Clase", m.group(1))
    if "bombeable" in low:
        add("Colocación", "bombeable")
    elif "tiro directo" in low:
        add("Colocación", "tiro directo")
    if "fabricado en planta" in low or "premezclado" in low:
        add("Fabricación", "premezclado en planta")
    elif "hecho en obra" in low or "hecha en obra" in low:
        add("Fabricación", "en obra")
    m = _ACABADO.search(low)
    if m:
        add("Acabado", m.group(1).replace("comun", "común"))
    m = _ESPESOR.search(low)
    if m:
        add("Espesor", f"{(m.group(1) or m.group(2)).replace(',', '.')} cm")
    m = _PROPORCION.search(low)
    if m:
        add("Proporción", f"1:{m.group(1)}")

    elementos = _elementos(low)
    if elementos:
        add("Elemento", ", ".join(elementos))
    return ficha


def _elementos(low: str) -> list[str]:
    """Los elementos nombrados, por aparición y sin traslapes: «columnas de
    cimentación» ya nombró columnas, no se cuenta dos veces."""
    encontrados: list[tuple[int, str]] = []
    for elemento in _ELEMENTOS:
        posicion = low.find(elemento)
        if posicion < 0:
            continue
        if any(elemento in previo for _, previo in encontrados):
            continue
        encontrados.append((posicion, elemento))
    encontrados.sort()
    return [nombre for _, nombre in encontrados[:5]]
