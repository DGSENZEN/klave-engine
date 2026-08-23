"""Paramétricos: a past presupuesto becomes per-m² rules; rules propose lines
for what the plan cannot read, never for what it did read."""

import io

import pytest
from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.catalog_services import import_plantilla
from klave_engine.costing.catalog_store import get_catalog_store
from klave_engine.costing.models import (
    BillOfQuantities,
    CostingAssumptions,
    CostingConfig,
)
from klave_engine.costing.parametrics import ParametricBasis, apply_parametrics, compute_basis
from klave_engine.costing.report import generate_cost_report
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.taxonomy import classify_family
from klave_engine.detection.views import SheetSegmentation, ViewKind, ViewRegion
from klave_engine.dxf.units import DrawingUnits
from openpyxl import Workbook


@pytest.fixture
def store(data_dir):
    return get_catalog_store(data_dir)


def _slab(det_id, area, family="reticular"):
    det = make_detection(
        det_id, DetectionType.slab_region, det_id, (0, 0, 5, 5), 0.9, [], "m", [],
        {"estimated_area": area, "family": family},
    )
    det.family = classify_family(det).value
    return det


def _room(det_id, area, kind, label):
    det = make_detection(
        det_id, DetectionType.room, det_id, (0, 0, 1, 1), 0.85, [], "m", [],
        {"estimated_area": area, "room_kind": kind, "label": label},
    )
    det.family = classify_family(det).value
    return det


def _segmentation():
    return SheetSegmentation(
        views=[
            ViewRegion(view_id="f0", title="ES-000 · CIMENTACIÓN", kind=ViewKind.plan,
                       level_key="cimentacion", anchor=(0, 0)),
            ViewRegion(view_id="f1", title="ES-100 · PLANTA BAJA", kind=ViewKind.plan,
                       level_key="planta_baja", anchor=(0, 0)),
            ViewRegion(view_id="f2", title="ES-200 · PLANTA ALTA", kind=ViewKind.plan,
                       level_key="planta_alta", anchor=(0, 0)),
        ],
        assignment={"s0": "f0", "s1": "f1", "s2": "f2", "r1": "f1", "r2": "f2"},
        is_segmented=True,
    )


def test_basis_reads_built_area_from_superstructure_slabs_and_locales():
    dets = [_slab("s0", 150.0, "cimentacion"), _slab("s1", 120.0), _slab("s2", 95.0),
            _room("r1", 12.0, "interior", "BAÑO PRINCIPAL"), _room("r2", 9.0, "interior", "BAÑO")]
    basis = compute_basis(dets, _segmentation(), 1.0)
    assert basis.area_construida_m2 == 215.0 and basis.plantas == 2
    assert "2 tableros" in basis.area_source
    assert basis.locales["interior"] == 2 and basis.locales["baño"] == 2
    assert basis.value("local:baño") == (2.0, "locales «baño» leídos del plano")
    forced = compute_basis(dets, _segmentation(), 1.0, area_override_m2=300.0)
    assert forced.area_construida_m2 == 300.0 and "Parámetros" in forced.area_source


def test_rules_propose_lines_only_where_the_plan_read_nothing():
    a = CostingAssumptions()
    catalog = build_default_catalog(a)
    apus = build_all_apus(catalog)
    boq = BillOfQuantities(project_id="p")
    # EST-004 already read from the plan: a rule for it must not override it.
    from klave_engine.costing.models import BoqLine, QuantityKind

    boq.lines.append(BoqLine(
        concept_code="EST-004", description="Muros", unit="M2", quantity=200.0, unit_price=500.0,
        amount=100000.0, phase="Estructura", raw_quantity=200.0, raw_kind=QuantityKind.LENGTH,
        source_detection_count=10, confidence=0.9,
    ))
    rules = [
        {"concept_code": "EST-004", "basis": "m2_construida", "factor": 2.0, "source": "Lote 02"},
        {"concept_code": "PIS-001", "basis": "m2_construida", "factor": 0.8, "source": "Lote 02"},
        {"concept_code": "ACA-003", "basis": "local:baño", "factor": 6.0, "source": "regla"},
        {"concept_code": "PRE-001", "basis": "proyecto", "factor": 1.0, "source": "regla"},
        {"concept_code": "NOPE-1", "basis": "m2_construida", "factor": 1.0},
    ]
    basis = ParametricBasis(area_construida_m2=215.0, area_source="tableros", plantas=2,
                            locales={"baño": 2})
    applied = apply_parametrics(boq, catalog, apus, rules, basis)
    assert applied == 3
    lines = {ln.concept_code: ln for ln in boq.lines}
    assert lines["EST-004"].quantity == 200.0 and not lines["EST-004"].parametric
    assert lines["PIS-001"].parametric and lines["PIS-001"].quantity == 172.0
    assert lines["PIS-001"].confidence == 0.5 and "Lote 02" in lines["PIS-001"].assumptions[0]
    assert lines["ACA-003"].quantity == 12.0 and "local baño" in lines["ACA-003"].assumptions[0]
    assert lines["PRE-001"].quantity == 1.0
    assert any("inexistente" in w for w in boq.warnings)


def _xlsx(rows):
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_plantilla_import_maps_rows_and_creates_rules(store):
    raw = _xlsx([
        ["Clave", "Descripción", "Unidad", "Cantidad", "P.U."],
        ["PRELIMINARES", None, None, None, None],
        ["PRE-001", "Trazo y nivelación con equipo topográfico", "M2", 320, 18.5],
        ["INSTALACIONES", None, None, None, None],
        ["INS-ELE-01", "Salida eléctrica para contacto, incluye tubería y cable", "SAL", 48, 950.0],
        ["INS-HID-02", "Salida hidráulica de cobre 13 mm", "SAL", 12, 1480.0],
        ["SIN-PRECIO", "Concepto por cotización", "PZA", 3, None],
    ])
    result = import_plantilla(
        store, raw, "lote02.xlsx", name="Lote 02", tipologia="casa habitación",
        area_m2=320.0, actor="Ana",
    )
    assert result["concepts_created"] == 2 and result["rules"] == 2
    assert result["comparison_rules"] == 1  # PRE-001 is read by the engine
    assert any("SIN-PRECIO" in p for p in result["problems"])
    rules = {r["concept_code"]: r for r in store.list_parametric_rules()}
    assert "PRE-001" not in rules  # comparison-only rules do not propose lines
    assert abs(rules["INS-ELE-01"]["factor"] - 48 / 320) < 1e-9
    assert rules["INS-ELE-01"]["source"].startswith("Lote 02")
    prices = store.load_concept_prices()
    assert prices["INS-ELE-01"]["price"] == 950.0
    # A new project of 215 m² read from its slabs proposes 32.25 salidas.
    dets = [_slab("s1", 120.0), _slab("s2", 95.0)]
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    report = generate_cost_report(
        "p", dets, units, CostingConfig(), _segmentation(), None,
        price_book=store.load_price_book(), apu_templates=store.load_templates(),
        store_concepts=store.load_concepts(), concept_prices=store.load_concept_prices(),
        parametric_rules=store.list_parametric_rules(),
    )
    line = next(ln for ln in report.boq.lines if ln.concept_code == "INS-ELE-01")
    assert line.parametric and abs(line.quantity - 48 / 320 * 215) < 1e-6
    assert line.unit_price == 950.0 and line.phase == "INSTALACIONES"
