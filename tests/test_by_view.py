"""A presupuesto line on a segmented sheet says how much of it sits on each planta."""

from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.boq import generate_bill_of_quantities
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.models import CostingAssumptions
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.views import SheetSegmentation, ViewKind, ViewRegion
from klave_engine.dxf.units import DrawingUnits

from tests.precios import LIBRO


def _slab(det_id, area, family="reticular"):
    return make_detection(
        det_id, DetectionType.slab_region, det_id, (0, 0, 1, 1), 0.9, [], "slab_panel", [],
        {"estimated_area": area, "family": family},
    )


def test_quantities_split_by_planta():
    dets = [_slab("a", 100.0), _slab("b", 40.0), _slab("c", 60.0), _slab("z", 80.0, "cimentacion")]
    seg = SheetSegmentation(
        views=[
            ViewRegion(view_id="f0", title="ES-000 · CIMENTACIÓN", kind=ViewKind.plan,
                       level_key="cimentacion", anchor=(0, 0)),
            ViewRegion(view_id="f1", title="ES-100 · PLANTA BAJA", kind=ViewKind.plan,
                       level_key="planta_baja", anchor=(0, 0)),
            ViewRegion(view_id="f2", title="ES-400 · AZOTEA", kind=ViewKind.plan,
                       level_key="azotea", anchor=(0, 0)),
        ],
        assignment={"z": "f0", "a": "f1", "b": "f1", "c": "f2"},
        is_segmented=True,
    )
    assumptions = CostingAssumptions()
    catalog = [c for c in build_default_catalog(assumptions) if c.code in {"EST-003", "CIM-007"}]
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    boq = generate_bill_of_quantities(
        "t", dets, units, catalog, build_all_apus(catalog, LIBRO), segmentation=seg,
        assumptions=assumptions,
    )
    lines = {line.concept_code: line for line in boq.lines}
    assert lines["EST-003"].quantity == 200.0
    assert lines["EST-003"].by_view == {"ES-100 · PLANTA BAJA": 140.0, "ES-400 · AZOTEA": 60.0}
    # A single-planta line carries no breakdown (nothing to split).
    assert lines["CIM-007"].by_view == {}


def test_losa_sin_tipo_no_se_cobra_como_reticular():
    # Una losa sin sistema declarado no es reticular: sale como EST-016,
    # sin precio, hasta que el plano declare el sistema o el taller la mapee.
    dets = [_slab("s1", 20.0, family=None)]
    assumptions = CostingAssumptions()
    catalog = [c for c in build_default_catalog(assumptions) if c.code in {"EST-003", "EST-016"}]
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    boq = generate_bill_of_quantities(
        "t", dets, units, catalog, build_all_apus(catalog, LIBRO),
        assumptions=assumptions,
    )
    lines = {line.concept_code: line for line in boq.lines}
    assert "EST-003" not in lines or lines["EST-003"].quantity == 0.0
    assert lines["EST-016"].quantity == 20.0
    assert lines["EST-016"].unpriced is True


def _col(det_id):
    return make_detection(
        det_id, DetectionType.column_tag, f"C-{det_id}", (0, 0, 1, 1), 0.9, [], "m", []
    )


def _seg(views_and_dets):
    views = [
        ViewRegion(view_id=vid, title=f"ES · {vid.upper()}", kind=ViewKind.plan,
                   level_key=key, anchor=(0, 0))
        for vid, key, _ids in views_and_dets
    ]
    assignment = {d: vid for vid, _key, ids in views_and_dets for d in ids}
    return SheetSegmentation(views=views, assignment=assignment, is_segmented=True)


def test_sin_alturas_las_plantas_se_suman():
    # Sin niveles declarados, un castillo de PB y uno de PA son piezas
    # distintas: la vista más poblada no puede descartar a las demás (E6).
    dets = [_col(i) for i in ("a", "b", "c", "d", "e")]
    assumptions = CostingAssumptions()
    catalog = [c for c in build_default_catalog(assumptions) if c.code == "EST-001"]
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    apus = build_all_apus(catalog, LIBRO)

    def run(seg):
        boq = generate_bill_of_quantities(
            "t", dets, units, catalog, apus, segmentation=seg, assumptions=assumptions
        )
        return {line.concept_code: line for line in boq.lines}["EST-001"]

    dos_plantas = run(_seg([
        ("f1", "planta_baja", ["a", "b", "c"]),
        ("f2", "planta_alta", ["d", "e"]),
    ]))
    una_planta = run(_seg([("f1", "planta_baja", ["a", "b", "c", "d", "e"])]))
    solo_tres = run(_seg([("f1", "planta_baja", ["a", "b", "c"])]))

    # Sumar 3+2 con la misma altura supuesta = 5 en una planta…
    assert dos_plantas.quantity == una_planta.quantity
    # …y estrictamente más que quedarse con la planta más poblada.
    assert dos_plantas.quantity > solo_tres.quantity
    assert set(dos_plantas.by_view) == {"ES · F1", "ES · F2"}
