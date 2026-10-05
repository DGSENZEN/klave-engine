"""El siguiente paso del camino de v1: el primero que falta, uno solo."""

from apps.api.routes.tablero import _lo_que_sigue

BASE = dict(status="processed", sheet_count=3, has_reading=True, units_ok=True,
            units_reliable=True, detections_ok=True, lines=[], sin_precio=0, has_report=True)


def _step(**over):
    return _lo_que_sigue(**{**BASE, **over})["accion"]


def test_the_path_in_order():
    assert _step(sheet_count=0) == "subir"
    assert _step(status="running") == "esperar"
    assert _step(status="failed") == "lectura"
    assert _step(has_report=False) == "procesar"
    assert _step(units_ok=False) == "unidades"
    assert _step(units_reliable=False) == "unidades"
    assert _step(detections_ok=False) == "revisar"
    pending = [{"variants": [{"mapping": ""}, {"mapping": "confirmada"}]}]
    assert _step(lines=pending) == "mapear"
    assert "1 de 2" in _lo_que_sigue(**{**BASE, "lines": pending})["detail"]
    assert _step(sin_precio=2) == "precio"
    assert _step() == "exportar"
    # Una propuesta todavía espera a una persona; automáticas y «sin equivalente» no.
    done = [{"variants": [{"mapping": "automatica"}, {"mapping": "sin_equivalente"}]}]
    assert _step(lines=done) == "exportar"
    assert _step(lines=[{"variants": [{"mapping": "propuesta"}]}]) == "mapear"
