"""OPUS/Neodata 'conceptos con insumos' Excel exports become concepts with
their matrices; what cannot be priced is reported, not imported."""

import io

import pytest
from klave_engine.costing.sources.custom import CustomCatalogError
from klave_engine.costing.sources.matrices import parse_matrices_table, parse_matrices_workbook
from openpyxl import Workbook

OPUS_STYLE = [
    ["Clave", "Descripción", "Unidad", "Cantidad", "Costo", "Rendimiento", "Partida"],
    ["", "ALBAÑILERÍA", "", "", "", "", ""],
    ["ALB-010", "Muro de block 15x20x40 asentado con mortero 1:4", "M2", "", "", 12.5, ""],
    ["MAT-BLOCK15", "Block de concreto 15x20x40", "PZA", 12.5, 14.2, "", ""],
    ["MAT-MORT14", "Mortero cemento-arena 1:4", "M3", 0.021, 2150.0, "", ""],
    ["MO-OF-ALB", "Oficial albañil", "JOR", 0.16, 690.0, "", ""],
    ["MO-AYUD", "Ayudante", "JOR", 0.16, 420.0, "", ""],
    ["HERR", "Herramienta menor", "%", 3.0, "", "", ""],
    ["ALB-020", "Aplanado fino en muros", "M2", "", "", 18.0, ""],
    ["MAT-MORT14", "Mortero cemento-arena 1:4", "M3", 0.024, 2150.0, "", ""],
    ["MO-OF-ALB", "Oficial albañil", "JOR", 0.09, 690.0, "", ""],
    ["ALB-030", "Concepto por cotización", "M2", "", "", "", ""],
    ["MAT-X", "Insumo sin costo", "PZA", 1.0, 0, "", ""],
]


def test_opus_style_layout_groups_insumos_under_their_concept():
    parse = parse_matrices_table(OPUS_STYLE)
    codes = [c.code for c in parse.concepts]
    assert codes == ["ALB-010", "ALB-020"]
    muro = parse.concepts[0]
    assert muro.unit == "M2" and muro.phase == "ALBAÑILERÍA"
    assert muro.production_rate_per_day == 12.5
    assert muro.components == [
        ("MAT-BLOCK15", 12.5), ("MAT-MORT14", 0.021), ("MO-OF-ALB", 0.16), ("MO-AYUD", 0.16),
        ("HERR", 3.0),
    ]
    assert parse.insumos["MO-OF-ALB"].resource_type == "mano_de_obra"
    assert parse.insumos["MAT-BLOCK15"].resource_type == "material"
    herr = parse.insumos["HERR"]
    assert herr.is_labor_percentage and herr.resource_type == "equipo"
    # ALB-030's only insumo has no cost: concept dropped, and the parse says why.
    assert any("ALB-030" in p for p in parse.problems)
    assert any("MAT-X" in p and "por cotización" in p for p in parse.problems)


def test_tipo_column_layout_and_neodata_headers():
    table = [
        ["Tipo", "Código", "Concepto", "U", "Cant.", "P.U.", "Rend."],
        ["CONCEPTO", "EST-900", "Trabe de concreto", "M3", "", "", 4.0],
        ["INSUMO", "MAT-CONC250", "Concreto f'c=250", "M3", 1.05, "2,450.00", ""],
        ["INSUMO", "MO-CUAD-FIE", "Cuadrilla fierrero", "JOR", 0.35, 1850, ""],
    ]
    parse = parse_matrices_table(table)
    assert [c.code for c in parse.concepts] == ["EST-900"]
    assert parse.concepts[0].components == [("MAT-CONC250", 1.05), ("MO-CUAD-FIE", 0.35)]
    assert parse.insumos["MAT-CONC250"].unit_cost == 2450.0
    assert parse.problems == []


def test_workbook_without_the_layout_is_rejected():
    wb = Workbook()
    ws = wb.active
    ws.append(["Clave", "Descripción", "Precio"])
    ws.append(["X", "Y", 1])
    buffer = io.BytesIO()
    wb.save(buffer)
    with pytest.raises(CustomCatalogError):
        parse_matrices_workbook(buffer.getvalue(), "x.xlsx")


def test_xlsx_roundtrip():
    wb = Workbook()
    ws = wb.active
    for row in OPUS_STYLE:
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    parse = parse_matrices_workbook(buffer.getvalue(), "catalogo.xlsx")
    assert [c.code for c in parse.concepts] == ["ALB-010", "ALB-020"]
