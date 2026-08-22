"""Parser for the Tabulador General de Precios Unitarios of Mexico City.

The PDF is real text laid out as ``Clave · Concepto de Obra · Unidad · P.U.``
where a concept's description wraps onto indented lines and parent rows
(``GC17E  Muros de tabique…``) carry no unit or price: they describe the
group that the priced children belong to. A unit token sometimes wraps to
its own line after the price; it is dropped.
"""

import re
from collections.abc import Iterable, Iterator
from pathlib import Path

_HEADER_RE = re.compile(r"^\s*Clave\s+Concepto de Obra\s+Unidad\s+P\.\s*U\.", re.I)
_ROW_RE = re.compile(r"^\s{0,12}([A-Z]{2}\d{2}[A-Z0-9]{0,4})\s{2,}(\S.*?)\s*$")
_PRICED_RE = re.compile(r"^(.*?)\s+(\S{1,14})\s+\$?([\d,]{1,12}\.\d{2})\s*$")
_PRICE_ONLY_RE = re.compile(r"^\s*\$?([\d,]{1,12}\.\d{2})\s*$")
_UNIT_ONLY_RE = re.compile(r"^\s*(\S{1,12})\s*$")
_KNOWN_UNITS = {
    "m", "m2", "m3", "ml", "pza", "pieza", "kg", "ton", "t", "lote", "jor", "hr", "h",
    "día", "dia", "km", "lt", "l", "cm", "salida", "juego", "punto", "mes", "sem", "viaje",
    "ha", "m3-km", "ton-km", "m2-día", "m-mes", "planta", "cm2", "equipo", "par", "rollo",
    "millar", "elemento", "tramo", "unidad", "u", "sal", "est", "gl", "glb", "global",
    "prueba", "lto", "muestra", "semana", "visita", "hora", "toma", "análisis", "analisis",
    "serie", "junta", "diseño", "litro", "informe", "reporte", "sondeo", "pozo",
}


def _is_unit(token: str) -> bool:
    return token.lower().strip(".") in _KNOWN_UNITS


def parse_cdmx_lines(lines: Iterable[str], *, page: int = 0) -> Iterator[dict[str, object]]:
    """Yield priced rows (and unpriced group descriptions) from layout text."""
    current: dict[str, object] | None = None
    group_desc = ""
    group_clave = ""

    def flush() -> Iterator[dict[str, object]]:
        nonlocal current, group_desc, group_clave
        if current is None:
            return
        if current.get("price") is None:
            # A parent row: becomes context for the priced rows that follow.
            group_clave = str(current["clave"])
            group_desc = " ".join(str(current["description"]).split())
        else:
            current["description"] = " ".join(str(current["description"]).split())
            current["group_clave"] = group_clave if str(current["clave"]).startswith(
                group_clave
            ) else ""
            current["group_description"] = (
                group_desc if str(current["clave"]).startswith(group_clave) else ""
            )
            yield current
        current = None

    for raw in lines:
        line = raw.rstrip()
        if not line.strip() or _HEADER_RE.match(line):
            continue
        if line.strip().startswith(("SECRETARÍA", "DIRECCIÓN", "TABULADOR", "GOBIERNO",
                                    "NORMAS", "ESTRATÉGICOS")):
            continue
        row = _ROW_RE.match(line)
        if row:
            yield from flush()
            clave, rest = row.group(1), row.group(2)
            priced = _PRICED_RE.match(rest)
            if priced and (_is_unit(priced.group(2)) or priced.group(2).isalpha()):
                current = {
                    "clave": clave,
                    "description": priced.group(1),
                    "unit": priced.group(2),
                    "price": float(priced.group(3).replace(",", "")),
                    "unit_guess": not _is_unit(priced.group(2)),
                    "page": page,
                }
            else:
                current = {"clave": clave, "description": rest, "unit": None,
                           "price": None, "page": page}
            continue
        if current is None:
            continue
        text = line.strip()
        if current.get("price") is None:
            # Continuation of an unpriced row; it may carry the unit + price.
            priced = _PRICED_RE.match(text)
            if priced and (_is_unit(priced.group(2)) or priced.group(2).isalpha()):
                current["description"] = f"{current['description']} {priced.group(1)}"
                current["unit"] = priced.group(2)
                current["price"] = float(priced.group(3).replace(",", ""))
                current["unit_guess"] = not _is_unit(priced.group(2))
            else:
                price_only = _PRICE_ONLY_RE.match(text)
                if price_only and current.get("unit"):
                    current["price"] = float(price_only.group(1).replace(",", ""))
                else:
                    current["description"] = f"{current['description']} {text}"
            continue
        # Priced row: trailing description, or a wrapped unit token to drop.
        if _UNIT_ONLY_RE.match(text) and _is_unit(text):
            continue
        current["description"] = f"{current['description']} {text}"
    yield from flush()


def parse_cdmx_tabulador(path: Path) -> Iterator[dict[str, object]]:
    import pdfplumber

    with pdfplumber.open(str(path)) as pdf:
        for index, page in enumerate(pdf.pages):
            text = page.extract_text(layout=True) or ""
            yield from parse_cdmx_lines(text.splitlines(), page=index + 1)
