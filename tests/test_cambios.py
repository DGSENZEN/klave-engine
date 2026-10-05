"""Qué cambió entre dos lecturas: por elemento (agregado, eliminado, movido,
modificado) y por concepto (cantidad y pesos), sin adivinar identidades."""

import pytest
from klave_engine.costing.cambios import comparar, comparar_elementos
from klave_engine.costing.models import BillOfQuantities, BoqLine, CostReport, QuantityKind
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.dxf.units import DrawingUnits

U = DrawingUnits(unit="m", source="declared", confidence=1.0)


def _col(det_id, x, mark="K-1", seccion="15x15", source="e.dxf"):
    d = make_detection(det_id, DetectionType.column_tag, "EST", (x, 0, x + 0.15, 0.15), 0.9,
                       [det_id], "tag", [], {"section_cm": seccion}, source)
    return d.model_copy(update={"mark": mark, "family_label": "Castillos"})


def _report(lines):
    return CostReport.model_construct(project_id="p",
                                      boq=BillOfQuantities(project_id="p", lines=lines),
                                      drawing_units=U)


def _line(code, qty, ids, pu=1000.0, unpriced=False):
    return BoqLine(concept_code=code, description=code, unit="M3", quantity=qty,
                   unit_price=pu, amount=qty * pu, phase="Estructura", raw_quantity=qty,
                   raw_kind=QuantityKind.COUNT, source_detection_count=len(ids),
                   source_detections=ids, confidence=0.9, unpriced=unpriced)


def test_same_marks_many_times_moved_removed_added_modified():
    # Cinco K-1 idénticos en hilera: el de x=2 se mueve 1 m, el de x=4 se quita,
    # al de x=0 le cambian la sección, y aparece uno nuevo lejos.
    antes = [_col(f"a{i}", float(i)) for i in range(5)]
    despues = [
        _col("b0", 0.0, seccion="20x20"), _col("b1", 1.0), _col("b2", 2.0 + 0.0), _col("b3", 3.0),
        _col("b9", 30.0),
    ]
    despues[2] = _col("b2", 2.0).model_copy(update={"bbox": (2.0, 1.0, 2.15, 1.15)})
    cambios = comparar_elementos(antes, despues, 1.0, 1.0)
    tipos = sorted((c.tipo, c.antes_id, c.despues_id) for c in cambios)
    assert tipos == [
        ("agregado", None, "b9"), ("eliminado", "a4", None),
        ("modificado", "a0", "b0"), ("movido", "a2", "b2"),
    ]
    mod = next(c for c in cambios if c.tipo == "modificado")
    assert mod.campos[0].campo == "Sección" and mod.campos[0].despues == "20x20"
    assert next(c for c in cambios if c.tipo == "movido").movido_m == pytest.approx(1.0)


def test_identity_never_jumps_sheets_or_types():
    antes = [_col("a", 0.0, source="E-01.dxf")]
    despues = [_col("b", 0.0, source="E-02.dxf")]
    tipos = sorted(c.tipo for c in comparar_elementos(antes, despues, 1.0, 1.0))
    assert tipos == ["agregado", "eliminado"]


def test_units_do_not_fake_a_move():
    antes = [_col("a", 1000.0).model_copy(update={"bbox": (1000.0, 0, 1150.0, 150.0)})]  # mm
    despues = [_col("b", 1.0)]  # metros
    assert comparar_elementos(antes, despues, 0.001, 1.0) == []


def test_concepts_carry_quantity_pesos_and_their_elements():
    antes_d = [_col("a0", 0.0), _col("a1", 1.0)]
    despues_d = [_col("b0", 0.0), _col("b1", 1.0), _col("b2", 9.0)]
    antes_r = _report([_line("EST-001", 2.0, ["a0", "a1"])])
    despues_r = _report([_line("EST-001", 3.0, ["b0", "b1", "b2"], pu=1200.0),
                         _line("CIM-002", 1.5, [], unpriced=True)])
    c = comparar("run_a", "run_b", antes_d, despues_d, antes_r, despues_r,
                 mismo_plano=False, misma_version=True)
    est = next(x for x in c.conceptos if x.concept_code == "EST-001")
    assert est.diferencia == 1.0 and est.importe_diferencia == 1200.0
    assert est.elementos == {"agregado": 1}
    cim = next(x for x in c.conceptos if x.concept_code == "CIM-002")
    assert cim.cantidad_antes == 0.0 and cim.importe_diferencia is None
    assert c.importe_diferencia == 1200.0 and c.importe_sin_precio == 1
    assert c.resumen == {"agregado": 1}


def test_identical_runs_report_nothing():
    dets = [_col(f"a{i}", float(i)) for i in range(3)]
    r = _report([_line("EST-001", 3.0, ["a0", "a1", "a2"])])
    c = comparar("x", "y", dets, [d.model_copy(update={"detection_id": d.detection_id + "'"})
                                   for d in dets], r, r)
    assert c.conceptos == [] and c.elementos == []


def test_pieces_sharing_an_identity_are_not_swapped():
    """Una corrida partida por diámetro deja dos piezas con el mismo centro:
    hallado en Marina, donde 56 elementos sin tocar salían «modificados»."""
    def corrida(det_id, diam, largo, bbox):
        return make_detection(det_id, DetectionType.pipe_run, "HID", bbox, 0.9, [det_id], "run",
                              [], {"diametro": diam, "length_m": largo}, "h.dxf")

    antes = [corrida("a1", '13 mm (1/2")', 4.0, (0, 0, 10, 2)),
             corrida("a2", '19 mm (3/4")', 6.0, (2, 0, 8, 2))]
    despues = [corrida("b2", '19 mm (3/4")', 6.0, (2, 0, 8, 2)),
               corrida("b1", '13 mm (1/2")', 4.0, (0, 0, 10, 2))]
    assert comparar_elementos(antes, despues, 1.0, 1.0) == []
