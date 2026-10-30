"""Tarea 15d: las variantes de un renglón se reparten sobre las detecciones que el renglón cuenta.

Una detección que el renglón no cuenta (la de la planta de cimentación en un renglón de
superestructura, la de una planta de superestructura en uno de cimentación, la de un detalle)
no forma variante: medida sola, el respaldo del alcance (``… or matched_plan``) le inventaba
cantidad y las demás variantes la devolvían a prorrata, sin aviso. Una prueba por cada familia
que se separa en variantes.
"""

import pytest
from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.boq import generate_bill_of_quantities
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.models import CostingAssumptions
from klave_engine.detection.results import Detection, DetectionType, make_detection
from klave_engine.detection.taxonomy import classify_family
from klave_engine.detection.views import SheetSegmentation, ViewKind, ViewRegion
from klave_engine.dxf.units import DrawingUnits

from tests.precios import LIBRO

UNITS = DrawingUnits(unit="m", source="declared", confidence=1.0)
NIVELES = [1.45, 4.35, 7.95, 11.15]  # PB 3.60 m, PA 3.20 m


def _vistas(niveles: bool = True) -> list[ViewRegion]:
    npt = NIVELES if niveles else [None] * 4
    vistas = [
        ViewRegion(view_id="f0", title="ES-000 · CIMENTACIÓN", kind=ViewKind.plan,
                   level_key="cimentacion", npt_level=npt[0], anchor=(0, 0)),
        ViewRegion(view_id="f1", title="ES-100 · PLANTA BAJA", kind=ViewKind.plan,
                   level_key="planta_baja", npt_level=npt[1], anchor=(0, 0)),
        ViewRegion(view_id="f2", title="ES-200 · PLANTA ALTA", kind=ViewKind.plan,
                   level_key="planta_alta", npt_level=npt[2], anchor=(0, 0)),
        ViewRegion(view_id="f3", title="ES-400 · AZOTEA", kind=ViewKind.plan,
                   level_key="azotea", npt_level=npt[3], anchor=(0, 0)),
        ViewRegion(view_id="det", title="ES-500 · DETALLES", kind=ViewKind.excluded,
                   anchor=(0, 0)),
    ]
    return vistas


def _linea(code: str, dets: list[Detection], asignacion: dict[str, str], niveles: bool = True,
           a: CostingAssumptions | None = None):
    a = a or CostingAssumptions(opening_share_pct=0)
    seg = SheetSegmentation(
        views=_vistas(niveles), is_segmented=True, assignment=asignacion,
        npt_levels=NIVELES if niveles else [],
    )
    catalog = [c for c in build_default_catalog(a) if c.code == code]
    boq = generate_bill_of_quantities(
        "t", dets, UNITS, catalog, build_all_apus(catalog, LIBRO), segmentation=seg, assumptions=a
    )
    (linea,) = [ln for ln in boq.lines if ln.concept_code == code]
    return linea


def _det(det_id: str, kind: DetectionType, label: str, props: dict) -> Detection:
    det = make_detection(det_id, kind, label, (0, 0, 1, 1), 0.9, [], "m", [], props)
    det.family = classify_family(det).value
    return det


def _variantes(linea) -> dict[str, float]:
    return {v.key: v.quantity for v in linea.variants}


def _sin_ajuste(linea) -> None:
    assert not any("repartidas en proporción" in n for n in linea.assumptions)
    assert sum(v.quantity for v in linea.variants) == pytest.approx(linea.quantity)


# --- columnas (volumen) ---------------------------------------------------------------------


def _columna(det_id: str, seccion: str) -> Detection:
    return _det(det_id, DetectionType.column_tag, "K-1", {"section_cm": seccion})


def test_columnas_sin_niveles_la_de_cimentacion_no_es_variante():
    # Sin niveles declarados, dos plantas de superestructura se suman a la altura supuesta; el
    # castillo de la cimentación no se cuenta y su sección (30x30) no es variante: medido solo
    # caía al respaldo «la planta más poblada» y se inventaba 0.09 × 2.70 m³.
    a = CostingAssumptions()
    dets = [_columna("c0", "30x30"), _columna("c1", "15x20"), _columna("c2", "20x20")]
    linea = _linea("EST-001", dets, {"c0": "f0", "c1": "f1", "c2": "f2"}, niveles=False, a=a)
    h = a.column_height_m
    assert linea.quantity == pytest.approx((0.03 + 0.04) * h)
    assert _variantes(linea) == {
        "EST-001.15X20": pytest.approx(0.03 * h),
        "EST-001.20X20": pytest.approx(0.04 * h),
    }
    _sin_ajuste(linea)


# --- muros (área: largo × altura de su planta) -----------------------------------------------


def _muro(det_id: str, largo: float, espesor: float, tipo: str = "block") -> Detection:
    return _det(det_id, DetectionType.wall, det_id, {
        "estimated_length": largo, "estimated_thickness": espesor, "wall_kind": tipo,
    })


def test_muros_sin_niveles_el_de_cimentacion_no_es_variante():
    # EST-004 suma las plantas de superestructura; el muro de 25 cm de la cimentación no se
    # cuenta. Medido solo, el alcance volvía a «todas las vistas» y le daba 8 m × 2.70 m.
    dets = [_muro("w0", 8.0, 0.25), _muro("w1", 10.0, 0.15), _muro("w2", 20.0, 0.20)]
    linea = _linea("EST-004", dets, {"w0": "f0", "w1": "f1", "w2": "f2"}, niveles=False)
    assert linea.quantity == pytest.approx((10.0 + 20.0) * 2.7)
    assert _variantes(linea) == {
        "EST-004.BLOCK-15": pytest.approx(10.0 * 2.7),
        "EST-004.BLOCK-20": pytest.approx(20.0 * 2.7),
    }
    _sin_ajuste(linea)


def test_muros_con_niveles_el_de_cimentacion_no_deja_variante_en_cero():
    # Con alturas por planta, el muro de la cimentación medido solo daba 0 m² pero con un
    # elemento «que contribuye»: una variante BLOCK-25 vacía en el renglón.
    dets = [_muro("w0", 8.0, 0.25), _muro("w1", 10.0, 0.15), _muro("w2", 20.0, 0.20)]
    linea = _linea("EST-004", dets, {"w0": "f0", "w1": "f1", "w2": "f2"})
    assert linea.quantity == pytest.approx(10.0 * 3.6 + 20.0 * 3.2)
    assert _variantes(linea) == {
        "EST-004.BLOCK-15": pytest.approx(10.0 * 3.6),
        "EST-004.BLOCK-20": pytest.approx(20.0 * 3.2),
    }
    _sin_ajuste(linea)


def test_muros_de_concreto_el_de_cimentacion_no_es_variante():
    # EST-014 (volumen: largo × espesor × altura): el muro de contención de 30 cm en la
    # cimentación no se cuenta en la superestructura.
    dets = [
        _muro("w0", 8.0, 0.30, "concreto"), _muro("w1", 10.0, 0.15, "concreto"),
        _muro("w2", 20.0, 0.20, "concreto"),
    ]
    linea = _linea("EST-014", dets, {"w0": "f0", "w1": "f1", "w2": "f2"}, niveles=False)
    assert linea.quantity == pytest.approx(10.0 * 0.15 * 2.7 + 20.0 * 0.20 * 2.7)
    assert _variantes(linea) == {
        "EST-014.CONCRETO-15": pytest.approx(10.0 * 0.15 * 2.7),
        "EST-014.CONCRETO-20": pytest.approx(20.0 * 0.20 * 2.7),
    }
    _sin_ajuste(linea)


# --- trabes y dalas (largo; volumen) ---------------------------------------------------------


def _viga(det_id: str, largo: float, seccion: str, familia: str) -> Detection:
    det = _det(det_id, DetectionType.beam_tag, det_id, {
        "estimated_span_length": largo, "section_cm": seccion,
    })
    det.family = familia
    return det


def test_dalas_la_de_cimentacion_no_es_variante():
    # EST-005 (m): la dala de desplante de 20x40 dibujada en la cimentación no es de la
    # superestructura; medida sola, el respaldo le daba sus 6 m.
    dets = [
        _viga("d0", 6.0, "20x40", "dala"), _viga("d1", 5.0, "15x20", "dala"),
        _viga("d2", 7.0, "15x25", "dala"),
    ]
    linea = _linea("EST-005", dets, {"d0": "f0", "d1": "f1", "d2": "f2"})
    assert linea.quantity == pytest.approx(12.0)
    assert _variantes(linea) == {
        "EST-005.15X20": pytest.approx(5.0),
        "EST-005.15X25": pytest.approx(7.0),
    }
    _sin_ajuste(linea)


def test_trabes_la_de_cimentacion_no_es_variante():
    # EST-002 (m³: largo × sección declarada).
    dets = [
        _viga("t0", 6.0, "40x80", "trabe"), _viga("t1", 5.0, "25x50", "trabe"),
        _viga("t2", 4.0, "30x60", "trabe"),
    ]
    linea = _linea("EST-002", dets, {"t0": "f0", "t1": "f1", "t2": "f2"})
    assert linea.quantity == pytest.approx(5.0 * 0.125 + 4.0 * 0.18)
    assert _variantes(linea) == {
        "EST-002.25X50": pytest.approx(5.0 * 0.125),
        "EST-002.30X60": pytest.approx(4.0 * 0.18),
    }
    _sin_ajuste(linea)


def test_contratrabes_la_de_una_planta_alta_no_es_variante():
    # CIM-008 (cimentación): una contratrabe leída en PLANTA ALTA no es de la cimentación;
    # medida sola, el respaldo «sin planta de cimentación» la contaba.
    dets = [
        _viga("ct0", 6.0, "30x90", "contratrabe"), _viga("ct1", 5.0, "25x70", "contratrabe"),
        _viga("ct2", 4.0, "40x80", "contratrabe"),
    ]
    linea = _linea("CIM-008", dets, {"ct0": "f2", "ct1": "f0", "ct2": "f0"})
    assert linea.quantity == pytest.approx(5.0 * 0.175 + 4.0 * 0.32)
    assert _variantes(linea) == {
        "CIM-008.25X70": pytest.approx(5.0 * 0.175),
        "CIM-008.40X80": pytest.approx(4.0 * 0.32),
    }
    _sin_ajuste(linea)


# --- losas (área; volumen) -------------------------------------------------------------------


def _losa(det_id: str, area: float, familia: str, espesor_cm: float) -> Detection:
    return _det(det_id, DetectionType.slab_region, det_id, {
        "estimated_area": area, "family": familia, "thickness_cm": espesor_cm,
    })


def test_losas_la_de_cimentacion_no_es_variante():
    # EST-003 (m²): un tablero reticular de 35 cm en la planta de cimentación no se cuenta.
    dets = [
        _losa("l0", 50.0, "reticular", 35), _losa("l1", 40.0, "reticular", 25),
        _losa("l2", 30.0, "reticular", 30),
    ]
    linea = _linea("EST-003", dets, {"l0": "f0", "l1": "f1", "l2": "f2"})
    assert linea.quantity == pytest.approx(70.0)
    assert _variantes(linea) == {
        "EST-003.RETICULAR-25": pytest.approx(40.0),
        "EST-003.RETICULAR-30": pytest.approx(30.0),
    }
    _sin_ajuste(linea)


def test_losa_de_cimentacion_la_de_una_planta_no_es_variante():
    # CIM-007 (m³): una losa de cimentación de 40 cm leída en PLANTA BAJA no se cuenta.
    dets = [
        _losa("lc0", 50.0, "cimentacion", 40), _losa("lc1", 40.0, "cimentacion", 25),
        _losa("lc2", 30.0, "cimentacion", 30),
    ]
    linea = _linea("CIM-007", dets, {"lc0": "f1", "lc1": "f0", "lc2": "f0"})
    assert linea.quantity == pytest.approx(40.0 * 0.25 + 30.0 * 0.30)
    assert _variantes(linea) == {
        "CIM-007.CIMENTACION-25": pytest.approx(40.0 * 0.25),
        "CIM-007.CIMENTACION-30": pytest.approx(30.0 * 0.30),
    }
    _sin_ajuste(linea)


# --- zapatas y pilotes (cimentación) ---------------------------------------------------------


def _zapata(det_id: str, area: float, tipo: str) -> Detection:
    return _det(det_id, DetectionType.footing, det_id, {
        "estimated_area": area, "footing_kind": tipo, "peralte_cm": 40,
    })


def test_zapatas_la_de_una_planta_no_es_variante():
    # CIM-002 (m³): una zapata corrida leída en PLANTA BAJA no es de la cimentación.
    dets = [_zapata("z0", 6.0, "corrida"), _zapata("z1", 4.0, "aislada"),
            _zapata("z2", 2.0, "colindancia")]
    linea = _linea("CIM-002", dets, {"z0": "f1", "z1": "f0", "z2": "f0"})
    assert linea.quantity == pytest.approx((4.0 + 2.0) * 0.40)
    assert _variantes(linea) == {
        "CIM-002.AISLADA": pytest.approx(4.0 * 0.40),
        "CIM-002.COLINDANCIA": pytest.approx(2.0 * 0.40),
    }
    _sin_ajuste(linea)


def test_pilotes_el_de_una_planta_no_es_variante():
    # CIM-010 (piezas): un círculo de 1.20 m leído como pilote en PLANTA BAJA no se cuenta.
    dets = [
        _det("p0", DetectionType.pile, "P", {"diameter": 1.2}),
        _det("p1", DetectionType.pile, "P", {"diameter": 0.6}),
        _det("p2", DetectionType.pile, "P", {"diameter": 0.8}),
        _det("p3", DetectionType.pile, "P", {"diameter": 0.8}),
    ]
    linea = _linea("CIM-010", dets, {"p0": "f1", "p1": "f0", "p2": "f0", "p3": "f0"})
    assert linea.quantity == pytest.approx(3.0)
    assert _variantes(linea) == {"CIM-010.60": 1.0, "CIM-010.80": 2.0}
    _sin_ajuste(linea)


# --- tuberías (alcance «todas»): un detalle no es variante -----------------------------------


def test_tuberias_la_de_un_detalle_no_es_variante():
    # HID-003 cuenta todas las plantas; el tramo de 50 mm dibujado en un detalle no se cuenta
    # (ya medía cero solo; queda fijado).
    def tubo(det_id: str, largo: float, diametro: str) -> Detection:
        return _det(det_id, DetectionType.pipe_run, det_id, {
            "estimated_length": largo, "run_family": "agua_fria", "diametro": diametro,
        })

    dets = [tubo("h0", 3.0, "50 mm"), tubo("h1", 10.0, "13 mm"), tubo("h2", 6.0, "19 mm")]
    linea = _linea("HID-003", dets, {"h0": "det", "h1": "f1", "h2": "f2"})
    assert linea.quantity == pytest.approx(16.0)
    assert _variantes(linea) == {"HID-003.13MM": 10.0, "HID-003.19MM": 6.0}
    _sin_ajuste(linea)


# --- vanos: cada variante descuenta lo que el renglón descontó --------------------------------


def test_muros_con_vanos_leidos_la_variante_sin_vanos_no_descuenta_el_supuesto():
    # El renglón leyó una puerta de 0.90 m en el muro de 15 cm: descuenta 0.90 × 2.10 y nada más.
    # La variante de 20 cm, sin vanos leídos, no descuenta el 18 % supuesto: medida sola lo
    # hacía, y el reparto a prorrata le pasaba ese faltante a la de 15 cm.
    a = CostingAssumptions()  # opening_share_pct 18 por omisión
    assert a.opening_share_pct > 0
    w1 = _muro("w1", 10.0, 0.15)
    w1.properties.update(opening_length=0.9, openings=[{"width": 0.9}])
    dets = [w1, _muro("w2", 20.0, 0.20)]
    linea = _linea("EST-004", dets, {"w1": "f1", "w2": "f2"}, a=a)
    vano = 0.9 * a.opening_height_m
    assert linea.quantity == pytest.approx(10.0 * 3.6 + 20.0 * 3.2 - vano)
    assert _variantes(linea) == {
        "EST-004.BLOCK-15": pytest.approx(10.0 * 3.6 - vano),
        "EST-004.BLOCK-20": pytest.approx(20.0 * 3.2),
    }
    _sin_ajuste(linea)


def test_muros_sin_vanos_leidos_cada_variante_descuenta_el_supuesto():
    a = CostingAssumptions()
    dets = [_muro("w1", 10.0, 0.15), _muro("w2", 20.0, 0.20)]
    linea = _linea("EST-004", dets, {"w1": "f1", "w2": "f2"}, a=a)
    resto = 1 - a.opening_share_pct / 100
    assert _variantes(linea) == {
        "EST-004.BLOCK-15": pytest.approx(10.0 * 3.6 * resto),
        "EST-004.BLOCK-20": pytest.approx(20.0 * 3.2 * resto),
    }
    _sin_ajuste(linea)
