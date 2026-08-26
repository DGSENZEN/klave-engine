"""The programa is handed to a client citing RLOPSRM art. 224. These are the
things that must be true of it before that is defensible."""

import pytest
from klave_engine.costing.models import CostingConfig, ScheduleLink
from klave_engine.costing.report import generate_cost_report
from klave_engine.costing.schedule import _dedupe_links
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.taxonomy import classify_family
from klave_engine.dxf.units import DrawingUnits

from tests.precios import LIBRO


def _structural_detections():
    """A column and a beam: enough to produce concrete, its steel and its
    formwork, which is where every ordering bug in this file lives."""
    detections = []
    for index in range(6):
        column = make_detection(
            f"c{index}", DetectionType.column_tag, f"C-{index}",
            (index, 0, index + 0.3, 0.3), 0.9, [], "m", [],
            {"section_cm": "30x30"},
        )
        column.family = classify_family(column).value
        detections.append(column)
    for index in range(4):
        beam = make_detection(
            f"b{index}", DetectionType.beam_tag, f"T-{index}",
            (0, index, 5.0, index + 0.3), 0.9, [], "m", [],
            {"estimated_span_length": 5.0, "section_cm": "30x60"},
        )
        beam.family = classify_family(beam).value
        detections.append(beam)
    return detections


def _structural_report():
    units = DrawingUnits(unit="m", source="dxf_header", confidence=0.9)
    return generate_cost_report(
        "p", _structural_detections(), units, CostingConfig(), None, None, price_book=LIBRO
    )


@pytest.fixture
def store_report(tmp_path):
    """A report built through a real catalog store.

    The acero and cimbra concepts this test is about are created by
    apply_steel/apply_formwork against the store's catalog and matrices —
    build_default_catalog alone has neither, so a store-less fixture produces
    a two-line BoQ and an invariant that passes by skipping every pair.
    """
    from klave_engine.costing.catalog_store import CatalogStore

    from tests.precios import sembrar

    store = CatalogStore(tmp_path / "catalog.db")
    sembrar(store)
    detections = _structural_detections()
    units = DrawingUnits(unit="m", source="dxf_header", confidence=0.9)
    return generate_cost_report(
        "p", detections, units, CostingConfig(), None, None,
        price_book=store.load_price_book(),
        store_concepts=store.load_concepts(),
        apu_templates=store.load_templates(),
        rendimientos=store.load_rendimientos(),
    )


def test_no_activity_lists_the_same_predecessor_twice():
    """The step anchor and the crew tail are often the same concept, and both
    branches used to append their own link — 13 of 30 activities on Marina."""
    report = _structural_report()

    for activity in report.schedule.activities:
        seen = [(link.predecessor, link.kind) for link in activity.predecessors]
        assert len(seen) == len(set(seen)), f"{activity.concept_code} repite {seen}"


@pytest.mark.parametrize(
    "links",
    [
        pytest.param(
            [
                ScheduleLink(predecessor="EST-001", kind="SS", lag_days=3),
                ScheduleLink(predecessor="EST-001", kind="SS", lag_days=7),
            ],
            id="smaller-first",
        ),
        pytest.param(
            [
                ScheduleLink(predecessor="EST-001", kind="SS", lag_days=7),
                ScheduleLink(predecessor="EST-001", kind="SS", lag_days=3),
            ],
            id="larger-first",
        ),
    ],
)
def test_dedupe_links_keeps_the_larger_lag_on_a_collision(links):
    """Two SS links to the same predecessor are two constraints on one edge;
    both apply at once, so the true bound is their max and the smaller lag
    must not survive. A fixture-based test cannot exercise this: the step
    anchor and the crew tail always compute the same lag from the same
    activity's duration_days when they collide, so only a hand-built pair
    with genuinely different lags reaches the branch that chooses.

    Both input orders are exercised so that a magnitude-blind "last one
    wins" implementation — which would satisfy a single fixed order,
    because the larger happened to be listed last — cannot pass: the
    larger lag must survive regardless of which one was appended first."""
    result = _dedupe_links(links)

    assert result == [ScheduleLink(predecessor="EST-001", kind="SS", lag_days=7)]


def test_dedupe_links_does_not_collapse_a_differing_kind():
    """The key is (predecessor, kind): an FS and an SS to the same
    predecessor are different constraints and both must survive."""
    links = [
        ScheduleLink(predecessor="EST-001", kind="SS", lag_days=3),
        ScheduleLink(predecessor="EST-001", kind="FS", lag_days=0),
    ]

    result = _dedupe_links(links)

    assert {(link.predecessor, link.kind, link.lag_days) for link in result} == {
        ("EST-001", "SS", 3),
        ("EST-001", "FS", 0),
    }


CIMBRA_DE = {"EST-008": "EST-001", "EST-009": "EST-002", "EST-011": "EST-013",
             "CIM-006": "CIM-002", "CIM-009": "CIM-008", "EST-010": "EST-005"}
ACERO_DE = {"ACE-001": "EST-001", "ACE-002": "EST-005", "ACE-003": "CIM-002",
            "ACE-004": "EST-002", "ACE-006": "EST-013"}


def test_nothing_is_poured_before_it_is_formed_or_reinforced(store_report):
    """On Marina this failed by 213 days: the programa said pour the columns
    on day 83 and install their formwork on day 296. A cost engineer sees
    that in five seconds, and the document cites RLOPSRM art. 224.

    Built on ``store_report``, not ``_structural_report()``: the derived
    concepts this test is about only come from apply_steel/apply_formwork
    against a real catalog store, so a store-less fixture would make every
    pair below skip and this test would pass whether or not the bug exists."""
    by_code = {a.concept_code: a for a in store_report.schedule.activities}

    checked = 0
    for derived, pour in {**CIMBRA_DE, **ACERO_DE}.items():
        if derived not in by_code or pour not in by_code:
            continue
        checked += 1
        assert by_code[derived].start_day <= by_code[pour].start_day, (
            f"{derived} arranca el día {by_code[derived].start_day}, "
            f"después de colar {pour} el día {by_code[pour].start_day}"
        )
    assert checked > 0, "ningún par derivado/colado se pudo verificar: la prueba no probó nada"
