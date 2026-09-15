"""Los endpoints de generación y validación: generar una matriz, generar las
que faltan, validar, la tolerancia del taller y las plantillas a la vista;
el análisis y el estado del catálogo llevan la fuente de cada línea."""

import sqlite3

import pytest
from klave_engine.common import config as config_module
from klave_engine.costing.catalog_store import get_catalog_store


@pytest.fixture
def client(data_dir):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    store = get_catalog_store(data_dir)
    conn = sqlite3.connect(store.db_path)
    conn.execute(
        "INSERT INTO concepts (code, description, unit, phase, production_rate_per_day, "
        "sequence_order, origin) VALUES ('COL-API', "
        "'Columnas de concreto armado f''c=250 kg/cm² de 30x40 cm', 'M3', 'Estructura', 1.0, "
        "900, 'taller')"
    )
    conn.commit()
    conn.close()
    config_module.get_settings.cache_clear()
    return TestClient(create_app())


def test_generate_validate_and_tolerance_endpoints(client):
    generated = client.post(
        "/catalog/concepts/COL-API/generar", json={}, headers={"X-Actor": "Diego"}
    )
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["plantilla"] == "concreto-armado-m3" and body["lines"] >= 8
    assert body["validation"]["verdict"] == "sin_referencia"
    # Volver a generar sin force sobre una matriz generada está permitido;
    # sobre una del taller (tras editar) pide confirmación.
    assert client.post("/catalog/concepts/COL-API/generar", json={}).status_code == 200
    apu = client.get("/catalog/apus/COL-API").json()
    conc = next(line for line in apu["lines"] if line["resource_code"] == "MAT-CONC250")
    assert "desperdicio" in conc["source"]
    state = client.get("/catalog").json()
    component = next(c for c in state["apus"]["COL-API"] if c["resource_code"] == "MAT-CONC250")
    assert component["source"] == conc["source"]
    concept = next(c for c in state["concepts"] if c["code"] == "COL-API")
    assert concept["origin"] == "generada" and concept["validation"]["verdict"] == "sin_referencia"
    edited = client.put(
        "/catalog/apus/COL-API",
        json={"components": [{"resource_code": "MAT-CONC250", "quantity": 1.1}]},
        headers={"X-Actor": "Diego"},
    )
    assert edited.status_code == 200
    refused = client.post("/catalog/concepts/COL-API/generar", json={})
    assert refused.status_code == 409 and "matriz del taller" in refused.json()["detail"]["message"]
    assert client.post("/catalog/concepts/COL-API/generar", json={"force": True}).status_code == 200
    validated = client.post("/catalog/concepts/COL-API/validar")
    assert validated.status_code == 200 and validated.json()["verdict"] == "sin_referencia"
    assert client.get("/catalog/matrices/validacion").json()["tolerance_pct"] == 15.0
    saved = client.put("/catalog/matrices/validacion", json={"tolerance_pct": 10})
    assert saved.status_code == 200 and saved.json()["tolerance_pct"] == 10.0
    assert client.put("/catalog/matrices/validacion", json={"tolerance_pct": 0}).status_code == 422
    summary = client.post("/catalog/matrices/validar")
    assert summary.status_code == 200 and summary.json()["validated"] >= 1
    missing = client.post("/catalog/matrices/generar-faltantes", headers={"X-Actor": "Diego"})
    assert missing.status_code == 200
    assert {"generated", "skipped"} <= set(missing.json())
    plantillas = client.get("/catalog/matrices/plantillas").json()["plantillas"]
    assert any(p["key"] == "concreto-armado-m3" for p in plantillas)
    assert all(line["source"] for p in plantillas for line in p["lines"])
    assert client.post("/catalog/concepts/NO-EXISTE/generar", json={}).status_code == 404
