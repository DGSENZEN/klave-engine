"""El dibujo de una corrida se arma una vez: misma respuesta, coordenadas a
cuatro decimales, ETag que ahorra la descarga, una hoja a la vez, y la
respuesta comprimida."""

import json

from tests.test_variantes_api import _project


def _client(monkeypatch):
    from fastapi.testclient import TestClient
    from klave_engine.common import config as config_module

    from apps.api.main import create_app

    config_module.get_settings.cache_clear()
    return TestClient(create_app())


def _entities(n=400):
    out = []
    for i in range(n):
        out.append({
            "entity_id": f"e{i}", "entity_type": "line", "layer": "MUROS" if i % 2 else "EJES",
            "bbox": [i * 1.123456789, 0.0, i * 1.123456789 + 1, 1.0],
            "points": [[i * 1.123456789, 0.0], [i * 1.123456789 + 1.0000004, 1.0]],
            "properties": {}, "source_file": "e.dxf",
        })
    return out


def test_cached_rounded_etag_sheet_and_gzip(data_dir, monkeypatch):
    pid, processed = _project(data_dir)
    (processed / "normalized_entities.json").write_text(json.dumps(_entities()))
    client = _client(monkeypatch)

    first = client.get(f"/projects/{pid}/geometry")
    assert first.status_code == 200, first.text
    second = client.get(f"/projects/{pid}/geometry")
    assert first.json() == second.json()
    shape = first.json()["shapes"][3]
    assert shape["pts"][0] == [round(3 * 1.123456789, 4), 0.0]
    assert len(first.json()["detections"]) == 3

    shapes = client.get(f"/projects/{pid}/geometry/shapes")
    etag = shapes.headers["etag"]
    assert "detections" not in shapes.json() and len(shapes.json()["shapes"]) == 400
    again = client.get(f"/projects/{pid}/geometry/shapes", headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.content == b""

    # Una revisión mueve el veredicto sin rearmar el dibujo.
    client.put(f"/projects/{pid}/reviews/detections/c0", json={"status": "excluded"})
    dets = client.get(f"/projects/{pid}/geometry/detections").json()["detections"]
    assert next(d for d in dets if d["id"] == "c0")["review"] == "excluded"
    assert client.get(f"/projects/{pid}/geometry/shapes",
                      headers={"If-None-Match": etag}).status_code == 304

    gz = client.get(f"/projects/{pid}/geometry", headers={"Accept-Encoding": "gzip"})
    assert gz.headers.get("content-encoding") == "gzip"

    # Un reproceso cambia el archivo: la caché no sirve el dibujo viejo.
    (processed / "normalized_entities.json").write_text(json.dumps(_entities(10)))
    assert len(client.get(f"/projects/{pid}/geometry/shapes").json()["shapes"]) == 10
    assert client.get(f"/projects/{pid}/geometry?sheet=99").json()["shapes"] == []
