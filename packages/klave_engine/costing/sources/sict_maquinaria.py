"""Parser for the SICT tabulador de costos horarios de maquinaria y equipo.

Each row: ``Serie · Descripción (wrapping) · VA USD · VA MXN · Activo ·
Espera · Reserva`` — acquisition values and the three RLOPSRM hourly costs.
Group headers (``1010 MOTOSIERRAS``) name the family of the rows below.
"""

import re
from collections.abc import Iterable, Iterator
from pathlib import Path

_ROW_RE = re.compile(
    r"^\s*(\d{3,5})\s+(.+?)\s+\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})"
    r"\s+\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s*$"
)
_GROUP_RE = re.compile(r"^\s*(\d{2,4})\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ,/\-\.\(\)0-9]+?)\s*$")
_CONTINUATION_RE = re.compile(r"^\s{10,}(\S.*?)\s*$")


def _money(text: str) -> float:
    return float(text.replace(",", ""))


def parse_sict_lines(lines: Iterable[str], *, page: int = 0) -> Iterator[dict[str, object]]:
    group = ""
    current: dict[str, object] | None = None

    def flush() -> Iterator[dict[str, object]]:
        nonlocal current
        if current is not None:
            current["description"] = " ".join(str(current["description"]).split())
            yield current
            current = None

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        row = _ROW_RE.match(line)
        if row:
            yield from flush()
            current = {
                "clave": row.group(1),
                "description": row.group(2),
                "unit": "hr",
                "price": _money(row.group(5)),  # costo horario activo
                "group_clave": "",
                "group_description": group,
                "page": page,
                "extra": {
                    "va_usd": _money(row.group(3)),
                    "va_mxn": _money(row.group(4)),
                    "activo": _money(row.group(5)),
                    "espera": _money(row.group(6)),
                    "reserva": _money(row.group(7)),
                },
            }
            continue
        header = _GROUP_RE.match(line)
        if header and not line.strip().startswith("TABULADOR"):
            yield from flush()
            group = " ".join(header.group(2).split())
            continue
        cont = _CONTINUATION_RE.match(line)
        if cont and current is not None and not line.strip().startswith(("Valores", "Imagen")):
            current["description"] = f"{current['description']} {cont.group(1)}"
    yield from flush()


def parse_sict_maquinaria(path: Path) -> Iterator[dict[str, object]]:
    import pdfplumber

    with pdfplumber.open(str(path)) as pdf:
        for index, page in enumerate(pdf.pages):
            text = page.extract_text(layout=True) or ""
            yield from parse_sict_lines(text.splitlines(), page=index + 1)
