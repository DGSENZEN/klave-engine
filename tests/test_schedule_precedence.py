"""The programa is handed to a client citing RLOPSRM art. 224. These are the
things that must be true of it before that is defensible."""

import pytest
from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    Concept,
    CostingConfig,
    QuantityKind,
    ScheduleConfig,
    ScheduleLink,
)
from klave_engine.costing.report import generate_cost_report
from klave_engine.costing.schedule import _dedupe_links, build_schedule
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


def test_the_pour_waits_for_its_formwork_to_finish(store_report):
    """Traslape between trades is correct modelling and stays SS. But you
    cannot pour a column while its formwork is still going up: that pair is
    finish-to-start, and it is the only kind of edge that creates real float
    for everything else.

    Built on ``store_report``, not ``_structural_report()`` — R7 again: the
    hard edges below only exist between concepts that apply_steel/
    apply_formwork create against a real catalog store, so a store-less
    fixture has no formwork or steel activities to build one to, and
    ``hard_edges > 0`` would fail for the wrong reason."""
    by_code = {a.concept_code: a for a in store_report.schedule.activities}

    hard_edges = 0
    for pour in by_code.values():
        for link in pour.predecessors:
            if link.kind != "FS":
                continue
            hard_edges += 1
            predecessor = by_code[link.predecessor]
            assert pour.start_day >= predecessor.end_day + link.lag_days
    assert hard_edges > 0, "ninguna arista dura: el colado no espera a nada"


def test_the_critical_path_is_not_the_whole_job():
    """27 of 30 activities critical is the signature of a chain, not a
    network: with only SS lags there is nowhere for float to come from.

    Deliberately not built on ``store_report`` — measured empirically before
    writing this test, not assumed. ``store_report``'s detections (columns
    and beams only) put every derived concept at its own unique
    sequence_order, so its 5 activities form a single chain with no fan-out
    at all (verified: 5/5 critical both before and after Step 3 — a pure
    chain cannot have float, by construction, regardless of SS vs FS). The
    real catalog does have genuine parallel steps — e.g. EST-006/EST-012 and
    EST-007/EST-013 share a sequence_order — but reaching them needs
    losa/muro detections outside this file's fixtures, and guessing at their
    property filters risks a fixture that silently tests nothing.

    So this builds the network directly, the same way test_schedule_cpm.py
    does, with two real DERIVADO_DE triples (columna and zapata) tied at the
    same three sequence_order steps but on different crews, so the shorter
    one gets real float. HARD_PREDECESSORS still comes from the production
    DERIVADO_DE map — these are genuine hard-edge pairs, not invented ones.

    Note for the record: on ``store_report``'s own chain, Step 3 changes
    dates (EST-002 moves from day 5 to day 6 — it no longer starts before
    its own formwork finishes) but not the critical count, which stays 5/5
    either way. A chain has nowhere for float to come from no matter how
    correct its edges are; that is exactly the point this test is making
    with a network that has somewhere for it to go."""
    catalog = [
        Concept(code="EST-008", description="cimbra columna", unit="M2",
                phase="Estructura", production_rate_per_day=1.0, sequence_order=1),
        Concept(code="CIM-006", description="cimbra zapata", unit="M2",
                phase="Estructura", production_rate_per_day=1.0, sequence_order=1),
        Concept(code="ACE-001", description="acero columna", unit="KG",
                phase="Estructura", production_rate_per_day=1.0, sequence_order=2),
        Concept(code="ACE-003", description="acero zapata", unit="KG",
                phase="Estructura", production_rate_per_day=1.0, sequence_order=2),
        Concept(code="EST-001", description="colado columna", unit="M3",
                phase="Estructura", production_rate_per_day=1.0, sequence_order=3),
        Concept(code="CIM-002", description="colado zapata", unit="M3",
                phase="Estructura", production_rate_per_day=1.0, sequence_order=3),
    ]
    # Columna: 2 units at every step. Zapata: 10. Same crews would queue them
    # (crew defaults to the concept's own code with no APU supplied, so they
    # do not); same sequence_order per step means the shorter one gets float
    # against the longer one's step_anchor instead of chaining after it.
    quantities = {
        "EST-008": 2.0, "CIM-006": 10.0, "ACE-001": 2.0,
        "ACE-003": 10.0, "EST-001": 2.0, "CIM-002": 10.0,
    }
    boq = BillOfQuantities(
        project_id="p",
        lines=[
            BoqLine(
                concept_code=code, description=code, unit="M3", quantity=qty,
                unit_price=100.0, amount=qty * 100.0, phase="Estructura",
                raw_quantity=qty, raw_kind=QuantityKind.VOLUME,
                source_detection_count=1, confidence=0.9,
            )
            for code, qty in quantities.items()
        ],
    )
    schedule = build_schedule(boq, catalog, ScheduleConfig())
    by_code = {a.concept_code: a for a in schedule.activities}

    # The hard edges are genuinely there (Step 3's own contribution)...
    assert any(link.kind == "FS" for a in schedule.activities for link in a.predecessors)
    # ...and the network they sit in still has real float in it.
    critical = [a for a in schedule.activities if a.critical]
    assert len(critical) < len(schedule.activities), "todo es ruta crítica: no hay red"
    assert not by_code["EST-001"].critical, "la cadena corta debería tener holgura"
    assert by_code["CIM-002"].critical, "la cadena larga debería ser crítica"
