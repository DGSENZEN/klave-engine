"""El vector de rasgos de un elemento: medidas en metros, contexto del plano,
fichas de texto, y nunca coordenadas absolutas."""

import pytest
from klave_engine.detection.features import Contexto, features, tokens
from klave_engine.detection.results import DetectionType, make_detection


def _det(det_id, kind, bbox, props=None, mark="", source="e.dxf"):
    d = make_detection(det_id, kind, "L", bbox, 0.9, [det_id], "regla", [], props or {}, source)
    return d.model_copy(update={"mark": mark})


def test_tokens_fold_accents_and_split():
    assert tokens("EST-COLUMNAS_Ñ") == ["est", "columnas", "n"]
    assert tokens("") == []


def test_features_in_metres_with_context_and_no_coordinates():
    cruce = _det("g", DetectionType.grid_intersection, (1000, 1000, 1000, 1000))
    col = _det("c", DetectionType.column_tag, (1100, 1000, 1400, 1400),
               {"section_area_du2": 120000.0, "layer": "EST-COL", "section_source": "cuadro"},
               mark="K-12")
    otra = _det("c2", DetectionType.column_tag, (5000, 0, 5300, 400), mark="K-12")
    ctx = Contexto.de([cruce, col, otra], 0.001)  # milímetros
    f = features(col, ctx)
    assert f["ancho_m"] == pytest.approx(0.3) and f["alto_m"] == pytest.approx(0.4)
    assert f["seccion_m2"] == pytest.approx(0.12)
    assert f["prefijo_marca"] == "K" and f["repeticion_marca"] == 2
    assert f["dist_eje_m"] == pytest.approx(0.32)  # centro (1250,1200) a (1000,1000)
    assert f["capa_tokens"] == ["est", "col"] and f["section_source"] == "cuadro"
    assert not any(isinstance(v, float) and v > 1000 for v in f.values())  # sin coordenadas
