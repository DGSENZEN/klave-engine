"""El Tabulador a Costo Directo de la SICT (infraestructura carretera).

Cada concepto ocupa varias líneas: «LINEA CÓDIGO descripción…», las
continuaciones, y al final «unidad $precio» en su propia línea. Un código
corto (101.03) sin precio es un capítulo o subcapítulo y da contexto a
los renglones que le siguen; el capítulo «1 CONSTRUCCIÓN» también.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from pathlib import Path

from klave_engine.costing.sources.pdftext import money, pdf_pages

_CONCEPT_RE = re.compile(r"^\s*(\d+)\s+(\d{3}\.\d{2}\.\d{4})\s+(.*)$")
_GROUP_RE = re.compile(r"^\s*(\d+)\s+(\d{3}(?:\.\d{1,2}){0,2})\s+(.+)$")
_CHAPTER_RE = re.compile(r"^\s*(\d)\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ,]+)$")
_PRICE_LINE_RE = re.compile(r"^\s*(\S+)\s+\$\s*([\d,]+\.\d{2})\s*$")
_SKIP_PREFIXES = ("TABULADOR A COSTO", "Y CONSERVACIÓN", "LINEA", "COSTO", "DIRECTO", "PAG.")


def parse_sict_costo_directo_lines(
    lines: Iterable[str], *, page: int = 0
) -> Iterator[dict[str, object]]:
    current: dict[str, object] | None = None
    group_clave = ""
    group_desc = ""

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith(_SKIP_PREFIXES):
            continue
        concept = _CONCEPT_RE.match(line)
        if concept:
            current = {
                "clave": concept.group(2), "description": concept.group(3).strip(),
                "unit": None, "price": None, "group_clave": group_clave,
                "group_description": group_desc, "page": page, "linea": int(concept.group(1)),
            }
            continue
        if current is not None:
            priced = _PRICE_LINE_RE.match(line)
            if priced:
                current["unit"] = priced.group(1)
                current["price"] = money(priced.group(2))
                current["description"] = " ".join(str(current["description"]).split())
                yield current
                current = None
                continue
            current["description"] = f"{current['description']} {line}"
            continue
        group = _GROUP_RE.match(line)
        if group:
            group_clave = group.group(2)
            group_desc = " ".join(group.group(3).split())
            continue
        chapter = _CHAPTER_RE.match(line)
        if chapter:
            group_clave = chapter.group(1)
            group_desc = chapter.group(2).strip()


def parse_sict_costo_directo(path: Path) -> Iterator[dict[str, object]]:
    for page, lines in pdf_pages(path):
        yield from parse_sict_costo_directo_lines(lines, page=page)
