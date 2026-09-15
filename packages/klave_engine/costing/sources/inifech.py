"""El Tabulador de Precios Unitarios del INIFECH (Chiapas): cada concepto
con su precio en quince regiones del estado.

Un código de diez dígitos abre el renglón (a veces solo en su línea), la
descripción sigue en varias líneas, y cierra «UNIDAD $ p1 $ p2 … $ p15».
El precio del renglón es el de la región 1; las quince viajan en
``extra["regiones"]`` — es la señal regional más completa que publica un
gobierno mexicano.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from pathlib import Path

from klave_engine.costing.sources.pdftext import money, pdf_pages

_CODE_RE = re.compile(r"^\s*(\d{10})(?:\s+(.*))?$")
_PRICES_RE = re.compile(r"^\s*([A-Z0-9.]+)\s+((?:\$\s*[\d,]+\.\d{2}\s*){2,})$")
_MONEY_EACH = re.compile(r"\$\s*([\d,]+\.\d{2})")
_SKIP_PREFIXES = ("INSTITUTO DE LA INFRAESTRUCTURA", "Tabulador de Precios", "CÓDIGO ", "Página ")


def parse_inifech_lines(lines: Iterable[str], *, page: int = 0) -> Iterator[dict[str, object]]:
    current: dict[str, object] | None = None
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith(_SKIP_PREFIXES):
            continue
        code = _CODE_RE.match(line)
        if code:
            current = {
                "clave": code.group(1), "description": (code.group(2) or "").strip(),
                "unit": None, "price": None, "group_clave": code.group(1)[:4],
                "group_description": "", "page": page,
            }
            continue
        if current is None:
            continue
        prices = _PRICES_RE.match(line)
        if prices:
            values = [money(m.group(1)) for m in _MONEY_EACH.finditer(prices.group(2))]
            regiones = {
                str(index + 1): value for index, value in enumerate(values) if value is not None
            }
            current["unit"] = prices.group(1)
            current["price"] = regiones.get("1")
            current["extra"] = {"regiones": regiones}
            current["description"] = " ".join(str(current["description"]).split())
            yield current
            current = None
            continue
        current["description"] = f"{current['description']} {line}"


def parse_inifech(path: Path) -> Iterator[dict[str, object]]:
    for page, lines in pdf_pages(path):
        yield from parse_inifech_lines(lines, page=page)
