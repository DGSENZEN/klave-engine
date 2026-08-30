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


def _cost_report_declarado(pid: str) -> dict:
    """Un cost_report.json completo, modo declarado puro: los cinco
    componentes de la integración por porcentaje, ni un análisis detrás.
    Construido con los modelos reales (no a mano) para que el esquema que
    CostReport.model_validate exige no se desalinee con lo que se escribe."""
    from klave_engine.costing.integration import integrate_costs, resolve_integration
    from klave_engine.costing.models import (
        BillOfQuantities,
        CostingConfig,
        CostReport,
        FinancialPlan,
        IndirectsConfig,
        WorkSchedule,
    )
    from klave_engine.dxf.units import DrawingUnits

    direct_cost = 1_000_000.0
    resolved = resolve_integration(CostingConfig(), None, direct_cost, None, None)
    integration = integrate_costs(direct_cost, IndirectsConfig(), resolved=resolved)
    report = CostReport(
        project_id=pid,
        currency="MXN",
        drawing_units=DrawingUnits(unit="m", source="dxf_header", confidence=0.9),
        boq=BillOfQuantities(project_id=pid, direct_cost_total=direct_cost),
        apus=[],
        integration=integration,
        schedule=WorkSchedule(
            activities=[], total_duration_days=0, workdays_per_month=24, phases=[]
        ),
        financial=FinancialPlan(
            advance_payment_pct=0.0, retention_pct=0.0, advance_payment=0.0,
            total_retention=0.0, periods=[], operating_projection=[],
            annual_operating_cost=0.0,
        ),
        integracion_resuelta=resolved,
    )
    return report.model_dump(mode="json")


def test_export_licitacion_bloquea_por_declarado_y_motivo_desbloquea(data_dir, monkeypatch):
    """El 409 de la licitación por porcentaje declarado, a nivel ruta: sin
    motivo se bloquea con las cuatro fuentes declaradas (la utilidad nunca
    bloquea), con motivo pasa, y el formato klave nunca lo exige."""
    client = _client(monkeypatch)
    pid = _proyecto(data_dir)
    _escribir(data_dir, pid, "cost_report.json", _cost_report_declarado(pid))
    _escribir(data_dir, pid, "detections.json", [])

    bloqueado = client.get(f"/projects/{pid}/export/presupuesto.xlsx?format=licitacion")
    assert bloqueado.status_code == 409, bloqueado.text
    detail = bloqueado.json()["detail"]
    assert detail["error_type"] == "export_blocked"
    assert any("porcentaje declarado" in b for b in detail["bloqueantes"])
    assert not any("(UT)" in b for b in detail["bloqueantes"])

    desbloqueado = client.get(
        f"/projects/{pid}/export/presupuesto.xlsx",
        params={"format": "licitacion", "motivo": "anteproyecto interno, no va a concurso"},
    )
    assert desbloqueado.status_code == 200, desbloqueado.text

    klave = client.get(f"/projects/{pid}/export/presupuesto.xlsx?format=klave")
    assert klave.status_code == 200, klave.text


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
