"""Indicadores: ratios every senior estimator checks, and the partidas a
plantilla has that this presupuesto lacks."""

from klave_engine.costing.indicadores import compute_indicators, phase_shares_from_rows
from klave_engine.costing.models import BillOfQuantities, BoqLine, QuantityKind
from klave_engine.costing.sources.presupuesto import PresupuestoRow


def _line(code, unit, qty, price, phase):
    return BoqLine(
        concept_code=code, description=code, unit=unit, quantity=qty, unit_price=price,
        amount=round(qty * price, 2), phase=phase, raw_quantity=qty, raw_kind=QuantityKind.COUNT,
        source_detection_count=1, confidence=0.9,
    )


def _boq():
    boq = BillOfQuantities(project_id="p")
    boq.lines = [
        _line("EST-001", "M3", 40.0, 13000.0, "Estructura"),
        _line("EST-002", "M3", 70.0, 11500.0, "Estructura"),
        _line("ACE-001", "KG", 20000.0, 38.0, "Estructura"),
        _line("EST-008", "M2", 600.0, 200.0, "Estructura"),
        _line("CIM-002", "M3", 8.0, 6600.0, "Cimentación"),
    ]
    boq.direct_cost_total = round(sum(ln.amount for ln in boq.lines), 2)
    totals: dict[str, float] = {}
    for ln in boq.lines:
        totals[ln.phase] = round(totals.get(ln.phase, 0.0) + ln.amount, 2)
    boq.totals_by_phase = totals
    return boq


def test_ratios_flag_out_of_range_values_with_reasons():
    out = compute_indicators(_boq(), area_construida_m2=300.0)
    by = {i.key: i for i in out.indicators}
    # 20 000 kg / 118 m³ = 169 kg/m³: above the typical 80–160.
    assert by["acero_por_m3"].status == "alto" and abs(by["acero_por_m3"].value - 20000 / 118) < 0.1
    assert by["cimbra_por_m3"].status == "ok"  # 600 / 118 ≈ 5.1
    assert by["concreto_por_m2"].status == "ok"  # 118 / 300 ≈ 0.39
    assert by["costo_directo_por_m2"].value == round(_boq().direct_cost_total / 300.0, 2)
    assert any("acero" in n and "arriba" in n for n in out.notes)
    without_area = compute_indicators(_boq(), None)
    assert {i.key: i.status for i in without_area.indicators}["concreto_por_m2"] == "sin_dato"


def test_missing_partidas_come_from_the_plantilla_shares():
    rows = [
        PresupuestoRow("PRE-1", "Trazo", "M2", 300, 18.0, "PRELIMINARES"),
        PresupuestoRow("EST-1", "Concreto", "M3", 100, 12000.0, "ESTRUCTURA"),
        PresupuestoRow("INS-1", "Salidas", "SAL", 60, 950.0, "INSTALACIONES"),
        PresupuestoRow("ACB-1", "Pintura", "M2", 900, 90.0, "ACABADOS"),
        PresupuestoRow("SIN", "Por cotización", "PZA", 1, None, "HERRERÍA"),
    ]
    shares = phase_shares_from_rows(rows)
    assert abs(sum(shares.values()) - 100.0) < 0.05 and "HERRERIA" not in shares
    out = compute_indicators(
        _boq(), 300.0, plantillas=[{"name": "Lote 02", "phase_shares": shares}]
    )
    assert out.reference == "plantilla Lote 02"
    assert "Instalaciones" in out.missing_phases and "Acabados" in out.missing_phases
    assert any("Partidas que tu plantilla tiene" in n for n in out.notes)
    estructura = next(s for s in out.phase_shares if s.phase == "Estructura")
    assert estructura.typical_pct is not None and estructura.status in ("ok", "alto")


def test_obra_negra_alone_is_not_called_cheap():
    # 2.2 M over 600 m² = 3,700 $/m²: below the whole-house band, but this
    # presupuesto has no albañilería, acabados nor instalaciones.
    out = compute_indicators(_boq(), area_construida_m2=600.0)
    cost = {i.key: i for i in out.indicators}["costo_directo_por_m2"]
    assert cost.status == "sin_referencia" and "obra negra" in cost.detail
    assert not any("costo directo" in n for n in out.notes)
    # With acabados in the mix the band applies again.
    boq = _boq()
    boq.lines.append(_line("ACA-001", "M2", 1000.0, 400.0, "Acabados"))
    boq.direct_cost_total = round(sum(ln.amount for ln in boq.lines), 2)
    boq.totals_by_phase["Acabados"] = 400000.0
    out = compute_indicators(boq, area_construida_m2=600.0)
    assert {i.key: i for i in out.indicators}["costo_directo_por_m2"].status == "bajo"
