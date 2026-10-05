"""Lo que el plano no dio: vistos sin cantidad, renglones sin precio y hojas
sin lectura — contados, nunca en silencio."""

from klave_engine.costing.captura import lo_que_el_plano_no_dio
from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    CostReport,
    QuantityKind,
)
from klave_engine.costing.reviews import DetectionReview, ProjectReviews
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.dxf.units import DrawingUnits


def _det(i, kind, source="e.dxf", props=None):
    d = make_detection(f"d{i}", kind, "L", (i, 0, i + 1, 1), 0.9, [f"d{i}"], "m", [],
                       props or {}, source)
    return d.model_copy(update={"mark": f"K-{i}", "family_label": "Castillos"
                                if kind == DetectionType.column_tag else "Zapatas"})


def _report(lines):
    return CostReport.model_construct(
        project_id="p", boq=BillOfQuantities(project_id="p", lines=lines),
        drawing_units=DrawingUnits(unit="m", source="declared", confidence=1.0),
    )


def test_lists_unconsumed_unpriced_and_unread():
    dets = [
        _det(1, DetectionType.column_tag), _det(2, DetectionType.column_tag),
        _det(3, DetectionType.column_tag, props={"role": "cuadro"}),
        _det(4, DetectionType.grid_line), _det(5, DetectionType.footing),
        _det(6, DetectionType.footing),
    ]
    line = BoqLine(
        concept_code="EST-001", description="Columnas", unit="M3", quantity=1.0,
        unit_price=0.0, amount=0.0, phase="Estructura", raw_quantity=1.0,
        raw_kind=QuantityKind.COUNT, source_detection_count=1, source_detections=["d1"],
        confidence=0.9, unpriced=True,
    )
    reviews = ProjectReviews(detections={"d6": DetectionReview(status="excluded")})
    inventory = {"sheets": [
        {"sheet": "e.dxf", "label": "E-01.dwg", "discipline": "estructural"},
        {"sheet": "el.dxf", "label": "IE-01.dwg", "discipline": "electrica"},
        {"sheet": "i.dxf", "label": "INDICE.dwg", "discipline": "indice"},
    ]}
    out = lo_que_el_plano_no_dio(_report([line]), dets, reviews, inventory)
    fams = {v.familia: v for v in out.vistos_sin_cantidad}
    assert fams["Castillos"].cantidad == 1 and fams["Castillos"].marcas == ["K-2"]
    assert fams["Zapatas"].cantidad == 1  # la zapata excluida no cuenta
    assert [s.descripcion for s in out.sin_precio] == ["Columnas"]
    assert [h.hoja for h in out.hojas_sin_lectura] == ["IE-01.dwg"]
    assert out.total == 4 + len(out.esperado_y_ausente)


def _linea(code, qty, desc="", unit="M3"):
    return BoqLine(
        concept_code=code, description=desc or code, unit=unit, quantity=qty, unit_price=0.0,
        amount=0.0, phase="Estructura", raw_quantity=qty, raw_kind=QuantityKind.COUNT,
        source_detection_count=1, confidence=0.9,
    )


def test_esperado_y_ausente_reads_scope_per_line():
    from klave_engine.costing.completitud import esperado_y_ausente

    boq = BillOfQuantities(project_id="p", lines=[
        _linea("CIM-002", 10.0, "Concreto en zapatas, incluye acero, cimbra y plantilla"),
        _linea("EST-001", 5.0, "Columnas de concreto armado"),
        _linea("EST-003", 50.0, "Losa armada con varilla del no. 3", "M2"),
        _linea("CIM-001", 30.0, "Excavación"),
        _linea("EST-004", 200.0, "Muro de block", "M2"),
    ])
    ids = {a.id: a for a in esperado_y_ausente(boq, plantas=2)}
    # Las zapatas traen su acero, cimbra y plantilla; las columnas no traen acero
    # aunque la losa diga «varilla»: el acero de una losa no arma columnas.
    assert "plantilla" not in ids and "cimbra-zapatas" not in ids
    assert "acero" in ids and "Columnas" in ids["acero"].evidencia
    assert {"relleno", "acarreo", "aplanado", "cadenas", "cimbra-columnas", "escalera"} <= set(ids)
    assert "castillos" not in ids  # EST-001 está
    # Con el renglón de acero aparte, ya no falta.
    boq.lines.append(_linea("ACE-001", 1.2, "Acero de refuerzo fy=4200", "TON"))
    assert "acero" not in {a.id for a in esperado_y_ausente(boq, plantas=1)}
    assert "escalera" not in {a.id for a in esperado_y_ausente(boq, plantas=1)}
