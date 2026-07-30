"""Risk rule triggering on the demo fixture."""

import pytest
from klave_engine.detection.suite import DetectorSuiteConfig, run_detectors
from klave_engine.evals.fixtures import DEMO_GOLD
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


def test_low_confidence_detection_triggers_risk(demo_manifest) -> None:
    """A detection below the threshold must raise the low-confidence risk
    (covered here rather than via the demo fixture, whose elements all sit on
    semantic layers and score high)."""
    from klave_engine.detection.results import Detection, DetectionType
    from klave_engine.graph.evidence import EvidencePacket

    weak = Detection(
        detection_id="det_weak",
        detection_type=DetectionType.wall,
        label="W?",
        bbox=(0.0, 0.0, 1.0, 1.0),
        confidence=0.45,
        evidence=EvidencePacket(source="x.dxf", method="test"),
        properties={"estimated_length": 5.0},
    )
    report = generate_risk_report("p", demo_manifest, [], [weak], None)
    types = {f.risk_type for f in report.findings}
    assert "low_confidence_detection_in_takeoff" in types


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
