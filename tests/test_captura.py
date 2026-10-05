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
    assert out.total == 4
