"""Costing engine tests: BoQ quantity rules, price integration, schedule, finance."""

import pytest
from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.integration import integrate_costs
from klave_engine.costing.models import (
    CostingAssumptions,
    CostingConfig,
    IndirectsConfig,
    ResourceType,
)
from klave_engine.costing.report import generate_cost_report
from klave_engine.costing.schedule import direct_spend_by_period
from klave_engine.detection.results import Detection, DetectionType
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
