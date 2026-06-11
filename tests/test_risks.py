"""Risk rule triggering on the demo fixture."""

import pytest
from klave_engine.evals.fixtures import DEMO_GOLD
from klave_engine.pipeline import DetectorSuiteConfig, run_detectors
from klave_engine.risks.rules import Severity, generate_risk_report
from klave_engine.takeoff.quantities import generate_quantity_report


@pytest.fixture(scope="module")
def risk_report(demo_entities, demo_index, demo_manifest):
    outputs = run_detectors(demo_entities, demo_index, demo_manifest, DetectorSuiteConfig())
    detections = [d for output in outputs for d in output.detections]
    quantities = generate_quantity_report("demo_project_001", detections)
    return generate_risk_report(
        "demo_project_001", demo_manifest, demo_entities, detections, quantities
    )


def test_expected_risk_types_trigger(risk_report) -> None:
    found_types = {f.risk_type for f in risk_report.findings}
    for expected in DEMO_GOLD["expected_risk_types"]:
        assert expected in found_types, f"missing risk type: {expected}"


def test_unresolved_detail_reference_is_high_and_specific(risk_report) -> None:
    finding = next(
        f for f in risk_report.findings if f.risk_type == "unresolved_detail_reference"
    )
    assert finding.severity == Severity.high
    assert "5/S-501" in finding.message
    assert "S-501" in finding.message
    assert finding.related_detections
    assert finding.recommended_human_action


def test_duplicate_column_tag_detected(risk_report) -> None:
    finding = next(f for f in risk_report.findings if f.risk_type == "duplicate_column_tag")
    assert "C1" in finding.message
    assert len(finding.related_detections) == 2


def test_empty_drawing_rule(demo_manifest) -> None:
    report = generate_risk_report("demo_project_001", demo_manifest, [], [], None)
    assert any(f.risk_type == "empty_drawing_after_parsing" for f in report.findings)


def test_no_footing_without_column_on_demo(risk_report) -> None:
    assert not any(f.risk_type == "footing_without_column" for f in risk_report.findings)
