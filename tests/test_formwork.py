"""Cimbra from counted elements; declared f'c checked against priced f'c."""

import pytest
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.cimentacion import apply_cimentacion_earthmoving
from klave_engine.costing.formwork import (
    FormworkLine,
    FormworkReport,
    apply_formwork,
    compute_formwork,
)
from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    CostingAssumptions,
    QuantityKind,
)
from klave_engine.detection.dimensions import DimensionInventory
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.schedules import parse_concrete_fc


def _line(code, quantity, raw, ids, unit="M3", description=""):
    return BoqLine(
        concept_code=code, description=description or code, unit=unit, quantity=quantity,
        unit_price=1.0, amount=quantity, phase="Estructura", raw_quantity=raw,
        raw_kind=QuantityKind.COUNT, source_detection_count=len(ids),
        source_detections=ids, confidence=0.9,
    )


def test_declared_fc_by_family():
    texts = [
        "RESISTENCIA EN CASTILLOS SOLIDOS________ F'C=200Kg/Cm² _____T.MA 3/4\"",
        "RESISTENCIA EN CIMENTACION_____________F'C=250Kg/Cm²",
        "RESISTENCIA EN LOSAS DE AZOTEA Y TRABES__F'C=250Kg/Cm²",
        "FIRME DE CONCRETO F'C=150 KG/CM²",
        "f'c = 200 kg/cm2",  # no family: ignored
    ]
    fc = parse_concrete_fc(texts)
    assert fc == {"castillo": 200, "cimentacion": 250, "losa": 250, "trabe": 250, "firme": 150}


def test_formwork_areas_and_fc_mismatch_warning():
    k = make_detection(
        "c1", DetectionType.column_tag, "K-1", (0, 0, 1, 1), 0.9, [], "m", [],
        {"section_cm": "15x20"},
    )
    t = make_detection(
        "b1", DetectionType.beam_tag, "T-1", (0, 0, 1, 1), 0.9, [], "m", [],
        {"estimated_span_length": 4.0},
    )
    z = make_detection(
        "f1", DetectionType.footing, "F1", (0, 0, 1, 1), 0.9, [], "m", [],
        {"dimensioned_width": 1.0, "dimensioned_length": 2.0},
    )
    boq = BillOfQuantities(
        project_id="p",
        lines=[
            _line("EST-001", 0.1, 1, ["c1"], description="Columnas f'c=250 kg/cm²"),
            _line("EST-002", 0.4, 4.0, ["b1"]),
            _line("EST-004", 27.0, 10.0, [], unit="M2"),
            _line("CIM-002", 1.0, 2.0, ["f1"]),
            _line("EST-003", 50.0, 50.0, [], unit="M2"),
        ],
    )
    specs = {"by_family": {"dala": {"section_cm": [15, 30]}}, "concrete_fc": {"castillo": 200}}
    assumptions = CostingAssumptions(column_height_m=3.0, footing_depth_m=0.35)
    report = compute_formwork(
        boq, [k, t, z], specs, DimensionInventory(vigueta_system="12-5"), assumptions, 1.0, None
    )
    areas = {line.concept_code: line.quantity for line in report.lines}
    assert areas["EST-008"] == pytest.approx(2 * (0.15 + 0.20) * 3.0)
    beam_h = assumptions.beam_section_m2 / 0.25
    assert areas["EST-009"] == pytest.approx((0.25 + 2 * beam_h) * 4.0)
    assert areas["EST-010"] == pytest.approx(2 * 0.30 * 10.0)
    assert areas["CIM-006"] == pytest.approx(2 * (1.0 + 2.0) * 0.35)
    assert "EST-011" not in areas  # vigueta y bovedilla: no contact formwork
    assert any("sin cimbra de contacto" in w for w in report.warnings)
    assert any("f'c=200" in w and "EST-001" in w for w in report.warnings)
    assert any("Ajusta el concepto" in n for n in boq.lines[0].assumptions)

    maciza = compute_formwork(boq, [k, t, z], specs, DimensionInventory(), assumptions, 1.0, None)
    assert next(line for line in maciza.lines if line.concept_code == "EST-011").quantity == 50.0


def test_plantilla_sin_matriz_sale_sin_precio():
    # A9: la línea sin precio queda visible y lo dice — nunca se descarta.
    a = CostingAssumptions()
    catalog = build_default_catalog(a)
    boq = BillOfQuantities(project_id="p", lines=[])
    report = FormworkReport(
        lines=[FormworkLine(concept_code="CIM-003", quantity=12.03,
                            source_detections=["f1"], notes=["área en planta"])]
    )
    added = apply_formwork(boq, catalog, apus={}, formwork=report)
    assert added == 1
    line = next(l for l in boq.lines if l.concept_code == "CIM-003")
    assert line.unpriced is True
    assert line.unit_price == 0.0 and line.amount == 0.0
    assert line.quantity == 12.03


def test_relleno_resta_la_plantilla_aunque_no_tenga_precio():
    # CIM-004 = excavación − enterrado; la plantilla enterrada (área × 0.05 m)
    # debe restarse aun cuando la línea de plantilla salga sin precio.
    a = CostingAssumptions()
    catalog = build_default_catalog(a)
    boq = BillOfQuantities(
        project_id="p",
        lines=[_line("CIM-001", 10.0, 10.0, ["e1"], description="Excavación")],
    )
    report = FormworkReport(
        lines=[FormworkLine(concept_code="CIM-003", quantity=12.0,
                            source_detections=["f1"], notes=[])]
    )
    apply_formwork(boq, catalog, apus={}, formwork=report)
    apply_cimentacion_earthmoving(boq, catalog, apus={}, assumptions=a)
    fill = next(l for l in boq.lines if l.concept_code == "CIM-004")
    # 10.0 excavados − 12.0 m² × 0.05 m de plantilla = 9.4 m³
    assert fill.quantity == 9.4
