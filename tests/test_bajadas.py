"""Las bajadas se ligan entre niveles: el símbolo repetido en la misma
posición de cada planta es UNA columna vertical, y su tramo vertical — que
la corrida en planta nunca dibuja — se mide de los niveles declarados."""

from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.boq import generate_bill_of_quantities
from klave_engine.costing.instalaciones import conceptos_de_instalaciones
from klave_engine.detection.bajadas import stamp_bajada_stacks
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.views import SheetSegmentation, ViewKind, ViewRegion
from klave_engine.dxf.units import DrawingUnits

from tests.precios import LIBRO


def _bajada(det_id, x, y):
    return make_detection(
        det_id, DetectionType.fixture, "subida-bajada", (x, y, x + 0.3, y + 0.3),
        0.9, [], "block", [], {"fixture_family": "bajada"}, "x.dxf",
    )


def _escena():
    frames = [
        SheetFrame(frame_id="f0", bbox=(0.0, 0.0, 40.0, 30.0), source_file="x.dxf",
                   code="IS-01", kind="unknown"),
        SheetFrame(frame_id="f1", bbox=(60.0, 0.0, 100.0, 30.0), source_file="x.dxf",
                   code="IS-02", kind="unknown"),
    ]
    seg = SheetSegmentation(
        views=[
            ViewRegion(view_id="f0", title="IS-01 · PB", kind=ViewKind.plan,
                       level_key="planta_baja", npt_level=0.0, anchor=(0, 0)),
            ViewRegion(view_id="f1", title="IS-02 · PA", kind=ViewKind.plan,
                       level_key="planta_alta", npt_level=2.7, anchor=(60, 0)),
        ],
        assignment={}, is_segmented=True,
    )
    dets = [
        _bajada("b1", 5.0, 5.0),    # PB, posición relativa (5, 5)
        _bajada("b2", 65.0, 5.0),   # PA, misma posición relativa → mismo tiro
        _bajada("b3", 20.0, 20.0),  # PB, sin pareja
    ]
    return dets, frames, seg


def test_el_tiro_se_liga_y_mide_su_tramo_vertical():
    dets, frames, seg = _escena()
    stamped = stamp_bajada_stacks(dets, frames, seg, meters_factor=1.0)
    assert stamped == 1  # un tiro ligado (b1+b2); b3 queda sin pareja
    por_id = {d.detection_id: d for d in dets}
    assert por_id["b1"].properties["stack_levels"] == 2
    assert por_id["b2"].properties["stack_id"] == por_id["b1"].properties["stack_id"]
    # El tramo vertical vive en UNA representante (el nivel más bajo): un
    # tiro es una columna, no N.
    assert por_id["b1"].properties["vertical_length_m"] == 2.7
    assert "vertical_length_m" not in por_id["b2"].properties
    assert "stack_id" not in por_id["b3"].properties


def test_san_006_cobra_el_tramo_vertical_sin_precio():
    dets, frames, seg = _escena()
    stamp_bajada_stacks(dets, frames, seg, meters_factor=1.0)
    catalog = [c for c in conceptos_de_instalaciones() if c.code == "SAN-006"]
    assert catalog, "SAN-006 debe existir en los conceptos de instalaciones"
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    boq = generate_bill_of_quantities(
        "t", dets, units, catalog, build_all_apus(catalog, LIBRO)
    )
    linea = next(li for li in boq.lines if li.concept_code == "SAN-006")
    assert linea.quantity == 2.7
    assert linea.unpriced is True


def test_sin_niveles_no_se_inventa_tramo():
    dets, frames, _seg = _escena()
    sin_niveles = SheetSegmentation(
        views=[
            ViewRegion(view_id="f0", title="IS-01", kind=ViewKind.plan, anchor=(0, 0)),
            ViewRegion(view_id="f1", title="IS-02", kind=ViewKind.plan, anchor=(60, 0)),
        ],
        assignment={}, is_segmented=True,
    )
    stamp_bajada_stacks(dets, frames, sin_niveles, meters_factor=1.0)
    por_id = {d.detection_id: d for d in dets}
    # El tiro se liga igual (la posición lo dice), pero sin niveles no hay
    # metros que declarar.
    assert por_id["b1"].properties["stack_levels"] == 2
    assert "vertical_length_m" not in por_id["b1"].properties
