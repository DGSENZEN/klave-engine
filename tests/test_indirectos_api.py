"""La captura del taller (oficina central + financiamiento) por la API."""

from klave_engine.common import config as config_module


def _client(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    config_module.get_settings.cache_clear()
    return TestClient(create_app())


def test_integracion_roundtrip(data_dir, monkeypatch):
    client = _client(monkeypatch)
    vacio = client.get("/catalog/integracion").json()
    assert vacio == {"oficina": {}, "financiamiento": {}}

    body = {
        "oficina": {
            "rubros": [{"concepto": "Renta de oficina", "categoria": "gastos_oficina",
                        "importe": 600000.0}],
            "volumen_anual_contratado": 40000000.0,
        },
        "financiamiento": {
            "tasa_anual": 12.0, "indicador": "TIIE 28 días",
            "fuente": "Banxico SF43783", "fecha_publicacion": "2026-08-27",
        },
    }
    saved = client.put("/catalog/integracion", json=body)
    assert saved.status_code == 200, saved.text
    stored = client.get("/catalog/integracion").json()
    assert stored["oficina"]["volumen_anual_contratado"] == 40000000.0
    assert stored["financiamiento"]["indicador"] == "TIIE 28 días"


def test_integracion_rechaza_basura(data_dir, monkeypatch):
    client = _client(monkeypatch)
    malo = client.put("/catalog/integracion", json={
        "oficina": {"volumen_anual_contratado": "mucho"}, "financiamiento": {}})
    assert malo.status_code == 422
