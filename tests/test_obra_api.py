"""Los convenios cambian lo contratado, y la estimación que sigue debe saberlo.

La lógica de cada módulo ya se prueba aparte; lo que se prueba aquí es la
costura, que es donde un contrato modificado se queda a medias: si la
estimación siguiente sigue leyendo el catálogo original, va a marcar como
excedido algo que ya se convino, y el aviso que sí importa se pierde entre los
que ya no."""

import json

import pytest
from klave_engine.common import config as config_module


@pytest.fixture
def client(data_dir, monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    config_module.get_settings.cache_clear()
    return TestClient(create_app())


def _proyecto(data_dir) -> str:
    """Un proyecto mínimo en disco: los artefactos de obra no salen del plano."""
    pid = "obra-test"
    root = data_dir / "projects" / pid
    (root / "processed").mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps({"project_id": pid, "project_name": "Obra de prueba", "drawings": []})
    )
    (data_dir / "projects_registry.json").write_text(json.dumps({pid: str(root)}))
    return pid


def _escribir(data_dir, pid: str, nombre: str, datos: object) -> None:
    (data_dir / "projects" / pid / "processed" / nombre).write_text(json.dumps(datos))


ESTIMACION_1 = {
    "numero": 1,
    "periodo_inicio": "2026-01-01",
    "periodo_fin": "2026-01-31",
    "monto_contrato": 50_000.0,
    "anticipo_pct": 30.0,
    "retencion_pct": 5.0,
    "renglones": [
        {
            "clave": "OP-001", "description": "Muro de tabique", "unit": "m2",
            "unit_price": 500.0, "quantity_period": 100.0, "quantity_previous": 0.0,
            "quantity_contract": 100.0,
        }
    ],
}


def test_la_estimacion_siguiente_lee_el_catalogo_ya_convenido(client, data_dir):
    pid = _proyecto(data_dir)
    _escribir(data_dir, pid, "estimaciones.json", [ESTIMACION_1])
    _escribir(data_dir, pid, "catalogo_convocante.json",
              {"renglones": [{"clave": "OP-001", "quantity": 100.0, "unit_price": 500.0}]})

    # Sin convenio: lo contratado sigue siendo 100.
    sin = client.post(f"/projects/{pid}/estimaciones/siguiente",
                      params={"inicio": "2026-02-01", "fin": "2026-02-28"})
    assert sin.status_code == 200, sin.text
    assert sin.json()["estimacion"]["renglones"][0]["quantity_contract"] == 100.0

    conv = client.put(f"/projects/{pid}/convenios/1", json={"convenio": {
        "numero": 1, "fecha": "2026-02-05", "motivo": "Ampliación de fachada",
        "renglones": [{
            "clave": "OP-001", "description": "Muro de tabique", "unit": "m2",
            "unit_price": 500.0, "quantity": 120.0, "quantity_anterior": 100.0,
        }],
    }})
    assert conv.status_code == 200, conv.text

    con = client.post(f"/projects/{pid}/estimaciones/siguiente",
                      params={"inicio": "2026-02-01", "fin": "2026-02-28"})
    renglon = con.json()["estimacion"]["renglones"][0]
    assert renglon["quantity_contract"] == 120.0
    # Y el monto del contrato crece con lo convenido, para amortizar bien:
    # 50 000 del catálogo más 10 000 del convenio.
    assert con.json()["estimacion"]["monto_contrato"] == 60_000.0


def test_un_concepto_que_entra_por_convenio_aparece_en_la_estimacion(client, data_dir):
    pid = _proyecto(data_dir)
    _escribir(data_dir, pid, "estimaciones.json", [ESTIMACION_1])
    client.put(f"/projects/{pid}/convenios/1", json={"convenio": {
        "numero": 1, "fecha": "2026-02-05", "motivo": "Concepto no previsto",
        "renglones": [{
            "clave": "OP-050", "description": "Impermeabilizante", "unit": "m2",
            "unit_price": 200.0, "quantity": 80.0, "quantity_anterior": 0.0,
        }],
    }})
    est = client.post(f"/projects/{pid}/estimaciones/siguiente",
                      params={"inicio": "2026-02-01", "fin": "2026-02-28"}).json()

    nuevo = [r for r in est["estimacion"]["renglones"] if r["clave"] == "OP-050"]
    assert len(nuevo) == 1
    assert nuevo[0]["quantity_contract"] == 80.0
    # Entra en cero: existe en el contrato, pero nadie lo ha medido todavía.
    assert nuevo[0]["quantity_period"] == 0.0


def test_el_techo_del_articulo_59_sale_en_el_estado(client, data_dir):
    pid = _proyecto(data_dir)
    _escribir(data_dir, pid, "catalogo_convocante.json",
              {"renglones": [{"clave": "OP-001", "quantity": 100.0, "unit_price": 500.0}]})
    client.put(f"/projects/{pid}/convenios/1", json={"convenio": {
        "numero": 1, "fecha": "2026-02-05",
        "renglones": [{
            "clave": "OP-001", "description": "Muro", "unit": "m2",
            "unit_price": 500.0, "quantity": 140.0, "quantity_anterior": 100.0,
        }],
    }})
    estado = client.get(f"/projects/{pid}/convenios").json()["estado"]

    assert estado["monto_original"] == 50_000.0
    assert estado["monto_convenido"] == 20_000.0
    assert estado["monto_pct"] == 40.0
    assert estado["rebasa_techo"] is True
    assert any("art. 59" in a for a in estado["avisos"])


def test_el_borrador_de_convenio_no_se_inventa_cuando_no_hay_excedente(client, data_dir):
    pid = _proyecto(data_dir)
    _escribir(data_dir, pid, "estimaciones.json", [ESTIMACION_1])
    r = client.post(f"/projects/{pid}/convenios/desde-estimacion/1",
                    params={"fecha": "2026-02-05"})
    assert r.status_code == 409
    assert r.json()["detail"]["error_type"] == "sin_excedentes"


def test_el_borrador_toma_lo_ejecutado_como_nueva_cantidad(client, data_dir):
    pid = _proyecto(data_dir)
    excedida = json.loads(json.dumps(ESTIMACION_1))
    excedida["renglones"][0]["quantity_period"] = 130.0
    _escribir(data_dir, pid, "estimaciones.json", [excedida])

    conv = client.post(f"/projects/{pid}/convenios/desde-estimacion/1",
                       params={"fecha": "2026-02-05"}).json()["convenio"]
    assert conv["renglones"][0]["quantity"] == 130.0
    assert conv["renglones"][0]["quantity_anterior"] == 100.0
    assert conv["motivo"] == ""


def test_el_finiquito_se_precarga_de_las_estimaciones_capturadas(client, data_dir):
    pid = _proyecto(data_dir)
    _escribir(data_dir, pid, "estimaciones.json", [ESTIMACION_1])
    _escribir(data_dir, pid, "catalogo_convocante.json",
              {"renglones": [{"clave": "OP-001", "quantity": 100.0, "unit_price": 500.0}]})

    cuerpo = client.get(f"/projects/{pid}/finiquito").json()
    assert cuerpo["guardado"] is False
    fin = cuerpo["finiquito"]
    assert fin["ejecutado"] == 50_000.0
    assert fin["retenciones_aplicadas"] == 2_500.0
    # Lo que el motor no puede saber nace en cero y a la vista.
    assert fin["dias_atraso"] == 0
    assert fin["pena_pct_diario"] == 0.0
    assert any("garantía" in s["concepto"] for s in cuerpo["resumen"]["saldos"])
    # Los derivados viajan calculados: la pantalla no debe volver a deducir el
    # signo por su cuenta.
    assert cuerpo["resumen"]["a_favor_de"] == "contratista"
    assert cuerpo["resumen"]["saldos"][0]["a_favor"] == "contratista"


def test_borrar_un_convenio_que_no_existe_es_404(client, data_dir):
    pid = _proyecto(data_dir)
    assert client.delete(f"/projects/{pid}/convenios/7").status_code == 404


def test_sin_catalogo_cargado_el_convenio_no_borra_el_monto_capturado(client, data_dir):
    """No todos los proyectos cargaron el catálogo de la convocante.

    Sin ese respaldo manda lo que se capturó a mano: tomar cero de un catálogo
    ausente dejaría el contrato por los suelos y la amortización del anticipo
    saldría mal, sin que nadie lo notara."""
    pid = _proyecto(data_dir)
    _escribir(data_dir, pid, "estimaciones.json", [ESTIMACION_1])
    client.put(f"/projects/{pid}/convenios/1", json={"convenio": {
        "numero": 1, "fecha": "2026-02-05",
        "renglones": [{
            "clave": "OP-001", "description": "Muro", "unit": "m2",
            "unit_price": 500.0, "quantity": 120.0, "quantity_anterior": 100.0,
        }],
    }})
    est = client.post(f"/projects/{pid}/estimaciones/siguiente",
                      params={"inicio": "2026-02-01", "fin": "2026-02-28"}).json()
    assert est["estimacion"]["monto_contrato"] == 60_000.0
