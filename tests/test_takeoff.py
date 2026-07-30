"""Quantity takeoff over the full detector suite on the demo fixture."""

import pytest
from klave_engine.detection.suite import DetectorSuiteConfig, run_detectors
from klave_engine.evals.fixtures import DEMO_GOLD
from klave_engine.evals.takeoff_eval import evaluate_takeoff
from klave_engine.takeoff.quantities import generate_quantity_report


@pytest.fixture(scope="module")
def quantity_report(demo_entities, demo_index, demo_manifest):
    outputs = run_detectors(demo_entities, demo_index, demo_manifest, DetectorSuiteConfig())
    detections = [d for output in outputs for d in output.detections]
    return generate_quantity_report("demo_project_001", detections)


def test_quantities_match_gold(quantity_report) -> None:
    results = evaluate_takeoff(quantity_report, DEMO_GOLD["quantities"])
    failed = [r for r in results if not r.passed]
    assert not failed, f"takeoff mismatches: {failed}"


def test_every_quantity_has_provenance_and_unit(quantity_report) -> None:
    for item in quantity_report.items:
        assert item.unit is not None
        if item.value > 0:
            assert item.source_detections, f"{item.name} has no source detections"


def test_report_states_assumed_unit(quantity_report) -> None:
    assert quantity_report.assumed_unit == "drawing_units"
    length_items = [i for i in quantity_report.items if i.name.startswith("estimated_")]
    assert all(i.assumptions for i in length_items)
