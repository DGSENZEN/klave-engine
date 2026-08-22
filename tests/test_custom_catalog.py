"""A taller's own catálogo (XLSX/CSV) becomes a reference source with groups."""

import io

import pytest
from klave_engine.costing.sources.custom import (
    CustomCatalogError,
    parse_concept_workbook,
    source_key_for,
)
from openpyxl import Workbook


def _xlsx(rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_workbook_with_title_block_groups_and_por_cotizacion():
    raw = _xlsx(
        [
            ["SISTEMA INTEGRAL DE CONTROL", None, None, None, None],
            [None, None, None, None, None],
            ["Clave", "Descripción Técnica del Concepto", "Unidad", "Cantidad", "P.U."],
            ["PRELIMINARES", None, None, None, None],
            ["PRE-001", "Trazo y nivelación manual", "m2", 1, "$15.81"],
            ["PRE-002", "Ducto 60 cm", "M", 1, 455.67],
            ["ESTRUCTURA", None, None, None, None],
            ["EST-010", "Losa maciza 10 cm", "M²", 1, 1250.5],
            ["EST-011", "Por cotización", "M3", 1, 0],
        ]
    )
    rows = parse_concept_workbook(raw, "catalogo.xlsx")
    assert [r["clave"] for r in rows] == ["PRE-001", "PRE-002", "EST-010"]
    assert rows[0]["price"] == 15.81 and rows[0]["unit"] == "M2"
    assert rows[0]["group_description"] == "PRELIMINARES"
    assert rows[2]["group_description"] == "ESTRUCTURA" and rows[2]["unit"] == "M2"


def test_csv_decimal_comma_and_key():
    header = b"codigo;concepto;unidad;precio unitario\n"
    rows = parse_concept_workbook(header + b"A-1;Muro de block;m2;412,50\n", "c.csv")
    assert rows[0]["price"] == 412.5  # decimal comma
    rows = parse_concept_workbook(header + b"A-2;Trabe;m3;1,250.75\n", "c.csv")
    assert rows[0]["price"] == 1250.75  # thousands comma
    assert (
        source_key_for("Catálogo Vivienda KLAV3 (corregido)")
        == "propio-catalogo-vivienda-klav3-corregido"
    )


def test_no_header_is_an_error():
    with pytest.raises(CustomCatalogError):
        parse_concept_workbook(_xlsx([["a", "b"], [1, 2]]), "x.xlsx")
