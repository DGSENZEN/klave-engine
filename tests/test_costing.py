"""Costing engine tests: BoQ quantity rules, price integration, schedule, finance."""

import pytest
from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.insumos import apply_price_overrides, default_price_book
from klave_engine.costing.integration import integrate_costs
from klave_engine.costing.models import (
    CostingAssumptions,
    CostingConfig,
    CostingOverrides,
    IndirectsConfig,
    ResourceType,
)
from klave_engine.costing.recompute import build_cost_report, load_costing_inputs
from klave_engine.costing.report import generate_cost_report
from klave_engine.costing.schedule import direct_spend_by_period
from klave_engine.detection.results import Detection, DetectionType
from klave_engine.detection.views import SheetSegmentation, ViewKind, ViewRegion
from klave_engine.dxf.units import DrawingUnits
from klave_engine.graph.evidence import EvidencePacket


def _detection(
    index: int, detection_type: DetectionType, confidence: float = 0.9, **properties
) -> Detection:
    return Detection(
        detection_id=f"det_{index:06d}",
        detection_type=detection_type,
        label=f"X{index}",
        bbox=(0.0, 0.0, 1.0, 1.0),
        confidence=confidence,
        evidence=EvidencePacket(source="x.dxf", method="test"),
        properties=properties,
    )


@pytest.fixture
def sample_detections() -> list[Detection]:
    detections = [
        _detection(i, DetectionType.column_tag) for i in range(10)
    ]
    detections += [
        _detection(20 + i, DetectionType.footing, estimated_area=2.0) for i in range(4)
    ]
    detections.append(
        _detection(30, DetectionType.beam_tag, estimated_span_length=50.0)
    )
    detections.append(_detection(31, DetectionType.slab_region, estimated_area=100.0))
    detections.append(_detection(32, DetectionType.wall, estimated_length=20.0))
    return detections


METERS = DrawingUnits(unit="m", source="dxf_header", confidence=0.9)


def test_boq_quantity_rules(sample_detections) -> None:
    report = generate_cost_report("p1", sample_detections, METERS, CostingConfig())
    by_code = {line.concept_code: line for line in report.boq.lines}
    a = CostingAssumptions()
    # 10 columns x section x height
    assert by_code["EST-001"].quantity == pytest.approx(
        10 * a.column_section_m2 * a.column_height_m
    )
    # 4 footings x 2 m² x depth
    assert by_code["CIM-002"].quantity == pytest.approx(8.0 * a.footing_depth_m)
    # excavation includes swell
    assert by_code["CIM-001"].quantity == pytest.approx(
        8.0 * a.excavation_depth_m * a.excavation_swell_factor
    )
    # 50 m of beam x section
    assert by_code["EST-002"].quantity == pytest.approx(50.0 * a.beam_section_m2)
    assert by_code["EST-003"].quantity == pytest.approx(100.0)
    assert by_code["EST-004"].quantity == pytest.approx(20.0 * a.wall_height_m)
    for line in report.boq.lines:
        assert line.amount == pytest.approx(line.quantity * line.unit_price, rel=1e-6)
        assert line.source_detection_count > 0


def test_boq_scales_with_millimeter_units(sample_detections) -> None:
    mm = DrawingUnits(unit="mm", source="dxf_header", confidence=0.9)
    report_m = generate_cost_report("p1", sample_detections, METERS, CostingConfig())
    report_mm = generate_cost_report("p1", sample_detections, mm, CostingConfig())
    beam_m = next(x for x in report_m.boq.lines if x.concept_code == "EST-002")
    beam_mm = next(x for x in report_mm.boq.lines if x.concept_code == "EST-002")
    assert beam_mm.quantity == pytest.approx(beam_m.quantity / 1000.0)


def test_unknown_units_warn_but_proceed(sample_detections) -> None:
    unknown = DrawingUnits()
    report = generate_cost_report("p1", sample_detections, unknown, CostingConfig())
    assert any("desconocidas" in w for w in report.warnings)
    assert report.boq.direct_cost_total > 0


def test_apus_have_breakdown_and_positive_prices() -> None:
    catalog = build_default_catalog(CostingAssumptions())
    apus = build_all_apus(catalog)
    assert set(apus) == {c.code for c in catalog}
    for apu in apus.values():
        assert apu.direct_unit_cost > 0
        assert apu.direct_unit_cost == pytest.approx(
            sum(line.amount for line in apu.lines), abs=0.05
        )
        labor = sum(
            x.amount for x in apu.lines if x.resource_type == ResourceType.labor
        )
        tool = next(x for x in apu.lines if x.resource_code == "EQ-HERRAMIENTA")
        assert tool.amount == pytest.approx(0.03 * labor, abs=0.05)


def test_cost_integration_sequence() -> None:
    config = IndirectsConfig()  # 8+5, 1.5, 10, 0.5, 5
    integration = integrate_costs(100_000.0, config)
    ci = 100_000 * 0.13
    fi = (100_000 + ci) * 0.015
    ut = (100_000 + ci + fi) * 0.10
    ca = (100_000 + ci + fi + ut) * 0.005
    sale = 100_000 + ci + fi + ut + ca
    assert integration.sale_price == pytest.approx(sale, abs=0.5)
    assert integration.contingency == pytest.approx(sale * 0.05, abs=0.5)
    assert integration.grand_total == pytest.approx(sale * 1.05, abs=1.0)
    assert integration.overcost_factor == pytest.approx(sale / 100_000, abs=1e-3)


def test_schedule_durations_and_phases(sample_detections) -> None:
    report = generate_cost_report("p1", sample_detections, METERS, CostingConfig())
    schedule = report.schedule
    assert schedule.phases == ["Preliminares", "Cimentación", "Estructura"]
    by_code = {a.concept_code: a for a in schedule.activities}
    for activity in schedule.activities:
        assert activity.duration_days >= 1
        assert activity.end_day == activity.start_day + activity.duration_days
    # later phases start after earlier ones (with overlap, but ordered)
    assert by_code["CIM-001"].start_day >= by_code["PRE-001"].start_day
    assert by_code["EST-001"].start_day > by_code["CIM-001"].start_day
    assert schedule.total_duration_days >= max(a.duration_days for a in schedule.activities)


def test_spend_periods_sum_to_direct_cost(sample_detections) -> None:
    report = generate_cost_report("p1", sample_detections, METERS, CostingConfig())
    spends = direct_spend_by_period(report.schedule)
    assert sum(spends) == pytest.approx(report.boq.direct_cost_total, rel=1e-3)


def test_financial_plan_consistency(sample_detections) -> None:
    report = generate_cost_report("p1", sample_detections, METERS, CostingConfig())
    plan = report.financial
    integration = report.integration
    total_billing = sum(p.billing for p in plan.periods)
    assert total_billing == pytest.approx(integration.sale_price, rel=1e-2)
    total_amortization = sum(p.advance_amortization for p in plan.periods)
    assert total_amortization == pytest.approx(plan.advance_payment, rel=1e-2)
    assert plan.periods[-1].progress_pct == pytest.approx(100.0, abs=1.5)
    # operating projection accumulates
    proj = plan.operating_projection
    assert len(proj) == 5
    assert proj[-1].accumulated == pytest.approx(
        sum(year.total for year in proj), abs=0.5
    )


def test_full_report_artifacts(sample_detections, tmp_path) -> None:
    from klave_engine.costing.report import boq_to_csv, cost_report_to_markdown

    report = generate_cost_report("p1", sample_detections, METERS, CostingConfig())
    markdown = cost_report_to_markdown(report)
    assert "Resumen Ejecutivo de Costos" in markdown
    assert "Precio de venta" in markdown
    path = boq_to_csv(report, tmp_path / "presupuesto.csv")
    content = path.read_text(encoding="utf-8")
    assert "COSTO DIRECTO TOTAL" in content
    assert "PRECIO DE VENTA" in content


# --- view-aware (segmented) costing -------------------------------------------


def _plan(view_id, level_key, npt, det_ids):
    return ViewRegion(
        view_id=view_id, title=view_id, kind=ViewKind.plan, level_key=level_key,
        npt_level=npt, anchor=(0.0, 0.0), detection_ids=det_ids,
    )


def test_segmented_columns_dedup_max_plan_and_npt_height() -> None:
    # Same 5 columns drawn in two plans (10 detections) → count once = 5,
    # height from NPT (top 6.0 m), not 2× or the assumed 3.0 m.
    cols_cim = [_detection(i, DetectionType.column_tag) for i in range(5)]
    cols_pb = [_detection(10 + i, DetectionType.column_tag) for i in range(5)]
    dets = cols_cim + cols_pb
    seg = SheetSegmentation(
        views=[
            _plan("v_cim", "cimentacion", 0.0, [d.detection_id for d in cols_cim]),
            _plan("v_pb", "planta_baja", 6.0, [d.detection_id for d in cols_pb]),
        ],
        assignment={d.detection_id: ("v_cim" if d in cols_cim else "v_pb") for d in dets},
        is_segmented=True,
        npt_levels=[0.0, 6.0],
    )
    report = generate_cost_report("p", dets, METERS, CostingConfig(), seg)
    est1 = next(line for line in report.boq.lines if line.concept_code == "EST-001")
    a = CostingAssumptions()
    assert est1.raw_quantity == 5.0  # max over plans, not 10
    assert est1.quantity == pytest.approx(5 * a.column_section_m2 * 6.0)  # NPT height


def test_segmented_footings_foundation_only() -> None:
    found = [_detection(i, DetectionType.footing, estimated_area=2.0) for i in range(3)]
    roof = [_detection(20 + i, DetectionType.footing, estimated_area=9.9) for i in range(8)]
    dets = found + roof
    seg = SheetSegmentation(
        views=[
            _plan("v_cim", "cimentacion", 0.0, [d.detection_id for d in found]),
            _plan("v_azo", "azotea", 6.0, [d.detection_id for d in roof]),
        ],
        assignment={d.detection_id: ("v_cim" if d in found else "v_azo") for d in dets},
        is_segmented=True,
        npt_levels=[0.0, 6.0],
    )
    report = generate_cost_report("p", dets, METERS, CostingConfig(), seg)
    cim2 = next(line for line in report.boq.lines if line.concept_code == "CIM-002")
    # only the 3 foundation footings count; the 8 false roof footings are excluded
    assert cim2.source_detection_count == 3
    assert cim2.raw_quantity == pytest.approx(6.0)  # 3 × 2.0 m²


def test_segmented_measured_section_clamped() -> None:
    # A column whose marker section is implausibly large is rejected → assumed.
    big = _detection(0, DetectionType.column_tag, section_area_du2=250.0)
    ok = _detection(1, DetectionType.column_tag, section_area_du2=0.09)
    dets = [big, ok]
    seg = SheetSegmentation(
        views=[_plan("v", "planta_baja", 3.0, [d.detection_id for d in dets])],
        assignment={d.detection_id: "v" for d in dets},
        is_segmented=True,
        npt_levels=[0.0, 3.0],
    )
    # one plan view alone still segments=True here; column volume uses that plan
    report = generate_cost_report("p", dets, METERS, CostingConfig(), seg)
    est1 = next(line for line in report.boq.lines if line.concept_code == "EST-001")
    # big rejected → assumed 0.09; ok accepted → 0.09; both ~0.09 here
    assert est1.quantity == pytest.approx((0.09 + 0.09) * 3.0, abs=1e-6)


def test_non_segmented_matches_flat(sample_detections) -> None:
    flat = generate_cost_report("p", sample_detections, METERS, CostingConfig())
    empty_seg = SheetSegmentation(views=[], assignment={}, is_segmented=False)
    with_seg = generate_cost_report("p", sample_detections, METERS, CostingConfig(), empty_seg)
    assert flat.boq.direct_cost_total == with_seg.boq.direct_cost_total


# --- live recompute (parameter / price overrides) -----------------------------


def test_price_override_scales_apu_and_total(sample_detections) -> None:
    base = generate_cost_report("p", sample_detections, METERS, CostingConfig())
    # Double the price of concrete; the concrete-bearing lines must rise.
    book = apply_price_overrides(default_price_book(), {"MAT-CONC250": 2650.0 * 2})
    bumped = generate_cost_report(
        "p", sample_detections, METERS, CostingConfig(), price_book=book
    )
    assert bumped.boq.direct_cost_total > base.boq.direct_cost_total
    assert bumped.integration.grand_total > base.integration.grand_total


def test_indirects_override_changes_sale_price(sample_detections) -> None:
    cfg = CostingConfig()
    cfg.indirects.profit_pct = 25.0  # was 10
    base = generate_cost_report("p", sample_detections, METERS, CostingConfig())
    bumped = generate_cost_report("p", sample_detections, METERS, cfg)
    assert bumped.integration.sale_price > base.integration.sale_price
    assert bumped.boq.direct_cost_total == base.boq.direct_cost_total  # CD unchanged


def test_recompute_roundtrip_from_artifacts(sample_detections, tmp_path) -> None:
    from klave_engine.common.io import write_json
    from klave_engine.detection.views import SheetSegmentation

    processed = tmp_path / "processed"
    processed.mkdir()
    write_json(processed / "detections.json", sample_detections)
    write_json(processed / "drawing_units.json", METERS)
    write_json(
        processed / "views.json",
        SheetSegmentation(views=[], assignment={}, is_segmented=False),
    )

    inputs = load_costing_inputs(processed, "p")
    assert len(inputs.detections) == len(sample_detections)
    over = CostingOverrides(config=CostingConfig(), insumo_prices={"MAT-ACERO": 30000.0})
    report = build_cost_report(inputs, over)
    assert report.boq.direct_cost_total > 0
