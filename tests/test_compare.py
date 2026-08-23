"""Engine vs human presupuesto: matched by clave, deltas shown, nothing hidden."""

import io
import json

from klave_engine.evals.compare import (
    compare,
    load_engine_lines,
    read_human_presupuesto,
    render_markdown,
)
from openpyxl import Workbook


def _engine(tmp_path):
    report = {"boq": {"lines": [
        {"concept_code": "EST-001", "description": "Castillos", "unit": "M3", "quantity": 41.06},
        {"concept_code": "EST-004", "description": "Muros", "unit": "M2", "quantity": 295.6},
        {"concept_code": "ACE-001", "description": "Acero", "unit": "KG", "quantity": 20898.0},
    ]}}
    path = tmp_path / "cost_report.json"
    path.write_text(json.dumps(report))
    return path


def test_compare_matches_by_clave_and_lists_the_unmatched(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["PRESUPUESTO LOTE 04", None, None, None])
    ws.append(["Clave", "Concepto", "Unidad", "Cantidad"])  # no price column: a generador
    ws.append(["EST-001", "Castillos K", "m3", 38.5])
    ws.append(["EST-004", "Muros de block", "m2", "310.00"])
    ws.append(["ALB-050", "Aplanado", "m2", 600])
    buffer = io.BytesIO()
    wb.save(buffer)
    human_path = tmp_path / "humano.xlsx"
    human_path.write_bytes(buffer.getvalue())
    human = read_human_presupuesto(human_path)
    assert [h.clave for h in human] == ["EST-001", "EST-004", "ALB-050"]
    rows = compare(load_engine_lines(_engine(tmp_path)), human)
    by = {r.clave: r for r in rows}
    assert abs(by["EST-001"].delta_pct - (41.06 - 38.5) / 38.5 * 100) < 1e-6
    assert by["ALB-050"].engine is None and by["ACE-001"].human is None
    text = render_markdown(rows)
    assert "solo humano" in text and "solo motor" in text
    assert "Conceptos comparados: 2" in text and "Mediana |Δ|" in text


def test_csv_with_price_column_also_reads(tmp_path):
    human_path = tmp_path / "humano.csv"
    human_path.write_text("clave;descripción;unidad;cantidad;p.u.\nEST-001;Castillos;m3;40,5;13386.19\n")
    human = read_human_presupuesto(human_path)
    assert human[0].clave == "EST-001" and human[0].quantity == 40.5


def test_compare_pairs_by_alias_description_and_flags_units():
    from klave_engine.evals.compare import HumanLine, compare, render_markdown

    engine = [
        {"concept_code": "EST-004", "taller_clave": "1-ALB-MUR-004",
         "description": "Muros de block/concreto, incluye refuerzo y mortero", "unit": "M2",
         "quantity": 420.0, "amount": 147000.0},
        {"concept_code": "ACE-001",
         "description": "Acero de refuerzo fy=4200 en castillos y columnas, habilitado",
         "unit": "KG", "quantity": 5300.0, "amount": 201400.0},
        {"concept_code": "CIM-002", "description": "Concreto f'c=250 en zapatas y dados",
         "unit": "M3", "quantity": 7.5, "amount": 27000.0},
    ]
    human = [
        # The taller's own clave: matched through the alias the engine prints.
        HumanLine("1-ALB-MUR-004", "MURO DE BLOCK 15 CM", "m²", 400.0, amount=140000.0),
        # No shared clave; the matcher pairs it by description and unit.
        HumanLine("ACERO-01", "Acero de refuerzo fy=4200 kg/cm2 habilitado en castillos",
                  "kg", 5500.0, amount=209000.0),
        # Same clave but another unit: flagged, never a quantity delta.
        HumanLine("CIM-002", "Concreto en zapatas", "M2", 7.5),
        HumanLine("INST-99", "Salidas eléctricas", "SAL", 40.0),
    ]
    rows = compare(engine, human)
    by = {r.clave: r for r in rows}
    assert by["1-ALB-MUR-004"].matched_by == "clave" and by["1-ALB-MUR-004"].engine == 420.0
    assert by["ACERO-01"].matched_by.startswith("descripción") and by["ACERO-01"].engine == 5300.0
    assert by["CIM-002"].unit_mismatch == "M3" and by["CIM-002"].delta_pct is None
    assert by["INST-99"].engine is None  # only the human has it
    report = render_markdown(rows)
    assert "unidad distinta (M3 vs M2)" in report
    assert "descripción" in report and "solo humano" in report
    assert "Importe (líneas con monto)" in report
