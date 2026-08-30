"""La captura del taller (oficina central + financiamiento) por la API."""

import json

from klave_engine.common import config as config_module


def _client(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    config_module.get_settings.cache_clear()
    return TestClient(create_app())


def _proyecto(data_dir) -> str:
    """Un proyecto mínimo en disco: los artefactos de obra no salen del plano.

    Mismo patrón que tests/test_obra_api.py::_proyecto — un projects_registry.json
    y un project_manifest.json bastan para que la API lo reconozca."""
    pid = "integracion-test"
    root = data_dir / "projects" / pid
    (root / "processed").mkdir(parents=True, exist_ok=True)
    (root / "processed" / "project_manifest.json").write_text(
        json.dumps({
            "project_id": pid, "project_name": "Obra de prueba",
            "root_path": str(root), "drawings": [],
        })
    )
    (data_dir / "projects_registry.json").write_text(json.dumps({pid: str(root)}))
    return pid


def _escribir(data_dir, pid: str, nombre: str, datos: object) -> None:
    (data_dir / "projects" / pid / "processed" / nombre).write_text(json.dumps(datos))


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


def test_costing_config_sin_reporte_trae_integracion_vacia(data_dir, monkeypatch):
    """Un proyecto que existe pero todavía no tiene cost_report.json: la
    configuración se ve completa igual, sólo que sin fuentes que enseñar."""
    client = _client(monkeypatch)
    pid = _proyecto(data_dir)
    resp = client.get(f"/projects/{pid}/costing-config")
    assert resp.status_code == 200, resp.text
    assert resp.json()["integracion"] == []


def test_costing_config_con_reporte_trae_las_fuentes(data_dir, monkeypatch):
    """Con un cost_report.json ya escrito, cada componente resuelto aparece
    con exactamente code/pct/amount/fuente/faltantes — lo que consume el web."""
    client = _client(monkeypatch)
    pid = _proyecto(data_dir)
    _escribir(data_dir, pid, "cost_report.json", {
        "integracion_resuelta": [
            {
                "code": "CI-C", "amount": 123456.78, "pct": 8.5,
                "fuente": "analisis",
                "documento": {"total": 123456.78},
                "faltantes": [],
            },
            {
                "code": "FI", "amount": None, "pct": 3.2,
                "fuente": "declarado",
                "documento": {},
                "faltantes": ["tasa", "indicador"],
            },
        ],
    })
    resp = client.get(f"/projects/{pid}/costing-config")
    assert resp.status_code == 200, resp.text
    assert resp.json()["integracion"] == [
        {"code": "CI-C", "pct": 8.5, "amount": 123456.78, "fuente": "analisis",
         "faltantes": []},
        {"code": "FI", "pct": 3.2, "amount": None, "fuente": "declarado",
         "faltantes": ["tasa", "indicador"]},
    ]
