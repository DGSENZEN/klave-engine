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
