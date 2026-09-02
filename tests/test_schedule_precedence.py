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


def test_the_hard_edge_pins_the_pour_past_what_ss_alone_would_allow():
    """What Step 3 actually changes: cimbra/acero to their pour used to be
    SS with a 50% overlap lag, so the pour could start halfway through its
    own formwork. FS(0) requires the formwork and the steel fully finished
    first, and that is strictly tighter than the SS lag whenever the
    predecessor's own duration is long enough for it to matter: for a
    10-day acero starting day 5, SS-with-50%-overlap allows day 10; FS(0)
    requires day 15 — acero's own end.

    Built by hand, not through ``store_report`` or any detection, the same
    way test_schedule_cpm.py does, so that gap can be shown as an exact,
    deliberate number instead of argued about. Two real DERIVADO_DE triples
    (columna and zapata) share the same three sequence_order steps on
    different crews, so the network also carries genuine float from that
    tie — the point is not the float itself, but that the hard edge still
    pins CIM-002 to ACE-003's end inside a network that has other structure
    going on, exactly as the SS edges elsewhere in it are undisturbed.

    This does NOT assert anything about the critical-path share, on
    purpose — an earlier version of this test did, and was wrong to. Adding
    an FS edge only ever tightens a cursor (``cursor = max(cursor,
    predecessor.end_day)``); it cannot turn a single path into a fork, and
    where a fork already exists (this fixture's tie, or store_report's own
    fan-out — EST-008 alone feeds three different successors there, SS and
    FS both), which side of it floats is decided by the tie, not by SS vs
    FS. Verified directly, both ways: with ``HARD_PREDECESSORS``
    monkeypatched to ``{}``, this fixture's critical set (CIM-006/ACE-003/
    CIM-002 critical, EST-008/ACE-001/EST-001 floating) and store_report's
    (5 of 5 critical) are each byte-identical to the FS-enabled run — only
    the dates move. Whether the real ~30-activity Marina catalog's critical
    share drops below 27/30 is Task 13's own checklist item, verified live
    against the real project, not something this file's fixtures are large
    enough to demonstrate."""
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

    # Step 3's own contribution: the FS edges exist...
    assert any(link.kind == "FS" for a in schedule.activities for link in a.predecessors), (
        "ninguna arista dura: el colado no espera a nada"
    )
    # ...and they are the binding constraint, not a redundant one. This does
    # not depend on the assert above having found anything — on purpose, so
    # it still fails on its own if Step 3's cursor push is ever removed
    # while some other FS link elsewhere keeps the first assert alive.
    # CIM-002's SS step-anchor lag off ACE-003 alone allows day 10 (ACE-003
    # starts day 5, half of its own 10-day duration is 5 more); FS(0) pins
    # it to ACE-003's own end — day 15 — instead.
    assert by_code["CIM-002"].start_day >= by_code["ACE-003"].end_day, (
        f"CIM-002 arranca el día {by_code['CIM-002'].start_day}, antes de que "
        f"termine su acero (ACE-003) el día {by_code['ACE-003'].end_day}"
    )


def _estructura_boq(quantities: dict[str, float]) -> BillOfQuantities:
    return BillOfQuantities(
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


# The same six-concept Estructura network the hard-edge test above builds by
# hand: two DERIVADO_DE triples (columna and zapata) sharing three
# sequence_order steps. Reused because it is the smallest fixture that carries
# real FS edges, and _stretch_phase only ever runs on "Estructura".
_ESTRUCTURA = [
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


def _fs_violations(schedule):
    by_code = {a.concept_code: a for a in schedule.activities}
    return [
        (a.concept_code, a.start_day, link.predecessor,
         by_code[link.predecessor].start_day, by_code[link.predecessor].end_day)
        for a in schedule.activities
        for link in a.predecessors
        if link.kind == "FS"
        and a.start_day < by_code[link.predecessor].end_day + link.lag_days
    ]


def test_the_multi_level_stretch_cannot_pour_a_column_into_its_own_formwork():
    """``levels > 1`` is a code path no other test in this file reaches — both
    fixtures run at the default 1 — so ``test_the_pour_waits_for_its_formwork_
    to_finish`` gave assurance the production path did not have.

    ``_stretch_phase`` used to scale ``start_day`` and ``duration_days``
    through two separate ``round()`` calls, and ``round(a·s) + round(b·s)``
    can exceed ``round((a+b)·s)`` by one. Nothing re-checked the FS edge
    afterwards, so the pour slid one day into its own acero: at levels=3 with
    these quantities, ACE-001 ran 8→16 and EST-001 started on 15. One day is
    not the 213 of the original bug, but the invariant is stated as absolute
    and a colado that begins before its cimbra is finished is exactly what the
    hard edge exists to prevent.

    Swept rather than spot-checked because which combinations round the wrong
    way is not something to guess at: over these levels, cycles, overlaps and
    quantity mixes the pre-fix implementation broke on 2 915 of 17 280
    schedules, and a single well-chosen case would not have been convincing
    that the fix is structural rather than lucky."""
    checked = 0
    edges = 0
    broken: list[tuple] = []
    for quantities in ((2.0, 3.0, 5.0), (5.0, 2.0, 13.0), (7.0, 13.0, 3.0)):
        boq = _estructura_boq({
            "EST-008": quantities[0], "CIM-006": quantities[1],
            "ACE-001": quantities[2], "ACE-003": quantities[0],
            "EST-001": quantities[1], "CIM-002": quantities[2],
        })
        for levels in (2, 3, 4, 5):
            for cycle in (10, 15, 21, 30):
                for overlap in (0.0, 30.0, 50.0, 100.0):
                    schedule = build_schedule(
                        boq, _ESTRUCTURA,
                        ScheduleConfig(
                            per_level_cycle_days=cycle,
                            intra_phase_overlap_pct=overlap,
                        ),
                        levels=levels,
                    )
                    checked += 1
                    edges += sum(
                        1 for a in schedule.activities
                        for link in a.predecessors if link.kind == "FS"
                    )
                    broken.extend(
                        (levels, cycle, overlap, *v) for v in _fs_violations(schedule)
                    )

    assert checked == 192 and edges > 0, "el barrido no probó ninguna arista dura"
    assert not broken, broken[:5]


def test_the_multi_level_stretch_still_reaches_its_per_level_floor():
    """The invariant above must not be bought by refusing to stretch. A
    structure phase of N levels cannot be compressed below N cycles, and the
    stretched phase now lands exactly on that floor rather than near it."""
    boq = _estructura_boq({code.code: 2.0 for code in _ESTRUCTURA})
    config = ScheduleConfig(per_level_cycle_days=21, intra_phase_overlap_pct=50.0)

    short = build_schedule(boq, _ESTRUCTURA, config, levels=1)
    tall = build_schedule(boq, _ESTRUCTURA, config, levels=4)

    assert short.total_duration_days < 4 * 21
    assert tall.total_duration_days == 4 * 21
    for activity in tall.activities:
        assert activity.duration_days >= 1
        assert activity.end_day == activity.start_day + activity.duration_days


def test_the_programa_states_the_crew_assumption_it_is_making():
    """393 working days for a 546 m² house is what one crew per activity
    produces. There is no honest source to derive a crew count from — the
    plantilla de campo is staffing, not cuadrillas — so the assumption is not
    guessed. It is said out loud, next to the number it produced."""
    report = _structural_report()

    stated = " ".join(report.schedule.assumptions)
    assert "frente" in stated.lower()
    assert "cuadrilla" in stated.lower()


def test_the_crew_assumption_is_not_restated_differently_in_the_boq():
    """report.py used to build its own, textually different sentence from
    the same two config numbers (crews_per_activity, frentes) and append it
    to boq.assumptions — which is what feeds the Diagnóstico's criterios
    (hallazgos.py) and the resumen_costos.md export. Both sentences said
    "frentes" and "cuadrillas", so test_the_programa_states_the_crew_
    assumption_it_is_making above could not have caught them disagreeing;
    it only ever looked at report.schedule.assumptions.

    schedule.py now builds that sentence exactly once
    (_crew_assumption_sentence); report.py's _mirror_schedule_assumptions no
    longer constructs its own — it copies schedule.assumptions into
    boq.assumptions verbatim. This asserts that mirror holds: every sentence
    the programa states about itself must show up, byte-for-byte, in the
    BoQ's own register too. A reintroduced second sentence — even one that
    also mentions frentes and cuadrillas — fails this unless it is exactly
    the same string."""
    report = _structural_report()

    assert report.schedule.assumptions, "el programa no declaró ningún supuesto"
    for statement in report.schedule.assumptions:
        assert statement in report.boq.assumptions
