"""La referencia de un elemento: id estable, ejes sólo si el plano los nombra,
planta del marco, y la liga al visor."""

from klave_engine.costing.referencias import ejes_cercanos, element_id, referencias
from klave_engine.detection.results import DetectionType, make_detection


def _det(det_id, kind, bbox, props=None, label="", source="e.dxf"):
    det = make_detection(det_id, kind, "L", bbox, 0.9, [det_id], "m", [], props or {}, source)
    return det.model_copy(update={"label": label or det.label})


def _grid(det_id, label, axis, coord, src="auto_no"):
    if axis == "vertical":
        bbox = (coord, 0, coord, 20)
    else:
        bbox = (0, coord, 20, coord)
    return _det(det_id, DetectionType.grid_line, bbox,
                {"axis": axis, "coordinate": coord, "label_source": src}, label=label)


def test_element_id_is_stable_and_position_sensitive():
    a = _det("x1", DetectionType.column_tag, (1.0, 1.0, 1.4, 1.4))
    b = _det("x2", DetectionType.column_tag, (1.01, 1.0, 1.41, 1.4))  # 1 cm
    c = _det("x3", DetectionType.column_tag, (3.0, 1.0, 3.4, 1.4))
    assert element_id(a, 1.0) == element_id(b, 1.0)
    assert element_id(a, 1.0) != element_id(c, 1.0)
    assert element_id(a, 1.0).startswith("el_")


def test_ejes_only_when_the_drawing_named_them():
    col = _det("c", DetectionType.column_tag, (4.8, 9.8, 5.2, 10.2))
    named = [_grid("g1", "B", "vertical", 5.0, "texto"), _grid("g2", "3", "horizontal", 10.0,
                                                                "texto")]
    assert ejes_cercanos(col, named, 1.0) == "B / 3"
    auto = [_grid("g3", "V1", "vertical", 5.0, "auto")]
    assert ejes_cercanos(col, auto, 1.0) == ""
    far = [_grid("g4", "C", "vertical", 9.0, "texto")]
    assert ejes_cercanos(col, far, 1.0) == ""


def test_referencias_carry_sheet_and_visor_link():
    col = _det("c", DetectionType.column_tag, (4.8, 9.8, 5.2, 10.2), source="planos/E-01.dxf")
    refs = referencias("obra 1", [col], None, 1.0)
    ref = refs["c"]
    assert ref.hoja == "E-01" and ref.planta == ""
    assert ref.visor == "/proyecto/obra%201/plano?bbox=4.8,9.8,5.2,10.2"
