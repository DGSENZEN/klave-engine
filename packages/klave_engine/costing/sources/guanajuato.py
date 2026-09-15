"""La Unidad Estatal de Costos de Guanajuato publica tres cosas que ningún
otro gobierno junta: el Tabulador de Referencia en Excel por región (seis
regiones, ~3,400 conceptos cada una), un listado de precios de mercado de
materiales por región, y un listado de costos horarios de maquinaria.

Tabulador: una hoja con «Código | Concepto | Unidad | Cantidad | Costo»;
las filas de jerarquía llevan código corto (ED, 10, 100) y sin unidad;
los conceptos son ``UEC.ED.10.100.1010``. Seis archivos → una sola fuente:
el precio del renglón es el de la región I y las demás viajan en
``extra["regiones"]``; una clave que sólo exista en otra región entra con
esa región como precio.

Listados (PDF con tabla): materiales «Familia | Descripción | Presentación
| Unidad | REGIÓN 1…6» (celdas vacías = esa región no lo publica);
maquinaria «Descripción | Motor | Potencia | Operación | Costo horario».
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from klave_engine.costing.sources.pdftext import money, pdf_tables

_CONCEPT_CODE_RE = re.compile(r"^UEC\.[A-Z]{2}\.\d+\.\d+\.\d+$")
_REGION_SUFFIX_RE = re.compile(r"_R(I|II|III|IV|V|VI)\.xlsx$", re.I)
_ROMAN = ["I", "II", "III", "IV", "V", "VI"]


def _cell(value: object) -> str:
    return "" if value is None else str(value).strip()


def parse_guanajuato_sheet(rows: list[list[object]], *, region: str) -> Iterator[dict]:
    """Los conceptos de una hoja regional con su capítulo y subcapítulo."""
    capitulo = ""
    subcapitulo_clave = ""
    subcapitulo = ""
    for row in rows:
        cells = [_cell(v) for v in list(row) + [""] * 5][:5]
        code, concept, unit, _cantidad, cost = cells
        if not code or code.lower() == "código":
            continue
        if _CONCEPT_CODE_RE.match(code):
            price = money(cost) if cost else None
            if price is None:
                try:
                    price = float(cost)
                except ValueError:
                    price = None
            yield {
                "clave": code, "description": " ".join(concept.split()), "unit": unit,
                "price": price, "group_clave": subcapitulo_clave,
                "group_description": f"{capitulo} · {subcapitulo}".strip(" ·"),
                "region": region,
            }
            continue
        # Jerarquía: dos dígitos = capítulo, tres = subcapítulo; letras = nivel superior.
        if code.isdigit() and len(code) == 2:
            capitulo = " ".join(concept.split())
            subcapitulo_clave, subcapitulo = "", ""
        elif code.isdigit() and len(code) == 3:
            subcapitulo_clave = code
            subcapitulo = " ".join(concept.split())


def _sibling_files(first: Path) -> list[tuple[str, Path]]:
    """Los seis archivos regionales a partir del de la región I."""
    stem = _REGION_SUFFIX_RE.sub("", first.name)
    found = []
    for roman in _ROMAN:
        candidate = first.with_name(f"{stem}_R{roman}.xlsx")
        if candidate.exists():
            found.append((roman, candidate))
    return found or [("I", first)]


def parse_guanajuato_tabulador(path: Path) -> Iterator[dict[str, object]]:
    from openpyxl import load_workbook

    merged: dict[str, dict] = {}
    order: list[str] = []
    for roman, file in _sibling_files(path):
        workbook = load_workbook(str(file), read_only=True, data_only=True)
        try:
            sheet = workbook.worksheets[0]
            rows = list(sheet.iter_rows(values_only=True))
            for row in parse_guanajuato_sheet(rows, region=roman):
                if row["price"] is None:
                    continue
                record = merged.get(row["clave"])
                if record is None:
                    record = {
                        "clave": row["clave"], "description": row["description"],
                        "unit": row["unit"], "price": row["price"],
                        "group_clave": row["group_clave"],
                        "group_description": row["group_description"],
                        "extra": {"regiones": {}}, "page": None,
                    }
                    merged[row["clave"]] = record
                    order.append(row["clave"])
                record["extra"]["regiones"][roman] = row["price"]
                if roman == "I":
                    record["price"] = row["price"]
        finally:
            workbook.close()
    for clave in order:
        yield merged[clave]


# ------------------------------------------------------------- los listados

def parse_guanajuato_materiales_table(table: list[list[str]]) -> Iterator[dict[str, object]]:
    header_seen = False
    familia = ""
    for row in table:
        cells = [(c or "").replace("\n", " ").strip() for c in row]
        if not header_seen:
            if any(c.lower().startswith("descripci") for c in cells):
                header_seen = True
            continue
        if len(cells) < 5 or not cells[1] or cells[1].lower().startswith("precio"):
            if cells and cells[0]:
                familia = cells[0]
            continue
        if cells[0]:
            familia = cells[0]
        description, presentacion, unit = cells[1], cells[2], cells[3]
        regiones = {
            str(index + 1): money(value)
            for index, value in enumerate(cells[4:10]) if value and money(value) is not None
        }
        if not regiones or not unit:
            continue
        first = next(iter(regiones.values()))
        yield {
            "clave": f"GTO-MAT-{_slug(description)}",
            "description": " ".join(description.split()),
            "unit": unit, "price": first, "group_clave": _slug(familia)[:20] if familia else "",
            "group_description": familia or "Materiales",
            "extra": {"regiones": regiones, "presentacion": presentacion},
        }


def parse_guanajuato_maquinaria_table(table: list[list[str]]) -> Iterator[dict[str, object]]:
    for row in table:
        cells = [(c or "").replace("\n", " ").strip() for c in row]
        if len(cells) < 6 or cells[0].lower().startswith("descripci"):
            continue
        description = cells[1] or cells[0]
        cost = money(cells[5])
        if not description or cost is None:
            continue
        yield {
            "clave": f"GTO-EQ-{_slug(description)}",
            "description": " ".join(description.split()),
            "unit": "HORA", "price": cost, "group_clave": "", "group_description": "Maquinaria",
            "extra": {"motor": cells[2], "potencia_hp": cells[3], "operacion": cells[4]},
        }


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", text.upper()).strip("-")
    return cleaned[:40]


def parse_guanajuato_materiales(path: Path) -> Iterator[dict[str, object]]:
    for page, table in pdf_tables(path):
        for row in parse_guanajuato_materiales_table(table):
            row["page"] = page
            yield row


def parse_guanajuato_maquinaria(path: Path) -> Iterator[dict[str, object]]:
    for page, table in pdf_tables(path):
        for row in parse_guanajuato_maquinaria_table(table):
            row["page"] = page
            yield row
