"""El Catálogo General de Precios Unitarios de la CONAGUA (agua potable y
alcantarillado).

Renglón: «NNNN NN concepto UNIDAD $ precio». «NNNN 00 descripción» abre un
grupo (el suministro, la instalación) y los renglones que siguen se leen
bajo él; las líneas sin clave entre renglones son contexto del grupo
(«INSTALACIÓN DE PIEZAS ESPECIALES DE FIERRO GALVANIZADO…»). Los importes
vienen con espacios sueltos («1 ,006.84») y se limpian.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from pathlib import Path

from klave_engine.costing.sources.pdftext import money, pdf_pages

_CODE_RE = re.compile(r"^\s*(\d{1,2}\s?\d{3})[ .](\d{2})\b\s*(.*)$")
_TAIL_RE = re.compile(
    r"^(.*?)\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9./]*)\s+\$\s*([\d\s,]+\.\d{2})(?:\s+\d{1,3})?\s*$"
)
_SKIP_RE = re.compile(
    r"^(CLAVE\b|C O N C E P T O|Enero|Página|Avenida|www\.gob\.mx|Subdirección|Gerencia|\d{1,3}$)",
    re.I,
)


def _clave(base: str, suffix: str) -> str:
    return f"{base.replace(' ', '')}-{suffix}"


def parse_conagua_lines(lines: Iterable[str], *, page: int = 0) -> Iterator[dict[str, object]]:
    """Un renglón puede cerrar en su línea («… UNIDAD $ precio») o partirse:
    la clave y el arranque en una línea, el resto y el precio en la
    siguiente. La clave «NNNN 00» abre grupo; las líneas sin clave entre
    renglones son contexto que se lee bajo el grupo."""
    group_clave = ""
    group_desc = ""
    pending: dict[str, object] | None = None
    pending_is_group = False
    context: list[str] = []

    def close(row: dict[str, object], tail: re.Match[str], *, prefix: str) -> dict[str, object]:
        text = f"{prefix} {tail.group(1)}".strip()
        row["description"] = " ".join(text.split())
        row["unit"] = tail.group(2).rstrip(".")
        row["price"] = money(tail.group(3))
        return row

    for raw in lines:
        line = raw.strip()
        if not line or _SKIP_RE.match(line):
            continue
        code = _CODE_RE.match(line)
        if code:
            base, suffix, rest = code.groups()
            if pending is not None and pending_is_group:
                group_desc = " ".join(str(pending["description"]).split())
            pending, pending_is_group = None, False
            if suffix == "00":
                group_clave = base.replace(" ", "")
                pending = {"description": rest}
                pending_is_group = True
                context = []
                continue
            if context:
                group_desc = " ".join(" ".join(context).split())
                context = []
            row: dict[str, object] = {
                "clave": _clave(base, suffix), "description": rest, "unit": None, "price": None,
                "group_clave": group_clave if base.replace(" ", "") == group_clave else "",
                "group_description": group_desc, "page": page,
            }
            tail = _TAIL_RE.match(rest)
            if tail:
                yield close(row, tail, prefix="")
            else:
                pending = row
            continue
        if pending is not None and not pending_is_group:
            tail = _TAIL_RE.match(line)
            if tail:
                yield close(pending, tail, prefix=str(pending["description"]))
                pending = None
            else:
                pending["description"] = f"{pending['description']} {line}"
            continue
        if pending is not None and pending_is_group:
            pending["description"] = f"{pending['description']} {line}"
            group_desc = " ".join(str(pending["description"]).split())
            continue
        context.append(line)


def parse_conagua(path: Path) -> Iterator[dict[str, object]]:
    for page, lines in pdf_pages(path):
        yield from parse_conagua_lines(lines, page=page)
